import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  archiveWorldItem,
  createWorldItem,
  disableWorldItem,
  fetchWorldItems,
  fetchWorldMeta,
  importExistingContent,
  mobTestBattle,
  previewWorldItem,
  publishWorldItem,
  testRunWorldItem,
  updateWorldItem,
  validateWorldItem,
} from "../../../api/adminWorldApi.js";
import { loadCatalog } from "../../../api/adminApi.js";
import { ConfirmModal } from "../ConfirmModal.jsx";
import { TechnicalData } from "../TechnicalData.jsx";

const KIND_LABELS = {
  location: "🗺️ Локации", mob: "⚔️ Мобы", button: "🔘 Кнопки", transition: "🔀 Переходы",
  event: "✨ События", npc: "🧙 NPC", quest: "📜 Квесты", raid: "🐉 Рейды",
  // Под-объекты локаций (расширенный конструктор).
  location_zone: "🌫️ Зоны", location_resource: "🌿 Ресурсы", location_loot: "🎁 Добыча",
  location_mob_spawn: "🐾 Мобы локации", location_weekly_limit: "📊 Недельные лимиты",
  location_weekly_rotation: "🔄 Ротации", location_depletion_rule: "📉 Истощение",
  location_empty_event: "🏜️ Пустая локация", location_hidden_event: "🕵️ Скрытые события",
  location_event_answer: "💬 Варианты ответа",
  // Под-объекты мобов.
  mob_variant: "🎭 Варианты мобов", mob_skill: "🌀 Навыки мобов", mob_passive: "🛡️ Пассивы мобов",
  mob_resistance: "🔥 Сопр./слабости", mob_effect: "☠️ Эффекты мобов",
  mob_event_link: "🔗 Моб↔событие", mob_zone_link: "🔗 Моб↔зона", mob_phase: "👑 Фазы босса",
};
const KIND_NEW_LABEL = {
  location: "＋ Новая локация", mob: "＋ Новый моб", button: "＋ Новая кнопка", transition: "＋ Новый переход",
  event: "＋ Новое событие", npc: "＋ Новый NPC", quest: "＋ Новый квест", raid: "＋ Новый рейд",
  location_zone: "＋ Новая зона", location_resource: "＋ Новый ресурс", location_loot: "＋ Новая добыча",
  location_mob_spawn: "＋ Новый моб локации", location_weekly_limit: "＋ Новый лимит",
  location_weekly_rotation: "＋ Новая ротация", location_depletion_rule: "＋ Новое правило",
  location_empty_event: "＋ Новое пустое событие", location_hidden_event: "＋ Новое скрытое событие",
  location_event_answer: "＋ Новый вариант ответа",
  mob_variant: "＋ Новый вариант", mob_skill: "＋ Новый навык", mob_passive: "＋ Новый пассив",
  mob_resistance: "＋ Новое сопр./слабость", mob_effect: "＋ Новый эффект",
  mob_event_link: "＋ Новая привязка", mob_zone_link: "＋ Новая привязка", mob_phase: "＋ Новая фаза",
};

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

const EMPTY_EVENT = {
  name: "", text: "", location: "", type: "found_item", result: "give_item",
  chance: 25, cooldown: 0, min_level: "", max_level: "",
  required_item: "", consumed_item: "", given_item: "", battle_mob: "",
  effect: "", repeatable: true,
};

const EMPTY_NPC = {
  name: "", role: "", location: "", description: "", image: "",
  first_message: "", functions: [],
};

const EMPTY_QUEST = {
  name: "", description: "", npc_giver: "", location: "",
  goal_type: "kill_mob", goal_target: "", reward: "",
  repeatable: false, cooldown: 0,
};

const EMPTY_RAID = {
  name: "", description: "", entry_location: "", raid_type: "world_boss",
  boss_mob: "", min_level: 1, max_members: 5, required_items: "", cooldown: 0, reward: "",
};

const EMPTY_BY_KIND = {
  location: EMPTY_LOCATION, mob: EMPTY_MOB, button: EMPTY_BUTTON, transition: EMPTY_TRANSITION,
  event: EMPTY_EVENT, npc: EMPTY_NPC, quest: EMPTY_QUEST, raid: EMPTY_RAID,
  // Под-объекты (расширенные конструкторы) — пустышки выводятся из схем ниже
  // (см. mergeSchemaEmpties после объявления SUBOBJECT_SCHEMAS).
};

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

function RefSelect({ value, onChange, options, disabled, placeholder = "— не выбрано —" }) {
  return (
    <select value={value || ""} disabled={disabled} onChange={(e) => onChange(e.target.value)}>
      <option value="">{placeholder}</option>
      {(options || []).map((o) => <option key={o.id} value={o.id}>{o.name} ({o.id})</option>)}
    </select>
  );
}

function EventForm({ value, onChange, meta, disabled, refOptions }) {
  const set = (k, v) => onChange({ ...value, [k]: v });
  return (
    <div className="ntv2-world-form">
      <div className="ntv2-form-row">
        <Field label="Название"><input value={value.name} disabled={disabled} onChange={(e) => set("name", e.target.value)} /></Field>
        <Field label="Тип"><select value={value.type} disabled={disabled} onChange={(e) => set("type", e.target.value)}>{(meta.eventTypes || []).map((t) => <option key={t} value={t}>{t}</option>)}</select></Field>
      </div>
      <Field label="Локация"><RefSelect value={value.location} onChange={(v) => set("location", v)} options={refOptions.location} disabled={disabled} /></Field>
      <Field label="Текст игроку"><textarea rows={3} value={value.text} disabled={disabled} onChange={(e) => set("text", e.target.value)} /></Field>
      <div className="ntv2-form-row">
        <Field label="Шанс %"><input type="number" value={value.chance} disabled={disabled} onChange={(e) => set("chance", e.target.value)} /></Field>
        <Field label="Кулдаун (сек)"><input type="number" value={value.cooldown} disabled={disabled} onChange={(e) => set("cooldown", e.target.value)} /></Field>
        <Field label="Ур. от"><input type="number" value={value.min_level} disabled={disabled} onChange={(e) => set("min_level", e.target.value)} /></Field>
        <Field label="Ур. до"><input type="number" value={value.max_level} disabled={disabled} onChange={(e) => set("max_level", e.target.value)} /></Field>
      </div>
      <Field label="Результат"><select value={value.result} disabled={disabled} onChange={(e) => set("result", e.target.value)}>{(meta.eventResultTypes || []).map((t) => <option key={t} value={t}>{t}</option>)}</select></Field>
      <div className="ntv2-form-row">
        <Field label="Выдаваемый предмет (item_id)"><input className="ntv2-mono" value={value.given_item} disabled={disabled} onChange={(e) => set("given_item", e.target.value)} /></Field>
        <Field label="Требуемый предмет"><input className="ntv2-mono" value={value.required_item} disabled={disabled} onChange={(e) => set("required_item", e.target.value)} /></Field>
        <Field label="Списываемый предмет"><input className="ntv2-mono" value={value.consumed_item} disabled={disabled} onChange={(e) => set("consumed_item", e.target.value)} /></Field>
      </div>
      <div className="ntv2-form-row">
        <Field label="Запускаемый бой (моб)"><RefSelect value={value.battle_mob} onChange={(v) => set("battle_mob", v)} options={refOptions.mob} disabled={disabled} /></Field>
        <Field label="Накладываемый эффект"><input value={value.effect} disabled={disabled} onChange={(e) => set("effect", e.target.value)} /></Field>
        <label className="ntv2-check"><input type="checkbox" checked={Boolean(value.repeatable)} disabled={disabled} onChange={(e) => set("repeatable", e.target.checked)} /> Повторяемое</label>
      </div>
    </div>
  );
}

function NpcForm({ value, onChange, meta, disabled, refOptions }) {
  const set = (k, v) => onChange({ ...value, [k]: v });
  const fns = Array.isArray(value.functions) ? value.functions : [];
  const toggleFn = (fn) => set("functions", fns.includes(fn) ? fns.filter((f) => f !== fn) : [...fns, fn]);
  return (
    <div className="ntv2-world-form">
      <div className="ntv2-form-row">
        <Field label="Имя"><input value={value.name} disabled={disabled} onChange={(e) => set("name", e.target.value)} /></Field>
        <Field label="Роль"><input value={value.role} disabled={disabled} onChange={(e) => set("role", e.target.value)} /></Field>
        <Field label="Локация"><RefSelect value={value.location} onChange={(v) => set("location", v)} options={refOptions.location} disabled={disabled} /></Field>
      </div>
      <Field label="Первое сообщение"><textarea rows={2} value={value.first_message} disabled={disabled} onChange={(e) => set("first_message", e.target.value)} /></Field>
      <Field label="Описание"><textarea rows={3} value={value.description} disabled={disabled} onChange={(e) => set("description", e.target.value)} /></Field>
      <Field label="Изображение (URL)"><input value={value.image} disabled={disabled} onChange={(e) => set("image", e.target.value)} /></Field>
      <div className="ntv2-panel">
        <h4 className="ntv2-subhead">Функции</h4>
        <div className="ntv2-form-row" style={{ gap: 12 }}>
          {(meta.npcFunctions || []).map((fn) => (
            <label className="ntv2-check" key={fn}><input type="checkbox" checked={fns.includes(fn)} disabled={disabled} onChange={() => toggleFn(fn)} /> {fn}</label>
          ))}
        </div>
      </div>
    </div>
  );
}

function QuestForm({ value, onChange, meta, disabled, refOptions }) {
  const set = (k, v) => onChange({ ...value, [k]: v });
  let targetControl;
  if (value.goal_type === "kill_mob") targetControl = <RefSelect value={value.goal_target} onChange={(v) => set("goal_target", v)} options={refOptions.mob} disabled={disabled} />;
  else if (value.goal_type === "visit_location") targetControl = <RefSelect value={value.goal_target} onChange={(v) => set("goal_target", v)} options={refOptions.location} disabled={disabled} />;
  else if (value.goal_type === "talk_npc") targetControl = <RefSelect value={value.goal_target} onChange={(v) => set("goal_target", v)} options={refOptions.npc} disabled={disabled} />;
  else targetControl = <input className="ntv2-mono" value={value.goal_target} disabled={disabled} placeholder="item_id / объект" onChange={(e) => set("goal_target", e.target.value)} />;
  return (
    <div className="ntv2-world-form">
      <Field label="Название"><input value={value.name} disabled={disabled} onChange={(e) => set("name", e.target.value)} /></Field>
      <Field label="Описание"><textarea rows={3} value={value.description} disabled={disabled} onChange={(e) => set("description", e.target.value)} /></Field>
      <div className="ntv2-form-row">
        <Field label="NPC-выдаватель"><RefSelect value={value.npc_giver} onChange={(v) => set("npc_giver", v)} options={refOptions.npc} disabled={disabled} /></Field>
        <Field label="Локация"><RefSelect value={value.location} onChange={(v) => set("location", v)} options={refOptions.location} disabled={disabled} /></Field>
      </div>
      <div className="ntv2-form-row">
        <Field label="Цель"><select value={value.goal_type} disabled={disabled} onChange={(e) => set("goal_type", e.target.value)}>{(meta.questGoalTypes || []).map((t) => <option key={t} value={t}>{t}</option>)}</select></Field>
        <Field label="Объект цели">{targetControl}</Field>
      </div>
      <Field label="Награда (описание / JSON)"><textarea rows={2} value={value.reward} disabled={disabled} onChange={(e) => set("reward", e.target.value)} /></Field>
      <div className="ntv2-form-row" style={{ gap: 14 }}>
        <label className="ntv2-check"><input type="checkbox" checked={Boolean(value.repeatable)} disabled={disabled} onChange={(e) => set("repeatable", e.target.checked)} /> Повторяемое</label>
        <Field label="Кулдаун (сек)"><input type="number" value={value.cooldown} disabled={disabled} onChange={(e) => set("cooldown", e.target.value)} /></Field>
      </div>
    </div>
  );
}

function RaidForm({ value, onChange, meta, disabled, refOptions }) {
  const set = (k, v) => onChange({ ...value, [k]: v });
  return (
    <div className="ntv2-world-form">
      <div className="ntv2-form-row">
        <Field label="Название"><input value={value.name} disabled={disabled} onChange={(e) => set("name", e.target.value)} /></Field>
        <Field label="Тип рейда"><select value={value.raid_type} disabled={disabled} onChange={(e) => set("raid_type", e.target.value)}>{(meta.raidTypes || []).map((t) => <option key={t} value={t}>{t}</option>)}</select></Field>
      </div>
      <div className="ntv2-form-row">
        <Field label="Локация входа"><RefSelect value={value.entry_location} onChange={(v) => set("entry_location", v)} options={refOptions.location} disabled={disabled} /></Field>
        <Field label="Босс (моб)"><RefSelect value={value.boss_mob} onChange={(v) => set("boss_mob", v)} options={refOptions.mob} disabled={disabled} /></Field>
      </div>
      <div className="ntv2-form-row">
        <Field label="Мин. уровень"><input type="number" value={value.min_level} disabled={disabled} onChange={(e) => set("min_level", e.target.value)} /></Field>
        <Field label="Макс. участников"><input type="number" value={value.max_members} disabled={disabled} onChange={(e) => set("max_members", e.target.value)} /></Field>
        <Field label="Кулдаун (сек)"><input type="number" value={value.cooldown} disabled={disabled} onChange={(e) => set("cooldown", e.target.value)} /></Field>
      </div>
      <Field label="Требуемые предметы (item_id через запятую)"><input className="ntv2-mono" value={value.required_items} disabled={disabled} onChange={(e) => set("required_items", e.target.value)} /></Field>
      <Field label="Описание"><textarea rows={3} value={value.description} disabled={disabled} onChange={(e) => set("description", e.target.value)} /></Field>
      <Field label="Награда (описание / JSON)"><textarea rows={2} value={value.reward} disabled={disabled} onChange={(e) => set("reward", e.target.value)} /></Field>
    </div>
  );
}

// --- Схемы под-объектов локаций и мобов (расширенные конструкторы) ---------
// Вместо 18 рукописных форм — одна форма, управляемая схемой полей. Тип поля:
// text/textarea/number/checkbox/mono(item_id) + select(metaKey) + ref(kind) +
// list(построчно → массив строк). ref-kind «location_zone» — зоны, «event» —
// события, «mob»/«location»/«npc» — соответствующие объекты.
const SUBOBJECT_SCHEMAS = {
  location_zone: [
    { key: "name", label: "Название", type: "text" },
    { key: "type", label: "Тип зоны", type: "select", metaKey: "zoneTypes" },
    { key: "location", label: "Локация", type: "ref", ref: "location" },
    { key: "trigger_chance", label: "Срабатывание %", type: "number" },
    { key: "player_text", label: "Текст игроку", type: "textarea" },
    { key: "description", label: "Тех. описание", type: "textarea" },
  ],
  location_resource: [
    { key: "location", label: "Локация", type: "ref", ref: "location" },
    { key: "item_id", label: "Предмет-ресурс (item_id)", type: "mono" },
    { key: "category", label: "Категория", type: "select", metaKey: "resourceCategories" },
    { key: "base_chance", label: "Базовый шанс %", type: "number" },
    { key: "min_chance", label: "Мин. шанс %", type: "number" },
    { key: "min_count", label: "Кол-во: от", type: "number" },
    { key: "max_count", label: "до", type: "number" },
    { key: "weekly_limit", label: "Недельный лимит", type: "number" },
  ],
  location_loot: [
    { key: "location", label: "Локация", type: "ref", ref: "location" },
    { key: "item_id", label: "Предмет (item_id)", type: "mono" },
    { key: "source", label: "Источник", type: "select", metaKey: "lootSources" },
    { key: "chance", label: "Шанс %", type: "number" },
    { key: "min_chance", label: "Мин. шанс %", type: "number" },
    { key: "min_count", label: "Кол-во: от", type: "number" },
    { key: "max_count", label: "до", type: "number" },
    { key: "weekly_limit", label: "Недельный лимит", type: "number" },
  ],
  location_mob_spawn: [
    { key: "location", label: "Локация", type: "ref", ref: "location" },
    { key: "mob_id", label: "Моб", type: "ref", ref: "mob" },
    { key: "spawn_chance", label: "Шанс встречи %", type: "number" },
    { key: "min_chance", label: "Мин. шанс %", type: "number" },
    { key: "mob_level_min", label: "Ур. моба: от", type: "number" },
    { key: "mob_level_max", label: "до", type: "number" },
    { key: "min_in_battle", label: "В бою: от", type: "number" },
    { key: "max_in_battle", label: "до", type: "number" },
    { key: "weekly_stock", label: "Недельный запас", type: "number" },
  ],
  location_weekly_limit: [
    { key: "location", label: "Локация", type: "ref", ref: "location" },
    { key: "limit_type", label: "Тип лимита", type: "select", metaKey: "weeklyLimitTypes" },
    { key: "linked_object", label: "Связанный объект (item_id/mob_id)", type: "mono" },
    { key: "total_stock", label: "Запас на неделю", type: "number" },
    { key: "min_per_event", label: "За событие: от", type: "number" },
    { key: "max_per_event", label: "до", type: "number" },
    { key: "base_chance", label: "Базовый шанс %", type: "number" },
    { key: "min_chance", label: "Мин. шанс %", type: "number" },
    { key: "source", label: "Источник", type: "select", metaKey: "lootSources" },
    { key: "depletion_text", label: "Текст при истощении", type: "textarea" },
  ],
  location_weekly_rotation: [
    { key: "name", label: "Название ротации", type: "text" },
    { key: "location", label: "Локация", type: "ref", ref: "location" },
    { key: "periodicity", label: "Периодичность", type: "select", metaKey: "rotationPeriodicity" },
    { key: "selection_mode", label: "Режим выбора", type: "select", metaKey: "rotationSelectionModes" },
    { key: "active_resources", label: "Активных ресурсов", type: "number" },
    { key: "active_mobs", label: "Активных мобов", type: "number" },
    { key: "active_events", label: "Активных событий", type: "number" },
  ],
  location_depletion_rule: [
    { key: "location", label: "Локация (необязательно)", type: "ref", ref: "location" },
    { key: "base_chance", label: "Базовый шанс %", type: "number" },
    { key: "min_chance", label: "Мин. шанс %", type: "number" },
    { key: "trigger", label: "Когда включать", type: "select", metaKey: "depletionTriggers" },
    { key: "redistribution_mode", label: "Перераспределение", type: "select", metaKey: "redistributionModes" },
    { key: "event_group", label: "Группа событий", type: "select", metaKey: "eventGroups" },
  ],
  location_empty_event: [
    { key: "location", label: "Локация", type: "ref", ref: "location" },
    { key: "player_text", label: "Текст игроку", type: "textarea" },
    { key: "min_percent_depleted", label: "Мин. % истощённых", type: "number" },
    { key: "chance", label: "Шанс %", type: "number" },
  ],
  location_hidden_event: [
    { key: "admin_name", label: "Название (админка)", type: "text" },
    { key: "player_name", label: "Название (игроку, после открытия)", type: "text" },
    { key: "player_text", label: "Текст игроку", type: "textarea" },
    { key: "location", label: "Локация", type: "ref", ref: "location" },
    { key: "conditions", label: "Условия открытия (по строке)", type: "list" },
    { key: "open_chance", label: "Шанс открытия %", type: "number" },
    { key: "given_item", label: "Выдаваемый предмет (item_id)", type: "mono" },
    { key: "battle_mob", label: "Запускаемый бой (моб)", type: "ref", ref: "mob" },
  ],
  location_event_answer: [
    { key: "button_text", label: "Текст кнопки", type: "text" },
    { key: "result", label: "Результат", type: "select", metaKey: "eventResultTypes" },
    { key: "result_text", label: "Текст результата", type: "textarea" },
    { key: "hidden", label: "Скрытый вариант", type: "checkbox" },
    { key: "conditions", label: "Условия показа (по строке)", type: "list" },
    { key: "required_item", label: "Требуемый предмет (item_id)", type: "mono" },
    { key: "reward_item", label: "Награда-предмет (item_id)", type: "mono" },
    { key: "success_chance", label: "Шанс успеха %", type: "number" },
    { key: "fail_chance", label: "Шанс провала %", type: "number" },
  ],
  mob_variant: [
    { key: "name", label: "Название варианта", type: "text" },
    { key: "mob_id", label: "Моб", type: "ref", ref: "mob" },
    { key: "variant_type", label: "Тип варианта", type: "select", metaKey: "mobVariantTypes" },
    { key: "hp_mult", label: "×HP", type: "number" },
    { key: "damage_mult", label: "×Урон", type: "number" },
    { key: "defense_mult", label: "×Защита", type: "number" },
    { key: "exp_mult", label: "×Опыт", type: "number" },
    { key: "coins_mult", label: "×Монеты", type: "number" },
    { key: "drop_mult", label: "×Дроп", type: "number" },
    { key: "spawn_chance", label: "Шанс варианта %", type: "number" },
    { key: "description", label: "Описание", type: "textarea" },
  ],
  mob_skill: [
    { key: "name", label: "Название навыка", type: "text" },
    { key: "mob_id", label: "Моб", type: "ref", ref: "mob" },
    { key: "skill_type", label: "Тип навыка", type: "select", metaKey: "mobSkillTypes" },
    { key: "use_condition", label: "Условие", type: "select", metaKey: "mobSkillConditions" },
    { key: "use_chance", label: "Шанс использования %", type: "number" },
    { key: "cooldown", label: "Кулдаун (ходов)", type: "number" },
    { key: "player_text", label: "Текст игроку", type: "textarea" },
  ],
  mob_passive: [
    { key: "name", label: "Название", type: "text" },
    { key: "mob_id", label: "Моб", type: "ref", ref: "mob" },
    { key: "player_description", label: "Описание игроку", type: "textarea" },
  ],
  mob_resistance: [
    { key: "mob_id", label: "Моб", type: "ref", ref: "mob" },
    { key: "resist_type", label: "Тип", type: "select", metaKey: "mobResistTypes" },
    { key: "value", label: "Значение", type: "number" },
    { key: "is_weakness", label: "Это слабость", type: "checkbox" },
  ],
  mob_effect: [
    { key: "name", label: "Название эффекта", type: "text" },
    { key: "mob_id", label: "Моб", type: "ref", ref: "mob" },
    { key: "effect_id", label: "Эффект из конструктора (id)", type: "mono" },
    { key: "chance", label: "Шанс наложения %", type: "number" },
    { key: "duration", label: "Длительность (ходов)", type: "number" },
    { key: "player_text", label: "Текст игроку", type: "textarea" },
  ],
  mob_event_link: [
    { key: "mob_id", label: "Моб", type: "ref", ref: "mob" },
    { key: "event_id", label: "Событие", type: "ref", ref: "event" },
    { key: "spawn_chance", label: "Шанс появления %", type: "number" },
    { key: "count", label: "Количество мобов", type: "number" },
    { key: "variant_type", label: "Вариант", type: "select", metaKey: "mobVariantTypes" },
  ],
  mob_zone_link: [
    { key: "mob_id", label: "Моб", type: "ref", ref: "mob" },
    { key: "zone_id", label: "Зона", type: "ref", ref: "location_zone" },
    { key: "spawn_chance_delta", label: "Δ шанса встречи", type: "number" },
    { key: "variant_type", label: "Вариант", type: "select", metaKey: "mobVariantTypes" },
  ],
  mob_phase: [
    { key: "name", label: "Название фазы", type: "text" },
    { key: "mob_id", label: "Моб (босс)", type: "ref", ref: "mob" },
    { key: "start_condition", label: "Условие начала", type: "text" },
    { key: "player_text", label: "Описание игроку", type: "textarea" },
    { key: "transition_message", label: "Сообщение при переходе", type: "textarea" },
  ],
};

function emptyFromSchema(schema) {
  const out = {};
  for (const f of schema) {
    if (f.type === "checkbox") out[f.key] = false;
    else if (f.type === "list") out[f.key] = [];
    else if (f.type === "number") out[f.key] = "";
    else out[f.key] = "";
  }
  return out;
}

// Пустышки под-объектов выводятся из их схем (без рукописных EMPTY_*).
for (const [schemaKind, schema] of Object.entries(SUBOBJECT_SCHEMAS)) {
  EMPTY_BY_KIND[schemaKind] = emptyFromSchema(schema);
}

// Какие справочники-ссылки нужны схеме (для пикеров ref).
function refKindsForSchema(schema) {
  return [...new Set((schema || []).filter((f) => f.type === "ref").map((f) => f.ref))];
}

function GenericForm({ value, onChange, meta, refOptions, disabled, schema }) {
  const set = (k, v) => onChange({ ...value, [k]: v });
  return (
    <div className="ntv2-world-form">
      {schema.map((f) => {
        if (f.type === "checkbox") {
          return (
            <label className="ntv2-check" key={f.key}>
              <input type="checkbox" checked={Boolean(value[f.key])} disabled={disabled} onChange={(e) => set(f.key, e.target.checked)} /> {f.label}
            </label>
          );
        }
        let control;
        if (f.type === "textarea") {
          control = <textarea rows={3} value={value[f.key] || ""} disabled={disabled} onChange={(e) => set(f.key, e.target.value)} />;
        } else if (f.type === "number") {
          control = <input type="number" value={value[f.key] ?? ""} disabled={disabled} onChange={(e) => set(f.key, e.target.value)} />;
        } else if (f.type === "mono") {
          control = <input className="ntv2-mono" value={value[f.key] || ""} disabled={disabled} onChange={(e) => set(f.key, e.target.value)} />;
        } else if (f.type === "select") {
          control = (
            <select value={value[f.key] || ""} disabled={disabled} onChange={(e) => set(f.key, e.target.value)}>
              <option value="">— не выбрано —</option>
              {(meta[f.metaKey] || []).map((o) => <option key={o} value={o}>{o}</option>)}
            </select>
          );
        } else if (f.type === "ref") {
          control = <RefSelect value={value[f.key]} onChange={(v) => set(f.key, v)} options={refOptions[f.ref]} disabled={disabled} />;
        } else if (f.type === "list") {
          const text = Array.isArray(value[f.key]) ? value[f.key].join("\n") : (value[f.key] || "");
          control = <textarea rows={3} value={text} disabled={disabled} onChange={(e) => set(f.key, e.target.value.split("\n").map((s) => s.trim()).filter(Boolean))} />;
        } else {
          control = <input value={value[f.key] || ""} disabled={disabled} onChange={(e) => set(f.key, e.target.value)} />;
        }
        return <Field label={f.label} key={f.key}>{control}</Field>;
      })}
    </div>
  );
}

const FORM_BY_KIND = {
  location: LocationForm, mob: MobForm, button: ButtonForm, transition: TransitionForm,
  event: EventForm, npc: NpcForm, quest: QuestForm, raid: RaidForm,
};

export function WorldSection({ guarded, hasPerm }) {
  const [meta, setMeta] = useState(null);
  const [kind, setKind] = useState("location");
  const [items, setItems] = useState([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [editing, setEditing] = useState(null);
  const [confirm, setConfirm] = useState(null);
  const [refOptions, setRefOptions] = useState({ location: [], mob: [], npc: [] });
  const [preview, setPreview] = useState(null);
  const [testReport, setTestReport] = useState(null);
  const [battleReport, setBattleReport] = useState(null);

  const can = useMemo(() => ({
    create: hasPerm("world.create_draft"),
    edit: hasPerm("world.edit_draft"),
    validate: hasPerm("world.validate"),
    publish: hasPerm("world.publish"),
    disable: hasPerm("world.disable"),
    archive: hasPerm("world.archive"),
    testRun: hasPerm("world.test_run"),
    mobTestBattle: hasPerm("mob.test_battle"),
  }), [hasPerm]);

  const loadList = useCallback(async () => {
    const payload = await guarded(() => fetchWorldItems(kind, statusFilter));
    if (payload) setItems(payload.items || []);
  }, [guarded, kind, statusFilter]);

  // Какие справочники объектов нужны форме текущего типа (для пикеров-ссылок).
  const neededRefs = useMemo(() => {
    if (SUBOBJECT_SCHEMAS[kind]) return refKindsForSchema(SUBOBJECT_SCHEMAS[kind]);
    return ({
      button: ["location"], transition: ["location"],
      event: ["location", "mob"], npc: ["location"],
      quest: ["location", "mob", "npc"], raid: ["location", "mob"],
    }[kind] || []);
  }, [kind]);

  const loadRefs = useCallback(async (kinds) => {
    const entries = await Promise.all(kinds.map(async (k) => {
      const payload = await guarded(() => fetchWorldItems(k));
      return [k, (payload?.items || []).map((i) => ({ id: i.id, name: i.data?.name || i.id }))];
    }));
    setRefOptions((cur) => ({ ...cur, ...Object.fromEntries(entries) }));
  }, [guarded]);

  useEffect(() => { (async () => { const m = await guarded(() => fetchWorldMeta()); if (m) setMeta(m); })(); }, [guarded]);
  useEffect(() => { loadList(); }, [loadList]);
  useEffect(() => { if (neededRefs.length) loadRefs(neededRefs); }, [neededRefs, loadRefs]);

  const statuses = meta?.statuses || [];
  const schema = SUBOBJECT_SCHEMAS[kind];
  const Form = FORM_BY_KIND[kind] || LocationForm;

  function resetPanels() { setPreview(null); setTestReport(null); setBattleReport(null); }

  async function runMobBattle() {
    const payload = await guarded(() => mobTestBattle(editing.id, { count: 300 }), "Тестовый бой проведён.");
    if (payload?.report) setBattleReport(payload.report);
  }
  function switchKind(k) { setKind(k); setEditing(null); setStatusFilter(""); resetPanels(); }
  function startCreate() { resetPanels(); setEditing({ id: "", data: { ...(EMPTY_BY_KIND[kind] || {}) }, status: "draft", validation: null, isNew: true }); }
  function openItem(item) { resetPanels(); setEditing({ id: item.id, data: { ...(EMPTY_BY_KIND[kind] || {}), ...(item.data || {}) }, status: item.status, validation: item.validation, isNew: false }); }

  async function runPreview() {
    const payload = await guarded(() => previewWorldItem(kind, editing.id));
    if (payload?.preview) { setPreview(payload.preview); setTestReport(null); }
  }

  async function runTestRun() {
    const payload = await guarded(() => testRunWorldItem(kind, editing.id), "Тестовый проход выполнен.");
    if (payload?.report) { setTestReport(payload.report); setPreview(payload.report.preview || null); }
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

        {schema ? (
          <GenericForm schema={schema} value={editing.data} onChange={(data) => setEditing({ ...editing, data })} meta={meta} refOptions={refOptions} disabled={!(editing.isNew ? can.create : can.edit)} />
        ) : (
          <Form value={editing.data} onChange={(data) => setEditing({ ...editing, data })} meta={meta} locationOptions={refOptions.location} refOptions={refOptions} disabled={!(editing.isNew ? can.create : can.edit)} />
        )}

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
          {!editing.isNew ? <button type="button" className="ntv2-btn" onClick={runPreview}>Предпросмотр</button> : null}
          {!editing.isNew && can.testRun ? <button type="button" className="ntv2-btn" onClick={runTestRun}>Тестовый проход</button> : null}
          {!editing.isNew && kind === "mob" && can.mobTestBattle ? <button type="button" className="ntv2-btn" onClick={runMobBattle}>Тестовый бой</button> : null}
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

        {testReport ? (
          <div className={`ntv2-panel ${testReport.ok ? "" : "ntv2-danger-zone"}`}>
            <h4 className="ntv2-subhead">{testReport.ok ? "✅ Тестовый проход пройден" : "❌ Тестовый проход: есть проблемы"}</h4>
            <div className="ntv2-list">
              {testReport.checks.map((c, i) => (
                <div className={`ntv2-list-row${c.ok ? "" : " ntv2-danger-zone"}`} key={i}>
                  <span className="ntv2-badge">{c.kind}</span>
                  <b>{c.title}</b>
                  <span className="ntv2-mono">{c.id}</span>
                  <span className={`ntv2-badge ${c.ok ? "ntv2-badge-owner" : "ntv2-badge-error"}`}>{c.ok ? "ок" : "ошибки"}</span>
                  {(c.errors || []).map((e, j) => <span className="ntv2-error" key={j}>{e}</span>)}
                </div>
              ))}
            </div>
          </div>
        ) : null}

        {battleReport ? (
          <div className={`ntv2-panel ${battleReport.warnings?.length ? "ntv2-danger-zone" : ""}`}>
            <h4 className="ntv2-subhead">Тестовый бой ({battleReport.simulations} симуляций)</h4>
            <div className="ntv2-list">
              <div className="ntv2-list-row"><b>Шанс победы</b><span>{Math.round(battleReport.winRate * 100)}%</span></div>
              <div className="ntv2-list-row"><b>Шанс смерти</b><span>{Math.round(battleReport.deathRate * 100)}%</span></div>
              <div className="ntv2-list-row"><b>Средняя длительность</b><span>{battleReport.avgTurns} ходов</span></div>
              <div className="ntv2-list-row"><b>Урон моба / ход</b><span>{battleReport.avgMobDamagePerTurn}</span></div>
              <div className="ntv2-list-row"><b>Урон игрока / ход</b><span>{battleReport.avgPlayerDamagePerTurn}</span></div>
              <div className="ntv2-list-row"><b>Средний опыт / монеты</b><span>{battleReport.avgExp} / {battleReport.avgCoins}</span></div>
            </div>
            {(battleReport.warnings || []).map((w, i) => <p className="ntv2-error" key={i}>⚠️ {w}</p>)}
            <TechnicalData label="Тестовый бой (данные)" value={battleReport} />
          </div>
        ) : null}

        {preview ? (
          <div className="ntv2-panel">
            <h4 className="ntv2-subhead">Предпросмотр</h4>
            <div className="ntv2-preview-card">
              <b>{preview.title}</b>
              {preview.text ? <p>{preview.text}</p> : null}
              {preview.kind === "location" ? (
                <>
                  {preview.telegramButtons?.length ? <p className="ntv2-hint">Telegram: {preview.telegramButtons.map((b) => `[${b}]`).join(" ")}</p> : null}
                  {preview.vkButtons?.length ? <p className="ntv2-hint">VK: {preview.vkButtons.map((b) => `[${b}]`).join(" ")}</p> : null}
                  {preview.transitions?.length ? <p className="ntv2-hint">Переходы: {preview.transitions.map((t) => t.to).join(", ")}</p> : null}
                  {preview.events?.length ? <p className="ntv2-hint">События: {preview.events.map((e) => `${e.name} (${e.chance ?? "?"}%)`).join(", ")}</p> : null}
                  {preview.npcs?.length ? <p className="ntv2-hint">NPC: {preview.npcs.map((n) => n.name).join(", ")}</p> : null}
                  {preview.mobs?.length ? <p className="ntv2-hint">Мобы: {preview.mobs.map((m) => m.name).join(", ")}</p> : null}
                </>
              ) : null}
            </div>
            <TechnicalData label="Предпросмотр (данные)" value={preview} />
          </div>
        ) : null}

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
        {can.publish ? (
          <button type="button" className="ntv2-btn" title="Загрузить существующие предметы и мобов из игры в конструкторы" onClick={() => setConfirm({
            title: "Импортировать существующий контент?",
            body: <p>Существующие предметы и мобы из игры будут добавлены в конструкторы как опубликованные записи (повторно — без дублей). Живые данные игры не меняются.</p>,
            confirmLabel: "Импортировать",
            run: async (reason) => {
              const res = await guarded(() => importExistingContent(["item", "mob"], false, reason), "Импорт выполнен.");
              await loadList();
              const reports = res?.reports || [];
              if (reports.length) window.alert(reports.map((r) => `${r.kind}: создано ${r.created}, пропущено ${r.skipped}`).join("\n"));
            },
          })}>Импортировать существующее</button>
        ) : null}
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
