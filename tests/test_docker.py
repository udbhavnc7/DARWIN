import os

import pytest
from fastapi.testclient import TestClient

from darwin.docker_resources import cgroup_counters, check_counter_continuity, docker_environment
from darwin.docker_sandbox import DockerSandbox
from darwin.experiments import StartExperiment
from darwin.main import app
from darwin.search import SearchRequest


@pytest.mark.skipif(os.name != 'nt', reason='Docker Desktop credential helper discovery on Windows')
def test_docker_child_can_find_credential_helper_without_changing_parent_path(tmp_path):
    cli = tmp_path / 'Docker Desktop' / 'bin' / 'docker.exe'
    env = {'PATH': r'C:\Windows\System32', 'PYTHONPATH': 'snapshot'}
    result = docker_environment(str(cli), env)
    assert result['PATH'].split(os.pathsep) == [str(cli.parent), env['PATH']]
    assert result['PYTHONPATH'] == env['PYTHONPATH']
    assert env['PATH'] == r'C:\Windows\System32'


def test_docker_faults_keep_proxies_inside_owned_sandbox(tmp_path):
    request = StartExperiment(mode='docker_faults', fault_scenarios=['timeout_retry_duplicate'],
                              fault_fixture='unsafe_retry',
                              genomes=[{'app_replicas': 3, 'notification_mode': 'queued'}])
    sandbox = DockerSandbox(request, {'genome': request.genomes[0].model_dump()}, tmp_path, tmp_path)
    services = sandbox.config['services']
    assert sandbox.config['networks']['sandbox']['internal']
    assert 'toxiproxy' not in sandbox.app_services
    assert 'darwin.unsafe_payment:app' in services['payment']['command']
    assert '@db:5432/' in services['seed']['environment']['DARWIN_DATABASE_URL']
    for name in ('api-1', 'api-2', 'api-3', 'worker'):
        assert services[name]['networks'] == ['sandbox']
        assert 'ports' not in services[name]
        env = services[name]['environment']
        assert env['DARWIN_INSTANCE_ID'] == name
        assert 'host=toxiproxy' in env['DARWIN_DATABASE_URL']
        assert env['DARWIN_PAYMENT_URL'] == 'http://toxiproxy:18000'
        assert services[name]['volumes'] == services['gateway']['volumes']
    assert {name for name, service in services.items() if service.get('ports')} == {'gateway', 'db', 'toxiproxy'}
    assert all(port['host_ip'] == '127.0.0.1' for service in services.values() for port in service.get('ports', []))


def test_docker_benchmark_does_not_install_fault_fixture(tmp_path):
    request = StartExperiment(mode='docker_benchmark', workload_profile='checkout_heavy')
    sandbox = DockerSandbox(request, {'genome': request.genomes[0].model_dump()}, tmp_path, tmp_path)
    assert 'toxiproxy' not in sandbox.services
    assert 'DARWIN_ISOLATED_FAULT_TEST' not in sandbox.services['payment']['environment']
    assert SearchRequest(runtime='docker').runtime == 'docker'


def test_validate_endpoint_keeps_docker_execution_fields():
    response = TestClient(app).post('/api/experiments/validate', json={
        'mode': 'docker_faults', 'fault_scenarios': ['timeout_retry_duplicate'],
        'fault_fixture': 'unsafe_retry',
    })
    assert response.status_code == 200
    assert response.json()['mode'] == 'docker_faults'
    assert response.json()['fault_fixture'] == 'unsafe_retry'


def test_cgroup_evidence_rejects_missing_or_changed_limits():
    raw = '40000 100000\n402653184\n0\n10485760\nusage_usec 1230000\nuser_usec 1000000'
    assert cgroup_counters(raw, .4, 384 * 2**20) == {'cpu_seconds': 1.23, 'memory_peak_mb': 10}
    for substitute in ('max 100000', '50000 100000'):
        with pytest.raises(RuntimeError, match='CPU limit'):
            cgroup_counters(raw.replace('40000 100000', substitute), .4, 384 * 2**20)
    with pytest.raises(RuntimeError, match='memory or swap'):
        cgroup_counters(raw.replace('402653184\n0', '402653184\nmax'), .4, 384 * 2**20)
    before = {'started': 'a', 'containers': {'id': {'cpu_seconds': 1.23}}}
    with pytest.raises(RuntimeError, match='changed'):
        check_counter_continuity(before, {**before, 'started': 'b'})
