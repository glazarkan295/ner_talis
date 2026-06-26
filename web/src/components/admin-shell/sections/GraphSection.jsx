import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  fetchGraphLegend,
  fetchFullGraph,
  fetchErrorGraph,
  fetchGraphAround,
  fetchGraphPath,
  fetchGraphNode,
  fetchGraphValidation,
} from "../../../api/adminGraphApi.js";

// Интерактивная схема / карта связей (ТЗ 12). Чистый SVG без сторонних
// зависимостей: слои-фильтры, поиск, фокус вокруг объекта, путь между
// объектами, режим ошибок, боковая карточка узла, масштаб/панорама/перетаскивание.

const TYPE_COLORS = {
  location: "#3b82f6", mob: "#ef4444", event: "#a855f7", npc: "#14b8a6",
  item: "#f59e0b", recipe: "#d97706", effect: "#8b5cf6", quest: "#0ea5e9",
  raid: "#dc2626", button: "#64748b", transition: "#94a3b8",
  trait: "#10b981", blessing: "#eab308", phase: "#f43f5e", level: "#6366f1",
  skill: "#06b6d4", race: "#84cc16", fine: "#9ca3af", camp: "#22c55e",
  city: "#0891b2", achievement: "#fbbf24",
};
const DEFAULT_COLOR = "#94a3b8";
const RENDER_SOFT_CAP = 600;

// Тип узла → раздел админки (для «открыть в конструкторе», ТЗ §8).
const TYPE_TO_SECTION = {
  item: "items", effect: "effects", recipe: "recipes", trait: "traits",
  blessing: "blessings", phase: "phases", level: "levels", skill: "skills",
  race: "races", fine: "fines", camp: "camps", city: "city",
  achievement: "achievements", world_event: "events", guild: "guilds",
  profile_tab: "profile_layout", profile_block: "profile_layout", profile_theme: "profile_layout",
};
function sectionForType(type) {
  if (type in TYPE_TO_SECTION) return TYPE_TO_SECTION[type];
  if (type.startsWith("site_")) return "site";
  return "world"; // локации/мобы/события/переходы/кнопки/npc/квесты/рейды
}

function downloadFile(name, content, mime) {
  try {
    const blob = new Blob([content], { type: mime });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = name;
    document.body.appendChild(a); a.click();
    document.body.removeChild(a); URL.revokeObjectURL(url);
  } catch { /* noop */ }
}
function toMarkdown(nodes, edges, label) {
  const byType = {};
  nodes.forEach((n) => { (byType[n.type] = byType[n.type] || []).push(n); });
  const out = [`# Схема Нер-Талис${label ? ` — ${label}` : ""}`, "", `Узлов: ${nodes.length}, связей: ${edges.length}`, ""];
  Object.keys(byType).sort().forEach((t) => {
    out.push(`## ${t} (${byType[t].length})`);
    byType[t].forEach((n) => out.push(`- ${n.title || n.id} — \`${n.id}\` [${n.status || "—"}]${n.has_errors ? " ⚠️" : ""}`));
    out.push("");
  });
  out.push("## Связи", "");
  edges.forEach((e) => out.push(`- \`${e.from}\` —${e.label}→ \`${e.to}\`${e.broken ? " ⚠️" : ""}`));
  return out.join("\n");
}

function colorFor(type) {
  if (type in TYPE_COLORS) return TYPE_COLORS[type];
  if (type.startsWith("location_")) return "#60a5fa";
  if (type.startsWith("mob_")) return "#fca5a5";
  return DEFAULT_COLOR;
}

// --- Лёгкая силовая раскладка (Fruchterman–Reingold, фикс. число итераций) ---
function computeLayout(nodes, edges) {
  const n = nodes.length;
  const pos = {};
  if (!n) return pos;
  const W = Math.max(800, Math.sqrt(n) * 160);
  const area = W * W;
  const k = Math.sqrt(area / n);
  const idx = {};
  nodes.forEach((nd, i) => {
    const a = (2 * Math.PI * i) / n;
    pos[nd.id] = { x: Math.cos(a) * W * 0.4 + (Math.random() - 0.5) * 40, y: Math.sin(a) * W * 0.4 + (Math.random() - 0.5) * 40 };
    idx[nd.id] = i;
  });
  const iters = n > 350 ? 80 : 160;
  let temp = W * 0.1;
  const adj = edges.filter((e) => pos[e.from] && pos[e.to]);
  for (let it = 0; it < iters; it++) {
    const disp = {};
    nodes.forEach((nd) => { disp[nd.id] = { x: 0, y: 0 }; });
    // Отталкивание (O(n^2), приемлемо до ~400 узлов).
    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        const a = nodes[i].id, b = nodes[j].id;
        let dx = pos[a].x - pos[b].x, dy = pos[a].y - pos[b].y;
        let dist = Math.hypot(dx, dy) || 0.01;
        const force = (k * k) / dist;
        const fx = (dx / dist) * force, fy = (dy / dist) * force;
        disp[a].x += fx; disp[a].y += fy;
        disp[b].x -= fx; disp[b].y -= fy;
      }
    }
    // Притяжение вдоль рёбер.
    for (const e of adj) {
      let dx = pos[e.from].x - pos[e.to].x, dy = pos[e.from].y - pos[e.to].y;
      let dist = Math.hypot(dx, dy) || 0.01;
      const force = (dist * dist) / k;
      const fx = (dx / dist) * force, fy = (dy / dist) * force;
      disp[e.from].x -= fx; disp[e.from].y -= fy;
      disp[e.to].x += fx; disp[e.to].y += fy;
    }
    for (const nd of nodes) {
      const d = disp[nd.id];
      const dl = Math.hypot(d.x, d.y) || 0.01;
      pos[nd.id].x += (d.x / dl) * Math.min(dl, temp);
      pos[nd.id].y += (d.y / dl) * Math.min(dl, temp);
    }
    temp *= 0.95;
  }
  return pos;
}

// Слои по глубине (ТЗ §28): мир → локации → подлокации → события/мобы →
// награды/предметы → эффекты → системные слои (сайт/профиль/прочее).
const DEPTH_TIERS = [
  ["city", "world_event"],
  ["location", "location_zone", "transition", "button"],
  ["sublocation", "location_resource", "location_loot", "location_mob_spawn", "location_weekly_limit", "location_weekly_rotation", "location_depletion_rule", "location_empty_event"],
  ["sublocation_node", "sublocation_transition", "event", "location_hidden_event", "location_event_answer", "npc", "quest", "raid"],
  ["mob", "mob_variant", "mob_skill", "mob_passive", "mob_resistance", "mob_effect", "mob_event_link", "mob_zone_link", "mob_phase"],
  ["item", "recipe", "profession", "workshop", "item_upgrade", "item_enchant", "item_disassemble"],
  ["effect", "trait", "blessing", "phase", "formula"],
  ["site_page", "site_page_block", "site_menu_item", "site_news", "site_guide", "site_faq", "site_banner", "site_announcement", "site_post", "site_rating", "site_lore", "site_where_is", "site_theme", "profile_tab", "profile_block", "profile_theme", "achievement", "fine", "level", "exp", "skill", "race", "guild", "registration", "workshop_message"],
];
const TIER_OF = (() => {
  const m = {};
  DEPTH_TIERS.forEach((types, i) => types.forEach((t) => { m[t] = i; }));
  return m;
})();
const DEFAULT_TIER = 3;
const LAYER_GAP = 240;
function tierOf(type) {
  if (type in TIER_OF) return TIER_OF[type];
  if (type.startsWith("location_")) return 2;
  if (type.startsWith("mob_")) return 4;
  if (type.startsWith("site_") || type.startsWith("profile_")) return 7;
  return DEFAULT_TIER;
}
// Проекция точки слоя (x,y в плоскости слоя, z по глубине) на экран —
// вращение по рысканью/тангажу + ортография (псевдо-3D, §29).
function project3d(x, y, z, yaw, pitch) {
  const cy = Math.cos(yaw), sy = Math.sin(yaw), cx = Math.cos(pitch), sx = Math.sin(pitch);
  const x1 = x * cy + z * sy;
  const z1 = -x * sy + z * cy;
  const y1 = y * cx - z1 * sx;
  const z2 = y * sx + z1 * cx;
  return { x: x1, y: y1, depth: z2 };
}

function nodeStroke(node) {
  if (node.has_errors || node.missing) return "#dc2626";
  if (node.status === "draft") return "#a3a3a3";
  return "#1f2937";
}
function nodeDash(node) {
  if (node.status === "draft") return "4 3";
  if (node.missing) return "2 2";
  return undefined;
}
function nodeOpacity(node) {
  if (node.missing) return 0.5;
  if (node.status === "disabled" || node.status === "archived") return 0.55;
  if (node.status === "external") return 0.7;
  return 1;
}

export function GraphSection({ guarded, onOpenSection }) {
  const [legend, setLegend] = useState(null);
  const [graph, setGraph] = useState({ nodes: [], edges: [] });
  const [positions, setPositions] = useState({});
  const [view, setView] = useState({ x: 0, y: 0, scale: 1 });
  const [enabledTypes, setEnabledTypes] = useState(null); // Set | null = все
  const [statusFilter, setStatusFilter] = useState("");
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState("full");
  const [selected, setSelected] = useState(null);
  const [detail, setDetail] = useState(null);
  const [pathInputs, setPathInputs] = useState({ source: "", target: "" });
  const [highlightPath, setHighlightPath] = useState([]);
  const [info, setInfo] = useState("");
  const [forceRender, setForceRender] = useState(false);
  const [render3d, setRender3d] = useState(false);
  const [cam, setCam] = useState({ yaw: 0.6, pitch: 0.5 });
  const [lowDetail, setLowDetail] = useState(false);
  const svgRef = useRef(null);
  const drag = useRef(null);

  const applyGraph = useCallback((g) => {
    const nodes = g?.nodes || [];
    const edges = g?.edges || [];
    setGraph({ nodes, edges });
    setPositions(computeLayout(nodes, edges));
    setView({ x: 0, y: 0, scale: 1 });
    setForceRender(false);
  }, []);

  const loadFull = useCallback(async () => {
    setMode("full"); setHighlightPath([]);
    const g = await guarded(() => fetchFullGraph());
    if (g) { applyGraph(g); setInfo(""); }
  }, [guarded, applyGraph]);

  useEffect(() => { (async () => {
    const l = await guarded(() => fetchGraphLegend());
    if (l) setLegend(l);
  })(); }, [guarded]);
  useEffect(() => { loadFull(); }, [loadFull]);

  const typeLabel = useCallback((t) => legend?.nodeTypes?.find((x) => x.value === t)?.label || t, [legend]);

  // Типы, реально присутствующие в текущем графе (для слоёв).
  const presentTypes = useMemo(() => {
    const s = new Set(graph.nodes.map((n) => n.type));
    return [...s].sort((a, b) => typeLabel(a).localeCompare(typeLabel(b)));
  }, [graph.nodes, typeLabel]);

  const isTypeOn = (t) => enabledTypes === null || enabledTypes.has(t);
  const toggleType = (t) => {
    setEnabledTypes((prev) => {
      const base = prev === null ? new Set(presentTypes) : new Set(prev);
      if (base.has(t)) base.delete(t); else base.add(t);
      return base.size === presentTypes.length ? null : base;
    });
  };

  const q = query.trim().toLowerCase();
  const matches = (n) => !q || n.title?.toLowerCase().includes(q) || n.entity_id?.toLowerCase().includes(q) || n.id.toLowerCase().includes(q);

  const visibleNodes = useMemo(() => graph.nodes.filter((n) =>
    isTypeOn(n.type) && (!statusFilter || n.status === statusFilter)
  ), [graph.nodes, enabledTypes, statusFilter, presentTypes]);
  const visibleIds = useMemo(() => new Set(visibleNodes.map((n) => n.id)), [visibleNodes]);
  const visibleEdges = useMemo(() => graph.edges.filter((e) => visibleIds.has(e.from) && visibleIds.has(e.to)), [graph.edges, visibleIds]);

  const pathSet = useMemo(() => new Set(highlightPath), [highlightPath]);

  // Экранные координаты узлов: в 2D — как есть, в 3D — проекция по слоям.
  const midTier = (DEPTH_TIERS.length - 1) / 2;
  const proj = useMemo(() => {
    if (!render3d) return positions;
    const map = {};
    for (const n of graph.nodes) {
      const base = positions[n.id];
      if (!base) continue;
      const z = (tierOf(n.type) - midTier) * LAYER_GAP;
      map[n.id] = project3d(base.x, base.y, z, cam.yaw, cam.pitch);
    }
    return map;
  }, [render3d, positions, graph.nodes, cam, midTier]);
  const depthRange = useMemo(() => {
    if (!render3d) return null;
    const ds = visibleNodes.map((n) => proj[n.id]?.depth).filter((d) => d !== undefined);
    if (!ds.length) return null;
    const min = Math.min(...ds), max = Math.max(...ds);
    return { min, max, span: (max - min) || 1 };
  }, [render3d, proj, visibleNodes]);
  const depthNorm = (id) => {
    if (!depthRange) return 0;
    const d = proj[id]?.depth;
    return d === undefined ? 0 : (d - depthRange.min) / depthRange.span; // 0 ближе, 1 дальше
  };
  const drawOrder = useMemo(() => {
    if (!render3d) return visibleNodes;
    return [...visibleNodes].sort((a, b) => (proj[b.id]?.depth || 0) - (proj[a.id]?.depth || 0));
  }, [render3d, visibleNodes, proj]);

  // --- Масштаб/панорама/перетаскивание ---
  const toGraph = (clientX, clientY) => {
    const rect = svgRef.current.getBoundingClientRect();
    return { x: (clientX - rect.left - view.x) / view.scale, y: (clientY - rect.top - view.y) / view.scale };
  };
  const onWheel = (e) => {
    e.preventDefault();
    const rect = svgRef.current.getBoundingClientRect();
    const mx = e.clientX - rect.left, my = e.clientY - rect.top;
    const factor = e.deltaY < 0 ? 1.12 : 1 / 1.12;
    setView((v) => {
      const scale = Math.min(3, Math.max(0.12, v.scale * factor));
      return { scale, x: mx - (mx - v.x) * (scale / v.scale), y: my - (my - v.y) * (scale / v.scale) };
    });
  };
  const onMouseDown = (e) => {
    if (e.target.dataset?.node) return;
    if (render3d) {
      drag.current = { type: "rotate", sx: e.clientX, sy: e.clientY, yaw: cam.yaw, pitch: cam.pitch };
    } else {
      drag.current = { type: "pan", sx: e.clientX, sy: e.clientY, ox: view.x, oy: view.y };
    }
  };
  const onNodeDown = (e, id) => {
    e.stopPropagation();
    if (render3d) return; // в 3D узлы не таскаем — клик открывает карточку
    const gp = toGraph(e.clientX, e.clientY);
    drag.current = { type: "node", id, dx: gp.x - positions[id].x, dy: gp.y - positions[id].y, moved: false };
  };
  const onMouseMove = (e) => {
    const d = drag.current;
    if (!d) return;
    if (d.type === "pan") {
      setView((v) => ({ ...v, x: d.ox + (e.clientX - d.sx), y: d.oy + (e.clientY - d.sy) }));
    } else if (d.type === "rotate") {
      const yaw = d.yaw + (e.clientX - d.sx) * 0.01;
      const pitch = Math.max(-1.4, Math.min(1.4, d.pitch + (e.clientY - d.sy) * 0.01));
      setCam({ yaw, pitch });
    } else if (d.type === "node") {
      const gp = toGraph(e.clientX, e.clientY);
      d.moved = true;
      setPositions((p) => ({ ...p, [d.id]: { x: gp.x - d.dx, y: gp.y - d.dy } }));
    }
  };
  const onMouseUp = () => { drag.current = null; };

  const fitView = () => {
    const ids = visibleNodes.map((n) => n.id).filter((id) => proj[id]);
    if (!ids.length || !svgRef.current) return;
    const xs = ids.map((id) => proj[id].x), ys = ids.map((id) => proj[id].y);
    const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
    const rect = svgRef.current.getBoundingClientRect();
    const pad = 80;
    const scale = Math.min(3, Math.max(0.12, Math.min((rect.width - pad) / (maxX - minX || 1), (rect.height - pad) / (maxY - minY || 1))));
    setView({ scale, x: rect.width / 2 - ((minX + maxX) / 2) * scale, y: rect.height / 2 - ((minY + maxY) / 2) * scale });
  };

  // --- Действия ---
  async function openNode(node) {
    setSelected(node.id);
    const [type, ...rest] = node.id.split(":");
    const d = await guarded(() => fetchGraphNode(type, rest.join(":")));
    if (d) setDetail(d);
  }
  async function focusNode(nodeId) {
    const [type, ...rest] = nodeId.split(":");
    const g = await guarded(() => fetchGraphAround(type, rest.join(":"), 2));
    if (g) { setMode("focus"); applyGraph(g); setInfo(`Фокус вокруг: ${nodeId}`); }
  }
  async function loadErrors() {
    setHighlightPath([]);
    const g = await guarded(() => fetchErrorGraph());
    if (g) { setMode("errors"); applyGraph(g); setInfo(`Только ошибки: узлов ${g.nodes?.length || 0}, сирот ${g.orphans?.length || 0}`); }
  }
  async function runPath() {
    const { source, target } = pathInputs;
    if (!source || !target) return;
    const g = await guarded(() => fetchGraphPath(source, target));
    if (g) {
      if (g.found) { applyGraph(g); setMode("path"); setHighlightPath(g.path || []); setInfo(`Путь: ${(g.path || []).length} шагов`); }
      else { setInfo(g.error || "Путь не найден."); }
    }
  }
  async function checkHealth() {
    const v = await guarded(() => fetchGraphValidation());
    if (v) setInfo(`Узлов: ${v.node_count}, рёбер: ${v.edge_count}, битых связей: ${v.broken_edges?.length || 0}, сирот: ${v.orphan_count}`);
  }

  const tooBig = visibleNodes.length > RENDER_SOFT_CAP && !forceRender;
  const selectedNode = graph.nodes.find((n) => n.id === selected) || detail?.node;

  return (
    <section className="ntv2-section ntgraph">
      <style>{GRAPH_CSS}</style>
      <header className="ntv2-section-head">
        <div>
          <h2>🕸️ Интерактивная схема</h2>
          <p className="ntv2-muted">Единая карта связей всех сущностей: локации, мобы, события, предметы, эффекты, достижения и др. Битые связи и недостижимые узлы подсвечены.</p>
        </div>
      </header>

      <div className="ntgraph-toolbar">
        <div className="ntgraph-modes">
          <button type="button" className={`ntv2-btn-mini${mode === "full" ? " active" : ""}`} onClick={loadFull}>Вся карта</button>
          <button type="button" className={`ntv2-btn-mini${mode === "errors" ? " active" : ""}`} onClick={loadErrors}>Только ошибки</button>
          <button type="button" className="ntv2-btn-mini" onClick={checkHealth}>Проверить схему</button>
          <button type="button" className={`ntv2-btn-mini${render3d ? " active" : ""}`} onClick={() => setRender3d((v) => !v)}>{render3d ? "🧊 3D" : "🗺️ 2D"}</button>
          <button type="button" className={`ntv2-btn-mini${lowDetail ? " active" : ""}`} onClick={() => setLowDetail((v) => !v)} title="Режим низкой детализации">⚡ Лёгкий</button>
        </div>
        <input className="ntgraph-search" placeholder="🔎 Поиск по названию/ID…" value={query} onChange={(e) => setQuery(e.target.value)} />
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="">Все статусы</option>
          <option value="published">Опубликовано</option>
          <option value="draft">Черновик</option>
          <option value="disabled">Отключено</option>
          <option value="archived">Архив</option>
          <option value="missing">Не найден</option>
        </select>
        <div className="ntgraph-zoom">
          <button type="button" className="ntv2-btn-mini" onClick={() => setView((v) => ({ ...v, scale: Math.min(3, v.scale * 1.2) }))}>＋</button>
          <button type="button" className="ntv2-btn-mini" onClick={() => setView((v) => ({ ...v, scale: Math.max(0.12, v.scale / 1.2) }))}>－</button>
          <button type="button" className="ntv2-btn-mini" onClick={fitView}>Вписать</button>
          <button type="button" className="ntv2-btn-mini" onClick={() => downloadFile("graph.json", JSON.stringify({ nodes: visibleNodes, edges: visibleEdges }, null, 2), "application/json")}>⬇ JSON</button>
          <button type="button" className="ntv2-btn-mini" onClick={() => downloadFile("graph.md", toMarkdown(visibleNodes, visibleEdges, mode), "text/markdown")}>⬇ MD</button>
        </div>
      </div>

      <div className="ntgraph-pathbar">
        <span>Путь:</span>
        <input placeholder="источник (type:id)" value={pathInputs.source} onChange={(e) => setPathInputs((p) => ({ ...p, source: e.target.value }))} />
        <span>→</span>
        <input placeholder="цель (type:id)" value={pathInputs.target} onChange={(e) => setPathInputs((p) => ({ ...p, target: e.target.value }))} />
        <button type="button" className="ntv2-btn-mini" onClick={runPath}>Построить путь</button>
        {info ? <span className="ntgraph-info">{info}</span> : null}
      </div>

      <div className="ntgraph-layers">
        <span className="ntgraph-layers-title">Слои:</span>
        <button type="button" className="ntv2-btn-mini" onClick={() => setEnabledTypes(null)}>Все</button>
        <button type="button" className="ntv2-btn-mini" onClick={() => setEnabledTypes(new Set())}>Снять</button>
        {presentTypes.map((t) => (
          <label key={t} className={`ntgraph-layer${isTypeOn(t) ? " on" : ""}`}>
            <input type="checkbox" checked={isTypeOn(t)} onChange={() => toggleType(t)} />
            <span className="ntgraph-dot" style={{ background: colorFor(t) }} />
            {typeLabel(t)}
          </label>
        ))}
      </div>

      {render3d ? (
        <div className="ntgraph-cambar">
          <span>Камера:</span>
          <button type="button" className="ntv2-btn-mini" onClick={() => setCam((c) => ({ ...c, yaw: c.yaw - 0.2 }))}>◄ Поворот</button>
          <button type="button" className="ntv2-btn-mini" onClick={() => setCam((c) => ({ ...c, yaw: c.yaw + 0.2 }))}>Поворот ►</button>
          <button type="button" className="ntv2-btn-mini" onClick={() => setCam((c) => ({ ...c, pitch: Math.min(1.4, c.pitch + 0.2) }))}>▲ Наклон</button>
          <button type="button" className="ntv2-btn-mini" onClick={() => setCam((c) => ({ ...c, pitch: Math.max(-1.4, c.pitch - 0.2) }))}>Наклон ▼</button>
          <button type="button" className="ntv2-btn-mini" onClick={() => setCam({ yaw: 0, pitch: 1.35 })}>Сверху</button>
          <button type="button" className="ntv2-btn-mini" onClick={() => setCam({ yaw: 0.9, pitch: 0.05 })}>Сбоку</button>
          <button type="button" className="ntv2-btn-mini" onClick={() => setCam({ yaw: 0.6, pitch: 0.5 })}>Изометрия</button>
          <span className="ntgraph-info">Перетаскивание фона — вращение, колесо — масштаб. Глубже = меньше и прозрачнее.</span>
        </div>
      ) : null}

      <div className="ntgraph-stage">
        {tooBig ? (
          <div className="ntgraph-toobig">
            <p>В схеме {visibleNodes.length} узлов — это много для одновременной отрисовки.</p>
            <p>Сузьте слои/статус или откройте «Только ошибки», либо отрисуйте всё принудительно.</p>
            <button type="button" className="ntv2-btn" onClick={() => setForceRender(true)}>Отрисовать всё ({visibleNodes.length})</button>
          </div>
        ) : (
          <svg
            ref={svgRef}
            className="ntgraph-svg"
            onWheel={onWheel}
            onMouseDown={onMouseDown}
            onMouseMove={onMouseMove}
            onMouseUp={onMouseUp}
            onMouseLeave={onMouseUp}
          >
            <defs>
              <marker id="ntgraph-arrow" markerWidth="9" markerHeight="9" refX="8" refY="3" orient="auto">
                <path d="M0,0 L0,6 L8,3 z" fill="#94a3b8" />
              </marker>
              <marker id="ntgraph-arrow-broken" markerWidth="9" markerHeight="9" refX="8" refY="3" orient="auto">
                <path d="M0,0 L0,6 L8,3 z" fill="#dc2626" />
              </marker>
            </defs>
            <g transform={`translate(${view.x},${view.y}) scale(${view.scale})`}>
              {visibleEdges.map((e) => {
                const a = proj[e.from], b = proj[e.to];
                if (!a || !b) return null;
                const broken = e.broken;
                const inPath = pathSet.has(e.from) && pathSet.has(e.to);
                const op = render3d ? 0.25 + 0.55 * (1 - (depthNorm(e.from) + depthNorm(e.to)) / 2) : 0.8;
                return (
                  <line
                    key={e.id}
                    x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                    stroke={broken ? "#dc2626" : inPath ? "#22c55e" : "#cbd5e1"}
                    strokeWidth={inPath ? 2.5 : 1.2}
                    strokeDasharray={broken ? "5 4" : undefined}
                    markerEnd={`url(#ntgraph-arrow${broken ? "-broken" : ""})`}
                    opacity={op}
                  />
                );
              })}
              {drawOrder.map((n) => {
                const p = proj[n.id];
                if (!p) return null;
                const dim = q && !matches(n);
                const sel = n.id === selected;
                const inPath = pathSet.has(n.id);
                const norm = render3d ? depthNorm(n.id) : 0;
                const depthScale = render3d ? (1.25 - 0.55 * norm) : 1;       // ближе крупнее (§29)
                const depthOpacity = render3d ? (0.5 + 0.5 * (1 - norm)) : 1; // дальше прозрачнее
                const r = (sel ? 16 : lowDetail ? 8 : 12) * depthScale;
                const baseOp = dim ? 0.2 : nodeOpacity(n) * depthOpacity;
                return (
                  <g key={n.id} transform={`translate(${p.x},${p.y})`} opacity={baseOp} style={{ cursor: "pointer" }}>
                    <circle
                      data-node="1"
                      r={r}
                      fill={colorFor(n.type)}
                      stroke={inPath ? "#22c55e" : sel ? "#2563eb" : nodeStroke(n)}
                      strokeWidth={inPath || sel ? 3 : (n.has_errors || n.missing ? 2.4 : 1.2)}
                      strokeDasharray={nodeDash(n)}
                      onMouseDown={(e) => onNodeDown(e, n.id)}
                      onClick={(e) => { e.stopPropagation(); if (!drag.current?.moved) openNode(n); }}
                    />
                    {lowDetail && !sel ? null : (
                      <text textAnchor="middle" y={r + 13} fontSize={11} fill="#334155" style={{ pointerEvents: "none" }}>
                        {(n.title || n.entity_id || n.id).slice(0, 22)}
                      </text>
                    )}
                  </g>
                );
              })}
            </g>
          </svg>
        )}

        {selectedNode ? (
          <aside className="ntgraph-card">
            <button type="button" className="ntgraph-card-close" onClick={() => { setSelected(null); setDetail(null); }}>✕</button>
            <h3>{selectedNode.title || selectedNode.entity_id}</h3>
            <div className="ntgraph-card-meta">
              <span className="ntgraph-dot" style={{ background: colorFor(selectedNode.type) }} />
              {typeLabel(selectedNode.type)} · <code>{selectedNode.id}</code>
            </div>
            <div className="ntgraph-card-row"><b>Статус:</b> {selectedNode.status || "—"}</div>
            {selectedNode.has_errors && selectedNode.errors?.length ? (
              <div className="ntgraph-card-errors">
                <b>Ошибки:</b>
                <ul>{selectedNode.errors.map((er, i) => <li key={i}>{er}</li>)}</ul>
              </div>
            ) : null}
            {selectedNode.warnings?.length ? (
              <div className="ntgraph-card-warn"><b>Предупреждения:</b> {selectedNode.warnings.length}</div>
            ) : null}
            {detail ? (
              <>
                <div className="ntgraph-card-row"><b>Исходящие связи:</b> {detail.outgoing?.length || 0}</div>
                <div className="ntgraph-card-row"><b>Входящие связи:</b> {detail.incoming?.length || 0}</div>
                <div className="ntgraph-card-row"><b>Где используется:</b> {detail.used_by?.length || 0}</div>
                {detail.outgoing?.length ? (
                  <details className="ntgraph-card-list"><summary>Ведёт к…</summary>
                    <ul>{detail.outgoing.map((e) => <li key={e.id}>{e.label}: <code>{e.to}</code>{e.broken ? " ⚠️" : ""}</li>)}</ul>
                  </details>
                ) : null}
                {detail.incoming?.length ? (
                  <details className="ntgraph-card-list"><summary>Используется в…</summary>
                    <ul>{detail.incoming.map((e) => <li key={e.id}><code>{e.from}</code> {e.label}{e.broken ? " ⚠️" : ""}</li>)}</ul>
                  </details>
                ) : null}
              </>
            ) : null}
            <div className="ntgraph-card-actions">
              <button type="button" className="ntv2-btn-mini" onClick={() => focusNode(selectedNode.id)}>Показать связи</button>
              {onOpenSection ? (
                <button type="button" className="ntv2-btn-mini" onClick={() => onOpenSection(sectionForType(selectedNode.type))}>Открыть в конструкторе</button>
              ) : null}
              <button type="button" className="ntv2-btn-mini" onClick={() => { setPathInputs((p) => ({ ...p, source: selectedNode.id })); }}>В путь: источник</button>
              <button type="button" className="ntv2-btn-mini" onClick={() => { setPathInputs((p) => ({ ...p, target: selectedNode.id })); }}>В путь: цель</button>
              <button type="button" className="ntv2-btn-mini" onClick={() => { try { navigator.clipboard?.writeText(selectedNode.id); setInfo("ID скопирован: " + selectedNode.id); } catch { /* noop */ } }}>Скопировать ID</button>
            </div>
          </aside>
        ) : null}
      </div>

      <footer className="ntgraph-foot">
        <span>Узлов: {visibleNodes.length} / {graph.nodes.length} · Рёбер: {visibleEdges.length}</span>
        <span className="ntgraph-legend-hint">Колесо — масштаб, перетаскивание фона — панорама, узел — карточка. Красная обводка — ошибка, пунктир — черновик, серый — отключён.</span>
      </footer>
    </section>
  );
}

const GRAPH_CSS = `
.ntgraph-toolbar,.ntgraph-pathbar,.ntgraph-layers,.ntgraph-cambar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:8px 0}
.ntgraph-cambar{font-size:13px}
.ntgraph-toolbar .ntgraph-search{flex:1;min-width:180px;padding:6px 10px;border:1px solid #cbd5e1;border-radius:8px}
.ntgraph-modes{display:flex;gap:6px}
.ntv2-btn-mini.active{background:#2563eb;color:#fff;border-color:#2563eb}
.ntgraph-zoom{display:flex;gap:4px;margin-left:auto}
.ntgraph-pathbar input{padding:5px 8px;border:1px solid #cbd5e1;border-radius:8px;min-width:150px}
.ntgraph-info{color:#2563eb;font-size:12px}
.ntgraph-layers-title{font-weight:600;font-size:13px}
.ntgraph-layer{display:inline-flex;align-items:center;gap:5px;font-size:12px;padding:3px 8px;border:1px solid #e2e8f0;border-radius:999px;cursor:pointer;opacity:.5}
.ntgraph-layer.on{opacity:1;background:#f1f5f9}
.ntgraph-dot{width:10px;height:10px;border-radius:50%;display:inline-block;border:1px solid #1f2937}
.ntgraph-stage{position:relative;border:1px solid #e2e8f0;border-radius:12px;overflow:hidden;background:#f8fafc;height:62vh;min-height:420px}
.ntgraph-svg{width:100%;height:100%;display:block;cursor:grab}
.ntgraph-svg:active{cursor:grabbing}
.ntgraph-toobig{display:flex;flex-direction:column;gap:10px;align-items:center;justify-content:center;height:100%;text-align:center;color:#475569;padding:20px}
.ntgraph-card{position:absolute;top:10px;right:10px;width:320px;max-height:calc(100% - 20px);overflow:auto;background:#fff;border:1px solid #cbd5e1;border-radius:12px;padding:14px;box-shadow:0 8px 30px rgba(0,0,0,.12)}
.ntgraph-card-close{position:absolute;top:8px;right:8px;border:none;background:transparent;font-size:16px;cursor:pointer}
.ntgraph-card h3{margin:0 24px 6px 0;font-size:16px}
.ntgraph-card-meta{display:flex;align-items:center;gap:6px;font-size:12px;color:#475569;margin-bottom:8px}
.ntgraph-card-row{font-size:13px;margin:3px 0}
.ntgraph-card-errors{background:#fef2f2;border:1px solid #fecaca;border-radius:8px;padding:8px;margin:8px 0;font-size:12px}
.ntgraph-card-errors ul,.ntgraph-card-list ul{margin:4px 0 0;padding-left:18px}
.ntgraph-card-warn{font-size:12px;color:#b45309;margin:4px 0}
.ntgraph-card-list{margin:6px 0;font-size:12px}
.ntgraph-card-list code,.ntgraph-card-meta code,.ntgraph-card-row code{font-size:11px}
.ntgraph-card-actions{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}
.ntgraph-foot{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;font-size:12px;color:#64748b;margin-top:8px}
`;
