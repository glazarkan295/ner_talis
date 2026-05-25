import json
import sys
import unittest
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


if __name__ == "__main__":
    unittest.main()
