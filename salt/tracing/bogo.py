"""
Provide a no-op solution for a tracer.
"""

import logging
from contextlib import contextmanager

from salt.tracing.base import BaseSpan, BaseTracer, BaseTracingManager

log = logging.getLogger(__name__)


class BogoTracer(BaseTracer):
    @contextmanager
    def start_as_current_span(
        self, name, *args, **kwargs
    ):  # pylint: disable=arguments-differ
        """
        Context manager for creating a new span and set it as the current
        span.
        """
        yield self.start_span(name, *args, **kwargs)

    def start_span(self, name, *args, **kwargs):  # pylint: disable=arguments-differ
        """
        Create a new span.  Start the span without setting it as the current
        span in the context.
        """
        return BOGO_SPAN


class BogoTracingManager(BaseTracingManager):
    @classmethod
    def initialize(cls, *args, **kwargs):
        pass

    @classmethod
    def get_tracer(cls, *args):  # pylint: disable=arguments-differ
        return BogoTracer()

    @classmethod
    def get_current_span(cls, context=None):
        return BOGO_SPAN

    @classmethod
    def _xlate_status(cls, code):
        return None


class BogoSpan(BaseSpan):
    """A bogus span represents a single operation within a trace."""

    def to_json(self):
        return ""

    # pylint: disable=unnecessary-pass
    def end(self, end_time=None):
        """Sets the current time as the span's end time.

        The span's end time is the wall time at which the operation finished.

        Only the first call to `end` should modify the span, and
        implementations are free to ignore or raise on further calls.
        """
        pass

    def get_span_context(self):
        """Gets the span's SpanContext.

        Get an immutable, serializable identifier for this span that can be
        used to create new child spans.

        Returns:
            A :class:`opentelemetry.trace.SpanContext` with a copy of this span's immutable state.
        """
        pass

    def set_attributes(self, attributes):
        """Sets Attributes.

        Sets Attributes with the key and value passed as arguments dict.

        Note: The behavior of `None` value attributes is undefined, and hence
        strongly discouraged. It is also preferred to set attributes at span
        creation, instead of calling this method later since samplers can only
        consider information already present during span creation.
        """
        pass

    def set_attribute(self, key, value):
        """Sets an Attribute.

        Sets a single Attribute with the key and value passed as arguments.

        Note: The behavior of `None` value attributes is undefined, and hence
        strongly discouraged. It is also preferred to set attributes at span
        creation, instead of calling this method later since samplers can only
        consider information already present during span creation.
        """
        pass

    def add_event(
        self,
        name,
        attributes=None,
        timestamp=None,
    ):
        """Adds an `Event`.

        Adds a single `Event` with the name and, optionally, a timestamp and
        attributes passed as arguments. Implementations should generate a
        timestamp if the `timestamp` argument is omitted.
        """
        pass

    def update_name(self, name):
        """Updates the `Span` name.

        This will override the name provided via :func:`opentelemetry.trace.Tracer.start_span`.

        Upon this update, any sampling behavior based on Span name will depend
        on the implementation.
        """

    def is_recording(self):
        """Returns whether this span will be recorded.

        Returns true if this Span is active and recording information like
        events with the add_event operation and attributes using set_attribute.
        """
        return True

    def set_status(
        self,
        status,
        description=None,
    ):
        """Sets the Status of the Span. If used, this will override the default
        Span status.
        """
        pass

    def record_exception(
        self,
        exception,
        attributes=None,
        timestamp=None,
        escaped=False,
    ):
        """Records an exception as a span event."""
        pass

    def __enter__(self):
        """Invoked when `Span` is used as a context manager.

        Returns the `Span` itself.
        """
        return self

    def __exit__(
        self,
        exc_type,
        exc_val,
        exc_tb,
    ):
        """Ends context manager and calls `end` on the `Span`."""
        self.end()


def initialize(opts):
    BogoTracingManager.initialize(opts)


BOGO_SPAN = BogoSpan()
