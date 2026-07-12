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
import { VersionHistory } from "../VersionHistory.jsx";
import { EmojiInput, EmojiTextarea } from "../EmojiField.jsx";
import { SearchBox, NoResults, filterEntities } from "../SearchFilter.jsx";
import { fetchFormulas } from "../../../api/adminFormulaApi.js";
import { fetchEffects } from "../../../api/adminEffectApi.js";
import { fetchItems } from "../../../api/adminItemApi.js";
import { fetchWorldItems } from "../../../api/adminWorldApi.js";
import { fetchAchievements } from "../../../api/adminAchievementApi.js";

const STATUS_TONE = { published: "ntv2-badge-owner", error: "ntv2-badge-error", disabled: "ntv2-badge-danger" };

const EMPTY = {
  name: "", skill_type: "active", branch: "neutral", path: "none",
  resource_type: "none", resource_cost: 0, cooldown_turns: 0,
  damage_type: "physical", target_mode: "single_enemy",
  weapon_requirements: ["any"], unlock_path_level: 0, choice_index: 0,
  short_description: "", description: "", base_damage_formula: "",
  damage_formula_id: "", use_cost_formula_id: "", learn_cost_formula_id: "",
  upgrade_cost_formula_id: "", level_power_formula_id: "",
  learn_cost_skill_points: 0,
  modifiers: [],
  source_type: "standard", linked_item_id: "", linked_mob_id: "", linked_achievement_id: "", linked_button_id: "",
  special: false, hidden: false, unlock_condition: "", action_type: "damage", works_in_battle: true, works_outside_battle: false,
  hp_amount: 0, mana_amount: 0, spirit_amount: 0, energy_amount: 0,
  hp_formula_id: "", mana_formula_id: "", spirit_formula_id: "", energy_formula_id: "",
  apply_effect_ids: [], remove_effect_ids: [], required_magic_book_id: "", required_hand: "",
  required_player_state: "", forbidden_player_state: "", passive_slot_cost: 1,
  ammo_enabled: false, ammo_item_id: "", ammo_per_use: 1,
};

function Field({ label, children }) {
  return <label className="ntv2-field"><span>{label}</span>{children}</label>;
}

export function SkillsSection({ guarded, hasPerm }) {
  const [meta, setMeta] = useState(null);
  const [list, setList] = useState([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState(null);
  const [confirm, setConfirm] = useState(null);
  const [formulaOptions, setFormulaOptions] = useState([]);
  const [effectOptions, setEffectOptions] = useState([]);
  const [itemOptions, setItemOptions] = useState([]);
  const [mobOptions, setMobOptions] = useState([]);
  const [buttonOptions, setButtonOptions] = useState([]);
  const [achievementOptions, setAchievementOptions] = useState([]);

  const can = useMemo(() => ({
    create: hasPerm("skill_def.create"), edit: hasPerm("skill_def.edit"), validate: hasPerm("skill_def.validate"),
    publish: hasPerm("skill_def.publish"), disable: hasPerm("skill_def.disable"),
    archive: hasPerm("skill_def.archive"), del: hasPerm("skill_def.delete"),
  }), [hasPerm]);

  const load = useCallback(async () => { const p = await guarded(() => fetchSkills(statusFilter)); if (p) setList(p.items || []); }, [guarded, statusFilter]);
  useEffect(() => { (async () => { const m = await guarded(() => fetchSkillMeta()); if (m) setMeta(m); })(); }, [guarded]);
  useEffect(() => { (async () => { const f = await guarded(() => fetchFormulas("published")); if (f) setFormulaOptions((f.items || []).map((x) => ({ value: x.id, label: x.data?.name || x.id }))); })(); }, [guarded]);
  useEffect(() => { (async () => {
    const e = await guarded(() => fetchEffects("published")); if (e) setEffectOptions((e.items || []).map((x) => ({ value: x.id, label: x.data?.effect_name || x.id })));
    const i = await guarded(() => fetchItems("published")); if (i) setItemOptions((i.items || []).map((x) => ({ value: x.id, label: x.data?.name || x.id })));
    const m = await guarded(() => fetchWorldItems("mob", "published")); if (m) setMobOptions((m.items || []).map((x) => ({ value: x.id, label: x.data?.name || x.id })));
    const b = await guarded(() => fetchWorldItems("button", "published")); if (b) setButtonOptions((b.items || []).map((x) => ({ value: x.id, label: x.data?.text || x.data?.name || x.id })));
    const a = await guarded(() => fetchAchievements("published")); if (a) setAchievementOptions((a.items || []).map((x) => ({ value: x.id, label: x.data?.name || x.id })));
  })(); }, [guarded]);
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
            <Field label="Название"><EmojiInput value={d.name} disabled={disabled} onChange={(v) => set("name", v)} /></Field>
            {sel("skill_type", "Тип навыка", SKILL_TYPE, meta.skillTypes)}
          </div>

          <div className="ntv2-panel"><h4 className="ntv2-subhead">Источник и связи</h4>
            <div className="ntv2-form-row"><Field label="Источник"><select value={d.source_type || "standard"} disabled={disabled} onChange={(e) => set("source_type", e.target.value)}><option value="standard">Обычный</option><option value="item">Предметный</option><option value="mob">Навык моба</option><option value="achievement">За достижение</option><option value="special">Особый</option></select></Field>
              {d.source_type === "item" ? <Field label="Предмет"><select value={d.linked_item_id || ""} disabled={disabled} onChange={(e) => set("linked_item_id", e.target.value)}><option value="">—</option>{itemOptions.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</select></Field> : null}
              {d.source_type === "mob" ? <Field label="Моб"><select value={d.linked_mob_id || ""} disabled={disabled} onChange={(e) => set("linked_mob_id", e.target.value)}><option value="">—</option>{mobOptions.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</select></Field> : null}
              {d.source_type === "achievement" ? <Field label="Достижение"><select value={d.linked_achievement_id || ""} disabled={disabled} onChange={(e) => set("linked_achievement_id", e.target.value)}><option value="">—</option>{achievementOptions.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</select></Field> : null}
              <Field label="Кнопка"><select value={d.linked_button_id || ""} disabled={disabled} onChange={(e) => set("linked_button_id", e.target.value)}><option value="">—</option>{buttonOptions.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</select></Field>
            </div>
            <div className="ntv2-form-row"><label className="ntv2-check"><input type="checkbox" checked={Boolean(d.special)} disabled={disabled} onChange={(e) => set("special", e.target.checked)} /> Особый</label><label className="ntv2-check"><input type="checkbox" checked={Boolean(d.hidden)} disabled={disabled} onChange={(e) => set("hidden", e.target.checked)} /> Скрытый</label><Field label="Условие открытия"><input value={d.unlock_condition || ""} disabled={disabled} onChange={(e) => set("unlock_condition", e.target.value)} /></Field></div>
          </div>
          <div className="ntv2-form-row">
            {sel("branch", "Ветвь", SKILL_BRANCH, meta.branches)}
            <Field label="Путь">
              <select value={d.path} disabled={disabled} onChange={(e) => set("path", e.target.value)}>
                {pathsForBranch(d.branch).map((x) => <option key={x} value={x}>{tr(SKILL_PATH, x)}</option>)}
              </select>
            </Field>
          </div>
          <div className="ntv2-form-row"><Field label="Действие"><select value={d.action_type || "damage"} disabled={disabled} onChange={(e) => set("action_type", e.target.value)}><option value="damage">Урон</option><option value="heal">Лечение HP</option><option value="restore_mana">Восстановить ману</option><option value="restore_spirit">Восстановить дух</option><option value="restore_energy">Восстановить энергию</option><option value="apply_effect">Наложить эффект</option><option value="remove_effect">Снять эффект</option></select></Field><label className="ntv2-check"><input type="checkbox" checked={d.works_in_battle !== false} disabled={disabled} onChange={(e) => set("works_in_battle", e.target.checked)} /> В бою</label><label className="ntv2-check"><input type="checkbox" checked={Boolean(d.works_outside_battle)} disabled={disabled} onChange={(e) => set("works_outside_battle", e.target.checked)} /> Вне боя</label></div>
          <div className="ntv2-form-row">{num("hp_amount", "Лечение HP")}{num("mana_amount", "Восстановление маны")}{num("spirit_amount", "Восстановление духа")}{num("energy_amount", "Восстановление энергии")}</div>
          <div className="ntv2-form-row"><Field label="Накладываемые эффекты"><select multiple value={d.apply_effect_ids || []} disabled={disabled} onChange={(e) => set("apply_effect_ids", [...e.target.selectedOptions].map((o) => o.value))}>{effectOptions.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</select></Field><Field label="Снимаемые эффекты"><select multiple value={d.remove_effect_ids || []} disabled={disabled} onChange={(e) => set("remove_effect_ids", [...e.target.selectedOptions].map((o) => o.value))}>{effectOptions.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</select></Field></div>

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
          <div className="ntv2-panel"><h4 className="ntv2-subhead">Опубликованные формулы</h4><div className="ntv2-form-row">
            {num("learn_cost_skill_points", "Базовая цена изучения, очки")}
            {[["damage_formula_id","Урон"],["hp_formula_id","Лечение HP"],["mana_formula_id","Мана"],["spirit_formula_id","Дух"],["energy_formula_id","Энергия"],["use_cost_formula_id","Стоимость применения"],["learn_cost_formula_id","Стоимость изучения"],["upgrade_cost_formula_id","Стоимость повышения"],["level_power_formula_id","Усиление по уровню"]].map(([key,label]) => <Field key={key} label={label}><select value={d[key] || ''} disabled={disabled} onChange={(e) => set(key,e.target.value)}><option value="">— без формулы —</option>{formulaOptions.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</select></Field>)}
          </div></div>

          <div className="ntv2-panel">
            <h4 className="ntv2-subhead">Требования к оружию</h4>
            <div className="ntv2-form-row" style={{ gap: 10 }}>
              {(meta.weaponRequirements || []).map((code) => (
                <label className="ntv2-check" key={code}><input type="checkbox" checked={(d.weapon_requirements || []).includes(code)} disabled={disabled} onChange={() => toggleWeapon(code)} /> {tr(SKILL_WEAPON_REQUIREMENT, code)}</label>
              ))}
            </div>
          </div>
          <div className="ntv2-panel"><h4 className="ntv2-subhead">Книга, боеприпасы, состояние и руки</h4><div className="ntv2-form-row"><Field label="Магическая книга"><select value={d.required_magic_book_id || ""} disabled={disabled} onChange={(e) => set("required_magic_book_id", e.target.value)}><option value="">— не требуется —</option>{itemOptions.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</select></Field><Field label="Требуемая рука"><select value={d.required_hand || ""} disabled={disabled} onChange={(e) => set("required_hand", e.target.value)}><option value="">—</option><option value="left">Левая</option><option value="right">Правая</option><option value="both">Обе</option></select></Field><Field label="Требуемое состояние"><input value={d.required_player_state || ""} disabled={disabled} onChange={(e) => set("required_player_state", e.target.value)} /></Field><Field label="Запрещающее состояние"><input value={d.forbidden_player_state || ""} disabled={disabled} onChange={(e) => set("forbidden_player_state", e.target.value)} /></Field>{isPassive ? num("passive_slot_cost", "Пассивных слотов") : null}</div><div className="ntv2-form-row"><label className="ntv2-check"><input type="checkbox" checked={Boolean(d.ammo_enabled)} disabled={disabled} onChange={(e) => set("ammo_enabled", e.target.checked)} /> Требует боеприпасы</label>{d.ammo_enabled ? <><Field label="Боеприпас"><select value={d.ammo_item_id || ""} disabled={disabled} onChange={(e) => set("ammo_item_id", e.target.value)}><option value="">—</option>{itemOptions.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</select></Field>{num("ammo_per_use", "За применение")}</> : null}</div></div>

          <h4 className="ntv2-subhead">Открытие пути</h4>
          <div className="ntv2-form-row">{num("unlock_path_level", "Порог открытия (уровень пути)")}{num("choice_index", "Индекс выбора")}</div>

          <Field label="Краткое описание"><EmojiInput value={d.short_description} disabled={disabled} onChange={(v) => set("short_description", v)} /></Field>
          <Field label="Описание эффекта"><EmojiTextarea rows={2} value={d.description} disabled={disabled} onChange={(v) => set("description", v)} /></Field>

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

        {!editing.isNew ? <VersionHistory base="skills" id={editing.id} canRollback={can.edit && (editing.status !== "published" || can.publish)} onRolledBack={refreshEditing} /> : null}

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
      <div className="ntv2-filters"><SearchBox value={query} onChange={setQuery} /></div>
      {!list.length ? <p className="ntv2-hint">Навыков пока нет. Можно создать новый или импортировать существующие из каталога.</p> : null}
      <NoResults items={list} query={query} />
      <div className="ntv2-list">
        {filterEntities(list, query).map((item) => (
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
