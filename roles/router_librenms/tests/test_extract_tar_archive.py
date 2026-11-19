"""Tests for the LibreNMS archive extractor."""

import io
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parents[1] / "files"))

from extract_tar_archive import (\n    BoundedTarInfo,\n    _expanded_member_size,\n    extract_archive,\n)


class ExtractArchiveTests(unittest.TestCase):
    """Exercise safe extraction of LibreNMS source archives."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.archive = self.root / "source.tar.gz"
        self.destination = self.root / "destination"
        self.destination.mkdir()

    def tearDown(self):
        self.temporary.cleanup()

    def create_archive(self, entries, mode="w:gz"):
        """Create a tar archive from simple test entries."""
        with tarfile.open(self.archive, mode) as archive:
            for name, content, kind, target in entries:
                member = tarfile.TarInfo(name)
                if kind == "directory":
                    member.type = tarfile.DIRTYPE
                    member.mode = 0o755
                    archive.addfile(member)
                elif kind == "symlink":
                    member.type = tarfile.SYMTYPE
                    member.linkname = target
                    archive.addfile(member)
                elif kind == "hardlink":
                    member.type = tarfile.LNKTYPE
                    member.linkname = target
                    archive.addfile(member)
                else:
                    data = content.encode()
                    member.size = len(data)
                    archive.addfile(member, io.BytesIO(data))

    def test_extracts_and_strips_top_level_directory(self):
        self.create_archive([
            ("agent-main/snmp", "", "directory", ""),
            ("agent-main/snmp/distro", "script", "file", ""),
        ])
        extract_archive(self.archive, self.destination)
        self.assertEqual(
            (self.destination / "snmp/distro").read_text(), "script"
        )
        self.assertFalse((self.destination / "agent-main").exists())

    def test_accepts_archive_without_explicit_root_entry(self):
        self.create_archive([
            ("agent-main/snmp/distro", "script", "file", ""),
        ])
        extract_archive(self.archive, self.destination)
        self.assertEqual(
            (self.destination / "snmp/distro").read_text(), "script"
        )

    def test_accepts_uncompressed_tar(self):
        self.create_archive(
            [("agent-main/file", "data", "file", "")], mode="w:"
        )
        extract_archive(self.archive, self.destination)
        self.assertEqual((self.destination / "file").read_text(), "data")

    def test_allows_safe_relative_symlinks(self):
        self.create_archive([
            ("agent-main/snmp", "", "directory", ""),
            ("agent-main/snmp/target", "data", "file", ""),
            ("agent-main/snmp/link", "", "symlink", "target"),
        ])
        extract_archive(self.archive, self.destination)
        self.assertEqual(
            (self.destination / "snmp/link").read_text(), "data"
        )

    def test_rejects_path_traversal(self):
        self.create_archive([
            ("agent-main/../../outside", "bad", "file", ""),
        ])
        with self.assertRaisesRegex(ValueError, "Unsafe archive path"):
            extract_archive(self.archive, self.destination)
        self.assertFalse((self.root / "outside").exists())

    def test_rejects_absolute_paths(self):
        self.create_archive([("/tmp/outside", "bad", "file", "")])
        with self.assertRaisesRegex(ValueError, "Unsafe archive path"):
            extract_archive(self.archive, self.destination)

    def test_rejects_escaping_symlinks(self):
        self.create_archive([
            (
                "agent-main/snmp/link",
                "",
                "symlink",
                "../../../../outside",
            ),
        ])
        with self.assertRaises(tarfile.FilterError):
            extract_archive(self.archive, self.destination)

    def test_rejects_hard_links(self):
        self.create_archive([
            ("agent-main/file", "data", "file", ""),
            ("agent-main/link", "", "hardlink", "agent-main/file"),
        ])
        with self.assertRaisesRegex(ValueError, "Hard links"):
            extract_archive(self.archive, self.destination)

    def test_rejects_multiple_top_level_directories(self):
        self.create_archive([
            ("first/file", "one", "file", ""),
            ("second/file", "two", "file", ""),
        ])
        with self.assertRaisesRegex(ValueError, "top-level directory"):
            extract_archive(self.archive, self.destination)

    def test_rejects_oversized_archive(self):
        self.create_archive([("agent-main/file", "data", "file", "")])
        with mock.patch(
            "extract_tar_archive.MAX_ARCHIVE_SIZE",
            self.archive.stat().st_size - 1,
        ):
            with self.assertRaisesRegex(ValueError, "compressed size"):
                extract_archive(self.archive, self.destination)

    def test_rejects_too_many_members_before_scanning_the_archive(self):
        self.create_archive([
            ("agent-main/one", "1", "file", ""),
            ("agent-main/two", "2", "file", ""),
            ("agent-main/three", "3", "file", ""),
        ])
        original_next = tarfile.TarFile.next
        calls = 0

        def counting_next(archive):
            nonlocal calls
            calls += 1
            return original_next(archive)

        with (
            mock.patch("extract_tar_archive.MAX_ARCHIVE_MEMBERS", 1),
            mock.patch.object(tarfile.TarFile, "next", counting_next),
        ):
            with self.assertRaisesRegex(ValueError, "too many members"):
                extract_archive(self.archive, self.destination)
        self.assertEqual(calls, 3)

    def test_rejects_excessive_expanded_size(self):
        self.create_archive([("agent-main/file", "payload", "file", "")])
        with mock.patch("extract_tar_archive.MAX_EXPANDED_SIZE", 1):
            with self.assertRaisesRegex(ValueError, "expanded size"):
                extract_archive(self.archive, self.destination)

    def test_rejects_oversized_pax_metadata(self):
        with tarfile.open(self.archive, "w:gz", format=tarfile.PAX_FORMAT) as archive:
            member = tarfile.TarInfo("agent-main/file")
            member.pax_headers = {"comment": "x" * 1024}
            member.size = 1
            archive.addfile(member, io.BytesIO(b"x"))
        with mock.patch(
            "extract_tar_archive.MAX_MEMBER_METADATA_SIZE", 512
        ):
            with self.assertRaisesRegex(ValueError, "metadata exceeds"):
                extract_archive(self.archive, self.destination)

    def test_rejects_cumulative_pax_metadata(self):
        with tarfile.open(self.archive, "w:gz", format=tarfile.PAX_FORMAT) as archive:
            for name in ("agent-main/one", "agent-main/two"):
                member = tarfile.TarInfo(name)
                member.pax_headers = {"comment": "x" * 300}
                member.size = 1
                archive.addfile(member, io.BytesIO(b"x"))
        with mock.patch(
            "extract_tar_archive.MAX_MEMBER_METADATA_SIZE", 512
        ), mock.patch(
            "extract_tar_archive.MAX_TOTAL_METADATA_SIZE", 512
        ):
            with self.assertRaisesRegex(ValueError, "Archive metadata"):
                extract_archive(self.archive, self.destination)

    def test_counts_sparse_logical_size_towards_expansion_limit(self):
        member = tarfile.TarInfo("agent-main/sparse")
        member.size = 1
        member.pax_headers = {"GNU.sparse.realsize": "100"}
        self.assertEqual(_expanded_member_size(member), 100)

    def test_requires_empty_destination(self):
        (self.destination / "existing").touch()
        self.create_archive([("agent-main/file", "data", "file", "")])
        with self.assertRaisesRegex(ValueError, "empty directory"):
            extract_archive(self.archive, self.destination)


if __name__ == "__main__":
    unittest.main()
