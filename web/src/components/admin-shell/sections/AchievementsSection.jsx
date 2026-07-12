import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  achievementLifecycle,
  createAchievement,
  createAchievementCategory,
  fetchAchievement,
  fetchAchievementMeta,
  fetchAchievements,
  fetchAchievementUsage,
  updateAchievement,
} from "../../../api/adminAchievementApi.js";
import { tr, ITEM_QUALITY, ACH_TYPE, ACH_VISIBILITY, ACH_CONDITION_LOGIC, ACH_CONDITION_TYPE, ACH_PROGRESS_TYPE, ACH_REWARD_TYPE, ACH_REPEAT_PERIOD } from "../../../i18n/adminLabels.js";
import { ConfirmModal } from "../ConfirmModal.jsx";
import { VersionHistory } from "../VersionHistory.jsx";
import { MessageComposer } from "../MessageComposer.jsx";
import { SearchBox, NoResults, filterEntities } from "../SearchFilter.jsx";

const STATUS_TONE = { published: "ntv2-badge-owner", error: "ntv2-badge-error", disabled: "ntv2-badge-danger" };

const EMPTY = {
  name: "", player_name: "", system_name: "", short_description: "", description: "", technical_description: "", hidden_description: "", hint: "", category: "", type: "normal",
  rarity: "common", visibility: "open", icon: "", image: "", color: "", achievement_points: 0, tags: [], progress_type: "numeric",
  condition_logic: "all", condition_n: "", conditions: [], rewards: [], effects: [],
  repeatable: false, repeat_period: "", start_date: "", end_date: "", repeat_yearly: false,
  stages: [], progress_enabled: true, required_progress: 1, show_progress: true, hide_progress: false, show_percent: false, show_number: true, reset_on_death: false, reset_on_event_end: false, reset_on_season_end: false, permanent_progress: true,
  hidden: false, secret: false, hide_until_earned: false, show_as_question: false, show_hint: false, hide_conditions: false, reveal_after_first_progress: false, reveal_npc_id: "", reveal_item_id: "", reveal_event_id: "", reveal_text: "",
};

function Field({ label, children }) {
  return <label className="ntv2-field"><span>{label}</span>{children}</label>;
}

function RowEditor({ title, rows, onChange, disabled, render, blank }) {
  const list = Array.isArray(rows) ? rows : [];
  const set = (i, patch) => onChange(list.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));
  return (
    <div className="ntv2-panel">
      <h4 className="ntv2-subhead">{title} ({list.length})</h4>
      <div className="ntv2-list">
        {list.map((row, i) => (
          <div className="ntv2-list-row" key={i}>
            {render(row, (patch) => set(i, patch))}
            {!disabled ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => onChange(list.filter((_, idx) => idx !== i))}>×</button> : null}
          </div>
        ))}
      </div>
      {!disabled ? <button type="button" className="ntv2-btn" style={{ marginTop: 8 }} onClick={() => onChange([...list, { ...blank }])}>＋ Добавить</button> : null}
    </div>
  );
}

function CategoriesManager({ meta, guarded, onChanged, canManage }) {
  const [name, setName] = useState("");
  const [id, setId] = useState("");
  if (!canManage) return null;
  return (
    <div className="ntv2-panel">
      <h4 className="ntv2-subhead">Категории ({(meta.categories || []).length})</h4>
      <div className="ntv2-list">
        {(meta.categories || []).map((c) => <div className="ntv2-list-row" key={c.id}><b>{c.name}</b><span className="ntv2-mono">{c.id}</span></div>)}
      </div>
      <div className="ntv2-form-row" style={{ marginTop: 8 }}>
        <input placeholder="id (латиница)" value={id} onChange={(e) => setId(e.target.value)} />
        <input placeholder="название" value={name} onChange={(e) => setName(e.target.value)} />
        <button type="button" className="ntv2-btn" disabled={!id.trim() || !name.trim()} onClick={() => guarded(() => createAchievementCategory(id.trim(), { name: name.trim() }, "новая категория"), "Категория создана.").then(() => { setId(""); setName(""); onChanged(); })}>Добавить категорию</button>
      </div>
    </div>
  );
}

export function AchievementsSection({ guarded, hasPerm }) {
  const [meta, setMeta] = useState(null);
  const [items, setItems] = useState([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState(null);
  const [confirm, setConfirm] = useState(null);
  const [usage, setUsage] = useState(null);

  const can = useMemo(() => ({
    create: hasPerm("achievement.create"), edit: hasPerm("achievement.edit"),
    validate: hasPerm("achievement.validate"), publish: hasPerm("achievement.publish"),
    disable: hasPerm("achievement.disable"), archive: hasPerm("achievement.archive"),
    categories: hasPerm("achievement.manage_categories"),
  }), [hasPerm]);

  const loadMeta = useCallback(async () => { const m = await guarded(() => fetchAchievementMeta()); if (m) setMeta(m); }, [guarded]);
  const load = useCallback(async () => { const p = await guarded(() => fetchAchievements(statusFilter)); if (p) setItems(p.items || []); }, [guarded, statusFilter]);

  useEffect(() => { loadMeta(); }, [loadMeta]);
  useEffect(() => { load(); }, [load]);

  const statuses = meta?.statuses || [];
  const statusLabel = (v) => statuses.find((s) => s.value === v)?.label || v;

  async function openItem(id) {
    const p = await guarded(() => fetchAchievement(id));
    if (p?.item) { setUsage(null); setEditing({ id, data: { ...EMPTY, ...(p.item.data || {}) }, status: p.item.status, validation: p.validation, isNew: false }); }
  }
  function startCreate() { setEditing({ id: "", data: { ...EMPTY }, status: "draft", validation: null, isNew: true }); }

  async function save() {
    const e = editing;
    if (e.isNew) { const p = await guarded(() => createAchievement(e.id.trim(), e.data, ""), "Создано."); if (p?.item) await openItem(e.id.trim()); }
    else { await guarded(() => updateAchievement(e.id, e.data, ""), "Сохранено."); await openItem(e.id); }
    await load();
  }
  async function runValidate() { const p = await guarded(() => achievementLifecycle(editing.id, "validate", ""), "Проверка выполнена."); if (p?.validation) setEditing((c) => ({ ...c, validation: p.validation })); }
  async function refreshEditing() { await load(); if (editing) await openItem(editing.id); }

  if (!meta) return <section className="ntv2-section"><h2>Достижения</h2><p className="ntv2-hint">Загрузка…</p></section>;

  if (editing) {
    const d = editing.data;
    const set = (k, v) => setEditing({ ...editing, data: { ...d, [k]: v } });
    const disabled = !(editing.isNew ? can.create : can.edit);
    const v = editing.validation;
    return (
      <section className="ntv2-section">
        <div className="ntv2-card-head">
          <button type="button" className="ntv2-btn" onClick={() => setEditing(null)}>← К списку</button>
          <h2>{editing.isNew ? "Новое достижение" : d.name || editing.id}</h2>
          {!editing.isNew ? <span className={`ntv2-badge ${STATUS_TONE[editing.status] || ""}`}>{statusLabel(editing.status)}</span> : null}
        </div>
        {editing.isNew ? <Field label="ID (латиница)"><input value={editing.id} onChange={(e) => setEditing({ ...editing, id: e.target.value })} /></Field> : <p className="ntv2-hint ntv2-mono">{editing.id}</p>}

        <div className="ntv2-world-form">
          <div className="ntv2-form-row">
            <Field label="Название"><input value={d.name} disabled={disabled} onChange={(e) => set("name", e.target.value)} /></Field>
            <Field label="Категория"><select value={d.category} disabled={disabled} onChange={(e) => set("category", e.target.value)}><option value="">— выбрать —</option>{(meta.categories || []).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></Field>
          </div>
          <div className="ntv2-form-row">
            <Field label="Тип"><select value={d.type} disabled={disabled} onChange={(e) => set("type", e.target.value)}>{meta.types.map((x) => <option key={x} value={x}>{tr(ACH_TYPE, x)}</option>)}</select></Field>
            <Field label="Редкость"><select value={d.rarity} disabled={disabled} onChange={(e) => set("rarity", e.target.value)}>{meta.rarities.map((x) => <option key={x} value={x}>{tr(ITEM_QUALITY, x)}</option>)}</select></Field>
            <Field label="Видимость"><select value={d.visibility} disabled={disabled} onChange={(e) => set("visibility", e.target.value)}>{meta.visibilities.map((x) => <option key={x} value={x}>{tr(ACH_VISIBILITY, x)}</option>)}</select></Field>
            <Field label="Прогресс"><select value={d.progress_type} disabled={disabled} onChange={(e) => set("progress_type", e.target.value)}>{meta.progressTypes.map((x) => <option key={x} value={x}>{tr(ACH_PROGRESS_TYPE, x)}</option>)}</select></Field>
          </div>
          <Field label="Краткое описание"><textarea rows={2} value={d.short_description} disabled={disabled} onChange={(e) => set("short_description", e.target.value)} /></Field>
          <Field label="Полное описание"><textarea rows={3} value={d.description} disabled={disabled} onChange={(e) => set("description", e.target.value)} /></Field>
          <div className="ntv2-form-row"><Field label="Название игроку"><input value={d.player_name || ""} disabled={disabled} onChange={(e) => set("player_name", e.target.value)} /></Field><Field label="Системное название"><input value={d.system_name || ""} disabled={disabled} onChange={(e) => set("system_name", e.target.value)} /></Field><Field label="Очки достижения"><input type="number" value={d.achievement_points || 0} disabled={disabled} onChange={(e) => set("achievement_points", e.target.value)} /></Field></div>
          <Field label="Техническое описание"><textarea rows={2} value={d.technical_description || ""} disabled={disabled} onChange={(e) => set("technical_description", e.target.value)} /></Field>
          <Field label="Иконка (URL)"><input value={d.icon} disabled={disabled} onChange={(e) => set("icon", e.target.value)} /></Field>
          <div className="ntv2-form-row"><Field label="Изображение"><input value={d.image || ""} disabled={disabled} onChange={(e) => set("image", e.target.value)} /></Field><Field label="Цвет"><input value={d.color || ""} disabled={disabled} onChange={(e) => set("color", e.target.value)} /></Field><Field label="Теги (через запятую)"><input value={(d.tags || []).join(", ")} disabled={disabled} onChange={(e) => set("tags", e.target.value.split(",").map((x) => x.trim()).filter(Boolean))} /></Field></div>
          <MessageComposer label="Уведомление о получении (изображение/формат/предпросмотр)" value={d.notify_message} category="achievements" uploadKey={`${editing.id || "ach"}_msg`} disabled={disabled} onChange={(v) => set("notify_message", v)} />

          <div className="ntv2-form-row">
            <Field label="Логика условий"><select value={d.condition_logic} disabled={disabled} onChange={(e) => set("condition_logic", e.target.value)}>{meta.conditionLogic.map((x) => <option key={x} value={x}>{tr(ACH_CONDITION_LOGIC, x)}</option>)}</select></Field>
            {d.condition_logic === "n_of" ? <Field label="N"><input type="number" value={d.condition_n} disabled={disabled} onChange={(e) => set("condition_n", e.target.value)} /></Field> : null}
          </div>
        </div>

        <RowEditor title="Условия" rows={d.conditions} disabled={disabled} onChange={(rows) => set("conditions", rows)} blank={{ type: meta.conditionTypes[0], operator: "gte", amount: 1, target: "", period: "all", minimum: "", maximum: "", required: true, alternative: false, hidden: false, show_to_player: true, text: "", unmet_text: "" }}
          render={(row, setRow) => (<>
            <select value={row.type} disabled={disabled} onChange={(e) => setRow({ type: e.target.value })}>{meta.conditionTypes.map((x) => <option key={x} value={x}>{tr(ACH_CONDITION_TYPE, x)}</option>)}</select>
            <select title="Оператор" value={row.operator || "gte"} disabled={disabled} onChange={(e) => setRow({ operator: e.target.value })}>{(meta.conditionOperators || []).map((x) => <option key={x} value={x}>{x}</option>)}</select>
            <input type="number" title="кол-во" style={{ width: 90 }} value={row.amount} disabled={disabled} onChange={(e) => setRow({ amount: e.target.value })} />
            <input className="ntv2-mono" placeholder="цель (id, опц.)" value={row.target || ""} disabled={disabled} onChange={(e) => setRow({ target: e.target.value })} />
            {row.operator === "between" ? <><input type="number" title="Минимум" placeholder="min" value={row.minimum || ""} disabled={disabled} onChange={(e) => setRow({ minimum: e.target.value })} /><input type="number" title="Максимум" placeholder="max" value={row.maximum || ""} disabled={disabled} onChange={(e) => setRow({ maximum: e.target.value })} /></> : null}
            <select title="Период счётчика" value={row.period || "all"} disabled={disabled} onChange={(e) => setRow({ period: e.target.value })}>{(meta.conditionPeriods || []).map((x) => <option key={x} value={x}>{x}</option>)}</select>
            <label className="ntv2-check"><input type="checkbox" checked={row.required !== false} disabled={disabled} onChange={(e) => setRow({ required: e.target.checked })} /> обязательное</label>
            <label className="ntv2-check"><input type="checkbox" checked={Boolean(row.alternative)} disabled={disabled} onChange={(e) => setRow({ alternative: e.target.checked })} /> альтернативное</label>
            <label className="ntv2-check"><input type="checkbox" checked={Boolean(row.hidden)} disabled={disabled} onChange={(e) => setRow({ hidden: e.target.checked })} /> скрытое</label>
            <label className="ntv2-check"><input type="checkbox" checked={row.show_to_player !== false} disabled={disabled} onChange={(e) => setRow({ show_to_player: e.target.checked })} /> игроку</label>
            <input placeholder="Текст условия" value={row.text || ""} disabled={disabled} onChange={(e) => setRow({ text: e.target.value })} />
            <input placeholder="Текст невыполненного условия" value={row.unmet_text || ""} disabled={disabled} onChange={(e) => setRow({ unmet_text: e.target.value })} />
          </>)} />

        <RowEditor title="Награды" rows={d.rewards} disabled={disabled} onChange={(rows) => set("rewards", rows)} blank={{ type: meta.rewardTypes[0], amount: 1, object_id: "", text: "", duration_seconds: 0, bind_on_receive: false, immediate: true, deliver: false, notify: true, hidden: false }}
          render={(row, setRow) => (<>
            <select value={row.type} disabled={disabled} onChange={(e) => setRow({ type: e.target.value })}>{meta.rewardTypes.map((x) => <option key={x} value={x}>{tr(ACH_REWARD_TYPE, x)}</option>)}</select>
            {(row.type === "item" || row.type === "unique_item") ? <input className="ntv2-mono" placeholder="item_id" value={row.item_id || ""} disabled={disabled} onChange={(e) => setRow({ item_id: e.target.value })} /> : null}
            {row.type === "title" ? <input placeholder="title_id" value={row.title_id || ""} disabled={disabled} onChange={(e) => setRow({ title_id: e.target.value })} /> : null}
            {row.type === "title" ? <><input placeholder="Название титула" value={row.title_name || ""} disabled={disabled} onChange={(e) => setRow({ title_name: e.target.value })} /><input placeholder="Описание титула" value={row.title_description || ""} disabled={disabled} onChange={(e) => setRow({ title_description: e.target.value })} /><label className="ntv2-check"><input type="checkbox" checked={row.show_profile !== false} disabled={disabled} onChange={(e) => setRow({ show_profile: e.target.checked })} /> профиль</label><label className="ntv2-check"><input type="checkbox" checked={Boolean(row.show_rating)} disabled={disabled} onChange={(e) => setRow({ show_rating: e.target.checked })} /> рейтинг</label><label className="ntv2-check"><input type="checkbox" checked={Boolean(row.active_by_default)} disabled={disabled} onChange={(e) => setRow({ active_by_default: e.target.checked })} /> активен</label></> : null}
            {row.type === "skill" ? <><input placeholder="skill_id" value={row.skill_id || ""} disabled={disabled} onChange={(e) => setRow({ skill_id: e.target.value })} /><label className="ntv2-check"><input type="checkbox" checked={Boolean(row.activation_required)} disabled={disabled} onChange={(e) => setRow({ activation_required: e.target.checked })} /> нужна активация</label><label className="ntv2-check"><input type="checkbox" checked={row.can_upgrade !== false} disabled={disabled} onChange={(e) => setRow({ can_upgrade: e.target.checked })} /> можно улучшать</label><label className="ntv2-check"><input type="checkbox" checked={Boolean(row.temporary)} disabled={disabled} onChange={(e) => setRow({ temporary: e.target.checked })} /> временный</label></> : null}
            {row.type === "effect" ? <input className="ntv2-mono" placeholder="effect_id" value={row.effect_id || ""} disabled={disabled} onChange={(e) => setRow({ effect_id: e.target.value })} /> : null}
            <input className="ntv2-mono" placeholder="object_id / skill / access" value={row.object_id || ""} disabled={disabled} onChange={(e) => setRow({ object_id: e.target.value })} />
            <input type="number" title="кол-во" style={{ width: 90 }} value={row.amount} disabled={disabled} onChange={(e) => setRow({ amount: e.target.value })} />
            <input type="number" title="длительность, сек" placeholder="сек" value={row.duration_seconds || 0} disabled={disabled} onChange={(e) => setRow({ duration_seconds: e.target.value })} />
            <label className="ntv2-check"><input type="checkbox" checked={Boolean(row.bind_on_receive)} disabled={disabled} onChange={(e) => setRow({ bind_on_receive: e.target.checked })} /> привязать</label>
            <label className="ntv2-check"><input type="checkbox" checked={row.immediate !== false} disabled={disabled} onChange={(e) => setRow({ immediate: e.target.checked })} /> сразу</label>
            <label className="ntv2-check"><input type="checkbox" checked={Boolean(row.deliver)} disabled={disabled} onChange={(e) => setRow({ deliver: e.target.checked })} /> доставка</label>
            <input placeholder="Текст получения" value={row.text || ""} disabled={disabled} onChange={(e) => setRow({ text: e.target.value })} />
          </>)} />

        <Field label="Эффекты достижения (effect_id по строкам, ТЗ 09 §17)"><textarea rows={2} value={(Array.isArray(d.effects) ? d.effects : []).join("\n")} disabled={disabled} onChange={(e) => set("effects", e.target.value.split("\n").map((s) => s.trim()).filter(Boolean))} /></Field>

        <RowEditor title="Ступени (многоступенчатое)" rows={d.stages} disabled={disabled} onChange={(rows) => set("stages", rows)} blank={{ stage_id: "", number: 1, name: "", description: "", required_progress: 0, title_id: "", effect_id: "", skill_id: "", achievement_points: 0, receive_text: "", show_to_player: true, hidden: false, rewards: [] }}
          render={(row, setRow) => (<>
            <input className="ntv2-mono" placeholder="stage_id" value={row.stage_id || ""} disabled={disabled} onChange={(e) => setRow({ stage_id: e.target.value })} />
            <input type="number" title="номер" value={row.number || 1} disabled={disabled} onChange={(e) => setRow({ number: e.target.value })} />
            <input placeholder="название ступени" value={row.name || ""} disabled={disabled} onChange={(e) => setRow({ name: e.target.value })} />
            <input type="number" title="нужный прогресс" style={{ width: 120 }} value={row.required_progress} disabled={disabled} onChange={(e) => setRow({ required_progress: e.target.value })} />
            <input placeholder="title_id" value={row.title_id || ""} disabled={disabled} onChange={(e) => setRow({ title_id: e.target.value })} /><input placeholder="effect_id" value={row.effect_id || ""} disabled={disabled} onChange={(e) => setRow({ effect_id: e.target.value })} /><input placeholder="skill_id" value={row.skill_id || ""} disabled={disabled} onChange={(e) => setRow({ skill_id: e.target.value })} /><input placeholder="Текст получения" value={row.receive_text || ""} disabled={disabled} onChange={(e) => setRow({ receive_text: e.target.value })} />
          </>)} />

        <div className="ntv2-panel"><h4 className="ntv2-subhead">Прогресс и скрытость</h4><div className="ntv2-form-row">
          {[['progress_enabled','Прогресс включён'],['show_progress','Показывать прогресс'],['hide_progress','Скрыть прогресс'],['show_percent','Показывать %'],['show_number','Показывать числом'],['reset_on_death','Сброс при смерти'],['reset_on_event_end','Сброс после события'],['reset_on_season_end','Сброс после сезона'],['permanent_progress','Сохранять навсегда'],['hidden','Скрытое'],['secret','Секретное'],['hide_until_earned','Не показывать до получения'],['show_as_question','Показывать ???'],['show_hint','Показывать намёк'],['hide_conditions','Скрывать условия'],['reveal_after_first_progress','Раскрыть после прогресса']].map(([key,label]) => <label className="ntv2-check" key={key}><input type="checkbox" checked={Boolean(d[key])} disabled={disabled} onChange={(e) => set(key,e.target.checked)} />{label}</label>)}
        </div><div className="ntv2-form-row"><Field label="Требуемый прогресс"><input type="number" value={d.required_progress || 1} disabled={disabled} onChange={(e) => set("required_progress",e.target.value)} /></Field><Field label="Намёк"><input value={d.hint || ""} disabled={disabled} onChange={(e) => set("hint",e.target.value)} /></Field><Field label="Скрытое описание"><input value={d.hidden_description || ""} disabled={disabled} onChange={(e) => set("hidden_description",e.target.value)} /></Field></div><div className="ntv2-form-row"><Field label="Раскрывает NPC"><input value={d.reveal_npc_id || ""} disabled={disabled} onChange={(e) => set("reveal_npc_id",e.target.value)} /></Field><Field label="Раскрывает предмет"><input value={d.reveal_item_id || ""} disabled={disabled} onChange={(e) => set("reveal_item_id",e.target.value)} /></Field><Field label="Раскрывает событие"><input value={d.reveal_event_id || ""} disabled={disabled} onChange={(e) => set("reveal_event_id",e.target.value)} /></Field></div></div>

        <div className="ntv2-panel">
          <h4 className="ntv2-subhead">Повтор / сезон</h4>
          <div className="ntv2-form-row">
            <label className="ntv2-check"><input type="checkbox" checked={Boolean(d.repeatable)} disabled={disabled} onChange={(e) => set("repeatable", e.target.checked)} /> Повторяемое</label>
            {d.repeatable ? <Field label="Период"><select value={d.repeat_period} disabled={disabled} onChange={(e) => set("repeat_period", e.target.value)}><option value="">—</option>{meta.repeatPeriods.map((x) => <option key={x} value={x}>{tr(ACH_REPEAT_PERIOD, x)}</option>)}</select></Field> : null}
            <Field label="Дата начала (ISO)"><input value={d.start_date} disabled={disabled} onChange={(e) => set("start_date", e.target.value)} /></Field>
            <Field label="Дата окончания (ISO)"><input value={d.end_date} disabled={disabled} onChange={(e) => set("end_date", e.target.value)} /></Field>
            <label className="ntv2-check"><input type="checkbox" checked={Boolean(d.repeat_yearly)} disabled={disabled} onChange={(e) => set("repeat_yearly", e.target.checked)} /> Каждый год</label>
          </div>
        </div>

        {v ? (
          <div className={`ntv2-panel ${v.ok ? "" : "ntv2-danger-zone"}`}>
            <h4 className="ntv2-subhead">{v.ok ? "✅ Готово к публикации" : "❌ Проверка не пройдена"}</h4>
            {(v.errors || []).map((e, i) => <div className="ntv2-error" key={"e" + i}>{e}</div>)}
            {(v.warnings || []).map((w, i) => <p className="ntv2-hint" key={"w" + i}>⚠️ {w}</p>)}
          </div>
        ) : null}

        <div className="ntv2-form-row" style={{ marginTop: 14 }}>
          {(editing.isNew ? can.create : can.edit) ? <button type="button" className="ntv2-btn ntv2-btn-primary" disabled={editing.isNew && !editing.id.trim()} onClick={save}>{editing.isNew ? "Создать" : "Сохранить"}</button> : null}
          {!editing.isNew && can.validate ? <button type="button" className="ntv2-btn" onClick={runValidate}>Проверить</button> : null}
          {!editing.isNew ? <button type="button" className="ntv2-btn" onClick={async () => { const p = await guarded(() => fetchAchievementUsage(editing.id)); if (p?.usage) setUsage(p.usage); }}>Где используется</button> : null}
          {!editing.isNew && can.publish ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => setConfirm({ title: "Опубликовать достижение?", dangerous: true, confirmLabel: "Опубликовать", body: <p>Достижение будет проверено и опубликовано.</p>, run: async (r) => { await guarded(() => achievementLifecycle(editing.id, "publish", r), "Опубликовано."); await refreshEditing(); } })}>Опубликовать</button> : null}
          {!editing.isNew && can.disable && editing.status === "published" ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => setConfirm({ title: "Отключить?", dangerous: true, confirmLabel: "Отключить", body: <p>Достижение перестанет действовать.</p>, run: async (r) => { await guarded(() => achievementLifecycle(editing.id, "disable", r), "Отключено."); await refreshEditing(); } })}>Отключить</button> : null}
          {!editing.isNew && can.archive ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => setConfirm({ title: "В архив?", dangerous: true, confirmLabel: "В архив", body: <p>Достижение уйдёт в архив.</p>, run: async (r) => { await guarded(() => achievementLifecycle(editing.id, "archive", r), "В архиве."); setEditing(null); await load(); } })}>В архив</button> : null}
        </div>

        {usage ? <div className="ntv2-panel"><h4 className="ntv2-subhead">Где используется</h4>{usage.used_by?.length ? <ul>{usage.used_by.map((x) => <li className="ntv2-mono" key={x}>{x}</li>)}</ul> : <p className="ntv2-hint">Связей и прогресса игроков нет.</p>}</div> : null}

        {!editing.isNew ? <VersionHistory base="achievements" id={editing.id} canRollback={can.edit && (editing.status !== "published" || can.publish)} onRolledBack={refreshEditing} /> : null}

        <ConfirmModal open={Boolean(confirm)} title={confirm?.title} body={confirm?.body} dangerous={confirm?.dangerous} confirmLabel={confirm?.confirmLabel} requireReason
          onConfirm={async (r) => { await confirm.run(r); setConfirm(null); }} onCancel={() => setConfirm(null)} />
      </section>
    );
  }

  return (
    <section className="ntv2-section">
      <h2>Достижения</h2>
      <CategoriesManager meta={meta} guarded={guarded} onChanged={loadMeta} canManage={can.categories} />
      <div className="ntv2-filters">
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="">Все статусы</option>
          {statuses.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
        </select>
        {can.create ? <button type="button" className="ntv2-btn ntv2-btn-primary" onClick={startCreate}>＋ Новое достижение</button> : null}
        <SearchBox value={query} onChange={setQuery} />
      </div>
      {!items.length ? <p className="ntv2-hint">Достижений нет.</p> : null}
      <NoResults items={items} query={query} />
      <div className="ntv2-list">
        {filterEntities(items, query).map((item) => (
          <button key={item.id} type="button" className="ntv2-list-row ntv2-player-row" onClick={() => openItem(item.id)}>
            <b>{item.data?.name || item.id}</b>
            <span className="ntv2-mono">{item.id}</span>
            <span className={`ntv2-badge ${STATUS_TONE[item.status] || ""}`}>{statusLabel(item.status)}</span>
            {item.data?.rarity ? <span className="ntv2-hint">{item.data.rarity}</span> : null}
          </button>
        ))}
      </div>
    </section>
  );
}
