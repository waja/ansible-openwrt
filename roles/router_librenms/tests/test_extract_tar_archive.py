"""Tests for the LibreNMS archive extractor."""

import io
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parents[1] / "files"))

from extract_tar_archive import extract_archive


class ExtractArchiveTests(unittest.TestCase):
    """Exercise safe extraction of Git source archives."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.archive = self.root / "source.tar"
        self.destination = self.root / "destination"
        self.destination.mkdir()

    def tearDown(self):
        self.temporary.cleanup()

    def create_archive(self, entries, mode="w:"):
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

    def test_does_not_retain_members_with_global_pax_metadata(self):
        global_headers = {f"test.key.{index}": "value" for index in range(128)}
        with self.archive.open("wb") as output:
            output.write(tarfile.TarInfo.create_pax_global_header(global_headers))
            with tarfile.open(
                fileobj=output, mode="w:", format=tarfile.PAX_FORMAT
            ) as archive:
                for index in range(20):
                    archive.addfile(tarfile.TarInfo(f"agent-main/file-{index}"))

        original_extract = tarfile.TarFile.extract
        cached_member_counts = []

        def tracking_extract(archive, member, *args, **kwargs):
            cached_member_counts.append(len(archive.members))
            return original_extract(archive, member, *args, **kwargs)

        with mock.patch.object(tarfile.TarFile, "extract", tracking_extract):
            extract_archive(self.archive, self.destination)

        self.assertEqual(len(cached_member_counts), 20)
        self.assertLessEqual(max(cached_member_counts), 1)
        self.assertEqual(len(list(self.destination.iterdir())), 20)

    def test_extracts_git_archive_with_global_pax_and_long_paths(self):
        repository = self.root / "repository"
        long_directory = "a" * 110
        (repository / long_directory).mkdir(parents=True)
        (repository / long_directory / "script.sh").write_text("script")

        subprocess.run(["git", "init", "-q", str(repository)], check=True)
        subprocess.run(
            ["git", "-C", str(repository), "config", "user.email",
             "test@example.invalid"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(repository), "config", "user.name", "Test"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(repository), "add", "."], check=True
        )
        subprocess.run(
            ["git", "-C", str(repository), "commit", "--no-gpg-sign", "-qm", "fixture"],
            check=True,
        )
        with self.archive.open("wb") as output:
            subprocess.run(
                ["git", "-C", str(repository), "archive", "--format=tar", "--prefix=source-root/", "HEAD"],
                check=True,
                stdout=output,
            )

        with tarfile.open(self.archive) as archive:
            self.assertIn("comment", archive.pax_headers)
            self.assertTrue(
                any("path" in member.pax_headers for member in archive)
            )

        extract_archive(self.archive, self.destination)
        self.assertEqual(
            (self.destination / long_directory / "script.sh").read_text(),
            "script",
        )

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
        self.create_archive([("agent-main/snmp/distro", "script", "file", "")])
        extract_archive(self.archive, self.destination)
        self.assertEqual(
            (self.destination / "snmp/distro").read_text(), "script"
        )

    def test_accepts_uncompressed_tar(self):
        self.create_archive([("agent-main/file", "data", "file", "")])
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
        self.create_archive([("agent-main/../../outside", "bad", "file", "")])
        with self.assertRaisesRegex(ValueError, "Unsafe archive path"):
            extract_archive(self.archive, self.destination)
        self.assertFalse((self.root / "outside").exists())

    def test_rejects_absolute_paths(self):
        self.create_archive([("/tmp/outside", "bad", "file", "")])
        with self.assertRaisesRegex(ValueError, "Unsafe archive path"):
            extract_archive(self.archive, self.destination)

    def test_rejects_escaping_symlinks(self):
        self.create_archive([
            ("agent-main/snmp/link", "", "symlink", "../../../../outside"),
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

    def test_rejects_gnu_longname_entries(self):
        name = "agent-main/" + "a" * 120
        with tarfile.open(self.archive, "w:", format=tarfile.GNU_FORMAT) as archive:
            member = tarfile.TarInfo(name)
            member.size = 1
            archive.addfile(member, io.BytesIO(b"x"))
        with self.assertRaisesRegex(ValueError, "GNU longname"):
            extract_archive(self.archive, self.destination)

    def test_rejects_old_gnu_sparse_entries(self):
        member = tarfile.TarInfo("agent-main/sparse")
        member.type = tarfile.GNUTYPE_SPARSE
        member.size = 1
        header = bytearray(member.tobuf(tarfile.GNU_FORMAT))
        header[386:398] = tarfile.itn(0, 12, tarfile.GNU_FORMAT)
        header[398:410] = tarfile.itn(1, 12, tarfile.GNU_FORMAT)
        header[482] = 0
        header[483:495] = tarfile.itn(1, 12, tarfile.GNU_FORMAT)
        header[148:156] = b"        "
        checksum = tarfile.calc_chksums(header)[0]
        header[148:156] = f"{checksum:06o}\0 ".encode()

        with self.archive.open("wb") as archive:
            archive.write(header)
            archive.write(b"x")
            archive.write(b"\0" * (2 * tarfile.BLOCKSIZE))

        with self.assertRaisesRegex(ValueError, "GNU longname and sparse"):
            extract_archive(self.archive, self.destination)

    def test_rejects_pax_sparse_entries(self):
        with tarfile.open(
            self.archive, "w:", format=tarfile.PAX_FORMAT
        ) as archive:
            member = tarfile.TarInfo("agent-main/sparse")
            member.pax_headers = {
                "GNU.sparse.major": "1",
                "GNU.sparse.minor": "0",
                "GNU.sparse.realsize": "3",
            }
            payload = b"1\n0\n3\n" + b"\0" * (tarfile.BLOCKSIZE - 6) + b"abc"
            member.size = len(payload)
            archive.addfile(member, io.BytesIO(payload))
        with self.assertRaisesRegex(ValueError, "GNU sparse"):
            extract_archive(self.archive, self.destination)

    def test_rejects_unsupported_member_type(self):
        with tarfile.open(self.archive, "w:") as archive:
            member = tarfile.TarInfo("agent-main/unsupported")
            member.type = b"Z"
            member.size = 4
            archive.addfile(member, io.BytesIO(b"data"))
        with self.assertRaisesRegex(ValueError, "Unsupported archive member"):
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

    def test_rejects_too_many_members(self):
        self.create_archive([
            ("agent-main/one", "1", "file", ""),
            ("agent-main/two", "2", "file", ""),
        ])
        with mock.patch("extract_tar_archive.MAX_ARCHIVE_MEMBERS", 1):
            with self.assertRaisesRegex(ValueError, "too many members"):
                extract_archive(self.archive, self.destination)

    def test_rejects_excessive_expanded_size(self):
        self.create_archive([("agent-main/file", "payload", "file", "")])
        with mock.patch("extract_tar_archive.MAX_EXPANDED_SIZE", 1):
            with self.assertRaisesRegex(ValueError, "expanded size"):
                extract_archive(self.archive, self.destination)

    def test_rejects_oversized_pax_metadata(self):
        with tarfile.open(
            self.archive, "w:", format=tarfile.PAX_FORMAT
        ) as archive:
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
        with tarfile.open(
            self.archive, "w:", format=tarfile.PAX_FORMAT
        ) as archive:
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

    def test_requires_empty_destination(self):
        (self.destination / "existing").touch()
        self.create_archive([("agent-main/file", "data", "file", "")])
        with self.assertRaisesRegex(ValueError, "empty directory"):
            extract_archive(self.archive, self.destination)


if __name__ == "__main__":
    unittest.main()
