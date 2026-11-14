"""Run bounded, equal-budget local searches and retain their full evidence."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from statistics import median
import time

import httpx


def save(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8000')
    parser.add_argument('--output', type=Path, default=Path('artifacts/validation/search-comparison.json'))
    parser.add_argument('--seed', type=int, default=72)
    parser.add_argument('--resume', action='store_true', help='Keep completed searches and retry the interrupted strategy')
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    report = {'started_at': datetime.now(timezone.utc).isoformat(), 'status': 'running',
              'scope': 'normal traffic; service outage, ambiguous payment retry, all five invariants',
              'searches': [], 'seed': args.seed}
    if args.resume:
        report = json.loads(args.output.read_bytes())
        if report['seed'] != args.seed:
            raise SystemExit('Resume with the original seed')
        if report['status'] == 'completed':
            raise SystemExit('This validation comparison is already complete')
        report['status'] = 'running'
        report.pop('error', None)
    elif args.output.exists():
        raise SystemExit('Choose a new output path to preserve the previous validation record')
    save(args.output, report)
    with httpx.Client(base_url=args.url, timeout=20, trust_env=False) as client:
        plan = [('nsga2', True), ('random', True), ('hill_climbing', True), ('nsga2', False)]
        for index, (algorithm, simulator) in enumerate(plan):
            body = {'algorithm': algorithm, 'use_simulator': simulator, 'seed': args.seed,
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
            print(algorithm, simulator, result['search_id'], flush=True)
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
            'algorithm': search['request']['algorithm'], 'simulator': search['request']['use_simulator'],
            'attempts': search['attempts_used'], 'feasible_configurations': len(feasible),
            'best_feasible_p95_ms': min((row['objectives'][0] for row in feasible), default=None),
            'search_overhead_s': search['search_overhead_s'],
            'retrospective_no_gate_ranking': sorted(ungated, key=lambda row: row['median_p95_ms']),
        })
    report.update(status='completed', finished_at=datetime.now(timezone.utc).isoformat())
    save(args.output, report)


if __name__ == '__main__':
    main()
