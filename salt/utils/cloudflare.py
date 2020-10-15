# -*- coding: utf-8 -*-
"""
Cloudflare salt utilities
"""
from __future__ import absolute_import

# Import python libs
import hashlib
import logging
import logging.handlers
import socket  # Contemporary `localhost` grain uses `socket.gethostname()`, so we will do the same

import yaml

# prefer C bindings over python when available
SafeLoader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)

# Do not import any salt code to avoid potential import loops

hostname = socket.gethostname()
context_log_enabled = True
context_log = None  # Logger for template error contexts
DISABLE_CONFIG_NAME = "disable_template_context_log"
CONTEXT_LOG_PATH = "/var/log/salt/template_context"


def is_context_log_enabled():
    """
    Attempt to find config in master opts and then minion opts in their
    standard locations.  Since this module is intended to exist below the salt
    layer, to prevent import loops, the following will always be a hack, so:
    - We will not try to overcomplicate it (i.e. no `master.d/*`, `config.get`,
      or sneaking salt configs through pillar)
    - If the lookup fails, we will continue with the default

    :returns: ``False`` to disable sending template context info to a separate
        log and ``True`` to keep template context info separated into its own
        log file
    """
    for conf_path in ("/etc/salt/master", "/etc/salt/minion"):
        try:
            with open(conf_path) as conf_file:
                opts = yaml.load(conf_file, Loader=SafeLoader)
        except Exception as ex:
            continue

        if isinstance(opts, dict):
            if opts.get(DISABLE_CONFIG_NAME):
                return False

    # Fail back to default if config cannot be found
    return True


def setup_context_logger():
    """
    Set up the log used to store contexts for template (jinja, yaml) rendering
    errors
    """
    global context_log_enabled
    context_log_enabled = is_context_log_enabled()
    if not context_log_enabled:
        return

    formatter = logging.Formatter(
        "%(asctime)s,%(msecs)03d [%(name)-17s][%(levelname)-8s] %(message)s"
    )

    handler = logging.handlers.WatchedFileHandler(CONTEXT_LOG_PATH)
    handler.setFormatter(formatter)

    logger = logging.getLogger(__name__)
    logger.propagate = (
        False  # Do not send messages from this logger to the upstream handlers
    )
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)

    global context_log
    context_log = logger


def cf_redirect_context(exception, err_msg, line_num, context, trace=None, hash_size=7):
    """
    Do not send debug information that could contain sensitive data into normal
    data return streams that have wide visibility

    :param exception: The exception to raise; must be a
        `salt.exceptions.SaltRenderError` or derived exception
    :type exception: salt.exceptions.SaltRenderError

    :param err_msg: The error message to display
    :type err_msg: str

    :param line_num: Line position in source file/data containing error
    :type line_num: int

    :param context: All or part of source file/data containing erroneous line
    :type context: str

    :param trace: Python stack trace formatted into a string
    :type context: str

    :param hash_size: Number of hash characters to use to uniquely tag context
        lines
    :type hash_size: int
    """
    if context_log is None and context_log_enabled:
        setup_context_logger()

    if context_log_enabled:
        context_hash = hashlib.sha256(context.encode()).hexdigest()[:hash_size]
        exc_msg = exception(err_msg, line_num=line_num, buf=context, trace=trace)
        annotated_exc_msg = "\n".join(
            [
                "[{hash}] {line}".format(hash=context_hash, line=l)
                for l in str(exc_msg).split("\n")
            ]
        )
        context_log.error(annotated_exc_msg)
        raise exception(
            "{err} at line {line}: See template context log for details\n"
            "log host: {hostname}\n"
            "log hash: {hash}\n"
            "log data: \"grep -E '\[{hash}\]' {log_path}\""
            "".format(
                err=err_msg,
                line=line_num,
                hash=context_hash,
                hostname=hostname,
                log_path=CONTEXT_LOG_PATH,
            ),
        )
    else:  # Pass through to unmodified exception
        raise exception(err_msg, line_num=line_num, buf=context, trace=trace)
