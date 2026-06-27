"""RBAC для админ-панели V2 — роли, права и их разрешение.

Модель доступа (гибрид):

* **ENV-bootstrap** — каждый, кто указан в ``TELEGRAM_ADMIN_USER_IDS`` /
  ``VK_ADMIN_USER_IDS`` (текущий механизм доступа), по умолчанию получает роль
  ``owner``, чтобы при включении RBAC никто не потерял доступ.
* **Override в хранилище** — owner может переопределить роль любого админа; такие
  переопределения хранятся персистентно (файл ``data/admin_roles.json`` с
  блокировкой, как у портового рынка/курьера) и имеют приоритет над ENV.

Право проверяется на КАЖДОМ изменяющем admin-эндпоинте, а не только факт
наличия сессии. ``owner`` имеет все права (sentinel ``*``).
"""

from __future__ import annotations

import json
import os
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

try:  # POSIX-блокировка (на Windows отсутствует)
    import fcntl
except Exception:  # pragma: no cover - Windows
    fcntl = None  # type: ignore[assignment]

from project_paths import project_path, resolve_project_path
from services.admin_access import is_configured_admin_user

# --- Роли -------------------------------------------------------------------
OWNER = "owner"
ADMIN = "admin"
SUPPORT = "support"
MODERATOR = "moderator"
CONTENT = "content"
ECONOMY = "economy"
READ_ONLY = "read_only"

ROLES = (OWNER, ADMIN, SUPPORT, MODERATOR, CONTENT, ECONOMY, READ_ONLY)
DEFAULT_ROLE = READ_ONLY

ROLE_LABELS = {
    OWNER: "Владелец",
    ADMIN: "Администратор",
    SUPPORT: "Поддержка",
    MODERATOR: "Модератор",
    CONTENT: "Контент",
    ECONOMY: "Экономика",
    READ_ONLY: "Только чтение",
}

# --- Права ------------------------------------------------------------------
# Просмотр
PERM_PLAYERS_VIEW = "players.view"
PERM_CATALOG_VIEW = "catalog.view"
PERM_ECONOMY_VIEW = "economy.view"
PERM_PROMOS_VIEW = "promos.view"
PERM_MODERATION_VIEW = "moderation.view"
PERM_AUDIT_VIEW = "audit.view"
PERM_SYSTEM_VIEW = "system.view"
PERM_BACKUP_VIEW = "backup.view"
# Игроки / поддержка
PERM_PLAYERS_DELETE = "players.delete"
PERM_PLAYERS_RESET = "players.reset"
PERM_PLAYERS_UNSTUCK = "players.unstuck"
PERM_PLAYERS_MESSAGE = "players.message"
PERM_BACKUP_RESTORE = "backup.restore"
# Награды / экономика игрока
PERM_REWARDS_GRANT = "rewards.grant"
PERM_REWARDS_REMOVE = "rewards.remove"
PERM_REWARDS_BULK = "rewards.bulk_grant"
PERM_CURRENCY_CHANGE = "currency.change"
PERM_INVENTORY_EDIT = "inventory.edit"
# Модерация
PERM_MOD_WARN = "moderation.warn"
PERM_MOD_MUTE = "moderation.mute"
PERM_MOD_BAN = "moderation.ban"
PERM_FINES_MANAGE = "fines.manage"
# Экономика мира
PERM_ECONOMY_MANAGE = "economy.manage"
# Контент
PERM_CONTENT_EDIT = "content.edit"
PERM_ASSETS_MANAGE = "assets.manage"
# Промокоды / рассылки
PERM_PROMOS_MANAGE = "promos.manage"
PERM_BROADCAST_SEND = "broadcast.send"
# Система
PERM_SYSTEM_MANAGE = "system.manage"
PERM_ROLES_MANAGE = "roles.manage"
# Конструктор мира (data-driven контент: локации/мобы/дроп/события/NPC/квесты/рейды)
# — единый жизненный цикл черновик→проверка→публикация→архив, права по этапам.
PERM_WORLD_VIEW = "world.view"
PERM_WORLD_CREATE_DRAFT = "world.create_draft"
PERM_WORLD_EDIT_DRAFT = "world.edit_draft"
PERM_WORLD_VALIDATE = "world.validate"
PERM_WORLD_PUBLISH = "world.publish"
PERM_WORLD_DISABLE = "world.disable"
PERM_WORLD_ARCHIVE = "world.archive"
PERM_WORLD_TEST_RUN = "world.test_run"
# Расширенный конструктор локаций (ТЗ §60): отдельные права на под-системы
# локации, которых нет в базовом world.* — ресурсы/добыча/мобы локации/зоны/
# недельные ротации/недельные лимиты/привязки. Базовый цикл локаций/кнопок/
# событий/переходов по-прежнему гейтится world.* (без дублирования).
PERM_LOCATION_RESOURCES_VIEW = "location_resources.view"
PERM_LOCATION_RESOURCES_EDIT = "location_resources.edit"
PERM_LOCATION_LOOT_VIEW = "location_loot.view"
PERM_LOCATION_LOOT_EDIT = "location_loot.edit"
PERM_LOCATION_MOBS_VIEW = "location_mobs.view"
PERM_LOCATION_MOBS_EDIT = "location_mobs.edit"
PERM_LOCATION_ZONES_VIEW = "location_zones.view"
PERM_LOCATION_ZONES_EDIT = "location_zones.edit"
PERM_LOCATION_ROTATION_VIEW = "location_rotation.view"
PERM_LOCATION_ROTATION_EDIT = "location_rotation.edit"
PERM_LOCATION_ROTATION_FORCE_UPDATE = "location_rotation.force_update"
PERM_LOCATION_LIMITS_VIEW = "location_limits.view"
PERM_LOCATION_LIMITS_EDIT = "location_limits.edit"
PERM_LOCATION_LIMITS_FORCE_RESTORE = "location_limits.force_restore"
PERM_LOCATION_LIMITS_FORCE_DEPLETE = "location_limits.force_deplete"
PERM_LOCATION_LINKS_EDIT = "location_links.edit"
# Конструктор мобов (ТЗ «Конструктор мобов» §33). Базовый цикл моба гейтится
# world.* (как у локаций); mob.* — granular-слой для под-систем/баланса/боя.
PERM_MOB_VIEW = "mob.view"
PERM_MOB_CREATE = "mob.create"
PERM_MOB_EDIT = "mob.edit"
PERM_MOB_PUBLISH = "mob.publish"
PERM_MOB_DISABLE = "mob.disable"
PERM_MOB_ARCHIVE = "mob.archive"
PERM_MOB_DELETE_SOFT = "mob.delete_soft"
PERM_MOB_RESTORE = "mob.restore"
PERM_MOB_CHANGE_IMAGE = "mob.change_image"
PERM_MOB_CHANGE_STATS = "mob.change_stats"
PERM_MOB_CHANGE_SKILLS = "mob.change_skills"
PERM_MOB_CHANGE_LOOT = "mob.change_loot"
PERM_MOB_CHANGE_LOCATIONS = "mob.change_locations"
PERM_MOB_CHANGE_EVENTS = "mob.change_events"
PERM_MOB_CHANGE_SPAWN_CHANCE = "mob.change_spawn_chance"
PERM_MOB_CHANGE_WEEKLY_LIMITS = "mob.change_weekly_limits"
PERM_MOB_TEST_BATTLE = "mob.test_battle"
PERM_MOB_VIEW_BALANCE = "mob.view_balance"
PERM_MOB_AUDIT = "mob.audit"
# Конструктор штрафов (ТЗ «Конструктор штрафов») — авторинг ТИПОВ штрафов.
# Снятие/выдача штрафов игрокам остаётся на fines.manage (рантайм-система).
PERM_FINE_DEF_VIEW = "fine_def.view"
PERM_FINE_DEF_CREATE = "fine_def.create"
PERM_FINE_DEF_EDIT = "fine_def.edit"
PERM_FINE_DEF_VALIDATE = "fine_def.validate"
PERM_FINE_DEF_PUBLISH = "fine_def.publish"
PERM_FINE_DEF_DISABLE = "fine_def.disable"
PERM_FINE_DEF_ARCHIVE = "fine_def.archive"
PERM_FINE_DEF_DELETE = "fine_def.delete"
# Конструктор навыков (ТЗ §7) — авторинг ОПРЕДЕЛЕНИЙ навыков/умений.
# Рантайм навыков игрока (выбор у Распорядительного камня, расход ресурса)
# остаётся на active_skill_service — здесь только шаблоны.
PERM_SKILL_DEF_VIEW = "skill_def.view"
PERM_SKILL_DEF_CREATE = "skill_def.create"
PERM_SKILL_DEF_EDIT = "skill_def.edit"
PERM_SKILL_DEF_VALIDATE = "skill_def.validate"
PERM_SKILL_DEF_PUBLISH = "skill_def.publish"
PERM_SKILL_DEF_DISABLE = "skill_def.disable"
PERM_SKILL_DEF_ARCHIVE = "skill_def.archive"
PERM_SKILL_DEF_DELETE = "skill_def.delete"
# Конструктор ремесла (ТЗ «импорт ремесла») — рецепты/мастерские/алхимия/чертежи.
PERM_RECIPE_VIEW = "recipe.view"
PERM_RECIPE_CREATE = "recipe.create"
PERM_RECIPE_EDIT = "recipe.edit"
PERM_RECIPE_VALIDATE = "recipe.validate"
PERM_RECIPE_PUBLISH = "recipe.publish"
PERM_RECIPE_DISABLE = "recipe.disable"
PERM_RECIPE_ARCHIVE = "recipe.archive"
PERM_RECIPE_DELETE = "recipe.delete"
# Конструктор лагеря (доп. ТЗ §4) — отдых/восстановление/события лагеря.
PERM_CAMP_VIEW = "camp.view"
PERM_CAMP_CREATE = "camp.create"
PERM_CAMP_EDIT = "camp.edit"
PERM_CAMP_VALIDATE = "camp.validate"
PERM_CAMP_PUBLISH = "camp.publish"
PERM_CAMP_DISABLE = "camp.disable"
PERM_CAMP_ARCHIVE = "camp.archive"
PERM_CAMP_DELETE = "camp.delete"
# Конструкторы черт/благословений/фаз мобов (ТЗ «черты/благословения/фазы»).
PERM_TRAIT_VIEW = "trait.view"
PERM_TRAIT_CREATE = "trait.create"
PERM_TRAIT_EDIT = "trait.edit"
PERM_TRAIT_VALIDATE = "trait.validate"
PERM_TRAIT_PUBLISH = "trait.publish"
PERM_TRAIT_DISABLE = "trait.disable"
PERM_TRAIT_ARCHIVE = "trait.archive"
PERM_TRAIT_DELETE = "trait.delete"
PERM_BLESSING_VIEW = "blessing.view"
PERM_BLESSING_CREATE = "blessing.create"
PERM_BLESSING_EDIT = "blessing.edit"
PERM_BLESSING_VALIDATE = "blessing.validate"
PERM_BLESSING_PUBLISH = "blessing.publish"
PERM_BLESSING_DISABLE = "blessing.disable"
PERM_BLESSING_ARCHIVE = "blessing.archive"
PERM_BLESSING_DELETE = "blessing.delete"
PERM_PHASE_VIEW = "phase.view"
PERM_PHASE_CREATE = "phase.create"
PERM_PHASE_EDIT = "phase.edit"
PERM_PHASE_VALIDATE = "phase.validate"
PERM_PHASE_PUBLISH = "phase.publish"
PERM_PHASE_DISABLE = "phase.disable"
PERM_PHASE_ARCHIVE = "phase.archive"
PERM_PHASE_DELETE = "phase.delete"
# Конструкторы уровней/опыта/регистрации/рас (чат-ТЗ «уровни/опыт/регистрация/расы»).
PERM_LEVEL_VIEW = "level.view"
PERM_LEVEL_CREATE = "level.create"
PERM_LEVEL_EDIT = "level.edit"
PERM_LEVEL_VALIDATE = "level.validate"
PERM_LEVEL_PUBLISH = "level.publish"
PERM_LEVEL_DISABLE = "level.disable"
PERM_LEVEL_ARCHIVE = "level.archive"
PERM_LEVEL_DELETE = "level.delete"
PERM_EXP_VIEW = "exp.view"
PERM_EXP_CREATE = "exp.create"
PERM_EXP_EDIT = "exp.edit"
PERM_EXP_VALIDATE = "exp.validate"
PERM_EXP_PUBLISH = "exp.publish"
PERM_EXP_DISABLE = "exp.disable"
PERM_EXP_ARCHIVE = "exp.archive"
PERM_EXP_DELETE = "exp.delete"
PERM_REGISTRATION_VIEW = "registration.view"
PERM_REGISTRATION_CREATE = "registration.create"
PERM_REGISTRATION_EDIT = "registration.edit"
PERM_REGISTRATION_VALIDATE = "registration.validate"
PERM_REGISTRATION_PUBLISH = "registration.publish"
PERM_REGISTRATION_DISABLE = "registration.disable"
PERM_REGISTRATION_ARCHIVE = "registration.archive"
PERM_REGISTRATION_DELETE = "registration.delete"
PERM_RACE_VIEW = "race.view"
PERM_RACE_CREATE = "race.create"
PERM_RACE_EDIT = "race.edit"
PERM_RACE_VALIDATE = "race.validate"
PERM_RACE_PUBLISH = "race.publish"
PERM_RACE_DISABLE = "race.disable"
PERM_RACE_ARCHIVE = "race.archive"
PERM_RACE_DELETE = "race.delete"
# Конструктор города и крепости (ТЗ §4) — узлы/кнопки/товары/сервисы/криминал.
# Город и крепость редактируются как система узлов (узел = точка структуры).
PERM_CITY_VIEW = "city.view"
PERM_CITY_CREATE = "city.create"
PERM_CITY_EDIT = "city.edit"
PERM_CITY_PUBLISH = "city.publish"
PERM_CITY_DISABLE = "city.disable"
PERM_CITY_ARCHIVE = "city.archive"
PERM_CITY_DELETE = "city.delete"
# Гильдии
PERM_GUILD_VIEW = "guild.view"
PERM_GUILD_CREATE = "guild.create"
PERM_GUILD_EDIT = "guild.edit"
PERM_GUILD_DISABLE = "guild.disable"
PERM_GUILD_MANAGE_MEMBERS = "guild.manage_members"
PERM_GUILD_MANAGE_STORAGE = "guild.manage_storage"
PERM_GUILD_MANAGE_TREASURY = "guild.manage_treasury"
PERM_GUILD_AUDIT = "guild.audit"
# Мировые события / праздники / мировые боссы
PERM_WORLD_EVENT_VIEW = "world_event.view"
PERM_WORLD_EVENT_CREATE = "world_event.create"
PERM_WORLD_EVENT_EDIT = "world_event.edit"
PERM_WORLD_EVENT_SCHEDULE = "world_event.schedule"
PERM_WORLD_EVENT_START = "world_event.start"
PERM_WORLD_EVENT_STOP = "world_event.stop"
PERM_WORLD_EVENT_REWARD = "world_event.reward"
PERM_WORLD_EVENT_ARCHIVE = "world_event.archive"
PERM_WORLD_EVENT_AUDIT = "world_event.audit"
# Достижения
PERM_ACHIEVEMENT_VIEW = "achievement.view"
PERM_ACHIEVEMENT_CREATE = "achievement.create"
PERM_ACHIEVEMENT_EDIT = "achievement.edit"
PERM_ACHIEVEMENT_VALIDATE = "achievement.validate"
PERM_ACHIEVEMENT_PUBLISH = "achievement.publish"
PERM_ACHIEVEMENT_DISABLE = "achievement.disable"
PERM_ACHIEVEMENT_ARCHIVE = "achievement.archive"
PERM_ACHIEVEMENT_GRANT_MANUAL = "achievement.grant_manual"
PERM_ACHIEVEMENT_REVOKE_MANUAL = "achievement.revoke_manual"
PERM_ACHIEVEMENT_VIEW_HIDDEN = "achievement.view_hidden"
PERM_ACHIEVEMENT_VIEW_PLAYER_PROGRESS = "achievement.view_player_progress"
PERM_ACHIEVEMENT_MANAGE_CATEGORIES = "achievement.manage_categories"
PERM_ACHIEVEMENT_MANAGE_REWARDS = "achievement.manage_rewards"
PERM_ACHIEVEMENT_AUDIT = "achievement.audit"
# Очередь сообщений / доставка
PERM_MESSAGES_VIEW_QUEUE = "messages.view_queue"
PERM_MESSAGES_VIEW_PLAYER = "messages.view_player_messages"
PERM_MESSAGES_SEND_DIRECT = "messages.send_direct"
PERM_MESSAGES_SEND_BROADCAST = "messages.send_broadcast"
PERM_MESSAGES_RETRY = "messages.retry"
PERM_MESSAGES_CANCEL = "messages.cancel"
PERM_MESSAGES_VIEW_ERRORS = "messages.view_errors"
PERM_MESSAGES_MANAGE_DISPATCHER = "messages.manage_dispatcher"
PERM_MESSAGES_AUDIT = "messages.audit"
# Конструктор предметов
PERM_ITEM_VIEW = "item.view"
PERM_ITEM_CREATE = "item.create"
PERM_ITEM_EDIT = "item.edit"
PERM_ITEM_EDIT_PUBLISHED = "item.edit_published"
PERM_ITEM_VALIDATE = "item.validate"
PERM_ITEM_PUBLISH = "item.publish"
PERM_ITEM_DISABLE = "item.disable"
PERM_ITEM_ARCHIVE = "item.archive"
PERM_ITEM_DELETE_SOFT = "item.delete_soft"
PERM_ITEM_DELETE_HARD = "item.delete_hard"
PERM_ITEM_RESTORE = "item.restore"
PERM_ITEM_CHANGE_IMAGE = "item.change_image"
PERM_ITEM_CHANGE_PRICE = "item.change_price"
PERM_ITEM_CHANGE_EFFECTS = "item.change_effects"
PERM_ITEM_MASS_EDIT = "item.mass_edit"
PERM_ITEM_VIEW_TECHNICAL = "item.view_technical"
PERM_ITEM_VIEW_USAGE = "item.view_usage"
PERM_ITEM_AUDIT = "item.audit"
# Конструктор эффектов / зон / проклятий
PERM_EFFECT_VIEW = "effect.view"
PERM_EFFECT_CREATE = "effect.create"
PERM_EFFECT_EDIT = "effect.edit"
PERM_EFFECT_VALIDATE = "effect.validate"
PERM_EFFECT_PUBLISH = "effect.publish"
PERM_EFFECT_DISABLE = "effect.disable"
PERM_EFFECT_ARCHIVE = "effect.archive"
PERM_EFFECT_DELETE = "effect.delete"
PERM_EFFECT_AUDIT = "effect.audit"
# Конструктор сайта (профиль/павильон/новости/гайды/FAQ/рейтинги/настройки)
PERM_SITE_VIEW = "site.view"
PERM_SITE_SETTINGS_EDIT = "site.settings_edit"
PERM_SITE_MENU_EDIT = "site.menu_edit"
PERM_SITE_HOMEPAGE_EDIT = "site.homepage_edit"
PERM_PROFILE_LAYOUT_VIEW = "profile_layout.view"
PERM_PROFILE_LAYOUT_EDIT = "profile_layout.edit"
PERM_PROFILE_LAYOUT_PUBLISH = "profile_layout.publish"
PERM_PAVILION_VIEW = "pavilion.view"
PERM_PAVILION_MANAGE = "pavilion.manage"
PERM_PAVILION_MODERATE = "pavilion.moderate"
PERM_PAVILION_BLOCK = "pavilion.block"
PERM_PAVILION_AUDIT = "pavilion.audit"
PERM_NEWS_VIEW = "news.view"
PERM_NEWS_CREATE = "news.create"
PERM_NEWS_EDIT = "news.edit"
PERM_NEWS_PUBLISH = "news.publish"
PERM_NEWS_ARCHIVE = "news.archive"
PERM_GUIDES_VIEW = "guides.view"
PERM_GUIDES_CREATE = "guides.create"
PERM_GUIDES_EDIT = "guides.edit"
PERM_GUIDES_PUBLISH = "guides.publish"
PERM_GUIDES_ARCHIVE = "guides.archive"
PERM_FAQ_VIEW = "faq.view"
PERM_FAQ_CREATE = "faq.create"
PERM_FAQ_EDIT = "faq.edit"
PERM_FAQ_PUBLISH = "faq.publish"
PERM_RATINGS_VIEW = "ratings.view"
PERM_RATINGS_CREATE = "ratings.create"
PERM_RATINGS_EDIT = "ratings.edit"
PERM_RATINGS_PUBLISH = "ratings.publish"
PERM_RATINGS_REWARD = "ratings.reward"
PERM_SITE_ASSETS_UPLOAD = "site_assets.upload"
PERM_SITE_ASSETS_EDIT = "site_assets.edit"
PERM_SITE_AUDIT_VIEW = "site_audit.view"
# Интерактивная схема / карта связей (ТЗ 12) — единый граф всех сущностей.
# Read-only агрегатор: достаточно одной просмотровой привилегии.
PERM_GRAPH_VIEW = "graph.view"
PERM_GRAPH_EDIT = "graph.edit"  # редактирование связей на схеме (ТЗ 12 §34)
# Конструктор формул (ТЗ 13 §2) — игровые формулы без правки кода.
PERM_FORMULA_VIEW = "formula.view"
PERM_FORMULA_CREATE = "formula.create"
PERM_FORMULA_EDIT = "formula.edit"
PERM_FORMULA_VALIDATE = "formula.validate"
PERM_FORMULA_PUBLISH = "formula.publish"
PERM_FORMULA_DISABLE = "formula.disable"
PERM_FORMULA_ARCHIVE = "formula.archive"
PERM_FORMULA_DELETE = "formula.delete"
# Расширенное ремесло (ТЗ 13 §5): профессии и мастерские.
PERM_PROFESSION_VIEW = "profession.view"
PERM_PROFESSION_CREATE = "profession.create"
PERM_PROFESSION_EDIT = "profession.edit"
PERM_PROFESSION_VALIDATE = "profession.validate"
PERM_PROFESSION_PUBLISH = "profession.publish"
PERM_PROFESSION_DISABLE = "profession.disable"
PERM_PROFESSION_ARCHIVE = "profession.archive"
PERM_PROFESSION_DELETE = "profession.delete"
PERM_WORKSHOP_VIEW = "workshop.view"
PERM_WORKSHOP_CREATE = "workshop.create"
PERM_WORKSHOP_EDIT = "workshop.edit"
PERM_WORKSHOP_VALIDATE = "workshop.validate"
PERM_WORKSHOP_PUBLISH = "workshop.publish"
PERM_WORKSHOP_DISABLE = "workshop.disable"
PERM_WORKSHOP_ARCHIVE = "workshop.archive"
PERM_WORKSHOP_DELETE = "workshop.delete"
# Сообщения мастерских (ТЗ 14) — шаблоны отображения списков.
PERM_WORKSHOP_MSG_VIEW = "workshop_message.view"
PERM_WORKSHOP_MSG_CREATE = "workshop_message.create"
PERM_WORKSHOP_MSG_EDIT = "workshop_message.edit"
PERM_WORKSHOP_MSG_VALIDATE = "workshop_message.validate"
PERM_WORKSHOP_MSG_PUBLISH = "workshop_message.publish"
PERM_WORKSHOP_MSG_DISABLE = "workshop_message.disable"
PERM_WORKSHOP_MSG_ARCHIVE = "workshop_message.archive"
PERM_WORKSHOP_MSG_DELETE = "workshop_message.delete"
# Конструктор репутации (item-reputation §3 / эффекты §3).
PERM_REPUTATION_VIEW = "reputation.view"
PERM_REPUTATION_CREATE = "reputation.create"
PERM_REPUTATION_EDIT = "reputation.edit"
PERM_REPUTATION_VALIDATE = "reputation.validate"
PERM_REPUTATION_PUBLISH = "reputation.publish"
PERM_REPUTATION_DISABLE = "reputation.disable"
PERM_REPUTATION_ARCHIVE = "reputation.archive"
PERM_REPUTATION_DELETE = "reputation.delete"
# Конструктор таверны (ТЗ таверны).
PERM_TAVERN_VIEW = "tavern.view"
PERM_TAVERN_CREATE = "tavern.create"
PERM_TAVERN_EDIT = "tavern.edit"
PERM_TAVERN_VALIDATE = "tavern.validate"
PERM_TAVERN_PUBLISH = "tavern.publish"
PERM_TAVERN_DISABLE = "tavern.disable"
PERM_TAVERN_ARCHIVE = "tavern.archive"
PERM_TAVERN_DELETE = "tavern.delete"
# Конструктор текстов бота (full-import ТЗ §5.18).
PERM_TEXT_VIEW = "text.view"
PERM_TEXT_CREATE = "text.create"
PERM_TEXT_EDIT = "text.edit"
PERM_TEXT_VALIDATE = "text.validate"
PERM_TEXT_PUBLISH = "text.publish"
PERM_TEXT_DISABLE = "text.disable"
PERM_TEXT_ARCHIVE = "text.archive"
PERM_TEXT_DELETE = "text.delete"
# Конструктор будущего PVP (ТЗ 4 §1).
PERM_PVP_VIEW = "pvp.view"
PERM_PVP_CREATE = "pvp.create"
PERM_PVP_EDIT = "pvp.edit"
PERM_PVP_VALIDATE = "pvp.validate"
PERM_PVP_PUBLISH = "pvp.publish"
PERM_PVP_DISABLE = "pvp.disable"
PERM_PVP_ARCHIVE = "pvp.archive"
PERM_PVP_DELETE = "pvp.delete"

ALL_PERMISSIONS = (
    PERM_PLAYERS_VIEW, PERM_CATALOG_VIEW, PERM_ECONOMY_VIEW, PERM_PROMOS_VIEW,
    PERM_MODERATION_VIEW, PERM_AUDIT_VIEW, PERM_SYSTEM_VIEW, PERM_BACKUP_VIEW,
    PERM_PLAYERS_DELETE, PERM_PLAYERS_RESET, PERM_PLAYERS_UNSTUCK,
    PERM_PLAYERS_MESSAGE, PERM_BACKUP_RESTORE,
    PERM_REWARDS_GRANT, PERM_REWARDS_REMOVE, PERM_REWARDS_BULK,
    PERM_CURRENCY_CHANGE, PERM_INVENTORY_EDIT,
    PERM_MOD_WARN, PERM_MOD_MUTE, PERM_MOD_BAN, PERM_FINES_MANAGE,
    PERM_ECONOMY_MANAGE, PERM_CONTENT_EDIT, PERM_ASSETS_MANAGE,
    PERM_PROMOS_MANAGE, PERM_BROADCAST_SEND,
    PERM_SYSTEM_MANAGE, PERM_ROLES_MANAGE,
    PERM_WORLD_VIEW, PERM_WORLD_CREATE_DRAFT, PERM_WORLD_EDIT_DRAFT,
    PERM_WORLD_VALIDATE, PERM_WORLD_PUBLISH, PERM_WORLD_DISABLE,
    PERM_WORLD_ARCHIVE, PERM_WORLD_TEST_RUN,
    PERM_LOCATION_RESOURCES_VIEW, PERM_LOCATION_RESOURCES_EDIT,
    PERM_LOCATION_LOOT_VIEW, PERM_LOCATION_LOOT_EDIT,
    PERM_LOCATION_MOBS_VIEW, PERM_LOCATION_MOBS_EDIT,
    PERM_LOCATION_ZONES_VIEW, PERM_LOCATION_ZONES_EDIT,
    PERM_LOCATION_ROTATION_VIEW, PERM_LOCATION_ROTATION_EDIT,
    PERM_LOCATION_ROTATION_FORCE_UPDATE,
    PERM_LOCATION_LIMITS_VIEW, PERM_LOCATION_LIMITS_EDIT,
    PERM_LOCATION_LIMITS_FORCE_RESTORE, PERM_LOCATION_LIMITS_FORCE_DEPLETE,
    PERM_LOCATION_LINKS_EDIT,
    PERM_MOB_VIEW, PERM_MOB_CREATE, PERM_MOB_EDIT, PERM_MOB_PUBLISH,
    PERM_MOB_DISABLE, PERM_MOB_ARCHIVE, PERM_MOB_DELETE_SOFT, PERM_MOB_RESTORE,
    PERM_MOB_CHANGE_IMAGE, PERM_MOB_CHANGE_STATS, PERM_MOB_CHANGE_SKILLS,
    PERM_MOB_CHANGE_LOOT, PERM_MOB_CHANGE_LOCATIONS, PERM_MOB_CHANGE_EVENTS,
    PERM_MOB_CHANGE_SPAWN_CHANCE, PERM_MOB_CHANGE_WEEKLY_LIMITS,
    PERM_MOB_TEST_BATTLE, PERM_MOB_VIEW_BALANCE, PERM_MOB_AUDIT,
    PERM_FINE_DEF_VIEW, PERM_FINE_DEF_CREATE, PERM_FINE_DEF_EDIT,
    PERM_FINE_DEF_VALIDATE, PERM_FINE_DEF_PUBLISH, PERM_FINE_DEF_DISABLE,
    PERM_FINE_DEF_ARCHIVE, PERM_FINE_DEF_DELETE,
    PERM_SKILL_DEF_VIEW, PERM_SKILL_DEF_CREATE, PERM_SKILL_DEF_EDIT,
    PERM_SKILL_DEF_VALIDATE, PERM_SKILL_DEF_PUBLISH, PERM_SKILL_DEF_DISABLE,
    PERM_SKILL_DEF_ARCHIVE, PERM_SKILL_DEF_DELETE,
    PERM_CITY_VIEW, PERM_CITY_CREATE, PERM_CITY_EDIT, PERM_CITY_PUBLISH,
    PERM_CITY_DISABLE, PERM_CITY_ARCHIVE, PERM_CITY_DELETE,
    PERM_RECIPE_VIEW, PERM_RECIPE_CREATE, PERM_RECIPE_EDIT, PERM_RECIPE_VALIDATE,
    PERM_RECIPE_PUBLISH, PERM_RECIPE_DISABLE, PERM_RECIPE_ARCHIVE, PERM_RECIPE_DELETE,
    PERM_CAMP_VIEW, PERM_CAMP_CREATE, PERM_CAMP_EDIT, PERM_CAMP_VALIDATE,
    PERM_CAMP_PUBLISH, PERM_CAMP_DISABLE, PERM_CAMP_ARCHIVE, PERM_CAMP_DELETE,
    PERM_TRAIT_VIEW, PERM_TRAIT_CREATE, PERM_TRAIT_EDIT, PERM_TRAIT_VALIDATE,
    PERM_TRAIT_PUBLISH, PERM_TRAIT_DISABLE, PERM_TRAIT_ARCHIVE, PERM_TRAIT_DELETE,
    PERM_BLESSING_VIEW, PERM_BLESSING_CREATE, PERM_BLESSING_EDIT, PERM_BLESSING_VALIDATE,
    PERM_BLESSING_PUBLISH, PERM_BLESSING_DISABLE, PERM_BLESSING_ARCHIVE, PERM_BLESSING_DELETE,
    PERM_PHASE_VIEW, PERM_PHASE_CREATE, PERM_PHASE_EDIT, PERM_PHASE_VALIDATE,
    PERM_PHASE_PUBLISH, PERM_PHASE_DISABLE, PERM_PHASE_ARCHIVE, PERM_PHASE_DELETE,
    PERM_LEVEL_VIEW, PERM_LEVEL_CREATE, PERM_LEVEL_EDIT, PERM_LEVEL_VALIDATE,
    PERM_LEVEL_PUBLISH, PERM_LEVEL_DISABLE, PERM_LEVEL_ARCHIVE, PERM_LEVEL_DELETE,
    PERM_EXP_VIEW, PERM_EXP_CREATE, PERM_EXP_EDIT, PERM_EXP_VALIDATE,
    PERM_EXP_PUBLISH, PERM_EXP_DISABLE, PERM_EXP_ARCHIVE, PERM_EXP_DELETE,
    PERM_REGISTRATION_VIEW, PERM_REGISTRATION_CREATE, PERM_REGISTRATION_EDIT, PERM_REGISTRATION_VALIDATE,
    PERM_REGISTRATION_PUBLISH, PERM_REGISTRATION_DISABLE, PERM_REGISTRATION_ARCHIVE, PERM_REGISTRATION_DELETE,
    PERM_RACE_VIEW, PERM_RACE_CREATE, PERM_RACE_EDIT, PERM_RACE_VALIDATE,
    PERM_RACE_PUBLISH, PERM_RACE_DISABLE, PERM_RACE_ARCHIVE, PERM_RACE_DELETE,
    PERM_GUILD_VIEW, PERM_GUILD_CREATE, PERM_GUILD_EDIT, PERM_GUILD_DISABLE,
    PERM_GUILD_MANAGE_MEMBERS, PERM_GUILD_MANAGE_STORAGE,
    PERM_GUILD_MANAGE_TREASURY, PERM_GUILD_AUDIT,
    PERM_WORLD_EVENT_VIEW, PERM_WORLD_EVENT_CREATE, PERM_WORLD_EVENT_EDIT,
    PERM_WORLD_EVENT_SCHEDULE, PERM_WORLD_EVENT_START, PERM_WORLD_EVENT_STOP,
    PERM_WORLD_EVENT_REWARD, PERM_WORLD_EVENT_ARCHIVE, PERM_WORLD_EVENT_AUDIT,
    PERM_ACHIEVEMENT_VIEW, PERM_ACHIEVEMENT_CREATE, PERM_ACHIEVEMENT_EDIT,
    PERM_ACHIEVEMENT_VALIDATE, PERM_ACHIEVEMENT_PUBLISH, PERM_ACHIEVEMENT_DISABLE,
    PERM_ACHIEVEMENT_ARCHIVE, PERM_ACHIEVEMENT_GRANT_MANUAL,
    PERM_ACHIEVEMENT_REVOKE_MANUAL, PERM_ACHIEVEMENT_VIEW_HIDDEN,
    PERM_ACHIEVEMENT_VIEW_PLAYER_PROGRESS, PERM_ACHIEVEMENT_MANAGE_CATEGORIES,
    PERM_ACHIEVEMENT_MANAGE_REWARDS, PERM_ACHIEVEMENT_AUDIT,
    PERM_MESSAGES_VIEW_QUEUE, PERM_MESSAGES_VIEW_PLAYER,
    PERM_MESSAGES_SEND_DIRECT, PERM_MESSAGES_SEND_BROADCAST,
    PERM_MESSAGES_RETRY, PERM_MESSAGES_CANCEL, PERM_MESSAGES_VIEW_ERRORS,
    PERM_MESSAGES_MANAGE_DISPATCHER, PERM_MESSAGES_AUDIT,
    PERM_ITEM_VIEW, PERM_ITEM_CREATE, PERM_ITEM_EDIT, PERM_ITEM_EDIT_PUBLISHED,
    PERM_ITEM_VALIDATE, PERM_ITEM_PUBLISH, PERM_ITEM_DISABLE, PERM_ITEM_ARCHIVE,
    PERM_ITEM_DELETE_SOFT, PERM_ITEM_DELETE_HARD, PERM_ITEM_RESTORE,
    PERM_ITEM_CHANGE_IMAGE, PERM_ITEM_CHANGE_PRICE, PERM_ITEM_CHANGE_EFFECTS,
    PERM_ITEM_MASS_EDIT, PERM_ITEM_VIEW_TECHNICAL, PERM_ITEM_VIEW_USAGE,
    PERM_ITEM_AUDIT,
    PERM_EFFECT_VIEW, PERM_EFFECT_CREATE, PERM_EFFECT_EDIT, PERM_EFFECT_VALIDATE,
    PERM_EFFECT_PUBLISH, PERM_EFFECT_DISABLE, PERM_EFFECT_ARCHIVE,
    PERM_EFFECT_DELETE, PERM_EFFECT_AUDIT,
    PERM_SITE_VIEW, PERM_SITE_SETTINGS_EDIT, PERM_SITE_MENU_EDIT,
    PERM_SITE_HOMEPAGE_EDIT, PERM_PROFILE_LAYOUT_VIEW, PERM_PROFILE_LAYOUT_EDIT,
    PERM_PROFILE_LAYOUT_PUBLISH, PERM_PAVILION_VIEW, PERM_PAVILION_MANAGE,
    PERM_PAVILION_MODERATE, PERM_PAVILION_BLOCK, PERM_PAVILION_AUDIT,
    PERM_NEWS_VIEW, PERM_NEWS_CREATE, PERM_NEWS_EDIT, PERM_NEWS_PUBLISH,
    PERM_NEWS_ARCHIVE, PERM_GUIDES_VIEW, PERM_GUIDES_CREATE, PERM_GUIDES_EDIT,
    PERM_GUIDES_PUBLISH, PERM_GUIDES_ARCHIVE, PERM_FAQ_VIEW, PERM_FAQ_CREATE,
    PERM_FAQ_EDIT, PERM_FAQ_PUBLISH, PERM_RATINGS_VIEW, PERM_RATINGS_CREATE,
    PERM_RATINGS_EDIT, PERM_RATINGS_PUBLISH, PERM_RATINGS_REWARD,
    PERM_SITE_ASSETS_UPLOAD, PERM_SITE_ASSETS_EDIT, PERM_SITE_AUDIT_VIEW,
    PERM_GRAPH_VIEW, PERM_GRAPH_EDIT,
    PERM_FORMULA_VIEW, PERM_FORMULA_CREATE, PERM_FORMULA_EDIT, PERM_FORMULA_VALIDATE,
    PERM_FORMULA_PUBLISH, PERM_FORMULA_DISABLE, PERM_FORMULA_ARCHIVE, PERM_FORMULA_DELETE,
    PERM_PROFESSION_VIEW, PERM_PROFESSION_CREATE, PERM_PROFESSION_EDIT, PERM_PROFESSION_VALIDATE,
    PERM_PROFESSION_PUBLISH, PERM_PROFESSION_DISABLE, PERM_PROFESSION_ARCHIVE, PERM_PROFESSION_DELETE,
    PERM_WORKSHOP_VIEW, PERM_WORKSHOP_CREATE, PERM_WORKSHOP_EDIT, PERM_WORKSHOP_VALIDATE,
    PERM_WORKSHOP_PUBLISH, PERM_WORKSHOP_DISABLE, PERM_WORKSHOP_ARCHIVE, PERM_WORKSHOP_DELETE,
    PERM_WORKSHOP_MSG_VIEW, PERM_WORKSHOP_MSG_CREATE, PERM_WORKSHOP_MSG_EDIT, PERM_WORKSHOP_MSG_VALIDATE,
    PERM_WORKSHOP_MSG_PUBLISH, PERM_WORKSHOP_MSG_DISABLE, PERM_WORKSHOP_MSG_ARCHIVE, PERM_WORKSHOP_MSG_DELETE,
    PERM_REPUTATION_VIEW, PERM_REPUTATION_CREATE, PERM_REPUTATION_EDIT, PERM_REPUTATION_VALIDATE,
    PERM_REPUTATION_PUBLISH, PERM_REPUTATION_DISABLE, PERM_REPUTATION_ARCHIVE, PERM_REPUTATION_DELETE,
    PERM_TAVERN_VIEW, PERM_TAVERN_CREATE, PERM_TAVERN_EDIT, PERM_TAVERN_VALIDATE,
    PERM_TAVERN_PUBLISH, PERM_TAVERN_DISABLE, PERM_TAVERN_ARCHIVE, PERM_TAVERN_DELETE,
    PERM_TEXT_VIEW, PERM_TEXT_CREATE, PERM_TEXT_EDIT, PERM_TEXT_VALIDATE,
    PERM_TEXT_PUBLISH, PERM_TEXT_DISABLE, PERM_TEXT_ARCHIVE, PERM_TEXT_DELETE,
    PERM_PVP_VIEW, PERM_PVP_CREATE, PERM_PVP_EDIT, PERM_PVP_VALIDATE,
    PERM_PVP_PUBLISH, PERM_PVP_DISABLE, PERM_PVP_ARCHIVE, PERM_PVP_DELETE,
)

# Опасные действия — требуют двойного подтверждения на фронте и помечаются в
# аудите. Используется и эндпоинтами, и вьювером аудита (фильтр «опасные»).
DANGEROUS_ACTIONS = frozenset({
    "player.delete",
    "player.reset",
    "backup.restore",
    "rewards.bulk_grant",
    "rewards.bulk_remove",
    "currency.large_change",
    "promo.delete",
    "asset.image_change",
    "system.maintenance_on",
    "system.feature_flag",
    "roles.change",
    # Конструктор мира / события / гильдии — действия, меняющие живой мир.
    "world.publish",
    "world.disable",
    "world.archive",
    # Ручное вмешательство в недельную ротацию/лимиты локации (ТЗ §40, §60).
    "location_rotation.force_update",
    "location_limits.force_restore",
    "location_limits.force_deplete",
    # Конструктор мобов — действия, меняющие живой мир/баланс (ТЗ §33).
    "mob.publish",
    "mob.disable",
    "mob.archive",
    "mob.delete_soft",
    "mob.restore",
    "mob.change_loot",
    # Конструктор штрафов — публикация/отключение/архив/удаление типов штрафов.
    "fine_def.publish",
    "fine_def.disable",
    "fine_def.archive",
    "fine_def.delete",
    # Конструктор навыков — публикация/отключение/архив/удаление навыков.
    "skill_def.publish",
    "skill_def.disable",
    "skill_def.archive",
    "skill_def.delete",
    # Конструктор города/крепости — действия, меняющие живые узлы.
    "city.publish",
    "city.disable",
    "city.archive",
    "city.delete",
    # Конструктор ремесла — публикация/отключение/архив/удаление рецептов.
    "recipe.publish",
    "recipe.disable",
    "recipe.archive",
    "recipe.delete",
    # Конструктор лагеря — публикация/отключение/архив/удаление лагерей.
    "camp.publish",
    "camp.disable",
    "camp.archive",
    "camp.delete",
    # Импорт-миграция — массовая публикация существующего контента в конструкторы.
    "import.run",
    "import.rollback",
    "guild.disable",
    "world_event.start",
    "world_event.stop",
    "world_event.reward",
    "world_event.archive",
    "achievement.publish",
    "achievement.disable",
    "achievement.archive",
    "achievement.grant_manual",
    "achievement.revoke_manual",
    "item.publish",
    "item.disable",
    "item.archive",
    "item.delete_soft",
    "item.delete_hard",
    "item.restore",
    "item.change_image",
    "item.mass_edit",
    "effect.publish",
    "effect.disable",
    "effect.archive",
    "effect.delete",
    "news.publish",
    "news.archive",
    "guides.publish",
    "guides.archive",
    "faq.publish",
    "ratings.publish",
    "ratings.reward",
    "profile_layout.publish",
    "profile_layout.disable",
    "profile_layout.archive",
    "profile_layout.delete",
    "pavilion.block",
    "site.settings_edit",
})

# owner → все права (sentinel). Остальные роли — явные множества.
ROLE_PERMISSIONS: dict[str, set[str]] = {
    OWNER: {"*"},
    ADMIN: set(p for p in ALL_PERMISSIONS if p != PERM_ROLES_MANAGE),
    SUPPORT: {
        PERM_PLAYERS_VIEW, PERM_PLAYERS_UNSTUCK, PERM_PLAYERS_MESSAGE,
        PERM_REWARDS_GRANT, PERM_BACKUP_VIEW, PERM_AUDIT_VIEW,
        PERM_GUILD_VIEW, PERM_WORLD_EVENT_VIEW,
        PERM_ACHIEVEMENT_VIEW, PERM_ACHIEVEMENT_VIEW_PLAYER_PROGRESS,
        PERM_MESSAGES_VIEW_QUEUE, PERM_MESSAGES_VIEW_PLAYER,
        PERM_MESSAGES_SEND_DIRECT, PERM_MESSAGES_RETRY,
        PERM_ITEM_VIEW, PERM_EFFECT_VIEW, PERM_MOB_VIEW, PERM_SKILL_DEF_VIEW,
        PERM_SITE_VIEW, PERM_NEWS_VIEW, PERM_GUIDES_VIEW, PERM_FAQ_VIEW,
        PERM_RATINGS_VIEW, PERM_PAVILION_VIEW, PERM_PAVILION_MODERATE,
        PERM_GRAPH_VIEW,
    },
    MODERATOR: {
        PERM_PLAYERS_VIEW, PERM_MODERATION_VIEW,
        PERM_MOD_WARN, PERM_MOD_MUTE,
        PERM_GUILD_VIEW, PERM_GUILD_MANAGE_MEMBERS,
        PERM_ACHIEVEMENT_VIEW,
        PERM_MESSAGES_VIEW_PLAYER,
        PERM_ITEM_VIEW, PERM_EFFECT_VIEW, PERM_SKILL_DEF_VIEW,
    },
    # content создаёт и правит ЧЕРНОВИКИ мира/событий/гильдий/достижений, но не
    # публикует и не запускает (publish/start/disband → admin/owner).
    CONTENT: {
        PERM_CATALOG_VIEW, PERM_CONTENT_EDIT, PERM_ASSETS_MANAGE,
        PERM_WORLD_VIEW, PERM_WORLD_CREATE_DRAFT, PERM_WORLD_EDIT_DRAFT,
        PERM_WORLD_VALIDATE, PERM_WORLD_TEST_RUN,
        # Конструктор локаций: content ведёт под-системы (без force-вмешательства).
        PERM_LOCATION_RESOURCES_VIEW, PERM_LOCATION_RESOURCES_EDIT,
        PERM_LOCATION_LOOT_VIEW, PERM_LOCATION_LOOT_EDIT,
        PERM_LOCATION_MOBS_VIEW, PERM_LOCATION_MOBS_EDIT,
        PERM_LOCATION_ZONES_VIEW, PERM_LOCATION_ZONES_EDIT,
        PERM_LOCATION_ROTATION_VIEW, PERM_LOCATION_ROTATION_EDIT,
        PERM_LOCATION_LIMITS_VIEW, PERM_LOCATION_LIMITS_EDIT,
        PERM_LOCATION_LINKS_EDIT,
        # Конструктор мобов: content ведёт черновики (без публикации/баланса дропа).
        PERM_MOB_VIEW, PERM_MOB_CREATE, PERM_MOB_EDIT, PERM_MOB_CHANGE_IMAGE,
        PERM_MOB_CHANGE_STATS, PERM_MOB_CHANGE_SKILLS, PERM_MOB_CHANGE_LOCATIONS,
        PERM_MOB_CHANGE_EVENTS, PERM_MOB_CHANGE_SPAWN_CHANCE,
        PERM_MOB_TEST_BATTLE, PERM_MOB_VIEW_BALANCE,
        # Конструктор штрафов: content ведёт черновики (без публикации).
        PERM_FINE_DEF_VIEW, PERM_FINE_DEF_CREATE, PERM_FINE_DEF_EDIT, PERM_FINE_DEF_VALIDATE,
        # Конструктор навыков: content ведёт черновики (без публикации).
        PERM_SKILL_DEF_VIEW, PERM_SKILL_DEF_CREATE, PERM_SKILL_DEF_EDIT, PERM_SKILL_DEF_VALIDATE,
        # Конструктор города/крепости: content ведёт черновики узлов (без публикации).
        PERM_CITY_VIEW, PERM_CITY_CREATE, PERM_CITY_EDIT,
        # Конструктор ремесла: content ведёт черновики рецептов.
        PERM_RECIPE_VIEW, PERM_RECIPE_CREATE, PERM_RECIPE_EDIT, PERM_RECIPE_VALIDATE,
        # Конструктор лагеря: content ведёт черновики лагерей.
        PERM_CAMP_VIEW, PERM_CAMP_CREATE, PERM_CAMP_EDIT, PERM_CAMP_VALIDATE,
        PERM_TRAIT_VIEW, PERM_TRAIT_CREATE, PERM_TRAIT_EDIT, PERM_TRAIT_VALIDATE,
        PERM_BLESSING_VIEW, PERM_BLESSING_CREATE, PERM_BLESSING_EDIT, PERM_BLESSING_VALIDATE,
        PERM_PHASE_VIEW, PERM_PHASE_CREATE, PERM_PHASE_EDIT, PERM_PHASE_VALIDATE,
        PERM_LEVEL_VIEW, PERM_LEVEL_CREATE, PERM_LEVEL_EDIT, PERM_LEVEL_VALIDATE,
        PERM_EXP_VIEW, PERM_EXP_CREATE, PERM_EXP_EDIT, PERM_EXP_VALIDATE,
        PERM_REGISTRATION_VIEW, PERM_REGISTRATION_CREATE, PERM_REGISTRATION_EDIT, PERM_REGISTRATION_VALIDATE,
        PERM_RACE_VIEW, PERM_RACE_CREATE, PERM_RACE_EDIT, PERM_RACE_VALIDATE,
        PERM_GUILD_VIEW, PERM_GUILD_CREATE, PERM_GUILD_EDIT,
        PERM_WORLD_EVENT_VIEW, PERM_WORLD_EVENT_CREATE,
        PERM_WORLD_EVENT_EDIT, PERM_WORLD_EVENT_SCHEDULE,
        PERM_ACHIEVEMENT_VIEW, PERM_ACHIEVEMENT_CREATE, PERM_ACHIEVEMENT_EDIT,
        PERM_ACHIEVEMENT_VALIDATE, PERM_ACHIEVEMENT_VIEW_HIDDEN,
        PERM_ACHIEVEMENT_MANAGE_CATEGORIES, PERM_ACHIEVEMENT_MANAGE_REWARDS,
        PERM_ITEM_VIEW, PERM_ITEM_CREATE, PERM_ITEM_EDIT, PERM_ITEM_VALIDATE,
        PERM_ITEM_CHANGE_IMAGE, PERM_ITEM_CHANGE_PRICE, PERM_ITEM_CHANGE_EFFECTS,
        PERM_ITEM_VIEW_TECHNICAL, PERM_ITEM_VIEW_USAGE,
        PERM_EFFECT_VIEW, PERM_EFFECT_CREATE, PERM_EFFECT_EDIT, PERM_EFFECT_VALIDATE,
        # Конструктор сайта: content ведёт новости/гайды/FAQ и черновики (без публикации).
        PERM_SITE_VIEW, PERM_NEWS_VIEW, PERM_NEWS_CREATE, PERM_NEWS_EDIT,
        PERM_GUIDES_VIEW, PERM_GUIDES_CREATE, PERM_GUIDES_EDIT,
        PERM_FAQ_VIEW, PERM_FAQ_CREATE, PERM_FAQ_EDIT,
        PERM_RATINGS_VIEW, PERM_RATINGS_CREATE, PERM_RATINGS_EDIT,
        PERM_PROFILE_LAYOUT_VIEW, PERM_PROFILE_LAYOUT_EDIT,
        PERM_SITE_ASSETS_UPLOAD,
        PERM_GRAPH_VIEW, PERM_GRAPH_EDIT,
        PERM_FORMULA_VIEW, PERM_FORMULA_CREATE, PERM_FORMULA_EDIT, PERM_FORMULA_VALIDATE,
        PERM_PROFESSION_VIEW, PERM_PROFESSION_CREATE, PERM_PROFESSION_EDIT, PERM_PROFESSION_VALIDATE,
        PERM_WORKSHOP_VIEW, PERM_WORKSHOP_CREATE, PERM_WORKSHOP_EDIT, PERM_WORKSHOP_VALIDATE,
        PERM_WORKSHOP_MSG_VIEW, PERM_WORKSHOP_MSG_CREATE, PERM_WORKSHOP_MSG_EDIT, PERM_WORKSHOP_MSG_VALIDATE,
        PERM_REPUTATION_VIEW, PERM_REPUTATION_CREATE, PERM_REPUTATION_EDIT, PERM_REPUTATION_VALIDATE,
        PERM_TAVERN_VIEW, PERM_TAVERN_CREATE, PERM_TAVERN_EDIT, PERM_TAVERN_VALIDATE,
        PERM_TEXT_VIEW, PERM_TEXT_CREATE, PERM_TEXT_EDIT, PERM_TEXT_VALIDATE,
        PERM_PVP_VIEW, PERM_PVP_CREATE, PERM_PVP_EDIT, PERM_PVP_VALIDATE,
    },
    # economy подтверждает события с крупными наградами/множителями экономики.
    ECONOMY: {
        PERM_ECONOMY_VIEW, PERM_ECONOMY_MANAGE, PERM_CATALOG_VIEW,
        PERM_PROMOS_VIEW, PERM_AUDIT_VIEW,
        PERM_WORLD_EVENT_VIEW, PERM_WORLD_EVENT_REWARD, PERM_GUILD_VIEW,
        PERM_ACHIEVEMENT_VIEW,
        # Баланс локаций: economy крутит шансы/ресурсы/добычу/лимиты/ротации.
        PERM_WORLD_VIEW,
        PERM_LOCATION_RESOURCES_VIEW, PERM_LOCATION_RESOURCES_EDIT,
        PERM_LOCATION_LOOT_VIEW, PERM_LOCATION_LOOT_EDIT,
        PERM_LOCATION_MOBS_VIEW, PERM_LOCATION_MOBS_EDIT,
        PERM_LOCATION_ROTATION_VIEW, PERM_LOCATION_ROTATION_EDIT,
        PERM_LOCATION_LIMITS_VIEW, PERM_LOCATION_LIMITS_EDIT,
        PERM_LOCATION_ZONES_VIEW,
        # Баланс мобов: economy крутит дроп/недельный запас/шанс/опыт-монеты.
        PERM_MOB_VIEW, PERM_MOB_CHANGE_LOOT, PERM_MOB_CHANGE_WEEKLY_LIMITS,
        PERM_MOB_CHANGE_SPAWN_CHANCE, PERM_MOB_VIEW_BALANCE,
        # Баланс города: economy правит товары/цены/сервисы (узлы — без публикации).
        PERM_CITY_VIEW, PERM_CITY_EDIT,
        # Баланс ремесла: economy правит рецепты (шансы/время/ресурсы).
        PERM_RECIPE_VIEW, PERM_RECIPE_EDIT,
        PERM_FINE_DEF_VIEW,
        PERM_ITEM_VIEW, PERM_ITEM_CHANGE_PRICE, PERM_ITEM_VIEW_USAGE,
        PERM_EFFECT_VIEW,
        PERM_SITE_VIEW, PERM_RATINGS_VIEW, PERM_RATINGS_REWARD, PERM_NEWS_VIEW,
        PERM_GRAPH_VIEW,
    },
    READ_ONLY: {
        PERM_PLAYERS_VIEW, PERM_CATALOG_VIEW, PERM_ECONOMY_VIEW,
        PERM_PROMOS_VIEW, PERM_MODERATION_VIEW, PERM_AUDIT_VIEW,
        PERM_SYSTEM_VIEW, PERM_BACKUP_VIEW,
        PERM_WORLD_VIEW, PERM_GUILD_VIEW, PERM_WORLD_EVENT_VIEW,
        PERM_LOCATION_RESOURCES_VIEW, PERM_LOCATION_LOOT_VIEW,
        PERM_LOCATION_MOBS_VIEW, PERM_LOCATION_ZONES_VIEW,
        PERM_LOCATION_ROTATION_VIEW, PERM_LOCATION_LIMITS_VIEW,
        PERM_MOB_VIEW, PERM_MOB_VIEW_BALANCE, PERM_FINE_DEF_VIEW,
        PERM_SKILL_DEF_VIEW, PERM_CITY_VIEW, PERM_RECIPE_VIEW, PERM_CAMP_VIEW,
        PERM_TRAIT_VIEW, PERM_BLESSING_VIEW, PERM_PHASE_VIEW,
        PERM_LEVEL_VIEW, PERM_EXP_VIEW, PERM_REGISTRATION_VIEW, PERM_RACE_VIEW,
        PERM_ACHIEVEMENT_VIEW, PERM_MESSAGES_VIEW_QUEUE,
        PERM_ITEM_VIEW, PERM_ITEM_VIEW_USAGE, PERM_EFFECT_VIEW,
        PERM_SITE_VIEW, PERM_NEWS_VIEW, PERM_GUIDES_VIEW, PERM_FAQ_VIEW,
        PERM_RATINGS_VIEW, PERM_PROFILE_LAYOUT_VIEW, PERM_PAVILION_VIEW,
        PERM_SITE_AUDIT_VIEW,
        PERM_GRAPH_VIEW, PERM_FORMULA_VIEW, PERM_PROFESSION_VIEW, PERM_WORKSHOP_VIEW,
        PERM_WORKSHOP_MSG_VIEW, PERM_REPUTATION_VIEW, PERM_TAVERN_VIEW,
        PERM_TEXT_VIEW, PERM_PVP_VIEW,
    },
}


def normalize_role(role: Any) -> str:
    value = str(role or "").strip().casefold()
    return value if value in ROLES else DEFAULT_ROLE


def permissions_for(role: str) -> set[str]:
    role = normalize_role(role)
    perms = ROLE_PERMISSIONS.get(role, set())
    if "*" in perms:
        return set(ALL_PERMISSIONS)
    return set(perms)


def has_permission(role: str, permission: str) -> bool:
    role = normalize_role(role)
    perms = ROLE_PERMISSIONS.get(role, set())
    return "*" in perms or permission in perms


# --- Хранилище override'ов ролей (файл с блокировкой) -----------------------
_ROLES_LOCK = threading.Lock()


def roles_path() -> Path:
    override = os.getenv("ADMIN_ROLES_PATH")
    if override:
        return resolve_project_path(override)
    return project_path("data", "admin_roles.json")


def _load_roles() -> dict[str, str]:
    path = roles_path()
    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError):
        return {}
    if isinstance(data, dict):
        data = data.get("roles", data)
    if not isinstance(data, dict):
        return {}
    return {str(key): normalize_role(value) for key, value in data.items() if value}


def _save_roles(roles: dict[str, str]) -> None:
    path = roles_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as file:
        json.dump({"roles": roles}, file, ensure_ascii=False, indent=2)
    tmp_path.replace(path)


@contextmanager
def _roles_file_lock() -> Iterator[None]:
    if fcntl is None:
        yield
        return
    path = roles_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def identity_key(platform: Any, admin_user_id: Any) -> str:
    return f"{str(platform or '').strip().casefold()}:{str(admin_user_id or '').strip()}"


def get_role_overrides() -> dict[str, str]:
    with _ROLES_LOCK, _roles_file_lock():
        return _load_roles()


def set_role_override(platform: Any, admin_user_id: Any, role: str) -> str:
    role = normalize_role(role)
    key = identity_key(platform, admin_user_id)
    with _ROLES_LOCK, _roles_file_lock():
        roles = _load_roles()
        roles[key] = role
        _save_roles(roles)
    return role


def remove_role_override(platform: Any, admin_user_id: Any) -> bool:
    key = identity_key(platform, admin_user_id)
    with _ROLES_LOCK, _roles_file_lock():
        roles = _load_roles()
        if key not in roles:
            return False
        roles.pop(key, None)
        _save_roles(roles)
    return True


def resolve_admin_role(platform: Any, admin_user_id: Any) -> str:
    """Роль админа: override из хранилища → ENV-bootstrap (owner) → default."""
    overrides = get_role_overrides()
    key = identity_key(platform, admin_user_id)
    if key in overrides:
        return overrides[key]
    if is_configured_admin_user(platform, admin_user_id):
        return OWNER
    return DEFAULT_ROLE


def role_for_session(session: dict[str, Any] | None) -> str:
    if not isinstance(session, dict):
        return DEFAULT_ROLE
    return resolve_admin_role(session.get("platform"), session.get("admin_user_id"))


def session_has_permission(session: dict[str, Any] | None, permission: str) -> bool:
    return has_permission(role_for_session(session), permission)


def require_permission(session: dict[str, Any] | None, permission: str) -> str:
    """Возвращает роль, если право есть; иначе бросает PermissionError."""
    role = role_for_session(session)
    if not has_permission(role, permission):
        raise PermissionError(
            f"Недостаточно прав: требуется «{permission}» (ваша роль: {ROLE_LABELS.get(role, role)})."
        )
    return role
