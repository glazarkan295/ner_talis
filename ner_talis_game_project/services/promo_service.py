"""Сервис промокодов Нер-Талис."""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from project_paths import resolve_project_path
from services.derived_stats_service import calculate_energy_stats
from services.inventory_service import add_inventory_item, recalculate_inventory_overflow
from services.item_registry import get_item_definition_by_id, registry_item_to_inventory_item, slugify_fallback_item_id
from services.progression_service import grant_experience

try:  # POSIX file lock for JSON fallback storage.
    import fcntl  # type: ignore
except Exception:  # pragma: no cover - Windows fallback keeps thread safety via storage locks only.
    fcntl = None  # type: ignore


def _promo_path() -> Path:
    return resolve_project_path(os.getenv("PROMO_CODES_PATH", "data/promo_codes.json"))


def _normalize_code(code: str) -> str:
    """Canonical promo key: no leading slash(es), trimmed, upper-cased.

    Admins may enter "/START100" while a player redeems "/promo start100";
    both must resolve to the same code. The canonical form has no slash.
    """
    return str(code or "").strip().lstrip("/").strip().upper()


def _parse_promo_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


@contextmanager
def _file_locked() -> Iterator[None]:
    path = _promo_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        if fcntl is not None:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _storage_supports_promo(storage: Any | None) -> bool:
    return storage is not None and hasattr(storage, "load_promo_data") and hasattr(storage, "save_promo_data")


def load_promo_data(storage: Any | None = None) -> dict[str, Any]:
    if _storage_supports_promo(storage):
        data = storage.load_promo_data()
        if isinstance(data, dict):
            data.setdefault("codes", {})
            return data
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


def save_promo_data(data: dict[str, Any], storage: Any | None = None) -> None:
    if _storage_supports_promo(storage):
        storage.save_promo_data(data)
        return
    path = _promo_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2, default=str)


def add_promo_code(*, code: str, uses_left: int, reward: dict[str, Any], expires_at: str | None = None, one_use_per_player: bool = True, note: str = "", storage: Any | None = None) -> dict[str, Any]:
    normalized_code = _normalize_code(code)
    if not normalized_code:
        raise ValueError("Код промокода пустой.")
    if not isinstance(reward, dict):
        raise ValueError("Награда промокода должна быть JSON-объектом.")
    uses = int(uses_left)
    if uses <= 0:
        raise ValueError("Количество использований должно быть больше 0.")

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
    # Single-row upsert avoids the "DELETE all + reinsert all" rewrite that could
    # drop a concurrently created code.
    if storage is not None and callable(getattr(storage, "save_promo_code", None)):
        storage.save_promo_code(normalized_code, promo)
        return promo
    with _file_locked() if storage is None else _null_context():
        data = load_promo_data(storage)
        data["codes"][normalized_code] = promo
        save_promo_data(data, storage)
        return promo


@contextmanager
def _null_context() -> Iterator[None]:
    yield


def import_promo_codes(items: list[dict[str, Any]], storage: Any | None = None) -> int:
    imported = 0
    for item in items:
        add_promo_code(
            code=str(item.get("code", "")),
            uses_left=int(item.get("uses_left", item.get("uses", 1))),
            reward=item.get("reward") or {},
            expires_at=item.get("expires_at"),
            one_use_per_player=bool(item.get("one_use_per_player", True)),
            note=str(item.get("note", "")),
            storage=storage,
        )
        imported += 1
    return imported


def deactivate_promo_code(code: str, storage: Any | None = None) -> bool:
    normalized_code = _normalize_code(code)
    if storage is not None and callable(getattr(storage, "save_promo_code", None)):
        promo = (load_promo_data(storage).get("codes") or {}).get(normalized_code)
        if not promo:
            return False
        promo["active"] = False
        promo["updated_at"] = datetime.now(timezone.utc).isoformat()
        storage.save_promo_code(normalized_code, promo)
        return True
    with _file_locked() if storage is None else _null_context():
        data = load_promo_data(storage)
        promo = data.get("codes", {}).get(normalized_code)
        if not promo:
            return False
        promo["active"] = False
        promo["updated_at"] = datetime.now(timezone.utc).isoformat()
        save_promo_data(data, storage)
        return True


def delete_promo_code(code: str, storage: Any | None = None) -> bool:
    normalized_code = _normalize_code(code)
    if storage is not None and callable(getattr(storage, "delete_promo_code", None)):
        return bool(storage.delete_promo_code(normalized_code))
    with _file_locked() if storage is None else _null_context():
        data = load_promo_data(storage)
        if normalized_code not in data.get("codes", {}):
            return False
        data["codes"].pop(normalized_code, None)
        save_promo_data(data, storage)
        return True


def list_promo_codes(limit: int = 20, storage: Any | None = None) -> list[dict[str, Any]]:
    data = load_promo_data(storage)
    promos = list(data.get("codes", {}).values())
    promos.sort(key=lambda item: str(item.get("created_at", "")), reverse=True)
    return promos[:max(1, limit)]


def _promo_reward_inventory_item(item: dict[str, Any], amount: int) -> dict[str, Any]:
    """Build a real inventory item for a promo reward.

    Admin/promo JSON usually stores only {"item_id": "...", "amount": N}.
    Without registry enrichment such rewards turn into bare technical stacks with
    no Russian name, icon, stack size, sell price or use effect.  Start from the
    canonical item registry, then let explicit promo JSON fields override it so
    special event rewards can still customize the item.
    """

    item_id = str(item.get("item_id") or item.get("id") or "").strip()
    item_name = str(item.get("name") or item.get("name_ru") or item_id or "promo_item").strip()

    explicit_source = item.get("source") is not None
    definition = get_item_definition_by_id(item_id) if item_id else None
    if definition is not None:
        prepared = registry_item_to_inventory_item(definition, amount)
    else:
        # Do not fall back from a mistyped item_id to a registry lookup by name:
        # that would attach another item's stats/effects/icons to an unknown id.
        fallback_id = item_id or slugify_fallback_item_id(item_name or "promo_item")
        prepared = {
            "id": fallback_id,
            "item_id": fallback_id,
            "name": item_name or fallback_id,
            "name_ru": item_name or fallback_id,
            "category": "Ресурсы",
            "type": "Материал",
            "quality": "обычный",
            "amount": amount,
            "max_stack": 999,
            "stackable": True,
            "source": "promo_code",
            "actions": [],
        }

    for key, value in item.items():
        if key == "amount" or value is None:
            continue
        prepared[key] = value

    if item_id:
        prepared["id"] = item_id
        prepared["item_id"] = item_id
    prepared["amount"] = amount
    if not explicit_source:
        prepared["source"] = "promo_code"
    return prepared


def apply_reward_to_player(player: dict[str, Any], reward: dict[str, Any]) -> dict[str, Any]:
    money_reward = int(reward.get("money_copper", reward.get("money", 0)) or 0)
    if money_reward:
        current_money = int(player.get("money_copper", player.get("money", 0)) or 0)
        new_money = max(0, current_money + money_reward)
        player["money_copper"] = new_money
        player["money"] = new_money

    energy_reward = int(reward.get("current_energy", reward.get("energy", 0)) or 0)
    if energy_reward:
        energy_stats = calculate_energy_stats(player)
        max_energy = int(energy_stats["max_energy"])
        current_energy = int(energy_stats["current_energy"])
        new_energy = min(max_energy, max(0, current_energy + energy_reward))
        player["current_energy"] = new_energy
        player["energy"] = new_energy

    if "free_stat_points" in reward:
        player["free_stat_points"] = int(player.get("free_stat_points", 0)) + int(reward.get("free_stat_points") or 0)
    if "free_skill_points" in reward:
        player["free_skill_points"] = int(player.get("free_skill_points", 0)) + int(reward.get("free_skill_points") or 0)

    experience_reward = int(reward.get("experience", reward.get("exp", reward.get("xp", 0))) or 0)
    if experience_reward > 0:
        grant_experience(player, experience_reward)

    for item in reward.get("items") or []:
        if isinstance(item, dict):
            amount = int(item.get("amount", 1) or 0)
            if amount <= 0:
                continue
            prepared_item = _promo_reward_inventory_item(item, amount)
            add_inventory_item(player, prepared_item, amount, default_source="promo_code")
    recalculate_inventory_overflow(player)
    return player


_CLAIM_FAILURE_MESSAGES = {
    "not_found": "Промокод не найден или отключён.",
    "inactive": "Промокод не найден или отключён.",
    "broken_expiry": "Промокод повреждён: неверный expires_at.",
    "expired": "Срок действия промокода истёк.",
    "already_used": "Этот промокод уже использован этим игроком.",
    "exhausted": "Лимит использований промокода закончился.",
}


def _redeem_with_atomic_claim(storage: Any, game_id: str, code: str) -> tuple[bool, str]:
    """Atomic redemption: storage reserves one use before the reward is granted.

    The storage-level claim (SELECT ... FOR UPDATE / BEGIN IMMEDIATE / lock)
    guarantees two concurrent redemptions cannot exceed ``uses_left`` nor grant a
    second reward to the same player. If the player update then fails, the use is
    refunded so the code is not silently consumed.
    """
    player = storage.get_player_by_game_id(game_id)
    if player is None:
        return False, "Игрок не найден."

    # Pass the canonical code so the storage claim matches the stored key
    # regardless of case or a leading slash the player/admin may have typed.
    ok, reason, reward = storage.claim_promo_use(_normalize_code(code), str(game_id))
    if not ok:
        return False, _CLAIM_FAILURE_MESSAGES.get(reason, "Промокод не найден или отключён.")

    try:
        player = apply_reward_to_player(player, reward or {})
        storage.update_player(player)
    except Exception:
        try:
            storage.refund_promo_use(_normalize_code(code), str(game_id))
        except Exception:
            pass
        raise
    return True, "Промокод успешно применён."


def redeem_promo_code(storage: Any, game_id: str, code: str) -> tuple[bool, str]:
    # Preferred path: the storage exposes an atomic claim/refund pair.
    if callable(getattr(storage, "claim_promo_use", None)) and callable(getattr(storage, "refund_promo_use", None)):
        return _redeem_with_atomic_claim(storage, game_id, code)

    # File fallback: guard read-modify-write with a file lock.
    with _file_locked() if not _storage_supports_promo(storage) else _null_context():
        data = load_promo_data(storage)
        normalized_code = _normalize_code(code)
        promo = data.get("codes", {}).get(normalized_code)
        if not promo or not promo.get("active"):
            return False, "Промокод не найден или отключён."

        expires_at = promo.get("expires_at")
        if expires_at:
            parsed_expires_at = _parse_promo_datetime(expires_at)
            if parsed_expires_at is None:
                return False, "Промокод повреждён: неверный expires_at."
            if parsed_expires_at < datetime.now(timezone.utc):
                return False, "Срок действия промокода истёк."

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
        save_promo_data(data, storage)
        return True, "Промокод успешно применён."
