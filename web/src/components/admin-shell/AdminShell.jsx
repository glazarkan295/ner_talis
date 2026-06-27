import React, { useCallback, useEffect, useMemo, useState } from "react";
import "./AdminShell.css";
import { fetchMe, getAdminSessionToken } from "../../api/adminV2Api.js";
import { globalSearch } from "../../api/adminSearchApi.js";
import { OverviewSection } from "./sections/OverviewSection.jsx";
import { PlayersSection } from "./sections/PlayersSection.jsx";
import { WorldSection } from "./sections/WorldSection.jsx";
import { GuildsSection } from "./sections/GuildsSection.jsx";
import { EventsSection } from "./sections/EventsSection.jsx";
import { AchievementsSection } from "./sections/AchievementsSection.jsx";
import { MessagesSection } from "./sections/MessagesSection.jsx";
import { PromosSection } from "./sections/PromosSection.jsx";
import { ItemsSection } from "./sections/ItemsSection.jsx";
import { EffectsSection } from "./sections/EffectsSection.jsx";
import { FinesSection } from "./sections/FinesSection.jsx";
import { SkillsSection } from "./sections/SkillsSection.jsx";
import { SiteSection } from "./sections/SiteSection.jsx";
import { ProfileLayoutSection } from "./sections/ProfileLayoutSection.jsx";
import { CitySection } from "./sections/CitySection.jsx";
import { RecipesSection } from "./sections/RecipesSection.jsx";
import { CampSection } from "./sections/CampSection.jsx";
import { GraphSection } from "./sections/GraphSection.jsx";
import { SublocationsSection } from "./sections/SublocationsSection.jsx";
import { FormulasSection } from "./sections/FormulasSection.jsx";
import { WorkshopMessagesSection } from "./sections/WorkshopMessagesSection.jsx";
import { ReputationSection } from "./sections/ReputationSection.jsx";
import { TavernSection } from "./sections/TavernSection.jsx";
import { ImportSection } from "./sections/ImportSection.jsx";
import { TextsSection } from "./sections/TextsSection.jsx";
import { DashboardSection } from "./sections/DashboardSection.jsx";
import { LibrarySection } from "./sections/LibrarySection.jsx";

const TRAIT_CONFIG = {
  base: "traits", title: "Конструктор черт мобов", permPrefix: "trait",
  newLabel: "Новая черта", nameField: "trait_name",
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
  world: "Мир", sublocations: "Мир", city: "Мир", camps: "Мир", events: "Мир",
  items: "Контент", achievements: "Контент", traits: "Контент",
  blessings: "Контент", phases: "Контент", texts: "Контент",
  effects: "Бой", addictions: "Бой", tolerances: "Бой", skills: "Бой",
  formulas: "Бой", reputations: "Бой",
  recipes: "Ремесло и экономика", professions: "Ремесло и экономика",
  workshops: "Ремесло и экономика", workshop_messages: "Ремесло и экономика",
  upgrades: "Ремесло и экономика", enchants: "Ремесло и экономика",
  disassembles: "Ремесло и экономика", fines: "Ремесло и экономика",
  taverns: "Ремесло и экономика", promos: "Ремесло и экономика",
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
        <GlobalSearch guarded={guarded} onOpen={setActive} />
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
      </main>
    </div>
  );
}
