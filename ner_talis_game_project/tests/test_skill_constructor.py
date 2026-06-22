"""Конструктор навыков (ТЗ §7) — валидация определений + RBAC + импорт каталога."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services import skill_constructor_service as sc


def _val(data):
    return sc.validate({"data": data})


class SkillConstructorValidateTest(unittest.TestCase):
    def test_ok_active(self):
        res = _val({
            "name": "Огненный болт", "skill_type": "active", "branch": "mana", "path": "fire",
            "resource_type": "mana", "resource_cost": 10, "cooldown_turns": 2,
            "damage_type": "magic", "target_mode": "single_enemy",
            "weapon_requirements": ["staff", "magic_book"], "unlock_path_level": 25,
            "description": "Бьёт врага огнём.",
        })
        self.assertTrue(res["ok"], res["errors"])

    def test_ok_passive(self):
        res = _val({
            "name": "Каменная кожа", "skill_type": "passive", "branch": "spirit", "path": "shield",
            "resource_type": "none", "resource_cost": 0, "cooldown_turns": 0,
            "damage_type": "none", "target_mode": "passive", "description": "Повышает защиту.",
        })
        self.assertTrue(res["ok"], res["errors"])

    def test_requires_name(self):
        res = _val({"skill_type": "active"})
        self.assertFalse(res["ok"])
        self.assertTrue(any("название" in e.lower() for e in res["errors"]))

    def test_unknown_enums(self):
        res = _val({"name": "X", "skill_type": "ultimate", "resource_type": "stamina", "damage_type": "psychic"})
        self.assertFalse(res["ok"])
        joined = " ".join(res["errors"])
        self.assertIn("тип навыка", joined)
        self.assertIn("тип ресурса", joined)
        self.assertIn("тип урона", joined)

    def test_path_must_match_branch(self):
        res = _val({"name": "X", "branch": "spirit", "path": "fire"})
        self.assertFalse(res["ok"])
        self.assertTrue(any("не относится к ветви" in e for e in res["errors"]))

    def test_negative_numbers_and_html(self):
        res = _val({"name": "X", "resource_cost": -3, "cooldown_turns": -1})
        self.assertFalse(res["ok"])
        joined = " ".join(res["errors"])
        self.assertIn("Стоимость ресурса не может быть отрицательной", joined)
        self.assertIn("Откат не может быть отрицательным", joined)
        res2 = _val({"name": "X", "description": "<script>hack()</script>"})
        self.assertFalse(res2["ok"])
        self.assertTrue(any("HTML" in e for e in res2["errors"]))

    def test_bad_weapon_requirement(self):
        res = _val({"name": "X", "weapon_requirements": ["lightsaber"]})
        self.assertFalse(res["ok"])
        self.assertTrue(any("оружию" in e.lower() for e in res["errors"]))

    def test_passive_with_cost_warns(self):
        res = _val({"name": "X", "skill_type": "passive", "resource_cost": 5, "target_mode": "passive"})
        self.assertTrue(res["ok"], res["errors"])
        self.assertTrue(any("Пассивный навык со стоимостью" in w for w in res["warnings"]))


class SkillConstructorRbacTest(unittest.TestCase):
    def test_perms_registered_and_mapped(self):
        from services import admin_rbac as rbac
        self.assertIn(rbac.PERM_SKILL_DEF_PUBLISH, rbac.ALL_PERMISSIONS)
        self.assertTrue(rbac.has_permission(rbac.CONTENT, "skill_def.create"))
        self.assertTrue(rbac.has_permission(rbac.CONTENT, "skill_def.edit"))
        self.assertFalse(rbac.has_permission(rbac.CONTENT, "skill_def.publish"))
        self.assertTrue(rbac.has_permission(rbac.READ_ONLY, "skill_def.view"))
        self.assertFalse(rbac.has_permission(rbac.READ_ONLY, "skill_def.edit"))
        self.assertTrue(rbac.has_permission(rbac.ADMIN, "skill_def.publish"))
        for action in ("skill_def.publish", "skill_def.disable", "skill_def.archive", "skill_def.delete"):
            self.assertIn(action, rbac.DANGEROUS_ACTIONS)


class SkillConstructorImportTest(unittest.TestCase):
    def setUp(self):
        self._skills = tempfile.NamedTemporaryFile(suffix=".json", delete=False).name
        os.environ["SKILL_CONSTRUCTOR_PATH"] = self._skills

    def tearDown(self):
        os.environ.pop("SKILL_CONSTRUCTOR_PATH", None)
        for suffix in ("", ".lock", ".tmp"):
            try:
                os.unlink(self._skills + suffix)
            except OSError:
                pass

    def test_import_published_marked_idempotent(self):
        from services import constructor_import as ci

        r1 = ci.import_skills()
        self.assertGreater(r1["created"], 0)
        items = sc.store().list()
        self.assertTrue(items)
        self.assertTrue(any(i["status"] == "published" for i in items))
        self.assertTrue(any((i.get("data") or {}).get("imported") for i in items))
        # Импортированные записи проходят валидацию (коды ветвей/путей сведены).
        for item in items:
            res = sc.validate(item)
            self.assertTrue(res["ok"], (item["id"], res["errors"]))
        r2 = ci.import_skills()
        self.assertEqual(r2["created"], 0)
        self.assertEqual(r2["skipped"], r1["created"])


if __name__ == "__main__":
    unittest.main()
