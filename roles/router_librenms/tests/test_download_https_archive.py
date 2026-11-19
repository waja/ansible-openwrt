"""Tests for bounded HTTPS archive downloads."""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parents[1] / "files"))

import download_https_archive


class FakeSocket:
    """Track socket timeout updates made by the downloader."""

    def settimeout(self, _timeout):
        pass


class FakeRaw:
    def __init__(self):
        self._sock = FakeSocket()


class FakeFile:
    def __init__(self):
        self.raw = FakeRaw()


class FakeResponse:
    """Small response double for download limit tests."""

    def __init__(self, chunks, content_length=None):
        self.chunks = iter(chunks)
        self.fp = FakeFile()
        self.headers = (
            {} if content_length is None
            else {"Content-Length": content_length}
        )

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def geturl(self):
        return "https://example.invalid/archive.tar.gz"

    def read1(self, _size):
        return next(self.chunks, b"")


class FakeOpener:
    """Return a configured response without making a network request."""

    def __init__(self, response):
        self.response = response

    def open(self, _url, timeout):
        return self.response


class DownloadArchiveTests(unittest.TestCase):
    """Verify the download limit and temporary-file cleanup."""

    def download(self, temporary, response, limit=3):
        destination = Path(temporary) / "archive.tar.gz"
        with (
            mock.patch.object(
                download_https_archive, "MAX_ARCHIVE_SIZE", limit
            ),
            mock.patch.object(
                download_https_archive,
                "build_opener",
                return_value=FakeOpener(response),
            ),
        ):
            download_https_archive.download(
                "https://example.invalid/archive.tar.gz", destination
            )
        return destination

    def test_downloads_exact_limit_and_preserves_contents(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination = self.download(
                temporary, FakeResponse([b"ab", b"c"], "3")
            )
            self.assertEqual(destination.read_bytes(), b"abc")
            self.assertEqual(
                {path.name for path in Path(temporary).iterdir()},
                {"archive.tar.gz"},
            )

    def test_rejects_invalid_content_length_and_cleans_up(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, "invalid Content-Length"):
                self.download(temporary, FakeResponse([], "unknown"))
            self.assertEqual(list(Path(temporary).iterdir()), [])

    def test_rejects_oversized_content_length_and_cleans_up(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, "exceeds maximum size"):
                self.download(temporary, FakeResponse([], "4"))
            self.assertEqual(list(Path(temporary).iterdir()), [])

    def test_rejects_stream_larger_than_declared_length(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, "exceeds maximum size"):
                self.download(temporary, FakeResponse([b"ab", b"cd"], "2"))
            self.assertEqual(list(Path(temporary).iterdir()), [])

    def test_enforces_total_download_deadline(self):
        with tempfile.TemporaryDirectory() as temporary:
            response = FakeResponse([b"a", b"b"])
            with mock.patch.object(
                download_https_archive, "DOWNLOAD_TIMEOUT", 10
            ), mock.patch.object(
                download_https_archive.time,
                "monotonic",
                side_effect=[0, 0, 11],
            ):
                with self.assertRaisesRegex(TimeoutError, "timed out"):
                    self.download(temporary, response)
            self.assertEqual(list(Path(temporary).iterdir()), [])

    def test_rejects_download_larger_than_limit_without_content_length(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, "maximum size"):
                self.download(temporary, FakeResponse([b"ab", b"cd"]))
            self.assertEqual(list(Path(temporary).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
