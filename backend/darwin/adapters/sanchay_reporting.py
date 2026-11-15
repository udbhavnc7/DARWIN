"""Sanchay financial-report evaluation adapter (v1).

The baseline imports the pinned Sanchay reporting module. The candidate lives in
a temporary source overlay and is wired into the real Reports tab call site.
Fixtures are deterministic, fictional ledgers generated from a seed; no user
finance data is read or written.

Timed scope: the three report aggregations used by ReportsTab. Currency
filtering, React state and DOM rendering are outside the timed region.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import difflib
import hashlib
import json
import os
from pathlib import Path
import random
import re
import shutil
import subprocess
import sys
import time

from darwin.adapters.base import (
    AdapterCancelled, AdapterError, Candidate, EvaluationBudget,
    PreparedEvaluation, SupportAssessment,
)
from darwin.repository_catalog import SANCHAY_ADAPTER_ID, SANCHAY_ADAPTER_VERSION
from darwin.verdict_policy import decide

HARNESS_DIR = Path(__file__).parent / 'sanchay_harness'
MIN_NODE = (22, 18)

CURRENCIES = ('INR', 'USD', 'EUR', 'GBP', 'JPY')
CATEGORIES = ('Groceries', 'Dining', 'Transport', 'Shopping', 'Bills',
              'Entertainment', 'Health', 'Rent')
PAYEES = ('Corner Store', 'Cafe Mocha', 'Metro Card', 'Book House', 'Power Co',
          'Cinema 9', 'City Clinic', 'Landlord', 'Pharmacy', 'Cloud Music',
          'Taxi Co', 'Hardware Mart')
ACCOUNTS = (
    {'id': 'acc_inr', 'name': 'HDFC Savings', 'type': 'Bank', 'currency': 'INR',
     'balance': 250000, 'openingBalance': 100000, 'status': 'Active', 'change': 0},
    {'id': 'acc_usd', 'name': 'USD Checking', 'type': 'Bank', 'currency': 'USD',
     'balance': 5000, 'openingBalance': 1000, 'status': 'Active', 'change': 0},
    {'id': 'acc_eur', 'name': 'Revolut EUR', 'type': 'Bank', 'currency': 'EUR',
     'balance': 4000, 'openingBalance': 1000, 'status': 'Active', 'change': 0},
    {'id': 'acc_gbp', 'name': 'GBP Wallet', 'type': 'Bank', 'currency': 'GBP',
     'balance': 3000, 'openingBalance': 1000, 'status': 'Active', 'change': 0},
    {'id': 'acc_jpy', 'name': 'JPY Cash', 'type': 'Cash', 'currency': 'JPY',
     'balance': 500000, 'openingBalance': 100000, 'status': 'Active', 'change': 0},
)
ACCOUNT_BY_CURRENCY = {account['currency']: account for account in ACCOUNTS}


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def _amount(rng: random.Random, currency: str) -> float:
    if currency == 'JPY':
        return float(rng.randint(50, 20_000))
    return round(rng.randint(100, 500_000) / 100, 2)


def _iso(index: int) -> str:
    moment = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=index % 330, seconds=(index * 37) % 86400)
    return moment.isoformat().replace('+00:00', 'Z')


def _transaction_currency(tx: dict, accounts_by_id: dict[str, dict]) -> str:
    if tx.get('currency'):
        return tx['currency']
    account = accounts_by_id.get(tx.get('accountId', ''))
    return (account or {}).get('currency', 'INR')


def _base_transaction(index: int, currency: str, kind: str, tx_type: str,
                      status: str, amount: float, category: str, counterparty: str | None,
                      *, goal_id: str | None = None, refund_of: str | None = None) -> dict:
    account = ACCOUNT_BY_CURRENCY[currency]
    tx = {
        'id': f'tx_{index:08d}',
        'title': f'{counterparty or category} {index}',
        'category': category,
        'amount': amount,
        'type': tx_type,
        'status': status,
        'date': _iso(index),
        'accountId': account['id'],
        'kind': kind,
        'counterparty': counterparty,
        'reference': f'REF-{index % 997:04d}',
        'note': 'Synthetic DARWIN fixture',
        'tags': ['synthetic', kind],
    }
    if currency != account['currency']:
        tx['currency'] = currency
    if goal_id:
        tx['goalId'] = goal_id
    if refund_of:
        tx['refundOfId'] = refund_of
    return tx


def _generate_ledger(seed: int, size: int, currency: str) -> dict:
    """Exactly `size` primary-currency rows plus non-counted other-currency noise."""
    rng = random.Random(f'sanchay-reporting-v1:{seed}:{size}:{currency}')
    transactions: list[dict] = []
    completed_debits: list[dict] = []
    index = 0
    while len(transactions) < size:
        roll = rng.random()
        category = rng.choice(CATEGORIES)
        payee = rng.choice(PAYEES)
        status = ('Completed' if rng.random() < 0.86 else
                  rng.choice(('Pending', 'Failed', 'Flagged')))

        if roll < 0.12:
            amount = _amount(rng, currency)
            tx = _base_transaction(index, currency, 'income', 'credit', status, amount,
                                   'Income', rng.choice(('Employer', 'Client Payment', 'Refund Desk')))
            tx['category'] = 'Income'
        elif roll < 0.20 and completed_debits:
            original = rng.choice(completed_debits)
            amount = round(min(original['amount'] * rng.uniform(0.1, 0.8), original['amount']), 0 if currency == 'JPY' else 2)
            amount = float(max(1, int(amount) if currency == 'JPY' else amount))
            tx = _base_transaction(index, currency, 'refund', 'credit', status, amount,
                                   original['category'], original.get('counterparty'),
                                   refund_of=original['id'])
        elif roll < 0.28:
            goal = rng.random() < 0.45
            tx = _base_transaction(index, currency, 'transfer', 'debit', 'Completed',
                                   _amount(rng, currency), 'Savings', 'Self',
                                   goal_id='goal_1' if goal else None)
            if rng.random() < 0.35:
                pair = dict(tx)
                pair['id'] = f'tx_{index:08d}_in'
                pair['type'] = 'credit'
                pair['title'] = f'Transfer in {index}'
                pair['goalId'] = None
                pair['kind'] = 'transfer'
                transactions.append(pair)
                index += 1
                if len(transactions) >= size:
                    break
        elif roll < 0.38:
            tx = _base_transaction(index, currency, 'expense', 'debit', status,
                                   _amount(rng, currency), category, payee)
        else:
            tx = _base_transaction(index, currency, 'expense', 'debit', status,
                                   _amount(rng, currency), category, payee)
        transactions.append(tx)
        if tx['status'] == 'Completed' and tx['type'] == 'debit' and tx['kind'] == 'expense':
            completed_debits.append(tx)
        index += 1

    transactions = transactions[:size]
    # Add non-counted other-currency noise; the real report path scopes it out.
    noise: list[dict] = []
    others = [item for item in CURRENCIES if item != currency]
    for offset in range(max(8, size // 12)):
        other = others[offset % len(others)]
        noise.append(_base_transaction(900_000 + offset, other, 'expense', 'debit',
                                       'Completed', _amount(rng, other),
                                       rng.choice(CATEGORIES), rng.choice(PAYEES)))
    ledger = transactions + noise
    accounts_by_id = {account['id']: account for account in ACCOUNTS}
    scoped = [tx for tx in ledger if _transaction_currency(tx, accounts_by_id) == currency]
    if len(scoped) != size:
        raise AdapterError(f'Fixture generator produced {len(scoped)} scoped rows instead of {size}',
                           'fixture_generation_failed')
    return {'transactions': scoped, 'raw_rows': len(ledger), 'noise_rows': len(noise)}


def _expected(totals, categories, payees):
    return {'totals': totals, 'categories': categories, 'payees': payees}


def _edge_fixtures() -> list[dict]:
    store = _base_transaction(1, 'INR', 'expense', 'debit', 'Completed', 100, 'Groceries', 'Corner Store')
    return [
        {
            'id': 'edge-empty', 'seed': 0, 'size': 0, 'currency': 'INR', 'timed': False,
            'transactions': [],
            'expected': _expected({'income': 0, 'spending': 0, 'saved': 0, 'net': 0}, [], []),
        },
        {
            'id': 'edge-single-expense', 'seed': 0, 'size': 1, 'currency': 'INR', 'timed': False,
            'transactions': [store],
            'expected': _expected(
                {'income': 0, 'spending': 100, 'saved': 0, 'net': -100},
                [{'category': 'Groceries', 'amount': 100, 'pct': 100}],
                [{'name': 'Corner Store', 'amount': 100, 'count': 1}],
            ),
        },
        {
            'id': 'edge-refund', 'seed': 0, 'size': 2, 'currency': 'INR', 'timed': False,
            'transactions': [
                _base_transaction(10, 'INR', 'expense', 'debit', 'Completed', 900, 'Groceries', 'City Clinic'),
                _base_transaction(11, 'INR', 'refund', 'credit', 'Completed', 300, 'Groceries', 'City Clinic',
                                  refund_of='tx_00000010'),
            ],
            'expected': _expected(
                {'income': 0, 'spending': 600, 'saved': 0, 'net': -600},
                [{'category': 'Groceries', 'amount': 600, 'pct': 100}],
                [{'name': 'City Clinic', 'amount': 600, 'count': 1}],
            ),
        },
        {
            'id': 'edge-transfers-and-goal', 'seed': 0, 'size': 4, 'currency': 'INR', 'timed': False,
            'transactions': [
                _base_transaction(20, 'INR', 'income', 'credit', 'Completed', 2000, 'Income', 'Employer'),
                _base_transaction(21, 'INR', 'expense', 'debit', 'Completed', 500, 'Groceries', 'Corner Store'),
                _base_transaction(22, 'INR', 'transfer', 'debit', 'Completed', 100, 'Savings', 'Self', goal_id='goal_1'),
                _base_transaction(23, 'INR', 'transfer', 'debit', 'Completed', 400, 'Savings', 'Self'),
            ],
            'expected': _expected(
                {'income': 2000, 'spending': 500, 'saved': 100, 'net': 1400},
                [{'category': 'Groceries', 'amount': 500, 'pct': 100}],
                [{'name': 'Corner Store', 'amount': 500, 'count': 1}],
            ),
        },
        {
            'id': 'edge-pending-failed', 'seed': 0, 'size': 3, 'currency': 'INR', 'timed': False,
            'transactions': [
                _base_transaction(30, 'INR', 'expense', 'debit', 'Pending', 400, 'Dining', 'Cafe Mocha'),
                _base_transaction(31, 'INR', 'expense', 'debit', 'Failed', 700, 'Shopping', 'Book House'),
                _base_transaction(32, 'INR', 'expense', 'debit', 'Completed', 100, 'Groceries', 'Corner Store'),
            ],
            'expected': _expected(
                {'income': 0, 'spending': 100, 'saved': 0, 'net': -100},
                [{'category': 'Groceries', 'amount': 100, 'pct': 100}],
                [{'name': 'Corner Store', 'amount': 100, 'count': 1}],
            ),
        },
        {
            'id': 'edge-jpy-precision', 'seed': 0, 'size': 2, 'currency': 'JPY', 'timed': False,
            'transactions': [
                _base_transaction(40, 'JPY', 'expense', 'debit', 'Completed', 1000, 'Dining', 'Cafe Mocha'),
                _base_transaction(41, 'JPY', 'expense', 'debit', 'Completed', 250, 'Dining', 'Cafe Mocha'),
            ],
            'expected': _expected(
                {'income': 0, 'spending': 1250, 'saved': 0, 'net': -1250},
                [{'category': 'Dining', 'amount': 1250, 'pct': 100}],
                [{'name': 'Cafe Mocha', 'amount': 1250, 'count': 2}],
            ),
        },
        {
            'id': 'edge-multicurrency-scope', 'seed': 0, 'size': 3, 'currency': 'INR', 'timed': False,
            'scope': True, 'scoped_rows': 2,
            'transactions': [
                _base_transaction(50, 'INR', 'expense', 'debit', 'Completed', 500, 'Groceries', 'Corner Store'),
                _base_transaction(51, 'USD', 'expense', 'debit', 'Completed', 999, 'Shopping', 'Book House'),
                _base_transaction(52, 'INR', 'income', 'credit', 'Completed', 250, 'Income', 'Employer'),
            ],
            'expected': _expected(
                {'income': 250, 'spending': 500, 'saved': 0, 'net': -250},
                [{'category': 'Groceries', 'amount': 500, 'pct': 100}],
                [{'name': 'Corner Store', 'amount': 500, 'count': 1}],
            ),
            'scoping_note': 'Rows were pre-scoped to INR exactly as ReportsTab does before aggregation.',
        },
    ]


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding='utf-8')


def _copy_text(source: Path, target: Path, transform=None) -> str:
    text = source.read_text(encoding='utf-8')
    if transform:
        text = transform(text)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding='utf-8')
    return text


def _rewrite_module_specifiers(text: str) -> str:
    replacements = (
        ("from '../types/finance'", "from '../types/finance.ts'"),
        ("from './money'", "from './money.ts'"),
        ("from './categories'", "from './categories.ts'"),
        ("from './reportBundle'", "from './reportBundle.ts'"),
    )
    for old, new in replacements:
        text = text.replace(old, new)
    return text


def _patch_reporting(text: str) -> str:
    addition = (
        "\n\n// Real Project Mode candidate: shared single-pass report aggregation.\n"
        "export { computeReportBundle } from './reportBundle';\n"
        "export type { ReportBundle } from './reportBundle';\n"
    )
    return text.rstrip() + addition


def _patch_reports_tab(text: str) -> str:
    import_old = (
        "import {\n"
        "  DEFAULT_CURRENCY,\n"
        "  buildStatementCsv,\n"
        "  computeCategoryBreakdown,\n"
        "  computePayeeBreakdown,\n"
        "  computeReportTotals,\n"
        "  reportCurrencies,\n"
        "  reportsAccountMap,\n"
        "  scopeToCurrency,\n"
        "  transactionCurrency,\n"
        "} from '../utils/reporting';"
    )
    import_new = (
        "import {\n"
        "  DEFAULT_CURRENCY,\n"
        "  buildStatementCsv,\n"
        "  computeReportBundle,\n"
        "  reportCurrencies,\n"
        "  reportsAccountMap,\n"
        "  scopeToCurrency,\n"
        "  transactionCurrency,\n"
        "} from '../utils/reporting';"
    )
    totals_old = (
        "  const totals = useMemo(\n"
        "    () => computeReportTotals(inCurrency, activeCurrency),\n"
        "    [inCurrency, activeCurrency]\n"
        "  );"
    )
    totals_new = (
        "  const reportBundle = useMemo(\n"
        "    () => computeReportBundle(inCurrency, activeCurrency),\n"
        "    [inCurrency, activeCurrency]\n"
        "  );\n"
        "\n"
        "  const totals = reportBundle.totals;"
    )
    categories_old = (
        "  const categories = useMemo(\n"
        "    () =>\n"
        "      computeCategoryBreakdown(inCurrency, activeCurrency)\n"
        "        .slice(0, 6)\n"
        "        .map((row, index) => ({ ...row, color: CHART_COLORS[index % CHART_COLORS.length] })),\n"
        "    [inCurrency, activeCurrency]\n"
        "  );"
    )
    categories_new = (
        "  const categories = useMemo(\n"
        "    () =>\n"
        "      reportBundle.categories\n"
        "        .slice(0, 6)\n"
        "        .map((row, index) => ({ ...row, color: CHART_COLORS[index % CHART_COLORS.length] })),\n"
        "    [reportBundle]\n"
        "  );"
    )
    payees_old = (
        "  const payees = useMemo(\n"
        "    () => computePayeeBreakdown(inCurrency, activeCurrency),\n"
        "    [inCurrency, activeCurrency]\n"
        "  );"
    )
    payees_new = "  const payees = reportBundle.payees;"
    for old, new in ((import_old, import_new), (totals_old, totals_new),
                     (categories_old, categories_new), (payees_old, payees_new)):
        if text.count(old) != 1:
            raise AdapterError(
                'The Sanchay Reports tab call site no longer matches the audited source. '
                'DARWIN will not guess at a patch for a changed call site.',
                'call_site_changed', 'NO_FEASIBLE_CANDIDATE',
            )
        text = text.replace(old, new)
    return text


def _unified_diff(original: str, candidate: str, relative: str) -> str:
    return ''.join(difflib.unified_diff(
        original.splitlines(keepends=True), candidate.splitlines(keepends=True),
        fromfile=f'a/{relative}', tofile=f'b/{relative}', n=3,
    ))


def _node_binary() -> str:
    binary = shutil.which('node')
    if not binary:
        raise AdapterError(
            'Node.js was not found. Install Node 22.18 or newer to run the Sanchay report benchmark.',
            'node_missing', 'FAILED_INFRASTRUCTURE',
        )
    try:
        completed = subprocess.run([binary, '--version'], capture_output=True, text=True,
                                   timeout=8, check=False,
                                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except OSError as exc:
        raise AdapterError(f'Node.js could not start: {exc}', 'node_missing', 'FAILED_INFRASTRUCTURE') from exc
    version = completed.stdout.strip().lstrip('v')
    match = re.match(r'^(\d+)\.(\d+)', version)
    if not match or (int(match.group(1)), int(match.group(2))) < MIN_NODE:
        raise AdapterError(
            f'Node {version or "unknown"} is too old. DARWIN needs Node 22.18+ for native TypeScript execution.',
            'node_too_old', 'FAILED_INFRASTRUCTURE',
        )
    return binary


def _test_counts(output: str) -> dict:
    """Extract Vitest's pass/fail totals from its human-readable tail."""
    line = next((item for item in output.splitlines() if re.match(r'\s*Tests\s+', item)), '')
    if not line:
        return {}
    def count(word: str) -> int:
        match = re.search(rf'(\d+)\s+{word}', line)
        return int(match.group(1)) if match else 0
    passed, failed, skipped = count('passed'), count('failed'), count('skipped')
    return {'tests_passed': passed, 'tests_failed': failed, 'tests_skipped': skipped,
            'tests_total': passed + failed + skipped}


class SanchayReportingAdapter:
    id = SANCHAY_ADAPTER_ID
    version = SANCHAY_ADAPTER_VERSION
    evaluation_type = 'client_data_processing'

    def detect(self, source_root: Path, commit_sha: str, pinned: bool) -> SupportAssessment:
        required = ('web/src/utils/reporting.ts', 'web/src/utils/money.ts',
                    'web/src/utils/categories.ts', 'web/src/types/finance.ts',
                    'web/src/components/ReportsTab.tsx', 'web/src/data/persistence.ts')
        missing = [item for item in required if not (source_root / item).is_file()]
        reporting = (source_root / 'web/src/utils/reporting.ts').read_text(encoding='utf-8', errors='replace') \
            if (source_root / 'web/src/utils/reporting.ts').is_file() else ''
        exports = all(name in reporting for name in
                      ('computeReportTotals', 'computeCategorySpending',
                       'computeCategoryBreakdown', 'computePayeeBreakdown'))
        supported = not missing and exports and pinned
        reason = (
            'Pinned Sanchay report source and Reports tab call site found.'
            if supported else
            ('This commit is not the audited pinned revision.' if not pinned else
             'Required Sanchay report source files or exports were not found.')
        )
        return SupportAssessment(self.id, self.version, supported, self.evaluation_type,
                                 reason, required)

    def describe(self, source_root: Path, commit_sha: str, pinned: bool) -> dict:
        return {
            'adapter_id': self.id,
            'adapter_version': self.version,
            'evaluation_type': self.evaluation_type,
            'commit_sha': commit_sha,
            'supported': pinned,
            'timed_scope': 'three report aggregations used by ReportsTab',
            'fixtures': 'deterministic fictional ledgers; no user finance data',
        }

    def prepare(self, source_root: Path, work_dir: Path, budget: EvaluationBudget) -> PreparedEvaluation:
        source_root = source_root.resolve()
        work_dir = work_dir.resolve()
        harness = work_dir / 'harness'
        harness.mkdir(parents=True, exist_ok=True)
        overlay = work_dir / 'candidate' / 'overlay'
        overlay.mkdir(parents=True, exist_ok=True)
        (harness / 'fixtures').mkdir(parents=True, exist_ok=True)

        baseline_dir = harness / 'source'
        candidate_dir = harness / 'candidate-web'
        required = {
            'web/src/utils/reporting.ts': ('reporting.ts', 'src/utils/reporting.ts'),
            'web/src/utils/money.ts': ('money.ts', 'src/utils/money.ts'),
            'web/src/utils/categories.ts': ('categories.ts', 'src/utils/categories.ts'),
            'web/src/types/finance.ts': ('types/finance.ts', 'src/types/finance.ts'),
        }
        for source_rel, (baseline_rel, candidate_rel) in required.items():
            source = source_root / source_rel
            if not source.is_file():
                raise AdapterError(f'Required Sanchay source file is missing: {source_rel}',
                                   'source_incomplete', 'NO_FEASIBLE_CANDIDATE')
            _copy_text(source, baseline_dir / baseline_rel, _rewrite_module_specifiers)
            _copy_text(source, candidate_dir / candidate_rel, _rewrite_module_specifiers)

        # Candidate module in both harness form and real source-overlay form.
        module_template = (HARNESS_DIR / 'reportBundle.candidate.ts').read_text(encoding='utf-8')
        _copy_text(HARNESS_DIR / 'reportBundle.candidate.ts',
                   candidate_dir / 'src/utils/reportBundle.ts', _rewrite_module_specifiers)
        (overlay / 'web/src/utils').mkdir(parents=True, exist_ok=True)
        (overlay / 'web/src/components').mkdir(parents=True, exist_ok=True)
        (overlay / 'web/src/utils/reportBundle.ts').write_text(module_template, encoding='utf-8')

        original_reporting = (source_root / 'web/src/utils/reporting.ts').read_text(encoding='utf-8')
        candidate_reporting = _patch_reporting(original_reporting)
        (overlay / 'web/src/utils/reporting.ts').write_text(candidate_reporting, encoding='utf-8')
        # Harness reporting copy must use .ts specifiers after the export is added.
        candidate_reporting_harness = _rewrite_module_specifiers(candidate_reporting)
        (candidate_dir / 'src/utils/reporting.ts').write_text(candidate_reporting_harness, encoding='utf-8')

        original_tab = (source_root / 'web/src/components/ReportsTab.tsx').read_text(encoding='utf-8')
        candidate_tab = _patch_reports_tab(original_tab)
        (overlay / 'web/src/components/ReportsTab.tsx').write_text(candidate_tab, encoding='utf-8')

        checks = [
            {
                'name': 'candidate is wired into the Reports tab call site',
                'passed': 'computeReportBundle(inCurrency, activeCurrency)' in candidate_tab,
                'detail': 'web/src/components/ReportsTab.tsx',
            },
            {
                'name': 'Reports tab no longer calls the three original aggregations',
                'passed': all(token not in candidate_tab for token in
                              ('computeReportTotals(inCurrency', 'computeCategoryBreakdown(inCurrency',
                               'computePayeeBreakdown(inCurrency')),
                'detail': 'the candidate replaces the three independent traversal hooks',
            },
            {
                'name': 'Reporting module re-exports the candidate for the real call site',
                'passed': 'computeReportBundle' in candidate_reporting,
                'detail': 'web/src/utils/reporting.ts',
            },
        ]
        if not all(item['passed'] for item in checks):
            raise AdapterError('The candidate could not be wired into the real Reports tab call site.',
                               'wiring_failed', 'NO_FEASIBLE_CANDIDATE')

        # Source-only diff artifact.
        diff_text = ''.join([
            _unified_diff('', module_template, 'web/src/utils/reportBundle.ts'),
            _unified_diff(original_reporting, candidate_reporting, 'web/src/utils/reporting.ts'),
            _unified_diff(original_tab, candidate_tab, 'web/src/components/ReportsTab.tsx'),
        ])
        diff_path = work_dir / 'candidate' / 'candidate.diff'
        diff_path.write_text(diff_text, encoding='utf-8')

        # Harness runner and entries.
        for name in ('baseline-entry.ts', 'candidate-entry.ts', 'runner.mjs'):
            shutil.copy2(HARNESS_DIR / name, harness / name)
        (harness / 'package.json').write_text('{"type":"module","private":true}\n', encoding='utf-8')

        fixtures = self._build_fixtures(harness / 'fixtures', budget)
        config = {
            'schema_version': 1,
            'fixtures': [
                {'id': item['id'], 'path': f"fixtures/{item['file']}", 'seed': item['seed'],
                 'size': item['size'], 'timed': item['timed']}
                for item in fixtures
            ],
            'sizes': list(budget.sizes),
            'seeds': list(budget.seeds),
            'repetitions': budget.repetitions,
            'warmups': budget.warmups,
            'payee_limit': 5,
            'output': 'benchmark.json',
        }
        config_path = harness / 'config.json'
        _write_json(config_path, config)

        return PreparedEvaluation(
            work_dir=work_dir, source_root=source_root, harness_dir=harness,
            fixtures=fixtures, config_path=config_path, candidate_diff=diff_path,
            candidate_files=['web/src/utils/reportBundle.ts', 'web/src/utils/reporting.ts',
                             'web/src/components/ReportsTab.tsx'],
            checks=checks,
        )

    def _build_fixtures(self, folder: Path, budget: EvaluationBudget) -> list[dict]:
        fixtures: list[dict] = []
        for seed in budget.seeds:
            for size in budget.sizes:
                currency = CURRENCIES[(seed + size // 1000) % len(CURRENCIES)]
                ledger = _generate_ledger(seed, size, currency)
                identifier = f'seed{seed}-size{size}'
                checksum = _sha256_text(_canonical(ledger['transactions']))
                value = {
                    'schema_version': 1,
                    'id': identifier,
                    'seed': seed,
                    'size': size,
                    'currency': currency,
                    'accounts': list(ACCOUNTS),
                    'transactions': ledger['transactions'],
                    'raw_rows': ledger['raw_rows'],
                    'noise_rows': ledger['noise_rows'],
                    'scoped_rows': size,
                    'checksum_sha256': checksum,
                    'generated_by': f'{self.id}@{self.version}',
                }
                filename = f'{identifier}.json'
                _write_json(folder / filename, value)
                fixtures.append({'id': identifier, 'seed': seed, 'size': size, 'currency': currency,
                                 'timed': True, 'file': filename, 'checksum_sha256': checksum})
        for edge in _edge_fixtures():
            checksum = _sha256_text(_canonical(edge['transactions']))
            value = {
                'schema_version': 1,
                'accounts': list(ACCOUNTS),
                'scoped_rows': edge.get('scoped_rows', len(edge['transactions'])),
                'checksum_sha256': checksum,
                'generated_by': f'{self.id}@{self.version}',
                **edge,
            }
            filename = f"{edge['id']}.json"
            _write_json(folder / filename, value)
            fixtures.append({'id': edge['id'], 'seed': 0, 'size': edge['size'],
                             'currency': edge['currency'], 'timed': False, 'file': filename,
                             'checksum_sha256': checksum})
        return fixtures

    def candidates(self, prepared: PreparedEvaluation) -> list[Candidate]:
        return [Candidate(
            candidate_id='sanchay-single-pass-reporting',
            label='Shared single-pass report aggregation',
            description=(
                'Computes totals, category spending and payee aggregates in one traversal, '
                'then applies the original filters, ordering and money rounding.'
            ),
            diff_path=prepared.candidate_diff,
            files=prepared.candidate_files,
            wiring={'call_site': 'web/src/components/ReportsTab.tsx',
                    'checks': prepared.checks},
        )]

    def measure(self, prepared: PreparedEvaluation, candidate: Candidate,
                budget: EvaluationBudget, check) -> dict:
        node = _node_binary()
        timeout = budget.wall_clock_s
        env = {
            key: os.environ[key] for key in
            ('PATH', 'SystemRoot', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'HOME',
             'USERPROFILE', 'ComSpec', 'PATHEXT', 'NUMBER_OF_PROCESSORS')
            if key in os.environ
        }
        env.update({'NODE_OPTIONS': '', 'NO_COLOR': '1', 'CI': '1'})
        command = [node, '--no-warnings', '--max-old-space-size=512',
                   'runner.mjs', 'config.json']
        started = time.monotonic()
        stdout = ''
        stderr = ''
        process = subprocess.Popen(
            command, cwd=str(prepared.harness_dir), env=env, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding='utf-8', errors='replace',
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        try:
            while process.poll() is None:
                if check():
                    self._kill(process)
                    raise AdapterCancelled('Evaluation cancelled by operator')
                if time.monotonic() - started > timeout:
                    self._kill(process)
                    raise AdapterError(
                        f'The Node benchmark exceeded its {timeout} s wall-clock budget.',
                        'benchmark_timeout', 'FAILED_INFRASTRUCTURE',
                    )
                time.sleep(0.2)
            stdout, stderr = process.communicate(timeout=10)
        finally:
            if process.poll() is None:
                self._kill(process)
        duration = round(time.monotonic() - started, 3)
        if process.returncode != 0:
            tail = (stderr or stdout or '').strip()[-4000:]
            raise AdapterError(
                f'The benchmark runner failed with exit code {process.returncode}. {tail}',
                'benchmark_failed', 'FAILED_INFRASTRUCTURE',
            )
        result_path = prepared.harness_dir / 'benchmark.json'
        if not result_path.is_file():
            raise AdapterError('The benchmark runner produced no evidence file.',
                               'benchmark_missing', 'FAILED_INFRASTRUCTURE')
        benchmark = json.loads(result_path.read_text(encoding='utf-8'))
        if not benchmark.get('ok'):
            raise AdapterError('The benchmark runner reported an internal failure.',
                               'benchmark_failed', 'FAILED_INFRASTRUCTURE')
        source_tests = None
        if budget.include_source_tests:
            source_tests = self._run_source_tests(prepared, check)
        return {
            'benchmark': benchmark,
            'source_tests': source_tests,
            'duration_s': duration,
            'command': command,
            'stdout_tail': stdout.strip()[-4000:],
            'stderr_tail': stderr.strip()[-4000:],
        }

    def _kill(self, process: subprocess.Popen) -> None:
        if process.poll() is not None:
            return
        try:
            if os.name == 'nt':
                subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                               capture_output=True, timeout=15, check=False,
                               creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            else:
                process.terminate()
        except (OSError, subprocess.SubprocessError):
            pass
        try:
            process.kill()
        except OSError:
            pass

    def _run_source_tests(self, prepared: PreparedEvaluation, check) -> dict:
        web = prepared.source_root / 'web'
        vitest = next((path for path in (
            web / 'node_modules/vitest/vitest.mjs',
            web / 'node_modules/vitest/dist/cli.js',
        ) if path.is_file()), None)
        if not vitest:
            return {
                'status': 'skipped',
                'reason': 'The pinned checkout has no installed Vitest runtime; DARWIN did not install packages.',
            }
        overlay = prepared.work_dir / 'source-tests'
        shutil.rmtree(overlay, ignore_errors=True)
        shutil.copytree(web / 'src', overlay / 'src',
                        ignore=shutil.ignore_patterns('node_modules', '.DS_Store'),
                        dirs_exist_ok=True)
        for name in ('package.json', 'vite.config.ts', 'tsconfig.json', 'tsconfig.app.json',
                     'tsconfig.node.json', 'index.html'):
            source = web / name
            if source.is_file():
                shutil.copy2(source, overlay / name)
        for relative in ('src/utils/reportBundle.ts', 'src/utils/reporting.ts',
                         'src/components/ReportsTab.tsx'):
            source = prepared.work_dir / 'candidate' / 'overlay' / 'web' / relative
            target = overlay / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        link = overlay / 'node_modules'
        try:
            if os.name == 'nt':
                completed = subprocess.run(
                    [os.environ.get('ComSpec', 'cmd.exe'), '/c', 'mklink', '/J',
                     str(link), str(web / 'node_modules')],
                    capture_output=True, text=True, timeout=30, check=False,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
                )
                if completed.returncode != 0:
                    raise OSError(completed.stderr.strip() or 'junction failed')
            else:
                os.symlink(web / 'node_modules', link, target_is_directory=True)
        except OSError as exc:
            return {'status': 'skipped', 'reason': f'Could not expose the installed test runtime: {exc}'}

        node = _node_binary()
        command = [node, str(vitest), 'run', 'src/utils/reporting.test.ts', '--reporter=dot']
        started = time.monotonic()
        try:
            process = subprocess.Popen(
                command, cwd=str(overlay), text=True, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, encoding='utf-8', errors='replace',
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
            )
            while process.poll() is None:
                if check():
                    self._kill(process)
                    raise AdapterCancelled('Evaluation cancelled during source tests')
                if time.monotonic() - started > 240:
                    self._kill(process)
                    return {'status': 'failed', 'reason': 'Source test overlay exceeded 240 s.'}
                time.sleep(0.2)
            output = process.communicate(timeout=10)[0] or ''
            result = {
                'status': 'passed' if process.returncode == 0 else 'failed',
                'command': command,
                'duration_s': round(time.monotonic() - started, 3),
                'exit_code': process.returncode,
                'output_tail': output.strip()[-6000:],
                'suite': 'web/src/utils/reporting.test.ts',
            }
            result.update(_test_counts(output))
            return result
        finally:
            link.unlink(missing_ok=True)

    def verify(self, prepared: PreparedEvaluation, candidate: Candidate,
               measurements: dict) -> dict:
        benchmark = measurements['benchmark']
        checks = list(prepared.checks)
        checks.extend(benchmark.get('parity', {}).get('checks', []))
        source_tests = measurements.get('source_tests')
        if source_tests and source_tests.get('status') == 'failed':
            checks.append({
                'name': "Sanchay's existing reporting tests pass against the candidate overlay",
                'passed': False,
                'detail': source_tests.get('reason') or source_tests.get('output_tail', '')[-500:],
            })
        wiring_ok = all(item['passed'] for item in prepared.checks)
        parity_ok = bool(benchmark.get('parity', {}).get('passed')) and wiring_ok and not (
            source_tests and source_tests.get('status') == 'failed')

        runs = {item['fixture_id']: item for item in benchmark.get('runs', [])}
        summaries = []
        for item in benchmark.get('summaries', []):
            run = runs.get(item['fixture_id'], {})
            summaries.append({
                **item,
                'baseline_samples_ns': run.get('baseline_ns', []),
                'candidate_samples_ns': run.get('candidate_ns', []),
            })

        verdict = decide(
            parity_passed=parity_ok,
            checks=checks,
            summaries=summaries,
            candidate_count=1,
            infrastructure_ok=True,
        )
        verdict['source_tests'] = source_tests or {
            'status': 'not_run',
            'reason': 'Quick mode does not run the repository test overlay.',
        }
        return {
            'parity': {
                'passed': parity_ok,
                'checks_passed': sum(1 for item in checks if item.get('passed')),
                'checks_total': len(checks),
                'failures': [item for item in checks if not item.get('passed')][:8],
            },
            'checks': checks,
            'summaries': summaries,
            'verdict': verdict,
            'source_tests': verdict['source_tests'],
            'environment': benchmark.get('environment', {}),
            'measurement_scope': benchmark.get('measurement_scope'),
            'harness': {
                'command': measurements.get('command'),
                'duration_s': measurements.get('duration_s'),
                'stdout_tail': measurements.get('stdout_tail'),
                'stderr_tail': measurements.get('stderr_tail'),
            },
        }

    def explain(self, evidence: dict) -> dict:
        return evidence['verdict']
