import json
import unittest
from http import HTTPStatus
from pathlib import Path
from urllib.parse import urlsplit


_PHOTO_DIR = Path(__file__).resolve().parents[1] / "bot" / "assets" / "httpbird"


class HttpbirdAssetsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.credits = json.loads((_PHOTO_DIR / "credits.json").read_text(encoding="utf-8"))

    def test_each_credited_status_has_a_jpeg_and_no_extra_images(self):
        self.assertTrue(self.credits)
        self.assertEqual(
            set(self.credits),
            {photo.stem for photo in _PHOTO_DIR.glob("*.jpg")},
        )
        for code in self.credits:
            with self.subTest(code=code):
                self.assertEqual(str(HTTPStatus(int(code)).value), code)
                with (_PHOTO_DIR / f"{code}.jpg").open("rb") as photo:
                    self.assertEqual(photo.read(2), b"\xff\xd8")
                    photo.seek(-2, 2)
                    self.assertEqual(photo.read(2), b"\xff\xd9")

    def test_each_photo_has_credit_and_alt_text(self):
        for code, credit in self.credits.items():
            with self.subTest(code=code):
                for field in ("alt", "author", "license"):
                    self.assertTrue(credit[field].strip())
                source = urlsplit(credit["source"])
                self.assertEqual((source.scheme, source.hostname), ("https", "commons.wikimedia.org"))
