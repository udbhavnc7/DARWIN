"""Read-only resource checks before clearing an interrupted-run block. Stop the API first."""
import argparse
import json
import os
import socket
import subprocess
from uuid import UUID

from filelock import FileLock
import psycopg
import psutil

from darwin.experiments import Store, now
from darwin.shop.db import DEFAULT_DSN


def verify_absent(store, record):
    for candidate in record.get('candidates', []):
        for evaluation in candidate['evaluations']:
            ident = str(UUID(evaluation['evaluation_id']))
            folder = store.root / str(UUID(record['experiment_id'])) / ident
            path = folder / 'ownership.json'
            ownership = json.loads(path.read_text()) if path.exists() else {}
            if record['request']['mode'].startswith('native_'):
                for item in ownership.get('process_identities', []):
                    try:
                        process = psutil.Process(item['pid'])
                        if abs(process.create_time() - item['created_at']) < .01:
                            raise RuntimeError(f'Owned process {process.pid} still exists')
                    except psutil.NoSuchProcess:
                        pass
                for port in ownership.get('socket_ports', []):
                    with socket.socket() as sock:
                        sock.settimeout(.2)
                        if sock.connect_ex(('127.0.0.1', port)) == 0:
                            raise RuntimeError(f'Port {port} is occupied; inspect it before clearing recovery')
                if record['request']['mode'] == 'native_benchmark':
                    if (folder / 'private-pgdata').exists():
                        raise RuntimeError('Private database directory remains; review before clearing recovery')
                    continue
                database = 'darwin_run_' + ident.replace('-', '')
                with psycopg.connect(os.environ.get('DARWIN_NATIVE_DATABASE_URL', DEFAULT_DSN), connect_timeout=2) as conn:
                    if conn.execute('SELECT 1 FROM pg_database WHERE datname=%s', (database,)).fetchone():
                        raise RuntimeError(f'Owned database {database} still exists')
            else:
                project = 'darwin-run-' + ident.replace('-', '')
                for command in (['docker', 'ps', '-aq'], ['docker', 'volume', 'ls', '-q'], ['docker', 'network', 'ls', '-q']):
                    output = subprocess.check_output([*command, '--filter', f'label=com.docker.compose.project={project}'], timeout=10)
                    if output.strip():
                        raise RuntimeError(f'Docker resources still exist for {project}; use its saved Compose file to clean up')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default='artifacts/experiments')
    args = parser.parse_args()
    store = Store(args.root)
    with FileLock(str(store.root / 'worker.lock'), timeout=0):
        for record in store.all():
            if record.get('cleanup_status') == 'requires_review':
                verify_absent(store, record)
                record.update(cleanup_status='verified_absent', recovery_verified_at=now())
                store.save(record, 'Verified that interrupted sandbox resources are absent')
                print(record['experiment_id'], 'resources absent; restart the API to resume')


if __name__ == '__main__':
    main()
