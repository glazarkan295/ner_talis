import React, { useCallback, useEffect, useState } from "react";
import { fetchPlayers } from "../../../api/adminV2Api.js";
import { PlayerCard } from "./PlayerCard.jsx";

export function PlayersSection({ guarded, hasPerm }) {
  const [query, setQuery] = useState("");
  const [players, setPlayers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState(null); // game_id

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const payload = await guarded(() => fetchPlayers(query));
      if (payload) setPlayers(payload.players || []);
    } finally {
      setLoading(false);
    }
  }, [guarded, query]);

  // Debounce search so each keystroke doesn't hit the backend.
  useEffect(() => {
    const id = window.setTimeout(load, 250);
    return () => window.clearTimeout(id);
  }, [load]);

  if (selected) {
    return (
      <PlayerCard
        gameId={selected}
        guarded={guarded}
        hasPerm={hasPerm}
        onBack={() => { setSelected(null); load(); }}
        onDeleted={() => { setSelected(null); load(); }}
      />
    );
  }

  return (
    <section className="ntv2-section">
      <h2>Игроки</h2>
      <div className="ntv2-filters">
        <input
          placeholder="Поиск по нику, game_id, Telegram/VK id"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          style={{ minWidth: 320 }}
        />
      </div>
      {loading ? <p className="ntv2-hint">Загрузка…</p> : null}
      {!loading && !players.length ? <p className="ntv2-hint">Игроки не найдены.</p> : null}
      <div className="ntv2-list">
        {players.map((p) => (
          <button
            key={p.game_id}
            type="button"
            className="ntv2-list-row ntv2-player-row"
            onClick={() => setSelected(p.game_id)}
          >
            <b>{p.name || "без имени"}</b>
            <span className="ntv2-mono">{p.game_id}</span>
            <span className="ntv2-badge">ур. {p.level}</span>
            {p.last_activity ? <span className="ntv2-hint">активность {p.last_activity}</span> : null}
          </button>
        ))}
      </div>
    </section>
  );
}
