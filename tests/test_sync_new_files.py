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


if __name__ == "__main__":
    unittest.main()
