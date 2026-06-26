import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  fetchWorldItems, fetchWorldItem, createWorldItem, updateWorldItem,
  publishWorldItem, disableWorldItem, archiveWorldItem,
} from "../../../api/adminWorldApi.js";
import {
  fetchSublocationMeta, fetchSublocationSchema, fetchSublocationNodes,
} from "../../../api/adminSublocationApi.js";

// Конструктор подлокаций (ТЗ 09): карточка подлокации + внутренние узлы и
// переходы + визуальная схема и структурная проверка. CRUD идёт через generic
// world-API по kind: sublocation / sublocation_node / sublocation_transition.

const K_SUB = "sublocation";
const K_NODE = "sublocation_node";
const K_TR = "sublocation_transition";

const SUB_TYPE_LABEL = {
  cave: "Пещера", dungeon: "Подземелье", labyrinth: "Лабиринт", ruins: "Руины",
  house: "Дом", building: "Здание", mine: "Шахта", catacombs: "Катакомбы",
  raid_dungeon: "Данж", tower: "Башня", camp: "Лагерь", hidden_zone: "Скрытая зона",
  world_event_zone: "Зона мир. события", story: "Сюжетная", quest: "Квестовая",
  raid: "Рейдовая", special: "Особая",
};
const NODE_TYPE_LABEL = {
  entry: "Вход", exit: "Выход", corridor: "Коридор", room: "Комната", hall: "Зал",
  fork: "Развилка", dead_end: "Тупик", stairs: "Лестница", hidden_passage: "Скрытый проход",
  stash: "Тайник", trap: "Ловушка", resource_point: "Ресурс", battle_point: "Бой",
  npc_point: "NPC", boss_room: "Комната босса", final_point: "Финал",
  safe_point: "Безопасная", danger_point: "Опасная", floor_transition: "Между этажами",
};
const NODE_COLOR = {
  entry: "#22c55e", exit: "#ef4444", final_point: "#ef4444", boss_room: "#dc2626",
  trap: "#f59e0b", resource_point: "#16a34a", battle_point: "#e11d48",
  npc_point: "#14b8a6", hidden_passage: "#a855f7", fork: "#6366f1",
};
const nodeColor = (t) => NODE_COLOR[t] || "#3b82f6";

function Field({ label, children }) {
  return <label className="ntv2-field"><span>{label}</span>{children}</label>;
}

const EMPTY_SUB = {
  name: "", type: "cave", parent_location: "", short_description: "", description: "",
  image: "", danger: "", min_level: 1, max_level: "", can_leave: true, can_die: true,
  death_return_location: "", use_pve: true, use_camp: false, use_resources: true,
  use_events: true, use_mobs: true, use_traps: false, use_chests: false, use_boss: false,
  lifetime_seconds: "", reentry_cooldown_seconds: "", visit_limit: "", max_nodes: "",
  opens_at_depth: "",
};

export function SublocationsSection({ guarded, hasPerm }) {
  const [meta, setMeta] = useState(null);
  const [list, setList] = useState([]);
  const [locations, setLocations] = useState([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(null);   // sublocation id
  const [card, setCard] = useState(null);           // edited data
  const [creating, setCreating] = useState(false);
  const [newId, setNewId] = useState("");
  const [nodes, setNodes] = useState([]);
  const [transitions, setTransitions] = useState([]);
  const [schema, setSchema] = useState(null);
  const [tab, setTab] = useState("card");
  const [info, setInfo] = useState("");

  const can = useMemo(() => ({
    create: hasPerm("world.create_draft"), edit: hasPerm("world.edit_draft") || hasPerm("world.edit"),
    publish: hasPerm("world.publish"),
  }), [hasPerm]);

  const loadList = useCallback(async () => {
    const p = await guarded(() => fetchWorldItems(K_SUB, statusFilter));
    if (p) setList(p.items || []);
  }, [guarded, statusFilter]);

  useEffect(() => { (async () => {
    const m = await guarded(() => fetchSublocationMeta()); if (m) setMeta(m);
    const loc = await guarded(() => fetchWorldItems("location")); if (loc) setLocations(loc.items || []);
  })(); }, [guarded]);
  useEffect(() => { loadList(); }, [loadList]);

  const statuses = meta?.statuses || [];
  const statusLabel = (v) => statuses.find((s) => s.value === v)?.label || v;
  const locOptions = useMemo(() => locations.map((l) => ({ id: l.id, name: (l.data || {}).name || l.id })), [locations]);

  const loadSub = useCallback(async (id) => {
    setSelected(id); setTab("card"); setCreating(false);
    const p = await guarded(() => fetchWorldItem(K_SUB, id));
    if (p) setCard({ ...EMPTY_SUB, ...(p.item.data || {}) });
    await reloadNodes(id);
  }, [guarded]);

  const reloadNodes = useCallback(async (id) => {
    const n = await guarded(() => fetchSublocationNodes(id));
    if (n) { setNodes(n.nodes || []); setTransitions(n.transitions || []); }
    const s = await guarded(() => fetchSublocationSchema(id));
    if (s) setSchema(s.schema);
  }, [guarded]);

  function startCreate() {
    setCreating(true); setSelected(null); setNewId(""); setCard({ ...EMPTY_SUB }); setTab("card");
  }
  async function saveCard() {
    if (creating) {
      if (!newId.trim()) { setInfo("Укажите ID подлокации."); return; }
      const r = await guarded(() => createWorldItem(K_SUB, newId.trim(), card, "create sublocation"));
      if (r) { setInfo("Создано."); setCreating(false); await loadList(); await loadSub(newId.trim()); }
    } else if (selected) {
      const r = await guarded(() => updateWorldItem(K_SUB, selected, card, "edit sublocation"));
      if (r) { setInfo("Сохранено."); await loadList(); }
    }
  }
  async function lifecycle(verb) {
    if (!selected) return;
    const fn = verb === "publish" ? publishWorldItem : verb === "disable" ? disableWorldItem : archiveWorldItem;
    const r = await guarded(() => fn(K_SUB, selected, verb));
    if (r) { setInfo(`Статус: ${verb}`); await loadList(); }
  }

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return list.filter((s) => !q || (s.data?.name || "").toLowerCase().includes(q) || s.id.toLowerCase().includes(q));
  }, [list, query]);

  const setF = (k, v) => setCard((c) => ({ ...c, [k]: v }));
  const flag = (k, label) => (
    <label className="ntv2-check" key={k}>
      <input type="checkbox" checked={Boolean(card?.[k])} onChange={(e) => setF(k, e.target.checked)} /> {label}
    </label>
  );

  return (
    <section className="ntv2-section ntsub">
      <style>{SUB_CSS}</style>
      <header className="ntv2-section-head">
        <div>
          <h2>🕳️ Конструктор подлокаций</h2>
          <p className="ntv2-muted">Внутренние места внутри локаций: пещеры, данжи, лабиринты, дома. Узлы, переходы, скрытые проходы и проверка схемы.</p>
        </div>
        {can.create ? <button type="button" className="ntv2-btn" onClick={startCreate}>＋ Новая подлокация</button> : null}
      </header>

      <div className="ntsub-layout">
        <aside className="ntsub-list">
          <input className="ntsub-search" placeholder="🔎 Поиск…" value={query} onChange={(e) => setQuery(e.target.value)} />
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            <option value="">Все статусы</option>
            {statuses.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
          </select>
          <ul>
            {filtered.map((s) => (
              <li key={s.id} className={selected === s.id ? "active" : ""} onClick={() => loadSub(s.id)}>
                <b>{s.data?.name || s.id}</b>
                <span className="ntsub-badge">{statusLabel(s.status)}</span>
                <small>{SUB_TYPE_LABEL[s.data?.type] || s.data?.type}</small>
              </li>
            ))}
            {!filtered.length ? <li className="ntsub-empty">Пусто</li> : null}
          </ul>
        </aside>

        <div className="ntsub-main">
          {info ? <div className="ntsub-info">{info}</div> : null}
          {!card ? (
            <div className="ntsub-placeholder">Выберите подлокацию слева или создайте новую.</div>
          ) : (
            <>
              <div className="ntsub-tabs">
                <button type="button" className={tab === "card" ? "active" : ""} onClick={() => setTab("card")}>Карточка</button>
                <button type="button" className={tab === "nodes" ? "active" : ""} onClick={() => setTab("nodes")} disabled={creating}>Узлы ({nodes.length})</button>
                <button type="button" className={tab === "transitions" ? "active" : ""} onClick={() => setTab("transitions")} disabled={creating}>Переходы ({transitions.length})</button>
                <button type="button" className={tab === "schema" ? "active" : ""} onClick={() => setTab("schema")} disabled={creating}>Схема</button>
              </div>

              {tab === "card" ? (
                <div className="ntsub-form">
                  {creating ? <Field label="ID подлокации"><input value={newId} onChange={(e) => setNewId(e.target.value)} placeholder="old_cave" /></Field> : null}
                  <Field label="Название"><input value={card.name} onChange={(e) => setF("name", e.target.value)} /></Field>
                  <div className="ntv2-form-row">
                    <Field label="Тип"><select value={card.type} onChange={(e) => setF("type", e.target.value)}>{(meta?.sublocationTypes || []).map((t) => <option key={t} value={t}>{SUB_TYPE_LABEL[t] || t}</option>)}</select></Field>
                    <Field label="Родительская локация"><select value={card.parent_location} onChange={(e) => setF("parent_location", e.target.value)}><option value="">—</option>{locOptions.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}</select></Field>
                    <Field label="Опасность"><input value={card.danger} onChange={(e) => setF("danger", e.target.value)} /></Field>
                  </div>
                  <div className="ntv2-form-row">
                    <Field label="Мин. уровень"><input type="number" value={card.min_level} onChange={(e) => setF("min_level", e.target.value)} /></Field>
                    <Field label="Макс. уровень"><input type="number" value={card.max_level} onChange={(e) => setF("max_level", e.target.value)} /></Field>
                    <Field label="Открывается с глубины поиска"><input type="number" value={card.opens_at_depth} onChange={(e) => setF("opens_at_depth", e.target.value)} /></Field>
                  </div>
                  <Field label="Краткое описание"><textarea rows={2} value={card.short_description} onChange={(e) => setF("short_description", e.target.value)} /></Field>
                  <Field label="Полное описание"><textarea rows={3} value={card.description} onChange={(e) => setF("description", e.target.value)} /></Field>
                  <Field label="Изображение (/assets/…)"><input value={card.image} onChange={(e) => setF("image", e.target.value)} /></Field>
                  <div className="ntv2-form-row" style={{ gap: 12, flexWrap: "wrap" }}>
                    {flag("can_leave", "Можно покинуть")}{flag("can_die", "Можно умереть")}{flag("use_pve", "PVE")}
                    {flag("use_camp", "Лагерь")}{flag("use_resources", "Ресурсы")}{flag("use_events", "События")}
                    {flag("use_mobs", "Мобы")}{flag("use_traps", "Ловушки")}{flag("use_chests", "Сундуки")}{flag("use_boss", "Босс")}
                  </div>
                  <div className="ntv2-form-row">
                    <Field label="Время жизни (сек, если временная)"><input type="number" value={card.lifetime_seconds} onChange={(e) => setF("lifetime_seconds", e.target.value)} /></Field>
                    <Field label="Кулдаун входа (сек)"><input type="number" value={card.reentry_cooldown_seconds} onChange={(e) => setF("reentry_cooldown_seconds", e.target.value)} /></Field>
                    <Field label="Лимит посещений"><input type="number" value={card.visit_limit} onChange={(e) => setF("visit_limit", e.target.value)} /></Field>
                    <Field label="Макс. узлов"><input type="number" value={card.max_nodes} onChange={(e) => setF("max_nodes", e.target.value)} /></Field>
                  </div>
                  <Field label="Куда переносить после смерти (id локации)"><input value={card.death_return_location} onChange={(e) => setF("death_return_location", e.target.value)} /></Field>
                  <div className="ntsub-actions">
                    {can.edit ? <button type="button" className="ntv2-btn" onClick={saveCard}>{creating ? "Создать" : "Сохранить"}</button> : null}
                    {!creating && can.publish ? (
                      <>
                        <button type="button" className="ntv2-btn-mini" onClick={() => lifecycle("publish")}>Опубликовать</button>
                        <button type="button" className="ntv2-btn-mini" onClick={() => lifecycle("disable")}>Отключить</button>
                        <button type="button" className="ntv2-btn-mini" onClick={() => lifecycle("archive")}>В архив</button>
                      </>
                    ) : null}
                  </div>
                </div>
              ) : null}

              {tab === "nodes" && selected ? (
                <NodesPanel guarded={guarded} meta={meta} subId={selected} nodes={nodes} canEdit={can.edit} onChanged={() => reloadNodes(selected)} />
              ) : null}
              {tab === "transitions" && selected ? (
                <TransitionsPanel guarded={guarded} meta={meta} subId={selected} nodes={nodes} transitions={transitions} canEdit={can.edit} onChanged={() => reloadNodes(selected)} />
              ) : null}
              {tab === "schema" && selected ? (
                <SchemaPanel nodes={nodes} transitions={transitions} schema={schema} />
              ) : null}
            </>
          )}
        </div>
      </div>
    </section>
  );
}

function NodesPanel({ guarded, meta, subId, nodes, canEdit, onChanged }) {
  const [nid, setNid] = useState("");
  const [name, setName] = useState("");
  const [type, setType] = useState("room");
  async function add() {
    if (!nid.trim() || !name.trim()) return;
    const data = { name: name.trim(), node_type: type, sublocation_id: subId };
    const r = await guarded(() => createWorldItem(K_NODE, nid.trim(), data, "add node"));
    if (r) { setNid(""); setName(""); onChanged(); }
  }
  async function remove(id) {
    const r = await guarded(() => archiveWorldItem(K_NODE, id, "archive node"));
    if (r) onChanged();
  }
  return (
    <div className="ntsub-sub">
      {canEdit ? (
        <div className="ntsub-addrow">
          <input placeholder="ID узла (n_entry)" value={nid} onChange={(e) => setNid(e.target.value)} />
          <input placeholder="Название" value={name} onChange={(e) => setName(e.target.value)} />
          <select value={type} onChange={(e) => setType(e.target.value)}>{(meta?.nodeTypes || []).map((t) => <option key={t} value={t}>{NODE_TYPE_LABEL[t] || t}</option>)}</select>
          <button type="button" className="ntv2-btn-mini" onClick={add}>＋ Узел</button>
        </div>
      ) : null}
      <table className="ntsub-table">
        <thead><tr><th>ID</th><th>Название</th><th>Тип</th><th>Статус</th><th /></tr></thead>
        <tbody>
          {nodes.map((n) => (
            <tr key={n.id}>
              <td><code>{n.id}</code></td>
              <td>{n.data?.name}</td>
              <td><span className="ntsub-dot" style={{ background: nodeColor(n.data?.node_type) }} /> {NODE_TYPE_LABEL[n.data?.node_type] || n.data?.node_type}</td>
              <td>{n.status}</td>
              <td>{canEdit ? <button type="button" className="ntv2-btn-mini" onClick={() => remove(n.id)}>В архив</button> : null}</td>
            </tr>
          ))}
          {!nodes.length ? <tr><td colSpan={5} className="ntsub-empty">Узлов нет</td></tr> : null}
        </tbody>
      </table>
    </div>
  );
}

function TransitionsPanel({ guarded, meta, subId, nodes, transitions, canEdit, onChanged }) {
  const opts = nodes.map((n) => ({ id: n.id, name: n.data?.name || n.id }));
  const [tid, setTid] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [text, setText] = useState("");
  const [hidden, setHidden] = useState(false);
  const [cond, setCond] = useState("");
  async function add() {
    if (!tid.trim() || !from || !to) return;
    const data = { sublocation_id: subId, from_node: from, to_node: to, button_text: text, hidden, access_condition: cond };
    const r = await guarded(() => createWorldItem(K_TR, tid.trim(), data, "add transition"));
    if (r) { setTid(""); setText(""); setHidden(false); onChanged(); }
  }
  async function remove(id) {
    const r = await guarded(() => archiveWorldItem(K_TR, id, "archive transition"));
    if (r) onChanged();
  }
  const nm = (id) => opts.find((o) => o.id === id)?.name || id;
  return (
    <div className="ntsub-sub">
      {canEdit ? (
        <div className="ntsub-addrow ntsub-addrow-wrap">
          <input placeholder="ID перехода (t1)" value={tid} onChange={(e) => setTid(e.target.value)} />
          <select value={from} onChange={(e) => setFrom(e.target.value)}><option value="">из узла…</option>{opts.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}</select>
          <select value={to} onChange={(e) => setTo(e.target.value)}><option value="">в узел…</option>{opts.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}</select>
          <input placeholder="Текст кнопки" value={text} onChange={(e) => setText(e.target.value)} />
          <select value={cond} onChange={(e) => setCond(e.target.value)} title="Условие доступа"><option value="">без условия</option>{(meta?.accessConditions || []).map((c) => <option key={c} value={c}>{c}</option>)}</select>
          <label className="ntv2-check"><input type="checkbox" checked={hidden} onChange={(e) => setHidden(e.target.checked)} /> скрытый</label>
          <button type="button" className="ntv2-btn-mini" onClick={add}>＋ Переход</button>
        </div>
      ) : null}
      <table className="ntsub-table">
        <thead><tr><th>ID</th><th>Откуда</th><th>Куда</th><th>Кнопка</th><th>Скрытый</th><th /></tr></thead>
        <tbody>
          {transitions.map((t) => (
            <tr key={t.id}>
              <td><code>{t.id}</code></td>
              <td>{nm(t.data?.from_node)}</td>
              <td>{nm(t.data?.to_node)}</td>
              <td>{t.data?.button_text}</td>
              <td>{t.data?.hidden ? "🔒" : ""}</td>
              <td>{canEdit ? <button type="button" className="ntv2-btn-mini" onClick={() => remove(t.id)}>В архив</button> : null}</td>
            </tr>
          ))}
          {!transitions.length ? <tr><td colSpan={6} className="ntsub-empty">Переходов нет</td></tr> : null}
        </tbody>
      </table>
    </div>
  );
}

function SchemaPanel({ nodes, transitions, schema }) {
  // Простая раскладка по кругу + стрелки переходов.
  const active = nodes.filter((n) => n.status !== "archived");
  const pos = useMemo(() => {
    const m = {}; const n = active.length || 1;
    active.forEach((nd, i) => {
      const a = (2 * Math.PI * i) / n - Math.PI / 2;
      m[nd.id] = { x: 300 + Math.cos(a) * 200, y: 220 + Math.sin(a) * 160 };
    });
    return m;
  }, [active]);
  const nm = (id) => nodes.find((x) => x.id === id)?.data?.name || id;
  return (
    <div className="ntsub-sub">
      {schema ? (
        <div className={`ntsub-check ${schema.ok ? "ok" : "bad"}`}>
          <b>{schema.ok ? "✅ Схема корректна" : "⚠️ Есть проблемы"}</b>
          {" "}узлов: {schema.node_count}, переходов: {schema.transition_count}
          {schema.errors?.length ? <ul>{schema.errors.map((e, i) => <li key={i} className="err">{e}</li>)}</ul> : null}
          {schema.warnings?.length ? <ul>{schema.warnings.map((w, i) => <li key={i} className="warn">{w}</li>)}</ul> : null}
        </div>
      ) : null}
      <svg className="ntsub-svg" viewBox="0 0 600 440">
        <defs>
          <marker id="ntsub-arrow" markerWidth="9" markerHeight="9" refX="8" refY="3" orient="auto"><path d="M0,0 L0,6 L8,3 z" fill="#94a3b8" /></marker>
        </defs>
        {transitions.filter((t) => t.status !== "archived").map((t) => {
          const a = pos[t.data?.from_node], b = pos[t.data?.to_node];
          if (!a || !b) return null;
          return <line key={t.id} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={t.data?.hidden ? "#a855f7" : "#cbd5e1"} strokeWidth={1.6} strokeDasharray={t.data?.hidden ? "5 4" : undefined} markerEnd="url(#ntsub-arrow)" />;
        })}
        {active.map((n) => {
          const p = pos[n.id];
          return (
            <g key={n.id} transform={`translate(${p.x},${p.y})`}>
              <circle r={14} fill={nodeColor(n.data?.node_type)} stroke="#1f2937" strokeWidth={1.4} />
              <text textAnchor="middle" y={28} fontSize={11} fill="#334155">{nm(n.id).slice(0, 18)}</text>
            </g>
          );
        })}
        {!active.length ? <text x={300} y={220} textAnchor="middle" fill="#94a3b8">Нет узлов — добавьте их во вкладке «Узлы»</text> : null}
      </svg>
    </div>
  );
}

const SUB_CSS = `
.ntsub-layout{display:flex;gap:14px;align-items:flex-start}
.ntsub-list{width:260px;flex-shrink:0}
.ntsub-list .ntsub-search,.ntsub-list select{width:100%;padding:6px 8px;border:1px solid #cbd5e1;border-radius:8px;margin-bottom:6px}
.ntsub-list ul{list-style:none;margin:0;padding:0;max-height:62vh;overflow:auto}
.ntsub-list li{padding:8px 10px;border:1px solid #e2e8f0;border-radius:8px;margin-bottom:6px;cursor:pointer;display:flex;flex-direction:column;gap:2px}
.ntsub-list li.active{border-color:#2563eb;background:#eff6ff}
.ntsub-list li .ntsub-badge{font-size:11px;color:#64748b}
.ntsub-list li small{color:#94a3b8}
.ntsub-empty{color:#94a3b8;text-align:center}
.ntsub-main{flex:1;min-width:0}
.ntsub-info{background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;padding:6px 10px;margin-bottom:8px;font-size:13px}
.ntsub-placeholder{color:#64748b;padding:30px;text-align:center;border:1px dashed #cbd5e1;border-radius:12px}
.ntsub-tabs{display:flex;gap:6px;margin-bottom:10px}
.ntsub-tabs button{padding:6px 12px;border:1px solid #cbd5e1;border-radius:8px;background:#fff;cursor:pointer}
.ntsub-tabs button.active{background:#2563eb;color:#fff;border-color:#2563eb}
.ntsub-form .ntv2-field{display:block;margin-bottom:8px}
.ntsub-actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}
.ntsub-addrow{display:flex;gap:6px;margin-bottom:10px;flex-wrap:nowrap}
.ntsub-addrow-wrap{flex-wrap:wrap}
.ntsub-addrow input,.ntsub-addrow select{padding:5px 8px;border:1px solid #cbd5e1;border-radius:8px}
.ntsub-table{width:100%;border-collapse:collapse;font-size:13px}
.ntsub-table th,.ntsub-table td{border-bottom:1px solid #e2e8f0;padding:6px 8px;text-align:left}
.ntsub-dot{width:10px;height:10px;border-radius:50%;display:inline-block;border:1px solid #1f2937}
.ntsub-check{border:1px solid #e2e8f0;border-radius:8px;padding:8px 10px;margin-bottom:8px;font-size:13px}
.ntsub-check.bad{background:#fef2f2;border-color:#fecaca}
.ntsub-check.ok{background:#f0fdf4;border-color:#bbf7d0}
.ntsub-check ul{margin:4px 0 0;padding-left:18px}
.ntsub-check li.err{color:#b91c1c}
.ntsub-check li.warn{color:#b45309}
.ntsub-svg{width:100%;height:440px;border:1px solid #e2e8f0;border-radius:12px;background:#f8fafc}
`;
