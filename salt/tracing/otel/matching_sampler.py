import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from re import Pattern
from typing import Any, Optional

import opentelemetry.context as ot_context
import opentelemetry.trace as ot_trace
import opentelemetry.util.types as ot_types
from opentelemetry.sdk.trace import sampling
from opentelemetry.trace.span import TraceState

log = logging.getLogger(__name__)


_KNOWN_SUB_SAMPLERS = {
    "always_on": sampling.ALWAYS_ON,
    "always_off": sampling.ALWAYS_OFF,
    "parentbased_always_on": sampling.DEFAULT_ON,
    "parentbased_always_off": sampling.DEFAULT_OFF,
    "traceidratio": sampling.TraceIdRatioBased,
    "parentbased_traceidratio": sampling.ParentBasedTraceIdRatio,
}


@dataclass
class SampleDatum:
    """Placeholder for data associated with figuring out whether to sample
    or not."""

    parent_context: Optional[ot_context.Context]
    trace_id: int
    name: str
    kind: Optional[ot_trace.SpanKind]
    attributes: Optional[ot_types.Attributes]
    links: Optional[Sequence[ot_trace.Link]]
    trace_state: Optional[TraceState]


class MatchingSampler(sampling.Sampler):
    """OTEL Sampler configuration:
    sampler:
      type: [matching|always_on|always_off]
      matchers:
        - pattern: .*
          sampler: parentbased_traceidratio
          ratio: 0.001
    """

    def __init__(self, opts: dict[str, Any]):
        self.opts = opts
        self._sub_samplers: list[_SubSampler] = _generate_sub_samplers(opts["matchers"])
        self.default_decision: sampling.Decision = sampling.Decision.RECORD_ONLY

    def _generate_default_result(self, sd: SampleDatum) -> sampling.SamplingResult:
        decision = self.default_decision
        attributes = sd.attributes
        parent_context = sd.parent_context

        if decision is sampling.Decision.DROP:
            attributes = None

        return sampling.SamplingResult(
            decision,
            attributes,
            _get_parent_trace_state(parent_context),
        )

    def _get_sampling_result(self, sd: SampleDatum) -> sampling.SamplingResult:
        for ms in self._sub_samplers:
            if ms.compiled_pattern.match(sd.name):
                return ms.sampler.should_sample(
                    sd.parent_context,
                    sd.trace_id,
                    sd.name,
                    sd.kind,
                    sd.attributes,
                    sd.links,
                    sd.trace_state,
                )

        return self._generate_default_result(sd)

    # pylint: disable=signature-differs
    def should_sample(
        self,
        parent_context: Optional[ot_context.Context],
        trace_id: int,
        name: str,
        kind: Optional[ot_trace.SpanKind] = None,
        attributes: Optional[ot_types.Attributes] = None,
        links: Optional[Sequence[ot_trace.Link]] = None,
        trace_state: Optional[TraceState] = None,
    ) -> sampling.SamplingResult:
        sd: SampleDatum = SampleDatum(
            parent_context,
            trace_id,
            name,
            kind,
            attributes,
            links,
            trace_state,
        )
        return self._get_sampling_result(sd)

    def get_description(self) -> str:
        return "Matching"


@dataclass
class _SubSampler:
    raw_pattern: str
    compiled_pattern: Pattern
    sampler: sampling.Sampler


def _generate_sub_samplers(opts: list[dict[str, Any]]) -> list[_SubSampler]:
    sub_samplers: list[_SubSampler] = []

    for sub_sampler_opts in opts:
        ms = _generate_sub_sampler(sub_sampler_opts)
        if ms is not None:
            sub_samplers.append(ms)

    return sub_samplers


def _generate_sub_sampler(sub_sampler_opts: dict[str, Any]) -> Optional[_SubSampler]:
    raw_pattern = sub_sampler_opts.get("pattern", None)
    if raw_pattern is None:
        log.warning(
            "Couldn't find pattern in MatchingSampler option %s", sub_sampler_opts
        )
        return None
    try:
        compiled_pattern: Pattern = re.compile(raw_pattern)
    except Exception as exc:  # pylint: disable=broad-except
        log.warning(
            "Couldn't compile MatchingSampler match hit regexp pattern, ignoring: %s: %s",
            raw_pattern,
            exc,
        )
        return None

    sub_sampler_type = sub_sampler_opts.get("sampler", None)
    if sub_sampler_type is None:
        log.warning(
            "Missing MatchingSampler match hit type, ignoring: %s:", raw_pattern
        )
        return None

    if sub_sampler_type not in _KNOWN_SUB_SAMPLERS:
        log.warning("Unknown sub sampler type: %s, ignoring", sub_sampler_type)
        return None

    _sampler: sampling.Sampler
    if sub_sampler_type in ("traceidratio", "parentbased_traceidratio"):
        _sampler = _build_ratio_based_sub_sampler(sub_sampler_type, sub_sampler_opts)
    else:
        # singleton sampler.
        _sampler = _KNOWN_SUB_SAMPLERS[sub_sampler_type]

    return _SubSampler(
        raw_pattern=raw_pattern, compiled_pattern=compiled_pattern, sampler=_sampler
    )


def _build_ratio_based_sub_sampler(
    sub_sampler_type: str, sub_sampler_opts: dict[str, Any]
) -> sampling.Sampler:
    sampler_args = []

    ratio: Optional[str] = sub_sampler_opts.get("ratio", None)
    if ratio is None:
        raise Exception(
            f"No ratio specified for MatchingSampler subsampler: {sub_sampler_type}, {sub_sampler_opts}"
        )
    try:
        rate = float(ratio)
    except (ValueError, TypeError):
        raise Exception(
            f"Could not convert MatchingSampler subsampler {sub_sampler_type} {sub_sampler_opts}ratio: {ratio} to float.",
        )

    sampler_args.append(rate)

    try:
        sampler = _KNOWN_SUB_SAMPLERS[sub_sampler_type](*sampler_args)
    except Exception as exc:  # pylint: disable=broad-except
        raise Exception(
            "Exception while creating match sampler: "
            + f"{sub_sampler_type} {sub_sampler_opts}"
        ) from exc

    return sampler


def _get_parent_trace_state(parent_context) -> Optional[TraceState]:
    parent_span_context = ot_trace.get_current_span(parent_context).get_span_context()
    if parent_span_context is None or not parent_span_context.is_valid:
        return None
    return parent_span_context.trace_state
