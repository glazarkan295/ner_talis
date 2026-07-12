import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  createEvent,
  eventLifecycle,
  fetchEvent,
  fetchEventMeta,
  fetchEvents,
  updateEvent,
} from "../../../api/adminCommunityApi.js";
import { tr, EVENT_REPEAT_TYPE, WORLD_EVENT_TYPE, EVENT_REWARD_TYPE, SPECIAL_LOOT_SOURCE, EVENT_LOCATION_BINDING } from "../../../i18n/adminLabels.js";
import { ConfirmModal } from "../ConfirmModal.jsx";
import { EmojiInput, EmojiTextarea } from "../EmojiField.jsx";
import { MessageComposer } from "../MessageComposer.jsx";
import { SearchBox, NoResults, filterEntities } from "../SearchFilter.jsx";
import { TechnicalData } from "../TechnicalData.jsx";
import { fetchGraphNode } from "../../../api/adminGraphApi.js";

const STATUS_TONE = { active: "ntv2-badge-owner", finished: "ntv2-badge-owner", disabled: "ntv2-badge-danger", scheduled: "ntv2-badge-error" };

const EMPTY_EVENT = {
  name: "", player_name: "", system_name: "", type: "festive", category: "", short_description: "", description: "", technical_description: "", image: "", icon: "", tags: [],
  start_date: "", end_date: "", endless: false, manual_start: true, manual_end: true, start_by_condition: false, start_condition: "", end_by_condition: false, end_condition: "", timezone: "UTC",
  // Повтор (ТЗ §4.1/§4.2): тип + параметры в зависимости от типа.
  repeat_enabled: false, repeat_type: "yearly", repeat_weekday: "", repeat_day_of_month: "",
  repeat_month: "", repeat_start_hour: "", repeat_end_hour: "",
  repeat_duration_days: "", repeat_start_day: "", repeat_end_month: "", repeat_end_day: "",
  exp_multiplier: "", drop_multiplier: "", coin_multiplier: "",
  scope_type: "world", scope_id: "", scope_ids: [], player_ids: [], player_group_ids: [], all_world: true, modifiers: [],
  start_message: "", end_message: "",
  send_start_message: true, send_end_message: true, send_reminder: false, reminder_message: "", reminder_interval_seconds: 0, notify_all: true, buttons: [],
  // Награды (§4.3) и особая добыча (§4.4).
  rewards: [], special_loot: [],
};

function Field({ label, children }) {
  return <label className="ntv2-field"><span>{label}</span>{children}</label>;
}

export function EventsSection({ guarded, hasPerm }) {
  const [meta, setMeta] = useState(null);
  const [items, setItems] = useState([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState(null);
  const [confirm, setConfirm] = useState(null);
  const [usage, setUsage] = useState(null);

  const can = useMemo(() => ({
    create: hasPerm("world_event.create"), edit: hasPerm("world_event.edit"),
    schedule: hasPerm("world_event.schedule"), start: hasPerm("world_event.start"),
    stop: hasPerm("world_event.stop"), reward: hasPerm("world_event.reward"),
    archive: hasPerm("world_event.archive"),
  }), [hasPerm]);

  const load = useCallback(async () => {
    const payload = await guarded(() => fetchEvents(statusFilter));
    if (payload) setItems(payload.items || []);
  }, [guarded, statusFilter]);

  useEffect(() => { (async () => { const m = await guarded(() => fetchEventMeta()); if (m) setMeta(m); })(); }, [guarded]);
  useEffect(() => { load(); }, [load]);

  const statuses = meta?.statuses || [];
  const statusLabel = (v) => statuses.find((s) => s.value === v)?.label || v;

  async function openItem(id) {
    const payload = await guarded(() => fetchEvent(id));
    if (payload?.item) {
      const merged = { ...EMPTY_EVENT, ...(payload.item.data || {}) };
      // Совместимость со старым флагом repeat_yearly → новый блок повтора.
      if (merged.repeat_yearly && !payload.item.data?.repeat_enabled) { merged.repeat_enabled = true; merged.repeat_type = "yearly"; }
      setEditing({ id, data: merged, status: payload.item.status, validation: payload.validation, isNew: false });
    }
  }
  function startCreate() { setEditing({ id: "", data: { ...EMPTY_EVENT }, status: "draft", validation: null, isNew: true }); }

  async function save() {
    const e = editing;
    if (e.isNew) {
      const payload = await guarded(() => createEvent(e.id.trim(), e.data, ""), "Событие создано.");
      if (payload?.item) await openItem(e.id.trim());
    } else {
      await guarded(() => updateEvent(e.id, e.data, ""), "Сохранено.");
      await openItem(e.id);
    }
    await load();
  }

  async function refreshEditing() { await load(); if (editing) await openItem(editing.id); }

  function lifecycleBtn(label, verb, { dangerous = false } = {}) {
    return (
      <button type="button" className={`ntv2-btn ${dangerous ? "ntv2-btn-danger" : ""}`} onClick={() => {
        if (!dangerous) { guarded(() => eventLifecycle(editing.id, verb, ""), "Готово.").then(refreshEditing); return; }
        setConfirm({
          title: `${label}?`, dangerous: true, confirmLabel: label,
          body: <p>Действие «{label}» для события <b>{editing.data.name || editing.id}</b>.</p>,
          run: async (reason) => { await guarded(() => eventLifecycle(editing.id, verb, reason), "Готово."); await refreshEditing(); },
        });
      }}>{label}</button>
    );
  }

  if (!meta) return <section className="ntv2-section"><h2>Мировые события</h2><p className="ntv2-hint">Загрузка…</p></section>;

  if (editing) {
    const d = editing.data;
    const set = (k, v) => setEditing({ ...editing, data: { ...d, [k]: v } });
    const disabled = !(editing.isNew ? can.create : can.edit);
    const v = editing.validation;
    return (
      <section className="ntv2-section">
        <div className="ntv2-card-head">
          <button type="button" className="ntv2-btn" onClick={() => setEditing(null)}>← К списку</button>
          <h2>{editing.isNew ? "Новое событие" : d.name || editing.id}</h2>
          {!editing.isNew ? <span className={`ntv2-badge ${STATUS_TONE[editing.status] || ""}`}>{statusLabel(editing.status)}</span> : null}
        </div>
        {editing.isNew ? <Field label="ID (латиница)"><input value={editing.id} onChange={(e) => setEditing({ ...editing, id: e.target.value })} /></Field> : <p className="ntv2-hint ntv2-mono">{editing.id}</p>}

        <div className="ntv2-world-form">
          <div className="ntv2-form-row">
            <Field label="Название"><input value={d.name} disabled={disabled} onChange={(e) => set("name", e.target.value)} /></Field>
            <Field label="Название для игрока"><EmojiInput value={d.player_name || ""} disabled={disabled} onChange={(v) => set("player_name", v)} /></Field>
            <Field label="Системное название"><input value={d.system_name || ""} disabled={disabled} onChange={(e) => set("system_name", e.target.value)} /></Field>
            <Field label="Тип"><select value={d.type} disabled={disabled} onChange={(e) => set("type", e.target.value)}>{(meta.types || []).map((x) => <option key={x} value={x}>{tr(WORLD_EVENT_TYPE, x)}</option>)}</select></Field>
            <Field label="Категория"><input value={d.category || ""} disabled={disabled} onChange={(e) => set("category", e.target.value)} /></Field>
          </div>
          <div className="ntv2-panel">
            <h4 className="ntv2-subhead">Область действия</h4>
            <div className="ntv2-form-row">
              <Field label="Тип области"><select value={d.scope_type || "world"} disabled={disabled} onChange={(e) => set("scope_type", e.target.value)}>{["world","region","city","location","sublocation","camp","market","npc","player_group","players","player"].map((x) => <option key={x} value={x}>{x}</option>)}</select></Field>
              <Field label="ID области"><input className="ntv2-mono" value={d.scope_id || ""} disabled={disabled} onChange={(e) => set("scope_id", e.target.value)} /></Field>
              <label className="ntv2-check"><input type="checkbox" checked={Boolean(d.all_world)} disabled={disabled} onChange={(e) => set("all_world", e.target.checked)} /> Весь мир</label>
            </div>
            <Field label="Дополнительные ID области (по строкам)"><textarea rows={2} value={(d.scope_ids || []).join("\n")} disabled={disabled} onChange={(e) => set("scope_ids", e.target.value.split("\n").map((x) => x.trim()).filter(Boolean))} /></Field>
            <Field label="Конкретные игроки (NT-ID)"><textarea rows={2} value={(d.player_ids || []).join("\n")} disabled={disabled} onChange={(e) => set("player_ids", e.target.value.split("\n").map((x) => x.trim()).filter(Boolean))} /></Field>
            <Field label="Группы игроков (ID)"><textarea rows={2} value={(d.player_group_ids || []).join("\n")} disabled={disabled} onChange={(e) => set("player_group_ids", e.target.value.split("\n").map((x) => x.trim()).filter(Boolean))} /></Field>
          </div>
          <div className="ntv2-form-row">
            <Field label="Дата начала (ISO)"><input value={d.start_date} disabled={disabled} placeholder="2026-12-31" onChange={(e) => set("start_date", e.target.value)} /></Field>
            <Field label="Дата окончания (ISO)"><input value={d.end_date} disabled={disabled} placeholder="2027-01-10" onChange={(e) => set("end_date", e.target.value)} /></Field>
          </div>
          <div className="ntv2-panel"><h4 className="ntv2-subhead">Управление периодом</h4><div className="ntv2-form-row">
            <label className="ntv2-check"><input type="checkbox" checked={Boolean(d.endless)} disabled={disabled} onChange={(e) => set("endless", e.target.checked)} /> Бессрочно</label>
            <label className="ntv2-check"><input type="checkbox" checked={Boolean(d.manual_start)} disabled={disabled} onChange={(e) => set("manual_start", e.target.checked)} /> Ручной запуск</label>
            <label className="ntv2-check"><input type="checkbox" checked={Boolean(d.manual_end)} disabled={disabled} onChange={(e) => set("manual_end", e.target.checked)} /> Ручное завершение</label>
            <Field label="Часовой пояс"><input value={d.timezone || "UTC"} disabled={disabled} onChange={(e) => set("timezone", e.target.value)} /></Field>
          </div><div className="ntv2-form-row">
            <label className="ntv2-check"><input type="checkbox" checked={Boolean(d.start_by_condition)} disabled={disabled} onChange={(e) => set("start_by_condition", e.target.checked)} /> Запуск по условию</label><Field label="Условие старта"><input value={d.start_condition || ""} disabled={disabled} onChange={(e) => set("start_condition", e.target.value)} /></Field>
            <label className="ntv2-check"><input type="checkbox" checked={Boolean(d.end_by_condition)} disabled={disabled} onChange={(e) => set("end_by_condition", e.target.checked)} /> Завершение по условию</label><Field label="Условие завершения"><input value={d.end_condition || ""} disabled={disabled} onChange={(e) => set("end_condition", e.target.value)} /></Field>
          </div></div>
          <div className="ntv2-panel">
            <h4 className="ntv2-subhead">Модификаторы мира ({(d.modifiers || []).length})</h4>
            {(d.modifiers || []).map((row, i) => {
              const upd = (patch) => set("modifiers", d.modifiers.map((r, idx) => idx === i ? { ...r, ...patch } : r));
              return <div className="ntv2-form-row" key={i}>
                <Field label="Тип"><select value={row.type || ""} disabled={disabled} onChange={(e) => upd({ type: e.target.value })}>{["event_chance","mob_chance","elite_mob_chance","pvp_chance","pve_chance","drop_chance","resource_amount","buy_price","sell_price","commission","reward","experience","energy","energy_flat","rest_time","craft_time","craft_success","craft_success_percent","location_access","npc_access","active_zone","player_effect"].map((x) => <option key={x} value={x}>{x}</option>)}</select></Field>
                <Field label="Значение"><input type="number" value={row.value ?? ""} disabled={disabled} onChange={(e) => upd({ value: e.target.value })} /></Field>
                <Field label="Режим"><select value={row.value_mode || "percent"} disabled={disabled} onChange={(e) => upd({ value_mode: e.target.value })}><option value="percent">процент</option><option value="multiplier">множитель</option><option value="number">число</option></select></Field>
                <Field label="ID объекта"><input className="ntv2-mono" value={row.object_id || ""} disabled={disabled} onChange={(e) => upd({ object_id: e.target.value })} /></Field>
                <Field label="ID формулы"><input className="ntv2-mono" value={row.formula_id || ""} disabled={disabled} onChange={(e) => upd({ formula_id: e.target.value })} /></Field>
                <Field label="Условие"><input value={row.condition || ""} disabled={disabled} onChange={(e) => upd({ condition: e.target.value })} /></Field>
                <Field label="Текст игроку"><input value={row.player_text || ""} disabled={disabled} onChange={(e) => upd({ player_text: e.target.value })} /></Field>
                {!disabled ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => set("modifiers", d.modifiers.filter((_, idx) => idx !== i))}>×</button> : null}
              </div>;
            })}
            {!disabled ? <button type="button" className="ntv2-btn" onClick={() => set("modifiers", [...(d.modifiers || []), { type: "drop_chance", value: 10, value_mode: "percent" }])}>＋ Модификатор</button> : null}
          </div>
          <div className="ntv2-panel">
            <h4 className="ntv2-subhead">Повтор</h4>
            <div className="ntv2-form-row" style={{ alignItems: "center", gap: 12 }}>
              <label className="ntv2-check"><input type="checkbox" checked={Boolean(d.repeat_enabled)} disabled={disabled} onChange={(e) => set("repeat_enabled", e.target.checked)} /> Повторять</label>
              {d.repeat_enabled ? <Field label="Тип повтора"><select value={d.repeat_type} disabled={disabled} onChange={(e) => set("repeat_type", e.target.value)}>{(meta.repeatTypes || []).map((x) => <option key={x} value={x}>{tr(EVENT_REPEAT_TYPE, x)}</option>)}</select></Field> : null}
              {d.repeat_enabled && d.repeat_type === "weekly" ? <Field label="День недели (0=Пн…6=Вс)"><input type="number" min="0" max="6" value={d.repeat_weekday} disabled={disabled} onChange={(e) => set("repeat_weekday", e.target.value)} /></Field> : null}
              {d.repeat_enabled && d.repeat_type === "monthly" ? <Field label="День месяца (1–31)"><input type="number" min="1" max="31" value={d.repeat_day_of_month} disabled={disabled} onChange={(e) => set("repeat_day_of_month", e.target.value)} /></Field> : null}
              {d.repeat_enabled && d.repeat_type === "yearly" ? <Field label="Месяц (1–12)"><input type="number" min="1" max="12" value={d.repeat_month} disabled={disabled} onChange={(e) => set("repeat_month", e.target.value)} /></Field> : null}
            </div>
            {d.repeat_enabled ? (
              <div className="ntv2-form-row">
                <Field label="Час запуска (0–23)"><input type="number" min="0" max="23" value={d.repeat_start_hour} disabled={disabled} onChange={(e) => set("repeat_start_hour", e.target.value)} /></Field>
                <Field label="Час завершения (0–23)"><input type="number" min="0" max="23" value={d.repeat_end_hour} disabled={disabled} onChange={(e) => set("repeat_end_hour", e.target.value)} /></Field>
                <Field label="Длится дней"><input type="number" min="0" value={d.repeat_duration_days} disabled={disabled} onChange={(e) => set("repeat_duration_days", e.target.value)} /></Field>
              </div>
            ) : null}
            {d.repeat_enabled && d.repeat_type === "yearly" ? (
              <div className="ntv2-form-row">
                <Field label="День начала (1–31)"><input type="number" min="1" max="31" value={d.repeat_start_day} disabled={disabled} onChange={(e) => set("repeat_start_day", e.target.value)} /></Field>
                <Field label="Месяц окончания (1–12)"><input type="number" min="1" max="12" value={d.repeat_end_month} disabled={disabled} onChange={(e) => set("repeat_end_month", e.target.value)} /></Field>
                <Field label="День окончания (1–31)"><input type="number" min="1" max="31" value={d.repeat_end_day} disabled={disabled} onChange={(e) => set("repeat_end_day", e.target.value)} /></Field>
              </div>
            ) : null}
          </div>
          <div className="ntv2-form-row">
            <Field label={`×Опыт (≤${meta.maxMultiplier})`}><input type="number" value={d.exp_multiplier} disabled={disabled} onChange={(e) => set("exp_multiplier", e.target.value)} /></Field>
            <Field label="×Дроп"><input type="number" value={d.drop_multiplier} disabled={disabled} onChange={(e) => set("drop_multiplier", e.target.value)} /></Field>
            <Field label="×Монеты"><input type="number" value={d.coin_multiplier} disabled={disabled} onChange={(e) => set("coin_multiplier", e.target.value)} /></Field>
          </div>
          <Field label="Краткое описание"><EmojiTextarea rows={2} value={d.short_description} disabled={disabled} onChange={(v) => set("short_description", v)} /></Field>
          <Field label="Полное описание"><EmojiTextarea rows={3} value={d.description} disabled={disabled} onChange={(v) => set("description", v)} /></Field>
          <Field label="Техническое описание"><textarea rows={3} value={d.technical_description || ""} disabled={disabled} onChange={(e) => set("technical_description", e.target.value)} /></Field>
          <div className="ntv2-form-row"><Field label="Иконка"><EmojiInput value={d.icon || ""} disabled={disabled} onChange={(v) => set("icon", v)} /></Field><Field label="Теги (по строкам)"><textarea rows={2} value={(d.tags || []).join("\n")} disabled={disabled} onChange={(e) => set("tags", e.target.value.split("\n").map((x) => x.trim()).filter(Boolean))} /></Field></div>
          <Field label="Сообщение о начале"><EmojiTextarea rows={2} value={d.start_message} disabled={disabled} onChange={(v) => set("start_message", v)} /></Field>
          <Field label="Сообщение о завершении"><EmojiTextarea rows={2} value={d.end_message} disabled={disabled} onChange={(v) => set("end_message", v)} /></Field>
          <div className="ntv2-form-row"><label className="ntv2-check"><input type="checkbox" checked={d.send_start_message !== false} disabled={disabled} onChange={(e) => set("send_start_message", e.target.checked)} /> Сообщать о старте</label><label className="ntv2-check"><input type="checkbox" checked={d.send_end_message !== false} disabled={disabled} onChange={(e) => set("send_end_message", e.target.checked)} /> Сообщать о завершении</label><label className="ntv2-check"><input type="checkbox" checked={Boolean(d.send_reminder)} disabled={disabled} onChange={(e) => set("send_reminder", e.target.checked)} /> Напоминания</label><label className="ntv2-check"><input type="checkbox" checked={d.notify_all !== false} disabled={disabled} onChange={(e) => set("notify_all", e.target.checked)} /> Всем игрокам</label></div>
          {d.send_reminder ? <div className="ntv2-form-row"><Field label="Текст напоминания"><EmojiTextarea rows={2} value={d.reminder_message || ""} disabled={disabled} onChange={(v) => set("reminder_message", v)} /></Field><Field label="Интервал, сек"><input type="number" value={d.reminder_interval_seconds || 0} disabled={disabled} onChange={(e) => set("reminder_interval_seconds", e.target.value)} /></Field></div> : null}
          <Field label="Изображение (URL)"><input value={d.image} disabled={disabled} onChange={(e) => set("image", e.target.value)} /></Field>
          <div className="ntv2-panel"><h4 className="ntv2-subhead">Кнопки уведомления</h4>{(d.buttons || []).map((row, i) => { const upd = (patch) => set("buttons", d.buttons.map((r, idx) => idx === i ? { ...r, ...patch } : r)); return <div className="ntv2-form-row" key={i}><Field label="ID"><input value={row.button_id || ""} disabled={disabled} onChange={(e) => upd({ button_id: e.target.value })} /></Field><Field label="Текст"><EmojiInput value={row.text || ""} disabled={disabled} onChange={(v) => upd({ text: v })} /></Field><Field label="Действие"><input value={row.action || ""} disabled={disabled} onChange={(e) => upd({ action: e.target.value })} /></Field><Field label="Цель"><input value={row.target || ""} disabled={disabled} onChange={(e) => upd({ target: e.target.value })} /></Field>{!disabled ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => set("buttons", d.buttons.filter((_, idx) => idx !== i))}>×</button> : null}</div>; })}{!disabled ? <button type="button" className="ntv2-btn" onClick={() => set("buttons", [...(d.buttons || []), { button_id: "", text: "", action: "", target: "" }])}>＋ Кнопка</button> : null}</div>
          <MessageComposer label="Объявление игрокам (изображение/формат/предпросмотр)" value={d.announce_message} category="world_events" uploadKey={`${editing.id || "event"}_msg`} disabled={disabled} onChange={(v) => set("announce_message", v)} />

          {/* Награды (§4.3) */}
          <div className="ntv2-panel">
            <h4 className="ntv2-subhead">Награды ({(d.rewards || []).length})</h4>
            <div className="ntv2-list">
              {(d.rewards || []).map((row, i) => {
                const upd = (patch) => set("rewards", d.rewards.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));
                return (
                  <div className="ntv2-list-row" key={i}>
                    <select value={row.type || ""} disabled={disabled} onChange={(e) => upd({ type: e.target.value })}>{(meta.rewardTypes || []).map((x) => <option key={x} value={x}>{tr(EVENT_REWARD_TYPE, x)}</option>)}</select>
                    <input type="number" style={{ width: 110 }} placeholder="кол-во" value={row.amount || ""} disabled={disabled} onChange={(e) => upd({ amount: e.target.value })} />
                    <input className="ntv2-mono" placeholder="item_id/цель" value={row.item_id || ""} disabled={disabled} onChange={(e) => upd({ item_id: e.target.value })} />
                    {!disabled ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => set("rewards", d.rewards.filter((_, idx) => idx !== i))}>×</button> : null}
                  </div>
                );
              })}
            </div>
            {!disabled ? <button type="button" className="ntv2-btn" style={{ marginTop: 8 }} onClick={() => set("rewards", [...(d.rewards || []), { type: (meta.rewardTypes || ["experience"])[0], amount: "", item_id: "" }])}>＋ Награда</button> : null}
          </div>

          {/* Особая добыча события (§4.4) */}
          <div className="ntv2-panel">
            <h4 className="ntv2-subhead">Особая добыча ({(d.special_loot || []).length})</h4>
            <div className="ntv2-list">
              {(d.special_loot || []).map((row, i) => {
                const upd = (patch) => set("special_loot", d.special_loot.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));
                return (
                  <div className="ntv2-list-row" key={i}>
                    <input className="ntv2-mono" placeholder="item_id" value={row.item_id || ""} disabled={disabled} onChange={(e) => upd({ item_id: e.target.value })} />
                    <select value={row.source || ""} disabled={disabled} onChange={(e) => upd({ source: e.target.value })}><option value="">источник</option>{(meta.specialLootSources || []).map((x) => <option key={x} value={x}>{tr(SPECIAL_LOOT_SOURCE, x)}</option>)}</select>
                    <input type="number" style={{ width: 80 }} title="шанс %" value={row.chance || ""} disabled={disabled} onChange={(e) => upd({ chance: e.target.value })} />
                    <input type="number" style={{ width: 70 }} title="мин" value={row.min_count || ""} disabled={disabled} onChange={(e) => upd({ min_count: e.target.value })} />
                    <input type="number" style={{ width: 70 }} title="макс" value={row.max_count || ""} disabled={disabled} onChange={(e) => upd({ max_count: e.target.value })} />
                    <select value={row.location_binding || ""} disabled={disabled} title="привязка к локациям" onChange={(e) => upd({ location_binding: e.target.value })}><option value="">локации</option>{(meta.locationBindings || []).map((x) => <option key={x} value={x}>{tr(EVENT_LOCATION_BINDING, x)}</option>)}</select>
                    <input type="number" style={{ width: 80 }} title="лимит на игрока" value={row.per_player_limit || ""} disabled={disabled} onChange={(e) => upd({ per_player_limit: e.target.value })} />
                    <input type="number" style={{ width: 80 }} title="общий лимит" value={row.total_limit || ""} disabled={disabled} onChange={(e) => upd({ total_limit: e.target.value })} />
                    {!disabled ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => set("special_loot", d.special_loot.filter((_, idx) => idx !== i))}>×</button> : null}
                  </div>
                );
              })}
            </div>
            {!disabled ? <button type="button" className="ntv2-btn" style={{ marginTop: 8 }} onClick={() => set("special_loot", [...(d.special_loot || []), { item_id: "", source: "selected_mobs", chance: "", min_count: 1, max_count: 1 }])}>＋ Особая добыча</button> : null}
          </div>
        </div>

        {v ? (
          <div className={`ntv2-panel ${v.ok ? "" : "ntv2-danger-zone"}`}>
            <h4 className="ntv2-subhead">{v.ok ? "✅ Готово к запуску" : "❌ Проверка не пройдена"}</h4>
            {(v.errors || []).map((e, i) => <div className="ntv2-error" key={"e" + i}>{e}</div>)}
            {(v.warnings || []).map((w, i) => <p className="ntv2-hint" key={"w" + i}>⚠️ {w}</p>)}
          </div>
        ) : null}

        <div className="ntv2-form-row" style={{ marginTop: 14 }}>
          {(editing.isNew ? can.create : can.edit) ? <button type="button" className="ntv2-btn ntv2-btn-primary" disabled={editing.isNew && !editing.id.trim()} onClick={save}>{editing.isNew ? "Создать" : "Сохранить"}</button> : null}
          {!editing.isNew && can.schedule ? lifecycleBtn("Запланировать", "schedule") : null}
          {!editing.isNew && can.start ? lifecycleBtn("Запустить", "start", { dangerous: true }) : null}
          {!editing.isNew && can.stop && editing.status === "active" ? lifecycleBtn("Остановить", "stop", { dangerous: true }) : null}
          {!editing.isNew && can.stop && editing.status === "active" ? lifecycleBtn("Завершить", "finish", { dangerous: true }) : null}
          {!editing.isNew && can.reward ? lifecycleBtn("Выдать награды", "reward", { dangerous: true }) : null}
          {!editing.isNew && can.archive ? lifecycleBtn("В архив", "archive", { dangerous: true }) : null}
          {!editing.isNew ? <button type="button" className="ntv2-btn" onClick={async () => { const p = await guarded(() => fetchGraphNode("world_event", editing.id)); if (p) setUsage(p); }}>Где используется</button> : null}
        </div>
        {usage ? <TechnicalData label="Связи мирового события" value={usage} /> : null}

        <ConfirmModal open={Boolean(confirm)} title={confirm?.title} body={confirm?.body} dangerous={confirm?.dangerous} confirmLabel={confirm?.confirmLabel} requireReason
          onConfirm={async (reason) => { await confirm.run(reason); setConfirm(null); }} onCancel={() => setConfirm(null)} />
      </section>
    );
  }

  return (
    <section className="ntv2-section">
      <h2>Мировые события</h2>
      <div className="ntv2-filters">
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="">Все статусы</option>
          {statuses.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
        </select>
        {can.create ? <button type="button" className="ntv2-btn ntv2-btn-primary" onClick={startCreate}>＋ Новое событие</button> : null}
        <SearchBox value={query} onChange={setQuery} />
      </div>
      {!items.length ? <p className="ntv2-hint">Событий нет.</p> : null}
      <NoResults items={items} query={query} />
      <div className="ntv2-list">
        {filterEntities(items, query).map((item) => (
          <button key={item.id} type="button" className="ntv2-list-row ntv2-player-row" onClick={() => openItem(item.id)}>
            <b>{item.data?.name || item.id}</b>
            <span className="ntv2-mono">{item.id}</span>
            <span className={`ntv2-badge ${STATUS_TONE[item.status] || ""}`}>{statusLabel(item.status)}</span>
            {item.data?.type ? <span className="ntv2-hint">{item.data.type}</span> : null}
          </button>
        ))}
      </div>
    </section>
  );
}
