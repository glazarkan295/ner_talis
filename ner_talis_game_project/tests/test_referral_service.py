"""Реферальные ссылки (чат-ТЗ): код, ссылка, привязка новичка к рефереру."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services import referral_service as rs
from services import referral_constructor_service as rcs


class _FakeStorage:
    def __init__(self):
        self.players: dict[str, dict] = {}

    def add(self, player):
        self.players[player["game_id"]] = player

    def get_player_by_game_id(self, gid):
        return self.players.get(str(gid))

    def update_player(self, player):
        self.players[str(player["game_id"])] = player

    def list_player_audience_rows(self):
        return [{"game_id": gid, "level": p.get("level", 1)} for gid, p in self.players.items()]


class ReferralServiceTest(unittest.TestCase):
    def test_parse_and_code(self):
        self.assertEqual(rs.parse_referral_code("ref_NT-ABC"), "NT-ABC")
        self.assertEqual(rs.parse_referral_code("NT-ABC"), "NT-ABC")
        self.assertEqual(rs.parse_referral_code("ref_<bad>!"), "bad")  # префикс снят, мусор вычищен
        self.assertEqual(rs.parse_referral_code(""), "")
        self.assertEqual(rs.referral_code_for({"game_id": "NT-1"}), "NT-1")

    def test_telegram_link_requires_bot_username(self):
        saved = os.environ.get("TELEGRAM_BOT_USERNAME")
        try:
            os.environ.pop("TELEGRAM_BOT_USERNAME", None)
            self.assertEqual(rs.build_telegram_link({"game_id": "NT-1"}), "")
            os.environ["TELEGRAM_BOT_USERNAME"] = "@ner_talis_bot"
            self.assertEqual(rs.build_telegram_link({"game_id": "NT-1"}), "https://t.me/ner_talis_bot?start=ref_NT-1")
        finally:
            if saved is None:
                os.environ.pop("TELEGRAM_BOT_USERNAME", None)
            else:
                os.environ["TELEGRAM_BOT_USERNAME"] = saved

    def test_attach_links_new_player_and_bumps_referrer(self):
        storage = _FakeStorage()
        storage.add({"game_id": "NT-REFERRER", "referral_count": 0})
        newbie = {"game_id": "NT-NEW"}
        self.assertTrue(rs.attach_referral(storage, newbie, "ref_NT-REFERRER"))
        self.assertEqual(newbie["referred_by"], "NT-REFERRER")
        ref = storage.get_player_by_game_id("NT-REFERRER")
        self.assertEqual(ref["referral_count"], 1)
        self.assertIn("NT-NEW", ref["referrals"])

    def test_attach_rejects_self_unknown_and_double(self):
        storage = _FakeStorage()
        storage.add({"game_id": "NT-A"})
        # сам себя
        self.assertFalse(rs.attach_referral(storage, {"game_id": "NT-A"}, "NT-A"))
        # неизвестный реферер
        self.assertFalse(rs.attach_referral(storage, {"game_id": "NT-B"}, "NT-GHOST"))
        # повторная привязка
        newbie = {"game_id": "NT-C", "referred_by": "NT-A"}
        self.assertFalse(rs.attach_referral(storage, newbie, "NT-A"))

    def test_mark_then_save_failure_no_phantom_referral(self):
        # 15-CODEX §6: при сбое создания игрока реферер НЕ получает приглашённого.
        storage = _FakeStorage()
        storage.add({"game_id": "NT-R", "referral_count": 0})
        newbie = {"game_id": "NT-NEW"}
        # шаг 1: пометить (до сохранения) — реферер ещё не тронут
        self.assertEqual(rs.mark_referred_by(newbie, "ref_NT-R"), "NT-R")
        self.assertEqual(newbie["referred_by"], "NT-R")
        ref = storage.get_player_by_game_id("NT-R")
        self.assertEqual(ref.get("referral_count", 0), 0)
        self.assertNotIn("NT-NEW", ref.get("referrals") or [])
        # шаг 2 (credit) НЕ вызывается, т.к. сохранение упало → фантома нет.

    def test_credit_is_idempotent(self):
        # 15-CODEX §6: повторное подтверждение не двоит счётчик.
        storage = _FakeStorage()
        storage.add({"game_id": "NT-R", "referral_count": 0})
        newbie = {"game_id": "NT-NEW"}
        rs.mark_referred_by(newbie, "NT-R")
        self.assertTrue(rs.credit_referrer(storage, newbie))
        self.assertFalse(rs.credit_referrer(storage, newbie))  # второй раз — no-op
        ref = storage.get_player_by_game_id("NT-R")
        self.assertEqual(ref["referral_count"], 1)
        self.assertEqual(ref["referrals"].count("NT-NEW"), 1)

    def test_published_registration_rewards_are_applied_once(self):
        saved = os.environ.get("REFERRAL_CONSTRUCTOR_PATH")
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["REFERRAL_CONSTRUCTOR_PATH"] = str(Path(tmp) / "rules.json")
            try:
                rcs.store().create("welcome", {
                    "name": "Старт", "enabled": True, "platform": "telegram",
                    "trigger": "registration_complete",
                    "referrer_rewards": [{"type": "currency", "object_id": "copper", "amount": 100}],
                    "referred_rewards": [{"type": "exp", "amount": 10}],
                })
                rcs.store().set_status("welcome", rcs.STATUS_PUBLISHED, force=True)
                storage = _FakeStorage(); storage.add({"game_id": "NT-R", "money": 0})
                newbie = {"game_id": "NT-N", "main_platform": "telegram", "experience": 0, "total_experience": 0}
                rs.mark_referred_by(newbie, "NT-R")
                self.assertTrue(rs.credit_referrer(storage, newbie))
                self.assertEqual(storage.get_player_by_game_id("NT-R")["money"], 100)
                self.assertEqual(newbie["experience"], 10)
                self.assertFalse(rs.credit_referrer(storage, newbie))
                self.assertEqual(storage.get_player_by_game_id("NT-R")["money"], 100)
            finally:
                if saved is None: os.environ.pop("REFERRAL_CONSTRUCTOR_PATH", None)
                else: os.environ["REFERRAL_CONSTRUCTOR_PATH"] = saved

    def test_referral_summary_shape(self):
        s = rs.referral_summary({"game_id": "NT-9", "referral_count": 3, "referred_by": "NT-1"})
        self.assertEqual(s["code"], "NT-9")
        self.assertEqual(s["count"], 3)
        self.assertEqual(s["referredBy"], "NT-1")
        self.assertIn("vkLink", s)  # ТЗ 2.0 файл 16: обе ссылки в сводке

    def test_delayed_condition_full_rewards_history_and_manual_review(self):
        saved = os.environ.get("REFERRAL_CONSTRUCTOR_PATH")
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["REFERRAL_CONSTRUCTOR_PATH"] = str(Path(tmp) / "rules.json")
            try:
                rcs.store().create("level_campaign", {"name":"До третьего уровня","enabled":True,"platform":"telegram","link_type":"personal","trigger":"level_reached","trigger_value":3,"manual_review":True,
                    "referrer_rewards":[{"type":"skill_points","amount":2}],"referred_rewards":[{"type":"energy","amount":5}]})
                rcs.store().set_status("level_campaign",rcs.STATUS_PUBLISHED,force=True)
                storage=_FakeStorage();ref={"game_id":"NT-R"};new={"game_id":"NT-N","main_platform":"telegram","level":1,"energy":10}
                storage.add(ref);storage.add(new);rs.mark_referred_by(new,"NT-R")
                self.assertTrue(rs.credit_referrer(storage,new))  # связь сохранена, но условие ещё не выполнено
                self.assertEqual(ref.get("referral_count",0),0)
                new["level"]=3
                self.assertTrue(rs.process_referral_event(storage,new,"level_reached",3))
                stats=rs.referral_statistics(storage);self.assertEqual(stats["pending"],1)
                invite=stats["history"][0]["invite_id"]
                self.assertTrue(rs.review_invitation(storage,invite,True,"проверено"))
                self.assertEqual(ref["referral_count"],1);self.assertEqual(ref["free_skill_points"],2);self.assertEqual(new["energy"],15)
                self.assertEqual(rs.referral_statistics(storage)["credited"],1)
            finally:
                if saved is None:os.environ.pop("REFERRAL_CONSTRUCTOR_PATH",None)
                else:os.environ["REFERRAL_CONSTRUCTOR_PATH"]=saved

    def test_vk_link(self):
        # ТЗ 2.0 файл 16 §3/§6: VK-ссылка со стабильным ref-кодом.
        saved = {k: os.environ.get(k) for k in ("VK_BOT_SCREEN_NAME", "VK_GROUP_ID")}
        try:
            os.environ.pop("VK_BOT_SCREEN_NAME", None)
            os.environ.pop("VK_GROUP_ID", None)
            self.assertEqual(rs.build_vk_link({"game_id": "NT-1"}), "")
            os.environ["VK_GROUP_ID"] = "12345"
            self.assertEqual(rs.build_vk_link({"game_id": "NT-1"}), "https://vk.me/club12345?ref=ref_NT-1")
            os.environ["VK_BOT_SCREEN_NAME"] = "nertalis"
            self.assertEqual(rs.build_vk_link({"game_id": "NT-1"}), "https://vk.me/nertalis?ref=ref_NT-1")
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


if __name__ == "__main__":
    unittest.main()
