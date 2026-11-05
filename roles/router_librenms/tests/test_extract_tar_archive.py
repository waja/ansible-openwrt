"""Tests for the LibreNMS archive extractor."""

import io
import tarfile
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parents[1] / "files"))

from extract_tar_archive import extract_archive


class ExtractArchiveTests(unittest.TestCase):
    """Exercise safe extraction of LibreNMS source archives."""

    def create_archive(self, archive_path, entries):
        """Create a gzip-compressed tar archive from test entries."""
        with tarfile.open(archive_path, "w:gz") as archive:
            for name, content, kind, linkname in entries:
                info = tarfile.TarInfo(name)
                if kind == "directory":
                    info.type = tarfile.DIRTYPE
                    archive.addfile(info)
                elif kind == "symlink":
                    info.type = tarfile.SYMTYPE
                    info.linkname = linkname
                    archive.addfile(info)
                else:
                    data = content.encode()
                    info.size = len(data)
                    archive.addfile(info, io.BytesIO(data))

    def test_extracts_files_without_top_level_directory(self):
        """Verify extraction strips the sole top-level directory."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "source.tar.gz"
            destination = root / "destination"
            destination.mkdir()
            self.create_archive(
                archive,
                [
                    ("agent-main/snmp", "", "directory", ""),
                    ("agent-main/snmp/distro", "distro script", "file", ""),
                ],
            )

            extract_archive(archive, destination)

            self.assertEqual(
                (destination / "snmp/distro").read_text(),
                "distro script",
            )
            self.assertFalse((destination / "agent-main").exists())

    def test_accepts_archive_without_explicit_root_entry(self):
        """Accept members beneath a root absent from the archive entries."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "source.tar.gz"
            destination = root / "destination"
            destination.mkdir()
            self.create_archive(
                archive,
                [("agent-main/snmp/distro", "script", "file", "")],
            )

            extract_archive(archive, destination)

            self.assertEqual((destination / "snmp/distro").read_text(), "script")

    def test_allows_safe_relative_symlinks(self):
        """Verify safe relative symbolic links are preserved."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "source.tar.gz"
            destination = root / "destination"
            destination.mkdir()
            self.create_archive(
                archive,
                [
                    ("agent-main", "", "directory", ""),
                    ("agent-main/snmp", "", "directory", ""),
                    ("agent-main/snmp/target", "data", "file", ""),
                    (
                        "agent-main/snmp/link",
                        "",
                        "symlink",
                        "target",
                    ),
                ],
            )

            extract_archive(archive, destination)

            self.assertTrue((destination / "snmp/link").is_symlink())
            self.assertEqual((destination / "snmp/link").read_text(), "data")

    def test_rejects_parent_directory_traversal(self):
        """Verify parent-directory traversal is rejected."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "source.tar.gz"
            destination = root / "destination"
            destination.mkdir()
            outside = root / "outside"
            self.create_archive(
                archive,
                [
                    ("agent-main", "", "directory", ""),
                    ("agent-main/../../outside", "bad", "file", ""),
                ],
            )

            with self.assertRaises(ValueError):
                extract_archive(archive, destination)

            self.assertFalse(outside.exists())

    def test_rejects_absolute_paths(self):
        """Verify absolute archive paths are rejected explicitly."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "source.tar.gz"
            destination = root / "destination"
            destination.mkdir()
            self.create_archive(
                archive,
                [
                    ("/tmp/outside", "bad", "file", ""),
                ],
            )

            with self.assertRaisesRegex(ValueError, "^Unsafe archive path:"):
                extract_archive(archive, destination)

    def test_rejects_symlinks_escaping_destination(self):
        """Verify symbolic links cannot escape the destination."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "source.tar.gz"
            destination = root / "destination"
            destination.mkdir()
            self.create_archive(
                archive,
                [
                    ("agent-main", "", "directory", ""),
                    (
                        "agent-main/snmp/link",
                        "",
                        "symlink",
                        "../../../../outside",
                    ),
                ],
            )

            with self.assertRaises(tarfile.FilterError):
                extract_archive(archive, destination)

    def test_requires_empty_destination(self):
        """Verify extraction refuses a non-empty destination."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "source.tar.gz"
            destination = root / "destination"
            destination.mkdir()
            (destination / "existing").touch()
            self.create_archive(
                archive,
                [("agent-main", "", "directory", "")],
            )

            with self.assertRaises(ValueError):
                extract_archive(archive, destination)


if __name__ == "__main__":
    unittest.main()
