import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  cancelMessage,
  deleteMessage,
  fetchMessages,
  fetchMessagesMeta,
  fetchMessagesStats,
  retryMessage,
  runDispatcher,
} from "../../../api/adminMessagesApi.js";
import { TechnicalData } from "../TechnicalData.jsx";

const STATUS_TONE = {
  sent: "ntv2-badge-owner", delivered: "ntv2-badge-owner",
  failed: "ntv2-badge-error", blocked: "ntv2-badge-error",
  retry_wait: "ntv2-badge-error", cancelled: "ntv2-badge-danger",
};
const STATUS_LABEL={queued:"Ожидает очередь",sending:"Отправляется",sent:"Отправлено",delivered:"Доставлено",failed:"Ошибка отправки",retry_wait:"Ожидает повтор",cancelled:"Отменено",blocked:"Платформа недоступна",expired:"Истекло",waiting_timer:"Ожидает таймер",waiting_battle:"Ожидает завершение боя",waiting_event:"Ожидает завершение события",waiting_action:"Ожидает действие игрока",notification_pending:"Нет доступной платформы",deleted:"Удалено админом"};

export function MessagesSection({ guarded, hasPerm }) {
  const [meta, setMeta] = useState(null);
  const [stats, setStats] = useState(null);
  const [items, setItems] = useState([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [errorsOnly, setErrorsOnly] = useState(false);

  const can = useMemo(() => ({
    retry: hasPerm("messages.retry"), cancel: hasPerm("messages.cancel"),
    dispatch: hasPerm("messages.manage_dispatcher"),
  }), [hasPerm]);

  const loadStats = useCallback(async () => { const s = await guarded(() => fetchMessagesStats()); if (s) setStats(s); }, [guarded]);
  const load = useCallback(async () => {
    const p = await guarded(() => fetchMessages({ status: statusFilter, errors_only: errorsOnly, limit: 200 }));
    if (p) setItems(p.messages || []);
  }, [guarded, statusFilter, errorsOnly]);

  useEffect(() => { (async () => { const m = await guarded(() => fetchMessagesMeta()); if (m) setMeta(m); })(); }, [guarded]);
  useEffect(() => { loadStats(); }, [loadStats]);
  useEffect(() => { load(); }, [load]);

  async function refresh() { await Promise.all([load(), loadStats()]); }

  if (!meta) return <section className="ntv2-section"><h2>Очередь сообщений</h2><p className="ntv2-hint">Загрузка…</p></section>;

  const byStatus = stats?.stats?.by_status || {};
  const disp = stats?.dispatcher || meta.dispatcher || {};

  return (
    <section className="ntv2-section">
      <h2>Очередь сообщений</h2>

      <div className="ntv2-cards">
        <div className="ntv2-card"><div className="ntv2-card-label">Всего</div><div className="ntv2-card-value">{stats?.stats?.total ?? "—"}</div></div>
        <div className="ntv2-card"><div className="ntv2-card-label">Ожидают</div><div className="ntv2-card-value">{(byStatus.queued || 0) + (byStatus.retry_wait || 0)}</div></div>
        <div className="ntv2-card"><div className="ntv2-card-label">Отправлено</div><div className="ntv2-card-value">{byStatus.sent || 0}</div></div>
        <div className="ntv2-card"><div className="ntv2-card-label">Ошибки</div><div className="ntv2-card-value">{(byStatus.failed || 0) + (byStatus.blocked || 0)}</div></div>
        <div className="ntv2-card">
          <div className="ntv2-card-label">Диспетчер</div>
          <div className="ntv2-card-value">{disp.running ? "🟢 готов" : "⚪ нет sender"}</div>
          <span className="ntv2-hint">в очереди: {disp.pending ?? 0}</span>
        </div>
      </div>
      {disp.last_error ? <p className="ntv2-hint">Последняя ошибка: {disp.last_error}</p> : null}

      <div className="ntv2-filters" style={{ marginTop: 12 }}>
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="">Все статусы</option>
          {meta.statuses.map((s) => <option key={s} value={s}>{STATUS_LABEL[s] || s}</option>)}
        </select>
        <label className="ntv2-check"><input type="checkbox" checked={errorsOnly} onChange={(e) => setErrorsOnly(e.target.checked)} /> Только ошибки</label>
        <button type="button" className="ntv2-btn" onClick={refresh}>Обновить</button>
        {can.dispatch ? <button type="button" className="ntv2-btn ntv2-btn-primary" onClick={() => guarded(() => runDispatcher("ручной прогон"), "Диспетчер выполнен.").then(refresh)}>Прогнать диспетчер</button> : null}
      </div>

      {!items.length ? <p className="ntv2-hint">Сообщений нет.</p> : null}
      <div className="ntv2-list">
        {items.map((m) => (
          <div className="ntv2-audit-row" key={m.id}>
            <div className="ntv2-audit-head">
              <span className={`ntv2-badge ${STATUS_TONE[m.status] || ""}`}>{STATUS_LABEL[m.status] || m.status}</span>
              <span className="ntv2-audit-action">{m.type}</span>
              <span className="ntv2-badge">{m.priority}</span>
              <span className="ntv2-audit-time">{m.platform}:{m.recipient}</span>
            </div>
            <div className="ntv2-audit-meta">
              <span className="ntv2-mono">{m.game_id || "—"}</span>
              <span>попыток: {m.attempts}/{m.max_attempts}</span>
              {m.error ? <span className="ntv2-audit-reason">{m.error}</span> : null}
            </div>
            <div style={{ marginTop: 4 }}>{(m.text || "").slice(0, 160)}</div>
            <div className="ntv2-form-row" style={{ marginTop: 6 }}>
              {can.retry && m.status !== "sent" ? <button type="button" className="ntv2-btn" onClick={() => guarded(() => retryMessage(m.id, "ручной повтор"), "Поставлено на повтор.").then(refresh)}>Повторить</button> : null}
              {can.cancel && !["sent", "cancelled"].includes(m.status) ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => guarded(() => cancelMessage(m.id, "отмена"), "Отменено.").then(refresh)}>Отменить</button> : null}
              {can.cancel && m.status !== "deleted" ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => guarded(() => deleteMessage(m.id, "удаление администратором"), "Удалено.").then(refresh)}>Удалить</button> : null}
            </div>
            <TechnicalData label="Данные сообщения" value={m} />
          </div>
        ))}
      </div>
    </section>
  );
}
