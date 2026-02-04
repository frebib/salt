import inspect
import logging
import textwrap
import threading
import time
from typing import Any

import pytest
import yaml
from _pytest.logging import LogCaptureFixture
from opentelemetry.sdk import trace as sdk_trace
from opentelemetry.sdk.trace import export as ot_export
from opentelemetry.sdk.trace import sampling as ot_sampling

from salt.tracing.otel.matching_sampler import MatchingSampler, _SubSampler
from salt.tracing.otel.sampler import _DEFAULT_SAMPLER, _get_sampler_type, get_sampler

SAMPLER_CONFIGS = [
    {
        "yaml": textwrap.dedent(
            f"""
            type: matching
            matchers:
              - pattern: .*
                sampler: parentbased_traceidratio
                ratio: 0.001
              - pattern: "^(_handle.*|get_file|loader)"
                sampler: always_off
            """
        ),
        "result": {
            "sampler": MatchingSampler,
            "matchers": [
                {
                    "pattern": ".*",
                    "positive_matches": ["foo", "bar", ""],
                    "negative_matches": [],
                    "sampler": ot_sampling.ParentBasedTraceIdRatio,
                },
                {
                    "pattern": "^(_handle.*|get_file|loader)",
                    "positive_matches": [
                        "_handle_payload",
                        "_handle_request",
                        "loader.utils",
                    ],
                    "negative_matches": [
                        "direct_call.execute",
                        "RemotePillar.compile_pillar",
                    ],
                    "sampler": ot_sampling.ALWAYS_OFF,
                },
            ],
        },
    },
]


def is_matching_sampler(desired_class_or_instance, got_class_or_instance) -> bool:
    if inspect.isclass(desired_class_or_instance):
        return isinstance(got_class_or_instance, desired_class_or_instance)
    else:
        # Singleton match
        return desired_class_or_instance is got_class_or_instance


@pytest.mark.parametrize(
    "sampler_opts,should_warn", [(None, False), ([], False), (1, True), ("foo", True)]
)
def test_non_dict_otel_sampler_config(
    sampler_opts: Any, should_warn: bool, caplog: LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING):
        assert get_sampler(sampler_opts) is _DEFAULT_SAMPLER
        assert (
            f"Error getting sampler type from: {sampler_opts}" in caplog.text
        ) == should_warn
        assert (f"Falling back to default OTEL sampler" in caplog.text) == should_warn


def test_otel_sampler_config():
    for config in SAMPLER_CONFIGS:
        desired_result = config["result"]
        config_dict = next(yaml.safe_load_all(config["yaml"]))

        sampler_type = _get_sampler_type(config_dict)
        assert sampler_type == config_dict["type"]

        sampler = get_sampler(config_dict)
        assert is_matching_sampler(desired_result["sampler"], sampler)

        if desired_result["sampler"] == MatchingSampler:
            generated_matchers_dict: dict[str, _SubSampler] = {
                gm.raw_pattern: gm for gm in sampler._sub_samplers
            }

            for desired_matcher in desired_result.get("matchers", []):
                generated_matcher = generated_matchers_dict[desired_matcher["pattern"]]

                assert is_matching_sampler(
                    desired_matcher["sampler"], generated_matcher.sampler
                )

                for positive in desired_matcher["positive_matches"]:
                    assert generated_matcher.compiled_pattern.match(positive)
                for negative in desired_matcher["negative_matches"]:
                    assert not generated_matcher.compiled_pattern.match(negative)


def test_otel_sampler_pattern_matching():
    sampler = MatchingSampler(
        {
            "type": "matching",
            "matchers": [
                {
                    "pattern": "^(_handle.*|get_file|loader)",
                    "sampler": "always_off",
                },
                {
                    "pattern": ".*",
                    "sampler": "always_on",
                },
            ],
        }
    )

    sampling_result: ot_sampling.SamplingResult = sampler.should_sample(
        parent_context=None,
        trace_id=0xDEADBEEF,
        name="get_file",
        kind=None,
        attributes=None,
        links=None,
        trace_state=None,
    )

    assert not sampling_result.decision.is_sampled()

    sampling_result: ot_sampling.SamplingResult = sampler.should_sample(
        parent_context=None,
        trace_id=0xDEADBEEF,
        name="other_thing",
        kind=None,
        attributes=None,
        links=None,
        trace_state=None,
    )

    assert sampling_result.decision.is_sampled()


class MySpanExporter(ot_export.SpanExporter):
    """Very simple span exporter used for testing."""

    def __init__(
        self,
        destination,
        max_export_batch_size=None,
        export_timeout_millis=0.0,
        export_event: threading.Event = None,
    ):
        self.destination = destination
        self.max_export_batch_size = max_export_batch_size
        self.is_shutdown = False
        self.export_timeout = export_timeout_millis / 1e3
        self.export_event = export_event

    def export(self, spans: sdk_trace.Span) -> ot_export.SpanExportResult:
        if (
            self.max_export_batch_size is not None
            and len(spans) > self.max_export_batch_size
        ):
            raise ValueError("Batch is too big")
        time.sleep(self.export_timeout)
        self.destination.extend(span.name for span in spans)
        if self.export_event:
            self.export_event.set()
        return ot_export.SpanExportResult.SUCCESS

    def shutdown(self):
        self.is_shutdown = True


def test_otel_sampler_ratio_based():
    # Note that the ratio samplers are TRACEID based, not SPANID based.
    test_ratio = 0.5
    n_spans = 10000

    sampler = MatchingSampler(
        {
            "type": "matching",
            "matchers": [
                {
                    "pattern": "always_on.*",
                    "sampler": "always_on",
                },
                {
                    "pattern": "always_off.*",
                    "sampler": "always_off",
                },
                {
                    "pattern": "traceidratio.*",
                    "sampler": "traceidratio",
                    "ratio": test_ratio,
                },
            ],
        }
    )

    tracer_provider = sdk_trace.TracerProvider(sampler=sampler)
    tracer = tracer_provider.get_tracer(__name__)
    spans_names_list: list[str] = []

    exporter = MySpanExporter(
        destination=spans_names_list,
        max_export_batch_size=n_spans * 2,
    )
    span_processor = ot_export.BatchSpanProcessor(
        exporter,
        max_queue_size=n_spans * 2,
        max_export_batch_size=n_spans * 2,
        schedule_delay_millis=100,
    )
    tracer_provider.add_span_processor(span_processor)

    def _add_span(name: str):
        with tracer.start_as_current_span(name):
            pass

    for i in range(n_spans):
        _add_span(f"always_on_{i}")
        _add_span(f"always_off_{i}")
        _add_span(f"traceidratio_{i}")

    # Don't forget to flush.
    assert span_processor.force_flush()

    result_ratios = {
        "always_on": 1.0,
        "always_off": 0,
        "traceidratio": test_ratio,
    }

    for sampler_name, want_ratio in result_ratios.items():
        n_sampled = len([s for s in spans_names_list if s.startswith(sampler_name)])
        got_ratio: float = float(n_sampled) / n_spans

        assert got_ratio == pytest.approx(
            want_ratio,
            rel=1e-1,  # Pretty loose matching.
        ), f"Failed with {sampler_name}"
