"""Tests for bounded HTTPS archive downloads."""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parents[1] / "files"))

import download_https_archive


class FakeResponse:
    """Provide a small in-memory HTTP response for download tests."""

    def __init__(self, chunks, content_length=None):
        self.chunks = iter(chunks)
        self.headers = {}
        if content_length is not None:
            self.headers["Content-Length"] = str(content_length)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def geturl(self):
        return "https://example.invalid/archive.tar.gz"

    def read(self, size=-1):
        try:
            chunk = next(self.chunks)
        except StopIteration:
            return b""
        if len(chunk) > size:
            raise AssertionError("Downloader requested an oversized read")
        return chunk


class DownloadArchiveTests(unittest.TestCase):
    """Verify downloads enforce the archive-size limit before writing."""

    def test_rejects_oversized_content_length_before_reading(self):
        """Reject a declared oversized response without reading its body."""
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "archive.tar.gz"
            response = FakeResponse([b"must not be read"], content_length=11)
            with (
                mock.patch.object(
                    download_https_archive, "MAX_ARCHIVE_SIZE", 10
                ),
                mock.patch.object(
                    download_https_archive,
                    "build_opener",
                    return_value=mock.Mock(
                        open=mock.Mock(return_value=response)
                    ),
                ),
            ):
                with self.assertRaisesRegex(ValueError, "exceeds maximum size"):
                    download_https_archive.download(
                        "https://example.invalid/archive.tar.gz",
                        destination,
                    )
            self.assertFalse(destination.exists())

    def test_rejects_stream_larger_than_limit(self):
        """Stop writing as soon as a streamed response exceeds the limit."""
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "archive.tar.gz"
            destination.write_bytes(b"previous archive")
            response = FakeResponse([b"123456", b"78901"])
            with (
                mock.patch.object(
                    download_https_archive, "MAX_ARCHIVE_SIZE", 10
                ),
                mock.patch.object(
                    download_https_archive,
                    "DOWNLOAD_CHUNK_SIZE",
                    6,
                ),
                mock.patch.object(
                    download_https_archive,
                    "build_opener",
                    return_value=mock.Mock(
                        open=mock.Mock(return_value=response)
                    ),
                ),
            ):
                with self.assertRaisesRegex(ValueError, "exceeds maximum size"):
                    download_https_archive.download(
                        "https://example.invalid/archive.tar.gz",
                        destination,
                    )
            self.assertEqual(destination.read_bytes(), b"previous archive")
            temporary_files = list(
                Path(temporary).glob(".librenms-archive-*")
            )
            self.assertEqual(temporary_files, [])

    def test_accepts_response_at_size_limit(self):
        """Accept a response whose complete body fits the configured limit."""
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "archive.tar.gz"
            response = FakeResponse([b"12345", b"67890"])
            with (
                mock.patch.object(
                    download_https_archive, "MAX_ARCHIVE_SIZE", 10
                ),
                mock.patch.object(
                    download_https_archive,
                    "DOWNLOAD_CHUNK_SIZE",
                    5,
                ),
                mock.patch.object(
                    download_https_archive,
                    "build_opener",
                    return_value=mock.Mock(
                        open=mock.Mock(return_value=response)
                    ),
                ),
            ):
                download_https_archive.download(
                    "https://example.invalid/archive.tar.gz",
                    destination,
                )
            self.assertEqual(destination.read_bytes(), b"1234567890")


if __name__ == "__main__":
    unittest.main()
