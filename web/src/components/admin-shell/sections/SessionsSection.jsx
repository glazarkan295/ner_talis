import React, { useCallback, useEffect, useState } from "react";
import { fetchSessions, revokeSession } from "../../../api/adminV2Api.js";

export function SessionsSection({ guarded, canRevoke }) {
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [confirm, setConfirm] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const payload = await guarded(() => fetchSessions());
      if (payload) setSessions(payload.sessions || []);
    } finally {
      setLoading(false);
    }
  }, [guarded]);

  useEffect(() => { load(); }, [load]);

  async function doRevoke() {
    if (!confirm) return;
    await guarded(() => revokeSession(confirm.id, "отозвана из панели V2"), "Сессия отозвана.");
    setConfirm(null);
    await load();
  }

  return (
    <section className="ntv2-section">
      <h2>Активные сессии</h2>
      {loading ? <p className="ntv2-hint">Загрузка…</p> : null}
      {!loading && !sessions.length ? <p className="ntv2-hint">Активных сессий нет.</p> : null}

      <div className="ntv2-list">
        {sessions.map((s) => (
          <div className={`ntv2-list-row${s.isCurrent ? " ntv2-list-row-current" : ""}`} key={s.id}>
            <span className="ntv2-mono">{s.platform}:{s.adminUserId}</span>
            <span className="ntv2-badge">{s.role}</span>
            <span className="ntv2-hint">{s.scope || "—"} · до {s.expiresAt || "—"}</span>
            {s.isCurrent ? <span className="ntv2-badge ntv2-badge-owner">текущая</span> : null}
            {canRevoke && !s.isCurrent ? (
              <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => setConfirm(s)}>Отозвать</button>
            ) : null}
          </div>
        ))}
      </div>

      {confirm ? (
        <div className="ntv2-modal-overlay" role="dialog" aria-modal="true">
          <div className="ntv2-modal ntv2-modal-danger">
            <h3>Отозвать сессию?</h3>
            <p className="ntv2-modal-danger-tag">⚠️ Опасное действие</p>
            <p>Сессия <b>{confirm.platform}:{confirm.adminUserId}</b> ({confirm.role}) перестанет работать немедленно.</p>
            <div className="ntv2-modal-actions">
              <button type="button" className="ntv2-btn" onClick={() => setConfirm(null)}>Отмена</button>
              <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={doRevoke}>Отозвать</button>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}
