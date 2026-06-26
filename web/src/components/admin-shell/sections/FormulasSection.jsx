import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  fetchFormulaMeta, fetchFormulas, fetchFormula, createFormula, updateFormula,
  formulaLifecycle, evaluateFormula, fetchFormulaWhereUsed,
} from "../../../api/adminFormulaApi.js";

// Конструктор формул (ТЗ 13 §2): выражение + переменные + ограничения +
// «Проверить формулу» (безопасный вычислитель на бэкенде).

const EMPTY = {
  name: "", category: "exp", short_description: "", technical_description: "",
  expression: "", variables: [], min_result: "", max_result: "", rounding: "none",
  is_percent: false, allow_negative: true, allow_zero: true, used_in: "",
};

function Field({ label, hint, children }) {
  return <label className="ntv2-field"><span>{label}{hint ? <i className="ntfx-hint" title={hint}> ⓘ</i> : null}</span>{children}</label>;
}

export function FormulasSection({ guarded, hasPerm }) {
  const [meta, setMeta] = useState(null);
  const [list, setList] = useState([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(null);
  const [data, setData] = useState(null);
  const [creating, setCreating] = useState(false);
  const [newId, setNewId] = useState("");
  const [testValues, setTestValues] = useState({});
  const [testResult, setTestResult] = useState(null);
  const [whereUsed, setWhereUsed] = useState(null);
  const [info, setInfo] = useState("");

  const can = useMemo(() => ({
    create: hasPerm("formula.create"), edit: hasPerm("formula.edit"),
    publish: hasPerm("formula.publish"),
  }), [hasPerm]);

  const load = useCallback(async () => {
    const p = await guarded(() => fetchFormulas(statusFilter)); if (p) setList(p.items || []);
  }, [guarded, statusFilter]);
  useEffect(() => { (async () => { const m = await guarded(() => fetchFormulaMeta()); if (m) setMeta(m); })(); }, [guarded]);
  useEffect(() => { load(); }, [load]);

  const statuses = meta?.statuses || [];
  const catLabel = (v) => meta?.categories?.find((c) => c.value === v)?.label || v;
  const statusLabel = (v) => statuses.find((s) => s.value === v)?.label || v;

  async function openItem(id) {
    setSelected(id); setCreating(false); setTestResult(null); setWhereUsed(null);
    const p = await guarded(() => fetchFormula(id));
    if (p) { setData({ ...EMPTY, ...(p.item.data || {}) }); seedTestValues(p.item.data); }
  }
  function startCreate() {
    setCreating(true); setSelected(null); setNewId(""); setData({ ...EMPTY }); setTestResult(null); setTestValues({}); setWhereUsed(null);
  }
  async function loadWhereUsed() {
    if (!selected) return;
    const p = await guarded(() => fetchFormulaWhereUsed(selected));
    if (p) setWhereUsed(p.usage || []);
  }
  function seedTestValues(d) {
    const tv = {};
    (d?.variables || []).forEach((v) => { if (v.key) tv[v.key] = v.default ?? 0; });
    setTestValues(tv);
  }
  async function save() {
    if (creating) {
      if (!newId.trim()) { setInfo("Укажите ID формулы."); return; }
      const r = await guarded(() => createFormula(newId.trim(), data, "create formula"));
      if (r) { setInfo("Создано."); setCreating(false); await load(); await openItem(newId.trim()); }
    } else if (selected) {
      const r = await guarded(() => updateFormula(selected, data, "edit formula"));
      if (r) { setInfo("Сохранено."); await load(); }
    }
  }
  async function lifecycle(verb) {
    if (!selected) return;
    const r = await guarded(() => formulaLifecycle(selected, verb, verb));
    if (r) { setInfo(`Статус: ${verb}`); await load(); }
  }
  async function runTest() {
    const r = await guarded(() => evaluateFormula(data, testValues));
    if (r) setTestResult(r.test);
  }

  const setF = (k, v) => setData((d) => ({ ...d, [k]: v }));
  const setVar = (i, k, v) => setData((d) => ({ ...d, variables: d.variables.map((row, idx) => idx === i ? { ...row, [k]: v } : row) }));
  const addVar = () => setData((d) => ({ ...d, variables: [...(d.variables || []), { key: "", label: "", default: "", description: "" }] }));
  const delVar = (i) => setData((d) => ({ ...d, variables: d.variables.filter((_, idx) => idx !== i) }));

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return list.filter((f) => !q || (f.data?.name || "").toLowerCase().includes(q) || f.id.toLowerCase().includes(q));
  }, [list, query]);

  const allVarKeys = useMemo(() => {
    const declared = (data?.variables || []).map((v) => v.key).filter(Boolean);
    const catalog = (meta?.variableCatalog || []).map((v) => v.key);
    return [...new Set([...declared, ...catalog])];
  }, [data, meta]);

  return (
    <section className="ntv2-section ntfx">
      <style>{FX_CSS}</style>
      <header className="ntv2-section-head">
        <div>
          <h2>🧮 Конструктор формул</h2>
          <p className="ntv2-muted">Игровые формулы без правки кода: выражение, переменные, ограничения и проверка результата.</p>
        </div>
        {can.create ? <button type="button" className="ntv2-btn" onClick={startCreate}>＋ Новая формула</button> : null}
      </header>

      <div className="ntfx-layout">
        <aside className="ntfx-list">
          <input className="ntfx-search" placeholder="🔎 Поиск…" value={query} onChange={(e) => setQuery(e.target.value)} />
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            <option value="">Все статусы</option>
            {statuses.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
          </select>
          <ul>
            {filtered.map((f) => (
              <li key={f.id} className={selected === f.id ? "active" : ""} onClick={() => openItem(f.id)}>
                <b>{f.data?.name || f.id}</b>
                <small>{catLabel(f.data?.category)} · {statusLabel(f.status)}</small>
              </li>
            ))}
            {!filtered.length ? <li className="ntfx-empty">Пусто</li> : null}
          </ul>
        </aside>

        <div className="ntfx-main">
          {info ? <div className="ntfx-info">{info}</div> : null}
          {!data ? (
            <div className="ntfx-placeholder">Выберите формулу слева или создайте новую.</div>
          ) : (
            <>
              <div className="ntfx-form">
                {creating ? <Field label="ID формулы"><input value={newId} onChange={(e) => setNewId(e.target.value)} placeholder="mob_exp" /></Field> : null}
                <div className="ntv2-form-row">
                  <Field label="Название"><input value={data.name} onChange={(e) => setF("name", e.target.value)} /></Field>
                  <Field label="Категория"><select value={data.category} onChange={(e) => setF("category", e.target.value)}>{(meta?.categories || []).map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}</select></Field>
                </div>
                <Field label="Текст формулы" hint="Поддерживаются + - * / // % **, скобки, сравнения, тернарный if, функции min/max/abs/round/floor/ceil/sqrt/pow и переменные.">
                  <textarea rows={2} value={data.expression} onChange={(e) => setF("expression", e.target.value)} placeholder="base_amount * mob_level" />
                </Field>
                <Field label="Краткое описание"><input value={data.short_description} onChange={(e) => setF("short_description", e.target.value)} /></Field>
                <Field label="Техническое описание"><textarea rows={2} value={data.technical_description} onChange={(e) => setF("technical_description", e.target.value)} /></Field>

                <div className="ntfx-vars">
                  <div className="ntfx-vars-head"><b>Переменные</b>{can.edit ? <button type="button" className="ntv2-btn-mini" onClick={addVar}>＋ Переменная</button> : null}</div>
                  {(data.variables || []).map((v, i) => (
                    <div className="ntfx-var-row" key={i}>
                      <input placeholder="ключ" value={v.key} onChange={(e) => setVar(i, "key", e.target.value)} />
                      <input placeholder="подпись" value={v.label} onChange={(e) => setVar(i, "label", e.target.value)} />
                      <input placeholder="по умолч." value={v.default} onChange={(e) => setVar(i, "default", e.target.value)} />
                      <input placeholder="описание" value={v.description} onChange={(e) => setVar(i, "description", e.target.value)} />
                      <button type="button" className="ntv2-btn-mini" onClick={() => delVar(i)}>✕</button>
                    </div>
                  ))}
                  {meta?.variableCatalog?.length ? (
                    <div className="ntfx-catalog">Каталог: {meta.variableCatalog.map((v) => <code key={v.key} title={v.label}>{v.key}</code>)}</div>
                  ) : null}
                </div>

                <div className="ntv2-form-row">
                  <Field label="Мин. результат"><input type="number" value={data.min_result} onChange={(e) => setF("min_result", e.target.value)} /></Field>
                  <Field label="Макс. результат"><input type="number" value={data.max_result} onChange={(e) => setF("max_result", e.target.value)} /></Field>
                  <Field label="Округление"><select value={data.rounding} onChange={(e) => setF("rounding", e.target.value)}>{(meta?.roundingModes || []).map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}</select></Field>
                </div>
                <div className="ntv2-form-row" style={{ gap: 14 }}>
                  <label className="ntv2-check"><input type="checkbox" checked={data.is_percent} onChange={(e) => setF("is_percent", e.target.checked)} /> Это шанс (0–100%)</label>
                  <label className="ntv2-check"><input type="checkbox" checked={data.allow_negative} onChange={(e) => setF("allow_negative", e.target.checked)} /> Разрешить отрицательный</label>
                  <label className="ntv2-check"><input type="checkbox" checked={data.allow_zero} onChange={(e) => setF("allow_zero", e.target.checked)} /> Разрешить ноль</label>
                </div>

                <div className="ntfx-actions">
                  {can.edit ? <button type="button" className="ntv2-btn" onClick={save}>{creating ? "Создать" : "Сохранить"}</button> : null}
                  {!creating ? <button type="button" className="ntv2-btn-mini" onClick={loadWhereUsed}>Где используется</button> : null}
                  {!creating && can.publish ? (
                    <>
                      <button type="button" className="ntv2-btn-mini" onClick={() => lifecycle("publish")}>Опубликовать</button>
                      <button type="button" className="ntv2-btn-mini" onClick={() => lifecycle("disable")}>Отключить</button>
                      <button type="button" className="ntv2-btn-mini" onClick={() => lifecycle("archive")}>В архив</button>
                    </>
                  ) : null}
                </div>
                {whereUsed ? (
                  <div className="ntfx-whereused">
                    <b>Где используется ({whereUsed.length}):</b>
                    {whereUsed.length === 0 ? <span className="ntv2-muted"> нигде</span> : (
                      <ul>{whereUsed.map((r, i) => <li key={i}>{r.type}: <b>{r.name}</b> <code>{r.id}</code> <span className="ntv2-muted">({(r.fields || []).join(", ")})</span></li>)}</ul>
                    )}
                  </div>
                ) : null}
              </div>

              <div className="ntfx-test">
                <h3>🧪 Проверить формулу</h3>
                <div className="ntfx-test-vars">
                  {allVarKeys.map((k) => (
                    <label key={k} className="ntfx-test-var">
                      <span>{k}</span>
                      <input type="number" value={testValues[k] ?? ""} onChange={(e) => setTestValues((t) => ({ ...t, [k]: e.target.value }))} />
                    </label>
                  ))}
                  {!allVarKeys.length ? <span className="ntv2-muted">Нет переменных — формула из констант.</span> : null}
                </div>
                <button type="button" className="ntv2-btn" onClick={runTest}>Рассчитать</button>
                {testResult ? (
                  <div className={`ntfx-result ${testResult.ok ? "ok" : "bad"}`}>
                    {testResult.ok ? (
                      <>
                        <div className="ntfx-result-val">Результат: <b>{testResult.result}</b>{testResult.raw_result !== testResult.result ? <span className="ntv2-muted"> (сырой: {testResult.raw_result})</span> : null}</div>
                        {testResult.notes?.length ? <ul>{testResult.notes.map((n, i) => <li key={i}>{n}</li>)}</ul> : null}
                      </>
                    ) : (
                      <ul>{(testResult.errors || []).map((e, i) => <li key={i} className="err">{e}</li>)}</ul>
                    )}
                  </div>
                ) : null}
              </div>
            </>
          )}
        </div>
      </div>
    </section>
  );
}

const FX_CSS = `
.ntfx-layout{display:flex;gap:14px;align-items:flex-start}
.ntfx-list{width:240px;flex-shrink:0}
.ntfx-list .ntfx-search,.ntfx-list select{width:100%;padding:6px 8px;border:1px solid #cbd5e1;border-radius:8px;margin-bottom:6px}
.ntfx-list ul{list-style:none;margin:0;padding:0;max-height:62vh;overflow:auto}
.ntfx-list li{padding:8px 10px;border:1px solid #e2e8f0;border-radius:8px;margin-bottom:6px;cursor:pointer;display:flex;flex-direction:column}
.ntfx-list li.active{border-color:#2563eb;background:#eff6ff}
.ntfx-list li small{color:#94a3b8}
.ntfx-empty{color:#94a3b8;text-align:center}
.ntfx-main{flex:1;min-width:0;display:flex;gap:14px;flex-wrap:wrap}
.ntfx-form{flex:1;min-width:340px}
.ntfx-form .ntv2-field{display:block;margin-bottom:8px}
.ntfx-hint{color:#2563eb;cursor:help;font-style:normal}
.ntfx-info{flex-basis:100%;background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;padding:6px 10px;font-size:13px}
.ntfx-placeholder{color:#64748b;padding:30px;text-align:center;border:1px dashed #cbd5e1;border-radius:12px;flex-basis:100%}
.ntfx-vars{border:1px solid #e2e8f0;border-radius:8px;padding:8px;margin:8px 0}
.ntfx-vars-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px}
.ntfx-var-row{display:flex;gap:6px;margin-bottom:5px}
.ntfx-var-row input{flex:1;min-width:0;padding:4px 6px;border:1px solid #cbd5e1;border-radius:6px}
.ntfx-catalog{font-size:11px;color:#64748b;margin-top:4px}
.ntfx-catalog code{margin-right:6px;background:#f1f5f9;padding:1px 4px;border-radius:4px;cursor:help}
.ntfx-actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}
.ntfx-test{width:300px;flex-shrink:0;border:1px solid #e2e8f0;border-radius:12px;padding:12px;background:#f8fafc}
.ntfx-test h3{margin:0 0 8px;font-size:15px}
.ntfx-test-vars{display:flex;flex-direction:column;gap:6px;margin-bottom:10px}
.ntfx-test-var{display:flex;justify-content:space-between;align-items:center;gap:8px;font-size:13px}
.ntfx-test-var input{width:120px;padding:4px 6px;border:1px solid #cbd5e1;border-radius:6px}
.ntfx-result{margin-top:10px;border-radius:8px;padding:8px;font-size:13px}
.ntfx-result.ok{background:#f0fdf4;border:1px solid #bbf7d0}
.ntfx-result.bad{background:#fef2f2;border:1px solid #fecaca}
.ntfx-result-val{font-size:15px}
.ntfx-result ul{margin:6px 0 0;padding-left:18px}
.ntfx-result li.err{color:#b91c1c}
`;
