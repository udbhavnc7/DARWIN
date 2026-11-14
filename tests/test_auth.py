"""The optional token guard must never weaken the default local-only setup."""
from fastapi.testclient import TestClient
import pytest
from starlette.websockets import WebSocketDisconnect

from darwin.main import app

client = TestClient(app)


def test_local_requests_stay_open_when_no_token_is_configured(monkeypatch):
    monkeypatch.delenv('DARWIN_API_TOKEN', raising=False)
    assert client.get('/api/health').status_code == 200
    assert client.get('/api/project').status_code == 200


def test_configured_token_guards_api_but_not_health(monkeypatch):
    monkeypatch.setenv('DARWIN_API_TOKEN', 'demo-token')
    assert client.get('/api/health').status_code == 200
    assert client.get('/api/project').status_code == 401
    assert client.get('/api/preflight').status_code == 401
    assert client.get('/api/project', headers={'Authorization': 'Bearer wrong'}).status_code == 401
    assert client.get('/api/project', headers={'Authorization': 'Bearer demo-token'}).status_code == 200
    assert client.get('/api/project', headers={'X-DARWIN-Token': 'demo-token'}).status_code == 200


def test_non_api_routes_are_not_guarded(monkeypatch):
    monkeypatch.setenv('DARWIN_API_TOKEN', 'demo-token')
    assert client.get('/docs').status_code == 200


def test_configured_token_guards_experiment_websockets(monkeypatch):
    monkeypatch.setenv('DARWIN_API_TOKEN', 'demo-token')
    path = '/ws/experiments/00000000-0000-0000-0000-000000000000'
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(path) as socket:
            socket.receive_json()
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(path, headers={'Authorization': 'Bearer wrong'}) as socket:
            socket.receive_json()
