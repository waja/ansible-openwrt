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
    """Bound PAX headers and reject archive extensions we do not need."""

    def _proc_pax(self, archive):
        if self.size < 0:
            raise ValueError("Archive extension has an invalid size")
        size = self._block(self.size)
        if size > MAX_MEMBER_METADATA_SIZE:
            raise ValueError("Archive member metadata exceeds maximum size")
        total = getattr(archive, "_metadata_size", 0) + size
        if total > MAX_TOTAL_METADATA_SIZE:
            raise ValueError("Archive metadata exceeds maximum size")
        archive._metadata_size = total
        return super()._proc_pax(archive)

    def _proc_member(self, archive):
        if self.type in (
            tarfile.GNUTYPE_LONGNAME,
            tarfile.GNUTYPE_LONGLINK,
            tarfile.GNUTYPE_SPARSE,
        ):
            raise ValueError("GNU longname and sparse entries are not supported")
        return super()._proc_member(archive)

    def _proc_gnusparse_01(self, member, pax_headers):
        raise ValueError("GNU sparse entries are not supported")

    def _proc_gnusparse_00(self, member, raw_headers):
        raise ValueError("GNU sparse entries are not supported")

    def _proc_gnusparse_10(self, member, pax_headers, archive):
        raise ValueError("GNU sparse entries are not supported")


def _validate_member(member, roots):
    """Validate a member type and path and record its top-level directory."""
    if member.islnk():
        raise ValueError(f"Hard links are not supported: {member.name!r}")
    if not (member.isfile() or member.isdir() or member.issym()):
        raise ValueError(f"Unsupported archive member type: {member.type!r}")

    path = PurePosixPath(member.name)
    parts = path.parts
    if member.size < 0:
        raise ValueError("Archive member has an invalid size")
    if not member.isfile() and member.size:
        raise ValueError("Non-file archive members must have zero size")
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
    roots = set()
    member_count = 0
    expanded_size = 0

    # Keep one file descriptor across both passes. This prevents replacing the
    # path between validation and extraction; the second pass rechecks limits
    # and member policy in case the opened file is modified in place.
    with archive_path.open("rb") as archive_file:
        if os.fstat(archive_file.fileno()).st_size > MAX_ARCHIVE_SIZE:
            raise ValueError("Archive exceeds maximum compressed size")

        with tarfile.open(
            fileobj=archive_file, mode="r:*", tarinfo=BoundedTarInfo
        ) as archive:
            # TarFile caches the first member on open. Keep firstmember intact
            # while clearing the list cache to bound PAX metadata retention.
            archive.members.clear()
            member = archive.next()
            while member is not None:
                member_count += 1
                if member_count > MAX_ARCHIVE_MEMBERS:
                    raise ValueError("Archive contains too many members")
                _validate_member(member, roots)
                if member.isfile():
                    expanded_size += member.size
                    if expanded_size > MAX_EXPANDED_SIZE:
                        raise ValueError("Archive exceeds maximum expanded size")
                archive.members.clear()
                member = archive.next()

            if member_count == 0:
                raise ValueError("Archive is empty")
            if len(roots) != 1:
                raise ValueError("Archive must contain one top-level directory")
            root = next(iter(roots))

        archive_file.seek(0)
        if os.fstat(archive_file.fileno()).st_size > MAX_ARCHIVE_SIZE:
            raise ValueError("Archive exceeds maximum compressed size")

        def safe_filter(member, path):
            """Strip the archive root and apply Python's safe data filter."""
            parts = PurePosixPath(member.name).parts
            if parts[0] != root:
                raise ValueError("Archive contains inconsistent root paths")
            if len(parts) == 1:
                return None
            stripped = member.replace(
                name=PurePosixPath(*parts[1:]).as_posix()
            )
            return tarfile.data_filter(stripped, path)

        # Recheck each member while extracting. This keeps the limits and
        # member policy effective if the opened file changes between passes.
        extracted_count = 0
        extracted_size = 0
        extraction_roots = set()
        with tarfile.open(
            fileobj=archive_file, mode="r:*", tarinfo=BoundedTarInfo
        ) as archive:
            archive.members.clear()
            member = archive.next()
            while member is not None:
                extracted_count += 1
                if extracted_count > MAX_ARCHIVE_MEMBERS:
                    raise ValueError("Archive contains too many members")
                _validate_member(member, extraction_roots)
                if extraction_roots != {root}:
                    raise ValueError("Archive contains inconsistent root paths")
                if member.isfile():
                    extracted_size += member.size
                    if extracted_size > MAX_EXPANDED_SIZE:
                        raise ValueError("Archive exceeds maximum expanded size")
                archive.extract(
                    member,
                    path=os.fspath(destination),
                    filter=safe_filter,
                )
                archive.members.clear()
                member = archive.next()

            if extracted_count == 0:
                raise ValueError("Archive is empty")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(
            "Usage: extract_tar_archive.py ARCHIVE DESTINATION"
        )
    try:
        extract_archive(sys.argv[1], sys.argv[2])
    except (OSError, tarfile.TarError, ValueError) as error:
        raise SystemExit(f"Archive extraction failed: {error}") from error
