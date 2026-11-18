#!/usr/bin/env python3
"""Unit tests for LibreNMS source archive validation."""

import gzip
import io
import tarfile
import tempfile
import unittest
from pathlib import Path

from validate_archive import (
    ArchiveValidationError,
    MAX_MEMBERS,
    MAX_UNPACKED_BYTES,
    validate_archive,
)

REQUIRED = (
    "snmp/distro",
    "snmp/Openwrt/wlClients.sh",
    "snmp/Openwrt/wlFrequency.sh",
    "snmp/Openwrt/wlNoiseFloor.sh",
    "snmp/Openwrt/wlRate.sh",
    "snmp/Openwrt/wlSNR.sh",
)


class ArchiveValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.archive_path = Path(self.temp_dir.name) / "archive.tar.gz"

    def tearDown(self):
        self.temp_dir.cleanup()

    def write_archive(self, entries=None):
        if entries is None:
            entries = [(name, tarfile.REGTYPE, b"script") for name in REQUIRED]
        with tarfile.open(self.archive_path, "w:gz") as archive:
            for entry in entries:
                name, kind, data = entry[:3]
                linkname = entry[3] if len(entry) > 3 else ""
                member_name = (
                    name
                    if name.startswith("/") or name.startswith("other-root/")
                    else "source-root/" + name
                )
                member = tarfile.TarInfo(member_name)
                member.type = kind
                member.linkname = linkname
                if kind == tarfile.REGTYPE:
                    member.size = len(data)
                    archive.addfile(member, io.BytesIO(data))
                else:
                    archive.addfile(member)

    def test_accepts_expected_regular_files(self):
        self.write_archive()
        validate_archive(self.archive_path)

    def test_accepts_top_level_directory_entry(self):
        entries = [("", tarfile.DIRTYPE, b"")]
        entries.extend((name, tarfile.REGTYPE, b"script") for name in REQUIRED)
        self.write_archive(entries)
        validate_archive(self.archive_path)

    def test_rejects_parent_directory_traversal(self):
        self.write_archive(
            [(name, tarfile.REGTYPE, b"x") for name in REQUIRED]
            + [("../escape", tarfile.REGTYPE, b"x")]
        )
        with self.assertRaisesRegex(ArchiveValidationError, "Unsafe archive path"):
            validate_archive(self.archive_path)

    def test_rejects_absolute_paths(self):
        self.write_archive(
            [(name, tarfile.REGTYPE, b"x") for name in REQUIRED]
            + [("/tmp/escape", tarfile.REGTYPE, b"x")]
        )
        with self.assertRaisesRegex(ArchiveValidationError, "Unsafe archive path"):
            validate_archive(self.archive_path)

    def test_rejects_backslash_paths(self):
        self.write_archive(
            [(name, tarfile.REGTYPE, b"x") for name in REQUIRED]
            + [("..\\escape", tarfile.REGTYPE, b"x")]
        )
        with self.assertRaisesRegex(ArchiveValidationError, "Unsafe archive path"):
            validate_archive(self.archive_path)

    def test_rejects_symbolic_links(self):
        self.write_archive(
            [(name, tarfile.REGTYPE, b"x") for name in REQUIRED]
            + [("link", tarfile.SYMTYPE, b"")]
        )
        with self.assertRaisesRegex(ArchiveValidationError, "member type"):
            validate_archive(self.archive_path)

    def test_rejects_hard_links(self):
        self.write_archive(
            [(name, tarfile.REGTYPE, b"x") for name in REQUIRED]
            + [("link", tarfile.LNKTYPE, b"")]
        )
        with self.assertRaisesRegex(ArchiveValidationError, "member type"):
            validate_archive(self.archive_path)

    def test_rejects_duplicate_paths(self):
        entries = [(name, tarfile.REGTYPE, b"x") for name in REQUIRED]
        entries.append((REQUIRED[0], tarfile.REGTYPE, b"second"))
        self.write_archive(entries)
        with self.assertRaisesRegex(ArchiveValidationError, "Duplicate"):
            validate_archive(self.archive_path)

    def test_rejects_duplicate_root_directory_entries(self):
        entries = [("", tarfile.DIRTYPE, b""), ("", tarfile.DIRTYPE, b"")]
        entries.extend((name, tarfile.REGTYPE, b"x") for name in REQUIRED)
        self.write_archive(entries)
        with self.assertRaisesRegex(ArchiveValidationError, "Duplicate"):
            validate_archive(self.archive_path)

    def test_rejects_regular_file_as_ancestor(self):
        entries = [(name, tarfile.REGTYPE, b"x") for name in REQUIRED]
        entries.append(("snmp", tarfile.REGTYPE, b"not-a-directory"))
        self.write_archive(entries)
        with self.assertRaisesRegex(ArchiveValidationError, "ancestor|descendants"):
            validate_archive(self.archive_path)

    def test_rejects_regular_file_ancestor_before_children(self):
        entries = [("snmp", tarfile.REGTYPE, b"not-a-directory")]
        entries.extend((name, tarfile.REGTYPE, b"x") for name in REQUIRED)
        self.write_archive(entries)
        with self.assertRaisesRegex(ArchiveValidationError, "ancestor"):
            validate_archive(self.archive_path)

    def test_rejects_regular_file_with_link_target(self):
        entries = [(name, tarfile.REGTYPE, b"x") for name in REQUIRED]
        entries.append(("extra", tarfile.REGTYPE, b"payload"))
        entries.append(("linked", tarfile.REGTYPE, b"x", "target"))
        self.write_archive(entries)
        with self.assertRaisesRegex(ArchiveValidationError, "link target"):
            validate_archive(self.archive_path)

    def test_rejects_missing_tar_terminator(self):
        self.write_archive()
        archive_data = gzip.decompress(self.archive_path.read_bytes())
        last_data_block = (len(archive_data.rstrip(b"\\0")) - 1) // 512
        archive_data = (
            archive_data[: (last_data_block + 1) * 512] + b"\\0" * 512
        )
        self.archive_path.write_bytes(gzip.compress(archive_data))

        with self.assertRaisesRegex(ArchiveValidationError, "two-block tar terminator"):
            validate_archive(self.archive_path)

    def test_rejects_invalid_header_after_required_files(self):
        entries = [(name, tarfile.REGTYPE, b"x") for name in REQUIRED]
        entries.append(("extra", tarfile.REGTYPE, b"x"))
        self.write_archive(entries)

        archive_data = bytearray(gzip.decompress(self.archive_path.read_bytes()))
        header_offset = archive_data.index(b"source-root/extra")
        archive_data[header_offset + 148] = ord("X")
        self.archive_path.write_bytes(gzip.compress(archive_data))

        with self.assertRaisesRegex(ArchiveValidationError, "Invalid tar header"):
            validate_archive(self.archive_path)

    def test_rejects_missing_required_file(self):
        self.write_archive(
            [(name, tarfile.REGTYPE, b"x") for name in REQUIRED[:-1]]
        )
        with self.assertRaisesRegex(ArchiveValidationError, "missing required"):
            validate_archive(self.archive_path)

    def test_rejects_multiple_top_level_directories(self):
        entries = [(name, tarfile.REGTYPE, b"x") for name in REQUIRED]
        entries.append(("other-root/extra", tarfile.REGTYPE, b"x"))
        self.write_archive(entries)
        with self.assertRaisesRegex(ArchiveValidationError, "top-level"):
            validate_archive(self.archive_path)

    def test_rejects_expanded_size_over_limit(self):
        entries = [(name, tarfile.REGTYPE, b"x") for name in REQUIRED[:-1]]
        entries.append(
            (REQUIRED[-1], tarfile.REGTYPE, b"x" * (MAX_UNPACKED_BYTES + 1))
        )
        self.write_archive(entries)
        with self.assertRaisesRegex(ArchiveValidationError, "expanded-size"):
            validate_archive(self.archive_path)

    def test_rejects_excessive_member_count(self):
        entries = [(name, tarfile.REGTYPE, b"x") for name in REQUIRED]
        entries.extend(
            (f"extra-{index}", tarfile.REGTYPE, b"")
            for index in range(MAX_MEMBERS)
        )
        self.write_archive(entries)
        with self.assertRaisesRegex(ArchiveValidationError, "members"):
            validate_archive(self.archive_path)


if __name__ == "__main__":
    unittest.main()
