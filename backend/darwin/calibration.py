"""Fit one service-time scale from verified native benchmark samples."""
import argparse
import hashlib
import json
import math
from pathlib import Path
from statistics import mean
from tempfile import NamedTemporaryFile
from uuid import UUID

from darwin.contracts import Genome
from darwin.performance import WINDOW_S, latency, schedule
from darwin.simulator import MODEL_VERSION, simulate

REPORT_NAME = 'simulation-calibration.json'


def benchmark_rows(root, run_id):
    folder = root / str(run_id)
    comparison = json.loads((folder / 'comparison.json').read_bytes())
    request = comparison['request']
    if request['mode'] != 'native_benchmark' or comparison['experiment_id'] != str(run_id):
        raise ValueError(f'{run_id} is not a native benchmark comparison')
    profile = request['workload_profile']
    for candidate in comparison['candidates']:
        genome = Genome.model_validate(candidate['genome'])
        for evaluation in candidate['evaluations']:
            if evaluation['status'] != 'completed':
                continue
            ident = UUID(evaluation['evaluation_id'])
            raw = (folder / str(ident) / 'samples.json').read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            expected = next(item['sha256'] for item in evaluation['artifacts'] if item['name'] == 'samples.json')
            if digest != expected:
                raise ValueError(f'Sample digest mismatch for {ident}')
            samples = json.loads(raw)
            seed = evaluation['seed']
            plan = schedule(profile, seed)
            observed_plan = [{key: sample[key] for key in plan[0]} for sample in samples]
            if observed_plan != plan:
                raise ValueError(f'Sample schedule mismatch for {ident}')
            measured_p95 = latency(samples, .95)
            if not math.isfinite(measured_p95) or measured_p95 <= 0:
                raise ValueError(f'Invalid measured p95 for {ident}')
            yield {
                'experiment_id': str(run_id), 'evaluation_id': str(ident), 'samples_sha256': digest,
                'source_hash': comparison['source_hash'], 'genome': genome.model_dump(),
                'workload_profile': profile, 'seed': seed, 'measured_p95_ms': measured_p95,
                'measured_error_rate': sum(not row['ok'] for row in samples) / len(samples),
            }


def cohort(row):
    return row['workload_profile'], Genome.model_validate(row['genome'])


def prediction(row, scale):
    profile, genome = cohort(row)
    return simulate(genome, profile, row['seed'], WINDOW_S, service_scale=scale)['metrics']['p95_ms']


def calibrate(root, fit_runs, holdout_runs, holdout_seed):
    if set(fit_runs) & set(holdout_runs):
        raise ValueError('Run-level holdouts cannot also be fit runs')
    fit, heldout = [], []
    for run_id in dict.fromkeys(fit_runs):
        for row in benchmark_rows(root, run_id):
            if row['seed'] == holdout_seed:
                heldout.append(row)
            elif row['measured_error_rate'] == 0:
                fit.append(row)
    for run_id in dict.fromkeys(holdout_runs):
        heldout.extend(benchmark_rows(root, run_id))
    if not fit or not heldout:
        raise ValueError('Calibration requires successful fit runs and separate held-out repetitions')

    def loss(scale):
        return mean(abs(math.log(prediction(row, scale) / row['measured_p95_ms'])) for row in fit)

    scale = min((step / 20 for step in range(5, 161)), key=loss)
    fit_cohorts = [cohort(row) for row in fit]
    for row in heldout:
        row['seen_workload_and_genome'] = cohort(row) in fit_cohorts
        row['predicted_p95_ms'] = prediction(row, scale)
        row['unscaled_p95_ms'] = prediction(row, 1)
        row['signed_error_ms'] = row['predicted_p95_ms'] - row['measured_p95_ms']
        row['absolute_percentage_error'] = 100 * abs(row['signed_error_ms']) / row['measured_p95_ms']
    return {
        'model_version': MODEL_VERSION, 'duration_s': WINDOW_S, 'service_scale': scale,
        'holdout_seed': holdout_seed, 'fit': fit, 'heldout': heldout,
        'fit_mean_absolute_log_error': loss(scale),
        'heldout_mae_ms': mean(abs(row['signed_error_ms']) for row in heldout),
        'heldout_mape_percent': mean(row['absolute_percentage_error'] for row in heldout),
        'heldout_unscaled_mape_percent': mean(
            100 * abs(row['unscaled_p95_ms'] - row['measured_p95_ms']) / row['measured_p95_ms']
            for row in heldout),
    }


def calibrated_simulation(root, genome, profile, seed, duration_s, database_delay_ms):
    report_path = root / REPORT_NAME
    report = json.loads(report_path.read_bytes()) if report_path.is_file() else {}
    compatible = (report.get('model_version') == MODEL_VERSION
                  and duration_s == report.get('duration_s') and database_delay_ms == 0
                  and any(cohort(row) == (profile, genome) for row in report.get('fit', [])))
    scale = report['service_scale'] if compatible else 1.0
    result = simulate(genome, profile, seed, duration_s, database_delay_ms, service_scale=scale)
    if compatible:
        comparisons = [row for row in report['heldout'] if cohort(row) == (profile, genome)]
        result['calibration_status'] = 'fitted_limited_evidence'
        result['heldout_evidence'] = {
            'repetitions': len(comparisons),
            'absolute_percentage_errors': [row['absolute_percentage_error'] for row in comparisons],
        }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('fit_runs', type=UUID, nargs='+')
    parser.add_argument('--holdout-run', action='append', type=UUID, default=[])
    parser.add_argument('--holdout-seed', type=int, default=44)
    parser.add_argument('--root', type=Path, default=Path('artifacts/experiments'))
    args = parser.parse_args()
    report = calibrate(args.root, args.fit_runs, args.holdout_run, args.holdout_seed)
    output = args.root / REPORT_NAME
    with NamedTemporaryFile(mode='w', encoding='utf-8', dir=args.root, delete=False) as handle:
        temporary = Path(handle.name)
    try:
        temporary.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n', encoding='utf-8')
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    print(f'{output}: {len(report["fit"])} fit, {len(report["heldout"])} held out; '
          f'p95 MAE {report["heldout_mae_ms"]:.1f} ms, MAPE {report["heldout_mape_percent"]:.1f}%')


if __name__ == '__main__':
    main()
