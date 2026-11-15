"""HTTP surface for Real Project Mode.

Read-only repository inspection is separate from executable evaluation. A public
GitHub repository can be inspected without any approved adapter, but only a
catalogued repository at its pinned commit can start a live evaluation.
"""
from __future__ import annotations

import asyncio
import os
import secrets
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, Field

from darwin.repository_catalog import adapter_catalog
from darwin.repository_evaluations import PRESETS, TERMINAL
from darwin.repository_import import RepositoryError

router = APIRouter()


class InspectRequest(BaseModel):
    url: str = Field(min_length=8, max_length=300)
    ref: str = Field(default='main', min_length=1, max_length=100)
    consent: bool = Field(
        default=False,
        description='The caller explicitly allows DARWIN to download this public source.',
    )


class EvaluationRequest(BaseModel):
    inspection_id: str = Field(min_length=1, max_length=100)
    adapter_id: str | None = Field(default=None, max_length=100)
    mode: Literal['quick', 'full'] = 'quick'
    include_source_tests: bool | None = None


def repositories(request: Request):
    engine = getattr(request.app.state, 'repositories', None)
    if engine is None:
        raise HTTPException(503, 'The repository worker is not started')
    return engine


def _not_found() -> HTTPException:
    return HTTPException(404, 'Project evaluation not found')


def _public(value):
    if isinstance(value, dict):
        return {key: _public(item) for key, item in value.items() if not key.startswith('_')}
    if isinstance(value, list):
        return [_public(item) for item in value]
    return value


def _repository_error(exc: RepositoryError) -> HTTPException:
    return HTTPException(
        exc.status_code,
        str(exc),
        headers={'X-DARWIN-Error': exc.code},
    )


def _evaluation(engine, ident: str) -> dict:
    try:
        return engine.get_evaluation(ident)
    except KeyError:
        raise _not_found()


@router.get('/api/repositories/catalog')
def catalog():
    """Trusted examples plus the inspection/execution boundary."""
    return {
        **adapter_catalog(),
        'presets': {
            key: {
                'seeds': list(value['seeds']),
                'sizes': list(value['sizes']),
                'repetitions': value['repetitions'],
                'warmups': value['warmups'],
                'include_source_tests': value['include_source_tests'],
            }
            for key, value in PRESETS.items()
        },
    }


@router.post('/api/repositories/inspect')
def inspect(body: InspectRequest, request: Request):
    """Pin and download a public GitHub repository read-only, then classify it."""
    try:
        return _public(repositories(request).inspect(body.url, body.ref, body.consent))
    except RepositoryError as exc:
        raise _repository_error(exc)


@router.get('/api/repositories/inspections')
def inspections(request: Request):
    return _public(repositories(request).store.all_inspections())


@router.get('/api/repositories/inspections/{ident}')
def inspection(ident: str, request: Request):
    try:
        return _public(repositories(request).get_inspection(ident))
    except KeyError:
        raise HTTPException(404, 'Repository inspection not found')


@router.post('/api/project-evaluations', status_code=202)
def start_evaluation(body: EvaluationRequest, request: Request):
    engine = repositories(request)
    inspection_record = None
    try:
        inspection_record = engine.get_inspection(body.inspection_id)
    except KeyError:
        raise HTTPException(404, 'Repository inspection not found')
    adapter_id = body.adapter_id or next(
        (item['adapter_id'] for item in inspection_record.get('supported_evaluations', [])),
        None,
    )
    if not adapter_id:
        raise HTTPException(409, 'No approved executable adapter is available for this source.')
    try:
        return _public(engine.submit(body.inspection_id, adapter_id, body.mode,
                                     body.include_source_tests))
    except RepositoryError as exc:
        raise _repository_error(exc)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))


@router.get('/api/project-evaluations')
def evaluations(request: Request):
    return _public(repositories(request).list_evaluations())


@router.get('/api/project-evaluations/{ident}')
def evaluation(ident: str, request: Request):
    return _public(_evaluation(repositories(request), ident))


@router.post('/api/project-evaluations/{ident}/cancel')
def cancel_evaluation(ident: str, request: Request):
    engine = repositories(request)
    _evaluation(engine, ident)
    return _public(engine.cancel(ident))


@router.get('/api/project-evaluations/{ident}/events')
def evaluation_events(ident: str, request: Request, after: int = 0):
    engine = repositories(request)
    _evaluation(engine, ident)
    return engine.events(ident, max(0, after))


@router.get('/api/project-evaluations/{ident}/artifacts/{name}')
def evaluation_artifact(ident: str, name: str, request: Request):
    engine = repositories(request)
    _evaluation(engine, ident)
    try:
        path = engine.evidence_path(ident, name)
    except (KeyError, OSError):
        raise HTTPException(404, 'That evidence file is not registered for this evaluation')
    return FileResponse(path, filename=name)


@router.get('/api/project-evaluations/{ident}/diff')
def evaluation_diff(ident: str, request: Request):
    engine = repositories(request)
    _evaluation(engine, ident)
    try:
        path = engine.evidence_path(ident, 'candidate.diff')
    except (KeyError, OSError):
        raise HTTPException(404, 'No candidate diff was recorded')
    return PlainTextResponse(path.read_text(encoding='utf-8', errors='replace'),
                             media_type='text/x-diff')


@router.get('/api/project-evaluations/{ident}/bundle')
def evaluation_bundle(ident: str, request: Request):
    engine = repositories(request)
    _evaluation(engine, ident)
    try:
        path = engine.bundle(ident)
    except KeyError:
        raise HTTPException(404, 'No evidence bundle is available')
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    return FileResponse(path, media_type='application/zip',
                        filename=f'darwin-project-evidence-{ident}.zip')


def token_guard(websocket: WebSocket) -> bool:
    """Match the HTTP token guard so event streams are not an anonymous bypass."""
    token = os.environ.get('DARWIN_API_TOKEN')
    if not token:
        return True
    header = websocket.headers.get('authorization', '')
    supplied = header[7:].strip() if header.lower().startswith('bearer ') \
        else websocket.headers.get('x-darwin-token', '').strip()
    return bool(supplied) and secrets.compare_digest(supplied.encode(), token.encode())


@router.websocket('/ws/project-evaluations/{ident}')
async def stream(websocket: WebSocket, ident: str, after: int = 0):
    if not token_guard(websocket):
        await websocket.close(code=1008)
        return
    engine = getattr(websocket.app.state, 'repositories', None)
    if engine is None:
        await websocket.close(code=1013)
        return
    try:
        engine.get_evaluation(ident)
    except KeyError:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    try:
        while True:
            for event in engine.events(ident, after):
                await websocket.send_json(event)
                after = event['sequence']
            if engine.get_evaluation(ident)['status'] in TERMINAL:
                for event in engine.events(ident, after):
                    await websocket.send_json(event)
                await websocket.close()
                return
            await asyncio.sleep(.25)
    except WebSocketDisconnect:
        pass
