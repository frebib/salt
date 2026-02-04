import enum
import logging
import socket
from contextlib import contextmanager
from typing import Optional

import opentelemetry.context as ot_context
import opentelemetry.trace as ot_trace
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.sdk import resources as ot_resources
from opentelemetry.sdk.trace import Span, TracerProvider, sampling
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from opentelemetry.trace.status import StatusCode

from salt.tracing.base import BaseTracingManager, SpanStatusType
from salt.tracing.otel.sampler import get_sampler

OTEL_EXPORTER_JAEGER_AGENT_PORT = 6831
DEFAULT_PROCESSOR_MAX_QUEUE_SIZE = 20480
DEFAULT_PROCESSOR_EXPORTER_BATCH_SIZE = 128
DEFAULT_PROCESSOR_SCHEDULE_DELAY_MILLIS = 100


log = logging.getLogger(__name__)


class OtelInterfaceError(Exception):
    pass


class CollectorType(enum.Enum):
    """
    Distinguish telemetry collector types
    """

    open_telemetry = 0
    jaeger = 1


class TracingManagerOptions:
    # During salt-minon state runtime the we know everything it needs to about
    # the minion's configuration, the logic for defining the correct
    # highstate_metrics configuration should be there
    # (salt/states/salt-minion/config.sls) rather than worry about what pillar
    # data does/doesn't exist at the run time of the returner.

    # Production should always be running highstate_metrics. To turn it off,
    # remove "highstate_metrics" from the "returner" section of the minion
    # config.
    def __init__(
        self,
        service_name,
        service_version=None,
        container_name=None,
        collector_type=CollectorType.jaeger,
        agent_host_name="127.0.0.1",
        agent_port=OTEL_EXPORTER_JAEGER_AGENT_PORT,
        agent_path="",
        log_spans_start_end=False,
        resource_attributes=None,
        sampler=None,
    ):
        self.service_name = service_name
        self.service_version = service_version or "unknown"
        self.container_name = container_name or socket.gethostname()

        self.collector_type = collector_type
        self.agent_host_name = agent_host_name
        self.agent_port = agent_port
        self.agent_path = agent_path

        if not isinstance(log_spans_start_end, bool):
            raise OtelInterfaceError(
                "otel option log_spans_start_end must be a boolean"
            )
        self.log_spans_start_end = log_spans_start_end
        self.resource_attributes = resource_attributes
        self.sampler = sampler


class OpentelemetryTracingManager(BaseTracingManager):
    """
    Placeholder for tracing system contact.
    """

    # See https://opentelemetry.io/docs/collector/configuration/
    options: TracingManagerOptions = None
    tm: Optional["OpentelemetryTracingManager"] = None

    # The exporter is how we send data out and speaks to whatever is receiving
    # the traces.
    _tracer_exporter = None

    # The processor isn't strictly necessary, but can do things like batching.
    # https://github.com/open-telemetry/opentelemetry-collector/tree/main/processor#recommended-processors
    # Typically SimpleSpanProcessor (no batching),
    #        or BatchSpanProcessor (includes batching).
    #
    # The processor knows what exporter to call upstream.
    _tracer_processor = None

    # The provider is the programmer-facing piece that provides the Tracer.
    # It knows what processor(s) to call upstream.
    _tracer_provider = None

    _sampler: Optional[sampling.Sampler] = None

    @classmethod
    def initialize(cls, *args, **kwargs):
        if len(args) != 1 or kwargs:
            raise OtelInterfaceError(
                "OpentelemetryTracingManager.initialize only takes one arg."
            )
        options = args[0]

        if not isinstance(options, TracingManagerOptions):
            raise OtelInterfaceError(
                f"{cls.__name__}.initialize not passed a TracingManagerOptions arg: {options}"
            )

        if cls.tm is not None:
            raise OtelInterfaceError(
                f"{cls.__name__}.initialize being called more than once."
            )

        # Create singleton
        cls.tm = cls()
        cls.tm.options = options

        cls.tm._initialize()

    @classmethod
    def get_tracer(cls, name):
        return cls.tm._get_tracer(name)

    # Note that otel gets the current span from the context, and uses its
    @classmethod
    def get_current_span(cls, context=None):
        return ot_trace.get_current_span(context=context)

    @classmethod
    def _xlate_status(cls, code):
        _code = {
            SpanStatusType.UNSET: StatusCode.UNSET,
            SpanStatusType.OK: StatusCode.OK,
            SpanStatusType.ERROR: StatusCode.ERROR,
        }.get(code, None)

        if _code is None:
            raise OtelInterfaceError(f"Unknown status {code}")

        return StatusCode(_code)

    def _make_tracer_provider(self):
        resource_map = {
            ot_resources.SERVICE_NAME: self.options.service_name,
            ot_resources.CONTAINER_NAME: self.options.container_name,
        }
        if self.options.resource_attributes:
            if not isinstance(self.options.resource_attributes, dict):
                raise OtelInterfaceError("resource_attribtes option must be a dict")
            resource_map.update(self.options.resource_attributes)

        return TracerProvider(
            sampler=self._sampler,
            resource=ot_resources.Resource.create(resource_map),
        )

    def _make_tracer_exporter(self):
        return JaegerExporter(
            agent_host_name=self.options.agent_host_name,
            agent_port=self.options.agent_port,
            udp_split_oversized_batches=True,
        )

    def _make_tracer_processor(self):
        return BatchSpanProcessor(
            span_exporter=self._tracer_exporter,
            # After max_queue_size, spans can get dropped
            max_queue_size=DEFAULT_PROCESSOR_MAX_QUEUE_SIZE,
            # Flush the queue after max_export_batch_size.
            max_export_batch_size=DEFAULT_PROCESSOR_EXPORTER_BATCH_SIZE,
            # Flush queue every n millis
            schedule_delay_millis=DEFAULT_PROCESSOR_SCHEDULE_DELAY_MILLIS,
        )

    def _initialize(self):
        # Process misc opts first
        if self.options.log_spans_start_end:
            enable_log_spans_start_end()

        # Initialize sampler
        self._sampler = get_sampler(self.options.sampler)

        # Setup individual pieces to hook together, then connect 'em.
        self._tracer_provider = self._make_tracer_provider()
        self._tracer_exporter = self._make_tracer_exporter()
        self._tracer_processor = self._make_tracer_processor()

        # Hook pieces together for the flow through the local python process
        # part of otel.
        # (code) -> Tracer -> Processor[s] -> Exporter -> (EXT: Collector)
        self._tracer_provider.add_span_processor(self._tracer_processor)

    def _get_tracer(self, name):
        return self._tracer_provider.get_tracer(name)


def initialize(opts):
    # Validate opts
    reqd_opts = ("service_name",)
    opt_opts = (
        "sampler",
        "service_version",
        "container_name",
        "agent_host_name",
        "agent_port",
        "log_spans_start_end",
        # This will be a dict of resource attributes to use (or None).
        # These are meant to be site specific, not things like
        # "service_version".
        "resource_attributes",
    )
    all_opts = set(reqd_opts + opt_opts)

    for reqd_opt in reqd_opts:
        if not opts.get(reqd_opt):
            raise OtelInterfaceError(f"Initialize missing required option: {reqd_opt}")

    unknown_opts = set(opts.keys()) - all_opts
    if unknown_opts:
        log.warning("Unknown options passed to initialize: %s", unknown_opts)
        for unknown_opt in unknown_opts:
            del opts[unknown_opt]

    otm_options = TracingManagerOptions(**opts)
    OpentelemetryTracingManager.initialize(otm_options)

    return OpentelemetryTracingManager.tm


def enable_log_spans_start_end():
    def log_span_wrap(fn):
        def wrapper(span, *args, **kwargs):
            fn(span, *args, **kwargs)
            for jsl in span.to_json().split("\n"):
                log.trace("<span> %s", jsl)

        return wrapper

    # Monkeypatch span enter, exit
    orig_span_start = Span.start
    orig_span_end = Span.end

    Span.start = log_span_wrap(orig_span_start)
    Span.end = log_span_wrap(orig_span_end)
