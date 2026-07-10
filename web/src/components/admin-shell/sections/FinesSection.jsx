import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  createFine,
  deleteFine,
  fetchFine,
  fetchFineMeta,
  fetchFines,
  fineLifecycle,
  updateFine,
  validateFine,
} from "../../../api/adminFinesApi.js";
import { tr, FINE_TYPE, FINE_SOURCE, FINE_ISSUER_ROLE, CURRENCY, FINE_RESTRICTION } from "../../../i18n/adminLabels.js";
import { ConfirmModal } from "../ConfirmModal.jsx";
import { VersionHistory } from "../VersionHistory.jsx";
import { EmojiInput, EmojiTextarea } from "../EmojiField.jsx";
import { MessageComposer } from "../MessageComposer.jsx";
import { SearchBox, NoResults, filterEntities } from "../SearchFilter.jsx";

const STATUS_TONE = { published: "ntv2-badge-owner", error: "ntv2-badge-error", disabled: "ntv2-badge-danger" };

const EMPTY = {
  name: "", type: "city", source: "black_market_raid", currency: "copper",
  short_description: "", description: "",
  base_amount: 100, min_amount: "", max_amount: "",
  first_deadline_days: 7, second_deadline_days: 23, restriction_start_day: 24,
  interest_enabled: true, interest_percent_per_day: 1, interest_start_day: 8,
  restrictions: [], issuer_roles: [],
  stages: [], payment_places: [], removal_methods: [],
  payment_npc_id: "", payment_commission: "", fortress_id: "", city_id: "",
  can_become_permanent: false,
  messages: { on_issue: "", on_pay: "", on_block: "" },
};

function Field({ label, children }) {
  return <label className="ntv2-field"><span>{label}</span>{children}</label>;
}

export function FinesSection({ guarded, hasPerm }) {
  const [meta, setMeta] = useState(null);
  const [list, setList] = useState([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState(null);
  const [confirm, setConfirm] = useState(null);

  const can = useMemo(() => ({
    create: hasPerm("fine_def.create"), edit: hasPerm("fine_def.edit"), validate: hasPerm("fine_def.validate"),
    publish: hasPerm("fine_def.publish"), disable: hasPerm("fine_def.disable"),
    archive: hasPerm("fine_def.archive"), del: hasPerm("fine_def.delete"),
  }), [hasPerm]);

  const load = useCallback(async () => { const p = await guarded(() => fetchFines(statusFilter)); if (p) setList(p.items || []); }, [guarded, statusFilter]);
  useEffect(() => { (async () => { const m = await guarded(() => fetchFineMeta()); if (m) setMeta(m); })(); }, [guarded]);
  useEffect(() => { load(); }, [load]);

  const statuses = meta?.statuses || [];
  const statusLabel = (v) => statuses.find((s) => s.value === v)?.label || v;

  async function openItem(id) {
    const p = await guarded(() => fetchFine(id));
    if (p?.item) setEditing({ id, data: { ...EMPTY, ...(p.item.data || {}), messages: { ...EMPTY.messages, ...(p.item.data?.messages || {}) } }, status: p.item.status, validation: p.validation, isNew: false });
  }
  function startCreate() { setEditing({ id: "", data: { ...EMPTY }, status: "draft", validation: null, isNew: true }); }

  async function save() {
    const e = editing;
    if (e.isNew) { const p = await guarded(() => createFine(e.id.trim(), e.data, ""), "Создано."); if (p?.item) await openItem(e.id.trim()); }
    else { await guarded(() => updateFine(e.id, e.data, "правка"), "Сохранено."); await openItem(e.id); }
    await load();
  }
  async function runValidate() { const p = await guarded(() => validateFine(editing.id, ""), "Проверка выполнена."); if (p?.validation) setEditing((c) => ({ ...c, validation: p.validation })); }
  async function refreshEditing() { await load(); if (editing) await openItem(editing.id); }

  if (!meta) return <section className="ntv2-section"><h2>Конструктор штрафов</h2><p className="ntv2-hint">Загрузка…</p></section>;

  if (editing) {
    const d = editing.data;
    const set = (k, v) => setEditing({ ...editing, data: { ...d, [k]: v } });
    const setMsg = (k, v) => setEditing({ ...editing, data: { ...d, messages: { ...(d.messages || {}), [k]: v } } });
    const disabled = !(editing.isNew ? can.create : can.edit);
    const v = editing.validation;
    const num = (key, label) => <Field label={label} key={key}><input type="number" value={d[key]} disabled={disabled} onChange={(e) => set(key, e.target.value)} /></Field>;
    const toggleIn = (key, code) => {
      const cur = Array.isArray(d[key]) ? d[key] : [];
      const has = cur.some((x) => (x.code || x) === code);
      set(key, has ? cur.filter((x) => (x.code || x) !== code) : [...cur, key === "restrictions" ? { code } : code]);
    };
    const isOn = (key, code) => (Array.isArray(d[key]) ? d[key] : []).some((x) => (x.code || x) === code);
    return (
      <section className="ntv2-section">
        <div className="ntv2-card-head">
          <button type="button" className="ntv2-btn" onClick={() => setEditing(null)}>← К списку</button>
          <h2>{editing.isNew ? "Новый тип штрафа" : d.name || editing.id}</h2>
          {!editing.isNew ? <span className={`ntv2-badge ${STATUS_TONE[editing.status] || ""}`}>{statusLabel(editing.status)}</span> : null}
        </div>
        {editing.isNew ? <Field label="ID (латиница, напр. city_fine)"><input value={editing.id} onChange={(e) => setEditing({ ...editing, id: e.target.value })} /></Field> : <p className="ntv2-hint ntv2-mono">{editing.id}</p>}

        <div className="ntv2-world-form">
          <div className="ntv2-form-row">
            <Field label="Название"><EmojiInput value={d.name} disabled={disabled} onChange={(v) => set("name", v)} /></Field>
            <Field label="Тип"><select value={d.type} disabled={disabled} onChange={(e) => set("type", e.target.value)}>{meta.fineTypes.map((x) => <option key={x} value={x}>{tr(FINE_TYPE, x)}</option>)}</select></Field>
          </div>
          <div className="ntv2-form-row">
            <Field label="Источник"><select value={d.source} disabled={disabled} onChange={(e) => set("source", e.target.value)}>{meta.sources.map((x) => <option key={x} value={x}>{tr(FINE_SOURCE, x)}</option>)}</select></Field>
            <Field label="Валюта"><select value={d.currency} disabled={disabled} onChange={(e) => set("currency", e.target.value)}>{meta.currencies.map((x) => <option key={x} value={x}>{tr(CURRENCY, x)}</option>)}</select></Field>
          </div>
          <Field label="Краткое описание"><EmojiInput value={d.short_description} disabled={disabled} onChange={(v) => set("short_description", v)} /></Field>
          <Field label="Полное описание"><EmojiTextarea rows={2} value={d.description} disabled={disabled} onChange={(v) => set("description", v)} /></Field>

          <h4 className="ntv2-subhead">Сумма</h4>
          <div className="ntv2-form-row">{num("base_amount", "Базовая сумма")}{num("min_amount", "Мин. сумма")}{num("max_amount", "Макс. сумма")}</div>

          <h4 className="ntv2-subhead">Сроки и проценты</h4>
          <div className="ntv2-form-row">{num("first_deadline_days", "1-й срок (дн.)")}{num("second_deadline_days", "2-й срок (дн.)")}{num("restriction_start_day", "Ограничения с дня")}</div>
          <div className="ntv2-form-row" style={{ gap: 14, alignItems: "center" }}>
            <label className="ntv2-check"><input type="checkbox" checked={Boolean(d.interest_enabled)} disabled={disabled} onChange={(e) => set("interest_enabled", e.target.checked)} /> Начислять проценты</label>
            {num("interest_percent_per_day", "Процент в день %")}{num("interest_start_day", "Проценты с дня")}
          </div>

          <div className="ntv2-panel">
            <h4 className="ntv2-subhead">Ограничения</h4>
            <div className="ntv2-form-row" style={{ gap: 10 }}>
              {(meta.restrictions || []).map((code) => (
                <label className="ntv2-check" key={code}><input type="checkbox" checked={isOn("restrictions", code)} disabled={disabled} onChange={() => toggleIn("restrictions", code)} /> {tr(FINE_RESTRICTION, code)}</label>
              ))}
            </div>
          </div>

          <div className="ntv2-panel">
            <h4 className="ntv2-subhead">Стадии штрафа (ТЗ 2.0 §9–§10)</h4>
            {(Array.isArray(d.stages) ? d.stages : []).map((row, i) => {
              const upd = (c, val) => set("stages", d.stages.map((r, idx) => idx === i ? { ...r, [c]: val } : r));
              return (
                <div className="ntv2-form-row" key={i} style={{ gap: 6, alignItems: "flex-end", flexWrap: "wrap" }}>
                  <Field label="Стадия"><select value={row.stage || ""} disabled={disabled} onChange={(e) => upd("stage", e.target.value)}><option value="">—</option>{(meta.stages || []).map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}</select></Field>
                  <Field label="Срок (дней)"><input type="number" style={{ width: 80 }} value={row.duration_days ?? ""} disabled={disabled} onChange={(e) => upd("duration_days", e.target.value)} /></Field>
                  <Field label="Базовая сумма"><input type="number" style={{ width: 100 }} value={row.base_amount ?? ""} disabled={disabled} onChange={(e) => upd("base_amount", e.target.value)} /></Field>
                  <Field label="% увеличения"><input type="number" style={{ width: 90 }} value={row.percent_increase ?? ""} disabled={disabled} onChange={(e) => upd("percent_increase", e.target.value)} /></Field>
                  <label className="ntv2-check"><input type="checkbox" checked={Boolean(row.force_fortress)} disabled={disabled} onChange={(e) => upd("force_fortress", e.target.checked)} /> В крепость</label>
                  <label className="ntv2-check"><input type="checkbox" checked={Boolean(row.block_city)} disabled={disabled} onChange={(e) => upd("block_city", e.target.checked)} /> Запрет города</label>
                  <label className="ntv2-check"><input type="checkbox" checked={Boolean(row.permanent)} disabled={disabled} onChange={(e) => upd("permanent", e.target.checked)} /> Бессрочная</label>
                  <Field label="Текст стадии"><input value={row.text || ""} disabled={disabled} onChange={(e) => upd("text", e.target.value)} /></Field>
                  {!disabled ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => set("stages", d.stages.filter((_, idx) => idx !== i))}>×</button> : null}
                </div>
              );
            })}
            {!disabled ? <button type="button" className="ntv2-btn" style={{ marginTop: 6 }} onClick={() => set("stages", [...(Array.isArray(d.stages) ? d.stages : []), { stage: "first" }])}>＋ Стадия</button> : null}
          </div>

          <div className="ntv2-panel">
            <h4 className="ntv2-subhead">Оплата и снятие (ТЗ 2.0 §14)</h4>
            <div className="ntv2-form-row" style={{ gap: 14 }}>
              <label className="ntv2-check"><input type="checkbox" checked={Boolean(d.can_become_permanent)} disabled={disabled} onChange={(e) => set("can_become_permanent", e.target.checked)} /> Может стать бессрочным</label>
              <Field label="NPC оплаты (id)"><input value={d.payment_npc_id || ""} disabled={disabled} onChange={(e) => set("payment_npc_id", e.target.value)} /></Field>
              <Field label="Комиссия оплаты"><input type="number" style={{ width: 100 }} value={d.payment_commission ?? ""} disabled={disabled} onChange={(e) => set("payment_commission", e.target.value)} /></Field>
              <Field label="Крепость (id)"><input value={d.fortress_id || ""} disabled={disabled} onChange={(e) => set("fortress_id", e.target.value)} /></Field>
              <Field label="Город (id)"><input value={d.city_id || ""} disabled={disabled} onChange={(e) => set("city_id", e.target.value)} /></Field>
            </div>
            <div className="ntv2-subhead" style={{ fontSize: 12, marginTop: 6 }}>Места оплаты</div>
            <div className="ntv2-form-row" style={{ gap: 10 }}>
              {(meta.paymentPlaces || []).map((p) => (
                <label className="ntv2-check" key={p.value}><input type="checkbox" checked={(d.payment_places || []).includes(p.value)} disabled={disabled} onChange={() => set("payment_places", (d.payment_places || []).includes(p.value) ? d.payment_places.filter((x) => x !== p.value) : [...(d.payment_places || []), p.value])} /> {p.label}</label>
              ))}
            </div>
            <div className="ntv2-subhead" style={{ fontSize: 12, marginTop: 6 }}>Способы снятия</div>
            <div className="ntv2-form-row" style={{ gap: 10 }}>
              {(meta.removalMethods || []).map((m) => (
                <label className="ntv2-check" key={m.value}><input type="checkbox" checked={(d.removal_methods || []).includes(m.value)} disabled={disabled} onChange={() => set("removal_methods", (d.removal_methods || []).includes(m.value) ? d.removal_methods.filter((x) => x !== m.value) : [...(d.removal_methods || []), m.value])} /> {m.label}</label>
              ))}
            </div>
          </div>

          <div className="ntv2-panel">
            <h4 className="ntv2-subhead">Кто может выдать</h4>
            <div className="ntv2-form-row" style={{ gap: 10 }}>
              {(meta.issuerRoles || []).map((code) => (
                <label className="ntv2-check" key={code}><input type="checkbox" checked={isOn("issuer_roles", code)} disabled={disabled} onChange={() => toggleIn("issuer_roles", code)} /> {tr(FINE_ISSUER_ROLE, code)}</label>
              ))}
            </div>
          </div>

          <div className="ntv2-panel">
            <h4 className="ntv2-subhead">Сообщения игроку</h4>
            <Field label="При получении штрафа"><EmojiTextarea rows={2} value={d.messages?.on_issue || ""} disabled={disabled} onChange={(v) => setMsg("on_issue", v)} /></Field>
            <Field label="При оплате"><EmojiTextarea rows={2} value={d.messages?.on_pay || ""} disabled={disabled} onChange={(v) => setMsg("on_pay", v)} /></Field>
            <Field label="При запрете входа"><EmojiTextarea rows={2} value={d.messages?.on_block || ""} disabled={disabled} onChange={(v) => setMsg("on_block", v)} /></Field>
          </div>

          <MessageComposer label="Уведомление о штрафе (изображение/формат/предпросмотр)" value={d.issue_message} category="fines" uploadKey={`${editing.id || "fine"}_msg`} disabled={disabled} onChange={(v) => set("issue_message", v)} />
        </div>

        {v ? (
          <div className={`ntv2-panel ${v.ok ? "" : "ntv2-danger-zone"}`}>
            <h4 className="ntv2-subhead">{v.ok ? "✅ Готов к публикации" : "❌ Проверка не пройдена"}</h4>
            {(v.errors || []).map((e, i) => <div className="ntv2-error" key={"e" + i}>{e}</div>)}
            {(v.warnings || []).map((w, i) => <p className="ntv2-hint" key={"w" + i}>⚠️ {w}</p>)}
          </div>
        ) : null}

        <div className="ntv2-form-row" style={{ marginTop: 14 }}>
          {!disabled ? <button type="button" className="ntv2-btn ntv2-btn-primary" disabled={editing.isNew && !editing.id.trim()} onClick={save}>{editing.isNew ? "Создать" : "Сохранить"}</button> : null}
          {!editing.isNew && can.validate ? <button type="button" className="ntv2-btn" onClick={runValidate}>Проверить</button> : null}
          {!editing.isNew && can.publish ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => setConfirm({ title: "Опубликовать тип штрафа?", dangerous: true, confirmLabel: "Опубликовать", body: <p>Тип штрафа будет проверен и опубликован.</p>, run: async (r) => { await guarded(() => fineLifecycle(editing.id, "publish", r), "Опубликовано."); await refreshEditing(); } })}>Опубликовать</button> : null}
          {!editing.isNew && can.disable && editing.status === "published" ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => setConfirm({ title: "Отключить?", dangerous: true, confirmLabel: "Отключить", body: <p>Тип штрафа перестанет применяться.</p>, run: async (r) => { await guarded(() => fineLifecycle(editing.id, "disable", r), "Отключено."); await refreshEditing(); } })}>Отключить</button> : null}
          {!editing.isNew && can.archive ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => setConfirm({ title: "В архив?", dangerous: true, confirmLabel: "В архив", body: <p>Тип штрафа уйдёт в архив.</p>, run: async (r) => { await guarded(() => fineLifecycle(editing.id, "archive", r), "В архиве."); await refreshEditing(); } })}>В архив</button> : null}
          {!editing.isNew && can.del ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => setConfirm({ title: "Удалить тип штрафа?", dangerous: true, confirmLabel: "Удалить", body: <p>Полное удаление определения типа штрафа.</p>, run: async (r) => { await guarded(() => deleteFine(editing.id, editing.id, r), "Удалено."); setEditing(null); await load(); } })}>Удалить</button> : null}
        </div>

        {!editing.isNew ? <VersionHistory base="fines" id={editing.id} canRollback={can.edit} onRolledBack={refreshEditing} /> : null}

        <ConfirmModal open={Boolean(confirm)} title={confirm?.title} body={confirm?.body} dangerous={confirm?.dangerous} confirmLabel={confirm?.confirmLabel} requireReason
          onConfirm={async (r) => { await confirm.run(r); setConfirm(null); }} onCancel={() => setConfirm(null)} />
      </section>
    );
  }

  return (
    <section className="ntv2-section">
      <h2>Конструктор штрафов</h2>
      <div className="ntv2-filters">
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="">Все статусы</option>
          {statuses.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
        </select>
        {can.create ? <button type="button" className="ntv2-btn ntv2-btn-primary" onClick={startCreate}>＋ Новый тип штрафа</button> : null}
      </div>
      <div className="ntv2-filters"><SearchBox value={query} onChange={setQuery} /></div>
      {!list.length ? <p className="ntv2-hint">Типов штрафов пока нет.</p> : null}
      <NoResults items={list} query={query} />
      <div className="ntv2-list">
        {filterEntities(list, query).map((item) => (
          <button key={item.id} type="button" className="ntv2-list-row ntv2-player-row" onClick={() => openItem(item.id)}>
            <b>{item.data?.name || item.id}</b>
            <span className="ntv2-mono">{item.id}</span>
            <span className={`ntv2-badge ${STATUS_TONE[item.status] || ""}`}>{statusLabel(item.status)}</span>
            {item.data?.type ? <span className="ntv2-hint">{tr(FINE_TYPE, item.data.type)}</span> : null}
          </button>
        ))}
      </div>
    </section>
  );
}
