"""Конструктор штрафов (ТЗ «Конструктор штрафов») — валидация типов + RBAC."""

import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services import fine_constructor_service as fc


def _val(data):
    return fc.validate({"data": data})


class FineConstructorValidateTest(unittest.TestCase):
    def test_ok_minimal(self):
        res = _val({
            "name": "Городской штраф", "type": "city", "source": "black_market_raid",
            "currency": "copper", "base_amount": 100, "first_deadline_days": 7,
            "interest_enabled": True, "interest_percent_per_day": 1,
            "restrictions": [{"code": "force_fortress"}, {"code": "block_city"}],
            "issuer_roles": ["guard", "manager", "admin"],
        })
        self.assertTrue(res["ok"], res["errors"])

    def test_requires_name(self):
        res = _val({"type": "city", "base_amount": 100})
        self.assertFalse(res["ok"])
        self.assertTrue(any("название" in e.lower() for e in res["errors"]))

    def test_unknown_enums(self):
        res = _val({"name": "X", "type": "teleport_tax", "source": "aliens", "base_amount": 10})
        self.assertFalse(res["ok"])
        joined = " ".join(res["errors"])
        self.assertIn("тип штрафа", joined)
        self.assertIn("источник", joined)

    def test_amount_and_percent_bounds(self):
        res = _val({"name": "X", "base_amount": -5, "min_amount": 100, "max_amount": 10})
        self.assertFalse(res["ok"])
        joined = " ".join(res["errors"])
        self.assertIn("Базовая сумма не может быть отрицательной", joined)
        self.assertIn("Минимальная сумма больше максимальной", joined)
        res2 = _val({"name": "X", "base_amount": 10, "interest_enabled": True, "interest_percent_per_day": 250})
        self.assertFalse(res2["ok"])
        self.assertTrue(any("Процент в день" in e for e in res2["errors"]))

    def test_bad_restriction_and_html(self):
        res = _val({"name": "X", "base_amount": 10, "restrictions": [{"code": "ban_everything"}]})
        self.assertFalse(res["ok"])
        self.assertTrue(any("ограничение" in e.lower() for e in res["errors"]))
        res2 = _val({"name": "X", "base_amount": 10, "description": "<script>hack()</script>"})
        self.assertFalse(res2["ok"])
        self.assertTrue(any("HTML" in e for e in res2["errors"]))


class FineConstructorRbacTest(unittest.TestCase):
    def test_perms_registered_and_mapped(self):
        from services import admin_rbac as rbac
        self.assertIn(rbac.PERM_FINE_DEF_PUBLISH, rbac.ALL_PERMISSIONS)
        self.assertTrue(rbac.has_permission(rbac.CONTENT, "fine_def.create"))
        self.assertTrue(rbac.has_permission(rbac.CONTENT, "fine_def.edit"))
        self.assertFalse(rbac.has_permission(rbac.CONTENT, "fine_def.publish"))
        self.assertTrue(rbac.has_permission(rbac.READ_ONLY, "fine_def.view"))
        self.assertFalse(rbac.has_permission(rbac.READ_ONLY, "fine_def.edit"))
        self.assertTrue(rbac.has_permission(rbac.ADMIN, "fine_def.publish"))
        for action in ("fine_def.publish", "fine_def.disable", "fine_def.archive", "fine_def.delete"):
            self.assertIn(action, rbac.DANGEROUS_ACTIONS)


if __name__ == "__main__":
    unittest.main()
