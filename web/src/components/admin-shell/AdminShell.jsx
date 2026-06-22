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
import { AuditSection } from "./sections/AuditSection.jsx";
import { ReferenceSection } from "./sections/ReferenceSection.jsx";
import { RolesSection } from "./sections/RolesSection.jsx";
import { SessionsSection } from "./sections/SessionsSection.jsx";

// Permission constants mirror services/admin_rbac.py. The owner sentinel "*"
// is handled by hasPerm below, so listing the concrete permission is enough.
const NAV = [
  { id: "overview", label: "Обзор", icon: "🏠", perm: null },
  { id: "players", label: "Игроки", icon: "👤", perm: "players.view" },
  { id: "world", label: "Конструктор мира", icon: "🌍", perm: "world.view" },
  { id: "items", label: "Конструктор предметов", icon: "📦", perm: "item.view" },
  { id: "effects", label: "Конструктор эффектов", icon: "✨", perm: "effect.view" },
  { id: "fines", label: "Конструктор штрафов", icon: "⚖️", perm: "fine_def.view" },
  { id: "skills", label: "Конструктор навыков", icon: "🌀", perm: "skill_def.view" },
  { id: "site", label: "Конструктор сайта", icon: "🌐", perm: "site.view" },
  { id: "profile_layout", label: "Раскладка профиля", icon: "🪪", perm: "profile_layout.view" },
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
        {active === "world" && hasPerm("world.view") && <WorldSection guarded={guarded} hasPerm={hasPerm} />}
        {active === "items" && hasPerm("item.view") && <ItemsSection guarded={guarded} hasPerm={hasPerm} />}
        {active === "effects" && hasPerm("effect.view") && <EffectsSection guarded={guarded} hasPerm={hasPerm} />}
        {active === "fines" && hasPerm("fine_def.view") && <FinesSection guarded={guarded} hasPerm={hasPerm} />}
        {active === "skills" && hasPerm("skill_def.view") && <SkillsSection guarded={guarded} hasPerm={hasPerm} />}
        {active === "site" && hasPerm("site.view") && <SiteSection guarded={guarded} hasPerm={hasPerm} />}
        {active === "profile_layout" && hasPerm("profile_layout.view") && <ProfileLayoutSection guarded={guarded} hasPerm={hasPerm} />}
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
