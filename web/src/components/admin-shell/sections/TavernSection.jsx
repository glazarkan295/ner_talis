import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  fetchTavernMeta, fetchTaverns, fetchTavern, createTavern, updateTavern,
  tavernLifecycle, previewTavern, fetchTavernUsage,
} from "../../../api/adminTavernApi.js";

// Конструктор таверны (ТЗ таверны): услуги/меню/отдых/слухи/NPC/события/
// репутация/риски/расписание + предпросмотр игрока. Кнопки и тексты —
// редактируемые. Формулы цен игроку не показываются.

const EMPTY = {
  name: "", short_name: "", tavern_type: "city_tavern", tavern_mode: "active",
  location_id: "", city_id: "", fortress_id: "", sublocation_id: "", camp_id: "", region_id: "", image_path: "",
  player_entry_text: "", description: "", admin_description: "",
  available_in_telegram: true, available_in_vk: true, order: 0,
  services: [], menu: [], rest_options: [], rumors: [], npc_links: [],
  events: [], reputation_rules: [], risks: [], schedule: [], buttons: [],
  jobs: [], food: [], drinks: [], rooms: [], quests: [], effects: [],
};

function Field({ label, children }) {
  return <label className="ntv2-field"><span>{label}</span>{children}</label>;
}

export function TavernSection({ guarded, hasPerm }) {
  const [meta, setMeta] = useState(null);
  const [list, setList] = useState([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [selected, setSelected] = useState(null);
  const [data, setData] = useState(null);
  const [creating, setCreating] = useState(false);
  const [newId, setNewId] = useState("");
  const [preview, setPreview] = useState(null);
  const [info, setInfo] = useState("");
  const [usage, setUsage] = useState(null);

  const can = useMemo(() => ({
    create: hasPerm("tavern.create"), edit: hasPerm("tavern.edit"), publish: hasPerm("tavern.publish"),
  }), [hasPerm]);

  const load = useCallback(async () => { const p = await guarded(() => fetchTaverns(statusFilter)); if (p) setList(p.items || []); }, [guarded, statusFilter]);
  useEffect(() => { (async () => { const m = await guarded(() => fetchTavernMeta()); if (m) setMeta(m); })(); }, [guarded]);
  useEffect(() => { load(); }, [load]);

  const statuses = meta?.statuses || [];
  const statusLabel = (v) => statuses.find((s) => s.value === v)?.label || v;

  async function openItem(id) {
    setSelected(id); setCreating(false); setPreview(null);
    const p = await guarded(() => fetchTavern(id));
    if (p) setData({ ...EMPTY, ...(p.item.data || {}) });
  }
  function startCreate() { setCreating(true); setSelected(null); setNewId(""); setData({ ...EMPTY }); setPreview(null); }
  async function save() {
    if (creating) {
      if (!newId.trim()) { setInfo("Укажите ID таверны."); return; }
      const r = await guarded(() => createTavern(newId.trim(), data, "create tavern"));
      if (r) { setInfo("Создано."); setCreating(false); await load(); await openItem(newId.trim()); }
    } else if (selected) {
      const r = await guarded(() => updateTavern(selected, data, "edit tavern"));
      if (r) { setInfo("Сохранено."); await load(); }
    }
  }
  async function lifecycle(verb) { if (!selected) return; const r = await guarded(() => tavernLifecycle(selected, verb, verb)); if (r) { setInfo(`Статус: ${verb}`); await load(); } }
  async function runPreview() { if (!selected) return; const r = await guarded(() => previewTavern(selected, null)); if (r) setPreview(r.preview); }
  async function loadUsage() { if (!selected) return; const r = await guarded(() => fetchTavernUsage(selected)); if (r) setUsage(r.usage); }

  const setF = (k, v) => setData((d) => ({ ...d, [k]: v }));
  // Редактор списка объектов с произвольными колонками.
  const listEditor = (key, columns) => {
    const rows = Array.isArray(data[key]) ? data[key] : [];
    const upd = (i, c, val) => setF(key, rows.map((r, idx) => idx === i ? { ...r, [c]: val } : r));
    return (
      <div className="nttav-list">
        {rows.map((row, i) => (
          <div className="nttav-row" key={i}>
            {columns.map((c) => <input key={c.key} placeholder={c.label} value={row[c.key] ?? ""} onChange={(e) => upd(i, c.key, e.target.value)} />)}
            <button type="button" className="ntv2-btn-mini" onClick={() => setF(key, rows.filter((_, idx) => idx !== i))}>✕</button>
          </div>
        ))}
        <button type="button" className="ntv2-btn-mini" onClick={() => setF(key, [...rows, {}])}>＋ Добавить</button>
      </div>
    );
  };

  return (
    <section className="ntv2-section nttav">
      <style>{TAV_CSS}</style>
      <header className="ntv2-section-head">
        <div>
          <h2>🍺 Конструктор таверны</h2>
          <p className="ntv2-muted">Услуги, меню, отдых, слухи, NPC, события, репутация, риски и расписание. Тексты и кнопки редактируются; формулы цен игроку не видны.</p>
        </div>
        {can.create ? <button type="button" className="ntv2-btn" onClick={startCreate}>＋ Новая таверна</button> : null}
      </header>

      <div className="nttav-layout">
        <aside className="nttav-side">
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            <option value="">Все статусы</option>
            {statuses.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
          </select>
          <ul>
            {list.map((s) => <li key={s.id} className={selected === s.id ? "active" : ""} onClick={() => openItem(s.id)}><b>{s.data?.name || s.id}</b><small>{statusLabel(s.status)}</small></li>)}
            {!list.length ? <li className="nttav-empty">Пусто</li> : null}
          </ul>
        </aside>

        <div className="nttav-main">
          {info ? <div className="nttav-info">{info}</div> : null}
          {!data ? <div className="nttav-placeholder">Выберите таверну или создайте новую.</div> : (
            <>
              <div className="nttav-form">
                {creating ? <Field label="ID таверны"><input value={newId} onChange={(e) => setNewId(e.target.value)} placeholder="seldar_tavern" /></Field> : null}
                <div className="ntv2-form-row">
                  <Field label="Название"><input value={data.name} onChange={(e) => setF("name", e.target.value)} /></Field>
                  <Field label="Тип"><select value={data.tavern_type} onChange={(e) => setF("tavern_type", e.target.value)}>{(meta?.tavernTypes || []).map((tp) => <option key={tp.value} value={tp.value}>{tp.label}</option>)}</select></Field>
                  <Field label="Статус таверны"><select value={data.tavern_mode} onChange={(e) => setF("tavern_mode", e.target.value)}>{(meta?.tavernModes || []).map((m) => <option key={m} value={m}>{m}</option>)}</select></Field>
                </div>
                <div className="ntv2-form-row">
                  <Field label="Локация (id)"><input value={data.location_id} onChange={(e) => setF("location_id", e.target.value)} /></Field>
                  <Field label="Город (id)"><input value={data.city_id} onChange={(e) => setF("city_id", e.target.value)} /></Field>
                  <Field label="Крепость (id)"><input value={data.fortress_id} onChange={(e) => setF("fortress_id", e.target.value)} /></Field>
                  <Field label="Подлокация (id)"><input value={data.sublocation_id} onChange={(e) => setF("sublocation_id", e.target.value)} /></Field>
                  <Field label="Лагерь (id)"><input value={data.camp_id} onChange={(e) => setF("camp_id", e.target.value)} /></Field>
                  <Field label="Изображение (/assets/…)"><input value={data.image_path} onChange={(e) => setF("image_path", e.target.value)} /></Field>
                </div>
                <div className="ntv2-form-row" style={{ gap: 14 }}>
                  <label className="ntv2-check"><input type="checkbox" checked={data.available_in_telegram} onChange={(e) => setF("available_in_telegram", e.target.checked)} /> Telegram</label>
                  <label className="ntv2-check"><input type="checkbox" checked={data.available_in_vk} onChange={(e) => setF("available_in_vk", e.target.checked)} /> VK</label>
                </div>
                <Field label="Текст входа (игроку)"><textarea rows={2} value={data.player_entry_text} onChange={(e) => setF("player_entry_text", e.target.value)} /></Field>
                <Field label="Описание (админ)"><textarea rows={2} value={data.admin_description} onChange={(e) => setF("admin_description", e.target.value)} /></Field>

                <details className="nttav-panel" open><summary>Услуги</summary>{listEditor("services", [
                  { key: "service_id", label: "id" }, { key: "name", label: "название" },
                  { key: "service_type", label: "тип" }, { key: "price", label: "цена" },
                  { key: "currency", label: "валюта" },
                ])}<div className="ntv2-muted" style={{ fontSize: 11 }}>Типы: {(meta?.serviceTypes || []).join(", ")}</div></details>
                <details className="nttav-panel"><summary>Меню</summary>{listEditor("menu", [
                  { key: "menu_item_id", label: "id" }, { key: "name", label: "название" },
                  { key: "menu_category", label: "категория" }, { key: "linked_item_id", label: "предмет id" },
                  { key: "price", label: "цена" }, { key: "currency", label: "валюта" },
                ])}</details>
                <details className="nttav-panel"><summary>Работы (ТЗ §5.2)</summary>{listEditor("jobs", [
                  { key: "job_id", label: "id" }, { key: "name", label: "название" },
                  { key: "trains_stat", label: "характеристика" }, { key: "work_level", label: "уровень" },
                  { key: "max_level", label: "макс." }, { key: "base_duration_seconds", label: "длит. (сек)" },
                  { key: "base_cooldown_seconds", label: "откат (сек)" }, { key: "reward", label: "награда" },
                  { key: "stat_raise_chance", label: "шанс +хар. %" },
                  { key: "time_reduction_percent", label: "сниж. времени %" },
                  { key: "cooldown_reduction_percent", label: "сниж. отката %" },
                  { key: "success_text", label: "текст успеха" }, { key: "fail_text", label: "текст провала" },
                ])}<div className="ntv2-muted" style={{ fontSize: 11 }}>Характеристики: {(meta?.statKeys || []).map((s) => `${s.value} (${s.label})`).join(", ")}. Снижение времени/отката от прокачки — не более {meta?.maxWorkReductionPercent ?? 40}%.</div></details>
                <details className="nttav-panel"><summary>Еда (ТЗ §5.4)</summary>{listEditor("food", [
                  { key: "food_id", label: "id" }, { key: "name", label: "название" },
                  { key: "food_type", label: "тип" }, { key: "price", label: "цена" },
                  { key: "currency", label: "валюта" }, { key: "effect", label: "эффект" },
                  { key: "effect_duration_seconds", label: "длит. эффекта (сек)" }, { key: "cooldown_seconds", label: "кулдаун (сек)" },
                ])}<div className="ntv2-muted" style={{ fontSize: 11 }}>Типы: {(meta?.foodTypes || []).map((f) => `${f.value} (${f.label})`).join(", ")}</div></details>
                <details className="nttav-panel"><summary>Напитки</summary>{listEditor("drinks", [
                  { key: "drink_id", label: "id" }, { key: "name", label: "название" }, { key: "description", label: "описание" }, { key: "price", label: "цена" }, { key: "currency", label: "валюта" }, { key: "restore_energy", label: "энергия" }, { key: "effect_id", label: "эффект" }, { key: "rumor_chance", label: "шанс слуха" }, { key: "event_chance", label: "шанс события" }, { key: "consume_text", label: "текст" },
                ])}</details>
                <details className="nttav-panel"><summary>Отдых</summary>{listEditor("rest_options", [
                  { key: "rest_option_id", label: "id" }, { key: "name", label: "название" },
                  { key: "price", label: "цена" }, { key: "restore_energy_percent", label: "энергия %" },
                  { key: "restore_hp_percent", label: "HP %" },
                ])}</details>
                <details className="nttav-panel"><summary>Комнаты</summary>{listEditor("rooms", [
                  { key: "room_id", label: "id" }, { key: "name", label: "название" }, { key: "price", label: "цена" }, { key: "duration_seconds", label: "длительность" }, { key: "restore_hp_percent", label: "HP %" }, { key: "restore_energy_percent", label: "энергия %" }, { key: "effect_id", label: "эффект" }, { key: "risk_id", label: "риск" }, { key: "enter_text", label: "вход" }, { key: "exit_text", label: "выход" },
                ])}</details>
                <details className="nttav-panel"><summary>Слухи</summary>{listEditor("rumors", [
                  { key: "rumor_id", label: "id" }, { key: "rumor_type", label: "тип" },
                  { key: "rumor_text", label: "текст" }, { key: "chance_percent", label: "шанс %" },
                ])}</details>
                <details className="nttav-panel"><summary>Задания</summary>{listEditor("quests", [
                  { key: "quest_id", label: "quest id" }, { key: "source", label: "источник" }, { key: "condition", label: "условие" }, { key: "repeatable", label: "повтор" }, { key: "offer_text", label: "предложение" }, { key: "denied_text", label: "отказ" }, { key: "complete_text", label: "завершение" },
                ])}</details>
                <details className="nttav-panel"><summary>NPC</summary>{listEditor("npc_links", [
                  { key: "npc_id", label: "npc id" }, { key: "role_in_tavern", label: "роль" },
                ])}</details>
                <details className="nttav-panel"><summary>Эффекты</summary>{listEditor("effects", [
                  { key: "effect_id", label: "effect id" }, { key: "source", label: "источник" }, { key: "duration_seconds", label: "длительность" }, { key: "chance_percent", label: "шанс" }, { key: "condition", label: "условие" }, { key: "apply_text", label: "наложение" }, { key: "end_text", label: "окончание" },
                ])}</details>
                <details className="nttav-panel"><summary>События</summary>{listEditor("events", [
                  { key: "tavern_event_id", label: "id" }, { key: "event_type", label: "тип" },
                  { key: "player_text", label: "текст" }, { key: "chance_percent", label: "шанс %" },
                ])}</details>
                <details className="nttav-panel"><summary>Доступ, подполье и тексты</summary>
                  <div className="ntv2-form-row"><Field label="Требуемый уровень"><input type="number" value={data.required_level || ""} onChange={(e) => setF("required_level", e.target.value)} /></Field><Field label="Требуемый предмет"><input value={data.required_item_id || ""} onChange={(e) => setF("required_item_id", e.target.value)} /></Field><Field label="Репутация"><input value={data.required_reputation_id || ""} onChange={(e) => setF("required_reputation_id", e.target.value)} /></Field></div>
                  <div className="ntv2-form-row"><Field label="Подпольное казино (id)"><input value={data.casino_id || ""} onChange={(e) => setF("casino_id", e.target.value)} /></Field><label className="ntv2-check"><input type="checkbox" checked={Boolean(data.requires_no_fine)} onChange={(e) => setF("requires_no_fine", e.target.checked)} /> Без штрафа</label><label className="ntv2-check"><input type="checkbox" checked={Boolean(data.night_only)} onChange={(e) => setF("night_only", e.target.checked)} /> Только ночью</label></div>
                  {[["main_menu_text","Главное меню"],["tavern_description_text","Описание таверны"],["innkeeper_text","Трактирщик"],["food_list_text","Список еды"],["food_purchase_text","Покупка еды"],["drink_list_text","Список напитков"],["drink_purchase_text","Покупка напитка"],["rest_text","Отдых"],["room_text","Комната"],["rumor_text","Слух"],["quests_text","Задание"],["brawl_text","Драка"],["theft_text","Кража"],["access_denied_text","Недоступность"],["not_enough_money_text","Нехватка денег"],["closed_text","Закрытая таверна"],["exit_text","Выход"]].map(([key,label]) => <Field key={key} label={label}><textarea rows={2} value={data[key] || ""} onChange={(e) => setF(key,e.target.value)} /></Field>)}
                </details>
                <details className="nttav-panel"><summary>Правила репутации</summary>{listEditor("reputation_rules", [
                  { key: "reputation_id", label: "репутация id" }, { key: "visibility", label: "видимость" },
                  { key: "min_value", label: "от" }, { key: "max_value", label: "до" },
                  { key: "price_modifier_percent", label: "цена %" },
                ])}</details>
                <details className="nttav-panel"><summary>Риски</summary>{listEditor("risks", [
                  { key: "risk_id", label: "id" }, { key: "risk_type", label: "тип" },
                  { key: "chance_percent", label: "шанс %" }, { key: "player_text", label: "текст" },
                ])}</details>
                <details className="nttav-panel"><summary>Расписание</summary>{listEditor("schedule", [
                  { key: "mode", label: "режим" }, { key: "start_time", label: "с" },
                  { key: "end_time", label: "до" }, { key: "fallback_text", label: "fallback" },
                ])}</details>
                <details className="nttav-panel"><summary>Кнопки</summary>{listEditor("buttons", [
                  { key: "button_id", label: "id" }, { key: "text", label: "текст" },
                  { key: "action_type", label: "действие" }, { key: "target_id", label: "цель" },
                ])}</details>

                <div className="nttav-actions">
                  {can.edit ? <button type="button" className="ntv2-btn" onClick={save}>{creating ? "Создать" : "Сохранить"}</button> : null}
                  {!creating && can.publish ? (
                    <>
                      <button type="button" className="ntv2-btn-mini" onClick={() => lifecycle("publish")}>Опубликовать</button>
                      <button type="button" className="ntv2-btn-mini" onClick={() => lifecycle("disable")}>Отключить</button>
                      <button type="button" className="ntv2-btn-mini" onClick={() => lifecycle("archive")}>В архив</button>
                      <button type="button" className="ntv2-btn-mini" onClick={loadUsage}>Где используется</button>
                    </>
                  ) : null}
                </div>
                {usage ? <div className="ntv2-panel"><b>Связи таверны</b><pre style={{whiteSpace:"pre-wrap",fontSize:11}}>{JSON.stringify(usage,null,2)}</pre></div> : null}
              </div>

              <div className="nttav-preview">
                <h3>📱 Предпросмотр</h3>
                <button type="button" className="ntv2-btn" onClick={runPreview} disabled={creating}>Показать игроку</button>
                {preview ? (
                  <div className="nttav-pv">
                    <div className="nttav-pv-entry">{preview.entry_text}</div>
                    {preview.services?.length ? <div><b>Услуги:</b><ul>{preview.services.map((s, i) => <li key={i}>{s.name} — {s.price} {s.currency}</li>)}</ul></div> : null}
                    {preview.menu?.length ? <div><b>Меню:</b><ul>{preview.menu.map((s, i) => <li key={i}>{s.name} — {s.price} {s.currency}</li>)}</ul></div> : null}
                    {preview.food?.length ? <div><b>Еда:</b><ul>{preview.food.map((s, i) => <li key={i}>{s.name} — {s.price} {s.currency}</li>)}</ul></div> : null}
                    {preview.jobs?.length ? <div><b>Работы:</b><ul>{preview.jobs.map((j, i) => <li key={i}>{j.name}{j.trains_stat ? ` (${j.trains_stat})` : ""}</li>)}</ul></div> : null}
                    <div className="nttav-pv-rumor">💬 {preview.rumor}</div>
                    <div className="nttav-pv-btns">{(preview.buttons || []).map((b, i) => <span key={i}>[ {b} ]</span>)}</div>
                  </div>
                ) : <p className="ntv2-muted">Сначала сохраните таверну, затем покажите предпросмотр.</p>}
              </div>
            </>
          )}
        </div>
      </div>
    </section>
  );
}

const TAV_CSS = `
.nttav-layout{display:flex;gap:14px;align-items:flex-start}
.nttav-side{width:220px;flex-shrink:0}
.nttav-side select{width:100%;padding:6px 8px;border:1px solid #cbd5e1;border-radius:8px;margin-bottom:6px}
.nttav-side ul{list-style:none;margin:0;padding:0;max-height:62vh;overflow:auto}
.nttav-side li{padding:8px 10px;border:1px solid #e2e8f0;border-radius:8px;margin-bottom:6px;cursor:pointer;display:flex;flex-direction:column}
.nttav-side li.active{border-color:#2563eb;background:#eff6ff}
.nttav-side li small{color:#94a3b8}
.nttav-empty{color:#94a3b8;text-align:center}
.nttav-main{flex:1;min-width:0;display:flex;gap:14px;flex-wrap:wrap}
.nttav-form{flex:1;min-width:380px}
.nttav-form .ntv2-field{display:block;margin-bottom:8px}
.nttav-info{flex-basis:100%;background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;padding:6px 10px;font-size:13px}
.nttav-placeholder{color:#64748b;padding:30px;text-align:center;border:1px dashed #cbd5e1;border-radius:12px;flex-basis:100%}
.nttav-panel{border:1px solid #e2e8f0;border-radius:8px;padding:8px;margin:8px 0}
.nttav-list .nttav-row{display:flex;gap:5px;margin-bottom:5px;flex-wrap:wrap}
.nttav-list input{flex:1;min-width:70px;padding:4px 6px;border:1px solid #cbd5e1;border-radius:6px}
.nttav-actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}
.nttav-preview{width:300px;flex-shrink:0;border:1px solid #e2e8f0;border-radius:12px;padding:12px;background:#f8fafc}
.nttav-preview h3{margin:0 0 8px;font-size:15px}
.nttav-pv{margin-top:10px;font-size:13px;background:#fff;border:1px solid #cbd5e1;border-radius:10px;padding:10px}
.nttav-pv-entry{white-space:pre-wrap;margin-bottom:6px}
.nttav-pv ul{margin:2px 0 6px;padding-left:18px}
.nttav-pv-rumor{margin:6px 0;color:#475569}
.nttav-pv-btns{display:flex;flex-wrap:wrap;gap:4px;color:#2563eb}
`;
