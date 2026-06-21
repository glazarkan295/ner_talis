// Admin V2 outgoing message queue API client. Reuses the shared V2 session.
import { requestAdminJson } from "./adminApi.js";

const t = () => Date.now();
const post = (url, body) => requestAdminJson(url, { method: "POST", body: JSON.stringify(body || {}) });
const base = "/api/admin/v2/messages";

export const fetchMessagesMeta = () => requestAdminJson(`${base}/meta?_=${t()}`);
export const fetchMessagesStats = () => requestAdminJson(`${base}/stats?_=${t()}`);
export const fetchMessages = (filters = {}) => {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([k, v]) => { if (v !== "" && v !== false && v != null) params.set(k, String(v)); });
  params.set("_", String(t()));
  return requestAdminJson(`${base}?${params.toString()}`);
};
export const fetchPlayerMessages = (gameId) => requestAdminJson(`${base}/players/${encodeURIComponent(gameId)}?_=${t()}`);
export const sendDirectMessage = (gameId, text, priority, reason) => post(`${base}/send`, { game_id: gameId, text, priority, reason });
export const retryMessage = (id, reason) => post(`${base}/${encodeURIComponent(id)}/retry`, { reason });
export const cancelMessage = (id, reason) => post(`${base}/${encodeURIComponent(id)}/cancel`, { reason });
export const runDispatcher = (reason) => post(`${base}/dispatch`, { reason });
