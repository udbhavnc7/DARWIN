"""Correctness and evidence gates must override raw speed."""
from darwin.verdict_policy import decide


def summary(size=50_000, baseline=None, candidate=None):
    baseline = baseline or [8_000_000, 8_100_000, 8_200_000, 8_300_000]
    candidate = candidate or [3_500_000, 3_600_000, 3_700_000, 3_800_000]
    return {
        'fixture_id': f'seed7-size{size}',
        'seed': 7,
        'size': size,
        'baseline_samples_ns': baseline,
        'candidate_samples_ns': candidate,
    }


def passed_check(name='outputs match'):
    return {'name': name, 'passed': True, 'detail': ''}


def test_verified_improvement_requires_all_gates():
    verdict = decide(parity_passed=True, checks=[passed_check()], summaries=[summary()])
    assert verdict['status'] == 'VERIFIED_IMPROVEMENT'
    assert verdict['correctness']['checks_passed'] == 1
    assert verdict['change_pct'] > 50
    assert verdict['correctness']['passed'] is True


def test_faster_incorrect_candidate_is_rejected():
    verdict = decide(
        parity_passed=False,
        checks=[{'name': 'totals match', 'passed': False, 'detail': 'spending differs'}],
        summaries=[summary(candidate=[1, 2, 3, 4])],
    )
    assert verdict['status'] == 'REJECTED_INCORRECT'
    assert 'faster' in verdict['reason']
    assert verdict['correctness']['passed'] is False


def test_any_measured_regression_retains_baseline():
    verdict = decide(
        parity_passed=True,
        checks=[passed_check()],
        summaries=[
            summary(size=10_000, baseline=[1_000_000] * 4, candidate=[900_000] * 4),
            summary(size=50_000, baseline=[8_000_000] * 4, candidate=[8_500_000] * 4),
        ],
    )
    assert verdict['status'] == 'BASELINE_RETAINED'
    assert '10,000' in verdict['reason'] or '50000' in verdict['reason'] or '50,000' in verdict['reason']


def test_slower_primary_size_retains_baseline():
    verdict = decide(parity_passed=True, checks=[passed_check()],
                     summaries=[summary(candidate=[9_000_000] * 4)])
    assert verdict['status'] == 'BASELINE_RETAINED'


def test_below_product_threshold_is_inconclusive():
    verdict = decide(parity_passed=True, checks=[passed_check()],
                     summaries=[summary(baseline=[8_000_000] * 4, candidate=[7_800_000] * 4)])
    assert verdict['status'] == 'INCONCLUSIVE'
    assert 'below the 5%' in verdict['reason']


def test_low_paired_win_rate_is_inconclusive():
    verdict = decide(
        parity_passed=True, checks=[passed_check()],
        summaries=[summary(baseline=[8_000_000, 8_100_000, 8_200_000, 8_300_000],
                           candidate=[3_000_000, 8_500_000, 8_600_000, 8_700_000])],
    )
    assert verdict['status'] == 'INCONCLUSIVE'
    assert 'paired' in verdict['reason']


def test_no_samples_is_not_measured():
    verdict = decide(parity_passed=True, checks=[passed_check()], summaries=[])
    assert verdict['status'] == 'NOT_MEASURED'
    assert verdict['per_size'] == []


def test_no_candidate_is_explicit():
    verdict = decide(parity_passed=True, checks=[], summaries=[], candidate_count=0)
    assert verdict['status'] == 'NO_FEASIBLE_CANDIDATE'


def test_infrastructure_failure_has_no_metrics():
    verdict = decide(parity_passed=True, checks=[], summaries=[summary()],
                     infrastructure_ok=False, infrastructure_error='Node exited')
    assert verdict['status'] == 'FAILED_INFRASTRUCTURE'
    assert verdict['per_size'] == []
    assert verdict['reason'] == 'Node exited'
