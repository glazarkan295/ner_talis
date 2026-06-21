import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  createSiteItem,
  fetchSiteItem,
  fetchSiteItems,
  fetchSiteMeta,
  siteLifecycle,
  updateSiteItem,
  validateSiteItem,
} from "../../../api/adminSiteApi.js";
import { tr, BANNER_TYPE, GUIDE_DIFFICULTY } from "../../../i18n/adminLabels.js";
import { ConfirmModal } from "../ConfirmModal.jsx";

const KIND_LABELS = { news: "📰 Новости", guide: "📚 Гайды", faq: "❓ FAQ", banner: "🎌 Баннеры", announcement: "📢 Объявления" };
const KIND_NEW = { news: "＋ Новость", guide: "＋ Гайд", faq: "＋ Вопрос", banner: "＋ Баннер", announcement: "＋ Объявление" };
const STATUS_TONE = { published: "ntv2-badge-owner", error: "ntv2-badge-error", hidden: "ntv2-badge-danger", scheduled: "ntv2-badge-error" };

// Поля формы зависят от типа; общие — title/body, FAQ — question/answer.
const EMPTY_BY_KIND = {
  news: { title: "", short_description: "", body: "", category: "", cover: "", publish_at: "", end_at: "", pinned: false, show_home: false },
  guide: { title: "", short_description: "", body: "", category: "", difficulty: "novice", image: "" },
  faq: { question: "", answer: "", short_description: "", category: "" },
  banner: { title: "", text: "", type: "info", icon: "", start_date: "", end_date: "", show_home: true },
  announcement: { title: "", text: "", type: "info", icon: "", start_date: "", end_date: "" },
};

function Field({ label, children }) {
  return <label className="ntv2-field"><span>{label}</span>{children}</label>;
}

function itemTitle(kind, item) {
  const d = item.data || {};
  return (kind === "faq" ? d.question : d.title) || item.id;
}

function SiteForm({ kind, value, onChange, meta, disabled }) {
  const set = (k, v) => onChange({ ...value, [k]: v });
  if (kind === "faq") {
    return (
      <div className="ntv2-world-form">
        <Field label="Вопрос"><input value={value.question} disabled={disabled} onChange={(e) => set("question", e.target.value)} /></Field>
        <Field label="Краткий ответ"><textarea rows={2} value={value.short_description} disabled={disabled} onChange={(e) => set("short_description", e.target.value)} /></Field>
        <Field label="Подробный ответ"><textarea rows={4} value={value.answer} disabled={disabled} onChange={(e) => set("answer", e.target.value)} /></Field>
        <Field label="Категория"><input value={value.category} disabled={disabled} onChange={(e) => set("category", e.target.value)} /></Field>
      </div>
    );
  }
  if (kind === "banner" || kind === "announcement") {
    return (
      <div className="ntv2-world-form">
        <div className="ntv2-form-row">
          <Field label="Заголовок"><input value={value.title} disabled={disabled} onChange={(e) => set("title", e.target.value)} /></Field>
          <Field label="Тип"><select value={value.type} disabled={disabled} onChange={(e) => set("type", e.target.value)}>{(meta.bannerTypes || []).map((x) => <option key={x} value={x}>{tr(BANNER_TYPE, x)}</option>)}</select></Field>
        </div>
        <Field label="Текст"><textarea rows={3} value={value.text} disabled={disabled} onChange={(e) => set("text", e.target.value)} /></Field>
        <div className="ntv2-form-row">
          <Field label="Иконка"><input value={value.icon} disabled={disabled} onChange={(e) => set("icon", e.target.value)} /></Field>
          <Field label="Дата начала (ISO)"><input value={value.start_date} disabled={disabled} onChange={(e) => set("start_date", e.target.value)} /></Field>
          <Field label="Дата окончания (ISO)"><input value={value.end_date} disabled={disabled} onChange={(e) => set("end_date", e.target.value)} /></Field>
        </div>
      </div>
    );
  }
  // news / guide
  return (
    <div className="ntv2-world-form">
      <div className="ntv2-form-row">
        <Field label="Заголовок"><input value={value.title} disabled={disabled} onChange={(e) => set("title", e.target.value)} /></Field>
        {kind === "news"
          ? <Field label="Категория"><select value={value.category} disabled={disabled} onChange={(e) => set("category", e.target.value)}><option value="">—</option>{(meta.newsCategories || []).map((c) => <option key={c} value={c}>{c}</option>)}</select></Field>
          : <Field label="Сложность"><select value={value.difficulty} disabled={disabled} onChange={(e) => set("difficulty", e.target.value)}>{(meta.guideDifficulties || []).map((d) => <option key={d} value={d}>{tr(GUIDE_DIFFICULTY, d)}</option>)}</select></Field>}
      </div>
      <Field label="Краткое описание"><textarea rows={2} value={value.short_description} disabled={disabled} onChange={(e) => set("short_description", e.target.value)} /></Field>
      <Field label="Полный текст"><textarea rows={5} value={value.body} disabled={disabled} onChange={(e) => set("body", e.target.value)} /></Field>
      <div className="ntv2-form-row">
        <Field label={kind === "news" ? "Обложка (URL)" : "Изображение (URL)"}><input value={kind === "news" ? value.cover : value.image} disabled={disabled} onChange={(e) => set(kind === "news" ? "cover" : "image", e.target.value)} /></Field>
        {kind === "news" ? <Field label="Дата публикации (ISO)"><input value={value.publish_at} disabled={disabled} onChange={(e) => set("publish_at", e.target.value)} /></Field> : null}
        {kind === "news" ? <label className="ntv2-check"><input type="checkbox" checked={Boolean(value.pinned)} disabled={disabled} onChange={(e) => set("pinned", e.target.checked)} /> Закрепить</label> : null}
        {kind === "news" ? <label className="ntv2-check"><input type="checkbox" checked={Boolean(value.show_home)} disabled={disabled} onChange={(e) => set("show_home", e.target.checked)} /> На главной</label> : null}
      </div>
    </div>
  );
}

export function SiteSection({ guarded, hasPerm }) {
  const [meta, setMeta] = useState(null);
  const [kind, setKind] = useState("news");
  const [list, setList] = useState([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [editing, setEditing] = useState(null);
  const [confirm, setConfirm] = useState(null);

  // Права зависят от семьи: news.* / guides.* / faq.* / site.* (баннеры).
  const family = { news: "news", guide: "guides", faq: "faq", banner: "site", announcement: "site" }[kind];
  const can = useMemo(() => {
    if (family === "site") return { create: hasPerm("site.homepage_edit"), edit: hasPerm("site.homepage_edit"), publish: hasPerm("site.homepage_edit"), archive: hasPerm("site.homepage_edit") };
    if (family === "faq") return { create: hasPerm("faq.create"), edit: hasPerm("faq.edit"), publish: hasPerm("faq.publish"), archive: hasPerm("faq.publish") };
    return { create: hasPerm(`${family}.create`), edit: hasPerm(`${family}.edit`), publish: hasPerm(`${family}.publish`), archive: hasPerm(`${family}.archive`) };
  }, [family, hasPerm]);

  const load = useCallback(async () => { const p = await guarded(() => fetchSiteItems(kind, statusFilter)); if (p) setList(p.items || []); }, [guarded, kind, statusFilter]);
  useEffect(() => { (async () => { const m = await guarded(() => fetchSiteMeta()); if (m) setMeta(m); })(); }, [guarded]);
  useEffect(() => { load(); }, [load]);

  const statuses = meta?.statuses || [];
  const statusLabel = (v) => statuses.find((s) => s.value === v)?.label || v;

  function switchKind(k) { setKind(k); setEditing(null); setStatusFilter(""); }
  function startCreate() { setEditing({ id: "", data: { ...(EMPTY_BY_KIND[kind] || {}) }, status: "draft", validation: null, isNew: true }); }
  async function openItem(id) {
    const p = await guarded(() => fetchSiteItem(kind, id));
    if (p?.item) setEditing({ id, data: { ...(EMPTY_BY_KIND[kind] || {}), ...(p.item.data || {}) }, status: p.item.status, validation: p.validation, isNew: false });
  }

  async function save() {
    const e = editing;
    if (e.isNew) { const p = await guarded(() => createSiteItem(kind, e.id.trim(), e.data, ""), "Создано."); if (p?.item) await openItem(e.id.trim()); }
    else { await guarded(() => updateSiteItem(kind, e.id, e.data, "правка"), "Сохранено."); await openItem(e.id); }
    await load();
  }
  async function runValidate() { const p = await guarded(() => validateSiteItem(kind, editing.id, ""), "Проверка выполнена."); if (p?.validation) setEditing((c) => ({ ...c, validation: p.validation })); }
  async function refreshEditing() { await load(); if (editing) await openItem(editing.id); }

  if (!meta) return <section className="ntv2-section"><h2>Конструктор сайта</h2><p className="ntv2-hint">Загрузка…</p></section>;

  if (editing) {
    const disabled = !(editing.isNew ? can.create : can.edit);
    const v = editing.validation;
    return (
      <section className="ntv2-section">
        <div className="ntv2-card-head">
          <button type="button" className="ntv2-btn" onClick={() => setEditing(null)}>← К списку</button>
          <h2>{editing.isNew ? KIND_NEW[kind] : itemTitle(kind, { data: editing.data, id: editing.id })}</h2>
          {!editing.isNew ? <span className={`ntv2-badge ${STATUS_TONE[editing.status] || ""}`}>{statusLabel(editing.status)}</span> : null}
        </div>
        {editing.isNew ? <Field label="ID (латиница)"><input value={editing.id} onChange={(e) => setEditing({ ...editing, id: e.target.value })} /></Field> : <p className="ntv2-hint ntv2-mono">{editing.id}</p>}

        <SiteForm kind={kind} value={editing.data} onChange={(data) => setEditing({ ...editing, data })} meta={meta} disabled={disabled} />

        {v ? (
          <div className={`ntv2-panel ${v.ok ? "" : "ntv2-danger-zone"}`}>
            <h4 className="ntv2-subhead">{v.ok ? "✅ Готово к публикации" : "❌ Проверка не пройдена"}</h4>
            {(v.errors || []).map((e, i) => <div className="ntv2-error" key={"e" + i}>{e}</div>)}
            {(v.warnings || []).map((w, i) => <p className="ntv2-hint" key={"w" + i}>⚠️ {w}</p>)}
          </div>
        ) : null}

        <div className="ntv2-form-row" style={{ marginTop: 14 }}>
          {!disabled ? <button type="button" className="ntv2-btn ntv2-btn-primary" disabled={editing.isNew && !editing.id.trim()} onClick={save}>{editing.isNew ? "Создать" : "Сохранить"}</button> : null}
          {!editing.isNew && can.edit ? <button type="button" className="ntv2-btn" onClick={runValidate}>Проверить</button> : null}
          {!editing.isNew && can.publish ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => setConfirm({ title: "Опубликовать?", dangerous: true, confirmLabel: "Опубликовать", body: <p>Материал будет проверен и опубликован на сайте.</p>, run: async (r) => { await guarded(() => siteLifecycle(kind, editing.id, "publish", r), "Опубликовано."); await refreshEditing(); } })}>Опубликовать</button> : null}
          {!editing.isNew && can.publish && editing.status === "published" ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => setConfirm({ title: "Скрыть?", dangerous: true, confirmLabel: "Скрыть", body: <p>Материал будет скрыт с сайта.</p>, run: async (r) => { await guarded(() => siteLifecycle(kind, editing.id, "hide", r), "Скрыто."); await refreshEditing(); } })}>Скрыть</button> : null}
          {!editing.isNew && can.archive ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => setConfirm({ title: "В архив?", dangerous: true, confirmLabel: "В архив", body: <p>Материал уйдёт в архив.</p>, run: async (r) => { await guarded(() => siteLifecycle(kind, editing.id, "archive", r), "В архиве."); await refreshEditing(); } })}>В архив</button> : null}
        </div>

        <ConfirmModal open={Boolean(confirm)} title={confirm?.title} body={confirm?.body} dangerous={confirm?.dangerous} confirmLabel={confirm?.confirmLabel} requireReason
          onConfirm={async (r) => { await confirm.run(r); setConfirm(null); }} onCancel={() => setConfirm(null)} />
      </section>
    );
  }

  return (
    <section className="ntv2-section">
      <h2>Конструктор сайта</h2>
      <div className="ntv2-subnav">
        {meta.kinds.map((k) => <button key={k} type="button" className={`ntv2-subnav-item${k === kind ? " active" : ""}`} onClick={() => switchKind(k)}>{KIND_LABELS[k] || k}</button>)}
      </div>
      <div className="ntv2-filters">
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="">Все статусы</option>
          {statuses.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
        </select>
        {can.create ? <button type="button" className="ntv2-btn ntv2-btn-primary" onClick={startCreate}>{KIND_NEW[kind]}</button> : null}
      </div>
      {!list.length ? <p className="ntv2-hint">Материалов нет.</p> : null}
      <div className="ntv2-list">
        {list.map((item) => (
          <button key={item.id} type="button" className="ntv2-list-row ntv2-player-row" onClick={() => openItem(item.id)}>
            <b>{itemTitle(kind, item)}</b>
            <span className="ntv2-mono">{item.id}</span>
            <span className={`ntv2-badge ${STATUS_TONE[item.status] || ""}`}>{statusLabel(item.status)}</span>
            {item.data?.category ? <span className="ntv2-hint">{item.data.category}</span> : null}
          </button>
        ))}
      </div>
    </section>
  );
}
