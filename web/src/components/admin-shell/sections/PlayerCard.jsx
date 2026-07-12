import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  deletePlayer,
  fetchPlayer,
  fetchPlayerChat,
  fetchPlayerLogs,
  forgiveFine,
  grantRewards,
  messagePlayer,
  openPlayerView,
  openPlayerReadonlyView,
  repairFines,
  removeFine,
  deleteBrokenFine,
  resetPlayer,
  unstuckPlayer,
} from "../../../api/adminV2Api.js";
import { loadCatalog } from "../../../api/adminApi.js";
import { tr, FINE_STATUS } from "../../../i18n/adminLabels.js";
import {
  fetchPlayerAchievements,
  grantAchievementToPlayer,
  revokeAchievementFromPlayer,
} from "../../../api/adminAchievementApi.js";
import { ConfirmModal } from "../ConfirmModal.jsx";
import { TechnicalData } from "../TechnicalData.jsx";
import { EmojiTextarea } from "../EmojiField.jsx";

// Admin achievements panel for a player: progress + manual grant/revoke.
function AchievementsPanel({ gameId, guarded, hasPerm }) {
  const [data, setData] = useState(null);
  const [grantId, setGrantId] = useState("");
  const canGrant = hasPerm("achievement.grant_manual");
  const canRevoke = hasPerm("achievement.revoke_manual");

  const load = useCallback(async () => {
    const payload = await guarded(() => fetchPlayerAchievements(gameId));
    if (payload?.progress) setData(payload.progress);
  }, [guarded, gameId]);
  useEffect(() => { load(); }, [load]);

  if (!data) return <div className="ntv2-panel"><h3>Достижения</h3><p className="ntv2-hint">Загрузка…</p></div>;
  const earned = data.achievements.filter((a) => a.earned);
  const rest = data.achievements.filter((a) => !a.earned);
  return (
    <div className="ntv2-panel">
      <h3>Достижения ({earned.length}/{data.achievements.length})</h3>
      <div className="ntv2-list">
        {earned.map((a) => (
          <div className="ntv2-list-row" key={a.id}>
            <b>{a.name || a.id}</b>
            <span className="ntv2-badge ntv2-badge-owner">{a.rarity || "—"}</span>
            <span className="ntv2-hint">{a.source === "manual" ? "вручную" : "авто"}</span>
            {canRevoke ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => guarded(() => revokeAchievementFromPlayer(a.id, gameId, "откат из карточки"), "Достижение отозвано.").then(load)}>Отозвать</button> : null}
          </div>
        ))}
        {rest.map((a) => (
          <div className="ntv2-list-row" key={a.id}>
            <span>{a.name || a.id}</span>
            <span className="ntv2-mono">{a.id}</span>
            {a.progress ? <span className="ntv2-hint">{a.progress}</span> : null}
            {canGrant ? <button type="button" className="ntv2-btn" onClick={() => guarded(() => grantAchievementToPlayer(a.id, gameId, "выдано из карточки"), "Достижение выдано.").then(load)}>Выдать</button> : null}
          </div>
        ))}
        {!data.achievements.length ? <p className="ntv2-hint">Опубликованных достижений нет.</p> : null}
      </div>
      {canGrant ? (
        <div className="ntv2-form-row" style={{ marginTop: 10 }}>
          <input className="ntv2-mono" placeholder="id достижения для ручной выдачи" value={grantId} onChange={(e) => setGrantId(e.target.value)} />
          <button type="button" className="ntv2-btn" disabled={!grantId.trim()} onClick={() => guarded(() => grantAchievementToPlayer(grantId.trim(), gameId, "ручная выдача"), "Достижение выдано.").then(() => { setGrantId(""); load(); })}>Выдать по id</button>
        </div>
      ) : null}
    </div>
  );
}

function rewardKey(item) { return item.item_id || item.id; }

// Catalog-backed reward picker: search the catalog, pick items + amounts,
// the parent grants them in one audited operation.
function RewardPicker({ onGrant, disabled }) {
  const [query, setQuery] = useState("");
  const [catalog, setCatalog] = useState({ items: [], categories: [] });
  const [category, setCategory] = useState("");
  const [selected, setSelected] = useState({}); // key -> {item, amount}

  useEffect(() => {
    const id = window.setTimeout(async () => {
      try { setCatalog(await loadCatalog("", query, category)); } catch { /* surfaced by parent on grant */ }
    }, 250);
    return () => window.clearTimeout(id);
  }, [query, category]);

  const chosen = useMemo(() => Object.values(selected), [selected]);

  function add(item) {
    const key = rewardKey(item);
    setSelected((old) => ({ ...old, [key]: { item, amount: old[key]?.amount || 1 } }));
  }
  function setAmount(key, amount) {
    setSelected((old) => ({ ...old, [key]: { ...old[key], amount } }));
  }
  function remove(key) {
    setSelected((old) => { const next = { ...old }; delete next[key]; return next; });
  }

  function grant(reason) {
    const rewards = chosen
      .map(({ item, amount }) => ({ item_id: rewardKey(item), amount: Number(amount) || 0 }))
      .filter((r) => r.amount > 0);
    return onGrant(rewards, reason).then(() => setSelected({}));
  }

  return (
    <div>
      <div className="ntv2-filters">
        <input placeholder="Поиск предмета" value={query} onChange={(e) => setQuery(e.target.value)} />
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

      {chosen.length ? (
        <div className="ntv2-panel">
          <h4 className="ntv2-subhead">К выдаче</h4>
          <div className="ntv2-list">
            {chosen.map(({ item, amount }) => {
              const key = rewardKey(item);
              return (
                <div className="ntv2-list-row" key={key}>
                  <b>{item.name}</b>
                  <span className="ntv2-mono">{key}</span>
                  <input type="number" min="1" value={amount} style={{ width: 90 }}
                    onChange={(e) => setAmount(key, e.target.value)} />
                  <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => remove(key)}>×</button>
                </div>
              );
            })}
          </div>
          <RewardGrantButton disabled={disabled} chosenCount={chosen.length} onGrant={grant} />
        </div>
      ) : <p className="ntv2-hint">Выберите предметы/валюту из каталога.</p>}
    </div>
  );
}

function RewardGrantButton({ chosenCount, onGrant, disabled }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" className="ntv2-btn ntv2-btn-primary" disabled={disabled} onClick={() => setOpen(true)}>
        Выдать игроку ({chosenCount})
      </button>
      <ConfirmModal
        open={open}
        title="Выдать награды игроку?"
        body={<p>Будет выдано позиций: <b>{chosenCount}</b>. Игрок получит сообщение в чат бота.</p>}
        confirmLabel="Выдать"
        requireReason
        onConfirm={async (reason) => { await onGrant(reason); setOpen(false); }}
        onCancel={() => setOpen(false)}
      />
    </>
  );
}

export function PlayerCard({ gameId, guarded, hasPerm, onBack, onDeleted }) {
  const [player, setPlayer] = useState(null);
  const [confirm, setConfirm] = useState(null); // {title, body, dangerous, run, confirmLabel}
  const [message, setMessage] = useState("");
  const [logs, setLogs] = useState(null);
  const [chat, setChat] = useState(null);

  const load = useCallback(async () => {
    const payload = await guarded(() => fetchPlayer(gameId));
    if (payload) setPlayer(payload.player);
  }, [guarded, gameId]);

  useEffect(() => { load(); }, [load]);

  async function openView() {
    const payload = await guarded(() => openPlayerView(gameId));
    if (payload?.url) window.open(payload.url, "_blank", "noopener");
  }
  async function openReadonlyView() { const payload=await guarded(()=>openPlayerReadonlyView(gameId));if(payload?.url)window.open(payload.url,"_blank","noopener"); }

  async function sendMessage(reason) {
    await guarded(() => messagePlayer(gameId, message.trim(), reason), "Сообщение отправлено игроку.");
    setMessage("");
  }

  if (!player) {
    return (
      <section className="ntv2-section">
        <button type="button" className="ntv2-btn" onClick={onBack}>← К списку</button>
        <p className="ntv2-hint">Загрузка карточки…</p>
      </section>
    );
  }

  const fines = player.fines || [];
  const fineHistory = player.fineHistory || [];

  return (
    <section className="ntv2-section">
      <div className="ntv2-card-head">
        <button type="button" className="ntv2-btn" onClick={onBack}>← К списку</button>
        <h2>{player.name || "без имени"}</h2>
        <span className="ntv2-mono">{player.game_id}</span>
      </div>

      <div className="ntv2-cards">
        <div className="ntv2-card"><div className="ntv2-card-label">Уровень</div><div className="ntv2-card-value">{player.level}</div></div>
        <div className="ntv2-card"><div className="ntv2-card-label">Опыт</div><div className="ntv2-card-value">{player.experience}</div></div>
        <div className="ntv2-card"><div className="ntv2-card-label">Монеты (медь)</div><div className="ntv2-card-value">{player.money}</div></div>
        <div className="ntv2-card"><div className="ntv2-card-label">Локация</div><div className="ntv2-card-value">{player.location || "—"}</div></div>
        <div className="ntv2-card"><div className="ntv2-card-label">Активность</div><div className="ntv2-card-value">{player.last_activity || "—"}</div></div>
      </div>

      {/* Быстрые действия */}
      <div className="ntv2-form-row" style={{ marginTop: 14 }}>
        <button type="button" className="ntv2-btn" onClick={openReadonlyView}>Открыть read-only профиль</button>
        {/* ТЗ 22 §3: токен профиля даёт РЕДАКТИРУЕМЫЙ доступ (backend требует inventory.edit),
            поэтому кнопку показываем только при этом праве — иначе 403 разлогинивал бы админа. */}
        {hasPerm("inventory.edit") ? <button type="button" className="ntv2-btn" onClick={openView}>Открыть редактируемый профиль</button> : null}
        <button type="button" className="ntv2-btn" onClick={async () => setLogs((await guarded(() => fetchPlayerLogs(gameId)))?.logs || [])}>Логи 24ч</button>
        <button type="button" className="ntv2-btn" onClick={async () => setChat((await guarded(() => fetchPlayerChat(gameId)))?.chat || [])}>Чат 24ч</button>
        {hasPerm("players.unstuck") ? (
          <button type="button" className="ntv2-btn" onClick={() => setConfirm({
            title: "Сбросить застревание?",
            body: <p>Сбросит текущее действие/бой/таймер и вернёт игрока на Центральную площадь Селдара. Прогресс, инвентарь и эффекты не трогаются.</p>,
            confirmLabel: "Разблокировать",
            run: async (reason) => { const r = await guarded(() => unstuckPlayer(gameId, reason), "Игрок разблокирован."); await load(); return r; },
          })}>Anti-stuck</button>
        ) : null}
      </div>

      {logs ? <TechnicalData label={`Логи (${logs.length})`} value={logs} /> : null}
      {chat ? <TechnicalData label={`Чат (${chat.length})`} value={chat} /> : null}

      {/* Сообщение игроку */}
      {hasPerm("players.message") ? (
        <div className="ntv2-panel">
          <h3>Сообщение игроку</h3>
          <EmojiTextarea rows={3} placeholder="Текст сообщения — придёт в чат бота" value={message} onChange={setMessage} style={{ width: "100%", boxSizing: "border-box" }} />
          <div className="ntv2-form-row" style={{ marginTop: 8 }}>
            <button type="button" className="ntv2-btn ntv2-btn-primary" disabled={!message.trim()} onClick={() => sendMessage("")}>Отправить</button>
          </div>
        </div>
      ) : null}

      {/* Награды */}
      {hasPerm("rewards.grant") ? (
        <div className="ntv2-panel">
          <h3>Выдать награды</h3>
          <RewardPicker onGrant={async (rewards, reason) => {
            if (!rewards.length) return;
            await guarded(() => grantRewards(gameId, rewards, reason), "Награды выданы.");
            await load();
          }} />
        </div>
      ) : null}

      {/* Штрафы */}
      {hasPerm("fines.manage") ? (
        <div className="ntv2-panel">
          <h3>Штрафы ({fines.length})</h3>
          {!fines.length ? <p className="ntv2-hint">Активных штрафов нет.</p> : (
            <div className="ntv2-list">
              {fines.map((f) => (
                <div className="ntv2-list-row" key={f.id}>
                  <span>{f.source || "штраф"}</span>
                  <span className="ntv2-badge">{f.amount} меди</span>
                  <span className="ntv2-hint">день {f.day} · {tr(FINE_STATUS, f.status)}</span>
                  <button type="button" className="ntv2-btn" onClick={() => setConfirm({ title: "Снять этот штраф?", body: <p>{f.id}</p>, confirmLabel: "Снять", dangerous: true, run: async (reason) => { await guarded(() => removeFine(gameId, f.id, reason), "Штраф снят."); await load(); } })}>Снять</button>
                  <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => setConfirm({ title: "Удалить битый штраф?", body: <p>Принудительное удаление {f.id} останется в истории и аудите.</p>, confirmLabel: "Удалить", dangerous: true, run: async (reason) => { await guarded(() => deleteBrokenFine(gameId, f.id, reason), "Штраф удалён."); await load(); } })}>Удалить</button>
                </div>
              ))}
            </div>
          )}
          <div className="ntv2-form-row" style={{ marginTop: 10 }}>
            {fines.length ? (
              <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => setConfirm({
                title: "Простить все штрафы?",
                body: <p>С игрока будут сняты все активные штрафы ({fines.length}) и снят запрет на перемещение.</p>,
                confirmLabel: "Простить",
                dangerous: true,
                run: async (reason) => { await guarded(() => forgiveFine(gameId, reason), "Штрафы прощены."); await load(); },
              })}>Простить штрафы</button>
            ) : null}
            {/* §6: найти и починить зависшие штрафы (терминальные, что висят как активные). */}
            <button type="button" className="ntv2-btn" onClick={async () => {
              const res = await guarded(() => repairFines(gameId, "проверка штрафов из панели"), "Проверка штрафов выполнена.");
              await load();
              const rep = res?.report;
              if (rep) window.alert(rep.fixed ? `Исправлено. Состояние: ${rep.state}. Изменения: ${(rep.issues || []).join(", ") || "—"}` : `Штрафы в порядке. Состояние: ${rep.state}.`);
            }}>Проверить штрафы</button>
          </div>
          <details style={{ marginTop: 10 }}><summary>История штрафов ({fineHistory.length})</summary><div className="ntv2-list">{fineHistory.slice().reverse().map((h, i) => <div className="ntv2-list-row" key={`${h.created_at_ts || h.at || i}-${i}`}><span>{h.action || h.event}</span><span className="ntv2-mono">{h.fine_id || "—"}</span><span>{h.source_name || h.source || "—"}</span><span className="ntv2-hint">{h.amount ?? "—"} · {h.place || h.reason || ""}</span></div>)}</div></details>
        </div>
      ) : null}

      {/* Достижения */}
      {hasPerm("achievement.view_player_progress") ? (
        <AchievementsPanel gameId={gameId} guarded={guarded} hasPerm={hasPerm} />
      ) : null}

      {/* Danger zone */}
      {(hasPerm("players.reset") || hasPerm("players.delete")) ? (
        <div className="ntv2-panel ntv2-danger-zone">
          <h3>⚠️ Опасная зона</h3>
          <div className="ntv2-form-row">
            {hasPerm("players.reset") ? (
              <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => setConfirm({
                title: "Сбросить прогресс игрока?",
                body: <p>Уровень, опыт, инвентарь, навыки и характеристики <b>{player.name}</b> будут сброшены к началу. Личность (имя/раса/привязки) сохранится. Делается бэкап.</p>,
                confirmLabel: "Сбросить прогресс",
                dangerous: true,
                run: async (reason) => { await guarded(() => resetPlayer(gameId, reason), "Прогресс игрока сброшен."); await load(); },
              })}>Сбросить прогресс</button>
            ) : null}
            {hasPerm("players.delete") ? (
              <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => setConfirm({
                title: "Удалить игрока полностью?",
                body: <p>Профиль <b>{player.name}</b> ({player.game_id}) будет удалён без возможности восстановления вместе с привязками Telegram/VK и именем. Игрок начнёт регистрацию с нуля.</p>,
                confirmLabel: "Удалить навсегда",
                dangerous: true,
                run: async (reason) => { await guarded(() => deletePlayer(gameId, reason), "Игрок удалён."); onDeleted?.(); },
              })}>Удалить игрока</button>
            ) : null}
          </div>
        </div>
      ) : null}

      <ConfirmModal
        open={Boolean(confirm)}
        title={confirm?.title}
        body={confirm?.body}
        confirmLabel={confirm?.confirmLabel || "Подтвердить"}
        dangerous={confirm?.dangerous}
        requireReason
        onConfirm={async (reason) => { await confirm.run(reason); setConfirm(null); }}
        onCancel={() => setConfirm(null)}
      />
    </section>
  );
}
