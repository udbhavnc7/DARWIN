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

FLASK_REDIS_ADAPTER_ID = 'flask-redis-compose-v1'
FLASK_REDIS_ADAPTER_VERSION = '1.0.0'
FLASK_REDIS_REPOSITORY = 'https://github.com/docker/awesome-compose'
FLASK_REDIS_COMMIT = '30f4b7f6a6c3b0c0ecf4d4efb0de203c48d11562'

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
    },
    {
        'id': 'flask-redis',
        'name': 'Flask + Redis sample',
        'subtitle': 'Genuine public backend · awesome-compose',
        'repository_url': FLASK_REDIS_REPOSITORY,
        'default_ref': 'master',
        'pinned_commit': FLASK_REDIS_COMMIT,
        'trusted': True,
        'sparse_paths': ['flask-redis'],
        'summary': (
            'Docker’s public Flask + Redis Compose sample. A hit counter stored in Redis is served '
            'by a Flask app. DARWIN does not run the repository Compose file; it deploys a reviewed '
            'isolated stack (gunicorn, nginx, official Redis) from app.py and requirements.txt only.'
        ),
        'evaluation_type': 'backend_architecture',
        'license': 'CC0-1.0',
        'adapter': {
            'adapter_id': FLASK_REDIS_ADAPTER_ID,
            'adapter_version': FLASK_REDIS_ADAPTER_VERSION,
            'display_name': 'Architecture: replicas and gunicorn workers',
            'change_summary': (
                'Baseline is one Flask replica with one gunicorn worker. Candidates add a second '
                'replica behind nginx, or a second worker on the original replica. Redis stays shared.'
            ),
            'mechanism': (
                'DARWIN copies flask-redis/app.py into a DARWIN-owned image, generates nginx + Compose, '
                'drives seeded HTTP GET /, checks that the Redis counter increases, and optionally '
                'restarts one replica to measure recovery.'
            ),
            'correctness_rules': [
                'GET / returns the reviewed Flask counter sentence.',
                'The viewed-count integer strictly increases through the gateway (shared Redis).',
                'A restarted web replica becomes healthy again on loopback.',
            ],
            'scope_note': (
                'This evaluates deployable process topology for one public sample. It does not convert '
                'Flask to another framework, invent a SQL database, or run the repository Dockerfile.'
            ),
            'modes': [
                {
                    'id': 'quick',
                    'label': 'Quick measured comparison',
                    'description': 'Baseline plus the challenge’s primary candidate, bounded HTTP window.',
                    'estimated_seconds': 180,
                },
                {
                    'id': 'full',
                    'label': 'Bounded architecture search',
                    'description': 'All reviewed candidates, fault restart, Pareto of p95 / errors / replicas.',
                    'estimated_seconds': 420,
                },
            ],
        },
    },
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


def is_trusted_source(url: str, commit_sha: str, adapter_id: str | None = None) -> bool:
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
            'backend_isolation': 'Linux Docker engine required. Repository Compose files are never executed.',
        },
        'challenges': [
            {'id': 'faster', 'label': 'Faster under traffic'},
            {'id': 'spike', 'label': 'Handle a traffic spike'},
            {'id': 'resources', 'label': 'Use fewer resources'},
            {'id': 'recover', 'label': 'Recover more reliably'},
        ],
    }
