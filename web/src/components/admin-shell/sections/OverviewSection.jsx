import React from "react";

// Landing card: who am I, what can I do. Keeps the operator oriented and makes
// the active role obvious (helps debug "почему кнопка не видна").
export function OverviewSection({ me }) {
  const permissions = me?.permissions || [];
  const isOwner = Boolean(me?.isOwner);
  return (
    <section className="ntv2-section">
      <h2>Обзор</h2>
      <div className="ntv2-cards">
        <div className="ntv2-card">
          <div className="ntv2-card-label">Ваша роль</div>
          <div className="ntv2-card-value">{me?.roleLabel || me?.role || "—"}</div>
          {isOwner ? <span className="ntv2-badge ntv2-badge-owner">owner</span> : null}
        </div>
        <div className="ntv2-card">
          <div className="ntv2-card-label">Платформа / ID</div>
          <div className="ntv2-card-value">
            {(me?.platform || "—")} · {me?.admin_user_id || "—"}
          </div>
        </div>
        <div className="ntv2-card">
          <div className="ntv2-card-label">Сессия истекает</div>
          <div className="ntv2-card-value">{me?.sessionExpiresAt || "—"}</div>
        </div>
      </div>

      <h3>Доступные права ({isOwner ? "все" : permissions.length})</h3>
      {isOwner ? (
        <p className="ntv2-hint">Роль owner имеет полный доступ ко всем разделам.</p>
      ) : (
        <div className="ntv2-perm-grid">
          {permissions.map((perm) => (
            <span key={perm} className="ntv2-perm-chip">{perm}</span>
          ))}
          {!permissions.length ? <p className="ntv2-hint">Прав нет — только просмотр.</p> : null}
        </div>
      )}
    </section>
  );
}
