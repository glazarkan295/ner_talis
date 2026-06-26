import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  fetchWmMeta, fetchWmList, fetchWm, createWm, updateWm, wmLifecycle, previewWmAdhoc,
} from "../../../api/adminWorkshopMessageApi.js";

// Конструктор сообщений мастерских (ТЗ 14): порядок блоков, отображение списков,
// кнопки, формат отправки, пагинация + предпросмотр Telegram/VK.

const EMPTY = {
  name: "", scope: "global", workshop_id: "", workshop_type: "",
  header: "", description: "", image: "",
  block_order: ["header", "description", "available_recipes", "unavailable_recipes", "materials", "requirements", "queue", "hints", "buttons"],
  grouping: "none", sorting: "alpha", unavailable_display: "name_reason",
  show_only_missing: false, requirements_display: "all", show_queue: "if_active",
  send_format: "single", use_pagination: false, items_per_page: 8,
  hints: [], buttons: [], result_texts: {},
};

function Field({ label, children }) {
  return <label className="ntv2-field"><span>{label}</span>{children}</label>;
}

export function WorkshopMessagesSection({ guarded, hasPerm }) {
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
    create: hasPerm("workshop_message.create"), edit: hasPerm("workshop_message.edit"),
    publish: hasPerm("workshop_message.publish"),
  }), [hasPerm]);

  const load = useCallback(async () => { const p = await guarded(() => fetchWmList(statusFilter)); if (p) setList(p.items || []); }, [guarded, statusFilter]);
  useEffect(() => { (async () => { const m = await guarded(() => fetchWmMeta()); if (m) setMeta(m); })(); }, [guarded]);
  useEffect(() => { load(); }, [load]);

  const statuses = meta?.statuses || [];
  const statusLabel = (v) => statuses.find((s) => s.value === v)?.label || v;
  const blockLabel = (b) => meta?.blockTypes?.find((x) => x.value === b)?.label || b;

  async function openItem(id) {
    setSelected(id); setCreating(false); setPreview(null);
    const p = await guarded(() => fetchWm(id));
    if (p) setData({ ...EMPTY, ...(p.item.data || {}) });
  }
  function startCreate() { setCreating(true); setSelected(null); setNewId(""); setData({ ...EMPTY }); setPreview(null); }
  async function save() {
    if (creating) {
      if (!newId.trim()) { setInfo("Укажите ID шаблона."); return; }
      const r = await guarded(() => createWm(newId.trim(), data, "create template"));
      if (r) { setInfo("Создано."); setCreating(false); await load(); await openItem(newId.trim()); }
    } else if (selected) {
      const r = await guarded(() => updateWm(selected, data, "edit template"));
      if (r) { setInfo("Сохранено."); await load(); }
    }
  }
  async function lifecycle(verb) { if (!selected) return; const r = await guarded(() => wmLifecycle(selected, verb, verb)); if (r) { setInfo(`Статус: ${verb}`); await load(); } }
  async function runPreview() { const r = await guarded(() => previewWmAdhoc(data, null)); if (r) setPreview(r.preview); }

  const setF = (k, v) => setData((d) => ({ ...d, [k]: v }));
  const allBlocks = meta?.blockTypes?.map((b) => b.value) || [];
  const order = data?.block_order || [];
  const toggleBlock = (b) => setF("block_order", order.includes(b) ? order.filter((x) => x !== b) : [...order, b]);
  const moveBlock = (i, dir) => {
    const j = i + dir;
    if (j < 0 || j >= order.length) return;
    const next = [...order];
    [next[i], next[j]] = [next[j], next[i]];
    setF("block_order", next);
  };

  return (
    <section className="ntv2-section ntwm">
      <style>{WM_CSS}</style>
      <header className="ntv2-section-head">
        <div>
          <h2>🧾 Сообщения мастерских</h2>
          <p className="ntv2-muted">Шаблоны отображения списков рецептов/материалов/требований/очереди и кнопок в сообщениях ремесла (Telegram/VK).</p>
        </div>
        {can.create ? <button type="button" className="ntv2-btn" onClick={startCreate}>＋ Новый шаблон</button> : null}
      </header>

      <div className="ntwm-layout">
        <aside className="ntwm-list">
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            <option value="">Все статусы</option>
            {statuses.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
          </select>
          <ul>
            {list.map((s) => <li key={s.id} className={selected === s.id ? "active" : ""} onClick={() => openItem(s.id)}><b>{s.data?.name || s.id}</b><small>{statusLabel(s.status)}</small></li>)}
            {!list.length ? <li className="ntwm-empty">Пусто</li> : null}
          </ul>
        </aside>

        <div className="ntwm-main">
          {info ? <div className="ntwm-info">{info}</div> : null}
          {!data ? <div className="ntwm-placeholder">Выберите шаблон или создайте новый.</div> : (
            <>
              <div className="ntwm-form">
                {creating ? <Field label="ID шаблона"><input value={newId} onChange={(e) => setNewId(e.target.value)} placeholder="forge_default" /></Field> : null}
                <div className="ntv2-form-row">
                  <Field label="Название"><input value={data.name} onChange={(e) => setF("name", e.target.value)} /></Field>
                  <Field label="Область"><select value={data.scope} onChange={(e) => setF("scope", e.target.value)}>{(meta?.scopes || []).map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}</select></Field>
                  {data.scope === "by_workshop" ? <Field label="Мастерская (id)"><input value={data.workshop_id} onChange={(e) => setF("workshop_id", e.target.value)} /></Field> : null}
                </div>
                <Field label="Заголовок"><input value={data.header} onChange={(e) => setF("header", e.target.value)} /></Field>
                <Field label="Описание"><textarea rows={2} value={data.description} onChange={(e) => setF("description", e.target.value)} /></Field>

                <div className="ntwm-panel">
                  <b>Порядок блоков</b>
                  <div className="ntwm-blocks">
                    {order.map((b, i) => (
                      <div className="ntwm-block-row" key={b}>
                        <span>{i + 1}. {blockLabel(b)}</span>
                        <span className="ntwm-block-ctl">
                          <button type="button" className="ntv2-btn-mini" onClick={() => moveBlock(i, -1)}>▲</button>
                          <button type="button" className="ntv2-btn-mini" onClick={() => moveBlock(i, 1)}>▼</button>
                          <button type="button" className="ntv2-btn-mini" onClick={() => toggleBlock(b)}>✕</button>
                        </span>
                      </div>
                    ))}
                  </div>
                  <div className="ntwm-add-blocks">
                    {allBlocks.filter((b) => !order.includes(b)).map((b) => <button type="button" key={b} className="ntv2-btn-mini" onClick={() => toggleBlock(b)}>＋ {blockLabel(b)}</button>)}
                  </div>
                </div>

                <div className="ntv2-form-row">
                  <Field label="Группировка"><select value={data.grouping} onChange={(e) => setF("grouping", e.target.value)}>{(meta?.groupingModes || []).map((g) => <option key={g} value={g}>{g}</option>)}</select></Field>
                  <Field label="Сортировка"><select value={data.sorting} onChange={(e) => setF("sorting", e.target.value)}>{(meta?.sortModes || []).map((g) => <option key={g} value={g}>{g}</option>)}</select></Field>
                  <Field label="Недоступные рецепты"><select value={data.unavailable_display} onChange={(e) => setF("unavailable_display", e.target.value)}>{(meta?.unavailableDisplay || []).map((g) => <option key={g} value={g}>{g}</option>)}</select></Field>
                </div>
                <div className="ntv2-form-row" style={{ gap: 14 }}>
                  <label className="ntv2-check"><input type="checkbox" checked={data.show_only_missing} onChange={(e) => setF("show_only_missing", e.target.checked)} /> Только недостающие материалы</label>
                  <Field label="Требования"><select value={data.requirements_display} onChange={(e) => setF("requirements_display", e.target.value)}><option value="all">все</option><option value="unmet_only">только невыполненные</option></select></Field>
                  <Field label="Очередь"><select value={data.show_queue} onChange={(e) => setF("show_queue", e.target.value)}><option value="always">всегда</option><option value="if_active">если есть</option><option value="never">не показывать</option></select></Field>
                </div>
                <div className="ntv2-form-row" style={{ gap: 14, alignItems: "center" }}>
                  <Field label="Формат отправки"><select value={data.send_format} onChange={(e) => setF("send_format", e.target.value)}>{(meta?.sendFormats || []).map((g) => <option key={g} value={g}>{g === "single" ? "одно сообщение" : "несколько"}</option>)}</select></Field>
                  <label className="ntv2-check"><input type="checkbox" checked={data.use_pagination} onChange={(e) => setF("use_pagination", e.target.checked)} /> Пагинация</label>
                  {data.use_pagination ? <Field label="На странице"><input type="number" value={data.items_per_page} onChange={(e) => setF("items_per_page", e.target.value)} /></Field> : null}
                </div>
                <Field label="Подсказки (по строкам)"><textarea rows={2} value={(data.hints || []).join("\n")} onChange={(e) => setF("hints", e.target.value.split("\n").map((s) => s.trim()).filter(Boolean))} /></Field>
                <Field label="Кнопки (текст по строкам)"><textarea rows={2} value={(data.buttons || []).map((b) => b.text || "").join("\n")} onChange={(e) => setF("buttons", e.target.value.split("\n").map((s) => s.trim()).filter(Boolean).map((txt) => ({ text: txt })))} /></Field>

                <div className="ntwm-actions">
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

              <div className="ntwm-preview">
                <h3>📱 Предпросмотр</h3>
                {preview ? (
                  <>
                    <pre className="ntwm-tg">{preview.text || "(пусто)"}</pre>
                    <div className="ntv2-muted">Длина: {preview.length} симв.</div>
                  </>
                ) : <p className="ntv2-muted">Нажмите «Предпросмотр» — покажем сообщение на тестовом состоянии.</p>}
              </div>
            </>
          )}
        </div>
      </div>
    </section>
  );
}

const WM_CSS = `
.ntwm-layout{display:flex;gap:14px;align-items:flex-start}
.ntwm-list{width:220px;flex-shrink:0}
.ntwm-list select{width:100%;padding:6px 8px;border:1px solid #cbd5e1;border-radius:8px;margin-bottom:6px}
.ntwm-list ul{list-style:none;margin:0;padding:0;max-height:62vh;overflow:auto}
.ntwm-list li{padding:8px 10px;border:1px solid #e2e8f0;border-radius:8px;margin-bottom:6px;cursor:pointer;display:flex;flex-direction:column}
.ntwm-list li.active{border-color:#2563eb;background:#eff6ff}
.ntwm-list li small{color:#94a3b8}
.ntwm-empty{color:#94a3b8;text-align:center}
.ntwm-main{flex:1;min-width:0;display:flex;gap:14px;flex-wrap:wrap}
.ntwm-form{flex:1;min-width:360px}
.ntwm-form .ntv2-field{display:block;margin-bottom:8px}
.ntwm-info{flex-basis:100%;background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;padding:6px 10px;font-size:13px}
.ntwm-placeholder{color:#64748b;padding:30px;text-align:center;border:1px dashed #cbd5e1;border-radius:12px;flex-basis:100%}
.ntwm-panel{border:1px solid #e2e8f0;border-radius:8px;padding:8px;margin:8px 0}
.ntwm-blocks{margin:6px 0}
.ntwm-block-row{display:flex;justify-content:space-between;align-items:center;padding:4px 6px;border-bottom:1px solid #f1f5f9}
.ntwm-block-ctl{display:flex;gap:4px}
.ntwm-add-blocks{display:flex;flex-wrap:wrap;gap:6px;margin-top:6px}
.ntwm-actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}
.ntwm-preview{width:300px;flex-shrink:0;border:1px solid #e2e8f0;border-radius:12px;padding:12px;background:#f8fafc}
.ntwm-preview h3{margin:0 0 8px;font-size:15px}
.ntwm-tg{white-space:pre-wrap;background:#fff;border:1px solid #cbd5e1;border-radius:10px;padding:10px;font-size:13px;font-family:inherit}
`;
