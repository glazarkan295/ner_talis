import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  createSkill,
  deleteSkill,
  fetchSkill,
  fetchSkillMeta,
  fetchSkills,
  importSkills,
  skillLifecycle,
  updateSkill,
  validateSkill,
} from "../../../api/adminSkillsApi.js";
import {
  tr,
  SKILL_TYPE,
  SKILL_BRANCH,
  SKILL_PATH,
  SKILL_RESOURCE_TYPE,
  SKILL_DAMAGE_TYPE,
  SKILL_TARGET_MODE,
  SKILL_WEAPON_REQUIREMENT,
} from "../../../i18n/adminLabels.js";
import { ConfirmModal } from "../ConfirmModal.jsx";

const STATUS_TONE = { published: "ntv2-badge-owner", error: "ntv2-badge-error", disabled: "ntv2-badge-danger" };

const EMPTY = {
  name: "", skill_type: "active", branch: "neutral", path: "none",
  resource_type: "none", resource_cost: 0, cooldown_turns: 0,
  damage_type: "physical", target_mode: "single_enemy",
  weapon_requirements: ["any"], unlock_path_level: 0, choice_index: 0,
  short_description: "", description: "", base_damage_formula: "",
  modifiers: [],
};

function Field({ label, children }) {
  return <label className="ntv2-field"><span>{label}</span>{children}</label>;
}

export function SkillsSection({ guarded, hasPerm }) {
  const [meta, setMeta] = useState(null);
  const [list, setList] = useState([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [editing, setEditing] = useState(null);
  const [confirm, setConfirm] = useState(null);

  const can = useMemo(() => ({
    create: hasPerm("skill_def.create"), edit: hasPerm("skill_def.edit"), validate: hasPerm("skill_def.validate"),
    publish: hasPerm("skill_def.publish"), disable: hasPerm("skill_def.disable"),
    archive: hasPerm("skill_def.archive"), del: hasPerm("skill_def.delete"),
  }), [hasPerm]);

  const load = useCallback(async () => { const p = await guarded(() => fetchSkills(statusFilter)); if (p) setList(p.items || []); }, [guarded, statusFilter]);
  useEffect(() => { (async () => { const m = await guarded(() => fetchSkillMeta()); if (m) setMeta(m); })(); }, [guarded]);
  useEffect(() => { load(); }, [load]);

  const statuses = meta?.statuses || [];
  const statusLabel = (v) => statuses.find((s) => s.value === v)?.label || v;
  const pathsForBranch = (branch) => (meta?.pathsByBranch?.[branch] || meta?.paths || []);

  async function openItem(id) {
    const p = await guarded(() => fetchSkill(id));
    if (p?.item) setEditing({ id, data: { ...EMPTY, ...(p.item.data || {}) }, status: p.item.status, validation: p.validation, isNew: false });
  }
  function startCreate() { setEditing({ id: "", data: { ...EMPTY }, status: "draft", validation: null, isNew: true }); }

  async function save() {
    const e = editing;
    if (e.isNew) { const p = await guarded(() => createSkill(e.id.trim(), e.data, ""), "Создано."); if (p?.item) await openItem(e.id.trim()); }
    else { await guarded(() => updateSkill(e.id, e.data, "правка"), "Сохранено."); await openItem(e.id); }
    await load();
  }
  async function runValidate() { const p = await guarded(() => validateSkill(editing.id, ""), "Проверка выполнена."); if (p?.validation) setEditing((c) => ({ ...c, validation: p.validation })); }
  async function refreshEditing() { await load(); if (editing) await openItem(editing.id); }

  if (!meta) return <section className="ntv2-section"><h2>Конструктор навыков</h2><p className="ntv2-hint">Загрузка…</p></section>;

  if (editing) {
    const d = editing.data;
    const set = (k, v) => setEditing({ ...editing, data: { ...d, [k]: v } });
    const disabled = !(editing.isNew ? can.create : can.edit);
    const v = editing.validation;
    const isPassive = d.skill_type === "passive";
    const num = (key, label) => <Field label={label} key={key}><input type="number" value={d[key]} disabled={disabled} onChange={(e) => set(key, e.target.value)} /></Field>;
    const sel = (key, label, map, options) => (
      <Field label={label} key={key}>
        <select value={d[key]} disabled={disabled} onChange={(e) => set(key, e.target.value)}>
          {options.map((x) => <option key={x} value={x}>{tr(map, x)}</option>)}
        </select>
      </Field>
    );
    const toggleWeapon = (code) => {
      const cur = Array.isArray(d.weapon_requirements) ? d.weapon_requirements : [];
      set("weapon_requirements", cur.includes(code) ? cur.filter((x) => x !== code) : [...cur, code]);
    };
    const setMod = (i, k, val) => set("modifiers", (d.modifiers || []).map((m, idx) => (idx === i ? { ...m, [k]: val } : m)));
    const addMod = () => set("modifiers", [...(d.modifiers || []), { name: "", effect: "" }]);
    const delMod = (i) => set("modifiers", (d.modifiers || []).filter((_, idx) => idx !== i));

    return (
      <section className="ntv2-section">
        <div className="ntv2-card-head">
          <button type="button" className="ntv2-btn" onClick={() => setEditing(null)}>← К списку</button>
          <h2>{editing.isNew ? "Новый навык" : d.name || editing.id}</h2>
          {!editing.isNew ? <span className={`ntv2-badge ${STATUS_TONE[editing.status] || ""}`}>{statusLabel(editing.status)}</span> : null}
        </div>
        {editing.isNew ? <Field label="ID (латиница, напр. fire_bolt)"><input value={editing.id} onChange={(e) => setEditing({ ...editing, id: e.target.value })} /></Field> : <p className="ntv2-hint ntv2-mono">{editing.id}</p>}

        <div className="ntv2-world-form">
          <div className="ntv2-form-row">
            <Field label="Название"><input value={d.name} disabled={disabled} onChange={(e) => set("name", e.target.value)} /></Field>
            {sel("skill_type", "Тип навыка", SKILL_TYPE, meta.skillTypes)}
          </div>
          <div className="ntv2-form-row">
            {sel("branch", "Ветвь", SKILL_BRANCH, meta.branches)}
            <Field label="Путь">
              <select value={d.path} disabled={disabled} onChange={(e) => set("path", e.target.value)}>
                {pathsForBranch(d.branch).map((x) => <option key={x} value={x}>{tr(SKILL_PATH, x)}</option>)}
              </select>
            </Field>
          </div>

          <h4 className="ntv2-subhead">Боевые параметры</h4>
          <div className="ntv2-form-row">
            {sel("resource_type", "Ресурс", SKILL_RESOURCE_TYPE, meta.resourceTypes)}
            {num("resource_cost", "Стоимость ресурса")}
            {num("cooldown_turns", "Откат (ходов)")}
          </div>
          <div className="ntv2-form-row">
            {sel("damage_type", "Тип урона", SKILL_DAMAGE_TYPE, meta.damageTypes)}
            {sel("target_mode", "Цель", SKILL_TARGET_MODE, meta.targetModes)}
          </div>
          <Field label="Формула базового урона (текст)"><input value={d.base_damage_formula} disabled={disabled} onChange={(e) => set("base_damage_formula", e.target.value)} /></Field>

          <div className="ntv2-panel">
            <h4 className="ntv2-subhead">Требования к оружию</h4>
            <div className="ntv2-form-row" style={{ gap: 10 }}>
              {(meta.weaponRequirements || []).map((code) => (
                <label className="ntv2-check" key={code}><input type="checkbox" checked={(d.weapon_requirements || []).includes(code)} disabled={disabled} onChange={() => toggleWeapon(code)} /> {tr(SKILL_WEAPON_REQUIREMENT, code)}</label>
              ))}
            </div>
          </div>

          <h4 className="ntv2-subhead">Открытие пути</h4>
          <div className="ntv2-form-row">{num("unlock_path_level", "Порог открытия (уровень пути)")}{num("choice_index", "Индекс выбора")}</div>

          <Field label="Краткое описание"><input value={d.short_description} disabled={disabled} onChange={(e) => set("short_description", e.target.value)} /></Field>
          <Field label="Описание эффекта"><textarea rows={2} value={d.description} disabled={disabled} onChange={(e) => set("description", e.target.value)} /></Field>

          <div className="ntv2-panel">
            <h4 className="ntv2-subhead">Модификаторы навыка</h4>
            {(d.modifiers || []).map((m, i) => (
              <div className="ntv2-form-row" key={i} style={{ gap: 8, alignItems: "center" }}>
                <Field label="Название"><input value={m.name || ""} disabled={disabled} onChange={(e) => setMod(i, "name", e.target.value)} /></Field>
                <Field label="Эффект"><input value={m.effect || ""} disabled={disabled} onChange={(e) => setMod(i, "effect", e.target.value)} /></Field>
                {!disabled ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => delMod(i)}>✕</button> : null}
              </div>
            ))}
            {!disabled ? <button type="button" className="ntv2-btn" onClick={addMod}>＋ Модификатор</button> : null}
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
          {!editing.isNew && can.publish ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => setConfirm({ title: "Опубликовать навык?", dangerous: true, confirmLabel: "Опубликовать", body: <p>Навык будет проверен и опубликован.</p>, run: async (r) => { await guarded(() => skillLifecycle(editing.id, "publish", r), "Опубликовано."); await refreshEditing(); } })}>Опубликовать</button> : null}
          {!editing.isNew && can.disable && editing.status === "published" ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => setConfirm({ title: "Отключить?", dangerous: true, confirmLabel: "Отключить", body: <p>Навык перестанет действовать.</p>, run: async (r) => { await guarded(() => skillLifecycle(editing.id, "disable", r), "Отключено."); await refreshEditing(); } })}>Отключить</button> : null}
          {!editing.isNew && can.archive ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => setConfirm({ title: "В архив?", dangerous: true, confirmLabel: "В архив", body: <p>Навык уйдёт в архив.</p>, run: async (r) => { await guarded(() => skillLifecycle(editing.id, "archive", r), "В архиве."); await refreshEditing(); } })}>В архив</button> : null}
          {!editing.isNew && can.del ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => setConfirm({ title: "Удалить навык?", dangerous: true, confirmLabel: "Удалить", body: <p>Полное удаление определения навыка.</p>, run: async (r) => { await guarded(() => deleteSkill(editing.id, editing.id, r), "Удалено."); setEditing(null); await load(); } })}>Удалить</button> : null}
        </div>

        <ConfirmModal open={Boolean(confirm)} title={confirm?.title} body={confirm?.body} dangerous={confirm?.dangerous} confirmLabel={confirm?.confirmLabel} requireReason
          onConfirm={async (r) => { await confirm.run(r); setConfirm(null); }} onCancel={() => setConfirm(null)} />
      </section>
    );
  }

  return (
    <section className="ntv2-section">
      <h2>Конструктор навыков</h2>
      <div className="ntv2-filters">
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="">Все статусы</option>
          {statuses.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
        </select>
        {can.create ? <button type="button" className="ntv2-btn ntv2-btn-primary" onClick={startCreate}>＋ Новый навык</button> : null}
        {can.publish ? <button type="button" className="ntv2-btn" onClick={() => setConfirm({ title: "Импортировать существующие навыки?", dangerous: true, confirmLabel: "Импортировать", body: <p>Навыки из каталога путей будут заведены как опубликованные записи конструктора (без дублей).</p>, run: async (r) => { const p = await guarded(() => importSkills(false, r), "Импорт выполнен."); if (p?.report) { const rep = p.report; await load(); window.alert(`Импорт навыков: создано ${rep.created}, пропущено ${rep.skipped}, ошибок ${rep.invalid}.`); } } })}>Импортировать существующие</button> : null}
      </div>
      {!list.length ? <p className="ntv2-hint">Навыков пока нет. Можно создать новый или импортировать существующие из каталога.</p> : null}
      <div className="ntv2-list">
        {list.map((item) => (
          <button key={item.id} type="button" className="ntv2-list-row ntv2-player-row" onClick={() => openItem(item.id)}>
            <b>{item.data?.name || item.id}</b>
            <span className="ntv2-mono">{item.id}</span>
            <span className={`ntv2-badge ${STATUS_TONE[item.status] || ""}`}>{statusLabel(item.status)}</span>
            {item.data?.skill_type ? <span className="ntv2-hint">{tr(SKILL_TYPE, item.data.skill_type)}</span> : null}
            {item.data?.path && item.data.path !== "none" ? <span className="ntv2-hint">{tr(SKILL_PATH, item.data.path)}</span> : null}
          </button>
        ))}
      </div>
    </section>
  );
}
