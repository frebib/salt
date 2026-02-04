import logging
import re
from typing import Dict

from salt.tracing.bogo import BogoTracingManager

_TRACING_MANAGER_CLASS = BogoTracingManager
_TM = None
# We cache these to avoid having to recreate them over and over again for a
# given module.
_TRACERS = {}  # __name__ to tracer lookup

log = logging.getLogger(__name__)


class TracingOptions:
    # Print traceback with log.trace on every new span.
    traceback_new_spans = False


# Called from salt.utils.parsers.TracingMixIn
def setup_tracing(opts):
    """
    Initializes the tracer as configured.

    tracing:
      module:
        otel:
          service_name: salt-master
          agent_host_name: 127.0.0.1
          agent_port: 8792
          log_spans_start_end: true
      debugging:
        backtraces: true

    :param dict opts: The Salt options dictionary
    """

    global _TM

    def _get_trace_mod_and_args(trace_config_dict):
        if not isinstance(trace_config_dict, dict):
            log.error("Invalid trace config: %s", trace_config_dict)
            return None, None

        _trace_mod_name, _trace_mod_kwargs = next(iter(trace_config_dict.items()))

        if _trace_mod_name == "base":
            log.error("'base' is not a valid trace module for use.")
            return None, None

        # salt.tracing fully at run-time to check for tracing modules.
        import salt.tracing

        _trace_mod = getattr(salt.tracing, _trace_mod_name, None)
        if _trace_mod is None:
            log.error("Tracing module %s doesn't exist.", _trace_mod_name)
            return None, None

        _trace_init_fn = getattr(_trace_mod, "initialize", None)
        if _trace_init_fn is None:
            log.error("Tracing module %s didn't load fully.", _trace_mod_name)
            return None, None

        return _trace_init_fn, _trace_mod_kwargs

    default_tracer_dict = {"module": {"bogo": None}}
    trace_opts = opts["tracing"] if opts.get("tracing") else default_tracer_dict

    log.debug("Initial trace config options: %s", trace_opts)
    trace_init_fn = None
    if "module" not in trace_opts:
        log.warning("No tracing module specified. Using bogo tracer.")
    else:
        trace_init_fn, trace_mod_kwargs = _get_trace_mod_and_args(trace_opts["module"])

    tracing_dbg = trace_opts.get("debugging", {})
    for k, v in tracing_dbg.items():
        if k == "backtraces":
            if not isinstance(v, bool):
                log.error("debugging: backtraces must be a bool, leaving False")
                v = False
            TracingOptions.traceback_new_spans = v

    # Fall-back to bogo tracer.
    if trace_init_fn is None:
        log.error("Problems loading tracing module. Using bogo tracer.")
        trace_init_fn, trace_mod_kwargs = _get_trace_mod_and_args(
            default_tracer_dict["module"]
        )

    # <trace_module>.initialize() should return a TraceManager.
    try:
        _TM = trace_init_fn(trace_mod_kwargs)
    except Exception as exc:  # pylint: disable=broad-except
        log.warning(
            "Couldn't execute trace module initializer: %s: %s. Using bogo tracer.",
            trace_init_fn,
            exc,
        )
        trace_init_fn, trace_mod_kwargs = _get_trace_mod_and_args(
            default_tracer_dict["module"]
        )
        _TM = trace_init_fn(trace_mod_kwargs)


def get_tracing_manager():
    global _TM

    if _TM is None:
        _TM = _TRACING_MANAGER_CLASS()
    return _TM


def get_tracer(module_name):
    global _TRACERS  # pylint: disable=global-variable-not-assigned

    # Get tracer at runtime, not load-time.
    tracer = _TRACERS.get(module_name, None)
    if tracer is None:
        tracer = get_tracing_manager().get_tracer(module_name)
        _TRACERS[module_name] = tracer
    return tracer
