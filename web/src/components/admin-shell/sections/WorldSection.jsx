import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  archiveWorldItem,
  createWorldItem,
  deleteWorldItem,
  disableWorldItem,
  discardWorldDraft,
  editWorldDraft,
  fetchWorldHistory,
  fetchWorldUsage,
  fetchWorldItems,
  fetchWorldMeta,
  fetchLocationLimitRuntime,
  importExistingContent,
  mobTestBattle,
  previewWorldItem,
  publishWorldDraft,
  publishWorldItem,
  rollbackWorldItem,
  testRunWorldItem,
  setLocationLimitRemaining,
  updateWorldItem,
  validateWorldItem,
} from "../../../api/adminWorldApi.js";
import { loadCatalog } from "../../../api/adminApi.js";
import { fetchFormulas } from "../../../api/adminFormulaApi.js";
import { fetchEffects } from "../../../api/adminEffectApi.js";
import { trOption, tr, CURRENCY } from "../../../i18n/adminLabels.js";
import { ConfirmModal } from "../ConfirmModal.jsx";
import { TechnicalData } from "../TechnicalData.jsx";
import { MessageComposer } from "../MessageComposer.jsx";
import { SearchBox, NoResults, filterEntities } from "../SearchFilter.jsx";

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
  // Глубина поиска (ТЗ 09 §19): необязательная настройка.
  search_depth_enabled: false, search_depth_start: 1, search_depth_max: 0, search_depth_formula_id: "",
  show_search_depth: false, search_depth_text: "", search_depth_thresholds: [],
};

const EMPTY_MOB = {
  name: "", player_name:"",system_name:"",short_description:"",full_description:"",technical_description:"", type: "beast", description: "", image: "",icon:"",mob_rank:"normal",family:"",faction:"",tags:[],
  level:1,min_level: 1, max_level: 5,scale_to_player_level:false,hp: 100,mana:0,spirit:0,energy:0,
  phys_damage: 0, mag_damage: 0, accuracy: 0, evasion: 0,
  phys_defense: 0, mag_defense: 0,armor:0,crit_chance: 0, crit_damage: 0,initiative:0,player_escape_chance:100,escape_forbidden:false,actions_per_turn:1,main_action:"attack",extra_action:"",
  strength:0,agility:0,endurance:0,intelligence:0,wisdom:0,perception:0,
  experience: 0, coins: 0, spawn_chance: 100, can_be_enhanced: false, damage_formula_id: "", exp_formula_id: "",
  locations: "", drop: [],
};

const EMPTY_BUTTON = {
  text: "", owner_location: "", owner_sublocation: "", owner_event: "", owner_npc: "", owner_dialogue: "", action: "goto_location", target: "",
  show_condition: "", order: 1, uses_energy: false, starts_timer: false,
  starts_event: false, starts_battle: false, show_telegram: true, show_vk: true,
  system_name: "", admin_description: "", button_type: "transition", category: "world", icon: "", color: "", tags: [],
  show_site: false, show_profile: false, hidden: false, temporary: false, one_time: false, confirmation: false,
  min_level: 0, max_level: 0, show_required_item_id: "", required_quest_id: "", required_achievement_id: "",
  required_reputation_id: "", min_reputation: 0, required_effect_id: "", hidden_by_effect_id: "",
  required_hidden_reputation_id:"",min_hidden_reputation:0,required_fine_id:"",hidden_by_fine_id:"",show_admin_only:false,show_moderator_only:false,
  button_group:"",row:0,row_position:0,main_menu:false,bottom_keyboard:false,inline_button:false,profile_button:false,admin_button:false,send_mode:"single",
  energy_cost: 0, give_item_id: "", give_item_amount: 1, take_item_id: "", take_item_amount: 1,
  apply_effect_id: "", remove_effect_id: "", open_access: "", message: "", error_text: "",
  not_enough_energy_text: "", unavailable_text: "", confirm_text: "", cancel_text: "",
};

const EMPTY_TRANSITION = {
  name: "", from_location: "", to_location: "", access_condition: "always",
  cost: 0, required_item: "", required_quest: "", requires_energy: false,
  allowed_with_fine: false, allowed_in_battle: false, allowed_during_timer: false,
};

const EMPTY_EVENT = {
  name: "", text: "", location: "", type: "found_item", result: "give_item",
  outcome_type: "", chance: 25, chance_formula_id: "", cooldown: 0, min_level: "", max_level: "",
  required_item: "", consumed_item: "", given_item: "", battle_mob: "",
  effect: "", repeatable: true, rewards: [], losses: [], consequences: [],
};

const EMPTY_NPC = {
  name: "", player_name: "", system_name: "", role: "", roles: [], npc_kind: "regular",
  faction: "", reputation_group: "", location: "", sublocation_id: "", additional_locations: [],
  short_description: "", description: "", technical_description: "", hidden_description: "", image: "", icon: "", tags: [],
  first_message: "", functions: [],
  // Вид NPC (доп.§3) + привязка к событиям (доп.§4).
  npc_kind: "regular", event_ids: [], quest_ids: [], asks_questions: false, special_type: "",
  // Торговля (доп.§12).
  trade: { sells: [], buys: [], stock_type: "shared", can_buy_from_player: true, can_sell_to_player: true },
  dialogues: [], services: [], schedule: [], access_conditions: [], combat_mob_id: "",
  min_level: 0, max_level: 0, required_race: "", required_item_id: "", required_reputation_id: "", min_reputation: 0,
  denied_text: "", schedule_closed_text: "", hidden_until_condition: false, temporary: false,
  appear_condition:"", disappear_condition:"", event_appear_id:"", event_disappear_id:"", moves_between_locations:false,
  required_hidden_reputation_id:"", min_hidden_reputation:0, combat_skills:[], combat_drop:[], combat_reward:"", kill_fine_id:"", kill_consequences:[],
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

function FormulaSelect({ value, onChange, options, disabled }) {
  return <select value={value || ""} disabled={disabled} onChange={(e) => onChange(e.target.value)}><option value="">— фиксированное значение —</option>{(options || []).map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</select>;
}

function LocationForm({ value, onChange, meta, disabled, uploadKey, formulaOptions }) {
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
        <Field label="Тип"><select value={value.type} disabled={disabled} onChange={(e) => set("type", e.target.value)}>{(meta.locationTypes || []).map((t) => <option key={t} value={t}>{trOption("locationTypes", t)}</option>)}</select></Field>
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
      <MessageComposer label="Сообщение при входе (изображение/формат/предпросмотр)" value={value.scene_message} category="locations" uploadKey={`${uploadKey || "location"}_msg`} disabled={disabled} onChange={(v) => set("scene_message", v)} />
      <fieldset className="ntv2-fieldset">
        <legend>🔎 Глубина поиска</legend>
        <div className="ntv2-form-row" style={{ gap: 14 }}>
          {flag("search_depth_enabled", "Включить глубину поиска")}
          {flag("show_search_depth", "Показывать игроку")}
        </div>
        {value.search_depth_enabled ? (
          <>
            <div className="ntv2-form-row">
              <Field label="Стартовая глубина"><input type="number" value={value.search_depth_start} disabled={disabled} onChange={(e) => set("search_depth_start", e.target.value)} /></Field>
              <Field label="Макс. глубина (0 = без лимита)"><input type="number" value={value.search_depth_max} disabled={disabled} onChange={(e) => set("search_depth_max", e.target.value)} /></Field>
              <Field label="Формула максимальной глубины"><FormulaSelect value={value.search_depth_formula_id} onChange={(v) => set("search_depth_formula_id", v)} options={formulaOptions} disabled={disabled} /></Field>
            </div>
            <Field label="Текст для игрока (при показе глубины)"><textarea rows={2} value={value.search_depth_text} disabled={disabled} onChange={(e) => set("search_depth_text", e.target.value)} /></Field>
            <SearchDepthThresholdsEditor rows={value.search_depth_thresholds || []} disabled={disabled} onChange={(rows) => set("search_depth_thresholds", rows)} />
          </>
        ) : null}
      </fieldset>
    </div>
  );
}

function SearchDepthThresholdsEditor({ rows, disabled, onChange }) {
  const update = (idx, key, val) => onChange(rows.map((r, i) => (i === idx ? { ...r, [key]: val } : r)));
  const add = () => onChange([...rows, { min_depth: "", max_depth: "", note: "" }]);
  const remove = (idx) => onChange(rows.filter((_, i) => i !== idx));
  return (
    <div className="ntv2-depth-thresholds">
      <div className="ntv2-field-label">Пороги глубины (события/ресурсы/мобы по глубине, §19.6)</div>
      {rows.map((row, idx) => (
        <div className="ntv2-form-row" key={idx} style={{ gap: 8, alignItems: "flex-end" }}>
          <Field label="От глубины"><input type="number" value={row.min_depth ?? ""} disabled={disabled} onChange={(e) => update(idx, "min_depth", e.target.value)} /></Field>
          <Field label="До (0 = ∞)"><input type="number" value={row.max_depth ?? ""} disabled={disabled} onChange={(e) => update(idx, "max_depth", e.target.value)} /></Field>
          <Field label="Что открывается (заметка)"><input value={row.note ?? ""} disabled={disabled} onChange={(e) => update(idx, "note", e.target.value)} /></Field>
          {!disabled ? <button type="button" className="ntv2-btn-mini" onClick={() => remove(idx)}>✕</button> : null}
        </div>
      ))}
      {!disabled ? <button type="button" className="ntv2-btn-mini" onClick={add}>＋ Порог</button> : null}
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
            <input placeholder="Название" value={row.name || ""} disabled={disabled} onChange={(e)=>setRow(i,{name:e.target.value})}/>
            <input type="number" title="шанс %" style={{ width: 80 }} value={row.chance} disabled={disabled} onChange={(e) => setRow(i, { chance: e.target.value })} />
            <input type="number" title="мин" style={{ width: 70 }} value={row.min_count} disabled={disabled} onChange={(e) => setRow(i, { min_count: e.target.value })} />
            <input type="number" title="макс" style={{ width: 70 }} value={row.max_count} disabled={disabled} onChange={(e) => setRow(i, { max_count: e.target.value })} />
            <input placeholder="Качество" value={row.quality || ""} disabled={disabled} onChange={(e)=>setRow(i,{quality:e.target.value})}/>
            <input placeholder="Группа" value={row.drop_group || ""} disabled={disabled} onChange={(e)=>setRow(i,{drop_group:e.target.value})}/>
            <input placeholder="Условие" value={row.condition || ""} disabled={disabled} onChange={(e)=>setRow(i,{condition:e.target.value})}/>
            <input type="number" placeholder="Лимит" value={row.drop_limit ?? ""} disabled={disabled} onChange={(e)=>setRow(i,{drop_limit:e.target.value})}/>
            <label className="ntv2-check"><input type="checkbox" checked={Boolean(row.bind_on_receive)} disabled={disabled} onChange={(e)=>setRow(i,{bind_on_receive:e.target.checked})}/> Привязать</label>
            <input placeholder="Текст выпадения" value={row.drop_text || ""} disabled={disabled} onChange={(e)=>setRow(i,{drop_text:e.target.value})}/>
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

function MobForm({ value, onChange, meta, disabled, formulaOptions }) {
  const set = (k, v) => onChange({ ...value, [k]: v });
  const num = (key, label) => <Field label={label} key={key}><input type="number" value={value[key]} disabled={disabled} onChange={(e) => set(key, e.target.value)} /></Field>;
  return (
    <div className="ntv2-world-form">
      <div className="ntv2-form-row">
        <Field label="Название"><input value={value.name} disabled={disabled} onChange={(e) => set("name", e.target.value)} /></Field>
        <Field label="Название игроку"><input value={value.player_name || ""} disabled={disabled} onChange={(e) => set("player_name", e.target.value)} /></Field>
        <Field label="Системное название"><input value={value.system_name || ""} disabled={disabled} onChange={(e) => set("system_name", e.target.value)} /></Field>
        <Field label="Тип"><select value={value.type} disabled={disabled} onChange={(e) => set("type", e.target.value)}>{(meta.mobTypes || []).map((t) => <option key={t} value={t}>{trOption("mobTypes", t)}</option>)}</select></Field>
        <Field label="Ранг"><input value={value.mob_rank || "normal"} disabled={disabled} onChange={(e) => set("mob_rank",e.target.value)}/></Field>
        <Field label="Семейство"><input value={value.family || ""} disabled={disabled} onChange={(e) => set("family",e.target.value)}/></Field>
        <Field label="Фракция"><input value={value.faction || ""} disabled={disabled} onChange={(e) => set("faction",e.target.value)}/></Field>
      </div>
      <div className="ntv2-form-row">{num("level","Уровень")}{num("min_level", "Ур. от")}{num("max_level", "Ур. до")}{num("hp", "HP")}{num("mana","Мана")}{num("spirit","Дух")}{num("energy","Энергия")}{num("spawn_chance", "Шанс появления %")}<label className="ntv2-check"><input type="checkbox" checked={Boolean(value.scale_to_player_level)} disabled={disabled} onChange={(e)=>set("scale_to_player_level",e.target.checked)}/> Масштабировать по игроку</label></div>
      <div className="ntv2-form-row">{num("phys_damage", "Физ. урон")}{num("mag_damage", "Маг. урон")}{num("accuracy", "Точность")}{num("evasion", "Уклонение")}</div>
      <div className="ntv2-form-row">{num("phys_defense", "Физ. защита")}{num("mag_defense", "Маг. защита")}{num("armor","Броня")}{num("crit_chance", "Крит %")}{num("crit_damage", "Крит урон")}{num("initiative","Инициатива")}{num("player_escape_chance","Шанс побега игрока")}{num("actions_per_turn","Действий за ход")}</div>
      <div className="ntv2-form-row">{num("strength","Сила")}{num("agility","Ловкость")}{num("endurance","Выносливость")}{num("intelligence","Интеллект")}{num("wisdom","Мудрость")}{num("perception","Восприятие")}<label className="ntv2-check"><input type="checkbox" checked={Boolean(value.escape_forbidden)} disabled={disabled} onChange={(e)=>set("escape_forbidden",e.target.checked)}/> Запрет побега</label></div>
      <div className="ntv2-form-row"><Field label="Основное действие"><input value={value.main_action || ""} disabled={disabled} onChange={(e)=>set("main_action",e.target.value)}/></Field><Field label="Дополнительное действие"><input value={value.extra_action || ""} disabled={disabled} onChange={(e)=>set("extra_action",e.target.value)}/></Field><Field label="Теги"><input value={(value.tags || []).join(", ")} disabled={disabled} onChange={(e)=>set("tags",e.target.value.split(",").map(x=>x.trim()).filter(Boolean))}/></Field></div>
      <div className="ntv2-form-row">{num("experience", "Опыт")}{num("coins", "Монеты")}
        <label className="ntv2-check"><input type="checkbox" checked={Boolean(value.can_be_enhanced)} disabled={disabled} onChange={(e) => set("can_be_enhanced", e.target.checked)} /> Может быть усиленным</label>
      </div>
      <div className="ntv2-form-row">{num("coins_min","Минимум монет")}{num("coins_max","Максимум монет")}{num("extra_reward_chance","Шанс доп. награды")}{num("experience_reduction_after_10","Снижение опыта после 10 ур.")}{num("rank_reward_multiplier","Множитель по рангу")}<Field label="Награда за первую победу"><textarea value={value.first_win_reward || ""} disabled={disabled} onChange={(e)=>set("first_win_reward",e.target.value)}/></Field><Field label="Награда за повторную победу"><textarea value={value.repeat_win_reward || ""} disabled={disabled} onChange={(e)=>set("repeat_win_reward",e.target.value)}/></Field></div>
      <div className="ntv2-form-row">
        <Field label="Формула урона"><FormulaSelect value={value.damage_formula_id} onChange={(v) => set("damage_formula_id", v)} options={formulaOptions} disabled={disabled} /></Field>
        <Field label="Формула опыта"><FormulaSelect value={value.exp_formula_id} onChange={(v) => set("exp_formula_id", v)} options={formulaOptions} disabled={disabled} /></Field>
      </div>
      <Field label="Локации появления (id через запятую)"><input value={value.locations} disabled={disabled} onChange={(e) => set("locations", e.target.value)} /></Field>
      <Field label="Короткое описание"><textarea rows={2} value={value.short_description || ""} disabled={disabled} onChange={(e) => set("short_description", e.target.value)} /></Field>
      <Field label="Полное описание"><textarea rows={3} value={value.full_description || value.description || ""} disabled={disabled} onChange={(e) => onChange({...value,full_description:e.target.value,description:e.target.value})} /></Field>
      <Field label="Техническое описание"><textarea rows={2} value={value.technical_description || ""} disabled={disabled} onChange={(e) => set("technical_description", e.target.value)} /></Field>
      <div className="ntv2-form-row"><Field label="Изображение (локальный путь)"><input value={value.image} disabled={disabled} onChange={(e) => set("image", e.target.value)} /></Field><Field label="Иконка"><input value={value.icon || ""} disabled={disabled} onChange={(e)=>set("icon",e.target.value)}/></Field></div>
      <DropEditor rows={value.drop} onChange={(drop) => set("drop", drop)} disabled={disabled} />
    </div>
  );
}

function EffectSelect({ value, onChange, options, disabled }) {
  return <select value={value || ""} disabled={disabled} onChange={(e) => onChange(e.target.value)}><option value="">— нет —</option>{(options || []).map((option) => <option key={option.value} value={option.value}>{option.label} ({option.value})</option>)}</select>;
}

function ButtonForm({ value, onChange, meta, disabled, locationOptions, refOptions, effectOptions }) {
  const set = (k, v) => onChange({ ...value, [k]: v });
  const flag = (key, label) => (
    <label className="ntv2-check" key={key}>
      <input type="checkbox" checked={Boolean(value[key])} disabled={disabled} onChange={(e) => set(key, e.target.checked)} /> {label}
    </label>
  );
  return (
    <div className="ntv2-world-form">
      <Field label="Текст кнопки"><input value={value.text} disabled={disabled} onChange={(e) => set("text", e.target.value)} /></Field>
      <div className="ntv2-form-row"><Field label="Системное название"><input value={value.system_name || ""} disabled={disabled} onChange={(e)=>set("system_name",e.target.value)}/></Field><Field label="Описание админу"><input value={value.admin_description || ""} disabled={disabled} onChange={(e)=>set("admin_description",e.target.value)}/></Field><Field label="Тип кнопки"><input value={value.button_type || ""} disabled={disabled} onChange={(e)=>set("button_type",e.target.value)}/></Field><Field label="Категория"><input value={value.category || ""} disabled={disabled} onChange={(e)=>set("category",e.target.value)}/></Field><Field label="Эмодзи"><input value={value.icon || ""} disabled={disabled} onChange={(e)=>set("icon",e.target.value)}/></Field><Field label="Цвет"><input value={value.color || ""} disabled={disabled} onChange={(e)=>set("color",e.target.value)}/></Field></div>
      <div className="ntv2-form-row">
        <Field label="Локация-владелец"><LocationSelect value={value.owner_location} onChange={(v) => set("owner_location", v)} options={locationOptions} disabled={disabled} /></Field>
        <Field label="Подлокация-владелец"><RefSelect value={value.owner_sublocation || ""} onChange={(v) => set("owner_sublocation", v)} options={refOptions.sublocation || []} disabled={disabled} /></Field>
        <Field label="Событие-владелец"><RefSelect value={value.owner_event || ""} onChange={(v) => set("owner_event", v)} options={refOptions.event || []} disabled={disabled} /></Field>
        <Field label="NPC-владелец"><RefSelect value={value.owner_npc || ""} onChange={(v) => set("owner_npc", v)} options={refOptions.npc || []} disabled={disabled} /></Field>
        <Field label="Действие"><select value={value.action} disabled={disabled} onChange={(e) => set("action", e.target.value)}>{(meta.buttonActions || []).map((a) => <option key={a} value={a}>{trOption("buttonActions", a)}</option>)}</select></Field>
        <Field label="Порядок"><input type="number" value={value.order} disabled={disabled} onChange={(e) => set("order", e.target.value)} /></Field>
      </div>
      {value.action === "goto_location" ? (
        <Field label="Куда ведёт"><LocationSelect value={value.target} onChange={(v) => set("target", v)} options={locationOptions} disabled={disabled} /></Field>
      ) : <Field label="ID цели / команда"><input className="ntv2-mono" value={value.target || ""} disabled={disabled} onChange={(e) => set("target", e.target.value)} /></Field>}
      <Field label="Условие показа"><input value={value.show_condition} disabled={disabled} onChange={(e) => set("show_condition", e.target.value)} /></Field>
      <div className="ntv2-form-row" style={{ gap: 14 }}>
        {flag("uses_energy", "Тратит энергию")}{flag("starts_timer", "Запускает таймер")}{flag("starts_event", "Запускает событие")}{flag("starts_battle", "Запускает бой")}
        {flag("show_telegram", "Telegram")}{flag("show_vk", "VK")}
      </div>
      <div className="ntv2-panel">
        <h4 className="ntv2-subhead">Отображение и условия</h4>
        <div className="ntv2-form-row" style={{ flexWrap: "wrap" }}>
          {flag("show_site", "Сайт")}{flag("show_profile", "Профиль")}{flag("hidden", "Скрытая")}{flag("temporary", "Временная")}{flag("one_time", "Одноразовая")}{flag("confirmation", "Подтверждение")}
        </div>
        <div className="ntv2-form-row">
          <Field label="Уровень от"><input type="number" value={value.min_level ?? 0} disabled={disabled} onChange={(e) => set("min_level", e.target.value)} /></Field>
          <Field label="Уровень до"><input type="number" value={value.max_level ?? 0} disabled={disabled} onChange={(e) => set("max_level", e.target.value)} /></Field>
          <Field label="Требуемый предмет"><input className="ntv2-mono" value={value.show_required_item_id || ""} disabled={disabled} onChange={(e) => set("show_required_item_id", e.target.value)} /></Field>
          <Field label="Квест"><input className="ntv2-mono" value={value.required_quest_id || ""} disabled={disabled} onChange={(e) => set("required_quest_id", e.target.value)} /></Field>
          <Field label="Достижение"><input className="ntv2-mono" value={value.required_achievement_id || ""} disabled={disabled} onChange={(e) => set("required_achievement_id", e.target.value)} /></Field>
        </div>
        <div className="ntv2-form-row">
          <Field label="Репутация"><input className="ntv2-mono" value={value.required_reputation_id || ""} disabled={disabled} onChange={(e) => set("required_reputation_id", e.target.value)} /></Field>
          <Field label="Мин. репутация"><input type="number" value={value.min_reputation ?? 0} disabled={disabled} onChange={(e) => set("min_reputation", e.target.value)} /></Field>
          <Field label="Требуемый эффект"><EffectSelect value={value.required_effect_id} onChange={(v) => set("required_effect_id", v)} options={effectOptions} disabled={disabled} /></Field>
          <Field label="Скрыть при эффекте"><EffectSelect value={value.hidden_by_effect_id} onChange={(v) => set("hidden_by_effect_id", v)} options={effectOptions} disabled={disabled} /></Field>
          <Field label="Скрытая репутация"><input value={value.required_hidden_reputation_id || ""} disabled={disabled} onChange={(e)=>set("required_hidden_reputation_id",e.target.value)}/></Field><Field label="Мин. скрытая"><input type="number" value={value.min_hidden_reputation ?? 0} disabled={disabled} onChange={(e)=>set("min_hidden_reputation",e.target.value)}/></Field><Field label="Показывать при штрафе"><input value={value.required_fine_id || ""} disabled={disabled} onChange={(e)=>set("required_fine_id",e.target.value)}/></Field><Field label="Скрывать при штрафе"><input value={value.hidden_by_fine_id || ""} disabled={disabled} onChange={(e)=>set("hidden_by_fine_id",e.target.value)}/></Field>
        </div>
      </div>
      <div className="ntv2-panel">
        <h4 className="ntv2-subhead">Последствия нажатия</h4>
        <div className="ntv2-form-row">
          <Field label="Энергия"><input type="number" value={value.energy_cost ?? 0} disabled={disabled} onChange={(e) => set("energy_cost", e.target.value)} /></Field>
          <Field label="Выдать item_id"><input className="ntv2-mono" value={value.give_item_id || ""} disabled={disabled} onChange={(e) => set("give_item_id", e.target.value)} /></Field>
          <Field label="Количество"><input type="number" value={value.give_item_amount ?? 1} disabled={disabled} onChange={(e) => set("give_item_amount", e.target.value)} /></Field>
          <Field label="Забрать item_id"><input className="ntv2-mono" value={value.take_item_id || ""} disabled={disabled} onChange={(e) => set("take_item_id", e.target.value)} /></Field>
          <Field label="Количество"><input type="number" value={value.take_item_amount ?? 1} disabled={disabled} onChange={(e) => set("take_item_amount", e.target.value)} /></Field>
        </div>
        <div className="ntv2-form-row">
          <Field label="Наложить эффект"><EffectSelect value={value.apply_effect_id} onChange={(v) => set("apply_effect_id", v)} options={effectOptions} disabled={disabled} /></Field>
          <Field label="Снять эффект"><EffectSelect value={value.remove_effect_id} onChange={(v) => set("remove_effect_id", v)} options={effectOptions} disabled={disabled} /></Field>
          <Field label="Открыть доступ"><input className="ntv2-mono" value={value.open_access || ""} disabled={disabled} onChange={(e) => set("open_access", e.target.value)} /></Field>
        </div>
      </div>
      <div className="ntv2-panel">
        <h4 className="ntv2-subhead">Сообщения</h4>
        <Field label="При нажатии"><textarea rows={2} value={value.message || ""} disabled={disabled} onChange={(e) => set("message", e.target.value)} /></Field>
        <Field label="Ошибка"><textarea rows={2} value={value.error_text || ""} disabled={disabled} onChange={(e) => set("error_text", e.target.value)} /></Field>
        <Field label="Не хватает энергии"><textarea rows={2} value={value.not_enough_energy_text || ""} disabled={disabled} onChange={(e) => set("not_enough_energy_text", e.target.value)} /></Field>
        <Field label="Недоступна"><textarea rows={2} value={value.unavailable_text || ""} disabled={disabled} onChange={(e) => set("unavailable_text", e.target.value)} /></Field>
        <Field label="Скрытая кнопка"><textarea rows={2} value={value.hidden_text || ""} disabled={disabled} onChange={(e)=>set("hidden_text",e.target.value)}/></Field><Field label="Подтверждение"><textarea rows={2} value={value.confirm_text || ""} disabled={disabled} onChange={(e)=>set("confirm_text",e.target.value)}/></Field><Field label="Отмена"><textarea rows={2} value={value.cancel_text || ""} disabled={disabled} onChange={(e)=>set("cancel_text",e.target.value)}/></Field><Field label="Режим отправки"><select value={value.send_mode || "single"} disabled={disabled} onChange={(e)=>set("send_mode",e.target.value)}><option value="single">Одним сообщением</option><option value="multiple">Несколькими</option><option value="edit">Редактировать текущее</option></select></Field>
      </div>
      <div className="ntv2-panel"><h4 className="ntv2-subhead">Расположение</h4><div className="ntv2-form-row"><Field label="Родительский диалог"><input value={value.owner_dialogue || ""} disabled={disabled} onChange={(e)=>set("owner_dialogue",e.target.value)}/></Field><Field label="Группа"><input value={value.button_group || ""} disabled={disabled} onChange={(e)=>set("button_group",e.target.value)}/></Field><Field label="Ряд"><input type="number" value={value.row ?? 0} disabled={disabled} onChange={(e)=>set("row",e.target.value)}/></Field><Field label="Позиция"><input type="number" value={value.row_position ?? 0} disabled={disabled} onChange={(e)=>set("row_position",e.target.value)}/></Field>{flag("main_menu","Главное меню")}{flag("bottom_keyboard","Нижняя клавиатура")}{flag("inline_button","Inline")}{flag("profile_button","Профиль")}{flag("admin_button","Админская")}</div></div>
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
        <Field label="Условие доступа"><select value={value.access_condition} disabled={disabled} onChange={(e) => set("access_condition", e.target.value)}>{(meta.accessConditions || []).map((c) => <option key={c} value={c}>{trOption("accessConditions", c)}</option>)}</select></Field>
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

function EventForm({ value, onChange, meta, disabled, refOptions, uploadKey, formulaOptions, effectOptions }) {
  const set = (k, v) => onChange({ ...value, [k]: v });
  const rewards = Array.isArray(value.rewards) ? value.rewards : [];
  const losses = Array.isArray(value.losses) ? value.losses : [];
  const consequences = Array.isArray(value.consequences) ? value.consequences : [];
  return (
    <div className="ntv2-world-form">
      <div className="ntv2-form-row">
        <Field label="Название"><input value={value.name} disabled={disabled} onChange={(e) => set("name", e.target.value)} /></Field>
        <Field label="Тип"><select value={value.type} disabled={disabled} onChange={(e) => set("type", e.target.value)}>{(meta.eventTypes || []).map((t) => <option key={t} value={t}>{trOption("eventTypes", t)}</option>)}</select></Field>
      </div>
      <RowEditor title="Награды события" rows={rewards} disabled={disabled} onChange={(rows) => set("rewards", rows)} blank={{ type: "item", object_id: "", amount: 1, chance: 100, text: "" }} render={(row, setRow) => <>
        <select value={row.type || "item"} disabled={disabled} onChange={(e) => setRow({ type: e.target.value })}>{["item","currency","experience","energy","hp","mana","spirit","stat_points","skill_points","reputation","hidden_reputation","location_access","effect","curse","achievement","fine"].map((type) => <option value={type} key={type}>{type}</option>)}</select>
        <input className="ntv2-mono" placeholder="ID объекта" value={row.object_id || ""} disabled={disabled} onChange={(e) => setRow({ object_id: e.target.value })} />
        <input type="number" min="0" placeholder="количество" value={row.amount ?? 1} disabled={disabled} onChange={(e) => setRow({ amount: e.target.value })} />
        <input type="number" min="0" max="100" placeholder="шанс %" value={row.chance ?? 100} disabled={disabled} onChange={(e) => setRow({ chance: e.target.value })} />
        <input placeholder="текст получения" value={row.text || ""} disabled={disabled} onChange={(e) => setRow({ text: e.target.value })} />
        <label className="ntv2-check"><input type="checkbox" checked={Boolean(row.bind_on_receive)} disabled={disabled} onChange={(e) => setRow({ bind_on_receive: e.target.checked })} /> Привязать</label>
      </>} />
      <RowEditor title="Потери события" rows={losses} disabled={disabled} onChange={(rows) => set("losses", rows)} blank={{ type: "hp", object_id: "", amount: 1, percent: false, text: "" }} render={(row, setRow) => <>
        <select value={row.type || "hp"} disabled={disabled} onChange={(e) => setRow({ type: e.target.value })}>{["hp","mana","spirit","energy","item","money","experience","reputation"].map((type) => <option value={type} key={type}>{type}</option>)}</select>
        <input className="ntv2-mono" placeholder="ID предмета/репутации" value={row.object_id || ""} disabled={disabled} onChange={(e) => setRow({ object_id: e.target.value })} />
        <input type="number" min="0" placeholder="значение" value={row.amount ?? 1} disabled={disabled} onChange={(e) => setRow({ amount: e.target.value })} />
        <label className="ntv2-check"><input type="checkbox" checked={Boolean(row.percent)} disabled={disabled} onChange={(e) => setRow({ percent: e.target.checked })} /> %</label>
        <input placeholder="текст потери" value={row.text || ""} disabled={disabled} onChange={(e) => setRow({ text: e.target.value })} />
      </>} />
      <RowEditor title="Последствия события" rows={consequences} disabled={disabled} onChange={(rows) => set("consequences", rows)} blank={{ type: "message", object_id: "", chance: 100, text: "" }} render={(row, setRow) => <>
        <select value={row.type || "message"} disabled={disabled} onChange={(e) => setRow({ type: e.target.value })}>{["next_event","open_npc","open_sublocation","open_location","open_access","close_access","apply_effect","remove_effect","start_battle","quest_progress","achievement","fine","message","chat_message"].map((type) => <option value={type} key={type}>{type}</option>)}</select>
        <input className="ntv2-mono" placeholder="ID цели" value={row.object_id || ""} disabled={disabled} onChange={(e) => setRow({ object_id: e.target.value })} />
        <input type="number" min="0" max="100" placeholder="шанс %" value={row.chance ?? 100} disabled={disabled} onChange={(e) => setRow({ chance: e.target.value })} />
        <input placeholder="текст" value={row.text || ""} disabled={disabled} onChange={(e) => setRow({ text: e.target.value })} />
        {row.type === "message" || row.type === "chat_message" ? <label className="ntv2-check"><input type="checkbox" checked={Boolean(row.deliver)} disabled={disabled} onChange={(e) => setRow({ deliver: e.target.checked })} /> В очередь сообщений</label> : null}
      </>} />
      <Field label="Формула шанса"><FormulaSelect value={value.chance_formula_id} onChange={(v) => set("chance_formula_id", v)} options={formulaOptions} disabled={disabled} /></Field>
      <Field label="Локация"><RefSelect value={value.location} onChange={(v) => set("location", v)} options={refOptions.location} disabled={disabled} /></Field>
      <div className="ntv2-form-row">
        <Field label="Подлокация"><RefSelect value={value.sublocation_id || ""} onChange={(v) => set("sublocation_id", v)} options={refOptions.sublocation || []} disabled={disabled} /></Field>
        <Field label="Узел подлокации (необязательно)"><input className="ntv2-mono" value={value.node_id || ""} disabled={disabled} onChange={(e) => set("node_id", e.target.value)} /></Field>
        <Field label="Кнопка запуска"><input value={value.button_text || ""} disabled={disabled} onChange={(e) => set("button_text", e.target.value)} /></Field>
        <Field label="Текст запуска"><input value={value.start_text || ""} disabled={disabled} onChange={(e) => set("start_text", e.target.value)} /></Field>
      </div>
      <div className="ntv2-panel">
        <h4 className="ntv2-subhead">Условия запуска</h4>
        <div className="ntv2-form-row">
          <Field label="Мин. энергия"><input type="number" min="0" value={value.min_energy ?? 0} disabled={disabled} onChange={(e) => set("min_energy", e.target.value)} /></Field>
          <Field label="Раса"><input className="ntv2-mono" value={value.required_race || ""} disabled={disabled} onChange={(e) => set("required_race", e.target.value)} /></Field>
          <Field label="Надетый предмет"><input className="ntv2-mono" value={value.required_equipped_item_id || ""} disabled={disabled} onChange={(e) => set("required_equipped_item_id", e.target.value)} /></Field>
          <Field label="Требуемый эффект"><input className="ntv2-mono" value={value.required_effect_id || ""} disabled={disabled} onChange={(e) => set("required_effect_id", e.target.value)} /></Field>
          <Field label="Запрещающий эффект"><input className="ntv2-mono" value={value.forbidden_effect_id || ""} disabled={disabled} onChange={(e) => set("forbidden_effect_id", e.target.value)} /></Field>
        </div>
        <div className="ntv2-form-row">
          <Field label="Репутация"><input className="ntv2-mono" value={value.required_reputation_id || ""} disabled={disabled} onChange={(e) => set("required_reputation_id", e.target.value)} /></Field>
          <Field label="Мин. репутация"><input type="number" value={value.min_reputation ?? 0} disabled={disabled} onChange={(e) => set("min_reputation", e.target.value)} /></Field>
          <Field label="Скрытая репутация"><input className="ntv2-mono" value={value.required_hidden_reputation_id || ""} disabled={disabled} onChange={(e) => set("required_hidden_reputation_id", e.target.value)} /></Field>
          <Field label="Мин. скрытая"><input type="number" value={value.min_hidden_reputation ?? 0} disabled={disabled} onChange={(e) => set("min_hidden_reputation", e.target.value)} /></Field>
          <Field label="Квест"><input className="ntv2-mono" value={value.required_quest_id || ""} disabled={disabled} onChange={(e) => set("required_quest_id", e.target.value)} /></Field>
          <Field label="Достижение"><input className="ntv2-mono" value={value.required_achievement_id || ""} disabled={disabled} onChange={(e) => set("required_achievement_id", e.target.value)} /></Field>
        </div>
        <div className="ntv2-form-row">
          <Field label="Время с"><input type="time" value={value.time_start || ""} disabled={disabled} onChange={(e) => set("time_start", e.target.value)} /></Field>
          <Field label="Время до"><input type="time" value={value.time_end || ""} disabled={disabled} onChange={(e) => set("time_end", e.target.value)} /></Field>
          <Field label="Дни недели (0–6)"><input value={(value.weekdays || []).join(",")} disabled={disabled} onChange={(e) => set("weekdays", e.target.value.split(",").map((x) => Number(x.trim())).filter((x) => Number.isInteger(x) && x >= 0 && x <= 6))} /></Field>
          <label className="ntv2-check"><input type="checkbox" checked={Boolean(value.requires_fine)} disabled={disabled} onChange={(e) => set("requires_fine", e.target.checked)} /> Нужен штраф</label>
          <label className="ntv2-check"><input type="checkbox" checked={Boolean(value.requires_no_fine)} disabled={disabled} onChange={(e) => set("requires_no_fine", e.target.checked)} /> Без штрафа</label>
          <label className="ntv2-check"><input type="checkbox" checked={Boolean(value.admin_only)} disabled={disabled} onChange={(e) => set("admin_only", e.target.checked)} /> Только админ</label>
        </div>
        <Field label="Текст невыполненного условия"><input value={value.access_denied_text || ""} disabled={disabled} onChange={(e) => set("access_denied_text", e.target.value)} /></Field>
      </div>
      <Field label="Текст игроку"><textarea rows={3} value={value.text} disabled={disabled} onChange={(e) => set("text", e.target.value)} /></Field>
      <div className="ntv2-form-row">
        <Field label="Шанс %"><input type="number" value={value.chance} disabled={disabled} onChange={(e) => set("chance", e.target.value)} /></Field>
        <Field label="Вес"><input type="number" value={value.weight ?? 0} disabled={disabled} onChange={(e) => set("weight", e.target.value)} /></Field>
        <Field label="Группа случайного выбора"><input className="ntv2-mono" value={value.event_group || ""} disabled={disabled} onChange={(e) => set("event_group", e.target.value)} /></Field>
        <Field label="Мин. шанс"><input type="number" min="0" max="100" value={value.min_chance ?? 0} disabled={disabled} onChange={(e) => set("min_chance", e.target.value)} /></Field>
        <Field label="Макс. шанс"><input type="number" min="0" max="100" value={value.max_chance ?? 100} disabled={disabled} onChange={(e) => set("max_chance", e.target.value)} /></Field>
        <Field label="Шанс после лимита"><input type="number" min="0" max="100" value={value.chance_after_limit ?? 0} disabled={disabled} onChange={(e) => set("chance_after_limit", e.target.value)} /></Field>
        <Field label="Перераспределение"><select value={value.redistribution_mode || "none"} disabled={disabled} onChange={(e) => set("redistribution_mode", e.target.value)}><option value="none">Не менять</option><option value="even">Поровну</option><option value="by_weight">По весу</option><option value="same_group">Внутри группы</option></select></Field>
        <Field label="Лимит запусков"><input type="number" min="0" value={value.limit ?? 0} disabled={disabled} onChange={(e) => set("limit", e.target.value)} /></Field>
        <Field label="Кулдаун (сек)"><input type="number" value={value.cooldown} disabled={disabled} onChange={(e) => set("cooldown", e.target.value)} /></Field>
        <Field label="Ур. от"><input type="number" value={value.min_level} disabled={disabled} onChange={(e) => set("min_level", e.target.value)} /></Field>
        <Field label="Ур. до"><input type="number" value={value.max_level} disabled={disabled} onChange={(e) => set("max_level", e.target.value)} /></Field>
      </div>
      <div className="ntv2-form-row">
        <Field label="Результат"><select value={value.result} disabled={disabled} onChange={(e) => set("result", e.target.value)}>{(meta.eventResultTypes || []).map((t) => <option key={t} value={t}>{trOption("eventResultTypes", t)}</option>)}</select></Field>
        <Field label="Тип исхода"><select value={value.outcome_type || ""} disabled={disabled} onChange={(e) => set("outcome_type", e.target.value)}><option value="">— не выбрано —</option>{(meta.eventOutcomeTypes || []).map((t) => <option key={t} value={t}>{trOption("eventOutcomeTypes", t)}</option>)}</select></Field>
      </div>
      <div className="ntv2-form-row">
        <Field label="Выдаваемый предмет (item_id)"><input className="ntv2-mono" value={value.given_item} disabled={disabled} onChange={(e) => set("given_item", e.target.value)} /></Field>
        <Field label="Требуемый предмет"><input className="ntv2-mono" value={value.required_item} disabled={disabled} onChange={(e) => set("required_item", e.target.value)} /></Field>
        <Field label="Списываемый предмет"><input className="ntv2-mono" value={value.consumed_item} disabled={disabled} onChange={(e) => set("consumed_item", e.target.value)} /></Field>
        <Field label="Требуемое открытие"><input className="ntv2-mono" value={value.required_unlock || ""} disabled={disabled} onChange={(e) => set("required_unlock", e.target.value)} /></Field>
      </div>
      <div className="ntv2-form-row">
        <Field label="Запускаемый бой (моб)"><RefSelect value={value.battle_mob} onChange={(v) => set("battle_mob", v)} options={refOptions.mob} disabled={disabled} /></Field>
        <Field label="Накладываемый эффект"><EffectSelect value={value.effect} onChange={(v) => set("effect", v)} options={effectOptions} disabled={disabled} /></Field>
        <label className="ntv2-check"><input type="checkbox" checked={Boolean(value.repeatable)} disabled={disabled} onChange={(e) => set("repeatable", e.target.checked)} /> Повторяемое</label>
      </div>
      <MessageComposer label="Сообщение игроку (изображение/формат/предпросмотр)" value={value.player_message} category="events" uploadKey={`${uploadKey || "event"}_msg`} disabled={disabled} onChange={(v) => set("player_message", v)} />
    </div>
  );
}

const TRADE_CURRENCIES = ["copper", "silver", "gold", "magic_gold", "ancient"];

function TradePanel({ value, set, disabled }) {
  const trade = value.trade || {};
  const setTrade = (patch) => set("trade", { ...trade, ...patch });
  const sideRows = (side) => (Array.isArray(trade[side]) ? trade[side] : []);
  const updRow = (side, i, patch) => setTrade({ [side]: sideRows(side).map((r, idx) => (idx === i ? { ...r, ...patch } : r)) });
  const addRow = (side) => setTrade({ [side]: [...sideRows(side), { item_id: "", price: "", currency: "copper", quantity: "", limit: "" }] });
  const delRow = (side, i) => setTrade({ [side]: sideRows(side).filter((_, idx) => idx !== i) });
  const sideTitle = { sells: "Продаёт игроку", buys: "Покупает у игрока" };
  return (
    <div className="ntv2-panel">
      <h4 className="ntv2-subhead">Торговля</h4>
      <div className="ntv2-form-row" style={{ gap: 14 }}>
        <Field label="Склад"><select value={trade.stock_type || "shared"} disabled={disabled} onChange={(e) => setTrade({ stock_type: e.target.value })}><option value="shared">Общий</option><option value="personal">Личный</option></select></Field>
        <label className="ntv2-check"><input type="checkbox" checked={trade.can_buy_from_player !== false} disabled={disabled} onChange={(e) => setTrade({ can_buy_from_player: e.target.checked })} /> Покупает у игрока</label>
        <label className="ntv2-check"><input type="checkbox" checked={trade.can_sell_to_player !== false} disabled={disabled} onChange={(e) => setTrade({ can_sell_to_player: e.target.checked })} /> Продаёт игроку</label>
      </div>
      {["sells", "buys"].map((side) => (
        <div key={side} style={{ marginTop: 8 }}>
          <div className="ntv2-hint">{sideTitle[side]} ({sideRows(side).length})</div>
          <div className="ntv2-list">
            {sideRows(side).map((row, i) => (
              <div className="ntv2-list-row" key={i}>
                <input className="ntv2-mono" placeholder="item_id" value={row.item_id || ""} disabled={disabled} onChange={(e) => updRow(side, i, { item_id: e.target.value })} />
                <input type="number" style={{ width: 100 }} placeholder="цена" value={row.price || ""} disabled={disabled} onChange={(e) => updRow(side, i, { price: e.target.value })} />
                <select value={row.currency || "copper"} disabled={disabled} onChange={(e) => updRow(side, i, { currency: e.target.value })}>{TRADE_CURRENCIES.map((c) => <option key={c} value={c}>{tr(CURRENCY, c)}</option>)}</select>
                {side === "sells" ? <input type="number" style={{ width: 80 }} title="кол-во" placeholder="кол-во" value={row.quantity || ""} disabled={disabled} onChange={(e) => updRow(side, i, { quantity: e.target.value })} /> : null}
                <input type="number" style={{ width: 80 }} title="лимит на игрока" placeholder="лимит" value={row.limit || ""} disabled={disabled} onChange={(e) => updRow(side, i, { limit: e.target.value })} />
                {!disabled ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => delRow(side, i)}>×</button> : null}
              </div>
            ))}
          </div>
          {!disabled ? <button type="button" className="ntv2-btn" style={{ marginTop: 6 }} onClick={() => addRow(side)}>＋ {sideTitle[side]}</button> : null}
        </div>
      ))}
    </div>
  );
}

function NpcForm({ value, onChange, meta, disabled, refOptions, uploadKey, effectOptions }) {
  const set = (k, v) => onChange({ ...value, [k]: v });
  const fns = Array.isArray(value.functions) ? value.functions : [];
  const toggleFn = (fn) => set("functions", fns.includes(fn) ? fns.filter((f) => f !== fn) : [...fns, fn]);
  const dialogues = Array.isArray(value.dialogues) ? value.dialogues : [];
  const schedule = Array.isArray(value.schedule) ? value.schedule : [];
  const services = Array.isArray(value.services) ? value.services : [];
  const patchService = (index, patch) => set("services", services.map((row, i) => i === index ? { ...row, ...patch } : row));
  const patchDialogue = (index, patch) => set("dialogues", dialogues.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  return (
    <div className="ntv2-world-form">
      <div className="ntv2-form-row">
        <Field label="Имя"><input value={value.name} disabled={disabled} onChange={(e) => set("name", e.target.value)} /></Field>
        <Field label="Роль"><input value={value.role} disabled={disabled} onChange={(e) => set("role", e.target.value)} /></Field>
        <Field label="Вид NPC"><select value={value.npc_kind || "regular"} disabled={disabled} onChange={(e) => set("npc_kind", e.target.value)}>{(meta.npcKinds || []).map((k) => <option key={k} value={k}>{trOption("npcKinds", k)}</option>)}</select></Field>
        <Field label="Локация"><RefSelect value={value.location} onChange={(v) => set("location", v)} options={refOptions.location} disabled={disabled} /></Field>
      </div>
      <div className="ntv2-form-row">
        <Field label="Имя для игрока"><input value={value.player_name || ""} disabled={disabled} onChange={(e) => set("player_name", e.target.value)} /></Field>
        <Field label="Системное имя"><input value={value.system_name || ""} disabled={disabled} onChange={(e) => set("system_name", e.target.value)} /></Field>
        <Field label="Фракция"><input value={value.faction || ""} disabled={disabled} onChange={(e) => set("faction", e.target.value)} /></Field>
        <Field label="Репутационная группа"><input value={value.reputation_group || ""} disabled={disabled} onChange={(e) => set("reputation_group", e.target.value)} /></Field>
        <Field label="Подлокация"><RefSelect value={value.sublocation_id || ""} onChange={(v) => set("sublocation_id", v)} options={refOptions.sublocation || []} disabled={disabled} /></Field>
      </div>
      <div className="ntv2-form-row">
        <Field label="Мин. уровень"><input type="number" value={value.min_level ?? 0} disabled={disabled} onChange={(e) => set("min_level", e.target.value)} /></Field>
        <Field label="Макс. уровень"><input type="number" value={value.max_level ?? 0} disabled={disabled} onChange={(e) => set("max_level", e.target.value)} /></Field>
        <Field label="Требуемая раса"><input className="ntv2-mono" value={value.required_race || ""} disabled={disabled} onChange={(e) => set("required_race", e.target.value)} /></Field>
        <Field label="Требуемый предмет"><input className="ntv2-mono" value={value.required_item_id || ""} disabled={disabled} onChange={(e) => set("required_item_id", e.target.value)} /></Field>
        <Field label="Репутация"><input className="ntv2-mono" value={value.required_reputation_id || ""} disabled={disabled} onChange={(e) => set("required_reputation_id", e.target.value)} /></Field>
        <Field label="Мин. репутация"><input type="number" value={value.min_reputation ?? 0} disabled={disabled} onChange={(e) => set("min_reputation", e.target.value)} /></Field>
      </div>
      <Field label="Текст недоступности"><textarea rows={2} value={value.denied_text || ""} disabled={disabled} onChange={(e) => set("denied_text", e.target.value)} /></Field>
      <Field label="Первое сообщение"><textarea rows={2} value={value.first_message} disabled={disabled} onChange={(e) => set("first_message", e.target.value)} /></Field>
      <Field label="Описание"><textarea rows={3} value={value.description} disabled={disabled} onChange={(e) => set("description", e.target.value)} /></Field>
      <Field label="Изображение (URL)"><input value={value.image} disabled={disabled} onChange={(e) => set("image", e.target.value)} /></Field>
      <div className="ntv2-form-row"><Field label="Короткое описание"><textarea value={value.short_description || ""} disabled={disabled} onChange={(e)=>set("short_description",e.target.value)}/></Field><Field label="Техническое описание"><textarea value={value.technical_description || ""} disabled={disabled} onChange={(e)=>set("technical_description",e.target.value)}/></Field><Field label="Скрытое описание"><textarea value={value.hidden_description || ""} disabled={disabled} onChange={(e)=>set("hidden_description",e.target.value)}/></Field><Field label="Иконка"><input value={value.icon || ""} disabled={disabled} onChange={(e)=>set("icon",e.target.value)}/></Field></div>
      <div className="ntv2-form-row"><Field label="Условие появления"><input value={value.appear_condition || ""} disabled={disabled} onChange={(e)=>set("appear_condition",e.target.value)}/></Field><Field label="Условие исчезновения"><input value={value.disappear_condition || ""} disabled={disabled} onChange={(e)=>set("disappear_condition",e.target.value)}/></Field><Field label="Появляется во время события"><input value={value.event_appear_id || ""} disabled={disabled} onChange={(e)=>set("event_appear_id",e.target.value)}/></Field><Field label="Исчезает после события"><input value={value.event_disappear_id || ""} disabled={disabled} onChange={(e)=>set("event_disappear_id",e.target.value)}/></Field><label className="ntv2-check"><input type="checkbox" checked={Boolean(value.moves_between_locations)} disabled={disabled} onChange={(e)=>set("moves_between_locations",e.target.checked)}/> Перемещается</label></div>
      {/* Привязка к событиям (доп.§4) + поля по виду NPC (доп.§3). */}
      <Field label="Привязан к событиям (event_id через запятую)"><input className="ntv2-mono" value={(value.event_ids || []).join(", ")} disabled={disabled} onChange={(e) => set("event_ids", e.target.value.split(",").map((s) => s.trim()).filter(Boolean))} /></Field>
      {value.npc_kind === "quest_giver" ? (
        <Field label="Задания (quest_id через запятую)"><input className="ntv2-mono" value={(value.quest_ids || []).join(", ")} disabled={disabled} onChange={(e) => set("quest_ids", e.target.value.split(",").map((s) => s.trim()).filter(Boolean))} /></Field>
      ) : null}
      {value.npc_kind === "questioner" ? (
        <label className="ntv2-check"><input type="checkbox" checked={Boolean(value.asks_questions)} disabled={disabled} onChange={(e) => set("asks_questions", e.target.checked)} /> Задаёт вопросы (вопросы/ответы настраиваются в событиях-диалогах)</label>
      ) : null}
      {value.npc_kind === "special" ? (
        <Field label="Тип особого NPC"><input value={value.special_type || ""} disabled={disabled} onChange={(e) => set("special_type", e.target.value)} /></Field>
      ) : null}
      {value.npc_kind === "trader" || fns.includes("shop") || fns.includes("trade") ? <TradePanel value={value} set={set} disabled={disabled} /> : null}
      <div className="ntv2-panel">
        <h4 className="ntv2-subhead">Функции</h4>
        <div className="ntv2-form-row" style={{ gap: 12 }}>
          {(meta.npcFunctions || []).map((fn) => (
            <label className="ntv2-check" key={fn}><input type="checkbox" checked={fns.includes(fn)} disabled={disabled} onChange={() => toggleFn(fn)} /> {trOption("npcFunctions", fn)}</label>
          ))}
        </div>
      </div>
      <div className="ntv2-panel"><h4 className="ntv2-subhead">Услуги NPC</h4>{services.map((row,index)=><div className="ntv2-list-row" key={index}>
        <input className="ntv2-mono" placeholder="ID услуги" value={row.service_id || ""} disabled={disabled} onChange={(e)=>patchService(index,{service_id:e.target.value})}/><input placeholder="Название" value={row.name || ""} disabled={disabled} onChange={(e)=>patchService(index,{name:e.target.value})}/>
        <select value={row.service_type || "shop"} disabled={disabled} onChange={(e)=>patchService(index,{service_type:e.target.value})}>{["shop","black_market","port_market","repair","craft","alchemy","enchant","remove_curse","healing","rest","rumors","find_player","assassin_order","board","reward","exchange_currency","exchange_items","pay_fines","training","guide","battle"].map(x=><option key={x}>{x}</option>)}</select>
        <input type="number" placeholder="Стоимость" value={row.cost ?? 0} disabled={disabled} onChange={(e)=>patchService(index,{cost:e.target.value})}/><input placeholder="Валюта" value={row.currency || "copper"} disabled={disabled} onChange={(e)=>patchService(index,{currency:e.target.value})}/><input className="ntv2-mono" placeholder="Требуемый предмет" value={row.required_item_id || ""} disabled={disabled} onChange={(e)=>patchService(index,{required_item_id:e.target.value})}/><input placeholder="Условие" value={row.condition || ""} disabled={disabled} onChange={(e)=>patchService(index,{condition:e.target.value})}/><input placeholder="Целевое действие" value={row.target_action || ""} disabled={disabled} onChange={(e)=>patchService(index,{target_action:e.target.value})}/><input placeholder="Успех" value={row.success_text || ""} disabled={disabled} onChange={(e)=>patchService(index,{success_text:e.target.value})}/><input placeholder="Ошибка" value={row.error_text || ""} disabled={disabled} onChange={(e)=>patchService(index,{error_text:e.target.value})}/><label className="ntv2-check"><input type="checkbox" checked={row.active!==false} disabled={disabled} onChange={(e)=>patchService(index,{active:e.target.checked})}/> Активна</label>{!disabled?<button type="button" className="ntv2-btn ntv2-btn-danger" onClick={()=>set("services",services.filter((_,i)=>i!==index))}>×</button>:null}
      </div>)}{!disabled?<button type="button" className="ntv2-btn" onClick={()=>set("services",[...services,{service_id:`service_${services.length+1}`,name:"Новая услуга",service_type:"shop",cost:0,currency:"copper",active:true}])}>＋ Услуга</button>:null}</div>
      <div className="ntv2-panel">
        <h4 className="ntv2-subhead">Диалоговые реплики</h4>
        {dialogues.map((row, index) => (
          <div className="ntv2-list-row" key={index} style={{ flexWrap: "wrap" }}>
            <input className="ntv2-mono" placeholder="ID реплики" value={row.id || ""} disabled={disabled} onChange={(e) => patchDialogue(index, { id: e.target.value })} />
            <select value={row.dialogue_type || "answer"} disabled={disabled} onChange={(e) => patchDialogue(index, { dialogue_type: e.target.value })}><option value="greeting">Приветствие</option><option value="question">Вопрос</option><option value="answer">Ответ</option><option value="quest">Квестовая</option><option value="trade">Торговая</option><option value="reputation">Репутационная</option><option value="hidden">Скрытая</option><option value="final">Финальная</option></select>
            <input className="ntv2-mono" placeholder="parent_id" value={row.parent_id || ""} disabled={disabled} onChange={(e) => patchDialogue(index, { parent_id: e.target.value })} />
            <input placeholder="Кнопка ответа игрока" value={row.player_button || ""} disabled={disabled} onChange={(e) => patchDialogue(index, { player_button: e.target.value })} />
            <input className="ntv2-mono" placeholder="next_id" value={row.next_id || ""} disabled={disabled} onChange={(e) => patchDialogue(index, { next_id: e.target.value })} />
            <textarea rows={2} placeholder="Текст NPC" value={row.npc_text || ""} disabled={disabled} onChange={(e) => patchDialogue(index, { npc_text: e.target.value })} />
            <input type="number" placeholder="мин. уровень" value={row.min_level ?? ""} disabled={disabled} onChange={(e) => patchDialogue(index, { min_level: e.target.value })} />
            <input className="ntv2-mono" placeholder="reward item_id" value={row.reward_item_id || ""} disabled={disabled} onChange={(e) => patchDialogue(index, { reward_item_id: e.target.value })} />
            <input type="number" placeholder="кол-во" value={row.reward_amount ?? 1} disabled={disabled} onChange={(e) => patchDialogue(index, { reward_amount: e.target.value })} />
            <EffectSelect value={row.effect_id} onChange={(v) => patchDialogue(index, { effect_id: v })} options={effectOptions} disabled={disabled} />
            <input className="ntv2-mono" placeholder="open_access" value={row.open_access || ""} disabled={disabled} onChange={(e) => patchDialogue(index, { open_access: e.target.value })} />
            <input className="ntv2-mono" placeholder="loss item_id" value={row.loss_item_id || ""} disabled={disabled} onChange={(e)=>patchDialogue(index,{loss_item_id:e.target.value})}/><input type="number" placeholder="потеря" value={row.loss_amount ?? ""} disabled={disabled} onChange={(e)=>patchDialogue(index,{loss_amount:e.target.value})}/><input className="ntv2-mono" placeholder="quest progress ID" value={row.quest_progress_id || ""} disabled={disabled} onChange={(e)=>patchDialogue(index,{quest_progress_id:e.target.value})}/><input className="ntv2-mono" placeholder="reputation ID" value={row.reputation_id || ""} disabled={disabled} onChange={(e)=>patchDialogue(index,{reputation_id:e.target.value})}/><input type="number" placeholder="Δ репутации" value={row.reputation_delta ?? ""} disabled={disabled} onChange={(e)=>patchDialogue(index,{reputation_delta:e.target.value})}/><input placeholder="Техническая заметка" value={row.technical_note || ""} disabled={disabled} onChange={(e)=>patchDialogue(index,{technical_note:e.target.value})}/>
            <label className="ntv2-check"><input type="checkbox" checked={Boolean(row.ends_dialogue)} disabled={disabled} onChange={(e) => patchDialogue(index, { ends_dialogue: e.target.checked })} /> Завершает</label>
            {!disabled ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => set("dialogues", dialogues.filter((_, i) => i !== index))}>×</button> : null}
          </div>
        ))}
        {!disabled ? <button type="button" className="ntv2-btn" onClick={() => set("dialogues", [...dialogues, { id: `line_${dialogues.length + 1}`, dialogue_type: dialogues.length ? "answer" : "greeting", parent_id: "", npc_text: "", player_button: "", next_id: "", ends_dialogue: false }])}>＋ Добавить реплику</button> : null}
      </div>
      <div className="ntv2-form-row">
        <Field label="Боевая версия (mob_id)"><RefSelect value={value.combat_mob_id || ""} onChange={(v) => set("combat_mob_id", v)} options={refOptions.mob || []} disabled={disabled} /></Field>
        <Field label="Доп. локации (ID через запятую)"><input value={(value.additional_locations || []).join(", ")} disabled={disabled} onChange={(e) => set("additional_locations", e.target.value.split(",").map((s) => s.trim()).filter(Boolean))} /></Field>
      </div>
      <div className="ntv2-form-row"><Field label="Скрытая репутация"><input value={value.required_hidden_reputation_id || ""} disabled={disabled} onChange={(e)=>set("required_hidden_reputation_id",e.target.value)}/></Field><Field label="Мин. скрытая репутация"><input type="number" value={value.min_hidden_reputation ?? 0} disabled={disabled} onChange={(e)=>set("min_hidden_reputation",e.target.value)}/></Field><Field label="Навыки NPC в бою"><input value={(value.combat_skills || []).join(", ")} disabled={disabled} onChange={(e)=>set("combat_skills",e.target.value.split(",").map(x=>x.trim()).filter(Boolean))}/></Field><Field label="Дроп NPC (JSON)"><textarea value={JSON.stringify(value.combat_drop || [])} disabled={disabled} onChange={(e)=>{try{set("combat_drop",JSON.parse(e.target.value||"[]"))}catch{}}}/></Field><Field label="Награда за победу"><input value={value.combat_reward || ""} disabled={disabled} onChange={(e)=>set("combat_reward",e.target.value)}/></Field><Field label="Штраф за убийство"><input value={value.kill_fine_id || ""} disabled={disabled} onChange={(e)=>set("kill_fine_id",e.target.value)}/></Field></div>
      <div className="ntv2-panel">
        <h4 className="ntv2-subhead">Расписание</h4>
        {schedule.map((row, index) => <div className="ntv2-list-row" key={index}>
          <input placeholder="Дни 0–6 через запятую" value={(row.weekdays || []).join(",")} disabled={disabled} onChange={(e) => set("schedule", schedule.map((item, i) => i === index ? { ...item, weekdays: e.target.value.split(",").map((v) => Number(v.trim())).filter((v) => Number.isInteger(v) && v >= 0 && v <= 6) } : item))} />
          <input type="time" value={row.start || "00:00"} disabled={disabled} onChange={(e) => set("schedule", schedule.map((item, i) => i === index ? { ...item, start: e.target.value } : item))} />
          <input type="time" value={row.end || "23:59"} disabled={disabled} onChange={(e) => set("schedule", schedule.map((item, i) => i === index ? { ...item, end: e.target.value } : item))} />
          {!disabled ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => set("schedule", schedule.filter((_, i) => i !== index))}>×</button> : null}
        </div>)}
        {!disabled ? <button type="button" className="ntv2-btn" onClick={() => set("schedule", [...schedule, { weekdays: [0, 1, 2, 3, 4, 5, 6], start: "00:00", end: "23:59", active: true }])}>＋ Интервал</button> : null}
        <Field label="Текст вне расписания"><input value={value.schedule_closed_text || ""} disabled={disabled} onChange={(e) => set("schedule_closed_text", e.target.value)} /></Field>
      </div>
      <MessageComposer label="Диалог игроку (изображение/формат/предпросмотр)" value={value.dialog_message} category="npc" uploadKey={`${uploadKey || "npc"}_msg`} disabled={disabled} onChange={(v) => set("dialog_message", v)} />
    </div>
  );
}

function QuestForm({ value, onChange, meta, disabled, refOptions, uploadKey }) {
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
        <Field label="Цель"><select value={value.goal_type} disabled={disabled} onChange={(e) => set("goal_type", e.target.value)}>{(meta.questGoalTypes || []).map((t) => <option key={t} value={t}>{trOption("questGoalTypes", t)}</option>)}</select></Field>
        <Field label="Объект цели">{targetControl}</Field>
      </div>
      <Field label="Награда (описание / JSON)"><textarea rows={2} value={value.reward} disabled={disabled} onChange={(e) => set("reward", e.target.value)} /></Field>
      <div className="ntv2-form-row" style={{ gap: 14 }}>
        <label className="ntv2-check"><input type="checkbox" checked={Boolean(value.repeatable)} disabled={disabled} onChange={(e) => set("repeatable", e.target.checked)} /> Повторяемое</label>
        <Field label="Кулдаун (сек)"><input type="number" value={value.cooldown} disabled={disabled} onChange={(e) => set("cooldown", e.target.value)} /></Field>
      </div>
      <MessageComposer label="Сообщение игроку (изображение/формат/предпросмотр)" value={value.player_message} category="quests" uploadKey={`${uploadKey || "quest"}_msg`} disabled={disabled} onChange={(v) => set("player_message", v)} />
    </div>
  );
}

function RaidForm({ value, onChange, meta, disabled, refOptions }) {
  const set = (k, v) => onChange({ ...value, [k]: v });
  return (
    <div className="ntv2-world-form">
      <div className="ntv2-form-row">
        <Field label="Название"><input value={value.name} disabled={disabled} onChange={(e) => set("name", e.target.value)} /></Field>
        <Field label="Тип рейда"><select value={value.raid_type} disabled={disabled} onChange={(e) => set("raid_type", e.target.value)}>{(meta.raidTypes || []).map((t) => <option key={t} value={t}>{trOption("raidTypes", t)}</option>)}</select></Field>
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
    { key: "effects", label: "Опубликованные эффекты зоны", type: "effect_list" },
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
    { key: "active", label: "Активный", type: "checkbox" },
    { key: "passive", label: "Пассивный", type: "checkbox" },
    { key: "use_condition", label: "Условие", type: "select", metaKey: "mobSkillConditions" },
    { key: "use_chance", label: "Шанс использования %", type: "number" },
    { key: "priority", label: "Приоритет", type: "number" },
    { key: "cooldown", label: "Кулдаун (ходов)", type: "number" },
    { key: "resource", label: "Ресурс стоимости", type: "text" },
    { key: "resource_cost", label: "Стоимость ресурса", type: "number" },
    { key: "target", label: "Цель", type: "text" },
    { key: "base_damage", label: "Базовый урон", type: "number" },
    { key: "damage_formula_id", label: "Формула урона", type: "mono" },
    { key: "apply_effect_id", label: "Накладываемый эффект", type: "effect_ref" },
    { key: "player_text", label: "Текст игроку", type: "textarea" },
  ],
  mob_passive: [
    { key: "name", label: "Название", type: "text" },
    { key: "mob_id", label: "Моб", type: "ref", ref: "mob" },
    { key: "player_description", label: "Описание игроку", type: "textarea" },
    { key: "passive_type", label: "Тип / черта", type: "text" },
    { key: "effect_id", label: "Эффект", type: "effect_ref" },
    { key: "trigger_condition", label: "Условие срабатывания", type: "text" },
    { key: "value", label: "Значение", type: "number" },
    { key: "show_player", label: "Показывать игроку", type: "checkbox" },
    { key: "hidden", label: "Скрытая черта", type: "checkbox" },
  ],
  mob_resistance: [
    { key: "mob_id", label: "Моб", type: "ref", ref: "mob" },
    { key: "resist_type", label: "Тип", type: "select", metaKey: "mobResistTypes" },
    { key: "value", label: "Значение", type: "number" },
    { key: "is_weakness", label: "Это слабость", type: "checkbox" },
    { key: "weapon_type", label: "Тип оружия уязвимости", type: "text" },
    { key: "effect_id", label: "Эффект уязвимости", type: "effect_ref" },
    { key: "weakening_item_id", label: "Предмет ослабления", type: "mono" },
    { key: "weakening_effect_id", label: "Эффект ослабления", type: "effect_ref" },
    { key: "weakens", label: "Что ослабляется", type: "text" },
    { key: "duration", label: "Длительность", type: "number" },
    { key: "success_text", label: "Текст успешного ослабления", type: "textarea" },
    { key: "fail_text", label: "Текст неудачи", type: "textarea" },
  ],
  mob_effect: [
    { key: "name", label: "Название эффекта", type: "text" },
    { key: "mob_id", label: "Моб", type: "ref", ref: "mob" },
    { key: "effect_id", label: "Эффект из конструктора", type: "effect_ref" },
    { key: "trigger", label: "Триггер", type: "text" },
    { key: "chance", label: "Шанс наложения %", type: "number" },
    { key: "duration", label: "Длительность (ходов)", type: "number" },
    { key: "target", label: "Цель", type: "text" },
    { key: "player_text", label: "Текст игроку", type: "textarea" },
  ],
  mob_event_link: [
    { key: "mob_id", label: "Моб", type: "ref", ref: "mob" },
    { key: "event_id", label: "Событие", type: "ref", ref: "event" },
    { key: "spawn_chance", label: "Шанс появления %", type: "number" },
    { key: "count", label: "Количество мобов", type: "number" },
    { key: "variant_type", label: "Вариант", type: "select", metaKey: "mobVariantTypes" },
    { key: "object_type", label: "Тип объекта", type: "text" },
    { key: "weight", label: "Вес", type: "number" },
    { key: "conditions", label: "Условия появления", type: "text" },
    { key: "limit", label: "Лимит", type: "number" },
    { key: "active", label: "Активен", type: "checkbox" },
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
    { key: "phase_number", label: "Номер фазы", type: "number" },
    { key: "hp_percent", label: "Порог здоровья %", type: "number" },
    { key: "turn_count", label: "Количество ходов", type: "number" },
    { key: "entry_event_id", label: "Событие входа", type: "ref", ref: "event" },
    { key: "player_text", label: "Описание игроку", type: "textarea" },
    { key: "transition_message", label: "Сообщение при переходе", type: "textarea" },
    { key: "stat_changes", label: "Изменение характеристик (JSON)", type: "textarea" },
    { key: "add_skill_ids", label: "Добавить навыки", type: "list" },
    { key: "remove_skill_ids", label: "Убрать навыки", type: "list" },
    { key: "add_effect_ids", label: "Добавить эффекты", type: "list" },
    { key: "remove_effect_ids", label: "Убрать эффекты", type: "list" },
    { key: "drop_modifier", label: "Изменение дропа", type: "number" },
    { key: "forbid_escape", label: "Запретить побег", type: "checkbox" },
    { key: "special_finish", label: "Особое завершение боя", type: "text" },
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

function GenericForm({ value, onChange, meta, refOptions, effectOptions, disabled, schema }) {
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
              {(meta[f.metaKey] || []).map((o) => <option key={o} value={o}>{trOption(f.metaKey, o)}</option>)}
            </select>
          );
        } else if (f.type === "ref") {
          control = <RefSelect value={value[f.key]} onChange={(v) => set(f.key, v)} options={refOptions[f.ref]} disabled={disabled} />;
        } else if (f.type === "effect_ref") {
          control = <EffectSelect value={value[f.key]} onChange={(v) => set(f.key, v)} options={effectOptions} disabled={disabled} />;
        } else if (f.type === "effect_list") {
          control = <select multiple value={Array.isArray(value[f.key]) ? value[f.key] : []} disabled={disabled} onChange={(e) => set(f.key, [...e.target.selectedOptions].map((o) => o.value))}>{(effectOptions || []).map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</select>;
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
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [editing, setEditing] = useState(null);
  const [confirm, setConfirm] = useState(null);
  const [refOptions, setRefOptions] = useState({ location: [], mob: [], npc: [] });
  const [formulaOptions, setFormulaOptions] = useState([]);
  const [effectOptions, setEffectOptions] = useState([]);
  const [preview, setPreview] = useState(null);
  const [testReport, setTestReport] = useState(null);
  const [battleReport, setBattleReport] = useState(null);
  const [history, setHistory] = useState(null);
  const [usage, setUsage] = useState(null);
  const [limitRuntime, setLimitRuntime] = useState(null);
  const [limitDraft, setLimitDraft] = useState({});

  const can = useMemo(() => ({
    create: hasPerm("world.create_draft"),
    edit: hasPerm("world.edit_draft"),
    validate: hasPerm("world.validate"),
    publish: hasPerm("world.publish"),
    disable: hasPerm("world.disable"),
    archive: hasPerm("world.archive"),
    testRun: hasPerm("world.test_run"),
    mobTestBattle: hasPerm("mob.test_battle"),
    limitView: hasPerm("location_limits.view"),
    limitEdit: hasPerm("location_limits.edit") || hasPerm("location_limits.force_restore") || hasPerm("location_limits.force_deplete"),
  }), [hasPerm]);

  const loadList = useCallback(async () => {
    const payload = await guarded(() => fetchWorldItems(kind, statusFilter));
    if (payload) setItems(payload.items || []);
  }, [guarded, kind, statusFilter]);

  // Какие справочники объектов нужны форме текущего типа (для пикеров-ссылок).
  const neededRefs = useMemo(() => {
    if (SUBOBJECT_SCHEMAS[kind]) return refKindsForSchema(SUBOBJECT_SCHEMAS[kind]);
    return ({
      button: ["location", "sublocation", "event", "npc"], transition: ["location"],
      event: ["location", "mob"], npc: ["location", "sublocation", "mob"],
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
  useEffect(() => { (async () => { const f = await guarded(() => fetchFormulas("published")); if (f) setFormulaOptions((f.items || []).map((x) => ({ value: x.id, label: x.data?.name || x.id }))); })(); }, [guarded]);
  useEffect(() => { (async () => { const e = await guarded(() => fetchEffects("published")); if (e) setEffectOptions((e.items || []).map((x) => ({ value: x.id, label: x.data?.effect_name || x.id }))); })(); }, [guarded]);
  useEffect(() => { loadList(); }, [loadList]);
  useEffect(() => { if (neededRefs.length) loadRefs(neededRefs); }, [neededRefs, loadRefs]);

  const statuses = meta?.statuses || [];
  const schema = SUBOBJECT_SCHEMAS[kind];
  const Form = FORM_BY_KIND[kind] || LocationForm;

  function resetPanels() { setPreview(null); setTestReport(null); setBattleReport(null); setHistory(null); setUsage(null); setLimitRuntime(null); setLimitDraft({}); }

  async function runMobBattle() {
    const payload = await guarded(() => mobTestBattle(editing.id, { count: 300 }), "Тестовый бой проведён.");
    if (payload?.report) setBattleReport(payload.report);
  }
  function switchKind(k) { setKind(k); setEditing(null); setStatusFilter(""); resetPanels(); }
  function startCreate() { resetPanels(); setEditing({ id: "", data: { ...(EMPTY_BY_KIND[kind] || {}) }, status: "draft", validation: null, isNew: true }); }
  function openItem(item) { resetPanels(); setEditing({ id: item.id, data: { ...(EMPTY_BY_KIND[kind] || {}), ...(item.data || {}) }, status: item.status, validation: item.validation, isNew: false, hasDraft: Boolean(item.has_draft), draftData: item.draft_data || null }); }

  async function runPreview() {
    const payload = await guarded(() => previewWorldItem(kind, editing.id));
    if (payload?.preview) { setPreview(payload.preview); setTestReport(null); }
  }

  async function loadUsage() {
    const payload = await guarded(() => fetchWorldUsage(kind, editing.id));
    if (payload?.usage) {
      setUsage(payload.usage);
      setPreview(null);
      setTestReport(null);
    }
  }

  async function loadLimitRuntime() {
    const locationId = editing.data?.location;
    if (!locationId) return;
    const payload = await guarded(() => fetchLocationLimitRuntime(locationId));
    if (payload) {
      setLimitRuntime(payload);
      setLimitDraft(Object.fromEntries((payload.items || []).map((row) => [row.id, row.remaining ?? 0])));
    }
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
    if (fresh) setEditing((cur) => ({ ...cur, status: fresh.status, hasDraft: Boolean(fresh.has_draft), draftData: fresh.draft_data || null }));
  }

  // --- Версионирование (Этап 1): история/откат и draft-overlay --------------
  async function loadHistory() {
    const payload = await guarded(() => fetchWorldHistory(kind, editing.id));
    if (payload) { setHistory(payload.history || []); setPreview(null); setTestReport(null); }
  }

  function doRollback(version) {
    setConfirm({
      title: `Откатить к версии ${version}?`, dangerous: true, confirmLabel: "Откатить",
      body: <p>Текущие данные будут заменены снимком версии {version}. Текущая версия тоже сохранится в истории — откат обратим.</p>,
      run: async (reason) => {
        const payload = await guarded(() => rollbackWorldItem(kind, editing.id, version, reason), "Откат выполнен.");
        if (payload?.item) setEditing((cur) => ({ ...cur, data: { ...(EMPTY_BY_KIND[kind] || {}), ...(payload.item.data || {}) }, status: payload.item.status, validation: payload.item.validation }));
        setHistory(null);
        await loadList();
      },
    });
  }

  async function saveDraft() {
    // Правка-черновик опубликованного объекта: live в игре не меняется.
    const payload = await guarded(() => editWorldDraft(kind, editing.id, editing.data, ""), "Сохранено как черновик (live не изменён).");
    if (payload?.item) setEditing((cur) => ({ ...cur, hasDraft: Boolean(payload.item.has_draft), draftData: payload.item.draft_data || null }));
    await loadList();
  }

  function doPublishDraft() {
    setConfirm({
      title: "Опубликовать черновик?", dangerous: true, confirmLabel: "Опубликовать",
      body: <p>Черновик будет проверен и перенесён в live — игроки увидят изменения.</p>,
      run: async (reason) => {
        const payload = await guarded(() => publishWorldDraft(kind, editing.id, reason), "Черновик опубликован.");
        if (payload?.item) setEditing((cur) => ({ ...cur, data: { ...(EMPTY_BY_KIND[kind] || {}), ...(payload.item.data || {}) }, status: payload.item.status, hasDraft: false, draftData: null }));
        await loadList();
      },
    });
  }

  function doDiscardDraft() {
    setConfirm({
      title: "Отменить черновик?", dangerous: true, confirmLabel: "Отменить черновик",
      body: <p>Накопленные правки черновика будут отброшены. Live-версия останется как есть.</p>,
      run: async (reason) => {
        await guarded(() => discardWorldDraft(kind, editing.id, reason), "Черновик отменён.");
        setEditing((cur) => ({ ...cur, hasDraft: false, draftData: null }));
        await loadList();
      },
    });
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
          {editing.hasDraft ? <span className="ntv2-badge ntv2-badge-error" title="Есть неопубликованный черновик; live в игре не изменён">✎ есть черновик</span> : null}
        </div>

        {editing.isNew ? (
          <Field label="ID (латиница, напр. small_plateau)"><input value={editing.id} onChange={(e) => setEditing({ ...editing, id: e.target.value })} /></Field>
        ) : <p className="ntv2-hint ntv2-mono">{editing.id}</p>}

        {schema ? (
          <GenericForm schema={schema} value={editing.data} onChange={(data) => setEditing({ ...editing, data })} meta={meta} refOptions={refOptions} effectOptions={effectOptions} disabled={!(editing.isNew ? can.create : can.edit)} />
        ) : (
          <Form value={editing.data} onChange={(data) => setEditing({ ...editing, data })} meta={meta} locationOptions={refOptions.location} refOptions={refOptions} formulaOptions={formulaOptions} effectOptions={effectOptions} disabled={!(editing.isNew ? can.create : can.edit)} uploadKey={editing.id || "new"} />
        )}

        {v ? (
          <div className={`ntv2-panel ${v.ok ? "" : "ntv2-danger-zone"}`}>
            <h4 className="ntv2-subhead">{v.ok ? "✅ Проверка пройдена" : "❌ Проверка не пройдена"}</h4>
            {(v.errors || []).map((e, i) => <div className="ntv2-error" key={"e" + i}>{e}</div>)}
            {(v.warnings || []).map((w, i) => <p className="ntv2-hint" key={"w" + i}>⚠️ {w}</p>)}
          </div>
        ) : null}

        {history !== null ? (
          <div className="ntv2-panel">
            <h4 className="ntv2-subhead">История версий</h4>
            {history.length ? (
              <div className="ntv2-list">
                {[...history].reverse().map((h) => (
                  <div className="ntv2-list-row" key={h.version}>
                    <span className="ntv2-badge">в.{h.version}</span>
                    <b>{(h.data && (h.data.name || h.data.title)) || "—"}</b>
                    <span className="ntv2-hint ntv2-mono">{h.updated_at || ""}</span>
                    {can.edit ? <button type="button" className="ntv2-btn" onClick={() => doRollback(h.version)}>Откатить</button> : null}
                  </div>
                ))}
              </div>
            ) : <p className="ntv2-hint">История пуста — объект ещё не редактировался.</p>}
          </div>
        ) : null}

        <div className="ntv2-form-row" style={{ marginTop: 14 }}>
          {(editing.isNew ? can.create : can.edit) ? (
            <button type="button" className="ntv2-btn ntv2-btn-primary" disabled={editing.isNew && !editing.id.trim()} onClick={save}>{editing.isNew ? "Создать черновик" : "Сохранить"}</button>
          ) : null}
          {!editing.isNew && can.edit && editing.status === "published" ? (
            <button type="button" className="ntv2-btn" title="Сохранить правки в черновик — live в игре не изменится" onClick={saveDraft}>Сохранить как черновик</button>
          ) : null}
          {!editing.isNew && editing.hasDraft && can.publish ? (
            <button type="button" className="ntv2-btn ntv2-btn-primary" onClick={doPublishDraft}>Опубликовать черновик</button>
          ) : null}
          {!editing.isNew && editing.hasDraft && can.edit ? (
            <button type="button" className="ntv2-btn" onClick={doDiscardDraft}>Отменить черновик</button>
          ) : null}
          {!editing.isNew && can.validate ? <button type="button" className="ntv2-btn" onClick={runValidate}>Проверить</button> : null}
          {!editing.isNew ? <button type="button" className="ntv2-btn" onClick={runPreview}>Предпросмотр</button> : null}
          {!editing.isNew ? <button type="button" className="ntv2-btn" onClick={loadUsage}>Где используется</button> : null}
          {!editing.isNew && kind === "location_weekly_limit" && can.limitView ? <button type="button" className="ntv2-btn" onClick={loadLimitRuntime}>Остатки недели</button> : null}
          {!editing.isNew ? <button type="button" className="ntv2-btn" onClick={loadHistory}>История версий</button> : null}
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
          {!editing.isNew && can.archive ? (
            <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={async () => {
              const payload = await guarded(() => fetchWorldUsage(kind, editing.id));
              const found = payload?.usage;
              setUsage(found || null);
              if (found?.total) return;
              setConfirm({
                title: "Удалить объект безвозвратно?", dangerous: true, confirmLabel: "Удалить",
                requireConfirmText: editing.id,
                body: <p>Запись будет удалена из реестра. Историю восстановить нельзя.</p>,
                run: async (reason) => {
                  await guarded(() => deleteWorldItem(kind, editing.id, reason), "Объект удалён.");
                  setEditing(null);
                  await loadList();
                },
              });
            }}>Удалить</button>
          ) : null}
        </div>

        {usage ? (
          <div className={`ntv2-panel ${usage.total ? "ntv2-danger-zone" : ""}`}>
            <h4 className="ntv2-subhead">Где используется</h4>
            {!usage.total ? <p className="ntv2-hint">Связей нет — объект можно удалить.</p> : (
              <div className="ntv2-list">
                {usage.items.map((row) => (
                  <div className="ntv2-list-row" key={`${row.kind}:${row.id}`}>
                    <span className="ntv2-badge">{KIND_LABELS[row.kind] || row.kind}</span>
                    <b>{row.name}</b>
                    <span className="ntv2-mono">{row.id}</span>
                    <span className="ntv2-hint">{row.paths.join(", ")}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        ) : null}

        {limitRuntime ? (
          <div className="ntv2-panel">
            <h4 className="ntv2-subhead">Остатки недели: {limitRuntime.location_id}</h4>
            <div className="ntv2-list">{(limitRuntime.items || []).map((row) => (
              <div className="ntv2-list-row" key={row.id}>
                <b>{row.name}</b><span className="ntv2-mono">{row.id}</span>
                <span>{row.remaining ?? "∞"} / {row.total ?? "∞"}</span>
                <span className="ntv2-hint">использовано: {row.used ?? "—"}; неделя {row.week}</span>
                {can.limitEdit && row.total !== null ? <>
                  <input type="number" min="0" max={row.total} value={limitDraft[row.id] ?? 0} onChange={(e) => setLimitDraft((cur) => ({ ...cur, [row.id]: e.target.value }))} />
                  <button type="button" className="ntv2-btn" onClick={() => setConfirm({
                    title: "Изменить остаток недельного лимита?", dangerous: true, confirmLabel: "Применить",
                    body: <p>Остаток <b>{row.name}</b> будет установлен в {limitDraft[row.id]} из {row.total}.</p>,
                    run: async (reason) => { await guarded(() => setLocationLimitRemaining(row.id, limitRuntime.location_id, limitDraft[row.id], row.week, reason), "Остаток изменён."); await loadLimitRuntime(); },
                  })}>Установить</button>
                </> : null}
              </div>
            ))}</div>
          </div>
        ) : null}

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
          requireConfirmText={confirm?.requireConfirmText || ""}
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
        <SearchBox value={query} onChange={setQuery} />
      </div>
      {!items.length ? <p className="ntv2-hint">Пока нет объектов. {can.create ? "Создайте первый черновик." : ""}</p> : null}
      <NoResults items={items} query={query} />
      <div className="ntv2-list">
        {filterEntities(items, query).map((item) => (
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
