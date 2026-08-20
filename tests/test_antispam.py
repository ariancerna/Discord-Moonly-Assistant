import tempfile
import unittest
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw

from utils.antispam import AntispamStore, fingerprint_image, hamming_distance


def make_test_image(color: str = "#10131a", accent: str = "#00d26a") -> bytes:
    image = Image.new("RGB", (320, 180), color)
    draw = ImageDraw.Draw(image)
    draw.rectangle((40, 35, 280, 145), outline=accent, width=8)
    draw.rectangle((105, 75, 215, 110), fill=accent)
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


class FingerprintTests(unittest.TestCase):
    def test_exact_images_have_same_hashes(self):
        data = make_test_image()
        first = fingerprint_image(data, "first.png", "image/png")
        second = fingerprint_image(data, "renamed.png", "image/png")

        self.assertEqual(first.sha256, second.sha256)
        self.assertEqual(first.dhash, second.dhash)
        self.assertEqual(hamming_distance(first.dhash, second.dhash), 0)

    def test_reencoded_image_remains_visually_close(self):
        original = make_test_image()
        with Image.open(BytesIO(original)) as source:
            output = BytesIO()
            source.save(output, format="JPEG", quality=75)
        reencoded = output.getvalue()

        first = fingerprint_image(original, "original.png", "image/png")
        second = fingerprint_image(reencoded, "reencoded.jpg", "image/jpeg")

        self.assertNotEqual(first.sha256, second.sha256)
        self.assertLessEqual(hamming_distance(first.dhash, second.dhash), 8)

    def test_store_finds_exact_and_visual_matches(self):
        original = fingerprint_image(make_test_image(), "spam.png", "image/png")
        with tempfile.TemporaryDirectory() as directory:
            store = AntispamStore(str(Path(directory) / "antispam.db"))
            self.assertTrue(store.add_fingerprint(123, original))
            self.assertFalse(store.add_fingerprint(123, original))
            self.assertEqual(store.find_match(123, original, 8), ("exact", 0))
            self.assertEqual(store.counts(123), (1, 0))


if __name__ == "__main__":
    unittest.main()
