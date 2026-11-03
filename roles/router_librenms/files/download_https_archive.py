#!/usr/bin/env python3
"""Download an archive while requiring HTTPS for every redirect."""

import os
import shutil
import sys
import tempfile
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, build_opener


class HTTPSOnlyRedirectHandler(HTTPRedirectHandler):
    """Reject redirects that would send the request over a non-HTTPS scheme."""

    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        if urlsplit(new_url).scheme.lower() != "https":
            raise URLError("Refusing redirect to a non-HTTPS URL")
        return super().redirect_request(
            request, file_pointer, code, message, headers, new_url
        )


def download(url, destination):
    """Download URL to destination, allowing only HTTPS redirects."""
    if urlsplit(url).scheme.lower() != "https":
        raise ValueError("Archive URL must use HTTPS")

    directory = os.path.dirname(os.path.abspath(destination))
    descriptor, temporary_path = tempfile.mkstemp(
        prefix=".librenms-archive-", dir=directory
    )
    try:
        with os.fdopen(descriptor, "wb") as output:
            opener = build_opener(HTTPSOnlyRedirectHandler)
            with opener.open(url, timeout=60) as response:
                if urlsplit(response.geturl()).scheme.lower() != "https":
                    raise URLError("Archive response did not use HTTPS")
                shutil.copyfileobj(response, output)
        os.replace(temporary_path, destination)
    finally:
        if os.path.exists(temporary_path):
            os.unlink(temporary_path)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("Usage: download_https_archive.py URL DESTINATION")
    download(sys.argv[1], sys.argv[2])
