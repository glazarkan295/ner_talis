import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  createCityItem,
  cityLifecycle,
  deleteCityItem,
  fetchCityItem,
  fetchCityItems,
  fetchCityMeta,
  fetchCityNodeRuntime,
  fetchCityTree,
  fetchCityWhereUsed,
  updateCityItem,
  validateCityItem,
} from "../../../api/adminCityApi.js";
import {
  tr, CITY_KIND, CITY_NODE_TYPE, CITY_BUTTON_ACTION, CITY_SHOP_KIND,
  CITY_SERVICE_KIND, CITY_STOCK_TYPE, CURRENCY,
} from "../../../i18n/adminLabels.js";
import { ConfirmModal } from "../ConfirmModal.jsx";
import { EmojiInput, EmojiTextarea } from "../EmojiField.jsx";
import { ImageUploadField } from "../ImageUploadField.jsx";
import { MessageComposer } from "../MessageComposer.jsx";
import { SearchBox, NoResults, filterEntities } from "../SearchFilter.jsx";

const STATUS_TONE = { published: "ntv2-badge-owner", error: "ntv2-badge-error", disabled: "ntv2-badge-danger" };
const KIND_NEW = { city_node: "＋ Узел", city_button: "＋ Кнопка", city_shop_item: "＋ Товар", city_service: "＋ Сервис", criminal_zone: "＋ Криминальная зона" };

const EMPTY_BY_KIND = {
  city_node: { name: "", node_type: "quarter", parent_id: "", short_description: "", description: "", image: "", background: "", order: 0, access_condition: "", restrictions: "", entry_message: null },
  city_button: { label: "", icon: "", action: "goto_node", node_id: "", target_node_id: "", order: 0, condition: "", cost: 0, energy_cost: 0, success_text: "", denied_text: "" },
  city_shop_item: { item_id: "", shop_kind: "city_market", node_id: "", price_buy: 0, price_sell: 0, currency: "copper", stock: 0, per_player_limit: 0, daily_limit: 0, weekly_limit: 0, appear_chance: 100, stock_type: "always", can_buy: true, can_sell: false },
  city_service: { name: "", service_kind: "forge", node_id: "", description: "", craft_time: 0, cost: 0, success_chance: 100, upgrade_chance: 0, enabled: true, start_text: "", success_text: "", fail_text: "", no_resources_text: "" },
  criminal_zone: { name: "", node_id: "", services: "", raid_chance: 0, fine_amount: 0, fine_deadline_days: 0, move_to_node: "", restrictions: "", enter_text: "", raid_text: "", success_text: "", fail_text: "" },
};

const SCHEMA_BY_KIND = {
  city_node: [
    { k: "name", label: "Название узла", type: "text" },
    { k: "node_type", label: "Тип узла", type: "meta", metaKey: "nodeTypes", labelMap: CITY_NODE_TYPE },
    { k: "parent_id", label: "Родительский узел (ID)", type: "text" },
    { k: "order", label: "Порядок отображения", type: "number" },
    { k: "short_description", label: "Краткое описание", type: "textarea" },
    { k: "description", label: "Полное описание", type: "textarea" },
    { k: "image", label: "Изображение", type: "image" },
    { k: "background", label: "Фон", type: "image" },
    { k: "access_condition", label: "Условие доступа", type: "text" },
    { k: "restrictions", label: "Ограничения", type: "text" },
    { k: "entry_message", label: "Сообщение игроку при входе", type: "message" },
  ],
  city_button: [
    { k: "label", label: "Текст кнопки", type: "text" },
    { k: "icon", label: "Иконка/эмодзи", type: "text" },
    { k: "action", label: "Действие", type: "meta", metaKey: "buttonActions", labelMap: CITY_BUTTON_ACTION },
    { k: "node_id", label: "Узел кнопки (ID)", type: "text" },
    { k: "target_node_id", label: "Куда ведёт (ID узла)", type: "text" },
    { k: "order", label: "Порядок", type: "number" },
    { k: "condition", label: "Условие показа/нажатия", type: "text" },
    { k: "cost", label: "Стоимость действия", type: "number" },
    { k: "energy_cost", label: "Расход энергии", type: "number" },
    { k: "success_text", label: "Текст при успехе", type: "textarea" },
    { k: "denied_text", label: "Текст при запрете", type: "textarea" },
  ],
  city_shop_item: [
    { k: "item_id", label: "Предмет (ID)", type: "text" },
    { k: "shop_kind", label: "Торговая точка", type: "meta", metaKey: "shopKinds", labelMap: CITY_SHOP_KIND },
    { k: "node_id", label: "Узел (ID)", type: "text" },
    { k: "price_buy", label: "Цена покупки", type: "number" },
    { k: "price_sell", label: "Цена продажи", type: "number" },
    { k: "currency", label: "Валюта", type: "meta", metaKey: "currencies", labelMap: CURRENCY },
    { k: "stock", label: "Общий склад", type: "number" },
    { k: "per_player_limit", label: "Лимит на игрока", type: "number" },
    { k: "daily_limit", label: "Лимит на день", type: "number" },
    { k: "weekly_limit", label: "Лимит на неделю", type: "number" },
    { k: "appear_chance", label: "Шанс появления (%)", type: "number" },
    { k: "stock_type", label: "Доступность", type: "meta", metaKey: "stockTypes", labelMap: CITY_STOCK_TYPE },
    { k: "can_buy", label: "Можно купить", type: "checkbox" },
    { k: "can_sell", label: "Можно продать", type: "checkbox" },
  ],
  city_service: [
    { k: "name", label: "Название сервиса", type: "text" },
    { k: "service_kind", label: "Тип сервиса", type: "meta", metaKey: "serviceKinds", labelMap: CITY_SERVICE_KIND },
    { k: "node_id", label: "Узел (ID)", type: "text" },
    { k: "description", label: "Описание", type: "textarea" },
    { k: "craft_time", label: "Время создания (сек)", type: "number" },
    { k: "cost", label: "Стоимость", type: "number" },
    { k: "success_chance", label: "Шанс успеха (%)", type: "number" },
    { k: "upgrade_chance", label: "Шанс улучшения качества (%)", type: "number" },
    { k: "enabled", label: "Включён", type: "checkbox" },
    { k: "start_text", label: "Текст начала работы", type: "textarea" },
    { k: "success_text", label: "Текст успешного создания", type: "textarea" },
    { k: "fail_text", label: "Текст провала", type: "textarea" },
    { k: "no_resources_text", label: "Текст нехватки ресурсов", type: "textarea" },
  ],
  criminal_zone: [
    { k: "name", label: "Название зоны", type: "text" },
    { k: "node_id", label: "Узел (ID)", type: "text" },
    { k: "services", label: "Доступные услуги", type: "text" },
    { k: "raid_chance", label: "Шанс облавы (%)", type: "number" },
    { k: "fine_amount", label: "Сумма штрафа", type: "number" },
    { k: "fine_deadline_days", label: "Срок оплаты (дн.)", type: "number" },
    { k: "move_to_node", label: "Куда переносить (ID узла)", type: "text" },
    { k: "restrictions", label: "Ограничения", type: "text" },
    { k: "enter_text", label: "Текст при входе", type: "textarea" },
    { k: "raid_text", label: "Текст при облаве", type: "textarea" },
    { k: "success_text", label: "Текст при успехе", type: "textarea" },
    { k: "fail_text", label: "Текст при провале", type: "textarea" },
  ],
};

function Field({ label, children }) {
  return <label className="ntv2-field"><span>{label}</span>{children}</label>;
}

function CityForm({ schema, value, onChange, meta, disabled, uploadKey }) {
  const set = (k, v) => onChange({ ...value, [k]: v });
  return (
    <div className="ntv2-world-form">
      {schema.map((f) => {
        if (f.type === "message") return <MessageComposer key={f.k} label={f.label} value={value[f.k]} category="city" uploadKey={`${uploadKey || "new"}_${f.k}`} disabled={disabled} onChange={(v) => set(f.k, v)} />;
        if (f.type === "image") return <ImageUploadField key={f.k} label={f.label} value={value[f.k] || ""} category="city" uploadKey={`${uploadKey || "new"}_${f.k}`} disabled={disabled} onChange={(v) => set(f.k, v)} />;
        if (f.type === "checkbox") return <label className="ntv2-check" key={f.k}><input type="checkbox" checked={Boolean(value[f.k])} disabled={disabled} onChange={(e) => set(f.k, e.target.checked)} /> {f.label}</label>;
        if (f.type === "number") return <Field label={f.label} key={f.k}><input type="number" value={value[f.k] ?? ""} disabled={disabled} onChange={(e) => set(f.k, e.target.value)} /></Field>;
        if (f.type === "textarea") return <Field label={f.label} key={f.k}><EmojiTextarea rows={2} value={value[f.k] || ""} disabled={disabled} onChange={(v) => set(f.k, v)} /></Field>;
        if (f.type === "meta") {
          const options = (meta && meta[f.metaKey]) || [];
          return <Field label={f.label} key={f.k}><select value={value[f.k] ?? ""} disabled={disabled} onChange={(e) => set(f.k, e.target.value)}><option value="">—</option>{options.map((o) => <option key={o} value={o}>{tr(f.labelMap, o)}</option>)}</select></Field>;
        }
        return <Field label={f.label} key={f.k}><EmojiInput value={value[f.k] || ""} disabled={disabled} onChange={(v) => set(f.k, v)} /></Field>;
      })}
    </div>
  );
}

// Дерево узлов (§5): город/крепость → кварталы → здания → сервисы.
function CityTree({ guarded }) {
  const [tree, setTree] = useState([]);
  useEffect(() => { (async () => { const p = await guarded(() => fetchCityTree()); if (p) setTree(p.tree || []); })(); }, [guarded]);
  const renderNode = (n) => (
    <div key={n.id} style={{ paddingLeft: n.depth * 16 }} className="ntv2-hint">
      {"› "}<b>{n.name}</b> <span className="ntv2-mono">{n.id}</span> · {tr(CITY_NODE_TYPE, n.node_type)} {n.status !== "published" ? `(${n.status})` : ""}
      {(n.children || []).map(renderNode)}
    </div>
  );
  return (
    <div className="ntv2-panel">
      <h4 className="ntv2-subhead">Дерево узлов</h4>
      {!tree.length ? <p className="ntv2-hint">Узлов пока нет.</p> : tree.map(renderNode)}
    </div>
  );
}

export function CitySection({ guarded, hasPerm }) {
  const [meta, setMeta] = useState(null);
  const [kind, setKind] = useState("city_node");
  const [list, setList] = useState([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [editing, setEditing] = useState(null);
  const [confirm, setConfirm] = useState(null);
  const [showTree, setShowTree] = useState(false);
  const [usedBy, setUsedBy] = useState(null);
  const [runtimeView, setRuntimeView] = useState(null);
  const [query, setQuery] = useState("");

  const can = useMemo(() => ({
    create: hasPerm("city.create"), edit: hasPerm("city.edit"), publish: hasPerm("city.publish"),
    disable: hasPerm("city.disable"), archive: hasPerm("city.archive"), del: hasPerm("city.delete"),
  }), [hasPerm]);

  const load = useCallback(async () => { const p = await guarded(() => fetchCityItems(kind, statusFilter)); if (p) setList(p.items || []); }, [guarded, kind, statusFilter]);
  useEffect(() => { (async () => { const m = await guarded(() => fetchCityMeta()); if (m) setMeta(m); })(); }, [guarded]);
  useEffect(() => { load(); }, [load]);

  const statuses = meta?.statuses || [];
  const statusLabel = (v) => statuses.find((s) => s.value === v)?.label || v;
  const itemTitle = (item) => { const d = item.data || {}; return d.name || d.label || d.item_id || item.id; };

  function switchKind(k) { setKind(k); setEditing(null); setStatusFilter(""); }
  function startCreate() { setEditing({ id: "", data: { ...(EMPTY_BY_KIND[kind] || {}) }, status: "draft", validation: null, isNew: true }); }
  async function openItem(id) {
    setUsedBy(null);
    setRuntimeView(null);
    const p = await guarded(() => fetchCityItem(kind, id));
    if (p?.item) setEditing({ id, data: { ...(EMPTY_BY_KIND[kind] || {}), ...(p.item.data || {}) }, status: p.item.status, validation: p.validation, isNew: false });
  }
  async function loadWhereUsed() { const p = await guarded(() => fetchCityWhereUsed(kind, editing.id)); if (p) setUsedBy(p.usedBy || []); }
  async function loadRuntimeView() { const p = await guarded(() => fetchCityNodeRuntime(editing.id)); if (p) setRuntimeView({ ...p.view, _live: p.liveEnabled }); }
  async function save() {
    const e = editing;
    if (e.isNew) { const p = await guarded(() => createCityItem(kind, e.id.trim(), e.data, ""), "Создано."); if (p?.item) await openItem(e.id.trim()); }
    else { await guarded(() => updateCityItem(kind, e.id, e.data, "правка"), "Сохранено."); await openItem(e.id); }
    await load();
  }
  async function runValidate() { const p = await guarded(() => validateCityItem(kind, editing.id, ""), "Проверка выполнена."); if (p?.validation) setEditing((c) => ({ ...c, validation: p.validation })); }
  async function refreshEditing() { await load(); if (editing) await openItem(editing.id); }

  if (!meta) return <section className="ntv2-section"><h2>Город и крепость</h2><p className="ntv2-hint">Загрузка…</p></section>;

  if (editing) {
    const disabled = !(editing.isNew ? can.create : can.edit);
    const v = editing.validation;
    return (
      <section className="ntv2-section">
        <div className="ntv2-card-head">
          <button type="button" className="ntv2-btn" onClick={() => setEditing(null)}>← К списку</button>
          <h2>{editing.isNew ? KIND_NEW[kind] : itemTitle({ data: editing.data, id: editing.id })}</h2>
          {!editing.isNew ? <span className={`ntv2-badge ${STATUS_TONE[editing.status] || ""}`}>{statusLabel(editing.status)}</span> : null}
        </div>
        {editing.isNew ? <Field label="ID (латиница)"><input value={editing.id} onChange={(e) => setEditing({ ...editing, id: e.target.value })} /></Field> : <p className="ntv2-hint ntv2-mono">{editing.id}</p>}

        <CityForm schema={SCHEMA_BY_KIND[kind]} value={editing.data} onChange={(data) => setEditing({ ...editing, data })} meta={meta} disabled={disabled} uploadKey={editing.id} />

        {v ? (
          <div className={`ntv2-panel ${v.ok ? "" : "ntv2-danger-zone"}`}>
            <h4 className="ntv2-subhead">{v.ok ? "✅ Готово к публикации" : "❌ Проверка не пройдена"}</h4>
            {(v.errors || []).map((e, i) => <div className="ntv2-error" key={"e" + i}>{e}</div>)}
            {(v.warnings || []).map((w, i) => <p className="ntv2-hint" key={"w" + i}>⚠️ {w}</p>)}
          </div>
        ) : null}

        {!editing.isNew && kind === "city_node" ? (
          <div className="ntv2-panel">
            <div className="ntv2-card-head" style={{ marginBottom: 6 }}>
              <h4 className="ntv2-subhead" style={{ margin: 0 }}>Рантайм-вид (как увидит бот)</h4>
              <button type="button" className="ntv2-btn" onClick={loadRuntimeView}>Показать</button>
            </div>
            {runtimeView === null ? <p className="ntv2-hint">Предпросмотр узла из опубликованного контента (живой город включается флагом CITY_CONSTRUCTOR_LIVE).</p> : null}
            {runtimeView && runtimeView.id === undefined ? <p className="ntv2-hint">Узел не опубликован — рантайм-вид доступен только для опубликованных узлов.</p> : null}
            {runtimeView && runtimeView.id ? (
              <div>
                {runtimeView._live ? null : <p className="ntv2-hint">⚠️ Флаг CITY_CONSTRUCTOR_LIVE выключен — в живой игре пока используется статическая навигация.</p>}
                <p><b>{runtimeView.name}</b> — {runtimeView.description || "без описания"}</p>
                <div className="ntv2-hint">Кнопки: {(runtimeView.buttons || []).map((b) => b.label).join(", ") || "—"}</div>
                <div className="ntv2-hint">Переходы (дети): {(runtimeView.children || []).map((c) => c.name).join(", ") || "—"}</div>
                <div className="ntv2-hint">Товары: {(runtimeView.shop_items || []).length} · Сервисы: {(runtimeView.services || []).length} · Криминал: {(runtimeView.criminal_zones || []).length}</div>
              </div>
            ) : null}
          </div>
        ) : null}

        {!editing.isNew ? (
          <div className="ntv2-panel">
            <div className="ntv2-card-head" style={{ marginBottom: 6 }}>
              <h4 className="ntv2-subhead" style={{ margin: 0 }}>Где используется</h4>
              <button type="button" className="ntv2-btn" onClick={loadWhereUsed}>Проверить связи</button>
            </div>
            {usedBy === null ? <p className="ntv2-hint">Нажмите «Проверить связи», чтобы увидеть, что ссылается на этот объект.</p> : null}
            {usedBy !== null && !usedBy.length ? <p className="ntv2-hint">Ничего не ссылается — объект можно безопасно изменить/отключить.</p> : null}
            {usedBy && usedBy.length ? (
              <div className="ntv2-list">
                {usedBy.map((u) => (
                  <div className="ntv2-list-row" key={u.id}>
                    <b>{u.name}</b>
                    <span className="ntv2-mono">{u.id}</span>
                    <span className="ntv2-hint">{tr(CITY_KIND, u.kind)} · {(u.fields || []).join(", ")}</span>
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        ) : null}

        <div className="ntv2-form-row" style={{ marginTop: 14 }}>
          {!disabled ? <button type="button" className="ntv2-btn ntv2-btn-primary" disabled={editing.isNew && !editing.id.trim()} onClick={save}>{editing.isNew ? "Создать" : "Сохранить"}</button> : null}
          {!editing.isNew && can.edit ? <button type="button" className="ntv2-btn" onClick={runValidate}>Проверить</button> : null}
          {!editing.isNew && can.publish ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => setConfirm({ title: "Опубликовать?", dangerous: true, confirmLabel: "Опубликовать", body: <p>Объект будет проверен и опубликован в живой структуре.</p>, run: async (r) => { await guarded(() => cityLifecycle(kind, editing.id, "publish", r), "Опубликовано."); await refreshEditing(); } })}>Опубликовать</button> : null}
          {!editing.isNew && can.disable && editing.status === "published" ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => setConfirm({ title: "Отключить?", dangerous: true, confirmLabel: "Отключить", body: <p>Объект перестанет действовать.</p>, run: async (r) => { await guarded(() => cityLifecycle(kind, editing.id, "disable", r), "Отключено."); await refreshEditing(); } })}>Отключить</button> : null}
          {!editing.isNew && can.archive ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => setConfirm({ title: "В архив?", dangerous: true, confirmLabel: "В архив", body: <p>Объект уйдёт в архив.</p>, run: async (r) => { await guarded(() => cityLifecycle(kind, editing.id, "archive", r), "В архиве."); await refreshEditing(); } })}>В архив</button> : null}
          {!editing.isNew && can.del ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => setConfirm({ title: "Удалить?", dangerous: true, confirmLabel: "Удалить", body: <p>Полное удаление объекта.</p>, run: async (r) => { await guarded(() => deleteCityItem(kind, editing.id, editing.id, r), "Удалено."); setEditing(null); await load(); } })}>Удалить</button> : null}
        </div>

        <ConfirmModal open={Boolean(confirm)} title={confirm?.title} body={confirm?.body} dangerous={confirm?.dangerous} confirmLabel={confirm?.confirmLabel} requireReason
          onConfirm={async (r) => { await confirm.run(r); setConfirm(null); }} onCancel={() => setConfirm(null)} />
      </section>
    );
  }

  return (
    <section className="ntv2-section">
      <h2>Город и крепость</h2>
      <p className="ntv2-hint">Город и крепость как система узлов: узлы → кнопки → товары/сервисы/криминальные зоны.</p>
      <div className="ntv2-subnav">
        {meta.kinds.map((k) => <button key={k} type="button" className={`ntv2-subnav-item${k === kind ? " active" : ""}`} onClick={() => switchKind(k)}>{tr(CITY_KIND, k)}</button>)}
      </div>
      <div className="ntv2-filters">
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="">Все статусы</option>
          {statuses.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
        </select>
        {can.create ? <button type="button" className="ntv2-btn ntv2-btn-primary" onClick={startCreate}>{KIND_NEW[kind]}</button> : null}
        <button type="button" className="ntv2-btn" onClick={() => setShowTree((s) => !s)}>{showTree ? "Скрыть дерево" : "Дерево узлов"}</button>
        <SearchBox value={query} onChange={setQuery} />
      </div>
      {showTree ? <CityTree guarded={guarded} /> : null}
      {!list.length ? <p className="ntv2-hint">Объектов нет.</p> : null}
      <NoResults query={list.length ? query : ""} />
      <div className="ntv2-list">
        {filterEntities(list, query).map((item) => (
          <button key={item.id} type="button" className="ntv2-list-row ntv2-player-row" onClick={() => openItem(item.id)}>
            <b>{itemTitle(item)}</b>
            <span className="ntv2-mono">{item.id}</span>
            <span className={`ntv2-badge ${STATUS_TONE[item.status] || ""}`}>{statusLabel(item.status)}</span>
            {kind === "city_node" && item.data?.node_type ? <span className="ntv2-hint">{tr(CITY_NODE_TYPE, item.data.node_type)}</span> : null}
            {kind === "city_button" && item.data?.action ? <span className="ntv2-hint">{tr(CITY_BUTTON_ACTION, item.data.action)}</span> : null}
            {kind === "city_service" && item.data?.service_kind ? <span className="ntv2-hint">{tr(CITY_SERVICE_KIND, item.data.service_kind)}</span> : null}
          </button>
        ))}
      </div>
    </section>
  );
}
