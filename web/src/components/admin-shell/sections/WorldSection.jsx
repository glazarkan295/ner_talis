import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  archiveWorldItem,
  createWorldItem,
  disableWorldItem,
  fetchWorldItems,
  fetchWorldMeta,
  publishWorldItem,
  updateWorldItem,
  validateWorldItem,
} from "../../../api/adminWorldApi.js";
import { loadCatalog } from "../../../api/adminApi.js";
import { ConfirmModal } from "../ConfirmModal.jsx";

const KIND_LABELS = { location: "🗺️ Локации", mob: "⚔️ Мобы", button: "🔘 Кнопки", transition: "🔀 Переходы" };
const KIND_NEW_LABEL = { location: "＋ Новая локация", mob: "＋ Новый моб", button: "＋ Новая кнопка", transition: "＋ Новый переход" };

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

const EMPTY_MOB = {
  name: "", type: "beast", description: "", image: "",
  min_level: 1, max_level: 5, hp: 100,
  phys_damage: 0, mag_damage: 0, accuracy: 0, evasion: 0,
  phys_defense: 0, mag_defense: 0, crit_chance: 0, crit_damage: 0,
  experience: 0, coins: 0, spawn_chance: 100, can_be_enhanced: false,
  locations: "", drop: [],
};

const EMPTY_BUTTON = {
  text: "", owner_location: "", action: "goto_location", target: "",
  show_condition: "", order: 1, uses_energy: false, starts_timer: false,
  starts_event: false, starts_battle: false, show_telegram: true, show_vk: true,
};

const EMPTY_TRANSITION = {
  name: "", from_location: "", to_location: "", access_condition: "always",
  cost: 0, required_item: "", required_quest: "", requires_energy: false,
  allowed_with_fine: false, allowed_in_battle: false, allowed_during_timer: false,
};

const EMPTY_BY_KIND = { location: EMPTY_LOCATION, mob: EMPTY_MOB, button: EMPTY_BUTTON, transition: EMPTY_TRANSITION };

function itemTitle(kind, item) {
  const d = item.data || {};
  if (kind === "transition") return d.name || `${d.from_location || "?"} → ${d.to_location || "?"}`;
  if (kind === "button") return d.text || item.id;
  return d.name || item.id;
}

function Field({ label, children }) {
  return <label className="ntv2-field"><span>{label}</span>{children}</label>;
}

function LocationSelect({ value, onChange, options, disabled }) {
  return (
    <select value={value || ""} disabled={disabled} onChange={(e) => onChange(e.target.value)}>
      <option value="">— выберите локацию —</option>
      {options.map((o) => <option key={o.id} value={o.id}>{o.name} ({o.id})</option>)}
    </select>
  );
}

function LocationForm({ value, onChange, meta, disabled }) {
  const set = (k, v) => onChange({ ...value, [k]: v });
  const flag = (key, label) => (
    <label className="ntv2-check" key={key}>
      <input type="checkbox" checked={Boolean(value[key])} disabled={disabled} onChange={(e) => set(key, e.target.checked)} /> {label}
    </label>
  );
  return (
    <div className="ntv2-world-form">
      <Field label="Название"><input value={value.name} disabled={disabled} onChange={(e) => set("name", e.target.value)} /></Field>
      <div className="ntv2-form-row">
        <Field label="Тип"><select value={value.type} disabled={disabled} onChange={(e) => set("type", e.target.value)}>{(meta.locationTypes || []).map((t) => <option key={t} value={t}>{t}</option>)}</select></Field>
        <Field label="Опасность"><input value={value.danger} disabled={disabled} onChange={(e) => set("danger", e.target.value)} /></Field>
        <Field label="Мин. уровень"><input type="number" value={value.min_level} disabled={disabled} onChange={(e) => set("min_level", e.target.value)} /></Field>
      </div>
      <div className="ntv2-form-row">
        <Field label="Уровни мобов: от"><input type="number" value={value.mob_level_min} disabled={disabled} onChange={(e) => set("mob_level_min", e.target.value)} /></Field>
        <Field label="до"><input type="number" value={value.mob_level_max} disabled={disabled} onChange={(e) => set("mob_level_max", e.target.value)} /></Field>
      </div>
      <Field label="Краткое описание"><textarea rows={2} value={value.short_description} disabled={disabled} onChange={(e) => set("short_description", e.target.value)} /></Field>
      <Field label="Полное описание"><textarea rows={4} value={value.description} disabled={disabled} onChange={(e) => set("description", e.target.value)} /></Field>
      <Field label="Изображение (URL)"><input value={value.image} disabled={disabled} onChange={(e) => set("image", e.target.value)} /></Field>
      <div className="ntv2-form-row" style={{ gap: 14 }}>
        {flag("can_search", "Поиск")}{flag("can_camp", "Лагерь")}{flag("can_fish", "Рыбалка")}
        {flag("can_teleport", "Телепорт")}{flag("city_functions", "Городские функции")}{flag("safe", "Безопасная")}
      </div>
    </div>
  );
}

function DropEditor({ rows, onChange, disabled }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);

  useEffect(() => {
    if (!query.trim()) { setResults([]); return undefined; }
    const id = window.setTimeout(async () => {
      try { const c = await loadCatalog("", query, ""); setResults((c.items || []).slice(0, 8)); } catch { setResults([]); }
    }, 250);
    return () => window.clearTimeout(id);
  }, [query]);

  const list = Array.isArray(rows) ? rows : [];
  const setRow = (i, patch) => onChange(list.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));
  const addRow = (item_id = "") => onChange([...list, { item_id, chance: 10, min_count: 1, max_count: 1, only_enhanced: false, only_event: false }]);
  const removeRow = (i) => onChange(list.filter((_, idx) => idx !== i));

  return (
    <div className="ntv2-panel">
      <h4 className="ntv2-subhead">Дроп ({list.length})</h4>
      {!disabled ? (
        <div className="ntv2-filters">
          <input placeholder="Найти предмет в каталоге" value={query} onChange={(e) => setQuery(e.target.value)} />
          <button type="button" className="ntv2-btn" onClick={() => addRow("")}>＋ Пустая строка</button>
        </div>
      ) : null}
      {results.length ? (
        <div className="ntv2-catalog-grid">
          {results.map((item) => (
            <button type="button" key={item.item_id || item.id} className="ntv2-catalog-card" onClick={() => { addRow(item.item_id || item.id); setQuery(""); }}>
              {item.icon ? <img src={item.icon} alt="" /> : null}<span>{item.name}</span>
            </button>
          ))}
        </div>
      ) : null}
      <div className="ntv2-list">
        {list.map((row, i) => (
          <div className="ntv2-list-row ntv2-drop-row" key={i}>
            <input className="ntv2-mono" style={{ flex: 2 }} placeholder="item_id" value={row.item_id} disabled={disabled} onChange={(e) => setRow(i, { item_id: e.target.value })} />
            <input type="number" title="шанс %" style={{ width: 80 }} value={row.chance} disabled={disabled} onChange={(e) => setRow(i, { chance: e.target.value })} />
            <input type="number" title="мин" style={{ width: 70 }} value={row.min_count} disabled={disabled} onChange={(e) => setRow(i, { min_count: e.target.value })} />
            <input type="number" title="макс" style={{ width: 70 }} value={row.max_count} disabled={disabled} onChange={(e) => setRow(i, { max_count: e.target.value })} />
            <label className="ntv2-check"><input type="checkbox" checked={Boolean(row.only_enhanced)} disabled={disabled} onChange={(e) => setRow(i, { only_enhanced: e.target.checked })} /> усил.</label>
            <label className="ntv2-check"><input type="checkbox" checked={Boolean(row.only_event)} disabled={disabled} onChange={(e) => setRow(i, { only_event: e.target.checked })} /> событие</label>
            {!disabled ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => removeRow(i)}>×</button> : null}
          </div>
        ))}
        {!list.length ? <p className="ntv2-hint">Дроп пуст. Добавьте строки или найдите предмет в каталоге.</p> : null}
      </div>
    </div>
  );
}

function MobForm({ value, onChange, meta, disabled }) {
  const set = (k, v) => onChange({ ...value, [k]: v });
  const num = (key, label) => <Field label={label} key={key}><input type="number" value={value[key]} disabled={disabled} onChange={(e) => set(key, e.target.value)} /></Field>;
  return (
    <div className="ntv2-world-form">
      <div className="ntv2-form-row">
        <Field label="Название"><input value={value.name} disabled={disabled} onChange={(e) => set("name", e.target.value)} /></Field>
        <Field label="Тип"><select value={value.type} disabled={disabled} onChange={(e) => set("type", e.target.value)}>{(meta.mobTypes || []).map((t) => <option key={t} value={t}>{t}</option>)}</select></Field>
      </div>
      <div className="ntv2-form-row">{num("min_level", "Ур. от")}{num("max_level", "Ур. до")}{num("hp", "HP")}{num("spawn_chance", "Шанс появления %")}</div>
      <div className="ntv2-form-row">{num("phys_damage", "Физ. урон")}{num("mag_damage", "Маг. урон")}{num("accuracy", "Точность")}{num("evasion", "Уклонение")}</div>
      <div className="ntv2-form-row">{num("phys_defense", "Физ. защита")}{num("mag_defense", "Маг. защита")}{num("crit_chance", "Крит %")}{num("crit_damage", "Крит урон")}</div>
      <div className="ntv2-form-row">{num("experience", "Опыт")}{num("coins", "Монеты")}
        <label className="ntv2-check"><input type="checkbox" checked={Boolean(value.can_be_enhanced)} disabled={disabled} onChange={(e) => set("can_be_enhanced", e.target.checked)} /> Может быть усиленным</label>
      </div>
      <Field label="Локации появления (id через запятую)"><input value={value.locations} disabled={disabled} onChange={(e) => set("locations", e.target.value)} /></Field>
      <Field label="Описание"><textarea rows={3} value={value.description} disabled={disabled} onChange={(e) => set("description", e.target.value)} /></Field>
      <Field label="Изображение (URL)"><input value={value.image} disabled={disabled} onChange={(e) => set("image", e.target.value)} /></Field>
      <DropEditor rows={value.drop} onChange={(drop) => set("drop", drop)} disabled={disabled} />
    </div>
  );
}

function ButtonForm({ value, onChange, meta, disabled, locationOptions }) {
  const set = (k, v) => onChange({ ...value, [k]: v });
  const flag = (key, label) => (
    <label className="ntv2-check" key={key}>
      <input type="checkbox" checked={Boolean(value[key])} disabled={disabled} onChange={(e) => set(key, e.target.checked)} /> {label}
    </label>
  );
  return (
    <div className="ntv2-world-form">
      <Field label="Текст кнопки"><input value={value.text} disabled={disabled} onChange={(e) => set("text", e.target.value)} /></Field>
      <div className="ntv2-form-row">
        <Field label="Локация-владелец"><LocationSelect value={value.owner_location} onChange={(v) => set("owner_location", v)} options={locationOptions} disabled={disabled} /></Field>
        <Field label="Действие"><select value={value.action} disabled={disabled} onChange={(e) => set("action", e.target.value)}>{(meta.buttonActions || []).map((a) => <option key={a} value={a}>{a}</option>)}</select></Field>
        <Field label="Порядок"><input type="number" value={value.order} disabled={disabled} onChange={(e) => set("order", e.target.value)} /></Field>
      </div>
      {value.action === "goto_location" ? (
        <Field label="Куда ведёт"><LocationSelect value={value.target} onChange={(v) => set("target", v)} options={locationOptions} disabled={disabled} /></Field>
      ) : null}
      <Field label="Условие показа"><input value={value.show_condition} disabled={disabled} onChange={(e) => set("show_condition", e.target.value)} /></Field>
      <div className="ntv2-form-row" style={{ gap: 14 }}>
        {flag("uses_energy", "Тратит энергию")}{flag("starts_timer", "Запускает таймер")}{flag("starts_event", "Запускает событие")}{flag("starts_battle", "Запускает бой")}
        {flag("show_telegram", "Telegram")}{flag("show_vk", "VK")}
      </div>
    </div>
  );
}

function TransitionForm({ value, onChange, meta, disabled, locationOptions }) {
  const set = (k, v) => onChange({ ...value, [k]: v });
  const flag = (key, label) => (
    <label className="ntv2-check" key={key}>
      <input type="checkbox" checked={Boolean(value[key])} disabled={disabled} onChange={(e) => set(key, e.target.checked)} /> {label}
    </label>
  );
  return (
    <div className="ntv2-world-form">
      <Field label="Название перехода"><input value={value.name} disabled={disabled} onChange={(e) => set("name", e.target.value)} /></Field>
      <div className="ntv2-form-row">
        <Field label="Из локации"><LocationSelect value={value.from_location} onChange={(v) => set("from_location", v)} options={locationOptions} disabled={disabled} /></Field>
        <Field label="В локацию"><LocationSelect value={value.to_location} onChange={(v) => set("to_location", v)} options={locationOptions} disabled={disabled} /></Field>
      </div>
      <div className="ntv2-form-row">
        <Field label="Условие доступа"><select value={value.access_condition} disabled={disabled} onChange={(e) => set("access_condition", e.target.value)}>{(meta.accessConditions || []).map((c) => <option key={c} value={c}>{c}</option>)}</select></Field>
        <Field label="Стоимость"><input type="number" value={value.cost} disabled={disabled} onChange={(e) => set("cost", e.target.value)} /></Field>
      </div>
      <div className="ntv2-form-row">
        <Field label="Требуется предмет (item_id)"><input value={value.required_item} disabled={disabled} onChange={(e) => set("required_item", e.target.value)} /></Field>
        <Field label="Требуется квест (id)"><input value={value.required_quest} disabled={disabled} onChange={(e) => set("required_quest", e.target.value)} /></Field>
      </div>
      <div className="ntv2-form-row" style={{ gap: 14 }}>
        {flag("requires_energy", "Требует энергию")}{flag("allowed_with_fine", "Доступен при штрафе")}{flag("allowed_in_battle", "Доступен в бою")}{flag("allowed_during_timer", "Доступен при таймере")}
      </div>
    </div>
  );
}

const FORM_BY_KIND = { location: LocationForm, mob: MobForm, button: ButtonForm, transition: TransitionForm };

export function WorldSection({ guarded, hasPerm }) {
  const [meta, setMeta] = useState(null);
  const [kind, setKind] = useState("location");
  const [items, setItems] = useState([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [editing, setEditing] = useState(null);
  const [confirm, setConfirm] = useState(null);
  const [locationOptions, setLocationOptions] = useState([]);

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

  const loadLocationOptions = useCallback(async () => {
    const payload = await guarded(() => fetchWorldItems("location"));
    if (payload) setLocationOptions((payload.items || []).map((i) => ({ id: i.id, name: i.data?.name || i.id })));
  }, [guarded]);

  useEffect(() => { (async () => { const m = await guarded(() => fetchWorldMeta()); if (m) setMeta(m); })(); }, [guarded]);
  useEffect(() => { loadList(); }, [loadList]);
  // Кнопки/переходы ссылаются на локации — держим актуальный список для пикеров.
  useEffect(() => { if (kind === "button" || kind === "transition") loadLocationOptions(); }, [kind, loadLocationOptions]);

  const statuses = meta?.statuses || [];
  const Form = FORM_BY_KIND[kind] || LocationForm;

  function switchKind(k) { setKind(k); setEditing(null); setStatusFilter(""); }
  function startCreate() { setEditing({ id: "", data: { ...(EMPTY_BY_KIND[kind] || {}) }, status: "draft", validation: null, isNew: true }); }
  function openItem(item) { setEditing({ id: item.id, data: { ...(EMPTY_BY_KIND[kind] || {}), ...(item.data || {}) }, status: item.status, validation: item.validation, isNew: false }); }

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
    const payload = await guarded(() => fetchWorldItems(kind, statusFilter));
    if (payload) setItems(payload.items || []);
    const fresh = (payload?.items || []).find((i) => i.id === editing.id);
    if (fresh) setEditing((cur) => ({ ...cur, status: fresh.status }));
  }

  if (!meta) return <section className="ntv2-section"><h2>Конструктор мира</h2><p className="ntv2-hint">Загрузка…</p></section>;

  if (editing) {
    const v = editing.validation;
    return (
      <section className="ntv2-section">
        <div className="ntv2-card-head">
          <button type="button" className="ntv2-btn" onClick={() => setEditing(null)}>← К списку</button>
          <h2>{editing.isNew ? KIND_NEW_LABEL[kind] : itemTitle(kind, { data: editing.data, id: editing.id })}</h2>
          {!editing.isNew ? <span className={`ntv2-badge ${STATUS_TONE[editing.status] || ""}`}>{statusLabel(statuses, editing.status)}</span> : null}
        </div>

        {editing.isNew ? (
          <Field label="ID (латиница, напр. small_plateau)"><input value={editing.id} onChange={(e) => setEditing({ ...editing, id: e.target.value })} /></Field>
        ) : <p className="ntv2-hint ntv2-mono">{editing.id}</p>}

        <Form value={editing.data} onChange={(data) => setEditing({ ...editing, data })} meta={meta} locationOptions={locationOptions} disabled={!(editing.isNew ? can.create : can.edit)} />

        {v ? (
          <div className={`ntv2-panel ${v.ok ? "" : "ntv2-danger-zone"}`}>
            <h4 className="ntv2-subhead">{v.ok ? "✅ Проверка пройдена" : "❌ Проверка не пройдена"}</h4>
            {(v.errors || []).map((e, i) => <div className="ntv2-error" key={"e" + i}>{e}</div>)}
            {(v.warnings || []).map((w, i) => <p className="ntv2-hint" key={"w" + i}>⚠️ {w}</p>)}
          </div>
        ) : null}

        <div className="ntv2-form-row" style={{ marginTop: 14 }}>
          {(editing.isNew ? can.create : can.edit) ? (
            <button type="button" className="ntv2-btn ntv2-btn-primary" disabled={editing.isNew && !editing.id.trim()} onClick={save}>{editing.isNew ? "Создать черновик" : "Сохранить"}</button>
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
          open={Boolean(confirm)} title={confirm?.title} body={confirm?.body}
          dangerous={confirm?.dangerous} confirmLabel={confirm?.confirmLabel} requireReason
          onConfirm={async (reason) => { await confirm.run(reason); setConfirm(null); }}
          onCancel={() => setConfirm(null)}
        />
      </section>
    );
  }

  return (
    <section className="ntv2-section">
      <h2>Конструктор мира</h2>
      <div className="ntv2-subnav">
        {meta.kinds.map((k) => (
          <button key={k} type="button" className={`ntv2-subnav-item${k === kind ? " active" : ""}`} onClick={() => switchKind(k)}>{KIND_LABELS[k] || k}</button>
        ))}
      </div>
      <div className="ntv2-filters">
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="">Все статусы</option>
          {statuses.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
        </select>
        {can.create ? <button type="button" className="ntv2-btn ntv2-btn-primary" onClick={startCreate}>{KIND_NEW_LABEL[kind]}</button> : null}
      </div>
      {!items.length ? <p className="ntv2-hint">Пока нет объектов. {can.create ? "Создайте первый черновик." : ""}</p> : null}
      <div className="ntv2-list">
        {items.map((item) => (
          <button key={item.id} type="button" className="ntv2-list-row ntv2-player-row" onClick={() => openItem(item)}>
            <b>{itemTitle(kind, item)}</b>
            <span className="ntv2-mono">{item.id}</span>
            <span className={`ntv2-badge ${STATUS_TONE[item.status] || ""}`}>{statusLabel(statuses, item.status)}</span>
            {item.data?.type || item.data?.action ? <span className="ntv2-hint">{item.data.type || item.data.action}</span> : null}
          </button>
        ))}
      </div>
    </section>
  );
}
