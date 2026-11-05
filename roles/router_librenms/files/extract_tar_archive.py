#!/usr/bin/env python3
"""Safely extract a single-root tar archive within resource limits."""

import os
import sys
import tarfile
from pathlib import Path, PurePosixPath


MAX_ARCHIVE_SIZE = 64 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 10_000
MAX_EXPANDED_SIZE = 256 * 1024 * 1024
MAX_EXTENSION_METADATA_SIZE = 1024 * 1024
MAX_EXTENSION_METADATA_TOTAL_SIZE = 8 * 1024 * 1024


def extract_archive(archive, destination):
    """Extract archive contents while removing its top-level directory."""
    destination = Path(destination).resolve(strict=True)
    if not destination.is_dir():
        raise ValueError("Destination must be an existing directory")
    if any(destination.iterdir()):
        raise ValueError("Destination directory must be empty")

    archive_size = Path(archive).stat().st_size
    if archive_size > MAX_ARCHIVE_SIZE:
        raise ValueError(
            f"Archive exceeds maximum size of {MAX_ARCHIVE_SIZE} bytes"
        )

    metadata_budget = [0]

    class BoundedTarInfo(tarfile.TarInfo):
        """Bound individual and cumulative extension metadata."""

        def _account_extension_metadata(self):
            block_size = tarfile.BLOCKSIZE
            padded_size = (
                (self.size + block_size - 1) // block_size
            ) * block_size
            metadata_budget[0] += block_size + padded_size
            if self.size > MAX_EXTENSION_METADATA_SIZE:
                raise ValueError(
                    "Archive extension metadata exceeds maximum size of "
                    f"{MAX_EXTENSION_METADATA_SIZE} bytes"
                )
            if metadata_budget[0] > MAX_EXTENSION_METADATA_TOTAL_SIZE:
                raise ValueError(
                    "Archive cumulative extension metadata exceeds "
                    f"{MAX_EXTENSION_METADATA_TOTAL_SIZE} bytes"
                )

        def _proc_pax(self, source):
            self._account_extension_metadata()
            return super()._proc_pax(source)

        def _proc_gnulong(self, source):
            self._account_extension_metadata()
            return super()._proc_gnulong(source)

    with tarfile.open(archive, mode="r:*", tarinfo=BoundedTarInfo) as source:
        members = []
        expanded_size = 0
        while True:
            member = source.next()
            if member is None:
                break
            members.append(member)
            if len(members) > MAX_ARCHIVE_MEMBERS:
                raise ValueError(
                    f"Archive exceeds maximum of {MAX_ARCHIVE_MEMBERS} members"
                )
            expanded_size += member.size
            if expanded_size > MAX_EXPANDED_SIZE:
                raise ValueError(
                    "Archive exceeds maximum expanded size of "
                    f"{MAX_EXPANDED_SIZE} bytes"
                )

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
