#!/usr/bin/env python3
"""Validate a LibreNMS source archive before it is staged on an OpenWrt router."""

import gzip
import os
import sys
import tarfile
from pathlib import PurePosixPath

MAX_ARCHIVE_BYTES = 8 * 1024 * 1024
MAX_UNPACKED_BYTES = 32 * 1024 * 1024
MAX_DECOMPRESSED_BYTES = 48 * 1024 * 1024
MAX_MEMBERS = 4096
REQUIRED_FILES = {
    "snmp/distro",
    "snmp/Openwrt/wlClients.sh",
    "snmp/Openwrt/wlFrequency.sh",
    "snmp/Openwrt/wlNoiseFloor.sh",
    "snmp/Openwrt/wlRate.sh",
    "snmp/Openwrt/wlSNR.sh",
}


class ArchiveValidationError(ValueError):
    """Raised when an archive is unsafe or incomplete."""


class StrictTarInfo(tarfile.TarInfo):
    """Reject malformed headers even after valid members were parsed."""

    @classmethod
    def frombuf(cls, buf, encoding, errors):
        try:
            return super().frombuf(buf, encoding, errors)
        except tarfile.InvalidHeaderError as error:
            raise ArchiveValidationError(
                f"Invalid tar header: {error}"
            ) from error


class BoundedReader:
    """Limit bytes read from a decompressed archive stream."""

    def __init__(self, stream, limit):
        self.stream = stream
        self.limit = limit
        self.bytes_read = 0

    def read(self, size=-1):
        remaining = self.limit - self.bytes_read
        if remaining < 0:
            raise ArchiveValidationError(
                "Archive exceeds the decompressed-stream size limit"
            )
        if size < 0 or size > remaining + 1:
            size = remaining + 1
        data = self.stream.read(size)
        self.bytes_read += len(data)
        if self.bytes_read > self.limit:
            raise ArchiveValidationError(
                "Archive exceeds the decompressed-stream size limit"
            )
        return data


def validate_archive(archive_path):
    """Validate paths, member types and resource bounds without extracting."""
    if os.path.getsize(archive_path) > MAX_ARCHIVE_BYTES:
        raise ArchiveValidationError(
            f"Archive exceeds the {MAX_ARCHIVE_BYTES}-byte compressed-size limit"
        )

    try:
        with gzip.open(archive_path, "rb") as compressed:
            bounded = BoundedReader(compressed, MAX_DECOMPRESSED_BYTES)
            with tarfile.open(
                fileobj=bounded, mode="r|", tarinfo=StrictTarInfo
            ) as archive:
                root = None
                unpacked_size = 0
                member_count = 0
                seen_paths = set()
                regular_files = set()

                for member in archive:
                    member_count += 1
                    if member_count > MAX_MEMBERS:
                        raise ArchiveValidationError(
                            f"Archive contains more than {MAX_MEMBERS} members"
                        )

                    raw_name = member.name
                    if (
                        not raw_name
                        or raw_name.startswith("/")
                        or "\\" in raw_name
                    ):
                        raise ArchiveValidationError(
                            f"Unsafe archive path: {raw_name!r}"
                        )

                    normalized_name = raw_name.rstrip("/")
                    parts = normalized_name.split("/")
                    if not normalized_name or any(
                        part in ("", ".", "..") for part in parts
                    ):
                        raise ArchiveValidationError(
                            f"Unsafe archive path: {raw_name!r}"
                        )

                    if root is None:
                        root = parts[0]
                    if parts[0] != root or (
                        len(parts) < 2 and not member.isdir()
                    ):
                        raise ArchiveValidationError(
                            "Archive members must share one top-level directory"
                        )

                    if len(parts) == 1:
                        relative_path = ""
                    else:
                        relative_path = PurePosixPath(*parts[1:]).as_posix()

                    if relative_path in seen_paths:
                        raise ArchiveValidationError(
                            f"Duplicate archive path: {relative_path or root}"
                        )
                    seen_paths.add(relative_path)

                    if len(parts) == 1:
                        continue

                    if not (member.isdir() or member.isfile()):
                        raise ArchiveValidationError(
                            f"Unsupported archive member type: {raw_name!r}"
                        )
                    if member.isfile() and member.linkname:
                        raise ArchiveValidationError(
                            f"Regular file has an unexpected link target: {raw_name!r}"
                        )

                    parent = PurePosixPath(relative_path).parent
                    while str(parent) != ".":
                        if str(parent) in regular_files:
                            raise ArchiveValidationError(
                                f"Regular file is an ancestor of {relative_path!r}"
                            )
                        parent = parent.parent

                    if member.isfile():
                        prefix = relative_path + "/"
                        if any(
                            path.startswith(prefix) for path in regular_files
                        ):
                            raise ArchiveValidationError(
                                f"Regular file conflicts with existing descendants: {relative_path!r}"
                            )
                        unpacked_size += member.size
                        regular_files.add(relative_path)

                    if unpacked_size > MAX_UNPACKED_BYTES:
                        raise ArchiveValidationError(
                            "Archive exceeds the "
                            f"{MAX_UNPACKED_BYTES}-byte expanded-size limit"
                        )

                # TarFile stops at the first zero block. Require the second
                # zero block as well, and reject EOF without a valid terminator.
                if archive.fileobj.read(tarfile.BLOCKSIZE) != (
                    b"\\0" * tarfile.BLOCKSIZE
                ):
                    raise ArchiveValidationError(
                        "Archive is missing the two-block tar terminator"
                    )

                # Consume the remainder so gzip CRC/trailer errors and
                # oversized trailing metadata cannot be silently ignored.
                while bounded.read(64 * 1024):
                    pass

                missing = REQUIRED_FILES - regular_files
                if missing:
                    raise ArchiveValidationError(
                        "Archive is missing required files: "
                        + ", ".join(sorted(missing))
                    )
    except ArchiveValidationError:
        raise
    except (OSError, EOFError, gzip.BadGzipFile, tarfile.TarError) as error:
        raise ArchiveValidationError(
            f"Invalid gzip tar archive: {error}"
        ) from error


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: validate_archive.py ARCHIVE")
    try:
        validate_archive(sys.argv[1])
    except (ArchiveValidationError, OSError) as error:
        raise SystemExit(f"Unsafe LibreNMS source archive: {error}") from error
