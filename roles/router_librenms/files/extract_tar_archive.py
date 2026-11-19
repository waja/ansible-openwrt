#!/usr/bin/env python3
"""Safely extract a single-root tar archive without its root directory."""

import os
import sys
import tarfile
from pathlib import Path, PurePosixPath


MAX_ARCHIVE_SIZE = 64 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 10_000
MAX_EXPANDED_SIZE = 256 * 1024 * 1024
MAX_MEMBER_METADATA_SIZE = 1024 * 1024
MAX_TOTAL_METADATA_SIZE = 4 * 1024 * 1024


class BoundedTarInfo(tarfile.TarInfo):
    """Reject oversized or excessive PAX and GNU extension headers."""

    def _check_metadata_size(self, archive):
        size = self._block(self.size)
        if size > MAX_MEMBER_METADATA_SIZE:
            raise ValueError("Archive member metadata exceeds maximum size")
        total = getattr(archive, "_metadata_size", 0) + size
        if total > MAX_TOTAL_METADATA_SIZE:
            raise ValueError("Archive metadata exceeds maximum size")
        archive._metadata_size = total

    def _proc_pax(self, archive):
        self._check_metadata_size(archive)
        return super()._proc_pax(archive)

    def _proc_gnulong(self, archive):
        self._check_metadata_size(archive)
        return super()._proc_gnulong(archive)


def _expanded_member_size(member):
    """Return the logical size, including GNU sparse file metadata."""
    size = member.size
    for key in ("GNU.sparse.realsize", "GNU.sparse.size"):
        value = member.pax_headers.get(key)
        if value is not None:
            try:
                size = max(size, int(value))
            except ValueError as error:
                raise ValueError("Invalid sparse file size") from error
    return size


def _validate_member(member, roots):
    """Validate a member path and record its top-level directory."""
    path = PurePosixPath(member.name)
    parts = path.parts
    if path.is_absolute() or not parts or ".." in parts:
        raise ValueError(f"Unsafe archive path: {member.name!r}")
    roots.add(parts[0])
    if len(parts) == 1 and not member.isdir():
        raise ValueError("Archive must contain one top-level directory")


def extract_archive(archive_path, destination):
    """Extract an archive while rejecting unsafe paths and links."""
    archive_path = Path(archive_path)
    destination = Path(destination).resolve(strict=True)

    if not destination.is_dir() or any(destination.iterdir()):
        raise ValueError("Destination must be an empty directory")
    if archive_path.stat().st_size > MAX_ARCHIVE_SIZE:
        raise ValueError("Archive exceeds maximum compressed size")

    roots = set()
    member_count = 0
    expanded_size = 0
    with tarfile.open(\n        archive_path, mode="r|*", tarinfo=BoundedTarInfo\n    ) as archive:
        for member in archive:
            member_count += 1
            if member_count > MAX_ARCHIVE_MEMBERS:
                raise ValueError("Archive contains too many members")
            _validate_member(member, roots)
            if member.isfile():
                expanded_size += _expanded_member_size(member)
                if expanded_size > MAX_EXPANDED_SIZE:
                    raise ValueError("Archive exceeds maximum expanded size")

    if member_count == 0:
        raise ValueError("Archive is empty")
    if len(roots) != 1:
        raise ValueError("Archive must contain one top-level directory")
    root = next(iter(roots))

    def safe_filter(member, path):
        """Strip the archive root and apply Python's safe data filter."""
        parts = PurePosixPath(member.name).parts
        if parts[0] != root:
            raise ValueError("Archive contains inconsistent root paths")
        if len(parts) == 1:
            return None
        if member.islnk():
            raise ValueError(f"Hard links are not supported: {member.name!r}")
        stripped = member.replace(
            name=PurePosixPath(*parts[1:]).as_posix()
        )
        return tarfile.data_filter(stripped, path)

    # Reopen the archive: streaming mode avoids caching every TarInfo object.
    with tarfile.open(\n        archive_path, mode="r|*", tarinfo=BoundedTarInfo\n    ) as archive:
        archive.extractall(
            path=os.fspath(destination),
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
