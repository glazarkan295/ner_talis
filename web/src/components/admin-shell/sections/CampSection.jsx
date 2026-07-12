import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  createCamp,
  deleteCamp,
  fetchCamp,
  fetchCampMeta,
  fetchCampUsage,
  fetchCamps,
  importCamps,
  campLifecycle,
  updateCamp,
  validateCamp,
} from "../../../api/adminCampApi.js";
import { ConfirmModal } from "../ConfirmModal.jsx";
import { VersionHistory } from "../VersionHistory.jsx";
import { EmojiInput, EmojiTextarea } from "../EmojiField.jsx";
import { SearchBox, NoResults, filterEntities } from "../SearchFilter.jsx";
import { fetchEffects } from "../../../api/adminEffectApi.js";

const STATUS_TONE = { published: "ntv2-badge-owner", error: "ntv2-badge-error", disabled: "ntv2-badge-danger" };

const CAMP_TYPE_LABEL = {
  standard: "Стандартный", safe: "Безопасный", dangerous: "Опасный",
  event: "Событийный", temporary: "Временный", special: "Специальный",
};
const TARGET_LABEL = {
  hp: "HP", mana: "Мана", spirit: "Дух", energy: "Энергия", stamina: "Стамина", fatigue: "Усталость",
};

const EMPTY = {
  name: "", player_name: "", system_name: "", camp_type: "standard", category: "rest_point", safety_type: "safe",
  short_description: "", full_text: "", technical_description: "", hidden_description: "",
  locations: [], actions: [], recovery: [],
  parent_location: "", parent_sublocation: "", region: "", city_id: "", min_level: 0, max_level: 0, priority: 0,
  active: true, can_rest: true, default_camp: false, death_camp: false, use_as_respawn: false, return_after_death: false,
  rest_price: 0, rest_currency: "copper", rest_item_id: "", rest_item_amount: 1, consume_rest_item: false,
  base_time: 30, min_time: 1, max_time: 600, low_energy_time: 300, zero_energy_time: 600, cooldown: 0, use_limit: 0,
  entry_text: "", exit_text: "", rest_text: "", rest_start_text: "", rest_complete_text: "", rest_interrupted_text: "",
  death_text: "", death_return_text: "", access_denied_text: "", missing_item_text: "", danger_text: "", safe_text: "",
  npc_ids: [], event_ids: [], button_ids: [], weekly_limit_ids: [], services: [], effect_links: [], items: [],
  camp_events: [], weekly_limits: [], access_conditions: [],
};

function Field({ label, children }) {
  return <label className="ntv2-field"><span>{label}</span>{children}</label>;
}

export function CampSection({ guarded, hasPerm }) {
  const [meta, setMeta] = useState(null);
  const [list, setList] = useState([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState(null);
  const [confirm, setConfirm] = useState(null);
  const [usage, setUsage] = useState(null);
  const [effectOptions, setEffectOptions] = useState([]);

  const can = useMemo(() => ({
    create: hasPerm("camp.create"), edit: hasPerm("camp.edit"), validate: hasPerm("camp.validate"),
    publish: hasPerm("camp.publish"), disable: hasPerm("camp.disable"),
    archive: hasPerm("camp.archive"), del: hasPerm("camp.delete"),
  }), [hasPerm]);

  const load = useCallback(async () => { const p = await guarded(() => fetchCamps(statusFilter)); if (p) setList(p.items || []); }, [guarded, statusFilter]);
  useEffect(() => { (async () => { const m = await guarded(() => fetchCampMeta()); if (m) setMeta(m); })(); }, [guarded]);
  useEffect(() => { (async () => { const e = await guarded(() => fetchEffects("published")); if (e) setEffectOptions((e.items || []).map((x) => ({ value: x.id, label: x.data?.effect_name || x.id }))); })(); }, [guarded]);
  useEffect(() => { load(); }, [load]);

  const statuses = meta?.statuses || [];
  const statusLabel = (v) => statuses.find((s) => s.value === v)?.label || v;

  async function openItem(id) {
    const p = await guarded(() => fetchCamp(id));
    if (p?.item) { setUsage(null); setEditing({ id, data: { ...EMPTY, ...(p.item.data || {}) }, status: p.item.status, validation: p.validation, isNew: false }); }
  }
  function startCreate() { setEditing({ id: "", data: { ...EMPTY }, status: "draft", validation: null, isNew: true }); }

  async function save() {
    const e = editing;
    if (e.isNew) { const p = await guarded(() => createCamp(e.id.trim(), e.data, ""), "Создано."); if (p?.item) await openItem(e.id.trim()); }
    else { await guarded(() => updateCamp(e.id, e.data, "правка"), "Сохранено."); await openItem(e.id); }
    await load();
  }
  async function runValidate() { const p = await guarded(() => validateCamp(editing.id, ""), "Проверка выполнена."); if (p?.validation) setEditing((c) => ({ ...c, validation: p.validation })); }
  async function refreshEditing() { await load(); if (editing) await openItem(editing.id); }

  if (!meta) return <section className="ntv2-section"><h2>Конструктор лагеря</h2><p className="ntv2-hint">Загрузка…</p></section>;

  if (editing) {
    const d = editing.data;
    const set = (k, v) => setEditing({ ...editing, data: { ...d, [k]: v } });
    const disabled = !(editing.isNew ? can.create : can.edit);
    const v = editing.validation;
    const recovery = Array.isArray(d.recovery) ? d.recovery : [];
    const setRec = (i, patch) => set("recovery", recovery.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));
    const actions = Array.isArray(d.actions) ? d.actions : [];
    const effectLinks = Array.isArray(d.effect_links) ? d.effect_links : [];
    const campEvents = Array.isArray(d.camp_events) ? d.camp_events : [];
    const weeklyLimits = Array.isArray(d.weekly_limits) ? d.weekly_limits : [];
    const campItems = Array.isArray(d.items) ? d.items : [];
    const services = Array.isArray(d.services) ? d.services : [];
    const campNpcs = Array.isArray(d.camp_npcs) ? d.camp_npcs : [];
    const accessConditions = Array.isArray(d.access_conditions) ? d.access_conditions : [];
    const patchRow = (key, rows, index, patch) => set(key, rows.map((row, i) => (i === index ? { ...(typeof row === "object" && row ? row : {}), ...patch } : row)));
    const toggleAction = (a) => set("actions", actions.includes(a) ? actions.filter((x) => x !== a) : [...actions, a]);
    const num = (key, label) => <Field label={label} key={key}><input type="number" value={d[key]} disabled={disabled} onChange={(e) => set(key, e.target.value)} /></Field>;
    return (
      <section className="ntv2-section">
        <div className="ntv2-card-head">
          <button type="button" className="ntv2-btn" onClick={() => setEditing(null)}>← К списку</button>
          <h2>{editing.isNew ? "Новый лагерь" : d.name || editing.id}</h2>
          {!editing.isNew ? <span className={`ntv2-badge ${STATUS_TONE[editing.status] || ""}`}>{statusLabel(editing.status)}</span> : null}
        </div>
        {editing.isNew ? <Field label="ID (латиница, напр. safe_glade)"><input value={editing.id} onChange={(e) => setEditing({ ...editing, id: e.target.value })} /></Field> : <p className="ntv2-hint ntv2-mono">{editing.id}</p>}

        <div className="ntv2-world-form">
          <div className="ntv2-form-row">
            <Field label="Название"><EmojiInput value={d.name} disabled={disabled} onChange={(val) => set("name", val)} /></Field>
            <Field label="Тип лагеря"><select value={d.camp_type} disabled={disabled} onChange={(e) => set("camp_type", e.target.value)}>{(meta.campTypes || []).map((c) => <option key={c} value={c}>{CAMP_TYPE_LABEL[c] || c}</option>)}</select></Field>
            <Field label="Категория"><select value={d.category || "rest_point"} disabled={disabled} onChange={(e) => set("category", e.target.value)}>{(meta.campCategories || []).map((c) => <option key={c} value={c}>{c}</option>)}</select></Field>
            <Field label="Безопасность"><select value={d.safety_type || "safe"} disabled={disabled} onChange={(e) => set("safety_type", e.target.value)}>{(meta.safetyTypes || []).map((c) => <option key={c} value={c}>{c === "safe" ? "Безопасный" : c === "partial" ? "Частично безопасный" : "Опасный"}</option>)}</select></Field>
          </div>
          <Field label="Краткое описание"><EmojiTextarea rows={2} value={d.short_description} disabled={disabled} onChange={(val) => set("short_description", val)} /></Field>
          <Field label="Полный текст лагеря"><EmojiTextarea rows={3} value={d.full_text} disabled={disabled} onChange={(val) => set("full_text", val)} /></Field>
          <Field label="Локации (id через запятую)"><input className="ntv2-mono" value={(d.locations || []).join(", ")} disabled={disabled} onChange={(e) => set("locations", e.target.value.split(",").map((s) => s.trim()).filter(Boolean))} /></Field>
          <div className="ntv2-form-row">
            <Field label="Родительская локация"><input className="ntv2-mono" value={d.parent_location || ""} disabled={disabled} onChange={(e) => set("parent_location", e.target.value)} /></Field>
            <Field label="Родительская подлокация"><input className="ntv2-mono" value={d.parent_sublocation || ""} disabled={disabled} onChange={(e) => set("parent_sublocation", e.target.value)} /></Field>
            {num("min_level", "Мин. уровень")}{num("max_level", "Макс. уровень")}{num("priority", "Приоритет")}
          </div>

          <div className="ntv2-panel">
            <h4 className="ntv2-subhead">Доступ, отдых и смерть</h4>
            <div className="ntv2-form-row" style={{ flexWrap: "wrap" }}>
              {[["active", "Активен"], ["can_rest", "Можно отдыхать"], ["default_camp", "Лагерь по умолчанию"], ["death_camp", "Для смерти"], ["use_as_respawn", "Точка возрождения"], ["return_after_death", "Возврат после смерти"]].map(([key, label]) => (
                <label className="ntv2-check" key={key}><input type="checkbox" checked={Boolean(d[key])} disabled={disabled} onChange={(e) => set(key, e.target.checked)} /> {label}</label>
              ))}
            </div>
            <div className="ntv2-form-row">
              {num("rest_price", "Цена отдыха")}
              <Field label="Валюта"><select value={d.rest_currency || "copper"} disabled={disabled} onChange={(e) => set("rest_currency", e.target.value)}><option value="copper">Медь</option><option value="silver">Серебро</option><option value="gold">Золото</option></select></Field>
              <Field label="Предмет для отдыха"><input className="ntv2-mono" value={d.rest_item_id || ""} disabled={disabled} onChange={(e) => set("rest_item_id", e.target.value)} /></Field>
              {num("rest_item_amount", "Количество")}
              <label className="ntv2-check"><input type="checkbox" checked={Boolean(d.consume_rest_item)} disabled={disabled} onChange={(e) => set("consume_rest_item", e.target.checked)} /> Расходовать предмет</label>
            </div>
          </div>

          <div className="ntv2-panel">
            <h4 className="ntv2-subhead">Условия доступа</h4>
            {accessConditions.map((row, index) => <div className="ntv2-list-row" key={index}>
              <select value={row.type || "level"} disabled={disabled} onChange={(e) => patchRow("access_conditions", accessConditions, index, { type: e.target.value })}>{[["level","Уровень"],["race","Раса"],["item","Предмет"],["quest","Квест"],["event","Событие"],["reputation","Репутация"],["hidden_reputation","Скрытая репутация"],["fine","Штраф"],["unlock","Открытие"],["state","Состояние"]].map(([value,label]) => <option key={value} value={value}>{label}</option>)}</select>
              <input className="ntv2-mono" placeholder="ID объекта" value={row.object_id || ""} disabled={disabled} onChange={(e) => patchRow("access_conditions", accessConditions, index, { object_id: e.target.value })} />
              <select value={row.operator || "eq"} disabled={disabled} onChange={(e) => patchRow("access_conditions", accessConditions, index, { operator: e.target.value })}>{["eq","ne","gte","lte","gt","lt"].map((value) => <option key={value} value={value}>{value}</option>)}</select>
              <input placeholder="Значение" value={String(row.value ?? "")} disabled={disabled} onChange={(e) => patchRow("access_conditions", accessConditions, index, { value: e.target.value })} />
              <input placeholder="Текст отказа" value={row.error_text || ""} disabled={disabled} onChange={(e) => patchRow("access_conditions", accessConditions, index, { error_text: e.target.value })} />
              {!disabled ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => set("access_conditions", accessConditions.filter((_, i) => i !== index))}>×</button> : null}
            </div>)}
            {!disabled ? <button type="button" className="ntv2-btn" onClick={() => set("access_conditions", [...accessConditions, { type: "level", object_id: "", operator: "gte", value: 1, error_text: "", active: true }])}>＋ Условие</button> : null}
          </div>

          <h4 className="ntv2-subhead">Время (сек)</h4>
          <div className="ntv2-form-row">{num("base_time", "Базовое")}{num("min_time", "Мин.")}{num("max_time", "Макс.")}{num("low_energy_time", "При низкой энергии")}{num("zero_energy_time", "При нулевой энергии")}{num("cooldown", "Откат")}{num("use_limit", "Лимит исп.")}</div>

          <div className="ntv2-panel">
            <h4 className="ntv2-subhead">Восстановление ({recovery.length})</h4>
            <div className="ntv2-list">
              {recovery.map((row, i) => (
                <div className="ntv2-list-row" key={i}>
                  <select value={row.target || "hp"} disabled={disabled} onChange={(e) => setRec(i, { target: e.target.value })}>{(meta.recoveryTargets || []).map((rt) => <option key={rt} value={rt}>{TARGET_LABEL[rt] || rt}</option>)}</select>
                  <input type="number" style={{ width: 90 }} placeholder="плоско" value={row.flat ?? ""} disabled={disabled} onChange={(e) => setRec(i, { flat: e.target.value })} />
                  <input type="number" style={{ width: 90 }} placeholder="%" value={row.percent ?? ""} disabled={disabled} onChange={(e) => setRec(i, { percent: e.target.value })} />
                  <input type="number" style={{ width: 90 }} placeholder="мин." value={row.min ?? ""} disabled={disabled} onChange={(e) => setRec(i, { min: e.target.value })} />
                  <input type="number" style={{ width: 90 }} placeholder="макс." value={row.max ?? ""} disabled={disabled} onChange={(e) => setRec(i, { max: e.target.value })} />
                  <label className="ntv2-check"><input type="checkbox" checked={Boolean(row.full)} disabled={disabled} onChange={(e) => setRec(i, { full: e.target.checked })} /> Полностью</label>
                  {!disabled ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => set("recovery", recovery.filter((_, idx) => idx !== i))}>×</button> : null}
                </div>
              ))}
            </div>
            {!disabled ? <button type="button" className="ntv2-btn" style={{ marginTop: 6 }} onClick={() => set("recovery", [...recovery, { target: "hp", flat: 0, percent: 0 }])}>＋ Восстановление</button> : null}
          </div>

          <div className="ntv2-panel">
            <h4 className="ntv2-subhead">Связи</h4>
            {[["npc_ids", "NPC"], ["event_ids", "События"], ["button_ids", "Кнопки"], ["weekly_limit_ids", "Недельные лимиты"]].map(([key, label]) => (
              <Field label={`${label} (ID через запятую)`} key={key}><input className="ntv2-mono" value={(d[key] || []).join(", ")} disabled={disabled} onChange={(e) => set(key, e.target.value.split(",").map((s) => s.trim()).filter(Boolean))} /></Field>
            ))}
          </div>

          <div className="ntv2-panel">
            <h4 className="ntv2-subhead">Услуги лагеря</h4>
            {services.map((row, index) => {
              const service = typeof row === "string" ? { service_id: row, name: row, service_type: row } : row;
              return <div className="ntv2-list-row" key={index}>
                <input className="ntv2-mono" placeholder="service_id" value={service.service_id || ""} disabled={disabled} onChange={(e) => patchRow("services", services, index, { service_id: e.target.value })} />
                <input placeholder="Название кнопки" value={service.name || ""} disabled={disabled} onChange={(e) => patchRow("services", services, index, { name: e.target.value })} />
                <select value={service.service_type || "healing"} disabled={disabled} onChange={(e) => patchRow("services", services, index, { service_type: e.target.value })}>
                  {[["healing", "Лечение"], ["restore_energy", "Энергия"], ["restore_mana", "Мана"], ["restore_spirit", "Дух"], ["remove_effect", "Снять эффект"], ["remove_curse", "Снять проклятье"], ["apply_effect", "Наложить эффект"], ["repair", "Ремонт"], ["craft", "Ремесло"], ["trade", "Торговля"], ["rumors", "Слухи"], ["delivery", "Доставка"], ["storage", "Хранилище"], ["pay_fines", "Оплата штрафов"]].map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                </select>
                <input type="number" min="0" placeholder="цена" value={service.cost ?? 0} disabled={disabled} onChange={(e) => patchRow("services", services, index, { cost: e.target.value })} />
                <select value={service.currency || "copper"} disabled={disabled} onChange={(e) => patchRow("services", services, index, { currency: e.target.value })}><option value="copper">Медь</option><option value="silver">Серебро</option><option value="gold">Золото</option></select>
                <input className="ntv2-mono" placeholder="required NPC id" value={service.required_npc_id || ""} disabled={disabled} onChange={(e) => patchRow("services", services, index, { required_npc_id: e.target.value })} />
                {service.service_type === "apply_effect" || service.service_type === "remove_effect" ? <select value={service.effect_id || ""} disabled={disabled} onChange={(e) => patchRow("services", services, index, { effect_id: e.target.value })}><option value="">— эффект —</option>{effectOptions.map((o) => <option key={o.value} value={o.value}>{o.label} ({o.value})</option>)}</select> : <input className="ntv2-mono" placeholder="required item id" value={service.required_item_id || ""} disabled={disabled} onChange={(e) => patchRow("services", services, index, { required_item_id: e.target.value })} />}
                <input placeholder="Игровое действие/кнопка" value={service.target_action || ""} disabled={disabled} onChange={(e) => patchRow("services", services, index, { target_action: e.target.value })} />
                <input placeholder="Требуемое условие" value={service.required_condition || ""} disabled={disabled} onChange={(e) => patchRow("services", services, index, { required_condition: e.target.value })} />
                <input placeholder="текст успеха" value={service.success_text || ""} disabled={disabled} onChange={(e) => patchRow("services", services, index, { success_text: e.target.value })} />
                <input placeholder="текст ошибки" value={service.error_text || ""} disabled={disabled} onChange={(e) => patchRow("services", services, index, { error_text: e.target.value })} />
                {!disabled ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => set("services", services.filter((_, i) => i !== index))}>×</button> : null}
              </div>;
            })}
            {!disabled ? <button type="button" className="ntv2-btn" onClick={() => set("services", [...services, { service_id: `service_${services.length + 1}`, name: "Новая услуга", service_type: "healing", cost: 0, currency: "copper", active: true }])}>＋ Услуга</button> : null}
          </div>

          <div className="ntv2-panel">
            <h4 className="ntv2-subhead">NPC лагеря</h4>
            {campNpcs.map((row,index)=><div className="ntv2-list-row" key={index}>
              <input className="ntv2-mono" placeholder="ID NPC" value={row.npc_id || ""} disabled={disabled} onChange={(e)=>patchRow("camp_npcs",campNpcs,index,{npc_id:e.target.value})}/>
              <input placeholder="Название" value={row.name || ""} disabled={disabled} onChange={(e)=>patchRow("camp_npcs",campNpcs,index,{name:e.target.value})}/>
              <input placeholder="Роль" value={row.role || ""} disabled={disabled} onChange={(e)=>patchRow("camp_npcs",campNpcs,index,{role:e.target.value})}/>
              <label className="ntv2-check"><input type="checkbox" checked={Boolean(row.permanent)} disabled={disabled} onChange={(e)=>patchRow("camp_npcs",campNpcs,index,{permanent:e.target.checked})}/> Постоянный</label>
              <label className="ntv2-check"><input type="checkbox" checked={Boolean(row.temporary)} disabled={disabled} onChange={(e)=>patchRow("camp_npcs",campNpcs,index,{temporary:e.target.checked})}/> Временный</label>
              <label className="ntv2-check"><input type="checkbox" checked={Boolean(row.hidden)} disabled={disabled} onChange={(e)=>patchRow("camp_npcs",campNpcs,index,{hidden:e.target.checked})}/> Скрытый</label>
              <input placeholder="Условие появления" value={row.appear_condition || ""} disabled={disabled} onChange={(e)=>patchRow("camp_npcs",campNpcs,index,{appear_condition:e.target.value})}/>
              <input placeholder="Условие исчезновения" value={row.disappear_condition || ""} disabled={disabled} onChange={(e)=>patchRow("camp_npcs",campNpcs,index,{disappear_condition:e.target.value})}/>
              <input placeholder="Расписание" value={row.schedule || ""} disabled={disabled} onChange={(e)=>patchRow("camp_npcs",campNpcs,index,{schedule:e.target.value})}/>
              <input placeholder="Текст встречи" value={row.meeting_text || ""} disabled={disabled} onChange={(e)=>patchRow("camp_npcs",campNpcs,index,{meeting_text:e.target.value})}/>
              {!disabled?<button type="button" className="ntv2-btn ntv2-btn-danger" onClick={()=>set("camp_npcs",campNpcs.filter((_,i)=>i!==index))}>×</button>:null}
            </div>)}
            {!disabled?<button type="button" className="ntv2-btn" onClick={()=>set("camp_npcs",[...campNpcs,{npc_id:"",role:"guide",permanent:true,active:true}])}>＋ NPC</button>:null}
          </div>

          <div className="ntv2-panel">
            <h4 className="ntv2-subhead">Эффекты лагеря</h4>
            {effectLinks.map((row, index) => <div className="ntv2-list-row" key={index}>
              <select value={row.effect_id || ""} disabled={disabled} onChange={(e) => patchRow("effect_links", effectLinks, index, { effect_id: e.target.value })}><option value="">— эффект —</option>{effectOptions.map((o) => <option key={o.value} value={o.value}>{o.label} ({o.value})</option>)}</select>
              <select value={row.trigger || "on_rest"} disabled={disabled} onChange={(e) => patchRow("effect_links", effectLinks, index, { trigger: e.target.value })}><option value="on_enter">При входе</option><option value="on_rest">При отдыхе</option><option value="on_exit">При выходе</option><option value="passive">Постоянно</option></select>
              <input type="number" placeholder="длительность, сек" value={row.duration_seconds ?? ""} disabled={disabled} onChange={(e) => patchRow("effect_links", effectLinks, index, { duration_seconds: e.target.value })} />
              <input type="number" min="0" max="100" placeholder="шанс %" value={row.chance ?? 100} disabled={disabled} onChange={(e) => patchRow("effect_links", effectLinks, index, { chance: e.target.value })} />
              <input className="ntv2-mono" placeholder="защита: предмет" value={row.protection_item_id || ""} disabled={disabled} onChange={(e) => patchRow("effect_links", effectLinks, index, { protection_item_id: e.target.value })} />
              <input className="ntv2-mono" placeholder="защита: зелье" value={row.protection_potion_id || ""} disabled={disabled} onChange={(e) => patchRow("effect_links", effectLinks, index, { protection_potion_id: e.target.value })} />
              <input placeholder="текст наложения" value={row.apply_text || ""} disabled={disabled} onChange={(e) => patchRow("effect_links", effectLinks, index, { apply_text: e.target.value })} />
              <input placeholder="текст окончания" value={row.end_text || ""} disabled={disabled} onChange={(e) => patchRow("effect_links", effectLinks, index, { end_text: e.target.value })} />
              {!disabled ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => set("effect_links", effectLinks.filter((_, i) => i !== index))}>×</button> : null}
            </div>)}
            {!disabled ? <button type="button" className="ntv2-btn" onClick={() => set("effect_links", [...effectLinks, { effect_id: "", trigger: "on_rest", duration_seconds: 0, active: true }])}>＋ Эффект</button> : null}
          </div>

          <div className="ntv2-panel">
            <h4 className="ntv2-subhead">События лагеря</h4>
            {campEvents.map((row, index) => <div className="ntv2-list-row" key={index}>
              <input className="ntv2-mono" placeholder="event_id" value={row.event_id || ""} disabled={disabled} onChange={(e) => patchRow("camp_events", campEvents, index, { event_id: e.target.value })} />
              <input placeholder="Название" value={row.name || ""} disabled={disabled} onChange={(e) => patchRow("camp_events", campEvents, index, { name: e.target.value })} />
              <input placeholder="Тип события" value={row.event_type || ""} disabled={disabled} onChange={(e) => patchRow("camp_events", campEvents, index, { event_type: e.target.value })} />
              <select value={row.trigger || "on_rest"} disabled={disabled} onChange={(e) => patchRow("camp_events", campEvents, index, { trigger: e.target.value })}><option value="on_enter">При входе</option><option value="on_rest">При отдыхе</option><option value="on_exit">При выходе</option></select>
              <input type="number" min="0" max="100" placeholder="шанс %" value={row.chance ?? 100} disabled={disabled} onChange={(e) => patchRow("camp_events", campEvents, index, { chance: e.target.value })} />
              <input type="number" min="0" placeholder="вес" value={row.weight ?? 1} disabled={disabled} onChange={(e) => patchRow("camp_events", campEvents, index, { weight: e.target.value })} />
              <input placeholder="Условия" value={row.conditions || ""} disabled={disabled} onChange={(e) => patchRow("camp_events", campEvents, index, { conditions: e.target.value })} />
              <input type="number" min="0" placeholder="лимит/нед." value={row.weekly_limit ?? 0} disabled={disabled} onChange={(e) => patchRow("camp_events", campEvents, index, { weekly_limit: e.target.value })} />
              <input type="number" min="0" placeholder="лимит/день" value={row.daily_limit ?? 0} disabled={disabled} onChange={(e) => patchRow("camp_events", campEvents, index, { daily_limit: e.target.value })} />
              {!disabled ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => set("camp_events", campEvents.filter((_, i) => i !== index))}>×</button> : null}
            </div>)}
            {!disabled ? <button type="button" className="ntv2-btn" onClick={() => set("camp_events", [...campEvents, { event_id: "", trigger: "on_rest", chance: 100, active: true }])}>＋ Событие</button> : null}
          </div>

          <div className="ntv2-panel">
            <h4 className="ntv2-subhead">Недельные лимиты лагеря</h4>
            {weeklyLimits.map((row, index) => <div className="ntv2-list-row" key={index}>
              <input className="ntv2-mono" placeholder="limit_id" value={row.id || ""} disabled={disabled} onChange={(e) => patchRow("weekly_limits", weeklyLimits, index, { id: e.target.value })} />
              <select value={row.limit_type || "rest"} disabled={disabled} onChange={(e) => patchRow("weekly_limits", weeklyLimits, index, { limit_type: e.target.value })}><option value="rest">Отдых</option><option value="camp_event">Событие</option><option value="recovery">Восстановление</option><option value="service">Услуга</option><option value="reward">Награда</option></select>
              <input className="ntv2-mono" placeholder="ID объекта" value={row.object_id || ""} disabled={disabled} onChange={(e) => patchRow("weekly_limits", weeklyLimits, index, { object_id: e.target.value })} />
              <input type="number" min="0" placeholder="макс./неделю" value={row.max_per_week ?? 0} disabled={disabled} onChange={(e) => patchRow("weekly_limits", weeklyLimits, index, { max_per_week: e.target.value })} />
              <input placeholder="текст исчерпания" value={row.exhausted_text || ""} disabled={disabled} onChange={(e) => patchRow("weekly_limits", weeklyLimits, index, { exhausted_text: e.target.value })} />
              <input placeholder="Поведение после исчерпания" value={row.after_exhaustion || ""} disabled={disabled} onChange={(e) => patchRow("weekly_limits", weeklyLimits, index, { after_exhaustion: e.target.value })} />
              <input placeholder="Сброс лимита" value={row.reset_rule || "weekly"} disabled={disabled} onChange={(e) => patchRow("weekly_limits", weeklyLimits, index, { reset_rule: e.target.value })} />
              <label className="ntv2-check"><input type="checkbox" checked={Boolean(row.show_admin)} disabled={disabled} onChange={(e) => patchRow("weekly_limits", weeklyLimits, index, { show_admin: e.target.checked })} /> Админу</label>
              <label className="ntv2-check"><input type="checkbox" checked={Boolean(row.hide_player)} disabled={disabled} onChange={(e) => patchRow("weekly_limits", weeklyLimits, index, { hide_player: e.target.checked })} /> Скрыть</label>
              {!disabled ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => set("weekly_limits", weeklyLimits.filter((_, i) => i !== index))}>×</button> : null}
            </div>)}
            {!disabled ? <button type="button" className="ntv2-btn" onClick={() => set("weekly_limits", [...weeklyLimits, { id: `rest_${weeklyLimits.length + 1}`, limit_type: "rest", max_per_week: 1, exhausted_text: "" }])}>＋ Лимит</button> : null}
          </div>

          <div className="ntv2-panel">
            <h4 className="ntv2-subhead">Предметы лагеря</h4>
            {campItems.map((row, index) => <div className="ntv2-list-row" key={index}>
              <input className="ntv2-mono" placeholder="item_id" value={row.item_id || ""} disabled={disabled} onChange={(e) => patchRow("items", campItems, index, { item_id: e.target.value })} />
              <input placeholder="Название" value={row.name || ""} disabled={disabled} onChange={(e) => patchRow("items", campItems, index, { name: e.target.value })} />
              <input placeholder="роль" value={row.role || ""} disabled={disabled} onChange={(e) => patchRow("items", campItems, index, { role: e.target.value })} />
              <input type="number" min="1" placeholder="количество" value={row.amount ?? 1} disabled={disabled} onChange={(e) => patchRow("items", campItems, index, { amount: e.target.value })} />
              <label className="ntv2-check"><input type="checkbox" checked={Boolean(row.consumed)} disabled={disabled} onChange={(e) => patchRow("items", campItems, index, { consumed: e.target.checked })} /> Расходуется</label>
              <label className="ntv2-check"><input type="checkbox" checked={Boolean(row.required)} disabled={disabled} onChange={(e) => patchRow("items", campItems, index, { required: e.target.checked })} /> Требуется</label>
              <label className="ntv2-check"><input type="checkbox" checked={Boolean(row.issued)} disabled={disabled} onChange={(e) => patchRow("items", campItems, index, { issued: e.target.checked })} /> Выдаётся</label>
              <label className="ntv2-check"><input type="checkbox" checked={Boolean(row.sold)} disabled={disabled} onChange={(e) => patchRow("items", campItems, index, { sold: e.target.checked })} /> Продаётся</label>
              <label className="ntv2-check"><input type="checkbox" checked={Boolean(row.bought)} disabled={disabled} onChange={(e) => patchRow("items", campItems, index, { bought: e.target.checked })} /> Покупается</label>
              <input placeholder="ID услуги" value={row.used_in_service || ""} disabled={disabled} onChange={(e) => patchRow("items", campItems, index, { used_in_service: e.target.value })} />
              <input placeholder="ID события" value={row.used_in_event || ""} disabled={disabled} onChange={(e) => patchRow("items", campItems, index, { used_in_event: e.target.value })} />
              {!disabled ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => set("items", campItems.filter((_, i) => i !== index))}>×</button> : null}
            </div>)}
            {!disabled ? <button type="button" className="ntv2-btn" onClick={() => set("items", [...campItems, { item_id: "", role: "required", amount: 1, consumed: false, active: true }])}>＋ Предмет</button> : null}
          </div>

          <div className="ntv2-panel">
            <h4 className="ntv2-subhead">Тексты бота</h4>
            {[["entry_text", "Вход"], ["exit_text", "Выход"], ["inspect_text", "Осмотр"], ["rest_text", "Отдых"], ["rest_start_text", "Начало отдыха"], ["rest_complete_text", "Завершение отдыха"], ["rest_interrupted_text", "Прерванный отдых"], ["recovery_hp_text", "Восстановление HP"], ["recovery_mana_text", "Восстановление маны"], ["recovery_spirit_text", "Восстановление духа"], ["recovery_energy_text", "Восстановление энергии"], ["death_text", "Смерть"], ["death_return_text", "Возврат после смерти"], ["access_denied_text", "Недоступность"], ["closed_text", "Закрытый лагерь"], ["missing_item_text", "Нет предмета"], ["not_enough_money_text", "Нет денег"], ["danger_text", "Опасность"], ["safe_text", "Безопасность"], ["npc_appearance_text", "Появление NPC"], ["no_services_text", "Нет услуг"], ["limit_exhausted_text", "Лимит исчерпан"]].map(([key, label]) => (
              <Field label={label} key={key}><EmojiTextarea rows={2} value={d[key] || ""} disabled={disabled} onChange={(value) => set(key, value)} /></Field>
            ))}
          </div>

          <div className="ntv2-panel">
            <h4 className="ntv2-subhead">Доступные действия</h4>
            <div className="ntv2-form-row" style={{ flexWrap: "wrap", gap: 10 }}>
              {(meta.campActions || []).map((a) => (
                <label className="ntv2-check" key={a}><input type="checkbox" checked={actions.includes(a)} disabled={disabled} onChange={() => toggleAction(a)} /> {a}</label>
              ))}
            </div>
          </div>
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
          {!editing.isNew ? <button type="button" className="ntv2-btn" onClick={async () => {
            const p = await guarded(() => fetchCampUsage(editing.id));
            if (p?.usage) setUsage(p.usage);
          }}>Где используется</button> : null}
          {!editing.isNew && can.publish ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => setConfirm({ title: "Опубликовать лагерь?", dangerous: true, confirmLabel: "Опубликовать", body: <p>Лагерь будет проверен и опубликован.</p>, run: async (r) => { await guarded(() => campLifecycle(editing.id, "publish", r), "Опубликовано."); await refreshEditing(); } })}>Опубликовать</button> : null}
          {!editing.isNew && can.disable && editing.status === "published" ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => setConfirm({ title: "Отключить?", dangerous: true, confirmLabel: "Отключить", body: <p>Лагерь перестанет быть доступен.</p>, run: async (r) => { await guarded(() => campLifecycle(editing.id, "disable", r), "Отключено."); await refreshEditing(); } })}>Отключить</button> : null}
          {!editing.isNew && can.archive ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => setConfirm({ title: "В архив?", dangerous: true, confirmLabel: "В архив", body: <p>Лагерь уйдёт в архив.</p>, run: async (r) => { await guarded(() => campLifecycle(editing.id, "archive", r), "В архиве."); await refreshEditing(); } })}>В архив</button> : null}
          {!editing.isNew && can.del ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={async () => {
            const p = await guarded(() => fetchCampUsage(editing.id));
            if (p?.usage?.total) { setUsage(p.usage); return; }
            setConfirm({ title: "Удалить лагерь?", dangerous: true, confirmLabel: "Удалить", requireConfirmText: editing.id, body: <p>Полное безвозвратное удаление лагеря.</p>, run: async (r) => { await guarded(() => deleteCamp(editing.id, editing.id, r), "Удалено."); setEditing(null); await load(); } });
          }}>Удалить</button> : null}
        </div>

        {usage ? <div className={`ntv2-panel ${usage.total ? "ntv2-danger-zone" : ""}`}>
          <h4 className="ntv2-subhead">Где используется</h4>
          {!usage.total ? <p className="ntv2-hint">Связей нет.</p> : <div className="ntv2-list">{usage.items.map((row, index) => (
            <div className="ntv2-list-row" key={`${row.kind}:${row.id}:${index}`}><span className="ntv2-badge">{row.kind}</span><b>{row.name}</b><span className="ntv2-mono">{row.id}</span><span className="ntv2-hint">{row.path}</span></div>
          ))}</div>}
        </div> : null}

        {!editing.isNew ? <VersionHistory base="camps" id={editing.id} canRollback={can.edit && (editing.status !== "published" || can.publish)} onRolledBack={refreshEditing} /> : null}

        <ConfirmModal open={Boolean(confirm)} title={confirm?.title} body={confirm?.body} dangerous={confirm?.dangerous} confirmLabel={confirm?.confirmLabel} requireReason requireConfirmText={confirm?.requireConfirmText || ""}
          onConfirm={async (r) => { await confirm.run(r); setConfirm(null); }} onCancel={() => setConfirm(null)} />
      </section>
    );
  }

  return (
    <section className="ntv2-section">
      <h2>Конструктор лагеря</h2>
      <div className="ntv2-filters">
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="">Все статусы</option>
          {statuses.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
        </select>
        {can.create ? <button type="button" className="ntv2-btn ntv2-btn-primary" onClick={startCreate}>＋ Новый лагерь</button> : null}
        {can.publish ? <button type="button" className="ntv2-btn" onClick={() => setConfirm({ title: "Импортировать существующие лагеря?", dangerous: true, confirmLabel: "Импортировать", body: <p>Статического источника лагерей нет — будет показано напоминание создать их вручную.</p>, run: async (r) => { const p = await guarded(() => importCamps("new", r), "Импорт выполнен."); if (p?.report) { await load(); window.alert("Источника лагерей нет — создайте лагеря вручную и привяжите к локациям."); } } })}>Импортировать существующие</button> : null}
        <SearchBox value={query} onChange={setQuery} />
      </div>
      {!list.length ? <p className="ntv2-hint">Лагерей пока нет. Создайте новый.</p> : null}
      <NoResults items={list} query={query} />
      <div className="ntv2-list">
        {filterEntities(list, query).map((item) => (
          <button key={item.id} type="button" className="ntv2-list-row ntv2-player-row" onClick={() => openItem(item.id)}>
            <b>{item.data?.name || item.id}</b>
            <span className="ntv2-mono">{item.id}</span>
            <span className={`ntv2-badge ${STATUS_TONE[item.status] || ""}`}>{statusLabel(item.status)}</span>
            {item.data?.camp_type ? <span className="ntv2-hint">{CAMP_TYPE_LABEL[item.data.camp_type] || item.data.camp_type}</span> : null}
          </button>
        ))}
      </div>
    </section>
  );
}
