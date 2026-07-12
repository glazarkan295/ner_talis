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
  const [extraRewards, setExtraRewards] = useState([]);
  const [data, setData] = useState({ name: "", command: "/promo", code_after_command: "", system_name: "", short_description: "", technical_description: "", promo_type: "general", category: "", tags: [], command_active: true, command_hidden: false, command_visible: true, platform: "both", starts_at: "", expires_at: "", one_use_per_player: true, per_player_limit: 1, daily_limit: 0, weekly_limit: 0, min_level: 0, max_level: 0, required_race: "", required_achievement_id: "", required_quest_id: "", required_reputation_id: "", required_reputation_value: 0, required_hidden_reputation_id: "", required_location_id: "", required_item_id: "", required_effect_id: "", requires_no_fine: false, requires_fine: false, new_players_only: false, old_players_only: false, allowed_players: [], excluded_players: [], success_text: "", already_used_text: "", expired_text: "", inactive_text: "", invalid_text: "", condition_error_text: "", inventory_full_text: "", delivery_text: "", reward_error_text: "" });
  const setDataField = (key, value) => setData((old) => ({ ...old, [key]: value }));

  const load = useCallback(async () => { const p = await guarded(() => fetchPromos()); if (p) setPromos(p.promos || []); }, [guarded]);
  useEffect(() => { (async () => { const m = await guarded(() => fetchPromosMeta()); if (m) setMeta(m); })(); }, [guarded]);
  useEffect(() => { load(); }, [load]);

  async function create() {
    const payload = [...rewards.map((r) => ({ item_id: r.key, amount: Number(r.amount) || 0 })).filter((r) => r.amount > 0), ...extraRewards.filter((r) => r.type && Number(r.amount) > 0)];
    const p = await guarded(() => createPromo(code.trim(), Number(uses) || 1, duration, payload, "", { ...data, code_after_command: data.code_after_command || code.trim() }), "Промокод создан.");
    if (p?.ok) { setCode(""); setUses(1); setDuration("never"); setRewards([]); setExtraRewards([]); await load(); }
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
            <div className="ntv2-form-row"><Field label="Название"><input value={data.name} onChange={(e) => setDataField("name", e.target.value)} /></Field><Field label="Команда"><input value={data.command} onChange={(e) => setDataField("command", e.target.value)} placeholder="/promo" /></Field><Field label="Код после команды"><input value={data.code_after_command} onChange={(e) => setDataField("code_after_command", e.target.value)} /></Field><Field label="Тип"><select value={data.promo_type} onChange={(e) => setDataField("promo_type", e.target.value)}>{["general","personal","single_use","multi_use","timed","limited","event","seasonal","compensation","test","admin","hidden"].map((x) => <option key={x}>{x}</option>)}</select></Field><Field label="Платформа"><select value={data.platform} onChange={(e) => setDataField("platform", e.target.value)}><option value="both">Telegram + VK</option><option value="telegram">Telegram</option><option value="vk">VK</option></select></Field></div>
            <div className="ntv2-form-row"><Field label="Дата начала"><input type="datetime-local" value={data.starts_at} onChange={(e) => setDataField("starts_at", e.target.value)} /></Field><Field label="Дата окончания"><input type="datetime-local" value={data.expires_at} onChange={(e) => setDataField("expires_at", e.target.value)} /></Field><Field label="Лимит игрока"><input type="number" min="0" value={data.per_player_limit} onChange={(e) => setDataField("per_player_limit", Number(e.target.value))} /></Field><Field label="В день"><input type="number" min="0" value={data.daily_limit} onChange={(e) => setDataField("daily_limit", Number(e.target.value))} /></Field><Field label="В неделю"><input type="number" min="0" value={data.weekly_limit} onChange={(e) => setDataField("weekly_limit", Number(e.target.value))} /></Field></div>
            <div className="ntv2-form-row"><Field label="Мин. уровень"><input type="number" value={data.min_level} onChange={(e) => setDataField("min_level", Number(e.target.value))} /></Field><Field label="Макс. уровень"><input type="number" value={data.max_level} onChange={(e) => setDataField("max_level", Number(e.target.value))} /></Field><Field label="Раса"><input value={data.required_race} onChange={(e) => setDataField("required_race", e.target.value)} /></Field><Field label="Достижение"><input value={data.required_achievement_id} onChange={(e) => setDataField("required_achievement_id", e.target.value)} /></Field><Field label="Квест"><input value={data.required_quest_id} onChange={(e) => setDataField("required_quest_id", e.target.value)} /></Field><Field label="Предмет"><input value={data.required_item_id} onChange={(e) => setDataField("required_item_id", e.target.value)} /></Field><Field label="Эффект"><input value={data.required_effect_id} onChange={(e) => setDataField("required_effect_id", e.target.value)} /></Field></div>
            <div className="ntv2-form-row">{[["command_active","Команда активна"],["command_hidden","Команда скрыта"],["command_visible","Команда видна"],["one_use_per_player","Один раз"],["requires_no_fine","Без штрафа"],["requires_fine","Со штрафом"],["new_players_only","Только новые"],["old_players_only","Только старые"]].map(([key,label]) => <label className="ntv2-check" key={key}><input type="checkbox" checked={Boolean(data[key])} onChange={(e) => setDataField(key,e.target.checked)} />{label}</label>)}</div>
            <Field label="Разрешённые NT-ID (по строкам)"><textarea value={(data.allowed_players || []).join("\n")} onChange={(e) => setDataField("allowed_players", e.target.value.split("\n").map((x) => x.trim()).filter(Boolean))} /></Field><Field label="Исключённые NT-ID"><textarea value={(data.excluded_players || []).join("\n")} onChange={(e) => setDataField("excluded_players", e.target.value.split("\n").map((x) => x.trim()).filter(Boolean))} /></Field>
            <RewardPicker value={rewards} onChange={setRewards} />
            <div className="ntv2-panel"><h4>Особые награды</h4>{extraRewards.map((r,i) => <div className="ntv2-form-row" key={i}><select value={r.type || "item"} onChange={(e) => setExtraRewards(extraRewards.map((x,j) => j===i ? {...x,type:e.target.value}:x))}>{["item","currency","experience","energy","skill_points","stat_points","effect","curse","achievement","reputation","hidden_reputation","access","recipe","skill","system_flag"].map((x) => <option key={x}>{x}</option>)}</select><input placeholder="ID объекта" value={r.object_id || ""} onChange={(e) => setExtraRewards(extraRewards.map((x,j) => j===i ? {...x,object_id:e.target.value}:x))} /><input type="number" min="1" value={r.amount || 1} onChange={(e) => setExtraRewards(extraRewards.map((x,j) => j===i ? {...x,amount:Number(e.target.value)}:x))} /><button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => setExtraRewards(extraRewards.filter((_,j) => j!==i))}>×</button></div>)}<button type="button" className="ntv2-btn" onClick={() => setExtraRewards([...extraRewards,{type:"item",object_id:"",amount:1}])}>＋ Добавить награду</button></div>
            <div className="ntv2-form-row"><Field label="Успех"><input value={data.success_text} onChange={(e) => setDataField("success_text",e.target.value)} /></Field><Field label="Уже использован"><input value={data.already_used_text} onChange={(e) => setDataField("already_used_text",e.target.value)} /></Field><Field label="Условия не выполнены"><input value={data.condition_error_text} onChange={(e) => setDataField("condition_error_text",e.target.value)} /></Field><Field label="Ошибка награды"><input value={data.reward_error_text} onChange={(e) => setDataField("reward_error_text",e.target.value)} /></Field></div>
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
            {(p.validation_warnings || []).map((warning) => <span className="ntv2-hint" key={warning}>⚠️ {warning}</span>)}
            {p.expires_at ? <span className="ntv2-hint">до {String(p.expires_at).slice(0, 16).replace("T", " ")}</span> : <span className="ntv2-hint">бессрочно</span>}
            <details><summary>История активаций ({(p.activation_history || []).length})</summary><div className="ntv2-list">{(p.activation_history || []).slice().reverse().map((row,i) => <div className="ntv2-list-row" key={`${row.at}-${i}`}><span className="ntv2-mono">{row.nt_id || row.game_id}</span><span>{row.platform || "—"}</span><span>{String(row.at || "").replace("T"," ").slice(0,19)}</span><span className={`ntv2-badge ${row.status === "success" ? "ntv2-badge-owner" : "ntv2-badge-danger"}`}>{row.status}</span>{row.error ? <span className="ntv2-error">{row.error}</span> : null}</div>)}</div></details>
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
