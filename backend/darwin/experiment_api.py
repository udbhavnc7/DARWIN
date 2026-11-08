import asyncio
import hashlib
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from darwin.experiments import StartExperiment, TERMINAL

router = APIRouter()


def engine(request):
    result = getattr(request.app.state, 'engine', None)
    if result is None:
        raise HTTPException(503, 'Experiment worker is not started')
    return result


def get_record(worker, ident):
    try:
        return worker.store.get(str(ident))
    except KeyError:
        raise HTTPException(404, 'Experiment not found')


@router.post('/api/experiments', status_code=202)
def start(body: StartExperiment, request: Request):
    try:
        return engine(request).submit(body)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))


@router.get('/api/experiments')
def list_runs(request: Request):
    return engine(request).store.all()


@router.get('/api/experiments/{ident}')
def get_run(ident: UUID, request: Request):
    return get_record(engine(request), ident)


@router.post('/api/experiments/{ident}/cancel')
def cancel(ident: UUID, request: Request):
    worker = engine(request)
    get_record(worker, ident)
    return worker.cancel(str(ident))


@router.get('/api/experiments/{ident}/events')
def events(ident: UUID, request: Request, after: int = 0):
    worker = engine(request)
    get_record(worker, ident)
    return worker.store.events(str(ident), after)


@router.get('/api/candidates/{ident}')
def candidate(ident: UUID, request: Request):
    for record in engine(request).store.all():
        for value in record['candidates']:
            if value['candidate_id'] == str(ident):
                return {**value, 'experiment_id': record['experiment_id']}
    raise HTTPException(404, 'Candidate not found')


@router.post('/api/candidates/{ident}/rerun', status_code=202)
def rerun(ident: UUID, request: Request):
    value = candidate(ident, request)
    worker = engine(request)
    original = get_record(worker, value['experiment_id'])
    body = {**original['request'], 'genomes': [value['genome']]}
    try:
        return worker.submit(StartExperiment.model_validate(body), rerun_of=str(ident))
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))


@router.get('/api/experiments/{ident}/artifacts/{evaluation_id}/{name}')
def artifact(ident: UUID, evaluation_id: UUID, name: str, request: Request):
    worker = engine(request)
    record = get_record(worker, ident)
    registered = next((a for c in record['candidates'] for e in c['evaluations'] if e['evaluation_id'] == str(evaluation_id)
                       for a in e['artifacts'] if a['name'] == name), None)
    root = worker.store.root / str(ident) / str(evaluation_id)
    path = (root / name).resolve()
    if not registered or not path.is_relative_to(root.resolve()) or not path.is_file():
        raise HTTPException(404, 'Artifact not found')
    if hashlib.sha256(path.read_bytes()).hexdigest() != registered['sha256']:
        raise HTTPException(409, 'Artifact hash mismatch')
    return FileResponse(path, filename=name)


@router.websocket('/ws/experiments/{ident}')
async def stream(websocket: WebSocket, ident: UUID, after: int = 0):
    worker = getattr(websocket.app.state, 'engine', None)
    if worker is None:
        await websocket.close(code=1013)
        return
    try:
        worker.store.get(str(ident))
    except KeyError:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    try:
        while True:
            for event in worker.store.events(str(ident), after):
                await websocket.send_json(event)
                after = event['sequence']
            if worker.store.get(str(ident))['status'] in TERMINAL:
                for event in worker.store.events(str(ident), after):
                    await websocket.send_json(event)
                    after = event['sequence']
                await websocket.close()
                return
            await asyncio.sleep(.2)
    except WebSocketDisconnect:
        pass
