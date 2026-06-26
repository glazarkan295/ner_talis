import React, { useCallback, useEffect, useMemo, useState } from "react";
import "./AdminShell.css";
import { fetchMe, getAdminSessionToken } from "../../api/adminV2Api.js";
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
import { LibrarySection } from "./sections/LibrarySection.jsx";

const TRAIT_CONFIG = {
  base: "traits", title: "Конструктор черт мобов", permPrefix: "trait",
  newLabel: "Новая черта", nameField: "trait_name",
  importLabel: "Импортировать библиотеку черт?", importText: "50 универсальных черт будут заведены как опубликованные записи (без дублей).",
  fields: [
    { key: "trait_name", label: "Название", type: "text" },
    { key: "trait_rank", label: "Ранг", type: "select", metaKey: "traitRanks" },
    { key: "trigger", label: "Триггер", type: "select", metaKey: "triggers" },
    { key: "stack_rule", label: "Правило стака", type: "select", metaKey: "stackRules" },
    { key: "player_text", label: "Текст для игрока", type: "textarea" },
    { key: "admin_description", label: "Описание для админа", type: "textarea" },
    { key: "applicable_mob_categories", label: "Категории мобов", type: "multiselect", metaKey: "mobCategories" },
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
    { key: "title", label: "Заголовок", type: "text" },
    { key: "level", label: "Уровень", type: "number" },
    { key: "exp_required", label: "Опыт до уровня", type: "number" },
    { key: "stat_points", label: "Очки характеристик", type: "number" },
    { key: "skill_points", label: "Очки навыков", type: "number" },
    { key: "exp_formula_id", label: "Формула опыта (ТЗ 13 §2.8)", type: "formularef" },
    { key: "description", label: "Описание", type: "textarea" },
  ],
};
const EXP_CONFIG = {
  base: "exp", title: "Конструктор опыта", permPrefix: "exp",
  newLabel: "Новый источник опыта", nameField: "name",
  fields: [
    { key: "name", label: "Название", type: "text" },
    { key: "source_type", label: "Тип источника", type: "select", metaKey: "sourceTypes" },
    { key: "base_exp", label: "Базовый опыт", type: "number" },
    { key: "level_scaling_percent", label: "Масштаб по уровню, %", type: "number" },
    { key: "formula_id", label: "Формула (ТЗ 13 §2.8)", type: "formularef" },
    { key: "notes", label: "Заметки", type: "textarea" },
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
    { key: "race_name", label: "Название", type: "text" },
    { key: "description", label: "Описание", type: "textarea" },
    { key: "lore", label: "Лор", type: "textarea" },
    { key: "model_image", label: "Изображение модели (/assets/…)", type: "text" },
    { key: "playable", label: "Доступна для игры", type: "checkbox" },
    { key: "stat_bonuses", label: "Бонусы характеристик", type: "numbergroup", sub: _STAT_SUB },
    { key: "starting_stats", label: "Стартовые характеристики", type: "numbergroup", sub: _STAT_SUB },
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
import { AuditSection } from "./sections/AuditSection.jsx";
import { ReferenceSection } from "./sections/ReferenceSection.jsx";
import { RolesSection } from "./sections/RolesSection.jsx";
import { SessionsSection } from "./sections/SessionsSection.jsx";

// Permission constants mirror services/admin_rbac.py. The owner sentinel "*"
// is handled by hasPerm below, so listing the concrete permission is enough.
const NAV = [
  { id: "overview", label: "Обзор", icon: "🏠", perm: null },
  { id: "graph", label: "Интерактивная схема", icon: "🕸️", perm: "graph.view" },
  { id: "players", label: "Игроки", icon: "👤", perm: "players.view" },
  { id: "world", label: "Конструктор мира", icon: "🌍", perm: "world.view" },
  { id: "sublocations", label: "Конструктор подлокаций", icon: "🕳️", perm: "world.view" },
  { id: "items", label: "Конструктор предметов", icon: "📦", perm: "item.view" },
  { id: "effects", label: "Конструктор эффектов", icon: "✨", perm: "effect.view" },
  { id: "fines", label: "Конструктор штрафов", icon: "⚖️", perm: "fine_def.view" },
  { id: "skills", label: "Конструктор навыков", icon: "🌀", perm: "skill_def.view" },
  { id: "site", label: "Конструктор сайта", icon: "🌐", perm: "site.view" },
  { id: "profile_layout", label: "Раскладка профиля", icon: "🪪", perm: "profile_layout.view" },
  { id: "city", label: "Город и крепость", icon: "🏙️", perm: "city.view" },
  { id: "recipes", label: "Конструктор ремесла", icon: "⚒️", perm: "recipe.view" },
  { id: "professions", label: "Профессии ремесла", icon: "🛠️", perm: "profession.view" },
  { id: "workshops", label: "Мастерские", icon: "🏭", perm: "workshop.view" },
  { id: "workshop_messages", label: "Сообщения мастерских", icon: "🧾", perm: "workshop_message.view" },
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
  { id: "reference", label: "Справочник", icon: "📖", perm: null },
  { id: "audit", label: "Аудит", icon: "📜", perm: "audit.view" },
  { id: "sessions", label: "Сессии", icon: "🔑", perm: "system.view" },
  { id: "roles", label: "Роли и доступ", icon: "🛡️", perm: "roles.manage" },
];

function makeHasPerm(me) {
  const perms = new Set(me?.permissions || []);
  const owner = Boolean(me?.isOwner);
  return (perm) => !perm || owner || perms.has("*") || perms.has(perm);
}

export function AdminShell() {
  const [me, setMe] = useState(null);
  const [active, setActive] = useState("overview");
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

  // If the active tab becomes unavailable (role downgraded), fall back to overview.
  useEffect(() => {
    if (!visibleNav.some((item) => item.id === active)) setActive("overview");
  }, [visibleNav, active]);

  if (booting) {
    return <div className="ntv2"><div className="ntv2-boot">Загрузка админ-панели V2…</div></div>;
  }
  if (!me) {
    return <div className="ntv2"><div className="ntv2-boot ntv2-error">{error || "Сессия недоступна."}</div></div>;
  }

  return (
    <div className="ntv2">
      <aside className="ntv2-sidebar">
        <div className="ntv2-brand">
          <div className="ntv2-brand-title">Нер-Талис</div>
          <div className="ntv2-brand-sub">Админ-консоль V2</div>
        </div>
        <nav className="ntv2-nav">
          {visibleNav.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`ntv2-nav-item${active === item.id ? " active" : ""}`}
              onClick={() => setActive(item.id)}
            >
              <span className="ntv2-nav-icon">{item.icon}</span>
              <span>{item.label}</span>
            </button>
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

        {active === "overview" && <OverviewSection me={me} />}
        {active === "players" && hasPerm("players.view") && <PlayersSection guarded={guarded} hasPerm={hasPerm} />}
        {active === "graph" && hasPerm("graph.view") && <GraphSection guarded={guarded} hasPerm={hasPerm} onOpenSection={setActive} />}
        {active === "world" && hasPerm("world.view") && <WorldSection guarded={guarded} hasPerm={hasPerm} />}
        {active === "sublocations" && hasPerm("world.view") && <SublocationsSection guarded={guarded} hasPerm={hasPerm} />}
        {active === "items" && hasPerm("item.view") && <ItemsSection guarded={guarded} hasPerm={hasPerm} />}
        {active === "effects" && hasPerm("effect.view") && <EffectsSection guarded={guarded} hasPerm={hasPerm} />}
        {active === "fines" && hasPerm("fine_def.view") && <FinesSection guarded={guarded} hasPerm={hasPerm} />}
        {active === "skills" && hasPerm("skill_def.view") && <SkillsSection guarded={guarded} hasPerm={hasPerm} />}
        {active === "site" && hasPerm("site.view") && <SiteSection guarded={guarded} hasPerm={hasPerm} />}
        {active === "profile_layout" && hasPerm("profile_layout.view") && <ProfileLayoutSection guarded={guarded} hasPerm={hasPerm} />}
        {active === "city" && hasPerm("city.view") && <CitySection guarded={guarded} hasPerm={hasPerm} />}
        {active === "recipes" && hasPerm("recipe.view") && <RecipesSection guarded={guarded} hasPerm={hasPerm} />}
        {active === "professions" && hasPerm("profession.view") && <LibrarySection guarded={guarded} hasPerm={hasPerm} config={PROFESSION_CONFIG} />}
        {active === "workshops" && hasPerm("workshop.view") && <LibrarySection guarded={guarded} hasPerm={hasPerm} config={WORKSHOP_CONFIG} />}
        {active === "workshop_messages" && hasPerm("workshop_message.view") && <WorkshopMessagesSection guarded={guarded} hasPerm={hasPerm} />}
        {active === "formulas" && hasPerm("formula.view") && <FormulasSection guarded={guarded} hasPerm={hasPerm} />}
        {active === "camps" && hasPerm("camp.view") && <CampSection guarded={guarded} hasPerm={hasPerm} />}
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
