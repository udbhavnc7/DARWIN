"""Single registry of reviewed adapters.

Adding an external target means adding a typed adapter class and a trusted
catalog entry. Nothing downstream may key off a repository URL or a specific
framework, so inspection and the evaluation engine both resolve adapters here.
"""
from __future__ import annotations


def reviewed_adapters() -> list:
    from darwin.adapters.flask_redis import FlaskRedisAdapter
    from darwin.adapters.node_redis import NodeRedisAdapter
    from darwin.adapters.sanchay_reporting import SanchayReportingAdapter

    return [SanchayReportingAdapter(), FlaskRedisAdapter(), NodeRedisAdapter()]


def adapters_by_id() -> dict:
    return {adapter.id: adapter for adapter in reviewed_adapters()}


def compose_adapter_by_id(adapter_id: str):
    """Return a reviewed container adapter, never a client-pipeline one."""
    adapter = adapters_by_id().get(adapter_id)
    if adapter is None or adapter.evaluation_type != 'backend_architecture':
        return None
    return adapter
