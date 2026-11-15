"""Durable lifecycle for Real Project Mode evaluations.

Uses the existing experiment root and SQLite conventions, adds only new tables,
and runs one bounded repository evaluation at a time. It never fabricates
metrics: cancelled or interrupted work has no winner.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import queue
import re
import shutil
import sqlite3
import threading
import time
from datetime import datetime, timezone
from uuid import uuid4
import zipfile

from darwin.adapters.base import AdapterCancelled, AdapterError, EvaluationBudget
from darwin.repository_import import RepositoryError, RepositoryImporter

TERMINAL = {'completed', 'failed', 'cancelled'}

PRESETS = {
    'quick': {
        'seeds': (7,),
        'sizes': (10_000, 50_000),
        'repetitions': 10,
        'warmups': 2,
        'wall_clock_s': 120,
        'include_source_tests': False,
    },
    'full': {
        'seeds': (7, 21, 2026),
        'sizes': (1_000, 10_000, 50_000),
        'repetitions': 10,
        'warmups': 2,
        'wall_clock_s': 300,
        'include_source_tests': True,
    },
}

ARTIFACT_NAMES = {
    'source.json', 'workload.json', 'candidate.diff', 'benchmark.json',
    'parity.json', 'verdict.json', 'environment.json', 'source-tests.json',
    'replay.md', 'manifest.json',
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, default=str, ensure_ascii=False), encoding='utf-8')


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _public(value):
    if isinstance(value, dict):
        return {key: _public(item) for key, item in value.items() if not key.startswith('_')}
    if isinstance(value, list):
        return [_public(item) for item in value]
    return value


def _progress(stage: str, completed: int, total: int, label: str) -> dict:
    return {'stage': stage, 'completed': completed, 'total': total, 'label': label,
            'percent': round(completed / total * 100) if total else 0}


def _empty_verdict(status: str, label: str, reason: str) -> dict:
    return {
        'status': status, 'label': label, 'reason': reason,
        'policy': {'evidence_kind': 'live'},
        'per_size': [],
        'correctness': {'passed': False, 'checks_passed': 0, 'checks_total': 0, 'failures': []},
    }


class RepositoryStore:
    """New tables in the existing experiment database file."""

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = self.root / 'experiments.sqlite3'
        self.lock = threading.Lock()
        with self.connect() as conn:
            conn.executescript('''
                CREATE TABLE IF NOT EXISTS repository_inspections(
                    id TEXT PRIMARY KEY, data TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS project_evaluations(
                    id TEXT PRIMARY KEY, data TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS project_events(
                    evaluation_id TEXT, sequence INTEGER, data TEXT NOT NULL,
                    PRIMARY KEY(evaluation_id, sequence));
            ''')

    def connect(self):
        return sqlite3.connect(self.db, timeout=10)

    def save_inspection(self, record: dict) -> dict:
        with self.lock, self.connect() as conn:
            conn.execute(
                'INSERT INTO repository_inspections VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data',
                (record['inspection_id'], json.dumps(record), record['created_at']),
            )
        return record

    def get_inspection(self, ident: str) -> dict:
        with self.connect() as conn:
            row = conn.execute('SELECT data FROM repository_inspections WHERE id=?', (ident,)).fetchone()
        if not row:
            raise KeyError(ident)
        return json.loads(row[0])

    def all_inspections(self) -> list[dict]:
        with self.connect() as conn:
            return [json.loads(row[0]) for row in
                    conn.execute('SELECT data FROM repository_inspections ORDER BY created_at DESC')]

    def save_evaluation(self, record: dict, message: str) -> dict:
        with self.lock, self.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            conn.execute(
                'INSERT INTO project_evaluations VALUES (?,?,?,?) '
                'ON CONFLICT(id) DO UPDATE SET data=excluded.data, status=excluded.status',
                (record['evaluation_id'], json.dumps(record, default=str), record['status'],
                 record['created_at']),
            )
            sequence = conn.execute(
                'SELECT COALESCE(MAX(sequence),0)+1 FROM project_events WHERE evaluation_id=?',
                (record['evaluation_id'],),
            ).fetchone()[0]
            event = {
                'evaluation_id': record['evaluation_id'],
                'sequence': sequence,
                'occurred_at': now(),
                'type': 'project_evaluation',
                'status': record['status'],
                'stage': record.get('stage', 'queued'),
                'message': message,
            }
            conn.execute('INSERT INTO project_events VALUES (?,?,?)',
                         (record['evaluation_id'], sequence, json.dumps(event)))
        return record

    def get_evaluation(self, ident: str) -> dict:
        with self.connect() as conn:
            row = conn.execute('SELECT data FROM project_evaluations WHERE id=?', (ident,)).fetchone()
        if not row:
            raise KeyError(ident)
        return json.loads(row[0])

    def all_evaluations(self) -> list[dict]:
        with self.connect() as conn:
            return [json.loads(row[0]) for row in
                    conn.execute('SELECT data FROM project_evaluations ORDER BY created_at DESC')]

    def events(self, ident: str, after: int = 0) -> list[dict]:
        with self.connect() as conn:
            return [json.loads(row[0]) for row in conn.execute(
                'SELECT data FROM project_events WHERE evaluation_id=? AND sequence>? ORDER BY sequence',
                (ident, after))]


def default_adapters():
    from darwin.adapters.sanchay_reporting import SanchayReportingAdapter

    adapter = SanchayReportingAdapter()
    return {adapter.id: adapter}


class RepositoryEngine:
    def __init__(self, root: str | Path, importer: RepositoryImporter | None = None,
                 adapters: dict | None = None):
        self.store = RepositoryStore(root)
        self.importer = importer or RepositoryImporter()
        self.adapters = adapters or default_adapters()
        self.pending: queue.Queue[str] = queue.Queue()
        self.cancels: dict[str, threading.Event] = {}
        self.guard = threading.Lock()
        self.shutdown = threading.Event()
        self.worker = threading.Thread(target=self.loop, daemon=True, name='darwin-project-evaluations')
        for record in self.store.all_evaluations():
            if record['status'] not in TERMINAL:
                record.update(
                    status='failed', stage='interrupted', finished_at=now(),
                    cleanup_status='requires_review',
                    error='Repository evaluation was interrupted by a process restart. No metrics were retained.',
                )
                record['verdict'] = _empty_verdict(
                    'INTERRUPTED', 'Interrupted',
                    'The worker stopped before completing this evaluation. No winner is reported.',
                )
                self.store.save_evaluation(record, 'Interrupted by worker restart')
        self.worker.start()

    def inspect(self, url: str, ref: str | None = 'main', consent: bool = False) -> dict:
        record = self.importer.inspect(url, ref, consent)
        self.store.save_inspection(record)
        return record

    def get_inspection(self, ident: str) -> dict:
        return self.store.get_inspection(ident)

    def submit(self, inspection_id: str, adapter_id: str, mode: str = 'quick',
               include_source_tests: bool | None = None) -> dict:
        inspection = self.store.get_inspection(inspection_id)
        if not inspection.get('execution_allowed'):
            raise RepositoryError(
                'This repository is inspection-only. DARWIN has no approved executable adapter for it, '
                'and will not substitute the unrelated checkout lab.',
                'execution_not_allowed', 409,
            )
        support = next((item for item in inspection.get('supported_evaluations', [])
                        if item.get('adapter_id') == adapter_id), None)
        if not support:
            raise RepositoryError('That adapter is not supported for this source.', 'adapter_unsupported', 409)
        adapter = self.adapters.get(adapter_id)
        if not adapter:
            raise RepositoryError('That adapter is not installed in this DARWIN build.', 'adapter_missing', 503)
        preset = PRESETS.get(mode)
        if not preset:
            raise RepositoryError('Unknown evaluation mode.', 'invalid_mode', 400)
        with self.guard:
            if self.shutdown.is_set():
                raise RuntimeError('Repository worker is shutting down')
            if sum(record['status'] not in TERMINAL for record in self.store.all_evaluations()) >= 5:
                raise RuntimeError('Repository evaluation queue is full')
            ident = str(uuid4())
            source = _public(inspection['source'])
            record = {
                'schema_version': 1,
                'evaluation_id': ident,
                'inspection_id': inspection_id,
                'created_at': now(),
                'requested_at': now(),
                'status': 'queued',
                'stage': 'queued',
                'progress': _progress('queued', 0, 4, 'Queued for the local worker'),
                'evidence_kind': 'live',
                'adapter_id': adapter_id,
                'adapter_version': getattr(adapter, 'version', None),
                'evaluation_type': getattr(adapter, 'evaluation_type', None),
                'mode': mode,
                'source': source,
                'inspection': {
                    'project': inspection.get('project'),
                    'facts': inspection.get('facts', []),
                    'not_supported': inspection.get('not_supported', []),
                    'guesses': inspection.get('guesses', []),
                    'readiness': inspection.get('readiness'),
                    'warnings': inspection.get('warnings', []),
                    'policy': inspection.get('policy'),
                },
                'candidate': None,
                'workload': {
                    'preset': mode,
                    'seeds': list(preset['seeds']),
                    'sizes': list(preset['sizes']),
                    'repetitions': preset['repetitions'],
                    'warmups': preset['warmups'],
                    'include_source_tests': preset['include_source_tests']
                    if include_source_tests is None else bool(include_source_tests),
                    'fixtures': 'deterministic fictional ledgers',
                },
                'correctness': None,
                'measurements': [],
                'environment': None,
                'source_tests': None,
                'verdict': None,
                'error': None,
                'cleanup_status': 'not_started',
                'evidence': {'dir': f'project-evaluations/{ident}', 'files': []},
            }
            self.cancels[ident] = threading.Event()
            self.store.save_evaluation(record, 'Queued repository evaluation')
            self.pending.put(ident)
            return record

    def cancel(self, ident: str) -> dict:
        with self.guard:
            record = self.store.get_evaluation(ident)
            if record['status'] not in TERMINAL:
                self.cancels[ident].set()
                if record['status'] == 'queued':
                    record.update(status='cancelled', stage='cancelled', finished_at=now(),
                                  cleanup_status='not_needed',
                                  verdict=_empty_verdict('INTERRUPTED', 'Interrupted',
                                                         'Cancelled before execution. No metrics were produced.'))
                    self.store.save_evaluation(record, 'Cancelled before execution')
            return self.store.get_evaluation(ident)

    def loop(self) -> None:
        while not self.shutdown.is_set():
            try:
                ident = self.pending.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                self.execute(ident)
            except BaseException as exc:  # The worker must survive one broken record.
                try:
                    record = self.store.get_evaluation(ident)
                    record.update(
                        status='failed', stage='failed', error=str(exc),
                        finished_at=now(), cleanup_status='requires_review',
                    )
                    record['verdict'] = _empty_verdict(
                        'FAILED_INFRASTRUCTURE', 'Infrastructure failed',
                        'The evaluator stopped unexpectedly. No metrics are reported as valid.',
                    )
                    self.store.save_evaluation(record, 'Worker recovered from an unexpected failure')
                except BaseException:
                    pass

    def _check(self, stop: threading.Event) -> bool:
        return stop.is_set() or self.shutdown.is_set()

    def execute(self, ident: str) -> None:
        record = None
        inspection = None
        prepared = None
        stop = self.cancels.get(ident) or threading.Event()
        try:
            with self.guard:
                record = self.store.get_evaluation(ident)
                if record['status'] in TERMINAL:
                    return
                record.update(status='running', stage='preparing', started_at=now(),
                              progress=_progress('preparing', 1, 4,
                                                 'Preparing the pinned source and fictional ledgers'))
                self.store.save_evaluation(record, 'Preparing evaluation')
            inspection = self.store.get_inspection(record['inspection_id'])
            adapter = self.adapters.get(record['adapter_id'])
            if adapter is None:
                raise AdapterError('That adapter is not installed in this DARWIN build.',
                                   'adapter_missing', 'NO_FEASIBLE_CANDIDATE')
            source_root = Path(inspection.get('_source_root', ''))
            work_dir = self.store.root / record['evidence']['dir']
            work_dir.mkdir(parents=True, exist_ok=True)
            if self._check(stop):
                raise AdapterCancelled('Cancelled before preparation')
            if not source_root.is_dir():
                raise AdapterError(
                    'The cached source checkout is missing. Re-inspect the repository to download it again.',
                    'source_missing', 'FAILED_INFRASTRUCTURE',
                )
            support = adapter.detect(source_root, inspection['source']['commit_sha'],
                                     bool(inspection['source']['trusted']))
            if not support.supported:
                raise AdapterError(support.reason, 'adapter_not_supported', 'NO_FEASIBLE_CANDIDATE')
            preset = PRESETS[record['mode']]
            budget = EvaluationBudget(
                mode=record['mode'],
                seeds=tuple(preset['seeds']),
                sizes=tuple(preset['sizes']),
                repetitions=preset['repetitions'],
                warmups=preset['warmups'],
                wall_clock_s=preset['wall_clock_s'],
                include_source_tests=bool(record['workload'].get('include_source_tests')),
            )
            prepared = adapter.prepare(source_root, work_dir, budget)
            candidates = adapter.candidates(prepared)
            if not candidates:
                raise AdapterError('The adapter produced no source-compatible candidate.',
                                   'no_candidate', 'NO_FEASIBLE_CANDIDATE')
            candidate = candidates[0]
            record['candidate'] = {
                'candidate_id': candidate.candidate_id,
                'label': candidate.label,
                'description': candidate.description,
                'files': candidate.files,
                'wiring': candidate.wiring,
                'diff_sha256': _digest(prepared.candidate_diff),
            }
            record['workload']['fixtures'] = prepared.fixtures
            record.update(stage='checking_correctness',
                          progress=_progress('checking_correctness', 2, 4,
                                             'Running the real baseline and candidate on the same ledgers'))
            self.store.save_evaluation(record, 'Correctness harness prepared')

            measurements = adapter.measure(prepared, candidate, budget,
                                           lambda: self._check(stop))
            if self._check(stop):
                raise AdapterCancelled('Cancelled before the verdict')
            record.update(stage='measuring',
                          progress=_progress('measuring', 3, 4,
                                             'Comparing measured report-calculation time'))
            self.store.save_evaluation(record, 'Measurements captured')

            evidence = adapter.verify(prepared, candidate, measurements)
            record['correctness'] = {
                **(evidence.get('parity') or {}),
                'checks': evidence.get('checks', []),
            }
            record['measurements'] = (evidence.get('verdict') or {}).get('per_size', [])
            record['environment'] = evidence.get('environment')
            record['source_tests'] = evidence.get('source_tests')
            record['verdict'] = evidence.get('verdict')
            record['stage'] = 'verdict'
            record['progress'] = _progress('verdict', 4, 4, 'Verdict derived from recorded evidence')
            self._write_evidence(record, prepared, evidence, measurements, inspection)
            record['status'] = 'completed'
            record['stage'] = 'done'
            record['progress'] = _progress('done', 4, 4, 'Evaluation complete')
            record['cleanup_status'] = 'completed'
            record['finished_at'] = now()
        except AdapterCancelled as exc:
            record.update(status='cancelled', stage='cancelled', error=str(exc),
                          cleanup_status='completed', finished_at=now())
            record['verdict'] = _empty_verdict(
                'INTERRUPTED', 'Interrupted',
                'The operation was cancelled. No winner is reported.',
            )
            self._safe_failure_evidence(record, inspection)
        except AdapterError as exc:
            completed = exc.verdict == 'NO_FEASIBLE_CANDIDATE'
            record.update(status='completed' if completed else 'failed',
                          stage='no_candidate' if completed else 'failed',
                          error=str(exc), cleanup_status='completed', finished_at=now())
            record['verdict'] = _empty_verdict(
                exc.verdict,
                'No verified candidate' if completed else 'Infrastructure failed',
                str(exc),
            )
            self._safe_failure_evidence(record, inspection)
        except BaseException as exc:
            record.update(status='failed', stage='failed', error=str(exc),
                          cleanup_status='requires_review', finished_at=now())
            record['verdict'] = _empty_verdict(
                'FAILED_INFRASTRUCTURE', 'Infrastructure failed',
                'The evaluator stopped unexpectedly. No metrics are reported as valid.',
            )
            self._safe_failure_evidence(record, inspection)
        finally:
            if record is None:
                return
            if not record.get('finished_at'):
                record['finished_at'] = now()
            if record.get('started_at') and record.get('finished_at'):
                try:
                    start = datetime.fromisoformat(record['started_at'])
                    end = datetime.fromisoformat(record['finished_at'])
                    record['duration_s'] = round(max(0.0, (end - start).total_seconds()), 3)
                except ValueError:
                    pass
            if record.get('status') not in TERMINAL:
                record.update(status='failed', stage='failed', cleanup_status='requires_review')
                record['verdict'] = _empty_verdict(
                    'INTERRUPTED', 'Interrupted',
                    'The evaluator stopped before a verdict. No metrics are reported as valid.',
                )
            try:
                self.store.save_evaluation(record, 'Evaluation finished')
            finally:
                with self.guard:
                    self.cancels.pop(ident, None)

    def _safe_failure_evidence(self, record: dict, inspection: dict | None) -> None:
        """Failure evidence is useful but must never take down the worker."""
        try:
            self._write_failure_evidence(record, inspection or {})
        except BaseException as exc:
            record['evidence_error'] = f'Could not persist failure evidence: {exc}'

    def _write_failure_evidence(self, record: dict, inspection: dict) -> None:
        folder = self.store.root / record['evidence']['dir']
        folder.mkdir(parents=True, exist_ok=True)
        _write_json(folder / 'verdict.json', record.get('verdict') or {})
        _write_json(folder / 'source.json', {
            'source': _public(inspection.get('source', {})),
            'adapter': {'adapter_id': record.get('adapter_id'),
                        'adapter_version': record.get('adapter_version')},
            'inspection_id': record.get('inspection_id'),
        })
        _write_json(folder / 'workload.json', {
            'preset': record.get('mode'),
            'seeds': (record.get('workload') or {}).get('seeds'),
            'sizes': (record.get('workload') or {}).get('sizes'),
            'repetitions': (record.get('workload') or {}).get('repetitions'),
            'warmups': (record.get('workload') or {}).get('warmups'),
            'fixtures': (record.get('workload') or {}).get('fixtures'),
            'note': 'No valid measurements were retained for this evaluation.',
        })
        self._register_evidence(record, folder)

    def _write_evidence(self, record: dict, prepared, evidence: dict,
                        measurements: dict, inspection: dict) -> None:
        folder = self.store.root / record['evidence']['dir']
        folder.mkdir(parents=True, exist_ok=True)
        _write_json(folder / 'source.json', {
            'source': _public(inspection.get('source', {})),
            'adapter': {'adapter_id': record['adapter_id'], 'adapter_version': record['adapter_version']},
            'inspection_id': record['inspection_id'],
        })
        _write_json(folder / 'workload.json', {
            'preset': record['mode'],
            'seeds': record['workload']['seeds'],
            'sizes': record['workload']['sizes'],
            'repetitions': record['workload']['repetitions'],
            'warmups': record['workload']['warmups'],
            'fixtures': prepared.fixtures,
            'measurement_scope': evidence.get('measurement_scope'),
        })
        source_diff = prepared.candidate_diff.resolve()
        target_diff = (folder / 'candidate.diff').resolve()
        if source_diff != target_diff:
            shutil.copy2(source_diff, target_diff)
        benchmark = measurements.get('benchmark') or {}
        _write_json(folder / 'benchmark.json', benchmark)
        _write_json(folder / 'parity.json', {
            'passed': (evidence.get('parity') or {}).get('passed'),
            'checks': evidence.get('checks', []),
            'source_tests': evidence.get('source_tests'),
        })
        _write_json(folder / 'verdict.json', evidence.get('verdict') or {})
        _write_json(folder / 'environment.json', {
            'benchmark_environment': evidence.get('environment'),
            'harness': evidence.get('harness'),
            'source_tests': evidence.get('source_tests'),
            'measurement_scope': evidence.get('measurement_scope'),
        })
        _write_json(folder / 'source-tests.json', evidence.get('source_tests') or {'status': 'not_run'})
        diff_text = prepared.candidate_diff.read_text(encoding='utf-8', errors='replace')
        (folder / 'replay.md').write_text(
            '# Replay this Real Project Mode evaluation\n\n'
            f'- Evaluation: `{record["evaluation_id"]}`\n'
            f'- Adapter: `{record["adapter_id"]}` version `{record["adapter_version"]}`\n'
            f'- Source: {record["source"]["url"]} at `{record["source"]["commit_sha"]}`\n'
            f'- Mode: `{record["mode"]}`\n\n'
            '## API replay\n\n'
            '```powershell\n'
            f'$body = @{{ inspection_id = "{record["inspection_id"]}"; adapter_id = "{record["adapter_id"]}"; '
            f'mode = "{record["mode"]}"; consent = $true }} | ConvertTo-Json\n'
            'Invoke-RestMethod http://127.0.0.1:8000/api/project-evaluations -Method Post '
            '-ContentType application/json -Body $body\n'
            '```\n\n'
            'The source is fetched read-only at the pinned commit. DARWIN never edits, commits or pushes it.\n\n'
            '## Candidate diff\n\n'
            f'```diff\n{diff_text}\n```\n',
            encoding='utf-8',
        )
        self._register_evidence(record, folder)

    def _register_evidence(self, record: dict, folder: Path) -> None:
        files = []
        manifest = {
            'schema_version': 1,
            'evaluation_id': record['evaluation_id'],
            'inspection_id': record['inspection_id'],
            'source_commit': record['source']['commit_sha'],
            'adapter_id': record['adapter_id'],
            'adapter_version': record['adapter_version'],
            'evidence_kind': record.get('evidence_kind', 'live'),
            'created_at': now(),
            'files': {},
        }
        for path in sorted(folder.iterdir()):
            if not path.is_file() or path.name in ('manifest.json', 'evidence.zip'):
                continue
            digest = _digest(path)
            files.append({'name': path.name, 'sha256': digest, 'bytes': path.stat().st_size})
            manifest['files'][path.name] = digest
        _write_json(folder / 'manifest.json', manifest)
        manifest_digest = _digest(folder / 'manifest.json')
        files.append({'name': 'manifest.json', 'sha256': manifest_digest,
                      'bytes': (folder / 'manifest.json').stat().st_size})
        record['evidence'] = {'dir': record['evidence']['dir'], 'files': files,
                              'manifest_sha256': manifest_digest}

    def get_evaluation(self, ident: str) -> dict:
        return self.store.get_evaluation(ident)

    def list_evaluations(self) -> list[dict]:
        return self.store.all_evaluations()

    def events(self, ident: str, after: int = 0) -> list[dict]:
        return self.store.events(ident, after)

    def evidence_path(self, ident: str, name: str) -> Path:
        record = self.store.get_evaluation(ident)
        registered = next((item for item in record.get('evidence', {}).get('files', [])
                           if item['name'] == name), None)
        if name not in ARTIFACT_NAMES or not registered:
            raise KeyError(name)
        folder = (self.store.root / record['evidence']['dir']).resolve()
        path = (folder / name).resolve()
        if not path.is_relative_to(folder) or not path.is_file() or _digest(path) != registered['sha256']:
            raise KeyError(name)
        return path

    def bundle(self, ident: str) -> Path:
        record = self.store.get_evaluation(ident)
        folder = (self.store.root / record['evidence']['dir']).resolve()
        manifest_path = folder / 'manifest.json'
        if not manifest_path.is_file():
            raise KeyError('manifest')
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        for name, digest in manifest['files'].items():
            path = (folder / name).resolve()
            if not path.is_file() or not path.is_relative_to(folder) or _digest(path) != digest:
                raise ValueError(f'Evidence file failed digest verification: {name}')
        target = folder / f'darwin-project-evidence-{ident}.zip'
        temporary = folder / f'.bundle-{uuid4().hex}.zip'
        with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as archive:
            for name in sorted(manifest['files']):
                archive.write(folder / name, arcname=name)
            archive.write(manifest_path, arcname='manifest.json')
            archive.writestr('README.txt',
                             'DARWIN Real Project Mode evidence bundle.\n'
                             f'Evaluation: {ident}\n'
                             f'Source commit: {record["source"]["commit_sha"]}\n'
                             'Verify every file against manifest.json before trusting it.\n')
        os.replace(temporary, target)
        return target

    def close(self) -> None:
        self.shutdown.set()
        for event in list(self.cancels.values()):
            event.set()
        self.worker.join(timeout=30)
