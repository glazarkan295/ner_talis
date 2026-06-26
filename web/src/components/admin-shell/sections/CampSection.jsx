import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  createCamp,
  deleteCamp,
  fetchCamp,
  fetchCampMeta,
  fetchCamps,
  importCamps,
  campLifecycle,
  updateCamp,
  validateCamp,
} from "../../../api/adminCampApi.js";
import { ConfirmModal } from "../ConfirmModal.jsx";
import { VersionHistory } from "../VersionHistory.jsx";
import { EmojiInput, EmojiTextarea } from "../EmojiField.jsx";
import { SearchBox, NoResults, filterEntities } from "../SearchFilter.jsx";

const STATUS_TONE = { published: "ntv2-badge-owner", error: "ntv2-badge-error", disabled: "ntv2-badge-danger" };

const CAMP_TYPE_LABEL = {
  standard: "Стандартный", safe: "Безопасный", dangerous: "Опасный",
  event: "Событийный", temporary: "Временный", special: "Специальный",
};
const TARGET_LABEL = {
  hp: "HP", mana: "Мана", spirit: "Дух", energy: "Энергия", stamina: "Стамина", fatigue: "Усталость",
};

const EMPTY = {
  name: "", camp_type: "standard", short_description: "", full_text: "",
  locations: [], actions: [], recovery: [],
  base_time: 0, min_time: 0, max_time: 0, cooldown: 0, use_limit: 0,
};

function Field({ label, children }) {
  return <label className="ntv2-field"><span>{label}</span>{children}</label>;
}

export function CampSection({ guarded, hasPerm }) {
  const [meta, setMeta] = useState(null);
  const [list, setList] = useState([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState(null);
  const [confirm, setConfirm] = useState(null);

  const can = useMemo(() => ({
    create: hasPerm("camp.create"), edit: hasPerm("camp.edit"), validate: hasPerm("camp.validate"),
    publish: hasPerm("camp.publish"), disable: hasPerm("camp.disable"),
    archive: hasPerm("camp.archive"), del: hasPerm("camp.delete"),
  }), [hasPerm]);

  const load = useCallback(async () => { const p = await guarded(() => fetchCamps(statusFilter)); if (p) setList(p.items || []); }, [guarded, statusFilter]);
  useEffect(() => { (async () => { const m = await guarded(() => fetchCampMeta()); if (m) setMeta(m); })(); }, [guarded]);
  useEffect(() => { load(); }, [load]);

  const statuses = meta?.statuses || [];
  const statusLabel = (v) => statuses.find((s) => s.value === v)?.label || v;

  async function openItem(id) {
    const p = await guarded(() => fetchCamp(id));
    if (p?.item) setEditing({ id, data: { ...EMPTY, ...(p.item.data || {}) }, status: p.item.status, validation: p.validation, isNew: false });
  }
  function startCreate() { setEditing({ id: "", data: { ...EMPTY }, status: "draft", validation: null, isNew: true }); }

  async function save() {
    const e = editing;
    if (e.isNew) { const p = await guarded(() => createCamp(e.id.trim(), e.data, ""), "Создано."); if (p?.item) await openItem(e.id.trim()); }
    else { await guarded(() => updateCamp(e.id, e.data, "правка"), "Сохранено."); await openItem(e.id); }
    await load();
  }
  async function runValidate() { const p = await guarded(() => validateCamp(editing.id, ""), "Проверка выполнена."); if (p?.validation) setEditing((c) => ({ ...c, validation: p.validation })); }
  async function refreshEditing() { await load(); if (editing) await openItem(editing.id); }

  if (!meta) return <section className="ntv2-section"><h2>Конструктор лагеря</h2><p className="ntv2-hint">Загрузка…</p></section>;

  if (editing) {
    const d = editing.data;
    const set = (k, v) => setEditing({ ...editing, data: { ...d, [k]: v } });
    const disabled = !(editing.isNew ? can.create : can.edit);
    const v = editing.validation;
    const recovery = Array.isArray(d.recovery) ? d.recovery : [];
    const setRec = (i, patch) => set("recovery", recovery.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));
    const actions = Array.isArray(d.actions) ? d.actions : [];
    const toggleAction = (a) => set("actions", actions.includes(a) ? actions.filter((x) => x !== a) : [...actions, a]);
    const num = (key, label) => <Field label={label} key={key}><input type="number" value={d[key]} disabled={disabled} onChange={(e) => set(key, e.target.value)} /></Field>;
    return (
      <section className="ntv2-section">
        <div className="ntv2-card-head">
          <button type="button" className="ntv2-btn" onClick={() => setEditing(null)}>← К списку</button>
          <h2>{editing.isNew ? "Новый лагерь" : d.name || editing.id}</h2>
          {!editing.isNew ? <span className={`ntv2-badge ${STATUS_TONE[editing.status] || ""}`}>{statusLabel(editing.status)}</span> : null}
        </div>
        {editing.isNew ? <Field label="ID (латиница, напр. safe_glade)"><input value={editing.id} onChange={(e) => setEditing({ ...editing, id: e.target.value })} /></Field> : <p className="ntv2-hint ntv2-mono">{editing.id}</p>}

        <div className="ntv2-world-form">
          <div className="ntv2-form-row">
            <Field label="Название"><EmojiInput value={d.name} disabled={disabled} onChange={(val) => set("name", val)} /></Field>
            <Field label="Тип лагеря"><select value={d.camp_type} disabled={disabled} onChange={(e) => set("camp_type", e.target.value)}>{(meta.campTypes || []).map((c) => <option key={c} value={c}>{CAMP_TYPE_LABEL[c] || c}</option>)}</select></Field>
          </div>
          <Field label="Краткое описание"><EmojiTextarea rows={2} value={d.short_description} disabled={disabled} onChange={(val) => set("short_description", val)} /></Field>
          <Field label="Полный текст лагеря"><EmojiTextarea rows={3} value={d.full_text} disabled={disabled} onChange={(val) => set("full_text", val)} /></Field>
          <Field label="Локации (id через запятую)"><input className="ntv2-mono" value={(d.locations || []).join(", ")} disabled={disabled} onChange={(e) => set("locations", e.target.value.split(",").map((s) => s.trim()).filter(Boolean))} /></Field>

          <h4 className="ntv2-subhead">Время (сек)</h4>
          <div className="ntv2-form-row">{num("base_time", "Базовое")}{num("min_time", "Мин.")}{num("max_time", "Макс.")}{num("cooldown", "Откат")}{num("use_limit", "Лимит исп.")}</div>

          <div className="ntv2-panel">
            <h4 className="ntv2-subhead">Восстановление ({recovery.length})</h4>
            <div className="ntv2-list">
              {recovery.map((row, i) => (
                <div className="ntv2-list-row" key={i}>
                  <select value={row.target || "hp"} disabled={disabled} onChange={(e) => setRec(i, { target: e.target.value })}>{(meta.recoveryTargets || []).map((rt) => <option key={rt} value={rt}>{TARGET_LABEL[rt] || rt}</option>)}</select>
                  <input type="number" style={{ width: 90 }} placeholder="плоско" value={row.flat ?? ""} disabled={disabled} onChange={(e) => setRec(i, { flat: e.target.value })} />
                  <input type="number" style={{ width: 90 }} placeholder="%" value={row.percent ?? ""} disabled={disabled} onChange={(e) => setRec(i, { percent: e.target.value })} />
                  {!disabled ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => set("recovery", recovery.filter((_, idx) => idx !== i))}>×</button> : null}
                </div>
              ))}
            </div>
            {!disabled ? <button type="button" className="ntv2-btn" style={{ marginTop: 6 }} onClick={() => set("recovery", [...recovery, { target: "hp", flat: 0, percent: 0 }])}>＋ Восстановление</button> : null}
          </div>

          <div className="ntv2-panel">
            <h4 className="ntv2-subhead">Доступные действия</h4>
            <div className="ntv2-form-row" style={{ flexWrap: "wrap", gap: 10 }}>
              {(meta.campActions || []).map((a) => (
                <label className="ntv2-check" key={a}><input type="checkbox" checked={actions.includes(a)} disabled={disabled} onChange={() => toggleAction(a)} /> {a}</label>
              ))}
            </div>
          </div>
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
          {!editing.isNew && can.publish ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => setConfirm({ title: "Опубликовать лагерь?", dangerous: true, confirmLabel: "Опубликовать", body: <p>Лагерь будет проверен и опубликован.</p>, run: async (r) => { await guarded(() => campLifecycle(editing.id, "publish", r), "Опубликовано."); await refreshEditing(); } })}>Опубликовать</button> : null}
          {!editing.isNew && can.disable && editing.status === "published" ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => setConfirm({ title: "Отключить?", dangerous: true, confirmLabel: "Отключить", body: <p>Лагерь перестанет быть доступен.</p>, run: async (r) => { await guarded(() => campLifecycle(editing.id, "disable", r), "Отключено."); await refreshEditing(); } })}>Отключить</button> : null}
          {!editing.isNew && can.archive ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => setConfirm({ title: "В архив?", dangerous: true, confirmLabel: "В архив", body: <p>Лагерь уйдёт в архив.</p>, run: async (r) => { await guarded(() => campLifecycle(editing.id, "archive", r), "В архиве."); await refreshEditing(); } })}>В архив</button> : null}
          {!editing.isNew && can.del ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => setConfirm({ title: "Удалить лагерь?", dangerous: true, confirmLabel: "Удалить", body: <p>Полное удаление лагеря.</p>, run: async (r) => { await guarded(() => deleteCamp(editing.id, editing.id, r), "Удалено."); setEditing(null); await load(); } })}>Удалить</button> : null}
        </div>

        {!editing.isNew ? <VersionHistory base="camps" id={editing.id} canRollback={can.edit} onRolledBack={refreshEditing} /> : null}

        <ConfirmModal open={Boolean(confirm)} title={confirm?.title} body={confirm?.body} dangerous={confirm?.dangerous} confirmLabel={confirm?.confirmLabel} requireReason
          onConfirm={async (r) => { await confirm.run(r); setConfirm(null); }} onCancel={() => setConfirm(null)} />
      </section>
    );
  }

  return (
    <section className="ntv2-section">
      <h2>Конструктор лагеря</h2>
      <div className="ntv2-filters">
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="">Все статусы</option>
          {statuses.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
        </select>
        {can.create ? <button type="button" className="ntv2-btn ntv2-btn-primary" onClick={startCreate}>＋ Новый лагерь</button> : null}
        {can.publish ? <button type="button" className="ntv2-btn" onClick={() => setConfirm({ title: "Импортировать существующие лагеря?", dangerous: true, confirmLabel: "Импортировать", body: <p>Статического источника лагерей нет — будет показано напоминание создать их вручную.</p>, run: async (r) => { const p = await guarded(() => importCamps("new", r), "Импорт выполнен."); if (p?.report) { await load(); window.alert("Источника лагерей нет — создайте лагеря вручную и привяжите к локациям."); } } })}>Импортировать существующие</button> : null}
        <SearchBox value={query} onChange={setQuery} />
      </div>
      {!list.length ? <p className="ntv2-hint">Лагерей пока нет. Создайте новый.</p> : null}
      <NoResults items={list} query={query} />
      <div className="ntv2-list">
        {filterEntities(list, query).map((item) => (
          <button key={item.id} type="button" className="ntv2-list-row ntv2-player-row" onClick={() => openItem(item.id)}>
            <b>{item.data?.name || item.id}</b>
            <span className="ntv2-mono">{item.id}</span>
            <span className={`ntv2-badge ${STATUS_TONE[item.status] || ""}`}>{statusLabel(item.status)}</span>
            {item.data?.camp_type ? <span className="ntv2-hint">{CAMP_TYPE_LABEL[item.data.camp_type] || item.data.camp_type}</span> : null}
          </button>
        ))}
      </div>
    </section>
  );
}
