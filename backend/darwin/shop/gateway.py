import os
from itertools import count

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

SHOWCASE_ORIGINS = ('https://udbhavnc7.github.io', 'http://127.0.0.1:4173', 'http://localhost:4173')

app = FastAPI(title='DARWIN Shop Gateway')
app.add_middleware(CORSMiddleware, allow_origins=list(SHOWCASE_ORIGINS),
                   allow_methods=['*'], allow_headers=['*'], expose_headers=['*'],
                   allow_private_network=True)
sequence = count()


@app.get('/health')
def health():
    return {'status': 'ok', 'service': 'gateway'}


@app.api_route('/shop/{path:path}', methods=['GET', 'POST'])
async def proxy(path: str, request: Request):
    if (request.method, path) not in {('GET', 'catalog'), ('POST', 'checkout'), ('GET', 'ready'),
                                      ('GET', 'ledger'), ('POST', 'reset')}:
        return JSONResponse(status_code=404, content={'detail': 'Unknown shop route'})
    headers = {'content-type': 'application/json'}
    if 'idempotency-key' in request.headers:
        headers['idempotency-key'] = request.headers['idempotency-key']
    query = f'?{request.url.query}' if request.url.query else ''
    try:
        targets = os.environ.get('DARWIN_SHOP_API_URLS', os.environ.get('DARWIN_SHOP_API_URL', 'http://127.0.0.1:8013')).split(',')
        target = targets[next(sequence) % len(targets)].strip()
        async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
            response = await client.request(request.method, target + '/' + path + query,
                                            content=await request.body(), headers=headers)
        return Response(content=response.content, status_code=response.status_code,
                        headers={key: response.headers[key] for key in ('x-darwin-instance', 'x-darwin-cache') if key in response.headers},
                        media_type=response.headers.get('content-type', 'application/json'))
    except httpx.TransportError:
        return JSONResponse(status_code=503, content={'detail': 'Shop unavailable; reuse the same request key when retrying'})
