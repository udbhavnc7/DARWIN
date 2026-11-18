"""Safe, read-only retrieval and commit pinning for public GitHub repositories.

Real Project Mode never executes repository code during import. This module only
validates the URL/ref, resolves an exact commit, downloads a bounded read-only
checkout with Git's own transport, and records provenance. Lifecycle hooks and
package scripts are never invoked here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import ssl
import stat
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from uuid import uuid4

try:
    import certifi
except ImportError:
    certifi = None

from darwin.repository_catalog import catalog_entry, canonical_repository

GITHUB_HOST = 'github.com'
MAX_URL_LENGTH = 300
MAX_REPOSITORY_KB = 250_000  # 250 MB source archive/checkout ceiling.
MAX_CHECKOUT_FILES = 40_000
MAX_CHECKOUT_BYTES = 350 * 1024 * 1024
SHA_RE = re.compile(r'^[a-f0-9]{40}$')
OWNER_RE = re.compile(r'^[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,38})$')
NAME_RE = re.compile(r'^[A-Za-z0-9_.-]{1,100}$')
REF_RE = re.compile(r'^[A-Za-z0-9._/-]{1,100}$')


class RepositoryError(ValueError):
    """A safe, user-actionable import failure."""

    def __init__(self, message: str, code: str = 'invalid_repository', status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


@dataclass(frozen=True)
class GitHubRepository:
    owner: str
    name: str
    url: str


def validate_repository_url(value: str) -> GitHubRepository:
    if not isinstance(value, str):
        raise RepositoryError('Enter a public GitHub repository URL.')
    url = value.strip()
    if not url:
        raise RepositoryError('Enter a public GitHub repository URL.')
    if len(url) > MAX_URL_LENGTH:
        raise RepositoryError('That repository URL is too long.')
    if any(ord(ch) < 32 for ch in url) or '\\' in url or '%' in url:
        raise RepositoryError('That repository URL contains unsupported characters.')
    if url.startswith(('http://', 'git://', 'ssh://', 'file://')):
        raise RepositoryError('Only HTTPS GitHub repository URLs are supported.', 'unsupported_scheme')
    if not url.lower().startswith('https://'):
        raise RepositoryError('Only HTTPS GitHub repository URLs are supported.', 'unsupported_scheme')
    if '@' in url:
        raise RepositoryError('Credentials are not allowed in repository URLs.', 'credentials_rejected')
    from urllib.parse import urlsplit

    parts = urlsplit(url)
    if parts.scheme.lower() != 'https' or (parts.hostname or '').lower() != GITHUB_HOST:
        raise RepositoryError('Only github.com repository URLs are supported.', 'unsupported_host')
    if parts.port not in (None, 443):
        raise RepositoryError('Repository URLs must not specify a port.')
    if parts.query or parts.fragment:
        raise RepositoryError('Repository URLs must not include a query or fragment.')
    segments = [segment for segment in parts.path.split('/') if segment]
    if len(segments) != 2:
        raise RepositoryError('Use a repository URL in the form https://github.com/owner/repo.')
    owner, name = segments
    if name.lower().endswith('.git'):
        name = name[:-4]
    if owner in ('.', '..') or name in ('.', '..') or not owner or not name:
        raise RepositoryError('That repository path is not valid.')
    if owner.startswith('-') or name.startswith('-'):
        raise RepositoryError('That repository path is not valid.')
    if not OWNER_RE.fullmatch(owner) or not NAME_RE.fullmatch(name):
        raise RepositoryError('That GitHub owner or repository name is not valid.')
    canonical = f'https://{GITHUB_HOST}/{owner}/{name}'
    return GitHubRepository(owner=owner, name=name, url=canonical)


def validate_ref(value: str | None) -> str:
    ref = (value or 'main').strip()
    if not REF_RE.fullmatch(ref):
        raise RepositoryError('That branch or tag name is not valid.', 'invalid_ref')
    if ref.startswith('-') or ref.startswith('/') or ref.endswith('/') or ref.endswith('.'):
        raise RepositoryError('That branch or tag name is not valid.', 'invalid_ref')
    if '..' in ref or '//' in ref or '@{' in ref or ref.endswith('.lock'):
        raise RepositoryError('That branch or tag name is not valid.', 'invalid_ref')
    return ref


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class GitClient:
    """Narrow Git wrapper with prompts, hooks and inherited secrets disabled."""

    def __init__(self, timeout: int = 120):
        self.timeout = timeout
        self.git = shutil.which('git')
        if not self.git:
            raise RepositoryError(
                'Git is not installed. Install Git to inspect a repository, or use the trusted Sanchay example cache.',
                'git_unavailable', 503,
            )

    def environment(self) -> dict:
        keep = ('PATH', 'SystemRoot', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'HOME',
                'USERPROFILE', 'ComSpec', 'PATHEXT', 'LANG', 'LC_ALL')
        env = {key: os.environ[key] for key in keep if key in os.environ}
        env.update({
            'GIT_TERMINAL_PROMPT': '0',
            'GIT_ASKPASS': 'echo',
            'GIT_CONFIG_NOSYSTEM': '1',
            'GIT_CONFIG_GLOBAL': os.devnull,
            'GIT_LFS_SKIP_SMUDGE': '1',
            'GIT_HTTP_LOW_SPEED_LIMIT': '1000',
            'GIT_HTTP_LOW_SPEED_TIME': '30',
        })
        return env

    def run(self, args: list[str], cwd: Path | None = None, timeout: int | None = None) -> str:
        command = [self.git, *args]
        try:
            completed = subprocess.run(
                command, cwd=str(cwd) if cwd else None, env=self.environment(),
                capture_output=True, text=True, encoding='utf-8', errors='replace',
                timeout=timeout or self.timeout, check=False,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
            )
        except subprocess.TimeoutExpired as exc:
            raise RepositoryError('Git timed out while contacting GitHub.', 'git_timeout', 504) from exc
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or '').strip().splitlines()
            reason = detail[-1] if detail else f'Git exited with code {completed.returncode}'
            raise RepositoryError(f'Git could not retrieve the repository: {reason}', 'git_failed', 502)
        return completed.stdout.strip()

    def resolve(self, url: str, ref: str) -> str:
        if SHA_RE.fullmatch(ref.lower()):
            return ref.lower()
        patterns = [f'refs/heads/{ref}', f'refs/tags/{ref}', f'refs/tags/{ref}^{{}}']
        output = self.run(['ls-remote', '--heads', '--tags', url, *patterns], timeout=45)
        found: dict[str, str] = {}
        for line in output.splitlines():
            parts = line.split('\t')
            if len(parts) == 2 and SHA_RE.fullmatch(parts[0].lower()):
                found[parts[1]] = parts[0].lower()
        for key in (f'refs/tags/{ref}^{{}}', f'refs/heads/{ref}', f'refs/tags/{ref}'):
            if key in found:
                return found[key]
        raise RepositoryError(
            f'The branch or tag “{ref}” was not found in that public repository.',
            'ref_not_found', 404,
        )

    def checkout(self, url: str, ref: str, sha: str, target: Path,
                 sparse_paths: list[str] | None = None) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.parent / f'.tmp-{uuid4().hex}'
        hooks = target.parent / '.hooks-disabled'
        hooks.mkdir(parents=True, exist_ok=True)
        try:
            temporary.mkdir()
            self.run(['init', '-q', str(temporary)])
            self.run(['-C', str(temporary), 'config', 'core.hooksPath', str(hooks)])
            self.run(['-C', str(temporary), 'config', 'core.symlinks', 'false'])
            self.run(['-C', str(temporary), 'config', 'submodule.recurse', 'false'])
            self.run(['-C', str(temporary), 'remote', 'add', 'origin', url])
            if sparse_paths:
                self.run(['-C', str(temporary), 'sparse-checkout', 'init', '--cone'])
                self.run(['-C', str(temporary), 'sparse-checkout', 'set', *list(sparse_paths)])
            try:
                self.run(['-C', str(temporary), 'fetch', '--depth', '1', '--no-tags', 'origin', sha], timeout=180)
            except RepositoryError:
                # Public GitHub accepts pinned SHA fetches for reachable commits. If a
                # server refuses, fall back to the resolved branch/tag, then verify HEAD.
                self.run(['-C', str(temporary), 'fetch', '--depth', '1', '--no-tags', 'origin', ref], timeout=180)
            self.run(['-C', str(temporary), 'checkout', '-q', '--detach', 'FETCH_HEAD'])
            head = self.run(['-C', str(temporary), 'rev-parse', 'HEAD']).lower()
            if head != sha:
                raise RepositoryError(
                    f'The retrieved commit {head[:12]} does not match the requested pinned commit {sha[:12]}.',
                    'commit_mismatch', 409,
                )
            _install_checkout(temporary, target)
        except BaseException:
            _safe_rmtree(temporary)
            raise


def _install_checkout(source: Path, target: Path) -> None:
    """Move a prepared checkout into its cache path.

    Windows can refuse to delete or rename a directory for a few seconds after
    another process (an editor, an indexer or a virus scanner) touched it. Retry
    with a growing backoff, move the old copy aside instead of deleting it in
    place, and raise a clean RepositoryError when the path stays locked.
    """
    last_error: OSError | None = None
    for attempt in range(6):
        trash = target.parent / f'.stale-{uuid4().hex}'
        try:
            if target.exists():
                try:
                    target.rename(trash)
                except OSError:
                    _safe_rmtree(target)
            source.rename(target)
            if trash.exists():
                _safe_rmtree(trash)
            return
        except OSError as exc:
            last_error = exc
            _safe_rmtree(trash)
            time.sleep(0.25 * (attempt + 1))
    raise RepositoryError(
        'The cached copy of this repository is locked by another program. '
        'Close any editor, backup tool or scanner reading it, then inspect again.',
        'checkout_locked', 409,
    ) from last_error


def _remove_readonly(func, path, _):
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except OSError:
        pass


def _safe_rmtree(path: Path | str) -> None:
    p = Path(path)
    if not p.exists() and not p.is_symlink():
        return
    for root, dirs, files in os.walk(p):
        for f in files:
            try:
                os.chmod(os.path.join(root, f), stat.S_IWRITE)
            except OSError:
                pass
    shutil.rmtree(p, onerror=_remove_readonly)


def _bounded_tree(root: Path, skip: tuple[str, ...] = ()) -> tuple[int, int, list[str]]:
    files = 0
    total = 0
    symlinks: list[str] = []
    ignored = {'.git', *skip}
    for current, dirs, names in os.walk(root, followlinks=False):
        if Path(current).name == '.git':
            dirs[:] = []
            continue
        dirs[:] = [name for name in dirs if name not in ignored]
        for name in names:
            path = Path(current) / name
            if path.is_symlink():
                symlinks.append(path.relative_to(root).as_posix())
                continue
            if not path.is_file():
                continue
            files += 1
            try:
                total += path.stat().st_size
            except OSError:
                continue
            if files > MAX_CHECKOUT_FILES or total > MAX_CHECKOUT_BYTES:
                raise RepositoryError(
                    'That repository is larger than the inspection budget.',
                    'repository_too_large', 413,
                )
    return files, total, symlinks


def _github_metadata(owner: str, name: str, timeout: int = 12) -> dict:
    url = f'https://api.github.com/repos/{owner}/{name}'
    request = urllib.request.Request(url, headers={
        'User-Agent': 'DARWIN-Real-Project-Mode',
        'Accept': 'application/vnd.github+json',
    })
    ctx = ssl.create_default_context(cafile=certifi.where()) if certifi else None
    try:
        with urllib.request.urlopen(request, context=ctx, timeout=timeout) as response:
            return json.loads(response.read(1_000_000).decode('utf-8'))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise RepositoryError('That public repository was not found.', 'repository_not_found', 404) from exc
        if exc.code in (403, 429):
            return {'metadata_warning': 'GitHub metadata rate limit reached; size checked after download.'}
        raise RepositoryError(f'GitHub returned HTTP {exc.code} while inspecting the repository.', 'metadata_failed', 502) from exc
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        return {'metadata_warning': f'GitHub metadata unavailable: {exc}'}


class RepositoryImporter:
    """Resolve, pin, download and classify a GitHub repository once."""

    def __init__(self, cache_root: str | Path | None = None, git: GitClient | None = None,
                 metadata_fetcher=None, source_override: dict[str, Path] | None = None,
                 resolve_override: str | None = None):
        root = cache_root or os.environ.get('DARWIN_REPOSITORY_CACHE', '.runtime/repositories')
        self.cache_root = Path(root).resolve()
        self.cache_root.mkdir(parents=True, exist_ok=True)
        self.git = git or GitClient()
        self.metadata_fetcher = metadata_fetcher or _github_metadata
        # Test-only hooks. The HTTP API never passes these.
        self.source_override = {canonical_repository(k): Path(v).resolve() for k, v in (source_override or {}).items()}
        self.resolve_override = resolve_override.lower() if resolve_override else None

    def inspect(self, url: str, ref: str | None = 'main', consent: bool = False) -> dict:
        if consent is not True:
            raise RepositoryError(
                'Explicit consent is required before DARWIN downloads repository source.',
                'consent_required', 428,
            )
        repository = validate_repository_url(url)
        requested_ref = validate_ref(ref)
        if self.resolve_override:
            sha = self.resolve_override
        else:
            sha = self.git.resolve(repository.url, requested_ref)

        entry = catalog_entry(repository.url)
        pinned = bool(entry and entry['pinned_commit'] == sha)
        warnings: list[str] = []
        metadata = {}
        if canonical_repository(repository.url) not in self.source_override:
            metadata = self.metadata_fetcher(repository.owner, repository.name) or {}
            if metadata.get('metadata_warning'):
                warnings.append(metadata['metadata_warning'])
            size_kb = metadata.get('size')
            if isinstance(size_kb, (int, float)) and size_kb > MAX_REPOSITORY_KB:
                raise RepositoryError(
                    f'That repository is {size_kb / 1024:.0f} MB, above the {MAX_REPOSITORY_KB / 1024:.0f} MB inspection limit.',
                    'repository_too_large', 413,
                )
            if metadata.get('private'):
                raise RepositoryError('Private repositories are not supported.', 'private_repository', 403)

        source_root = self._source_root(repository, sha, requested_ref, entry)
        # A configured local checkout is a test/demo hook. Its installed
        # dependencies are not part of the repository, so exclude them from the
        # source budget while still enforcing the file/byte ceilings elsewhere.
        dependencies = ('node_modules', 'dist', 'build', '.gradle', '.cache') \
            if canonical_repository(repository.url) in self.source_override else ()
        files, total_bytes, symlinks = _bounded_tree(source_root, dependencies)
        if symlinks:
            warnings.append(
                f'{len(symlinks)} symbolic link(s) were not followed during inspection.'
            )

        from darwin.project_capabilities import inspect_source

        classification = inspect_source(source_root, repository.url, repository.owner,
                                        repository.name, sha, pinned)
        execution_allowed = bool(
            pinned and any(item.get('execution_allowed', True)
                           for item in classification['supported_evaluations'])
        )
        support_level = classification.get('support_level') or (
            'READY_FOR_MEASURED_EVOLUTION' if execution_allowed
            else 'EVALUABLE_WITH_SETUP' if classification['supported_evaluations']
            else 'INSPECTABLE'
        )
        prerequisites = classification.get('prerequisites') or []
        if classification['supported_evaluations'] and not pinned:
            warnings.append(
                'The repository has a known adapter, but this commit is not the pinned, audited revision. '
                'Inspection remains available; execution is disabled until the commit is reviewed.'
            )
            classification['supported_evaluations'] = []
            classification['evaluation_status'] = 'UNSUPPORTED_PROJECT'
            support_level = 'INSPECTABLE'
        elif classification['supported_evaluations'] and not execution_allowed:
            warnings.append(
                'A reviewed adapter matches this pinned source, but the execution prerequisite is not met: '
                + (prerequisites[0] if prerequisites else 'the isolated runtime is unavailable.')
            )
        if execution_allowed:
            # The generic inspection report cannot know whether a reviewed
            # adapter exists. Do not claim "this repository is never executed"
            # once an approved adapter will actually deploy it.
            for item in classification['not_supported']:
                if item.get('capability') == 'Measured runtime claims':
                    item['reason'] = (
                        'Measured claims are limited to the reviewed adapter scope: the pinned files '
                        'in DARWIN-owned isolated containers, one host and one bounded workload window. '
                        'The repository Compose file and Dockerfile are not executed.'
                    )

        if not classification['supported_evaluations']:
            warnings.append(
                'Repository inspected. No runnable optimization adapter is approved for this source, '
                'so DARWIN will not execute it or substitute the unrelated checkout lab.'
            )
        if (classification.get('screening') or {}).get('available'):
            warnings.append(
                'A simulated architecture screening is available. It models deployment controls from '
                'source and is not a measured runtime result.'
            )

        record = {
            'schema_version': 1,
            'inspection_id': str(uuid4()),
            'created_at': _now(),
            'status': 'inspected',
            'source': {
                'url': repository.url,
                'owner': repository.owner,
                'repo': repository.name,
                'requested_ref': requested_ref,
                'commit_sha': sha,
                'short_sha': sha[:12],
                'trusted': pinned,
                'cache_key': f'{repository.owner}__{repository.name}__{sha[:12]}',
                'file_count': files,
                'size_bytes': total_bytes,
                'metadata': {key: metadata.get(key) for key in
                             ('size', 'default_branch', 'language', 'license', 'pushed_at')
                             if metadata.get(key) is not None},
            },
            'project': classification['project'],
            'architecture': classification.get('architecture') or {},
            'facts': classification['facts'],
            'not_supported': classification['not_supported'],
            'supported_evaluations': classification['supported_evaluations'],
            'hotspots': classification.get('hotspots') or [],
            'screening': classification.get('screening') or {'available': False, 'controls': []},
            'guesses': classification['guesses'],
            'readiness': classification['readiness'],
            'warnings': warnings,
            'execution_allowed': execution_allowed,
            'support_level': support_level,
            'prerequisites': prerequisites,
            'evaluation_status': 'NOT_MEASURED' if execution_allowed else 'UNSUPPORTED_PROJECT',
            '_source_root': str(source_root),
            'policy': {
                'download': 'explicit consent recorded by API request',
                'execution': 'trusted adapter at pinned commit only',
                'original_source': 'read-only; DARWIN never commits, pushes or edits it',
                'candidate': 'temporary isolated overlay',
            },
        }
        return record

    def _source_root(self, repository: GitHubRepository, sha: str, ref: str,
                     entry: dict | None = None) -> Path:
        override = self.source_override.get(canonical_repository(repository.url))
        if override:
            if not override.is_dir():
                raise RepositoryError('The configured local source checkout is missing.', 'source_missing', 503)
            return override
        target = self.cache_root / f'{repository.owner}__{repository.name}__{sha[:12]}'
        marker = target / '.darwin-source.json'
        if marker.is_file():
            try:
                saved = json.loads(marker.read_text(encoding='utf-8'))
                if saved.get('url') == repository.url and saved.get('commit_sha') == sha:
                    return target
            except (OSError, ValueError):
                pass
        _safe_rmtree(target)
        sparse = (entry or {}).get('sparse_paths')
        self.git.checkout(repository.url, ref, sha, target, sparse_paths=sparse)
        marker.write_text(json.dumps({
            'url': repository.url,
            'commit_sha': sha,
            'requested_ref': ref,
            'retrieved_at': _now(),
            'read_only': True,
        }, indent=2), encoding='utf-8')
        return target
