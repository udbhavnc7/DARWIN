from fastapi import FastAPI
from contextlib import asynccontextmanager
import os
from darwin.experiments import Engine, StartExperiment
from darwin.experiment_api import router
from darwin.contracts import Budget, ExperimentRequest, Genome
from darwin.architecture import genome_hash, topology

@asynccontextmanager
async def lifespan(app):
    app.state.engine = Engine(os.environ.get('DARWIN_EXPERIMENT_DIR', 'artifacts/experiments'))
    yield
    app.state.engine.close()


app = FastAPI(title="DARWIN API", version="0.5.0", description="Phase 5 performance measurements", lifespan=lifespan)
app.include_router(router)


@app.get("/api/health")
def health():
    return {"status": "ok", "project": "DARWIN", "phase": 5}


@app.get("/api/project")
def project():
    return {
        "name": "DARWIN",
        "description": "Evolve backend configurations. Verify every improvement.",
        "phase": 5,
        "execution_available": True,
        "execution_modes": ["native_smoke", "docker_smoke"] + (["native_benchmark"] if os.name == "nt" else []),
        "benchmarking_available": os.name == "nt",
        "baseline": Genome().model_dump(),
        "budget": Budget().model_dump(),
        "workloads": ["normal", "flash_sale", "checkout_heavy"],
    }


@app.post("/api/experiments/validate", response_model=ExperimentRequest | StartExperiment)
def validate_request(request: ExperimentRequest | StartExperiment):
    """Validate a proposed request without starting or storing an experiment."""
    return request


@app.post('/api/genomes/preview')
def preview_genome(genome: Genome):
    return {'genome': genome.model_dump(), 'genome_hash': genome_hash(genome), 'topology': topology(genome)}

