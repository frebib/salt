import logging
from typing import Any, Optional

from opentelemetry.sdk.trace import sampling

from salt.tracing.otel.matching_sampler import MatchingSampler

log = logging.getLogger(__name__)

_DEFAULT_SAMPLER = sampling.ALWAYS_OFF

# Samplers that are pre-instantiated.
_STATIC_TOP_LEVEL_SAMPLERS = {
    "always_on": sampling.ALWAYS_ON,
    "always_off": sampling.ALWAYS_OFF,
}

# Samplers that take args and need to be instantiated.
_DYNAMIC_TOP_LEVEL_SAMPLERS = {
    "matching": MatchingSampler,
}


def get_sampler(sampler_opts: dict[str, Any]) -> sampling.Sampler:
    """Using the specified options get a sampler.  Return the default sampler
    if problems occur.
    """
    sampler_type: Optional[str] = None
    sampler: Optional[sampling.Sampler] = None

    # Return the default sampler if there are no sampler opts configured
    if not sampler_opts:
        return _DEFAULT_SAMPLER

    try:
        sampler_type = _get_sampler_type(sampler_opts)

    # pylint: disable=broad-except
    except Exception as exc:
        log.warning("Error getting sampler type from: %s: %s", sampler_opts, exc)

    if sampler_type:
        try:
            sampler = _get_or_create_sampler(sampler_type, sampler_opts)

        # pylint: disable=broad-except
        except Exception as exc:
            log.warning("Error getting or creating sampler: %s: %s", sampler_type, exc)

    if sampler is None:
        log.warning(
            "Falling back to default OTEL sampler: %s",
            _DEFAULT_SAMPLER.get_description(),
        )
        sampler = _DEFAULT_SAMPLER

    return sampler


def _get_sampler_type(sampler_opts: dict[str, Any]) -> Optional[str]:
    sampler_type = None
    if sampler_opts:
        if isinstance(sampler_opts, dict):
            sampler_type = sampler_opts.get("type")
            if sampler_type:
                sampler_type = sampler_type.lower()
        else:
            raise Exception("Sampler options must be a dict, ignoring sampler config.")
    else:
        raise Exception("No OTEL sampler configuration specified.")

    return sampler_type


def _get_or_create_sampler(
    sampler_type: str, sampler_opts: dict[str, Any]
) -> sampling.Sampler:
    sampler: sampling.Sampler
    dynamic_sampler_cls = _DYNAMIC_TOP_LEVEL_SAMPLERS.get(sampler_type, None)
    if dynamic_sampler_cls:
        # We need to instantiate the sampler
        return dynamic_sampler_cls(sampler_opts)
    else:
        static_sampler = _STATIC_TOP_LEVEL_SAMPLERS.get(sampler_type, None)
        if static_sampler is None:
            raise Exception(f"Unknown sampler type: {sampler_type}")
        else:
            return static_sampler
