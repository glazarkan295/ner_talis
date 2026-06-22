"""Вывод сообщения игроку (дополнение к ТЗ): валидация формата/блоков/лимитов."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services import message_output_service as mo


class MessageOutputValidateTest(unittest.TestCase):
    def test_empty_is_ok(self):
        self.assertTrue(mo.validate_message_output(None)["ok"])
        self.assertTrue(mo.validate_message_output({})["ok"])

    def test_single_requires_text_or_image(self):
        self.assertTrue(mo.validate_message_output({"format": "single", "text": "Привет"})["ok"])
        self.assertTrue(mo.validate_message_output({"format": "single", "image": "/assets/x.png"})["ok"])
        res = mo.validate_message_output({"format": "single", "text": "", "image": ""})
        self.assertTrue(res["ok"])  # пустой single без полей допустим (необязательное сообщение)

    def test_external_image_rejected(self):
        res = mo.validate_message_output({"format": "single", "text": "T", "image": "https://example.com/a.png"})
        self.assertFalse(res["ok"])
        self.assertTrue(any("файлом" in e for e in res["errors"]))

    def test_caption_and_text_limits_warn(self):
        long_caption = {"format": "single", "image": "/assets/a.png", "text": "x" * 1500}
        res = mo.validate_message_output(long_caption)
        self.assertTrue(res["ok"])
        self.assertTrue(any("подпись" in w.lower() for w in res["warnings"]))
        too_long = {"format": "single", "text": "y" * 5000}
        self.assertTrue(any("Telegram" in w for w in mo.validate_message_output(too_long)["warnings"]))

    def test_multiple_needs_blocks(self):
        res = mo.validate_message_output({"format": "multiple", "blocks": []})
        self.assertFalse(res["ok"])
        ok = mo.validate_message_output({"format": "multiple", "blocks": [{"order": 1, "text": "Шаг 1"}, {"order": 2, "image": "/assets/b.png"}]})
        self.assertTrue(ok["ok"], ok["errors"])

    def test_duplicate_order_warns(self):
        res = mo.validate_message_output({"format": "multiple", "blocks": [{"order": 1, "text": "a"}, {"order": 1, "text": "b"}]})
        self.assertTrue(res["ok"], res["errors"])
        self.assertTrue(any("порядок" in w.lower() for w in res["warnings"]))

    def test_unknown_format(self):
        self.assertFalse(mo.validate_message_output({"format": "carrier_pigeon", "text": "T"})["ok"])

    def test_meta(self):
        meta = mo.meta()
        self.assertTrue(any(f["value"] == "multiple" for f in meta["formats"]))
        self.assertEqual(meta["limits"]["tgCaption"], 1024)


class CityNodeEntryMessageTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._saved = os.environ.get("CITY_CONSTRUCTOR_PATH")
        os.environ["CITY_CONSTRUCTOR_PATH"] = str(Path(self._tmp.name) / "city.json")
        self.addCleanup(self._restore)

    def _restore(self):
        if self._saved is None:
            os.environ.pop("CITY_CONSTRUCTOR_PATH", None)
        else:
            os.environ["CITY_CONSTRUCTOR_PATH"] = self._saved

    def test_node_entry_message_validated(self):
        from services import city_constructor_service as city
        good = city.store().create("n_ok", {"_kind": "city_node", "name": "Узел", "node_type": "city", "entry_message": {"format": "single", "text": "Добро пожаловать!"}})
        self.assertTrue(city.validate("city_node", good)["ok"], city.validate("city_node", good)["errors"])
        bad = city.store().create("n_bad", {"_kind": "city_node", "name": "Узел", "node_type": "city", "entry_message": {"format": "single", "text": "T", "image": "http://x/y.png"}})
        res = city.validate("city_node", bad)
        self.assertFalse(res["ok"])
        self.assertTrue(any("Сообщение при входе" in e for e in res["errors"]))


if __name__ == "__main__":
    unittest.main()
