"""Загрузка изображений файлом в конструкторы (ТЗ доп.§2)."""

import base64
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services import admin_panel_service as aps


def _png_b64(size=(8, 8)):
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGBA", size, (10, 20, 30, 255)).save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


class ImageUploadTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._saved = os.environ.get("PUBLIC_UPLOADS_ASSETS_DIR")
        os.environ["PUBLIC_UPLOADS_ASSETS_DIR"] = self._tmp.name
        self.addCleanup(self._restore)

    def _restore(self):
        if self._saved is None:
            os.environ.pop("PUBLIC_UPLOADS_ASSETS_DIR", None)
        else:
            os.environ["PUBLIC_UPLOADS_ASSETS_DIR"] = self._saved

    def test_save_uploaded_image_writes_file_and_returns_local_path(self):
        res = aps.save_uploaded_image(category="items_models", key="iron_sword", content_base64=_png_b64())
        self.assertTrue(res["path"].startswith("/assets/admin_uploads/items_models/iron_sword"))
        # Файл реально записан в том загрузок.
        rel = res["path"].removeprefix("/assets/")
        self.assertTrue((Path(self._tmp.name) / rel).is_file())
        self.assertEqual((res["width"], res["height"]), (8, 8))
        self.assertGreater(res["bytes"], 0)
        self.assertEqual(res["variants"], {})

    def test_creates_proportional_preview_variants_without_upscaling(self):
        res = aps.save_uploaded_image(category="backgrounds", key="wide", content_base64=_png_b64((1600, 800)))
        self.assertEqual(set(res["variants"]), {"256", "512", "1024"})
        from PIL import Image
        for edge, public_path in res["variants"].items():
            path = Path(self._tmp.name) / public_path.removeprefix("/assets/")
            self.assertTrue(path.is_file())
            with Image.open(path) as image:
                self.assertEqual(image.size, (int(edge), int(edge) // 2))

    def test_accepts_data_uri_prefix(self):
        res = aps.save_uploaded_image(category="items", key="x", content_base64="data:image/png;base64," + _png_b64())
        self.assertTrue(res["path"].endswith(".png"))

    def test_rejects_non_image(self):
        with self.assertRaises(ValueError):
            aps.save_uploaded_image(category="items", key="x", content_base64=base64.b64encode(b"not an image").decode())

    def test_requires_key(self):
        with self.assertRaises(ValueError):
            aps.save_uploaded_image(category="items", key="  ", content_base64=_png_b64())

    def test_category_and_key_sanitized(self):
        res = aps.save_uploaded_image(category="../evil", key="../../etc/passwd", content_base64=_png_b64())
        # Путь остаётся внутри admin_uploads (без обхода каталогов).
        self.assertTrue(res["path"].startswith("/assets/admin_uploads/"))
        self.assertNotIn("..", res["path"])


if __name__ == "__main__":
    unittest.main()
