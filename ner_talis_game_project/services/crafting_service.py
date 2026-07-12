"""Runtime crafting and alchemy flows for Seldar workshops.

The service is intentionally button-light for Telegram/VK: lists are shown in
text, buttons use short numbered labels, and amounts/selection numbers are read
from ordinary chat messages.
"""

from __future__ import annotations

import json
import math
import random
import time
import uuid
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from project_paths import resolve_project_path
from services.derived_stats_service import safe_int
from services.inventory_service import add_inventory_item, apply_generated_item_level_and_price, inventory_add_result_notice, remove_empty_stacks_and_recalculate
from services.item_registry import build_inventory_item, get_item_definition_by_id, get_item_definition_by_name, registry_item_to_inventory_item
from services.race_bonus_service import alchemy_ingredient_refund, crafting_extra_effect_triggered

CHECK_TIMER = "Проверить таймер"
QUEUE_ONE = "В очередь ещё 1"
PROFILE_BUTTON = "Профиль"
BACK = "Назад"
CANCEL = "Отмена"
RETURN_TO_CHOICE = "Вернуться к выбору"
CREATE = "Создать"
CRAFT_DISTRICT = "Ремесленный квартал"
CRAFT_PREFIX = "Крафт №"

SMELTERY = "Плавильня"
FORGE = "Кузница"
LEATHERWORK = "Кожевенная мастерская"
JEWELRY = "Ювелирная мастерская"
BIJOUTERIE = "Бижутерия"
GEM_INSERT = "вставка камней"
RINGS_SECTION = "Кольца"
IRON_RINGS = "Железные кольца"
SILVER_RINGS = "Серебряные кольца"
RING_SUBSECTIONS = (IRON_RINGS, SILVER_RINGS)
ALCHEMY = "Алхимическая мастерская"
ENCHANTER = "Мастерская чародея"
BACK_TO_CENTRAL = "⬅️ Центральная площадь"
CENTRAL_SQUARE = "Центральная площадь"
MAINTENANCE_TEXT = "Мастерская временно закрыта на техническое обслуживание."

ALCHEMY_BY_RECIPE = "Создать по рецепту"
ALCHEMY_EXPERIMENT = "Эксперимент"
ALCHEMY_JOURNAL = "Журнал рецептов"
YES = "Да"
NO = "Нет"
CONFIRM_EXPERIMENT = "Провести опыт"
CHANGE_COMPOSITION = "Изменить состав"
CHANGE_ACTIONS = "Изменить действия"

CRAFTING_RECIPES_PATH = "data/crafting_recipes.json"
ALCHEMY_RUNTIME_PATH = "data/alchemy_system_runtime.json"
CRAFT_SECONDS_DEFAULT = 60


@dataclass(frozen=True)
class CraftResponse:
    text: str
    buttons: list[list[str]]
    zone_id: str
    scheduled_timer: dict[str, Any] | None = None


WORKSHOPS: dict[str, dict[str, Any]] = {
    SMELTERY: {
        "id": "smeltery",
        "zone": "seldar_smeltery",
        "title": "🔥 Плавильня",
        "skill": "smelting",
        "sections": None,
        "intro": "Здесь руду и лом превращают в слитки и сплавы.",
    },
    FORGE: {
        "id": "forge",
        "zone": "seldar_forge",
        "title": "🛠 Кузница",
        "skill": "blacksmithing",
        "sections": ["Оружие", "Броня", "Заготовки", "Рецепты"],
        "intro": "Здесь создают оружие и кузнечные заготовки.",
    },
    LEATHERWORK: {
        "id": "leatherwork",
        "zone": "seldar_leatherwork",
        "title": "🧵 Кожевенная мастерская",
        "skill": "leatherworking",
        "sections": ["Броня", "Заготовки", "Рецепты"],
        "intro": "Здесь шкуры, кожа и сухожилия превращаются в лёгкую броню и заготовки.",
    },
    JEWELRY: {
        "id": "jewelry",
        "zone": "seldar_jewelry_workshop",
        "title": "💎 Ювелирная мастерская",
        "skill": "jewelcrafting",
        "sections": ["Кольца", "Ожерелья", "Рецепты"],
        "intro": "Здесь создают простую бижутерию, рецепты и заготовки для будущих камней.",
    },
    ALCHEMY: {
        "id": "alchemy",
        "zone": "seldar_alchemy_workshop",
        "title": "⚗️ Алхимическая мастерская",
        "skill": "alchemy",
        "sections": None,
        "intro": "Здесь создают зелья, эликсиры, яды, реагенты и нестабильные смеси.",
    },
}
WORKSHOP_BY_ID = {data["id"]: data for data in WORKSHOPS.values()}
WORKSHOP_ACTION_BY_ID = {data["id"]: action for action, data in WORKSHOPS.items()}
SECTION_LABELS = {section for data in WORKSHOPS.values() for section in (data.get("sections") or [])}
# «Кольца» в ювелирной мастерской — не раздел рецептов, а под-меню с кнопками
# «Железные кольца» / «Серебряные кольца»; эти под-разделы маркируют рецепты колец.
SECTION_LABELS |= set(RING_SUBSECTIONS)

CRAFT_ACTIONS = frozenset(
    set(WORKSHOPS.keys())
    | {ENCHANTER, BACK_TO_CENTRAL, CENTRAL_SQUARE, BIJOUTERIE, GEM_INSERT}
    | SECTION_LABELS
    | {
        BACK,
        CANCEL,
        RETURN_TO_CHOICE,
        CREATE,
        CHECK_TIMER,
        QUEUE_ONE,
        CRAFT_DISTRICT,
        ALCHEMY_BY_RECIPE,
        ALCHEMY_EXPERIMENT,
        ALCHEMY_JOURNAL,
        YES,
        NO,
        CONFIRM_EXPERIMENT,
        CHANGE_COMPOSITION,
        CHANGE_ACTIONS,
    }
    | {f"{CRAFT_PREFIX}{index}" for index in range(1, 51)}
)

CRAFTING_ZONE_PREFIXES = (
    "seldar_smeltery",
    "seldar_forge",
    "seldar_leatherwork",
    "seldar_jewelry_workshop",
    "seldar_alchemy_workshop",
)


def current_crafting_zone(player: dict[str, Any]) -> str:
    return str(player.get("current_zone") or player.get("location_id") or "")


def is_crafting_zone(player: dict[str, Any]) -> bool:
    return current_crafting_zone(player).startswith(CRAFTING_ZONE_PREFIXES)


def clear_stale_crafting_context_if_needed(player: dict[str, Any]) -> bool:
    """Drop leftover crafting context when the player is no longer in a workshop.

    Numeric recipe/amount input is valid only inside the matching workshop. An
    active craft timer is different: it intentionally locks all actions until
    completion and must never be cleared by this stale-context guard.
    """
    active_timer = player.get("active_timer")
    if isinstance(active_timer, dict) and active_timer.get("type") == "craft":
        return False
    if isinstance(player.get("crafting_context"), dict) and not is_crafting_zone(player):
        player.pop("crafting_context", None)
        return True
    return False


ACTION_NAMES = {
    "grind": "Измельчить",
    "cut": "Нарезать",
    "dry": "Высушить",
    "soak": "Замочить",
    "heat": "Нагреть",
    "boil": "Кипятить",
    "distill": "Перегнать",
    "mix": "Смешать",
    "infuse": "Настаивать",
    "magic_treat": "Обработать магией",
    "cool": "Охладить",
    "stabilize": "Стабилизировать",
    "crystallize": "Кристаллизовать",
}

ROLE_TITLES = {
    "base": "основу",
    "active": "активный ингредиент",
    "catalyst": "катализатор",
    "stabilizer": "стабилизатор",
}

ROLE_DRAFT_KEYS = {
    "base": "base",
    "active": "active_ingredients",
    "catalyst": "catalysts",
    "stabilizer": "stabilizers",
}

STAGE_SUCCESS_LEVELS = {"Простая алхимия": 1, "Сложная алхимия": 25, "Высшая алхимия": 60, "Великая алхимия": 120}
STAGE_GUARANTEED_LEVELS = {"Простая алхимия": 60, "Сложная алхимия": 120}
STAGE_POWER_BONUS = {"Простая алхимия": 1.0, "Сложная алхимия": 1.2, "Высшая алхимия": 1.5, "Великая алхимия": 2.0}
STAGE_COMPLEXITY_BASE = {"Простая алхимия": 10, "Сложная алхимия": 25, "Высшая алхимия": 45, "Великая алхимия": 75}
STAGE_RISK_PENALTY = {"Простая алхимия": 0, "Сложная алхимия": 4, "Высшая алхимия": 8, "Великая алхимия": 15}


@lru_cache(maxsize=4)
def load_crafting_recipes() -> list[dict[str, Any]]:
    path = resolve_project_path(CRAFTING_RECIPES_PATH)
    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    if not isinstance(payload, list):
        return []
    static = [recipe for recipe in payload if isinstance(recipe, dict)]
    try:
        from services.recipe_constructor_service import published_runtime_recipes
        live = published_runtime_recipes()
    except Exception:
        live = []
    by_id = {str(recipe.get("id") or ""): recipe for recipe in static if recipe.get("id")}
    for recipe in live:
        if recipe.get("id"):
            by_id[str(recipe["id"])] = recipe
    return list(by_id.values())


def invalidate_crafting_recipe_cache() -> None:
    load_crafting_recipes.cache_clear()
    recipe_by_id.cache_clear()


@lru_cache(maxsize=4)
def recipe_by_id() -> dict[str, dict[str, Any]]:
    return {str(recipe.get("id")): recipe for recipe in load_crafting_recipes() if recipe.get("id")}


@lru_cache(maxsize=4)
def load_alchemy_runtime() -> dict[str, Any]:
    path = resolve_project_path(ALCHEMY_RUNTIME_PATH)
    try:
        with path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
    except (OSError, json.JSONDecodeError):
        payload = {}
    return payload if isinstance(payload, dict) else {}


def now_ts() -> float:
    return time.time()


def new_timer_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def format_duration(seconds: int | float) -> str:
    seconds = max(0, int(math.ceil(float(seconds or 0))))
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    parts: list[str] = []
    if hours:
        parts.append(f"{hours} ч")
    if minutes:
        parts.append(f"{minutes} мин")
    if sec or not parts:
        parts.append(f"{sec} сек")
    return " ".join(parts)


def timer_remaining_seconds(timer: dict[str, Any] | None) -> int:
    if not isinstance(timer, dict):
        return 0
    return max(0, math.ceil(float(timer.get("ends_at") or 0) - now_ts()))


def build_timer_schedule(player: dict[str, Any], timer: dict[str, Any]) -> dict[str, Any]:
    return {
        "timer_id": timer.get("id"),
        "game_id": player.get("game_id") or player.get("id"),
        "seconds": int(timer.get("seconds") or timer_remaining_seconds(timer)),
        "type": timer.get("type"),
    }


def _item_name(item_id: str | None, fallback: str | None = None) -> str:
    definition = get_item_definition_by_id(str(item_id or "")) if item_id else None
    if definition:
        return str(definition.get("name_ru") or definition.get("name") or item_id)
    return str(fallback or item_id or "Предмет")



def _ingredient_item_type_matches(item: dict[str, Any], item_type: str | None) -> bool:
    """Return True when an inventory stack can satisfy a type-based recipe slot."""

    wanted = str(item_type or "").strip().casefold()
    if not wanted:
        return False
    values = {
        str(item.get("subtype") or "").casefold(),
        str(item.get("type") or "").casefold(),
        str(item.get("item_class") or "").casefold(),
        str(item.get("category") or "").casefold(),
    }
    if wanted in values:
        return True
    if wanted in {"tendon", "sinew", "сухожилие", "сухожилия"} and values & {"tendon", "sinew", "сухожилие", "сухожилия"}:
        return True
    if wanted in {"hide", "pelt", "шкура", "шкурка"} and values & {"hide", "pelt", "шкура", "шкурка"}:
        return True
    return False


def _ingredient_matches_item(item: dict[str, Any], ingredient: dict[str, Any]) -> bool:
    if item.get("quest_item") or item.get("locked") or item.get("protected"):
        return False
    group_id = str(ingredient.get("material_group_id") or "").strip()
    if group_id:
        try:
            from services.craft_material_group_service import matches
            return matches(item, group_id)
        except Exception:
            return False
    match_type = str(ingredient.get("match_type") or "").casefold()
    if match_type == "any_item_type":
        return _ingredient_item_type_matches(item, str(ingredient.get("item_type") or ""))
    item_id = ingredient.get("item_id")
    name = ingredient.get("name") or _item_name(item_id)
    if item_id and str(item.get("item_id") or item.get("id") or "") == str(item_id):
        return True
    if name and str(item.get("name") or item.get("name_ru") or "").casefold() == str(name).casefold():
        return True
    return False


def _ingredient_available_count(player: dict[str, Any], ingredient: dict[str, Any]) -> int:
    total = 0
    for item in player.get("inventory", []):
        if isinstance(item, dict) and _ingredient_matches_item(item, ingredient):
            total += safe_int(item.get("amount"), 1)
    return total


def _ingredient_variants(ingredient: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the primary ingredient plus explicitly configured alternatives."""
    variants = [ingredient]
    for raw in ingredient.get("alternatives") or []:
        if isinstance(raw, str):
            variants.append({**ingredient, "item_id": raw, "alternatives": []})
        elif isinstance(raw, dict):
            variants.append({**ingredient, **raw, "alternatives": []})
    return variants


def _selected_ingredient(player: dict[str, Any], ingredient: dict[str, Any], amount: int) -> dict[str, Any] | None:
    return next((row for row in _ingredient_variants(ingredient) if _ingredient_available_count(player, row) >= amount), None)


def _consume_ingredient(player: dict[str, Any], ingredient: dict[str, Any], amount: int) -> bool:
    amount = max(0, safe_int(amount, 0))
    if amount <= 0:
        return True
    if _ingredient_available_count(player, ingredient) < amount:
        return False
    remaining = amount
    inventory = player.setdefault("inventory", [])
    for item in list(inventory):
        if not isinstance(item, dict) or not _ingredient_matches_item(item, ingredient):
            continue
        current = safe_int(item.get("amount"), 1)
        taken = min(current, remaining)
        item["amount"] = current - taken
        remaining -= taken
        if item["amount"] <= 0:
            inventory.remove(item)
        if remaining <= 0:
            remove_empty_stacks_and_recalculate(player)
            return True
    remove_empty_stacks_and_recalculate(player)
    return remaining <= 0

def _inventory_count(player: dict[str, Any], *, item_id: str | None = None, name: str | None = None) -> int:
    total = 0
    for item in player.get("inventory", []):
        if not isinstance(item, dict):
            continue
        if item.get("quest_item") or item.get("locked") or item.get("protected"):
            continue
        item_amount = safe_int(item.get("amount"), 1)
        if item_id and str(item.get("item_id") or item.get("id") or "") == item_id:
            total += item_amount
        elif name and str(item.get("name") or item.get("name_ru") or "").casefold() == name.casefold():
            total += item_amount
    return total


def _consume_inventory(player: dict[str, Any], *, item_id: str | None = None, name: str | None = None, amount: int = 1) -> bool:
    amount = max(0, safe_int(amount, 0))
    if amount <= 0:
        return True
    if _inventory_count(player, item_id=item_id, name=name) < amount:
        return False
    remaining = amount
    inventory = player.setdefault("inventory", [])
    for item in list(inventory):
        if not isinstance(item, dict):
            continue
        if item.get("quest_item") or item.get("locked") or item.get("protected"):
            continue
        matches = False
        if item_id and str(item.get("item_id") or item.get("id") or "") == item_id:
            matches = True
        elif name and str(item.get("name") or item.get("name_ru") or "").casefold() == name.casefold():
            matches = True
        if not matches:
            continue
        current = safe_int(item.get("amount"), 1)
        taken = min(current, remaining)
        item["amount"] = current - taken
        remaining -= taken
        if item["amount"] <= 0:
            inventory.remove(item)
        if remaining <= 0:
            remove_empty_stacks_and_recalculate(player)
            return True
    remove_empty_stacks_and_recalculate(player)
    return True


def _recipe_output_name(recipe: dict[str, Any]) -> str:
    output = recipe.get("output") or {}
    return _item_name(output.get("item_id"), output.get("name"))


def _recipe_formula_context(recipe: dict[str, Any], *, player: dict[str, Any] | None = None, quantity: int = 1) -> dict[str, float]:
    from services.formula_runtime import numeric_context
    return numeric_context({
        "recipe_level": recipe.get("level", recipe.get("required_level", 1)),
        "profession_level": _craft_skill_level(player or {}, str(recipe.get("workshop") or "")),
        "difficulty": recipe.get("difficulty", 0), "item_count": quantity,
        "base_amount": (recipe.get("output") or {}).get("amount", 1),
    }, player=player)


def _recipe_output_amount(recipe: dict[str, Any], *, player: dict[str, Any] | None = None) -> int:
    output = recipe.get("output") or {}
    from services.formula_runtime import evaluate
    calculated = evaluate(recipe.get("result_formula_id"), _recipe_formula_context(recipe, player=player), default=None)
    if calculated is not None:
        return max(1, safe_int(calculated, 1))
    if output.get("amount_min") is not None or output.get("amount_max") is not None:
        return max(1, safe_int(output.get("amount_min") or output.get("amount_max"), 1))
    return max(1, safe_int(output.get("amount"), 1))


def _recipe_output_amount_max(recipe: dict[str, Any]) -> int:
    output = recipe.get("output") or {}
    if output.get("amount_min") is not None or output.get("amount_max") is not None:
        return max(_recipe_output_amount(recipe), safe_int(output.get("amount_max") or output.get("amount_min"), _recipe_output_amount(recipe)))
    return _recipe_output_amount(recipe)


def _recipe_output_amount_label(recipe: dict[str, Any]) -> str:
    minimum = _recipe_output_amount(recipe)
    maximum = _recipe_output_amount_max(recipe)
    return str(minimum) if minimum == maximum else f"{minimum}–{maximum}"


def _roll_recipe_output_amount(recipe: dict[str, Any], *, player: dict[str, Any] | None = None) -> int:
    minimum = _recipe_output_amount(recipe, player=player)
    if recipe.get("result_formula_id"):
        return minimum
    maximum = _recipe_output_amount_max(recipe)
    if maximum > minimum:
        return random.randint(minimum, maximum)
    return minimum


def _recipes_for(workshop_id: str, section: str | None = None, constructor_workshop_id: str | None = None) -> list[dict[str, Any]]:
    result = [recipe for recipe in load_crafting_recipes() if recipe.get("workshop") == workshop_id]
    if constructor_workshop_id:
        result = [recipe for recipe in result if str(recipe.get("workshop_id") or "") == str(constructor_workshop_id)]
    if section is not None:
        result = [recipe for recipe in result if str(recipe.get("section") or "") == section]
    elif workshop_id != "smeltery":
        result = [recipe for recipe in result if str(recipe.get("section") or "") in {"", "default"}]
    return result


def _has_ingredients(player: dict[str, Any], recipe: dict[str, Any], quantity: int = 1) -> bool:
    for ingredient in recipe.get("ingredients") or []:
        if not isinstance(ingredient, dict):
            continue
        amount = max(1, safe_int(ingredient.get("amount"), 1)) * max(1, quantity)
        if ingredient.get("optional"):
            continue
        if _selected_ingredient(player, ingredient, amount) is None:
            return False
    for tool in recipe.get("tools") or []:
        if not isinstance(tool, dict) or tool.get("required", True) is False:
            continue
        variants = {**tool, "alternatives": tool.get("alternatives") or ([tool.get("alternative_item_id")] if tool.get("alternative_item_id") else [])}
        selected = _selected_ingredient(player, variants, 1)
        if selected is None:
            return False
        minimum = safe_int(tool.get("min_durability"), 0)
        if minimum:
            matching = [row for row in player.get("inventory", []) if isinstance(row, dict) and _ingredient_matches_item(row, selected)]
            if not any(safe_int(row.get("durability"), safe_int(row.get("max_durability"), 0)) >= minimum for row in matching):
                return False
    return True


def _has_material_ingredients(player: dict[str, Any], recipe: dict[str, Any], quantity: int = 1) -> bool:
    bare = {**recipe, "tools": []}
    return _has_ingredients(player, bare, quantity)


def _has_tools(player: dict[str, Any], recipe: dict[str, Any]) -> bool:
    bare = {"ingredients": [], "tools": recipe.get("tools") or []}
    return _has_ingredients(player, bare, 1)


def _max_craft_count(player: dict[str, Any], recipe: dict[str, Any]) -> int:
    counts: list[int] = []
    for ingredient in recipe.get("ingredients") or []:
        if not isinstance(ingredient, dict):
            continue
        amount = max(1, safe_int(ingredient.get("amount"), 1))
        if ingredient.get("optional"):
            continue
        counts.append(max((_ingredient_available_count(player, row) // amount for row in _ingredient_variants(ingredient)), default=0))
    return min(counts) if counts else 0


def _consume_recipe_ingredients(player: dict[str, Any], recipe: dict[str, Any], quantity: int) -> bool:
    if not _has_ingredients(player, recipe, quantity):
        return False
    for ingredient in recipe.get("ingredients") or []:
        if not isinstance(ingredient, dict):
            continue
        if ingredient.get("optional") or ingredient.get("consumed", True) is False:
            continue
        amount = max(1, safe_int(ingredient.get("amount"), 1)) * max(1, quantity)
        selected = _selected_ingredient(player, ingredient, amount)
        if selected is None or not _consume_ingredient(player, selected, amount):
            return False
    for tool in recipe.get("tools") or []:
        if not isinstance(tool, dict):
            continue
        selected = _selected_ingredient(player, tool, 1)
        if selected is None:
            continue
        if tool.get("consumed"):
            _consume_ingredient(player, selected, max(1, safe_int(tool.get("amount"), 1)))
        loss = max(0, safe_int(tool.get("durability_loss"), 0))
        if recipe.get("tool_durability_formula_id"):
            from services.formula_runtime import evaluate
            loss = max(0, safe_int(evaluate(recipe.get("tool_durability_formula_id"), _recipe_formula_context(recipe, player=player, quantity=quantity) | {"base_amount": loss}, default=loss), loss))
        if loss:
            for row in player.get("inventory", []):
                if isinstance(row, dict) and _ingredient_matches_item(row, selected):
                    row["durability"] = max(0, safe_int(row.get("durability"), safe_int(row.get("max_durability"), 0)) - loss)
                    break
    return True


def _ingredient_line(player: dict[str, Any], ingredient: dict[str, Any], quantity: int = 1) -> str:
    item_id = ingredient.get("item_id")
    name = ingredient.get("name") or _item_name(item_id)
    amount = max(1, safe_int(ingredient.get("amount"), 1)) * max(1, quantity)
    role = str(ingredient.get("role") or "Ингредиент")
    available = _ingredient_available_count(player, ingredient)
    return f"{role}: {name} ×{amount} (есть: {available})"


def _craft_skill_level(player: dict[str, Any], workshop_id: str) -> int:
    skill_key = WORKSHOP_BY_ID.get(workshop_id, {}).get("skill")
    data = (player.get("crafting_levels") or {}).get(skill_key or "", {})
    return max(1, safe_int(data.get("level"), 1)) if isinstance(data, dict) else 1


def _add_craft_experience(player: dict[str, Any], workshop_id: str, amount: int) -> None:
    skill_key = WORKSHOP_BY_ID.get(workshop_id, {}).get("skill")
    if not skill_key:
        return
    crafting_levels = player.setdefault("crafting_levels", {})
    skill = crafting_levels.setdefault(skill_key, {"level": 1, "experience": 0})
    if not isinstance(skill, dict):
        crafting_levels[skill_key] = {"level": 1, "experience": 0}
        skill = crafting_levels[skill_key]
    gained = max(1, amount) * 5
    profession = None
    try:
        from services import profession_constructor_service as professions
        aliases = {"blacksmithing": "smithing", "jewelcrafting": "jewelry"}
        wanted = aliases.get(skill_key or "", skill_key or "")
        profession = next((row.get("data") or {} for row in professions.store().list(status=professions.STATUS_PUBLISHED)
                           if str((row.get("data") or {}).get("profession_type") or row.get("id") or "") in {wanted, skill_key}), None)
        if profession:
            from services.formula_runtime import evaluate
            gained = max(0, safe_int(evaluate(profession.get("exp_formula_id"), {
                "profession_level": safe_int(skill.get("level"), 1), "base_amount": gained,
                "item_count": max(1, amount),
            }, default=gained), gained))
    except Exception:
        profession = None
    skill["experience"] = safe_int(skill.get("experience"), 0) + gained
    if profession:
        from services.formula_runtime import evaluate
        max_level = max(1, safe_int(profession.get("max_level"), 100))
        while safe_int(skill.get("level"), 1) < max_level:
            level = max(1, safe_int(skill.get("level"), 1))
            fallback = level * 100
            required = max(1, safe_int(evaluate(profession.get("next_level_formula_id"), {
                "profession_level": level, "player_level": safe_int(player.get("level"), 1),
                "base_amount": fallback,
            }, default=fallback), fallback))
            if safe_int(skill.get("experience"), 0) < required:
                break
            skill["experience"] = safe_int(skill.get("experience"), 0) - required
            skill["level"] = level + 1


def _set_city_zone(player: dict[str, Any], zone_id: str) -> None:
    player["current_city"] = "seldar"
    player["current_zone"] = zone_id
    player["location_id"] = zone_id
    player.pop("market_context", None)


def _craft_district_buttons() -> list[list[str]]:
    return [[SMELTERY, FORGE], [LEATHERWORK, JEWELRY], [ALCHEMY, ENCHANTER], [BACK_TO_CENTRAL]]


def _section_buttons(workshop_id: str) -> list[list[str]]:
    data = WORKSHOP_BY_ID[workshop_id]
    sections = list(data.get("sections") or [])
    rows = [[sections[index], sections[index + 1]] for index in range(0, len(sections) - 1, 2)]
    if len(sections) % 2:
        rows.append([sections[-1]])
    rows.append([CRAFT_DISTRICT])
    return rows


def _workshop_home_button(workshop_id: str) -> str:
    return WORKSHOP_ACTION_BY_ID.get(workshop_id, CRAFT_DISTRICT)


def _recipe_navigation_buttons(workshop_id: str, *, source: str = "list", section: str | None = None) -> list[list[str]]:
    if workshop_id == "jewelry" and section in RING_SUBSECTIONS:
        # Back from a metal-specific ring list returns to the «Кольца» sub-menu.
        return [[RINGS_SECTION], [JEWELRY]]
    if workshop_id == "alchemy":
        if source == "preview":
            return [[ALCHEMY_BY_RECIPE], [ALCHEMY]]
        if source == "quantity":
            return [[ALCHEMY_BY_RECIPE], [ALCHEMY]]
        return [[ALCHEMY]]
    if workshop_id == "smeltery":
        if source == "list":
            return [[CRAFT_DISTRICT]]
        return [[SMELTERY], [CRAFT_DISTRICT]]
    return [[_workshop_home_button(workshop_id)], [CRAFT_DISTRICT]]


def _recipe_buttons(recipes: list[dict[str, Any]], workshop_id: str, section: str | None = None) -> list[list[str]]:
    rows: list[list[str]] = []
    for index in range(0, len(recipes), 2):
        row = [f"{CRAFT_PREFIX}{index + 1}"]
        if index + 2 <= len(recipes):
            row.append(f"{CRAFT_PREFIX}{index + 2}")
        rows.append(row)
    rows.extend(_recipe_navigation_buttons(workshop_id, source="list", section=section))
    return rows


def _active_context(player: dict[str, Any]) -> dict[str, Any]:
    context = player.setdefault("crafting_context", {})
    if not isinstance(context, dict):
        context = {}
        player["crafting_context"] = context
    return context


def _clear_context(player: dict[str, Any]) -> None:
    player.pop("crafting_context", None)


def _maintenance_response(storage: Any, player: dict[str, Any], title: str, text: str | None = None) -> CraftResponse:
    _clear_context(player)
    _set_city_zone(player, "seldar_craft_district")
    storage.update_player(player)
    message = f"{title}\n\n{text or MAINTENANCE_TEXT}"
    return CraftResponse(message, _craft_district_buttons(), "seldar_craft_district")


def _jewelry_home_buttons() -> list[list[str]]:
    return [[BIJOUTERIE, GEM_INSERT], [CRAFT_DISTRICT]]


def _jewelry_section_buttons() -> list[list[str]]:
    sections = list(WORKSHOP_BY_ID["jewelry"].get("sections") or [])
    rows = [[sections[index], sections[index + 1]] for index in range(0, len(sections) - 1, 2)]
    if len(sections) % 2:
        rows.append([sections[-1]])
    rows.append([JEWELRY])
    return rows


def _jewelry_home_response(storage: Any, player: dict[str, Any]) -> CraftResponse:
    data = WORKSHOP_BY_ID["jewelry"]
    _set_city_zone(player, data["zone"])
    context = _active_context(player)
    context.clear()
    context.update({"workshop": "jewelry", "step": "jewelry_home"})
    storage.update_player(player)
    text = f"{data['title']}\n\n{data['intro']}\n\nВыберите отдел:"
    return CraftResponse(text, _jewelry_home_buttons(), data["zone"])


def _jewelry_bijouterie_response(storage: Any, player: dict[str, Any]) -> CraftResponse:
    data = WORKSHOP_BY_ID["jewelry"]
    _set_city_zone(player, data["zone"])
    context = _active_context(player)
    context.clear()
    context.update({"workshop": "jewelry", "step": "sections"})
    storage.update_player(player)
    text = "💍 Бижутерия\n\nВыберите раздел создания:"
    return CraftResponse(text, _jewelry_section_buttons(), data["zone"])


def _jewelry_rings_menu_buttons() -> list[list[str]]:
    return [[IRON_RINGS, SILVER_RINGS], [BIJOUTERIE]]


def _jewelry_rings_menu_response(storage: Any, player: dict[str, Any]) -> CraftResponse:
    data = WORKSHOP_BY_ID["jewelry"]
    _set_city_zone(player, data["zone"])
    context = _active_context(player)
    context.clear()
    context.update({"workshop": "jewelry", "step": "ring_sections"})
    storage.update_player(player)
    text = "💍 Кольца\n\nВыберите тип колец:"
    return CraftResponse(text, _jewelry_rings_menu_buttons(), data["zone"])


def _jewelry_gem_insert_response(storage: Any, player: dict[str, Any]) -> CraftResponse:
    data = WORKSHOP_BY_ID["jewelry"]
    _set_city_zone(player, data["zone"])
    context = _active_context(player)
    context.clear()
    context.update({"workshop": "jewelry", "step": "jewelry_home"})
    storage.update_player(player)
    text = "💎 Вставка камней\n\nДанный отдел временно закрыт на технические работы."
    return CraftResponse(text, _jewelry_home_buttons(), data["zone"])


def _show_workshop_menu(storage: Any, player: dict[str, Any], workshop_id: str) -> CraftResponse:
    if workshop_id == "jewelry":
        return _jewelry_home_response(storage, player)
    data = WORKSHOP_BY_ID[workshop_id]
    _set_city_zone(player, data["zone"])
    if workshop_id == "alchemy":
        context = _active_context(player)
        context.clear()
        context.update({"workshop": "alchemy", "step": "alchemy_menu"})
        storage.update_player(player)
        return _alchemy_menu_response(player)
    sections = data.get("sections")
    context = _active_context(player)
    context.clear()
    if sections:
        context.update({"workshop": workshop_id, "step": "sections"})
        storage.update_player(player)
        text = f"{data['title']}\n\n{data['intro']}\n\nВыберите раздел создания:"
        return CraftResponse(text, _section_buttons(workshop_id), data["zone"])
    context.update({"workshop": workshop_id, "section": "default", "step": "list"})
    storage.update_player(player)
    return _show_recipe_list(storage, player, workshop_id, "default")


def _show_constructor_workshop(storage: Any, player: dict[str, Any], workshop: dict[str, Any]) -> CraftResponse:
    from services.workshop_constructor_service import player_has_access
    ok, message = player_has_access(player, workshop)
    runtime_type = str(workshop.get("runtime_workshop") or workshop.get("type") or "forge")
    if runtime_type not in WORKSHOP_BY_ID:
        return CraftResponse(str(workshop.get("unavailable_text") or "Для этого типа мастерской ещё не назначен совместимый игровой процесс."), [], str(player.get("current_zone") or ""))
    if not ok:
        return CraftResponse(message, [], str(player.get("current_zone") or ""))
    context = _active_context(player)
    context.clear()
    context.update({"workshop": runtime_type, "constructor_workshop_id": str(workshop.get("id") or ""), "step": "list", "section": "default"})
    storage.update_player(player)
    return _show_recipe_list(storage, player, runtime_type, "default")


def _show_recipe_list(storage: Any, player: dict[str, Any], workshop_id: str, section: str | None) -> CraftResponse:
    data = WORKSHOP_BY_ID[workshop_id]
    constructor_workshop_id = str((_active_context(player)).get("constructor_workshop_id") or "") or None
    recipes = _recipes_for(workshop_id, None if section in {None, "default"} else section, constructor_workshop_id)
    if workshop_id == "smeltery":
        recipes = _recipes_for(workshop_id, "default", constructor_workshop_id)
    if workshop_id == "alchemy":
        unlocked = {str(recipe_id) for recipe_id in player.get("unlocked_alchemy_recipes", []) if recipe_id}
        recipes = [recipe for recipe in recipes if str(recipe.get("id") or "") in unlocked]
    unlocked_recipes = {str(recipe_id) for recipe_id in player.get("unlocked_recipes") or []}
    recipes = [recipe for recipe in recipes if not recipe.get("hidden") or str(recipe.get("id") or "") in unlocked_recipes]
    context = _active_context(player)
    context.update({"workshop": workshop_id, "section": section or "default", "step": "list", "recipe_ids": [recipe["id"] for recipe in recipes]})
    _set_city_zone(player, data["zone"])
    storage.update_player(player)
    lines = [data["title"], "", "Что можно создать:"]
    if section and section != "default":
        lines.append(f"Раздел: {section}")
    lines.append("")
    if not recipes:
        if workshop_id == "alchemy":
            lines.append("Открытых алхимических рецептов пока нет. Рецепты можно купить, найти или открыть удачным экспериментом.")
        else:
            lines.append("В этом разделе пока нет доступных рецептов.")
        return CraftResponse("\n".join(lines), _recipe_navigation_buttons(workshop_id, source="list", section=section), data["zone"])
    for index, recipe in enumerate(recipes, 1):
        mark = "✅" if _has_ingredients(player, recipe) else "❌"
        out_amount_label = _recipe_output_amount_label(recipe)
        out_suffix = f" ×{out_amount_label}" if out_amount_label != "1" else ""
        lines.append(f"{index}. {mark} {_recipe_output_name(recipe)}{out_suffix}")
    lines.append("\nНажмите короткую кнопку вида «Крафт №1», чтобы посмотреть рецепт и ингредиенты.")
    return CraftResponse("\n".join(lines), _recipe_buttons(recipes, workshop_id, section), data["zone"])


def _selected_recipe_from_context(player: dict[str, Any], action: str) -> dict[str, Any] | None:
    context = _active_context(player)
    try:
        number = int(action.removeprefix(CRAFT_PREFIX).strip())
    except ValueError:
        return None
    recipe_ids = context.get("recipe_ids") or []
    if not isinstance(recipe_ids, list) or number < 1 or number > len(recipe_ids):
        return None
    return recipe_by_id().get(str(recipe_ids[number - 1]))


def _preview_recipe(storage: Any, player: dict[str, Any], recipe: dict[str, Any]) -> CraftResponse:
    context = _active_context(player)
    workshop_id = str(recipe.get("workshop") or context.get("workshop") or "smeltery")
    data = WORKSHOP_BY_ID.get(workshop_id, WORKSHOP_BY_ID["smeltery"])
    context.update({"workshop": workshop_id, "section": recipe.get("section") or context.get("section") or "default", "step": "preview", "selected_recipe_id": recipe.get("id")})
    _set_city_zone(player, data["zone"])
    storage.update_player(player)
    out_amount_label = _recipe_output_amount_label(recipe)
    unit_seconds = _recipe_craft_seconds(recipe)
    lines = [
        f"{data['title']} · рецепт",
        "",
        f"Предмет: {_recipe_output_name(recipe)} ×{out_amount_label}",
        f"Время создания за 1 предмет: {format_duration(unit_seconds)}",
        "При создании нескольких предметов время увеличивается пропорционально количеству.",
        "",
        str(recipe.get("text_recipe_card") or recipe.get("description") or "Краткое описание пока не добавлено."),
        "",
        "Ресурсы:",
    ]
    for ingredient in recipe.get("ingredients") or []:
        lines.append(_ingredient_line(player, ingredient))
    if recipe.get("actions"):
        action_names = " → ".join(ACTION_NAMES.get(action, str(action)) for action in recipe.get("actions") or [])
        lines.append(f"\nАлхимические действия: {action_names}")
    max_count = _max_craft_count(player, recipe)
    lines.append(f"\nМожно создать сейчас: {max_count}.")
    return CraftResponse("\n".join(lines), [[CREATE]] + _recipe_navigation_buttons(workshop_id, source="preview"), data["zone"])


def _prompt_quantity(storage: Any, player: dict[str, Any]) -> CraftResponse:
    context = _active_context(player)
    recipe = recipe_by_id().get(str(context.get("selected_recipe_id") or ""))
    if not recipe:
        return _return_to_choice(storage, player)
    context["step"] = "quantity"
    storage.update_player(player)
    return CraftResponse(
        f"Сколько создать предмета «{_recipe_output_name(recipe)}»?\nОтправьте количество числом в чат.",
        _recipe_navigation_buttons(str(recipe.get("workshop") or ""), source="quantity"),
        WORKSHOP_BY_ID[str(recipe.get("workshop"))]["zone"],
    )




def _recipe_craft_seconds(recipe: dict[str, Any], *, player: dict[str, Any] | None = None, quantity: int = 1) -> int:
    seconds = max(1, safe_int(recipe.get("craft_time_seconds"), CRAFT_SECONDS_DEFAULT))
    from services.formula_runtime import evaluate
    seconds = max(1, safe_int(evaluate(recipe.get("time_formula_id"), _recipe_formula_context(recipe, player=player, quantity=quantity) | {"base_amount": seconds}, default=seconds), seconds))
    try:
        from services.world_event_runtime import multiplier
        seconds = max(1, math.ceil(seconds * multiplier("craft_time_multiplier", context={"workshop_id": recipe.get("workshop"), "recipe_id": recipe.get("id")})))
    except Exception:
        pass
    if player:
        seconds = max(1, round(seconds * max(0.05, 1 + _craft_effect_value(player, "craft_time_percent") / 100)))
    return seconds


def _total_craft_seconds(recipe: dict[str, Any], quantity: int, *, player: dict[str, Any] | None = None) -> int:
    return _recipe_craft_seconds(recipe, player=player, quantity=quantity) * max(1, safe_int(quantity, 1))


def _recipe_cost_copper(recipe: dict[str, Any], player: dict[str, Any], quantity: int) -> int:
    workshop_cost = 0
    workshop_id = str((player.get("crafting_context") or {}).get("constructor_workshop_id") or "")
    if workshop_id:
        try:
            from services.workshop_constructor_service import store as workshop_store
            row = workshop_store().get(workshop_id)
            if row and row.get("status") == "published":
                workshop_cost = max(0, safe_int((row.get("data") or {}).get("use_cost"), 0)) * (max(1, quantity) if (row.get("data") or {}).get("cost_per_operation", True) else 1)
        except Exception:
            pass
    if recipe.get("free", True) and not recipe.get("cost_formula_id"):
        try:
            from services.economy_runtime import service_price
            return service_price("craft", workshop_cost, player, {"quantity": quantity, "recipe_id": recipe.get("id")})
        except (ImportError, ValueError): return workshop_cost
    fixed = (safe_int(recipe.get("price_copper"), 0) + safe_int(recipe.get("price_silver"), 0) * 100
             + safe_int(recipe.get("price_gold"), 0) * 10_000
             + safe_int(recipe.get("price_magic_gold"), 0) * 1_000_000
             + safe_int(recipe.get("price_ancient"), 0) * 10_000_000) * max(1, quantity) + workshop_cost
    from services.formula_runtime import evaluate
    value = evaluate(recipe.get("cost_formula_id"), _recipe_formula_context(recipe, player=player, quantity=quantity) | {
        "base_amount": fixed, "price": fixed,
    }, default=fixed)
    result=max(0, safe_int(value, fixed))
    try:
        from services.economy_runtime import service_price
        return service_price("craft", result, player, {"quantity": quantity, "recipe_id": recipe.get("id")})
    except (ImportError, ValueError): return result


def _craft_effect_value(player: dict[str, Any], key: str) -> float:
    total = 0.0
    try:
        from services.effect_runtime_service import effect_fields, _definition
        for field in effect_fields():
            for row in player.get(field) or []:
                if isinstance(row, dict):
                    data = _definition(row)
                    if data.get("blocks_crafting") or data.get("craft_block"):
                        if key == "blocked":
                            return 1.0
                    total += float(data.get(key) or 0)
    except (TypeError, ValueError):
        pass
    workshop_id = str((player.get("crafting_context") or {}).get("constructor_workshop_id") or "")
    if workshop_id:
        try:
            from services.workshop_constructor_service import store as workshop_store
            workshop = workshop_store().get(workshop_id)
            data = workshop.get("data") if workshop and workshop.get("status") == "published" else {}
            total += float((data or {}).get(key) or 0)
            from services.effect_formula_runtime import resolve
            for effect_id in (data or {}).get("effect_ids") or []:
                effect = resolve(str(effect_id)) or {}
                if effect.get("blocks_crafting") or effect.get("craft_block"):
                    if key == "blocked":
                        return 1.0
                total += float(effect.get(key) or 0)
        except (TypeError, ValueError):
            pass
    return total


def _inventory_counts_by_id(player: dict[str, Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in player.get("inventory", []):
        if isinstance(row, dict):
            item_id = str(row.get("item_id") or row.get("id") or "")
            if item_id:
                out[item_id] = out.get(item_id, 0) + safe_int(row.get("amount"), 1)
    return out


def _recipe_energy_cost(recipe: dict[str, Any], player: dict[str, Any], quantity: int) -> int:
    base = max(0, safe_int(recipe.get("energy_cost"), 0)) * max(1, quantity)
    from services.formula_runtime import evaluate
    value = evaluate(recipe.get("energy_formula_id"), _recipe_formula_context(recipe, player=player, quantity=quantity) | {"base_amount": base}, default=base)
    return max(0, safe_int(value, base))

def _apply_elf_alchemy_refund(
    player: dict[str, Any],
    recipe: dict[str, Any],
    quantity: int,
    workshop_id: str,
) -> list[str]:
    """Эльфийское «Чутьё зельевара»: вернуть часть алхимических ингредиентов."""
    if workshop_id != "alchemy":
        return []
    ingredient_keys: list[tuple[str, int]] = []
    names: dict[str, str] = {}
    for ingredient in recipe.get("ingredients") or []:
        if not isinstance(ingredient, dict):
            continue
        item_id = str(ingredient.get("item_id") or "").strip()
        if not item_id:
            continue  # обобщённые ингредиенты (по типу) не возвращаем
        amount = max(1, safe_int(ingredient.get("amount"), 1))
        ingredient_keys.append((item_id, amount))
        names[item_id] = str(ingredient.get("name") or _item_name(item_id))
    refunds = alchemy_ingredient_refund(player, ingredient_keys, quantity)
    lines: list[str] = []
    for item_id, amount in refunds.items():
        if amount <= 0:
            continue
        name = names.get(item_id) or _item_name(item_id)
        add_inventory_item(
            player,
            build_inventory_item(name, amount, item_id=item_id),
            amount,
            item_id=item_id,
            default_source="Чутьё зельевара",
        )
        lines.append(f"🌿 Чутьё зельевара: сэкономлено {name} ×{amount}.")
    return lines


def _start_craft(storage: Any, player: dict[str, Any], quantity_text: str) -> CraftResponse:
    context = _active_context(player)
    recipe = recipe_by_id().get(str(context.get("selected_recipe_id") or ""))
    if not recipe:
        return _return_to_choice(storage, player)
    try:
        quantity = int(str(quantity_text).strip())
    except ValueError:
        return CraftResponse("Нужно отправить количество числом.", _recipe_navigation_buttons(str(recipe.get("workshop") or ""), source="quantity"), WORKSHOP_BY_ID[str(recipe.get("workshop"))]["zone"])
    if quantity <= 0:
        return CraftResponse("Количество должно быть больше нуля.", _recipe_navigation_buttons(str(recipe.get("workshop") or ""), source="quantity"), WORKSHOP_BY_ID[str(recipe.get("workshop"))]["zone"])
    if safe_int(player.get("level"), 1) < safe_int(recipe.get("player_level"), 0):
        return CraftResponse(str(recipe.get("text_not_enough_level") or "Недостаточный уровень для рецепта."), _recipe_navigation_buttons(str(recipe.get("workshop") or ""), source="quantity"), WORKSHOP_BY_ID[str(recipe.get("workshop"))]["zone"])
    if _craft_skill_level(player, str(recipe.get("workshop") or "")) < safe_int(recipe.get("profession_level"), 0):
        return CraftResponse(str(recipe.get("text_not_enough_level") or "Недостаточный уровень ремесленной профессии."), _recipe_navigation_buttons(str(recipe.get("workshop") or ""), source="quantity"), WORKSHOP_BY_ID[str(recipe.get("workshop"))]["zone"])
    if recipe.get("hidden") and str(recipe.get("id") or "") not in {str(x) for x in player.get("unlocked_recipes") or []}:
        return CraftResponse(str(recipe.get("text_unavailable") or "Рецепт ещё не открыт."), _recipe_navigation_buttons(str(recipe.get("workshop") or ""), source="quantity"), WORKSHOP_BY_ID[str(recipe.get("workshop"))]["zone"])
    blueprint_id = str(recipe.get("blueprint_id") or "")
    if recipe.get("blueprint_required") and _inventory_count(player, item_id=blueprint_id) < 1:
        return CraftResponse(str(recipe.get("text_unavailable") or "Для рецепта требуется чертёж."), _recipe_navigation_buttons(str(recipe.get("workshop") or ""), source="quantity"), WORKSHOP_BY_ID[str(recipe.get("workshop"))]["zone"])
    if _craft_effect_value(player, "blocked"):
        return CraftResponse(str(recipe.get("text_blocked") or "Активный эффект запрещает ремесло."), _recipe_navigation_buttons(str(recipe.get("workshop") or ""), source="quantity"), WORKSHOP_BY_ID[str(recipe.get("workshop"))]["zone"])
    if not _has_material_ingredients(player, recipe, quantity):
        return CraftResponse(str(recipe.get("text_not_enough_ingredients") or "Не хватает ресурсов для выбранного количества."), _recipe_navigation_buttons(str(recipe.get("workshop") or ""), source="quantity"), WORKSHOP_BY_ID[str(recipe.get("workshop"))]["zone"])
    if not _has_tools(player, recipe):
        return CraftResponse(str(recipe.get("text_not_enough_tool") or "Не хватает подходящего инструмента."), _recipe_navigation_buttons(str(recipe.get("workshop") or ""), source="quantity"), WORKSHOP_BY_ID[str(recipe.get("workshop"))]["zone"])
    delivery_mode = str(recipe.get("result_delivery") or "overload")
    if delivery_mode in {"inventory", "reject"}:
        from services.craft_result_delivery import can_place
        preview_amount = _recipe_output_amount(recipe) * quantity
        preview_item = _crafted_output_item(str((recipe.get("output") or {}).get("item_id") or recipe.get("output_item_id") or ""), _recipe_output_name(recipe), preview_amount)
        if not can_place(player, preview_item, preview_amount, delivery_mode):
            return CraftResponse(str(recipe.get("text_inventory_full") or "В инвентаре недостаточно места для результата."), _recipe_navigation_buttons(str(recipe.get("workshop") or ""), source="quantity"), WORKSHOP_BY_ID[str(recipe.get("workshop"))]["zone"])
    craft_cost = _recipe_cost_copper(recipe, player, quantity)
    money_key = "money_copper" if "money_copper" in player else "money"
    current_money = max(0, safe_int(player.get(money_key), 0))
    if current_money < craft_cost:
        return CraftResponse("Недостаточно монет для оплаты ремесла.", _recipe_navigation_buttons(str(recipe.get("workshop") or ""), source="quantity"), WORKSHOP_BY_ID[str(recipe.get("workshop"))]["zone"])
    energy_cost = _recipe_energy_cost(recipe, player, quantity)
    current_energy = max(0, safe_int(player.get("energy"), 0))
    if current_energy < max(energy_cost, safe_int(recipe.get("min_energy"), 0)):
        return CraftResponse(str(recipe.get("text_not_enough_energy") or "Недостаточно энергии для ремесла."), _recipe_navigation_buttons(str(recipe.get("workshop") or ""), source="quantity"), WORKSHOP_BY_ID[str(recipe.get("workshop"))]["zone"])
    from services.craft_weekly_limit_runtime import check as check_craft_limit, consume as consume_craft_limit
    limit_ok, limit_message = check_craft_limit(player, recipe, quantity=quantity, result_amount=_recipe_output_amount(recipe))
    if not limit_ok:
        return CraftResponse(limit_message, _recipe_navigation_buttons(str(recipe.get("workshop") or ""), source="quantity"), WORKSHOP_BY_ID[str(recipe.get("workshop"))]["zone"])
    if craft_cost:
        player[money_key] = current_money - craft_cost
        if money_key == "money_copper" and "money" in player:
            player["money"] = player[money_key]
        try:
            from services.economy_runtime import record
            record(player,"craft_payment","copper",-craft_cost,current_money,safe_int(player.get(money_key),0),source="craft",source_id=str(recipe.get("id") or ""))
        except (ImportError,OSError):pass
    if energy_cost and recipe.get("energy_charge_at", "start") == "start":
        player["energy"] = current_energy - energy_cost
    inventory_before = _inventory_counts_by_id(player)
    _consume_recipe_ingredients(player, recipe, quantity)
    if recipe.get("blueprint_required") and recipe.get("blueprint_one_time"):
        _consume_inventory(player, item_id=blueprint_id, amount=1)
    inventory_after = _inventory_counts_by_id(player)
    consumed_items = [{"item_id": item_id, "amount": before - inventory_after.get(item_id, 0)} for item_id, before in inventory_before.items() if before > inventory_after.get(item_id, 0)]
    consume_craft_limit(player, recipe, quantity=quantity, result_amount=_recipe_output_amount(recipe))
    workshop_id = str(recipe.get("workshop") or "smeltery")
    refund_lines = _apply_elf_alchemy_refund(player, recipe, quantity, workshop_id)
    seconds = _total_craft_seconds(recipe, quantity, player=player)
    craft_payload = {"recipe_id": recipe.get("id"), "quantity": quantity, "workshop_id": workshop_id, "energy_cost": energy_cost,
                     "charged_energy": energy_cost if recipe.get("energy_charge_at", "start") == "start" else 0,
                     "charged_cost": craft_cost, "consumed_items": consumed_items}
    if workshop_id == "alchemy":
        components = _recipe_components(recipe, quantity)
        metrics = _alchemy_metrics(player, components, [str(action) for action in (recipe.get("actions") or [])])
        if _alchemy_level(player) < STAGE_SUCCESS_LEVELS.get(str(metrics.get("stage")), 1):
            craft_payload.update({"alchemy_failure": True, "failure_item_id": "suspicious_potion"})
        elif random.randint(1, 100) > int(metrics.get("success_chance", 95)):
            craft_payload.update({"alchemy_failure": True, "failure_item_id": "suspicious_potion"})
        craft_payload["alchemy_metrics"] = metrics
    else:
        from services.formula_runtime import evaluate
        chance_context = _recipe_formula_context(recipe, player=player, quantity=quantity)
        success = safe_int(evaluate(recipe.get("success_formula_id"), chance_context | {"base_amount": recipe.get("success_chance", 100)}, default=recipe.get("success_chance", 100)), 100)
        success = max(0, min(100, success + round(_craft_effect_value(player, "craft_success_chance"))))
        critical = safe_int(evaluate(recipe.get("critical_formula_id"), chance_context | {"base_amount": recipe.get("critical_chance", 0)}, default=recipe.get("critical_chance", 0)), 0)
        partial = max(0, min(100, safe_int(recipe.get("partial_success_chance"), 0)))
        fail_chance = safe_int(evaluate(recipe.get("fail_formula_id"), chance_context | {"base_amount": recipe.get("fail_chance", 0)}, default=recipe.get("fail_chance", 0)), 0)
        roll = random.randint(1, 100)
        craft_payload["partial_success"] = roll > success and roll <= min(100, success + partial)
        craft_payload["craft_failure"] = (fail_chance > 0 and random.randint(1, 100) <= max(0, min(100, fail_chance))) or (roll > success and not craft_payload["partial_success"])
        craft_payload["critical_success"] = not craft_payload["craft_failure"] and random.randint(1, 100) <= max(0, min(100, critical + round(_craft_effect_value(player, "craft_critical_chance"))))
    timer = {
        "id": new_timer_id("craft"),
        "type": "craft",
        "seconds": seconds,
        "ends_at": now_ts() + seconds,
        "location_id": WORKSHOP_BY_ID[workshop_id]["zone"],
        "craft": craft_payload,
    }
    player["active_timer"] = timer
    context.clear()
    context.update({"workshop": workshop_id, "step": "crafting"})
    _set_city_zone(player, WORKSHOP_BY_ID[workshop_id]["zone"])
    storage.update_player(player)
    output_amount = _recipe_output_amount(recipe) * quantity
    text = (
        f"{str(recipe.get('text_start') or '⏳ Создание началось.')}\n\n"
        f"Предмет: {_recipe_output_name(recipe)} ×{output_amount}\n"
        f"Время: {format_duration(seconds)}\n\n"
        "Когда таймер закончится, придёт сообщение с результатом."
    )
    if refund_lines:
        text += "\n\n" + "\n".join(refund_lines)
    timer_buttons = [[CHECK_TIMER]] + ([[CANCEL]] if recipe.get("can_cancel", True) else []) + [[CRAFT_DISTRICT]]
    return CraftResponse(text, timer_buttons, WORKSHOP_BY_ID[workshop_id]["zone"], scheduled_timer=build_timer_schedule(player, timer))



def _quality_variant_stat_key(raw_type: str) -> str:
    mapping = {
        "strength": "bonus_strength",
        "endurance": "bonus_endurance",
        "dexterity": "bonus_agility",
        "agility": "bonus_agility",
        "perception": "bonus_perception",
        "intelligence": "bonus_intelligence",
        "wisdom": "bonus_wisdom",
        "accuracy": "bonus_accuracy",
        "dodge": "bonus_dodge",
        "armor": "armor",
        "physical_defense": "bonus_physical_defense",
        "magical_defense": "bonus_magic_defense",
        "magic_defense": "bonus_magic_defense",
        "magic_armor": "magic_armor",
        "hp": "bonus_hp",
        "max_hp": "bonus_hp",
        "spirit": "bonus_spirit",
        "inventory_slots": "bonus_inventory_slots",
        "stun_resist_chance": "bonus_stun_resist_chance",
        "stun_resist": "bonus_stun_resist_chance",
        "blind_resist_chance": "bonus_blind_resist_chance",
        "blind_resist": "bonus_blind_resist_chance",
        "bleed_resist_chance": "bonus_bleed_resist_chance",
        "bleed_resist": "bonus_bleed_resist_chance",
        "poison_resist_chance": "bonus_poison_resist_chance",
        "poison_resist": "bonus_poison_resist_chance",
        "crit_chance": "bonus_crit_chance",
        "crit_damage": "bonus_crit_damage",
        "bonus_max_mana": "bonus_mana",
        "max_mana": "bonus_mana",
        "bonus_max_spirit": "bonus_spirit",
        "max_spirit": "bonus_spirit",
    }
    return mapping.get(str(raw_type or ""), str(raw_type or ""))


RESIST_VARIANT_KEYS = {
    "bonus_stun_resist_chance",
    "bonus_blind_resist_chance",
    "bonus_bleed_resist_chance",
    "bonus_poison_resist_chance",
}


def _quality_variant_value(key: str, quality: str) -> int:
    if key == "bonus_crit_damage":
        return 5 if quality == "common" else 8 if quality == "uncommon" else 12
    if key in {"bonus_mana", "bonus_spirit", "bonus_hp"}:
        return 5 if quality == "common" else 8 if quality == "uncommon" else 12
    if key == "bonus_crit_chance":
        return 1 if quality != "rare" else 2
    if key in RESIST_VARIANT_KEYS:
        # Сопротивления указываются в процентах.
        return 2 if quality == "common" else 4 if quality == "uncommon" else 6
    if key in {"armor", "magic_armor", "bonus_dodge", "bonus_physical_defense", "bonus_magic_defense", "bonus_inventory_slots"}:
        return 1 if quality != "rare" else 2
    return 1 if quality != "rare" else 2


def _quality_variant_label(key: str) -> str:
    labels = {
        "bonus_strength": "Сила",
        "bonus_endurance": "Выносливость",
        "bonus_agility": "Ловкость",
        "bonus_perception": "Восприятие",
        "bonus_intelligence": "Интеллект",
        "bonus_wisdom": "Мудрость",
        "bonus_accuracy": "Точность",
        "bonus_dodge": "Уклонение",
        "armor": "Броня",
        "magic_armor": "Магическая броня",
        "bonus_physical_defense": "Физическая защита",
        "bonus_magic_defense": "Магическая защита",
        "bonus_hp": "HP",
        "bonus_inventory_slots": "Слоты инвентаря",
        "bonus_stun_resist_chance": "Сопротивление оглушению",
        "bonus_blind_resist_chance": "Сопротивление ослеплению",
        "bonus_bleed_resist_chance": "Сопротивление кровотечению",
        "bonus_poison_resist_chance": "Сопротивление отравлению",
        "bonus_crit_chance": "Шанс крита",
        "bonus_crit_damage": "Урон крита",
        "bonus_mana": "Мана",
        "bonus_spirit": "Дух",
    }
    return labels.get(key, key)


def _roll_quality_variant(definition: dict[str, Any]) -> dict[str, Any] | None:
    """Roll the final quality for a craftable item with quality variants.

    Uncommon and rare quality items are not crafted directly. A regular recipe
    creates the base item and then rolls the final quality instead:
    rare 10%, uncommon 40%, common 50%.
    """

    variants = [variant for variant in definition.get("quality_variants") or [] if isinstance(variant, dict)]
    if not variants:
        return None
    roll = random.randint(1, 100)
    wanted = "common"
    if roll <= 10:
        wanted = "rare"
    elif roll <= 50:
        wanted = "uncommon"
    return next((variant for variant in variants if str(variant.get("quality")) == wanted), variants[0])


def _crafted_output_item(item_id: str, item_name: str, amount: int, *, bonus_effect: bool = False) -> dict[str, Any]:
    definition = get_item_definition_by_id(item_id)
    if not definition:
        return build_inventory_item(item_name, amount, item_id=item_id)
    variant = _roll_quality_variant(definition)
    item = registry_item_to_inventory_item(definition, amount)
    if item.get("base_sell_price_copper") is None:
        base_price = item.get("sell_price_copper", item.get("sellPriceCopper"))
        if base_price is not None:
            item["base_sell_price_copper"] = max(0, safe_int(base_price, 0))
    if not variant:
        return item
    quality = str(variant.get("quality") or item.get("quality") or "common")
    quality_ru = {"common": "обычный", "uncommon": "необычный", "rare": "редкий"}.get(quality, quality)
    item["quality"] = quality_ru
    if quality != "common":
        item["name"] = f"{item.get('name') or item_name} ({quality_ru})"
        item["name_ru"] = item["name"]
        sell_price = 500 if quality == "rare" else 300
        item["quality_price_floor_copper"] = sell_price
        item["sell_price_copper"] = sell_price
        item["sellPriceCopper"] = sell_price
        item["can_sell"] = True
        item["canSell"] = True
    asset_filename = variant.get("asset_filename")
    if asset_filename:
        asset_path = str(asset_filename).replace("\\", "/")
        if asset_path.startswith("/assets/"):
            item["icon"] = asset_path
        else:
            item["icon"] = "/assets/items/crafting/" + asset_path.split("/")[-1]
        item["asset_icon"] = item["icon"]
    pool = [entry for entry in variant.get("effect_pool") or [] if isinstance(entry, dict)]
    count = max(1, safe_int(variant.get("effects_count"), 1))
    # Дворф «Мастерская закалка»: +1 эффект, если в пуле есть запасной вариант.
    if bonus_effect and len(pool) > count:
        count += 1
    if len(pool) > count:
        pool = random.sample(pool, count)
    stat_modifiers: dict[str, int] = {}
    stats: list[str] = []
    for entry in pool[:count]:
        key = _quality_variant_stat_key(str(entry.get("type") or ""))
        value = _quality_variant_value(key, quality)
        stat_modifiers[key] = stat_modifiers.get(key, 0) + value
        suffix = "%" if key in {"bonus_crit_chance", "bonus_crit_damage"} or key in RESIST_VARIANT_KEYS else ""
        stats.append(f"{_quality_variant_label(key)}: +{value}{suffix}")
    item["stat_modifiers"] = stat_modifiers
    item["stats"] = stats
    return item


def _place_craft_output(player: dict[str, Any], item: dict[str, Any], amount: int, recipe: dict[str, Any]):
    from services.craft_result_delivery import place
    return place(player, item, amount, mode=str(recipe.get("result_delivery") or "overload"), source="Ремесло")


def _apply_recipe_result_settings(item: dict[str, Any], recipe: dict[str, Any], *, player: dict[str, Any] | None = None, critical: bool = False) -> dict[str, Any]:
    qualities = ["common", "uncommon", "rare", "epic", "legendary", "mythic", "celestial", "divine"]
    quality = str(recipe.get("result_quality") or item.get("quality") or "")
    if recipe.get("quality_formula_id"):
        from services.formula_runtime import evaluate
        index = safe_int(evaluate(recipe.get("quality_formula_id"), _recipe_formula_context(recipe, player=player) | {"base_amount": qualities.index(quality) if quality in qualities else 0}, default=qualities.index(quality) if quality in qualities else 0), 0)
        quality = qualities[max(0, min(len(qualities) - 1, index))]
    if quality:
        if critical and recipe.get("critical_quality_upgrade") and quality in qualities:
            quality = qualities[min(len(qualities) - 1, qualities.index(quality) + 1)]
        item["quality"] = quality
    if recipe.get("result_level") not in (None, ""):
        item["item_level"] = max(1, safe_int(recipe.get("result_level"), 1))
        item["level"] = item["item_level"]
    if recipe.get("bind_on_create"):
        item["bound"] = True
        item["binding_type"] = str(recipe.get("binding_type") or "character")
    if recipe.get("unique_result"):
        item["unique"] = True
        item["is_unique"] = True
    handed = str(recipe.get("crafted_handedness") or "keep")
    if handed in {"one_handed", "two_handed"} and (item.get("can_be_one_handed") or item.get("can_be_two_handed") or item.get("two_handed") is not None):
        item["two_handed"] = handed == "two_handed"
    for prop in recipe.get("result_properties") or []:
        if isinstance(prop, dict) and random.randint(1, 100) <= max(0, min(100, safe_int(prop.get("chance"), 100))):
            key = str(prop.get("key") or prop.get("stat") or "")
            if key:
                item.setdefault("stat_modifiers", {})[key] = safe_int(prop.get("value"), 0)
    for effect in recipe.get("result_effects") or []:
        effect_id = str(effect.get("effect_id") if isinstance(effect, dict) else effect or "")
        chance = safe_int(effect.get("chance"), 100) if isinstance(effect, dict) else 100
        if effect_id and random.randint(1, 100) <= max(0, min(100, chance)):
            item.setdefault("effect_ids", []).append(effect_id)
    return item

def _unlock_alchemy_recipe(player: dict[str, Any], recipe_id: str | None) -> None:
    if not recipe_id:
        return
    unlocked = player.setdefault("unlocked_alchemy_recipes", [])
    if not isinstance(unlocked, list):
        unlocked = []
        player["unlocked_alchemy_recipes"] = unlocked
    if str(recipe_id) not in {str(item) for item in unlocked}:
        unlocked.append(str(recipe_id))


def enqueue_same_craft(storage: Any, player: dict[str, Any]) -> CraftResponse:
    timer = player.get("active_timer")
    craft = timer.get("craft") if isinstance(timer, dict) and isinstance(timer.get("craft"), dict) else {}
    recipe = recipe_by_id().get(str(craft.get("recipe_id") or ""))
    zone = str((timer or {}).get("location_id") or player.get("current_zone") or "seldar_craft_district")
    if not recipe or not recipe.get("can_queue"):
        return CraftResponse("Этот рецепт нельзя добавлять в очередь.", [[CHECK_TIMER]], zone)
    if str(recipe.get("workshop") or "") == "alchemy":
        return CraftResponse("Алхимические эксперименты нельзя ставить в автоматическую очередь.", [[CHECK_TIMER]], zone)
    quantity = 1
    if not _has_ingredients(player, recipe, quantity):
        return CraftResponse(str(recipe.get("text_not_enough_ingredients") or "Не хватает ресурсов для очереди."), [[CHECK_TIMER]], zone)
    cost = _recipe_cost_copper(recipe, player, quantity)
    money_key = "money_copper" if "money_copper" in player else "money"
    if safe_int(player.get(money_key), 0) < cost:
        return CraftResponse(str(recipe.get("text_not_enough_money") or "Недостаточно монет для очереди."), [[CHECK_TIMER]], zone)
    energy = _recipe_energy_cost(recipe, player, quantity)
    if safe_int(player.get("energy"), 0) < max(energy, safe_int(recipe.get("min_energy"), 0)):
        return CraftResponse(str(recipe.get("text_not_enough_energy") or "Недостаточно энергии для очереди."), [[CHECK_TIMER]], zone)
    from services.craft_weekly_limit_runtime import check as check_limit, consume as consume_limit
    ok, message = check_limit(player, recipe, quantity=1, result_amount=_recipe_output_amount(recipe))
    if not ok:
        return CraftResponse(message, [[CHECK_TIMER]], zone)
    before = _inventory_counts_by_id(player)
    if not _consume_recipe_ingredients(player, recipe, 1):
        return CraftResponse("Не удалось зарезервировать ингредиенты очереди.", [[CHECK_TIMER]], zone)
    after = _inventory_counts_by_id(player)
    consumed = [{"item_id": iid, "amount": amount - after.get(iid, 0)} for iid, amount in before.items() if amount > after.get(iid, 0)]
    player[money_key] = safe_int(player.get(money_key), 0) - cost
    if energy and recipe.get("energy_charge_at", "start") == "start":
        player["energy"] = safe_int(player.get("energy"), 0) - energy
    consume_limit(player, recipe, quantity=1, result_amount=_recipe_output_amount(recipe))
    success = max(0, min(100, safe_int(recipe.get("success_chance"), 100) + round(_craft_effect_value(player, "craft_success_chance"))))
    critical = max(0, min(100, safe_int(recipe.get("critical_chance"), 0) + round(_craft_effect_value(player, "craft_critical_chance"))))
    roll = random.randint(1, 100)
    partial = roll > success and roll <= min(100, success + max(0, safe_int(recipe.get("partial_success_chance"), 0)))
    failure = roll > success and not partial
    payload = {"recipe_id": recipe.get("id"), "quantity": 1, "workshop_id": recipe.get("workshop"), "energy_cost": energy,
               "charged_energy": energy if recipe.get("energy_charge_at", "start") == "start" else 0, "charged_cost": cost,
               "consumed_items": consumed, "craft_failure": failure, "partial_success": partial,
               "critical_success": not failure and random.randint(1, 100) <= critical}
    player.setdefault("craft_queue", []).append({"craft": payload, "seconds": _total_craft_seconds(recipe, 1, player=player), "location_id": zone})
    storage.update_player(player)
    return CraftResponse(f"Рецепт добавлен в очередь. Позиций: {len(player['craft_queue'])}.", [[CHECK_TIMER, QUEUE_ONE, CANCEL]], zone)


def _start_next_queued(player: dict[str, Any]) -> dict[str, Any] | None:
    queue = player.get("craft_queue")
    if not isinstance(queue, list) or not queue:
        return None
    job = queue.pop(0)
    seconds = max(1, safe_int(job.get("seconds"), 1))
    timer = {"id": new_timer_id("craft"), "type": "craft", "seconds": seconds, "ends_at": now_ts() + seconds,
             "location_id": job.get("location_id"), "craft": job.get("craft") or {}}
    player["active_timer"] = timer
    return timer


def complete_craft_timer(storage: Any, player: dict[str, Any], timer_id: str | None = None) -> CraftResponse:
    timer = player.get("active_timer")
    if not isinstance(timer, dict) or timer.get("type") != "craft":
        return CraftResponse("⏳ Активного ремесленного таймера нет.", _craft_district_buttons(), str(player.get("current_zone") or "seldar_craft_district"))
    if timer_id and str(timer.get("id") or "") != str(timer_id):
        return CraftResponse("⏳ Этот ремесленный таймер уже неактуален.", _craft_district_buttons(), str(player.get("current_zone") or "seldar_craft_district"))
    remaining = timer_remaining_seconds(timer)
    if remaining > 0:
        return CraftResponse(f"⏳ Создание ещё идёт. Осталось: {format_duration(remaining)}.", [[CHECK_TIMER], [CRAFT_DISTRICT]], str(timer.get("location_id") or player.get("current_zone") or "seldar_craft_district"))
    craft = timer.get("craft") if isinstance(timer.get("craft"), dict) else {}
    recipe = recipe_by_id().get(str(craft.get("recipe_id") or ""))
    workshop_id = str(craft.get("workshop_id") or (recipe or {}).get("workshop") or "smeltery")
    zone = str(timer.get("location_id") or WORKSHOP_BY_ID.get(workshop_id, WORKSHOP_BY_ID["smeltery"])["zone"])
    player["active_timer"] = None
    _clear_context(player)
    _set_city_zone(player, zone)
    quantity = max(1, safe_int(craft.get("quantity"), 1))
    delivered_amount = 0
    consequence_text = ""
    consequence_buttons: list[list[str]] | None = None
    if not recipe and not craft.get("alchemy_failure"):
        storage.update_player(player)
        return CraftResponse("⏳ Ремесленный таймер завершён, но рецепт не найден. Таймер очищен.", _craft_district_buttons(), zone)
    if craft.get("alchemy_failure") or craft.get("craft_failure"):
        item_id = craft.get("failure_item_id") or ((recipe or {}).get("failure_result_item_id") if recipe else None)
        item_name = _item_name(str(item_id)) if item_id else ""
        amount = max(1, safe_int((recipe or {}).get("failure_result_amount"), 1))
        if item_id:
            result, delivered_amount = _place_craft_output(player, build_inventory_item(str(item_name), amount, item_id=str(item_id)), amount, recipe or {})
        else:
            result = None
        if recipe and craft.get("craft_failure"):
            policy = str(recipe.get("failure_material_policy") or "lose_all")
            return_percent = 100 if policy == "return_all" else max(0, min(100, safe_int(recipe.get("failure_return_percent"), 0))) if policy == "return_percent" else 0
            if recipe.get("material_loss_formula_id"):
                from services.formula_runtime import evaluate
                loss_percent = max(0, min(100, safe_int(evaluate(recipe.get("material_loss_formula_id"), _recipe_formula_context(recipe, player=player, quantity=quantity) | {"base_amount": 100 - return_percent}, default=100 - return_percent), 100 - return_percent)))
                return_percent = 100 - loss_percent
            for consumed in craft.get("consumed_items") or []:
                if not isinstance(consumed, dict):
                    continue
                returned = math.floor(max(0, safe_int(consumed.get("amount"), 0)) * return_percent / 100)
                consumed_id = str(consumed.get("item_id") or "")
                if consumed_id and returned:
                    add_inventory_item(player, build_inventory_item(_item_name(consumed_id), returned, item_id=consumed_id), returned, item_id=consumed_id, default_source="Возврат после провала ремесла")
            failure_effect = str(recipe.get("failure_effect_id") or recipe.get("failure_curse_id") or "")
            if failure_effect:
                from services.effect_formula_runtime import apply_to_player
                apply_to_player(player, failure_effect, source="craft_failure", context={"recipe_id": recipe.get("id")})
            failure_event_id = str(recipe.get("failure_event_id") or "")
            if failure_event_id:
                from services.world_runtime import render_event
                view = render_event(failure_event_id, player=player)
                if view:
                    player["constructor_event_id"] = failure_event_id
                    consequence_text = str(view.get("text") or "")
                    consequence_buttons = view.get("buttons") or []
            failure_mob_id = str(recipe.get("failure_battle_mob_id") or "")
            if failure_mob_id:
                try:
                    from services.pve_battle_service import create_battle_for_constructor_mob
                    _, battle_text = create_battle_for_constructor_mob(player, failure_mob_id, location_id=str(player.get("current_location") or player.get("location_id") or "craft_event"))
                    consequence_text = battle_text
                    consequence_buttons = [["Атаковать", "Защищаться"], ["Попытаться сбежать"]]
                except ValueError:
                    consequence_text = str(recipe.get("text_failure_consequence_error") or "Последствие провала не удалось запустить.")
            for extra in recipe.get("byproducts") or []:
                if not isinstance(extra, dict) or str(extra.get("when") or "success") not in {"failure", "any"}:
                    continue
                extra_id = str(extra.get("item_id") or "")
                if extra_id and random.randint(1, 100) <= max(0, min(100, safe_int(extra.get("chance"), 100))):
                    extra_amount = max(1, safe_int(extra.get("amount"), 1)) * quantity
                    _, delivered = _place_craft_output(player, _crafted_output_item(extra_id, _item_name(extra_id), extra_amount), extra_amount, recipe)
                    delivered_amount += delivered
    else:
        output = recipe.get("output") or {}
        item_id = output.get("item_id")
        item_name = output.get("name") or _item_name(item_id)
        per_craft_amount = _roll_recipe_output_amount(recipe, player=player)
        amount = per_craft_amount * quantity
        if craft.get("partial_success"):
            amount = max(1, math.floor(amount * max(1, min(100, safe_int(recipe.get("partial_result_percent"), 50))) / 100))
        definition = get_item_definition_by_id(str(item_id or "")) if item_id else None
        craft_skill = str(WORKSHOP_BY_ID.get(workshop_id, {}).get("skill") or workshop_id)
        if isinstance(definition, dict) and definition.get("quality_variants") and amount > 1:
            result = None
            for _ in range(amount):
                crafted_item = _crafted_output_item(
                    str(item_id), str(item_name), 1,
                    bonus_effect=crafting_extra_effect_triggered(player, craft_skill),
                )
                _apply_recipe_result_settings(crafted_item, recipe, player=player, critical=bool(craft.get("critical_success")))
                apply_generated_item_level_and_price(player, crafted_item, "crafted")
                result, delivered = _place_craft_output(player, crafted_item, 1, recipe)
                delivered_amount += delivered
        else:
            crafted_item = _crafted_output_item(
                str(item_id), str(item_name), amount,
                bonus_effect=crafting_extra_effect_triggered(player, craft_skill),
            )
            _apply_recipe_result_settings(crafted_item, recipe, player=player, critical=bool(craft.get("critical_success")))
            apply_generated_item_level_and_price(player, crafted_item, "crafted")
            result, delivered_amount = _place_craft_output(player, crafted_item, amount, recipe)
        # Дополнительные и побочные результаты конструктора (§13.2–§13.3).
        extra_rows = list(recipe.get("results") or []) + list(recipe.get("byproducts") or [])
        for extra in extra_rows:
            if not isinstance(extra, dict):
                continue
            extra_id = str(extra.get("item_id") or "").strip()
            if not extra_id or extra_id == str(item_id or ""):
                continue
            when = str(extra.get("when") or "success")
            if when == "critical" and not craft.get("critical_success"):
                continue
            chance = max(0, min(100, safe_int(extra.get("chance"), 100)))
            if random.randint(1, 100) > chance:
                continue
            extra_amount = max(1, safe_int(extra.get("amount"), 1)) * quantity
            _, delivered = _place_craft_output(player, _crafted_output_item(extra_id, _item_name(extra_id), extra_amount), extra_amount, recipe)
            delivered_amount += delivered
        if workshop_id == "alchemy":
            _unlock_alchemy_recipe(player, str(recipe.get("id") or ""))
        try:
            from services.quest_runtime_service import progress as quest_progress
            quest_progress(player, "craft_item", str(item_id or ""), amount)
        except Exception:
            pass
        from services.item_effect_trigger_runtime import trigger as trigger_item_effect
        trigger_item_effect(player, {"item_id": str(item_id or "")}, "on_receive_item", context={"item_count": amount, "recipe_level": recipe.get("level", 1)})
        from services.item_effect_trigger_runtime import trigger_owned
        trigger_owned(player, "on_craft", context={"item_count": amount, "recipe_level": recipe.get("level", 1)})
        try:
            from services.achievement_engine import record_game_event
            record_game_event(player, "craft_item", amount, str(item_id or ""), storage=storage)
            from services.event_campaign_runtime import progress as event_progress
            event_progress(player, "craft_item", str(item_id or ""), amount, storage=storage)
            event_progress(player, "complete_recipe", str(recipe.get("id") or ""), quantity, storage=storage)
        except Exception:
            pass
    craft_exp = quantity
    if recipe:
        from services.formula_runtime import evaluate
        craft_exp = max(1, safe_int(evaluate(recipe.get("exp_formula_id"), _recipe_formula_context(recipe, player=player, quantity=quantity) | {"base_amount": quantity}, default=quantity), quantity))
    _add_craft_experience(player, workshop_id, craft_exp)
    if recipe and recipe.get("energy_charge_at") == "complete":
        player["energy"] = max(0, safe_int(player.get("energy"), 0) - max(0, safe_int(craft.get("energy_cost"), 0)))
    next_timer = None if consequence_buttons is not None else _start_next_queued(player)
    if not craft.get("alchemy_failure") and not craft.get("craft_failure"):
        try:
            from services.reputation_runtime_service import apply_trigger
            apply_trigger(player,"craft",str(recipe.get("id") or craft.get("recipe_id") or ""),reason="Успешное ремесло")
        except Exception:pass
    storage.update_player(player)
    notice = inventory_add_result_notice(result, item_name) if result is not None else ""
    if craft.get("alchemy_failure") or craft.get("craft_failure"):
        from services.text_runtime import game_text
        fallback = str((recipe or {}).get("text_fail") or "❌ Ремесло завершилось провалом.")
        text = game_text("craft.fail", fallback) + (f" Получено: {item_name} ×{amount}.{notice}" if item_name else "")
    else:
        from services.text_runtime import game_text
        fallback = str(recipe.get("text_partial_success") if craft.get("partial_success") else recipe.get("text_critical_success") if craft.get("critical_success") else recipe.get("text_success") or "✅ Создание завершено.")
        text = game_text("craft.success", fallback) + f" Получено: {item_name} ×{amount}.{notice}"
    if delivered_amount:
        text += " " + str((recipe or {}).get("text_delivery") or f"В доставку отправлено: ×{delivered_amount}.")
    if consequence_text:
        text += "\n\n" + consequence_text
    buttons = _alchemy_menu_buttons() if workshop_id == "alchemy" else _workshop_after_complete_buttons(workshop_id)
    if consequence_buttons is not None:
        buttons = consequence_buttons
    if next_timer:
        text += f"\n\n⏳ Следующая позиция очереди запущена: {format_duration(next_timer['seconds'])}."
        buttons = [[CHECK_TIMER, QUEUE_ONE, CANCEL]]
    return CraftResponse(text, buttons, zone, scheduled_timer=build_timer_schedule(player, next_timer) if next_timer else None)


def cancel_craft_timer(storage: Any, player: dict[str, Any]) -> CraftResponse:
    timer = player.get("active_timer")
    if not isinstance(timer, dict) or timer.get("type") != "craft":
        return CraftResponse("Активного ремесла для отмены нет.", _craft_district_buttons(), str(player.get("current_zone") or "seldar_craft_district"))
    craft = timer.get("craft") if isinstance(timer.get("craft"), dict) else {}
    recipe = recipe_by_id().get(str(craft.get("recipe_id") or ""))
    if not recipe or not recipe.get("can_cancel", True):
        return CraftResponse(str((recipe or {}).get("text_cancel_denied") or "Эту операцию нельзя отменить."), [[CHECK_TIMER]], str(timer.get("location_id") or "seldar_craft_district"))
    if recipe.get("return_materials_on_cancel", True):
        for row in craft.get("consumed_items") or []:
            item_id = str((row or {}).get("item_id") or "") if isinstance(row, dict) else ""
            amount = max(0, safe_int((row or {}).get("amount"), 0)) if isinstance(row, dict) else 0
            if item_id and amount:
                add_inventory_item(player, build_inventory_item(_item_name(item_id), amount, item_id=item_id), amount, item_id=item_id, default_source="Возврат отменённого ремесла")
    if recipe.get("refund_cost_on_cancel", True):
        money_key = "money_copper" if "money_copper" in player else "money"
        player[money_key] = max(0, safe_int(player.get(money_key), 0)) + max(0, safe_int(craft.get("charged_cost"), 0))
        if money_key == "money_copper" and "money" in player:
            player["money"] = player[money_key]
    if recipe.get("energy_refund_on_cancel", True):
        player["energy"] = safe_int(player.get("energy"), 0) + max(0, safe_int(craft.get("charged_energy"), 0))
    from services.craft_weekly_limit_runtime import refund
    refund(player, recipe, quantity=max(1, safe_int(craft.get("quantity"), 1)), result_amount=_recipe_output_amount(recipe))
    player["active_timer"] = None
    next_timer = _start_next_queued(player)
    _clear_context(player)
    storage.update_player(player)
    text = str(recipe.get("text_cancel") or "Создание отменено. Ресурсы возвращены по настройкам рецепта.")
    if next_timer:
        text += " Следующая позиция очереди запущена."
    return CraftResponse(text, [[CHECK_TIMER, QUEUE_ONE, CANCEL]] if next_timer else _craft_district_buttons(), str(timer.get("location_id") or "seldar_craft_district"), scheduled_timer=build_timer_schedule(player, next_timer) if next_timer else None)


def _workshop_after_complete_buttons(workshop_id: str) -> list[list[str]]:
    action = WORKSHOP_ACTION_BY_ID.get(workshop_id)
    rows = [[action]] if action else []
    rows.append([CRAFT_DISTRICT])
    return rows


def _return_to_choice(storage: Any, player: dict[str, Any]) -> CraftResponse:
    context = _active_context(player)
    workshop_id = str(context.get("workshop") or "")
    if workshop_id == "alchemy":
        return _alchemy_menu_response(player, persist_storage=storage)
    if workshop_id in WORKSHOP_BY_ID:
        section = context.get("section")
        if WORKSHOP_BY_ID[workshop_id].get("sections") and (not section or section == "default"):
            return _show_workshop_menu(storage, player, workshop_id)
        return _show_recipe_list(storage, player, workshop_id, str(section or "default"))
    _clear_context(player)
    _set_city_zone(player, "seldar_craft_district")
    storage.update_player(player)
    return CraftResponse("⚒ Ремесленный квартал", _craft_district_buttons(), "seldar_craft_district")


# ----------------------------- Alchemy flow -----------------------------


def _alchemy_menu_buttons() -> list[list[str]]:
    return [[ALCHEMY_BY_RECIPE, ALCHEMY_EXPERIMENT], [CRAFT_DISTRICT]]


def _alchemy_menu_response(player: dict[str, Any], persist_storage: Any | None = None) -> CraftResponse:
    _set_city_zone(player, WORKSHOP_BY_ID["alchemy"]["zone"])
    context = _active_context(player)
    context.clear()
    context.update({"workshop": "alchemy", "step": "alchemy_menu"})
    if persist_storage is not None:
        persist_storage.update_player(player)
    text = (
        "⚗️ Алхимическая мастерская\n\n"
        "Алхимия использует основу, активные ингредиенты, катализаторы, стабилизаторы и порядок действий.\n"
        "Выбор состава и действий проходит через нумерованные списки и ввод номера в чат.\n\n"
        "Выберите действие."
    )
    return CraftResponse(text, _alchemy_menu_buttons(), WORKSHOP_BY_ID["alchemy"]["zone"])


def _alchemy_data_by_role(role: str) -> list[dict[str, Any]]:
    payload = load_alchemy_runtime()
    return [entry for entry in payload.get("ingredients", []) if isinstance(entry, dict) and entry.get("role") == role]


def _alchemy_available_options(player: dict[str, Any], role: str) -> list[dict[str, Any]]:
    options: list[dict[str, Any]] = []
    for entry in _alchemy_data_by_role(role):
        item_id = str(entry.get("item_id") or "")
        if not item_id:
            continue
        count = _inventory_count(player, item_id=item_id)
        if count <= 0:
            continue
        item = dict(entry)
        item["name"] = _item_name(item_id)
        item["available"] = count
        options.append(item)
    return options


def _show_alchemy_component_list(storage: Any, player: dict[str, Any], role: str) -> CraftResponse:
    context = _active_context(player)
    options = _alchemy_available_options(player, role)
    context.update({"workshop": "alchemy", "step": f"choose_{role}", "alchemy_options": [entry["item_id"] for entry in options]})
    storage.update_player(player)
    title = ROLE_TITLES[role]
    lines = [f"Выберите {title}.", "Отправьте номер в чат.", ""]
    if not options:
        lines.append("Подходящих предметов в инвентаре нет.")
        return CraftResponse("\n".join(lines), [[ALCHEMY]], WORKSHOP_BY_ID["alchemy"]["zone"])
    for index, entry in enumerate(options, 1):
        lines.append(f"{index}. {entry['name']} ×{entry['available']}")
        lines.append(f"   {entry.get('description') or 'Базовое описание отсутствует.'}")
    return CraftResponse("\n".join(lines), [[ALCHEMY]], WORKSHOP_BY_ID["alchemy"]["zone"])


def _begin_experiment(storage: Any, player: dict[str, Any]) -> CraftResponse:
    context = _active_context(player)
    context.clear()
    context.update({"workshop": "alchemy", "mode": "experiment", "draft": {"base": [], "active_ingredients": [], "catalysts": [], "stabilizers": [], "actions": []}})
    return _show_alchemy_component_list(storage, player, "base")


def _select_alchemy_component(storage: Any, player: dict[str, Any], role: str, action: str) -> CraftResponse:
    context = _active_context(player)
    try:
        number = int(str(action).strip())
    except ValueError:
        return CraftResponse("Нужно отправить только номер из списка.", [[ALCHEMY]], WORKSHOP_BY_ID["alchemy"]["zone"])
    option_ids = context.get("alchemy_options") or []
    if not isinstance(option_ids, list) or number < 1 or number > len(option_ids):
        return CraftResponse(f"В списке нет варианта под номером {number}.\nОтправьте номер ещё раз.", [[ALCHEMY]], WORKSHOP_BY_ID["alchemy"]["zone"])
    item_id = str(option_ids[number - 1])
    context.update({"step": f"quantity_{role}", "pending_component": {"role": role, "item_id": item_id}})
    storage.update_player(player)
    return CraftResponse(f"Вы выбрали {ROLE_TITLES[role]}: {_item_name(item_id)}.\nУкажите количество.", [[ALCHEMY]], WORKSHOP_BY_ID["alchemy"]["zone"])


def _add_alchemy_component_quantity(storage: Any, player: dict[str, Any], role: str, action: str) -> CraftResponse:
    context = _active_context(player)
    pending = context.get("pending_component") if isinstance(context.get("pending_component"), dict) else {}
    item_id = str(pending.get("item_id") or "")
    try:
        amount = int(str(action).strip())
    except ValueError:
        return CraftResponse("Нужно отправить количество числом.", [[ALCHEMY]], WORKSHOP_BY_ID["alchemy"]["zone"])
    if amount <= 0:
        return CraftResponse("Количество должно быть больше нуля.", [[ALCHEMY]], WORKSHOP_BY_ID["alchemy"]["zone"])
    if _inventory_count(player, item_id=item_id) < amount:
        return CraftResponse("В инвентаре нет такого количества.", [[ALCHEMY]], WORKSHOP_BY_ID["alchemy"]["zone"])
    draft = context.setdefault("draft", {"base": [], "active_ingredients": [], "catalysts": [], "stabilizers": [], "actions": []})
    key = ROLE_DRAFT_KEYS[role]
    if role == "base":
        draft[key] = [{"item_id": item_id, "amount": amount}]
        context.pop("pending_component", None)
        storage.update_player(player)
        return _show_alchemy_component_list(storage, player, "active")
    draft.setdefault(key, []).append({"item_id": item_id, "amount": amount})
    context.pop("pending_component", None)
    if role == "active":
        context["step"] = "ask_more_active"
        storage.update_player(player)
        return CraftResponse(f"Добавлено: {_item_name(item_id)} ×{amount}.\nДобавить ещё один ингредиент?", [[YES, NO], [ALCHEMY]], WORKSHOP_BY_ID["alchemy"]["zone"])
    if role == "catalyst":
        context["step"] = "ask_more_catalyst"
        storage.update_player(player)
        return CraftResponse(f"Добавлено: {_item_name(item_id)} ×{amount}.\nДобавить ещё один катализатор?", [[YES, NO], [ALCHEMY]], WORKSHOP_BY_ID["alchemy"]["zone"])
    context["step"] = "ask_more_stabilizer"
    storage.update_player(player)
    return CraftResponse(f"Добавлено: {_item_name(item_id)} ×{amount}.\nДобавить ещё один стабилизатор?", [[YES, NO], [ALCHEMY]], WORKSHOP_BY_ID["alchemy"]["zone"])


def _ask_add_catalyst(storage: Any, player: dict[str, Any]) -> CraftResponse:
    context = _active_context(player)
    context["step"] = "ask_add_catalyst"
    storage.update_player(player)
    return CraftResponse("Хотите добавить катализатор?", [[YES, NO], [ALCHEMY]], WORKSHOP_BY_ID["alchemy"]["zone"])


def _ask_add_stabilizer(storage: Any, player: dict[str, Any]) -> CraftResponse:
    context = _active_context(player)
    context["step"] = "ask_add_stabilizer"
    storage.update_player(player)
    return CraftResponse("Хотите добавить стабилизатор?", [[YES, NO], [ALCHEMY]], WORKSHOP_BY_ID["alchemy"]["zone"])


def _action_options() -> list[dict[str, str]]:
    payload = load_alchemy_runtime()
    actions = payload.get("actions") if isinstance(payload.get("actions"), list) else []
    return [entry for entry in actions if isinstance(entry, dict) and entry.get("id")]


def _show_action_order(storage: Any, player: dict[str, Any]) -> CraftResponse:
    context = _active_context(player)
    context["step"] = "choose_actions"
    storage.update_player(player)
    lines = ["Выберите порядок действий.", "Отправьте номера действий через пробел.", "Пример: 1 8 5", ""]
    for index, action in enumerate(_action_options(), 1):
        lines.append(f"{index}. {action.get('name') or ACTION_NAMES.get(str(action.get('id')), str(action.get('id')))}")
    return CraftResponse("\n".join(lines), [[ALCHEMY]], WORKSHOP_BY_ID["alchemy"]["zone"])


def _ingredient_total_from_draft(draft: dict[str, Any]) -> int:
    # Stages are limited by the number of selected component entries, not by the
    # quantity of each stack.  Example: clean water ×1 + chamomile ×2 is two
    # ingredients and remains simple alchemy.
    total = 0
    for key in ("base", "active_ingredients", "catalysts", "stabilizers"):
        entries = draft.get(key) if isinstance(draft.get(key), list) else []
        total += sum(1 for entry in entries if isinstance(entry, dict))
    return total


def _stage_limits(draft: dict[str, Any]) -> tuple[str, int, int]:
    total = _ingredient_total_from_draft(draft)
    if total <= 2:
        return "Простая алхимия", 2, 2
    if total <= 3:
        return "Сложная алхимия", 3, 4
    if total <= 5:
        return "Высшая алхимия", 5, 6
    return "Великая алхимия", 8, 10


def _parse_action_order(storage: Any, player: dict[str, Any], action: str) -> CraftResponse:
    context = _active_context(player)
    parts = str(action).strip().split()
    if not parts or any(not part.isdigit() for part in parts):
        return CraftResponse("Нужно отправить номера действий через пробел.\nПример: 1 8 5", [[ALCHEMY]], WORKSHOP_BY_ID["alchemy"]["zone"])
    options = _action_options()
    indexes = [int(part) for part in parts]
    bad = next((index for index in indexes if index < 1 or index > len(options)), None)
    if bad is not None:
        return CraftResponse(f"В списке нет варианта под номером {bad}.\nОтправьте номер ещё раз.", [[ALCHEMY]], WORKSHOP_BY_ID["alchemy"]["zone"])
    draft = context.setdefault("draft", {})
    stage, _ingredient_limit, action_limit = _stage_limits(draft)
    if len(indexes) > action_limit:
        return CraftResponse("Вы выбрали слишком много действий для выбранных ингредиентов.", [[ALCHEMY]], WORKSHOP_BY_ID["alchemy"]["zone"])
    draft["actions"] = [str(options[index - 1]["id"]) for index in indexes]
    context["step"] = "confirm_experiment"
    storage.update_player(player)
    return _show_experiment_summary(player)


def _draft_components(draft: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for key in ("base", "active_ingredients", "catalysts", "stabilizers"):
        for entry in draft.get(key) if isinstance(draft.get(key), list) else []:
            if isinstance(entry, dict):
                result.append(entry)
    return result


def _show_experiment_summary(player: dict[str, Any]) -> CraftResponse:
    context = _active_context(player)
    draft = context.get("draft") if isinstance(context.get("draft"), dict) else {}
    stage, ingredient_limit, action_limit = _stage_limits(draft)
    components = _draft_components(draft)
    base = draft.get("base") if isinstance(draft.get("base"), list) else []
    active = draft.get("active_ingredients") if isinstance(draft.get("active_ingredients"), list) else []
    if not base or not active:
        return CraftResponse("Для опыта нужна основа и хотя бы один активный ингредиент.", [[CHANGE_COMPOSITION], [ALCHEMY]], WORKSHOP_BY_ID["alchemy"]["zone"])
    if _ingredient_total_from_draft(draft) > ingredient_limit:
        return CraftResponse("Вы выбрали слишком много ингредиентов для выбранной стадии.", [[CHANGE_COMPOSITION], [ALCHEMY]], WORKSHOP_BY_ID["alchemy"]["zone"])
    actions = draft.get("actions") if isinstance(draft.get("actions"), list) else []
    if len(actions) > action_limit:
        return CraftResponse("Вы выбрали слишком много действий для выбранных ингредиентов.", [[CHANGE_ACTIONS], [ALCHEMY]], WORKSHOP_BY_ID["alchemy"]["zone"])
    lines = ["Проверьте состав опыта:", ""]
    for entry in components:
        lines.append(f"• {_item_name(str(entry.get('item_id')))} ×{safe_int(entry.get('amount'), 1)}")
    action_names = " → ".join(ACTION_NAMES.get(action, action) for action in actions) or "—"
    metrics = _alchemy_metrics(player, components, actions)
    lines.extend(["", f"Действия: {action_names}", f"Предполагаемая стадия: {stage}", f"Общий риск: {_risk_label(int(metrics['risk']))}."])
    return CraftResponse("\n".join(lines), [[CONFIRM_EXPERIMENT], [CHANGE_COMPOSITION, CHANGE_ACTIONS], [ALCHEMY]], WORKSHOP_BY_ID["alchemy"]["zone"])


def _recipe_signature(recipe: dict[str, Any]) -> tuple[tuple[tuple[str, int], ...], tuple[str, ...]]:
    totals: dict[str, int] = {}
    for ingredient in recipe.get("ingredients") or []:
        if not isinstance(ingredient, dict):
            continue
        item_id = str(ingredient.get("item_id") or "")
        if not item_id:
            continue
        totals[item_id] = totals.get(item_id, 0) + max(1, safe_int(ingredient.get("amount"), 1))
    actions = tuple(str(action) for action in (recipe.get("actions") or []))
    return tuple(sorted(totals.items())), actions


def _draft_signature(draft: dict[str, Any]) -> tuple[tuple[tuple[str, int], ...], tuple[str, ...]]:
    totals: dict[str, int] = {}
    for entry in _draft_components(draft):
        item_id = str(entry.get("item_id") or "")
        if not item_id:
            continue
        totals[item_id] = totals.get(item_id, 0) + max(1, safe_int(entry.get("amount"), 1))
    actions = tuple(str(action) for action in (draft.get("actions") if isinstance(draft.get("actions"), list) else []))
    return tuple(sorted(totals.items())), actions


def _matching_alchemy_recipe(draft: dict[str, Any]) -> dict[str, Any] | None:
    signature = _draft_signature(draft)
    for recipe in _recipes_for("alchemy", "Рецепты"):
        if _recipe_signature(recipe) == signature:
            return recipe
    return None


def _alchemy_meta_by_id() -> dict[str, dict[str, Any]]:
    payload = load_alchemy_runtime()
    result: dict[str, dict[str, Any]] = {}
    for entry in payload.get("ingredients", []) if isinstance(payload.get("ingredients"), list) else []:
        if isinstance(entry, dict) and entry.get("item_id"):
            result[str(entry["item_id"])] = entry
    return result


def _alchemy_stage_for_components(component_count: int) -> str:
    if component_count <= 2:
        return "Простая алхимия"
    if component_count <= 3:
        return "Сложная алхимия"
    if component_count <= 5:
        return "Высшая алхимия"
    return "Великая алхимия"


def _alchemy_level(player: dict[str, Any]) -> int:
    crafting = player.get("crafting_levels") if isinstance(player.get("crafting_levels"), dict) else {}
    alchemy = crafting.get("alchemy") if isinstance(crafting.get("alchemy"), dict) else {}
    return max(1, safe_int(alchemy.get("level"), safe_int(player.get("alchemy_level"), 1)))


def _alchemy_metrics(player: dict[str, Any], components: list[dict[str, Any]], actions: list[str]) -> dict[str, Any]:
    meta = _alchemy_meta_by_id()
    component_count = max(1, len(components))
    stage = _alchemy_stage_for_components(component_count)
    level = _alchemy_level(player)
    base_power = 0
    tier_sum = volatility = toxicity = stability = 0
    for component in components:
        item_id = str(component.get("item_id") or "")
        amount = max(1, safe_int(component.get("amount"), 1))
        entry = meta.get(item_id, {})
        base_power += safe_int(entry.get("potency"), 1) * amount
        tier_sum += safe_int(entry.get("tier"), 1)
        volatility += safe_int(entry.get("volatility"), 0) * amount
        toxicity += safe_int(entry.get("toxicity"), 0) * amount
        stability += safe_int(entry.get("stability"), 0) * amount
    skill_bonus = 1.0 + min(0.5, max(0, level - 1) * 0.005)
    power = math.ceil(base_power * STAGE_POWER_BONUS.get(stage, 1.0) * skill_bonus)
    complexity = STAGE_COMPLEXITY_BASE.get(stage, 10) + tier_sum + volatility + toxicity + len(actions)
    chance = 60 + int(level * 1.5) + 5 - complexity
    chance = max(5, min(95, chance))
    if level >= STAGE_GUARANTEED_LEVELS.get(stage, 10**9):
        chance = 100
    try:
        from services.world_event_runtime import modifiers as world_modifiers
        mods = world_modifiers(context={"workshop_id": "alchemy", "game_id": player.get("game_id"), "level": level})
        chance = max(0, min(100, round(chance * float(mods.get("craft_success_multiplier", 1) or 0) + float(mods.get("craft_success_percent", 0) or 0))))
    except Exception:
        pass
    risk = max(0, volatility + toxicity + STAGE_RISK_PENALTY.get(stage, 0) - stability)
    return {"stage": stage, "power": power, "complexity": complexity, "success_chance": chance, "risk": risk, "level": level}


def _risk_label(risk: int) -> str:
    if risk <= 3:
        return "низкий"
    if risk <= 8:
        return "средний"
    if risk <= 15:
        return "высокий"
    return "очень высокий"


def _recipe_components(recipe: dict[str, Any], quantity: int = 1) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for ingredient in recipe.get("ingredients") or []:
        if isinstance(ingredient, dict):
            result.append({"item_id": str(ingredient.get("item_id") or ""), "amount": max(1, safe_int(ingredient.get("amount"), 1)) * max(1, quantity)})
    return result


def _consume_draft_components(player: dict[str, Any], draft: dict[str, Any]) -> bool:
    totals: dict[str, int] = {}
    for entry in _draft_components(draft):
        item_id = str(entry.get("item_id") or "")
        if not item_id:
            continue
        totals[item_id] = totals.get(item_id, 0) + max(1, safe_int(entry.get("amount"), 1))
    if any(_inventory_count(player, item_id=item_id) < amount for item_id, amount in totals.items()):
        return False
    for item_id, amount in totals.items():
        _consume_inventory(player, item_id=item_id, amount=amount)
    return True


def _start_alchemy_experiment(storage: Any, player: dict[str, Any]) -> CraftResponse:
    context = _active_context(player)
    draft = context.get("draft") if isinstance(context.get("draft"), dict) else {}
    if not _consume_draft_components(player, draft):
        return CraftResponse("Не хватает ингредиентов для опыта.", [[CHANGE_COMPOSITION], [ALCHEMY]], WORKSHOP_BY_ID["alchemy"]["zone"])
    recipe = _matching_alchemy_recipe(draft)
    metrics = _alchemy_metrics(player, _draft_components(draft), [str(action) for action in (draft.get("actions") if isinstance(draft.get("actions"), list) else [])])
    if recipe is None:
        # Non-exact experiments do not create a finished product.
        recipe_id = "alchemy_failed_experiment"
        failure = True
    else:
        recipe_id = str(recipe.get("id"))
        if _alchemy_level(player) < STAGE_SUCCESS_LEVELS.get(str(metrics.get("stage")), 1):
            failure = True
        else:
            failure = random.randint(1, 100) > int(metrics.get("success_chance", 95))
    seconds = CRAFT_SECONDS_DEFAULT
    timer = {
        "id": new_timer_id("craft"),
        "type": "craft",
        "seconds": seconds,
        "ends_at": now_ts() + seconds,
        "location_id": WORKSHOP_BY_ID["alchemy"]["zone"],
        "craft": {"recipe_id": recipe_id, "quantity": 1, "workshop_id": "alchemy", "alchemy_failure": failure, "failure_item_id": "suspicious_potion", "alchemy_metrics": metrics},
    }
    if failure:
        # При неудачном опыте алхимия выдаёт «Подозрительное зелье».
        # Store enough data for completion even though there is no public recipe.
        timer["craft"]["fallback_output"] = {"item_id": "suspicious_potion", "amount": 1}
    player["active_timer"] = timer
    context.clear()
    context.update({"workshop": "alchemy", "step": "crafting"})
    _set_city_zone(player, WORKSHOP_BY_ID["alchemy"]["zone"])
    storage.update_player(player)
    result_text = "алхимический опыт" if failure else _recipe_output_name(recipe or {})
    return CraftResponse(
        f"⏳ Вы начали {result_text}.\n\nВремя: {format_duration(seconds)}\nКогда таймер закончится, придёт результат.",
        [[CHECK_TIMER], [ALCHEMY]],
        WORKSHOP_BY_ID["alchemy"]["zone"],
        scheduled_timer=build_timer_schedule(player, timer),
    )


def _alchemy_journal(storage: Any, player: dict[str, Any]) -> CraftResponse:
    return _alchemy_menu_response(player, persist_storage=storage)


def _handle_alchemy_action(storage: Any, player: dict[str, Any], action: str) -> CraftResponse:
    context = _active_context(player)
    step = str(context.get("step") or "alchemy_menu")
    if action == CRAFT_DISTRICT:
        _clear_context(player)
        _set_city_zone(player, "seldar_craft_district")
        storage.update_player(player)
        return CraftResponse("⚒ Ремесленный квартал", _craft_district_buttons(), "seldar_craft_district")
    if action in {ALCHEMY, BACK, CANCEL, RETURN_TO_CHOICE}:
        return _alchemy_menu_response(player, persist_storage=storage)
    if action == ALCHEMY_BY_RECIPE:
        context.update({"workshop": "alchemy", "section": "Рецепты", "step": "list"})
        return _show_recipe_list(storage, player, "alchemy", "Рецепты")
    if action == ALCHEMY_EXPERIMENT:
        return _begin_experiment(storage, player)
    if action == ALCHEMY_JOURNAL:
        return _alchemy_journal(storage, player)
    if step == "choose_actions":
        return _parse_action_order(storage, player, action)
    if step.startswith("choose_"):
        role = step.removeprefix("choose_")
        return _select_alchemy_component(storage, player, role, action)
    if step.startswith("quantity_"):
        role = step.removeprefix("quantity_")
        return _add_alchemy_component_quantity(storage, player, role, action)
    if step == "ask_more_active":
        if action == YES:
            return _show_alchemy_component_list(storage, player, "active")
        if action == NO:
            return _ask_add_catalyst(storage, player)
    if step == "ask_add_catalyst":
        if action == YES:
            return _show_alchemy_component_list(storage, player, "catalyst")
        if action == NO:
            return _ask_add_stabilizer(storage, player)
    if step == "ask_more_catalyst":
        if action == YES:
            return _show_alchemy_component_list(storage, player, "catalyst")
        if action == NO:
            return _ask_add_stabilizer(storage, player)
    if step == "ask_add_stabilizer":
        if action == YES:
            return _show_alchemy_component_list(storage, player, "stabilizer")
        if action == NO:
            return _show_action_order(storage, player)
    if step == "ask_more_stabilizer":
        if action == YES:
            return _show_alchemy_component_list(storage, player, "stabilizer")
        if action == NO:
            return _show_action_order(storage, player)
    if step == "confirm_experiment":
        if action == CONFIRM_EXPERIMENT:
            return _start_alchemy_experiment(storage, player)
        if action == CHANGE_COMPOSITION:
            return _begin_experiment(storage, player)
        if action == CHANGE_ACTIONS:
            return _show_action_order(storage, player)
    if step == "list" and action.startswith(CRAFT_PREFIX):
        recipe = _selected_recipe_from_context(player, action)
        if recipe:
            return _preview_recipe(storage, player, recipe)
    if step == "preview" and action == CREATE:
        return _prompt_quantity(storage, player)
    if step == "quantity":
        return _start_craft(storage, player, action)
    return CraftResponse("Неизвестное алхимическое действие.", _alchemy_menu_buttons(), WORKSHOP_BY_ID["alchemy"]["zone"])


# ----------------------------- Public dispatch -----------------------------


def _is_number_sequence(action: str) -> bool:
    parts = str(action or "").split()
    return bool(parts) and all(part.isdigit() for part in parts)


def _is_contextual_crafting_input(context: dict[str, Any], action: str) -> bool:
    """Return True only for inputs that belong to the active crafting flow.

    A stale ``crafting_context`` must not capture every city button, slash
    command or random chat message. Otherwise the player can get dragged back
    into the last workshop (most visibly the Forge) by any unrelated input.
    """

    if not isinstance(context, dict) or not context:
        return False
    if str(action or "").strip().startswith("/"):
        return False
    if action in CRAFT_ACTIONS or action in WORKSHOPS or action in {ENCHANTER, JEWELRY}:
        return True
    if action.startswith(CRAFT_PREFIX):
        return True

    step = str(context.get("step") or "")
    workshop_id = str(context.get("workshop") or "")

    if workshop_id == "alchemy":
        if step == "choose_actions":
            return _is_number_sequence(action)
        if step.startswith("choose_") or step.startswith("quantity_"):
            return str(action or "").strip().isdigit()
        return False

    if step == "quantity":
        return str(action or "").strip().isdigit()

    return False


def should_handle_crafting_action(player: dict[str, Any], action: str) -> bool:
    if isinstance(player.get("active_timer"), dict) and player["active_timer"].get("type") == "craft":
        return True
    if action in WORKSHOPS or action in {ENCHANTER, JEWELRY}:
        return True

    try:
        from services.workshop_constructor_service import published_for_action
        if published_for_action(action):
            return True
    except Exception:
        pass
    context = player.get("crafting_context")
    if isinstance(context, dict) and _is_contextual_crafting_input(context, action):
        # A stale workshop context must not consume plain numeric input after the
        # player has already moved back to the city, market or an external area.
        return is_crafting_zone(player)

    if is_crafting_zone(player):
        if action in CRAFT_ACTIONS or action.startswith(CRAFT_PREFIX):
            return True
    return False


def handle_crafting_action(storage: Any, player: dict[str, Any], action: str) -> CraftResponse:
    active_timer = player.get("active_timer")
    if isinstance(active_timer, dict) and active_timer.get("type") == "craft":
        if action == CHECK_TIMER:
            return complete_craft_timer(storage, player, active_timer.get("id"))
        if action == QUEUE_ONE:
            return enqueue_same_craft(storage, player)
        if action == CANCEL:
            return cancel_craft_timer(storage, player)
        remaining = timer_remaining_seconds(active_timer)
        if remaining <= 0:
            return complete_craft_timer(storage, player, active_timer.get("id"))
        active_recipe = recipe_by_id().get(str((active_timer.get("craft") or {}).get("recipe_id") or "")) if isinstance(active_timer.get("craft"), dict) else None
        lock_buttons = [[CHECK_TIMER]] + ([[CANCEL]] if active_recipe and active_recipe.get("can_cancel", True) else [])
        return CraftResponse(
            f"⏳ Сначала дождитесь окончания создания. Осталось: {format_duration(remaining)}.",
            lock_buttons,
            str(active_timer.get("location_id") or player.get("current_zone") or "seldar_craft_district"),
        )

    if action in {BACK_TO_CENTRAL, CENTRAL_SQUARE}:
        _clear_context(player)
        _set_city_zone(player, "seldar_central_square")
        storage.update_player(player)
        return CraftResponse("🏙 Центральная площадь Селдара", [], "seldar_central_square")

    if action == ENCHANTER:
        return _maintenance_response(storage, player, "🔮 Мастерская чародея", "Мастерская временно закрыта на техническое обслуживание.")

    try:
        from services.workshop_constructor_service import published_for_action
        constructor_workshop = published_for_action(action)
    except Exception:
        constructor_workshop = None
    if constructor_workshop:
        return _show_constructor_workshop(storage, player, constructor_workshop)

    if action in WORKSHOPS:
        workshop_id = WORKSHOPS[action]["id"]
        return _show_workshop_menu(storage, player, workshop_id)

    if action == BIJOUTERIE:
        return _jewelry_bijouterie_response(storage, player)
    if action == GEM_INSERT:
        return _jewelry_gem_insert_response(storage, player)

    context = _active_context(player)
    workshop_id = str(context.get("workshop") or "")
    if workshop_id == "alchemy":
        return _handle_alchemy_action(storage, player, action)

    if action == CRAFT_DISTRICT:
        _clear_context(player)
        _set_city_zone(player, "seldar_craft_district")
        storage.update_player(player)
        return CraftResponse("⚒ Ремесленный квартал", _craft_district_buttons(), "seldar_craft_district")
    if action == CANCEL:
        _clear_context(player)
        _set_city_zone(player, "seldar_craft_district")
        storage.update_player(player)
        return CraftResponse("Создание отменено. Вы вернулись в Ремесленный квартал.", _craft_district_buttons(), "seldar_craft_district")
    if action == BACK:
        return _return_to_choice(storage, player)
    if action == RETURN_TO_CHOICE:
        return _return_to_choice(storage, player)
    if workshop_id == "jewelry" and action == RINGS_SECTION:
        # «Кольца» открывает под-меню выбора металла, а не список рецептов.
        return _jewelry_rings_menu_response(storage, player)
    if workshop_id in WORKSHOP_BY_ID and action in SECTION_LABELS:
        return _show_recipe_list(storage, player, workshop_id, action)
    if action.startswith(CRAFT_PREFIX):
        recipe = _selected_recipe_from_context(player, action)
        if not recipe:
            return CraftResponse("Такого номера крафта нет в текущем списке.", _recipe_navigation_buttons(workshop_id, source="list"), WORKSHOP_BY_ID.get(workshop_id, WORKSHOP_BY_ID["smeltery"])["zone"])
        return _preview_recipe(storage, player, recipe)
    step = str(context.get("step") or "")
    if step == "preview" and action == CREATE:
        return _prompt_quantity(storage, player)
    if step == "quantity":
        return _start_craft(storage, player, action)
    if workshop_id in WORKSHOP_BY_ID:
        return _show_workshop_menu(storage, player, workshop_id)
    _clear_context(player)
    _set_city_zone(player, "seldar_craft_district")
    storage.update_player(player)
    return CraftResponse("Неизвестное ремесленное действие.", _craft_district_buttons(), "seldar_craft_district")
