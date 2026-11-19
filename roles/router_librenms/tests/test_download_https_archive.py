"""Tests for bounded HTTPS archive downloads."""

import socket
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parents[1] / "files"))

import download_https_archive


class FakeResponse:
    """Small response double for download limit tests."""

    def __init__(self, chunks, content_length=None, on_read=None):
        self.chunks = iter(chunks)
        self.on_read = on_read
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
        if self.on_read:
            self.on_read()
        return next(self.chunks, b"")


class FakeOpener:
    """Return a configured response without making a network request."""

    def __init__(self, response, on_open=None):
        self.response = response
        self.on_open = on_open

    def open(self, _url, timeout):
        if self.on_open:
            self.on_open()
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

    def _assert_download_deadline(self, timeout_stage):
        with tempfile.TemporaryDirectory() as temporary:
            previous_handler = object()
            registered_handlers = []
            alarm = mock.Mock()

            def register_handler(_signum, handler):
                registered_handlers.append(handler)
                return previous_handler

            def trigger_timeout():
                self.assertEqual(alarm.call_args_list, [mock.call(
                    download_https_archive.DOWNLOAD_TIMEOUT
                )])
                registered_handlers[0](None, None)

            response = FakeResponse(
                [b"a"],
                on_read=(
                    trigger_timeout if timeout_stage == "read" else None
                ),
            )
            opener = FakeOpener(
                response,
                on_open=(
                    trigger_timeout if timeout_stage == "open" else None
                ),
            )
            with mock.patch.object(
                download_https_archive, "build_opener",
                return_value=opener,
            ), mock.patch.object(
                download_https_archive.signal, "signal",
                side_effect=register_handler,
            ) as register, mock.patch.object(
                download_https_archive.signal, "alarm", alarm
            ):
                with self.assertRaisesRegex(
                    download_https_archive.DownloadTimeout, "timed out"
                ):
                    download_https_archive.download(
                        "https://example.invalid/archive.tar.gz",
                        Path(temporary) / "archive.tar.gz",
                    )

            self.assertEqual(
                alarm.call_args_list,
                [
                    mock.call(download_https_archive.DOWNLOAD_TIMEOUT),
                    mock.call(0),
                ],
            )
            self.assertEqual(
                register.call_args_list,
                [
                    mock.call(
                        download_https_archive.signal.SIGALRM,
                        download_https_archive._raise_download_timeout,
                    ),
                    mock.call(
                        download_https_archive.signal.SIGALRM,
                        previous_handler,
                    ),
                ],
            )
            self.assertEqual(list(Path(temporary).iterdir()), [])

    def test_deadline_is_armed_before_response_headers(self):
        self._assert_download_deadline("open")

    def test_deadline_is_armed_during_chunked_body_reads(self):
        self._assert_download_deadline("read")

    def test_deadline_exception_is_not_caught_by_address_retries(self):
        addresses = [
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("192.0.2.1", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("192.0.2.2", 443)),
        ]
        connection = mock.Mock()
        connection.connect.side_effect = download_https_archive.DownloadTimeout(
            "deadline"
        )
        with mock.patch.object(socket, "getaddrinfo", return_value=addresses), (
            mock.patch.object(socket, "socket", return_value=connection)
        ):
            with self.assertRaises(download_https_archive.DownloadTimeout):
                socket.create_connection(("example.invalid", 443), timeout=1)
        connection.connect.assert_called_once_with(("192.0.2.1", 443))

    def test_socket_errors_still_allow_address_fallback(self):
        addresses = [
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("192.0.2.1", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("192.0.2.2", 443)),
        ]
        first = mock.Mock()
        first.connect.side_effect = OSError("unreachable")
        second = mock.Mock()
        with mock.patch.object(socket, "getaddrinfo", return_value=addresses), (
            mock.patch.object(
                socket, "socket", side_effect=[first, second]
            )
        ):
            self.assertIs(
                socket.create_connection(("example.invalid", 443), timeout=1),
                second,
            )
        first.connect.assert_called_once_with(("192.0.2.1", 443))
        second.connect.assert_called_once_with(("192.0.2.2", 443))
        first.close.assert_called_once()

    def test_redirect_response_does_not_read_body(self):
        response = mock.Mock()
        wrapped = download_https_archive._RedirectResponse(response)
        self.assertEqual(wrapped.read(), b"")
        self.assertEqual(wrapped.read(1024), b"")
        response.read.assert_not_called()
        wrapped.close()
        response.close.assert_called_once()

    def test_rejects_download_larger_than_limit_without_content_length(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, "maximum size"):
                self.download(temporary, FakeResponse([b"ab", b"cd"]))
            self.assertEqual(list(Path(temporary).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
