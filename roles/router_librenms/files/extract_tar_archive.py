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

    metadata_budget = {"total": 0}

    def reserve_metadata(source, size):
        """Reserve metadata bytes before reading an extension payload."""
        pending = getattr(source, "_pending_extension_metadata", 0) + size
        total = metadata_budget["total"] + size
        if total > MAX_EXTENSION_METADATA_TOTAL_SIZE:
            raise ValueError(
                "Archive cumulative extension metadata exceeds "
                f"{MAX_EXTENSION_METADATA_TOTAL_SIZE} bytes"
            )
        if pending > MAX_EXTENSION_METADATA_TOTAL_SIZE:
            raise ValueError(
                "Archive chained extension metadata exceeds "
                f"{MAX_EXTENSION_METADATA_TOTAL_SIZE} bytes"
            )
        metadata_budget["total"] = total
        source._pending_extension_metadata = pending

    def release_metadata(source, size):
        """Release metadata retained by a completed or failed parser."""
        source._pending_extension_metadata -= size

    class BoundedTarInfo(tarfile.TarInfo):
        """Bound individual and cumulative extension metadata."""

        def _bounded(self, source, parser):
            """Run an extension parser while its payload remains accounted."""
            if self.size > MAX_EXTENSION_METADATA_SIZE:
                raise ValueError(
                    "Archive extension metadata exceeds maximum size of "
                    f"{MAX_EXTENSION_METADATA_SIZE} bytes"
                )
            size = tarfile.BLOCKSIZE + self._block(self.size)
            reserve_metadata(source, size)
            try:
                return parser(source)
            finally:
                release_metadata(source, size)

        def _proc_pax(self, source):
            """Process PAX headers within the shared metadata budget."""
            return self._bounded(source, super()._proc_pax)

        def _proc_gnulong(self, source):
            """Process GNU long-name headers within the metadata budget."""
            return self._bounded(source, super()._proc_gnulong)

        def _proc_sparse(self, source):
            """Process GNU sparse headers with bounded extension blocks."""
            structs, isextended, origsize = self._sparse_structs
            del self._sparse_structs
            reserved = 0
            try:
                while isextended:
                    reserve_metadata(source, tarfile.BLOCKSIZE)
                    reserved += tarfile.BLOCKSIZE
                    buf = source.fileobj.read(tarfile.BLOCKSIZE)
                    pos = 0
                    for _ in range(21):
                        try:
                            offset = tarfile.nti(buf[pos:pos + 12])
                            numbytes = tarfile.nti(buf[pos + 12:pos + 24])
                        except ValueError:
                            break
                        if offset and numbytes:
                            structs.append((offset, numbytes))
                        pos += 24
                    isextended = bool(buf[504])
                self.sparse = structs
                self.offset_data = source.fileobj.tell()
                source.offset = self.offset_data + self._block(self.size)
                self.size = origsize
                return self
            finally:
                if reserved:
                    release_metadata(source, reserved)

        def _proc_gnusparse_10(self, next_member, pax_headers, source):
            """Read GNU sparse 1.0 maps within the shared metadata budget."""
            sparse = []
            reserved = 0
            try:
                reserve_metadata(source, tarfile.BLOCKSIZE)
                reserved += tarfile.BLOCKSIZE
                buf = source.fileobj.read(tarfile.BLOCKSIZE)
                fields, buf = buf.split(b"\n", 1)
                fields = int(fields)
                while len(sparse) < fields * 2:
                    if b"\n" not in buf:
                        reserve_metadata(source, tarfile.BLOCKSIZE)
                        reserved += tarfile.BLOCKSIZE
                        buf += source.fileobj.read(tarfile.BLOCKSIZE)
                    number, buf = buf.split(b"\n", 1)
                    sparse.append(int(number))
                next_member.offset_data = source.fileobj.tell()
                next_member.sparse = list(zip(sparse[::2], sparse[1::2]))
            finally:
                if reserved:
                    release_metadata(source, reserved)

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
