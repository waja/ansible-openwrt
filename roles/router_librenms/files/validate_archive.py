#!/usr/bin/env python3
"""Validate a LibreNMS source archive before it is staged on an OpenWrt router."""

import os
import sys
import tarfile
from pathlib import PurePosixPath

MAX_ARCHIVE_BYTES = 8 * 1024 * 1024
MAX_UNPACKED_BYTES = 32 * 1024 * 1024
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


def validate_archive(archive_path):
    """Validate paths, member types and resource bounds without extracting."""
    if os.path.getsize(archive_path) > MAX_ARCHIVE_BYTES:
        raise ArchiveValidationError(
            f"Archive exceeds the {MAX_ARCHIVE_BYTES}-byte compressed-size limit"
        )
    try:
        archive = tarfile.open(archive_path, mode="r:gz")
    except (OSError, tarfile.TarError) as error:
        raise ArchiveValidationError(f"Invalid gzip tar archive: {error}") from error

    with archive:
        members = archive.getmembers()
        if not members:
            raise ArchiveValidationError("Archive is empty")
        if len(members) > MAX_MEMBERS:
            raise ArchiveValidationError(
                f"Archive contains more than {MAX_MEMBERS} members"
            )

        root = None
        unpacked_size = 0
        seen_paths = set()
        regular_files = set()
        for member in members:
            raw_name = member.name
            if not raw_name or raw_name.startswith("/") or "\\" in raw_name:
                raise ArchiveValidationError(f"Unsafe archive path: {raw_name!r}")
            normalized_name = raw_name.rstrip("/")
            parts = normalized_name.split("/")
            if not normalized_name or any(
                part in ("", ".", "..") for part in parts
            ):
                raise ArchiveValidationError(f"Unsafe archive path: {raw_name!r}")
            if root is None:
                root = parts[0]
            if parts[0] != root or (len(parts) < 2 and not member.isdir()):
                raise ArchiveValidationError(
                    "Archive members must share one top-level directory"
                )
            if len(parts) == 1:
                continue
            relative_path = PurePosixPath(*parts[1:]).as_posix()
            if relative_path in seen_paths:
                raise ArchiveValidationError(
                    f"Duplicate archive path: {relative_path}"
                )
            seen_paths.add(relative_path)
            if not (member.isdir() or member.isfile()):
                raise ArchiveValidationError(
                    f"Unsupported archive member type: {raw_name!r}"
                )
            if member.isfile():
                unpacked_size += member.size
                regular_files.add(relative_path)
            if unpacked_size > MAX_UNPACKED_BYTES:
                raise ArchiveValidationError(
                    "Archive exceeds the "
                    f"{MAX_UNPACKED_BYTES}-byte expanded-size limit"
                )

        missing = REQUIRED_FILES - regular_files
        if missing:
            raise ArchiveValidationError(
                "Archive is missing required files: " + ", ".join(sorted(missing))
            )


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: validate_archive.py ARCHIVE")
    try:
        validate_archive(sys.argv[1])
    except (ArchiveValidationError, OSError) as error:
        raise SystemExit(f"Unsafe LibreNMS source archive: {error}") from error
