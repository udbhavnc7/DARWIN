"""Record one real Real Project Mode evaluation for exhibition fallback.

This script runs the pinned Sanchay checkout through the same bounded engine and
adapter used by the API, then leaves the digest-verified evidence and a replay
bundle under ``artifacts/experiments``. It never edits, commits or pushes the
source checkout.

The local checkout is used only to avoid a network download on exhibition day.
HEAD must match the catalogued commit and the working tree must be clean.

Usage:
    python scripts/record_project_evaluation.py --source C:\\path\\to\\Sanchay
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from darwin.repository_catalog import (
    SANCHAY_ADAPTER_ID, SANCHAY_COMMIT, SANCHAY_REPOSITORY,
)
from darwin.repository_evaluations import RepositoryEngine
from darwin.repository_import import RepositoryImporter

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = Path(os.environ.get(
    'DARWIN_SANCHAY_SOURCE', r'C:\Users\LENOVO\Downloads\Sanchay\Sanchay'))


def git(source: Path, *args: str) -> str:
    completed = subprocess.run(
        ['git', '-C', str(source), *args], capture_output=True, text=True, timeout=30,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), check=False,
    )
    if completed.returncode != 0:
        raise SystemExit(f'git {" ".join(args)} failed: {completed.stderr.strip()}')
    return completed.stdout.strip()


def verify_source(source: Path) -> None:
    if not (source / 'web/src/utils/reporting.ts').is_file():
        raise SystemExit(f'Not a Sanchay checkout: {source}')
    head = git(source, 'rev-parse', 'HEAD').lower()
    if head != SANCHAY_COMMIT:
        raise SystemExit(
            f'Refusing to record: HEAD is {head}, but the audited commit is {SANCHAY_COMMIT}. '
            'Check out the pinned revision first.'
        )
    if git(source, 'status', '--porcelain'):
        raise SystemExit('Refusing to record: the Sanchay working tree has local changes.')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--source', type=Path, default=DEFAULT_SOURCE)
    parser.add_argument('--experiments', type=Path, default=ROOT / 'artifacts' / 'experiments')
    parser.add_argument('--mode', choices=('quick', 'full'), default='full')
    parser.add_argument('--timeout', type=float, default=900)
    args = parser.parse_args()

    source = args.source.resolve()
    verify_source(source)
    print(f'Verified pinned Sanchay checkout: {source}')
    print(f'Commit: {SANCHAY_COMMIT}')

    importer = RepositoryImporter(
        cache_root=args.experiments / 'repository-cache',
        source_override={SANCHAY_REPOSITORY: source},
        resolve_override=SANCHAY_COMMIT,
    )
    engine = RepositoryEngine(args.experiments, importer=importer)
    try:
        inspection = engine.inspect(SANCHAY_REPOSITORY, 'main', True)
        if not inspection.get('execution_allowed'):
            raise SystemExit('The inspection did not approve the Sanchay adapter.')
        adapter = inspection['supported_evaluations'][0]
        print(f"Inspection {inspection['inspection_id']}: {inspection['project']['display_type']}")
        print(f"Adapter: {adapter['adapter_id']} - {adapter['display_name']}")

        record = engine.submit(inspection['inspection_id'], SANCHAY_ADAPTER_ID, args.mode)
        ident = record['evaluation_id']
        print(f'Started {args.mode} evaluation {ident}')
        deadline = time.monotonic() + args.timeout
        last = None
        while time.monotonic() < deadline:
            record = engine.store.get_evaluation(ident)
            marker = (record['status'], record.get('stage'), (record.get('progress') or {}).get('percent'))
            if marker != last:
                progress = record.get('progress') or {}
                print(f"  [{record['status']}] {progress.get('percent', 0):>3}% {progress.get('label', '')}")
                last = marker
            if record['status'] in {'completed', 'failed', 'cancelled'}:
                break
            time.sleep(0.5)
        else:
            engine.cancel(ident)
            raise SystemExit(f'Timed out after {args.timeout:.0f}s; the evaluation was cancelled.')

        if record['status'] != 'completed':
            raise SystemExit(f"Evaluation ended {record['status']}: {record.get('error')}")

        verdict = record.get('verdict') or {}
        correctness = record.get('correctness') or {}
        print()
        print(f"Verdict: {verdict.get('status')} - {verdict.get('label')}")
        print(f"Reason: {verdict.get('reason')}")
        print(f"Correctness: {correctness.get('checks_passed')}/{correctness.get('checks_total')} checks passed")
        for row in record.get('measurements', []):
            print(f"  {row['size']:,} rows: {row['change_pct']:+.1f}% "
                  f"({row['baseline_median_ms']:.2f} ms -> {row['candidate_median_ms']:.2f} ms), "
                  f"paired wins {row['paired_win_rate'] * 100:.0f}%")
        source_tests = record.get('source_tests') or {}
        print(f"Source tests: {source_tests.get('status')} "
              f"({source_tests.get('tests_passed', 0)}/{source_tests.get('tests_total', 0)})")

        evidence_files = (record.get('evidence') or {}).get('files', [])
        print(f"Evidence: {len(evidence_files)} registered files")
        for item in evidence_files:
            print(f"  {item['name']:<20} {item['bytes']:>9,} bytes  {item['sha256'][:12]}")
        bundle = engine.bundle(ident)
        print(f'Bundle: {bundle}')
        print(json.dumps({
            'evaluation_id': ident,
            'inspection_id': inspection['inspection_id'],
            'status': record['status'],
            'verdict': verdict.get('status'),
            'evidence_dir': record['evidence']['dir'],
            'bundle': str(bundle),
        }, indent=2))
    finally:
        engine.close()


if __name__ == '__main__':
    sys.exit(main())
