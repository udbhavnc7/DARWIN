"""Bounded, measured-feedback search with constrained NSGA-II selection."""
import itertools
import math
import queue
import random
import threading
import time
from statistics import median
from typing import Literal
from uuid import uuid4

from filelock import FileLock
from pydantic import Field, model_validator

from darwin.architecture import deployment_resources, genome_hash
from darwin.calibration import calibrated_simulation
from darwin.contracts import Budget, Constraints, Contract, Fault, Genome, Workload
from darwin.experiments import StartExperiment, Store, TERMINAL, now

CONTROLS = {'app_replicas': (1, 2, 3), 'catalog_cache_ttl_s': (0, 10, 30),
            'notification_mode': ('sync', 'queued'), 'retry_policy': ('none', 'idempotent_only')}


class SearchRequest(Contract):
    algorithm: Literal['random', 'hill_climbing', 'nsga2'] = 'nsga2'
    runtime: Literal['native', 'docker'] = 'native'
    workload_profile: Workload = 'normal'
    fault_scenarios: list[Fault] = Field(default_factory=lambda: ['db_delay', 'service_outage', 'timeout_retry_duplicate'])
    seed: int = Field(default=42, ge=0, le=2**32 - 1)
    budget: Budget = Field(default_factory=lambda: Budget(real_test_budget=12, wall_clock_s=2400))
    constraints: Constraints = Field(default_factory=Constraints)
    generations: int = Field(default=2, ge=1, le=20)
    population_size: int = Field(default=4, ge=2, le=36)
    promotions_per_generation: int = Field(default=2, ge=1, le=12)
    use_simulator: bool = True

    @model_validator(mode='after')
    def validate_runner(self):
        StartExperiment(mode=f'{self.runtime}_faults', fault_scenarios=self.fault_scenarios,
                        budget=self.budget, constraints=self.constraints)
        return self


def all_genomes():
    return [Genome(**dict(zip(CONTROLS, values)))
            for values in itertools.product(*CONTROLS.values())]


def distance(left, right):
    return sum(left[key] != right[key] for key in CONTROLS)


def objectives(candidate, repetitions):
    evaluations = candidate.get('evaluations', [])
    if len(evaluations) != repetitions or any(
            row.get('gate') != 'passed' or row.get('status') != 'completed'
            or row.get('tier') != 'measured' for row in evaluations):
        return None
    values = []
    for key in ('p95_ms', 'cpu_seconds', 'recovery_s'):
        numbers = [row['metrics'].get(key) for row in evaluations]
        if any(value is None or not math.isfinite(value) or value < 0 for value in numbers):
            return None
        values.append(median(numbers))
    return values


def dominates(left, right):
    if left['objectives'] is None:
        return right['objectives'] is None and left['penalty'] < right['penalty']
    if right['objectives'] is None:
        return True
    return all(a <= b for a, b in zip(left['objectives'], right['objectives'])) and any(
        a < b for a, b in zip(left['objectives'], right['objectives']))


def fronts(rows):
    remaining = list(rows)
    layers = []
    while remaining:
        layer = [row for row in remaining if not any(dominates(other, row) for other in remaining)]
        layers.append(layer)
        ids = {row['genome_hash'] for row in layer}
        remaining = [row for row in remaining if row['genome_hash'] not in ids]
    return layers


def crowding(layer):
    scores = {row['genome_hash']: 0.0 for row in layer}
    feasible = [row for row in layer if row['objectives'] is not None]
    for dimension in range(3):
        ordered = sorted(feasible, key=lambda row: (row['objectives'][dimension], row['genome_hash']))
        if len(ordered) <= 2:
            for row in ordered:
                scores[row['genome_hash']] = math.inf
            continue
        spread = ordered[-1]['objectives'][dimension] - ordered[0]['objectives'][dimension]
        if spread == 0:
            continue
        scores[ordered[0]['genome_hash']] = scores[ordered[-1]['genome_hash']] = math.inf
        for index in range(1, len(ordered) - 1):
            scores[ordered[index]['genome_hash']] += (
                ordered[index + 1]['objectives'][dimension] - ordered[index - 1]['objectives'][dimension]) / spread
    return scores


def select_population(rows, size):
    ordered = []
    for layer in fronts(rows):
        scores = crowding(layer)
        ordered.extend(sorted(layer, key=lambda row: (-scores[row['genome_hash']], row['genome_hash'])))
    return ordered[:size]


def propose(request, rng, seen, population):
    available = []
    for genome in all_genomes():
        if genome_hash(genome) in seen:
            continue
        cpu, memory = deployment_resources(genome)
        if cpu <= request.budget.sandbox_cpu_cores + 1e-9 and memory <= request.budget.sandbox_memory_mb:
            available.append(genome)
    count = min(request.population_size, request.budget.max_candidates - len(seen), len(available))
    if count <= 0:
        return []
    result = []
    if not seen:
        baseline = Genome()
        result.append((baseline, []))
        available.remove(baseline)
    elif request.algorithm == 'hill_climbing' and population:
        incumbent = min(population, key=lambda row: (
            row['objectives'] is None, row['objectives'] or [row['penalty']], row['genome_hash']))
        neighbors = [genome for genome in available if distance(genome.model_dump(), incumbent['genome']) == 1]
        rng.shuffle(neighbors)
        result.extend((genome, [incumbent['genome_hash']]) for genome in neighbors[:count])
    elif request.algorithm == 'nsga2' and population:
        ranked = select_population(population, request.population_size)
        positions = {row['genome_hash']: i for i, row in enumerate(ranked)}
        for _ in range(count * 20):
            parents = []
            for _ in range(2):
                contestants = rng.choices(ranked, k=2)
                parents.append(min(contestants, key=lambda row: positions[row['genome_hash']]))
            values = {key: rng.choice(parents)['genome'][key] for key in CONTROLS}
            mutation = rng.choice(list(CONTROLS))
            values[mutation] = rng.choice([value for value in CONTROLS[mutation] if value != values[mutation]])
            genome = Genome(**values)
            if genome in available and all(genome != item[0] for item in result):
                result.append((genome, sorted({parent['genome_hash'] for parent in parents})))
            if len(result) == count:
                break
    remaining = [genome for genome in available if all(genome != item[0] for item in result)]
    rng.shuffle(remaining)
    result.extend((genome, []) for genome in remaining[:count - len(result)])
    return result


def promote(rows, count, use_simulator):
    if count >= len(rows):
        return list(rows)
    baseline_hash = genome_hash(Genome())
    baseline = next((row for row in rows if row['genome_hash'] == baseline_hash), None)
    ordered = sorted(rows, key=lambda row: (
        row['simulation']['metrics']['p95_ms'] if use_simulator else 0, row['genome_hash']))
    selected = [baseline or ordered[0]]
    while len(selected) < count:
        remaining = [row for row in ordered if row not in selected]
        # Reserve alternate slots for uncertain/diverse proposals.
        chosen = max(remaining, key=lambda row: (
            min(distance(row['genome'], old['genome']) for old in selected), row['genome_hash']
        )) if len(selected) % 2 else remaining[0]
        selected.append(chosen)
    return selected


class SearchEngine:
    def __init__(self, engine):
        self.engine = engine
        self.store = Store(engine.store.root / 'searches')
        self.lock = FileLock(str(self.store.root / 'worker.lock'))
        self.lock.acquire(timeout=0)
        self.guard = threading.Lock()
        self.pending = queue.Queue()
        self.stopping = threading.Event()
        self.cancels = {}
        for record in self.store.all():
            if record['status'] not in TERMINAL:
                for ident in record['experiment_ids']:
                    if engine.store.get(ident)['status'] not in TERMINAL:
                        engine.cancel(ident)
                record.update(status='failed', error='Search coordinator was interrupted', finished_at=now())
                self.store.save(record, record['error'])
        self.worker = threading.Thread(target=self.loop, daemon=True, name='darwin-search')
        self.worker.start()

    def submit(self, request):
        with self.guard:
            if self.stopping.is_set() or self.engine.recovery_required:
                raise RuntimeError('Search worker unavailable')
            if any(row['status'] not in TERMINAL for row in self.store.all()):
                raise RuntimeError('Another search is active')
            ident = str(uuid4())
            record = {'experiment_id': ident, 'search_id': ident, 'created_at': now(),
                      'status': 'queued', 'request': request.model_dump(), 'candidates': [],
                      'experiment_ids': [], 'attempts_used': 0, 'pareto_ids': [], 'generation': 0,
                      'search_overhead_s': 0.0}
            self.cancels[ident] = threading.Event()
            self.store.save(record, 'Search queued')
            self.pending.put(ident)
            return record

    def cancel(self, ident):
        with self.guard:
            record = self.store.get(ident)
            if record['status'] not in TERMINAL:
                self.cancels[ident].set()
            return record

    def loop(self):
        while not self.stopping.is_set():
            try:
                ident = self.pending.get(timeout=.2)
            except queue.Empty:
                continue
            self.execute(ident)

    def execute(self, ident):
        record = self.store.get(ident)
        request = SearchRequest.model_validate(record['request'])
        rng = random.Random(request.seed)
        deadline = time.monotonic() + request.budget.wall_clock_s
        population = []
        active_id = None
        record.update(status='running', started_at=now())
        self.store.save(record, 'Search started')
        def cancelled():
            return self.stopping.is_set() or self.cancels[ident].is_set()
        try:
            for generation in range(request.generations):
                if cancelled():
                    break
                if time.monotonic() >= deadline:
                    raise TimeoutError('Search wall-clock budget exhausted')
                remaining_groups = (request.budget.real_test_budget - record['attempts_used']) // request.budget.repetitions
                if remaining_groups == 0:
                    break
                overhead_start = time.monotonic()
                proposals = propose(request, rng, {row['genome_hash'] for row in record['candidates']}, population)
                if not proposals:
                    break
                rows = []
                for genome, parents in proposals:
                    row = {'genome': genome.model_dump(), 'genome_hash': genome_hash(genome),
                           'parent_ids': parents, 'generation': generation, 'status': 'screened',
                           'objectives': None, 'penalty': 1, 'evaluations': []}
                    if request.use_simulator:
                        row['simulation'] = calibrated_simulation(
                            self.engine.store.root, genome, request.workload_profile, request.seed, 12, 0)
                    rows.append(row)
                promote_count = min(request.promotions_per_generation, remaining_groups)
                selected = rows[:promote_count] if request.algorithm == 'random' else promote(
                    rows, promote_count, request.use_simulator)
                for row in selected:
                    row['status'] = 'promoted'
                record['candidates'].extend(rows)
                record['generation'] = generation + 1
                record['search_overhead_s'] += time.monotonic() - overhead_start
                remaining_seconds = int(deadline - time.monotonic())
                if remaining_seconds < 60:
                    raise TimeoutError('Insufficient search time for another deployment')
                budget = request.budget.model_copy(update={
                    'real_test_budget': len(selected) * request.budget.repetitions,
                    'wall_clock_s': remaining_seconds})
                child = self.engine.submit(StartExperiment(
                    mode=f'{request.runtime}_faults', genomes=[Genome.model_validate(row['genome']) for row in selected],
                    seed=request.seed, workload_profile=request.workload_profile,
                    fault_scenarios=request.fault_scenarios, constraints=request.constraints, budget=budget))
                active_id = child['experiment_id']
                record['experiment_ids'].append(active_id)
                for row in selected:
                    row['experiment_id'] = active_id
                self.store.save(record, f'Generation {generation + 1}: measuring {len(selected)} configurations')
                while child['status'] not in TERMINAL:
                    if cancelled() or time.monotonic() >= deadline:
                        self.engine.cancel(active_id)
                    time.sleep(.2)
                    child = self.engine.store.get(active_id)
                record['attempts_used'] += child['attempts_used']
                for row, candidate in zip(selected, child['candidates']):
                    row.update(candidate_id=candidate['candidate_id'], evaluations=candidate['evaluations'],
                               summary=candidate.get('summary'), status='measured')
                    row['objectives'] = objectives(candidate, request.budget.repetitions)
                    row['penalty'] = sum(len(evaluation.get('gate_reasons', [])) for evaluation in candidate['evaluations']) + (
                        request.budget.repetitions - len(candidate['evaluations']))
                    if row['objectives'] is None:
                        row['penalty'] = max(1, row['penalty'])
                measured = [row for row in record['candidates'] if row['status'] == 'measured']
                population = select_population(population + selected, request.population_size)
                feasible = [row for row in measured if row['objectives'] is not None]
                record['pareto_ids'] = [row['genome_hash'] for row in fronts(feasible)[0]] if feasible else []
                self.store.save(record, f'Generation {generation + 1} collected; {len(feasible)} feasible configurations')
                if child['status'] == 'failed':
                    raise RuntimeError(f'Measured experiment failed: {child.get("error", active_id)}')
                if time.monotonic() >= deadline and not cancelled():
                    raise TimeoutError('Search wall-clock budget exhausted')
                if child['status'] == 'cancelled':
                    self.cancels[ident].set()
                    break
            record['status'] = 'cancelled' if cancelled() else 'completed'
        except Exception as exc:
            record.update(status='cancelled' if cancelled() else 'failed', error=str(exc))
            if active_id and self.engine.store.get(active_id)['status'] not in TERMINAL:
                self.engine.cancel(active_id)
        finally:
            record['finished_at'] = now()
            self.store.save(record, f'Search {record["status"]}')

    def close(self):
        self.stopping.set()
        self.worker.join(timeout=60)
        if not self.worker.is_alive():
            for record in self.store.all():
                if record['status'] == 'queued':
                    record.update(status='cancelled', finished_at=now())
                    self.store.save(record, 'Server shutdown before search execution')
            self.lock.release()
