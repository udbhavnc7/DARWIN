"""Typed adapter boundary for Real Project Mode.

An adapter declares what kind of system it evaluates and must never silently
replace an unsupported project with a different application. The concrete
implementations return plain dictionaries that are persisted as evidence.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


class AdapterError(RuntimeError):
    """An actionable adapter failure that must become an honest verdict."""

    def __init__(self, message: str, code: str = 'adapter_failed',
                 verdict: str = 'FAILED_INFRASTRUCTURE'):
        super().__init__(message)
        self.code = code
        self.verdict = verdict


class AdapterCancelled(RuntimeError):
    """Raised when the operator cancels an evaluation; no metrics are fabricated."""


@dataclass(frozen=True)
class SupportAssessment:
    adapter_id: str
    adapter_version: str
    supported: bool
    evaluation_type: str
    reason: str
    evidence: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class EvaluationBudget:
    mode: str
    seeds: tuple[int, ...]
    sizes: tuple[int, ...]
    repetitions: int
    warmups: int
    wall_clock_s: int
    include_source_tests: bool = False
    challenge: str = 'faster'
    search_mode: str = 'compare'
    warmup_s: int = 2
    window_s: int = 6

    def as_dict(self) -> dict:
        return {
            'mode': self.mode,
            'seeds': list(self.seeds),
            'sizes': list(self.sizes),
            'repetitions': self.repetitions,
            'warmups': self.warmups,
            'wall_clock_s': self.wall_clock_s,
            'include_source_tests': self.include_source_tests,
            'challenge': self.challenge,
            'search_mode': self.search_mode,
            'warmup_s': self.warmup_s,
            'window_s': self.window_s,
        }


@dataclass
class PreparedEvaluation:
    work_dir: Path
    source_root: Path
    harness_dir: Path
    fixtures: list[dict]
    config_path: Path
    candidate_diff: Path
    candidate_files: list[str]
    checks: list[dict]


@dataclass
class Candidate:
    candidate_id: str
    label: str
    description: str
    diff_path: Path
    files: list[str]
    wiring: dict


class ProjectAdapter(Protocol):
    id: str
    version: str
    evaluation_type: str

    def detect(self, source_root: Path, commit_sha: str, pinned: bool) -> SupportAssessment: ...

    def describe(self, source_root: Path, commit_sha: str, pinned: bool) -> dict: ...

    def prepare(self, source_root: Path, work_dir: Path,
                budget: EvaluationBudget) -> PreparedEvaluation: ...

    def candidates(self, prepared: PreparedEvaluation) -> list[Candidate]: ...

    def measure(self, prepared: PreparedEvaluation, candidate: Candidate,
                budget: EvaluationBudget, check) -> dict: ...

    def verify(self, prepared: PreparedEvaluation, candidate: Candidate,
               measurements: dict) -> dict: ...

    def explain(self, evidence: dict) -> dict: ...
