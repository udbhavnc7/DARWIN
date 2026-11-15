"""Capture read-only snapshots from a running local DARWIN stack for the hosted showcase.

The showcase build of the dashboard (``VITE_SHOWCASE=1``) serves these files instead of
calling the engine, so teammates can browse recorded evidence without anything running.
Only GET responses and deterministic, side-effect-free POST reads (topology preview,
SimPy estimate, Compose export) are captured. Nothing here starts runs or writes to the
shop. Machine-specific home directories are redacted before writing.

Usage (with the local stack running on 127.0.0.1):
    python scripts/capture_showcase.py
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKLOADS = ('normal', 'flash_sale', 'checkout_heavy')
GENOMES = [
    {'app_replicas': r, 'catalog_cache_ttl_s': ttl, 'notification_mode': n, 'retry_policy': p}
    for r, ttl, n, p in itertools.product((1, 2, 3), (0, 10, 30), ('sync', 'queued'), ('none', 'idempotent_only'))
]


def genome_key(genome: dict) -> str:
    return f"{genome['app_replicas']}-{genome['catalog_cache_ttl_s']}-{genome['notification_mode']}-{genome['retry_policy']}"


def redactor():
    homes = {str(Path.home()), os.environ.get('USERPROFILE', ''), os.environ.get('HOME', '')}
    patterns = []
    for home in filter(None, homes):
        for variant in {home, home.replace('\\', '/'), home.replace('\\', '\\\\'), home.replace('\\', '\\\\\\\\')}:
            patterns.append(re.escape(variant))
    regex = re.compile('|'.join(sorted(patterns, key=len, reverse=True)), re.IGNORECASE) if patterns else None
    return (lambda text: regex.sub('~', text)) if regex else (lambda text: text)


class Client:
    def __init__(self, api: str, shop: str, token: str | None):
        self.api, self.shop, self.token = api.rstrip('/'), shop.rstrip('/'), token

    def request(self, url: str, body: object | None = None) -> bytes:
        headers = {'Content-Type': 'application/json'}
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'
        data = json.dumps(body).encode() if body is not None else None
        with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers), timeout=60) as response:
            return response.read()

    def get(self, path: str):
        return json.loads(self.request(self.api + path))

    def post(self, path: str, body: object):
        return json.loads(self.request(self.api + path, body))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--api', default='http://127.0.0.1:8000')
    parser.add_argument('--shop', default='http://127.0.0.1:8010')
    parser.add_argument('--output', type=Path, default=ROOT / 'frontend' / 'showcase')
    args = parser.parse_args()
    client = Client(args.api, args.shop, os.environ.get('DARWIN_API_TOKEN'))
    redact = redactor()
    staging = args.output.with_name(args.output.name + '.tmp')
    shutil.rmtree(staging, ignore_errors=True)
    (staging / 'events').mkdir(parents=True)

    def write(name: str, value: object) -> None:
        (staging / name).write_text(redact(json.dumps(value, separators=(',', ':'))), encoding='utf-8')

    write('project.json', client.get('/api/project'))
    write('preflight.json', client.get('/api/preflight'))
    for runtime in ('native', 'docker'):
        write(f'scenarios-{runtime}.json', client.get(f'/api/exhibition/scenarios?runtime={runtime}'))

    experiments = client.get('/api/experiments')
    write('experiments.json', experiments)
    for run in experiments:
        write(f"events/experiment-{run['experiment_id']}.json", client.get(f"/api/experiments/{run['experiment_id']}/events"))
    searches = client.get('/api/searches')
    write('searches.json', searches)
    for run in searches:
        write(f"events/search-{run['search_id']}.json", client.get(f"/api/searches/{run['search_id']}/events"))

    previews, simulations, compose = {}, {}, {}
    for genome in GENOMES:
        key = genome_key(genome)
        previews[key] = client.post('/api/genomes/preview', genome)
        compose[key] = client.request(client.api + '/api/genomes/compose', genome).decode()
        for workload in WORKLOADS:
            simulations[f'{key}|{workload}'] = client.post(
                '/api/simulate', {'genome': genome, 'workload_profile': workload, 'duration_s': 12})
    write('previews.json', previews)
    write('simulations.json', simulations)
    write('compose.json', compose)

    shop = {'catalog': None, 'ledger': None}
    try:
        shop['catalog'] = json.loads(client.request(client.shop + '/shop/catalog'))
        shop['ledger'] = json.loads(client.request(client.shop + '/shop/ledger'))
    except (urllib.error.URLError, TimeoutError) as error:
        print(f'shop not captured: {error}')
    write('shop.json', shop)

    commit = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    write('manifest.json', {
        'captured_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'commit': commit, 'experiments': len(experiments), 'searches': len(searches),
    })
    # Copy rather than rename: a running Vite dev server may hold a watch handle on the staging folder.
    shutil.rmtree(args.output, ignore_errors=True)
    shutil.copytree(staging, args.output)
    shutil.rmtree(staging, ignore_errors=True)
    size = sum(path.stat().st_size for path in args.output.rglob('*') if path.is_file())
    print(f'captured {len(experiments)} experiments and {len(searches)} searches into {args.output} ({size / 1e6:.1f} MB)')


if __name__ == '__main__':
    main()
