"""
Provide a generic (albeit OTel inspired) interface to a tracing manager for
SaltStack.

Example configuration:

tracing:
  module:
    otel:
      # Optional sampler
      sampler:
        # Types are: [always_on|always_off|matching]
        #
        # "matching" sampler permits patterns and sub-samplers to be defined.
        # Patterns are matched in order, with the first pattern matching being
        # applied to the span being tested.
        # The default of the "matching" sampler is to "record only" which
        # means to not emit the span to the collector (i.e. not sample), but
        # to generate the span at run-time.
        #
        # Sub-sampler types are:
        # - always_on
        # - always_off
        # - parentbased_always_on
        # - parentbased_always_off
        # - traceidratio
        # - parentbased_traceidratio
        #
        # ratio based sub-samplers should specify the ratio as well
        type: matching
        matchers:
          - pattern: "^(_handle.*|get_file|loader)"
            sampler: always_off
          - pattern: "MySampledThing"
            sampler: traceidratio
            ratio: 0.001
          - pattern: ".*"
            sampler: parentbased_always_on

      service_name: salt-master
      agent_host_name: 127.0.0.1
      agent_port: 8792
      # The start and end of spans are logged at trace level
      log_spans_start_end: true
      resource_attributes:
        something: is_this

  debugging:
    # The backtraces of when spans start is inserted into spans.
    backtraces: true

"""

import functools
import logging
import threading
import traceback
from contextlib import contextmanager
from functools import wraps

# Import additional tracing modules here so they can be found in setup_tracing
# if needed.  This could go in setup_tracing, but that might be slightly
# confusing and there's no good reason *not* to have it here.
import salt.tracing.otel

# pylint: disable=unused-import
# Importing to make available from `tracing`.
from salt.tracing.base import SpanStatusType
from salt.tracing.bogo import BOGO_SPAN
from salt.tracing.setup import (
    TracingOptions,
    get_tracer,
    get_tracing_manager,
    setup_tracing,
)

log = logging.getLogger(__name__)


# Convenience fns
@contextmanager
def start_as_current_span(module_name, name):
    log.trace("start_as_current_span %s", module_name)

    # Runs at run-time, not load-time.
    _tracer = get_tracer(module_name)

    attributes = {}
    thread = threading.current_thread()
    attributes["span_thread"] = thread.name or thread.get_ident()

    if TracingOptions.traceback_new_spans:
        tbs = traceback.format_stack()
        for i, tb in enumerate(tbs):
            attributes[f"traceback{i:02}"] = tb

    gen_span_fn = functools.partial(
        _tracer.start_as_current_span, name, attributes=attributes
    )
    with gen_span_fn() as span:
        log.trace("start_as_current_span span context: %s", span.get_span_context())
        yield span


def with_span(func=None, prefix=None):
    def decorator(f):
        module_name = f.__module__
        function_name = f.__qualname__ if prefix is None else f"{prefix}.{f.__name__}"

        @wraps(f)
        def wrapper(*args, **kwargs):
            with start_as_current_span(module_name, function_name):
                return f(*args, **kwargs)

        return wrapper

    # If func is None, this function has been called during setup and the
    # decorator itself is needed. If func is not None, this function is
    # being called as the decorator itself, so the output of the decorator
    # function is needed.
    if func is None:
        return decorator
    else:
        return decorator(func)


def get_current_span():
    return get_tracing_manager().get_current_span()


def set_attributes(**attributes):
    span = get_current_span()
    span.set_attributes(attributes)


def set_span_status_error(msg):
    span_error_status = get_tracing_manager().make_span_status(SpanStatusType.ERROR)
    get_current_span().set_status(span_error_status, msg)


def record_exception_as_error(exc, msg):
    get_current_span().record_exception(exc)
    set_span_status_error(msg)
