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
    { key: "texts", label: "Тексты боя", type: "objlist", columns: [{ key: "key", label: "Ключ" }, { key: "text", label: "Текст" }] },
    { key: "description", label: "Описание (для админа)", type: "textarea" },
  ],
};
const PVP_CONFIG = {
  base: "pvp", title: "Конструктор PVP (будущий)", permPrefix: "pvp",
  newLabel: "Новое PVP-правило", nameField: "name",
  fields: [
    { key: "name", label: "Название", type: "text", hint: "Имя правила/пресета PVP." },
    { key: "pvp_type", label: "Тип PVP", type: "select", metaKey: "pvpTypes", hint: "Дуэль/арена/осада/заказ/… — задаёт смысл боя." },
    { key: "enabled", label: "Включён", type: "checkbox", hint: "Правило активно. PVP-боёв в игре пока нет — рантайм на вырост." },
    { key: "min_level", label: "Мин. уровень", type: "number", hint: "С какого уровня доступно PVP." },
    { key: "max_level_diff", label: "Макс. разница уровней", type: "number", hint: "Ограничение разницы уровней соперников (0 = без ограничения)." },
    { key: "cooldown_seconds", label: "Кулдаун между боями (сек)", type: "number" },
    { key: "accept_seconds", label: "Время на принятие (сек, дуэль)", type: "number" },
    { key: "require_consent", label: "Только по согласию", type: "checkbox" },
    { key: "attack_without_consent", label: "Нападение без согласия (свободный PVP)", type: "checkbox" },
    { key: "death_on_loss", label: "Поражение со смертью", type: "checkbox" },
    { key: "newbie_protection", label: "Защита новичков", type: "checkbox" },
    { key: "allowed_locations", label: "Разрешённые локации (id по строкам)", type: "list" },
    { key: "forbidden_locations", label: "Запрещённые локации (id по строкам)", type: "list" },
    { key: "conditions", label: "Условия входа в бой", type: "objlist", columns: [{ key: "type", label: "Тип" }, { key: "value", label: "Значение" }], hint: "Уровень/локация/событие/штраф/предмет/статус и т.д." },
    { key: "rewards", label: "Награды за победу", type: "objlist", columns: [{ key: "type", label: "Тип" }, { key: "value", label: "Значение" }] },
    { key: "penalties", label: "Штрафы и последствия поражения", type: "objlist", columns: [{ key: "type", label: "Тип" }, { key: "value", label: "Значение" }] },
    { key: "buttons", label: "Кнопки боя", type: "objlist", columns: [{ key: "action", label: "Действие" }, { key: "text", label: "Текст" }, { key: "resource_cost", label: "Расход" }], hint: "attack/skills/use_item/pouch/defend/flee/surrender/enemy_info." },
    { key: "turn_seconds", label: "Время на ход (сек)", type: "number", hint: "В PVP таймер включён по умолчанию (100 секунд, ТЗ 20 §5.5)." },
    { key: "warn_before_seconds", label: "Предупредить за N сек", type: "number" },
    { key: "on_timeout", label: "Действие при пропуске", type: "select", metaKey: "timeoutActions", hint: "skip/defend/auto/kick/tech_defeat/penalty." },
    { key: "max_skips", label: "Допустимо пропусков", type: "number" },
    { key: "action_order", label: "Порядок действий", type: "select", metaKey: "actionOrderTypes", hint: "По очереди/инициативе/скорости/одновременно/стороны и т.д." },
    { key: "log_mode", label: "Режим лога боя", type: "select", metaKey: "logModes", hint: "full_all / per_side / hide_enemy." },
    { key: "sides", label: "Стороны боя", type: "objlist", columns: [{ key: "name", label: "Название" }, { key: "players", label: "Игроки (id через запятую)" }, { key: "npc", label: "NPC (id через запятую)" }, { key: "leader", label: "Лидер" }], hint: "Для командного PVP — минимум 2 стороны." },
    { key: "npc_limit_per_side", label: "Лимит NPC на сторону", type: "number" },
    { key: "npc_limit_per_player", label: "Лимит NPC на игрока", type: "number" },
    { key: "npc_hire_cost", label: "Стоимость найма NPC", type: "number" },
    { key: "victory_conditions", label: "Условия победы (по строкам)", type: "list" },
    { key: "defeat_conditions", label: "Условия поражения (по строкам)", type: "list" },
    { key: "postdeath_curse_enabled", label: "Посмертные PVP-проклятья", type: "checkbox", hint: "Учитываются достижением «Проклятье? Какое проклятье?» (только PVP-смерть, ТЗ §1.6)." },
    { key: "postdeath_curse_chance", label: "Шанс проклятья, %", type: "number" },
    { key: "postdeath_curses", label: "Доступные проклятья (id по строкам)", type: "list" },
    { key: "curse_duration", label: "Длительность проклятья (сек)", type: "number" },
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
    { key: "description", label: "Описание", type: "textarea" },
    { key: "image_path", label: "Изображение", type: "text", hint: "Локальный путь /assets/…" },
    { key: "acquire_method", label: "Как получить", type: "select", metaKey: "acquireMethods", hint: "Нанять/задание/достижение/событие/таверна/гильдия/дом/предмет/навык/админ." },
    { key: "cost", label: "Стоимость", type: "number" },
    { key: "currency", label: "Валюта", type: "select", metaKey: "currencies" },
    { key: "duration_seconds", label: "Длительность (сек)", type: "number", hint: "Для временных союзников/наёмников." },
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
  newLabel: "Новое казино", nameField: "name",
  fields: [
    { key: "name", label: "Название", type: "text", hint: "Имя казино (видно админу)." },
    { key: "enabled", label: "Включено", type: "checkbox" },
    { key: "location_id", label: "Локация (id)", type: "text" },
    { key: "city_id", label: "Город (id)", type: "text" },
    { key: "owner_npc", label: "NPC/владелец", type: "text" },
    { key: "description", label: "Описание", type: "textarea" },
    { key: "min_level", label: "Минимальный уровень", type: "number" },
    { key: "min_bet", label: "Минимальная ставка", type: "number" },
    { key: "max_bet", label: "Максимальная ставка", type: "number" },
    { key: "currency", label: "Валюта", type: "select", metaKey: "currencies" },
    { key: "games_per_day", label: "Лимит игр в день", type: "number" },
    { key: "win_per_day", label: "Лимит выигрыша в день", type: "number" },
    { key: "cooldown_seconds", label: "Кулдаун (сек)", type: "number" },
    { key: "raid_risk_percent", label: "Риск облавы, %", type: "number" },
    { key: "depends_world_event", label: "Зависит от мировых событий", type: "checkbox" },
    { key: "depends_effects", label: "Зависит от эффектов", type: "checkbox" },
    { key: "depends_achievements", label: "Зависит от достижений", type: "checkbox" },
    { key: "depends_fines", label: "Зависит от штрафов", type: "checkbox" },
    { key: "games", label: "Игры и баланс", type: "objlist", columns: [{ key: "game_type", label: "Игра" }, { key: "win_chance", label: "Шанс выигрыша %" }, { key: "loss_chance", label: "Шанс проигрыша %" }, { key: "coefficient", label: "Коэффициент" }, { key: "commission", label: "Комиссия %" }, { key: "min_loss_chance", label: "Мин. проигрыш %" }, { key: "max_win_chance", label: "Макс. выигрыш %" }], hint: "Шанс проигрыша должен быть выше шанса выигрыша. Чем выше коэффициент — тем ниже шанс победы (Кости<Напёрстки<Очко)." },
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
  base: "levels", title: "Конструктор уровней", permPrefix: "level",
  newLabel: "Новый уровень", nameField: "title",
  fields: [
    { key: "title", label: "Заголовок", type: "text", hint: "Название уровня (например «Уровень 5»). Видно админу." },
    { key: "level", label: "Уровень", type: "number", hint: "Числовой номер уровня. Должен быть уникальным." },
    { key: "exp_required", label: "Опыт до уровня", type: "number", hint: "Сколько опыта нужно набрать, чтобы достичь этого уровня. Можно задать формулой ниже." },
    { key: "stat_points", label: "Очки характеристик", type: "number", hint: "Сколько очков характеристик выдаётся за достижение уровня." },
    { key: "skill_points", label: "Очки навыков", type: "number", hint: "Сколько очков навыков выдаётся за достижение уровня." },
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
    { key: "level_scaling_percent", label: "Масштаб по уровню, %", type: "number", hint: "На сколько % меняется опыт с ростом уровня игрока/цели." },
    { key: "formula_id", label: "Формула (ТЗ 13 §2.8)", type: "formularef", hint: "Если задана, опыт считается формулой, а базовое значение/масштаб игнорируются." },
    { key: "notes", label: "Заметки", type: "textarea", hint: "Пояснение для админа, игроку не показывается." },
  ],
};
const REGISTRATION_CONFIG = {
  base: "registration", title: "Конструктор регистрации", permPrefix: "registration",
  newLabel: "Новый шаг", nameField: "label",
  fields: [
    { key: "label", label: "Подпись шага", type: "text" },
    { key: "step_type", label: "Тип шага", type: "select", metaKey: "stepTypes" },
    { key: "order", label: "Порядок", type: "number" },
    { key: "required", label: "Обязательный шаг", type: "checkbox" },
    { key: "text", label: "Текст", type: "textarea" },
  ],
};
const RACE_CONFIG = {
  base: "races", title: "Конструктор рас", permPrefix: "race",
  newLabel: "Новая раса", nameField: "race_name",
  supportsImport: true,
  importLabel: "Импортировать существующие расы?", importText: "Расы из data/races.json будут заведены как опубликованные записи (без дублей).",
  fields: [
    { key: "race_name", label: "Название", type: "text", hint: "Имя расы, видно игроку при регистрации. Обязательное поле." },
    { key: "description", label: "Описание", type: "textarea", hint: "Краткое описание расы для игрока." },
    { key: "lore", label: "Лор", type: "textarea", hint: "Расширенный лор/история расы (необязательно)." },
    { key: "model_image", label: "Изображение модели (/assets/…)", type: "text", hint: "Локальный путь к картинке (/assets/…). Внешние ссылки запрещены — загрузите файл." },
    { key: "playable", label: "Доступна для игры", type: "checkbox", hint: "Если выключено — раса недоступна при регистрации новых игроков." },
    { key: "stat_bonuses", label: "Бонусы характеристик", type: "numbergroup", sub: _STAT_SUB, hint: "Прибавки к характеристикам от расы (могут быть отрицательными)." },
    { key: "starting_stats", label: "Стартовые характеристики", type: "numbergroup", sub: _STAT_SUB, hint: "Базовые значения характеристик на старте для этой расы." },
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
    { key: "type", label: "Тип мастерской", type: "select", metaKey: "workshopTypes" },
    { key: "location", label: "Локация (id)", type: "text" },
    { key: "city", label: "Город (id)", type: "text" },
    { key: "fortress", label: "Крепость (id)", type: "text" },
    { key: "available", label: "Доступна", type: "checkbox" },
    { key: "access_condition", label: "Условие доступа", type: "text" },
    { key: "use_cost", label: "Стоимость использования", type: "number" },
    { key: "work_time", label: "Время работы (сек)", type: "number" },
    { key: "professions", label: "Профессии (id по строкам)", type: "list" },
    { key: "recipes", label: "Рецепты (id по строкам)", type: "list" },
    { key: "description", label: "Описание", type: "textarea" },
    { key: "image", label: "Изображение (/assets/…)", type: "text" },
  ],
};
const UPGRADE_CONFIG = {
  base: "upgrades", title: "Конструктор улучшения", permPrefix: "recipe",
  newLabel: "Новое правило улучшения", nameField: "name",
  fields: [
    { key: "name", label: "Название", type: "text" },
    { key: "upgrade_type", label: "Тип улучшения", type: "select", metaKey: "upgradeTypes" },
    { key: "target_item_type", label: "Тип предмета (ограничение)", type: "text" },
    { key: "result_effect", label: "Эффект результата (id)", type: "text" },
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
    { key: "enchant_effect", label: "Эффект зачарования (id)", type: "text" },
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
    { key: "depends_on_quality", label: "Зависит от качества", type: "checkbox" },
    { key: "depends_on_level", label: "Зависит от уровня", type: "checkbox" },
    { key: "requires_workshop", label: "Нужна мастерская (id)", type: "text" },
    { key: "requires_tool", label: "Нужен инструмент (id)", type: "text" },
    { key: "gives_exp", label: "Ремесленный опыт", type: "number" },
    { key: "success_text", label: "Текст успеха", type: "textarea" },
    { key: "fail_text", label: "Текст провала", type: "textarea" },
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
  { id: "fines", label: "Конструктор штрафов", icon: "⚖️", perm: "fine_def.view" },
  { id: "skills", label: "Конструктор навыков", icon: "🌀", perm: "skill_def.view" },
  { id: "site", label: "Конструктор сайта", icon: "🌐", perm: "site.view" },
  { id: "profile_layout", label: "Раскладка профиля", icon: "🪪", perm: "profile_layout.view" },
  { id: "city", label: "Город и крепость", icon: "🏙️", perm: "city.view" },
  { id: "taverns", label: "Конструктор таверны", icon: "🍺", perm: "tavern.view" },
  { id: "recipes", label: "Конструктор ремесла", icon: "⚒️", perm: "recipe.view" },
  { id: "professions", label: "Профессии ремесла", icon: "🛠️", perm: "profession.view" },
  { id: "workshops", label: "Мастерские", icon: "🏭", perm: "workshop.view" },
  { id: "workshop_messages", label: "Сообщения мастерских", icon: "🧾", perm: "workshop_message.view" },
  { id: "upgrades", label: "Улучшение предметов", icon: "🔧", perm: "recipe.view" },
  { id: "enchants", label: "Зачарование", icon: "🔮", perm: "recipe.view" },
  { id: "disassembles", label: "Разборка", icon: "🪓", perm: "recipe.view" },
  { id: "formulas", label: "Конструктор формул", icon: "🧮", perm: "formula.view" },
  { id: "camps", label: "Конструктор лагеря", icon: "🏕️", perm: "camp.view" },
  { id: "traits", label: "Черты мобов", icon: "🧬", perm: "trait.view" },
  { id: "blessings", label: "Благословения", icon: "🌟", perm: "blessing.view" },
  { id: "phases", label: "Фазы боссов", icon: "🌀", perm: "phase.view" },
  { id: "pvp", label: "Конструктор PVP", icon: "⚔️", perm: "pvp.view" },
  { id: "combat", label: "Боевые настройки", icon: "⏱️", perm: "combat.view" },
  { id: "npc-allies", label: "NPC-союзники", icon: "🤝", perm: "npc_ally.view" },
  { id: "mole", label: "Информатор Крот", icon: "🕵️", perm: "mole.view" },
  { id: "casino", label: "Подпольное казино", icon: "🎲", perm: "casino.view" },
  { id: "housing", label: "Жильё / дом игрока", icon: "🏠", perm: "housing.view" },
  { id: "levels", label: "Уровни", icon: "🪜", perm: "level.view" },
  { id: "exp", label: "Опыт", icon: "📈", perm: "exp.view" },
  { id: "registration", label: "Регистрация", icon: "📝", perm: "registration.view" },
  { id: "races", label: "Расы", icon: "🧝", perm: "race.view" },
  { id: "guilds", label: "Гильдии", icon: "🏰", perm: "guild.view" },
  { id: "events", label: "Мировые события", icon: "🌌", perm: "world_event.view" },
  { id: "achievements", label: "Достижения", icon: "🏆", perm: "achievement.view" },
  { id: "messages", label: "Очередь сообщений", icon: "📨", perm: "messages.view_queue" },
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
  workshops: "Ремесло и экономика", workshop_messages: "Ремесло и экономика",
  upgrades: "Ремесло и экономика", enchants: "Ремесло и экономика",
  disassembles: "Ремесло и экономика", fines: "Ремесло и экономика",
  taverns: "Ремесло и экономика", casino: "Ремесло и экономика",
  housing: "Ремесло и экономика", promos: "Ремесло и экономика",
  site: "Сайт и профиль", profile_layout: "Сайт и профиль",
  levels: "Прогрессия", exp: "Прогрессия", registration: "Прогрессия", races: "Прогрессия",
  messages: "Система", reference: "Система", audit: "Система",
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
  formula: "formulas", profession: "professions", workshop: "workshops",
  workshop_message: "workshop_messages", item_upgrade: "upgrades",
  item_enchant: "enchants", item_disassemble: "disassembles", reputation: "reputations",
  addiction: "addictions", tolerance: "tolerances", tavern: "taverns",
  sublocation: "sublocations", sublocation_node: "sublocations", sublocation_transition: "sublocations",
  npc_ally: "npc-allies", mole: "mole", casino: "casino", housing: "housing",
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
        {active === "taverns" && hasPerm("tavern.view") && <TavernSection guarded={guarded} hasPerm={hasPerm} />}
        {active === "recipes" && hasPerm("recipe.view") && <RecipesSection guarded={guarded} hasPerm={hasPerm} />}
        {active === "professions" && hasPerm("profession.view") && <LibrarySection guarded={guarded} hasPerm={hasPerm} config={PROFESSION_CONFIG} />}
        {active === "workshops" && hasPerm("workshop.view") && <LibrarySection guarded={guarded} hasPerm={hasPerm} config={WORKSHOP_CONFIG} />}
        {active === "workshop_messages" && hasPerm("workshop_message.view") && <WorkshopMessagesSection guarded={guarded} hasPerm={hasPerm} />}
        {active === "upgrades" && hasPerm("recipe.view") && <LibrarySection guarded={guarded} hasPerm={hasPerm} config={UPGRADE_CONFIG} />}
        {active === "enchants" && hasPerm("recipe.view") && <LibrarySection guarded={guarded} hasPerm={hasPerm} config={ENCHANT_CONFIG} />}
        {active === "disassembles" && hasPerm("recipe.view") && <LibrarySection guarded={guarded} hasPerm={hasPerm} config={DISASSEMBLE_CONFIG} />}
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
        {active === "exp" && hasPerm("exp.view") && <LibrarySection guarded={guarded} hasPerm={hasPerm} config={EXP_CONFIG} />}
        {active === "registration" && hasPerm("registration.view") && <LibrarySection guarded={guarded} hasPerm={hasPerm} config={REGISTRATION_CONFIG} />}
        {active === "races" && hasPerm("race.view") && <LibrarySection guarded={guarded} hasPerm={hasPerm} config={RACE_CONFIG} />}
        {active === "guilds" && hasPerm("guild.view") && <GuildsSection guarded={guarded} hasPerm={hasPerm} />}
        {active === "events" && hasPerm("world_event.view") && <EventsSection guarded={guarded} hasPerm={hasPerm} />}
        {active === "achievements" && hasPerm("achievement.view") && <AchievementsSection guarded={guarded} hasPerm={hasPerm} />}
        {active === "messages" && hasPerm("messages.view_queue") && <MessagesSection guarded={guarded} hasPerm={hasPerm} />}
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
