import http.client
import importlib.util
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("p10_development_runner",
                                              ROOT / "scripts" / "development_qwen_v1.py")
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


class FakeHttp:
    def __init__(self, chunks, content_length=None, delay=0):
        self.chunks = list(chunks)
        self.headers = {} if content_length is None else {"Content-Length": content_length}
        self.delay = delay

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, _limit):
        if self.delay:
            time.sleep(self.delay)
        value = self.chunks.pop(0)
        if isinstance(value, BaseException):
            raise value
        return value


class BoundedTransportTests(unittest.TestCase):
    def test_complete_small_response(self):
        with patch.object(RUNNER.urllib.request, "urlopen", return_value=FakeHttp([b'{"ok":', b"true}", b""])):
            self.assertEqual(RUNNER.bounded_chat_bytes({}, deadline_s=2, max_bytes=100), b'{"ok":true}')

    def test_incomplete_read_is_ambiguous(self):
        failure = http.client.IncompleteRead(b'{"partial"', 12)
        with patch.object(RUNNER.urllib.request, "urlopen", return_value=FakeHttp([failure])):
            with self.assertRaises(RUNNER.AmbiguousTransportError):
                RUNNER.bounded_chat_bytes({}, deadline_s=2, max_bytes=100)

    def test_response_byte_budget_is_ambiguous(self):
        with patch.object(RUNNER.urllib.request, "urlopen", return_value=FakeHttp([b"123456", b""])):
            with self.assertRaisesRegex(RUNNER.AmbiguousTransportError, "response_byte_budget"):
                RUNNER.bounded_chat_bytes({}, deadline_s=2, max_bytes=5)

    def test_trickling_response_hits_overall_deadline(self):
        with patch.object(RUNNER.urllib.request, "urlopen",
                          return_value=FakeHttp([b"x", b"x", b"x"], delay=.025)):
            with self.assertRaisesRegex(RUNNER.AmbiguousTransportError, "whole_request_deadline"):
                RUNNER.bounded_chat_bytes({}, deadline_s=.01, max_bytes=100)

    def test_premature_eof_before_declared_length_is_ambiguous(self):
        with patch.object(RUNNER.urllib.request, "urlopen",
                          return_value=FakeHttp([b"{}", b""], content_length="5")):
            with self.assertRaisesRegex(RUNNER.AmbiguousTransportError, "response_length_mismatch"):
                RUNNER.bounded_chat_bytes({}, deadline_s=2, max_bytes=100)

    def test_deadline_interrupts_a_single_never_returning_read(self):
        with patch.object(RUNNER.urllib.request, "urlopen",
                          return_value=FakeHttp([b"x"], delay=.2)):
            with self.assertRaisesRegex(RUNNER.AmbiguousTransportError, "whole_request_deadline"):
                RUNNER.bounded_chat_bytes({}, deadline_s=.02, max_bytes=100)


if __name__ == "__main__":
    unittest.main()
