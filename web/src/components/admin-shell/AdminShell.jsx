import React, { Suspense, lazy, useCallback, useEffect, useMemo, useState } from "react";
import "./AdminShell.css";

// Ленивая загрузка тяжёлых разделов (16-TZ §8): не тянуть их в initial bundle.
const lazyNamed = (factory, name) => lazy(() => factory().then((m) => ({ default: m[name] })));
import { fetchMe, getAdminSessionToken } from "../../api/adminV2Api.js";
import { globalSearch } from "../../api/adminSearchApi.js";
import { OverviewSection } from "./sections/OverviewSection.jsx";
import { PlayersSection } from "./sections/PlayersSection.jsx";
const WorldSection = lazyNamed(() => import("./sections/WorldSection.jsx"), "WorldSection");
import { GuildsSection } from "./sections/GuildsSection.jsx";
import { EventsSection } from "./sections/EventsSection.jsx";
const AchievementsSection = lazyNamed(() => import("./sections/AchievementsSection.jsx"), "AchievementsSection");
import { MessagesSection } from "./sections/MessagesSection.jsx";
import { PromosSection } from "./sections/PromosSection.jsx";
const ItemsSection = lazyNamed(() => import("./sections/ItemsSection.jsx"), "ItemsSection");
const EffectsSection = lazyNamed(() => import("./sections/EffectsSection.jsx"), "EffectsSection");
import { FinesSection } from "./sections/FinesSection.jsx";
import { SkillsSection } from "./sections/SkillsSection.jsx";
const SiteSection = lazyNamed(() => import("./sections/SiteSection.jsx"), "SiteSection");
const ProfileLayoutSection = lazyNamed(() => import("./sections/ProfileLayoutSection.jsx"), "ProfileLayoutSection");
const CitySection = lazyNamed(() => import("./sections/CitySection.jsx"), "CitySection");
const RecipesSection = lazyNamed(() => import("./sections/RecipesSection.jsx"), "RecipesSection");
import { CampSection } from "./sections/CampSection.jsx";
const GraphSection = lazyNamed(() => import("./sections/GraphSection.jsx"), "GraphSection");
const SublocationsSection = lazyNamed(() => import("./sections/SublocationsSection.jsx"), "SublocationsSection");
const FormulasSection = lazyNamed(() => import("./sections/FormulasSection.jsx"), "FormulasSection");
const WorkshopMessagesSection = lazyNamed(() => import("./sections/WorkshopMessagesSection.jsx"), "WorkshopMessagesSection");
import { ReputationSection } from "./sections/ReputationSection.jsx";
const TavernSection = lazyNamed(() => import("./sections/TavernSection.jsx"), "TavernSection");
const ImportSection = lazyNamed(() => import("./sections/ImportSection.jsx"), "ImportSection");
const TextsSection = lazyNamed(() => import("./sections/TextsSection.jsx"), "TextsSection");
import { DashboardSection } from "./sections/DashboardSection.jsx";
import { LibrarySection } from "./sections/LibrarySection.jsx";

const COMBAT_CONFIG = {
  base: "combat", title: "Боевые настройки (таймер/порядок)", permPrefix: "combat",
  newLabel: "Новый профиль боя", nameField: "name",
  fields: [
    { key: "name", label: "Название", type: "text", hint: "Имя профиля боевых настроек." },
    { key: "scope", label: "Область применения", type: "select", metaKey: "scopes", hint: "Глобально / PVE / PVP / моб / событие / подлокация / данж / мировой босс / режим PVP / особый бой." },
    { key: "admin_name", label: "Служебное название PVE", type: "text" },
    { key: "pve_type", label: "Тип PVE-боя", type: "select", metaKey: "pveTypes" },
    { key: "battle_source", label: "Источник запуска", type: "select", metaKey: "pveSources" },
    { key: "location_id", label: "ID локации", type: "text" },
    { key: "sublocation_id", label: "ID подлокации", type: "text" },
    { key: "event_id", label: "ID события", type: "text" },
    { key: "npc_id", label: "ID NPC", type: "text" },
    { key: "quest_id", label: "ID квеста", type: "text" },
    { key: "event_campaign_id", label: "ID событийной кампании", type: "text" },
    { key: "mob_id", label: "ID одиночного моба", type: "text" },
    { key: "mob_group_id", label: "ID группы мобов", type: "text" },
    { key: "boss_id", label: "ID босса", type: "text" },
    { key: "min_level", label: "Мин. уровень игрока", type: "number" },
    { key: "max_level", label: "Макс. уровень игрока", type: "number" },
    { key: "level_scaling", label: "Масштабирование уровня", type: "checkbox" },
    { key: "tags", label: "Теги", type: "list" },
    { key: "timer_enabled", label: "Включить таймер хода", type: "checkbox", hint: "В групповых боях по умолчанию 100 секунд на ход." },
    { key: "turn_seconds", label: "Время на ход (сек)", type: "number", hint: "По умолчанию 100. Одиночный PVE — обычно без таймера." },
    { key: "only_group_battles", label: "Только в групповых боях", type: "checkbox" },
    { key: "apply_single_pve", label: "Применять в одиночном PVE", type: "checkbox", hint: "Для боссов/данжей/событий и т.п. (точечно)." },
    { key: "apply_to_players", label: "Таймер для игроков", type: "checkbox" },
    { key: "apply_to_npc", label: "Таймер для NPC", type: "checkbox" },
    { key: "on_timeout", label: "Действие при истечении", type: "select", metaKey: "timeoutActions", hint: "Для PVP безопаснее: пропуск хода или базовая защита." },
    { key: "warn_before_seconds", label: "Предупредить за N сек", type: "number" },
    { key: "warn_text", label: "Текст предупреждения", type: "text" },
    { key: "skip_text", label: "Текст пропуска хода", type: "text" },
    { key: "can_extend", label: "Можно продлить ход", type: "checkbox" },
    { key: "max_extensions", label: "Макс. продлений", type: "number" },
    { key: "ally_order_type", label: "Порядок союзников-NPC", type: "select", metaKey: "allyOrderTypes", hint: "player_first/npc_first/by_initiative/…" },
    { key: "player_order_type", label: "Порядок игроков-союзников", type: "select", metaKey: "playerOrderTypes" },
    { key: "mixed_order_type", label: "Смешанный порядок (NPC+игроки)", type: "select", metaKey: "mixedOrderTypes" },
    { key: "enemy_order_type", label: "Порядок противников", type: "select", metaKey: "enemyOrderTypes" },
    { key: "enemy_target_rule", label: "Выбор цели противников", type: "select", metaKey: "enemyTargetRules", hint: "random/aggro/weakest/most_dangerous." },
    { key: "group_npc_actions", label: "Объединять действия NPC в одно сообщение", type: "checkbox" },
    { key: "show_npc_actions", label: "Показывать действия NPC игроку", type: "checkbox" },
    { key: "max_players", label: "Лимит игроков (группа)", type: "number" },
    { key: "max_npc", label: "Лимит NPC (сторона)", type: "number" },
    { key: "allow_npc_allies", label: "Разрешить союзников-NPC", type: "checkbox" },
    { key: "allow_player_allies", label: "Разрешить союзников-игроков", type: "checkbox" },
    { key: "max_player_allies", label: "Макс. союзников-игроков", type: "number" },
    { key: "join_method", label: "Способ присоединения", type: "text" },
    { key: "shared_battle", label: "Общий экземпляр боя", type: "checkbox" },
    { key: "separate_turns", label: "Раздельные ходы участников", type: "checkbox" },
    { key: "synchronized_turns", label: "Синхронные ходы стороны", type: "checkbox" },
    { key: "afk_action", label: "Действие союзника при AFK", type: "text" },
    { key: "reward_distribution", label: "Распределение наград", type: "text" },
    { key: "join_text", label: "Текст присоединения", type: "textarea" },
    { key: "leave_text", label: "Текст выхода", type: "textarea" },
    { key: "participants", label: "Участники боевой группы", type: "objlist", columns: [{ key: "participant_id", label: "ID" }, { key: "participant_type", label: "Тип" }, { key: "side", label: "Сторона" }, { key: "team", label: "Команда" }, { key: "name", label: "Название" }, { key: "source_id", label: "Источник/NPC ID" }, { key: "hp", label: "HP" }, { key: "mana", label: "Мана" }, { key: "spirit", label: "Дух" }, { key: "energy", label: "Энергия" }, { key: "damage", label: "Урон" }, { key: "skills", label: "Навыки" }, { key: "effects", label: "Эффекты" }, { key: "behavior", label: "Поведение" }, { key: "target_priority", label: "Приоритет целей" }, { key: "order", label: "Очередность" }, { key: "can_target", label: "Может быть целью" }, { key: "can_attack", label: "Может атаковать" }, { key: "can_heal", label: "Может лечить" }, { key: "can_use_items", label: "Может использовать предметы" }, { key: "can_escape", label: "Может сбежать" }, { key: "can_die", label: "Может умереть" }, { key: "victory_reward", label: "Награда" }, { key: "death_consequence", label: "Последствие смерти" }] },
    { key: "allow_ally_commands", label: "Разрешить приказы союзникам", type: "checkbox" },
    { key: "command_uses_action", label: "Приказ занимает действие", type: "checkbox" },
    { key: "available_commands", label: "Доступные приказы", type: "multiselect", metaKey: "allyCommands" },
    { key: "command_text", label: "Текст приказа", type: "text" },
    { key: "command_error_text", label: "Текст ошибки приказа", type: "text" },
    { key: "enemy_rules", label: "Противники, волны и фазы", type: "objlist", columns: [{ key: "mob_id", label: "Mob ID" }, { key: "count", label: "Количество" }, { key: "rank", label: "Ранг" }, { key: "level", label: "Уровень" }, { key: "scaling", label: "Скалирование" }, { key: "wave", label: "Волна" }, { key: "wave_condition", label: "Условие волны" }, { key: "phase", label: "Фаза" }, { key: "summon_condition", label: "Призыв" }, { key: "experience", label: "Опыт" }, { key: "coins", label: "Монеты" }, { key: "drop", label: "Дроп" }] },
    { key: "turn_order", label: "Порядок хода PVE", type: "select", metaKey: "turnOrders" },
    { key: "main_action_count", label: "Основных действий за ход", type: "number" },
    { key: "additional_action_count", label: "Дополнительных действий", type: "number" },
    { key: "pouch_fast_no_turn", label: "Подсумок/быстрые действия не завершают ход", type: "checkbox" },
    { key: "actions", label: "Действия боя", type: "objlist", columns: [{ key: "action_id", label: "ID" }, { key: "text", label: "Кнопка" }, { key: "action_type", label: "Тип" }, { key: "is_additional", label: "Доп." }, { key: "ends_turn", label: "Завершает ход" }, { key: "cost", label: "Стоимость" }, { key: "condition", label: "Условие" }] },
    { key: "player_escape_allowed", label: "Игрок может сбежать", type: "checkbox" },
    { key: "player_escape_chance", label: "Шанс побега игрока, %", type: "number" },
    { key: "player_escape_formula_id", label: "Формула побега игрока", type: "text" },
    { key: "player_escape_penalty", label: "Штраф за побег", type: "text" },
    { key: "player_escape_attack_on_fail", label: "Атака мобов при неудаче", type: "checkbox" },
    { key: "player_escape_group_behavior", label: "Поведение группы при побеге", type: "text" },
    { key: "mob_escape_rules", label: "Правила побега мобов", type: "objlist", columns: [{ key: "rule_id", label: "ID" }, { key: "enabled", label: "Вкл." }, { key: "mob_id", label: "Mob ID" }, { key: "group_id", label: "Group ID" }, { key: "mode", label: "Режим" }, { key: "condition_type", label: "Условие" }, { key: "operator", label: "Оператор" }, { key: "value", label: "Значение" }, { key: "chance", label: "Шанс %" }, { key: "formula_id", label: "Формула" }, { key: "check_timing", label: "Момент проверки" }, { key: "check_interval", label: "Интервал" }, { key: "player_can_stop", label: "Игрок остановит" }, { key: "npc_can_stop", label: "NPC остановит" }, { key: "stop_chance", label: "Шанс остановки" }, { key: "stop_formula_id", label: "Формула остановки" }, { key: "cancel_rewards", label: "Отменить награды" }, { key: "xp_factor", label: "Коэф. опыта" }, { key: "coin_factor", label: "Коэф. монет" }, { key: "drop_factor", label: "Коэф. дропа" }, { key: "quest_counts", label: "Считать для квеста" }, { key: "achievement_counts", label: "Считать достижение" }, { key: "event_id", label: "Запустить событие" }, { key: "reinforcement_mob_id", label: "Подкрепление Mob ID" }, { key: "future_encounter_id", label: "Будущая встреча" }, { key: "all_escaped_result", label: "Исход при общем побеге" }, { key: "boss_result", label: "Исход побега босса" }, { key: "attempt_text", label: "Текст попытки" }, { key: "success_text", label: "Текст успеха" }, { key: "fail_text", label: "Текст неудачи" }, { key: "stop_text", label: "Текст остановки" }, { key: "group_text", label: "Текст группы" }, { key: "boss_text", label: "Текст босса" }] },
    { key: "victory_rewards", label: "Награды за победу", type: "objlist", columns: [{ key: "type", label: "Тип" }, { key: "object_id", label: "ID" }, { key: "amount", label: "Количество" }, { key: "chance", label: "Шанс" }, { key: "text", label: "Текст" }] },
    { key: "defeat_consequences", label: "Последствия поражения", type: "objlist", columns: [{ key: "type", label: "Тип" }, { key: "object_id", label: "ID" }, { key: "amount", label: "Количество" }, { key: "percent", label: "%" }, { key: "text", label: "Текст" }] },
    { key: "victory_event_id", label: "Событие после победы", type: "text" },
    { key: "defeat_event_id", label: "Событие после поражения", type: "text" },
    { key: "message_layout", label: "Макет сообщения боя", type: "textarea" },
    { key: "message_blocks", label: "Блоки сообщения", type: "objlist", columns: [{ key: "block", label: "Блок" }, { key: "enabled", label: "Вкл." }, { key: "order", label: "Порядок" }, { key: "template", label: "Шаблон" }] },
    { key: "texts", label: "Тексты боя", type: "objlist", columns: [{ key: "key", label: "Ключ" }, { key: "text", label: "Текст" }] },
    { key: "description", label: "Описание (для админа)", type: "textarea" },
  ],
};
const PVP_CONFIG = {
  base: "pvp", title: "PVP-бой", permPrefix: "pvp",
  newLabel: "Новое PVP-правило", nameField: "name",
  fields: [
    { key: "name", label: "Название", type: "text", hint: "Имя правила/пресета PVP." },
    { key: "admin_name", label: "Название для админа", type: "text" },
    { key: "pvp_type", label: "Тип PVP", type: "select", metaKey: "pvpTypes", hint: "Дуэль/арена/осада/заказ/… — задаёт смысл боя." },
    { key: "pvp_source", label: "Источник PVP", type: "select", metaKey: "pvpSources" },
    { key: "enabled", label: "Включён", type: "checkbox", hint: "Опубликованное активное правило используется PVP-runtime." },
    { key: "min_level", label: "Мин. уровень", type: "number", hint: "С какого уровня доступно PVP." },
    { key: "max_level", label: "Макс. уровень", type: "number" },
    { key: "max_level_diff", label: "Макс. разница уровней", type: "number", hint: "Ограничение разницы уровней соперников (0 = без ограничения)." },
    { key: "cooldown_seconds", label: "Кулдаун между боями (сек)", type: "number" },
    { key: "accept_seconds", label: "Время на принятие (сек, дуэль)", type: "number" },
    { key: "require_consent", label: "Только по согласию", type: "checkbox" },
    { key: "attack_without_consent", label: "Нападение без согласия (свободный PVP)", type: "checkbox" },
    { key: "death_on_loss", label: "Поражение со смертью", type: "checkbox" },
    { key: "newbie_protection", label: "Защита новичков", type: "checkbox" },
    { key: "allowed_locations", label: "Разрешённые локации (id по строкам)", type: "list" },
    { key: "forbidden_locations", label: "Запрещённые локации (id по строкам)", type: "list" },
    { key: "allowed_cities", label: "Разрешённые города", type: "list" },
    { key: "criminal_zones_only", label: "Только криминальные зоны", type: "checkbox" },
    { key: "allowed_event_campaigns", label: "Разрешённые эвенты", type: "list" },
    { key: "tags", label: "Теги", type: "list" },
    { key: "conditions", label: "Условия входа в бой", type: "objlist", columns: [{ key: "type", label: "Тип" }, { key: "value", label: "Значение" }], hint: "Уровень/локация/событие/штраф/предмет/статус и т.д." },
    { key: "victory_rewards", label: "Награды за победу", type: "objlist", columns: [{ key: "type", label: "Тип" }, { key: "object_id", label: "ID" }, { key: "amount", label: "Количество" }, { key: "percent", label: "%" }, { key: "chance", label: "Шанс" }, { key: "text", label: "Текст" }] },
    { key: "defeat_consequences", label: "Последствия поражения", type: "objlist", columns: [{ key: "type", label: "Тип" }, { key: "object_id", label: "ID" }, { key: "amount", label: "Количество" }, { key: "percent", label: "%" }, { key: "text", label: "Текст" }] },
    { key: "buttons", label: "Кнопки боя", type: "objlist", columns: [{ key: "action", label: "Действие" }, { key: "text", label: "Текст" }, { key: "resource_cost", label: "Расход" }], hint: "attack/skills/use_item/pouch/defend/flee/surrender/enemy_info." },
    { key: "actions", label: "Действия PVP", type: "objlist", columns: [{ key: "action", label: "Действие" }, { key: "enabled", label: "Разрешено" }, { key: "cost", label: "Стоимость" }, { key: "damage", label: "Урон" }, { key: "effect_duration", label: "Эффект" }, { key: "chance", label: "Шанс" }, { key: "confirm", label: "Подтвердить" }, { key: "ends_turn", label: "Завершает ход" }] },
    { key: "turn_seconds", label: "Время на ход (сек)", type: "number", hint: "В PVP таймер включён по умолчанию (100 секунд, ТЗ 20 §5.5)." },
    { key: "warn_before_seconds", label: "Предупредить за N сек", type: "number" },
    { key: "on_timeout", label: "Действие при пропуске", type: "select", metaKey: "timeoutActions", hint: "skip/defend/auto/kick/tech_defeat/penalty." },
    { key: "max_skips", label: "Допустимо пропусков", type: "number" },
    { key: "afk_default_action", label: "Действие при AFK", type: "text" },
    { key: "afk_technical_defeat", label: "Техпоражение после лимита AFK", type: "checkbox" },
    { key: "action_order", label: "Порядок действий", type: "select", metaKey: "actionOrderTypes", hint: "По очереди/инициативе/скорости/одновременно/стороны и т.д." },
    { key: "log_mode", label: "Режим лога боя", type: "select", metaKey: "logModes", hint: "full_all / per_side / hide_enemy." },
    { key: "sides", label: "Стороны боя", type: "objlist", columns: [{ key: "name", label: "Название" }, { key: "players", label: "Игроки (id через запятую)" }, { key: "npc", label: "NPC (id через запятую)" }, { key: "leader", label: "Лидер" }], hint: "Для командного PVP — минимум 2 стороны." },
    { key: "allow_player_allies", label: "Разрешить игроков-союзников", type: "checkbox" },
    { key: "max_player_allies", label: "Макс. игроков-союзников", type: "number" },
    { key: "ally_sources", label: "Источники союзников", type: "list", hint: "invite/group/guild/event/quest/contract" },
    { key: "ally_can_decline", label: "Союзник может отказаться", type: "checkbox" },
    { key: "ally_afk_action", label: "Действие союзника при AFK", type: "text" },
    { key: "npc_allies", label: "NPC-союзники обеих сторон", type: "objlist", columns: [{ key: "side", label: "Сторона" }, { key: "npc_id", label: "NPC ID" }, { key: "combat_npc_id", label: "Боевая версия" }, { key: "role", label: "Роль" }, { key: "level", label: "Уровень" }, { key: "scaling", label: "Скалирование" }, { key: "behavior", label: "Поведение" }, { key: "skills", label: "Навыки" }, { key: "target_priority", label: "Приоритет" }, { key: "can_die", label: "Может умереть" }, { key: "disappear_after", label: "Исчезает" }, { key: "death_penalty", label: "Штраф смерти" }, { key: "victory_reward", label: "Награда" }, { key: "appear_text", label: "Появление" }, { key: "action_text", label: "Действие" }, { key: "leave_text", label: "Выбытие" }] },
    { key: "npc_limit_per_side", label: "Лимит NPC на сторону", type: "number" },
    { key: "npc_limit_per_player", label: "Лимит NPC на игрока", type: "number" },
    { key: "npc_hire_cost", label: "Стоимость найма NPC", type: "number" },
    { key: "victory_conditions", label: "Условия победы (по строкам)", type: "list" },
    { key: "defeat_conditions", label: "Условия поражения (по строкам)", type: "list" },
    { key: "flee_allowed", label: "Побег разрешён", type: "checkbox" },
    { key: "flee_chance", label: "Шанс побега, %", type: "number" },
    { key: "flee_formula_id", label: "Формула побега", type: "text" },
    { key: "surrender_allowed", label: "Сдача разрешена", type: "checkbox" },
    { key: "surrender_consequences", label: "Последствия сдачи", type: "objlist", columns: [{ key: "type", label: "Тип" }, { key: "object_id", label: "ID" }, { key: "amount", label: "Количество" }, { key: "percent", label: "%" }, { key: "text", label: "Текст" }] },
    { key: "postdeath_curse_enabled", label: "Посмертные PVP-проклятья", type: "checkbox", hint: "Учитываются достижением «Проклятье? Какое проклятье?» (только PVP-смерть, ТЗ §1.6)." },
    { key: "postdeath_curse_chance", label: "Шанс проклятья, %", type: "number" },
    { key: "postdeath_curses", label: "Доступные проклятья (id по строкам)", type: "list" },
    { key: "curse_duration", label: "Длительность проклятья (сек)", type: "number" },
    { key: "curse_requires_achievement", label: "Проклятье требует достижение", type: "checkbox" },
    { key: "curse_achievement_id", label: "ID достижения проклятья", type: "text" },
    { key: "criminal", label: "PVP считается преступлением", type: "checkbox" },
    { key: "fine_id", label: "ID штрафа", type: "text" },
    { key: "criminal_reputation_id", label: "ID криминальной репутации", type: "text" },
    { key: "criminal_reputation_amount", label: "Изменение крим. репутации", type: "number" },
    { key: "city_reputation_id", label: "ID городской репутации", type: "text" },
    { key: "city_reputation_amount", label: "Изменение городской репутации", type: "number" },
    { key: "raid_chance", label: "Шанс облавы, %", type: "number" },
    { key: "move_to_fortress_id", label: "Перенос в крепость ID", type: "text" },
    { key: "city_ban_id", label: "Запрет города ID", type: "text" },
    { key: "ban_start_locations", label: "Запрет стартовых локаций", type: "checkbox" },
    { key: "create_proof_bag", label: "Создать мешок с доказательством", type: "checkbox" },
    { key: "proof_item_id", label: "ID предмета-доказательства", type: "text" },
    { key: "guard_message", label: "Сообщение стражи", type: "textarea" },
    { key: "message_layout_mode", label: "Режим компоновки", type: "select", metaKey: "layoutModes" },
    { key: "message_layout", label: "Шаблон сообщения PVP", type: "textarea" },
    { key: "message_blocks", label: "Блоки сообщения PVP", type: "objlist", columns: [{ key: "block", label: "Блок" }, { key: "enabled", label: "Вкл." }, { key: "order", label: "Порядок" }, { key: "template", label: "Шаблон" }] },
    { key: "texts", label: "Тексты игроку", type: "objlist", columns: [{ key: "key", label: "Ключ" }, { key: "text", label: "Текст" }], hint: "invite/confirm/decline/turn_player/victory/defeat/death/curse/reward/penalty." },
    { key: "description", label: "Описание (для админа)", type: "textarea" },
  ],
};
const NPC_ALLY_CONFIG = {
  base: "npc-allies", title: "Конструктор NPC-союзников", permPrefix: "npc_ally",
  newLabel: "Новый NPC-союзник", nameField: "name",
  fields: [
    { key: "name", label: "Имя", type: "text", hint: "Имя NPC-союзника, видно админу и игроку." },
    { key: "ally_type", label: "Тип", type: "select", metaKey: "allyTypes", hint: "Боевой/лекарь/защитник/разведчик/носильщик/ремесленник/наёмник/спутник и т.д." },
    { key: "role", label: "Роль помощника", type: "select", metaKey: "allyRoles" },
    { key: "description", label: "Описание", type: "textarea" },
    { key: "image_path", label: "Изображение", type: "text", hint: "Локальный путь /assets/…" },
    { key: "acquire_method", label: "Как получить", type: "select", metaKey: "acquireMethods", hint: "Нанять/задание/достижение/событие/таверна/гильдия/дом/предмет/навык/админ." },
    { key: "cost", label: "Стоимость", type: "number" },
    { key: "currency", label: "Валюта", type: "select", metaKey: "currencies" },
    { key: "duration_seconds", label: "Длительность (сек)", type: "number", hint: "Для временных союзников/наёмников." },
    { key: "permanent", label: "Постоянный помощник", type: "checkbox" },
    { key: "active_on_receive", label: "Активировать при получении", type: "checkbox" },
    { key: "battles_limit", label: "Количество боёв/действий", type: "number" },
    { key: "time_limit_seconds", label: "Лимит времени (сек)", type: "number" },
    { key: "cooldown_seconds", label: "Кулдаун (сек)", type: "number" },
    { key: "required_level", label: "Требуемый уровень игрока", type: "number" },
    { key: "required_reputation", label: "Требуемая репутация", type: "number" },
    { key: "access_item_id", label: "Предмет доступа (id)", type: "text" },
    { key: "level", label: "Уровень", type: "number" },
    { key: "rank", label: "Ранг", type: "number" },
    { key: "hp", label: "Здоровье", type: "number" },
    { key: "mana", label: "Мана", type: "number" },
    { key: "spirit", label: "Дух", type: "number" },
    { key: "energy", label: "Энергия", type: "number" },
    { key: "armor", label: "Броня", type: "number" },
    { key: "phys_defense", label: "Физическая защита", type: "number" },
    { key: "magic_defense", label: "Магическая защита", type: "number" },
    { key: "accuracy", label: "Точность, %", type: "number" },
    { key: "dodge", label: "Уклонение, %", type: "number" },
    { key: "crit_chance", label: "Критический шанс, %", type: "number" },
    { key: "crit_damage", label: "Урон крита, %", type: "number" },
    { key: "speed", label: "Скорость/инициатива", type: "number" },
    { key: "abilities", label: "Способности", type: "multiselect", metaKey: "abilities", hint: "Атака/защита/лечение/поиск ресурсов/ремесло/сопровождение/PVE/PVP и т.д." },
    { key: "skills", label: "Навыки (id по строкам)", type: "list" },
    { key: "effects", label: "Эффекты (id по строкам)", type: "list" },
    { key: "resistances", label: "Сопротивления (по строкам)", type: "list" },
    { key: "weaknesses", label: "Слабости (по строкам)", type: "list" },
    { key: "combat_turn_mode", label: "Поведение хода в бою", type: "select", metaKey: "combatTurnModes" },
    { key: "target_mode", label: "Выбор цели", type: "select", metaKey: "targetModes" },
    { key: "target_priority", label: "Приоритет целей (по строкам)", type: "list" },
    { key: "protect_owner", label: "Защищает владельца", type: "checkbox" },
    { key: "heal_low_hp_ally", label: "Лечит союзника с низким HP", type: "checkbox" },
    { key: "can_die", label: "Может погибнуть", type: "checkbox" },
    { key: "can_revive", label: "Можно воскресить", type: "checkbox" },
    { key: "lost_after_battle", label: "Теряется после боя", type: "checkbox" },
    { key: "out_of_battle_behavior", label: "Поведение вне боя", type: "textarea" },
    { key: "gets_loot_share", label: "Получает долю добычи", type: "checkbox" },
    { key: "loot_share_percent", label: "Доля добычи, %", type: "number" },
    { key: "find_bonus_percent", label: "Бонус к шансу находки, %", type: "number" },
    { key: "owner_reward_penalty_percent", label: "Снижение награды игрока, %", type: "number" },
    { key: "own_resources", label: "Приносит ресурсы (id по строкам)", type: "list" },
    { key: "affects_player_exp", label: "Влияет на опыт игрока", type: "checkbox" },
    { key: "has_progress", label: "Имеет собственный прогресс", type: "checkbox" },
    { key: "can_level_up", label: "Повышает уровень", type: "checkbox" },
    { key: "restrictions", label: "Штрафы/запреты (по строкам)", type: "list" },
    { key: "loyalty_enabled", label: "Лояльность включена (§61)", type: "checkbox" },
    { key: "loyalty_start", label: "Стартовая лояльность", type: "number" },
    { key: "loyalty_min", label: "Минимальная лояльность", type: "number" },
    { key: "loyalty_max", label: "Максимальная лояльность", type: "number" },
    { key: "has_levels", label: "Имеет уровни (развитие §60)", type: "checkbox" },
    { key: "dev_level", label: "Текущий уровень", type: "number" },
    { key: "dev_max_level", label: "Максимальный уровень", type: "number" },
    { key: "dev_exp_per_battle", label: "Опыт за бой", type: "number" },
    { key: "dev_exp_per_quest", label: "Опыт за квест", type: "number" },
    { key: "dev_formula_id", label: "Формула развития (id)", type: "text" },
    { key: "permanent_death", label: "Может умереть навсегда (§62)", type: "checkbox" },
    { key: "revival_methods", label: "Способы восстановления", type: "multiselect", metaKey: "revivalMethods" },
    { key: "pvp_allow_mode", label: "Допуск в PVP (§58)", type: "select", metaKey: "pvpAllowModes" },
    { key: "out_of_battle_actions", label: "Внебоевые действия (§59)", type: "multiselect", metaKey: "outOfBattleActions" },
    { key: "own_actions", label: "Собственные действия помощника", type: "objlist", columns: [{ key: "id", label: "ID" }, { key: "name", label: "Название" }, { key: "type", label: "Тип" }, { key: "condition", label: "Условие" }, { key: "cost", label: "Стоимость" }, { key: "cooldown_seconds", label: "Откат" }, { key: "success_chance", label: "Шанс" }, { key: "formula_id", label: "Формула" }, { key: "success_text", label: "Текст успеха" }, { key: "fail_text", label: "Текст провала" }] },
    { key: "pve_enabled", label: "Участвует в PVE", type: "checkbox" },
    { key: "can_be_target", label: "Может быть целью", type: "checkbox" },
    { key: "default_behavior", label: "Поведение по умолчанию", type: "text" },
    { key: "phys_damage", label: "Физический урон", type: "number" },
    { key: "magic_damage", label: "Магический урон", type: "number" },
    { key: "initiative", label: "Инициатива", type: "number" },
    { key: "max_active_helpers", label: "Максимум активных помощников", type: "number" },
    { key: "max_total_helpers", label: "Максимум помощников всего", type: "number" },
    { key: "forbid_city", label: "Нельзя использовать в городе", type: "checkbox" },
    { key: "forbid_fortress", label: "Нельзя использовать в крепости", type: "checkbox" },
    { key: "forbid_with_fine", label: "Нельзя использовать при штрафе", type: "checkbox" },
    { key: "required_loyalty", label: "Минимальная лояльность", type: "number" },
    { key: "revival_seconds", label: "Время восстановления (сек)", type: "number" },
    { key: "exp_per_level", label: "Опыт на уровень", type: "number" },
    { key: "loyalty_on_victory", label: "Лояльность за победу", type: "number" },
    { key: "loyalty_on_defeat", label: "Потеря лояльности за поражение", type: "number" },
    { key: "outside_action_chance", label: "Шанс внебоевого действия, %", type: "number" },
    { key: "outside_action_cooldown", label: "Откат внебоевого действия (сек)", type: "number" },
    { key: "outside_bonus_percent", label: "Бонус вне боя, %", type: "number" },
    { key: "outside_target_id", label: "Цель внебоевого действия (ID)", type: "text" },
    ...[["obtain_text", "Текст получения"], ["denied_text", "Текст отказа"], ["summon_text", "Текст призыва"], ["battle_appear_text", "Текст появления в бою"], ["attack_text", "Текст атаки"], ["heal_text", "Текст лечения"], ["protect_text", "Текст защиты"], ["skill_text", "Текст навыка"], ["command_error_text", "Текст ошибки приказа"], ["death_text", "Текст смерти"], ["leave_text", "Текст выбытия"], ["return_text", "Текст возвращения"], ["level_up_text", "Текст повышения уровня"], ["loyalty_text", "Текст изменения лояльности"], ["outside_action_text", "Текст внебоевого действия"], ["use_denied_text", "Текст запрета использования"], ["outside_success_text", "Текст успеха вне боя"], ["outside_fail_text", "Текст провала вне боя"]].map(([key, label]) => ({ key, label, type: "textarea" })),
  ],
};
const EVENT_CAMPAIGN_CONFIG = {
  base: "event-campaigns", title: "Конструктор эвентов", permPrefix: "event_campaign", newLabel: "Новый эвент", nameField: "name",
  fields: [
    { key: "name", label: "Название", type: "text" }, { key: "player_name", label: "Название для игрока", type: "text" }, { key: "system_name", label: "Системное название", type: "text" },
    { key: "event_type", label: "Тип эвента", type: "select", metaKey: "eventTypes" }, { key: "category", label: "Категория", type: "text" }, { key: "short_description", label: "Краткое описание", type: "textarea" }, { key: "description", label: "Полное описание", type: "textarea" }, { key: "technical_description", label: "Техническое описание", type: "textarea" }, { key: "image", label: "Изображение", type: "text" }, { key: "icon", label: "Иконка", type: "text" }, { key: "tags", label: "Теги", type: "list" },
    { key: "start_at", label: "Дата начала (ISO)", type: "text" }, { key: "end_at", label: "Дата окончания (ISO)", type: "text" }, { key: "endless", label: "Бессрочный", type: "checkbox" },
    { key: "all_players", label: "Участвуют все", type: "checkbox" }, { key: "registration_required", label: "Нужна регистрация", type: "checkbox" }, { key: "registration_via_button", label: "Регистрация кнопкой", type: "checkbox" }, { key: "registration_via_npc", label: "Регистрация через NPC", type: "checkbox" }, { key: "registration_via_item", label: "Регистрация предметом", type: "checkbox" }, { key: "registration_item_id", label: "Предмет регистрации (ID)", type: "text" }, { key: "consume_registration_item", label: "Расходовать предмет регистрации", type: "checkbox" }, { key: "min_level", label: "Минимальный уровень", type: "number" }, { key: "required_race", label: "Требуемая раса", type: "text" }, { key: "required_achievement", label: "Требуемое достижение", type: "text" }, { key: "required_reputation_id", label: "Требуемая репутация", type: "text" }, { key: "required_reputation_value", label: "Значение репутации", type: "number" }, { key: "exclude_with_fine", label: "Исключить игроков со штрафом", type: "checkbox" }, { key: "participant_ids", label: "Участники (ID по строкам)", type: "list" }, { key: "excluded_player_ids", label: "Исключения (ID по строкам)", type: "list" },
    { key: "stages", label: "Этапы", type: "objlist", columns: [{ key: "stage_id", label: "ID" }, { key: "name", label: "Название" }, { key: "description", label: "Описание" }, { key: "start_at", label: "Начало" }, { key: "end_at", label: "Окончание" }, { key: "start_condition", label: "Условие старта" }, { key: "finish_condition", label: "Условие завершения" }, { key: "start_text", label: "Текст старта" }, { key: "finish_text", label: "Текст завершения" }] },
    { key: "tasks", label: "Задачи", type: "objlist", columns: [{ key: "task_id", label: "ID" }, { key: "stage_id", label: "Этап" }, { key: "task_type", label: "Тип" }, { key: "target_id", label: "Цель" }, { key: "required_count", label: "Количество" }, { key: "points", label: "Очки" }, { key: "show_progress", label: "Показывать" }, { key: "hidden", label: "Скрытая" }, { key: "complete_text", label: "Текст выполнения" }] },
    { key: "rewards", label: "Награды", type: "objlist", columns: [{ key: "type", label: "Тип" }, { key: "object_id", label: "ID объекта" }, { key: "amount", label: "Количество" }, { key: "quality", label: "Качество" }, { key: "scope", label: "participation/task/stage/rating/final" }, { key: "scope_id", label: "ID области" }, { key: "condition", label: "Условие" }] },
    { key: "rating_enabled", label: "Рейтинг включён", type: "checkbox" }, { key: "rating_type", label: "Тип рейтинга", type: "select", metaKey: "ratingTypes" }, { key: "points_formula_id", label: "Формула очков", type: "text" }, { key: "show_top", label: "Показывать топ", type: "checkbox" }, { key: "show_only_own_place", label: "В профиле только место игрока", type: "checkbox" }, { key: "hide_full_rating", label: "Скрыть полный рейтинг", type: "checkbox" }, { key: "send_results", label: "Отправить итоги", type: "checkbox" },
    { key: "locations", label: "Временные локации", type: "list" }, { key: "location_events", label: "События", type: "list" }, { key: "mobs", label: "Мобы", type: "list" }, { key: "npcs", label: "NPC", type: "list" }, { key: "items", label: "Предметы", type: "list" }, { key: "buttons", label: "Кнопки", type: "list" }, { key: "broadcast_ids", label: "Рассылки", type: "list" }, { key: "world_event_ids", label: "Мировые события", type: "list" }, { key: "world_modifiers", label: "Мировые модификаторы", type: "objlist", columns: [{ key: "key", label: "Параметр" }, { key: "value", label: "Значение" }] },
  ],
};
const BROADCAST_CAMPAIGN_CONFIG = {
  base: "broadcast-campaigns", title: "Конструктор рассылок", permPrefix: "broadcast_campaign", runtimeType: "broadcast", newLabel: "Новая рассылка", nameField: "name",
  fields: [
    { key: "name", label: "Название", type: "text" }, { key: "system_name", label: "Системное название", type: "text" }, { key: "broadcast_type", label: "Тип", type: "select", metaKey: "broadcastTypes" }, { key: "category", label: "Категория", type: "text" }, { key: "short_description", label: "Краткое описание", type: "textarea" }, { key: "technical_description", label: "Техническое описание", type: "textarea" }, { key: "tags", label: "Теги", type: "list" },
    { key: "audience_mode", label: "Аудитория", type: "select", metaKey: "audienceModes" }, { key: "specific_player_ids", label: "Список игроков", type: "list" }, { key: "exclude_player_ids", label: "Исключить игроков", type: "list" }, { key: "min_level", label: "Уровень от", type: "number" }, { key: "max_level", label: "Уровень до", type: "number" }, { key: "race_id", label: "Раса", type: "text" }, { key: "location_id", label: "Локация", type: "text" }, { key: "achievement_id", label: "Достижение", type: "text" }, { key: "quest_id", label: "Квест", type: "text" }, { key: "reputation_id", label: "Репутация", type: "text" }, { key: "reputation_value", label: "Значение репутации", type: "number" }, { key: "item_id", label: "Предмет-фильтр", type: "text" }, { key: "effect_id", label: "Эффект-фильтр", type: "text" }, { key: "active_days", label: "Активность за дней", type: "number" },
    { key: "title", label: "Заголовок сообщения", type: "text" }, { key: "text", label: "Текст сообщения", type: "textarea" }, { key: "image", label: "Изображение", type: "text" }, { key: "send_mode", label: "Режим отправки", type: "select", metaKey: "sendModes" }, { key: "format", label: "Форматирование", type: "select", metaKey: "formats" }, { key: "technical_note", label: "Техническое примечание", type: "textarea" },
    { key: "rewards", label: "Награды и вложения", type: "objlist", columns: [{ key: "type", label: "Тип" }, { key: "object_id", label: "ID объекта" }, { key: "amount", label: "Количество" }, { key: "quality", label: "Качество" }, { key: "bind_on_receive", label: "Привязать" }, { key: "delivery_mode", label: "inventory/delivery/overflow" }, { key: "receive_text", label: "Текст получения" }] },
    { key: "buttons", label: "Кнопки", type: "objlist", columns: [{ key: "button_id", label: "ID" }, { key: "text", label: "Текст" }, { key: "action", label: "Действие" }, { key: "target", label: "Цель" }, { key: "condition", label: "Условие" }] },
    { key: "send_immediately", label: "Отправить сразу", type: "checkbox" }, { key: "schedule_at", label: "Дата/время отправки (ISO)", type: "text" }, { key: "send_in_batches", label: "Отправлять частями", type: "checkbox" }, { key: "batch_size", label: "Размер пачки", type: "number" }, { key: "batch_delay_seconds", label: "Задержка между пачками, сек", type: "number" }, { key: "stop_on_errors", label: "Остановить при ошибках", type: "checkbox" }, { key: "retry_failed", label: "Повторять ошибочные", type: "checkbox" }, { key: "test_before_main", label: "Тест перед основной", type: "checkbox" }, { key: "test_player_ids", label: "Получатели теста (NT-ID)", type: "list" }, { key: "double_confirmation_required", label: "Двойное подтверждение наград", type: "checkbox" },
  ],
};
const MOLE_CONFIG = {
  base: "mole", title: "Информатор Крот (криминальный сервис)", permPrefix: "mole",
  newLabel: "Новый сервис Крота", nameField: "name",
  fields: [
    { key: "name", label: "Название", type: "text", hint: "Имя сервиса Крота (видно админу)." },
    { key: "location_id", label: "Локация (id)", type: "text" },
    { key: "city_id", label: "Город (id)", type: "text" },
    { key: "description", label: "Описание", type: "textarea" },
    { key: "info_search_modes", label: "Режимы поиска информации", type: "multiselect", metaKey: "infoSearchModes", hint: "По нику/ID/уровню/диапазону, регион/точная локация." },
    { key: "info_cost", label: "Стоимость информации", type: "number" },
    { key: "info_currency", label: "Валюта информации", type: "select", metaKey: "currencies" },
    { key: "info_cooldown_seconds", label: "Кулдаун информации (сек)", type: "number" },
    { key: "info_delay_seconds", label: "Задержка получения (сек)", type: "number" },
    { key: "info_freshness_seconds", label: "Время актуальности (сек)", type: "number" },
    { key: "info_error_chance", label: "Шанс ошибки, %", type: "number" },
    { key: "info_stale_chance", label: "Шанс устаревшей информации, %", type: "number" },
    { key: "info_protected_by", label: "Защита от поиска (эффект/предмет/статус, по строкам)", type: "list" },
    { key: "info_banned_targets", label: "Запрет поиска игроков (по строкам)", type: "list" },
    { key: "compass_enabled", label: "Магический компас включён", type: "checkbox", hint: "Дорогая услуга быстрого перемещения к цели (§3.3)." },
    { key: "compass_mode", label: "Режим компаса", type: "select", metaKey: "compassModes" },
    { key: "compass_cost", label: "Стоимость компаса", type: "number" },
    { key: "compass_currency", label: "Валюта компаса", type: "select", metaKey: "currencies" },
    { key: "compass_price_by_distance", label: "Цена зависит от расстояния", type: "checkbox" },
    { key: "compass_price_by_target_level", label: "Цена зависит от уровня цели", type: "checkbox" },
    { key: "compass_price_by_danger", label: "Цена зависит от опасности локации", type: "checkbox" },
    { key: "compass_one_time", label: "Одноразовый компас", type: "checkbox" },
    { key: "compass_duration_seconds", label: "Время действия компаса (сек)", type: "number" },
    { key: "order_attempts", label: "Количество попыток заказа", type: "number" },
    { key: "order_attack_cooldown_seconds", label: "Кулдаун между нападениями (сек)", type: "number" },
    { key: "order_duration_seconds", label: "Срок действия заказа (сек)", type: "number" },
    { key: "order_notify_orderer", label: "Уведомлять заказчика", type: "checkbox" },
    { key: "order_notify_target", label: "Уведомлять цель", type: "checkbox" },
    { key: "order_hide_orderer", label: "Скрывать имя заказчика", type: "checkbox" },
    { key: "order_drop_on_win", label: "Дроп с убийц при победе цели", type: "checkbox" },
    { key: "order_refund_policy", label: "Возврат средств при провале", type: "select", metaKey: "refundPolicies" },
    { key: "ban_max_level_diff", label: "Запрет: макс. разница уровней", type: "number", hint: "Обязательно: нельзя заказать при разнице уровней больше 400 (§3.5)." },
    { key: "ban_weaker_ratio", label: "Запрет: цель слабее в N раз", type: "number", hint: "Обязательно: нельзя заказать игрока слабее заказчика более чем в 2 раза (§3.5)." },
    { key: "ban_flags", label: "Доп. запреты заказа (по строкам)", type: "list", hint: "Новичок/под защитой/админ/безопасный статус/обучение/частый заказ/активный штраф." },
    { key: "assassin_categories", label: "Категории убийц", type: "objlist", columns: [{ key: "category", label: "Категория" }, { key: "price", label: "Цена" }, { key: "level", label: "Уровень" }, { key: "count", label: "Кол-во" }, { key: "success_chance", label: "Шанс %" }, { key: "attempts", label: "Попыток" }], hint: "Дешёвый/обычный/опытный/элитный/маг/отравитель/следопыт/группа/редкий/особый." },
    { key: "price_base", label: "Базовая цена", type: "number" },
    { key: "mult_target_level", label: "Множитель по уровню цели", type: "number" },
    { key: "mult_orderer_level", label: "Множитель по уровню заказчика", type: "number" },
    { key: "mult_distance", label: "Множитель по расстоянию", type: "number" },
    { key: "mult_category", label: "Множитель по категории", type: "number" },
    { key: "mult_urgency", label: "Множитель за срочность", type: "number" },
    { key: "mult_group", label: "Множитель за группу", type: "number" },
    { key: "mult_stealth", label: "Множитель за скрытность", type: "number" },
    { key: "price_min", label: "Минимальная цена", type: "number" },
    { key: "price_max", label: "Максимальная цена", type: "number" },
    { key: "mole_commission", label: "Комиссия Крота", type: "number" },
  ],
};
const CASINO_CONFIG = {
  base: "casino", title: "Подпольное казино", permPrefix: "casino",
  operationLogs: true,
  newLabel: "Новое казино", nameField: "name",
  fields: [
    { key: "name", label: "Название", type: "text", hint: "Имя казино (видно админу)." },
    { key: "player_name", label: "Название для игрока", type: "text" }, { key: "system_name", label: "Системное название", type: "text" },
    { key: "enabled", label: "Включено", type: "checkbox" },
    { key: "location_id", label: "Локация (id)", type: "text" },
    { key: "city_id", label: "Город (id)", type: "text" },
    { key: "sublocation_id", label: "Подлокация/тёмные переулки", type: "text" }, { key: "tavern_id", label: "Родительская таверна", type: "text" }, { key: "criminal_zone_id", label: "Криминальная зона", type: "text" },
    { key: "owner_npc", label: "NPC/владелец", type: "text" },
    { key: "description", label: "Описание", type: "textarea" },
    { key: "min_level", label: "Минимальный уровень", type: "number" },
    { key: "required_item_id", label: "Предмет доступа", type: "text" }, { key: "required_reputation_id", label: "Репутация доступа", type: "text" }, { key: "required_reputation_value", label: "Значение репутации", type: "number" }, { key: "required_hidden_reputation_id", label: "Скрытая репутация", type: "text" }, { key: "required_quest_id", label: "Квест доступа", type: "text" }, { key: "required_event_id", label: "Событие доступа", type: "text" }, { key: "requires_no_fine", label: "Только без штрафа", type: "checkbox" }, { key: "required_fine_id", label: "Требуемый штраф", type: "text" }, { key: "night_only", label: "Только ночью", type: "checkbox" }, { key: "closed_by_admin", label: "Закрыто администратором", type: "checkbox" },
    { key: "npc_links", label: "NPC казино", type: "objlist", columns: [{ key: "npc_id", label: "NPC ID" }, { key: "role", label: "Роль" }, { key: "condition", label: "Условие" }, { key: "dialogue_id", label: "Диалог" }, { key: "event_id", label: "Событие" }, { key: "active", label: "Активен" }] },
    { key: "min_bet", label: "Минимальная ставка", type: "number" },
    { key: "max_bet", label: "Максимальная ставка", type: "number" },
    { key: "currency", label: "Валюта", type: "select", metaKey: "currencies" },
    { key: "games_per_day", label: "Лимит игр в день", type: "number" },
    { key: "win_per_day", label: "Лимит выигрыша в день", type: "number" },
    { key: "cooldown_seconds", label: "Кулдаун (сек)", type: "number" },
    { key: "raid_risk_percent", label: "Риск облавы, %", type: "number" },
    { key: "games_per_week", label: "Лимит игр в неделю", type: "number" }, { key: "bet_sum_per_day", label: "Лимит суммы ставок/день", type: "number" }, { key: "suspicious_win_streak", label: "Подозрительная серия побед", type: "number" },
    { key: "raid_enabled", label: "Облавы включены", type: "checkbox" }, { key: "raid_depends_bet", label: "Риск зависит от ставки", type: "checkbox" }, { key: "raid_closes_casino", label: "Облава закрывает казино", type: "checkbox" }, { key: "raid_gives_fine", label: "Облава выдаёт штраф", type: "checkbox" }, { key: "raid_moves_fortress", label: "Переносит в крепость", type: "checkbox" }, { key: "fine_id", label: "ID штрафа", type: "text" },
    { key: "reputation_rules", label: "Репутация", type: "objlist", columns: [{ key: "reputation_id", label: "ID" }, { key: "hidden", label: "Скрытая" }, { key: "trigger", label: "Триггер" }, { key: "value", label: "Изменение" }] },
    { key: "events", label: "События", type: "objlist", columns: [{ key: "event_id", label: "ID" }, { key: "type", label: "Тип" }, { key: "chance", label: "Шанс" }, { key: "trigger", label: "Триггер" }, { key: "text", label: "Текст" }, { key: "consequence", label: "Последствие" }] },
    { key: "achievement_rules", label: "Достижения", type: "objlist", columns: [{ key: "achievement_id", label: "ID" }, { key: "condition", label: "Условие" }, { key: "text", label: "Текст" }] },
    { key: "buttons", label: "Кнопки", type: "objlist", columns: [{ key: "button_id", label: "ID" }, { key: "text", label: "Текст" }, { key: "action", label: "Действие" }, { key: "target_id", label: "Цель" }, { key: "condition", label: "Условие" }, { key: "error_text", label: "Ошибка" }, { key: "order", label: "Порядок" }] },
    { key: "depends_world_event", label: "Зависит от мировых событий", type: "checkbox" },
    { key: "depends_effects", label: "Зависит от эффектов", type: "checkbox" },
    { key: "depends_achievements", label: "Зависит от достижений", type: "checkbox" },
    { key: "depends_fines", label: "Зависит от штрафов", type: "checkbox" },
    { key: "games", label: "Игры и баланс", type: "objlist", columns: [{ key: "game_id", label: "ID" }, { key: "name", label: "Название" }, { key: "game_type", label: "Игра" }, { key: "min_bet", label: "Мин. ставка" }, { key: "max_bet", label: "Макс. ставка" }, { key: "currency", label: "Валюта" }, { key: "win_chance", label: "Шанс выигрыша %" }, { key: "loss_chance", label: "Шанс проигрыша %" }, { key: "coefficient", label: "Коэффициент" }, { key: "commission", label: "Комиссия %" }, { key: "win_formula_id", label: "Формула выигрыша" }, { key: "loss_formula_id", label: "Формула проигрыша" }, { key: "raid_risk_percent", label: "Риск облавы" }, { key: "game_limit", label: "Лимит" }, { key: "win_text", label: "Победа" }, { key: "loss_text", label: "Проигрыш" }, { key: "draw_text", label: "Ничья" }, { key: "active", label: "Активна" }], hint: "Шанс проигрыша должен быть выше шанса выигрыша. Чем выше коэффициент — тем ниже шанс победы." },
    { key: "win_rewards", label: "Выигрыши", type: "objlist", columns: [{ key: "type", label: "Тип" }, { key: "object_id", label: "Объект" }, { key: "amount", label: "Количество" }, { key: "quality", label: "Качество" }, { key: "chance", label: "Шанс" }, { key: "currency", label: "Валюта" }, { key: "text", label: "Текст" }] },
    { key: "losses", label: "Проигрыши", type: "objlist", columns: [{ key: "type", label: "Тип" }, { key: "object_id", label: "Объект" }, { key: "amount", label: "Значение" }, { key: "chance", label: "Шанс" }, { key: "currency", label: "Валюта" }, { key: "text", label: "Текст" }, { key: "consequence_text", label: "Последствие" }] },
    { key: "wheel_enabled", label: "Колесо Удачи включено", type: "checkbox" },
    { key: "wheel_prizes", label: "Призы колеса (5–10)", type: "objlist", columns: [{ key: "prize_type", label: "Тип" }, { key: "name", label: "Название" }, { key: "item_id", label: "Предмет/валюта" }, { key: "count", label: "Кол-во" }, { key: "chance", label: "Шанс %" }], hint: "Монеты/предмет/ингредиент. От 5 до 10 призов. При выпадении приза его шанс уходит в пустой результат." },
    { key: "wheel_empty_chance", label: "Шанс пустого результата, %", type: "number" },
    { key: "wheel_show_chances", label: "Показывать шансы игроку", type: "checkbox" },
    { key: "wheel_show_prizes", label: "Показывать список призов игроку", type: "checkbox" },
    { key: "wheel_spin_cost", label: "Стоимость прокрутки", type: "number" },
    { key: "wheel_refresh_paid", label: "Обновление призов за плату", type: "checkbox" },
    { key: "wheel_refresh_auto_24h", label: "Авто-обновление каждые 24ч", type: "checkbox" },
    { key: "text_spin", label: "Текст прокрутки", type: "text" },
    { key: "text_win", label: "Текст выигрыша", type: "text" },
    { key: "text_empty", label: "Текст пустого результата", type: "text" },
    ...[["entry_text","Вход"],["hidden_entry_text","Скрытый вход"],["access_denied_text","Отказ во входе"],["main_menu_text","Главное меню"],["game_select_text","Выбор игры"],["bet_text","Ставка"],["not_enough_money_text","Нехватка денег"],["win_text","Выигрыш"],["big_win_text","Крупный выигрыш"],["loss_text","Проигрыш"],["draw_text","Ничья"],["limit_text","Лимит"],["raid_text","Облава"],["fine_text","Штраф"],["closed_text","Закрытие"],["npc_text","Появление NPC"],["exit_text","Выход"],["technical_error_text","Техническая ошибка"]].map(([key,label]) => ({ key, label, type: "textarea" })),
  ],
};
const HOUSING_CONFIG = {
  base: "housing", title: "Жилой район / дом игрока", permPrefix: "housing",
  newLabel: "Новый план жилья", nameField: "name",
  fields: [
    { key: "name", label: "Название", type: "text", hint: "Имя плана жилья (видно админу)." },
    { key: "plot_type", label: "Тип участка", type: "select", metaKey: "plotTypes", hint: "Малый/средний/большой участок (§6.1)." },
    { key: "house_type", label: "Тип дома", type: "select", metaKey: "houseTypes" },
    { key: "cooking_tier", label: "Уровень готовки", type: "select", metaKey: "cookingTiers", hint: "Малый — обычные блюда; обычный — необычные эффекты; большой — особые эффекты." },
    { key: "full_rest_minutes", label: "Отдых до полного восстановления (мин)", type: "number", hint: "Малый 90 / обычный 60 / большой 40 (редактируется)." },
    { key: "extra_building_slots", label: "Доп. постройки (слотов)", type: "number" },
    { key: "base_features", label: "Базовые возможности (по строкам)", type: "list", hint: "Почтовый ящик / спец. комната / трофейная и т.д." },
    { key: "description", label: "Описание", type: "textarea" },
    { key: "special_rooms", label: "Специальные комнаты (§6.3)", type: "objlist", columns: [{ key: "room_type", label: "Комната" }, { key: "stats", label: "Характеристики (через запятую)" }, { key: "time_minutes", label: "Время (мин)" }, { key: "chance_percent", label: "Шанс %" }, { key: "daily_limit", label: "Лимит/день" }, { key: "success_text", label: "Текст успеха" }, { key: "fail_text", label: "Текст неудачи" }, { key: "cost", label: "Стоимость" }], hint: "Тренажёрный зал/Зал реакции/Комната медитации. По умолчанию 30 мин, 40%, 1 раз в день." },
    { key: "fixed_buildings", label: "Неулучшаемые постройки (§6.2)", type: "objlist", columns: [{ key: "building_type", label: "Постройка" }, { key: "effect", label: "Эффект" }], hint: "Ювелирный/кожевенный/кузнечный станок, плавильня, почтовый ящик, комната трофеев." },
    { key: "upgradable_buildings", label: "Улучшаемые постройки (§6.4)", type: "objlist", columns: [{ key: "building_type", label: "Постройка" }, { key: "level", label: "Уровень" }, { key: "max_level", label: "Макс." }, { key: "upgrade_cost", label: "Цена улучш." }, { key: "materials", label: "Материалы" }, { key: "upgrade_time_seconds", label: "Время (сек)" }, { key: "level_effect", label: "Эффект уровня" }], hint: "Склад/Оранжерея/Алтарь/Пруд." },
    { key: "dishes", label: "Домашняя готовка (§6.5)", type: "objlist", columns: [{ key: "name", label: "Блюдо" }, { key: "dish_type", label: "Тип" }, { key: "required_house", label: "Нужен дом" }, { key: "ingredients", label: "Ингредиенты" }, { key: "cook_time_seconds", label: "Время (сек)" }, { key: "effect", label: "Эффект" }, { key: "effect_duration_seconds", label: "Длит. эффекта" }, { key: "success_chance", label: "Шанс %" }], hint: "Обычные/необычные/особые блюда в зависимости от дома." },
    { key: "restore_hp_percent", label: "Отдых: восстановление HP, %", type: "number" },
    { key: "restore_mana_percent", label: "Отдых: восстановление маны, %", type: "number" },
    { key: "restore_spirit_percent", label: "Отдых: восстановление духа, %", type: "number" },
    { key: "restore_energy_percent", label: "Отдых: восстановление энергии, %", type: "number" },
    { key: "rest_room_bonus", label: "Бонусы отдыха от комнат/трофеев/алтаря (по строкам)", type: "list" },
    { key: "rest_can_interrupt", label: "Можно прервать отдых", type: "checkbox" },
    { key: "rest_interrupt_text", label: "Текст при прерывании отдыха", type: "text" },
    { key: "rest_start_text", label: "Текст начала отдыха", type: "text" },
    { key: "rest_finish_text", label: "Текст завершения отдыха", type: "text" },
  ],
};
const MESSAGE_RULE_CONFIG = {
  base: "message-rules", title: "Очередь и приоритет сообщений", permPrefix: "message_rule",
  newLabel: "Новое правило очереди", nameField: "name",
  fields: [
    { key: "name", label: "Название", type: "text", hint: "Имя правила очереди (видно админу)." },
    { key: "message_type", label: "Тип сообщения", type: "select", metaKey: "messageTypes", hint: "combat/achievement/reward/broadcast/penalty/… (§4)." },
    { key: "source", label: "Источник", type: "select", metaKey: "sourceTypes" },
    { key: "priority", label: "Приоритет", type: "number", hint: "1 — бой/критичное, 2 — достижения/награды, 3 — рассылки, 0 — ждать сообщения игрока, пусто — после таймера." },
    { key: "platform", label: "Платформа", type: "select", metaKey: "platforms" },
    { key: "channel", label: "Канал отправки", type: "text", hint: "Личный чат, группа игроков, админы или общий чат." },
    { key: "send_mode", label: "Режим отправки", type: "select", metaKey: "sendModes", hint: "Сразу/после таймера/после боя/после действия/в время/пачкой (§9)." },
    { key: "send_at", label: "Время отправки (для «в указанное время»)", type: "text" },
    { key: "timer_seconds", label: "Таймер (сек)", type: "number" },
    { key: "group_enabled", label: "Группировать похожие сообщения", type: "checkbox" },
    { key: "max_in_group", label: "Макс. сообщений в группе", type: "number" },
    { key: "group_header", label: "Заголовок группы", type: "text" },
    { key: "group_footer", label: "Итоговый текст группы", type: "text" },
    { key: "message_template", label: "Шаблон сообщения", type: "textarea", hint: "Переменные: {{player_name}}, {{game_id}}, {{message}}, {{amount}}, {{item_name}}, {{source_name}}, {{error}}, {{date}}, {{time}}." },
    { key: "buttons", label: "Кнопки сообщения", type: "objlist", columns: [{ key: "button_id", label: "ID" }, { key: "text", label: "Текст" }, { key: "action", label: "Действие" }, { key: "target", label: "Цель" }, { key: "show_condition", label: "Условие" }, { key: "ttl_seconds", label: "Срок жизни" }, { key: "one_time", label: "Одноразовая" }, { key: "error_text", label: "Текст ошибки" }] },
    { key: "repeat_on_error", label: "Повторять при ошибке доставки", type: "checkbox" },
    { key: "max_retries", label: "Макс. повторов", type: "number" },
    { key: "retry_interval_seconds", label: "Интервал повторов (сек)", type: "number" },
    { key: "ttl_seconds", label: "Срок жизни сообщения (сек)", type: "number" },
    { key: "delete_after_ttl", label: "Удалять из очереди после срока", type: "checkbox" },
    { key: "hide_until_condition", label: "Скрыть от игрока до условия", type: "checkbox" },
    { key: "log_send", label: "Логировать отправку", type: "checkbox" },
    { key: "show_admin", label: "Показывать админу", type: "checkbox" },
    { key: "error_text", label: "Текст ошибки доставки", type: "text" },
    { key: "description", label: "Описание (для админа)", type: "textarea" },
  ],
};
const QUEST_CONFIG = {
  base: "quests", title: "Квесты и задания", permPrefix: "quest",
  newLabel: "Новый квест", nameField: "name",
  supportsImport: true, importLabel: "Импортировать старые квесты?", importText: "Legacy-квесты будут импортированы с исходными ID; прогресс игроков не изменится.",
  fields: [
    { key: "name", label: "Название", type: "text", hint: "Имя квеста (видно админу и игроку)." },
    { key: "quest_type", label: "Тип квеста", type: "select", metaKey: "questTypes", hint: "Сюжетный/побочный/ежедневный/скрытый/NPC/доска и т.д." },
    { key: "category", label: "Категория", type: "text" },
    { key: "description", label: "Описание (игроку)", type: "textarea" },
    { key: "hidden_description", label: "Скрытое описание", type: "textarea" },
    { key: "image_path", label: "Изображение", type: "text", hint: "Локальный путь /assets/…" },
    { key: "level", label: "Уровень квеста", type: "number" },
    { key: "recommended_level", label: "Рекомендуемый уровень", type: "number" },
    { key: "min_level", label: "Минимальный уровень", type: "number" },
    { key: "max_level", label: "Максимальный уровень", type: "number" },
    { key: "difficulty", label: "Сложность", type: "text" },
    { key: "rarity", label: "Редкость", type: "text" },
    { key: "source_type", label: "Источник выдачи", type: "select", metaKey: "sourceTypes", hint: "NPC/доска/предмет/событие/локация/достижение/админ и т.д." },
    { key: "source_id", label: "ID источника", type: "text" },
    { key: "source_npc_id", label: "NPC-источник (id)", type: "text" },
    { key: "show_source", label: "Показывать источник игроку", type: "checkbox" },
    { key: "source_text", label: "Текст получения от источника", type: "textarea" },
    { key: "hidden", label: "Скрытый квест", type: "checkbox" },
    { key: "reveal_condition", label: "Условие открытия (для скрытых)", type: "text" },
    { key: "required_race", label: "Требуемая раса", type: "text" },
    { key: "accept_conditions", label: "Условия принятия", type: "objlist", columns: [{ key: "type", label: "Тип" }, { key: "object_id", label: "ID" }, { key: "amount", label: "Значение" }, { key: "operator", label: "Оператор" }, { key: "value", label: "Параметр" }], hint: "item/achievement/previous_quest/failed_quest/reputation/hidden_reputation/location/npc/effect/no_fine/has_fine/event_campaign/world_event/weekday" },
    { key: "stages", label: "Этапы", type: "objlist", columns: [{ key: "stage_id", label: "ID этапа" }, { key: "order", label: "№" }, { key: "name", label: "Название" }, { key: "description", label: "Описание" }, { key: "player_text", label: "Текст игроку" }, { key: "technical_description", label: "Тех. описание" }, { key: "start_conditions", label: "Условия старта" }, { key: "completion_conditions", label: "Условия завершения" }, { key: "stage_rewards", label: "Награды" }, { key: "next_stage", label: "След. этап" }, { key: "alt_stage", label: "Альт. этап" }, { key: "fail_stage", label: "Этап провала" }, { key: "hidden", label: "Скрытый" }, { key: "enabled", label: "Активен" }], hint: "ID этапов уникальны; переходы не должны образовывать цикл." },
    { key: "tasks", label: "Задачи", type: "objlist", columns: [{ key: "task_id", label: "ID" }, { key: "task_type", label: "Тип" }, { key: "target_id", label: "Цель (id)" }, { key: "target_name", label: "Название цели" }, { key: "required_count", label: "Кол-во" }, { key: "stage_id", label: "Этап" }, { key: "count_condition", label: "Условие зачёта" }, { key: "show_progress", label: "Показывать" }, { key: "hidden_progress", label: "Скрыть" }, { key: "optional", label: "Доп." }, { key: "alternative", label: "Альт." }, { key: "failure_task", label: "Провальная" }, { key: "progress_text", label: "Текст прогресса" }, { key: "complete_text", label: "Текст выполнения" }], hint: "talk_npc/kill_mob/find_item/gather_resource/deliver_item и т.д." },
    { key: "dialogs", label: "Диалоги NPC", type: "objlist", columns: [{ key: "dialogue_id", label: "ID реплики" }, { key: "npc_id", label: "NPC (id)" }, { key: "stage_id", label: "Этап" }, { key: "condition", label: "Условие" }, { key: "before_text", label: "До принятия" }, { key: "after_text", label: "После принятия" }, { key: "progress_text", label: "При прогрессе" }, { key: "complete_text", label: "При завершении" }, { key: "fail_text", label: "При провале" }, { key: "post_complete_text", label: "После завершения" }, { key: "hidden_text", label: "Скрытая реплика" }, { key: "choice_id", label: "Выбор" }, { key: "next_stage", label: "След. этап" }, { key: "reward", label: "Награда" }, { key: "consequence", label: "Последствие" }, { key: "phase", label: "Фаза" }, { key: "text", label: "Реплика" }], hint: "Фаза: before/after/progress/complete/fail." },
    { key: "quest_items", label: "Квестовые предметы", type: "objlist", columns: [{ key: "item_id", label: "Предмет (id)" }, { key: "count", label: "Кол-во" }, { key: "quality", label: "Качество" }, { key: "give_on_accept", label: "Выдать" }, { key: "take_on_complete", label: "Забрать в конце" }, { key: "take_on_fail", label: "Забрать при провале" }, { key: "transform_to_item_id", label: "Превратить в ID" }, { key: "open_access_id", label: "Открыть доступ" }, { key: "craft_recipe_id", label: "Создать ремеслом" }, { key: "bound", label: "Привязан" }, { key: "cannot_drop", label: "Нельзя выбросить" }, { key: "cannot_transfer", label: "Нельзя передать" }, { key: "hidden", label: "Скрыт" }, { key: "receive_text", label: "Получение" }, { key: "loss_text", label: "Потеря" }] },
    { key: "choices", label: "Выборы и ветвления", type: "objlist", columns: [{ key: "choice_id", label: "ID" }, { key: "text", label: "Текст выбора" }, { key: "condition", label: "Условие" }, { key: "next_stage", label: "След. этап" }, { key: "next_quest", label: "След. квест" }, { key: "rewards", label: "Награды" }, { key: "losses", label: "Потери" }, { key: "reputation_id", label: "Репутация ID" }, { key: "reputation_change", label: "Δ репутации" }, { key: "hidden_reputation_id", label: "Скрытая реп." }, { key: "hidden_reputation_change", label: "Δ скрытой" }, { key: "consequence", label: "Последствие" }, { key: "block_other_path", label: "Блок пути" }, { key: "remember_choice", label: "Запомнить" }, { key: "show_consequences", label: "Показать последствия" }, { key: "hide_consequences", label: "Скрыть последствия" }, { key: "result_text", label: "Результат" }] },
    { key: "completion_conditions", label: "Условия завершения (по строкам)", type: "list", hint: "Обязательно хотя бы одно: all_tasks_done / npc_confirm / items_delivered и т.д." },
    { key: "rewards", label: "Награды", type: "objlist", columns: [{ key: "type", label: "Тип" }, { key: "object_id", label: "ID объекта" }, { key: "count", label: "Кол-во" }, { key: "quality", label: "Качество" }, { key: "formula_id", label: "Формула" }, { key: "grant_timing", label: "Когда" }, { key: "delivery_mode", label: "Куда" }, { key: "text", label: "Текст" }], hint: "item/currency/exp/skill/effect/achievement/reputation/recipe и т.д." },
    { key: "can_fail", label: "Квест может провалиться", type: "checkbox" },
    { key: "fail_consequences", label: "Последствия провала", type: "objlist", columns: [{ key: "type", label: "Тип" }, { key: "object_id", label: "ID" }, { key: "amount", label: "Количество" }, { key: "text", label: "Текст" }] },
    { key: "fail_on_deadline", label: "Провал по сроку", type: "checkbox" }, { key: "fail_on_death", label: "Провал по смерти", type: "checkbox" }, { key: "fail_on_choice", label: "Провал по выбору", type: "checkbox" }, { key: "fail_on_item_loss", label: "Провал по потере предмета", type: "checkbox" }, { key: "fail_on_npc_death", label: "Провал по смерти NPC", type: "checkbox" }, { key: "fail_on_fine", label: "Провал по штрафу", type: "checkbox" }, { key: "fail_on_reputation", label: "Провал по репутации", type: "checkbox" }, { key: "repeat_after_fail", label: "Повтор после провала", type: "checkbox" },
    { key: "repeat_mode", label: "Повторяемость", type: "select", metaKey: "repeatModes" },
    { key: "repeat_cooldown_seconds", label: "Кулдаун повтора (сек)", type: "number" },
    { key: "repeat_count", label: "Количество повторов", type: "number" },
    { key: "deadline_seconds", label: "Срок выполнения (сек)", type: "number" },
    { key: "start_at", label: "Дата начала ISO", type: "text" }, { key: "end_at", label: "Дата окончания ISO", type: "text" }, { key: "reset_progress", label: "Сбрасывать прогресс", type: "checkbox" }, { key: "preserve_progress_percent", label: "Сохранять прогресс, %", type: "number" },
    { key: "timer_text", label: "Текст таймера", type: "text" },
    { key: "appear_text", label: "Текст появления", type: "text" },
    { key: "accept_text", label: "Текст принятия", type: "text" },
    { key: "decline_text", label: "Текст отказа", type: "text" },
    { key: "complete_text", label: "Текст завершения", type: "text" },
    { key: "reward_text", label: "Текст награды", type: "text" },
    { key: "fail_text", label: "Текст провала", type: "text" },
    { key: "stage_text", label: "Общий текст этапа", type: "text" }, { key: "task_text", label: "Общий текст задачи", type: "text" }, { key: "progress_text", label: "Общий текст прогресса", type: "text" }, { key: "task_complete_text", label: "Выполнение задачи", type: "text" }, { key: "unavailable_text", label: "Недоступность", type: "text" }, { key: "missing_item_text", label: "Не хватает предмета", type: "text" }, { key: "wrong_npc_text", label: "Неверный NPC", type: "text" }, { key: "wrong_location_text", label: "Неверная локация", type: "text" }, { key: "repeat_text", label: "Повторное прохождение", type: "text" }, { key: "reveal_text", label: "Открытие скрытого", type: "text" },
    { key: "buttons", label: "Кнопки квеста", type: "objlist", columns: [{ key: "action", label: "Действие" }, { key: "text", label: "Текст" }, { key: "emoji", label: "Эмодзи" }, { key: "condition", label: "Условие" }, { key: "enabled", label: "Активна" }, { key: "error_text", label: "Ошибка" }] },
    { key: "admin_notes", label: "Заметки админа", type: "textarea" },
  ],
};
const TRAIT_CONFIG = {
  base: "traits", title: "Конструктор черт мобов", permPrefix: "trait",
  newLabel: "Новая черта", nameField: "trait_name",
  supportsImport: true,
  importLabel: "Импортировать библиотеку черт?", importText: "50 универсальных черт будут заведены как опубликованные записи (без дублей).",
  fields: [
    { key: "trait_name", label: "Название", type: "text", hint: "Короткое имя черты, видно админу в списках. Обязательное поле." },
    { key: "trait_rank", label: "Ранг", type: "select", metaKey: "traitRanks", hint: "Особая/элитная/уникальная/мировая — ограничивает, каким мобам по рангу доступна черта." },
    { key: "trigger", label: "Триггер", type: "select", metaKey: "triggers", hint: "Когда срабатывает: пассивно, при атаке, при получении урона, в начале боя и т.д." },
    { key: "stack_rule", label: "Правило стака", type: "select", metaKey: "stackRules", hint: "Как складываются несколько одинаковых черт: сильнейшая, обновление, суммирование." },
    { key: "player_text", label: "Текст для игрока", type: "textarea", hint: "Что увидит игрок в бою. Без формул и технических деталей." },
    { key: "admin_description", label: "Описание для админа", type: "textarea", hint: "Техническое пояснение механики — игроку не показывается." },
    { key: "applicable_mob_categories", label: "Категории мобов", type: "multiselect", metaKey: "mobCategories", hint: "К каким категориям мобов применима черта. Пусто = без ограничений." },
  ],
};
const BLESSING_CONFIG = {
  base: "blessings", title: "Конструктор благословений", permPrefix: "blessing",
  newLabel: "Новое благословение", nameField: "blessing_name",
  supportsImport: true,
  importLabel: "Импортировать библиотеку благословений?", importText: "19 благословений будут заведены как опубликованные записи (без дублей).",
  fields: [
    { key: "blessing_name", label: "Название", type: "text" },
    { key: "source_type", label: "Источник", type: "select", metaKey: "sourceTypes" },
    { key: "stack_rule", label: "Правило стака", type: "select", metaKey: "stackRules" },
    { key: "allowed_targets", label: "Цели", type: "multiselect", metaKey: "allowedTargets" },
    { key: "player_text", label: "Текст для игрока", type: "textarea" },
    { key: "bonus_values", label: "Бонусы", type: "numbergroup", sub: [{ key: "flat_bonus", label: "Плоский" }, { key: "percent_bonus", label: "%" }, { key: "duration_seconds", label: "Длит. (сек)" }] },
  ],
};
const PHASE_CONFIG = {
  base: "phases", title: "Конструктор фаз боссов", permPrefix: "phase",
  newLabel: "Новая фаза", nameField: "phase_name",
  supportsImport: true,
  importLabel: "Импортировать библиотеку фаз?", importText: "20 универсальных фаз боссов будут заведены как опубликованные записи (без дублей).",
  fields: [
    { key: "phase_name", label: "Название", type: "text" },
    { key: "trigger_type", label: "Тип триггера", type: "select", metaKey: "triggerTypes" },
    { key: "trigger_value", label: "Значение триггера", type: "number" },
    { key: "allowed_boss_ranks", label: "Ранги боссов", type: "multiselect", metaKey: "bossRanks" },
    { key: "phase_text_for_player", label: "Текст для игрока", type: "textarea" },
    { key: "phase_admin_notes", label: "Заметки админа", type: "textarea" },
  ],
};
const _STAT_SUB = [
  { key: "strength", label: "Сила" }, { key: "endurance", label: "Выносл." },
  { key: "agility", label: "Ловк." }, { key: "perception", label: "Воспр." },
  { key: "intelligence", label: "Интел." }, { key: "wisdom", label: "Мудр." },
];
const LEVEL_CONFIG = {
  base: "levels", title: "Конструктор уровней и опыта", permPrefix: "level",
  newLabel: "Новый уровень", nameField: "title",
  fields: [
    { key: "entity_type", label: "Тип записи", type: "select", metaKey: "entityTypes" },
    { key: "title", label: "Заголовок", type: "text", hint: "Название уровня (например «Уровень 5»). Видно админу." },
    { key: "system_name", label: "Системное название", type: "text" }, { key: "active_rule", label: "Активное правило прогрессии", type: "checkbox" }, { key: "priority", label: "Приоритет", type: "number" },
    { key: "start_level", label: "Стартовый уровень", type: "number" }, { key: "start_experience", label: "Стартовый опыт", type: "number" }, { key: "max_level", label: "Максимальный уровень", type: "number" }, { key: "temporary_level_cap", label: "Временный кап", type: "number" },
    { key: "use_level_table", label: "Использовать таблицу", type: "checkbox" }, { key: "use_level_formula", label: "Использовать формулу", type: "checkbox" }, { key: "formula_id", label: "Формула общей кривой", type: "formularef" },
    { key: "level", label: "Уровень", type: "number", hint: "Числовой номер уровня. Должен быть уникальным." },
    { key: "exp_required", label: "Опыт до уровня", type: "number", hint: "Сколько опыта нужно набрать, чтобы достичь этого уровня. Можно задать формулой ниже." },
    { key: "stat_points", label: "Очки характеристик", type: "number", hint: "Сколько очков характеристик выдаётся за достижение уровня." },
    { key: "skill_points", label: "Очки навыков", type: "number", hint: "Сколько очков навыков выдаётся за достижение уровня." },
    { key: "stat_points_per_level", label: "Очков характеристик за уровень", type: "number" }, { key: "skill_points_per_level", label: "Очков навыков за уровень (стандарт 2)", type: "number" },
    { key: "stat_points_formula_id", label: "Формула очков характеристик", type: "formularef" }, { key: "skill_points_formula_id", label: "Формула очков навыков", type: "formularef" },
    { key: "rewards", label: "Награды уровня", type: "objlist", columns: [{key:"type",label:"currency/item/energy/location/skill/quest/achievement/effect"},{key:"object_id",label:"ID"},{key:"amount",label:"Количество"}] },
    { key: "unlocks", label: "Разблокировки", type: "list" },
    { key: "death_exp_loss_enabled", label: "Потеря опыта при смерти", type: "checkbox" }, { key: "death_loss_percent", label: "Потеря при смерти, %", type: "number" }, { key: "death_loss_from_current", label: "Считать от текущего опыта", type: "checkbox" },
    { key: "death_loss_min", label: "Минимальная потеря", type: "number" }, { key: "death_loss_max", label: "Максимальная потеря", type: "number" }, { key: "death_loss_formula_id", label: "Формула потери", type: "formularef" },
    { key: "accumulate_exp_after_cap", label: "Копить опыт после капа", type: "checkbox" }, { key: "burn_exp_after_cap", label: "Сжигать опыт после капа", type: "checkbox" }, { key: "convert_exp_after_cap", label: "Конвертировать опыт после капа", type: "checkbox" },
    { key: "migration_required", label: "Миграция существующих игроков проверена", type: "checkbox" },
    ...[["gain_exp_text","Получение опыта"],["not_enough_exp_text","Нехватка опыта"],["level_up_text","Повышение уровня"],["stat_points_text","Получение очков характеристик"],["skill_points_text","Получение очков навыков"],["penalty_text","Штраф опыта"],["death_loss_text","Потеря опыта при смерти"],["max_level_text","Максимальный уровень"],["level_cap_text","Кап уровня"]].map(([key,label])=>({key,label,type:"textarea"})),
    { key: "exp_formula_id", label: "Формула опыта (ТЗ 13 §2.8)", type: "formularef", hint: "Если задана, опыт до уровня считается формулой из конструктора формул, а не фиксированным числом." },
    { key: "description", label: "Описание", type: "textarea", hint: "Необязательное пояснение для админа." },
  ],
};
const EXP_CONFIG = {
  base: "exp", title: "Конструктор опыта", permPrefix: "exp",
  newLabel: "Новый источник опыта", nameField: "name",
  fields: [
    { key: "name", label: "Название", type: "text", hint: "Имя источника опыта (например «Победа над мобом»)." },
    { key: "source_type", label: "Тип источника", type: "select", metaKey: "sourceTypes", hint: "Откуда начисляется опыт: бой, поиск, ремесло, задание и т.д." },
    { key: "base_exp", label: "Базовый опыт", type: "number", hint: "Базовое количество опыта за событие до масштабирования." },
    { key: "source_id", label: "ID конкретного источника", type: "text" }, { key: "min_exp", label: "Минимум", type: "number" }, { key: "max_exp", label: "Максимум", type: "number" },
    { key: "use_player_level", label: "Учитывать уровень игрока", type: "checkbox" }, { key: "use_mob_level", label: "Учитывать уровень моба", type: "checkbox" }, { key: "use_penalties", label: "Учитывать штрафы", type: "checkbox" }, { key: "use_effects", label: "Учитывать эффекты", type: "checkbox" }, { key: "use_race", label: "Учитывать расу", type: "checkbox" }, { key: "show_player", label: "Показывать игроку", type: "checkbox" },
    { key: "penalty_after_level", label: "Штраф после уровня", type: "number" }, { key: "penalty_percent", label: "Штраф, %", type: "number" },
    { key: "level_scaling_percent", label: "Масштаб по уровню, %", type: "number", hint: "На сколько % меняется опыт с ростом уровня игрока/цели." },
    { key: "formula_id", label: "Формула (ТЗ 13 §2.8)", type: "formularef", hint: "Если задана, опыт считается формулой, а базовое значение/масштаб игнорируются." },
    { key: "notes", label: "Заметки", type: "textarea", hint: "Пояснение для админа, игроку не показывается." },
  ],
};
const REGISTRATION_CONFIG = {
  base: "registration", title: "Конструктор регистрации", permPrefix: "registration",
  newLabel: "Новый сценарий/шаг", nameField: "name",
  fields: [
    { key: "entity_type", label: "Тип записи", type: "select", metaKey: "entityTypes" },
    { key: "name", label: "Название сценария", type: "text" }, { key: "system_name", label: "Системное название", type: "text" },
    { key: "active", label: "Активный сценарий", type: "checkbox" }, { key: "telegram_enabled", label: "Использовать в Telegram", type: "checkbox" }, { key: "vk_enabled", label: "Использовать во VK", type: "checkbox" }, { key: "test_enabled", label: "Тестовый сценарий", type: "checkbox" },
    { key: "registration_enabled", label: "Регистрация включена", type: "checkbox" }, { key: "closed_text", label: "Текст закрытой регистрации", type: "textarea" }, { key: "priority", label: "Приоритет", type: "number" },
    { key: "label", label: "Подпись шага", type: "text" },
    { key: "step_type", label: "Тип шага", type: "select", metaKey: "stepTypes" },
    { key: "order", label: "Порядок", type: "number" },
    { key: "required", label: "Обязательный шаг", type: "checkbox" },
    { key: "text", label: "Текст", type: "textarea" },
    { key: "steps", label: "Шаги сценария", type: "objlist", columns: [{ key: "id", label: "ID" }, { key: "label", label: "Название" }, { key: "step_type", label: "Тип" }, { key: "order", label: "Порядок" }, { key: "text", label: "Текст" }, { key: "buttons", label: "Кнопки" }, { key: "required", label: "Обязательный" }, { key: "skippable", label: "Можно пропустить" }, { key: "condition", label: "Условие" }, { key: "after_action", label: "Действие после" }, { key: "error_text", label: "Ошибка" }] },
    { key: "auto_generate_nt_id", label: "Генерировать NT-ID", type: "checkbox" }, { key: "allow_admin_nt_id", label: "Ручной NT-ID админом", type: "checkbox" }, { key: "check_duplicates", label: "Проверять дубли", type: "checkbox" }, { key: "allow_telegram_link", label: "Привязка Telegram", type: "checkbox" }, { key: "allow_vk_link", label: "Привязка VK", type: "checkbox" }, { key: "profile_recovery_method", label: "Восстановление профиля", type: "text" },
    { key: "name_required", label: "Имя обязательно", type: "checkbox" }, { key: "name_min_length", label: "Мин. длина имени", type: "number" }, { key: "name_max_length", label: "Макс. длина имени", type: "number" }, { key: "forbidden_name_chars", label: "Запрещённые символы", type: "list" }, { key: "forbidden_names", label: "Запрещённые слова", type: "list" }, { key: "unique_name", label: "Уникальное имя", type: "checkbox" }, { key: "allow_name_change", label: "Разрешить смену имени", type: "checkbox" }, { key: "name_change_cost", label: "Цена смены имени", type: "number" },
    { key: "race_required", label: "Выбор расы обязателен", type: "checkbox" }, { key: "race_skippable", label: "Расу можно пропустить", type: "checkbox" }, { key: "default_race_id", label: "Раса по умолчанию", type: "text" }, { key: "available_races", label: "Доступные расы", type: "list" }, { key: "show_race_description", label: "Показывать описание расы", type: "checkbox" }, { key: "show_race_bonuses", label: "Показывать бонусы", type: "checkbox" }, { key: "hide_exact_bonus_values", label: "Скрывать точные бонусы", type: "checkbox" }, { key: "confirm_race", label: "Подтверждать выбор расы", type: "checkbox" }, { key: "forbid_race_change", label: "Запрет смены после регистрации", type: "checkbox" },
    { key: "starting_items", label: "Стартовые предметы", type: "objlist", columns: [{ key: "item_id", label: "ID" }, { key: "amount", label: "Количество" }, { key: "quality", label: "Качество" }, { key: "bind", label: "Привязать" }, { key: "delivery_mode", label: "Инвентарь/доставка/перегруз" }, { key: "condition", label: "Условие" }, { key: "race_id", label: "Раса" }, { key: "platform", label: "Платформа" }, { key: "referral", label: "Реферал" }, { key: "text", label: "Текст" }] },
    { key: "starting_skills", label: "Стартовые навыки", type: "objlist", columns: [{ key: "skill_id", label: "ID" }, { key: "all_players", label: "Всем" }, { key: "race_id", label: "Раса" }, { key: "branch", label: "Ветка" }, { key: "temporary", label: "Временно" }, { key: "permanent", label: "Постоянно" }, { key: "show_profile", label: "В профиле" }, { key: "text", label: "Текст" }] },
    { key: "start_city_id", label: "Стартовый город", type: "text" }, { key: "start_location_id", label: "Стартовая локация", type: "text" }, { key: "start_sublocation_id", label: "Стартовая подлокация", type: "text" }, { key: "start_camp_id", label: "Стартовый лагерь", type: "text" }, { key: "start_button_id", label: "Стартовая кнопка", type: "text" }, { key: "start_message", label: "Стартовое сообщение", type: "textarea" },
    { key: "referral_enabled", label: "Принимать реферальный код", type: "checkbox" }, { key: "referral_anti_fraud", label: "Антинакрутка", type: "checkbox" },
    ...[["welcome_text", "Приветствие"], ["existing_profile_text", "Уже зарегистрирован"], ["profile_creation_text", "Создание профиля"], ["name_prompt_text", "Выбор имени"], ["name_error_text", "Ошибка имени"], ["race_prompt_text", "Выбор расы"], ["race_description_text", "Описание расы"], ["race_confirmation_text", "Подтверждение расы"], ["referral_text", "Реферальная ссылка"], ["starting_items_text", "Стартовые предметы"], ["starting_skills_text", "Стартовые навыки"], ["starting_location_text", "Стартовая локация"], ["complete_text", "Завершение"], ["registration_error_text", "Ошибка регистрации"], ["technical_error_text", "Техническая ошибка"]].map(([key, label]) => ({ key, label, type: "textarea" })),
  ],
};
const RACE_CONFIG = {
  base: "races", title: "Конструктор рас", permPrefix: "race",
  newLabel: "Новая раса", nameField: "race_name",
  supportsImport: true,
  importLabel: "Импортировать существующие расы?", importText: "Расы из data/races.json будут заведены как опубликованные записи (без дублей).",
  fields: [
    { key: "race_name", label: "Название", type: "text", hint: "Имя расы, видно игроку при регистрации. Обязательное поле." },
    { key: "player_name", label: "Название для игрока", type: "text" },
    { key: "system_name", label: "Системное название", type: "text" },
    { key: "description", label: "Описание", type: "textarea", hint: "Краткое описание расы для игрока." },
    { key: "full_description", label: "Полное описание", type: "textarea" },
    { key: "lore", label: "Лор", type: "textarea", hint: "Расширенный лор/история расы (необязательно)." },
    { key: "technical_description", label: "Техническое описание", type: "textarea" },
    { key: "icon", label: "Иконка", type: "text" },
    { key: "model_image", label: "Изображение модели (/assets/…)", type: "text", hint: "Локальный путь к картинке (/assets/…). Внешние ссылки запрещены — загрузите файл." },
    { key: "playable", label: "Доступна для игры", type: "checkbox", hint: "Если выключено — раса недоступна при регистрации новых игроков." },
    { key: "registration_enabled", label: "Доступна при регистрации", type: "checkbox" },
    { key: "hidden", label: "Скрытая раса", type: "checkbox" },
    { key: "special", label: "Особая раса", type: "checkbox" },
    { key: "admin_only", label: "Только админская выдача", type: "checkbox" },
    { key: "display_order", label: "Порядок отображения", type: "number" },
    { key: "tags", label: "Теги", type: "list" },
    { key: "stat_bonuses", label: "Бонусы характеристик", type: "numbergroup", sub: _STAT_SUB, hint: "Прибавки к характеристикам от расы (могут быть отрицательными)." },
    { key: "starting_stats", label: "Стартовые характеристики", type: "numbergroup", sub: _STAT_SUB, hint: "Базовые значения характеристик на старте для этой расы." },
    { key: "start_hp", label: "Стартовое здоровье", type: "number" }, { key: "start_mana", label: "Стартовая мана", type: "number" }, { key: "start_spirit", label: "Стартовый дух", type: "number" }, { key: "start_energy", label: "Стартовая энергия", type: "number" },
    { key: "accuracy", label: "Точность", type: "number" }, { key: "dodge", label: "Уклонение", type: "number" }, { key: "crit_chance", label: "Шанс крита", type: "number" }, { key: "crit_damage", label: "Урон крита", type: "number" },
    { key: "physical_defense", label: "Физическая защита", type: "number" }, { key: "magic_defense", label: "Магическая защита", type: "number" }, { key: "armor", label: "Броня", type: "number" }, { key: "physical_damage", label: "Физический урон", type: "number" }, { key: "magic_damage", label: "Магический урон", type: "number" },
    { key: "bonuses", label: "Расовые бонусы", type: "objlist", columns: [{ key: "id", label: "ID" }, { key: "name", label: "Название" }, { key: "description", label: "Описание" }, { key: "type", label: "Тип" }, { key: "target", label: "Цель/параметр" }, { key: "effect_id", label: "Эффект" }, { key: "formula_id", label: "Формула" }, { key: "value", label: "Значение" }, { key: "percent", label: "%" }, { key: "condition", label: "Условие" }, { key: "chance", label: "Шанс" }, { key: "duration_seconds", label: "Длительность" }, { key: "context", label: "Контекст" }, { key: "show_player", label: "Показывать" }, { key: "hide_value", label: "Скрыть значение" }] },
    { key: "forbidden_skills", label: "Запрещённые навыки", type: "list" }, { key: "forbidden_items", label: "Запрещённые предметы", type: "list" }, { key: "forbidden_locations", label: "Запрещённые локации", type: "list" }, { key: "forbidden_quests", label: "Запрещённые квесты", type: "list" },
    { key: "npc_relations", label: "Отношения NPC", type: "objlist", columns: [{ key: "npc_id", label: "NPC" }, { key: "value", label: "Значение" }] }, { key: "reputation_changes", label: "Изменения репутации", type: "objlist", columns: [{ key: "reputation_id", label: "Репутация" }, { key: "value", label: "Значение" }] },
    { key: "effect_weaknesses", label: "Слабости к эффектам", type: "list" }, { key: "effect_resistances", label: "Сопротивления эффектам", type: "list" }, { key: "special_penalties", label: "Особые штрафы", type: "list" }, { key: "registration_conditions", label: "Условия регистрации", type: "list" },
    { key: "change_allowed", label: "Смена расы разрешена", type: "checkbox" }, { key: "change_via_admin", label: "Смена через админку", type: "checkbox" }, { key: "change_via_item", label: "Смена через предмет", type: "checkbox" }, { key: "change_via_quest", label: "Смена через квест", type: "checkbox" }, { key: "change_via_service", label: "Смена через услугу", type: "checkbox" },
    { key: "change_cost", label: "Стоимость смены", type: "number" }, { key: "reset_old_bonuses", label: "Снять бонусы старой расы", type: "checkbox" }, { key: "apply_new_bonuses", label: "Применить бонусы новой расы", type: "checkbox" }, { key: "preserve_progress", label: "Сохранить прогресс", type: "checkbox" }, { key: "reset_progress_percent", label: "Сброс прогресса, %", type: "number" },
    { key: "change_warning_text", label: "Крупное предупреждение о смене", type: "textarea" }, { key: "change_requires_confirmation", label: "Требовать подтверждение", type: "checkbox" }, { key: "change_success_text", label: "Текст успешной смены", type: "textarea" }, { key: "change_denied_text", label: "Текст запрета смены", type: "textarea" },
  ],
};
const PROFESSION_CONFIG = {
  base: "professions", title: "Конструктор профессий", permPrefix: "profession",
  newLabel: "Новая профессия", nameField: "name",
  fields: [
    { key: "name", label: "Название", type: "text" },
    { key: "profession_type", label: "Тип профессии", type: "select", metaKey: "professionTypes" },
    { key: "description", label: "Описание", type: "textarea" },
    { key: "max_level", label: "Максимальный уровень", type: "number" },
    { key: "start_level", label: "Стартовый уровень", type: "number" },
    { key: "exp_formula_id", label: "Формула опыта", type: "formularef" },
    { key: "next_level_formula_id", label: "Формула опыта до след. уровня", type: "formularef" },
    { key: "rewards_per_level", label: "Награды за уровень (по строкам)", type: "list" },
    { key: "unlocked_recipes", label: "Открываемые рецепты (id по строкам)", type: "list" },
    { key: "workshops", label: "Мастерские (id по строкам)", type: "list" },
  ],
};
const WORKSHOP_CONFIG = {
  base: "workshops", title: "Конструктор мастерских", permPrefix: "workshop",
  newLabel: "Новая мастерская", nameField: "name",
  fields: [
    { key: "name", label: "Название", type: "text" },
    { key: "player_name", label: "Название для игрока", type: "text" },
    { key: "system_name", label: "Системное название", type: "text" },
    { key: "button_text", label: "Текст кнопки открытия", type: "text" },
    { key: "type", label: "Тип мастерской", type: "select", metaKey: "workshopTypes" },
    { key: "runtime_workshop", label: "Совместимый игровой процесс", type: "select", metaKey: "workshopTypes" },
    { key: "location", label: "Локация (id)", type: "text" },
    { key: "locations", label: "Дополнительные локации", type: "list" },
    { key: "parent_sublocation", label: "Подлокация (id)", type: "text" },
    { key: "camp_id", label: "Лагерь (id)", type: "text" },
    { key: "owner_npc_id", label: "NPC-владелец", type: "text" },
    { key: "city", label: "Город (id)", type: "text" },
    { key: "fortress", label: "Крепость (id)", type: "text" },
    { key: "available", label: "Доступна", type: "checkbox" },
    { key: "access_condition", label: "Условие доступа", type: "text" },
    { key: "min_level", label: "Минимальный уровень", type: "number" },
    { key: "required_item_id", label: "Требуемый предмет", type: "text" },
    { key: "required_quest_id", label: "Требуемый квест", type: "text" },
    { key: "required_achievement_id", label: "Требуемое достижение", type: "text" },
    { key: "required_reputation_id", label: "Требуемая репутация", type: "text" },
    { key: "min_reputation", label: "Минимум репутации", type: "number" },
    { key: "requires_no_fine", label: "Требуется отсутствие штрафа", type: "checkbox" },
    { key: "access_denied_text", label: "Текст отказа", type: "textarea" },
    { key: "use_cost", label: "Стоимость использования", type: "number" },
    { key: "work_time", label: "Время работы (сек)", type: "number" },
    { key: "professions", label: "Профессии (id по строкам)", type: "list" },
    { key: "recipes", label: "Рецепты (id по строкам)", type: "list" },
    { key: "description", label: "Описание", type: "textarea" },
    { key: "short_description", label: "Краткое описание", type: "textarea" },
    { key: "technical_description", label: "Техническое описание", type: "textarea" },
    { key: "effect_ids", label: "Эффекты мастерской (ID по строкам)", type: "list" },
    { key: "tags", label: "Теги", type: "list" },
    { key: "image", label: "Изображение (/assets/…)", type: "text" },
  ],
};
const CRAFT_MATERIAL_GROUP_CONFIG = {
  base: "craft-material-groups", title: "Группы материалов", permPrefix: "recipe",
  newLabel: "Новая группа материалов", nameField: "name",
  fields: [
    { key: "name", label: "Название", type: "text" },
    { key: "description", label: "Описание", type: "textarea" },
    { key: "item_ids", label: "Предметы (ID по строкам)", type: "list" },
    { key: "categories", label: "Категории предметов", type: "list" },
    { key: "item_types", label: "Типы предметов", type: "list" },
    { key: "allowed_qualities", label: "Разрешённые качества", type: "list" },
    { key: "forbidden_qualities", label: "Запрещённые качества", type: "list" },
    { key: "min_item_level", label: "Минимальный уровень", type: "number" },
    { key: "max_item_level", label: "Максимальный уровень", type: "number" },
  ],
};
const UPGRADE_CONFIG = {
  base: "upgrades", title: "Конструктор улучшения", permPrefix: "recipe",
  newLabel: "Новое правило улучшения", nameField: "name",
  fields: [
    { key: "name", label: "Название", type: "text" },
    { key: "upgrade_type", label: "Тип улучшения", type: "select", metaKey: "upgradeTypes" },
    { key: "target_item_type", label: "Тип предмета (ограничение)", type: "text" },
    { key: "result_effect", label: "Эффект результата", type: "effectref" },
    { key: "upgrade_formula_id", label: "Формула шанса улучшения", type: "formularef" },
    { key: "break_risk_formula_id", label: "Формула риска поломки", type: "formularef" },
    { key: "success_chance", label: "Шанс успеха %", type: "number" },
    { key: "break_risk", label: "Риск поломки %", type: "number" },
    { key: "material_loss_risk", label: "Риск потери материала %", type: "number" },
    { key: "extra_effect_chance", label: "Шанс доп. эффекта %", type: "number" },
    { key: "materials", label: "Материалы (id по строкам)", type: "list" },
    { key: "description", label: "Описание", type: "textarea" },
  ],
};
const ENCHANT_CONFIG = {
  base: "enchants", title: "Конструктор зачарования", permPrefix: "recipe",
  newLabel: "Новое зачарование", nameField: "name",
  fields: [
    { key: "name", label: "Название", type: "text" },
    { key: "enchant_effect", label: "Эффект зачарования", type: "effectref" },
    { key: "enchant_formula_id", label: "Формула шанса зачарования", type: "formularef" },
    { key: "purify_formula_id", label: "Формула шанса очищения", type: "formularef" },
    { key: "break_risk_formula_id", label: "Формула риска поломки", type: "formularef" },
    { key: "clear_enchant", label: "Очистка зачарования", type: "checkbox" },
    { key: "target_item_type", label: "Тип предмета (ограничение)", type: "text" },
    { key: "success_chance", label: "Шанс успеха %", type: "number" },
    { key: "break_risk", label: "Риск поломки %", type: "number" },
    { key: "extra_effect_chance", label: "Шанс доп. эффекта %", type: "number" },
    { key: "materials", label: "Материалы (id по строкам)", type: "list" },
    { key: "description", label: "Описание", type: "textarea" },
  ],
};
const DISASSEMBLE_CONFIG = {
  base: "disassembles", title: "Конструктор разборки", permPrefix: "recipe",
  newLabel: "Новое правило разборки", nameField: "name",
  fields: [
    { key: "name", label: "Название", type: "text" },
    { key: "source_item_id", label: "Разбираемый предмет (id)", type: "text" },
    { key: "outputs", label: "Что можно получить (id по строкам)", type: "list" },
    { key: "output_chance", label: "Шанс получения %", type: "number" },
    { key: "success_formula_id", label: "Формула успешного разбора", type: "formularef" },
    { key: "depends_on_quality", label: "Зависит от качества", type: "checkbox" },
    { key: "depends_on_level", label: "Зависит от уровня", type: "checkbox" },
    { key: "requires_workshop", label: "Нужна мастерская (id)", type: "text" },
    { key: "requires_tool", label: "Нужен инструмент (id)", type: "text" },
    { key: "gives_exp", label: "Ремесленный опыт", type: "number" },
    { key: "success_text", label: "Текст успеха", type: "textarea" },
    { key: "fail_text", label: "Текст провала", type: "textarea" },
  ],
};
const REPAIR_CONFIG = {
  base: "repairs", title: "Конструктор ремонта", permPrefix: "recipe",
  newLabel: "Новое правило ремонта", nameField: "name",
  fields: [
    { key: "name", label: "Название", type: "text" },
    { key: "target_item_type", label: "Тип предмета", type: "text" },
    { key: "repair_percent", label: "Восстановить прочности %", type: "number" },
    { key: "repair_formula_id", label: "Формула объёма ремонта", type: "formularef" },
    { key: "success_formula_id", label: "Формула шанса ремонта", type: "formularef" },
    { key: "break_risk_formula_id", label: "Формула риска поломки", type: "formularef" },
    { key: "success_chance", label: "Шанс успеха %", type: "number" },
    { key: "break_risk", label: "Риск поломки %", type: "number" },
    { key: "materials", label: "Материалы (ID по строкам)", type: "list" },
    { key: "success_text", label: "Текст успеха", type: "textarea" },
    { key: "fail_text", label: "Текст провала", type: "textarea" },
    { key: "description", label: "Описание", type: "textarea" },
  ],
};
const ADDICTION_CONFIG = {
  base: "addictions", title: "Конструктор зависимости", permPrefix: "effect",
  newLabel: "Новая зависимость", nameField: "name_admin",
  fields: [
    { key: "name_admin", label: "Название (админ)", type: "text" },
    { key: "name_player", label: "Название (игрок)", type: "text" },
    { key: "player_text", label: "Текст игроку", type: "textarea" },
    { key: "description_admin", label: "Описание (админ)", type: "textarea" },
    { key: "addiction_scope", label: "Область", type: "select", metaKey: "scopes" },
    { key: "addiction_value_min", label: "Мин. значение", type: "number" },
    { key: "addiction_value_max", label: "Макс. значение", type: "number" },
    { key: "default_value", label: "Старт", type: "number" },
    { key: "gain_per_use", label: "Прирост за использование", type: "number" },
    { key: "decay_enabled", label: "Спад включён", type: "checkbox" },
    { key: "decay_per_day", label: "Спад в день", type: "number" },
    { key: "withdrawal_enabled", label: "Ломка включена", type: "checkbox" },
    { key: "withdrawal_delay_seconds", label: "Задержка ломки (сек)", type: "number" },
    { key: "treatment_enabled", label: "Лечение включено", type: "checkbox" },
    { key: "source_tags", label: "Теги источника (по строкам)", type: "list" },
    { key: "source_item_ids", label: "Предметы-источники (id по строкам)", type: "list" },
    { key: "stages", label: "Стадии", type: "objlist", columns: [
      { key: "stage_id", label: "id" }, { key: "name_player", label: "название" },
      { key: "min_value", label: "от" }, { key: "max_value", label: "до" },
      { key: "player_text", label: "текст игроку" },
    ] },
  ],
};
const TOLERANCE_CONFIG = {
  base: "tolerances", title: "Конструктор привыкания", permPrefix: "effect",
  newLabel: "Новое привыкание", nameField: "name_admin",
  fields: [
    { key: "name_admin", label: "Название (админ)", type: "text" },
    { key: "name_player", label: "Название (игрок)", type: "text" },
    { key: "player_text", label: "Текст игроку", type: "textarea" },
    { key: "tolerance_scope", label: "Область", type: "select", metaKey: "scopes" },
    { key: "value_min", label: "Мин. значение", type: "number" },
    { key: "value_max", label: "Макс. значение", type: "number" },
    { key: "gain_per_use", label: "Прирост за использование", type: "number" },
    { key: "gain_per_repeated_use", label: "Прирост за повтор", type: "number" },
    { key: "effectiveness_loss_per_value", label: "Потеря эффективности за ед.", type: "number" },
    { key: "min_effectiveness_percent", label: "Мин. эффективность %", type: "number" },
    { key: "max_penalty_percent", label: "Макс. штраф %", type: "number" },
    { key: "decay_enabled", label: "Спад включён", type: "checkbox" },
    { key: "decay_per_hour", label: "Спад в час", type: "number" },
    { key: "source_tags", label: "Теги источника (по строкам)", type: "list" },
    { key: "stages", label: "Стадии", type: "objlist", columns: [
      { key: "stage_id", label: "id" }, { key: "name_player", label: "название" },
      { key: "min_value", label: "от" }, { key: "max_value", label: "до" },
    ] },
  ],
};
const ECONOMY_CONFIG = {
  base: "economy", title: "Конструктор экономики", permPrefix: "economy", managePerm: "economy.manage",
  operationLogs: true,
  newLabel: "Новый экономический профиль", nameField: "name",
  fields: [
    { key: "name", label: "Название", type: "text" }, { key: "enabled", label: "Активен", type: "checkbox" },
    { key: "priority", label: "Приоритет", type: "number" }, { key: "price_mode", label: "Режим цен", type: "select", metaKey: "priceModes" },
    { key: "currencies", label: "Валюты", type: "objlist", columns: [{ key: "code", label: "ID" }, { key: "name", label: "Название" }, { key: "player_name", label: "Игроку" }, { key: "short_name", label: "Коротко" }, { key: "system_name", label: "Системное" }, { key: "symbol", label: "Символ" }, { key: "currency_type", label: "Тип" }, { key: "copper_rate", label: "Курс к меди" }, { key: "min_value", label: "Мин." }, { key: "max_value", label: "Макс." }, { key: "allow_negative", label: "Минус" }, { key: "rounding", label: "Округление" }, { key: "display_format", label: "Формат" }, { key: "display_order", label: "Порядок" }, { key: "show_player", label: "Игроку" }, { key: "admin_grant", label: "Админ +" }, { key: "admin_debit", label: "Админ −" }, { key: "transferable", label: "Передача" }, { key: "market_allowed", label: "Рынок" }, { key: "npc_allowed", label: "NPC" }, { key: "log_operations", label: "Лог" }] },
    { key: "exchange_rates", label: "Курсы валют", type: "objlist", columns: [{key:"rate_id",label:"ID"},{key:"source_currency",label:"Из"},{key:"target_currency",label:"В"},{key:"rate",label:"Коэффициент"},{key:"floating",label:"Плавающий"},{key:"formula_id",label:"Формула"},{key:"min_rate",label:"Мин."},{key:"max_rate",label:"Макс."},{key:"commission_percent",label:"Комиссия %"},{key:"active",label:"Активен"},{key:"success_text",label:"Текст"},{key:"error_text",label:"Ошибка"}] },
    { key: "price_rules", label: "Правила цен предметов", type: "objlist", columns: [{key:"rule_id",label:"ID"},{key:"item_id",label:"Предмет"},{key:"buy_price",label:"Покупка"},{key:"sell_price",label:"Продажа"},{key:"buy_currency",label:"Валюта покупки"},{key:"sell_currency",label:"Валюта продажи"},{key:"formula_id",label:"Формула"},{key:"quality_multiplier",label:"Качество"},{key:"level_multiplier",label:"Уровень"},{key:"reputation_id",label:"Репутация"}] },
    { key: "markets", label: "Рынки и ассортимент", type: "objlist", columns: [{key:"market_id",label:"ID"},{key:"name",label:"Название"},{key:"player_name",label:"Игроку"},{key:"system_name",label:"Системное"},{key:"market_type",label:"Тип"},{key:"location_id",label:"Локация"},{key:"sublocation_id",label:"Подлокация"},{key:"npc_id",label:"NPC"},{key:"short_description",label:"Кратко"},{key:"description",label:"Описание"},{key:"technical_description",label:"Техническое"},{key:"image",label:"Изображение"},{key:"icon",label:"Иконка"},{key:"items",label:"Ассортимент JSON"},{key:"use_charges",label:"Заряды"},{key:"max_charges",label:"Макс. зарядов"},{key:"current_charges",label:"Текущие"},{key:"buy_charge_cost",label:"Заряд покупки"},{key:"sell_charge_cost",label:"Заряд продажи"},{key:"charge_restore_amount",label:"Восстановление"},{key:"charge_restore_seconds",label:"Период зарядов"},{key:"no_charges_text",label:"Нет зарядов"},{key:"rotation_enabled",label:"Ротация"},{key:"rotation_mode",label:"Режим ротации"},{key:"rotation_seconds",label:"Частота"},{key:"rotation_size",label:"Размер ротации"},{key:"buy_enabled",label:"Покупка"},{key:"sell_enabled",label:"Продажа"},{key:"commission_percent",label:"Комиссия %"},{key:"access_condition",label:"Условие доступа"},{key:"reputation_id",label:"Репутация"},{key:"min_reputation",label:"Мин. репутация"},{key:"fine_block",label:"Блок штрафом"},{key:"raid_risk",label:"Риск облавы"},{key:"raid_chance",label:"Шанс облавы"},{key:"welcome_text",label:"Приветствие"},{key:"buy_text",label:"Текст покупки"},{key:"sell_text",label:"Текст продажи"},{key:"error_text",label:"Ошибка"},{key:"tags",label:"Теги"},{key:"active",label:"Активен"}] },
    { key: "delivery_rules", label: "Правила доставки", type: "objlist", columns: [{key:"rule_id",label:"ID"},{key:"name",label:"Название"},{key:"enabled",label:"Вкл."},{key:"base_cost",label:"База"},{key:"min_cost",label:"Мин."},{key:"max_cost",label:"Макс."},{key:"item_cost",label:"За предмет"},{key:"stack_cost",label:"За стак"},{key:"distance_cost",label:"Расстояние"},{key:"urgent_cost",label:"Срочность"},{key:"commission_percent",label:"Комиссия"},{key:"time_seconds",label:"Время"},{key:"cost_formula_id",label:"Формула цены"},{key:"time_formula_id",label:"Формула времени"},{key:"send_text",label:"Отправка"},{key:"receive_text",label:"Получение"},{key:"error_text",label:"Ошибка"}] },
    { key: "commissions", label: "Комиссии и налоги", type: "objlist", columns: [{key:"commission_id",label:"ID"},{key:"name",label:"Название"},{key:"commission_type",label:"Тип"},{key:"applies_to",label:"Где"},{key:"fixed_amount",label:"Сумма"},{key:"percent",label:"%"},{key:"min",label:"Мин."},{key:"max",label:"Макс."},{key:"currency",label:"Валюта"},{key:"formula_id",label:"Формула"},{key:"reputation_id",label:"Репутация"},{key:"effect_id",label:"Эффект"},{key:"text",label:"Текст"}] },
    { key: "services", label: "Цены услуг", type: "objlist", columns: [{key:"service_id",label:"ID"},{key:"name",label:"Название"},{key:"service_type",label:"Тип"},{key:"price",label:"Цена"},{key:"currency",label:"Валюта"},{key:"formula_id",label:"Формула"},{key:"npc_id",label:"NPC"},{key:"location_id",label:"Локация"},{key:"sublocation_id",label:"Подлокация"},{key:"camp_id",label:"Лагерь"},{key:"reputation_id",label:"Репутация"},{key:"success_text",label:"Успех"},{key:"error_text",label:"Ошибка"}] },
    { key: "rewards", label: "Экономические награды", type: "objlist", columns: [{key:"reward_id",label:"ID"},{key:"source_type",label:"Источник"},{key:"currency",label:"Валюта"},{key:"min",label:"Мин."},{key:"max",label:"Макс."},{key:"fixed",label:"Фикс."},{key:"formula_id",label:"Формула"},{key:"use_player_level",label:"Ур. игрока"},{key:"use_mob_level",label:"Ур. моба"},{key:"reputation_id",label:"Репутация"},{key:"effect_id",label:"Эффект"},{key:"text",label:"Текст"}] },
    { key: "casinos", label: "Экономика казино", type: "objlist", columns: [{key:"casino_id",label:"ID казино"},{key:"location_id",label:"Локация"},{key:"sublocation_id",label:"Подлокация"},{key:"min_bet",label:"Мин. ставка"},{key:"max_bet",label:"Макс. ставка"},{key:"currency",label:"Валюта"},{key:"win_chance",label:"Шанс выигрыша"},{key:"win_multiplier",label:"Множитель выигрыша"},{key:"commission_percent",label:"Комиссия"},{key:"game_limit",label:"Лимит ставок"},{key:"win_limit",label:"Лимит выигрыша"},{key:"weekly_limit",label:"Недельный лимит"},{key:"fine_risk",label:"Риск штрафа"},{key:"bet_text",label:"Текст ставки"},{key:"win_text",label:"Текст выигрыша"},{key:"loss_text",label:"Текст проигрыша"},{key:"limit_text",label:"Текст лимита"},{key:"enabled",label:"Вкл."}] },
    { key: "economic_effects", label: "Экономические эффекты", type: "objlist", columns: [{key:"effect_id",label:"ID"},{key:"influence_type",label:"Влияние"},{key:"applies_to",label:"Где"},{key:"value",label:"Значение"},{key:"percent",label:"%"},{key:"min",label:"Мин."},{key:"max",label:"Макс."},{key:"duration",label:"Срок"},{key:"text",label:"Текст"}] },
    { key: "pavilion", label: "Торговый павильон", type: "objlist", columns: [{key:"enabled",label:"Вкл."},{key:"player_available",label:"Игроку"},{key:"purchased",label:"Куплен"},{key:"rented",label:"Арендован"},{key:"rent_seconds",label:"Срок аренды"},{key:"rent_cost",label:"Цена аренды"},{key:"commission_percent",label:"Комиссия продажи"},{key:"item_limit",label:"Лимит товаров"},{key:"price_limit",label:"Лимит цены"},{key:"allowed_categories",label:"Разрешённые категории"},{key:"forbidden_categories",label:"Запрещённые категории"},{key:"sales_history",label:"История продаж JSON"},{key:"purchase_text",label:"Текст покупки"},{key:"rent_text",label:"Текст аренды"},{key:"expire_text",label:"Текст окончания"}] },
    { key: "global_buy_multiplier", label: "Глобальный множитель покупки", type: "number" },
    { key: "global_sell_multiplier", label: "Глобальный множитель продажи", type: "number" },
    { key: "reward_multiplier", label: "Множитель наград", type: "number" },
    { key: "drop_value_multiplier", label: "Множитель ценности дропа", type: "number" },
    { key: "market_commission_percent", label: "Комиссия рынка, %", type: "number" },
    { key: "auction_commission_percent", label: "Комиссия аукциона, %", type: "number" },
    { key: "delivery_commission_percent", label: "Комиссия доставки, %", type: "number" },
    { key: "price_formula_id", label: "Глобальная формула цены", type: "formularef" },
    { key: "reward_formula_id", label: "Формула наград", type: "formularef" },
    { key: "money_caps", label: "Лимиты денежной массы", type: "objlist", columns: [{ key: "scope", label: "Область" }, { key: "amount", label: "Лимит" }, { key: "period", label: "Период" }] },
    { key: "dynamic_rules", label: "Правила динамических цен", type: "objlist", columns: [{ key: "condition", label: "Условие" }, { key: "multiplier", label: "Множитель" }, { key: "min", label: "Мин." }, { key: "max", label: "Макс." }] },
    { key: "admin_notes", label: "Заметки", type: "textarea" },
  ],
};
const REFERRAL_CONFIG = {
  base: "referrals", title: "Конструктор реферальной системы", permPrefix: "promos", managePerm: "promos.manage",
  operationLogs: true, operationsPath: "operations/statistics", operationsLabel: "Статистика и история", operationsTitle: "Реферальная статистика, история и ручная проверка", operationsDataLabel: "Приглашения",
  newLabel: "Новое реферальное правило", nameField: "name",
  fields: [
    { key: "name", label: "Название", type: "text" }, { key: "enabled", label: "Активно", type: "checkbox" },
    { key: "code", label: "Код кампании/ссылки", type: "text" }, { key: "link_type", label: "Тип ссылки", type: "select", metaKey: "linkTypes" },
    { key: "campaign_id", label: "ID кампании", type: "text" }, { key: "owner_nt_id", label: "NT-ID владельца (пусто — личные ссылки)", type: "text" },
    { key: "starts_at", label: "Начало действия (ISO)", type: "text" }, { key: "ends_at", label: "Окончание действия (ISO)", type: "text" }, { key: "tags", label: "Теги", type: "lines" },
    { key: "priority", label: "Приоритет", type: "number" }, { key: "platform", label: "Платформа", type: "select", metaKey: "platforms" },
    { key: "trigger", label: "Когда награждать", type: "select", metaKey: "triggers" }, { key: "trigger_value", label: "Значение триггера", type: "number" },
    { key: "referrer_rewards", label: "Награды пригласившему", type: "objlist", columns: [{ key: "type", label: "Тип" }, { key: "object_id", label: "ID/валюта" }, { key: "amount", label: "Количество" }, {key:"delivery_mode",label:"Доставка"}, {key:"text",label:"Текст"}] },
    { key: "referred_rewards", label: "Награды приглашённому", type: "objlist", columns: [{ key: "type", label: "Тип" }, { key: "object_id", label: "ID/валюта" }, { key: "amount", label: "Количество" }, {key:"delivery_mode",label:"Доставка"}, {key:"text",label:"Текст"}] },
    { key: "per_referrer_limit", label: "Лимит на пригласившего", type: "number" }, { key: "per_referred_limit", label: "Лимит на приглашённого", type: "number" },
    { key: "daily_limit", label: "Приглашений в день", type: "number" }, { key: "weekly_limit", label: "Приглашений в неделю", type: "number" },
    { key: "daily_reward_limit", label: "Наград в день", type: "number" }, { key: "weekly_reward_limit", label: "Наград в неделю", type: "number" },
    { key: "platform_limit", label: "Лимит платформы", type: "number" }, { key: "campaign_limit", label: "Лимит кампании", type: "number" }, { key: "total_limit", label: "Общий лимит", type: "number" },
    { key: "prevent_self_referral", label: "Запрет самореферала", type: "checkbox" }, { key: "prevent_duplicate_accounts", label: "Защита от мультиаккаунтов", type: "checkbox" },
    { key: "manual_review", label: "Ручная проверка перед засчитыванием", type: "checkbox" }, { key: "excluded_nt_ids", label: "Исключённые NT-ID", type: "lines" },
    { key: "device_limit", label: "Лимит на устройство (если передан fingerprint)", type: "number" }, { key: "ip_limit", label: "Лимит на IP (если передан)", type: "number" },
    { key: "telegram_link_template", label: "Шаблон ссылки Telegram", type: "text" }, { key: "vk_link_template", label: "Шаблон ссылки VK", type: "text" },
    { key: "texts", label: "Все тексты бота", type: "objlist", columns: [{ key: "key", label: "invite/click/registered/referrer_reward/referred_reward/error/expired/used/antifraud/manual_review" }, { key: "text", label: "Текст" }] },
    { key: "admin_notes", label: "Заметки", type: "textarea" },
  ],
};
import { AuditSection } from "./sections/AuditSection.jsx";
import { ReferenceSection } from "./sections/ReferenceSection.jsx";
import { RolesSection } from "./sections/RolesSection.jsx";
import { SessionsSection } from "./sections/SessionsSection.jsx";

// Permission constants mirror services/admin_rbac.py. The owner sentinel "*"
// is handled by hasPerm below, so listing the concrete permission is enough.
const NAV = [
  { id: "dashboard", label: "Панель состояния", icon: "📊", perm: null },
  { id: "overview", label: "Обзор", icon: "🏠", perm: null },
  { id: "graph", label: "Интерактивная схема", icon: "🕸️", perm: "graph.view" },
  { id: "players", label: "Игроки", icon: "👤", perm: "players.view" },
  { id: "world", label: "Конструктор мира", icon: "🌍", perm: "world.view" },
  { id: "sublocations", label: "Конструктор подлокаций", icon: "🕳️", perm: "world.view" },
  { id: "items", label: "Конструктор предметов", icon: "📦", perm: "item.view" },
  { id: "effects", label: "Конструктор эффектов", icon: "✨", perm: "effect.view" },
  { id: "reputations", label: "Конструктор репутации", icon: "🎖️", perm: "reputation.view" },
  { id: "addictions", label: "Зависимости", icon: "🧪", perm: "effect.view" },
  { id: "tolerances", label: "Привыкание", icon: "🔁", perm: "effect.view" },
  { id: "fines", label: "Штрафы", icon: "⚖️", perm: "fine_def.view" },
  { id: "skills", label: "Конструктор навыков", icon: "🌀", perm: "skill_def.view" },
  { id: "site", label: "Конструктор сайта", icon: "🌐", perm: "site.view" },
  { id: "profile_layout", label: "Профиль игрока", icon: "🪪", perm: "profile_layout.view" },
  { id: "city", label: "Город", icon: "🏙️", perm: "city.view" },
  { id: "fortress", label: "Крепости", icon: "🏰", perm: "city.view" },
  { id: "taverns", label: "Конструктор таверны", icon: "🍺", perm: "tavern.view" },
  { id: "recipes", label: "Конструктор ремесла", icon: "⚒️", perm: "recipe.view" },
  { id: "economy", label: "Конструктор экономики", icon: "💰", perm: "economy.view" },
  { id: "referrals", label: "Реферальная система", icon: "🔗", perm: "promos.view" },
  { id: "professions", label: "Профессии ремесла", icon: "🛠️", perm: "profession.view" },
  { id: "workshops", label: "Мастерские", icon: "🏭", perm: "workshop.view" },
  { id: "craft-material-groups", label: "Группы материалов", icon: "🧱", perm: "recipe.view" },
  { id: "workshop_messages", label: "Сообщения мастерских", icon: "🧾", perm: "workshop_message.view" },
  { id: "upgrades", label: "Улучшение предметов", icon: "🔧", perm: "recipe.view" },
  { id: "enchants", label: "Зачарование", icon: "🔮", perm: "recipe.view" },
  { id: "disassembles", label: "Разборка", icon: "🪓", perm: "recipe.view" },
  { id: "repairs", label: "Ремонт", icon: "🧰", perm: "recipe.view" },
  { id: "formulas", label: "Конструктор формул", icon: "🧮", perm: "formula.view" },
  { id: "camps", label: "Конструктор лагеря", icon: "🏕️", perm: "camp.view" },
  { id: "traits", label: "Черты мобов", icon: "🧬", perm: "trait.view" },
  { id: "blessings", label: "Благословения", icon: "🌟", perm: "blessing.view" },
  { id: "phases", label: "Фазы боссов", icon: "🌀", perm: "phase.view" },
  { id: "pvp", label: "PVP-бой", icon: "⚔️", perm: "pvp.view" },
  { id: "combat", label: "Боевые настройки", icon: "⏱️", perm: "combat.view" },
  { id: "npc-allies", label: "NPC-помощники", icon: "🤝", perm: "npc_ally.view" },
  { id: "mole", label: "Информатор Крот", icon: "🕵️", perm: "mole.view" },
  { id: "casino", label: "Подпольное казино", icon: "🎲", perm: "casino.view" },
  { id: "housing", label: "Жильё / дом игрока", icon: "🏠", perm: "housing.view" },
  { id: "levels", label: "Уровни и опыт", icon: "🪜", perm: "level.view" },
  { id: "exp", label: "Опыт", icon: "📈", perm: "exp.view" },
  { id: "registration", label: "Регистрация", icon: "📝", perm: "registration.view" },
  { id: "races", label: "Расы", icon: "🧝", perm: "race.view" },
  { id: "quests", label: "Квесты и задания", icon: "📜", perm: "quest.view" },
  { id: "guilds", label: "Гильдии", icon: "🏰", perm: "guild.view" },
  { id: "events", label: "Мировые события", icon: "🌌", perm: "world_event.view" },
  { id: "event-campaigns", label: "Эвенты", icon: "🎪", perm: "event_campaign.view" },
  { id: "broadcast-campaigns", label: "Рассылки", icon: "📣", perm: "broadcast_campaign.view" },
  { id: "achievements", label: "Достижения", icon: "🏆", perm: "achievement.view" },
  { id: "messages", label: "Очередь сообщений", icon: "📨", perm: "messages.view_queue" },
  { id: "message-rules", label: "Правила приоритета", icon: "🚦", perm: "message_rule.view" },
  { id: "promos", label: "Промокоды и рассылки", icon: "🎟️", perm: "promos.view" },
  { id: "texts", label: "Тексты бота", icon: "💬", perm: "text.view" },
  { id: "import", label: "Импорт контента", icon: "📥", perm: "world.view" },
  { id: "reference", label: "Справочник", icon: "📖", perm: null },
  { id: "audit", label: "Аудит", icon: "📜", perm: "audit.view" },
  { id: "sessions", label: "Сессии", icon: "🔑", perm: "system.view" },
  { id: "roles", label: "Роли и доступ", icon: "🛡️", perm: "roles.manage" },
];

// Группировка бокового меню (ТЗ 11 §4.1). Порядок групп фиксирован; раздел без
// явной группы попадает в «Прочее».
const NAV_GROUP_ORDER = [
  "Главное", "Игроки", "Мир", "Контент", "Бой",
  "Ремесло и экономика", "Сайт и профиль", "Прогрессия", "Система", "Прочее",
];
const NAV_GROUP_OF = {
  dashboard: "Главное", overview: "Главное", graph: "Главное", import: "Главное",
  players: "Игроки",
  world: "Мир", sublocations: "Мир", city: "Мир", camps: "Мир", events: "Мир", mole: "Мир",
  items: "Контент", achievements: "Контент", traits: "Контент",
  blessings: "Контент", phases: "Контент", texts: "Контент",
  effects: "Бой", addictions: "Бой", tolerances: "Бой", skills: "Бой",
  formulas: "Бой", reputations: "Бой", pvp: "Бой", combat: "Бой", "npc-allies": "Бой",
  recipes: "Ремесло и экономика", professions: "Ремесло и экономика",
  workshops: "Ремесло и экономика", "craft-material-groups": "Ремесло и экономика", workshop_messages: "Ремесло и экономика",
  upgrades: "Ремесло и экономика", enchants: "Ремесло и экономика",
  disassembles: "Ремесло и экономика", repairs: "Ремесло и экономика", fines: "Ремесло и экономика",
  taverns: "Ремесло и экономика", casino: "Ремесло и экономика",
  housing: "Ремесло и экономика", promos: "Ремесло и экономика", economy: "Ремесло и экономика",
  referrals: "Прогрессия",
  site: "Сайт", profile_layout: "Интерфейс",
  levels: "Баланс", exp: "Баланс", registration: "Прогрессия", races: "Прогрессия", quests: "Прогрессия",
  messages: "Коммуникации", "message-rules": "Коммуникации", reference: "Система", audit: "Система",
  sessions: "Система", roles: "Система",
};

function makeHasPerm(me) {
  const perms = new Set(me?.permissions || []);
  const owner = Boolean(me?.isOwner);
  return (perm) => !perm || owner || perms.has("*") || perms.has(perm);
}

// Тип сущности → раздел админки (для перехода из глобального поиска, ТЗ 11 §4.2).
const SEARCH_TYPE_TO_SECTION = {
  item: "items", effect: "effects", recipe: "recipes", trait: "traits",
  blessing: "blessings", phase: "phases", level: "levels", exp: "exp",
  registration: "registration", race: "races", fine: "fines", camp: "camps",
  city: "city", achievement: "achievements", world_event: "events", guild: "guilds",
  formula: "formulas", profession: "professions", workshop: "workshops", craft_material_group: "craft-material-groups",
  workshop_message: "workshop_messages", item_upgrade: "upgrades",
  item_enchant: "enchants", item_disassemble: "disassembles", reputation: "reputations",
  item_repair: "repairs",
  addiction: "addictions", tolerance: "tolerances", tavern: "taverns",
  sublocation: "sublocations", sublocation_node: "sublocations", sublocation_transition: "sublocations",
  npc_ally: "npc-allies", mole: "mole", casino: "casino", housing: "housing", quest: "quests", event_campaign: "event-campaigns", broadcast_campaign: "broadcast-campaigns",
  message_rule: "message-rules",
};
function sectionForSearchType(type) {
  if (type in SEARCH_TYPE_TO_SECTION) return SEARCH_TYPE_TO_SECTION[type];
  if (type.startsWith("site_")) return "site";
  if (type.startsWith("profile_")) return "profile_layout";
  return "world"; // локации/мобы/события/переходы/кнопки/npc/квесты/рейды/под-объекты
}

function GlobalSearch({ guarded, onOpen }) {
  const [q, setQ] = useState("");
  const [res, setRes] = useState(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const term = q.trim();
    if (term.length < 2) { setRes(null); return; }
    let cancelled = false;
    const handle = setTimeout(async () => {
      const p = await guarded(() => globalSearch(term));
      if (!cancelled && p) { setRes(p); setOpen(true); }
    }, 250);
    return () => { cancelled = true; clearTimeout(handle); };
  }, [q, guarded]);

  return (
    <div className="ntv2-gsearch">
      <input
        className="ntv2-gsearch-input"
        placeholder="🔎 Глобальный поиск…"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        onFocus={() => res && setOpen(true)}
      />
      {open && res ? (
        <div className="ntv2-gsearch-drop">
          <div className="ntv2-gsearch-head">
            <span>Найдено: {res.total}</span>
            <button type="button" onClick={() => setOpen(false)}>✕</button>
          </div>
          {!res.groups.length ? <div className="ntv2-gsearch-empty">Ничего не найдено.</div> : null}
          {res.groups.map((g) => (
            <div className="ntv2-gsearch-group" key={g.type}>
              <div className="ntv2-gsearch-gtitle">{g.label}{g.truncated ? " …" : ""}</div>
              {g.items.map((it) => (
                <button
                  type="button"
                  className="ntv2-gsearch-item"
                  key={it.id}
                  onClick={() => { onOpen(sectionForSearchType(it.type)); setOpen(false); setQ(""); }}
                >
                  <b>{it.title}</b> <code>{it.entity_id}</code>
                </button>
              ))}
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

export function AdminShell() {
  const [me, setMe] = useState(null);
  const [active, setActive] = useState("dashboard");
  const [menuOpen, setMenuOpen] = useState(false); // мобильное off-canvas меню (§12)
  const [error, setError] = useState("");
  const [ok, setOk] = useState("");
  const [booting, setBooting] = useState(true);

  const guarded = useCallback(async (action, success = "") => {
    try {
      setError("");
      setOk("");
      const result = await action();
      if (success) setOk(success);
      return result;
    } catch (e) {
      setError(e?.message || "Ошибка админ-панели.");
      return null;
    }
  }, []);

  useEffect(() => {
    (async () => {
      try {
        await getAdminSessionToken(); // exchanges ?token= activation if present
        const payload = await fetchMe();
        setMe(payload);
      } catch (e) {
        setError(e?.message || "Нет активной админ-сессии. Запросите новую ссылку в админ-чате.");
      } finally {
        setBooting(false);
      }
    })();
  }, []);

  const hasPerm = useMemo(() => makeHasPerm(me), [me]);
  const visibleNav = useMemo(() => NAV.filter((item) => hasPerm(item.perm)), [hasPerm]);
  const groupedNav = useMemo(() => {
    const byGroup = new Map();
    for (const item of visibleNav) {
      const g = NAV_GROUP_OF[item.id] || "Прочее";
      if (!byGroup.has(g)) byGroup.set(g, []);
      byGroup.get(g).push(item);
    }
    return NAV_GROUP_ORDER.filter((g) => byGroup.has(g)).map((g) => ({ group: g, items: byGroup.get(g) }));
  }, [visibleNav]);

  // If the active tab becomes unavailable (role downgraded), fall back to overview.
  useEffect(() => {
    if (!visibleNav.some((item) => item.id === active)) setActive("dashboard");
  }, [visibleNav, active]);

  if (booting) {
    return <div className="ntv2"><div className="ntv2-boot">Загрузка админ-панели V2…</div></div>;
  }
  if (!me) {
    return <div className="ntv2"><div className="ntv2-boot ntv2-error">{error || "Сессия недоступна."}</div></div>;
  }

  return (
    <div className={`ntv2${menuOpen ? " ntv2-menu-open" : ""}`}>
      <button
        type="button"
        className="ntv2-menu-toggle"
        aria-label="Меню"
        onClick={() => setMenuOpen((o) => !o)}
      >☰</button>
      <div className="ntv2-scrim" onClick={() => setMenuOpen(false)} />
      <aside className="ntv2-sidebar">
        <div className="ntv2-brand">
          <div className="ntv2-brand-title">Нер-Талис</div>
          <div className="ntv2-brand-sub">Админ-консоль V2</div>
        </div>
        {/* ТЗ 22 §2: глобальный поиск требует graph.view — не показываем тем, у кого его нет (иначе 403 на /search). */}
        {hasPerm("graph.view") ? <GlobalSearch guarded={guarded} onOpen={setActive} /> : null}
        <nav className="ntv2-nav">
          {groupedNav.map(({ group, items }) => (
            <div className="ntv2-nav-group" key={group}>
              <div className="ntv2-nav-group-title">{group}</div>
              {items.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className={`ntv2-nav-item${active === item.id ? " active" : ""}`}
                  onClick={() => { setActive(item.id); setMenuOpen(false); }}
                >
                  <span className="ntv2-nav-icon">{item.icon}</span>
                  <span>{item.label}</span>
                </button>
              ))}
            </div>
          ))}
        </nav>
        <div className="ntv2-sidebar-foot">
          <div className="ntv2-role-pill">{me.roleLabel || me.role}</div>
          <a className="ntv2-v1-link" href="/admin_panel">← Классическая панель</a>
        </div>
      </aside>

      <main className="ntv2-main">
        {error ? <div className="ntv2-banner ntv2-error">{error}</div> : null}
        {ok ? <div className="ntv2-banner ntv2-ok">{ok}</div> : null}

        <Suspense fallback={<div className="ntv2-boot">Загрузка раздела…</div>}>
        {active === "dashboard" && <DashboardSection guarded={guarded} onOpenSection={setActive} />}
        {active === "overview" && <OverviewSection me={me} />}
        {active === "players" && hasPerm("players.view") && <PlayersSection guarded={guarded} hasPerm={hasPerm} />}
        {active === "graph" && hasPerm("graph.view") && <GraphSection guarded={guarded} hasPerm={hasPerm} onOpenSection={setActive} />}
        {active === "world" && hasPerm("world.view") && <WorldSection guarded={guarded} hasPerm={hasPerm} />}
        {active === "sublocations" && hasPerm("world.view") && <SublocationsSection guarded={guarded} hasPerm={hasPerm} />}
        {active === "items" && hasPerm("item.view") && <ItemsSection guarded={guarded} hasPerm={hasPerm} />}
        {active === "effects" && hasPerm("effect.view") && <EffectsSection guarded={guarded} hasPerm={hasPerm} />}
        {active === "reputations" && hasPerm("reputation.view") && <ReputationSection guarded={guarded} hasPerm={hasPerm} />}
        {active === "addictions" && hasPerm("effect.view") && <LibrarySection guarded={guarded} hasPerm={hasPerm} config={ADDICTION_CONFIG} />}
        {active === "tolerances" && hasPerm("effect.view") && <LibrarySection guarded={guarded} hasPerm={hasPerm} config={TOLERANCE_CONFIG} />}
        {active === "fines" && hasPerm("fine_def.view") && <FinesSection guarded={guarded} hasPerm={hasPerm} />}
        {active === "skills" && hasPerm("skill_def.view") && <SkillsSection guarded={guarded} hasPerm={hasPerm} />}
        {active === "site" && hasPerm("site.view") && <SiteSection guarded={guarded} hasPerm={hasPerm} />}
        {active === "profile_layout" && hasPerm("profile_layout.view") && <ProfileLayoutSection guarded={guarded} hasPerm={hasPerm} />}
        {active === "city" && hasPerm("city.view") && <CitySection guarded={guarded} hasPerm={hasPerm} />}
        {active === "fortress" && hasPerm("city.view") && <CitySection guarded={guarded} hasPerm={hasPerm} fortressMode />}
        {active === "taverns" && hasPerm("tavern.view") && <TavernSection guarded={guarded} hasPerm={hasPerm} />}
        {active === "recipes" && hasPerm("recipe.view") && <RecipesSection guarded={guarded} hasPerm={hasPerm} />}
        {active === "economy" && hasPerm("economy.view") && <LibrarySection guarded={guarded} hasPerm={hasPerm} config={ECONOMY_CONFIG} />}
        {active === "referrals" && hasPerm("promos.view") && <LibrarySection guarded={guarded} hasPerm={hasPerm} config={REFERRAL_CONFIG} />}
        {active === "professions" && hasPerm("profession.view") && <LibrarySection guarded={guarded} hasPerm={hasPerm} config={PROFESSION_CONFIG} />}
        {active === "workshops" && hasPerm("workshop.view") && <LibrarySection guarded={guarded} hasPerm={hasPerm} config={WORKSHOP_CONFIG} />}
        {active === "craft-material-groups" && hasPerm("recipe.view") && <LibrarySection guarded={guarded} hasPerm={hasPerm} config={CRAFT_MATERIAL_GROUP_CONFIG} />}
        {active === "workshop_messages" && hasPerm("workshop_message.view") && <WorkshopMessagesSection guarded={guarded} hasPerm={hasPerm} />}
        {active === "upgrades" && hasPerm("recipe.view") && <LibrarySection guarded={guarded} hasPerm={hasPerm} config={UPGRADE_CONFIG} />}
        {active === "enchants" && hasPerm("recipe.view") && <LibrarySection guarded={guarded} hasPerm={hasPerm} config={ENCHANT_CONFIG} />}
        {active === "disassembles" && hasPerm("recipe.view") && <LibrarySection guarded={guarded} hasPerm={hasPerm} config={DISASSEMBLE_CONFIG} />}
        {active === "repairs" && hasPerm("recipe.view") && <LibrarySection guarded={guarded} hasPerm={hasPerm} config={REPAIR_CONFIG} />}
        {active === "formulas" && hasPerm("formula.view") && <FormulasSection guarded={guarded} hasPerm={hasPerm} />}
        {active === "camps" && hasPerm("camp.view") && <CampSection guarded={guarded} hasPerm={hasPerm} />}
        {active === "import" && hasPerm("world.view") && <ImportSection guarded={guarded} hasPerm={hasPerm} />}
        {active === "texts" && hasPerm("text.view") && <TextsSection guarded={guarded} hasPerm={hasPerm} />}
        {active === "traits" && hasPerm("trait.view") && <LibrarySection guarded={guarded} hasPerm={hasPerm} config={TRAIT_CONFIG} />}
        {active === "blessings" && hasPerm("blessing.view") && <LibrarySection guarded={guarded} hasPerm={hasPerm} config={BLESSING_CONFIG} />}
        {active === "pvp" && hasPerm("pvp.view") && <LibrarySection guarded={guarded} hasPerm={hasPerm} config={PVP_CONFIG} />}
        {active === "combat" && hasPerm("combat.view") && <LibrarySection guarded={guarded} hasPerm={hasPerm} config={COMBAT_CONFIG} />}
        {active === "npc-allies" && hasPerm("npc_ally.view") && <LibrarySection guarded={guarded} hasPerm={hasPerm} config={NPC_ALLY_CONFIG} />}
        {active === "mole" && hasPerm("mole.view") && <LibrarySection guarded={guarded} hasPerm={hasPerm} config={MOLE_CONFIG} />}
        {active === "casino" && hasPerm("casino.view") && <LibrarySection guarded={guarded} hasPerm={hasPerm} config={CASINO_CONFIG} />}
        {active === "housing" && hasPerm("housing.view") && <LibrarySection guarded={guarded} hasPerm={hasPerm} config={HOUSING_CONFIG} />}
        {active === "phases" && hasPerm("phase.view") && <LibrarySection guarded={guarded} hasPerm={hasPerm} config={PHASE_CONFIG} />}
        {active === "levels" && hasPerm("level.view") && <LibrarySection guarded={guarded} hasPerm={hasPerm} config={LEVEL_CONFIG} />}
        {active === "quests" && hasPerm("quest.view") && <LibrarySection guarded={guarded} hasPerm={hasPerm} config={QUEST_CONFIG} />}
        {active === "exp" && hasPerm("exp.view") && <LibrarySection guarded={guarded} hasPerm={hasPerm} config={EXP_CONFIG} />}
        {active === "registration" && hasPerm("registration.view") && <LibrarySection guarded={guarded} hasPerm={hasPerm} config={REGISTRATION_CONFIG} />}
        {active === "races" && hasPerm("race.view") && <LibrarySection guarded={guarded} hasPerm={hasPerm} config={RACE_CONFIG} />}
        {active === "guilds" && hasPerm("guild.view") && <GuildsSection guarded={guarded} hasPerm={hasPerm} />}
        {active === "events" && hasPerm("world_event.view") && <EventsSection guarded={guarded} hasPerm={hasPerm} />}
        {active === "event-campaigns" && hasPerm("event_campaign.view") && <LibrarySection guarded={guarded} hasPerm={hasPerm} config={EVENT_CAMPAIGN_CONFIG} />}
        {active === "broadcast-campaigns" && hasPerm("broadcast_campaign.view") && <LibrarySection guarded={guarded} hasPerm={hasPerm} config={BROADCAST_CAMPAIGN_CONFIG} />}
        {active === "achievements" && hasPerm("achievement.view") && <AchievementsSection guarded={guarded} hasPerm={hasPerm} />}
        {active === "messages" && hasPerm("messages.view_queue") && <MessagesSection guarded={guarded} hasPerm={hasPerm} />}
        {active === "message-rules" && hasPerm("message_rule.view") && <LibrarySection guarded={guarded} hasPerm={hasPerm} config={MESSAGE_RULE_CONFIG} />}
        {active === "promos" && hasPerm("promos.view") && <PromosSection guarded={guarded} hasPerm={hasPerm} />}
        {active === "reference" && <ReferenceSection />}
        {active === "audit" && hasPerm("audit.view") && <AuditSection guarded={guarded} />}
        {active === "sessions" && hasPerm("system.view") && (
          <SessionsSection guarded={guarded} canRevoke={hasPerm("system.manage")} />
        )}
        {active === "roles" && hasPerm("roles.manage") && <RolesSection guarded={guarded} />}
        </Suspense>
      </main>
    </div>
  );
}
