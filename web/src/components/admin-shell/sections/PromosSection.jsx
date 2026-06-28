import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  createPromo,
  deletePromo,
  fetchPromos,
  fetchPromosMeta,
  previewBroadcast,
  sendBroadcast,
} from "../../../api/adminPromosApi.js";
import { loadCatalog } from "../../../api/adminApi.js";
import { ConfirmModal } from "../ConfirmModal.jsx";
import { EmojiTextarea } from "../EmojiField.jsx";
import { SearchBox, NoResults, filterEntities } from "../SearchFilter.jsx";

function Field({ label, children }) {
  return <label className="ntv2-field"><span>{label}</span>{children}</label>;
}

function rewardKey(item) { return item.item_id || item.id; }

// Каталог-пикер наград (как в карточке игрока): монеты/опыт/очки — синтетические id.
function RewardPicker({ value, onChange }) {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("");
  const [catalog, setCatalog] = useState({ items: [], categories: [] });

  useEffect(() => {
    const id = window.setTimeout(async () => {
      try { setCatalog(await loadCatalog("", query, category)); } catch { /* ошибка всплывёт при создании */ }
    }, 250);
    return () => window.clearTimeout(id);
  }, [query, category]);

  const add = (item) => {
    const key = rewardKey(item);
    if (value.some((r) => r.key === key)) return;
    onChange([...value, { key, name: item.name, amount: 1 }]);
  };
  const setAmount = (key, amount) => onChange(value.map((r) => (r.key === key ? { ...r, amount } : r)));
  const remove = (key) => onChange(value.filter((r) => r.key !== key));

  return (
    <div>
      <div className="ntv2-filters">
        <input placeholder="Поиск предмета/валюты" value={query} onChange={(e) => setQuery(e.target.value)} />
        <select value={category} onChange={(e) => setCategory(e.target.value)}>
          <option value="">Все категории</option>
          {catalog.categories.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
      </div>
      <div className="ntv2-catalog-grid">
        {catalog.items.slice(0, 60).map((item) => (
          <button type="button" className="ntv2-catalog-card" key={rewardKey(item)} onClick={() => add(item)}>
            {item.icon ? <img src={item.icon} alt="" /> : null}
            <span>{item.name}</span>
          </button>
        ))}
      </div>
      {value.length ? (
        <div className="ntv2-panel">
          <h4 className="ntv2-subhead">Награда промокода</h4>
          <div className="ntv2-list">
            {value.map((r) => (
              <div className="ntv2-list-row" key={r.key}>
                <b>{r.name}</b>
                <span className="ntv2-mono">{r.key}</span>
                <input type="number" min="1" value={r.amount} style={{ width: 90 }} onChange={(e) => setAmount(r.key, e.target.value)} />
                <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => remove(r.key)}>×</button>
              </div>
            ))}
          </div>
        </div>
      ) : <p className="ntv2-hint">Выберите предметы/валюту из каталога для награды.</p>}
    </div>
  );
}

function PromosTab({ guarded, can }) {
  const [meta, setMeta] = useState(null);
  const [promos, setPromos] = useState([]);
  const [confirm, setConfirm] = useState(null);
  const [promoQuery, setPromoQuery] = useState("");
  const [code, setCode] = useState("");
  const [uses, setUses] = useState(1);
  const [duration, setDuration] = useState("never");
  const [rewards, setRewards] = useState([]);

  const load = useCallback(async () => { const p = await guarded(() => fetchPromos()); if (p) setPromos(p.promos || []); }, [guarded]);
  useEffect(() => { (async () => { const m = await guarded(() => fetchPromosMeta()); if (m) setMeta(m); })(); }, [guarded]);
  useEffect(() => { load(); }, [load]);

  async function create() {
    const payload = rewards.map((r) => ({ item_id: r.key, amount: Number(r.amount) || 0 })).filter((r) => r.amount > 0);
    const p = await guarded(() => createPromo(code.trim(), Number(uses) || 1, duration, payload, ""), "Промокод создан.");
    if (p?.ok) { setCode(""); setUses(1); setDuration("never"); setRewards([]); await load(); }
  }

  if (!meta) return <p className="ntv2-hint">Загрузка…</p>;

  return (
    <div>
      {can.manage ? (
        <div className="ntv2-panel">
          <h3>Новый промокод</h3>
          <div className="ntv2-world-form">
            <div className="ntv2-form-row">
              <Field label="Код (без слэша)"><input value={code} onChange={(e) => setCode(e.target.value)} placeholder="START100" /></Field>
              <Field label="Использований"><input type="number" min="1" value={uses} onChange={(e) => setUses(e.target.value)} /></Field>
              <Field label="Время жизни"><select value={duration} onChange={(e) => setDuration(e.target.value)}>{meta.durations.map((d) => <option key={d.value} value={d.value}>{d.label}</option>)}</select></Field>
            </div>
            <RewardPicker value={rewards} onChange={setRewards} />
            <div className="ntv2-form-row" style={{ marginTop: 10 }}>
              <button type="button" className="ntv2-btn ntv2-btn-primary" disabled={!code.trim() || !rewards.length} onClick={create}>Создать промокод</button>
            </div>
          </div>
        </div>
      ) : null}

      <h3>Промокоды</h3>
      <div className="ntv2-filters"><SearchBox value={promoQuery} onChange={setPromoQuery} placeholder="Поиск по коду/награде…" /></div>
      {!promos.length ? <p className="ntv2-hint">Промокодов пока нет.</p> : null}
      <NoResults items={promos} query={promoQuery} />
      <div className="ntv2-list">
        {filterEntities(promos, promoQuery).map((p) => (
          <div className="ntv2-list-row" key={p.code}>
            <b>{p.code}</b>
            <span className={`ntv2-badge ${p.active ? "ntv2-badge-owner" : "ntv2-badge-danger"}`}>{p.active ? "активен" : "выключен"}</span>
            <span className="ntv2-hint">осталось: {p.uses_left}, использован: {p.used_count}</span>
            {p.expires_at ? <span className="ntv2-hint">до {String(p.expires_at).slice(0, 16).replace("T", " ")}</span> : <span className="ntv2-hint">бессрочно</span>}
            {can.manage ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => setConfirm({ code: p.code })}>Удалить</button> : null}
          </div>
        ))}
      </div>

      <ConfirmModal open={Boolean(confirm)} title="Удалить промокод?" dangerous confirmLabel="Удалить" requireReason
        body={<p>Промокод «{confirm?.code}» будет удалён без возможности восстановления.</p>}
        onConfirm={async () => { await guarded(() => deletePromo(confirm.code), "Промокод удалён."); setConfirm(null); await load(); }}
        onCancel={() => setConfirm(null)} />
    </div>
  );
}

function BroadcastTab({ guarded }) {
  const [meta, setMeta] = useState(null);
  const [audience, setAudience] = useState("all");
  const [specific, setSpecific] = useState([""]);
  const [message, setMessage] = useState("");
  const [count, setCount] = useState(null);
  const [confirm, setConfirm] = useState(null);

  useEffect(() => { (async () => { const m = await guarded(() => fetchPromosMeta()); if (m) setMeta(m); })(); }, [guarded]);

  const specificClean = useMemo(() => specific.map((s) => s.trim()).filter(Boolean), [specific]);
  const canSend = Boolean(message.trim() && (audience !== "specific" || specificClean.length));

  async function preview() {
    const p = await guarded(() => previewBroadcast(audience, specificClean));
    if (p) { setCount(p.recipients); setConfirm({ recipients: p.recipients, label: p.audienceLabel }); }
  }

  if (!meta) return <p className="ntv2-hint">Загрузка…</p>;

  return (
    <div>
      <div className="ntv2-panel">
        <h3>Рассылка игрокам</h3>
        <Field label="Аудитория">
          <select value={audience} onChange={(e) => { setAudience(e.target.value); setCount(null); }}>
            {meta.audiences.map((a) => <option key={a.value} value={a.value}>{a.label}</option>)}
          </select>
        </Field>
        {audience === "specific" ? (
          <div>
            {specific.map((value, index) => (
              <div className="ntv2-form-row" key={index} style={{ gap: 6, alignItems: "center" }}>
                <input placeholder="Ник или игровой ID" value={value} onChange={(e) => setSpecific((old) => old.map((v, i) => (i === index ? e.target.value : v)))} />
                {specific.length > 1 ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => setSpecific((old) => old.filter((_, i) => i !== index))}>×</button> : null}
              </div>
            ))}
            <button type="button" className="ntv2-btn" onClick={() => setSpecific((old) => [...old, ""])}>＋ Добавить игрока</button>
          </div>
        ) : null}
        <Field label="Текст сообщения"><EmojiTextarea rows={5} value={message} onChange={(v) => { setMessage(v); setCount(null); }} placeholder="Текст придёт игрокам в чат бота" /></Field>
        <div className="ntv2-form-row" style={{ marginTop: 8 }}>
          <button type="button" className="ntv2-btn ntv2-btn-primary" disabled={!canSend} onClick={preview}>Проверить аудиторию и отправить</button>
          {count != null ? <span className="ntv2-hint">получателей: {count}</span> : null}
        </div>
        <p className="ntv2-hint">Изображение/видео/файл добавляются ссылкой в текст — игроки получат сообщение в том же виде.</p>
      </div>

      <ConfirmModal open={Boolean(confirm)} title="Отправить рассылку?" dangerous confirmLabel="Отправить" requireReason
        body={<p>Сообщение получат: <b>{confirm?.label}</b> — {confirm?.recipients} игрок(ов). Действие необратимо.</p>}
        onConfirm={async (reason) => { const r = await guarded(() => sendBroadcast(audience, message.trim(), specificClean, reason), "Рассылка отправлена."); if (r?.ok) { setMessage(""); setCount(null); } setConfirm(null); }}
        onCancel={() => setConfirm(null)} />
    </div>
  );
}

export function PromosSection({ guarded, hasPerm }) {
  const [tab, setTab] = useState("promos");
  const can = useMemo(() => ({
    view: hasPerm("promos.view"), manage: hasPerm("promos.manage"), broadcast: hasPerm("broadcast.send"),
  }), [hasPerm]);

  return (
    <section className="ntv2-section">
      <h2>Промокоды и рассылки</h2>
      <div className="ntv2-filters">
        {can.view ? <button type="button" className={`ntv2-btn${tab === "promos" ? " ntv2-btn-primary" : ""}`} onClick={() => setTab("promos")}>Промокоды</button> : null}
        {can.broadcast ? <button type="button" className={`ntv2-btn${tab === "broadcast" ? " ntv2-btn-primary" : ""}`} onClick={() => setTab("broadcast")}>Рассылка</button> : null}
      </div>
      {tab === "promos" && can.view ? <PromosTab guarded={guarded} can={can} /> : null}
      {tab === "broadcast" && can.broadcast ? <BroadcastTab guarded={guarded} /> : null}
    </section>
  );
}
