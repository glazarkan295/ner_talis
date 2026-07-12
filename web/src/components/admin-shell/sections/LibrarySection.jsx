import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  createLibItem,
  deleteLibItem,
  duplicateLibItem,
  fetchLibItem,
  fetchLibList,
  fetchLibMeta,
  fetchLibPreview,
  fetchLibUsage,
  importLib,
  libLifecycle,
  updateLibItem,
  validateLibItem,
  broadcastRecipientPreview, broadcastStart, broadcastStop, broadcastRunBatch, broadcastRetryFailed, fetchBroadcastRun,
} from "../../../api/adminLibraryApi.js";
import { ConfirmModal } from "../ConfirmModal.jsx";
import { VersionHistory } from "../VersionHistory.jsx";
import { SearchBox, NoResults, filterEntities } from "../SearchFilter.jsx";
import { fetchFormulas } from "../../../api/adminFormulaApi.js";
import { fetchEffects } from "../../../api/adminEffectApi.js";
import { HintTip, HINT_TIP_CSS } from "../HintTip.jsx";
import { TechnicalData } from "../TechnicalData.jsx";
import { requestAdminJson } from "../../../api/adminApi.js";

const STATUS_TONE = { published: "ntv2-badge-owner", error: "ntv2-badge-error", disabled: "ntv2-badge-danger" };

// Опции селекта из meta: поддержка списка строк и списка {value,label}.
function options(meta, key) {
  const raw = (meta && meta[key]) || [];
  return raw.map((o) => (typeof o === "object" ? o : { value: o, label: o }));
}

function Field({ label, hint, children }) {
  return <label className="ntv2-field"><span>{label}<HintTip text={hint} /></span>{children}</label>;
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
  const [duplicateId, setDuplicateId] = useState("");
  const [preview, setPreview] = useState(null);
  const [usage, setUsage] = useState(null);
  const [formulaOptions, setFormulaOptions] = useState([]);
  const [effectOptions, setEffectOptions] = useState([]);
  const [runtimeInfo, setRuntimeInfo] = useState(null);
  const [operationLogs, setOperationLogs] = useState(null);
  const hasFormulaField = useMemo(() => fields.some((f) => f.type === "formularef"), [fields]);
  const hasEffectField = useMemo(() => fields.some((f) => f.type === "effectref"), [fields]);

  const can = useMemo(() => {
    const managed = config.managePerm ? hasPerm(config.managePerm) : null;
    return {
      create: managed ?? hasPerm(`${permPrefix}.create`), edit: managed ?? hasPerm(`${permPrefix}.edit`),
      validate: managed ?? hasPerm(`${permPrefix}.validate`), publish: managed ?? hasPerm(`${permPrefix}.publish`),
      disable: managed ?? hasPerm(`${permPrefix}.disable`), archive: managed ?? hasPerm(`${permPrefix}.archive`),
      del: managed ?? hasPerm(`${permPrefix}.delete`),
    };
  }, [hasPerm, permPrefix, config.managePerm]);

  const empty = useMemo(() => {
    const o = {};
    for (const f of fields) o[f.key] = (f.type === "multiselect" || f.type === "list" || f.type === "objlist") ? [] : (f.type === "number" ? 0 : (f.type === "numbergroup" ? {} : (f.type === "checkbox" ? false : "")));
    return o;
  }, [fields]);

  const load = useCallback(async () => { const p = await guarded(() => fetchLibList(base, statusFilter)); if (p) setList(p.items || []); }, [guarded, base, statusFilter]);
  useEffect(() => { (async () => { const m = await guarded(() => fetchLibMeta(base)); if (m) setMeta(m); })(); }, [guarded, base]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { if (!hasFormulaField) return; (async () => { const p = await guarded(() => fetchFormulas("published")); if (p) setFormulaOptions((p.items || []).map((f) => ({ value: f.id, label: (f.data?.name || f.id) }))); })(); }, [guarded, hasFormulaField]);
  useEffect(() => { if (!hasEffectField) return; (async () => { const p = await guarded(() => fetchEffects("published")); if (p) setEffectOptions((p.items || []).map((f) => ({ value: f.id, label: (f.data?.effect_name || f.id) }))); })(); }, [guarded, hasEffectField]);

  const statuses = meta?.statuses || [];
  const statusLabel = (v) => statuses.find((s) => (s.value || s) === v)?.label || v;

  async function openItem(id) {
    const p = await guarded(() => fetchLibItem(base, id));
    if (p?.item) { setEditing({ id, data: { ...empty, ...(p.item.data || {}) }, status: p.item.status, validation: p.validation, isNew: false }); setPreview(null); setUsage(null); setRuntimeInfo(null); }
  }
  function startCreate() { setEditing({ id: "", data: { ...empty }, status: "draft", validation: null, isNew: true }); }
  function startDuplicate() { setDuplicateId(`${editing.id}_copy`); }

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
        <style>{HINT_TIP_CSS}</style>
        <div className="ntv2-card-head">
          <button type="button" className="ntv2-btn" onClick={() => setEditing(null)}>← К списку</button>
          <h2>{editing.isNew ? newLabel : (d[nameField] || editing.id)}</h2>
          {!editing.isNew ? <span className={`ntv2-badge ${STATUS_TONE[editing.status] || ""}`}>{statusLabel(editing.status)}</span> : null}
        </div>

        {!editing.isNew && config.runtimeType === "broadcast" ? (
          <div className="ntv2-panel">
            <h4 className="ntv2-subhead">Отправка и журнал</h4>
            <div className="ntv2-form-row">
              <button type="button" className="ntv2-btn" onClick={async () => { const p = await guarded(() => broadcastRecipientPreview(editing.id)); if (p) setRuntimeInfo({ preview: p }); }}>Получатели до отправки</button>
              {can.publish && editing.status === "published" ? <button type="button" className="ntv2-btn" onClick={() => setConfirm({ title: "Тестовая отправка администраторам?", confirmLabel: "Отправить тест", body: <p>Сообщение и награды получат только администраторы из аудитории теста.</p>, run: async () => { const p = await guarded(() => broadcastStart(editing.id, true), "Тестовая рассылка запущена."); if (p) setRuntimeInfo(p.run); } })}>Тестовая отправка</button> : null}
              {can.publish && editing.status === "published" ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => setConfirm({ title: "Запустить массовую рассылку?", dangerous: true, confirmLabel: "Запустить", body: <p>Получатели рассчитаны по опубликованной карточке. Для наград это является вторым подтверждением.</p>, run: async () => { const p = await guarded(() => broadcastStart(editing.id, false), "Рассылка запущена."); if (p) setRuntimeInfo(p.run); } })}>Запустить рассылку</button> : null}
              <button type="button" className="ntv2-btn" onClick={async () => { const p = await guarded(() => fetchBroadcastRun(editing.id)); if (p) setRuntimeInfo(p.run); }}>Обновить журнал</button>
              {can.publish ? <button type="button" className="ntv2-btn" onClick={async () => { const p = await guarded(() => broadcastRunBatch(editing.id), "Следующая пачка обработана."); if (p) setRuntimeInfo(p.run); }}>Обработать пачку</button> : null}
              {can.publish ? <button type="button" className="ntv2-btn" onClick={async () => { const p = await guarded(() => broadcastRetryFailed(editing.id), "Ошибочные отправки поставлены на повтор."); if (p) setRuntimeInfo(p.run); }}>Повторить ошибки</button> : null}
              {can.disable ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => setConfirm({ title: "Остановить рассылку?", dangerous: true, confirmLabel: "Остановить", body: <p>Необработанные получатели не получат сообщение.</p>, run: async () => { const p = await guarded(() => broadcastStop(editing.id), "Рассылка остановлена."); if (p) setRuntimeInfo(p.run); } })}>Остановить</button> : null}
            </div>
            {runtimeInfo ? <TechnicalData label="Получатели / состояние / логи" value={runtimeInfo} /> : <p className="ntv2-hint">Перед запуском проверьте аудиторию и тестовую отправку.</p>}
          </div>
        ) : null}
        {editing.isNew ? <Field label="ID (латиница)"><input value={editing.id} onChange={(e) => setEditing({ ...editing, id: e.target.value })} /></Field> : <p className="ntv2-hint ntv2-mono">{editing.id}</p>}

        <div className="ntv2-world-form">
          {fields.map((f) => {
            if (f.type === "textarea") return <Field key={f.key} label={f.label} hint={f.hint}><textarea rows={f.rows || 2} value={d[f.key] || ""} disabled={disabled} onChange={(e) => set(f.key, e.target.value)} /></Field>;
            if (f.type === "number") return <Field key={f.key} label={f.label} hint={f.hint}><input type="number" value={d[f.key] ?? 0} disabled={disabled} onChange={(e) => set(f.key, e.target.value)} /></Field>;
            if (f.type === "checkbox") return <label className="ntv2-check" key={f.key}><input type="checkbox" checked={Boolean(d[f.key])} disabled={disabled} onChange={(e) => set(f.key, e.target.checked)} /> {f.label}<HintTip text={f.hint} /></label>;
            if (f.type === "select") return <Field key={f.key} label={f.label} hint={f.hint}><select value={d[f.key] || ""} disabled={disabled} onChange={(e) => set(f.key, e.target.value)}><option value="">—</option>{options(meta, f.metaKey).map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</select></Field>;
            if (f.type === "formularef") return <Field key={f.key} label={f.label} hint={f.hint}><select value={d[f.key] || ""} disabled={disabled} onChange={(e) => set(f.key, e.target.value)}><option value="">— без формулы —</option>{formulaOptions.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</select></Field>;
            if (f.type === "effectref") return <Field key={f.key} label={f.label} hint={f.hint}><select value={d[f.key] || ""} disabled={disabled} onChange={(e) => set(f.key, e.target.value)}><option value="">— без эффекта —</option>{effectOptions.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</select></Field>;
            if (f.type === "list") return <Field key={f.key} label={f.label} hint={f.hint}><textarea rows={f.rows || 2} value={(Array.isArray(d[f.key]) ? d[f.key] : []).join("\n")} disabled={disabled} onChange={(e) => set(f.key, e.target.value.split("\n").map((s) => s.trim()).filter(Boolean))} /></Field>;
            if (f.type === "objlist") {
              const rows = Array.isArray(d[f.key]) ? d[f.key] : [];
              const upd = (i, c, val) => set(f.key, rows.map((r, idx) => idx === i ? { ...r, [c]: val } : r));
              return (
                <div className="ntv2-panel" key={f.key}>
                  <h4 className="ntv2-subhead">{f.label}<HintTip text={f.hint} /></h4>
                  {rows.map((row, i) => (
                    <div className="ntv2-form-row" key={i} style={{ gap: 6, alignItems: "flex-end" }}>
                      {(f.columns || []).map((c) => <Field key={c.key} label={c.label}><input value={row[c.key] ?? ""} disabled={disabled} onChange={(e) => upd(i, c.key, e.target.value)} /></Field>)}
                      {!disabled ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => set(f.key, rows.filter((_, idx) => idx !== i))}>×</button> : null}
                    </div>
                  ))}
                  {!disabled ? <button type="button" className="ntv2-btn" style={{ marginTop: 6 }} onClick={() => set(f.key, [...rows, {}])}>＋ Строка</button> : null}
                </div>
              );
            }
            if (f.type === "multiselect") return (
              <div className="ntv2-panel" key={f.key}>
                <h4 className="ntv2-subhead">{f.label}<HintTip text={f.hint} /></h4>
                <div className="ntv2-form-row" style={{ flexWrap: "wrap", gap: 10 }}>
                  {options(meta, f.metaKey).map((o) => <label className="ntv2-check" key={o.value}><input type="checkbox" checked={(d[f.key] || []).includes(o.value)} disabled={disabled} onChange={() => toggleMulti(f.key, o.value)} /> {o.label}</label>)}
                </div>
              </div>
            );
            if (f.type === "numbergroup") {
              const obj = (d[f.key] && typeof d[f.key] === "object") ? d[f.key] : {};
              return (
                <div className="ntv2-panel" key={f.key}>
                  <h4 className="ntv2-subhead">{f.label}<HintTip text={f.hint} /></h4>
                  <div className="ntv2-form-row">
                    {(f.sub || []).map((s) => <Field key={s.key} label={s.label}><input type="number" value={obj[s.key] ?? 0} disabled={disabled} onChange={(e) => set(f.key, { ...obj, [s.key]: e.target.value })} /></Field>)}
                  </div>
                </div>
              );
            }
            return <Field key={f.key} label={f.label} hint={f.hint}><input value={d[f.key] || ""} disabled={disabled} onChange={(e) => set(f.key, e.target.value)} /></Field>;
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
          {!editing.isNew ? <button type="button" className="ntv2-btn" onClick={async () => { const p = await guarded(() => fetchLibPreview(base, editing.id)); if (p) setPreview(p.preview); }}>Предпросмотр</button> : null}
          {!editing.isNew ? <button type="button" className="ntv2-btn" onClick={async () => { const p = await guarded(() => fetchLibUsage(base, editing.id)); if (p) setUsage(p.usage); }}>Где используется</button> : null}
          {config.operationLogs ? <button type="button" className="ntv2-btn" onClick={async () => { const p = await guarded(() => requestAdminJson(`/api/admin/v2/${base}/${config.operationsPath || "operations/logs?limit=500"}`)); if (p) setOperationLogs(p); }}>{config.operationsLabel || "Логи операций"}</button> : null}
          {!editing.isNew && can.validate && editing.status === "draft" ? <button type="button" className="ntv2-btn" onClick={() => setConfirm({ title: "Отправить на проверку?", confirmLabel: "На проверку", body: <p>Запись будет проверена и получит статус «На проверке».</p>, run: async (r) => { await guarded(() => libLifecycle(base, editing.id, "review", r), "Отправлено на проверку."); await refreshEditing(); } })}>На проверку</button> : null}
          {!editing.isNew && can.create ? <button type="button" className="ntv2-btn" onClick={startDuplicate}>Дублировать</button> : null}
          {!editing.isNew && can.publish ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => setConfirm({ title: "Опубликовать?", dangerous: true, confirmLabel: "Опубликовать", body: <p>Запись будет проверена и опубликована.</p>, run: async (r) => { await guarded(() => libLifecycle(base, editing.id, "publish", r), "Опубликовано."); await refreshEditing(); } })}>Опубликовать</button> : null}
          {!editing.isNew && can.disable && editing.status === "published" ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => setConfirm({ title: "Отключить?", dangerous: true, confirmLabel: "Отключить", body: <p>Запись перестанет действовать.</p>, run: async (r) => { await guarded(() => libLifecycle(base, editing.id, "disable", r), "Отключено."); await refreshEditing(); } })}>Отключить</button> : null}
          {!editing.isNew && can.archive ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => setConfirm({ title: "В архив?", dangerous: true, confirmLabel: "В архив", body: <p>Запись уйдёт в архив.</p>, run: async (r) => { await guarded(() => libLifecycle(base, editing.id, "archive", r), "В архиве."); await refreshEditing(); } })}>В архив</button> : null}
          {!editing.isNew && can.edit && ["archive", "disabled", "error"].includes(editing.status) ? <button type="button" className="ntv2-btn" onClick={() => setConfirm({ title: "Восстановить как черновик?", confirmLabel: "Восстановить", body: <p>Запись вернётся в черновики и не будет включена в игру автоматически.</p>, run: async (r) => { await guarded(() => libLifecycle(base, editing.id, "restore", r), "Восстановлено."); await refreshEditing(); } })}>Восстановить</button> : null}
          {!editing.isNew && can.del ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => setConfirm({ title: "Удалить?", dangerous: true, confirmLabel: "Удалить", body: <p>Полное удаление записи.</p>, run: async (r) => { await guarded(() => deleteLibItem(base, editing.id, editing.id, r), "Удалено."); setEditing(null); await load(); } })}>Удалить</button> : null}
        </div>

        {preview ? <div className="ntv2-panel"><h4 className="ntv2-subhead">Предпросмотр</h4><h3>{preview.title || d[nameField] || editing.id}</h3>{preview.description ? <p>{preview.description}</p> : null}<TechnicalData label="Данные предпросмотра" value={preview} /></div> : null}
        {usage ? <div className="ntv2-panel"><h4 className="ntv2-subhead">Где используется</h4>{usage.used_by?.length ? <ul>{usage.used_by.map((id) => <li className="ntv2-mono" key={id}>{id}</li>)}</ul> : <p className="ntv2-hint">Входящих связей не найдено.</p>}<TechnicalData label="Все связи" value={usage} /></div> : null}
        {operationLogs ? <div className="ntv2-panel"><h4 className="ntv2-subhead">{config.operationsTitle || `Логи операций · подозрительных: ${(operationLogs.suspicious || []).length}`}</h4><TechnicalData label={config.operationsDataLabel || "Операции"} value={operationLogs} /></div> : null}

        {duplicateId ? (
          <div className="ntv2-panel">
            <h4 className="ntv2-subhead">Дублирование записи</h4>
            <Field label="ID новой записи"><input className="ntv2-mono" value={duplicateId} onChange={(e) => setDuplicateId(e.target.value)} /></Field>
            <div className="ntv2-form-row">
              <button type="button" className="ntv2-btn ntv2-btn-primary" disabled={!duplicateId.trim()} onClick={() => setConfirm({ title: "Создать копию?", confirmLabel: "Дублировать", body: <p>Будет создан независимый черновик с ID <span className="ntv2-mono">{duplicateId}</span>.</p>, run: async (r) => { const p = await guarded(() => duplicateLibItem(base, editing.id, duplicateId.trim(), r), "Копия создана."); if (p?.item) { setDuplicateId(""); await load(); await openItem(p.item.id); } } })}>Создать копию</button>
              <button type="button" className="ntv2-btn" onClick={() => setDuplicateId("")}>Отмена</button>
            </div>
          </div>
        ) : null}

        {/* ТЗ 22 §4: откат опубликованной записи требует и edit, и publish; черновик — только edit. */}
        {!editing.isNew ? <VersionHistory base={base} id={editing.id} canRollback={can.edit && (editing.status !== "published" || can.publish)} onRolledBack={refreshEditing} /> : null}

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
        {/* ТЗ 22 §1/§6: кнопку импорта показываем только если конструктор реально поддерживает import-route (config.supportsImport), а не просто при can.publish. */}
        {can.publish && config.supportsImport ? <button type="button" className="ntv2-btn" onClick={() => setConfirm({ title: config.importLabel || "Импортировать библиотеку?", dangerous: true, confirmLabel: "Импортировать", body: <p>{config.importText || "Стандартная библиотека будет заведена как опубликованные записи (без дублей)."}</p>, run: async (r) => { const p = await guarded(() => importLib(base, "new", r), "Импорт выполнен."); if (p?.report) { await load(); window.alert(`Импорт: создано ${p.report.created}, пропущено ${p.report.skipped}.`); } } })}>Импортировать библиотеку</button> : null}
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
