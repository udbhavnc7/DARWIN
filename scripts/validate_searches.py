"""Run bounded, equal-budget local searches and retain their full evidence.

Pass several seeds and workloads to replace single-seed anecdotes with a
campaign: every strategy gets the same budget for every (workload, seed)
pair, and the report keeps every original search record.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from statistics import mean, median
import time

import httpx

STRATEGIES = [('nsga2', True), ('random', True), ('hill_climbing', True), ('nsga2', False)]


def save(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8000')
    parser.add_argument('--output', type=Path, default=Path('artifacts/validation/search-comparison.json'))
    parser.add_argument('--seed', type=int, default=72, help='Seed used when --seeds is omitted')
    parser.add_argument('--seeds', default='', help='Comma-separated seeds, for example 72,101,202')
    parser.add_argument('--workloads', default='normal', help='Comma-separated workload profiles')
    parser.add_argument('--resume', action='store_true', help='Keep completed searches and retry the interrupted strategy')
    args = parser.parse_args()
    seeds = [int(value) for value in args.seeds.split(',') if value.strip()] or [args.seed]
    workloads = [value.strip() for value in args.workloads.split(',') if value.strip()]
    if len(set(seeds)) != len(seeds) or len(set(workloads)) != len(workloads):
        raise SystemExit('Seeds and workloads must be unique')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    report = {'started_at': datetime.now(timezone.utc).isoformat(), 'status': 'running',
              'scope': f"{', '.join(workloads)} traffic; service outage, ambiguous payment retry, "
                       'all five invariants',
              'searches': [], 'seed': seeds[0], 'seeds': seeds, 'workloads': workloads,
              'caveat': 'Seeds change workload schedules on one machine; they do not vary hardware.'}
    if args.resume:
        report = json.loads(args.output.read_bytes())
        if report.get('seeds', [report['seed']]) != seeds or report.get('workloads', ['normal']) != workloads:
            raise SystemExit('Resume with the original seeds and workloads')
        if report['status'] == 'completed':
            raise SystemExit('This validation comparison is already complete')
        report['status'] = 'running'
        report.pop('error', None)
        report['seeds'], report['workloads'] = seeds, workloads
    elif args.output.exists():
        raise SystemExit('Choose a new output path to preserve the previous validation record')
    save(args.output, report)
    plan = [(workload, seed, algorithm, simulator)
            for workload in workloads for seed in seeds for algorithm, simulator in STRATEGIES]
    token = os.environ.get('DARWIN_API_TOKEN')
    headers = {'Authorization': f'Bearer {token}'} if token else {}
    with httpx.Client(base_url=args.url, timeout=20, trust_env=False, headers=headers) as client:
        for index, (workload, seed, algorithm, simulator) in enumerate(plan):
            body = {'algorithm': algorithm, 'use_simulator': simulator, 'seed': seed,
                    'workload_profile': workload,
                    'generations': 2, 'promotions_per_generation': 1, 'population_size': 4,
                    'fault_scenarios': ['service_outage', 'timeout_retry_duplicate'],
                    'budget': {'max_candidates': 8, 'real_test_budget': 6, 'wall_clock_s': 1800}}
            result = None
            if index < len(report['searches']):
                saved = report['searches'][index]
                response = client.get('/api/searches/' + saved['search_id'])
                response.raise_for_status()
                result = response.json()
                if result['status'] == 'completed':
                    report['searches'][index] = result
                    continue
                if result['status'] in ('failed', 'cancelled'):
                    report.setdefault('interrupted_searches', []).append(result)
                    result = None
            if result is None:
                response = client.post('/api/searches', json=body)
                response.raise_for_status()
                result = response.json()
            report['searches'][index:index + 1] = [result]
            save(args.output, report)
            print(workload, seed, algorithm, simulator, result['search_id'], flush=True)
            while result['status'] not in ('completed', 'failed', 'cancelled'):
                time.sleep(3)
                response = client.get('/api/searches/' + result['search_id'])
                response.raise_for_status()
                result = response.json()
                report['searches'][index] = result
                save(args.output, report)
            print(result['status'], result.get('error', ''), flush=True)
            if result['status'] != 'completed':
                report.update(status='failed', error=result.get('error', result['status']))
                save(args.output, report)
                raise SystemExit('A search failed; review saved evidence before resuming')
    report['summary'] = []
    for search in report['searches']:
        measured = [row for row in search['candidates'] if row['status'] == 'measured']
        feasible = [row for row in measured if row['objectives'] is not None]
        # Retrospective gate ablation preserves every original rejection.
        ungated = [{'genome_hash': row['genome_hash'], 'originally_feasible': row['objectives'] is not None,
                    'median_p95_ms': median(evaluation['metrics']['p95_ms'] for evaluation in row['evaluations'])}
                   for row in measured if len(row['evaluations']) == 3
                   and all(evaluation.get('metrics') for evaluation in row['evaluations'])]
        report['summary'].append({
            'search_id': search['search_id'], 'status': search['status'],
            'workload': search['request']['workload_profile'], 'seed': search['request']['seed'],
            'algorithm': search['request']['algorithm'], 'simulator': search['request']['use_simulator'],
            'attempts': search['attempts_used'], 'feasible_configurations': len(feasible),
            'best_feasible_p95_ms': min((row['objectives'][0] for row in feasible), default=None),
            'search_overhead_s': search['search_overhead_s'],
            'retrospective_no_gate_ranking': sorted(ungated, key=lambda row: row['median_p95_ms']),
        })
    groups = {}
    for row in report['summary']:
        groups.setdefault((row['workload'], row['algorithm'], row['simulator']), []).append(row)
    report['aggregates'] = []
    for (workload, algorithm, simulator), rows in sorted(groups.items()):
        best = [row['best_feasible_p95_ms'] for row in rows if row['best_feasible_p95_ms'] is not None]
        report['aggregates'].append({
            'workload': workload, 'algorithm': algorithm, 'simulator': simulator,
            'searches': len(rows), 'seeds': sorted({row['seed'] for row in rows}),
            'searches_with_feasible_candidate': sum(1 for row in rows if row['feasible_configurations']),
            'mean_feasible_configurations': round(mean(row['feasible_configurations'] for row in rows), 2),
            'median_best_feasible_p95_ms': round(median(best), 2) if best else None,
            'min_best_feasible_p95_ms': round(min(best), 2) if best else None,
        })
    report.update(status='completed', finished_at=datetime.now(timezone.utc).isoformat())
    save(args.output, report)


if __name__ == '__main__':
    main()
