#!/usr/bin/env python3
"""Safely extract a single-root tar archive without its root directory."""

import os
import sys
import tarfile
from pathlib import Path, PurePosixPath


MAX_ARCHIVE_SIZE = 64 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 10_000
MAX_EXPANDED_SIZE = 256 * 1024 * 1024


def extract_archive(archive_path, destination):
    """Extract an archive while rejecting unsafe paths and links."""
    archive_path = Path(archive_path)
    destination = Path(destination).resolve(strict=True)

    if not destination.is_dir() or any(destination.iterdir()):
        raise ValueError("Destination must be an empty directory")
    if archive_path.stat().st_size > MAX_ARCHIVE_SIZE:
        raise ValueError("Archive exceeds maximum compressed size")

    with tarfile.open(archive_path, mode="r:*") as archive:
        members = archive.getmembers()
        if not members:
            raise ValueError("Archive is empty")
        if len(members) > MAX_ARCHIVE_MEMBERS:
            raise ValueError("Archive contains too many members")

        roots = set()
        expanded_size = 0
        for member in members:
            path = PurePosixPath(member.name)
            parts = path.parts
            if path.is_absolute() or not parts or ".." in parts:
                raise ValueError(f"Unsafe archive path: {member.name!r}")
            roots.add(parts[0])
            if member.isfile():
                expanded_size += member.size

        if len(roots) != 1 or any(
            len(PurePosixPath(member.name).parts) == 1
            and not member.isdir()
            for member in members
        ):
            raise ValueError("Archive must contain one top-level directory")
        if expanded_size > MAX_EXPANDED_SIZE:
            raise ValueError("Archive exceeds maximum expanded size")

        root = next(iter(roots))

        def safe_filter(member, path):
            """Strip the archive root and apply Python's safe data filter."""
            parts = PurePosixPath(member.name).parts
            if parts[0] != root:
                raise ValueError("Archive contains inconsistent root paths")
            if len(parts) == 1:
                return None
            if member.islnk():
                raise ValueError(
                    f"Hard links are not supported: {member.name!r}"
                )
            stripped = member.replace(
                name=PurePosixPath(*parts[1:]).as_posix()
            )
            return tarfile.data_filter(stripped, path)

        archive.extractall(
            path=os.fspath(destination),
            members=members,
            filter=safe_filter,
        )


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(
            "Usage: extract_tar_archive.py ARCHIVE DESTINATION"
        )
    try:
        extract_archive(sys.argv[1], sys.argv[2])
    except (OSError, tarfile.TarError, ValueError) as error:
        raise SystemExit(f"Archive extraction failed: {error}") from error
