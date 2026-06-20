import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  createItem,
  fetchItem,
  fetchItemMeta,
  fetchItems,
  fetchItemUsage,
  hardDeleteItem,
  itemLifecycle,
  updateItem,
  validateItem,
} from "../../../api/adminItemApi.js";
import { ConfirmModal } from "../ConfirmModal.jsx";
import { TechnicalData } from "../TechnicalData.jsx";

const STATUS_TONE = {
  published: "ntv2-badge-owner", error: "ntv2-badge-error",
  disabled: "ntv2-badge-danger", deleted_soft: "ntv2-badge-danger",
};

const EMPTY = {
  name: "", short_description: "", description: "", technical_description: "",
  category: "", item_type: "normal", quality: "common", unique: false,
  item_level: 1, min_player_level: 1, price_buy: 0, price_sell: 0,
  can_buy: true, can_sell: true, can_drop: true, can_trade: true,
  usable: false, equippable: false, equip_slot: "", two_handed: false,
  stackable: false, max_stack: 1, inventory_slot: "", tags: [],
  properties: [], effects: [],
};

function Field({ label, children }) {
  return <label className="ntv2-field"><span>{label}</span>{children}</label>;
}

function RowEditor({ title, rows, onChange, disabled, render, blank }) {
  const list = Array.isArray(rows) ? rows : [];
  const set = (i, patch) => onChange(list.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));
  return (
    <div className="ntv2-panel">
      <h4 className="ntv2-subhead">{title} ({list.length})</h4>
      <div className="ntv2-list">
        {list.map((row, i) => (
          <div className="ntv2-list-row" key={i}>
            {render(row, (patch) => set(i, patch))}
            {!disabled ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => onChange(list.filter((_, idx) => idx !== i))}>×</button> : null}
          </div>
        ))}
      </div>
      {!disabled ? <button type="button" className="ntv2-btn" style={{ marginTop: 8 }} onClick={() => onChange([...list, { ...blank }])}>＋ Добавить</button> : null}
    </div>
  );
}

export function ItemsSection({ guarded, hasPerm }) {
  const [meta, setMeta] = useState(null);
  const [list, setList] = useState([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [editing, setEditing] = useState(null);
  const [usage, setUsage] = useState(null);
  const [confirm, setConfirm] = useState(null);

  const can = useMemo(() => ({
    create: hasPerm("item.create"), edit: hasPerm("item.edit"), editPub: hasPerm("item.edit_published"),
    validate: hasPerm("item.validate"), publish: hasPerm("item.publish"),
    disable: hasPerm("item.disable"), archive: hasPerm("item.archive"),
    deleteSoft: hasPerm("item.delete_soft"), deleteHard: hasPerm("item.delete_hard"),
    restore: hasPerm("item.restore"), usage: hasPerm("item.view_usage"),
  }), [hasPerm]);

  const load = useCallback(async () => { const p = await guarded(() => fetchItems(statusFilter)); if (p) setList(p.items || []); }, [guarded, statusFilter]);
  useEffect(() => { (async () => { const m = await guarded(() => fetchItemMeta()); if (m) setMeta(m); })(); }, [guarded]);
  useEffect(() => { load(); }, [load]);

  const statuses = meta?.statuses || [];
  const statusLabel = (v) => statuses.find((s) => s.value === v)?.label || v;

  async function openItem(id) {
    const p = await guarded(() => fetchItem(id));
    if (p?.item) { setEditing({ id, data: { ...EMPTY, ...(p.item.data || {}) }, status: p.item.status, validation: p.validation, isNew: false }); setUsage(null); }
  }
  function startCreate() { setEditing({ id: "", data: { ...EMPTY }, status: "draft", validation: null, isNew: true }); setUsage(null); }

  async function save() {
    const e = editing;
    if (e.isNew) { const p = await guarded(() => createItem(e.id.trim(), e.data, ""), "Создано."); if (p?.item) await openItem(e.id.trim()); }
    else { await guarded(() => updateItem(e.id, e.data, "правка"), "Сохранено."); await openItem(e.id); }
    await load();
  }
  async function runValidate() { const p = await guarded(() => validateItem(editing.id, ""), "Проверка выполнена."); if (p?.validation) setEditing((c) => ({ ...c, validation: p.validation })); }
  async function loadUsage() { const p = await guarded(() => fetchItemUsage(editing.id)); if (p?.usage) setUsage(p.usage); }
  async function refreshEditing() { await load(); if (editing) await openItem(editing.id); }

  if (!meta) return <section className="ntv2-section"><h2>Конструктор предметов</h2><p className="ntv2-hint">Загрузка…</p></section>;

  if (editing) {
    const d = editing.data;
    const set = (k, v) => setEditing({ ...editing, data: { ...d, [k]: v } });
    const published = editing.status === "published";
    const disabled = editing.isNew ? !can.create : (published ? !can.editPub : !can.edit);
    const v = editing.validation;
    const flag = (key, label) => <label className="ntv2-check" key={key}><input type="checkbox" checked={Boolean(d[key])} disabled={disabled} onChange={(e) => set(key, e.target.checked)} /> {label}</label>;
    return (
      <section className="ntv2-section">
        <div className="ntv2-card-head">
          <button type="button" className="ntv2-btn" onClick={() => setEditing(null)}>← К списку</button>
          <h2>{editing.isNew ? "Новый предмет" : d.name || editing.id}</h2>
          {!editing.isNew ? <span className={`ntv2-badge ${STATUS_TONE[editing.status] || ""}`}>{statusLabel(editing.status)}</span> : null}
        </div>
        {editing.isNew ? <Field label="ID (латиница, напр. iron_sword)"><input value={editing.id} onChange={(e) => setEditing({ ...editing, id: e.target.value })} /></Field> : <p className="ntv2-hint ntv2-mono">{editing.id}</p>}

        <div className="ntv2-world-form">
          <div className="ntv2-form-row">
            <Field label="Название"><input value={d.name} disabled={disabled} onChange={(e) => set("name", e.target.value)} /></Field>
            <Field label="Категория"><select value={d.category} disabled={disabled} onChange={(e) => set("category", e.target.value)}><option value="">— выбрать —</option>{meta.categories.map((c) => <option key={c} value={c}>{c}</option>)}</select></Field>
          </div>
          <div className="ntv2-form-row">
            <Field label="Тип"><select value={d.item_type} disabled={disabled} onChange={(e) => set("item_type", e.target.value)}>{meta.types.map((x) => <option key={x} value={x}>{x}</option>)}</select></Field>
            <Field label="Качество"><select value={d.quality} disabled={disabled} onChange={(e) => set("quality", e.target.value)}>{meta.qualities.map((x) => <option key={x} value={x}>{x}</option>)}</select></Field>
            {flag("unique", "Уникальный")}
            <Field label="Ур. предмета"><input type="number" value={d.item_level} disabled={disabled} onChange={(e) => set("item_level", e.target.value)} /></Field>
            <Field label="Мин. ур. игрока"><input type="number" value={d.min_player_level} disabled={disabled} onChange={(e) => set("min_player_level", e.target.value)} /></Field>
          </div>
          <Field label="Краткое описание"><textarea rows={2} value={d.short_description} disabled={disabled} onChange={(e) => set("short_description", e.target.value)} /></Field>
          <Field label="Полное описание (игроку)"><textarea rows={3} value={d.description} disabled={disabled} onChange={(e) => set("description", e.target.value)} /></Field>
          <Field label="Техническое описание (админ)"><textarea rows={2} value={d.technical_description} disabled={disabled} onChange={(e) => set("technical_description", e.target.value)} /></Field>

          <div className="ntv2-form-row">
            <Field label="Цена покупки"><input type="number" value={d.price_buy} disabled={disabled} onChange={(e) => set("price_buy", e.target.value)} /></Field>
            <Field label="Цена продажи"><input type="number" value={d.price_sell} disabled={disabled} onChange={(e) => set("price_sell", e.target.value)} /></Field>
            {flag("can_buy", "Купить")}{flag("can_sell", "Продать")}{flag("can_drop", "Выбросить")}{flag("can_trade", "Передать")}
          </div>
          <div className="ntv2-form-row">
            {flag("stackable", "Стакается")}
            <Field label="Макс. стак"><input type="number" value={d.max_stack} disabled={disabled} onChange={(e) => set("max_stack", e.target.value)} /></Field>
            {flag("usable", "Используется")}
          </div>
          <div className="ntv2-form-row">
            {flag("equippable", "Экипируется")}
            {d.equippable ? <Field label="Слот"><select value={d.equip_slot} disabled={disabled} onChange={(e) => set("equip_slot", e.target.value)}><option value="">—</option>{meta.equipSlots.map((s) => <option key={s} value={s}>{s}</option>)}</select></Field> : null}
            {d.equippable ? flag("two_handed", "Двуручный") : null}
          </div>
        </div>

        <RowEditor title="Свойства" rows={d.properties} disabled={disabled} onChange={(rows) => set("properties", rows)} blank={{ type: meta.propertyTypes[0], value: 0, percent: false }}
          render={(row, setRow) => (<>
            <select value={row.type} disabled={disabled} onChange={(e) => setRow({ type: e.target.value })}>{meta.propertyTypes.map((x) => <option key={x} value={x}>{x}</option>)}</select>
            <input type="number" style={{ width: 100 }} value={row.value} disabled={disabled} onChange={(e) => setRow({ value: e.target.value })} />
            <label className="ntv2-check"><input type="checkbox" checked={Boolean(row.percent)} disabled={disabled} onChange={(e) => setRow({ percent: e.target.checked })} /> %</label>
          </>)} />

        <RowEditor title="Эффекты" rows={d.effects} disabled={disabled} onChange={(rows) => set("effects", rows)} blank={{ type: meta.effectTypes[0], value: "" }}
          render={(row, setRow) => (<>
            <select value={row.type} disabled={disabled} onChange={(e) => setRow({ type: e.target.value })}>{meta.effectTypes.map((x) => <option key={x} value={x}>{x}</option>)}</select>
            <input placeholder="параметр" value={row.value || ""} disabled={disabled} onChange={(e) => setRow({ value: e.target.value })} />
          </>)} />

        {v ? (
          <div className={`ntv2-panel ${v.ok ? "" : "ntv2-danger-zone"}`}>
            <h4 className="ntv2-subhead">{v.ok ? "✅ Готов к публикации" : "❌ Проверка не пройдена"}</h4>
            {(v.errors || []).map((e, i) => <div className="ntv2-error" key={"e" + i}>{e}</div>)}
            {(v.warnings || []).map((w, i) => <p className="ntv2-hint" key={"w" + i}>⚠️ {w}</p>)}
          </div>
        ) : null}

        {usage ? (
          <div className="ntv2-panel">
            <h4 className="ntv2-subhead">Где используется ({usage.total})</h4>
            {usage.total === 0 ? <p className="ntv2-hint">Нигде не используется.</p> : null}
            {["mob_drops", "events", "quests", "achievements", "recipes"].map((k) => (usage[k] || []).length ? <p className="ntv2-hint" key={k}>{k}: {(usage[k] || []).map((r) => r.name || r.id).join(", ")}</p> : null)}
          </div>
        ) : null}

        <div className="ntv2-form-row" style={{ marginTop: 14 }}>
          {!disabled ? <button type="button" className="ntv2-btn ntv2-btn-primary" disabled={editing.isNew && !editing.id.trim()} onClick={save}>{editing.isNew ? "Создать" : "Сохранить"}</button> : null}
          {!editing.isNew && can.validate ? <button type="button" className="ntv2-btn" onClick={runValidate}>Проверить</button> : null}
          {!editing.isNew && can.usage ? <button type="button" className="ntv2-btn" onClick={loadUsage}>Где используется</button> : null}
          {!editing.isNew && can.publish ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => setConfirm({ title: "Опубликовать предмет?", dangerous: true, confirmLabel: "Опубликовать", body: <p>Предмет будет проверен и опубликован.</p>, run: async (r) => { await guarded(() => itemLifecycle(editing.id, "publish", r), "Опубликовано."); await refreshEditing(); } })}>Опубликовать</button> : null}
          {!editing.isNew && can.disable && published ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => setConfirm({ title: "Отключить?", dangerous: true, confirmLabel: "Отключить", body: <p>Предмет перестанет выпадать/продаваться/создаваться.</p>, run: async (r) => { await guarded(() => itemLifecycle(editing.id, "disable", r), "Отключено."); await refreshEditing(); } })}>Отключить</button> : null}
          {!editing.isNew && can.archive ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => setConfirm({ title: "В архив?", dangerous: true, confirmLabel: "В архив", body: <p>Предмет уйдёт в архив.</p>, run: async (r) => { await guarded(() => itemLifecycle(editing.id, "archive", r), "В архиве."); await refreshEditing(); } })}>В архив</button> : null}
          {!editing.isNew && can.deleteSoft ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => setConfirm({ title: "Мягко удалить?", dangerous: true, confirmLabel: "Удалить мягко", body: <p>Предмет помечается удалённым, но остаётся в базе.</p>, run: async (r) => { await guarded(() => itemLifecycle(editing.id, "delete-soft", r), "Удалено мягко."); await refreshEditing(); } })}>Мягко удалить</button> : null}
          {!editing.isNew && can.deleteHard ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => setConfirm({ title: "Полностью удалить?", dangerous: true, confirmLabel: "Удалить навсегда", requireConfirmId: editing.id, body: <p>Полное удаление без восстановления. Доступно только owner и если предмет нигде не используется.</p>, run: async (r) => { await guarded(() => hardDeleteItem(editing.id, editing.id, r), "Удалено."); setEditing(null); await load(); } })}>Удалить навсегда</button> : null}
        </div>

        {Array.isArray(d.version_history) && d.version_history.length ? <TechnicalData label={`История версий (${d.version_history.length})`} value={d.version_history} /> : null}

        <ConfirmModal open={Boolean(confirm)} title={confirm?.title} body={confirm?.body} dangerous={confirm?.dangerous} confirmLabel={confirm?.confirmLabel} requireReason
          onConfirm={async (r) => { await confirm.run(r); setConfirm(null); }} onCancel={() => setConfirm(null)} />
      </section>
    );
  }

  return (
    <section className="ntv2-section">
      <h2>Конструктор предметов</h2>
      <div className="ntv2-filters">
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="">Все статусы</option>
          {statuses.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
        </select>
        {can.create ? <button type="button" className="ntv2-btn ntv2-btn-primary" onClick={startCreate}>＋ Новый предмет</button> : null}
      </div>
      {!list.length ? <p className="ntv2-hint">Предметов нет.</p> : null}
      <div className="ntv2-list">
        {list.map((item) => (
          <button key={item.id} type="button" className="ntv2-list-row ntv2-player-row" onClick={() => openItem(item.id)}>
            <b>{item.data?.name || item.id}</b>
            <span className="ntv2-mono">{item.id}</span>
            <span className={`ntv2-badge ${STATUS_TONE[item.status] || ""}`}>{statusLabel(item.status)}</span>
            {item.data?.category ? <span className="ntv2-hint">{item.data.category}</span> : null}
          </button>
        ))}
      </div>
    </section>
  );
}
