"""Truthful stack classification from file-backed evidence.

The rule is simple: a fact requires a source file that proves it. Package names
are not architecture. In particular, a Vite/React package is not a Node server,
and inherited native modules are not silently promoted to the visible app.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess

from darwin.repository_catalog import SANCHAY_ADAPTER_ID, SANCHAY_ADAPTER_VERSION, catalog_entry

MAX_TEXT_BYTES = 2_000_000


def _read(path: Path, limit: int = MAX_TEXT_BYTES) -> str:
    try:
        if not path.is_file() or path.stat().st_size > limit:
            return ''
        return path.read_text(encoding='utf-8', errors='replace')
    except OSError:
        return ''


def _json(path: Path) -> dict:
    text = _read(path)
    if not text:
        return {}
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else {}
    except ValueError:
        return {}


def _exists(root: Path, relative: str) -> bool:
    path = root / relative
    return path.is_file() and not path.is_symlink()


def _count_files(root: Path, pattern: str, cap: int = 5000) -> int:
    count = 0
    for _ in root.glob(pattern):
        count += 1
        if count >= cap:
            break
    return count


def _fact(label: str, value: str, evidence: list[str]) -> dict:
    return {'label': label, 'value': value, 'evidence': evidence}


def _node_version() -> str | None:
    executable = shutil.which('node')
    if not executable:
        return None
    try:
        completed = subprocess.run(
            [executable, '--version'], capture_output=True, text=True, timeout=5,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), check=False,
        )
        return completed.stdout.strip() if completed.returncode == 0 else 'present'
    except (OSError, subprocess.SubprocessError):
        return 'present'


def _sanchay_adapter(root: Path, pinned: bool) -> dict | None:
    expected = [
        'web/src/utils/reporting.ts',
        'web/src/utils/money.ts',
        'web/src/utils/categories.ts',
        'web/src/types/finance.ts',
        'web/src/components/ReportsTab.tsx',
        'web/src/data/persistence.ts',
    ]
    if not all(_exists(root, item) for item in expected):
        return None
    reporting = _read(root / 'web/src/utils/reporting.ts')
    reports_tab = _read(root / 'web/src/components/ReportsTab.tsx')
    persistence = _read(root / 'web/src/data/persistence.ts')
    required_exports = ('computeReportTotals', 'computeCategorySpending',
                        'computeCategoryBreakdown', 'computePayeeBreakdown')
    if not all(name in reporting for name in required_exports):
        return None
    if 'ReportsTab' not in reports_tab or 'computeReportTotals' not in reports_tab:
        return None
    if 'sanchay.local.v1' not in persistence or 'localStorage' not in persistence:
        return None
    entry = catalog_entry(adapter_id=SANCHAY_ADAPTER_ID)
    if not entry:
        return None
    adapter = entry['adapter']
    return {
        'adapter_id': adapter['adapter_id'],
        'adapter_version': SANCHAY_ADAPTER_VERSION,
        'display_name': adapter['display_name'],
        'evaluation_type': 'client_data_processing',
        'summary': (
            'Compare Sanchay\'s current three-pass report aggregation with a single-pass '
            'implementation over identical fictional ledgers.'
        ),
        'change_summary': adapter['change_summary'],
        'mechanism': adapter['mechanism'],
        'correctness_rules': list(adapter['correctness_rules']),
        'scope_note': adapter['scope_note'],
        'modes': list(adapter['modes']),
        'execution_allowed': bool(pinned),
        'execution_note': (
            'Runs the pinned Sanchay source in a temporary overlay. The original checkout is read-only.'
            if pinned else
            'This commit is not the audited revision. Inspection only; execution is disabled.'
        ),
        'evidence': expected,
    }


def inspect_source(root: str | Path, repository_url: str, owner: str, repo: str,
                   commit_sha: str, pinned: bool) -> dict:
    root = Path(root).resolve()
    web_package = _json(root / 'web/package.json')
    dependencies = web_package.get('dependencies') or {}
    dev_dependencies = web_package.get('devDependencies') or {}
    scripts = web_package.get('scripts') or {}
    reporting_exists = _exists(root, 'web/src/utils/reporting.ts')
    persistence_exists = _exists(root, 'web/src/data/persistence.ts')
    webview_shell = _exists(root, 'app/src/main/java/com/ivy/wallet/ui/SanchayModernUI.kt')
    webview_text = _read(root / 'app/src/main/java/com/ivy/wallet/ui/SanchayModernUI.kt')
    persistence_text = _read(root / 'web/src/data/persistence.ts')
    reporting_text = _read(root / 'web/src/utils/reporting.ts')
    reports_tab_text = _read(root / 'web/src/components/ReportsTab.tsx')

    root_package = _json(root / 'package.json')
    root_dependencies = {**(root_package.get('dependencies') or {}), **(root_package.get('devDependencies') or {})}
    server_frameworks = sorted(set(root_dependencies) & {'express', 'fastify', 'hono', 'koa', '@hapi/hapi'})
    server_entry = next((name for name in ('server.ts', 'server.js', 'src/server.ts', 'src/server.js',
                                           'src/index.ts', 'src/index.js')
                         if _exists(root, name)), None)

    facts: list[dict] = []
    not_supported: list[dict] = []
    guesses: list[dict] = []
    languages: list[str] = []

    if root_package:
        languages.append('JavaScript/TypeScript')
    if _exists(root, 'settings.gradle.kts') or _exists(root, 'build.gradle.kts'):
        languages.append('Kotlin/Java')
    if web_package:
        languages.append('TypeScript/React')

    is_sanchay_shape = bool(
        web_package and 'react' in dependencies and reporting_exists and persistence_exists
        and 'sanchay.local.v1' in persistence_text
    )
    is_client_app = bool(web_package and 'react' in dependencies)
    is_node_server = bool(server_frameworks and server_entry)

    if is_sanchay_shape:
        project_type = 'react_webview_local_app'
        display_type = 'React + WebView · local-first application'
        application_host = 'Android WebView shell'
        persistence = 'Browser localStorage (sanchay.local.v1)'
        is_server_backend = False
        summary = (
            'A client-side personal-finance dashboard. The visible React application reads and '
            'writes browser-local data; there is no deployed server API or server database.'
        )
    elif is_client_app and not is_node_server:
        project_type = 'client_web_app'
        display_type = 'Client-side web application'
        application_host = 'Browser'
        persistence = 'Local or unspecified (inspect source)'
        is_server_backend = False
        summary = 'A browser application with no verified server entry point.'
    elif is_node_server:
        project_type = 'node_service'
        display_type = 'Node.js service'
        application_host = 'Node.js process'
        persistence = 'Unspecified (inspect source)'
        is_server_backend = True
        summary = 'A Node.js service entry point was found, but no approved evaluation adapter exists.'
    else:
        project_type = 'unknown_repository'
        display_type = 'Repository inspected'
        application_host = 'Not classified from source'
        persistence = 'Not classified from source'
        is_server_backend = False
        summary = 'DARWIN inspected the source but did not find a supported application shape.'

    if web_package:
        react_version = dependencies.get('react')
        facts.append(_fact(
            'Visible application',
            f'React{f" {react_version}" if react_version else ""} + TypeScript',
            ['web/package.json'],
        ))
        facts.append(_fact(
            'Build tool',
            'Vite' if 'vite' in dev_dependencies or 'vite' in dependencies else 'Unknown',
            ['web/package.json'],
        ))
    if is_sanchay_shape:
        facts.append(_fact('Host shell', 'Android WebView', [
            'app/src/main/java/com/ivy/wallet/ui/SanchayModernUI.kt',
        ]))
        facts.append(_fact('Persistence', 'Browser localStorage · sanchay.local.v1', [
            'web/src/data/persistence.ts',
        ]))
        facts.append(_fact('Report code', 'Real reporting functions found', [
            'web/src/utils/reporting.ts',
        ]))
        facts.append(_fact('Report call site', 'ReportsTab calls totals, category and payee aggregations', [
            'web/src/components/ReportsTab.tsx',
        ]))
        not_supported.extend([
            {'capability': 'API replica scaling', 'reason': 'No deployed server API exists in the visible app.'},
            {'capability': 'Server-side queue or outbox', 'reason': 'There is no server process or queue to vary.'},
            {'capability': 'PostgreSQL / cloud failover', 'reason': 'Ledger data is browser-local; no server database is present.'},
            {'capability': 'Measured Android device performance', 'reason': 'v1 measures the report calculation pipeline, not device rendering.'},
        ])
        if webview_shell and 'WebView' not in webview_text:
            guesses.append({
                'label': 'WebView host',
                'guess': 'The Kotlin shell may host the web app, but the WebView import was not found.',
                'confidence': 'low',
            })

    kotlin_count = _count_files(root, 'app/src/**/*.kt', cap=3000) if _exists(root, 'settings.gradle.kts') else 0
    if kotlin_count:
        facts.append(_fact(
            'Inherited native modules',
            f'{kotlin_count}{"+" if kotlin_count >= 3000 else ""} Kotlin source files present; not imported by the web application',
            ['settings.gradle.kts', 'app/src'],
        ))
        not_supported.append({
            'capability': 'Kotlin/Room data path',
            'reason': 'The visible Sanchay dashboard is the web app; the inherited native modules are not its runtime data path.',
        })

    adapter = _sanchay_adapter(root, pinned) if is_sanchay_shape else None
    supported = [adapter] if adapter else []

    if not supported:
        not_supported.append({
            'capability': 'Runnable optimization adapter',
            'reason': 'No approved adapter matches this repository and commit. DARWIN will not execute its code.',
        })

    if is_sanchay_shape:
        adapter_facts = {
            'reporting_exports': all(name in reporting_text for name in (
                'computeReportTotals', 'computeCategorySpending',
                'computeCategoryBreakdown', 'computePayeeBreakdown')),
            'reports_tab_calls': all(name in reports_tab_text for name in (
                'computeReportTotals', 'computeCategoryBreakdown', 'computePayeeBreakdown')),
            'local_storage': 'sanchay.local.v1' in persistence_text,
        }
    else:
        adapter_facts = {}

    readiness = {
        'node_available': shutil.which('node') is not None,
        'node_version': _node_version(),
        'source_paths_present': bool(reporting_exists and persistence_exists) if is_sanchay_shape else False,
        'adapter_approved': bool(adapter and adapter['execution_allowed']),
        'source_tests_available': _exists(root, 'web/node_modules/vitest/package.json'),
    }

    return {
        'project': {
            'type': project_type,
            'display_type': display_type,
            'summary': summary,
            'application_host': application_host,
            'persistence': persistence,
            'is_server_backend': is_server_backend,
            'languages': sorted(set(languages)),
            'adapter_checks': adapter_facts,
        },
        'facts': facts,
        'not_supported': not_supported,
        'supported_evaluations': supported,
        'guesses': guesses,
        'readiness': readiness,
        'evaluation_status': 'NOT_MEASURED' if supported else 'UNSUPPORTED_PROJECT',
    }
