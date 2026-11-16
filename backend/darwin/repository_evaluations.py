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
from darwin.project_simulation import (
    SCREENING_ADAPTER_ID, SCREENING_ADAPTER_VERSION, empty_screening_verdict, screen_repository,
)
from darwin.repository_import import RepositoryError, RepositoryImporter

TERMINAL = {'completed', 'failed', 'cancelled'}

PRESETS = {
    'quick': {
        'seeds': (7,),
        'sizes': (10_000, 50_000),
        'repetitions': 10,
        'warmups': 2,
        'wall_clock_s': 120,
        'external_wall_clock_s': 300,
        'include_source_tests': False,
    },
    'full': {
        'seeds': (7, 21, 2026),
        'sizes': (1_000, 10_000, 50_000),
        'repetitions': 10,
        'warmups': 2,
        'wall_clock_s': 300,
        'external_wall_clock_s': 900,
        'include_source_tests': True,
    },
}

ARTIFACT_NAMES = {
    'source.json', 'workload.json', 'candidate.diff', 'benchmark.json',
    'parity.json', 'verdict.json', 'environment.json', 'source-tests.json',
    'architecture.json', 'screening.json', 'project-note.md',
    'replay.md', 'manifest.json', 'change.md',
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


def _change_text(record: dict, verdict: dict) -> str:
    """Reviewable deployment change derived only from recorded measurements."""
    rows = verdict.get('comparison') or []
    winner_id = verdict.get('winner_id')
    winner = next((row for row in rows if row.get('candidate_id') == winner_id), None)
    baseline = next((row for row in rows
                     if row.get('candidate_id') == verdict.get('baseline_id')),
                    rows[0] if rows else None)
    lines = [
        '# DARWIN architecture change',
        '',
        f'- Source: {record["source"]["url"]} at `{record["source"]["commit_sha"]}`',
        f'- Adapter: `{record["adapter_id"]}` `{record["adapter_version"]}`',
        f'- Verdict: **{verdict.get("status")}** — {verdict.get("label")}',
        f'- Evidence: {record.get("evidence_kind", "live")} isolated Linux Docker runs, '
        f'mode `{record["mode"]}`, challenge `{record["workload"].get("challenge")}`',
        f'- Evaluation: `{record["evaluation_id"]}`',
        '',
    ]
    if not winner or not baseline:
        return '\n'.join(lines + [
            'No deployable change is exported for this verdict.',
            '',
        ])
    lines += [
        '## Measured comparison',
        '',
        '| Candidate | Replicas | Workers | p95 ms | req/s | CPU s | Peak MB | Recovery s |',
        '| --- | --- | --- | --- | --- | --- | --- | --- |',
    ]
    for row in rows:
        lines.append(
            f'| {row.get("label") or row.get("candidate_id")} | {row.get("replicas")} | '
            f'{row.get("workers")} | {row.get("p95_ms")} | {row.get("requests_per_s")} | '
            f'{row.get("cpu_seconds")} | {row.get("memory_peak_mb")} | {row.get("recovery_s")} |'
        )
    lines += [
        '',
        '## Decision',
        '',
        f'{verdict.get("reason") or ""}',
        '',
        '## Apply',
        '',
    ]
    status = verdict.get('status')
    if status == 'VERIFIED_IMPROVEMENT':
        lines += [
            f'- Baseline topology: {baseline.get("replicas")} replica(s) × {baseline.get("workers")} worker(s).',
            f'- Recommended topology: {winner.get("replicas")} replica(s) × {winner.get("workers")} worker(s).',
            '- Deploy that many replicas of the same reviewed image behind the gateway and keep the '
            'shared Redis service. Do not copy the repository Compose file or Dockerfile; DARWIN '
            'generated and tested its own stack.',
        ]
    elif status == 'TRADEOFF_REQUIRES_CHOICE':
        lines += [
            f'- Baseline topology: {baseline.get("replicas")} replica(s) × {baseline.get("workers")} worker(s).',
            f'- Candidate topology: {winner.get("replicas")} replica(s) × {winner.get("workers")} worker(s) '
            f'({winner.get("label") or winner.get("candidate_id")}).',
            '- This is an operator choice, not an automatic recommendation. Adopt the candidate only '
            'if its measured regressions are acceptable for this deployment.',
        ]
    elif status == 'BASELINE_RETAINED':
        lines += [
            f'- Keep the baseline topology: {baseline.get("replicas")} replica(s) × '
            f'{baseline.get("workers")} worker(s).',
            '- No candidate cleared the gates, so no deployment change is proposed.',
        ]
    else:
        lines += ['- No deployment change is authorised for this verdict.']
    lines += [
        '',
        '## Rollback',
        '',
    ]
    if status in ('VERIFIED_IMPROVEMENT', 'TRADEOFF_REQUIRES_CHOICE', 'BASELINE_RETAINED'):
        lines += [
            f'- Restore {baseline.get("replicas")} replica(s) × {baseline.get("workers")} worker(s). '
            'No data migration is required because both topologies share the same Redis state.',
        ]
    else:
        lines += ['- Nothing was applied, so no rollback is required.']
    lines += [
        '',
        '## Limits',
        '',
        '- Measured on one host with the load generator and the service sharing CPU. Absolute '
        'numbers are lab-only and do not establish production performance.',
        '- Only the reviewed workload path and oracles were exercised. HTTP availability alone '
        'is not business correctness; counter monotonicity was the oracle here.',
        '- Simulation results never authorise a change in this document.',
        '',
    ]
    return '\n'.join(lines)


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
    from darwin.adapters.registry import adapters_by_id

    return adapters_by_id()


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
                record['verdict'] = empty_screening_verdict(
                    'The screening worker stopped before completing this evaluation. '
                    'No recommendation is reported.'
                ) if record.get('adapter_id') == SCREENING_ADAPTER_ID else _empty_verdict(
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

    def submit(self, inspection_id: str, adapter_id: str | None = None, mode: str = 'quick',
               include_source_tests: bool | None = None,
               challenge: str = 'faster') -> dict:
        inspection = self.store.get_inspection(inspection_id)
        preset = PRESETS.get(mode)
        if not preset:
            raise RepositoryError('Unknown evaluation mode.', 'invalid_mode', 400)
        if challenge not in {'faster', 'spike', 'resources', 'recover'}:
            raise RepositoryError('Unknown challenge.', 'invalid_challenge', 400)
        screening = inspection.get('screening') or {}
        if adapter_id == SCREENING_ADAPTER_ID:
            if not screening.get('available'):
                raise RepositoryError(
                    'Architecture screening is not available for this source: '
                    + (screening.get('reason') or 'no backend request path was detected.'),
                    'screening_unavailable', 409,
                )
            return self._submit_screening(inspection, mode, preset)
        if adapter_id is None and not inspection.get('execution_allowed') and screening.get('available'):
            return self._submit_screening(inspection, mode, preset)
        support = next((item for item in inspection.get('supported_evaluations', [])
                        if item.get('adapter_id') == adapter_id), None)
        if adapter_id and not support:
            raise RepositoryError('That adapter is not supported for this source.', 'adapter_unsupported', 409)
        if not inspection.get('execution_allowed'):
            prerequisite = (inspection.get('prerequisites') or
                            [item.get('prerequisite') for item in inspection.get('supported_evaluations') or []
                             if item.get('prerequisite')])
            raise RepositoryError(
                ('A reviewed adapter matches this source, but execution is not available yet: '
                 + (prerequisite[0] if prerequisite else 'no executable adapter is approved.'))
                if support else
                ('This repository is inspection-only. DARWIN has no approved executable adapter for it, '
                 'and will not substitute the unrelated checkout lab.'),
                'execution_not_allowed', 409,
            )
        adapter = self.adapters.get(adapter_id)
        if not adapter:
            raise RepositoryError('That adapter is not installed in this DARWIN build.', 'adapter_missing', 503)
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
                    'architecture': inspection.get('architecture'),
                    'facts': inspection.get('facts', []),
                    'not_supported': inspection.get('not_supported', []),
                    'hotspots': inspection.get('hotspots', []),
                    'screening': inspection.get('screening'),
                    'guesses': inspection.get('guesses', []),
                    'readiness': inspection.get('readiness'),
                    'warnings': inspection.get('warnings', []),
                    'policy': inspection.get('policy'),
                },
                'candidate': None,
                'workload': {
                    'preset': mode,
                    'challenge': challenge,
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
                'screening': None,
                'recommendation': None,
                'verdict': None,
                'error': None,
                'cleanup_status': 'not_started',
                'evidence': {'dir': f'project-evaluations/{ident}', 'files': []},
            }
            self.cancels[ident] = threading.Event()
            self.store.save_evaluation(record, 'Queued repository evaluation')
            self.pending.put(ident)
            return record

    def _submit_screening(self, inspection: dict, mode: str, preset: dict) -> dict:
        with self.guard:
            if self.shutdown.is_set():
                raise RuntimeError('Repository worker is shutting down')
            if sum(record['status'] not in TERMINAL for record in self.store.all_evaluations()) >= 5:
                raise RuntimeError('Repository evaluation queue is full')
            ident = str(uuid4())
            record = {
                'schema_version': 1,
                'evaluation_id': ident,
                'inspection_id': inspection['inspection_id'],
                'created_at': now(),
                'requested_at': now(),
                'status': 'queued',
                'stage': 'queued',
                'progress': _progress('queued', 0, 4, 'Queued for the local screening model'),
                'evidence_kind': 'simulated',
                'adapter_id': SCREENING_ADAPTER_ID,
                'adapter_version': SCREENING_ADAPTER_VERSION,
                'evaluation_type': 'architecture_screening',
                'mode': mode,
                'source': _public(inspection['source']),
                'inspection': {
                    'project': inspection.get('project'),
                    'architecture': inspection.get('architecture'),
                    'facts': inspection.get('facts', []),
                    'not_supported': inspection.get('not_supported', []),
                    'hotspots': inspection.get('hotspots', []),
                    'screening': inspection.get('screening'),
                    'guesses': inspection.get('guesses', []),
                    'readiness': inspection.get('readiness'),
                    'warnings': inspection.get('warnings', []),
                    'policy': inspection.get('policy'),
                },
                'candidate': None,
                'workload': {
                    'preset': mode,
                    'seeds': list(preset['seeds']),
                    'sizes': [],
                    'repetitions': 0,
                    'warmups': 0,
                    'include_source_tests': False,
                    'fixtures': 'synthetic workload derived from the inspected architecture',
                    'note': 'No repository code is executed. All values are model outputs.',
                },
                'correctness': None,
                'measurements': [],
                'environment': None,
                'source_tests': None,
                'screening': None,
                'recommendation': None,
                'verdict': None,
                'error': None,
                'cleanup_status': 'not_started',
                'evidence': {'dir': f'project-evaluations/{ident}', 'files': []},
            }
            self.cancels[ident] = threading.Event()
            self.store.save_evaluation(record, 'Queued simulated architecture screening')
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
                                  verdict=empty_screening_verdict(
                                      'Cancelled before the screening model ran. '
                                      'No recommendation was produced.'
                                  ) if record.get('adapter_id') == SCREENING_ADAPTER_ID else
                                  _empty_verdict('INTERRUPTED', 'Interrupted',
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
                    record['verdict'] = empty_screening_verdict(
                        'The screening worker stopped unexpectedly. No recommendation is reported.'
                    ) if record.get('adapter_id') == SCREENING_ADAPTER_ID else _empty_verdict(
                        'FAILED_INFRASTRUCTURE', 'Infrastructure failed',
                        'The evaluator stopped unexpectedly. No metrics are reported as valid.',
                    )
                    self.store.save_evaluation(record, 'Worker recovered from an unexpected failure')
                except BaseException:
                    pass

    def _check(self, stop: threading.Event) -> bool:
        return stop.is_set() or self.shutdown.is_set()

    def execute(self, ident: str) -> None:
        existing = self.store.get_evaluation(ident)
        if existing.get('adapter_id') == SCREENING_ADAPTER_ID:
            return self.execute_screening(ident)
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
                              progress=_progress(
                                  'preparing', 1, 4,
                                  'Preparing the pinned source and reviewed workload'
                                  if record.get('evaluation_type') == 'backend_architecture'
                                  else 'Preparing the pinned source and fictional ledgers'))
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
            external = record.get('evaluation_type') == 'backend_architecture'
            budget = EvaluationBudget(
                mode=record['mode'],
                seeds=tuple(preset['seeds']),
                sizes=tuple(preset['sizes']),
                repetitions=preset['repetitions'],
                warmups=preset['warmups'],
                wall_clock_s=(preset.get('external_wall_clock_s', preset['wall_clock_s'])
                              if external else preset['wall_clock_s']),
                include_source_tests=bool(record['workload'].get('include_source_tests')),
                challenge=record['workload'].get('challenge') or 'faster',
                search_mode='evolve' if external and record['mode'] == 'full' else 'compare',
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
                          progress=_progress(
                              'checking_correctness', 2, 4,
                              'Deploying the baseline and each candidate in the isolated stack'
                              if record.get('evaluation_type') == 'backend_architecture'
                              else 'Running the real baseline and candidate on the same ledgers'))
            self.store.save_evaluation(record, 'Correctness harness prepared')

            measurements = adapter.measure(prepared, candidate, budget,
                                           lambda: self._check(stop))
            if self._check(stop):
                raise AdapterCancelled('Cancelled before the verdict')
            record.update(stage='measuring',
                          progress=_progress(
                              'measuring', 3, 4,
                              'Comparing measured live architecture runs'
                              if record.get('evaluation_type') == 'backend_architecture'
                              else 'Comparing measured report-calculation time'))
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
            if record.get('evaluation_type') == 'backend_architecture':
                # The API must be able to show every measured run, not a hidden
                # summary. benchmark.json keeps the same data as evidence.
                record['architecture'] = {
                    'challenge': measurements.get('challenge'),
                    'runs': evidence.get('runs') or [],
                    'pareto': evidence.get('pareto') or [],
                    'comparison': evidence.get('comparison') or {},
                    'environment': evidence.get('environment') or {},
                    'complete': bool(measurements.get('complete', True)),
                    'skipped': measurements.get('skipped') or [],
                    'repetitions_requested': measurements.get('repetitions_requested'),
                }
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

    def execute_screening(self, ident: str) -> None:
        """Run the deterministic model. No repository code or dependency is touched."""
        record = None
        inspection = None
        stop = self.cancels.get(ident) or threading.Event()
        try:
            with self.guard:
                record = self.store.get_evaluation(ident)
                if record['status'] in TERMINAL:
                    return
                record.update(
                    status='running', stage='preparing', started_at=now(),
                    progress=_progress('preparing', 1, 4,
                                       'Loading the read-only architecture model'),
                )
                self.store.save_evaluation(record, 'Loading the inspected architecture model')
            inspection = self.store.get_inspection(record['inspection_id'])
            if self._check(stop):
                raise AdapterCancelled('Cancelled before screening')
            analysis = {
                'project': inspection.get('project') or {},
                'architecture': inspection.get('architecture') or {},
                'hotspots': inspection.get('hotspots') or [],
                'screening': inspection.get('screening') or {},
            }
            with self.guard:
                record.update(
                    stage='simulating',
                    progress=_progress('simulating', 2, 4,
                                       'Evaluating deployment variants with the deterministic model'),
                )
                self.store.save_evaluation(record, 'Simulating architecture variants')
            if self._check(stop):
                raise AdapterCancelled('Cancelled during screening')
            result = screen_repository(analysis, record['mode'])
            record['screening'] = result
            record['recommendation'] = result['recommendation']
            record['verdict'] = result['verdict']
            record['correctness'] = result['verdict']['correctness']
            record['measurements'] = []
            record.update(
                stage='evaluating',
                progress=_progress('evaluating', 3, 4,
                                   'Checking seed sensitivity and recommendation policy'),
            )
            self.store.save_evaluation(record, 'Screening policy evaluated')
            if self._check(stop):
                raise AdapterCancelled('Cancelled before the screening recommendation')
            record['stage'] = 'verdict'
            record['progress'] = _progress('verdict', 4, 4,
                                           'Simulated recommendation recorded')
            self._write_screening_evidence(record, inspection)
            record['status'] = 'completed'
            record['stage'] = 'done'
            record['progress'] = _progress('done', 4, 4, 'Screening complete')
            record['cleanup_status'] = 'completed'
            record['finished_at'] = now()
        except AdapterCancelled as exc:
            if record is None:
                raise
            record.update(status='cancelled', stage='cancelled', error=str(exc),
                          cleanup_status='completed', finished_at=now())
            record['verdict'] = empty_screening_verdict(
                'The screening was cancelled. No recommendation is reported.'
            )
            record['correctness'] = record['verdict']['correctness']
            record['recommendation'] = record['verdict']['recommendation']
            record['screening'] = None
            self._safe_failure_evidence(record, inspection)
        except BaseException as exc:
            if record is None:
                raise
            record.update(status='failed', stage='failed', error=str(exc),
                          cleanup_status='requires_review', finished_at=now())
            record['verdict'] = empty_screening_verdict(
                'The screening model stopped unexpectedly. No recommendation is reported.'
            )
            record['correctness'] = record['verdict']['correctness']
            record['recommendation'] = record['verdict']['recommendation']
            record['screening'] = None
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
                record['verdict'] = empty_screening_verdict(
                    'The screening stopped before a recommendation. No result is reported.'
                )
                record['correctness'] = record['verdict']['correctness']
                record['recommendation'] = record['verdict']['recommendation']
                record['screening'] = None
            try:
                self.store.save_evaluation(record, 'Screening finished')
            finally:
                with self.guard:
                    self.cancels.pop(ident, None)

    def _safe_failure_evidence(self, record: dict, inspection: dict | None) -> None:
        """Failure evidence is useful but must never take down the worker."""
        try:
            if record.get('adapter_id') == SCREENING_ADAPTER_ID:
                self._write_screening_failure_evidence(record, inspection or {})
            else:
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

    def _write_screening_failure_evidence(self, record: dict, inspection: dict) -> None:
        folder = self.store.root / record['evidence']['dir']
        folder.mkdir(parents=True, exist_ok=True)
        _write_json(folder / 'source.json', {
            'source': _public(inspection.get('source', {})),
            'adapter': {'adapter_id': record.get('adapter_id'),
                        'adapter_version': record.get('adapter_version')},
            'inspection_id': record.get('inspection_id'),
            'evidence_kind': 'simulated',
        })
        _write_json(folder / 'architecture.json', {
            'project': _public(inspection.get('project') or {}),
            'backend': (inspection.get('project') or {}).get('backend') or {},
            'architecture': inspection.get('architecture') or {},
            'hotspots': inspection.get('hotspots') or [],
            'facts': inspection.get('facts') or [],
            'not_supported': inspection.get('not_supported') or [],
            'guesses': inspection.get('guesses') or [],
            'screening_support': inspection.get('screening') or {},
        })
        _write_json(folder / 'workload.json', {
            'preset': record.get('mode'),
            'seeds': (record.get('workload') or {}).get('seeds'),
            'note': 'No screening result was retained. No repository code was executed.',
        })
        _write_json(folder / 'verdict.json', record.get('verdict') or {})
        (folder / 'project-note.md').write_text(
            self._project_note_markdown(inspection), encoding='utf-8'
        )
        self._register_evidence(record, folder)

    def _write_screening_evidence(self, record: dict, inspection: dict) -> None:
        folder = self.store.root / record['evidence']['dir']
        folder.mkdir(parents=True, exist_ok=True)
        backend = (inspection.get('project') or {}).get('backend') or {}
        _write_json(folder / 'source.json', {
            'source': _public(inspection.get('source', {})),
            'adapter': {'adapter_id': record['adapter_id'],
                        'adapter_version': record['adapter_version']},
            'inspection_id': record['inspection_id'],
            'evidence_kind': 'simulated',
        })
        _write_json(folder / 'architecture.json', {
            'project': _public(inspection.get('project') or {}),
            'backend': backend,
            'architecture': inspection.get('architecture') or {},
            'hotspots': inspection.get('hotspots') or [],
            'facts': inspection.get('facts') or [],
            'not_supported': inspection.get('not_supported') or [],
            'guesses': inspection.get('guesses') or [],
            'screening_support': inspection.get('screening') or {},
        })
        _write_json(folder / 'workload.json', {
            'preset': record['mode'],
            'seeds': record['workload']['seeds'],
            'fixtures': record['workload']['fixtures'],
            'note': record['workload'].get('note'),
            'model_workload': (record.get('screening') or {}).get('workload'),
            'assumptions': (record.get('screening') or {}).get('assumptions'),
        })
        _write_json(folder / 'screening.json', record.get('screening') or {})
        _write_json(folder / 'verdict.json', record.get('verdict') or {})
        (folder / 'project-note.md').write_text(
            self._project_note_markdown(inspection), encoding='utf-8'
        )
        recommendation = record.get('recommendation') or {}
        (folder / 'replay.md').write_text(
            '# Replay this simulated architecture screening\n\n'
            f'- Evaluation: `{record["evaluation_id"]}`\n'
            f'- Adapter: `{record["adapter_id"]}` version `{record["adapter_version"]}`\n'
            f'- Source: {record["source"]["url"]} at `{record["source"]["commit_sha"]}`\n'
            f'- Mode: `{record["mode"]}`\n'
            f'- Evidence kind: `simulated`\n'
            f'- Recommendation: `{recommendation.get("status", "INCONCLUSIVE")}`\n\n'
            '## API replay\n\n'
            '```powershell\n'
            f'$body = @{{ inspection_id = "{record["inspection_id"]}"; '
            f'adapter_id = "{record["adapter_id"]}"; mode = "{record["mode"]}"; '
            'consent = $true } | ConvertTo-Json\n'
            'Invoke-RestMethod http://127.0.0.1:8000/api/project-evaluations -Method Post '
            '-ContentType application/json -Body $body\n'
            '```\n\n'
            '## What ran\n\n'
            'The deterministic `architecture-screening-v1` model read the architecture recorded in '
            '`architecture.json` and evaluated deployment-level controls. No repository code, '
            'dependency, package manager, container or service was started. The source checkout '
            'was never edited, committed or pushed.\n\n'
            '## Important\n\n'
            'The recommendation is SIMULATED and NOT_MEASURED. It is an uncalibrated candidate for '
            'real deployment validation, not a measured winner.\n',
            encoding='utf-8',
        )
        self._register_evidence(record, folder)

    @staticmethod
    def _project_note_markdown(inspection: dict) -> str:
        project = inspection.get('project') or {}
        note = project.get('note') or {}
        backend = project.get('backend') or {}
        lines = [
            f'# {project.get("display_type") or "Project"}',
            '',
            (project.get('summary') or 'No summary was recorded.'),
            '',
            '## What the project is',
            '',
            note.get('what_it_is') or 'Not classified from source.',
            '',
            '## How the backend works',
            '',
            note.get('backend') or 'No backend request path was detected.',
            '',
            note.get('how_it_works') or '',
            '',
            '## Evolution scope',
            '',
            note.get('evolution') or '',
            '',
            '## Evidence',
            '',
            f'- Services detected: {len(backend.get("services") or [])}',
            f'- HTTP routes detected: {backend.get("route_count", 0)}',
            f'- Data stores detected: {len(backend.get("datastores") or [])}',
            f'- Queues detected: {len(backend.get("queues") or [])}',
            f'- External integrations detected: {len(backend.get("external_services") or [])}',
            '',
            'Every statement above comes from the inspected source. No repository code was executed.',
            '',
        ]
        return '\n'.join(lines)

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
            'challenge': record['workload'].get('challenge'),
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
        if record.get('evaluation_type') == 'backend_architecture':
            benchmark = {
                'evidence_kind': 'live',
                'runs': measurements.get('runs') or [],
                'pareto': measurements.get('pareto') or [],
                'complete': measurements.get('complete'),
                'skipped': measurements.get('skipped') or [],
                'repetitions_requested': measurements.get('repetitions_requested'),
                'wall_clock_s': measurements.get('wall_clock_s'),
                'environment': measurements.get('environment'),
                'note': (
                    'Each run deployed a DARWIN-owned isolated Compose stack on loopback. '
                    'The repository Compose file and Dockerfile were not used. '
                    'Latency, throughput and recovery were measured live; simulation never wins.'
                ),
            }
        _write_json(folder / 'benchmark.json', benchmark)
        _write_json(folder / 'parity.json', {
            'passed': (evidence.get('parity') or {}).get('passed'),
            'checks': evidence.get('checks', []),
            'source_tests': evidence.get('source_tests'),
        })
        _write_json(folder / 'verdict.json', evidence.get('verdict') or {})
        (folder / 'change.md').write_text(
            _change_text(record, evidence.get('verdict') or {}), encoding='utf-8')
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
            f'mode = "{record["mode"]}"; challenge = "{record["workload"].get("challenge") or "faster"}"; '
            'consent = $true } | ConvertTo-Json\n'
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
            # Only reviewed artifacts are ever registered. Stray or partial files in
            # the working folder must never become downloadable evidence.
            if not path.is_file() or path.name not in ARTIFACT_NAMES \
                    or path.name in ('manifest.json', 'evidence.zip'):
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

    def export_change(self, ident: str) -> str:
        record = self.store.get_evaluation(ident)
        verdict = record.get('verdict') or {}
        if record.get('status') != 'completed' or verdict.get('status') not in {
                'VERIFIED_IMPROVEMENT', 'TRADEOFF_REQUIRES_CHOICE'}:
            raise ValueError(
                'No measured architecture change is exported for verdict '
                f'{verdict.get("status") or record.get("status")}.'
            )
        try:
            return self.evidence_path(ident, 'change.md').read_text(encoding='utf-8')
        except (KeyError, OSError):
            pass
        try:
            return _change_text(record, verdict)
        except (KeyError, TypeError):
            raise ValueError(
                'The recorded change is incomplete; no deployment change is exported.'
            ) from None

    def list_evaluations(self) -> list[dict]:
        return self.store.all_evaluations()

    def events(self, ident: str, after: int = 0) -> list[dict]:
        return self.store.events(ident, after)

    def evidence_path(self, ident: str, name: str) -> Path:
        record = self.store.get_evaluation(ident)
        evidence = record.get('evidence') or {}
        registered = next((item for item in (evidence.get('files') or [])
                           if isinstance(item, dict) and item.get('name') == name), None)
        if name not in ARTIFACT_NAMES or not registered or not evidence.get('dir'):
            raise KeyError(name)
        digest = registered.get('sha256')
        folder = (self.store.root / evidence['dir']).resolve()
        path = (folder / name).resolve()
        if not digest or not path.is_relative_to(folder) or not path.is_file() \
                or _digest(path) != digest:
            raise KeyError(name)
        return path

    def bundle(self, ident: str) -> Path:
        record = self.store.get_evaluation(ident)
        evidence = record.get('evidence') or {}
        if not evidence.get('dir'):
            raise KeyError('manifest')
        folder = (self.store.root / evidence['dir']).resolve()
        manifest_path = folder / 'manifest.json'
        if not manifest_path.is_file():
            raise KeyError('manifest')
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        files = manifest.get('files')
        if not isinstance(files, dict):
            raise ValueError('The evidence manifest has no file table.')
        # Only reviewed artifacts may leave the host. A stray manifest entry is
        # ignored rather than packed, so the bundle cannot widen the download surface.
        packed = {name: digest for name, digest in files.items() if name in ARTIFACT_NAMES}
        for name, digest in packed.items():
            path = (folder / name).resolve()
            if not path.is_file() or not path.is_relative_to(folder) or _digest(path) != digest:
                raise ValueError(f'Evidence file failed digest verification: {name}')
        source = record.get('source') or {}
        target = folder / f'darwin-project-evidence-{ident}.zip'
        temporary = folder / f'.bundle-{uuid4().hex}.zip'
        with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as archive:
            for name in sorted(packed):
                archive.write(folder / name, arcname=name)
            archive.write(manifest_path, arcname='manifest.json')
            archive.writestr('README.txt',
                             'DARWIN Real Project Mode evidence bundle.\n'
                             f'Evaluation: {ident}\n'
                             f'Source commit: {source.get("commit_sha", "unknown")}\n'
                             'Verify every file against manifest.json before trusting it.\n')
        os.replace(temporary, target)
        return target

    def close(self) -> None:
        self.shutdown.set()
        for event in list(self.cancels.values()):
            event.set()
        self.worker.join(timeout=30)
