# -*- coding: utf-8 -*-
"""
An engine, which tries to perform TPM attestation to prove minion's key to the master
"""

# Import python libs

import binascii
import cryptography.hazmat.backends
import cryptography.hazmat.primitives.serialization
import cryptography.hazmat.primitives.hashes
import cryptography.hazmat.primitives.hmac
import cryptography.hazmat.primitives.kdf.hkdf
import ctypes
import ctypes.util
import datetime
import inspect
import logging
import os
import platform
import subprocess

# Import salt libs
import salt.crypt
import salt.utils.error
import salt.utils.event
import salt.minion

from salt.ext import six

try:
    import salt.utils.files

    _fopen = getattr(salt.utils.files, "fopen", salt.utils.fopen)
except ImportError:
    _fopen = salt.utils.fopen

log = logging.getLogger(__name__)

# the logger for the salt.crypt module, which does master authentication
cryptlogger = logging.getLogger("salt.crypt")

# for memfd_create(2)
libc = ctypes.CDLL(ctypes.util.find_library("c"))


def _ensure_binary(s, encoding="latin-1", errors="strict"):
    # Try to convert unicode messages to bytes
    # This is required for backwards compatibility to support 2017 minion
    # Will be obsolete when we upgrade to msgpack > 0.4.6 with use_bin_type=True
    if isinstance(s, six.binary_type):
        try:
            return s.decode("utf-8").encode(encoding, errors)
        except UnicodeError:
            return s
    if isinstance(s, six.text_type):
        return s.encode(encoding, errors)
    raise TypeError("not expecting type '%s'" % type(s))


# memfd_create(2) does not have a python wrapper
def _memfd_create(name):
    # older glibc (ex. in Debian Stretch) does not have a memfd_create(2)
    # wrapper, so we use the generic syscall(2) instead
    if hasattr(libc, "memfd_create"):
        return libc.memfd_create(ctypes.c_char_p(name), 0)

    arch = platform.machine()
    # https://chromium.googlesource.com/chromiumos/docs/+/master/constants/syscalls.md
    if hasattr(libc, "syscall"):
        if arch == "x86_64":
            return libc.syscall(319, ctypes.c_char_p(name), 0)
        if arch == "aarch64":
            return libc.syscall(279, ctypes.c_char_p(name), 0)

    # should not get here
    return -1


class PendingKeyHandler(logging.NullHandler):
    """
    Custom log handler which monitors salt crypt logger for messages about
    master caching minion keys.

    Salt does not have any API to get this status in an external module, so
    this is rather sane way to make the TPM attestation event driven without
    patching the code.
    """

    def handle(self, record):
        # look for 'pending key' message
        # we hope it will not change, because salt has other more important
        # things to fix in their thousands of issues on github
        if (
            "The Salt Master has cached the public key for this node"
            in record.getMessage()
        ):
            # the log says that the master cached the key, but "conveniently" omits which master :(
            # but salt.crypt.AsyncAuth class, which is the caller of this code should have the master
            # in its opts attribute
            async_auth = inspect.currentframe().f_back
            while async_auth and not isinstance(
                async_auth.f_locals.get("self"), salt.crypt.AsyncAuth
            ):
                async_auth = async_auth.f_back
            if async_auth:
                # notify the code below that the master needs key acceptance
                __salt__["event.fire"](
                    {"master": async_auth.f_locals["self"].opts["master"]},
                    "minion/auth/pending",
                )
            else:
                log.info("Pending key notification from unknown source")


def __virtual__():
    # tpm tools will check TPM2TOOLS_TCTI for the location of the TPM
    # in dev we need to direct them to the TPM emulator
    # in prod we want them to use /dev/tpmrm0 (in-kernel TPM resource manager)
    tpm_device = os.getenv("TPM2TOOLS_TCTI")
    if not tpm_device:
        log.error("Not loading TPM certify engine: TPM2TOOLS_TCTI is not defined")
        return False

    if tpm_device.startswith("device:") and not os.path.exists(
        tpm_device[len("device:") :]
    ):
        log.error(
            "Not loading TPM certify engine: %s not found", tpm_device[len("device:") :]
        )
        return False

    # salt will create an instance of the engine for each master, but we want
    # to attach our custom handler only once
    # Logger class however allows you to add a handler, but not to check if a
    # specific handler is already added, so we use a custom attribute on the
    # logger object as a marker
    # this code requires no locks as even with two or more defined masters this
    # function is called from a single process
    if not hasattr(cryptlogger, "pending_key_handler"):
        cryptlogger.pending_key_handler = PendingKeyHandler()
        cryptlogger.addHandler(cryptlogger.pending_key_handler)
        log.debug("Attached PendingKeyHandler to salt.crypt logger")

    return True


# cryptography.io backend
_backend = cryptography.hazmat.backends.default_backend()

_TPM2_ENDORSEMENT_KEY_HANDLE = 0x81010001
_TPM2_ATTESTATION_KEY_HANDLE = 0x81010002


def _master_communicate(minion_id, preshared_secret, channel, data):
    # cmd: wheel - we want to call a tpm_attest wheel module
    # eauth: potential_minions - we want to authenticate using potential_minions external authentication module
    # username and password for the authentication: password is derived from
    # the preshared secret, minion id and current date
    kdf = cryptography.hazmat.primitives.kdf.hkdf.HKDF(
        algorithm=cryptography.hazmat.primitives.hashes.SHA256(),
        length=32,
        salt="{}-{}".format(minion_id, datetime.date.today()).encode(),
        info=b"salt-tpm",
        backend=_backend,
    )
    message = {
        "cmd": "wheel",
        "eauth": "potential_minions",
        "username": minion_id,
        "password": kdf.derive(preshared_secret),
    }
    # merge command-specific arguments
    message.update(data)
    resp = channel.send(message)
    if resp.get("data", {}).get("success"):
        return resp.get("data", {}).get("return")
    else:
        log.warning("Master request failed: %s", resp.get("data", {}).get("return"))
        return False


# create persistent TPM endorsement and attestation keys if needed
def _create_keys():
    key_list_out = subprocess.check_output(["tpm2_getcap", "handles-persistent"])
    if not hex(_TPM2_ENDORSEMENT_KEY_HANDLE) in key_list_out:
        log.info("Endorsement key not found, creating...")
        res = subprocess.call(
            [
                "tpm2_createek",
                "-c",
                hex(_TPM2_ENDORSEMENT_KEY_HANDLE),
                "-G",
                "rsa",
            ]
        )
        if res != 0:
            log.error("Failed to create TPM endorsement key")

    if not hex(_TPM2_ATTESTATION_KEY_HANDLE) in key_list_out:
        log.info("Attestation key not found, creating...")
        res = subprocess.call(
            [
                "tpm2_createak",
                "-C",
                hex(_TPM2_ENDORSEMENT_KEY_HANDLE),
                "-c",
                hex(_TPM2_ATTESTATION_KEY_HANDLE),
                "-G",
                "rsa",
            ]
        )
        if res != 0:
            log.error("Failed to create TPM attestation key")


def _tpm_getpub(handle):
    pub_r, pub_w = os.pipe()
    res = subprocess.call(
        ["tpm2_readpublic", "-c", handle, "-o", "/proc/self/fd/{}".format(pub_w)]
    )
    if 0 == res:
        pub = os.read(pub_r, 4096)
    for f in [pub_w, pub_r]:
        os.close(f)
    # reading some keys creates a transient handle (like an in-memory context)
    # and you can't have more than 3 at a time (without using a resource
    # manager, which we don't use here for tests)
    # flush all transient handles after each key read
    subprocess.call(["tpm2_flushcontext", "--transient-object"])
    if 0 == res:
        return pub
    else:
        log.error("Failed to read the public key with handle %s: %d", handle, res)
        return False


def _tpm_quote(nonce):
    quote_r, quote_w = os.pipe()
    sig_r, sig_w = os.pipe()
    res = subprocess.call(
        [
            "tpm2_quote",
            "-c",
            hex(_TPM2_ATTESTATION_KEY_HANDLE),
            "-l",
            "sha256:7",
            "-q",
            binascii.hexlify(nonce),
            "-m",
            "/proc/self/fd/{}".format(quote_w),
            "-s",
            "/proc/self/fd/{}".format(sig_w),
        ]
    )
    if 0 == res:
        quote = os.read(quote_r, 4096)
        sig = os.read(sig_r, 4096)
    for f in [quote_w, quote_r, sig_w, sig_r]:
        os.close(f)
    if 0 == res:
        return quote, sig
    else:
        log.error("Failed to generate a TPM quote: %d", res)
        return False, False


def _tpm_activate_credential(encrypted):
    # tpm2_activatecredential does not accept NULL password as a default, so
    # need to specify the auth via a session
    # tpm2_policysecret below will read the input file, truncate it and write
    # the result back, so we can't use a unidirectional pipe here
    # use memfd_create(2) instead
    sess_fd = _memfd_create("session.ctx")
    if sess_fd <= 0:
        log.error("Failed to create a memory file: %d", sess_fd)
        return False
    # create an auth session object
    res = subprocess.call(
        [
            "tpm2_startauthsession",
            "--policy-session",
            "-S",
            "/proc/self/fd/{}".format(sess_fd),
        ]
    )
    if 0 != res:
        log.error("Failed to start an auth session with the TPM: %d", res)
        os.close(sess_fd)
        return False
    # enable endorsement authorization on the session
    res = subprocess.call(
        [
            "tpm2_policysecret",
            "-S",
            "/proc/self/fd/{}".format(sess_fd),
            "-c",
            "e",
        ]
    )
    if 0 != res:
        log.error(
            "Failed to attach endorsement autorization to the auth session: %d", res
        )
        os.close(sess_fd)
        return False
    cred_r, cred_w = os.pipe()
    decrypted_r, decrypted_w = os.pipe()
    os.write(cred_w, encrypted)
    res = subprocess.call(
        [
            "tpm2_activatecredential",
            "-C",
            hex(_TPM2_ENDORSEMENT_KEY_HANDLE),
            "-c",
            hex(_TPM2_ATTESTATION_KEY_HANDLE),
            "-i",
            "/proc/self/fd/{}".format(cred_r),
            "-o",
            "/proc/self/fd/{}".format(decrypted_w),
            "-P",
            "session:/proc/self/fd/{}".format(sess_fd),
        ]
    )
    if 0 == res:
        decrypted = os.read(decrypted_r, 4096)
    for f in [cred_r, cred_w, decrypted_r, decrypted_w, sess_fd]:
        os.close(f)
    if 0 == res:
        return decrypted
    else:
        log.error("Failed to decrypt a token from the master: %d", res)
        return False


def init_session(minion_id, preshared_secret, channel):
    args = {"fun": "tpm_attest.init_session", "id": minion_id}
    resp = _master_communicate(minion_id, preshared_secret, channel, args)
    return resp


def get_token(minion_id, preshared_secret, channel, quote, sig, attest_pub):
    args = {
        "fun": "tpm_attest.get_token",
        "id": minion_id,
        "quote": quote,
        "sig": sig,
        "attest_pub": attest_pub,
    }
    resp = _master_communicate(minion_id, preshared_secret, channel, args)
    return resp


def confirm_key(minion_id, preshared_secret, channel, opts, master_token):
    with _fopen(os.path.join(opts["pki_dir"], "minion.pub")) as rfh:
        pub = cryptography.hazmat.primitives.serialization.load_pem_public_key(
            rfh.read(), backend=_backend
        )
    hmac = cryptography.hazmat.primitives.hmac.HMAC(
        master_token, cryptography.hazmat.primitives.hashes.SHA256(), backend=_backend
    )
    hmac.update(
        pub.public_bytes(
            cryptography.hazmat.primitives.serialization.Encoding.DER,
            cryptography.hazmat.primitives.serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    args = {"fun": "tpm_attest.confirm_key", "id": minion_id, "mac": hmac.finalize()}
    resp = _master_communicate(minion_id, preshared_secret, channel, args)
    return resp


def do_tpm_attestation():
    # create TPM persistent keys, if they do not exist already
    _create_keys()
    # read the TPM attestation public key
    attest_pub = _tpm_getpub(hex(_TPM2_ATTESTATION_KEY_HANDLE))
    if not attest_pub:
        log.error("Failed to read the TPM attestation public key")
        return
    # create a minion
    minion = salt.minion.Minion(__opts__)
    # resolve salt master address
    minion.opts.update(salt.minion.resolve_dns(minion.opts))
    minion_id = minion.opts["id"]
    preshared_secret = binascii.unhexlify(
        minion.opts.get("tpm_attestation", {}).get("preauth_key", "")
    )
    if (
        not preshared_secret
        and minion.opts.get("grains", {}).get("environment") == "dev"
    ):
        # default dev preshared secret
        # see https://bitbucket.cfdata.org/projects/DEVOPS/repos/salt/browse/conf/dev-master
        preshared_secret = binascii.unhexlify(
            "a2407f2e386a8ccb997aba4027c7611272ff73f6eb2121e719045d53b3f34fa0"
        )
    if not preshared_secret:
        log.error("Master preshared_secret is not defined in the configuration file")
        return
    # create a request channel to the master
    master_channel = salt.transport.client.ReqChannel.factory(
        minion.opts, crypt="clear"
    )
    nonce = init_session(minion_id, preshared_secret, master_channel)
    if not nonce:
        log.error("Failed to obtain the nonce from the master")
        return
    else:
        nonce = _ensure_binary(nonce)
    quote, sig = _tpm_quote(nonce)
    if not quote:
        return
    encrypted_token = get_token(
        minion_id, preshared_secret, master_channel, quote, sig, attest_pub
    )
    if not encrypted_token:
        log.error("Failed to obtain the encrypted token from the master")
        return
    token = _tpm_activate_credential(_ensure_binary(encrypted_token))
    if not token:
        return
    confirm_key(minion_id, preshared_secret, master_channel, minion.opts, token)


def start():
    """
    Listen to minion/auth/pending event and trigger TPM attestation with
    the master
    """
    if __opts__["__role"] == "master":
        # this function is run in a dedicated engine process, so it should
        # be OK to throw an exception here
        salt.utils.error.raise_error(
            message="The engine should run on the minion side only"
        )

    # with multiple masters defined the minion will start a separate engine for
    # each master and will pass opts with a single master defined for this
    # engine
    master = __opts__["master"]
    log.debug("Starting tpmcertify engine for master %s", master)

    event_bus = salt.utils.event.get_event(
        "minion",
        transport=__opts__["transport"],
        opts=__opts__,
        sock_dir=__opts__["sock_dir"],
        listen=True,
    )

    while True:
        # in normal case the keys should be accepted, so the code should sleep
        # for this we use the "indefinite" wait with a blocking call
        event = event_bus.get_event(tag="minion/auth/pending", wait=0)
        # we only process events for the master we are responsible for
        if event and event.get("master") == master:
            log.info("Attempting TPM attestation with master %s", master)
            do_tpm_attestation()
            # TPM attestaion takes time, so it is likely that new events are
            # queued by the time it completes, so clean up the queue
            # even if attestation failed, the minion should retry the
            # authentication, so a new event should retrigger the
            # attestation later
            event = event_bus.get_event(tag="minion/auth/pending", no_block=True)
            while event:
                event = event_bus.get_event(tag="minion/auth/pending", no_block=True)
