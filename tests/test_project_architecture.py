"""Generic source inspection must stay file-backed, scoped and read-only."""
import json
from pathlib import Path

from darwin.project_architecture import analyse_repository
from darwin.project_capabilities import inspect_source
from darwin.project_simulation import screen_repository


def write(root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def express_tree(root: Path) -> Path:
    write(root, 'package.json', json.dumps({
        'name': 'small-api',
        'scripts': {'start': 'node server.js'},
        'dependencies': {'express': '^5.0.0', 'pg': '^8.0.0'},
    }))
    write(root, 'server.js', '''
import express from 'express';
const app = express();
app.get('/api/health', (req, res) => res.json({ok: true}));
app.get('/api/items', (req, res) => res.json([]));
app.post('/api/items', (req, res) => res.status(201).json({}));
''')
    return root


def next_tree(root: Path) -> Path:
    write(root, 'package.json', json.dumps({
        'name': 'small-next-app',
        'dependencies': {'next': '^15.0.0', 'react': '^19.0.0', 'react-dom': '^19.0.0'},
    }))
    write(root, 'app/page.tsx', 'export default function Page() { return null; }')
    write(root, 'app/api/health/route.ts',
          'export async function GET() { return Response.json({ok: true}); }')
    write(root, 'app/api/items/route.ts',
          'export async function GET() { return Response.json([]); }\n'
          'export async function POST() { return Response.json({}, {status: 201}); }')
    return root


def test_express_service_routes_and_screening_are_file_backed(tmp_path):
    result = analyse_repository(express_tree(tmp_path))
    project = result['project']
    backend = project['backend']

    assert project['type'] == 'node_service'
    assert project['is_server_backend'] is True
    assert [service['framework'] for service in backend['services']] == ['Express']
    assert backend['route_count'] == 3
    assert {route['method'] for route in backend['routes']} == {'GET', 'POST'}
    assert {route['file'] for route in backend['routes']} == {'server.js'}
    assert any(store['name'] == 'PostgreSQL' for store in backend['datastores'])
    assert result['screening']['available'] is True
    assert 'db_pool' in result['screening']['controls']
    assert any(fact['label'] == 'HTTP routes' and fact['value'].startswith('3 ')
               for fact in result['facts'])


def test_nextjs_file_routes_are_not_method_inflated(tmp_path):
    result = analyse_repository(next_tree(tmp_path))
    routes = result['project']['backend']['routes']

    assert result['project']['type'] == 'node_service'
    assert len(routes) == 3
    assert sorted((route['path'], route['method']) for route in routes) == [
        ('/api/health', 'GET'),
        ('/api/items', 'GET'),
        ('/api/items', 'POST'),
    ]
    assert all(route['snippet'] == 'Next.js route handler' for route in routes)


def test_client_only_react_app_has_no_backend_or_screening(tmp_path):
    write(tmp_path, 'package.json', json.dumps({
        'name': 'ui', 'dependencies': {'react': '^19.0.0', 'react-dom': '^19.0.0'},
        'devDependencies': {'vite': '^7.0.0'},
    }))
    write(tmp_path, 'src/App.tsx', 'export function App() { return null; }')

    result = analyse_repository(tmp_path)

    assert result['project']['type'] == 'client_web_app'
    assert result['project']['is_server_backend'] is False
    assert result['project']['backend']['route_count'] == 0
    assert result['screening']['available'] is False
    assert 'No backend service' in result['screening']['reason']


def test_dependency_name_alone_is_not_a_service(tmp_path):
    write(tmp_path, 'package.json', json.dumps({
        'name': 'not-a-server',
        'dependencies': {'express': '^5.0.0', 'pg': '^8.0.0'},
    }))
    write(tmp_path, 'src/theme.ts', 'export const theme = "light";')

    result = analyse_repository(tmp_path)

    assert result['project']['type'] == 'library'
    assert result['project']['backend']['detected'] is False
    assert result['project']['backend']['services'] == []
    assert result['screening']['available'] is False


def test_inspection_never_executes_package_scripts_or_repository_code(tmp_path):
    root = express_tree(tmp_path)
    marker = tmp_path / 'EXECUTED'
    write(root, 'package.json', json.dumps({
        'name': 'small-api',
        'scripts': {
            'start': 'node server.js',
            'postinstall': 'node -e "require(\'fs\').writeFileSync(\'EXECUTED\', \'yes\')"',
        },
        'dependencies': {'express': '^5.0.0', 'pg': '^8.0.0'},
    }))

    result = inspect_source(root, 'https://github.com/example/small-api', 'example',
                            'small-api', 'e' * 40, False)
    screening = screen_repository(result, 'quick')

    assert marker.exists() is False
    assert screening['label'] == 'SIMULATED'
    assert screening['verdict']['status'] == 'NOT_MEASURED'
