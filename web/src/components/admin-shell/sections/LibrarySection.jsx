import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  createLibItem,
  deleteLibItem,
  fetchLibItem,
  fetchLibList,
  fetchLibMeta,
  importLib,
  libLifecycle,
  updateLibItem,
  validateLibItem,
} from "../../../api/adminLibraryApi.js";
import { ConfirmModal } from "../ConfirmModal.jsx";
import { VersionHistory } from "../VersionHistory.jsx";
import { SearchBox, NoResults, filterEntities } from "../SearchFilter.jsx";

const STATUS_TONE = { published: "ntv2-badge-owner", error: "ntv2-badge-error", disabled: "ntv2-badge-danger" };

// Опции селекта из meta: поддержка списка строк и списка {value,label}.
function options(meta, key) {
  const raw = (meta && meta[key]) || [];
  return raw.map((o) => (typeof o === "object" ? o : { value: o, label: o }));
}

function Field({ label, children }) {
  return <label className="ntv2-field"><span>{label}</span>{children}</label>;
}

// Универсальная секция каталог-конструктора на EntityStore (черты/благословения/
// фазы). config: { base, title, permPrefix, newLabel, nameField, importLabel,
// importText, fields: [{key,label,type,metaKey,sub?}] }.
export function LibrarySection({ guarded, hasPerm, config }) {
  const { base, title, permPrefix, newLabel, nameField, fields } = config;
  const [meta, setMeta] = useState(null);
  const [list, setList] = useState([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState(null);
  const [confirm, setConfirm] = useState(null);

  const can = useMemo(() => ({
    create: hasPerm(`${permPrefix}.create`), edit: hasPerm(`${permPrefix}.edit`),
    validate: hasPerm(`${permPrefix}.validate`), publish: hasPerm(`${permPrefix}.publish`),
    disable: hasPerm(`${permPrefix}.disable`), archive: hasPerm(`${permPrefix}.archive`),
    del: hasPerm(`${permPrefix}.delete`),
  }), [hasPerm, permPrefix]);

  const empty = useMemo(() => {
    const o = {};
    for (const f of fields) o[f.key] = f.type === "multiselect" ? [] : (f.type === "number" ? 0 : (f.type === "numbergroup" ? {} : ""));
    return o;
  }, [fields]);

  const load = useCallback(async () => { const p = await guarded(() => fetchLibList(base, statusFilter)); if (p) setList(p.items || []); }, [guarded, base, statusFilter]);
  useEffect(() => { (async () => { const m = await guarded(() => fetchLibMeta(base)); if (m) setMeta(m); })(); }, [guarded, base]);
  useEffect(() => { load(); }, [load]);

  const statuses = meta?.statuses || [];
  const statusLabel = (v) => statuses.find((s) => (s.value || s) === v)?.label || v;

  async function openItem(id) {
    const p = await guarded(() => fetchLibItem(base, id));
    if (p?.item) setEditing({ id, data: { ...empty, ...(p.item.data || {}) }, status: p.item.status, validation: p.validation, isNew: false });
  }
  function startCreate() { setEditing({ id: "", data: { ...empty }, status: "draft", validation: null, isNew: true }); }

  async function save() {
    const e = editing;
    if (e.isNew) { const p = await guarded(() => createLibItem(base, e.id.trim(), e.data, ""), "Создано."); if (p?.item) await openItem(e.id.trim()); }
    else { await guarded(() => updateLibItem(base, e.id, e.data, "правка"), "Сохранено."); await openItem(e.id); }
    await load();
  }
  async function runValidate() { const p = await guarded(() => validateLibItem(base, editing.id, ""), "Проверка выполнена."); if (p?.validation) setEditing((c) => ({ ...c, validation: p.validation })); }
  async function refreshEditing() { await load(); if (editing) await openItem(editing.id); }

  if (!meta) return <section className="ntv2-section"><h2>{title}</h2><p className="ntv2-hint">Загрузка…</p></section>;

  if (editing) {
    const d = editing.data;
    const set = (k, v) => setEditing({ ...editing, data: { ...d, [k]: v } });
    const disabled = !(editing.isNew ? can.create : can.edit);
    const v = editing.validation;
    const toggleMulti = (k, opt) => {
      const cur = Array.isArray(d[k]) ? d[k] : [];
      set(k, cur.includes(opt) ? cur.filter((x) => x !== opt) : [...cur, opt]);
    };
    return (
      <section className="ntv2-section">
        <div className="ntv2-card-head">
          <button type="button" className="ntv2-btn" onClick={() => setEditing(null)}>← К списку</button>
          <h2>{editing.isNew ? newLabel : (d[nameField] || editing.id)}</h2>
          {!editing.isNew ? <span className={`ntv2-badge ${STATUS_TONE[editing.status] || ""}`}>{statusLabel(editing.status)}</span> : null}
        </div>
        {editing.isNew ? <Field label="ID (латиница)"><input value={editing.id} onChange={(e) => setEditing({ ...editing, id: e.target.value })} /></Field> : <p className="ntv2-hint ntv2-mono">{editing.id}</p>}

        <div className="ntv2-world-form">
          {fields.map((f) => {
            if (f.type === "textarea") return <Field key={f.key} label={f.label}><textarea rows={f.rows || 2} value={d[f.key] || ""} disabled={disabled} onChange={(e) => set(f.key, e.target.value)} /></Field>;
            if (f.type === "number") return <Field key={f.key} label={f.label}><input type="number" value={d[f.key] ?? 0} disabled={disabled} onChange={(e) => set(f.key, e.target.value)} /></Field>;
            if (f.type === "select") return <Field key={f.key} label={f.label}><select value={d[f.key] || ""} disabled={disabled} onChange={(e) => set(f.key, e.target.value)}><option value="">—</option>{options(meta, f.metaKey).map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</select></Field>;
            if (f.type === "multiselect") return (
              <div className="ntv2-panel" key={f.key}>
                <h4 className="ntv2-subhead">{f.label}</h4>
                <div className="ntv2-form-row" style={{ flexWrap: "wrap", gap: 10 }}>
                  {options(meta, f.metaKey).map((o) => <label className="ntv2-check" key={o.value}><input type="checkbox" checked={(d[f.key] || []).includes(o.value)} disabled={disabled} onChange={() => toggleMulti(f.key, o.value)} /> {o.label}</label>)}
                </div>
              </div>
            );
            if (f.type === "numbergroup") {
              const obj = (d[f.key] && typeof d[f.key] === "object") ? d[f.key] : {};
              return (
                <div className="ntv2-panel" key={f.key}>
                  <h4 className="ntv2-subhead">{f.label}</h4>
                  <div className="ntv2-form-row">
                    {(f.sub || []).map((s) => <Field key={s.key} label={s.label}><input type="number" value={obj[s.key] ?? 0} disabled={disabled} onChange={(e) => set(f.key, { ...obj, [s.key]: e.target.value })} /></Field>)}
                  </div>
                </div>
              );
            }
            return <Field key={f.key} label={f.label}><input value={d[f.key] || ""} disabled={disabled} onChange={(e) => set(f.key, e.target.value)} /></Field>;
          })}
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
          {!editing.isNew && can.publish ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => setConfirm({ title: "Опубликовать?", dangerous: true, confirmLabel: "Опубликовать", body: <p>Запись будет проверена и опубликована.</p>, run: async (r) => { await guarded(() => libLifecycle(base, editing.id, "publish", r), "Опубликовано."); await refreshEditing(); } })}>Опубликовать</button> : null}
          {!editing.isNew && can.disable && editing.status === "published" ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => setConfirm({ title: "Отключить?", dangerous: true, confirmLabel: "Отключить", body: <p>Запись перестанет действовать.</p>, run: async (r) => { await guarded(() => libLifecycle(base, editing.id, "disable", r), "Отключено."); await refreshEditing(); } })}>Отключить</button> : null}
          {!editing.isNew && can.archive ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => setConfirm({ title: "В архив?", dangerous: true, confirmLabel: "В архив", body: <p>Запись уйдёт в архив.</p>, run: async (r) => { await guarded(() => libLifecycle(base, editing.id, "archive", r), "В архиве."); await refreshEditing(); } })}>В архив</button> : null}
          {!editing.isNew && can.del ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => setConfirm({ title: "Удалить?", dangerous: true, confirmLabel: "Удалить", body: <p>Полное удаление записи.</p>, run: async (r) => { await guarded(() => deleteLibItem(base, editing.id, editing.id, r), "Удалено."); setEditing(null); await load(); } })}>Удалить</button> : null}
        </div>

        {!editing.isNew ? <VersionHistory base={base} id={editing.id} canRollback={can.edit} onRolledBack={refreshEditing} /> : null}

        <ConfirmModal open={Boolean(confirm)} title={confirm?.title} body={confirm?.body} dangerous={confirm?.dangerous} confirmLabel={confirm?.confirmLabel} requireReason
          onConfirm={async (r) => { await confirm.run(r); setConfirm(null); }} onCancel={() => setConfirm(null)} />
      </section>
    );
  }

  return (
    <section className="ntv2-section">
      <h2>{title}</h2>
      <div className="ntv2-filters">
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="">Все статусы</option>
          {statuses.map((s) => <option key={s.value || s} value={s.value || s}>{s.label || s}</option>)}
        </select>
        {can.create ? <button type="button" className="ntv2-btn ntv2-btn-primary" onClick={startCreate}>＋ {newLabel}</button> : null}
        {can.publish ? <button type="button" className="ntv2-btn" onClick={() => setConfirm({ title: config.importLabel || "Импортировать библиотеку?", dangerous: true, confirmLabel: "Импортировать", body: <p>{config.importText || "Стандартная библиотека будет заведена как опубликованные записи (без дублей)."}</p>, run: async (r) => { const p = await guarded(() => importLib(base, "new", r), "Импорт выполнен."); if (p?.report) { await load(); window.alert(`Импорт: создано ${p.report.created}, пропущено ${p.report.skipped}.`); } } })}>Импортировать библиотеку</button> : null}
        <SearchBox value={query} onChange={setQuery} />
      </div>
      {!list.length ? <p className="ntv2-hint">Записей пока нет. Создайте новую или импортируйте библиотеку.</p> : null}
      <NoResults items={list} query={query} />
      <div className="ntv2-list">
        {filterEntities(list, query).map((item) => (
          <button key={item.id} type="button" className="ntv2-list-row ntv2-player-row" onClick={() => openItem(item.id)}>
            <b>{item.data?.[nameField] || item.id}</b>
            <span className="ntv2-mono">{item.id}</span>
            <span className={`ntv2-badge ${STATUS_TONE[item.status] || ""}`}>{statusLabel(item.status)}</span>
          </button>
        ))}
      </div>
    </section>
  );
}
