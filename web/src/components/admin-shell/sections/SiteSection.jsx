import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  createSiteItem,
  fetchSiteItem,
  fetchSiteItems,
  fetchSiteMeta,
  fetchSiteWhereUsed,
  siteLifecycle,
  updateSiteItem,
  validateSiteItem,
} from "../../../api/adminSiteApi.js";
import {
  tr, BANNER_TYPE, GUIDE_DIFFICULTY, SITE_KIND, SITE_BLOCK_TYPE, SITE_PAGE_VISIBILITY,
  SITE_BLOCK_WIDTH, SITE_BLOCK_ALIGN, SITE_RATING_TYPE, SITE_RATING_PERIOD, SITE_LORE_TYPE,
} from "../../../i18n/adminLabels.js";
import { ConfirmModal } from "../ConfirmModal.jsx";
import { EmojiInput, EmojiTextarea } from "../EmojiField.jsx";
import { ImageUploadField } from "../ImageUploadField.jsx";

const KIND_LABELS = {
  news: "📰 Новости", guide: "📚 Гайды", faq: "❓ FAQ", banner: "🎌 Баннеры", announcement: "📢 Объявления",
  page: "📄 Страницы", page_block: "🧩 Блоки страниц", menu_item: "🧭 Меню", post: "✍️ Посты",
  rating: "🏆 Рейтинги", lore: "📜 Лор", where_is: "📍 Что где находится", site_theme: "🎨 Оформление",
};
const KIND_NEW = {
  news: "＋ Новость", guide: "＋ Гайд", faq: "＋ Вопрос", banner: "＋ Баннер", announcement: "＋ Объявление",
  page: "＋ Страница", page_block: "＋ Блок", menu_item: "＋ Пункт меню", post: "＋ Пост",
  rating: "＋ Рейтинг", lore: "＋ Запись лора", where_is: "＋ Запись", site_theme: "＋ Оформление",
};
const STATUS_TONE = { published: "ntv2-badge-owner", error: "ntv2-badge-error", hidden: "ntv2-badge-danger", scheduled: "ntv2-badge-error" };

// Права по типу — зеркало admin_site_api._KIND_CONFIG.
const _SITE = { create: "site.homepage_edit", edit: "site.homepage_edit", publish: "site.homepage_edit", archive: "site.homepage_edit" };
const _GUIDES = { create: "guides.create", edit: "guides.edit", publish: "guides.publish", archive: "guides.archive" };
const _NEWS = { create: "news.create", edit: "news.edit", publish: "news.publish", archive: "news.archive" };
const KIND_PERMS = {
  news: _NEWS, post: _NEWS, guide: _GUIDES, lore: _GUIDES, where_is: _GUIDES,
  faq: { create: "faq.create", edit: "faq.edit", publish: "faq.publish", archive: "faq.publish" },
  banner: _SITE, announcement: _SITE, page: _SITE, page_block: _SITE,
  menu_item: { create: "site.menu_edit", edit: "site.menu_edit", publish: "site.menu_edit", archive: "site.menu_edit" },
  site_theme: { create: "site.settings_edit", edit: "site.settings_edit", publish: "site.settings_edit", archive: "site.settings_edit" },
  rating: { create: "ratings.create", edit: "ratings.edit", publish: "ratings.publish", archive: "ratings.publish" },
};
function KIND_CAN(kind, hasPerm) {
  const p = KIND_PERMS[kind] || _NEWS;
  return { create: hasPerm(p.create), edit: hasPerm(p.edit), publish: hasPerm(p.publish), archive: hasPerm(p.archive) };
}

// Поля формы зависят от типа; общие — title/body, FAQ — question/answer.
const EMPTY_BY_KIND = {
  news: { title: "", short_description: "", body: "", category: "", cover: "", publish_at: "", end_at: "", pinned: false, show_home: false },
  guide: { title: "", short_description: "", body: "", category: "", difficulty: "novice", image: "" },
  faq: { question: "", answer: "", short_description: "", category: "" },
  banner: { title: "", text: "", type: "info", icon: "", start_date: "", end_date: "", show_home: true },
  announcement: { title: "", text: "", type: "info", icon: "", start_date: "", end_date: "" },
  page: { title: "", slug: "", short_description: "", body: "", image: "", background: "", color_scheme: "", visibility: "public", menu_order: 0, seo_title: "", seo_description: "", related: "" },
  page_block: { title: "", block_type: "text", page_id: "", content: "", image: "", bg_color: "", text_color: "", width: "full", align: "left", order: 0, show_pc: true, show_mobile: true },
  menu_item: { label: "", link: "", page_id: "", icon: "", parent_id: "", order: 0, visible: true, condition: "", mobile: true },
  post: { title: "", short_description: "", body: "", category: "", image: "", author: "", tags: "", pinned: false, show_home: false },
  rating: { title: "", description: "", rating_type: "level", period: "all_time", participants: "", show_fields: "", visible: true },
  lore: { title: "", lore_type: "history", text: "", image: "", related_location: "", related_npc: "", visibility: "public" },
  where_is: { title: "", short_answer: "", description: "", place: "", quarter: "", building: "", npc: "", button: "", image: "" },
  site_theme: { title: "", site_background: "", home_background: "", panel_color: "", card_color: "", button_color: "", text_color: "", link_color: "", warning_color: "", border_style: "", block_opacity: "", heading_style: "", menu_style: "" },
};

// Схемы новых типов (§2.3–2.12): поля рендерит GenericSiteForm.
// type: text | textarea | image | number | checkbox | select(options[, labelMap]) | meta(metaKey, labelMap)
const SCHEMA_BY_KIND = {
  page: [
    { k: "title", label: "Название страницы", type: "text" },
    { k: "slug", label: "Адрес (slug)", type: "text" },
    { k: "visibility", label: "Видимость", type: "meta", metaKey: "pageVisibilities", labelMap: SITE_PAGE_VISIBILITY },
    { k: "menu_order", label: "Порядок в меню", type: "number" },
    { k: "short_description", label: "Краткое описание", type: "textarea" },
    { k: "body", label: "Полный текст", type: "textarea" },
    { k: "image", label: "Изображение/баннер", type: "image", category: "site" },
    { k: "background", label: "Фон страницы", type: "image", category: "site" },
    { k: "color_scheme", label: "Цветовая схема", type: "text" },
    { k: "related", label: "Связанные материалы", type: "text" },
    { k: "seo_title", label: "SEO-заголовок", type: "text" },
    { k: "seo_description", label: "SEO-описание", type: "textarea" },
  ],
  page_block: [
    { k: "title", label: "Название блока", type: "text" },
    { k: "block_type", label: "Тип блока", type: "meta", metaKey: "blockTypes", labelMap: SITE_BLOCK_TYPE },
    { k: "page_id", label: "ID страницы", type: "text" },
    { k: "content", label: "Содержимое", type: "textarea" },
    { k: "image", label: "Изображение", type: "image", category: "site" },
    { k: "width", label: "Ширина", type: "meta", metaKey: "blockWidths", labelMap: SITE_BLOCK_WIDTH },
    { k: "align", label: "Выравнивание", type: "meta", metaKey: "blockAligns", labelMap: SITE_BLOCK_ALIGN },
    { k: "bg_color", label: "Цвет фона", type: "text" },
    { k: "text_color", label: "Цвет текста", type: "text" },
    { k: "order", label: "Порядок на странице", type: "number" },
    { k: "show_pc", label: "Показывать на ПК", type: "checkbox" },
    { k: "show_mobile", label: "Показывать на телефоне", type: "checkbox" },
  ],
  menu_item: [
    { k: "label", label: "Подпись", type: "text" },
    { k: "icon", label: "Иконка/эмодзи", type: "text" },
    { k: "link", label: "Ссылка", type: "text" },
    { k: "page_id", label: "Страница (ID)", type: "text" },
    { k: "parent_id", label: "Родительский пункт (ID)", type: "text" },
    { k: "order", label: "Порядок", type: "number" },
    { k: "condition", label: "Условие показа", type: "text" },
    { k: "visible", label: "Показывать", type: "checkbox" },
    { k: "mobile", label: "Показывать в мобильном меню", type: "checkbox" },
  ],
  post: [
    { k: "title", label: "Заголовок", type: "text" },
    { k: "category", label: "Категория", type: "metaPlain", metaKey: "newsCategories" },
    { k: "short_description", label: "Краткое описание", type: "textarea" },
    { k: "body", label: "Полный текст", type: "textarea" },
    { k: "image", label: "Изображение", type: "image", category: "site" },
    { k: "author", label: "Автор", type: "text" },
    { k: "tags", label: "Теги (через запятую)", type: "text" },
    { k: "pinned", label: "Закрепить", type: "checkbox" },
    { k: "show_home", label: "Показать на главной", type: "checkbox" },
  ],
  rating: [
    { k: "title", label: "Название рейтинга", type: "text" },
    { k: "rating_type", label: "Тип рейтинга", type: "meta", metaKey: "ratingTypes", labelMap: SITE_RATING_TYPE },
    { k: "period", label: "Период", type: "meta", metaKey: "ratingPeriods", labelMap: SITE_RATING_PERIOD },
    { k: "description", label: "Описание", type: "textarea" },
    { k: "participants", label: "Кто участвует", type: "text" },
    { k: "show_fields", label: "Какие данные показывать", type: "text" },
    { k: "visible", label: "Показывать на сайте", type: "checkbox" },
  ],
  lore: [
    { k: "title", label: "Название", type: "text" },
    { k: "lore_type", label: "Тип записи", type: "meta", metaKey: "loreTypes", labelMap: SITE_LORE_TYPE },
    { k: "text", label: "Текст", type: "textarea" },
    { k: "image", label: "Изображение", type: "image", category: "site" },
    { k: "related_location", label: "Связанная локация", type: "text" },
    { k: "related_npc", label: "Связанный NPC", type: "text" },
    { k: "visibility", label: "Видимость", type: "meta", metaKey: "pageVisibilities", labelMap: SITE_PAGE_VISIBILITY },
  ],
  where_is: [
    { k: "title", label: "Название", type: "text" },
    { k: "short_answer", label: "Краткий ответ", type: "text" },
    { k: "description", label: "Подробное описание", type: "textarea" },
    { k: "place", label: "Город/крепость/локация", type: "text" },
    { k: "quarter", label: "Квартал", type: "text" },
    { k: "building", label: "Здание", type: "text" },
    { k: "npc", label: "NPC", type: "text" },
    { k: "button", label: "Кнопка для перехода", type: "text" },
    { k: "image", label: "Изображение", type: "image", category: "site" },
  ],
  site_theme: [
    { k: "title", label: "Название оформления", type: "text" },
    { k: "site_background", label: "Общий фон сайта", type: "image", category: "site" },
    { k: "home_background", label: "Фон главной", type: "image", category: "site" },
    { k: "panel_color", label: "Цвет основной панели", type: "text" },
    { k: "card_color", label: "Цвет карточек", type: "text" },
    { k: "button_color", label: "Цвет кнопок", type: "text" },
    { k: "text_color", label: "Цвет текста", type: "text" },
    { k: "link_color", label: "Цвет ссылок", type: "text" },
    { k: "warning_color", label: "Цвет предупреждений", type: "text" },
    { k: "border_style", label: "Стиль рамок", type: "text" },
    { k: "block_opacity", label: "Прозрачность блоков (0–100)", type: "number" },
    { k: "heading_style", label: "Стиль заголовков", type: "text" },
    { k: "menu_style", label: "Стиль меню", type: "text" },
  ],
};

function Field({ label, children }) {
  return <label className="ntv2-field"><span>{label}</span>{children}</label>;
}

// Схема-форма для расширенных типов сайта (§2). Изображения — файлом.
function GenericSiteForm({ schema, value, onChange, meta, disabled, uploadKey }) {
  const set = (k, v) => onChange({ ...value, [k]: v });
  return (
    <div className="ntv2-world-form">
      {schema.map((f) => {
        if (f.type === "image") {
          return <ImageUploadField key={f.k} label={f.label} value={value[f.k] || ""} category={f.category || "site"} uploadKey={`${uploadKey || "new"}_${f.k}`} disabled={disabled} onChange={(v) => set(f.k, v)} />;
        }
        if (f.type === "checkbox") {
          return <label className="ntv2-check" key={f.k}><input type="checkbox" checked={Boolean(value[f.k])} disabled={disabled} onChange={(e) => set(f.k, e.target.checked)} /> {f.label}</label>;
        }
        if (f.type === "number") {
          return <Field label={f.label} key={f.k}><input type="number" value={value[f.k] ?? ""} disabled={disabled} onChange={(e) => set(f.k, e.target.value)} /></Field>;
        }
        if (f.type === "textarea") {
          return <Field label={f.label} key={f.k}><EmojiTextarea rows={3} value={value[f.k] || ""} disabled={disabled} onChange={(v) => set(f.k, v)} /></Field>;
        }
        if (f.type === "meta" || f.type === "metaPlain") {
          const options = (meta && meta[f.metaKey]) || [];
          return (
            <Field label={f.label} key={f.k}>
              <select value={value[f.k] ?? ""} disabled={disabled} onChange={(e) => set(f.k, e.target.value)}>
                <option value="">—</option>
                {options.map((o) => <option key={o} value={o}>{f.labelMap ? tr(f.labelMap, o) : o}</option>)}
              </select>
            </Field>
          );
        }
        return <Field label={f.label} key={f.k}><EmojiInput value={value[f.k] || ""} disabled={disabled} onChange={(v) => set(f.k, v)} /></Field>;
      })}
    </div>
  );
}

function itemTitle(kind, item) {
  const d = item.data || {};
  if (kind === "faq") return d.question || item.id;
  if (kind === "menu_item") return d.label || item.id;
  return d.title || item.id;
}

function SiteForm({ kind, value, onChange, meta, disabled }) {
  const set = (k, v) => onChange({ ...value, [k]: v });
  if (kind === "faq") {
    return (
      <div className="ntv2-world-form">
        <Field label="Вопрос"><EmojiInput value={value.question} disabled={disabled} onChange={(v) => set("question", v)} /></Field>
        <Field label="Краткий ответ"><EmojiTextarea rows={2} value={value.short_description} disabled={disabled} onChange={(v) => set("short_description", v)} /></Field>
        <Field label="Подробный ответ"><EmojiTextarea rows={4} value={value.answer} disabled={disabled} onChange={(v) => set("answer", v)} /></Field>
        <Field label="Категория"><input value={value.category} disabled={disabled} onChange={(e) => set("category", e.target.value)} /></Field>
      </div>
    );
  }
  if (kind === "banner" || kind === "announcement") {
    return (
      <div className="ntv2-world-form">
        <div className="ntv2-form-row">
          <Field label="Заголовок"><EmojiInput value={value.title} disabled={disabled} onChange={(v) => set("title", v)} /></Field>
          <Field label="Тип"><select value={value.type} disabled={disabled} onChange={(e) => set("type", e.target.value)}>{(meta.bannerTypes || []).map((x) => <option key={x} value={x}>{tr(BANNER_TYPE, x)}</option>)}</select></Field>
        </div>
        <Field label="Текст"><EmojiTextarea rows={3} value={value.text} disabled={disabled} onChange={(v) => set("text", v)} /></Field>
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
        <Field label="Заголовок"><EmojiInput value={value.title} disabled={disabled} onChange={(v) => set("title", v)} /></Field>
        {kind === "news"
          ? <Field label="Категория"><select value={value.category} disabled={disabled} onChange={(e) => set("category", e.target.value)}><option value="">—</option>{(meta.newsCategories || []).map((c) => <option key={c} value={c}>{c}</option>)}</select></Field>
          : <Field label="Сложность"><select value={value.difficulty} disabled={disabled} onChange={(e) => set("difficulty", e.target.value)}>{(meta.guideDifficulties || []).map((d) => <option key={d} value={d}>{tr(GUIDE_DIFFICULTY, d)}</option>)}</select></Field>}
      </div>
      <Field label="Краткое описание"><EmojiTextarea rows={2} value={value.short_description} disabled={disabled} onChange={(v) => set("short_description", v)} /></Field>
      <Field label="Полный текст"><EmojiTextarea rows={5} value={value.body} disabled={disabled} onChange={(v) => set("body", v)} /></Field>
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
  const [usedBy, setUsedBy] = useState(null);

  // Права по типу — зеркало admin_site_api._KIND_CONFIG.
  const can = useMemo(() => KIND_CAN(kind, hasPerm), [kind, hasPerm]);

  const load = useCallback(async () => { const p = await guarded(() => fetchSiteItems(kind, statusFilter)); if (p) setList(p.items || []); }, [guarded, kind, statusFilter]);
  useEffect(() => { (async () => { const m = await guarded(() => fetchSiteMeta()); if (m) setMeta(m); })(); }, [guarded]);
  useEffect(() => { load(); }, [load]);

  const statuses = meta?.statuses || [];
  const statusLabel = (v) => statuses.find((s) => s.value === v)?.label || v;

  function switchKind(k) { setKind(k); setEditing(null); setStatusFilter(""); setUsedBy(null); }
  function startCreate() { setEditing({ id: "", data: { ...(EMPTY_BY_KIND[kind] || {}) }, status: "draft", validation: null, isNew: true }); setUsedBy(null); }
  async function openItem(id) {
    setUsedBy(null);
    const p = await guarded(() => fetchSiteItem(kind, id));
    if (p?.item) setEditing({ id, data: { ...(EMPTY_BY_KIND[kind] || {}), ...(p.item.data || {}) }, status: p.item.status, validation: p.validation, isNew: false });
  }
  async function loadWhereUsed() { const p = await guarded(() => fetchSiteWhereUsed(kind, editing.id)); if (p) setUsedBy(p.usedBy || []); }

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

        {SCHEMA_BY_KIND[kind]
          ? <GenericSiteForm schema={SCHEMA_BY_KIND[kind]} value={editing.data} onChange={(data) => setEditing({ ...editing, data })} meta={meta} disabled={disabled} uploadKey={editing.id} />
          : <SiteForm kind={kind} value={editing.data} onChange={(data) => setEditing({ ...editing, data })} meta={meta} disabled={disabled} />}

        {v ? (
          <div className={`ntv2-panel ${v.ok ? "" : "ntv2-danger-zone"}`}>
            <h4 className="ntv2-subhead">{v.ok ? "✅ Готово к публикации" : "❌ Проверка не пройдена"}</h4>
            {(v.errors || []).map((e, i) => <div className="ntv2-error" key={"e" + i}>{e}</div>)}
            {(v.warnings || []).map((w, i) => <p className="ntv2-hint" key={"w" + i}>⚠️ {w}</p>)}
          </div>
        ) : null}

        {!editing.isNew && (kind === "page" || kind === "menu_item") ? (
          <div className="ntv2-panel">
            <div className="ntv2-card-head" style={{ marginBottom: 6 }}>
              <h4 className="ntv2-subhead" style={{ margin: 0 }}>Где используется</h4>
              <button type="button" className="ntv2-btn" onClick={loadWhereUsed}>Проверить связи</button>
            </div>
            {usedBy === null ? <p className="ntv2-hint">Нажмите «Проверить связи», чтобы увидеть зависимые блоки/пункты меню.</p> : null}
            {usedBy !== null && !usedBy.length ? <p className="ntv2-hint">Ничего не ссылается — можно безопасно изменить/скрыть.</p> : null}
            {usedBy && usedBy.length ? (
              <div className="ntv2-list">
                {usedBy.map((u) => (
                  <div className="ntv2-list-row" key={u.id}>
                    <b>{u.name}</b><span className="ntv2-mono">{u.id}</span>
                    <span className="ntv2-hint">{tr(SITE_KIND, u.kind)} · {(u.fields || []).join(", ")}</span>
                  </div>
                ))}
              </div>
            ) : null}
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
