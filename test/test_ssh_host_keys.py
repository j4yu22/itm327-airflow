"""Offline regressions for the required SSH host-key parser."""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import paramiko

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dags"))
from ssh_host_keys import required_host_key


class RequiredHostKeyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = paramiko.RSAKey.generate(2048)
        cls.pin = f"{cls.key.get_name()} {cls.key.get_base64()} instructor label"

    def test_openssh_public_key_and_comment(self):
        with patch.dict(os.environ, {"SFTP_HOST_KEY": self.pin}):
            parsed = required_host_key("SFTP_HOST_KEY")
        self.assertEqual(parsed.asbytes(), self.key.asbytes())

    def test_missing_invalid_mismatched_and_unsupported_pins_fail_closed(self):
        for value in ("", "missing-data", "ssh-rsa !!!", "ssh-ed25519 " + self.key.get_base64(),
                      "unsupported " + self.key.get_base64()):
            with self.subTest(value_type=value.partition(" ")[0]):
                with patch.dict(os.environ, {"SFTP_HOST_KEY": value}):
                    with self.assertRaisesRegex(ValueError, "^SFTP_HOST_KEY must contain"):
                        required_host_key("SFTP_HOST_KEY")


if __name__ == "__main__":
    unittest.main()
