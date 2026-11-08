from contextlib import asynccontextmanager
import logging
import threading
import time

import psycopg
from fastapi import FastAPI, HTTPException

from darwin.shop.db import connection
from darwin.shop.services import deliver_notification


def drain_batch():
    with connection() as conn:
        jobs = conn.execute("SELECT job_key FROM outbox WHERE status='pending' ORDER BY job_key LIMIT 100").fetchall()
    for job in jobs:
        deliver_notification(job['job_key'])
    return len(jobs)


@asynccontextmanager
async def lifespan(app):
    stop = threading.Event()
    app.state.last_success = 0
    def run():
        while not stop.is_set():
            try:
                drain_batch()
                app.state.last_success = time.monotonic()
            except psycopg.Error:
                logging.exception('Notification drain failed; unacknowledged jobs remain pending')
            stop.wait(0.25)
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    yield
    stop.set()
    thread.join(timeout=5)


app = FastAPI(title='DARWIN notification worker', lifespan=lifespan)


@app.get('/ready')
@app.get('/health')
def ready():
    if time.monotonic() - app.state.last_success > 5:
        raise HTTPException(503, 'Worker has not completed a recent database poll')
    return {'status': 'ready', 'service': 'notification-worker'}
