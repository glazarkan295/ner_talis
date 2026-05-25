import json
import struct
import sys
import unittest
import zlib
from collections import defaultdict
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT_DIR.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.item_registry import validate_item_registry_duplicates


def _registry_files():
    return [
        path
        for path in sorted((PROJECT_ROOT / "data").glob("items_*.json"))
        if not path.name.startswith("items_import_")
    ]


def _load_items(path):
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def _validate_png(path):
    data = path.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("bad PNG signature")
    position = 8
    seen_ihdr = False
    seen_iend = False
    while position + 12 <= len(data):
        length = struct.unpack(">I", data[position : position + 4])[0]
        chunk_type = data[position + 4 : position + 8]
        chunk_start = position + 8
        chunk_end = chunk_start + length
        crc_end = chunk_end + 4
        if crc_end > len(data):
            raise ValueError(f"truncated chunk {chunk_type!r}")
        expected_crc = struct.unpack(">I", data[chunk_end:crc_end])[0]
        actual_crc = zlib.crc32(chunk_type + data[chunk_start:chunk_end]) & 0xFFFFFFFF
        if expected_crc != actual_crc:
            raise ValueError(f"bad crc for {chunk_type!r}")
        if chunk_type == b"IHDR":
            seen_ihdr = True
        if chunk_type == b"IEND":
            seen_iend = True
            if crc_end != len(data):
                raise ValueError("trailing bytes after IEND")
            break
        position = crc_end
    if not seen_ihdr or not seen_iend:
        raise ValueError("missing IHDR or IEND")


class ItemRegistryIntegrityTest(unittest.TestCase):
    def test_registry_does_not_hide_conflicting_duplicate_item_ids(self):
        validate_item_registry_duplicates(_registry_files())
        occurrences = defaultdict(list)
        for path in _registry_files():
            for index, item in enumerate(_load_items(path), start=1):
                item_id = str(item.get("id") or item.get("item_id") or "").strip()
                if item_id:
                    occurrences[item_id].append(f"{path.relative_to(PROJECT_ROOT)}:{index}")
        duplicates = {item_id: places for item_id, places in occurrences.items() if len(places) > 1}
        self.assertEqual({}, duplicates)

    def test_all_declared_item_icons_exist_under_web_public(self):
        missing = []
        for path in _registry_files():
            for index, item in enumerate(_load_items(path), start=1):
                icon = str(item.get("icon") or "").strip()
                if not icon or icon.startswith(("http://", "https://")):
                    continue
                icon_path = PROJECT_ROOT / "web" / "public" / icon.lstrip("/")
                if not icon_path.exists():
                    item_id = str(item.get("id") or item.get("item_id") or "?")
                    missing.append(f"{path.relative_to(PROJECT_ROOT)}:{index} {item_id} -> {icon}")
        self.assertEqual([], missing)

    def test_web_public_item_png_assets_are_valid_png_files(self):
        invalid = []
        assets_dir = PROJECT_ROOT / "web" / "public" / "assets" / "items"
        for path in sorted(assets_dir.rglob("*.png")):
            try:
                _validate_png(path)
            except Exception as exc:
                invalid.append(f"{path.relative_to(PROJECT_ROOT)}: {exc}")
        self.assertEqual([], invalid)


if __name__ == "__main__":
    unittest.main()
