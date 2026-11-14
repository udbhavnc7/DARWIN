"""Single-worker, durable smoke and measured experiments."""
import hashlib
import json
import os
from pathlib import Path
import queue
import sqlite3
import threading
import time
from datetime import datetime, timezone
from uuid import uuid4
from typing import Literal

from filelock import FileLock
from pydantic import Field, model_validator

from darwin.architecture import ROOT, deployment_resources, genome_hash
from darwin.contracts import ExperimentRequest, Genome

TERMINAL = {'completed', 'failed', 'cancelled'}
FAULT_MODES = {'native_faults', 'docker_faults'}
MEASURED_MODES = FAULT_MODES | {'native_benchmark', 'docker_benchmark'}


class StartExperiment(ExperimentRequest):
    mode: Literal['native_smoke', 'docker_smoke', 'native_benchmark', 'docker_benchmark',
                  'native_faults', 'docker_faults'] = 'native_smoke'
    fault_fixture: Literal['safe', 'unsafe_retry'] = 'safe'
    genomes: list[Genome] = Field(default_factory=lambda: [Genome()], min_length=1, max_length=36)

    @model_validator(mode='after')
    def supported(self):
        if self.mode in FAULT_MODES:
            if not self.fault_scenarios or len(set(self.fault_scenarios)) != len(self.fault_scenarios):
                raise ValueError('Fault tests require a nonempty list of distinct scenarios')
            if self.fault_fixture == 'unsafe_retry' and 'timeout_retry_duplicate' not in self.fault_scenarios:
                raise ValueError('The unsafe retry fixture requires the payment-reply-loss scenario')
        elif self.fault_scenarios or self.fault_fixture != 'safe':
            raise ValueError('Fault scenarios and fixtures require a fault execution mode')
        if self.mode in ('native_benchmark', 'native_faults'):
            if os.name != 'nt' or not float(self.budget.sandbox_cpu_cores).is_integer():
                raise ValueError('Native benchmarks require Windows and whole logical CPUs')
        elif self.mode not in MEASURED_MODES and (self.workload_profile != 'normal' or self.constraints.max_p95_ms is not None):
            raise ValueError('Smoke experiments accept only the normal profile without a latency target')
        if len(self.genomes) > self.budget.max_candidates:
            raise ValueError('Candidate count exceeds max_candidates')
        if len(self.genomes) * self.budget.repetitions > self.budget.real_test_budget:
            raise ValueError('Real-test budget must cover every requested repetition')
        if len({genome_hash(g) for g in self.genomes}) != len(self.genomes):
            raise ValueError('Duplicate genomes are not separate candidates')
        for genome in self.genomes:
            cpu, memory = deployment_resources(genome)
            if cpu > self.budget.sandbox_cpu_cores + 1e-9:
                raise ValueError('Candidate exceeds configured CPU budget')
            if memory > self.budget.sandbox_memory_mb:
                raise ValueError('Candidate exceeds configured memory budget')
        return self


def now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, default=str), encoding='utf-8')


class Stopped(Exception):
    pass


class Store:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = self.root / 'experiments.sqlite3'
        with self.connect() as conn:
            conn.executescript('''CREATE TABLE IF NOT EXISTS experiments(id TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events(experiment_id TEXT, sequence INTEGER, data TEXT NOT NULL,
                PRIMARY KEY(experiment_id,sequence));''')

    def connect(self):
        return sqlite3.connect(self.db, timeout=10)

    def get(self, ident):
        with self.connect() as conn:
            row = conn.execute('SELECT data FROM experiments WHERE id=?', (ident,)).fetchone()
        if not row:
            raise KeyError(ident)
        return json.loads(row[0])

    def all(self):
        with self.connect() as conn:
            return [json.loads(row[0]) for row in conn.execute('SELECT data FROM experiments ORDER BY rowid DESC')]

    def save(self, value, message):
        with self.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            conn.execute('INSERT INTO experiments VALUES (?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data', (value['experiment_id'], json.dumps(value)))
            sequence = conn.execute('SELECT COALESCE(MAX(sequence),0)+1 FROM events WHERE experiment_id=?', (value['experiment_id'],)).fetchone()[0]
            event = {'experiment_id': value['experiment_id'], 'sequence': sequence, 'occurred_at': now(),
                     'type': 'experiment_status', 'status': value['status'], 'message': message}
            conn.execute('INSERT INTO events VALUES (?,?,?)', (value['experiment_id'], sequence, json.dumps(event)))

    def events(self, ident, after=0):
        with self.connect() as conn:
            return [json.loads(row[0]) for row in conn.execute('SELECT data FROM events WHERE experiment_id=? AND sequence>? ORDER BY sequence', (ident, after))]


class Engine:
    def __init__(self, root, adapter_factory=None):
        self.store = Store(root)
        self.lock = FileLock(str(self.store.root / 'worker.lock'))
        self.lock.acquire(timeout=0)
        self.pending = queue.Queue()
        self.cancels = {}
        self.guard = threading.Lock()
        self.shutdown = threading.Event()
        self.factory = adapter_factory
        self.recovery_required = False
        for record in self.store.all():
            if record['status'] not in TERMINAL:
                record.update(status='failed', error='Worker interrupted; inspect owned sandbox resources before resuming.', cleanup_status='requires_review')
                self.store.save(record, record['error'])
            if record.get('cleanup_status') == 'requires_review':
                self.recovery_required = True
        self.worker = threading.Thread(target=self.loop, daemon=True, name='darwin-experiments')
        self.worker.start()

    def submit(self, request, rerun_of=None):
        with self.guard:
            if self.shutdown.is_set() or self.recovery_required:
                raise RuntimeError('Worker unavailable: shutdown or interrupted sandbox cleanup requires review')
            if sum(r['status'] not in TERMINAL for r in self.store.all()) >= 20:
                raise RuntimeError('Experiment queue is full')
            ident = str(uuid4())
            record = {'experiment_id': ident, 'created_at': now(), 'status': 'queued', 'request': request.model_dump(),
                      'candidates': [], 'attempts_used': 0, 'cleanup_status': 'not_started', 'rerun_of': rerun_of,
                      'measurement_kind': 'measured' if request.mode in MEASURED_MODES else 'smoke_only', 'resource_limits_enforced': False}
            for genome in request.genomes:
                record['candidates'].append({'candidate_id': str(uuid4()), 'genome': genome.model_dump(),
                                              'genome_hash': genome_hash(genome), 'evaluations': []})
            self.cancels[ident] = threading.Event()
            self.store.save(record, 'Queued experiment')
            self.pending.put(ident)
            return record

    def cancel(self, ident):
        with self.guard:
            record = self.store.get(ident)
            if record['status'] not in TERMINAL:
                self.cancels[ident].set()
                if record['status'] == 'queued':
                    record.update(status='cancelled', finished_at=now(), cleanup_status='not_needed')
                    self.store.save(record, 'Cancelled before execution')
            return self.store.get(ident)

    def check(self, stop, deadline):
        if stop.is_set() or self.shutdown.is_set():
            raise Stopped('Cancelled')
        if time.monotonic() >= deadline:
            raise TimeoutError('Experiment wall-clock budget exhausted')

    def loop(self):
        while not self.shutdown.is_set():
            try:
                ident = self.pending.get(timeout=.2)
            except queue.Empty:
                continue
            self.execute(ident)

    def execute(self, ident):
        with self.guard:
            record = self.store.get(ident)
            if record['status'] in TERMINAL:
                return
            if self.recovery_required:
                record.update(status='failed', cleanup_status='not_needed', finished_at=now(), error='Earlier sandbox cleanup requires review')
                self.store.save(record, record['error'])
                return
            record.update(status='running', started_at=now())
            self.store.save(record, 'Worker started')
        request = StartExperiment.model_validate(record['request'])
        deadline = time.monotonic() + request.budget.wall_clock_s
        stop = self.cancels[ident]
        root = self.store.root / ident
        try:
            root.mkdir()
            # Retain the exact source inputs, including uncommitted files.
            source = root / 'source'
            source.mkdir()
            files = list((ROOT / 'backend').rglob('*.py')) + [
                ROOT / name for name in ('Dockerfile', '.dockerignore', 'compose.yaml',
                                         'pyproject.toml', 'requirements.lock.txt')
            ]
            hashes = {}
            for path in files:
                self.check(stop, deadline)
                relative = path.relative_to(ROOT)
                dest = source / relative
                dest.parent.mkdir(parents=True, exist_ok=True)
                data = path.read_bytes()
                dest.write_bytes(data)
                hashes[relative.as_posix()] = hashlib.sha256(data).hexdigest()
            record['source_hash'] = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
            write_json(root / 'source-manifest.json', hashes)
            candidates = record['candidates']
            for repetition in range(request.budget.repetitions):
                offset = repetition % len(candidates)
                for candidate in candidates[offset:] + candidates[:offset]:
                    attempt = request
                    if request.mode in MEASURED_MODES:
                        attempt = request.model_copy(update={'seed': (request.seed + repetition) % 2**32})
                    self.check(stop, deadline)
                    if record['attempts_used'] >= request.budget.real_test_budget:
                        raise RuntimeError('Real-test budget exhausted')
                    record['attempts_used'] += 1
                    evaluation = {'evaluation_id': str(uuid4()), 'repetition': repetition, 'status': 'running',
                                  'gate': 'not_checked', 'seed': attempt.seed, 'artifacts': []}
                    candidate['evaluations'].append(evaluation)
                    folder = root / evaluation['evaluation_id']
                    folder.mkdir()
                    if request.mode in FAULT_MODES:
                        write_json(folder / 'replay-request.json', {**request.model_dump(), 'genomes': [candidate['genome']]})
                        (folder / 'replay.ps1').write_text(
                            "# Replays the same seeds and scenarios using the currently running DARWIN source.\n"
                            "Invoke-RestMethod http://127.0.0.1:8000/api/experiments -Method Post -ContentType application/json "
                            "-Body (Get-Content -Raw (Join-Path $PSScriptRoot 'replay-request.json'))\n", encoding='utf-8')
                    self.store.save(record, f'Starting attempt {record["attempts_used"]}')
                    adapter = None
                    check = lambda: self.check(stop, deadline)
                    try:
                        if self.factory:
                            adapter = self.factory(attempt, candidate, folder, source)
                        elif request.mode.startswith('docker_'):
                            from darwin.docker_sandbox import DockerSandbox
                            adapter = DockerSandbox(attempt, candidate, folder, source)
                        elif request.mode == 'native_faults':
                            from darwin.fault_sandbox import FaultSandbox
                            adapter = FaultSandbox(attempt, candidate, folder, source)
                        elif request.mode == 'native_benchmark':
                            from darwin.measured_sandbox import MeasuredSandbox
                            adapter = MeasuredSandbox(attempt, candidate, folder, source)
                        else:
                            from darwin.sandbox import Sandbox
                            adapter = Sandbox(request, candidate, folder, source)
                        result = adapter.run(check)
                        record['resource_limits_enforced'] = bool(result.get('resource_limits_enforced', False))
                        check()
                        if request.mode in MEASURED_MODES:
                            evaluation.update(metrics=result['metrics'], tier='measured')
                            if request.mode in FAULT_MODES:
                                evaluation.update(gate=result['gate'], violations=result['violations'],
                                                  gate_reasons=result['gate_reasons'], recovery=result['recovery'])
                            write_json(folder / 'measurement.json', result)
                        else:
                            write_json(folder / 'smoke.json', result)
                        evaluation['status'] = 'completed'
                    except BaseException as exc:
                        evaluation.update(status='cancelled' if isinstance(exc, Stopped) else 'failed', error=str(exc))
                        if request.mode in FAULT_MODES:
                            evaluation.update(gate='failed', gate_reasons=['execution_incomplete'])
                        raise
                    finally:
                        try:
                            if adapter is not None:
                                adapter.close()
                            record['cleanup_status'] = 'completed'
                        except Exception as cleanup_error:
                            record.update(cleanup_status='requires_review', cleanup_error=str(cleanup_error))
                            if request.mode in FAULT_MODES:
                                evaluation.update(gate='failed', gate_reasons=['cleanup_unverified'])
                            self.recovery_required = True
                        if request.mode in FAULT_MODES:
                            for name in ('fault-report.json', 'measurement.json'):
                                report_path = folder / name
                                if report_path.exists():
                                    report = json.loads(report_path.read_text(encoding='utf-8'))
                                    report.update(gate=evaluation['gate'], gate_reasons=evaluation.get('gate_reasons', []),
                                                  cleanup_status=record['cleanup_status'])
                                    write_json(report_path, report)
                        manifest = {'evaluation_id': evaluation['evaluation_id'], 'candidate': candidate['genome'],
                                    'source_hash': record['source_hash'], 'seed': attempt.seed, 'mode': request.mode,
                                    'status': evaluation['status'], 'cleanup_status': record['cleanup_status'],
                                    'measurement_kind': record['measurement_kind'], 'workload_profile': request.workload_profile,
                                    'fault_fixture': request.fault_fixture, 'fault_scenarios': request.fault_scenarios,
                                    'gate': evaluation['gate'], 'files': {}}
                        for artifact in folder.iterdir():
                            if artifact.is_file():
                                digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
                                manifest['files'][artifact.name] = digest
                                evaluation['artifacts'].append({'name': artifact.name, 'sha256': digest})
                        write_json(folder / 'manifest.json', manifest)
                        evaluation['artifacts'].append({'name': 'manifest.json', 'sha256': hashlib.sha256((folder / 'manifest.json').read_bytes()).hexdigest()})
                        self.store.save(record, f'Attempt {record["attempts_used"]}: {evaluation["status"]}')
                    if self.recovery_required:
                        raise RuntimeError('Sandbox cleanup failed; additional runs are blocked')
            self.check(stop, deadline)
            if request.mode in MEASURED_MODES:
                from darwin.performance import summarize
                for candidate in candidates:
                    candidate['summary'] = summarize(candidate['evaluations'], request)
                    if request.mode in FAULT_MODES:
                        candidate['summary']['gate'] = 'passed' if all(e['gate'] == 'passed' for e in candidate['evaluations']) else 'failed'
                write_json(root / 'comparison.json', {'experiment_id': ident, 'source_hash': record['source_hash'],
                           'request': record['request'], 'candidates': candidates})
            record['status'] = 'completed'
        except Exception as exc:
            record.update(status='cancelled' if isinstance(exc, Stopped) else 'failed', error=str(exc))
        finally:
            record['finished_at'] = now()
            self.store.save(record, f'Experiment {record["status"]}')

    def close(self):
        self.shutdown.set()
        for event in self.cancels.values():
            event.set()
        self.worker.join(timeout=45)
        if not self.worker.is_alive():
            for record in self.store.all():
                if record['status'] == 'queued':
                    record.update(status='cancelled', cleanup_status='not_needed', finished_at=now())
                    self.store.save(record, 'Server shutdown before execution')
            self.lock.release()
