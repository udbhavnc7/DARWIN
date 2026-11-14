"""Exercise Docker smoke, measurement, fault gates and search on a local engine."""
import argparse
import json
from pathlib import Path
from statistics import median
import time

from darwin.docker_resources import docker_status
from darwin.experiments import Engine, StartExperiment, TERMINAL, write_json
from darwin.search import SearchEngine, SearchRequest


def finish(worker, record, timeout):
    deadline = time.monotonic() + timeout
    ident = record['experiment_id']
    while record['status'] not in TERMINAL:
        if time.monotonic() >= deadline:
            worker.cancel(ident)
            raise TimeoutError(f'Acceptance run {ident} exceeded its deadline')
        time.sleep(1)
        record = worker.store.get(ident)
    return record


RECOVERY_SCENARIOS = {'database_latency', 'database_disconnect', 'application_outage'}


def recovery_summary(record):
    """Keep the recovery windows that the safe fault run actually observed."""
    windows = {}
    for candidate in record['candidates']:
        for evaluation in candidate['evaluations']:
            for item in evaluation.get('recovery', []):
                windows.setdefault(item['scenario'], []).append(item['recovery_s'])
    return {scenario: {'repetitions': len(values), 'median_s': round(median(values), 2),
                       'max_s': round(max(values), 2)}
            for scenario, values in sorted(windows.items()) if all(value is not None for value in values)}


def validate_run(case, record):
    evaluations = [item for candidate in record['candidates'] for item in candidate['evaluations']]
    if record['status'] != 'completed' or record['cleanup_status'] != 'completed':
        raise RuntimeError(record.get('error') or f'{case} failed execution or cleanup')
    expected = len(record['request']['genomes']) * record['request']['budget']['repetitions']
    if len(evaluations) != expected or any(row['status'] != 'completed' for row in evaluations):
        raise RuntimeError(f'{case} did not finish every repetition')
    if case == 'smoke':
        return
    if not record['resource_limits_enforced'] or any(row.get('tier') != 'measured' for row in evaluations):
        raise RuntimeError(f'{case} is missing verified measurements')
    if case == 'safe':
        if any(row['gate'] != 'passed' for row in evaluations):
            reasons = sorted({reason for row in evaluations for reason in row.get('gate_reasons', [])})
            raise RuntimeError(f'The safe Docker configuration failed a fault gate: {", ".join(reasons)}')
        for row in evaluations:
            claims = {item['scenario']: item for item in row.get('recovery', [])}
            if set(claims) != RECOVERY_SCENARIOS:
                raise RuntimeError('The safe Docker run did not observe every recovery window')
            if any(not item.get('fault_observed') or not item.get('schedule_valid')
                   or item.get('recovery_s') is None for item in claims.values()):
                raise RuntimeError('A Docker recovery window was missing, censored or unverified')
    if case == 'unsafe' and any(
            row['gate'] != 'failed' or not any(item['invariant_id'] == 'I-01' for item in row['violations'])
            for row in evaluations):
        raise RuntimeError('The Docker fixture did not reproduce duplicate-payment rejection')


def validate_search(engine, result):
    if (result['status'] != 'completed' or result['generation'] != 2 or result['attempts_used'] != 6
            or len(result['experiment_ids']) != 2):
        raise RuntimeError(result.get('error') or 'Docker search did not finish both generations')
    for ident in result['experiment_ids']:
        validate_run('search', engine.store.get(ident))


def existing_result(worker, report, name, request, validate):
    ident = report['cases'].get(name)
    if ident:
        try:
            result = worker.store.get(ident)
            if result['request'] != request.model_dump():
                raise ValueError('Acceptance request changed')
            validate(result)
        except (KeyError, RuntimeError, ValueError):
            previous = report.setdefault('previous_cases', {}).setdefault(name, [])
            if ident not in previous:
                previous.append(ident)
        else:
            print(f'{name} verified from existing evidence {ident}', flush=True)
            return True
    return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='Directory for acceptance evidence')
    parser.add_argument('--resume', action='store_true', help='Reuse verified cases in the output directory')
    args = parser.parse_args()
    if docker_status() != '2':
        parser.error('Live acceptance needs a local Linux Docker engine with cgroup v2 and Compose')
    root = args.output.resolve()
    report_path = root / 'acceptance.json'
    if args.resume:
        if not report_path.is_file():
            parser.error('--resume requires a previous acceptance.json')
        report = json.loads(report_path.read_bytes())
        report.update(status='running')
        report.pop('error', None)
    else:
        root.mkdir(parents=True, exist_ok=False)
        report = {'status': 'running', 'cases': {}}
    faults = ['db_delay', 'service_outage', 'timeout_retry_duplicate']
    cases = [
        ('smoke', StartExperiment(mode='docker_smoke')),
        ('benchmark', StartExperiment(mode='docker_benchmark', genomes=[{}, {
            'app_replicas': 3, 'catalog_cache_ttl_s': 10, 'notification_mode': 'queued',
        }])),
        ('safe', StartExperiment(mode='docker_faults', fault_scenarios=faults,
                                 genomes=[{'notification_mode': 'queued'}])),
        ('unsafe', StartExperiment(mode='docker_faults', fault_scenarios=['timeout_retry_duplicate'],
                                   fault_fixture='unsafe_retry', genomes=[{'notification_mode': 'queued'}])),
    ]
    engine = Engine(root / 'experiments')
    search = None
    try:
        write_json(report_path, report)
        for name, request in cases:
            if existing_result(engine, report, name, request, lambda result: validate_run(name, result)):
                continue
            result = engine.submit(request)
            print(name, result['experiment_id'], flush=True)
            report['cases'][name] = result['experiment_id']
            write_json(report_path, report)
            result = finish(engine, result, request.budget.wall_clock_s + 90)
            validate_run(name, result)
        report['recovery'] = recovery_summary(engine.store.get(report['cases']['safe']))
        write_json(report_path, report)
        search = SearchEngine(engine)
        request = SearchRequest(runtime='docker', promotions_per_generation=1,
                                budget={'real_test_budget': 6, 'wall_clock_s': 1800})
        if not existing_result(search, report, 'search', request, lambda result: validate_search(engine, result)):
            result = search.submit(request)
            report['cases']['search'] = result['search_id']
            write_json(report_path, report)
            print('search', result['search_id'], flush=True)
            result = finish(search, result, request.budget.wall_clock_s + 90)
            validate_search(engine, result)
        report['status'] = 'passed'
    except BaseException as exc:
        report.update(status='failed', error=str(exc))
        raise
    finally:
        if search:
            search.close()
        engine.close()
        write_json(report_path, report)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
