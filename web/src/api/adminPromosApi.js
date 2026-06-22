// Admin V2 Promo codes + Broadcasts API client (ТЗ §9). Reuses V2 session.
import { requestAdminJson } from "./adminApi.js";

const t = () => Date.now();
const post = (url, body) => requestAdminJson(url, { method: "POST", body: JSON.stringify(body || {}) });
const base = "/api/admin/v2";

export const fetchPromosMeta = () => requestAdminJson(`${base}/promos/meta?_=${t()}`);
export const fetchPromos = () => requestAdminJson(`${base}/promos?_=${t()}`);
export const createPromo = (code, uses_left, duration, rewards, reason) =>
  post(`${base}/promos`, { code, uses_left, duration, rewards, reason });
export const deletePromo = (code) =>
  requestAdminJson(`${base}/promos?code=${encodeURIComponent(code)}`, { method: "DELETE" });

export const previewBroadcast = (audience, specific_players) =>
  post(`${base}/broadcast/preview`, { audience, specific_players });
export const sendBroadcast = (audience, message, specific_players, reason) =>
  post(`${base}/broadcast`, { audience, message, specific_players, reason });
