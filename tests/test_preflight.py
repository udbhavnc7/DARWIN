from darwin import preflight


def test_preflight_reports_missing_tools_without_raising(tmp_path, monkeypatch):
    monkeypatch.setattr(preflight.shutil, 'which', lambda command: None)
    monkeypatch.setattr(preflight, 'docker_status', lambda: None)
    monkeypatch.setattr(preflight, '_tcp', lambda host, port, timeout=0.25: False)
    snapshot = preflight.collect_preflight(tmp_path, refresh=True)
    checks = {check['id']: check for check in snapshot['checks']}
    assert checks['python']['status'] == 'ready'
    assert checks['node']['status'] == 'missing'
    assert checks['postgres']['remedy']
    assert checks['docker']['status'] == 'optional_missing'
    assert snapshot['ready'] is False
    assert 'native_smoke' in snapshot['execution_modes']
    assert snapshot['capabilities']['smoke'] is True


def test_preflight_marks_required_tools_ready(tmp_path, monkeypatch):
    monkeypatch.setattr(preflight.shutil, 'which', lambda command: f'/fake/{command}')
    monkeypatch.setattr(preflight, '_command', lambda args, timeout=3.0: 'v1.0')
    monkeypatch.setattr(preflight, 'docker_status', lambda: '2')
    monkeypatch.setattr(preflight, '_tcp', lambda host, port, timeout=0.25: True)
    snapshot = preflight.collect_preflight(tmp_path, refresh=True)
    checks = {check['id']: check for check in snapshot['checks']}
    assert snapshot['ready'] is True
    assert checks['docker']['status'] == 'ready'
    assert snapshot['capabilities']['docker'] is True


def test_preflight_cache_can_be_refreshed(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(preflight, '_execution_modes', lambda: calls.append(1) or ['native_smoke'])
    monkeypatch.setattr(preflight.shutil, 'which', lambda command: f'/fake/{command}')
    monkeypatch.setattr(preflight, '_command', lambda args, timeout=3.0: 'v1.0')
    monkeypatch.setattr(preflight, 'docker_status', lambda: None)
    monkeypatch.setattr(preflight, '_tcp', lambda host, port, timeout=0.25: True)
    first = preflight.collect_preflight(tmp_path, refresh=True)
    second = preflight.collect_preflight(tmp_path)
    preflight.collect_preflight(tmp_path, refresh=True)
    assert first == second
    assert len(calls) == 2
