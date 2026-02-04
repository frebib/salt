"""
Base class for TracingManager, Tracer, Span and independent status type.
"""

import abc
import enum
from contextlib import contextmanager


class BaseTracingManager(metaclass=abc.ABCMeta):
    """
    Abstract base class for a class that makes it possible to plugin
    tracing systems.
    """

    @classmethod
    @abc.abstractmethod
    def initialize(cls, *args, **kwargs):
        """
        Initialize the tracing manager.
        """

    @classmethod
    @abc.abstractmethod
    def get_tracer(cls, name):
        """
        Return the tracer.
        """

    @classmethod
    @abc.abstractmethod
    def get_current_span(cls, context=None):
        """Return the current span."""

    @classmethod
    def make_span_status(cls, code):
        """Return a status object that can be passed to set_status."""
        if not isinstance(code, SpanStatusType):
            # pylint: disable=broad-exception-raised
            raise Exception(f"Bad status code: {code}")
        return cls._xlate_status(code)

    @classmethod
    @abc.abstractmethod
    def _xlate_status(cls, code):
        """Translate the code into a value that the tracer can use."""


class BaseTracer(metaclass=abc.ABCMeta):
    @contextmanager
    @abc.abstractmethod
    def start_as_current_span(self, name, **kwargs):
        """
        Context manager for creating a new span and set it as the current
        span.
        """

    @abc.abstractmethod
    def start_span(self, name, **kwargs):
        """
        Create a new span.  Start the span without setting it as the current
        span in the context.
        """


class BaseSpan(metaclass=abc.ABCMeta):
    """A span represents a single operation within a trace."""

    @abc.abstractmethod
    def to_json(self):
        pass

    @abc.abstractmethod
    def end(self, end_time=None):
        """Sets the current time as the span's end time.

        The span's end time is the wall time at which the operation finished.

        Only the first call to `end` should modify the span, and
        implementations are free to ignore or raise on further calls.
        """

    @abc.abstractmethod
    def get_span_context(self):
        """Gets the span's SpanContext.

        Get an immutable, serializable identifier for this span that can be
        used to create new child spans.

        Returns:
            A :class:`opentelemetry.trace.SpanContext` with a copy of this span's immutable state.
        """

    @abc.abstractmethod
    def set_attributes(self, attributes):
        """Sets Attributes.

        Sets Attributes with the key and value passed as arguments dict.

        Note: The behavior of `None` value attributes is undefined, and hence
        strongly discouraged. It is also preferred to set attributes at span
        creation, instead of calling this method later since samplers can only
        consider information already present during span creation.
        """

    @abc.abstractmethod
    def set_attribute(self, key, value):
        """Sets an Attribute.

        Sets a single Attribute with the key and value passed as arguments.

        Note: The behavior of `None` value attributes is undefined, and hence
        strongly discouraged. It is also preferred to set attributes at span
        creation, instead of calling this method later since samplers can only
        consider information already present during span creation.
        """

    @abc.abstractmethod
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

    @abc.abstractmethod
    def update_name(self, name):
        """Updates the `Span` name.

        This will override the name provided via :func:`opentelemetry.trace.Tracer.start_span`.

        Upon this update, any sampling behavior based on Span name will depend
        on the implementation.
        """

    @abc.abstractmethod
    def is_recording(self):
        """Returns whether this span will be recorded.

        Returns true if this Span is active and recording information like
        events with the add_event operation and attributes using set_attribute.
        """

    @abc.abstractmethod
    def set_status(
        self,
        status,
        description=None,
    ):
        """Sets the Status of the Span. If used, this will override the default
        Span status.
        """

    @abc.abstractmethod
    def record_exception(
        self,
        exception,
        attributes=None,
        timestamp=None,
        escaped=False,
    ):
        """Records an exception as a span event."""

    @abc.abstractmethod
    def __enter__(self):
        """Invoked when `Span` is used as a context manager.

        Returns the `Span` itself.
        """

    @abc.abstractmethod
    def __exit__(
        self,
        exc_type,
        exc_val,
        exc_tb,
    ):
        """Ends context manager and calls `end` on the `Span`."""


class SpanStatusType(enum.Enum):
    """
    A generic span status type.
    """

    UNSET = 0
    OK = 1
    ERROR = 2
