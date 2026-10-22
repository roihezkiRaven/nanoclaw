import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("handoff", Path(__file__).with_name("browser-handoff.py"))
handoff = importlib.util.module_from_spec(spec)
spec.loader.exec_module(handoff)


class BrowserHandoffTest(unittest.TestCase):
    def test_only_local_dashboard_requests_are_accepted(self):
        self.assertTrue(handoff.allowed_headers(b"GET / HTTP/1.1\r\nHost: localhost:4848\r\nOrigin: http://localhost:4848"))
        self.assertFalse(handoff.allowed_headers(b"GET / HTTP/1.1\r\nHost: localhost:4848\r\nOrigin: https://evil.example"))
        self.assertFalse(handoff.allowed_headers(b"GET / HTTP/1.1\r\nHost: evil.example:4848"))
        self.assertFalse(handoff.allowed_headers(b"GET / HTTP/1.1\r\nHost: localhost:4848\r\nSec-Fetch-Site: cross-site"))

    def test_session_identity_cannot_inject_a_command_or_select_another_container(self):
        listing = "abcdef123456 ncl-fc17183a-sess-123-abc"
        self.assertEqual(handoff.container_for({"container_hostname": "abcdef123456"}, listing), "ncl-fc17183a-sess-123-abc")
        for hostname in ("$(bad)", "fedcba654321", "abcdef123456;touch file"):
            with self.assertRaises(ValueError):
                handoff.container_for({"container_hostname": hostname}, listing)


if __name__ == "__main__":
    unittest.main()
