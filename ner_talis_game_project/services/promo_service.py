"""Сервис промокодов Нер-Талис."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from project_paths import resolve_project_path


def _promo_path() -> Path:
    return resolve_project_path(os.getenv("PROMO_CODES_PATH", "data/promo_codes.json"))


def _normalize_code(code: str) -> str:
    return str(code).strip().upper()


def load_promo_data() -> dict[str, Any]:
    path = _promo_path()
    if not path.exists():
        return {"codes": {}}
    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except json.JSONDecodeError:
        return {"codes": {}}
    if not isinstance(data, dict):
        return {"codes": {}}
    data.setdefault("codes", {})
    return data


def save_promo_data(data: dict[str, Any]) -> None:
    path = _promo_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2, default=str)


def add_promo_code(*, code: str, uses_left: int, reward: dict[str, Any], expires_at: str | None = None, one_use_per_player: bool = True, note: str = "") -> dict[str, Any]:
    normalized_code = _normalize_code(code)
    if not normalized_code:
        raise ValueError("Код промокода пустой.")
    if not isinstance(reward, dict):
        raise ValueError("Награда промокода должна быть JSON-объектом.")
    uses = int(uses_left)
    if uses <= 0:
        raise ValueError("Количество использований должно быть больше 0.")

    data = load_promo_data()
    promo = {
        "code": normalized_code,
        "active": True,
        "uses_left": uses,
        "reward": reward,
        "expires_at": expires_at,
        "one_use_per_player": bool(one_use_per_player),
        "used_by": [],
        "note": note,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    data["codes"][normalized_code] = promo
    save_promo_data(data)
    return promo


def import_promo_codes(items: list[dict[str, Any]]) -> int:
    imported = 0
    for item in items:
        add_promo_code(
            code=str(item.get("code", "")),
            uses_left=int(item.get("uses_left", item.get("uses", 1))),
            reward=item.get("reward") or {},
            expires_at=item.get("expires_at"),
            one_use_per_player=bool(item.get("one_use_per_player", True)),
            note=str(item.get("note", "")),
        )
        imported += 1
    return imported


def deactivate_promo_code(code: str) -> bool:
    data = load_promo_data()
    normalized_code = _normalize_code(code)
    promo = data.get("codes", {}).get(normalized_code)
    if not promo:
        return False
    promo["active"] = False
    promo["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_promo_data(data)
    return True


def list_promo_codes(limit: int = 20) -> list[dict[str, Any]]:
    data = load_promo_data()
    promos = list(data.get("codes", {}).values())
    promos.sort(key=lambda item: str(item.get("created_at", "")), reverse=True)
    return promos[:max(1, limit)]


def apply_reward_to_player(player: dict[str, Any], reward: dict[str, Any]) -> dict[str, Any]:
    if "money" in reward:
        player["money"] = int(player.get("money", 0)) + int(reward.get("money") or 0)
    if "energy" in reward:
        max_energy = int(player.get("max_energy") or 100)
        player["energy"] = min(max_energy, int(player.get("energy", max_energy)) + int(reward.get("energy") or 0))
    if "free_stat_points" in reward:
        player["free_stat_points"] = int(player.get("free_stat_points", 0)) + int(reward.get("free_stat_points") or 0)
    if "free_skill_points" in reward:
        player["free_skill_points"] = int(player.get("free_skill_points", 0)) + int(reward.get("free_skill_points") or 0)
    for item in reward.get("items") or []:
        if isinstance(item, dict):
            player.setdefault("inventory", []).append({**item, "source": "promo_code"})
    return player


def redeem_promo_code(storage: Any, game_id: str, code: str) -> tuple[bool, str]:
    data = load_promo_data()
    normalized_code = _normalize_code(code)
    promo = data.get("codes", {}).get(normalized_code)
    if not promo or not promo.get("active"):
        return False, "Промокод не найден или отключён."

    expires_at = promo.get("expires_at")
    if expires_at:
        try:
            if datetime.fromisoformat(str(expires_at)) < datetime.now(timezone.utc):
                return False, "Срок действия промокода истёк."
        except ValueError:
            return False, "Промокод повреждён: неверный expires_at."

    used_by = {str(value) for value in promo.get("used_by", [])}
    if promo.get("one_use_per_player", True) and str(game_id) in used_by:
        return False, "Этот промокод уже использован этим игроком."

    uses_left = int(promo.get("uses_left", 0))
    if uses_left <= 0:
        return False, "Лимит использований промокода закончился."

    player = storage.get_player_by_game_id(game_id)
    if player is None:
        return False, "Игрок не найден."

    player = apply_reward_to_player(player, promo.get("reward") or {})
    storage.update_player(player)

    promo.setdefault("used_by", []).append(str(game_id))
    promo["uses_left"] = uses_left - 1
    promo["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_promo_data(data)
    return True, "Промокод успешно применён."
