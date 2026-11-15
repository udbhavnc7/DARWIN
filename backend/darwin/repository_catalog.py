"""Trusted repository examples for Real Project Mode.

Only repositories listed here may run an executable adapter. Any other public
GitHub repository can still be inspected, but it is explicitly inspection-only.
The pinned commit is part of the trust boundary: a moving branch is never enough
to authorize execution.
"""
from __future__ import annotations

from copy import deepcopy

SANCHAY_ADAPTER_ID = 'sanchay-reporting-v1'
SANCHAY_ADAPTER_VERSION = '1.0.0'
SANCHAY_REPOSITORY = 'https://github.com/udbhavnc7/Sanchay'
SANCHAY_COMMIT = '7e1bc4cdd31e53380e7896b4a20a864bbebcee1e'

CATALOG = [
    {
        'id': 'sanchay',
        'name': 'Sanchay',
        'subtitle': 'Personal finance · local-first',
        'repository_url': SANCHAY_REPOSITORY,
        'default_ref': 'main',
        'pinned_commit': SANCHAY_COMMIT,
        'trusted': True,
        'summary': (
            'A React + TypeScript personal-finance dashboard hosted in an Android WebView. '
            'Ledger data lives in browser local storage; there is no deployed server backend.'
        ),
        'evaluation_type': 'client_data_processing',
        'adapter': {
            'adapter_id': SANCHAY_ADAPTER_ID,
            'adapter_version': SANCHAY_ADAPTER_VERSION,
            'display_name': 'Financial reports: original vs single-pass aggregation',
            'change_summary': (
                'The Reports page currently walks the currency-scoped ledger three times: '
                'once for totals, once for category spending and once for payees. The candidate '
                'produces the same three results in one shared traversal.'
            ),
            'mechanism': (
                'One pass accumulates minor-unit totals, category spending and payee amounts. '
                'The existing minor-unit money helpers and the existing ordering/filtering rules '
                'are retained.'
            ),
            'correctness_rules': [
                'Totals, category breakdown and payee breakdown must match the original byte-for-byte after JSON canonicalisation.',
                'Refunds reduce spending and payee totals exactly as the original does; they never become income.',
                'Transfers are excluded from spending and payees; only completed goal debits count as saved.',
                'Pending, failed and flagged transactions never contribute to a completed report.',
                'Currencies are never combined; each report is scoped to one currency before aggregation.',
                'JPY (zero minor digits) and two-decimal currencies keep their existing precision.',
                'Results are deterministic and the original ledger array is not mutated.',
            ],
            'scope_note': (
                'This evaluates a client-side report-calculation strategy. It does not evaluate '
                'API replicas, a server queue, PostgreSQL, or cloud failover, because Sanchay has '
                'no deployed server backend.'
            ),
            'modes': [
                {
                    'id': 'quick',
                    'label': 'Quick live comparison',
                    'description': 'Two deterministic ledger sizes on one seed, prepared locally.',
                    'estimated_seconds': 20,
                },
                {
                    'id': 'full',
                    'label': 'Full comparison',
                    'description': 'Three seeds and three ledger sizes, with raw samples retained.',
                    'estimated_seconds': 60,
                },
            ],
        },
    }
]

SANCHAY = CATALOG[0]


def canonical_repository(url: str) -> str:
    text = (url or '').strip().rstrip('/')
    if text.lower().endswith('.git'):
        text = text[:-4]
    return text.lower()


def catalog_entry(url: str | None = None, adapter_id: str | None = None):
    """Return a copy of the trusted catalog entry that matches, else None."""
    for entry in CATALOG:
        if adapter_id and entry['adapter']['adapter_id'] != adapter_id:
            continue
        if url and canonical_repository(entry['repository_url']) != canonical_repository(url):
            continue
        return deepcopy(entry)
    return None


def is_trusted_source(url: str, commit_sha: str, adapter_id: str = SANCHAY_ADAPTER_ID) -> bool:
    entry = catalog_entry(url, adapter_id)
    return bool(entry and entry['pinned_commit'] == commit_sha)


def adapter_catalog() -> dict:
    """Presenter-facing catalog with no unverified measurements."""
    return {
        'schema_version': 1,
        'examples': [
            {
                'id': entry['id'],
                'name': entry['name'],
                'subtitle': entry['subtitle'],
                'repository_url': entry['repository_url'],
                'default_ref': entry['default_ref'],
                'pinned_commit': entry['pinned_commit'],
                'summary': entry['summary'],
                'evaluation_type': entry['evaluation_type'],
                'adapter': deepcopy(entry['adapter']),
            }
            for entry in CATALOG
        ],
        'policy': {
            'inspection': 'Public HTTPS GitHub repositories may be inspected after explicit consent.',
            'execution': 'Only catalogued repositories at the pinned commit may run an audited adapter.',
            'recorded_label': 'Saved results are always labelled recorded, never live.',
            'minimum_improvement_pct': 5.0,
        },
    }
