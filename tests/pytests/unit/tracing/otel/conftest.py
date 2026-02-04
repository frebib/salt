import pytest

from salt.tracing.otel.tracemanager import OpentelemetryTracingManager


@pytest.fixture(autouse=False)
def otel_tracing_manager():
    # Just returns the class
    yield OpentelemetryTracingManager

    # But does cleanup afterwards.
    OpentelemetryTracingManager.tm = None
