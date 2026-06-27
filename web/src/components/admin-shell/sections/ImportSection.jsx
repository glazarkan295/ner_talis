import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  fetchFeatureFlags,
  fetchImageAudit,
  fetchImportMeta,
  fetchImportReport,
  runImport,
  runImportCheck,
  runImportDryRun,
  runImportRollback,
  setFeatureFlag,
} from "../../../api/adminImportApi.js";

// Унифицированная панель импорта-миграции (full-import ТЗ §13 Этап 5):
// выбор типов + режима, dry-run (предпросмотр без записи), реальный импорт,
// проверка связей, просмотр отчёта (таблица + markdown).
export function ImportSection({ guarded, hasPerm }) {
  const canRun = hasPerm("world.publish");
  const canViewFlags = hasPerm("system.view");
  const canToggleFlags = hasPerm("system.manage");
  const [meta, setMeta] = useState(null);
  const [kinds, setKinds] = useState([]);
  const [mode, setMode] = useState("new");
  const [result, setResult] = useState(null);
  const [markdown, setMarkdown] = useState("");
  const [check, setCheck] = useState(null);
  const [images, setImages] = useState(null);
  const [flags, setFlags] = useState(null);
  const [flagMeta, setFlagMeta] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const loadMeta = useCallback(async () => {
    try {
      const m = await fetchImportMeta();
      setMeta(m);
    } catch (e) {
      setError(String(e.message || e));
    }
  }, []);

  const loadReport = useCallback(async () => {
    try {
      const r = await fetchImportReport("json");
      if (r?.content) setResult(r.content);
    } catch {
      /* отчётов ещё нет — не ошибка */
    }
  }, []);

  const loadFlags = useCallback(async () => {
    if (!canViewFlags) return;
    try {
      const r = await fetchFeatureFlags();
      setFlags(r?.flags || {});
      setFlagMeta(r?.meta || []);
    } catch (e) {
      setError(String(e.message || e));
    }
  }, [canViewFlags]);

  useEffect(() => {
    loadMeta();
    loadReport();
    loadFlags();
  }, [loadMeta, loadReport, loadFlags]);

  const toggleFlag = async (name, enabled) => {
    const r = await guarded(() => setFeatureFlag(name, enabled), "Флаг обновлён.");
    if (r?.flags) setFlags(r.flags);
  };

  const toggleKind = (k) =>
    setKinds((cur) => (cur.includes(k) ? cur.filter((x) => x !== k) : [...cur, k]));

  const allKinds = meta?.kinds || [];
  const selectedLabel = useMemo(
    () => (kinds.length ? `${kinds.length} выбрано` : "все типы"),
    [kinds],
  );

  const doDryRun = async () => {
    setBusy(true);
    setError("");
    setMarkdown("");
    try {
      const r = await runImportDryRun(kinds, mode);
      setResult(r);
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setBusy(false);
    }
  };

  const doRun = async () => {
    setBusy(true);
    setError("");
    setMarkdown("");
    const r = await guarded(() => runImport(kinds, mode), "Импорт выполнен.");
    if (r) setResult(r);
    setBusy(false);
  };

  const doCheck = async () => {
    setBusy(true);
    setError("");
    try {
      const r = await runImportCheck();
      setCheck(r?.report || null);
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setBusy(false);
    }
  };

  const doRollback = async () => {
    if (!window.confirm("Откатить последний импорт? Будут удалены записи, созданные последним импортом (правки админа сохранятся).")) return;
    setBusy(true);
    setError("");
    const r = await guarded(() => runImportRollback(), "Откат выполнен.");
    if (r) setCheck(null), setResult(null);
    setBusy(false);
    await loadReport();
  };

  const doImageAudit = async () => {
    setBusy(true);
    setError("");
    try {
      const r = await fetchImageAudit();
      setImages(r);
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setBusy(false);
    }
  };

  const showMarkdown = async () => {
    try {
      const r = await fetchImportReport("md");
      setMarkdown(r?.content || "");
    } catch (e) {
      setError(String(e.message || e));
    }
  };

  const summary = result?.summary || null;
  const reports = result?.reports || [];

  return (
    <div className="ntv2-section">
      <h3 className="ntv2-subhead">Импорт контента в админ-панель</h3>
      <p className="ntv2-hint">
        Перенос существующего игрового контента из кода/статики в конструкторы.
        Сначала запустите <b>dry-run</b> (ничего не пишет), затем реальный импорт.
      </p>

      {error ? <div className="ntv2-error">{error}</div> : null}

      <div className="ntv2-panel">
        <h4 className="ntv2-subhead">Что импортировать ({selectedLabel})</h4>
        <div className="ntv2-form-row" style={{ flexWrap: "wrap", gap: 8 }}>
          {allKinds.map((k) => (
            <label className="ntv2-check" key={k}>
              <input type="checkbox" checked={kinds.includes(k)} onChange={() => toggleKind(k)} /> {k}
            </label>
          ))}
        </div>
        <div className="ntv2-form-row" style={{ gap: 14, marginTop: 8 }}>
          <label className="ntv2-label">
            Режим повторного импорта
            <select value={mode} onChange={(e) => setMode(e.target.value)}>
              {(meta?.modes || [{ value: "new", label: "Добавить новые" }]).map((m) => (
                <option key={m.value} value={m.value}>{m.label}</option>
              ))}
            </select>
          </label>
        </div>
        <div className="ntv2-form-row" style={{ gap: 10, marginTop: 10 }}>
          <button type="button" className="ntv2-btn" disabled={busy} onClick={doDryRun}>Dry-run (предпросмотр)</button>
          {canRun ? <button type="button" className="ntv2-btn ntv2-btn-primary" disabled={busy} onClick={doRun}>Импортировать</button> : null}
          {canRun ? <button type="button" className="ntv2-btn ntv2-btn-danger" disabled={busy} onClick={doRollback}>Откатить последний</button> : null}
          <button type="button" className="ntv2-btn" disabled={busy} onClick={doCheck}>Проверить связи</button>
          <button type="button" className="ntv2-btn" disabled={busy} onClick={doImageAudit}>🖼 Аудит изображений</button>
          <button type="button" className="ntv2-btn" disabled={busy} onClick={showMarkdown}>Отчёт (markdown)</button>
        </div>
      </div>

      {summary ? (
        <div className="ntv2-panel">
          <h4 className="ntv2-subhead">
            {result?.dry_run ? "Предпросмотр (dry-run)" : "Результат импорта"} — режим {summary.mode}
          </h4>
          <p className="ntv2-hint">
            Найдено {summary.found} · создано {summary.created} · обновлено {summary.updated} ·
            пропущено {summary.skipped} · некорректных {summary.invalid} ·
            ошибок {summary.errors} · проверить {summary.needs_check}
          </p>
          <table className="ntv2-table">
            <thead>
              <tr><th>Тип</th><th>Найдено</th><th>Создано</th><th>Обновлено</th><th>Пропущено</th><th>Некорр.</th><th>Проверить</th></tr>
            </thead>
            <tbody>
              {reports.map((r) => (
                <tr key={r.kind}>
                  <td>{r.kind}</td><td>{r.found}</td><td>{r.created}</td><td>{r.updated}</td>
                  <td>{r.skipped}</td><td>{r.invalid}</td><td>{(r.needs_check || []).length}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {reports.flatMap((r) => (r.needs_check || []).map((nc, i) => (
            <p className="ntv2-hint" key={`${r.kind}-${i}`}>⚠️ {r.kind}/{nc.id}: {nc.reason}</p>
          )))}
        </div>
      ) : null}

      {check ? (
        <div className={`ntv2-panel ${check.ok ? "" : "ntv2-danger-zone"}`}>
          <h4 className="ntv2-subhead">{check.ok ? "✅ Связи целы" : `❌ Проблемы связей (${check.count})`}</h4>
          {(check.issues || []).map((it, i) => (
            <div className="ntv2-error" key={i}>{it.type}/{it.id}: {it.reason}</div>
          ))}
        </div>
      ) : null}

      {markdown ? (
        <div className="ntv2-panel">
          <h4 className="ntv2-subhead">Отчёт (markdown)</h4>
          <pre className="ntv2-mono" style={{ whiteSpace: "pre-wrap", maxHeight: 360, overflow: "auto" }}>{markdown}</pre>
        </div>
      ) : null}

      {images ? (
        <div className={`ntv2-panel ${images.missing || images.external ? "ntv2-danger-zone" : ""}`}>
          <h4 className="ntv2-subhead">
            🖼 Аудит изображений (§6): всего {images.total} · ок {images.ok} · нет файла {images.missing} · внешних {images.external}
          </h4>
          {(!images.missing && !images.external) ? <p className="ntv2-hint">Все изображения — локальные файлы и на месте.</p> : null}
          {(images.problems || []).map((p, i) => (
            <div className={p.status === "missing" ? "ntv2-error" : "ntv2-hint"} key={i}>
              {p.status === "missing" ? "❌ нет файла" : "⚠️ внешняя ссылка"}: {p.kind}/{p.id} · {p.field} = <code>{p.value}</code>
            </div>
          ))}
        </div>
      ) : null}

      {canViewFlags && flags ? (
        <div className="ntv2-panel">
          <h4 className="ntv2-subhead">Источники данных игры (V2)</h4>
          <p className="ntv2-hint">
            Включает чтение игрой данных из конструкторов V2 по доменам. По умолчанию
            всё ВЫКЛ — игра работает по старому коду (fallback), пока вы не включите.
          </p>
          <div className="ntv2-form-row" style={{ flexWrap: "wrap", gap: 10 }}>
            {flagMeta.map((f) => (
              <label className="ntv2-check" key={f.name} title={f.wired ? `${f.name} — влияет на runtime` : `${f.name} — пока только в админке, gameplay не меняет`}>
                <input
                  type="checkbox"
                  checked={Boolean(flags[f.name])}
                  disabled={!canToggleFlags}
                  onChange={(e) => toggleFlag(f.name, e.target.checked)}
                /> {f.label} {f.wired ? "✅" : <span style={{ opacity: 0.5 }}>(не подключено)</span>}
              </label>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
