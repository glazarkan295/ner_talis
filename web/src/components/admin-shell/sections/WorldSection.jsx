import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  archiveWorldItem,
  createWorldItem,
  disableWorldItem,
  fetchWorldItems,
  fetchWorldMeta,
  publishWorldItem,
  setWorldStatus,
  updateWorldItem,
  validateWorldItem,
} from "../../../api/adminWorldApi.js";
import { ConfirmModal } from "../ConfirmModal.jsx";
import { TechnicalData } from "../TechnicalData.jsx";

const KIND_LABELS = { location: "🗺️ Локации" };

const STATUS_TONE = {
  published: "ntv2-badge-owner",
  error: "ntv2-badge-error",
  disabled: "ntv2-badge-danger",
};

function statusLabel(statuses, value) {
  return statuses.find((s) => s.value === value)?.label || value;
}

const EMPTY_LOCATION = {
  name: "", type: "wild", danger: "", short_description: "", description: "",
  image: "", min_level: 1, mob_level_min: "", mob_level_max: "",
  can_search: false, can_camp: false, can_fish: false, can_teleport: false,
  city_functions: false, safe: false,
};

function LocationForm({ value, onChange, locationTypes, disabled }) {
  function set(key, v) { onChange({ ...value, [key]: v }); }
  const flag = (key, label) => (
    <label className="ntv2-check" key={key}>
      <input type="checkbox" checked={Boolean(value[key])} disabled={disabled} onChange={(e) => set(key, e.target.checked)} /> {label}
    </label>
  );
  return (
    <div className="ntv2-world-form">
      <label className="ntv2-field"><span>Название</span>
        <input value={value.name} disabled={disabled} onChange={(e) => set("name", e.target.value)} /></label>
      <div className="ntv2-form-row">
        <label className="ntv2-field"><span>Тип</span>
          <select value={value.type} disabled={disabled} onChange={(e) => set("type", e.target.value)}>
            {locationTypes.map((t) => <option key={t} value={t}>{t}</option>)}
          </select></label>
        <label className="ntv2-field"><span>Опасность</span>
          <input value={value.danger} disabled={disabled} onChange={(e) => set("danger", e.target.value)} /></label>
        <label className="ntv2-field"><span>Мин. уровень</span>
          <input type="number" value={value.min_level} disabled={disabled} onChange={(e) => set("min_level", e.target.value)} /></label>
      </div>
      <div className="ntv2-form-row">
        <label className="ntv2-field"><span>Уровни мобов: от</span>
          <input type="number" value={value.mob_level_min} disabled={disabled} onChange={(e) => set("mob_level_min", e.target.value)} /></label>
        <label className="ntv2-field"><span>до</span>
          <input type="number" value={value.mob_level_max} disabled={disabled} onChange={(e) => set("mob_level_max", e.target.value)} /></label>
      </div>
      <label className="ntv2-field"><span>Краткое описание</span>
        <textarea rows={2} value={value.short_description} disabled={disabled} onChange={(e) => set("short_description", e.target.value)} /></label>
      <label className="ntv2-field"><span>Полное описание</span>
        <textarea rows={4} value={value.description} disabled={disabled} onChange={(e) => set("description", e.target.value)} /></label>
      <label className="ntv2-field"><span>Изображение (URL)</span>
        <input value={value.image} disabled={disabled} onChange={(e) => set("image", e.target.value)} /></label>
      <div className="ntv2-form-row" style={{ gap: 14 }}>
        {flag("can_search", "Поиск")}
        {flag("can_camp", "Лагерь")}
        {flag("can_fish", "Рыбалка")}
        {flag("can_teleport", "Телепорт")}
        {flag("city_functions", "Городские функции")}
        {flag("safe", "Безопасная")}
      </div>
    </div>
  );
}

export function WorldSection({ guarded, hasPerm }) {
  const [meta, setMeta] = useState(null);
  const [kind] = useState("location");
  const [items, setItems] = useState([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [editing, setEditing] = useState(null); // {id, data, status, validation, isNew}
  const [confirm, setConfirm] = useState(null);

  const can = useMemo(() => ({
    create: hasPerm("world.create_draft"),
    edit: hasPerm("world.edit_draft"),
    validate: hasPerm("world.validate"),
    publish: hasPerm("world.publish"),
    disable: hasPerm("world.disable"),
    archive: hasPerm("world.archive"),
  }), [hasPerm]);

  const loadList = useCallback(async () => {
    const payload = await guarded(() => fetchWorldItems(kind, statusFilter));
    if (payload) setItems(payload.items || []);
  }, [guarded, kind, statusFilter]);

  useEffect(() => { (async () => { const m = await guarded(() => fetchWorldMeta()); if (m) setMeta(m); })(); }, [guarded]);
  useEffect(() => { loadList(); }, [loadList]);

  const statuses = meta?.statuses || [];
  const locationTypes = meta?.locationTypes || [];

  function startCreate() {
    setEditing({ id: "", data: { ...EMPTY_LOCATION }, status: "draft", validation: null, isNew: true });
  }
  function openItem(item) {
    setEditing({ id: item.id, data: { ...EMPTY_LOCATION, ...(item.data || {}) }, status: item.status, validation: item.validation, isNew: false });
  }

  async function save() {
    const e = editing;
    if (e.isNew) {
      const payload = await guarded(() => createWorldItem(kind, e.id.trim(), e.data, ""), "Черновик создан.");
      if (payload?.item) setEditing({ ...e, isNew: false, status: payload.item.status, validation: payload.item.validation });
    } else {
      const payload = await guarded(() => updateWorldItem(kind, e.id, e.data, ""), "Сохранено.");
      if (payload?.item) setEditing({ ...e, status: payload.item.status, validation: payload.item.validation });
    }
    await loadList();
  }

  async function runValidate() {
    const payload = await guarded(() => validateWorldItem(kind, editing.id), "Проверка выполнена.");
    if (payload?.validation) setEditing((cur) => ({ ...cur, validation: payload.validation }));
  }

  async function refreshEditing() {
    await loadList();
    const fresh = items.find((i) => i.id === editing.id);
    if (fresh) setEditing((cur) => ({ ...cur, status: fresh.status }));
  }

  if (!meta) return <section className="ntv2-section"><h2>Конструктор мира</h2><p className="ntv2-hint">Загрузка…</p></section>;

  // --- Editor view ---
  if (editing) {
    const v = editing.validation;
    return (
      <section className="ntv2-section">
        <div className="ntv2-card-head">
          <button type="button" className="ntv2-btn" onClick={() => setEditing(null)}>← К списку</button>
          <h2>{editing.isNew ? "Новая локация" : editing.data.name || editing.id}</h2>
          {!editing.isNew ? <span className={`ntv2-badge ${STATUS_TONE[editing.status] || ""}`}>{statusLabel(statuses, editing.status)}</span> : null}
        </div>

        {editing.isNew ? (
          <label className="ntv2-field"><span>ID (латиница, напр. small_plateau)</span>
            <input value={editing.id} onChange={(e) => setEditing({ ...editing, id: e.target.value })} /></label>
        ) : <p className="ntv2-hint ntv2-mono">{editing.id}</p>}

        <LocationForm
          value={editing.data}
          onChange={(data) => setEditing({ ...editing, data })}
          locationTypes={locationTypes}
          disabled={!(editing.isNew ? can.create : can.edit)}
        />

        {v ? (
          <div className={`ntv2-panel ${v.ok ? "" : "ntv2-danger-zone"}`}>
            <h4 className="ntv2-subhead">{v.ok ? "✅ Проверка пройдена" : "❌ Проверка не пройдена"}</h4>
            {(v.errors || []).map((e, i) => <div className="ntv2-error" key={"e" + i}>{e}</div>)}
            {(v.warnings || []).map((w, i) => <p className="ntv2-hint" key={"w" + i}>⚠️ {w}</p>)}
          </div>
        ) : null}

        <div className="ntv2-form-row" style={{ marginTop: 14 }}>
          {(editing.isNew ? can.create : can.edit) ? (
            <button type="button" className="ntv2-btn ntv2-btn-primary" disabled={editing.isNew && !editing.id.trim()} onClick={save}>
              {editing.isNew ? "Создать черновик" : "Сохранить"}
            </button>
          ) : null}
          {!editing.isNew && can.validate ? <button type="button" className="ntv2-btn" onClick={runValidate}>Проверить</button> : null}
          {!editing.isNew && can.publish ? (
            <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => setConfirm({
              title: "Опубликовать в игру?", dangerous: true, confirmLabel: "Опубликовать",
              body: <p>Объект будет проверен и опубликован — игроки увидят его в игре.</p>,
              run: async (reason) => { await guarded(() => publishWorldItem(kind, editing.id, reason), "Опубликовано."); await refreshEditing(); },
            })}>Опубликовать</button>
          ) : null}
          {!editing.isNew && can.disable && editing.status === "published" ? (
            <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => setConfirm({
              title: "Отключить контент?", dangerous: true, confirmLabel: "Отключить",
              body: <p>Объект перестанет действовать в игре, но останется в реестре.</p>,
              run: async (reason) => { await guarded(() => disableWorldItem(kind, editing.id, reason), "Отключено."); await refreshEditing(); },
            })}>Отключить</button>
          ) : null}
          {!editing.isNew && can.archive ? (
            <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => setConfirm({
              title: "В архив?", dangerous: true, confirmLabel: "В архив",
              body: <p>Объект уйдёт в архив — его больше нельзя редактировать.</p>,
              run: async (reason) => { await guarded(() => archiveWorldItem(kind, editing.id, reason), "В архиве."); setEditing(null); await loadList(); },
            })}>В архив</button>
          ) : null}
        </div>

        <ConfirmModal
          open={Boolean(confirm)}
          title={confirm?.title}
          body={confirm?.body}
          dangerous={confirm?.dangerous}
          confirmLabel={confirm?.confirmLabel}
          requireReason
          onConfirm={async (reason) => { await confirm.run(reason); setConfirm(null); }}
          onCancel={() => setConfirm(null)}
        />
      </section>
    );
  }

  // --- List view ---
  return (
    <section className="ntv2-section">
      <h2>Конструктор мира</h2>
      <div className="ntv2-subnav">
        {meta.kinds.map((k) => (
          <span key={k} className={`ntv2-subnav-item${k === kind ? " active" : ""}`}>{KIND_LABELS[k] || k}</span>
        ))}
      </div>
      <div className="ntv2-filters">
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="">Все статусы</option>
          {statuses.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
        </select>
        {can.create ? <button type="button" className="ntv2-btn ntv2-btn-primary" onClick={startCreate}>＋ Новая локация</button> : null}
      </div>
      {!items.length ? <p className="ntv2-hint">Пока нет объектов. {can.create ? "Создайте первый черновик." : ""}</p> : null}
      <div className="ntv2-list">
        {items.map((item) => (
          <button key={item.id} type="button" className="ntv2-list-row ntv2-player-row" onClick={() => openItem(item)}>
            <b>{item.data?.name || item.id}</b>
            <span className="ntv2-mono">{item.id}</span>
            <span className={`ntv2-badge ${STATUS_TONE[item.status] || ""}`}>{statusLabel(statuses, item.status)}</span>
            {item.data?.type ? <span className="ntv2-hint">{item.data.type}</span> : null}
          </button>
        ))}
      </div>
    </section>
  );
}
