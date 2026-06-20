import React, { useCallback, useEffect, useState } from "react";
import { fetchAudit } from "../../../api/adminV2Api.js";
import { TechnicalData } from "../TechnicalData.jsx";

const EMPTY_FILTERS = {
  admin_user_id: "",
  role: "",
  action_prefix: "",
  target_type: "",
  target_id: "",
  dangerous_only: false,
  errors_only: false,
};

function summarize(record) {
  const who = record.admin_name || record.admin_user_id || "—";
  const action = record.action || "—";
  const target = record.target_name || record.target_id || record.target_type || "";
  return { who, action, target };
}

export function AuditSection({ guarded }) {
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const payload = await guarded(() => fetchAudit({ ...filters, limit: 200 }));
      if (payload) setRecords(payload.records || []);
    } finally {
      setLoading(false);
    }
  }, [filters, guarded]);

  useEffect(() => { load(); }, [load]);

  function setField(key, value) {
    setFilters((old) => ({ ...old, [key]: value }));
  }

  return (
    <section className="ntv2-section">
      <h2>Журнал аудита</h2>
      <div className="ntv2-filters">
        <input placeholder="ID админа" value={filters.admin_user_id} onChange={(e) => setField("admin_user_id", e.target.value)} />
        <input placeholder="Роль" value={filters.role} onChange={(e) => setField("role", e.target.value)} />
        <input placeholder="Действие (префикс, напр. roles.)" value={filters.action_prefix} onChange={(e) => setField("action_prefix", e.target.value)} />
        <input placeholder="Тип объекта" value={filters.target_type} onChange={(e) => setField("target_type", e.target.value)} />
        <input placeholder="ID объекта" value={filters.target_id} onChange={(e) => setField("target_id", e.target.value)} />
        <label className="ntv2-check"><input type="checkbox" checked={filters.dangerous_only} onChange={(e) => setField("dangerous_only", e.target.checked)} /> Только опасные</label>
        <label className="ntv2-check"><input type="checkbox" checked={filters.errors_only} onChange={(e) => setField("errors_only", e.target.checked)} /> Только ошибки</label>
        <button type="button" className="ntv2-btn" onClick={() => setFilters({ ...EMPTY_FILTERS })}>Сбросить</button>
      </div>

      {loading ? <p className="ntv2-hint">Загрузка…</p> : null}
      {!loading && !records.length ? <p className="ntv2-hint">Записей нет.</p> : null}

      <div className="ntv2-audit-list">
        {records.map((record, index) => {
          const { who, action, target } = summarize(record);
          const isError = record.status && record.status !== "ok";
          return (
            <div key={record.created_at + ":" + index} className={`ntv2-audit-row${record.dangerous ? " ntv2-audit-danger" : ""}${isError ? " ntv2-audit-error" : ""}`}>
              <div className="ntv2-audit-head">
                <span className="ntv2-audit-time">{record.created_at || "—"}</span>
                <span className="ntv2-audit-action">{action}</span>
                {record.dangerous ? <span className="ntv2-badge ntv2-badge-danger">опасное</span> : null}
                {isError ? <span className="ntv2-badge ntv2-badge-error">ошибка</span> : null}
              </div>
              <div className="ntv2-audit-meta">
                <span>{who}{record.admin_role ? ` (${record.admin_role})` : ""}</span>
                {target ? <span>→ {target}</span> : null}
                {record.reason ? <span className="ntv2-audit-reason">«{record.reason}»</span> : null}
              </div>
              {record.error ? <div className="ntv2-error">{record.error}</div> : null}
              {(record.before || record.after) ? (
                <TechnicalData label="До / после" value={{ before: record.before, after: record.after }} />
              ) : null}
            </div>
          );
        })}
      </div>
    </section>
  );
}
