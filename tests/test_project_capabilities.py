"""Classification must be file-backed and must not turn React into a server."""
import json
from pathlib import Path

from darwin.project_capabilities import inspect_source
from darwin.repository_catalog import SANCHAY_COMMIT


def write(root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def sanchay_tree(root: Path) -> Path:
    write(root, 'web/package.json', json.dumps({
        'scripts': {'dev': 'vite', 'test': 'vitest'},
        'dependencies': {'react': '^19.3.1', 'react-dom': '^19.3.1'},
        'devDependencies': {'vite': '^7.0.0', 'typescript': '^5.6.0', 'vitest': '^3.0.0'},
    }))
    write(root, 'web/src/utils/reporting.ts', '''
export function computeReportTotals() { return {}; }
export function computeCategorySpending() { return new Map(); }
export function computeCategoryBreakdown() { return []; }
export function computePayeeBreakdown() { return []; }
''')
    write(root, 'web/src/utils/money.ts', 'export function addMoney() { return 0; }')
    write(root, 'web/src/utils/categories.ts', 'export const CATEGORIES = [];')
    write(root, 'web/src/types/finance.ts', 'export type Transaction = { id: string };')
    write(root, 'web/src/components/ReportsTab.tsx',
          "export function ReportsTab(){ return computeReportTotals([], 'INR'); }")
    write(root, 'web/src/data/persistence.ts',
          "export const KEY = 'sanchay.local.v1'; localStorage.getItem(KEY);")
    write(root, 'app/src/main/java/com/ivy/wallet/ui/SanchayModernUI.kt',
          'class SanchayModernUI { val view = WebView() }')
    write(root, 'settings.gradle.kts', 'include(":app")')
    return root


def test_sanchay_is_a_local_webview_app_not_a_server(tmp_path):
    root = sanchay_tree(tmp_path)
    result = inspect_source(root, 'https://github.com/udbhavnc7/Sanchay', 'udbhavnc7',
                            'Sanchay', SANCHAY_COMMIT, True)
    assert result['project']['type'] == 'react_webview_local_app'
    assert result['project']['is_server_backend'] is False
    assert 'localStorage' in result['project']['persistence']
    assert result['project']['application_host'] == 'Android WebView shell'
    capabilities = {item['capability'] for item in result['not_supported']}
    assert 'API replica scaling' in capabilities
    assert 'PostgreSQL / cloud failover' in capabilities
    labels = {item['label'] for item in result['facts']}
    assert {'Visible application', 'Host shell', 'Persistence', 'Report code'} <= labels
    adapter = result['supported_evaluations'][0]
    assert adapter['adapter_id'] == 'sanchay-reporting-v1'
    assert adapter['execution_allowed'] is True
    assert adapter['evaluation_type'] == 'client_data_processing'
    assert 'server' in adapter['scope_note'].lower()


def test_unpinned_commit_disables_execution(tmp_path):
    root = sanchay_tree(tmp_path)
    result = inspect_source(root, 'https://github.com/udbhavnc7/Sanchay', 'udbhavnc7',
                            'Sanchay', 'a' * 40, False)
    adapter = result['supported_evaluations'][0]
    assert adapter['execution_allowed'] is False
    assert 'not the audited revision' in adapter['execution_note']


def test_react_application_without_adapter_is_not_called_a_server(tmp_path):
    write(tmp_path, 'web/package.json', json.dumps({
        'dependencies': {'react': '^19.0.0'}, 'devDependencies': {'vite': '^7.0.0'},
    }))
    result = inspect_source(tmp_path, 'https://github.com/example/ui', 'example', 'ui', 'b' * 40, False)
    assert result['project']['type'] == 'client_web_app'
    assert result['project']['is_server_backend'] is False
    assert result['supported_evaluations'] == []
    assert result['evaluation_status'] == 'UNSUPPORTED_PROJECT'


def test_node_server_is_named_only_when_entry_and_framework_exist(tmp_path):
    write(tmp_path, 'package.json', json.dumps({
        'dependencies': {'express': '^5.0.0'}, 'scripts': {'start': 'node server.js'},
    }))
    write(tmp_path, 'server.ts', 'import express from "express";')
    result = inspect_source(tmp_path, 'https://github.com/example/api', 'example', 'api', 'c' * 40, False)
    assert result['project']['type'] == 'node_service'
    assert result['project']['is_server_backend'] is True
    assert result['supported_evaluations'] == []


def test_package_name_alone_does_not_create_a_server(tmp_path):
    write(tmp_path, 'web/package.json', json.dumps({'dependencies': {'react': '^19.0.0'}}))
    write(tmp_path, 'package.json', json.dumps({'dependencies': {'express': '^5.0.0'}}))
    result = inspect_source(tmp_path, 'https://github.com/example/app', 'example', 'app', 'd' * 40, False)
    assert result['project']['is_server_backend'] is False


def test_generic_inspection_exposes_architecture_and_screening(tmp_path):
    write(tmp_path, 'package.json', json.dumps({
        'name': 'small-api', 'dependencies': {'express': '^5.0.0', 'pg': '^8.0.0'},
    }))
    write(tmp_path, 'server.js', '''
const express = require('express');
const app = express();
app.get('/api/health', (req, res) => res.json({ok: true}));
app.get('/api/items', (req, res) => res.json([]));
app.post('/api/items', (req, res) => res.status(201).json({}));
''')
    result = inspect_source(tmp_path, 'https://github.com/example/small-api', 'example',
                            'small-api', 'e' * 40, False)

    assert result['project']['type'] == 'node_service'
    assert result['project']['note']['what_it_is']
    assert result['project']['backend']['route_count'] == 3
    assert result['architecture']['nodes']
    assert any(node['kind'] == 'service' for node in result['architecture']['nodes'])
    assert result['screening']['available'] is True
    assert 'db_pool' in result['screening']['controls']
    assert result['supported_evaluations'] == []
    assert result['evaluation_status'] == 'UNSUPPORTED_PROJECT'


def test_sanchay_keeps_its_measured_adapter_and_generic_screening_is_independent(tmp_path):
    root = sanchay_tree(tmp_path)
    result = inspect_source(root, 'https://github.com/udbhavnc7/Sanchay', 'udbhavnc7',
                            'Sanchay', SANCHAY_COMMIT, True)

    assert result['project']['type'] == 'react_webview_local_app'
    assert result['supported_evaluations'][0]['adapter_id'] == 'sanchay-reporting-v1'
    assert result['evaluation_status'] == 'NOT_MEASURED'
    assert result['project']['note']['what_it_is']
    assert result['project']['backend']['frontend_detected'] is True
    assert result['project']['backend']['services'] == []
    assert result['screening']['available'] is False
    assert result['screening']['controls'] == []
