import os
from itertools import count

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

app = FastAPI(title='DARWIN Shop Gateway')
sequence = count()


@app.get('/health')
def health():
    return {'status': 'ok', 'service': 'gateway'}


@app.api_route('/shop/{path:path}', methods=['GET', 'POST'])
async def proxy(path: str, request: Request):
    if (request.method, path) not in {('GET', 'catalog'), ('POST', 'checkout'), ('GET', 'ready')}:
        return JSONResponse(status_code=404, content={'detail': 'Unknown shop route'})
    headers = {'content-type': 'application/json'}
    if 'idempotency-key' in request.headers:
        headers['idempotency-key'] = request.headers['idempotency-key']
    try:
        targets = os.environ.get('DARWIN_SHOP_API_URLS', os.environ.get('DARWIN_SHOP_API_URL', 'http://127.0.0.1:8013')).split(',')
        target = targets[next(sequence) % len(targets)].strip()
        async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
            response = await client.request(request.method, target + '/' + path,
                                            content=await request.body(), headers=headers)
        return Response(content=response.content, status_code=response.status_code,
                        headers={key: response.headers[key] for key in ('x-darwin-instance', 'x-darwin-cache') if key in response.headers},
                        media_type=response.headers.get('content-type', 'application/json'))
    except httpx.TransportError:
        return JSONResponse(status_code=503, content={'detail': 'Shop unavailable; reuse the same request key when retrying'})
