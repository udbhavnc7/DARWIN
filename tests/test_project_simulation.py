"""The screening model is deterministic, bounded and never a measured winner."""
import json
from pathlib import Path

import pytest

from darwin.project_capabilities import inspect_source
from darwin.project_simulation import (
    POLICY, empty_screening_verdict, screen_repository,
)


def write(root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def analysed_express(tmp_path: Path) -> dict:
    write(tmp_path, 'package.json', json.dumps({
        'name': 'screening-api',
        'dependencies': {'express': '^5.0.0', 'pg': '^8.0.0'},
    }))
    write(tmp_path, 'server.js', '''
import express from 'express';
const app = express();
app.get('/api/health', (req, res) => res.json({ok: true}));
app.get('/api/items', (req, res) => res.json([]));
app.post('/api/items', (req, res) => {
  fetch('https://api.stripe.com/v1/charges').then(() => res.json({}));
});
''')
    return inspect_source(tmp_path, 'https://github.com/example/screening-api', 'example',
                          'screening-api', 'f' * 40, False)


def test_screening_is_deterministic_and_never_measured(tmp_path):
    analysis = analysed_express(tmp_path)

    first = screen_repository(analysis, 'quick')
    second = screen_repository(analysis, 'quick')

    assert first == second
    assert first['adapter_id'] == 'architecture-screening-v1'
    assert first['label'] == 'SIMULATED'
    assert first['evidence_kind'] == 'simulated'
    assert first['not_measured'] is True
    assert first['verdict']['status'] == 'NOT_MEASURED'
    assert first['verdict']['policy']['label'] == 'SIMULATED'
    assert first['verdict']['policy']['not_measured'] is True
    assert first['verdict']['correctness']['checks_total'] == 0
    assert 'No repository code was executed' in first['verdict']['correctness']['note']
    recommendation = first['recommendation']
    assert recommendation['measured'] is False
    assert recommendation['evidence_kind'] == 'simulated'
    assert recommendation['status'] in {
        'IMPROVEMENT_CANDIDATE', 'BASELINE_RETAINED', 'INCONCLUSIVE',
    }
    if recommendation['status'] == 'IMPROVEMENT_CANDIDATE':
        assert 'SIMULATED' in recommendation['summary']
        assert 'models p95 latency' in recommendation['summary']


def test_every_qualifying_variant_obeys_the_published_policy(tmp_path):
    screening = screen_repository(analysed_express(tmp_path), 'full')

    for variant in screening['variants']:
        if variant['label'] == 'Detected baseline':
            continue
        if not variant['qualifies']:
            continue
        assert variant['change_pct'] >= POLICY['minimum_improvement_pct']
        assert variant['metrics']['error_rate_pct'] <= POLICY['maximum_error_rate_pct']
        assert variant['error_delta_pct'] <= POLICY['maximum_error_delta_pct']
        assert variant['cost_multiplier'] <= POLICY['maximum_cost_multiplier']


def test_screening_only_varies_controls_supported_by_source_evidence(tmp_path):
    screening = screen_repository(analysed_express(tmp_path), 'quick')
    supported = set(screening['controls'])
    changed = {
        change['control']
        for variant in screening['variants']
        for change in variant['changes']
    }

    assert supported <= {
        'replicas', 'cache_ttl_s', 'offload_jobs', 'retry_policy',
        'db_pool', 'read_replicas', 'rate_limit',
    }
    assert changed <= supported
    assert 'replicas' in supported


def test_full_mode_reports_all_seeds_and_sensitivity(tmp_path):
    screening = screen_repository(analysed_express(tmp_path), 'full')
    recommendation = screening['recommendation']

    assert screening['seeds'] == [7, 21, 2026]
    assert recommendation['seed_sensitivity']['seeds'] == [7, 21, 2026]
    assert recommendation['seed_sensitivity']['min_change_pct'] <= \
        recommendation['seed_sensitivity']['max_change_pct']


def test_unavailable_screening_is_rejected():
    with pytest.raises(ValueError, match='not available'):
        screen_repository({'screening': {'available': False},
                           'project': {'backend': {}}})


def test_cancelled_or_failed_screening_has_no_winner():
    verdict = empty_screening_verdict('The screening was cancelled.')

    assert verdict['status'] == 'NOT_MEASURED'
    assert verdict['label'] == 'Screening did not complete'
    assert verdict['correctness']['passed'] is False
    recommendation = verdict['recommendation']
    assert recommendation['status'] == 'INCONCLUSIVE'
    assert recommendation['measured'] is False
    assert recommendation['changes'] == []
    assert 'cancelled' in recommendation['summary']
