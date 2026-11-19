#!/usr/bin/env python3
"""Download an archive while requiring HTTPS for every redirect."""

import os
import signal
import sys
import tempfile
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, build_opener


MAX_ARCHIVE_SIZE = 64 * 1024 * 1024
DOWNLOAD_CHUNK_SIZE = 64 * 1024
DOWNLOAD_TIMEOUT = 300
SOCKET_TIMEOUT = 60


class DownloadTimeout(Exception):
    """Raised when the total archive download deadline expires."""


class _RedirectResponse:
    """Close a redirect response without buffering its body."""

    def __init__(self, response):
        self.response = response
        self.closed = False

    def read(self, *_args, **_kwargs):
        return b""

    def close(self):
        if not self.closed:
            self.closed = True
            self.response.close()


class HTTPSOnlyRedirectHandler(HTTPRedirectHandler):
    """Reject redirects that would send the request over a non-HTTPS scheme."""

    def http_error_302(self, request, response, code, message, headers):
        # urllib's implementation calls response.read() without a size limit.
        redirect_response = _RedirectResponse(response)
        try:
            return super().http_error_302(
                request, redirect_response, code, message, headers
            )
        finally:
            redirect_response.close()

    http_error_301 = http_error_303 = http_error_307 = http_error_308 = (
        http_error_302
    )

    def redirect_request(
        self, request, file_pointer, code, message, headers, new_url
    ):
        if urlsplit(new_url).scheme.lower() != "https":
            raise URLError("Refusing redirect to a non-HTTPS URL")
        return super().redirect_request(
            request, file_pointer, code, message, headers, new_url
        )


def _raise_download_timeout(_signum, _frame):
    """Interrupt a download when its total time budget expires."""
    raise DownloadTimeout("Archive download timed out")


def download(url, destination):
    """Download URL to destination, allowing only HTTPS redirects."""
    if urlsplit(url).scheme.lower() != "https":
        raise ValueError("Archive URL must use HTTPS")

    directory = os.path.dirname(os.path.abspath(destination))
    descriptor, temporary_path = tempfile.mkstemp(
        prefix=".librenms-archive-", dir=directory
    )
    try:
        previous_handler = signal.signal(
            signal.SIGALRM, _raise_download_timeout
        )
        signal.alarm(DOWNLOAD_TIMEOUT)
        try:
            with os.fdopen(descriptor, "wb") as output:
                opener = build_opener(HTTPSOnlyRedirectHandler)
                with opener.open(url, timeout=SOCKET_TIMEOUT) as response:
                    if urlsplit(response.geturl()).scheme.lower() != "https":
                        raise URLError(
                            "Archive response did not use HTTPS"
                        )
                    content_length = response.headers.get("Content-Length")
                    if content_length is not None:
                        try:
                            declared_size = int(content_length)
                        except ValueError as error:
                            raise ValueError(
                                "Archive response has an invalid Content-Length"
                            ) from error
                        if (
                            declared_size < 0
                            or declared_size > MAX_ARCHIVE_SIZE
                        ):
                            raise ValueError(
                                "Archive response exceeds maximum size of "
                                f"{MAX_ARCHIVE_SIZE} bytes"
                            )

                    downloaded = 0
                    while True:
                        remaining = MAX_ARCHIVE_SIZE - downloaded + 1
                        chunk = response.read1(
                            min(DOWNLOAD_CHUNK_SIZE, remaining)
                        )
                        if not chunk:
                            break
                        downloaded += len(chunk)
                        if downloaded > MAX_ARCHIVE_SIZE:
                            raise ValueError(
                                "Archive response exceeds maximum size of "
                                f"{MAX_ARCHIVE_SIZE} bytes"
                            )
                        output.write(chunk)
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, previous_handler)
        os.replace(temporary_path, destination)
    finally:
        if os.path.exists(temporary_path):
            os.unlink(temporary_path)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("Usage: download_https_archive.py URL DESTINATION")
    download(sys.argv[1], sys.argv[2])
