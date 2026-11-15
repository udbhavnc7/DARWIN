"""The Sanchay adapter must use the real source and the real Reports call site."""
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from darwin.adapters.base import AdapterCancelled, EvaluationBudget
from darwin.adapters.sanchay_reporting import (
    SanchayReportingAdapter, _patch_reporting, _patch_reports_tab, _rewrite_module_specifiers,
    _test_counts,
)
from darwin.repository_catalog import SANCHAY_ADAPTER_ID, SANCHAY_COMMIT

LOCAL_SANCHAY = Path(os.environ.get(
    'DARWIN_SANCHAY_SOURCE', r'C:\Users\LENOVO\Downloads\Sanchay\Sanchay'))


def node_ready() -> bool:
    binary = shutil.which('node')
    if not binary:
        return False
    try:
        completed = subprocess.run([binary, '--version'], capture_output=True, text=True, timeout=5,
                                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), check=False)
    except (OSError, subprocess.SubprocessError):
        return False
    version = completed.stdout.strip().lstrip('v')
    try:
        major, minor = (int(part) for part in version.split('.')[:2])
    except ValueError:
        return False
    return (major, minor) >= (22, 18)


def test_module_specifiers_are_rewritten_for_native_node_typescript():
    text = "import { addMoney } from './money';\nimport type { Transaction } from '../types/finance';"
    rewritten = _rewrite_module_specifiers(text)
    assert "from './money.ts'" in rewritten
    assert "from '../types/finance.ts'" in rewritten


def test_vitest_totals_are_parsed_from_the_output_tail():
    output = '\n Test Files  1 passed (1)\n      Tests  29 passed (29)\n   Duration  559ms\n'
    assert _test_counts(output) == {
        'tests_passed': 29, 'tests_failed': 0, 'tests_skipped': 0, 'tests_total': 29,
    }
    failed = '\n      Tests  2 failed | 27 passed (29)\n'
    assert _test_counts(failed)['tests_failed'] == 2
    assert _test_counts(failed)['tests_passed'] == 27
    assert _test_counts('no summary') == {}


REPORTS_TAB_SHAPE = '''import {
  DEFAULT_CURRENCY,
  buildStatementCsv,
  computeCategoryBreakdown,
  computePayeeBreakdown,
  computeReportTotals,
  reportCurrencies,
  reportsAccountMap,
  scopeToCurrency,
  transactionCurrency,
} from '../utils/reporting';

export function ReportsTab() {
  const totals = useMemo(
    () => computeReportTotals(inCurrency, activeCurrency),
    [inCurrency, activeCurrency]
  );

  const categories = useMemo(
    () =>
      computeCategoryBreakdown(inCurrency, activeCurrency)
        .slice(0, 6)
        .map((row, index) => ({ ...row, color: CHART_COLORS[index % CHART_COLORS.length] })),
    [inCurrency, activeCurrency]
  );

  const payees = useMemo(
    () => computePayeeBreakdown(inCurrency, activeCurrency),
    [inCurrency, activeCurrency]
  );
}
'''


def test_candidate_replaces_the_audited_reports_tab_call_site():
    patched = _patch_reports_tab(REPORTS_TAB_SHAPE)
    assert 'computeReportBundle(inCurrency, activeCurrency)' in patched
    assert 'computeReportTotals(inCurrency' not in patched
    assert 'computeCategoryBreakdown(inCurrency' not in patched
    assert 'computePayeeBreakdown(inCurrency' not in patched


def test_changed_call_site_is_not_guessed_at():
    with pytest.raises(Exception) as caught:
        _patch_reports_tab('export function ReportsTab() { return null; }')
    assert getattr(caught.value, 'verdict', None) == 'NO_FEASIBLE_CANDIDATE'


def test_reporting_module_re_exports_candidate():
    patched = _patch_reporting('export const x = 1;')
    assert "export { computeReportBundle } from './reportBundle';" in patched


@pytest.mark.skipif(not LOCAL_SANCHAY.is_dir(),
                    reason='The local pinned Sanchay checkout is not available.')
def test_real_pinned_sanchay_detection():
    adapter = SanchayReportingAdapter()
    support = adapter.detect(LOCAL_SANCHAY, SANCHAY_COMMIT, True)
    assert support.supported is True
    assert support.adapter_id == SANCHAY_ADAPTER_ID
    changed = adapter.detect(LOCAL_SANCHAY, 'a' * 40, False)
    assert changed.supported is False
    assert 'not the audited pinned revision' in changed.reason


@pytest.mark.skipif(not LOCAL_SANCHAY.is_dir() or not node_ready(),
                    reason='The local Sanchay checkout or Node 22.18+ is not available.')
def test_real_quick_sanchay_comparison(tmp_path):
    adapter = SanchayReportingAdapter()
    budget = EvaluationBudget(
        mode='test', seeds=(7,), sizes=(500, 2_000), repetitions=3, warmups=1,
        wall_clock_s=60, include_source_tests=False,
    )
    prepared = adapter.prepare(LOCAL_SANCHAY, tmp_path / 'evaluation', budget)
    candidate = adapter.candidates(prepared)[0]
    measurements = adapter.measure(prepared, candidate, budget, lambda: False)
    evidence = adapter.verify(prepared, candidate, measurements)
    assert evidence['parity']['passed'] is True
    assert evidence['parity']['checks_total'] >= 20
    assert evidence['summaries']
    assert evidence['verdict']['status'] in {'VERIFIED_IMPROVEMENT', 'BASELINE_RETAINED', 'INCONCLUSIVE'}
    assert 'computeReportBundle' in prepared.candidate_diff.read_text(encoding='utf-8')
    assert 'ReportsTab.tsx' in prepared.candidate_diff.read_text(encoding='utf-8')
