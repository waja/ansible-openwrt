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
        """Account for extension bytes before tarfile reads their payload."""
        if self.size < 0:
            raise ValueError("Archive extension has an invalid size")
        size = self._block(self.size)
        if size > MAX_MEMBER_METADATA_SIZE:
            raise ValueError("Archive member metadata exceeds maximum size")
        total = getattr(archive, "_metadata_size", 0) + size
        if total > MAX_TOTAL_METADATA_SIZE:
            raise ValueError("Archive metadata exceeds maximum size")
        archive._metadata_size = total

    def _proc_pax(self, archive):
        """Bound PAX metadata before delegating to the standard parser."""
        self._check_metadata_size(archive)
        return super()._proc_pax(archive)

    def _proc_gnulong(self, archive):
        """Bound GNU long-name metadata before reading it."""
        self._check_metadata_size(archive)
        return super()._proc_gnulong(archive)

    def _proc_gnusparse_10(self, member, pax_headers, archive):
        """Bound the sparse map read from the archive data stream."""
        metadata_size = tarfile.BLOCKSIZE
        total = getattr(archive, "_metadata_size", 0) + metadata_size
        if (
            metadata_size > MAX_MEMBER_METADATA_SIZE
            or total > MAX_TOTAL_METADATA_SIZE
        ):
            raise ValueError("Archive metadata exceeds maximum size")
        buffer = archive.fileobj.read(tarfile.BLOCKSIZE)
        fields, buffer = buffer.split(b"\n", 1)
        fields = int(fields)
        sparse = []

        while len(sparse) < fields * 2:
            if b"\n" not in buffer:
                if metadata_size + tarfile.BLOCKSIZE > MAX_MEMBER_METADATA_SIZE:
                    raise ValueError(
                        "Archive member metadata exceeds maximum size"
                    )
                total = (
                    getattr(archive, "_metadata_size", 0)
                    + metadata_size
                    + tarfile.BLOCKSIZE
                )
                if total > MAX_TOTAL_METADATA_SIZE:
                    raise ValueError("Archive metadata exceeds maximum size")
                chunk = archive.fileobj.read(tarfile.BLOCKSIZE)
                if not chunk:
                    raise tarfile.InvalidHeaderError(
                        "truncated GNU sparse map"
                    )
                metadata_size += len(chunk)
                buffer += chunk
            number, buffer = buffer.split(b"\n", 1)
            sparse.append(int(number))

        total = getattr(archive, "_metadata_size", 0) + metadata_size
        if (
            metadata_size > MAX_MEMBER_METADATA_SIZE
            or total > MAX_TOTAL_METADATA_SIZE
        ):
            raise ValueError("Archive metadata exceeds maximum size")
        archive._metadata_size = total
        member.offset_data = archive.fileobj.tell()
        member.sparse = list(zip(sparse[::2], sparse[1::2], strict=True))


def _open_streaming_archive(archive_path):
    """Open a tar stream without retaining every TarInfo object."""
    options = {"mode": "r|*", "tarinfo": BoundedTarInfo}
    try:
        return tarfile.open(archive_path, stream=True, **options)
    except TypeError as error:
        if "stream" not in str(error):
            raise
        # Python before 3.13 lacks the stream argument. Clear the first
        # member cached by TarFile.__init__, then enable streaming manually.
        archive = tarfile.open(archive_path, **options)
        archive.stream = True
        archive.members.clear()
        next_member = archive.next

        def next_without_caching():
            member = next_member()
            if (
                member is not None
                and archive.members
                and archive.members[-1] is member
            ):
                archive.members.pop()
            return member

        archive.next = next_without_caching
        return archive


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


def _validate_sparse_extents(member):
    """Reject sparse maps that can write beyond their logical file size."""
    if member.sparse is None:
        return

    logical_size = _expanded_member_size(member)
    previous_end = 0
    expanded_size = 0
    for offset, length in member.sparse:
        if offset < 0 or length < 0:
            raise ValueError("Sparse archive contains a negative extent")
        if offset < previous_end:
            raise ValueError("Sparse archive contains overlapping extents")
        end = offset + length
        if end > logical_size:
            raise ValueError("Sparse extent exceeds logical file size")
        expanded_size += length
        if expanded_size > logical_size:
            raise ValueError("Sparse extents exceed logical file size")
        previous_end = end


def _validate_member(member, roots):
    """Validate a member type and path and record its top-level directory."""
    if member.islnk():
        raise ValueError(f"Hard links are not supported: {member.name!r}")
    if not (member.isfile() or member.isdir() or member.issym()):
        raise ValueError(
            f"Unsupported archive member type: {member.type!r}"
        )
    path = PurePosixPath(member.name)
    parts = path.parts
    if member.size < 0:
        raise ValueError("Archive member has an invalid size")
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
    with _open_streaming_archive(archive_path) as archive:
        for member in archive:
            member_count += 1
            if member_count > MAX_ARCHIVE_MEMBERS:
                raise ValueError("Archive contains too many members")
            _validate_member(member, roots)
            if member.isfile():
                _validate_sparse_extents(member)
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
    with _open_streaming_archive(archive_path) as archive:
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
