import tempfile
import unittest
from pathlib import Path

from simfea_api.security import safe_child_dir, safe_upload_path


class SafeUploadPathTest(unittest.TestCase):
    def test_uses_filename_basename(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            result = safe_upload_path(root, "../outside.md")

        self.assertEqual(result.name, "outside.md")
        self.assertEqual(result.parent, root.resolve())

    def test_rejects_empty_upload_filename(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                safe_upload_path(Path(tmp), "")


class SafeChildDirTest(unittest.TestCase):
    def test_accepts_child_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            result = safe_child_dir(root, "run-001")

        self.assertEqual(result, (root / "run-001").resolve())

    def test_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                safe_child_dir(Path(tmp), "../outside")


if __name__ == "__main__":
    unittest.main()
