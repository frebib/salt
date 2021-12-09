"""
Audit logging for salt
"""

import hashlib
import hmac
import logging
import socket
import uuid

import salt._logging
import salt.payload

# Cache hostname lookup; cannot use `platform.node()` for this because of
# module namespace collision within salt package
hostname = socket.gethostname()
del socket

log = logging.getLogger(__name__)
audit_log = salt._logging.get_audit_logger()


class Audit(object):
    """
    Audit logger
    """

    def __init__(self, opts):
        """
        Setup audit logger
        """
        self.opts = opts
        self.serial = salt.payload.Serial(self.opts)

    def _audit_log_hash_value(self, field_value):
        """
        HMAC hash a field value in the load
        """
        # This code is not python2 compatible
        field_str = (
            str(field_value) if not isinstance(field_value, str) else field_value
        )
        return (
            "<hashed>"
            + hmac.new(
                self.opts["audit_log_hmac_key"],
                field_str.encode(__salt_system_encoding__),
                hashlib.sha256,
            ).hexdigest()
        )

    def _filter_audit_req(self, load):
        """
        Filter or otherwise transform fields in the request load before sending
        the request to the audit log
        """
        for cmd_pat in (load["cmd"], "*"):
            if cmd_pat in self.opts["audit_log_exclude_req_fields"]:
                for field in self.opts["audit_log_exclude_req_fields"][cmd_pat]:
                    if field in load:
                        load[field] = "<filtered from audit log>"

            if cmd_pat in self.opts["audit_log_hash_req_fields"]:
                for field_pat in self.opts["audit_log_hash_req_fields"][cmd_pat]:
                    if field_pat == "*":
                        load = {
                            f: load[f]
                            if f == "cmd"
                            else self._audit_log_hash_value(load[f])
                            for f in load
                        }
                        break
                    elif field_pat in load:
                        load[field_pat] = self._audit_log_hash_value(load[field_pat])
        return load

    def _filter_audit_ret(self, data, req_opts):
        """
        Filter or otherwise transform fields in the return before sending it to
        the audit log
        """
        ret = (data, req_opts)
        if req_opts.get("key"):
            if req_opts["key"] in self.opts["audit_log_exclude_ret_data"]:
                ret = ("<filtered from audit log>", req_opts)
            elif req_opts["key"] in self.opts["audit_log_hash_ret_data"]:
                ret = (self._audit_log_hash_value(data), req_opts)
        return ret

    def audit_req(self, payload):
        """
        Send incoming payloads to the audit log
        """
        audit_id = uuid.uuid4().hex
        try:
            # Copy request payload
            payload = self.serial.loads(self.serial.dumps(payload))
            if (
                not payload["load"].get("cmd", "")
                in self.opts["audit_log_exclude_cmds"]
            ):
                payload["load"] = self._filter_audit_req(payload["load"])
                audit_log.info(
                    {
                        "request": payload,
                        "master": self.opts.get("id"),
                        "host": hostname,
                        "audit_id": audit_id,
                    }
                )

                # Return unique hash to be used to correlate return log with
                # request log
                return audit_id
        except Exception as ex:
            try:
                audit_log.error(
                    {
                        "request": "Cannot log request: {}".format(ex),
                        "master": self.opts.get("id"),
                        "host": hostname,
                        "audit_id": audit_id,
                    }
                )
            except Exception as ex_ex:
                log.error("Cannot audit log payload for {}: {}".format(audit_id, ex_ex))
        return None

    def audit_ret(self, ret, audit_id):
        """
        Send outgoing return data to the audit log

        Filtering the response data is more challenging because the response
        data, which although may have a type convention, originates from
        calling whatever ``cmd`` the user requested.  In addition, many of the
        ``AESFuncs`` and ``ClearFuncs`` called return the results of other
        functions.  The advice is that we need to do the python thing and be
        apprehensive about each return's structure.
        """
        try:
            if isinstance(ret, (tuple, list)):
                # It probably contains two dicts here with the fields we're
                # looking for
                if len(ret) == 2 and isinstance(ret[1], dict):
                    # Copy return data
                    data, req_opts = self.serial.loads(self.serial.dumps(ret))
                    ret_msg = self._filter_audit_ret(data, req_opts)
                    audit_log.info(
                        {
                            "return": ret_msg,
                            "master": self.opts.get("id"),
                            "host": hostname,
                            "audit_id": audit_id,
                        }
                    )
                    return
            audit_log.warning(
                {
                    "return": "Unknown return format detected: return data will not be filtered/hashed",
                    "master": self.opts.get("id"),
                    "host": hostname,
                    "audit_id": audit_id,
                }
            )
            audit_log.info(
                {
                    "return": ret,
                    "master": self.opts.get("id"),
                    "host": hostname,
                    "audit_id": audit_id,
                }
            )

        except Exception as ex:
            try:
                audit_log.error(
                    {
                        "return": "Cannot log return: {}".format(ex),
                        "master": self.opts.get("id"),
                        "host": hostname,
                        "audit_id": audit_id,
                    }
                )
            except Exception as ex_ex:
                log.error(
                    "Cannot audit log return payload for {}: {}".format(audit_id, ex_ex)
                )
