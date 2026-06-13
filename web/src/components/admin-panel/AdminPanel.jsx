import React, { useEffect, useMemo, useState } from "react";
import "./AdminPanel.css";
import {
  changeCatalogItemImage,
  createPlayerViewToken,
  createPromo,
  deletePlayer,
  deletePromo,
  getAdminSessionToken,
  loadCatalog,
  loadCatalogItem,
  loadPlayer,
  loadPlayerChat,
  loadPlayerLogs,
  loadPlayers,
  loadPromos,
  sendDelivery,
} from "../../api/adminApi.js";

const durations = [
  ["1h", "1 час"], ["12h", "12 часов"], ["1d", "1 день"], ["7d", "7 дней"],
  ["30d", "30 дней"], ["365d", "365 дней"], ["never", "бессрочный"],
];

function rewardKey(item) { return item.item_id || item.id; }
function selectedToRewards(selected, quantities) {
  return selected.map((item) => ({ item_id: rewardKey(item), amount: Number(quantities[rewardKey(item)] || 1) })).filter((x) => x.amount > 0);
}
function formatRewardCode(value) {
  const text = String(value || "").trim();
  if (!text) return "";
  return text.startsWith("/") ? text : `/${text}`;
}
function secondsLeftText(seconds) {
  if (seconds === null || seconds === undefined) return "бессрочный";
  const value = Math.max(0, Number(seconds) || 0);
  if (value <= 0) return "истёк";
  const days = Math.floor(value / 86400);
  const hours = Math.floor((value % 86400) / 3600);
  const minutes = Math.floor((value % 3600) / 60);
  if (days) return `${days} дн. ${hours} ч.`;
  if (hours) return `${hours} ч. ${minutes} мин.`;
  return `${minutes} мин.`;
}
function RewardList({ selected, quantities, setQuantities, onRemove }) {
  if (!selected.length) return <p>Ничего не выбрано в Каталоге.</p>;
  return <div className="nt-admin-list">{selected.map((item) => {
    const key = rewardKey(item);
    return <div className="nt-admin-card nt-admin-row nt-admin-reward-row" key={key}>
      <b>{item.name}</b>
      <span>{key}</span>
      <input type="number" min="1" value={quantities[key] || 1} onChange={(e) => setQuantities((old) => ({ ...old, [key]: e.target.value }))} />
      <button className="nt-admin-icon-button nt-danger" type="button" title="Убрать из списка" onClick={() => onRemove?.(key)}>×</button>
    </div>;
  })}</div>;
}

export function AdminPanel() {
  const [token, setToken] = useState("");
  const [tab, setTab] = useState("catalog");
  const [error, setError] = useState("");
  const [ok, setOk] = useState("");
  const [catalog, setCatalog] = useState({ items: [], categories: [] });
  const [catalogQ, setCatalogQ] = useState("");
  const [category, setCategory] = useState("");
  const [selectedDelivery, setSelectedDelivery] = useState([]);
  const [selectedPromo, setSelectedPromo] = useState([]);
  // Separate quantity maps so a number set for delivery does not leak into promo.
  const [deliveryQuantities, setDeliveryQuantities] = useState({});
  const [promoQuantities, setPromoQuantities] = useState({});
  const [modalItem, setModalItem] = useState(null);
  const [imageFile, setImageFile] = useState(null);
  const [imageConfirm, setImageConfirm] = useState(false);
  const [players, setPlayers] = useState([]);
  const [playerQ, setPlayerQ] = useState("");
  const [targetGameId, setTargetGameId] = useState("");
  const [playerModal, setPlayerModal] = useState(null);
  const [promos, setPromos] = useState([]);
  const [promoCode, setPromoCode] = useState("/promo_code");
  const [promoUses, setPromoUses] = useState(1);
  const [promoDuration, setPromoDuration] = useState("never");

  async function guarded(action, success = "") {
    try { setError(""); setOk(""); const result = await action(); if (success) setOk(success); return result; }
    catch (e) { setError(e.message || "Ошибка админ-панели."); throw e; }
  }
  async function refreshCatalog() {
    setCatalog(await loadCatalog(token, catalogQ, category));
  }
  async function refreshPromos() {
    setPromos((await loadPromos(token)).promos || []);
  }
  useEffect(() => { guarded(async () => { const session = await getAdminSessionToken(); if (!session) throw new Error("Нет активной админ-сессии. Запросите новую ссылку в админ-чате."); setToken(session); }).catch(() => {}); }, []);
  useEffect(() => { if (!token) return; guarded(refreshCatalog).catch(() => {}); }, [token, catalogQ, category]);
  useEffect(() => { if (!token) return; guarded(async () => setPlayers((await loadPlayers(token, playerQ)).players || [])).catch(() => {}); }, [token, playerQ]);
  useEffect(() => { if (!token || tab !== "promos") return; guarded(refreshPromos).catch(() => {}); }, [token, tab]);

  const playerOptions = useMemo(() => players.map((p) => <option key={p.game_id} value={p.game_id}>{p.name} — {p.game_id} — ур. {p.level}</option>), [players]);
  function addSelected(setter, item) { setter((old) => old.some((x) => rewardKey(x) === rewardKey(item)) ? old : [...old, item]); }
  function removeSelected(setter, key) { setter((old) => old.filter((item) => rewardKey(item) !== key)); }
  async function openCatalogItem(item) {
    const payload = await guarded(() => loadCatalogItem(token, rewardKey(item)));
    setModalItem(payload.item);
    setImageFile(null);
    setImageConfirm(false);
  }
  async function submitImageChange() {
    if (!modalItem || !imageFile || !imageConfirm) return;
    const payload = await guarded(() => changeCatalogItemImage(token, rewardKey(modalItem), imageFile), "Изображение предмета заменено.");
    const newPath = payload.asset_path;
    setModalItem((current) => current ? { ...current, icon: newPath, asset_path: newPath, image: newPath } : current);
    setCatalog((current) => ({
      ...current,
      items: current.items.map((item) => rewardKey(item) === rewardKey(modalItem) ? { ...item, icon: newPath } : item),
    }));
    setImageFile(null);
    setImageConfirm(false);
  }

  if (!token && !error) return <div className="nt-admin"><div className="nt-admin-shell">Загрузка админ-панели...</div></div>;
  return <div className="nt-admin"><main className="nt-admin-shell"><h1>Админ-панель Нер-Талис</h1>
    <div className="nt-admin-tabs">{[["catalog","Каталог"],["delivery","Доставка"],["promos","Промокоды"],["players","Игроки"]].map(([id,label]) => <button key={id} className={tab===id?"active":""} onClick={() => setTab(id)}>{label}</button>)}</div>
    {error ? <div className="nt-admin-error">{error}</div> : null}{ok ? <div className="nt-admin-ok">{ok}</div> : null}

    {tab === "catalog" && <section><div className="nt-admin-row"><input placeholder="Поиск предмета" value={catalogQ} onChange={(e)=>setCatalogQ(e.target.value)} /><select value={category} onChange={(e)=>setCategory(e.target.value)}><option value="">Все категории</option>{catalog.categories.map((c)=><option key={c} value={c}>{c}</option>)}</select></div><div className="nt-admin-grid">{catalog.items.map((item)=><article className="nt-admin-card" key={rewardKey(item)}>{item.icon ? <img src={item.icon} alt=""/> : null}<h3>{item.name}</h3><p>{item.category}</p><button onClick={()=>openCatalogItem(item)}>Открыть</button></article>)}</div></section>}

    {tab === "delivery" && <section><div className="nt-admin-row"><input placeholder="Поиск игрока" value={playerQ} onChange={(e)=>setPlayerQ(e.target.value)} /><select value={targetGameId} onChange={(e)=>setTargetGameId(e.target.value)}><option value="">Выбрать игрока</option>{playerOptions}</select></div><RewardList selected={selectedDelivery} quantities={deliveryQuantities} setQuantities={setDeliveryQuantities} onRemove={(key)=>removeSelected(setSelectedDelivery, key)}/><button onClick={()=>guarded(async()=>{ await sendDelivery(token, targetGameId, selectedToRewards(selectedDelivery, deliveryQuantities)); }, "Дар от высших сил отправлен игроку и поставлен в очередь сообщения бота.")}>Отправить игроку</button></section>}

    {tab === "promos" && <section><h2>Создать</h2><div className="nt-admin-row"><input placeholder="Команда промокода" value={promoCode} onChange={(e)=>setPromoCode(e.target.value)} /><input type="number" min="1" value={promoUses} onChange={(e)=>setPromoUses(e.target.value)} /><select value={promoDuration} onChange={(e)=>setPromoDuration(e.target.value)}>{durations.map(([v,l])=><option key={v} value={v}>{l}</option>)}</select></div><p className="nt-admin-hint">Игрок вводит команду: <b>{formatRewardCode(promoCode) || "—"}</b></p><RewardList selected={selectedPromo} quantities={promoQuantities} setQuantities={setPromoQuantities} onRemove={(key)=>removeSelected(setSelectedPromo, key)}/><button onClick={()=>guarded(async()=>{ await createPromo(token, formatRewardCode(promoCode), Number(promoUses), promoDuration, selectedToRewards(selectedPromo, promoQuantities)); await refreshPromos(); }, "Промокод создан.")}>Создать промокод</button><h2>Существующие</h2><div className="nt-admin-list">{promos.map((p)=><details className="nt-admin-card" key={p.code}><summary><span>{p.code} — {p.created_at || "без даты"}</span><button className="nt-admin-icon-button nt-danger" type="button" title="Удалить промокод" onClick={(event)=>{ event.preventDefault(); event.stopPropagation(); if(window.confirm(`Удалить промокод ${p.code}?`)) guarded(async()=>{ await deletePromo(token, p.code); await refreshPromos(); }, "Промокод удалён."); }}>×</button></summary><div className="nt-admin-promo-info"><p>Срок жизни: {p.expires_at || "бессрочный"}</p><p>Осталось жить: {secondsLeftText(p.seconds_left)}</p><p>Использований: {p.used_count || 0}</p><p>Осталось использований: {p.uses_left ?? 0}</p><pre className="nt-admin-pre">{JSON.stringify(p.reward || {}, null, 2)}</pre></div></details>)}</div></section>}

    {tab === "players" && <section><div className="nt-admin-row"><input placeholder="Поиск по нику или ID" value={playerQ} onChange={(e)=>setPlayerQ(e.target.value)} /></div><div className="nt-admin-list">{players.map((p)=><button key={p.game_id} onClick={async()=>setPlayerModal((await guarded(()=>loadPlayer(token, p.game_id))).player)}>{p.name} — {p.game_id} — уровень {p.level}</button>)}</div></section>}

    {modalItem ? <div className="nt-admin-modal"><div className="nt-admin-modal-card"><button onClick={()=>setModalItem(null)}>Закрыть</button><h2>{modalItem.name}</h2>{modalItem.icon ? <img className="nt-admin-modal-icon" src={modalItem.icon} alt="" /> : null}<p>{modalItem.description}</p><p><b>Где найти:</b> {modalItem.sources_text || "—"}</p><p><b>Для чего нужен:</b> {modalItem.needs_text || "—"}</p>{modalItem.formulas?.length ? <pre className="nt-admin-pre">{JSON.stringify(modalItem.formulas, null, 2)}</pre> : null}<div className="nt-admin-row"><button onClick={()=>addSelected(setSelectedDelivery, modalItem)}>Выбрать для передачи</button><button onClick={()=>addSelected(setSelectedPromo, modalItem)}>Выбрать для промокода</button></div><div className="nt-admin-upload-box"><label>Новое изображение предмета <input type="file" accept="image/png,image/jpeg,image/webp" onChange={(e)=>{ setImageFile(e.target.files?.[0] || null); setImageConfirm(false); }} /></label>{imageFile ? <label className="nt-admin-check"><input type="checkbox" checked={imageConfirm} onChange={(e)=>setImageConfirm(e.target.checked)} /> Подтверждаю замену изображения этого предмета во всех профилях и каталоге</label> : null}<button type="button" disabled={!imageFile || !imageConfirm} onClick={submitImageChange}>Подтвердить смену изображения</button></div></div></div> : null}
    {playerModal ? <div className="nt-admin-modal"><div className="nt-admin-modal-card"><button onClick={()=>setPlayerModal(null)}>Закрыть</button><h2>{playerModal.name} — {playerModal.game_id}</h2><pre className="nt-admin-pre">{playerModal.summary}</pre><div className="nt-admin-row"><button onClick={()=>{ if(window.confirm("Полностью удалить игрока?")) guarded(async()=>{ const gid = playerModal.game_id; await deletePlayer(token, gid); setPlayerModal(null); setPlayers((old)=>old.filter((p)=>p.game_id!==gid)); }, "Игрок удалён."); }}>Удалить игрока</button><button onClick={async()=>{ const payload = await guarded(()=>createPlayerViewToken(token, playerModal.game_id)); window.open(payload.url, "_blank", "noopener"); }}>Просмотреть профиль</button><button onClick={async()=>{ const logs = await guarded(()=>loadPlayerLogs(token, playerModal.game_id)); setPlayerModal({ ...playerModal, logs: logs.logs || [], chat: null }); }}>Посмотреть логи</button><button onClick={async()=>{ const chat = await guarded(()=>loadPlayerChat(token, playerModal.game_id)); setPlayerModal({ ...playerModal, chat: chat.chat || [], logs: null }); }}>Просмотреть чат</button></div>{playerModal.logs ? <pre className="nt-admin-pre">{JSON.stringify(playerModal.logs, null, 2)}</pre> : null}{playerModal.chat ? <pre className="nt-admin-pre">{JSON.stringify(playerModal.chat, null, 2)}</pre> : null}</div></div> : null}
  </main></div>;
}
