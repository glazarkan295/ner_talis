import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  createRecipe,
  deleteRecipe,
  fetchRecipe,
  fetchRecipeMeta,
  fetchRecipeUsage,
  fetchRecipes,
  importRecipes,
  recipeLifecycle,
  updateRecipe,
  validateRecipe,
} from "../../../api/adminRecipesApi.js";
import { tr, RECIPE_WORKSHOP } from "../../../i18n/adminLabels.js";
import { fetchFormulas } from "../../../api/adminFormulaApi.js";
import { fetchLibList } from "../../../api/adminLibraryApi.js";
import { fetchItems } from "../../../api/adminItemApi.js";
import { fetchEffects } from "../../../api/adminEffectApi.js";
import { fetchWorldItems } from "../../../api/adminWorldApi.js";
import { ConfirmModal } from "../ConfirmModal.jsx";
import { VersionHistory } from "../VersionHistory.jsx";
import { EmojiInput, EmojiTextarea } from "../EmojiField.jsx";
import { SearchBox, NoResults, filterEntities } from "../SearchFilter.jsx";

const STATUS_TONE = { published: "ntv2-badge-owner", error: "ntv2-badge-error", disabled: "ntv2-badge-danger" };

const EMPTY = {
  name: "", workshop: "forge", section: "", description: "",
  output_item_id: "", output_amount: 1, output_amount_min: "", output_amount_max: "", ingredients: [],
  craft_time: 60, success_chance: 100, quality_chance: 0, fail_chance: 0,
  blueprint_required: false, blueprint_id: "", blueprint_one_time: false,
  hidden: false, unlock_condition: "",
  // Расширение ремесла (ТЗ 13 §5.6–§5.8).
  recipe_type: "create_item", profession: "", workshop_id: "",
  profession_level: 0, player_level: 0, difficulty: "",
  result_formula_id: "", time_formula_id: "", cost_formula_id: "", exp_formula_id: "",
  free: true, price_copper: 0, price_silver: 0, price_gold: 0, price_magic_gold: 0, price_ancient: 0,
  can_mass_craft: false, can_queue: false, can_cancel: true,
  tools: [], results: [], byproducts: [], effect_ids: [], energy_cost: 0, min_energy: 0, energy_charge_at: "start",
  weekly_limits: [],
  critical_chance: 0, partial_success_chance: 0, success_formula_id: "", critical_formula_id: "", energy_formula_id: "", quality_formula_id: "",
  text_not_enough_ingredients: "", text_not_enough_tool: "", text_not_enough_money: "", text_not_enough_energy: "",
  text_start: "", text_success: "", text_critical_success: "", text_fail: "", text_cancel: "",
  text_partial_success: "", partial_result_percent: 50,
  result_delivery: "overload", text_inventory_full: "", text_delivery: "",
  result_quality: "", result_level: "", bind_on_create: false, unique_result: false, crafted_handedness: "keep", critical_quality_upgrade: false, result_effects: [],
  failure_material_policy: "lose_all", failure_return_percent: 0, failure_effect_id: "", failure_curse_id: "",
  failure_event_id: "", failure_battle_mob_id: "",
  text_workshop_open: "", text_recipe_list: "", text_recipe_card: "", text_not_enough_level: "", text_unavailable: "",
  text_item_break: "", text_material_loss: "", text_result_received: "", text_disassemble: "", text_repair: "",
  text_upgrade: "", text_enchant: "", text_purify: "",
};

function Field({ label, children }) {
  return <label className="ntv2-field"><span>{label}</span>{children}</label>;
}

export function RecipesSection({ guarded, hasPerm }) {
  const [meta, setMeta] = useState(null);
  const [list, setList] = useState([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [query, setQuery] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [editing, setEditing] = useState(null);
  const [confirm, setConfirm] = useState(null);
  const [formulaOpts, setFormulaOpts] = useState([]);
  const [professionOpts, setProfessionOpts] = useState([]);
  const [workshopOpts, setWorkshopOpts] = useState([]);
  const [itemOpts, setItemOpts] = useState([]);
  const [effectOpts, setEffectOpts] = useState([]);
  const [materialGroupOpts, setMaterialGroupOpts] = useState([]);
  const [eventOpts, setEventOpts] = useState([]);
  const [mobOpts, setMobOpts] = useState([]);
  const [usage, setUsage] = useState(null);

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
    const i = await guarded(() => fetchItems("published")); if (i) setItemOpts((i.items || []).map((x) => ({ value: x.id, label: x.data?.name || x.id })));
    const e = await guarded(() => fetchEffects("published")); if (e) setEffectOpts((e.items || []).map((x) => ({ value: x.id, label: x.data?.effect_name || x.id })));
    const g = await guarded(() => fetchLibList("craft-material-groups", "published")); if (g) setMaterialGroupOpts((g.items || []).map((x) => ({ value: x.id, label: x.data?.name || x.id })));
    const events = await guarded(() => fetchWorldItems("event", "published")); if (events) setEventOpts((events.items || []).map((x) => ({ value: x.id, label: x.data?.name || x.id })));
    const mobs = await guarded(() => fetchWorldItems("mob", "published")); if (mobs) setMobOpts((mobs.items || []).map((x) => ({ value: x.id, label: x.data?.name || x.id })));
  })(); }, [guarded]);
  useEffect(() => { load(); }, [load]);

  const statuses = meta?.statuses || [];
  const visibleList = useMemo(() => typeFilter ? list.filter((item) => String(item.data?.recipe_type || "create_item") === typeFilter) : list, [list, typeFilter]);
  const statusLabel = (v) => statuses.find((s) => s.value === v)?.label || v;

  async function openItem(id) {
    const p = await guarded(() => fetchRecipe(id));
    if (p?.item) { setUsage(null); setEditing({ id, data: { ...EMPTY, ...(p.item.data || {}) }, status: p.item.status, validation: p.validation, isNew: false }); }
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
    const tools = Array.isArray(d.tools) ? d.tools : [];
    const results = Array.isArray(d.results) ? d.results : [];
    const byproducts = Array.isArray(d.byproducts) ? d.byproducts : [];
    const weeklyLimits = Array.isArray(d.weekly_limits) ? d.weekly_limits : [];
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
            <Field label="Основной результат"><select value={d.output_item_id} disabled={disabled} onChange={(e) => set("output_item_id", e.target.value)}><option value="">— предмет —</option>{itemOpts.map((o) => <option key={o.value} value={o.value}>{o.label} ({o.value})</option>)}</select></Field>
            {num("output_amount", "Кол-во результата")}
            {num("output_amount_min", "Минимум результата")}{num("output_amount_max", "Максимум результата")}
            <Field label="Если инвентарь заполнен"><select value={d.result_delivery || "overload"} disabled={disabled} onChange={(e) => set("result_delivery", e.target.value)}><option value="inventory">Только обычный инвентарь</option><option value="overload">Разрешить перегруз</option><option value="delivery">Сразу в доставку</option><option value="partial">Выдать сколько поместится</option><option value="reject">Запретить запуск</option></select></Field>
          </div>
          <div className="ntv2-form-row">
            <Field label="Качество результата"><select value={d.result_quality || ""} disabled={disabled} onChange={(e) => set("result_quality", e.target.value)}><option value="">Из предмета</option>{[["common","Обычный"],["uncommon","Необычный"],["rare","Редкий"],["epic","Эпический"],["legendary","Легендарный"],["mythic","Мифический"],["celestial","Небесный"],["divine","Божественный"]].map(([v,l]) => <option key={v} value={v}>{l}</option>)}</select></Field>
            {num("result_level", "Уровень результата")}
            <Field label="Одноручный / двуручный"><select value={d.crafted_handedness || "keep"} disabled={disabled} onChange={(e) => set("crafted_handedness", e.target.value)}><option value="keep">Как у предмета</option><option value="one_handed">Одноручный</option><option value="two_handed">Двуручный</option></select></Field>
            <label className="ntv2-check"><input type="checkbox" checked={Boolean(d.bind_on_create)} disabled={disabled} onChange={(e) => set("bind_on_create", e.target.checked)} /> Привязать</label>
            <label className="ntv2-check"><input type="checkbox" checked={Boolean(d.unique_result)} disabled={disabled} onChange={(e) => set("unique_result", e.target.checked)} /> Уникальный</label>
            <label className="ntv2-check"><input type="checkbox" checked={Boolean(d.critical_quality_upgrade)} disabled={disabled} onChange={(e) => set("critical_quality_upgrade", e.target.checked)} /> Крит повышает качество</label>
          </div>
          <Field label="Случайные эффекты результата"><select multiple value={(d.result_effects || []).map((x) => typeof x === "string" ? x : x.effect_id)} disabled={disabled} onChange={(e) => set("result_effects", [...e.target.selectedOptions].map((o) => o.value))}>{effectOpts.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</select></Field>

          <div className="ntv2-panel">
            <h4 className="ntv2-subhead">Ингредиенты ({ings.length})</h4>
            <div className="ntv2-list">
              {ings.map((row, i) => (
                <div className="ntv2-list-row" key={i}>
                  <select value={row.item_id || ""} disabled={disabled} onChange={(e) => setIng(i, { item_id: e.target.value })}><option value="">— предмет —</option>{itemOpts.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</select>
                  <select value={row.material_group_id || ""} disabled={disabled} onChange={(e) => setIng(i, { material_group_id: e.target.value })}><option value="">— группа материалов —</option>{materialGroupOpts.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</select>
                  <input type="number" style={{ width: 80 }} placeholder="кол-во" value={row.amount ?? 1} disabled={disabled} onChange={(e) => setIng(i, { amount: e.target.value })} />
                  <select value={row.role || ""} disabled={disabled} onChange={(e) => setIng(i, { role: e.target.value })}><option value="">роль…</option>{(meta.materialRoles || []).map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}</select>
                  <input className="ntv2-mono" placeholder="альтернативы ID" value={(row.alternatives || []).join(", ")} disabled={disabled} onChange={(e) => setIng(i, { alternatives: e.target.value.split(",").map((x) => x.trim()).filter(Boolean) })} />
                  <label className="ntv2-check"><input type="checkbox" checked={row.consumed !== false} disabled={disabled} onChange={(e) => setIng(i, { consumed: e.target.checked })} /> Списать</label>
                  {!disabled ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => set("ingredients", ings.filter((_, idx) => idx !== i))}>×</button> : null}
                </div>
              ))}
            </div>
            {!disabled ? <button type="button" className="ntv2-btn" style={{ marginTop: 6 }} onClick={() => set("ingredients", [...ings, { item_id: "", amount: 1 }])}>＋ Ингредиент</button> : null}
          </div>

          <div className="ntv2-panel"><h4 className="ntv2-subhead">Инструменты ({tools.length})</h4>
            {tools.map((row, i) => <div className="ntv2-list-row" key={i}>
              <select value={row.item_id || ""} disabled={disabled} onChange={(e) => set("tools", tools.map((x, n) => n === i ? { ...x, item_id: e.target.value } : x))}><option value="">— инструмент —</option>{itemOpts.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</select>
              <input type="number" placeholder="мин. прочность" value={row.min_durability ?? 0} disabled={disabled} onChange={(e) => set("tools", tools.map((x, n) => n === i ? { ...x, min_durability: e.target.value } : x))} />
              <input type="number" placeholder="потеря прочности" value={row.durability_loss ?? 0} disabled={disabled} onChange={(e) => set("tools", tools.map((x, n) => n === i ? { ...x, durability_loss: e.target.value } : x))} />
              {!disabled ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => set("tools", tools.filter((_, n) => n !== i))}>×</button> : null}
            </div>)}
            {!disabled ? <button type="button" className="ntv2-btn" onClick={() => set("tools", [...tools, { item_id: "", required: true, consumed: false, durability_loss: 0 }])}>＋ Инструмент</button> : null}
          </div>

          <div className="ntv2-panel"><h4 className="ntv2-subhead">Дополнительные и побочные результаты</h4>
            {[["results", results, "Результат"], ["byproducts", byproducts, "Побочный результат"]].map(([key, rows, label]) => <div key={key}><div className="ntv2-hint">{label}</div>
              {rows.map((row, i) => <div className="ntv2-list-row" key={i}><select value={row.item_id || ""} disabled={disabled} onChange={(e) => set(key, rows.map((x, n) => n === i ? { ...x, item_id: e.target.value } : x))}><option value="">— предмет —</option>{itemOpts.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</select><input type="number" placeholder="кол-во" value={row.amount ?? 1} disabled={disabled} onChange={(e) => set(key, rows.map((x, n) => n === i ? { ...x, amount: e.target.value } : x))} /><input type="number" placeholder="шанс %" value={row.chance ?? 100} disabled={disabled} onChange={(e) => set(key, rows.map((x, n) => n === i ? { ...x, chance: e.target.value } : x))} />{!disabled ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => set(key, rows.filter((_, n) => n !== i))}>×</button> : null}</div>)}
              {!disabled ? <button type="button" className="ntv2-btn" onClick={() => set(key, [...rows, { item_id: "", amount: 1, chance: 100, when: "success" }])}>＋ {label}</button> : null}
            </div>)}
          </div>

          <h4 className="ntv2-subhead">Параметры</h4>
          <div className="ntv2-form-row">{num("craft_time", "Время (сек)")}{num("success_chance", "Шанс успеха %")}{num("quality_chance", "Шанс качества %")}{num("fail_chance", "Шанс провала %")}</div>
          <div className="ntv2-form-row">{num("critical_chance", "Критический успех %")}{num("partial_success_chance", "Частичный успех %")}{num("energy_cost", "Энергия")}{num("min_energy", "Мин. энергия")}</div>
          <div className="ntv2-form-row">{num("partial_result_percent", "Результат при частичном успехе %")}</div>
          <div className="ntv2-form-row"><Field label="Материалы при провале"><select value={d.failure_material_policy || "lose_all"} disabled={disabled} onChange={(e) => set("failure_material_policy", e.target.value)}><option value="lose_all">Потерять все</option><option value="return_all">Вернуть все</option><option value="return_percent">Вернуть процент</option></select></Field>{d.failure_material_policy === "return_percent" ? num("failure_return_percent", "Вернуть материалов %") : null}<Field label="Эффект при провале"><select value={d.failure_effect_id || ""} disabled={disabled} onChange={(e) => set("failure_effect_id", e.target.value)}><option value="">—</option>{effectOpts.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</select></Field><Field label="Проклятие при провале"><select value={d.failure_curse_id || ""} disabled={disabled} onChange={(e) => set("failure_curse_id", e.target.value)}><option value="">—</option>{effectOpts.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</select></Field><Field label="Событие при провале"><select value={d.failure_event_id || ""} disabled={disabled} onChange={(e) => set("failure_event_id", e.target.value)}><option value="">—</option>{eventOpts.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</select></Field><Field label="Бой при провале"><select value={d.failure_battle_mob_id || ""} disabled={disabled} onChange={(e) => set("failure_battle_mob_id", e.target.value)}><option value="">—</option>{mobOpts.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</select></Field></div>
          <div className="ntv2-panel"><h4 className="ntv2-subhead">Стоимость создания</h4>
            <label className="ntv2-check"><input type="checkbox" checked={Boolean(d.free)} disabled={disabled} onChange={(e) => set("free", e.target.checked)} /> Бесплатно</label>
            {!d.free ? <div className="ntv2-form-row">{num("price_copper", "Медь")}{num("price_silver", "Серебро")}{num("price_gold", "Золото")}{num("price_magic_gold", "Маг. золото")}{num("price_ancient", "Древние")}</div> : null}
          </div>

          <div className="ntv2-panel">
            <h4 className="ntv2-subhead">Профессия, тип и формулы (ТЗ 13 §5.6–§5.8)</h4>
            <div className="ntv2-form-row">
              <Field label="Тип рецепта"><select value={d.recipe_type || ""} disabled={disabled} onChange={(e) => set("recipe_type", e.target.value)}><option value="">—</option>{(meta.recipeTypes || []).map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}</select></Field>
              <Field label="Профессия"><select value={d.profession || ""} disabled={disabled} onChange={(e) => set("profession", e.target.value)}><option value="">—</option>{professionOpts.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</select></Field>
              <Field label="Мастерская (объект)"><select value={d.workshop_id || ""} disabled={disabled} onChange={(e) => set("workshop_id", e.target.value)}><option value="">—</option>{workshopOpts.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</select></Field>
            </div>
            <div className="ntv2-form-row">{num("profession_level", "Уровень профессии")}{num("player_level", "Уровень игрока")}<Field label="Сложность"><input value={d.difficulty} disabled={disabled} onChange={(e) => set("difficulty", e.target.value)} /></Field></div>
            <div className="ntv2-form-row">
              {[["result_formula_id", "Формула результата"], ["time_formula_id", "Формула времени"], ["cost_formula_id", "Формула стоимости"], ["exp_formula_id", "Формула опыта"], ["energy_formula_id", "Формула энергии"], ["success_formula_id", "Формула успеха"], ["critical_formula_id", "Формула крита"], ["quality_formula_id", "Формула качества"]].map(([key, label]) => (
                <Field key={key} label={label}><select value={d[key] || ""} disabled={disabled} onChange={(e) => set(key, e.target.value)}><option value="">— без формулы —</option>{formulaOpts.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</select></Field>
              ))}
            </div>
            <div className="ntv2-form-row" style={{ gap: 14 }}>
              <label className="ntv2-check"><input type="checkbox" checked={Boolean(d.can_mass_craft)} disabled={disabled} onChange={(e) => set("can_mass_craft", e.target.checked)} /> Массовое создание</label>
              <label className="ntv2-check"><input type="checkbox" checked={Boolean(d.can_queue)} disabled={disabled} onChange={(e) => set("can_queue", e.target.checked)} /> В очередь</label>
              <label className="ntv2-check"><input type="checkbox" checked={Boolean(d.can_cancel)} disabled={disabled} onChange={(e) => set("can_cancel", e.target.checked)} /> Можно отменить</label>
            </div>
          </div>

          <div className="ntv2-panel"><h4 className="ntv2-subhead">Эффекты и тексты бота</h4>
            <Field label="Эффекты, влияющие на рецепт"><select multiple value={d.effect_ids || []} disabled={disabled} onChange={(e) => set("effect_ids", [...e.target.selectedOptions].map((o) => o.value))}>{effectOpts.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</select></Field>
            {[["text_workshop_open", "Открытие мастерской"], ["text_recipe_list", "Список рецептов"], ["text_recipe_card", "Карточка рецепта"], ["text_not_enough_ingredients", "Не хватает ингредиентов"], ["text_not_enough_tool", "Не хватает инструмента"], ["text_not_enough_money", "Не хватает денег"], ["text_not_enough_energy", "Не хватает энергии"], ["text_not_enough_level", "Не хватает уровня"], ["text_unavailable", "Рецепт недоступен"], ["text_inventory_full", "Не хватает места"], ["text_delivery", "Отправлено в доставку"], ["text_start", "Начало"], ["text_success", "Успех"], ["text_critical_success", "Критический успех"], ["text_partial_success", "Частичный успех"], ["text_fail", "Провал"], ["text_item_break", "Поломка предмета"], ["text_material_loss", "Потеря материалов"], ["text_result_received", "Получение результата"], ["text_disassemble", "Разборка"], ["text_repair", "Ремонт"], ["text_upgrade", "Улучшение"], ["text_enchant", "Зачарование"], ["text_purify", "Очищение"], ["text_cancel", "Отмена"]].map(([key, label]) => <Field key={key} label={label}><input value={d[key] || ""} disabled={disabled} onChange={(e) => set(key, e.target.value)} /></Field>)}
          </div>

          <div className="ntv2-panel"><h4 className="ntv2-subhead">Недельные лимиты ({weeklyLimits.length})</h4>
            {weeklyLimits.map((row, i) => <div className="ntv2-list-row" key={i}>
              <input className="ntv2-mono" placeholder="limit_id" value={row.id || ""} disabled={disabled} onChange={(e) => set("weekly_limits", weeklyLimits.map((x, n) => n === i ? { ...x, id: e.target.value } : x))} />
              <select value={row.limit_type || "recipe_count"} disabled={disabled} onChange={(e) => set("weekly_limits", weeklyLimits.map((x, n) => n === i ? { ...x, limit_type: e.target.value } : x))}><option value="recipe_count">Создания рецепта</option><option value="result_count">Количество результата</option><option value="rare_result_count">Редкие результаты</option><option value="critical_count">Критические успехи</option><option value="upgrade">Улучшения</option><option value="enchant">Зачарования</option><option value="purify">Очищения</option><option value="disassemble">Разборы</option><option value="workshop_use">Мастерская</option><option value="npc_use">NPC</option></select>
              <input type="number" min="0" placeholder="макс./неделю" value={row.max_per_week ?? 0} disabled={disabled} onChange={(e) => set("weekly_limits", weeklyLimits.map((x, n) => n === i ? { ...x, max_per_week: e.target.value } : x))} />
              <input placeholder="текст исчерпания" value={row.exhausted_text || ""} disabled={disabled} onChange={(e) => set("weekly_limits", weeklyLimits.map((x, n) => n === i ? { ...x, exhausted_text: e.target.value } : x))} />
              {!disabled ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => set("weekly_limits", weeklyLimits.filter((_, n) => n !== i))}>×</button> : null}
            </div>)}
            {!disabled ? <button type="button" className="ntv2-btn" onClick={() => set("weekly_limits", [...weeklyLimits, { id: `limit_${weeklyLimits.length + 1}`, limit_type: "recipe_count", max_per_week: 1, exhausted_text: "Недельный лимит исчерпан.", active: true }])}>＋ Недельный лимит</button> : null}
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
          {!editing.isNew ? <button type="button" className="ntv2-btn" onClick={async () => { const p = await guarded(() => fetchRecipeUsage(editing.id)); if (p) setUsage(p.usedBy || []); }}>Где используется</button> : null}
          {!editing.isNew && can.publish ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => setConfirm({ title: "Опубликовать рецепт?", dangerous: true, confirmLabel: "Опубликовать", body: <p>Рецепт будет проверен и опубликован.</p>, run: async (r) => { await guarded(() => recipeLifecycle(editing.id, "publish", r), "Опубликовано."); await refreshEditing(); } })}>Опубликовать</button> : null}
          {!editing.isNew && can.disable && editing.status === "published" ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => setConfirm({ title: "Отключить?", dangerous: true, confirmLabel: "Отключить", body: <p>Рецепт перестанет быть доступен.</p>, run: async (r) => { await guarded(() => recipeLifecycle(editing.id, "disable", r), "Отключено."); await refreshEditing(); } })}>Отключить</button> : null}
          {!editing.isNew && can.archive ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => setConfirm({ title: "В архив?", dangerous: true, confirmLabel: "В архив", body: <p>Рецепт уйдёт в архив.</p>, run: async (r) => { await guarded(() => recipeLifecycle(editing.id, "archive", r), "В архиве."); await refreshEditing(); } })}>В архив</button> : null}
          {!editing.isNew && can.del ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => setConfirm({ title: "Удалить рецепт?", dangerous: true, confirmLabel: "Удалить", body: <p>Полное удаление рецепта.</p>, run: async (r) => { await guarded(() => deleteRecipe(editing.id, editing.id, r), "Удалено."); setEditing(null); await load(); } })}>Удалить</button> : null}
        </div>

        {usage ? <div className="ntv2-panel"><h4 className="ntv2-subhead">Где используется</h4>{usage.length ? usage.map((u) => <div className="ntv2-list-row" key={u.id}><b>{u.name}</b><span className="ntv2-mono">{u.id}</span><span>{(u.fields || []).join(", ")}</span></div>) : <p className="ntv2-hint">Связей нет.</p>}</div> : null}

        {!editing.isNew ? <VersionHistory base="recipes" id={editing.id} canRollback={can.edit && (editing.status !== "published" || can.publish)} onRolledBack={refreshEditing} /> : null}

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
        <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)}><option value="">Все подразделы ремесла</option>{(meta.recipeTypes || []).map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}</select>
        {can.create ? <button type="button" className="ntv2-btn ntv2-btn-primary" onClick={startCreate}>＋ Новый рецепт</button> : null}
        {can.publish ? <button type="button" className="ntv2-btn" onClick={() => setConfirm({ title: "Импортировать существующие рецепты?", dangerous: true, confirmLabel: "Импортировать", body: <p>Рецепты из crafting_recipes.json будут заведены как опубликованные записи (без дублей).</p>, run: async (r) => { const p = await guarded(() => importRecipes("new", r), "Импорт выполнен."); if (p?.report) { const rep = p.report; await load(); window.alert(`Импорт рецептов: создано ${rep.created}, пропущено ${rep.skipped}, ошибок ${rep.invalid}.`); } } })}>Импортировать существующие</button> : null}
        <SearchBox value={query} onChange={setQuery} />
      </div>
      {!list.length ? <p className="ntv2-hint">Рецептов пока нет. Можно создать новый или импортировать существующие.</p> : null}
      <NoResults items={visibleList} query={query} />
      <div className="ntv2-list">
        {filterEntities(visibleList, query).map((item) => (
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
