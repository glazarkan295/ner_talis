import React, { useEffect, useMemo, useState } from "react";
import "./AdminPanel.css";
import {
  changeCatalogItemImage,
  createPlayerViewToken,
  createPromo,
  deletePlayer,
  getAdminSessionToken,
  loadCatalog,
  loadCatalogItem,
  loadPlayer,
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
function RewardList({ selected, quantities, setQuantities }) {
  if (!selected.length) return <p>Ничего не выбрано в Каталоге.</p>;
  return <div className="nt-admin-list">{selected.map((item) => <div className="nt-admin-card nt-admin-row" key={rewardKey(item)}><b>{item.name}</b><span>{rewardKey(item)}</span><input type="number" min="1" value={quantities[rewardKey(item)] || 1} onChange={(e) => setQuantities((old) => ({ ...old, [rewardKey(item)]: e.target.value }))} /></div>)}</div>;
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
  const [quantities, setQuantities] = useState({});
  const [modalItem, setModalItem] = useState(null);
  const [players, setPlayers] = useState([]);
  const [playerQ, setPlayerQ] = useState("");
  const [targetGameId, setTargetGameId] = useState("");
  const [playerModal, setPlayerModal] = useState(null);
  const [promos, setPromos] = useState([]);
  const [promoCode, setPromoCode] = useState("");
  const [promoUses, setPromoUses] = useState(1);
  const [promoDuration, setPromoDuration] = useState("never");

  async function guarded(action, success = "") {
    try { setError(""); setOk(""); const result = await action(); if (success) setOk(success); return result; }
    catch (e) { setError(e.message || "Ошибка админ-панели."); throw e; }
  }
  useEffect(() => { guarded(async () => { const session = await getAdminSessionToken(); if (!session) throw new Error("Нет активной админ-сессии. Запросите новую ссылку в админ-чате."); setToken(session); }).catch(() => {}); }, []);
  useEffect(() => { if (!token) return; guarded(async () => setCatalog(await loadCatalog(token, catalogQ, category))).catch(() => {}); }, [token, catalogQ, category]);
  useEffect(() => { if (!token) return; guarded(async () => setPlayers((await loadPlayers(token, playerQ)).players || [])).catch(() => {}); }, [token, playerQ]);
  useEffect(() => { if (!token || tab !== "promos") return; guarded(async () => setPromos((await loadPromos(token)).promos || [])).catch(() => {}); }, [token, tab]);

  const playerOptions = useMemo(() => players.map((p) => <option key={p.game_id} value={p.game_id}>{p.name} — {p.game_id} — ур. {p.level}</option>), [players]);
  function addSelected(setter, item) { setter((old) => old.some((x) => rewardKey(x) === rewardKey(item)) ? old : [...old, item]); }

  if (!token && !error) return <div className="nt-admin"><div className="nt-admin-shell">Загрузка админ-панели...</div></div>;
  return <div className="nt-admin"><main className="nt-admin-shell"><h1>Админ-панель Нер-Талис</h1>
    <div className="nt-admin-tabs">{[["catalog","Каталог"],["delivery","Доставка"],["promos","Промокоды"],["players","Игроки"]].map(([id,label]) => <button key={id} className={tab===id?"active":""} onClick={() => setTab(id)}>{label}</button>)}</div>
    {error ? <div className="nt-admin-error">{error}</div> : null}{ok ? <div className="nt-admin-ok">{ok}</div> : null}

    {tab === "catalog" && <section><div className="nt-admin-row"><input placeholder="Поиск предмета" value={catalogQ} onChange={(e)=>setCatalogQ(e.target.value)} /><select value={category} onChange={(e)=>setCategory(e.target.value)}><option value="">Все категории</option>{catalog.categories.map((c)=><option key={c} value={c}>{c}</option>)}</select></div><div className="nt-admin-grid">{catalog.items.map((item)=><article className="nt-admin-card" key={rewardKey(item)}>{item.icon ? <img src={item.icon} alt=""/> : null}<h3>{item.name}</h3><p>{item.category}</p><button onClick={async()=>setModalItem((await guarded(()=>loadCatalogItem(token, rewardKey(item)))).item)}>Открыть</button></article>)}</div></section>}

    {tab === "delivery" && <section><div className="nt-admin-row"><input placeholder="Поиск игрока" value={playerQ} onChange={(e)=>setPlayerQ(e.target.value)} /><select value={targetGameId} onChange={(e)=>setTargetGameId(e.target.value)}><option value="">Выбрать игрока</option>{playerOptions}</select></div><RewardList selected={selectedDelivery} quantities={quantities} setQuantities={setQuantities}/><button onClick={()=>guarded(async()=>{ await sendDelivery(token, targetGameId, selectedToRewards(selectedDelivery, quantities)); }, "Дар свыше отправлен игроку и поставлен в очередь сообщения бота.")}>Отправить игроку</button></section>}

    {tab === "promos" && <section><h2>Создать</h2><div className="nt-admin-row"><input placeholder="Команда промокода" value={promoCode} onChange={(e)=>setPromoCode(e.target.value)} /><input type="number" min="1" value={promoUses} onChange={(e)=>setPromoUses(e.target.value)} /><select value={promoDuration} onChange={(e)=>setPromoDuration(e.target.value)}>{durations.map(([v,l])=><option key={v} value={v}>{l}</option>)}</select></div><RewardList selected={selectedPromo} quantities={quantities} setQuantities={setQuantities}/><button onClick={()=>guarded(async()=>{ await createPromo(token, promoCode, Number(promoUses), promoDuration, selectedToRewards(selectedPromo, quantities)); setPromos((await loadPromos(token)).promos || []); }, "Промокод создан.")}>Создать промокод</button><h2>Существующие</h2><div className="nt-admin-list">{promos.map((p)=><details className="nt-admin-card" key={p.code}><summary>{p.code} — {p.created_at || "без даты"}</summary><pre className="nt-admin-pre">{JSON.stringify(p, null, 2)}</pre></details>)}</div></section>}

    {tab === "players" && <section><div className="nt-admin-row"><input placeholder="Поиск по нику или ID" value={playerQ} onChange={(e)=>setPlayerQ(e.target.value)} /></div><div className="nt-admin-list">{players.map((p)=><button key={p.game_id} onClick={async()=>setPlayerModal((await guarded(()=>loadPlayer(token, p.game_id))).player)}>{p.name} — {p.game_id} — уровень {p.level}</button>)}</div></section>}

    {modalItem ? <div className="nt-admin-modal"><div className="nt-admin-modal-card"><button onClick={()=>setModalItem(null)}>Закрыть</button><h2>{modalItem.name}</h2><p>{modalItem.description}</p><p><b>Где найти:</b> {modalItem.sources_text || "—"}</p><p><b>Для чего нужен:</b> {modalItem.needs_text || "—"}</p>{modalItem.formulas?.length ? <pre className="nt-admin-pre">{JSON.stringify(modalItem.formulas, null, 2)}</pre> : null}<div className="nt-admin-row"><button onClick={()=>addSelected(setSelectedDelivery, modalItem)}>Выбрать для передачи</button><button onClick={()=>addSelected(setSelectedPromo, modalItem)}>Выбрать для промокода</button><label>Сменить изображение <input type="file" accept="image/png,image/jpeg,image/webp" onChange={(e)=>{ const file=e.target.files?.[0]; if(file) guarded(()=>changeCatalogItemImage(token, rewardKey(modalItem), file), "Изображение предмета заменено."); }} /></label></div></div></div> : null}
    {playerModal ? <div className="nt-admin-modal"><div className="nt-admin-modal-card"><button onClick={()=>setPlayerModal(null)}>Закрыть</button><h2>{playerModal.name} — {playerModal.game_id}</h2><pre className="nt-admin-pre">{playerModal.summary}</pre><div className="nt-admin-row"><button onClick={()=>{ if(window.confirm("Полностью удалить игрока?")) guarded(()=>deletePlayer(token, playerModal.game_id), "Игрок удалён."); }}>Удалить игрока</button><button onClick={async()=>{ const payload = await guarded(()=>createPlayerViewToken(token, playerModal.game_id)); window.open(payload.url, "_blank", "noopener"); }}>Просмотреть профиль</button><button onClick={async()=>{ const logs = await guarded(()=>loadPlayerLogs(token, playerModal.game_id)); setPlayerModal({ ...playerModal, logs: logs.logs || [] }); }}>Посмотреть логи</button></div>{playerModal.logs ? <pre className="nt-admin-pre">{JSON.stringify(playerModal.logs, null, 2)}</pre> : null}</div></div> : null}
  </main></div>;
}
