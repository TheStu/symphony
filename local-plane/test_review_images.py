from pathlib import Path
import tempfile
import unittest

from review_images import screenshots


class ReviewImagesTest(unittest.TestCase):
    def test_only_current_card_pngs_are_published(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(list(screenshots(root, "PL-1")), [])
            folder = Path(root, "PL-1/tmp/review/PL-1")
            folder.mkdir(parents=True)
            data = b"\x89PNG\r\n\x1a\nfixture"
            (folder / "mobile.png").write_bytes(data)
            (folder / "notes.txt").write_text("local notes")
            self.assertEqual(list(screenshots(root, "PL-1")), [("mobile.png", data)])
            (folder / "other.png").symlink_to(folder / "notes.txt")
            with self.assertRaises(OSError):
                list(screenshots(root, "PL-1"))


if __name__ == "__main__":
    unittest.main()
