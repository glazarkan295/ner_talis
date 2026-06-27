import React, { useCallback, useEffect, useState } from "react";
import { fetchDashboard } from "../../../api/adminDashboardApi.js";

// Dashboard / Панель состояния (ТЗ 11 §16): счётчики, ошибки, последние
// изменения, активные мировые события, последний импорт + быстрые ссылки.

const QUICK_LINKS = [
  { id: "items", label: "📦 Предметы" },
  { id: "world", label: "🌍 Мир" },
  { id: "effects", label: "✨ Эффекты" },
  { id: "achievements", label: "🏆 Достижения" },
  { id: "texts", label: "💬 Тексты" },
  { id: "import", label: "📥 Импорт" },
  { id: "graph", label: "🕸️ Схема" },
  { id: "players", label: "👤 Игроки" },
];

function Stat({ label, value, tone }) {
  return (
    <div className={`ntdash-stat${tone ? " " + tone : ""}`}>
      <div className="ntdash-stat-value">{value}</div>
      <div className="ntdash-stat-label">{label}</div>
    </div>
  );
}

export function DashboardSection({ guarded, onOpenSection }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    const r = await guarded(() => fetchDashboard());
    if (r) setData(r);
    setLoading(false);
  }, [guarded]);
  useEffect(() => { load(); }, [load]);

  const t = data?.totals || {};

  return (
    <section className="ntv2-section ntdash">
      <style>{DASH_CSS}</style>
      <header className="ntv2-section-head">
        <div>
          <h2>📊 Панель состояния</h2>
          <p className="ntv2-muted">Сводка по контенту, ошибкам и последним изменениям.</p>
        </div>
        <button type="button" className="ntv2-btn" onClick={load} disabled={loading}>↻ Обновить</button>
      </header>

      {loading && !data ? <div className="ntdash-skeleton">Загрузка сводки…</div> : null}

      {data ? (
        <>
          <div className="ntdash-stats">
            <Stat label="Игроков" value={data.players ?? "—"} />
            <Stat label="Объектов контента" value={t.objects ?? 0} />
            <Stat label="Объектов с ошибкой" value={t.errors ?? 0} tone={t.errors ? "bad" : ""} />
            <Stat label="Черновиков" value={t.drafts ?? 0} />
            <Stat label="Проблем связей" value={t.link_issues ?? 0} tone={t.link_issues ? "warn" : ""} />
            <Stat label="Проблем картинок" value={t.image_issues ?? 0} tone={t.image_issues ? "warn" : ""} />
            <Stat label="Активных мировых событий" value={t.active_world_events ?? 0} />
          </div>

          <div className="ntdash-grid">
            <div className="ntv2-panel">
              <h4 className="ntv2-subhead">Контент по конструкторам</h4>
              <table className="ntdash-table">
                <thead><tr><th>Конструктор</th><th>Всего</th><th>Опубл.</th><th>Черн.</th><th>Ошибки</th></tr></thead>
                <tbody>
                  {(data.constructors || []).map((c) => (
                    <tr key={c.key} className={c.section && onOpenSection ? "ntdash-row-link" : ""} onClick={() => c.section && onOpenSection && onOpenSection(c.section)}>
                      <td>{c.label}</td><td>{c.total}</td><td>{c.published}</td><td>{c.drafts}</td>
                      <td className={c.errors ? "ntdash-bad" : ""}>{c.errors}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="ntv2-panel">
              <h4 className="ntv2-subhead">Последние изменения</h4>
              {(data.recent_changes || []).length === 0 ? <p className="ntv2-hint">Записей нет.</p> : null}
              <ul className="ntdash-feed">
                {(data.recent_changes || []).map((r, i) => (
                  <li key={i} className={r.dangerous ? "ntdash-danger" : ""}>
                    <code>{r.action}</code> {r.target_type ? `· ${r.target_type}/${r.target_id ?? ""}` : ""}
                    <small>{r.role || ""} {r.at ? `· ${r.at}` : ""}{r.status && r.status !== "ok" ? ` · ${r.status}` : ""}</small>
                  </li>
                ))}
              </ul>
            </div>
          </div>

          {data.last_import ? (
            <div className="ntv2-panel">
              <h4 className="ntv2-subhead">Последний импорт {data.last_import.dry_run ? "(dry-run)" : ""}</h4>
              <p className="ntv2-hint">
                режим {data.last_import.mode} · создано {data.last_import.created} · обновлено {data.last_import.updated} ·
                пропущено {data.last_import.skipped} · проверить {data.last_import.needs_check}
              </p>
            </div>
          ) : null}

          <div className="ntv2-panel">
            <h4 className="ntv2-subhead">Быстрые ссылки</h4>
            <div className="ntdash-links">
              {QUICK_LINKS.map((l) => (
                <button type="button" key={l.id} className="ntv2-btn-mini" onClick={() => onOpenSection && onOpenSection(l.id)}>{l.label}</button>
              ))}
            </div>
          </div>
        </>
      ) : null}
    </section>
  );
}

const DASH_CSS = `
.ntdash-skeleton{padding:40px;text-align:center;color:#94a3b8;border:1px dashed #cbd5e1;border-radius:12px}
.ntdash-stats{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:14px}
.ntdash-stat{flex:1;min-width:130px;border:1px solid var(--line,#e2e8f0);border-radius:12px;padding:12px;text-align:center;background:var(--card,#f8fafc)}
.ntdash-stat-value{font-size:24px;font-weight:700;color:var(--gold,#b8860b)}
.ntdash-stat-label{font-size:12px;color:#94a3b8;margin-top:4px}
.ntdash-stat.bad .ntdash-stat-value{color:#dc2626}
.ntdash-stat.warn .ntdash-stat-value{color:#d97706}
.ntdash-grid{display:flex;gap:14px;flex-wrap:wrap;align-items:flex-start;margin-bottom:14px}
.ntdash-grid>.ntv2-panel{flex:1;min-width:320px}
.ntdash-table{width:100%;border-collapse:collapse;font-size:13px}
.ntdash-table th,.ntdash-table td{text-align:left;padding:4px 8px;border-bottom:1px solid #f1f5f9}
.ntdash-table th:not(:first-child),.ntdash-table td:not(:first-child){text-align:right}
.ntdash-row-link{cursor:pointer}
.ntdash-row-link:hover{background:rgba(255,255,255,.05)}
.ntdash-bad{color:#dc2626;font-weight:600}
.ntdash-feed{list-style:none;margin:0;padding:0;max-height:320px;overflow:auto}
.ntdash-feed li{padding:6px 4px;border-bottom:1px solid #f1f5f9;font-size:13px;display:flex;flex-direction:column}
.ntdash-feed li small{color:#94a3b8}
.ntdash-feed li.ntdash-danger code{color:#dc2626}
.ntdash-links{display:flex;flex-wrap:wrap;gap:8px}
`;
