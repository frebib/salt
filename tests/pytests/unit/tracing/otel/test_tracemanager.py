import pytest
from _pytest.logging import LogCaptureFixture

from salt.tracing.otel.matching_sampler import MatchingSampler
from salt.tracing.otel.sampler import _DEFAULT_SAMPLER
from salt.tracing.otel.tracemanager import (
    OpentelemetryTracingManager,
    OtelInterfaceError,
    TracingManagerOptions,
)
from salt.tracing.otel.tracemanager import initialize as otel_tmgr_initialize
from tests.support.mock import MagicMock, patch


def test_otel_trace_manager_resource_attrs():
    raw_opts = {
        "agent_host_name": "127.0.0.1",
        "agent_port": 8792,
        "log_spans_start_end": True,
        "resource_attributes": {
            "metal_colo": "pdx01",
            "metal_hw_gen": "None",
            "metal_region": "WNAM",
            "metal_role": "None",
            "metal_tier": "None",
        },
        "sampler": {
            "matchers": [
                {
                    "pattern": "^(_handle.*|get_file|loader)",
                    "sampler": "always_off",
                }
            ],
            "type": "matching",
        },
        "service_name": "salt-master-test",
    }
    otel_tmgr: OpentelemetryTracingManager = otel_tmgr_initialize(raw_opts)

    assert otel_tmgr.options.resource_attributes == raw_opts["resource_attributes"]


def test_otel_trace_manager_sampler_choice():
    test_configs = [
        # Should fail b/c of missing "ratio" arg and use default sampler.
        {
            "sampler_config": {
                "sampler": {
                    "matchers": [
                        {
                            "pattern": "^(_handle.*|get_file|loader)",
                            "sampler": "traceidratio",
                        }
                    ],
                    "type": "matching",
                },
            },
            "result_sampler": _DEFAULT_SAMPLER,
        },
        # Missing "sampler" section  -> default sampler
        {
            "sampler_config": {},
            "result_sampler": _DEFAULT_SAMPLER,
        },
        # Working MatchingSampler
        {
            "sampler_config": {
                "sampler": {
                    "matchers": [
                        {
                            "pattern": "^(_handle.*|get_file|loader)",
                            "sampler": "always_off",
                        }
                    ],
                    "type": "matching",
                },
            },
            "result_sampler": MatchingSampler,
        },
    ]

    default_tracemanager_opts = {
        "service_name": "salt-master-test",
    }

    for test_config in test_configs:
        raw_opts = dict(default_tracemanager_opts)
        raw_opts.update(test_config["sampler_config"])

        # We're not going to worry about initializing the class singleton,
        # just test the options.
        ot_mgr = OpentelemetryTracingManager()
        ot_mgr.options = TracingManagerOptions(**raw_opts)
        ot_mgr._initialize()

        result_sampler = test_config["result_sampler"]
        if result_sampler is _DEFAULT_SAMPLER:
            assert ot_mgr._sampler == _DEFAULT_SAMPLER
        else:
            assert isinstance(ot_mgr._sampler, result_sampler)


def test_initialize_raises_on_missing_required_opt() -> None:
    with pytest.raises(
        OtelInterfaceError, match="Initialize missing required option: service_name"
    ):
        otel_tmgr_initialize({})


@patch("salt.tracing.otel.tracemanager.OpentelemetryTracingManager")
@patch(
    "salt.tracing.otel.tracemanager.TracingManagerOptions.__init__", return_value=None
)
def test_warns_on_unknown_opt(
    tracing_manager_options_init_mock: MagicMock,
    opentelemetry_tracing_manager_mock: MagicMock,
    caplog: LogCaptureFixture,
) -> None:
    assert (
        otel_tmgr_initialize({"service_name": "test", "unknown_option": "unknown"})
        == opentelemetry_tracing_manager_mock.tm
    )

    assert "Unknown options passed to initialize: {'unknown_option'}" in caplog.text

    tracing_manager_options_init_mock.assert_called_once_with(service_name="test")
