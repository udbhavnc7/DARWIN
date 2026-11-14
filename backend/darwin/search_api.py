from uuid import UUID

from fastapi import APIRouter, HTTPException, Request

from darwin.search import SearchRequest

router = APIRouter()


def manager(request):
    worker = getattr(request.app.state, 'search', None)
    if worker is None:
        raise HTTPException(503, 'Search worker is not started')
    return worker


def record(request, ident):
    try:
        return manager(request).store.get(str(ident))
    except KeyError:
        raise HTTPException(404, 'Search not found')


@router.post('/api/searches', status_code=202)
def start_search(body: SearchRequest, request: Request):
    try:
        return manager(request).submit(body)
    except RuntimeError as exc:
        raise HTTPException(409, str(exc))


@router.get('/api/searches')
def list_searches(request: Request):
    return manager(request).store.all()


@router.get('/api/searches/{ident}')
def get_search(ident: UUID, request: Request):
    return record(request, ident)


@router.get('/api/searches/{ident}/events')
def search_events(ident: UUID, request: Request, after: int = 0):
    record(request, ident)
    return manager(request).store.events(str(ident), after)


@router.post('/api/searches/{ident}/cancel')
def cancel_search(ident: UUID, request: Request):
    record(request, ident)
    return manager(request).cancel(str(ident))


@router.post('/api/searches/{ident}/rerun', status_code=202)
def rerun_search(ident: UUID, request: Request):
    previous = record(request, ident)
    return start_search(SearchRequest.model_validate(previous['request']), request)
