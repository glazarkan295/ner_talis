// Admin V2 Reputation constructor API client (item-reputation §3, эффекты §3).
import { requestAdminJson } from "./adminApi.js";

const t = () => Date.now();
const base = "/api/admin/v2/reputations";
const post = (url, body) => requestAdminJson(url, { method: "POST", body: JSON.stringify(body || {}) });

export const fetchReputationMeta = () => requestAdminJson(`${base}/meta?_=${t()}`);
export const fetchReputations = (status = "") => requestAdminJson(`${base}?${new URLSearchParams(status ? { status } : {}).toString()}&_=${t()}`);
export const fetchReputation = (id) => requestAdminJson(`${base}/${encodeURIComponent(id)}?_=${t()}`);
export const createReputation = (id, data, reason) => post(base, { id, data, reason });
export const updateReputation = (id, data, reason) => requestAdminJson(`${base}/${encodeURIComponent(id)}`, { method: "PUT", body: JSON.stringify({ data, reason }) });
export const reputationLifecycle = (id, verb, reason) => post(`${base}/${encodeURIComponent(id)}/${verb}`, { reason });
export const previewReputation = (id, value, delta) => post(`${base}/${encodeURIComponent(id)}/preview`, { value, delta });
