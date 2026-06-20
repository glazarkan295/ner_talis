// Admin V2 Guilds + World Events API client. Reuses the shared V2 session.
import { requestAdminJson } from "./adminApi.js";

const t = () => Date.now();
const post = (url, body) => requestAdminJson(url, { method: "POST", body: JSON.stringify(body || {}) });

// ---- Guilds ----
export const fetchGuildMeta = () => requestAdminJson(`/api/admin/v2/guilds/meta?_=${t()}`);
export const fetchGuilds = (status = "") => requestAdminJson(`/api/admin/v2/guilds?${new URLSearchParams(status ? { status } : {}).toString()}&_=${t()}`);
export const fetchGuild = (id) => requestAdminJson(`/api/admin/v2/guilds/${encodeURIComponent(id)}?_=${t()}`);
export const createGuild = (id, data, reason) => post("/api/admin/v2/guilds", { id, data, reason });
export const updateGuild = (id, data, reason) => requestAdminJson(`/api/admin/v2/guilds/${encodeURIComponent(id)}`, { method: "PUT", body: JSON.stringify({ data, reason }) });
export const guildLifecycle = (id, verb, reason) => post(`/api/admin/v2/guilds/${encodeURIComponent(id)}/${verb}`, { reason });
export const guildAddMember = (id, user_id, role, reason) => post(`/api/admin/v2/guilds/${encodeURIComponent(id)}/members`, { user_id, role, reason });
export const guildSetRole = (id, user_id, role, reason) => post(`/api/admin/v2/guilds/${encodeURIComponent(id)}/members/set-role`, { user_id, role, reason });
export const guildRemoveMember = (id, user_id, reason) => post(`/api/admin/v2/guilds/${encodeURIComponent(id)}/members/remove`, { user_id, reason });

// ---- World events ----
export const fetchEventMeta = () => requestAdminJson(`/api/admin/v2/events/meta?_=${t()}`);
export const fetchEvents = (status = "") => requestAdminJson(`/api/admin/v2/events?${new URLSearchParams(status ? { status } : {}).toString()}&_=${t()}`);
export const fetchEvent = (id) => requestAdminJson(`/api/admin/v2/events/${encodeURIComponent(id)}?_=${t()}`);
export const createEvent = (id, data, reason) => post("/api/admin/v2/events", { id, data, reason });
export const updateEvent = (id, data, reason) => requestAdminJson(`/api/admin/v2/events/${encodeURIComponent(id)}`, { method: "PUT", body: JSON.stringify({ data, reason }) });
export const eventLifecycle = (id, verb, reason) => post(`/api/admin/v2/events/${encodeURIComponent(id)}/${verb}`, { reason });
