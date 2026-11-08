"""One genome drives both the topology and concrete deployment specification."""
import argparse
import copy
import hashlib
import json
from pathlib import Path

import yaml

from darwin.contracts import Genome

ROOT = Path(__file__).resolve().parents[2]


def canonical(genome: Genome):
    return json.dumps(genome.model_dump(), sort_keys=True, separators=(',', ':'))


def genome_hash(genome: Genome):
    return hashlib.sha256(canonical(genome).encode()).hexdigest()


def runtime_environment(genome: Genome):
    return {'DARWIN_GENOME_JSON': canonical(genome), 'DARWIN_CACHE_NAMESPACE': genome_hash(genome)}


def render_compose(genome: Genome):
    config = yaml.safe_load((ROOT / 'compose.yaml').read_text())
    config.pop('x-shop', None)
    config['name'] = 'darwin-' + genome_hash(genome)[:12]
    services = config['services']
    for service in services.values():
        if 'build' in service:
            service['build'] = str(ROOT)
            service['environment'] = {**service.get('environment', {}), **runtime_environment(genome)}
    prototype = services.pop('api')
    # Keep every allowed candidate within the MVP's 4-core / 4096-MiB envelope.
    for name, cpu, memory in [('db', 1, '1280m'), ('inventory', .5, '384m'),
                               ('payment', .5, '384m'), ('gateway', .25, '128m'), ('seed', .25, '256m')]:
        services[name]['cpus'], services[name]['mem_limit'] = cpu, memory
    api_names = [f'api-{i+1}' for i in range(genome.app_replicas)]
    for name in api_names:
        service = copy.deepcopy(prototype)
        service['environment'].update(DARWIN_INSTANCE_ID=name, DARWIN_REDIS_URL='redis://redis:6379/0')
        # Fixed per-instance cap: extra replicas have real resource cost.
        service['cpus'] = 0.4
        service['mem_limit'] = '384m'
        services[name] = service
    services['gateway']['environment']['DARWIN_SHOP_API_URLS'] = ','.join(f'http://{name}:8000' for name in api_names)
    services['gateway']['environment'].pop('DARWIN_SHOP_API_URL', None)
    services['gateway']['depends_on'] = {name: {'condition': 'service_healthy'} for name in api_names}
    if genome.catalog_cache_ttl_s:
        services['redis'] = {'image': 'redis:8', 'networks': ['sandbox'], 'cpus': 0.25, 'mem_limit': '128m',
                             'command': ['redis-server', '--save', '', '--appendonly', 'no', '--maxmemory', '96mb', '--maxmemory-policy', 'allkeys-lru'],
                             'healthcheck': {'test': ['CMD', 'redis-cli', 'ping'], 'interval': '5s', 'timeout': '3s', 'retries': 12}}
        for name in api_names:
            services[name]['depends_on']['redis'] = {'condition': 'service_healthy'}
    if genome.notification_mode == 'queued':
        worker = copy.deepcopy(prototype)
        worker['command'] = ['python', '-m', 'uvicorn', 'darwin.shop.worker:app', '--host', '0.0.0.0', '--port', '8000']
        worker['depends_on'] = {'seed': {'condition': 'service_completed_successfully'}}
        worker['cpus'], worker['mem_limit'] = 0.25, '256m'
        services['worker'] = worker
    return config


def topology(genome: Genome):
    services = render_compose(genome)['services']
    nodes = [{'id': name, 'kind': 'api' if name.startswith('api-') else name} for name in services if name != 'seed']
    edges = []
    for name in services:
        if name.startswith('api-'):
            edges.extend([{'source': 'gateway', 'target': name}, *[{'source': name, 'target': target} for target in ('inventory', 'payment', 'db')]])
            if 'redis' in services:
                edges.append({'source': name, 'target': 'redis'})
    edges.extend({'source': name, 'target': 'db'} for name in ('inventory', 'payment', 'worker') if name in services)
    return {'nodes': nodes, 'edges': edges, 'genome_hash': genome_hash(genome), 'deployment_verified': False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('genome', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    genome = Genome.model_validate_json(args.genome.read_text())
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'genome.json').write_text(canonical(genome) + '\n')
    (args.output / 'compose.yaml').write_text(yaml.safe_dump(render_compose(genome), sort_keys=False))
    (args.output / 'topology.json').write_text(json.dumps(topology(genome), indent=2))
    print(genome_hash(genome))


if __name__ == '__main__':
    main()
