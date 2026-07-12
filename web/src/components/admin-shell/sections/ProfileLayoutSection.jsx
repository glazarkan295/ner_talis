import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  createLayoutItem,
  deleteLayoutItem,
  fetchLayoutItem,
  fetchLayoutItems,
  fetchLayoutMeta,
  fetchLayoutWhereUsed,
  layoutLifecycle,
  updateLayoutItem,
  validateLayoutItem,
} from "../../../api/adminProfileLayoutApi.js";
import {
  tr, PROFILE_LAYOUT_KIND, PROFILE_BLOCK_TYPE, PROFILE_VISIBILITY, PROFILE_BLOCK_WIDTH,
} from "../../../i18n/adminLabels.js";
import { ConfirmModal } from "../ConfirmModal.jsx";
import { VersionHistory } from "../VersionHistory.jsx";
import { EmojiInput } from "../EmojiField.jsx";
import { ImageUploadField } from "../ImageUploadField.jsx";
import { SearchBox, NoResults, filterEntities } from "../SearchFilter.jsx";

const STATUS_TONE = { published: "ntv2-badge-owner", error: "ntv2-badge-error", disabled: "ntv2-badge-danger" };
const KIND_LABELS = { profile_settings: "⚙️ Основное и права", profile_tab: "📑 Вкладки", profile_block: "🧩 Блоки", profile_theme: "🎨 Оформление" };
const KIND_NEW = { profile_settings: "＋ Шаблон профиля", profile_tab: "＋ Вкладка", profile_block: "＋ Блок", profile_theme: "＋ Оформление" };

const EMPTY_BY_KIND = {
  profile_settings: { title: "", system_name: "", description: "", profile_type: "main", is_default: false, use_for_players: true, use_for_admin: false, use_for_test: false, profile_title: "Профиль персонажа", default_tab: "character", enabled_tabs: "", services_enabled: true, transfer_enabled: true, pavilion_enabled: true, promo_enabled: true, show_public_id: true, show_fines: true, show_achievements: true, show_activity: true, show_ratings: true, allow_profile_edit: true, allow_inventory_actions: true, allow_skill_actions: true, allow_transfer: true, allow_item_drop: true, allow_item_use: true, allow_equip: true, allow_craft_actions: true, readonly_text: "Админский режим: только просмотр, изменения отключены.", loading_text: "Загрузка профиля…", token_error_text: "Ссылка профиля недействительна.", expired_token_text: "Срок действия ссылки истёк.", unavailable_text: "Профиль недоступен.", empty_inventory_text: "Инвентарь пуст.", empty_skills_text: "Навыков пока нет.", no_fines_text: "Активных штрафов нет.", no_services_text: "Сервисы недоступны.", technical_error_text: "Произошла техническая ошибка." },
  profile_tab: { label: "", tab_key: "", icon: "", order: 0, visibility: "always", condition: "", show_pc: true, show_mobile: true, show_player: true, show_admin: true, hide_player: false, empty_text: "", default_tab: false },
  profile_block: { name: "", block_type: "main_info", tab: "", order: 0, width: "full", visibility: "always", condition: "", hint: "", show_pc: true, show_mobile: true, show_player: true, show_admin: true, hide_player: false, empty_text: "" },
  profile_theme: { title: "", profile_background: "", tab_background: "", card_background: "", button_color: "", text_color: "", border_color: "", active_tab_color: "", icon_style: "", card_style: "", modal_style: "", primary_color: "", secondary_color: "", background_color: "", positive_color: "", negative_color: "", warning_color: "", danger_color: "", border_style: "", border_radius: 12, icon_size: 32, item_image_size: 96, compact_mode: false, detailed_mode: true },
};

const SCHEMA_BY_KIND = {
  profile_settings: [
    { k: "title", label: "Название шаблона", type: "text" }, { k: "system_name", label: "Системное название", type: "text" }, { k: "description", label: "Описание", type: "textarea" },
    { k: "profile_type", label: "Тип профиля", type: "options", options: [["main", "Основной"], ["mobile", "Мобильный"], ["telegram", "Telegram"], ["vk", "VK"], ["site", "Сайт"], ["admin", "Админский"], ["read_only", "Read-only"], ["test", "Тестовый"], ["preview", "Предпросмотр"], ["service", "Служебный"]] },
    { k: "is_default", label: "Использовать как основной", type: "checkbox" }, { k: "use_for_players", label: "Использовать для игроков", type: "checkbox" }, { k: "use_for_admin", label: "Использовать для админского просмотра", type: "checkbox" }, { k: "use_for_test", label: "Использовать для тестового просмотра", type: "checkbox" },
    { k: "profile_title", label: "Заголовок профиля", type: "text" }, { k: "default_tab", label: "Вкладка по умолчанию", type: "text" }, { k: "enabled_tabs", label: "Разрешённые вкладки (через запятую)", type: "textarea" },
    { k: "services_enabled", label: "Разрешить сервисы", type: "checkbox" }, { k: "show_public_id", label: "Показывать публичный NT-ID", type: "checkbox" }, { k: "allow_profile_edit", label: "Разрешить редактирование профиля", type: "checkbox" }, { k: "allow_inventory_actions", label: "Разрешить действия с предметами", type: "checkbox" }, { k: "allow_skill_actions", label: "Разрешить действия с навыками", type: "checkbox" },
    { k: "transfer_enabled", label: "Сервис передачи", type: "checkbox" }, { k: "pavilion_enabled", label: "Торговый павильон", type: "checkbox" }, { k: "promo_enabled", label: "Промокоды", type: "checkbox" }, { k: "show_fines", label: "Показывать штрафы", type: "checkbox" }, { k: "show_achievements", label: "Показывать достижения", type: "checkbox" }, { k: "show_activity", label: "Показывать активность", type: "checkbox" }, { k: "show_ratings", label: "Показывать личные места", type: "checkbox" }, { k: "allow_transfer", label: "Разрешить передачу", type: "checkbox" }, { k: "allow_item_drop", label: "Разрешить выбрасывание", type: "checkbox" }, { k: "allow_item_use", label: "Разрешить использование", type: "checkbox" }, { k: "allow_equip", label: "Разрешить экипировку", type: "checkbox" }, { k: "allow_craft_actions", label: "Разрешить ремонт/улучшение/разбор", type: "checkbox" },
    { k: "readonly_text", label: "Текст read-only режима", type: "textarea" }, { k: "loading_text", label: "Текст загрузки", type: "textarea" }, { k: "token_error_text", label: "Текст ошибки токена", type: "textarea" }, { k: "expired_token_text", label: "Текст истёкшего токена", type: "textarea" }, { k: "unavailable_text", label: "Текст недоступного профиля", type: "textarea" }, { k: "empty_inventory_text", label: "Текст пустого инвентаря", type: "textarea" }, { k: "empty_skills_text", label: "Текст пустых навыков", type: "textarea" }, { k: "no_fines_text", label: "Текст отсутствия штрафов", type: "textarea" }, { k: "no_services_text", label: "Текст отсутствия сервисов", type: "textarea" }, { k: "technical_error_text", label: "Текст технической ошибки", type: "textarea" },
  ],
  profile_tab: [
    { k: "label", label: "Название вкладки", type: "text" },
    { k: "tab_key", label: "Ключ (латиница)", type: "text" },
    { k: "icon", label: "Иконка/эмодзи", type: "text" },
    { k: "order", label: "Порядок", type: "number" },
    { k: "visibility", label: "Видимость", type: "meta", metaKey: "visibilities", labelMap: PROFILE_VISIBILITY },
    { k: "condition", label: "Условие показа", type: "text" },
    { k: "default_tab", label: "Вкладка по умолчанию", type: "checkbox" },
    { k: "show_pc", label: "Показывать на ПК", type: "checkbox" },
    { k: "show_mobile", label: "Показывать на телефоне", type: "checkbox" },
    { k: "show_player", label: "Показывать игроку", type: "checkbox" }, { k: "show_admin", label: "Показывать админу", type: "checkbox" }, { k: "hide_player", label: "Скрыть от игрока", type: "checkbox" }, { k: "empty_text", label: "Текст пустой вкладки", type: "textarea" },
  ],
  profile_block: [
    { k: "name", label: "Название блока", type: "text" },
    { k: "block_type", label: "Тип блока", type: "meta", metaKey: "blockTypes", labelMap: PROFILE_BLOCK_TYPE },
    { k: "tab", label: "Вкладка (ключ)", type: "text" },
    { k: "order", label: "Порядок", type: "number" },
    { k: "width", label: "Ширина", type: "meta", metaKey: "blockWidths", labelMap: PROFILE_BLOCK_WIDTH },
    { k: "visibility", label: "Видимость", type: "meta", metaKey: "visibilities", labelMap: PROFILE_VISIBILITY },
    { k: "condition", label: "Условие показа", type: "text" },
    { k: "hint", label: "Подсказка", type: "text" },
    { k: "show_pc", label: "Показывать на ПК", type: "checkbox" },
    { k: "show_mobile", label: "Показывать на телефоне", type: "checkbox" },
    { k: "show_player", label: "Показывать игроку", type: "checkbox" }, { k: "show_admin", label: "Показывать админу", type: "checkbox" }, { k: "hide_player", label: "Скрыть от игрока", type: "checkbox" }, { k: "empty_text", label: "Текст пустого блока", type: "textarea" },
  ],
  profile_theme: [
    { k: "title", label: "Название оформления", type: "text" },
    { k: "profile_background", label: "Фон профиля", type: "image" },
    { k: "tab_background", label: "Фон вкладок", type: "image" },
    { k: "card_background", label: "Фон карточек", type: "image" },
    { k: "button_color", label: "Цвет кнопок", type: "text" },
    { k: "text_color", label: "Цвет текста", type: "text" },
    { k: "border_color", label: "Цвет рамок", type: "text" },
    { k: "active_tab_color", label: "Цвет активной вкладки", type: "text" },
    { k: "icon_style", label: "Стиль иконок", type: "text" },
    { k: "card_style", label: "Стиль карточек", type: "text" },
    { k: "modal_style", label: "Стиль модальных окон", type: "text" },
    { k: "primary_color", label: "Основной цвет", type: "text" }, { k: "secondary_color", label: "Вторичный цвет", type: "text" }, { k: "background_color", label: "Цвет фона", type: "text" }, { k: "positive_color", label: "Положительные значения", type: "text" }, { k: "negative_color", label: "Отрицательные значения", type: "text" }, { k: "warning_color", label: "Предупреждения", type: "text" }, { k: "danger_color", label: "Опасная зона", type: "text" }, { k: "border_style", label: "Стиль рамок", type: "text" }, { k: "border_radius", label: "Скругление блоков", type: "number" }, { k: "icon_size", label: "Размер иконок", type: "number" }, { k: "item_image_size", label: "Размер изображений предметов", type: "number" }, { k: "compact_mode", label: "Компактный режим", type: "checkbox" }, { k: "detailed_mode", label: "Подробный режим", type: "checkbox" },
  ],
};

function Field({ label, children }) {
  return <label className="ntv2-field"><span>{label}</span>{children}</label>;
}

function LayoutForm({ schema, value, onChange, meta, disabled, uploadKey }) {
  const set = (k, v) => onChange({ ...value, [k]: v });
  return (
    <div className="ntv2-world-form">
      {schema.map((f) => {
        if (f.type === "image") return <ImageUploadField key={f.k} label={f.label} value={value[f.k] || ""} category="profile" uploadKey={`${uploadKey || "new"}_${f.k}`} disabled={disabled} onChange={(v) => set(f.k, v)} />;
        if (f.type === "checkbox") return <label className="ntv2-check" key={f.k}><input type="checkbox" checked={Boolean(value[f.k])} disabled={disabled} onChange={(e) => set(f.k, e.target.checked)} /> {f.label}</label>;
        if (f.type === "number") return <Field label={f.label} key={f.k}><input type="number" value={value[f.k] ?? ""} disabled={disabled} onChange={(e) => set(f.k, e.target.value)} /></Field>;
        if (f.type === "textarea") return <Field label={f.label} key={f.k}><textarea rows={3} value={value[f.k] || ""} disabled={disabled} onChange={(e) => set(f.k, e.target.value)} /></Field>;
        if (f.type === "options") return <Field label={f.label} key={f.k}><select value={value[f.k] || ""} disabled={disabled} onChange={(e) => set(f.k, e.target.value)}>{f.options.map(([v, label]) => <option key={v} value={v}>{label}</option>)}</select></Field>;
        if (f.type === "meta") {
          const options = (meta && meta[f.metaKey]) || [];
          return <Field label={f.label} key={f.k}><select value={value[f.k] ?? ""} disabled={disabled} onChange={(e) => set(f.k, e.target.value)}><option value="">—</option>{options.map((o) => <option key={o} value={o}>{tr(f.labelMap, o)}</option>)}</select></Field>;
        }
        return <Field label={f.label} key={f.k}><EmojiInput value={value[f.k] || ""} disabled={disabled} onChange={(v) => set(f.k, v)} /></Field>;
      })}
    </div>
  );
}

// Предпросмотр раскладки (§3.7): вкладки по порядку + их блоки.
function LayoutPreview({ guarded }) {
  const [tabs, setTabs] = useState([]);
  const [blocks, setBlocks] = useState([]);
  useEffect(() => {
    (async () => {
      const t = await guarded(() => fetchLayoutItems("profile_tab"));
      const b = await guarded(() => fetchLayoutItems("profile_block"));
      if (t) setTabs(t.items || []);
      if (b) setBlocks(b.items || []);
    })();
  }, [guarded]);
  const ord = (x) => Number((x.data || {}).order) || 0;
  const sortedTabs = [...tabs].filter((t) => t.status !== "archive").sort((a, b) => ord(a) - ord(b));
  return (
    <div className="ntv2-panel">
      <h4 className="ntv2-subhead">Предпросмотр раскладки</h4>
      {!sortedTabs.length ? <p className="ntv2-hint">Вкладок пока нет.</p> : null}
      {sortedTabs.map((t) => {
        const key = (t.data || {}).tab_key || t.id;
        const tabBlocks = blocks.filter((b) => ((b.data || {}).tab || "") === key && b.status !== "archive").sort((a, b) => ord(a) - ord(b));
        return (
          <div key={t.id} className="ntv2-list-row" style={{ flexDirection: "column", alignItems: "stretch", gap: 4 }}>
            <div><b>{(t.data || {}).icon || "📑"} {(t.data || {}).label || t.id}</b> <span className="ntv2-mono">{key}</span> {t.status !== "published" ? <span className="ntv2-hint">({t.status})</span> : null}</div>
            <div style={{ paddingLeft: 14 }}>
              {tabBlocks.length ? tabBlocks.map((b) => <div key={b.id} className="ntv2-hint">• {tr(PROFILE_BLOCK_TYPE, (b.data || {}).block_type)} — {(b.data || {}).name || b.id}</div>) : <span className="ntv2-hint">— нет блоков</span>}
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function ProfileLayoutSection({ guarded, hasPerm }) {
  const [meta, setMeta] = useState(null);
  const [kind, setKind] = useState("profile_settings");
  const [list, setList] = useState([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [editing, setEditing] = useState(null);
  const [confirm, setConfirm] = useState(null);
  const [showPreview, setShowPreview] = useState(false);
  const [usedBy, setUsedBy] = useState(null);
  const [query, setQuery] = useState("");

  const can = useMemo(() => ({
    edit: hasPerm("profile_layout.edit"), publish: hasPerm("profile_layout.publish"),
  }), [hasPerm]);

  const load = useCallback(async () => { const p = await guarded(() => fetchLayoutItems(kind, statusFilter)); if (p) setList(p.items || []); }, [guarded, kind, statusFilter]);
  useEffect(() => { (async () => { const m = await guarded(() => fetchLayoutMeta()); if (m) setMeta(m); })(); }, [guarded]);
  useEffect(() => { load(); }, [load]);

  const statuses = meta?.statuses || [];
  const statusLabel = (v) => statuses.find((s) => s.value === v)?.label || v;
  const itemTitle = (item) => { const d = item.data || {}; return d.label || d.name || d.title || item.id; };

  function switchKind(k) { setKind(k); setEditing(null); setStatusFilter(""); setUsedBy(null); }
  function startCreate() { setEditing({ id: "", data: { ...(EMPTY_BY_KIND[kind] || {}) }, status: "draft", validation: null, isNew: true }); setUsedBy(null); }
  async function openItem(id) {
    setUsedBy(null);
    const p = await guarded(() => fetchLayoutItem(kind, id));
    if (p?.item) setEditing({ id, data: { ...(EMPTY_BY_KIND[kind] || {}), ...(p.item.data || {}) }, status: p.item.status, validation: p.validation, isNew: false });
  }
  async function loadWhereUsed() { const p = await guarded(() => fetchLayoutWhereUsed(kind, editing.id)); if (p) setUsedBy(p.usedBy || []); }
  async function save() {
    const e = editing;
    if (e.isNew) { const p = await guarded(() => createLayoutItem(kind, e.id.trim(), e.data, ""), "Создано."); if (p?.item) await openItem(e.id.trim()); }
    else { await guarded(() => updateLayoutItem(kind, e.id, e.data, "правка"), "Сохранено."); await openItem(e.id); }
    await load();
  }
  async function runValidate() { const p = await guarded(() => validateLayoutItem(kind, editing.id, ""), "Проверка выполнена."); if (p?.validation) setEditing((c) => ({ ...c, validation: p.validation })); }
  async function refreshEditing() { await load(); if (editing) await openItem(editing.id); }

  if (!meta) return <section className="ntv2-section"><h2>Раскладка профиля</h2><p className="ntv2-hint">Загрузка…</p></section>;

  if (editing) {
    const disabled = !can.edit;
    const v = editing.validation;
    return (
      <section className="ntv2-section">
        <div className="ntv2-card-head">
          <button type="button" className="ntv2-btn" onClick={() => setEditing(null)}>← К списку</button>
          <h2>{editing.isNew ? KIND_NEW[kind] : itemTitle({ data: editing.data, id: editing.id })}</h2>
          {!editing.isNew ? <span className={`ntv2-badge ${STATUS_TONE[editing.status] || ""}`}>{statusLabel(editing.status)}</span> : null}
        </div>
        {editing.isNew ? <Field label="ID (латиница)"><input value={editing.id} onChange={(e) => setEditing({ ...editing, id: e.target.value })} /></Field> : <p className="ntv2-hint ntv2-mono">{editing.id}</p>}

        <LayoutForm schema={SCHEMA_BY_KIND[kind]} value={editing.data} onChange={(data) => setEditing({ ...editing, data })} meta={meta} disabled={disabled} uploadKey={editing.id} />

        {v ? (
          <div className={`ntv2-panel ${v.ok ? "" : "ntv2-danger-zone"}`}>
            <h4 className="ntv2-subhead">{v.ok ? "✅ Готово к публикации" : "❌ Проверка не пройдена"}</h4>
            {(v.errors || []).map((e, i) => <div className="ntv2-error" key={"e" + i}>{e}</div>)}
            {(v.warnings || []).map((w, i) => <p className="ntv2-hint" key={"w" + i}>⚠️ {w}</p>)}
          </div>
        ) : null}

        {!editing.isNew && kind === "profile_tab" ? (
          <div className="ntv2-panel">
            <div className="ntv2-card-head" style={{ marginBottom: 6 }}>
              <h4 className="ntv2-subhead" style={{ margin: 0 }}>Где используется</h4>
              <button type="button" className="ntv2-btn" onClick={loadWhereUsed}>Проверить связи</button>
            </div>
            {usedBy === null ? <p className="ntv2-hint">Нажмите «Проверить связи», чтобы увидеть блоки на этой вкладке.</p> : null}
            {usedBy !== null && !usedBy.length ? <p className="ntv2-hint">На вкладке нет блоков — можно безопасно изменить/скрыть.</p> : null}
            {usedBy && usedBy.length ? (
              <div className="ntv2-list">
                {usedBy.map((u) => (
                  <div className="ntv2-list-row" key={u.id}>
                    <b>{u.name}</b><span className="ntv2-mono">{u.id}</span>
                    <span className="ntv2-hint">{(u.fields || []).join(", ")}</span>
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        ) : null}

        <div className="ntv2-form-row" style={{ marginTop: 14 }}>
          {can.edit ? <button type="button" className="ntv2-btn ntv2-btn-primary" disabled={editing.isNew && !editing.id.trim()} onClick={save}>{editing.isNew ? "Создать" : "Сохранить"}</button> : null}
          {!editing.isNew && can.edit ? <button type="button" className="ntv2-btn" onClick={runValidate}>Проверить</button> : null}
          {!editing.isNew && can.publish ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => setConfirm({ title: "Опубликовать?", dangerous: true, confirmLabel: "Опубликовать", body: <p>Объект раскладки будет проверен и опубликован.</p>, run: async (r) => { await guarded(() => layoutLifecycle(kind, editing.id, "publish", r), "Опубликовано."); await refreshEditing(); } })}>Опубликовать</button> : null}
          {!editing.isNew && can.publish && editing.status === "published" ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => setConfirm({ title: "Отключить?", dangerous: true, confirmLabel: "Отключить", body: <p>Объект перестанет применяться.</p>, run: async (r) => { await guarded(() => layoutLifecycle(kind, editing.id, "disable", r), "Отключено."); await refreshEditing(); } })}>Отключить</button> : null}
          {!editing.isNew && can.publish ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => setConfirm({ title: "В архив?", dangerous: true, confirmLabel: "В архив", body: <p>Объект уйдёт в архив.</p>, run: async (r) => { await guarded(() => layoutLifecycle(kind, editing.id, "archive", r), "В архиве."); await refreshEditing(); } })}>В архив</button> : null}
          {!editing.isNew && can.publish ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => setConfirm({ title: "Удалить?", dangerous: true, confirmLabel: "Удалить", body: <p>Полное удаление объекта раскладки.</p>, run: async (r) => { await guarded(() => deleteLayoutItem(kind, editing.id, editing.id, r), "Удалено."); setEditing(null); await load(); } })}>Удалить</button> : null}
        </div>

        {!editing.isNew ? <VersionHistory base={`profile-layout/${kind}`} id={editing.id} canRollback={can.edit && (editing.status !== "published" || can.publish)} onRolledBack={refreshEditing} /> : null}

        <ConfirmModal open={Boolean(confirm)} title={confirm?.title} body={confirm?.body} dangerous={confirm?.dangerous} confirmLabel={confirm?.confirmLabel} requireReason
          onConfirm={async (r) => { await confirm.run(r); setConfirm(null); }} onCancel={() => setConfirm(null)} />
      </section>
    );
  }

  return (
    <section className="ntv2-section">
      <h2>Профиль игрока</h2>
      <p className="ntv2-hint">Вкладки, блоки и оформление профиля игрока. Вкладка «Обзор» не используется — её данные распределяются по другим вкладкам.</p>
      <div className="ntv2-subnav">
        {meta.kinds.map((k) => <button key={k} type="button" className={`ntv2-subnav-item${k === kind ? " active" : ""}`} onClick={() => switchKind(k)}>{KIND_LABELS[k] || tr(PROFILE_LAYOUT_KIND, k)}</button>)}
      </div>
      <div className="ntv2-filters">
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="">Все статусы</option>
          {statuses.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
        </select>
        {can.edit ? <button type="button" className="ntv2-btn ntv2-btn-primary" onClick={startCreate}>{KIND_NEW[kind]}</button> : null}
        <button type="button" className="ntv2-btn" onClick={() => setShowPreview((s) => !s)}>{showPreview ? "Скрыть предпросмотр" : "Предпросмотр раскладки"}</button>
        <SearchBox value={query} onChange={setQuery} />
      </div>
      {showPreview ? <LayoutPreview guarded={guarded} /> : null}
      {!list.length ? <p className="ntv2-hint">Объектов нет.</p> : null}
      <NoResults items={list} query={query} />
      <div className="ntv2-list">
        {filterEntities(list, query).map((item) => (
          <button key={item.id} type="button" className="ntv2-list-row ntv2-player-row" onClick={() => openItem(item.id)}>
            <b>{itemTitle(item)}</b>
            <span className="ntv2-mono">{item.id}</span>
            <span className={`ntv2-badge ${STATUS_TONE[item.status] || ""}`}>{statusLabel(item.status)}</span>
            {kind === "profile_block" && item.data?.block_type ? <span className="ntv2-hint">{tr(PROFILE_BLOCK_TYPE, item.data.block_type)}</span> : null}
          </button>
        ))}
      </div>
    </section>
  );
}
