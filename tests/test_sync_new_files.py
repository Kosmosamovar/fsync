import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sync_new_files import build_index, copy_new_files, scan_source


class SyncNewFilesTest(unittest.TestCase):
    def test_build_index_and_copy_only_missing_files(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            src = root / "src"
            dst = root / "dst"
            src.mkdir()
            dst.mkdir()

            (src / "a.txt").write_text("hello world", encoding="utf-8")
            (src / "nested").mkdir()
            (src / "nested" / "b.bin").write_bytes(b"\x00\x01\x02\x03")

            index_path = root / "sync_index.json"
            manifest = build_index(src, index_path)

            self.assertIn("a.txt", manifest["files"])
            self.assertIn("nested/b.bin", manifest["files"])
            self.assertEqual(manifest["files"]["a.txt"]["size"], len("hello world".encode("utf-8")))

            copied = copy_new_files(src, dst, index_path)
            self.assertEqual(copied, ["a.txt", "nested/b.bin"])
            self.assertEqual((dst / "a.txt").read_text(encoding="utf-8"), "hello world")
            self.assertEqual((dst / "nested" / "b.bin").read_bytes(), b"\x00\x01\x02\x03")

            copied_again = copy_new_files(src, dst, index_path)
            self.assertEqual(copied_again, [])

            (src / "a.txt").write_text("updated content", encoding="utf-8")
            changed = copy_new_files(src, dst, index_path)
            self.assertEqual(changed, ["a.txt"])
            self.assertEqual((dst / "a.txt").read_text(encoding="utf-8"), "updated content")

            with index_path.open("r", encoding="utf-8") as handle:
                saved = __import__("json").load(handle)
            self.assertIn("a.txt", saved["files"])
            self.assertEqual(saved["files"]["a.txt"]["hash"], __import__("hashlib").sha256(b"updated content").hexdigest())

    def test_scan_source_skips_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            src = root / "src"
            src.mkdir()
            valid = src / "valid.txt"
            broken = src / "broken.txt"
            valid.write_text("ok", encoding="utf-8")
            broken.write_text("temporary", encoding="utf-8")

            real_stat = Path.stat

            def fake_stat(self, *args, **kwargs):
                if self == broken:
                    raise FileNotFoundError("missing file")
                return real_stat(self, *args, **kwargs)

            with patch.object(Path, "stat", fake_stat):
                manifest = scan_source(src)

            self.assertIn("valid.txt", manifest)
            self.assertNotIn("broken.txt", manifest)

    def test_simple_mode_uses_name_and_size(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            src = root / "src"
            dst = root / "dst"
            src.mkdir()
            dst.mkdir()

            src_file = src / "report.txt"
            src_file.write_text("alpha", encoding="utf-8")
            index_path = root / "index.json"
            build_index(src, index_path)

            copied = copy_new_files(src, dst, index_path, simple_mode=True)
            self.assertEqual(copied, ["report.txt"])
            self.assertEqual((dst / "report.txt").read_text(encoding="utf-8"), "alpha")

            src_file.write_text("beta", encoding="utf-8")
            copied = copy_new_files(src, dst, index_path, simple_mode=True)
            self.assertEqual(copied, ["report.txt"])
            self.assertEqual((dst / "report.txt").read_text(encoding="utf-8"), "beta")

            src_file.write_text("zzzz", encoding="utf-8")
            copied = copy_new_files(src, dst, index_path, simple_mode=True)
            self.assertEqual(copied, [])
            self.assertEqual((dst / "report.txt").read_text(encoding="utf-8"), "beta")

    def test_same_project_folder_with_new_folder_stays_empty(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            project = root / "project"
            new_dir = project / "new"
            project.mkdir()
            new_dir.mkdir()

            (project / "a.txt").write_text("hello", encoding="utf-8")
            (project / "nested").mkdir()
            (project / "nested" / "b.bin").write_bytes(b"\x00\x01")

            index_path = project / "sync_index.json"
            build_index(project, index_path)

            copied = copy_new_files(project, new_dir, index_path)
            self.assertEqual(copied, [])
            self.assertEqual(list(new_dir.rglob("*")), [])

    def test_same_folder_contents_work_with_different_absolute_paths(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            first_root = root / "pc1" / "sync_folder"
            second_root = root / "pc2" / "other" / "sync_folder"
            destination = root / "destination"
            first_root.mkdir(parents=True)
            second_root.mkdir(parents=True)
            destination.mkdir()

            (first_root / "a.txt").write_text("hello", encoding="utf-8")
            (first_root / "nested").mkdir()
            (first_root / "nested" / "b.bin").write_bytes(b"\x00\x01")

            (second_root / "a.txt").write_text("hello", encoding="utf-8")
            (second_root / "nested").mkdir()
            (second_root / "nested" / "b.bin").write_bytes(b"\x00\x01")

            index_path = root / "index.json"
            build_index(first_root, index_path)

            copied = copy_new_files(second_root, destination, index_path)
            self.assertEqual(copied, ["a.txt", "nested/b.bin"])
            self.assertEqual((destination / "a.txt").read_text(encoding="utf-8"), "hello")
            self.assertEqual((destination / "nested" / "b.bin").read_bytes(), b"\x00\x01")


if __name__ == "__main__":
    unittest.main()
