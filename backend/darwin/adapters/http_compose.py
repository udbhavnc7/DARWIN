"""Generic reviewed HTTP+Compose backend adapter.

Detection is file-backed (markers + allowlisted files), not repository name.
Execution always goes through IsolatedBackend, never the host interpreter.
"""
from __future__ import annotations

from pathlib import Path
import shutil

from darwin.adapters.base import (
    AdapterCancelled, AdapterError, Candidate, EvaluationBudget, PreparedEvaluation, SupportAssessment,
)
from darwin.backend_manifest import BackendManifest, CHALLENGES, CandidateDimension
from darwin.backend_verdict import decide_architecture, pareto_rows
from darwin.isolated_backend import IsolatedBackend, IsolationError, runner_available, topology


class HttpComposeAdapter:
    evaluation_type = 'backend_architecture'

    def __init__(self, manifest: BackendManifest):
        self.manifest = manifest
        self.id = manifest.adapter_id
        self.version = manifest.adapter_version

    def detect(self, source_root: Path, commit_sha: str, pinned: bool) -> SupportAssessment:
        root = Path(source_root)
        evidence = []
        for relative in self.manifest.source_files:
            path = root / relative
            if path.is_symlink() or not path.is_file():
                return SupportAssessment(
                    self.id, self.version, False, self.evaluation_type,
                    f'Required source file {relative} is missing or is a symlink.',
                    evidence,
                )
            evidence.append(relative)
        text = (root / self.manifest.source_files[0]).read_text(encoding='utf-8', errors='replace')
        missing = [marker for marker in self.manifest.detect_markers if marker not in text]
        if missing:
            return SupportAssessment(
                self.id, self.version, False, self.evaluation_type,
                'Source does not match the reviewed application markers for this adapter.',
                evidence,
            )
        if not pinned:
            return SupportAssessment(
                self.id, self.version, False, self.evaluation_type,
                'The commit is not the pinned, reviewed revision. Inspection only.',
                evidence,
            )
        ok, reason = runner_available()
        note = 'Reviewed adapter matches this pinned source.'
        if not ok:
            note += ' ' + reason
        return SupportAssessment(self.id, self.version, True, self.evaluation_type, note, evidence)

    def describe(self, source_root: Path, commit_sha: str, pinned: bool) -> dict:
        ok, reason = runner_available()
        return {
            'adapter_id': self.id,
            'adapter_version': self.version,
            'evaluation_type': self.evaluation_type,
            'manifest': self.manifest.as_dict(),
            'isolation': {'available': ok, 'reason': reason},
            'challenges': list(CHALLENGES.values()),
            'unsupported': list(self.manifest.unsupported),
        }

    def capabilities(self) -> dict:
        return {
            'inspect': True,
            'deploy': True,
            'dimensions': ['replicas', 'workers'],
            'faults': ['service_restart'] if self.manifest.allow_fault_restart else [],
            'metrics': ['p95_ms', 'requests_per_s', 'error_rate', 'recovery_s'],
            'invariants': list(self.manifest.correctness_rules),
            'search': 'bounded_measured_comparison',
        }

    def enumerate_candidates(self, challenge: str = 'faster') -> list[CandidateDimension]:
        selected = [item for item in self.manifest.candidates if challenge in item.challenges]
        if not selected:
            selected = list(self.manifest.candidates)
        return selected

    def prepare(self, source_root: Path, work_dir: Path, budget: EvaluationBudget) -> PreparedEvaluation:
        work_dir = Path(work_dir)
        harness = work_dir / 'stack'
        harness.mkdir(parents=True, exist_ok=True)
        diff = work_dir / 'candidate.diff'
        lines = [
            '--- a/darwin-owned-compose.yaml',
            '+++ b/darwin-owned-compose.yaml',
            '@@ DARWIN generates this file; the repository Compose file is never used @@',
        ]
        for item in self.manifest.candidates[1:]:
            lines.append(f'+ {item.candidate_id}: replicas={item.replicas} workers={item.workers}')
        diff.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        config = work_dir / 'manifest.json'
        config.write_text(__import__('json').dumps(self.manifest.as_dict(), indent=2), encoding='utf-8')
        return PreparedEvaluation(
            work_dir=work_dir, source_root=Path(source_root), harness_dir=harness,
            fixtures=[{'id': 'http-seed', 'seed': budget.seeds[0] if budget.seeds else 7,
                       'size': budget.window_s if hasattr(budget, 'window_s') else 0,
                       'currency': 'http', 'timed': True, 'file': 'http'}],
            config_path=config, candidate_diff=diff,
            candidate_files=list(self.manifest.source_files),
            checks=[{'name': rule, 'passed': True, 'detail': 'declared'} for rule in self.manifest.correctness_rules],
        )

    def candidates(self, prepared: PreparedEvaluation) -> list[Candidate]:
        rows = []
        for item in self.manifest.candidates:
            rows.append(Candidate(
                item.candidate_id, item.label, item.description,
                prepared.candidate_diff, prepared.candidate_files,
                {'replicas': item.replicas, 'workers': item.workers, 'topology': topology(item, self.manifest.needs_redis)},
            ))
        return rows

    def measure(self, prepared: PreparedEvaluation, candidate: Candidate,
                budget: EvaluationBudget, check) -> dict:
        challenge = getattr(budget, 'challenge', None) or 'faster'
        search_mode = getattr(budget, 'search_mode', None) or 'compare'
        wanted = self.enumerate_candidates(challenge)
        if search_mode == 'evolve':
            wanted = list(self.manifest.candidates)
        if candidate and candidate.candidate_id not in {item.candidate_id for item in wanted}:
            wanted = [next(item for item in self.manifest.candidates if item.candidate_id == candidate.candidate_id)]
        ok, reason = runner_available()
        if not ok:
            raise AdapterError(reason, 'isolation_unavailable', 'FAILED_INFRASTRUCTURE')

        include_fault = challenge == 'recover' or (budget.mode == 'full' and self.manifest.allow_fault_restart)
        seed = budget.seeds[0] if budget.seeds else 7
        runs = []
        checks = []
        for item in wanted:
            if check():
                raise AdapterCancelled('Cancelled between candidates')
            stack_dir = prepared.harness_dir / item.candidate_id
            if stack_dir.exists():
                shutil.rmtree(stack_dir, ignore_errors=True)
            stack_dir.mkdir(parents=True, exist_ok=True)
            runner = IsolatedBackend(stack_dir, self.manifest, item)
            try:
                written = runner.write_stack(prepared.source_root)
                runner.start(check)
                measured = runner.measure(seed, check, include_fault=include_fault)
            except IsolationError as exc:
                raise AdapterError(str(exc), getattr(exc, 'code', 'docker_failed'), 'FAILED_INFRASTRUCTURE') from exc
            finally:
                cleanup = runner.cleanup()
            oracle = measured.get('correctness') or {}
            checks.append({
                'name': f'{item.candidate_id} health and shared-state oracle',
                'passed': bool(oracle.get('passed')),
                'detail': oracle.get('detail') or '',
            })
            runs.append({
                'candidate_id': item.candidate_id,
                'label': item.label,
                'description': item.description,
                'replicas': item.replicas,
                'workers': item.workers,
                'topology': written['topology'],
                'compose_sha256': written['compose_sha256'],
                'metrics': measured['metrics'],
                'recovery_s': measured.get('recovery_s'),
                'ready_s': measured.get('ready_s'),
                'samples': measured.get('samples'),
                'cleanup_status': cleanup,
                'baseline': item.candidate_id.endswith('baseline') or item.candidate_id == self.manifest.candidates[0].candidate_id,
            })
        return {
            'runs': runs,
            'checks': checks,
            'challenge': challenge,
            'search_mode': search_mode,
            'pareto': pareto_rows(runs),
            'environment': {
                'isolation': 'linux-docker',
                'platform': os_name(),
                'repository_compose_used': False,
            },
        }

    def verify(self, prepared: PreparedEvaluation, candidate: Candidate, measurements: dict) -> dict:
        runs = measurements.get('runs') or []
        baseline = next((item for item in runs if item.get('baseline')), runs[0] if runs else None)
        others = [item for item in runs if item is not baseline]
        checks = measurements.get('checks') or []
        verdict = decide_architecture(
            challenge=measurements.get('challenge') or 'faster',
            checks=checks,
            baseline=baseline or {},
            candidates=runs,
        )
        return {
            'parity': {
                'passed': verdict['correctness']['passed'],
                'checks_passed': verdict['correctness']['checks_passed'],
                'checks_total': verdict['correctness']['checks_total'],
                'failures': verdict['correctness']['failures'],
            },
            'checks': checks,
            'summaries': [],
            'verdict': verdict,
            'source_tests': {
                'status': 'not_run',
                'reason': 'This adapter verifies HTTP oracles in isolation; it does not install repository test runners.',
            },
            'environment': measurements.get('environment'),
            'runs': runs,
            'pareto': measurements.get('pareto') or [],
            'comparison': {
                'baseline': baseline,
                'candidates': others,
                'challenge': measurements.get('challenge'),
            },
        }

    def explain(self, evidence: dict) -> dict:
        verdict = evidence.get('verdict') or {}
        return {
            'explanation': verdict.get('explanation') or verdict.get('reason'),
            'status': verdict.get('status'),
        }

    def export_change(self, evidence: dict) -> str:
        comparison = evidence.get('comparison') or {}
        baseline = comparison.get('baseline') or {}
        winner = evidence.get('verdict', {}).get('winner_id')
        cand = next((item for item in comparison.get('candidates') or []
                     if item.get('candidate_id') == winner), None)
        if not cand:
            return 'No deployable architecture change is exported.\n'
        return (
            '# DARWIN-owned Compose overlay (repository compose.yaml is unused)\n'
            f'# baseline: replicas={baseline.get("replicas")} workers={baseline.get("workers")}\n'
            f'# candidate: replicas={cand.get("replicas")} workers={cand.get("workers")}\n'
            '# Rollback: deploy the baseline service count and workers.\n'
        )


def os_name() -> str:
    import os
    return os.name
