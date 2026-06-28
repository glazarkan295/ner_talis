import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  createRecipe,
  deleteRecipe,
  fetchRecipe,
  fetchRecipeMeta,
  fetchRecipes,
  importRecipes,
  recipeLifecycle,
  updateRecipe,
  validateRecipe,
} from "../../../api/adminRecipesApi.js";
import { tr, RECIPE_WORKSHOP } from "../../../i18n/adminLabels.js";
import { fetchFormulas } from "../../../api/adminFormulaApi.js";
import { fetchLibList } from "../../../api/adminLibraryApi.js";
import { ConfirmModal } from "../ConfirmModal.jsx";
import { VersionHistory } from "../VersionHistory.jsx";
import { EmojiInput, EmojiTextarea } from "../EmojiField.jsx";
import { SearchBox, NoResults, filterEntities } from "../SearchFilter.jsx";

const STATUS_TONE = { published: "ntv2-badge-owner", error: "ntv2-badge-error", disabled: "ntv2-badge-danger" };

const EMPTY = {
  name: "", workshop: "forge", section: "", description: "",
  output_item_id: "", output_amount: 1, ingredients: [],
  craft_time: 60, success_chance: 100, quality_chance: 0, fail_chance: 0,
  blueprint_required: false, blueprint_id: "", blueprint_one_time: false,
  hidden: false, unlock_condition: "",
  // Расширение ремесла (ТЗ 13 §5.6–§5.8).
  recipe_type: "create_item", profession: "", workshop_id: "",
  profession_level: 0, player_level: 0, difficulty: "",
  result_formula_id: "", time_formula_id: "", cost_formula_id: "", exp_formula_id: "",
  can_mass_craft: false, can_queue: false, can_cancel: true,
};

function Field({ label, children }) {
  return <label className="ntv2-field"><span>{label}</span>{children}</label>;
}

export function RecipesSection({ guarded, hasPerm }) {
  const [meta, setMeta] = useState(null);
  const [list, setList] = useState([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState(null);
  const [confirm, setConfirm] = useState(null);
  const [formulaOpts, setFormulaOpts] = useState([]);
  const [professionOpts, setProfessionOpts] = useState([]);
  const [workshopOpts, setWorkshopOpts] = useState([]);

  const can = useMemo(() => ({
    create: hasPerm("recipe.create"), edit: hasPerm("recipe.edit"), validate: hasPerm("recipe.validate"),
    publish: hasPerm("recipe.publish"), disable: hasPerm("recipe.disable"),
    archive: hasPerm("recipe.archive"), del: hasPerm("recipe.delete"),
  }), [hasPerm]);

  const load = useCallback(async () => { const p = await guarded(() => fetchRecipes(statusFilter)); if (p) setList(p.items || []); }, [guarded, statusFilter]);
  useEffect(() => { (async () => { const m = await guarded(() => fetchRecipeMeta()); if (m) setMeta(m); })(); }, [guarded]);
  useEffect(() => { (async () => {
    const f = await guarded(() => fetchFormulas("published")); if (f) setFormulaOpts((f.items || []).map((x) => ({ value: x.id, label: x.data?.name || x.id })));
    const p = await guarded(() => fetchLibList("professions", "published")); if (p) setProfessionOpts((p.items || []).map((x) => ({ value: x.id, label: x.data?.name || x.id })));
    const w = await guarded(() => fetchLibList("workshops", "published")); if (w) setWorkshopOpts((w.items || []).map((x) => ({ value: x.id, label: x.data?.name || x.id })));
  })(); }, [guarded]);
  useEffect(() => { load(); }, [load]);

  const statuses = meta?.statuses || [];
  const statusLabel = (v) => statuses.find((s) => s.value === v)?.label || v;

  async function openItem(id) {
    const p = await guarded(() => fetchRecipe(id));
    if (p?.item) setEditing({ id, data: { ...EMPTY, ...(p.item.data || {}) }, status: p.item.status, validation: p.validation, isNew: false });
  }
  function startCreate() { setEditing({ id: "", data: { ...EMPTY }, status: "draft", validation: null, isNew: true }); }

  async function save() {
    const e = editing;
    if (e.isNew) { const p = await guarded(() => createRecipe(e.id.trim(), e.data, ""), "Создано."); if (p?.item) await openItem(e.id.trim()); }
    else { await guarded(() => updateRecipe(e.id, e.data, "правка"), "Сохранено."); await openItem(e.id); }
    await load();
  }
  async function runValidate() { const p = await guarded(() => validateRecipe(editing.id, ""), "Проверка выполнена."); if (p?.validation) setEditing((c) => ({ ...c, validation: p.validation })); }
  async function refreshEditing() { await load(); if (editing) await openItem(editing.id); }

  if (!meta) return <section className="ntv2-section"><h2>Конструктор ремесла</h2><p className="ntv2-hint">Загрузка…</p></section>;

  if (editing) {
    const d = editing.data;
    const set = (k, v) => setEditing({ ...editing, data: { ...d, [k]: v } });
    const disabled = !(editing.isNew ? can.create : can.edit);
    const v = editing.validation;
    const ings = Array.isArray(d.ingredients) ? d.ingredients : [];
    const setIng = (i, patch) => set("ingredients", ings.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));
    const num = (key, label) => <Field label={label} key={key}><input type="number" value={d[key]} disabled={disabled} onChange={(e) => set(key, e.target.value)} /></Field>;
    return (
      <section className="ntv2-section">
        <div className="ntv2-card-head">
          <button type="button" className="ntv2-btn" onClick={() => setEditing(null)}>← К списку</button>
          <h2>{editing.isNew ? "Новый рецепт" : d.name || editing.id}</h2>
          {!editing.isNew ? <span className={`ntv2-badge ${STATUS_TONE[editing.status] || ""}`}>{statusLabel(editing.status)}</span> : null}
        </div>
        {editing.isNew ? <Field label="ID (латиница, напр. forge_iron_sword)"><input value={editing.id} onChange={(e) => setEditing({ ...editing, id: e.target.value })} /></Field> : <p className="ntv2-hint ntv2-mono">{editing.id}</p>}

        <div className="ntv2-world-form">
          <div className="ntv2-form-row">
            <Field label="Название"><EmojiInput value={d.name} disabled={disabled} onChange={(val) => set("name", val)} /></Field>
            <Field label="Мастерская"><select value={d.workshop} disabled={disabled} onChange={(e) => set("workshop", e.target.value)}>{meta.workshops.map((w) => <option key={w} value={w}>{tr(RECIPE_WORKSHOP, w)}</option>)}</select></Field>
            <Field label="Раздел"><input value={d.section} disabled={disabled} onChange={(e) => set("section", e.target.value)} /></Field>
          </div>
          <Field label="Описание"><EmojiTextarea rows={2} value={d.description} disabled={disabled} onChange={(val) => set("description", val)} /></Field>
          <div className="ntv2-form-row">
            <Field label="Результат (item_id)"><input className="ntv2-mono" value={d.output_item_id} disabled={disabled} onChange={(e) => set("output_item_id", e.target.value)} /></Field>
            {num("output_amount", "Кол-во результата")}
          </div>

          <div className="ntv2-panel">
            <h4 className="ntv2-subhead">Ингредиенты ({ings.length})</h4>
            <div className="ntv2-list">
              {ings.map((row, i) => (
                <div className="ntv2-list-row" key={i}>
                  <input className="ntv2-mono" placeholder="item_id" value={row.item_id || ""} disabled={disabled} onChange={(e) => setIng(i, { item_id: e.target.value })} />
                  <input type="number" style={{ width: 80 }} placeholder="кол-во" value={row.amount ?? 1} disabled={disabled} onChange={(e) => setIng(i, { amount: e.target.value })} />
                  <select value={row.role || ""} disabled={disabled} onChange={(e) => setIng(i, { role: e.target.value })}><option value="">роль…</option>{(meta.materialRoles || []).map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}</select>
                  {!disabled ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => set("ingredients", ings.filter((_, idx) => idx !== i))}>×</button> : null}
                </div>
              ))}
            </div>
            {!disabled ? <button type="button" className="ntv2-btn" style={{ marginTop: 6 }} onClick={() => set("ingredients", [...ings, { item_id: "", amount: 1 }])}>＋ Ингредиент</button> : null}
          </div>

          <h4 className="ntv2-subhead">Параметры</h4>
          <div className="ntv2-form-row">{num("craft_time", "Время (сек)")}{num("success_chance", "Шанс успеха %")}{num("quality_chance", "Шанс качества %")}{num("fail_chance", "Шанс провала %")}</div>

          <div className="ntv2-panel">
            <h4 className="ntv2-subhead">Профессия, тип и формулы (ТЗ 13 §5.6–§5.8)</h4>
            <div className="ntv2-form-row">
              <Field label="Тип рецепта"><select value={d.recipe_type || ""} disabled={disabled} onChange={(e) => set("recipe_type", e.target.value)}><option value="">—</option>{(meta.recipeTypes || []).map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}</select></Field>
              <Field label="Профессия"><select value={d.profession || ""} disabled={disabled} onChange={(e) => set("profession", e.target.value)}><option value="">—</option>{professionOpts.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</select></Field>
              <Field label="Мастерская (объект)"><select value={d.workshop_id || ""} disabled={disabled} onChange={(e) => set("workshop_id", e.target.value)}><option value="">—</option>{workshopOpts.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</select></Field>
            </div>
            <div className="ntv2-form-row">{num("profession_level", "Уровень профессии")}{num("player_level", "Уровень игрока")}<Field label="Сложность"><input value={d.difficulty} disabled={disabled} onChange={(e) => set("difficulty", e.target.value)} /></Field></div>
            <div className="ntv2-form-row">
              {[["result_formula_id", "Формула результата"], ["time_formula_id", "Формула времени"], ["cost_formula_id", "Формула стоимости"], ["exp_formula_id", "Формула опыта"]].map(([key, label]) => (
                <Field key={key} label={label}><select value={d[key] || ""} disabled={disabled} onChange={(e) => set(key, e.target.value)}><option value="">— без формулы —</option>{formulaOpts.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</select></Field>
              ))}
            </div>
            <div className="ntv2-form-row" style={{ gap: 14 }}>
              <label className="ntv2-check"><input type="checkbox" checked={Boolean(d.can_mass_craft)} disabled={disabled} onChange={(e) => set("can_mass_craft", e.target.checked)} /> Массовое создание</label>
              <label className="ntv2-check"><input type="checkbox" checked={Boolean(d.can_queue)} disabled={disabled} onChange={(e) => set("can_queue", e.target.checked)} /> В очередь</label>
              <label className="ntv2-check"><input type="checkbox" checked={Boolean(d.can_cancel)} disabled={disabled} onChange={(e) => set("can_cancel", e.target.checked)} /> Можно отменить</label>
            </div>
          </div>

          <div className="ntv2-panel">
            <h4 className="ntv2-subhead">Чертёж и доступ</h4>
            <div className="ntv2-form-row" style={{ gap: 14, alignItems: "center" }}>
              <label className="ntv2-check"><input type="checkbox" checked={Boolean(d.blueprint_required)} disabled={disabled} onChange={(e) => set("blueprint_required", e.target.checked)} /> Нужен чертёж</label>
              <Field label="Чертёж (item_id)"><input className="ntv2-mono" value={d.blueprint_id} disabled={disabled} onChange={(e) => set("blueprint_id", e.target.value)} /></Field>
              <label className="ntv2-check"><input type="checkbox" checked={Boolean(d.blueprint_one_time)} disabled={disabled} onChange={(e) => set("blueprint_one_time", e.target.checked)} /> Одноразовый чертёж</label>
            </div>
            <div className="ntv2-form-row" style={{ gap: 14, alignItems: "center" }}>
              <label className="ntv2-check"><input type="checkbox" checked={Boolean(d.hidden)} disabled={disabled} onChange={(e) => set("hidden", e.target.checked)} /> Скрытый рецепт</label>
              <Field label="Условие открытия"><input value={d.unlock_condition} disabled={disabled} onChange={(e) => set("unlock_condition", e.target.value)} /></Field>
            </div>
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
          {!editing.isNew && can.publish ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => setConfirm({ title: "Опубликовать рецепт?", dangerous: true, confirmLabel: "Опубликовать", body: <p>Рецепт будет проверен и опубликован.</p>, run: async (r) => { await guarded(() => recipeLifecycle(editing.id, "publish", r), "Опубликовано."); await refreshEditing(); } })}>Опубликовать</button> : null}
          {!editing.isNew && can.disable && editing.status === "published" ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => setConfirm({ title: "Отключить?", dangerous: true, confirmLabel: "Отключить", body: <p>Рецепт перестанет быть доступен.</p>, run: async (r) => { await guarded(() => recipeLifecycle(editing.id, "disable", r), "Отключено."); await refreshEditing(); } })}>Отключить</button> : null}
          {!editing.isNew && can.archive ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => setConfirm({ title: "В архив?", dangerous: true, confirmLabel: "В архив", body: <p>Рецепт уйдёт в архив.</p>, run: async (r) => { await guarded(() => recipeLifecycle(editing.id, "archive", r), "В архиве."); await refreshEditing(); } })}>В архив</button> : null}
          {!editing.isNew && can.del ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => setConfirm({ title: "Удалить рецепт?", dangerous: true, confirmLabel: "Удалить", body: <p>Полное удаление рецепта.</p>, run: async (r) => { await guarded(() => deleteRecipe(editing.id, editing.id, r), "Удалено."); setEditing(null); await load(); } })}>Удалить</button> : null}
        </div>

        {!editing.isNew ? <VersionHistory base="recipes" id={editing.id} canRollback={can.edit} onRolledBack={refreshEditing} /> : null}

        <ConfirmModal open={Boolean(confirm)} title={confirm?.title} body={confirm?.body} dangerous={confirm?.dangerous} confirmLabel={confirm?.confirmLabel} requireReason
          onConfirm={async (r) => { await confirm.run(r); setConfirm(null); }} onCancel={() => setConfirm(null)} />
      </section>
    );
  }

  return (
    <section className="ntv2-section">
      <h2>Конструктор ремесла</h2>
      <div className="ntv2-filters">
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="">Все статусы</option>
          {statuses.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
        </select>
        {can.create ? <button type="button" className="ntv2-btn ntv2-btn-primary" onClick={startCreate}>＋ Новый рецепт</button> : null}
        {can.publish ? <button type="button" className="ntv2-btn" onClick={() => setConfirm({ title: "Импортировать существующие рецепты?", dangerous: true, confirmLabel: "Импортировать", body: <p>Рецепты из crafting_recipes.json будут заведены как опубликованные записи (без дублей).</p>, run: async (r) => { const p = await guarded(() => importRecipes("new", r), "Импорт выполнен."); if (p?.report) { const rep = p.report; await load(); window.alert(`Импорт рецептов: создано ${rep.created}, пропущено ${rep.skipped}, ошибок ${rep.invalid}.`); } } })}>Импортировать существующие</button> : null}
        <SearchBox value={query} onChange={setQuery} />
      </div>
      {!list.length ? <p className="ntv2-hint">Рецептов пока нет. Можно создать новый или импортировать существующие.</p> : null}
      <NoResults items={list} query={query} />
      <div className="ntv2-list">
        {filterEntities(list, query).map((item) => (
          <button key={item.id} type="button" className="ntv2-list-row ntv2-player-row" onClick={() => openItem(item.id)}>
            <b>{item.data?.name || item.id}</b>
            <span className="ntv2-mono">{item.id}</span>
            <span className={`ntv2-badge ${STATUS_TONE[item.status] || ""}`}>{statusLabel(item.status)}</span>
            {item.data?.workshop ? <span className="ntv2-hint">{tr(RECIPE_WORKSHOP, item.data.workshop)}</span> : null}
          </button>
        ))}
      </div>
    </section>
  );
}
