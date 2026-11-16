"""HTTP surface for Real Project Mode.

Read-only repository inspection is separate from executable evaluation. A public
GitHub repository can be inspected without any approved adapter, but only a
catalogued repository at its pinned commit can start a live evaluation.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
import secrets
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, Field

from darwin.repository_catalog import adapter_catalog
from darwin.repository_evaluations import PRESETS, TERMINAL
from darwin.repository_import import RepositoryError
from darwin.project_simulation import SCREENING_ADAPTER_ID, SCREENING_ADAPTER_VERSION

router = APIRouter()


class InspectRequest(BaseModel):
    url: str = Field(min_length=8, max_length=300)
    ref: str = Field(default='main', min_length=1, max_length=100)
    consent: bool = Field(
        default=False,
        description='The caller explicitly allows DARWIN to download this public source.',
    )


class ManifestValidationRequest(BaseModel):
    adapter_id: str = Field(min_length=1, max_length=100)
    manifest: dict


class EvaluationRequest(BaseModel):
    inspection_id: str = Field(min_length=1, max_length=100)
    adapter_id: str | None = Field(default=None, max_length=100)
    mode: Literal['quick', 'full'] = 'quick'
    challenge: Literal['faster', 'spike', 'resources', 'recover'] = 'faster'
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
        'screening': {
            'adapter_id': SCREENING_ADAPTER_ID,
            'adapter_version': SCREENING_ADAPTER_VERSION,
            'display_name': 'Backend architecture evolution (simulated)',
            'evaluation_type': 'architecture_screening',
            'evidence_kind': 'simulated',
            'label': 'SIMULATED',
            'scope_note': (
                'Models deployment-level architecture variants from inspected source. '
                'No repository code is executed and no runtime is measured.'
            ),
        },
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


@router.post('/api/repositories/validate-manifest')
def validate_manifest(body: ManifestValidationRequest, request: Request):
    """Validate a proposed run manifest against the reviewed, hashed manifest.

    This is a read-only review helper: nothing is written, downloaded or run.
    """
    from darwin.backend_manifest import validate_relative_files

    engine = repositories(request)
    adapter = engine.adapters.get(body.adapter_id)
    if adapter is None or not hasattr(adapter, 'manifest'):
        raise HTTPException(404, 'No reviewed container adapter is installed with that id.')
    expected = adapter.manifest.as_dict()
    submitted = dict(body.manifest)
    digest = submitted.pop('sha256', None)
    errors: list[str] = []
    try:
        computed = hashlib.sha256(
            json.dumps(submitted, sort_keys=True).encode('utf-8')).hexdigest()
    except (TypeError, ValueError):
        computed = ''
        errors.append('The manifest body is not JSON-serialisable.')
    if not digest or digest != computed:
        errors.append('The supplied sha256 does not match the manifest body.')
    if digest and digest != expected.get('sha256'):
        errors.append('The manifest does not match the reviewed adapter manifest.')
    if submitted.get('adapter_id') != body.adapter_id:
        errors.append('The manifest adapter_id does not match the request adapter_id.')
    try:
        validate_relative_files(submitted.get('source_files') or [])
    except (TypeError, ValueError) as exc:
        errors.append(f'Unsafe source path: {exc}')
    if submitted.get('runtime') not in ('gunicorn-flask', 'uvicorn-fastapi', 'node-express'):
        errors.append('The runtime is not supported by this isolated runner.')
    port = submitted.get('app_port')
    if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
        errors.append('app_port must be an integer between 1 and 65535.')
    return {
        'valid': not errors,
        'adapter_id': body.adapter_id,
        'sha256': computed or None,
        'reviewed_sha256': expected.get('sha256'),
        'errors': errors,
    }


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
    adapter_id = body.adapter_id
    screening = inspection_record.get('screening') or {}
    if adapter_id is None:
        supports = inspection_record.get('supported_evaluations') or []
        if supports:
            # A reviewed adapter matches. Let submit() explain the exact
            # prerequisite instead of a generic "nothing available" message.
            adapter_id = supports[0]['adapter_id']
        elif screening.get('available'):
            adapter_id = SCREENING_ADAPTER_ID
    if not adapter_id:
        raise HTTPException(
            409,
            'No approved executable adapter or architecture screening is available for this source.',
        )
    try:
        return _public(engine.submit(body.inspection_id, adapter_id, body.mode,
                                     body.include_source_tests, body.challenge))
    except RepositoryError as exc:
        raise _repository_error(exc)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))


@router.get('/api/repositories/inspections/{ident}/candidates')
def inspection_candidates(ident: str, request: Request):
    """Preview eligible architecture candidates without executing anything."""
    engine = repositories(request)
    try:
        inspection = engine.get_inspection(ident)
    except KeyError:
        raise HTTPException(404, 'Repository inspection not found')
    supports = inspection.get('supported_evaluations') or []
    if not supports:
        return {
            'eligible': False,
            'reason': 'No reviewed executable adapter matches this source.',
            'support_level': inspection.get('support_level', 'INSPECTABLE'),
            'candidates': [],
            'challenges': [],
        }
    support = supports[0]
    adapter = engine.adapters.get(support['adapter_id'])
    if adapter is None:
        raise HTTPException(503, 'That adapter is not installed in this DARWIN build.')
    manifest = adapter.describe(Path(inspection.get('_source_root', '')),
                                inspection['source']['commit_sha'],
                                bool(inspection['source']['trusted']))
    # Client-pipeline adapters declare their abilities on the inspection payload;
    # container adapters expose a capabilities() method on the adapter itself.
    capabilities = (adapter.capabilities() if hasattr(adapter, 'capabilities')
                    else support.get('capabilities') or {})
    return {
        'eligible': bool(inspection.get('execution_allowed')),
        'support_level': inspection.get('support_level'),
        'prerequisites': inspection.get('prerequisites') or [],
        'adapter_id': support['adapter_id'],
        'adapter_version': support['adapter_version'],
        'capabilities': capabilities,
        'challenges': support.get('challenges') or [],
        'unsupported': manifest.get('unsupported') or [],
        'candidates': [
            {
                'candidate_id': item['candidate_id'],
                'label': item['label'],
                'description': item['description'],
                'dimension': {'replicas': item['replicas'], 'workers': item['workers']},
                'challenges': list(item.get('challenges') or []),
            }
            for item in (manifest.get('manifest') or {}).get('candidates') or []
        ],
    }


@router.get('/api/project-evaluations/{ident}/change')
def evaluation_change(ident: str, request: Request):
    """Reviewable deployment change for the recorded verdict, plus rollback notes."""
    engine = repositories(request)
    _evaluation(engine, ident)
    try:
        text = engine.export_change(ident)
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    return PlainTextResponse(text, media_type='text/markdown')


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
