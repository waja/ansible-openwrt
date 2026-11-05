#!/usr/bin/env python3
"""Safely extract a single-root gzip-compressed tar archive."""

import os
import sys
import tarfile
from pathlib import Path, PurePosixPath


def extract_archive(archive, destination):
    """Extract archive contents while removing its top-level directory."""
    destination = Path(destination).resolve(strict=True)
    if not destination.is_dir():
        raise ValueError("Destination must be an existing directory")
    if any(destination.iterdir()):
        raise ValueError("Destination directory must be empty")

    with tarfile.open(archive, mode="r:gz") as source:
        members = source.getmembers()
        roots = set()

        for member in members:
            path = PurePosixPath(member.name)
            parts = path.parts
            if (
                path.is_absolute()
                or not parts
                or any(part in ("", ".", "..") for part in parts)
            ):
                raise ValueError(f"Unsafe archive path: {member.name!r}")

            roots.add(parts[0])

        if len(roots) != 1 or any(
            len(PurePosixPath(member.name).parts) == 1 and not member.isdir()
            for member in members
        ):
            raise ValueError(
                "Archive must contain exactly one top-level directory"
            )

        root = next(iter(roots))

        def safe_filter(member, path):
            """Strip the archive root and apply Python's data filter."""
            parts = PurePosixPath(member.name).parts
            if parts[0] != root:
                raise ValueError("Archive contains inconsistent root paths")
            if len(parts) == 1:
                return None

            # Hard links refer to archive-root paths and are not needed by
            # the LibreNMS agent files. Reject them rather than rewriting
            # their targets ambiguously.
            if member.islnk():
                raise ValueError(
                    f"Hard links are not supported: {member.name!r}"
                )

            stripped = member.replace(
                name=PurePosixPath(*parts[1:]).as_posix()
            )
            return tarfile.data_filter(stripped, path)

        source.extractall(
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
