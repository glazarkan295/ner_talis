import React, { useState } from "react";
import { fetchEntityHistory, rollbackEntity } from "../../api/adminVersioningApi.js";

// Переиспользуемый блок «История версий» для EntityStore-конструкторов (Этап 1).
// base — сегмент пути (effects/fines/recipes/skills/achievements), id — объект.
// canRollback — есть ли право редактирования; onRolledBack — обновить список.
export function VersionHistory({ base, id, canRollback = false, onRolledBack }) {
  const [open, setOpen] = useState(false);
  const [history, setHistory] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function load() {
    setBusy(true); setError(""); setNotice("");
    try {
      const payload = await fetchEntityHistory(base, id);
      setHistory(payload.history || []);
      setOpen(true);
    } catch (e) {
      setError(e.message || "Не удалось загрузить историю.");
    } finally {
      setBusy(false);
    }
  }

  async function rollback(version) {
    if (!window.confirm(`Откатить к версии ${version}? Текущая версия сохранится в истории — откат обратим.`)) return;
    setBusy(true); setError(""); setNotice("");
    try {
      await rollbackEntity(base, id, version, "");
      setNotice(`Откат к версии ${version} выполнен.`);
      await load();
      onRolledBack?.();
    } catch (e) {
      setError(e.message || "Откат не выполнен.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="ntv2-version-history">
      <button type="button" className="ntv2-btn" disabled={busy} onClick={() => (open ? setOpen(false) : load())}>
        {open ? "Скрыть историю" : "История версий"}
      </button>
      {error ? <div className="ntv2-error">{error}</div> : null}
      {notice ? <p className="ntv2-hint">{notice}</p> : null}
      {open && history !== null ? (
        <div className="ntv2-panel" style={{ marginTop: 8 }}>
          <h4 className="ntv2-subhead">История версий</h4>
          {history.length ? (
            <div className="ntv2-list">
              {[...history].reverse().map((h) => (
                <div className="ntv2-list-row" key={h.version}>
                  <span className="ntv2-badge">в.{h.version}</span>
                  <b>{(h.data && (h.data.name || h.data.title || h.data.effect_name)) || "—"}</b>
                  <span className="ntv2-hint ntv2-mono">{h.updated_at || ""}</span>
                  {canRollback ? <button type="button" className="ntv2-btn" disabled={busy} onClick={() => rollback(h.version)}>Откатить</button> : null}
                </div>
              ))}
            </div>
          ) : <p className="ntv2-hint">История пуста — объект ещё не редактировался.</p>}
        </div>
      ) : null}
    </div>
  );
}
