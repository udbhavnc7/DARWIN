"""Export verified experiment artifacts and a standalone recorded demo."""
import argparse
import hashlib
import html
import json
from pathlib import Path
from statistics import median
from uuid import UUID
import zipfile

from darwin.architecture import ROOT
from darwin.experiments import Store, TERMINAL


def checked_bytes(root, name, digest):
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f'Invalid artifact path: {name}')
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError(f'Artifact digest mismatch: {name}')
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('experiments', type=UUID, nargs='+')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--root', type=Path, default=ROOT / 'artifacts/experiments',
                        help='Experiment evidence directory')
    parser.add_argument('--comparison', type=Path)
    parser.add_argument('--docker-acceptance', type=Path, help='Completed Docker acceptance.json')
    parser.add_argument('--video', type=Path)
    parser.add_argument('--dashboard', type=Path, help='Dashboard screenshot for the recorded demo')
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit('Output already exists')
    if not (args.root / 'experiments.sqlite3').is_file():
        parser.error('--root must contain an experiment evidence store')
    store = Store(args.root)
    comparison = json.loads(args.comparison.read_bytes()) if args.comparison else None
    identifiers = list(map(str, args.experiments))
    if comparison:
        if comparison['status'] != 'completed':
            raise SystemExit('Wait for validation to complete before including the comparison')
        for search in comparison['searches'] + comparison.get('interrupted_searches', []):
            identifiers.extend(str(UUID(ident)) for ident in search['experiment_ids'])
    acceptance_files = {}
    if args.docker_acceptance:
        data = args.docker_acceptance.read_bytes()
        acceptance = json.loads(data)
        if acceptance['status'] != 'passed':
            parser.error('--docker-acceptance requires a passed acceptance report')
        cases = acceptance['cases']
        acceptance_files['docker-acceptance.json'] = data
        search_id = str(UUID(cases['search']))
        search_root = args.docker_acceptance.parent / 'experiments' / 'searches'
        if not (search_root / 'experiments.sqlite3').is_file():
            parser.error('Docker search evidence is missing beside the acceptance report')
        search_store = Store(search_root)
        search = search_store.get(search_id)
        acceptance_files['docker-search.json'] = json.dumps(search, indent=2).encode()
        identifiers.extend(str(UUID(ident)) for case, ident in cases.items() if case != 'search')
        identifiers.extend(str(UUID(ident)) for ident in search['experiment_ids'])
    records = [store.get(ident) for ident in dict.fromkeys(identifiers)]
    if any(record['status'] not in TERMINAL for record in records):
        raise SystemExit('Wait for experiments to finish before exporting')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    content = dict(acceptance_files)
    rows = []
    for record in records:
        ident = record['experiment_id']
        content[f'experiments/{ident}/record.json'] = json.dumps(record, indent=2).encode()
        content[f'experiments/{ident}/replay-request.json'] = json.dumps(record['request'], indent=2).encode()
        source = store.root / ident / 'source'
        source_manifest_raw = (store.root / ident / 'source-manifest.json').read_bytes()
        source_manifest = json.loads(source_manifest_raw)
        source_hash = hashlib.sha256(json.dumps(source_manifest, sort_keys=True).encode()).hexdigest()
        if source_hash != record['source_hash']:
            raise ValueError(f'Source manifest mismatch for {ident}')
        content[f'experiments/{ident}/source-manifest.json'] = source_manifest_raw
        for name, digest in source_manifest.items():
            content[f'experiments/{ident}/source/{name}'] = checked_bytes(source, name, digest)
        for candidate in record['candidates']:
            values = []
            checks = []
            for evaluation in candidate['evaluations']:
                for artifact in evaluation['artifacts']:
                    evaluation_id = str(UUID(evaluation['evaluation_id']))
                    name = artifact['name']
                    content[f'experiments/{ident}/{evaluation_id}/{name}'] = checked_bytes(
                        store.root / ident / evaluation_id, name, artifact['sha256'])
                    if name == 'fault-report.json':
                        checks.append(f'<a href="experiments/{ident}/{evaluation_id}/fault-report.json">Report {len(checks) + 1}</a>')
                if evaluation.get('metrics'):
                    values.append(evaluation['metrics']['p95_ms'])
            genome = candidate['genome']
            label = (f"{genome['app_replicas']} API · {genome['catalog_cache_ttl_s']}s cache · "
                     f"{genome['notification_mode']} · {genome['retry_policy']}")
            runtime = record['request']['mode'].split('_', 1)[0].capitalize()
            gate = candidate.get('summary', {}).get('gate',
                                                     'not_checked' if record['status'] == 'completed' else 'incomplete')
            rows.append('<tr><td>' + html.escape(ident[:8]) + '</td><td>' + runtime + '</td><td>' +
                        html.escape(label) + '</td><td>' +
                        html.escape(gate.replace('_', ' ')) +
                        '</td><td>' + (f'{median(values):.1f}' if values else '—') +
                        '</td><td>' + ' · '.join(checks) + '</td></tr>')
    summary_html = ''
    if comparison:
        content['search-comparison.json'] = args.comparison.read_bytes()
        summaries = []
        for row in comparison['summary']:
            label = row['algorithm'].replace('_', ' ') + (' · no simulator' if not row['simulator'] else '')
            p95 = row['best_feasible_p95_ms']
            summaries.append(
                f"<tr><td>{html.escape(label)}</td><td>{row['attempts']}</td>"
                f"<td>{row['feasible_configurations']}</td><td>{'—' if p95 is None else f'{p95:.1f}'}</td></tr>")
        summary_html = ('<h2>Equal-budget search comparison</h2><table><tr><th>Search</th><th>Attempts</th>'
                        '<th>Feasible configurations</th><th>Best feasible p95 ms</th></tr>'
                        + ''.join(summaries) + '</table><h2>Recorded experiments</h2>')
    calibration = store.root / 'simulation-calibration.json'
    if calibration.is_file():
        content['simulation-calibration.json'] = calibration.read_bytes()
    if args.video:
        content['recorded-demo.mp4'] = args.video.read_bytes()
    dashboard_html = ''
    if args.dashboard:
        dashboard_name = 'dashboard' + args.dashboard.suffix.lower()
        content[dashboard_name] = args.dashboard.read_bytes()
        dashboard_html = f'<p><a href="{html.escape(dashboard_name, quote=True)}">Dashboard screenshot</a></p>'
    project_files = ['README.md', 'ROADMAP.md', 'Dockerfile', 'compose.yaml', 'pyproject.toml',
                     'requirements.lock.txt', '.dockerignore', 'frontend/index.html',
                     'frontend/package.json', 'frontend/package-lock.json', 'frontend/tsconfig.json',
                     'frontend/vite.config.ts']
    for pattern in ('backend/**/*.py', 'frontend/src/**/*', 'frontend/public/**/*',
                    'scripts/*.py', 'scripts/*.ps1', 'examples/*.json', 'tests/*.py'):
        project_files.extend(path.relative_to(ROOT).as_posix() for path in ROOT.glob(pattern) if path.is_file())
    for name in sorted(set(project_files)):
        content['project/' + name] = (ROOT / name).read_bytes()
    content['recorded-demo.html'] = (
        '<!doctype html><html lang="en"><meta charset="utf-8"><title>DARWIN recorded demonstration</title>'
        '<style>body{background:#101611;color:#e5e9e3;font:18px system-ui;margin:40px}'
        'td,th{padding:16px;border-bottom:1px solid #65755d;text-align:left}h1,a{color:#c3ee83}</style>'
        '<h1>DARWIN · Recorded demonstration</h1><p>Saved local experiment results. '
        'Run IDs and artifact hashes are included in this bundle.</p>' + dashboard_html +
        ('<p><a href="docker-acceptance.json">Docker acceptance</a> · <a href="docker-search.json">Docker search</a></p>'
         if acceptance_files else '') + summary_html + '<table><tr><th>Run</th><th>Runtime</th>'
        '<th>Configuration</th><th>Correctness gate</th><th>Median p95 ms</th><th>Evidence</th></tr>' +
        ''.join(rows) + '</table></html>').encode()
    for name in ('README.md', 'ROADMAP.md'):
        content[name] = (ROOT / name).read_bytes()
    for path in (ROOT / 'docs').glob('*.md'):
        content['docs/' + path.name] = path.read_bytes()
        content['project/docs/' + path.name] = content['docs/' + path.name]
    content['SHA256SUMS.json'] = json.dumps(
        {name: hashlib.sha256(data).hexdigest() for name, data in content.items()}, indent=2).encode()
    with zipfile.ZipFile(args.output, 'x', zipfile.ZIP_DEFLATED) as bundle:
        for name, data in content.items():
            bundle.writestr(name, data)
    print(args.output)


if __name__ == '__main__':
    main()
