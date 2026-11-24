"""Load a trusted SSH server public key without echoing configuration values."""

import base64
import binascii
import os
import struct

import paramiko
from paramiko.pkey import UnknownKeyType


def required_host_key(variable: str) -> paramiko.PKey:
    """Read an OpenSSH public key from an environment variable or fail closed."""
    fields = os.getenv(variable, "").split(maxsplit=2)
    try:
        if len(fields) < 2:
            raise ValueError("missing key type or data")
        key_type, encoded_key = fields[:2]
        data = base64.b64decode(encoded_key, validate=True)
        key = paramiko.PKey.from_type_string(key_type, data)
        if key.get_name() != key_type or key.asbytes() != data:
            raise ValueError("key type or data does not match")
    except (ValueError, TypeError, binascii.Error, struct.error, paramiko.SSHException, UnknownKeyType):
        raise ValueError(
            f"{variable} must contain the trusted server's OpenSSH public key "
            "(key type and base64 data). Ask your instructor or server administrator."
        ) from None
    return key
