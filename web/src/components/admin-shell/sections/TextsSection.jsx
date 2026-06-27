import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  fetchTextMeta, fetchTextList, fetchText, createText, updateText,
  textLifecycle, previewText, importTexts,
} from "../../../api/adminTextApi.js";

// Конструктор текстов бота (full-import ТЗ §5.18): редактируемые сообщения с
// ключом, платформой, режимом разметки, переменными {name} и fallback.

const EMPTY = {
  text_key: "", text_value: "", fallback_text: "", context: "system",
  platform: "both", parse_mode: "none", entity_type: "none", entity_id: "",
  variables: [],
};

function Field({ label, children }) {
  return <label className="ntv2-field"><span>{label}</span>{children}</label>;
}

export function TextsSection({ guarded, hasPerm }) {
  const [meta, setMeta] = useState(null);
  const [list, setList] = useState([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [selected, setSelected] = useState(null);
  const [data, setData] = useState(null);
  const [creating, setCreating] = useState(false);
  const [newId, setNewId] = useState("");
  const [preview, setPreview] = useState(null);
  const [info, setInfo] = useState("");

  const can = useMemo(() => ({
    create: hasPerm("text.create"), edit: hasPerm("text.edit"),
    publish: hasPerm("text.publish"),
  }), [hasPerm]);

  const load = useCallback(async () => {
    const p = await guarded(() => fetchTextList(statusFilter));
    if (p) setList(p.items || []);
  }, [guarded, statusFilter]);
  useEffect(() => { (async () => { const m = await guarded(() => fetchTextMeta()); if (m) setMeta(m); })(); }, [guarded]);
  useEffect(() => { load(); }, [load]);

  const statuses = meta?.statuses || [];
  const statusLabel = (v) => statuses.find((s) => s.value === v)?.label || v;
  const contextLabel = (v) => meta?.contexts?.find((x) => x.value === v)?.label || v;

  async function openItem(id) {
    setSelected(id); setCreating(false); setPreview(null);
    const p = await guarded(() => fetchText(id));
    if (p) setData({ ...EMPTY, ...(p.item.data || {}) });
  }
  function startCreate() { setCreating(true); setSelected(null); setNewId(""); setData({ ...EMPTY }); setPreview(null); }
  async function save() {
    if (creating) {
      if (!newId.trim()) { setInfo("Укажите ID записи."); return; }
      const r = await guarded(() => createText(newId.trim(), data, "create text"));
      if (r) { setInfo("Создано."); setCreating(false); await load(); await openItem(newId.trim()); }
    } else if (selected) {
      const r = await guarded(() => updateText(selected, data, "edit text"));
      if (r) { setInfo("Сохранено."); await load(); }
    }
  }
  async function lifecycle(verb) { if (!selected) return; const r = await guarded(() => textLifecycle(selected, verb, verb)); if (r) { setInfo(`Статус: ${verb}`); await load(); } }
  async function runImport() {
    const r = await guarded(() => importTexts("new", "import texts"));
    if (r) { setInfo(`Импорт: создано ${r.report?.created ?? 0}.`); await load(); }
  }
  async function runPreview() {
    if (!selected) { setInfo("Сохраните запись, затем предпросмотр."); return; }
    const vars = {};
    (data.variables || []).forEach((v) => { vars[v] = `{${v}}`; });
    const r = await guarded(() => previewText(selected, vars));
    if (r) setPreview(r.preview);
  }

  const setF = (k, v) => setData((d) => ({ ...d, [k]: v }));

  return (
    <section className="ntv2-section nttx">
      <style>{TX_CSS}</style>
      <header className="ntv2-section-head">
        <div>
          <h2>💬 Тексты бота</h2>
          <p className="ntv2-muted">Редактируемые сообщения бота: ключ, платформа, разметка, переменные {"{name}"} и fallback (ТЗ §5.18).</p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          {can.publish ? <button type="button" className="ntv2-btn" onClick={runImport}>Импортировать базовые</button> : null}
          {can.create ? <button type="button" className="ntv2-btn" onClick={startCreate}>＋ Новый текст</button> : null}
        </div>
      </header>

      <div className="nttx-layout">
        <aside className="nttx-list">
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            <option value="">Все статусы</option>
            {statuses.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
          </select>
          <ul>
            {list.map((s) => (
              <li key={s.id} className={selected === s.id ? "active" : ""} onClick={() => openItem(s.id)}>
                <b>{s.data?.text_key || s.id}</b>
                <small>{contextLabel(s.data?.context)} · {statusLabel(s.status)}</small>
              </li>
            ))}
            {!list.length ? <li className="nttx-empty">Пусто</li> : null}
          </ul>
        </aside>

        <div className="nttx-main">
          {info ? <div className="nttx-info">{info}</div> : null}
          {!data ? <div className="nttx-placeholder">Выберите текст, создайте новый или импортируйте базовые.</div> : (
            <>
              <div className="nttx-form">
                {creating ? <Field label="ID записи"><input value={newId} onChange={(e) => setNewId(e.target.value)} placeholder="system_welcome" /></Field> : null}
                <Field label="Ключ текста (text_key)"><input className="ntv2-mono" value={data.text_key} onChange={(e) => setF("text_key", e.target.value)} placeholder="system.welcome" /></Field>
                <Field label="Текст"><textarea rows={4} value={data.text_value} onChange={(e) => setF("text_value", e.target.value)} /></Field>
                <Field label="Fallback (если основной пуст)"><textarea rows={2} value={data.fallback_text} onChange={(e) => setF("fallback_text", e.target.value)} /></Field>
                <div className="ntv2-form-row">
                  <Field label="Контекст"><select value={data.context} onChange={(e) => setF("context", e.target.value)}>{(meta?.contexts || []).map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}</select></Field>
                  <Field label="Платформа"><select value={data.platform} onChange={(e) => setF("platform", e.target.value)}>{(meta?.platforms || []).map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}</select></Field>
                  <Field label="Разметка"><select value={data.parse_mode} onChange={(e) => setF("parse_mode", e.target.value)}>{(meta?.parseModes || []).map((p) => <option key={p} value={p}>{p}</option>)}</select></Field>
                </div>
                <div className="ntv2-form-row">
                  <Field label="Тип сущности"><select value={data.entity_type} onChange={(e) => setF("entity_type", e.target.value)}>{(meta?.entityTypes || []).map((p) => <option key={p} value={p}>{p}</option>)}</select></Field>
                  <Field label="ID сущности"><input className="ntv2-mono" value={data.entity_id} onChange={(e) => setF("entity_id", e.target.value)} /></Field>
                </div>
                <Field label="Переменные (по строкам, без скобок)"><textarea rows={2} value={(data.variables || []).join("\n")} onChange={(e) => setF("variables", e.target.value.split("\n").map((s) => s.trim()).filter(Boolean))} /></Field>

                <div className="nttx-actions">
                  {can.edit ? <button type="button" className="ntv2-btn" onClick={save}>{creating ? "Создать" : "Сохранить"}</button> : null}
                  <button type="button" className="ntv2-btn-mini" onClick={runPreview}>Предпросмотр</button>
                  {!creating && can.publish ? (
                    <>
                      <button type="button" className="ntv2-btn-mini" onClick={() => lifecycle("publish")}>Опубликовать</button>
                      <button type="button" className="ntv2-btn-mini" onClick={() => lifecycle("disable")}>Отключить</button>
                      <button type="button" className="ntv2-btn-mini" onClick={() => lifecycle("archive")}>В архив</button>
                    </>
                  ) : null}
                </div>
              </div>

              <div className="nttx-preview">
                <h3>📱 Предпросмотр</h3>
                {preview != null ? (
                  <pre className="nttx-tg">{preview || "(пусто)"}</pre>
                ) : <p className="ntv2-muted">Нажмите «Предпросмотр» — подставим переменные как {"{name}"}.</p>}
              </div>
            </>
          )}
        </div>
      </div>
    </section>
  );
}

const TX_CSS = `
.nttx-layout{display:flex;gap:14px;align-items:flex-start}
.nttx-list{width:240px;flex-shrink:0}
.nttx-list select{width:100%;padding:6px 8px;border:1px solid #cbd5e1;border-radius:8px;margin-bottom:6px}
.nttx-list ul{list-style:none;margin:0;padding:0;max-height:62vh;overflow:auto}
.nttx-list li{padding:8px 10px;border:1px solid #e2e8f0;border-radius:8px;margin-bottom:6px;cursor:pointer;display:flex;flex-direction:column}
.nttx-list li.active{border-color:#2563eb;background:#eff6ff}
.nttx-list li small{color:#94a3b8}
.nttx-empty{color:#94a3b8;text-align:center}
.nttx-main{flex:1;min-width:0;display:flex;gap:14px;flex-wrap:wrap}
.nttx-form{flex:1;min-width:360px}
.nttx-form .ntv2-field{display:block;margin-bottom:8px}
.nttx-info{flex-basis:100%;background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;padding:6px 10px;font-size:13px}
.nttx-placeholder{color:#64748b;padding:30px;text-align:center;border:1px dashed #cbd5e1;border-radius:12px;flex-basis:100%}
.nttx-actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}
.nttx-preview{width:300px;flex-shrink:0;border:1px solid #e2e8f0;border-radius:12px;padding:12px;background:#f8fafc}
.nttx-preview h3{margin:0 0 8px;font-size:15px}
.nttx-tg{white-space:pre-wrap;background:#fff;border:1px solid #cbd5e1;border-radius:10px;padding:10px;font-size:13px;font-family:inherit}
`;
