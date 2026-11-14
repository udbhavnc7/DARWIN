from fastapi import FastAPI, HTTPException, Request, Response
from contextlib import asynccontextmanager
import os
from pathlib import Path
import secrets
from typing import Literal
from fastapi.responses import JSONResponse
from pydantic import Field
import yaml
from darwin.experiments import Engine, StartExperiment
from darwin.experiment_api import router
from darwin.contracts import Budget, Contract, ExperimentRequest, Genome, Workload
from darwin.architecture import genome_hash, render_compose, topology
from darwin.calibration import calibrated_simulation
from darwin.docker_resources import docker_status
from darwin.exhibition import scenario_catalog, scenario_request
from darwin.preflight import collect_preflight
from darwin.search import SearchEngine
from darwin.search_api import router as search_router

@asynccontextmanager
async def lifespan(app):
    app.state.engine = Engine(os.environ.get('DARWIN_EXPERIMENT_DIR', 'artifacts/experiments'))
    try:
        app.state.search = SearchEngine(app.state.engine)
        try:
            yield
        finally:
            app.state.search.close()
    finally:
        app.state.engine.close()


app = FastAPI(title="DARWIN API", version="0.10.0", description="Measured architecture search and correctness verification", lifespan=lifespan)
app.include_router(router)
app.include_router(search_router)


@app.middleware('http')
async def require_api_token(request: Request, call_next):
    """Optional shared-token guard for deployments that are not local-only.

    Local use stays unauthenticated and bound to 127.0.0.1. Setting
    DARWIN_API_TOKEN requires a bearer token on every /api route except the
    health probe, so the dashboard can sit behind a proxy that injects it.
    """
    token = os.environ.get('DARWIN_API_TOKEN')
    path = request.url.path
    if not token or not path.startswith('/api') or path == '/api/health':
        return await call_next(request)
    header = request.headers.get('authorization', '')
    supplied = header[7:].strip() if header.lower().startswith('bearer ') \
        else request.headers.get('x-darwin-token', '').strip()
    if not supplied or not secrets.compare_digest(supplied.encode(), token.encode()):
        return JSONResponse({'detail': 'A valid API token is required.'}, status_code=401,
                            headers={'WWW-Authenticate': 'Bearer'})
    return await call_next(request)


@app.get("/api/health")
def health():
    return {"status": "ok", "project": "DARWIN", "phase": 10}


def execution_modes():
    modes = ['native_smoke']
    if os.name == 'nt':
        modes.extend(['native_benchmark', 'native_faults'])
    cgroups = docker_status()
    if cgroups:
        modes.append('docker_smoke')
    if cgroups == '2':
        modes.extend(['docker_benchmark', 'docker_faults'])
    return modes


@app.get("/api/project")
def project():
    modes = execution_modes()
    return {
        "name": "DARWIN",
        "description": "Evolve backend configurations. Verify every improvement.",
        "phase": 10,
        "execution_available": True,
        "execution_modes": modes,
        "benchmarking_available": any(mode.endswith('_benchmark') for mode in modes),
        "baseline": Genome().model_dump(),
        "budget": Budget().model_dump(),
        "workloads": ["normal", "flash_sale", "checkout_heavy"],
    }


@app.get("/api/preflight")
def preflight(request: Request, refresh: bool = False):
    """Report what this machine can run before a visitor starts a demo."""
    engine = getattr(request.app.state, 'engine', None)
    root = engine.store.root if engine else Path(os.environ.get('DARWIN_EXPERIMENT_DIR', 'artifacts/experiments'))
    return collect_preflight(root, refresh)


@app.get('/api/exhibition/scenarios')
def exhibition_scenarios(request: Request, runtime: Literal['native', 'docker'] = 'native'):
    """List judge-facing presets and the recorded evidence that backs them."""
    engine = getattr(request.app.state, 'engine', None)
    if engine is None:
        raise HTTPException(503, 'Experiment store is not ready')
    search = getattr(request.app.state, 'search', None)
    searches = search.store.all() if search else []
    return scenario_catalog(engine.store.all(), runtime, searches, execution_modes())


@app.post('/api/exhibition/scenarios/{ident}', status_code=202)
def start_exhibition_scenario(ident: str, request: Request, runtime: Literal['native', 'docker'] = 'native'):
    """Start a preset through the same measured engine as a manual experiment."""
    try:
        body = scenario_request(ident, runtime)
    except KeyError:
        raise HTTPException(404, 'Scenario not found')
    engine = getattr(request.app.state, 'engine', None)
    if engine is None:
        raise HTTPException(503, 'Experiment worker is not started')
    try:
        return engine.submit(body)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))


class SimulationRequest(Contract):
    genome: Genome = Field(default_factory=Genome)
    workload_profile: Workload = 'normal'
    seed: int = Field(default=42, ge=0, le=2**32 - 1)
    duration_s: int = Field(default=60, ge=1, le=3600)
    database_delay_ms: float = Field(default=0, ge=0, le=10_000, allow_inf_nan=False)


@app.post('/api/simulate')
def run_simulation(body: SimulationRequest, request: Request):
    """Estimate performance for screening."""
    engine = getattr(request.app.state, 'engine', None)
    root = engine.store.root if engine else Path(os.environ.get('DARWIN_EXPERIMENT_DIR', 'artifacts/experiments'))
    return calibrated_simulation(root, body.genome, body.workload_profile, body.seed,
                                 body.duration_s, body.database_delay_ms)


@app.post("/api/experiments/validate", response_model=StartExperiment | ExperimentRequest)
def validate_request(request: ExperimentRequest | StartExperiment):
    """Validate a proposed request without starting or storing an experiment."""
    return request


@app.post('/api/genomes/preview')
def preview_genome(genome: Genome):
    return {'genome': genome.model_dump(), 'genome_hash': genome_hash(genome), 'topology': topology(genome)}


@app.post('/api/genomes/compose')
def download_compose(genome: Genome):
    """Export a configuration that builds from the DARWIN project directory."""
    filename = f'darwin-{genome_hash(genome)[:12]}.compose.yaml'
    return Response(yaml.safe_dump(render_compose(genome, build_context='.'), sort_keys=False),
                    media_type='application/yaml', headers={'Content-Disposition': f'attachment; filename="{filename}"'})

