import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  fetchReputationMeta, fetchReputations, fetchReputation, createReputation,
  updateReputation, reputationLifecycle, previewReputation,
  fetchReputationUsage,
  fetchReputationHistory, changePlayerReputation,
} from "../../../api/adminReputationApi.js";
import { TechnicalData } from "../TechnicalData.jsx";

// Конструктор репутации (item-reputation §3, эффекты §3): открытая/скрытая/
// частичная, область, диапазон, стадии, правила изменения, метки, угасание +
// предпросмотр последствий. Игроку формулы/точное значение скрытой — не видны.

const EMPTY = {
  name_ru: "", player_name: "", system_name: "", short_name: "", category: "", owner: "", faction_id: "", npc_id: "", city_id: "", location_id: "", short_description: "", description_player: "", description_admin: "", technical_description: "", tags: [], reputation_type: "open",
  visibility: "visible", scope_type: "city", scope_id: "",
  min_value: -1000, max_value: 1000, default_value: 0, display_mode: "stage",
  show_to_player: true, show_exact_value: false, show_change_notifications: true,
  stages: [], change_rules: [], marks: [],
  decay_enabled: false, decay_direction: "toward_default", decay_amount: 0,
  decay_interval_seconds: 0,
  allow_negative: true, use_change_formula: false, change_formula_id: "", show_hints: false, admin_only: false,
  buy_discount_percent: 0, sell_bonus_percent: 0, bad_reputation_markup_percent: 0, trade_blocked: false, hidden_products: false, fine_modifier_percent: 0, delivery_commission_percent: 0, market_commission_percent: 0, service_price_percent: 0, price_formula_id: "",
  hidden_use_conditions: true, hidden_use_dialogues: true, hidden_use_markets: true, hidden_use_crime: true, hidden_use_informant: true, hidden_use_assassin_orders: true, hidden_use_events: true,
};

function Field({ label, children }) {
  return <label className="ntv2-field"><span>{label}</span>{children}</label>;
}

export function ReputationSection({ guarded, hasPerm }) {
  const [meta, setMeta] = useState(null);
  const [list, setList] = useState([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [selected, setSelected] = useState(null);
  const [data, setData] = useState(null);
  const [creating, setCreating] = useState(false);
  const [newId, setNewId] = useState("");
  const [preview, setPreview] = useState(null);
  const [pv, setPv] = useState({ value: 0, delta: 100 });
  const [info, setInfo] = useState("");
  const [usage, setUsage] = useState(null);
  const [history, setHistory] = useState(null);
  const [manual, setManual] = useState({ gameId: "", delta: 0, reason: "", sourceId: "" });

  const can = useMemo(() => ({
    create: hasPerm("reputation.create"), edit: hasPerm("reputation.edit"),
    publish: hasPerm("reputation.publish"),
  }), [hasPerm]);

  const load = useCallback(async () => { const p = await guarded(() => fetchReputations(statusFilter)); if (p) setList(p.items || []); }, [guarded, statusFilter]);
  useEffect(() => { (async () => { const m = await guarded(() => fetchReputationMeta()); if (m) setMeta(m); })(); }, [guarded]);
  useEffect(() => { load(); }, [load]);

  const statuses = meta?.statuses || [];
  const statusLabel = (v) => statuses.find((s) => s.value === v)?.label || v;

  async function openItem(id) {
    setSelected(id); setCreating(false); setPreview(null);
    const p = await guarded(() => fetchReputation(id));
    if (p) setData({ ...EMPTY, ...(p.item.data || {}) });
  }
  function startCreate() { setCreating(true); setSelected(null); setNewId(""); setData({ ...EMPTY }); setPreview(null); }
  async function save() {
    if (creating) {
      if (!newId.trim()) { setInfo("Укажите ID репутации."); return; }
      const r = await guarded(() => createReputation(newId.trim(), data, "create reputation"));
      if (r) { setInfo("Создано."); setCreating(false); await load(); await openItem(newId.trim()); }
    } else if (selected) {
      const r = await guarded(() => updateReputation(selected, data, "edit reputation"));
      if (r) { setInfo("Сохранено."); await load(); }
    }
  }
  async function lifecycle(verb) { if (!selected) return; const r = await guarded(() => reputationLifecycle(selected, verb, verb)); if (r) { setInfo(`Статус: ${verb}`); await load(); } }
  async function runPreview() { if (!selected) return; const r = await guarded(() => previewReputation(selected, Number(pv.value), Number(pv.delta))); if (r) setPreview(r.preview); }

  const setF = (k, v) => setData((d) => ({ ...d, [k]: v }));
  // Универсальный редактор списка объектов (стадии/правила/метки).
  const listEditor = (key, columns, blank) => {
    const rows = Array.isArray(data[key]) ? data[key] : [];
    const upd = (i, c, val) => setF(key, rows.map((r, idx) => idx === i ? { ...r, [c]: val } : r));
    return (
      <div className="ntrep-list">
        {rows.map((row, i) => (
          <div className="ntrep-row" key={i}>
            {columns.map((c) => <input key={c.key} placeholder={c.label} value={c.type === "json" ? JSON.stringify(row[c.key] || []) : row[c.key] ?? ""} onChange={(e) => { if (c.type === "json") { try { upd(i, c.key, JSON.parse(e.target.value || "[]")); } catch {} } else upd(i, c.key, e.target.value); }} />)}
            <button type="button" className="ntv2-btn-mini" onClick={() => setF(key, rows.filter((_, idx) => idx !== i))}>✕</button>
          </div>
        ))}
        <button type="button" className="ntv2-btn-mini" onClick={() => setF(key, [...rows, { ...blank }])}>＋ Добавить</button>
      </div>
    );
  };

  return (
    <section className="ntv2-section ntrep">
      <style>{REP_CSS}</style>
      <header className="ntv2-section-head">
        <div>
          <h2>🎖️ Конструктор репутации</h2>
          <p className="ntv2-muted">Открытая/скрытая/частичная репутация: стадии, правила изменения, метки и угасание. Скрытой репутации игрок не видит точное значение.</p>
        </div>
        {can.create ? <button type="button" className="ntv2-btn" onClick={startCreate}>＋ Новая репутация</button> : null}
      </header>

      <div className="ntrep-layout">
        <aside className="ntrep-side">
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            <option value="">Все статусы</option>
            {statuses.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
          </select>
          <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)}><option value="">Все репутации</option><option value="open">Открытая репутация</option><option value="hidden">Скрытая репутация</option><option value="faction">Фракции</option><option value="npc">NPC-отношения</option><option value="city">Городская</option><option value="criminal">Криминальная</option></select>
          <ul>
            {list.filter((s) => !typeFilter || (typeFilter === "open" ? (s.data?.visibility || "visible") === "visible" : typeFilter === "hidden" ? s.data?.visibility === "hidden" : s.data?.reputation_type === typeFilter)).map((s) => <li key={s.id} className={selected === s.id ? "active" : ""} onClick={() => openItem(s.id)}><b>{s.data?.name_ru || s.id}</b><small>{statusLabel(s.status)}</small></li>)}
            {!list.length ? <li className="ntrep-empty">Пусто</li> : null}
          </ul>
        </aside>

        <div className="ntrep-main">
          {info ? <div className="ntrep-info">{info}</div> : null}
          {!data ? <div className="ntrep-placeholder">Выберите репутацию или создайте новую.</div> : (
            <>
              <div className="ntrep-form">
                {creating ? <Field label="ID репутации"><input value={newId} onChange={(e) => setNewId(e.target.value)} placeholder="guard_suspicion" /></Field> : null}
                <div className="ntv2-form-row">
                  <Field label="Название"><input value={data.name_ru} onChange={(e) => setF("name_ru", e.target.value)} /></Field>
                  <Field label="Название для игрока"><input value={data.player_name} onChange={(e) => setF("player_name", e.target.value)} /></Field>
                  <Field label="Системное название"><input value={data.system_name} onChange={(e) => setF("system_name", e.target.value)} /></Field>
                  <Field label="Короткое имя"><input value={data.short_name} onChange={(e) => setF("short_name", e.target.value)} /></Field>
                  <Field label="Тип репутации"><select value={data.reputation_type} onChange={(e) => setF("reputation_type", e.target.value)}>{(meta?.reputationTypes || []).map((v) => <option key={v}>{v}</option>)}</select></Field>
                  <Field label="Видимость"><select value={data.visibility} onChange={(e) => setF("visibility", e.target.value)}>{(meta?.visibility || []).map((v) => <option key={v.value} value={v.value}>{v.label}</option>)}</select></Field>
                </div>
                <div className="ntv2-form-row"><Field label="Категория"><input value={data.category} onChange={(e) => setF("category", e.target.value)} /></Field><Field label="Владелец"><input value={data.owner} onChange={(e) => setF("owner", e.target.value)} /></Field><Field label="Фракция"><input value={data.faction_id} onChange={(e) => setF("faction_id", e.target.value)} /></Field><Field label="NPC"><input value={data.npc_id} onChange={(e) => setF("npc_id", e.target.value)} /></Field><Field label="Город"><input value={data.city_id} onChange={(e) => setF("city_id", e.target.value)} /></Field><Field label="Локация"><input value={data.location_id} onChange={(e) => setF("location_id", e.target.value)} /></Field></div>
                <div className="ntv2-form-row">
                  <Field label="Область"><select value={data.scope_type} onChange={(e) => setF("scope_type", e.target.value)}>{(meta?.scopeTypes || []).map((s) => <option key={s} value={s}>{s}</option>)}</select></Field>
                  <Field label="ID области"><input value={data.scope_id} onChange={(e) => setF("scope_id", e.target.value)} /></Field>
                  <Field label="Отображение"><select value={data.display_mode} onChange={(e) => setF("display_mode", e.target.value)}>{(meta?.displayModes || []).map((s) => <option key={s} value={s}>{s}</option>)}</select></Field>
                </div>
                <div className="ntv2-form-row">
                  <Field label="Мин."><input type="number" value={data.min_value} onChange={(e) => setF("min_value", e.target.value)} /></Field>
                  <Field label="Макс."><input type="number" value={data.max_value} onChange={(e) => setF("max_value", e.target.value)} /></Field>
                  <Field label="Старт"><input type="number" value={data.default_value} onChange={(e) => setF("default_value", e.target.value)} /></Field>
                </div>
                <div className="ntv2-form-row" style={{ gap: 14 }}>
                  <label className="ntv2-check"><input type="checkbox" checked={data.show_to_player} onChange={(e) => setF("show_to_player", e.target.checked)} /> Видна игроку</label>
                  <label className="ntv2-check"><input type="checkbox" checked={data.show_exact_value} onChange={(e) => setF("show_exact_value", e.target.checked)} /> Показывать точное значение</label>
                  <label className="ntv2-check"><input type="checkbox" checked={data.show_change_notifications} onChange={(e) => setF("show_change_notifications", e.target.checked)} /> Уведомлять об изменении</label>
                  <label className="ntv2-check"><input type="checkbox" checked={data.allow_negative} onChange={(e) => setF("allow_negative", e.target.checked)} /> Может уходить в минус</label>
                  <label className="ntv2-check"><input type="checkbox" checked={data.show_hints} onChange={(e) => setF("show_hints", e.target.checked)} /> Только намёки</label>
                  <label className="ntv2-check"><input type="checkbox" checked={data.admin_only} onChange={(e) => setF("admin_only", e.target.checked)} /> Только админам</label>
                </div>
                <div className="ntv2-form-row"><label className="ntv2-check"><input type="checkbox" checked={data.use_change_formula} onChange={(e) => setF("use_change_formula", e.target.checked)} /> Формула изменения</label><Field label="ID формулы"><input value={data.change_formula_id} onChange={(e) => setF("change_formula_id", e.target.value)} /></Field></div>
                <Field label="Краткое описание"><textarea rows={2} value={data.short_description} onChange={(e) => setF("short_description", e.target.value)} /></Field>
                <Field label="Описание для игрока"><textarea rows={2} value={data.description_player} onChange={(e) => setF("description_player", e.target.value)} /></Field>
                <Field label="Описание для админа"><textarea rows={2} value={data.description_admin} onChange={(e) => setF("description_admin", e.target.value)} /></Field>
                <Field label="Техническое описание"><textarea rows={2} value={data.technical_description} onChange={(e) => setF("technical_description", e.target.value)} /></Field>
                <Field label="Теги (по строкам)"><textarea rows={2} value={(data.tags || []).join("\n")} onChange={(e) => setF("tags", e.target.value.split("\n").map((x) => x.trim()).filter(Boolean))} /></Field>

                <details className="ntrep-panel" open><summary>Стадии</summary>
                  {listEditor("stages", [
                    { key: "stage_id", label: "id" }, { key: "name_ru", label: "название" },
                    { key: "min_value", label: "от" }, { key: "max_value", label: "до" },
                    { key: "description_player", label: "текст игроку" },
                    { key: "color", label: "цвет" }, { key: "icon", label: "иконка" }, { key: "rewards", label: "награды JSON", type: "json" }, { key: "accesses", label: "доступы JSON", type: "json" }, { key: "restrictions", label: "ограничения JSON", type: "json" }, { key: "achievement_text", label: "текст уровня" },
                  ], { stage_id: "", name_ru: "", min_value: 0, max_value: 0, description_player: "", rewards: [], accesses: [], restrictions: [] })}
                </details>
                <details className="ntrep-panel"><summary>Правила изменения</summary>
                  {listEditor("change_rules", [
                    { key: "rule_id", label: "id" }, { key: "trigger", label: "триггер" },
                    { key: "source_id", label: "ID источника" }, { key: "change_value", label: "±значение" }, { key: "direction", label: "+/-" }, { key: "change_mode", label: "fixed/percent" }, { key: "formula_id", label: "ID формулы" }, { key: "daily_limit", label: "лимит/день" }, { key: "show_to_player", label: "показать" }, { key: "text", label: "текст" },
                  ], { rule_id: "", trigger: "", source_id: "", change_value: 0, direction: "positive", change_mode: "fixed", formula_id: "", daily_limit: 0, show_to_player: true, text: "" })}
                  <div className="ntv2-muted" style={{ fontSize: 11 }}>Триггеры: {(meta?.changeTriggers || []).join(", ")}</div>
                </details>
                <details className="ntrep-panel"><summary>Экономика и торговля</summary><div className="ntv2-form-row">{[["buy_discount_percent","Скидка покупки %"],["sell_bonus_percent","Бонус продажи %"],["bad_reputation_markup_percent","Наценка %"],["fine_modifier_percent","Штрафы %"],["delivery_commission_percent","Комиссия доставки %"],["market_commission_percent","Комиссия рынка %"],["service_price_percent","Цена услуг %"]].map(([k,l]) => <Field key={k} label={l}><input type="number" value={data[k]} onChange={(e) => setF(k,e.target.value)} /></Field>)}</div><div className="ntv2-form-row"><label className="ntv2-check"><input type="checkbox" checked={data.trade_blocked} onChange={(e) => setF("trade_blocked",e.target.checked)} /> Запрет торговли</label><label className="ntv2-check"><input type="checkbox" checked={data.hidden_products} onChange={(e) => setF("hidden_products",e.target.checked)} /> Скрытые товары</label><Field label="ID формулы цены"><input value={data.price_formula_id} onChange={(e) => setF("price_formula_id",e.target.value)} /></Field></div></details>
                <details className="ntrep-panel"><summary>Скрытая репутация</summary><div className="ntv2-form-row">{[["hidden_use_conditions","В условиях"],["hidden_use_dialogues","В диалогах"],["hidden_use_markets","В рынках"],["hidden_use_crime","В криминале"],["hidden_use_informant","У информатора"],["hidden_use_assassin_orders","В заказах убийц"],["hidden_use_events","В скрытых событиях"]].map(([k,l]) => <label className="ntv2-check" key={k}><input type="checkbox" checked={data[k]} onChange={(e) => setF(k,e.target.checked)} /> {l}</label>)}</div></details>
                <details className="ntrep-panel"><summary>Скрытые метки</summary>
                  {listEditor("marks", [
                    { key: "mark_id", label: "id" }, { key: "name_ru", label: "название" },
                    { key: "required_min_value", label: "от" }, { key: "required_max_value", label: "до" },
                  ], { mark_id: "", name_ru: "", required_min_value: 0, required_max_value: 0, is_hidden: true })}
                </details>
                <details className="ntrep-panel"><summary>Угасание</summary>
                  <div className="ntv2-form-row" style={{ gap: 14, alignItems: "center" }}>
                    <label className="ntv2-check"><input type="checkbox" checked={data.decay_enabled} onChange={(e) => setF("decay_enabled", e.target.checked)} /> Включить</label>
                    <Field label="Направление"><select value={data.decay_direction} onChange={(e) => setF("decay_direction", e.target.value)}>{(meta?.decayDirections || []).map((s) => <option key={s} value={s}>{s}</option>)}</select></Field>
                    <Field label="Величина"><input type="number" value={data.decay_amount} onChange={(e) => setF("decay_amount", e.target.value)} /></Field>
                    <Field label="Интервал (сек)"><input type="number" value={data.decay_interval_seconds} onChange={(e) => setF("decay_interval_seconds", e.target.value)} /></Field>
                  </div>
                </details>

                <div className="ntrep-actions">
                  {can.edit ? <button type="button" className="ntv2-btn" onClick={save}>{creating ? "Создать" : "Сохранить"}</button> : null}
                  {!creating && can.publish ? (
                    <>
                      <button type="button" className="ntv2-btn-mini" onClick={() => lifecycle("publish")}>Опубликовать</button>
                      <button type="button" className="ntv2-btn-mini" onClick={() => lifecycle("disable")}>Отключить</button>
                      <button type="button" className="ntv2-btn-mini" onClick={() => lifecycle("archive")}>В архив</button>
                      <button type="button" className="ntv2-btn-mini" onClick={async () => { const r = await guarded(() => fetchReputationUsage(selected)); if (r) setUsage(r.usage); }}>Где используется</button>
                      <button type="button" className="ntv2-btn-mini" onClick={async () => { const r = await guarded(() => fetchReputationHistory(selected)); if (r) setHistory(r.history); }}>История изменений</button>
                    </>
                  ) : null}
                </div>
                {usage ? <TechnicalData label="Связи репутации" value={usage} /> : null}
                {history ? <TechnicalData label="История репутации игроков" value={history} /> : null}
                {!creating && can.edit ? <details className="ntrep-panel"><summary>Ручное изменение игроку</summary><div className="ntv2-form-row"><Field label="NT-ID"><input value={manual.gameId} onChange={(e) => setManual({ ...manual, gameId:e.target.value })} /></Field><Field label="Изменение"><input type="number" value={manual.delta} onChange={(e) => setManual({ ...manual, delta:e.target.value })} /></Field><Field label="ID источника"><input value={manual.sourceId} onChange={(e) => setManual({ ...manual, sourceId:e.target.value })} /></Field><Field label="Причина"><input value={manual.reason} onChange={(e) => setManual({ ...manual, reason:e.target.value })} /></Field><button type="button" className="ntv2-btn" disabled={!manual.gameId || !manual.reason} onClick={async () => { const r=await guarded(() => changePlayerReputation(selected,manual.gameId,Number(manual.delta),manual.reason,manual.sourceId),"Репутация изменена."); if(r){const h=await guarded(() => fetchReputationHistory(selected));if(h)setHistory(h.history);} }}>Применить</button></div></details> : null}
              </div>

              <div className="ntrep-preview">
                <h3>🔮 Предпросмотр последствий</h3>
                <div className="ntv2-form-row">
                  <Field label="Текущее значение"><input type="number" value={pv.value} onChange={(e) => setPv((p) => ({ ...p, value: e.target.value }))} /></Field>
                  <Field label="Изменение ±"><input type="number" value={pv.delta} onChange={(e) => setPv((p) => ({ ...p, delta: e.target.value }))} /></Field>
                </div>
                <button type="button" className="ntv2-btn" onClick={runPreview} disabled={creating}>Рассчитать</button>
                {preview ? (
                  <div className="ntrep-pv">
                    <div>Значение: <b>{preview.current_value}</b> → <b>{preview.next_value}</b></div>
                    <div>Стадия: {preview.current_stage?.name_ru || "—"} → {preview.next_stage?.name_ru || "—"} {preview.stage_changed ? "🔁" : ""}</div>
                    <div>Метки до: {(preview.current_marks || []).join(", ") || "—"}</div>
                    <div>Метки после: {(preview.next_marks || []).join(", ") || "—"}</div>
                  </div>
                ) : <p className="ntv2-muted">Сначала сохраните репутацию, затем рассчитайте.</p>}
              </div>
            </>
          )}
        </div>
      </div>
    </section>
  );
}

const REP_CSS = `
.ntrep-layout{display:flex;gap:14px;align-items:flex-start}
.ntrep-side{width:220px;flex-shrink:0}
.ntrep-side select{width:100%;padding:6px 8px;border:1px solid #cbd5e1;border-radius:8px;margin-bottom:6px}
.ntrep-side ul{list-style:none;margin:0;padding:0;max-height:62vh;overflow:auto}
.ntrep-side li{padding:8px 10px;border:1px solid #e2e8f0;border-radius:8px;margin-bottom:6px;cursor:pointer;display:flex;flex-direction:column}
.ntrep-side li.active{border-color:#2563eb;background:#eff6ff}
.ntrep-side li small{color:#94a3b8}
.ntrep-empty{color:#94a3b8;text-align:center}
.ntrep-main{flex:1;min-width:0;display:flex;gap:14px;flex-wrap:wrap}
.ntrep-form{flex:1;min-width:380px}
.ntrep-form .ntv2-field{display:block;margin-bottom:8px}
.ntrep-info{flex-basis:100%;background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;padding:6px 10px;font-size:13px}
.ntrep-placeholder{color:#64748b;padding:30px;text-align:center;border:1px dashed #cbd5e1;border-radius:12px;flex-basis:100%}
.ntrep-panel{border:1px solid #e2e8f0;border-radius:8px;padding:8px;margin:8px 0}
.ntrep-list .ntrep-row{display:flex;gap:5px;margin-bottom:5px;flex-wrap:wrap}
.ntrep-list input{flex:1;min-width:80px;padding:4px 6px;border:1px solid #cbd5e1;border-radius:6px}
.ntrep-actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}
.ntrep-preview{width:300px;flex-shrink:0;border:1px solid #e2e8f0;border-radius:12px;padding:12px;background:#f8fafc}
.ntrep-preview h3{margin:0 0 8px;font-size:15px}
.ntrep-pv{margin-top:10px;font-size:13px;display:flex;flex-direction:column;gap:4px;background:#fff;border:1px solid #cbd5e1;border-radius:8px;padding:10px}
`;
