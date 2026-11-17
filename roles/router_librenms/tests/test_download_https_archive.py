"""Tests for bounded HTTPS archive downloads."""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parents[1] / "files"))

import download_https_archive


class FakeResponse:
    """Small response double for download limit tests."""

    headers = {}

    def __init__(self, chunks):
        self.chunks = iter(chunks)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def geturl(self):
        return "https://example.invalid/archive.tar.gz"

    def read(self, _size):
        return next(self.chunks, b"")


class FakeOpener:
    """Return a configured response without making a network request."""

    def __init__(self, response):
        self.response = response

    def open(self, _url, timeout):
        return self.response


class DownloadArchiveTests(unittest.TestCase):
    """Verify the download limit is enforced before excess data is written."""

    def test_rejects_download_larger_than_limit(self):
        response = FakeResponse([b"ab", b"cd"])
        opener = FakeOpener(response)

        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "archive.tar.gz"
            with (
                mock.patch.object(
                    download_https_archive,
                    "MAX_ARCHIVE_SIZE",
                    3,
                ),
                mock.patch.object(
                    download_https_archive,
                    "build_opener",
                    return_value=opener,
                ),
            ):
                with self.assertRaisesRegex(ValueError, "maximum size"):
                    download_https_archive.download(
                        "https://example.invalid/archive.tar.gz",
                        destination,
                    )

            self.assertFalse(destination.exists())
            self.assertEqual(list(Path(temporary).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
