import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  createEffect,
  deleteEffect,
  effectLifecycle,
  fetchEffect,
  fetchEffectMeta,
  fetchEffects,
  fetchEffectUsage,
  importExistingEffects,
  updateEffect,
  validateEffect,
} from "../../../api/adminEffectApi.js";
import { tr, EFFECT_TYPE, EFFECT_SOURCE, EFFECT_TARGET, EFFECT_ACTIVE_WHEN, EFFECT_STACK_RULE, STAT, RESOURCE, CONTROL_KIND, ZONE_ELEMENT } from "../../../i18n/adminLabels.js";
import { ConfirmModal } from "../ConfirmModal.jsx";
import { SearchBox, NoResults, filterEntities } from "../SearchFilter.jsx";
import { VersionHistory } from "../VersionHistory.jsx";

const STATUS_TONE = { published: "ntv2-badge-owner", error: "ntv2-badge-error", disabled: "ntv2-badge-danger" };

const EMPTY = {
  effect_name: "", effect_type: "stat_modifier", source_type: "item", target: "self",
  active_when: "equipped", stack_rule: "strongest_only", player_text: "", admin_description: "",
  show_to_player: true, apply_chance_percent: "", duration_turns: "", duration_seconds: "",
  max_stacks: "", can_be_cleansed: false, cleanse_tags: "", can_trigger_effects: false, can_be_reflected: false,
  // type-specific
  stat: "strength", resource: "hp", control_kind: "stun", zone_element: "fire",
  // common numeric values
  flat_bonus: "", percent_bonus: "", value_percent: "", percent_max_hp_damage: "",
  reflect_percent: "", absorb_percent_from_damage: "",
};

function Field({ label, children }) {
  return <label className="ntv2-field"><span>{label}</span>{children}</label>;
}

export function EffectsSection({ guarded, hasPerm }) {
  const [meta, setMeta] = useState(null);
  const [list, setList] = useState([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState(null);
  const [confirm, setConfirm] = useState(null);
  const [usage, setUsage] = useState(null);

  const can = useMemo(() => ({
    create: hasPerm("effect.create"), edit: hasPerm("effect.edit"), validate: hasPerm("effect.validate"),
    publish: hasPerm("effect.publish"), disable: hasPerm("effect.disable"),
    archive: hasPerm("effect.archive"), del: hasPerm("effect.delete"),
  }), [hasPerm]);

  const load = useCallback(async () => { const p = await guarded(() => fetchEffects(statusFilter)); if (p) setList(p.items || []); }, [guarded, statusFilter]);
  useEffect(() => { (async () => { const m = await guarded(() => fetchEffectMeta()); if (m) setMeta(m); })(); }, [guarded]);
  useEffect(() => { load(); }, [load]);

  const statuses = meta?.statuses || [];
  const statusLabel = (v) => statuses.find((s) => s.value === v)?.label || v;

  async function openItem(id) {
    const p = await guarded(() => fetchEffect(id));
    if (p?.item) setEditing({ id, data: { ...EMPTY, ...(p.item.data || {}) }, status: p.item.status, validation: p.validation, isNew: false });
    const u = await guarded(() => fetchEffectUsage(id));
    setUsage(u?.usage || []);
  }
  function startCreate() { setUsage(null); setEditing({ id: "", data: { ...EMPTY }, status: "draft", validation: null, isNew: true }); }

  async function save() {
    const e = editing;
    if (e.isNew) { const p = await guarded(() => createEffect(e.id.trim(), e.data, ""), "Создано."); if (p?.item) await openItem(e.id.trim()); }
    else { await guarded(() => updateEffect(e.id, e.data, "правка"), "Сохранено."); await openItem(e.id); }
    await load();
  }
  async function runValidate() { const p = await guarded(() => validateEffect(editing.id, ""), "Проверка выполнена."); if (p?.validation) setEditing((c) => ({ ...c, validation: p.validation })); }
  async function refreshEditing() { await load(); if (editing) await openItem(editing.id); }

  if (!meta) return <section className="ntv2-section"><h2>Конструктор эффектов</h2><p className="ntv2-hint">Загрузка…</p></section>;

  if (editing) {
    const d = editing.data;
    const set = (k, v) => setEditing({ ...editing, data: { ...d, [k]: v } });
    const disabled = !(editing.isNew ? can.create : can.edit);
    const v = editing.validation;
    const flag = (key, label) => <label className="ntv2-check" key={key}><input type="checkbox" checked={Boolean(d[key])} disabled={disabled} onChange={(e) => set(key, e.target.checked)} /> {label}</label>;
    const num = (key, label) => <Field label={label} key={key}><input type="number" value={d[key]} disabled={disabled} onChange={(e) => set(key, e.target.value)} /></Field>;
    const et = d.effect_type;
    return (
      <section className="ntv2-section">
        <div className="ntv2-card-head">
          <button type="button" className="ntv2-btn" onClick={() => setEditing(null)}>← К списку</button>
          <h2>{editing.isNew ? "Новый эффект" : d.effect_name || editing.id}</h2>
          {!editing.isNew ? <span className={`ntv2-badge ${STATUS_TONE[editing.status] || ""}`}>{statusLabel(editing.status)}</span> : null}
        </div>
        {editing.isNew ? <Field label="effect_id (латиница)"><input value={editing.id} onChange={(e) => setEditing({ ...editing, id: e.target.value })} /></Field> : <p className="ntv2-hint ntv2-mono">{editing.id}</p>}

        <div className="ntv2-world-form">
          <div className="ntv2-form-row">
            <Field label="Название (админ)"><input value={d.effect_name} disabled={disabled} onChange={(e) => set("effect_name", e.target.value)} /></Field>
            <Field label="Тип эффекта"><select value={d.effect_type} disabled={disabled} onChange={(e) => set("effect_type", e.target.value)}>{meta.effectTypes.map((x) => <option key={x} value={x}>{tr(EFFECT_TYPE, x)}</option>)}</select></Field>
          </div>
          <div className="ntv2-form-row">
            <Field label="Источник"><select value={d.source_type} disabled={disabled} onChange={(e) => set("source_type", e.target.value)}>{meta.sourceTypes.map((x) => <option key={x} value={x}>{tr(EFFECT_SOURCE, x)}</option>)}</select></Field>
            <Field label="Цель"><select value={d.target} disabled={disabled} onChange={(e) => set("target", e.target.value)}>{meta.targets.map((x) => <option key={x} value={x}>{tr(EFFECT_TARGET, x)}</option>)}</select></Field>
            <Field label="Когда работает"><select value={d.active_when} disabled={disabled} onChange={(e) => set("active_when", e.target.value)}>{meta.activeWhen.map((x) => <option key={x} value={x}>{tr(EFFECT_ACTIVE_WHEN, x)}</option>)}</select></Field>
            <Field label="Стак"><select value={d.stack_rule} disabled={disabled} onChange={(e) => set("stack_rule", e.target.value)}>{meta.stackRules.map((x) => <option key={x} value={x}>{tr(EFFECT_STACK_RULE, x)}</option>)}</select></Field>
          </div>

          {/* Type-specific selectors */}
          <div className="ntv2-form-row">
            {et === "stat_modifier" ? <Field label="Характеристика"><select value={d.stat} disabled={disabled} onChange={(e) => set("stat", e.target.value)}>{meta.stats.map((x) => <option key={x} value={x}>{tr(STAT, x)}</option>)}</select></Field> : null}
            {["max_resource_modifier", "resource_regeneration", "absorb_effect"].includes(et) ? <Field label="Ресурс"><select value={d.resource} disabled={disabled} onChange={(e) => set("resource", e.target.value)}>{meta.resources.map((x) => <option key={x} value={x}>{tr(RESOURCE, x)}</option>)}</select></Field> : null}
            {et === "control_effect" ? <Field label="Тип контроля"><select value={d.control_kind} disabled={disabled} onChange={(e) => set("control_kind", e.target.value)}>{meta.controlKinds.map((x) => <option key={x} value={x}>{tr(CONTROL_KIND, x)}</option>)}</select></Field> : null}
            {et === "zone_effect" ? <Field label="Стихия зоны"><select value={d.zone_element} disabled={disabled} onChange={(e) => set("zone_element", e.target.value)}>{meta.zoneElements.map((x) => <option key={x} value={x}>{tr(ZONE_ELEMENT, x)}</option>)}</select></Field> : null}
          </div>

          <Field label="Текст для игрока (без формул)"><textarea rows={2} value={d.player_text} disabled={disabled} onChange={(e) => set("player_text", e.target.value)} /></Field>
          <Field label="Описание для админа (можно формулы)"><textarea rows={2} value={d.admin_description} disabled={disabled} onChange={(e) => set("admin_description", e.target.value)} /></Field>

          <div className="ntv2-form-row">
            {num("apply_chance_percent", "Шанс %")}{num("duration_turns", "Длит. (ходы)")}{num("duration_seconds", "Длит. (сек)")}{num("max_stacks", "Макс. стаков")}
          </div>
          <div className="ntv2-form-row">
            {num("flat_bonus", "Плоский бонус")}{num("percent_bonus", "Процентный %")}{num("value_percent", "Значение %")}{num("percent_max_hp_damage", "Урон % max HP")}
          </div>
          <div className="ntv2-form-row">
            {num("reflect_percent", "Отражение %")}{num("absorb_percent_from_damage", "Поглощение %")}
            <Field label="Теги очищения (через запятую)"><input className="ntv2-mono" value={d.cleanse_tags} disabled={disabled} onChange={(e) => set("cleanse_tags", e.target.value)} /></Field>
          </div>
          <div className="ntv2-form-row" style={{ gap: 14 }}>
            {flag("show_to_player", "Показывать игроку")}{flag("can_be_cleansed", "Снимается очищением")}
            {flag("can_trigger_effects", "Запускает эффекты")}{flag("can_be_reflected", "Можно отразить")}
          </div>
        </div>

        {v ? (
          <div className={`ntv2-panel ${v.ok ? "" : "ntv2-danger-zone"}`}>
            <h4 className="ntv2-subhead">{v.ok ? "✅ Готов к публикации" : "❌ Проверка не пройдена"}</h4>
            {(v.errors || []).map((e, i) => <div className="ntv2-error" key={"e" + i}>{e}</div>)}
            {(v.warnings || []).map((w, i) => <p className="ntv2-hint" key={"w" + i}>⚠️ {w}</p>)}
          </div>
        ) : null}

        {!editing.isNew ? (
          <div className="ntv2-panel">
            <h4 className="ntv2-subhead">Где используется</h4>
            {usage === null ? <p className="ntv2-hint">Загрузка…</p>
              : !usage.length ? <p className="ntv2-hint">Нигде не используется (можно безопасно отключить/удалить).</p>
              : <div className="ntv2-list">{usage.map((u, i) => <div className="ntv2-list-row" key={i}><span className="ntv2-badge">{u.kind}</span><b>{u.name}</b><span className="ntv2-mono">{u.id}</span></div>)}</div>}
          </div>
        ) : null}

        <div className="ntv2-form-row" style={{ marginTop: 14 }}>
          {!disabled ? <button type="button" className="ntv2-btn ntv2-btn-primary" disabled={editing.isNew && !editing.id.trim()} onClick={save}>{editing.isNew ? "Создать" : "Сохранить"}</button> : null}
          {!editing.isNew && can.validate ? <button type="button" className="ntv2-btn" onClick={runValidate}>Проверить</button> : null}
          {!editing.isNew && can.publish ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => setConfirm({ title: "Опубликовать эффект?", dangerous: true, confirmLabel: "Опубликовать", body: <p>Эффект будет проверен и опубликован.</p>, run: async (r) => { await guarded(() => effectLifecycle(editing.id, "publish", r), "Опубликовано."); await refreshEditing(); } })}>Опубликовать</button> : null}
          {!editing.isNew && can.disable && editing.status === "published" ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => setConfirm({ title: "Отключить?", dangerous: true, confirmLabel: "Отключить", body: <p>Эффект перестанет применяться.</p>, run: async (r) => { await guarded(() => effectLifecycle(editing.id, "disable", r), "Отключено."); await refreshEditing(); } })}>Отключить</button> : null}
          {!editing.isNew && can.archive ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => setConfirm({ title: "В архив?", dangerous: true, confirmLabel: "В архив", body: <p>Эффект уйдёт в архив.</p>, run: async (r) => { await guarded(() => effectLifecycle(editing.id, "archive", r), "В архиве."); await refreshEditing(); } })}>В архив</button> : null}
          {!editing.isNew && can.del ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => setConfirm({ title: "Удалить эффект?", dangerous: true, confirmLabel: "Удалить", body: <p>Полное удаление определения эффекта.</p>, run: async (r) => { await guarded(() => deleteEffect(editing.id, editing.id, r), "Удалено."); setEditing(null); await load(); } })}>Удалить</button> : null}
        </div>

        {!editing.isNew ? <VersionHistory base="effects" id={editing.id} canRollback={can.edit} onRolledBack={refreshEditing} /> : null}

        <ConfirmModal open={Boolean(confirm)} title={confirm?.title} body={confirm?.body} dangerous={confirm?.dangerous} confirmLabel={confirm?.confirmLabel} requireReason
          onConfirm={async (r) => { await confirm.run(r); setConfirm(null); }} onCancel={() => setConfirm(null)} />
      </section>
    );
  }

  return (
    <section className="ntv2-section">
      <h2>Конструктор эффектов</h2>
      <div className="ntv2-filters">
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="">Все статусы</option>
          {statuses.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
        </select>
        {can.create ? <button type="button" className="ntv2-btn ntv2-btn-primary" onClick={startCreate}>＋ Новый эффект</button> : null}
        {can.publish ? (
          <button type="button" className="ntv2-btn" title="Добавить известные состояния и проклятия в конструктор" onClick={() => setConfirm({
            title: "Импортировать существующие эффекты?",
            body: <p>Известные состояния и проклятия будут добавлены в конструктор как опубликованные записи (повторно — без дублей).</p>,
            confirmLabel: "Импортировать",
            run: async (r) => {
              const res = await guarded(() => importExistingEffects(false, r), "Импорт выполнен.");
              await load();
              if (res) window.alert(`Создано: ${res.created ?? 0}, пропущено: ${res.skipped ?? 0}`);
            },
          })}>Импортировать существующие</button>
        ) : null}
        <SearchBox value={query} onChange={setQuery} />
      </div>
      {!list.length ? <p className="ntv2-hint">Эффектов нет.</p> : null}
      <NoResults items={list} query={query} />
      <div className="ntv2-list">
        {filterEntities(list, query).map((item) => (
          <button key={item.id} type="button" className="ntv2-list-row ntv2-player-row" onClick={() => openItem(item.id)}>
            <b>{item.data?.effect_name || item.id}</b>
            <span className="ntv2-mono">{item.id}</span>
            <span className={`ntv2-badge ${STATUS_TONE[item.status] || ""}`}>{statusLabel(item.status)}</span>
            {item.data?.effect_type ? <span className="ntv2-hint">{item.data.effect_type}</span> : null}
          </button>
        ))}
      </div>
    </section>
  );
}
