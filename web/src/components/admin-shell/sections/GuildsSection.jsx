import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  createGuild,
  fetchGuild,
  fetchGuildMeta,
  fetchGuilds,
  guildAddMember,
  guildLifecycle,
  guildRemoveMember,
  guildSetRole,
  updateGuild,
} from "../../../api/adminCommunityApi.js";
import { ConfirmModal } from "../ConfirmModal.jsx";
import { SearchBox, NoResults, filterEntities } from "../SearchFilter.jsx";

const STATUS_TONE = { active: "ntv2-badge-owner", disbanded: "ntv2-badge-danger", frozen: "ntv2-badge-error" };

const EMPTY_GUILD = {
  name: "", guild_type: "player", short_description: "", description: "",
  emblem: "", founder: "", leader: "", min_level: 1, max_members: 50, members: [],
};

function Field({ label, children }) {
  return <label className="ntv2-field"><span>{label}</span>{children}</label>;
}

export function GuildsSection({ guarded, hasPerm }) {
  const [meta, setMeta] = useState(null);
  const [items, setItems] = useState([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState(null);
  const [confirm, setConfirm] = useState(null);
  const [newMember, setNewMember] = useState({ user_id: "", role: "newbie" });

  const can = useMemo(() => ({
    create: hasPerm("guild.create"), edit: hasPerm("guild.edit"),
    disable: hasPerm("guild.disable"), members: hasPerm("guild.manage_members"),
  }), [hasPerm]);

  const load = useCallback(async () => {
    const payload = await guarded(() => fetchGuilds(statusFilter));
    if (payload) setItems(payload.items || []);
  }, [guarded, statusFilter]);

  useEffect(() => { (async () => { const m = await guarded(() => fetchGuildMeta()); if (m) setMeta(m); })(); }, [guarded]);
  useEffect(() => { load(); }, [load]);

  const statuses = meta?.statuses || [];
  const statusLabel = (v) => statuses.find((s) => s.value === v)?.label || v;

  async function openItem(id) {
    const payload = await guarded(() => fetchGuild(id));
    if (payload?.item) setEditing({ id, data: { ...EMPTY_GUILD, ...(payload.item.data || {}) }, status: payload.item.status, validation: payload.validation, isNew: false });
  }
  function startCreate() { setEditing({ id: "", data: { ...EMPTY_GUILD }, status: "draft", validation: null, isNew: true }); }

  async function save() {
    const e = editing;
    if (e.isNew) {
      const payload = await guarded(() => createGuild(e.id.trim(), e.data, ""), "Гильдия создана.");
      if (payload?.item) await openItem(e.id.trim());
    } else {
      await guarded(() => updateGuild(e.id, e.data, ""), "Сохранено.");
      await openItem(e.id);
    }
    await load();
  }

  async function refreshEditing() { await load(); if (editing) await openItem(editing.id); }

  if (!meta) return <section className="ntv2-section"><h2>Гильдии</h2><p className="ntv2-hint">Загрузка…</p></section>;

  if (editing) {
    const d = editing.data;
    const set = (k, v) => setEditing({ ...editing, data: { ...d, [k]: v } });
    const members = Array.isArray(d.members) ? d.members : [];
    const disabled = !(editing.isNew ? can.create : can.edit);
    return (
      <section className="ntv2-section">
        <div className="ntv2-card-head">
          <button type="button" className="ntv2-btn" onClick={() => setEditing(null)}>← К списку</button>
          <h2>{editing.isNew ? "Новая гильдия" : d.name || editing.id}</h2>
          {!editing.isNew ? <span className={`ntv2-badge ${STATUS_TONE[editing.status] || ""}`}>{statusLabel(editing.status)}</span> : null}
        </div>
        {editing.isNew ? <Field label="ID (латиница)"><input value={editing.id} onChange={(e) => setEditing({ ...editing, id: e.target.value })} /></Field> : <p className="ntv2-hint ntv2-mono">{editing.id}</p>}

        <div className="ntv2-world-form">
          <div className="ntv2-form-row">
            <Field label="Название"><input value={d.name} disabled={disabled} onChange={(e) => set("name", e.target.value)} /></Field>
            <Field label="Тип"><select value={d.guild_type} disabled={disabled} onChange={(e) => set("guild_type", e.target.value)}>{(meta.types || []).map((x) => <option key={x} value={x}>{x}</option>)}</select></Field>
          </div>
          <div className="ntv2-form-row">
            <Field label="Основатель"><input value={d.founder} disabled={disabled} onChange={(e) => set("founder", e.target.value)} /></Field>
            <Field label="Лидер"><input value={d.leader} disabled={disabled} onChange={(e) => set("leader", e.target.value)} /></Field>
            <Field label="Мин. уровень"><input type="number" value={d.min_level} disabled={disabled} onChange={(e) => set("min_level", e.target.value)} /></Field>
            <Field label="Макс. участников"><input type="number" value={d.max_members} disabled={disabled} onChange={(e) => set("max_members", e.target.value)} /></Field>
          </div>
          <Field label="Краткое описание"><textarea rows={2} value={d.short_description} disabled={disabled} onChange={(e) => set("short_description", e.target.value)} /></Field>
          <Field label="Полное описание"><textarea rows={3} value={d.description} disabled={disabled} onChange={(e) => set("description", e.target.value)} /></Field>
          <Field label="Эмблема (URL)"><input value={d.emblem} disabled={disabled} onChange={(e) => set("emblem", e.target.value)} /></Field>
        </div>

        {editing.validation && !editing.validation.ok ? (
          <div className="ntv2-panel ntv2-danger-zone">
            <h4 className="ntv2-subhead">❌ Проверка не пройдена</h4>
            {editing.validation.errors.map((e, i) => <div className="ntv2-error" key={i}>{e}</div>)}
          </div>
        ) : null}

        {!editing.isNew && can.members ? (
          <div className="ntv2-panel">
            <h3>Участники ({members.length})</h3>
            <div className="ntv2-list">
              {members.map((m) => (
                <div className="ntv2-list-row" key={m.user_id}>
                  <span className="ntv2-mono">{m.user_id}</span>
                  <select value={m.role} onChange={(e) => guarded(() => guildSetRole(editing.id, m.user_id, e.target.value, "смена роли"), "Роль изменена.").then(refreshEditing)}>
                    {(meta.roles || []).map((r) => <option key={r} value={r}>{r}</option>)}
                  </select>
                  <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => guarded(() => guildRemoveMember(editing.id, m.user_id, "исключён"), "Участник исключён.").then(refreshEditing)}>Исключить</button>
                </div>
              ))}
            </div>
            <div className="ntv2-form-row" style={{ marginTop: 10 }}>
              <input placeholder="game_id игрока" value={newMember.user_id} onChange={(e) => setNewMember({ ...newMember, user_id: e.target.value })} />
              <select value={newMember.role} onChange={(e) => setNewMember({ ...newMember, role: e.target.value })}>{(meta.roles || []).map((r) => <option key={r} value={r}>{r}</option>)}</select>
              <button type="button" className="ntv2-btn" disabled={!newMember.user_id.trim()} onClick={() => guarded(() => guildAddMember(editing.id, newMember.user_id.trim(), newMember.role, "добавлен"), "Участник добавлен.").then(() => { setNewMember({ user_id: "", role: "newbie" }); refreshEditing(); })}>Добавить</button>
            </div>
          </div>
        ) : null}

        <div className="ntv2-form-row" style={{ marginTop: 14 }}>
          {(editing.isNew ? can.create : can.edit) ? <button type="button" className="ntv2-btn ntv2-btn-primary" disabled={editing.isNew && !editing.id.trim()} onClick={save}>{editing.isNew ? "Создать" : "Сохранить"}</button> : null}
          {!editing.isNew && can.edit && editing.status !== "active" ? <button type="button" className="ntv2-btn" onClick={() => guarded(() => guildLifecycle(editing.id, "activate", "активация"), "Гильдия активна.").then(refreshEditing)}>Активировать</button> : null}
          {!editing.isNew && can.edit && editing.status === "active" ? <button type="button" className="ntv2-btn" onClick={() => guarded(() => guildLifecycle(editing.id, "freeze", "заморозка"), "Заморожена.").then(refreshEditing)}>Заморозить</button> : null}
          {!editing.isNew && can.disable ? (
            <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => setConfirm({
              title: "Распустить гильдию?", dangerous: true, confirmLabel: "Распустить",
              body: <p>Гильдия <b>{d.name}</b> будет распущена.</p>,
              run: async (reason) => { await guarded(() => guildLifecycle(editing.id, "disband", reason), "Гильдия распущена."); await refreshEditing(); },
            })}>Распустить</button>
          ) : null}
          {!editing.isNew && can.disable ? (
            <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => setConfirm({
              title: "В архив?", dangerous: true, confirmLabel: "В архив",
              body: <p>Гильдия уйдёт в архив.</p>,
              run: async (reason) => { await guarded(() => guildLifecycle(editing.id, "archive", reason), "В архиве."); setEditing(null); await load(); },
            })}>В архив</button>
          ) : null}
        </div>

        <ConfirmModal open={Boolean(confirm)} title={confirm?.title} body={confirm?.body} dangerous={confirm?.dangerous} confirmLabel={confirm?.confirmLabel} requireReason
          onConfirm={async (reason) => { await confirm.run(reason); setConfirm(null); }} onCancel={() => setConfirm(null)} />
      </section>
    );
  }

  return (
    <section className="ntv2-section">
      <h2>Гильдии</h2>
      <div className="ntv2-filters">
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="">Все статусы</option>
          {statuses.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
        </select>
        {can.create ? <button type="button" className="ntv2-btn ntv2-btn-primary" onClick={startCreate}>＋ Новая гильдия</button> : null}
        <SearchBox value={query} onChange={setQuery} />
      </div>
      {!items.length ? <p className="ntv2-hint">Гильдий нет.</p> : null}
      <NoResults query={items.length ? query : ""} />
      <div className="ntv2-list">
        {filterEntities(items, query).map((item) => (
          <button key={item.id} type="button" className="ntv2-list-row ntv2-player-row" onClick={() => openItem(item.id)}>
            <b>{item.data?.name || item.id}</b>
            <span className="ntv2-mono">{item.id}</span>
            <span className={`ntv2-badge ${STATUS_TONE[item.status] || ""}`}>{statusLabel(item.status)}</span>
            <span className="ntv2-hint">{(item.data?.members || []).length} уч.</span>
          </button>
        ))}
      </div>
    </section>
  );
}
