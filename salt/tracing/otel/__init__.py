"""
OpenTelemetry implementation of the tracing/base abstractions reqd.

Example config for otel:
    [{'otel': {'service_name': 'salt-minion',
               'container_name': 'salt-master-foo',
               'agent_host_name': '127.0.0.1',
                # 6831 for Edge
                # 8792 for Core (incl edge-psms)
               'agent_port': 6831
               }
     }
    ]

################################################################
SAMPLING/Decisions:

"A Sampler provides configurable logic, used by the SDK, for selecting
 which Spans are “recorded” and/or “sampled” in a tracing client library. To
 “record” a span means to build a representation of it in the client’s memory,
 which makes it eligible for being exported. To “sample” a span implies setting
 he W3C sampled flag, recording the span, and exporting the span when it is
 finished.

 OpenTelemetry supports spans that are “recorded” and not “sampled” for
 in-process observability of live spans (e.g., z-pages). "

https://opentelemetry.io/docs/specs/otel/trace/tracestate-probability-sampling/#sampler

TL;DR:

    Possible decisions are DROP, RECORD_ONLY (no sampling), RECORD_AND_SAMPLE

    DROP:               is_sampled = False  is_recording = False
    RECORD_AND_SAMPLE:  is_sampled = True   is_recording = True
    RECORD_ONLY:        is_sampled = False  is_recording = True

    If is_sampled is False, then the span is created at run-time, but is not exported
    If is_recording is False, then a bogus (NonRecordingSpan) is created and nothing is exported.

################################################################
OTEL Context notes:

OTEL use the `context` to store what span is current, this is accessed through
calling the `trace_api.get_current_span(context)` call.

The `trace_api.get_current_span` call looks up the value for the current key
from the passed in context.  If no context is passed in, then
`opentelemetry.context.get_current()` is called which returns a context based
on the `RUNTIME_CONTEXT`, which is controllable via env vars, etc.

So:
    `context` (*immutable dict-like) ->  { 'current-span-key': <current-span-here> }

 "A Context MUST be immutable, and its write operations MUST result in the
  creation of a new Context containing the original values and the specified
  values updated." - https://opentelemetry.io/docs/specs/otel/context/

`opentelemetry.trace.set_span_in_context` is used to set the span (really what
is everywhere else described as the "current" span) in a particular context.

When we want to pass ("propagate") context across services through requests,
we can `inject` and `extract` the SpanContext from a dict-like `carrier`.

    ################ Requester Side ################
    def requester_fn():
        # Start a "root" span with no parent.
        # `root_span` will have a new context, but `start_span` doesn't change
        # the global/default context's current_span
        root_span = tracer.start_span("parent")

        # This is a new context which only contains a "current_span" of the
        # root_span.
        #
        # NB: `set_span_in_context` returns a new context based on
        #     a passed in (or the current, empty) context.
        root_context = set_span_in_context(root_span)

        # root_context = {
        #   'current-span-97816d1a-974b-4496-938c-6da8baa093a7':
        #       _Span(name="childSpan",
        #             context=SpanContext(
        #                       trace_id=0x9355a74a5c3ede2154067d37bb98c8e7,
        #                       span_id=0x9c043a3559dad2ec,
        #                       trace_flags=0x01, trace_state=[], is_remote=False))}

        carrier = {} # usually headers are used as the carrier.
        TraceContextTextMapPropagator().inject(
            carrier=carrier,
            context=root_context)

        # `carrier` now contains the traceid, span-id, and trace flags from the
        # currentspan from the `root_context`, i.e. the `root_span`'s info.
        #
        # carrier = {'traceparent': '00-9355a74a5c3ede2154067d37bb98c8e7-9c043a3559dad2ec-01'}
        send_data_as_some_data_dict_to_worker(data_dict=carrier)

    ################ Worker Side ################
    def worker_fn(some_data_dict, current_worker_context=None):
        # some_data_dict acts as `carrier`

        # - If the current_worker_context is None, then the `extract` call will
        #   assume an empty context to start with as the "original" context.
        #
        # - If there is no context "embedded" in the carrier, then `extract`
        #   will return the new "original" context.
        #
        # - If there is a valid context "embedded" in the carrier, then
        #   `extract` will create a new context (by copying the "original"
        #   context) and setting the current span in the newly created context
        #   to be a NonRecordingSpan which exists only to pass the propagated
        #   information (trace-id, etc.)

        reconstituted_or_empty_context = TraceContextTextMapPropagator().extract(
            carrier=some_data_dict,
            context=current_worker_context)

        # rec...context =  {
        #       'current-span-97816d1a-974b-4496-938c-6da8baa093a7':
        #           NonRecordingSpan(
        #               SpanContext(
        #                   trace_id=0x9355a74a5c3ede2154067d37bb98c8e7,
        #                   span_id=0x9c043a3559dad2ec,
        #                   trace_flags=0x01, trace_state=[], is_remote=True))}

        # Now generate a new span (that should be a child to the span that was
        # created on the "requester" side).
        with salt.utils.tracing.start_as_current_span(
                __name__, "worker_fn",
                context=reconstituted_or_empty_context
        ) as worker_span:
            # Note that `start_as_current_span` also sets current_span in
            # "global" context.
            worker_span.set_attribute("somekey", "someval")

            # opentelemetry.context.get_current() = {
            #   'current-span-97816d1a-974b-4496-938c-6da8baa093a7':
            #       _Span(name="worker_fn",
            #             context=SpanContext(
            #                       trace_id=0x9355a74a5c3ede2154067d37bb98c8e7,
            #                       span_id=0xd37fbb9f0fcbb513,
            #                       trace_flags=0x01, trace_state=[], is_remote=False))}
"""

# pylint: disable=unused-import

try:
    import opentelemetry.trace

    HAS_OTEL_API = True
except ImportError:
    HAS_OTEL_API = False


try:
    import opentelemetry.sdk

    HAS_OTEL_SDK = True
except ImportError:
    HAS_OTEL_SDK = False


try:
    import opentelemetry.exporter.jaeger

    HAS_JAEGER_EXPORTER = True
except ImportError:
    HAS_JAEGER_EXPORTER = False

if all([HAS_OTEL_API, HAS_OTEL_SDK, HAS_JAEGER_EXPORTER]):
    from salt.tracing.otel.tracemanager import OpentelemetryTracingManager, initialize
