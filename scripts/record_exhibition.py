"""Export a compact, view-only evidence bundle for exhibition fallback.

The bundle contains two completed searches: one with measured feasible
tradeoffs and one that was explicitly rejected. It is copied into the
dashboard's public directory so the UI can still show recorded evidence when
the live API or its history is unavailable. It is never presented as a live
run and never replaces the measured engine.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from darwin.exhibition import _feasible, _measured
from darwin.search import Store

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_KEYS = ('genome', 'genome_hash', 'parent_ids', 'generation', 'status', 'objectives',
                  'penalty', 'simulation', 'summary', 'experiment_id', 'candidate_id')


def compact_evaluation(evaluation):
    return {
        'evaluation_id': evaluation.get('evaluation_id'),
        'repetition': evaluation.get('repetition'),
        'status': evaluation.get('status'),
        'gate': evaluation.get('gate'),
        'gate_reasons': evaluation.get('gate_reasons', []),
        'violations': evaluation.get('violations', []),
        'metrics': evaluation.get('metrics'),
        'recovery': [{'scenario': row.get('scenario'), 'recovery_s': row.get('recovery_s'),
                      'fault_observed': row.get('fault_observed'),
                      'schedule_valid': row.get('schedule_valid')}
                     for row in evaluation.get('recovery', [])],
    }


def compact_simulation(simulation):
    if not simulation:
        return None
    return {'calibration_status': simulation.get('calibration_status'),
            'metrics': {'p95_ms': simulation.get('metrics', {}).get('p95_ms')}}


def compact_search(record):
    return {
        'experiment_id': record['experiment_id'],
        'search_id': record['search_id'],
        'created_at': record.get('created_at'),
        'started_at': record.get('started_at'),
        'finished_at': record.get('finished_at'),
        'status': record.get('status'),
        'request': record.get('request'),
        'candidates': [{
            **{key: candidate[key] for key in CANDIDATE_KEYS if key in candidate},
            'simulation': compact_simulation(candidate.get('simulation')),
            'evaluations': [compact_evaluation(evaluation)
                            for evaluation in candidate.get('evaluations', [])],
        } for candidate in record.get('candidates', [])],
        'experiment_ids': record.get('experiment_ids', []),
        'attempts_used': record.get('attempts_used'),
        'pareto_ids': record.get('pareto_ids', []),
        'generation': record.get('generation'),
        'search_overhead_s': record.get('search_overhead_s'),
        'recorded': True,
    }


def select(records):
    completed = [record for record in records if record.get('status') == 'completed']
    feasible = [record for record in completed if len(_feasible(record)) >= 2]
    feasible.sort(key=lambda record: (len(_feasible(record)), record.get('finished_at') or ''), reverse=True)
    rejected = [record for record in completed if not _feasible(record) and _measured(record)]
    rejected.sort(key=lambda record: record.get('finished_at') or '', reverse=True)
    return (feasible[0] if feasible else None), (rejected[0] if rejected else None)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--experiments', type=Path, default=ROOT / 'artifacts' / 'experiments')
    parser.add_argument('--output', type=Path, default=ROOT / 'frontend' / 'public' / 'recorded-example.json')
    args = parser.parse_args()
    store = Store(args.experiments / 'searches')
    feasible, rejected = select(store.all())
    if feasible is None:
        raise SystemExit('No completed search with at least two feasible candidates was found')
    searches = [compact_search(record) for record in (feasible, rejected) if record]
    bundle = {
        'schema_version': 1,
        'label': 'Recorded run',
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'note': ('Saved from completed DARWIN searches for offline review. These are recorded '
                 'measurements, not a live execution. Re-run the search to produce new evidence.'),
        'searches': searches,
        'default': feasible['search_id'],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(bundle, indent=2, default=str), encoding='utf-8')
    print(f'Wrote {args.output} ({args.output.stat().st_size / 1024:.0f} KiB)')
    for record in searches:
        print(f'  {record["search_id"]} · {len(_feasible(record))} feasible · '
              f'{len(record["candidates"])} candidates · {record["request"]["algorithm"]}')


if __name__ == '__main__':
    main()
