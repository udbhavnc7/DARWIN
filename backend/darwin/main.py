from fastapi import FastAPI, Request, Response
from contextlib import asynccontextmanager
import os
from pathlib import Path
from pydantic import Field
import yaml
from darwin.experiments import Engine, StartExperiment
from darwin.experiment_api import router
from darwin.contracts import Budget, Contract, ExperimentRequest, Genome, Workload
from darwin.architecture import genome_hash, render_compose, topology
from darwin.calibration import calibrated_simulation
from darwin.docker_resources import docker_status
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


@app.get("/api/health")
def health():
    return {"status": "ok", "project": "DARWIN", "phase": 10}


@app.get("/api/project")
def project():
    modes = ['native_smoke']
    if os.name == 'nt':
        modes.extend(['native_benchmark', 'native_faults'])
    cgroups = docker_status()
    if cgroups:
        modes.append('docker_smoke')
    if cgroups == '2':
        modes.extend(['docker_benchmark', 'docker_faults'])
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

