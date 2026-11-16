"""Typed, hashed run manifests for isolated backend architecture evaluations.

A manifest is written by a reviewed adapter. It never accepts arbitrary
repository shell commands, Compose files, or host paths from the remote tree.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field


CHALLENGES = {
    'faster': {
        'id': 'faster',
        'label': 'Faster under traffic',
        'detail': 'Reduce p95 latency on the same seeded request mix.',
        'primary': 'p95_ms',
    },
    'spike': {
        'id': 'spike',
        'label': 'Handle a traffic spike',
        'detail': 'Keep errors low while raising completed requests per second.',
        'primary': 'requests_per_s',
    },
    'resources': {
        'id': 'resources',
        'label': 'Use fewer resources',
        'detail': 'Prefer a smaller footprint when latency and errors stay acceptable.',
        'primary': 'cpu_seconds',
    },
    'recover': {
        'id': 'recover',
        'label': 'Recover more reliably',
        'detail': 'Shorten time-to-healthy after an applicable service restart.',
        'primary': 'recovery_s',
    },
}


def challenge_catalog() -> list[dict]:
    return [dict(item) for item in CHALLENGES.values()]


@dataclass(frozen=True)
class WorkloadSpec:
    path: str
    method: str = 'GET'
    warmup_s: int = 2
    window_s: int = 6
    rate: int = 8
    timeout_s: float = 4.0

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class HealthSpec:
    path: str
    contains: str = ''
    status: int = 200
    timeout_s: float = 3.0


@dataclass(frozen=True)
class CandidateDimension:
    candidate_id: str
    label: str
    description: str
    replicas: int = 1
    workers: int = 1
    challenges: tuple[str, ...] = ('faster', 'spike', 'recover')


@dataclass(frozen=True)
class BackendManifest:
    adapter_id: str
    adapter_version: str
    runtime: str
    app_module: str
    source_subdir: str
    source_files: tuple[str, ...]
    detect_markers: tuple[str, ...]
    health: HealthSpec
    workload: WorkloadSpec
    needs_redis: bool = True
    body_pattern: str = ''
    candidates: tuple[CandidateDimension, ...] = ()
    unsupported: tuple[str, ...] = ()
    correctness_rules: tuple[str, ...] = ()
    network_policy: str = 'loopback-gateway-only'
    allow_fault_restart: bool = True
    app_port: int = 8000
    counter_pattern: str = r'(\d+)'

    def as_dict(self) -> dict:
        payload = {
            'adapter_id': self.adapter_id,
            'adapter_version': self.adapter_version,
            'runtime': self.runtime,
            'app_module': self.app_module,
            'source_subdir': self.source_subdir,
            'source_files': list(self.source_files),
            'health': asdict(self.health),
            'workload': self.workload.as_dict(),
            'needs_redis': self.needs_redis,
            'body_pattern': self.body_pattern,
            'candidates': [asdict(item) for item in self.candidates],
            'unsupported': list(self.unsupported),
            'correctness_rules': list(self.correctness_rules),
            'network_policy': self.network_policy,
            'allow_fault_restart': self.allow_fault_restart,
            'app_port': self.app_port,
            'counter_pattern': self.counter_pattern,
        }
        payload['sha256'] = hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode('utf-8')
        ).hexdigest()
        return payload


def validate_relative_files(files: list[str] | tuple[str, ...]) -> list[str]:
    """Reject absolute paths, traversal and empty names before any copy."""
    cleaned = []
    for item in files:
        text = str(item).replace('\\', '/').strip()
        if not text or text.startswith('/') or text.startswith('../') or '/../' in f'/{text}/':
            raise ValueError(f'Refused source path {item!r}')
        if ':' in text or text.startswith('~'):
            raise ValueError(f'Refused source path {item!r}')
        cleaned.append(text)
    return cleaned
