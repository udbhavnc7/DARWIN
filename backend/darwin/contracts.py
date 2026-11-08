"""Version-one contracts. Execution and persistence arrive in later phases."""
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator, field_validator

NonNegative = Annotated[float, Field(ge=0, allow_inf_nan=False)]
Status = Literal["queued", "running", "completed", "failed", "cancelled"]
Workload = Literal["normal", "flash_sale", "checkout_heavy"]
Fault = Literal["db_delay", "service_outage", "timeout_retry_duplicate"]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1


class Genome(Contract):
    app_replicas: Literal[1, 2, 3] = 1
    catalog_cache_ttl_s: Literal[0, 10, 30] = 0
    notification_mode: Literal["sync", "queued"] = "sync"
    retry_policy: Literal["none", "idempotent_only"] = "idempotent_only"

    @field_validator('app_replicas', 'catalog_cache_ttl_s', mode='before')
    @classmethod
    def integer_controls(cls, value):
        if type(value) is not int:
            raise ValueError('Numeric genome controls must be integers')
        return value


class Budget(Contract):
    max_candidates: int = Field(default=12, ge=1, le=200)
    real_test_budget: int = Field(default=6, ge=1, le=100)
    repetitions: int = Field(default=3, ge=3, le=10)
    wall_clock_s: int = Field(default=900, ge=60, le=14400)
    concurrent_deployments: Literal[1] = 1
    sandbox_cpu_cores: float = Field(default=4, gt=0, le=8, allow_inf_nan=False)
    sandbox_memory_mb: int = Field(default=4096, ge=512, le=8192)

    @model_validator(mode="after")
    def sufficient_repetitions(self):
        if self.real_test_budget < self.repetitions:
            raise ValueError("real_test_budget must cover one full repetition group")
        return self


class Constraints(Contract):
    max_error_rate: float = Field(default=0.01, ge=0, le=1, allow_inf_nan=False)
    max_p95_ms: Annotated[float, Field(gt=0, allow_inf_nan=False)] | None = None


class ExperimentRequest(Contract):
    project_id: Literal["shop-demo"] = "shop-demo"
    workload_profile: Workload = "normal"
    fault_scenarios: list[Fault] = Field(default_factory=list)
    seed: int = Field(default=42, ge=0, le=2**32 - 1)
    budget: Budget = Field(default_factory=Budget)
    constraints: Constraints = Field(default_factory=Constraints)


class Experiment(Contract):
    experiment_id: UUID
    request: ExperimentRequest
    status: Status = "queued"
    created_at: AwareDatetime


class Candidate(Contract):
    candidate_id: UUID
    experiment_id: UUID
    genome: Genome
    genome_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    parent_ids: list[UUID] = Field(default_factory=list)
    generation: int = Field(ge=0)


class Metrics(Contract):
    p50_ms: NonNegative
    p95_ms: NonNegative
    p99_ms: NonNegative
    requests_per_s: NonNegative
    error_rate: float = Field(ge=0, le=1, allow_inf_nan=False)
    cpu_seconds: NonNegative
    memory_peak_mb: NonNegative
    recovery_s: NonNegative | None = None
    sample_count: int = Field(gt=0)

    @model_validator(mode="after")
    def ordered_percentiles(self):
        if not self.p50_ms <= self.p95_ms <= self.p99_ms:
            raise ValueError("latency percentiles must be ordered")
        return self


class Violation(Contract):
    invariant_id: Literal["I-01", "I-02", "I-03", "I-04", "I-05"]
    candidate_id: UUID
    trace_artifact_id: UUID
    summary: str = Field(min_length=1)
    reproduced: bool = False


class Evaluation(Contract):
    evaluation_id: UUID
    candidate_id: UUID
    tier: Literal["simulated", "measured"]
    seed: int = Field(ge=0)
    repetition: int = Field(ge=0)
    status: Status
    source_revision: str = Field(min_length=1)
    metrics: Metrics | None = None
    gate: Literal["not_checked", "passed", "failed"] = "not_checked"
    violations: list[Violation] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_gate(self):
        if self.tier == "simulated" and self.gate != "not_checked":
            raise ValueError("simulation cannot certify feasibility")
        if self.gate == "passed" and (
            self.status != "completed" or self.metrics is None or self.violations
        ):
            raise ValueError("passing requires completed measured evidence and no violations")
        return self


class Artifact(Contract):
    artifact_id: UUID
    evaluation_id: UUID
    relative_path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    kind: Literal["manifest", "metrics", "trace", "compose", "log"]
    created_at: AwareDatetime


class Event(Contract):
    experiment_id: UUID
    sequence: int = Field(ge=1)
    occurred_at: AwareDatetime
    type: Literal["experiment_status", "candidate_status", "evaluation_status"]
    status: Status
    candidate_id: UUID | None = None
    evaluation_id: UUID | None = None
    message: str

