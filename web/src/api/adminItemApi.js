// Admin V2 Item Constructor API client. Reuses the shared V2 session.
import { requestAdminJson } from "./adminApi.js";

const t = () => Date.now();
const post = (url, body) => requestAdminJson(url, { method: "POST", body: JSON.stringify(body || {}) });
const base = "/api/admin/v2/items";

export const fetchItemMeta = () => requestAdminJson(`${base}/meta?_=${t()}`);
export const fetchItems = (status = "") => requestAdminJson(`${base}?${new URLSearchParams(status ? { status } : {}).toString()}&_=${t()}`);
export const fetchItem = (id) => requestAdminJson(`${base}/${encodeURIComponent(id)}?_=${t()}`);
export const fetchItemUsage = (id) => requestAdminJson(`${base}/${encodeURIComponent(id)}/usage?_=${t()}`);
export const createItem = (id, data, reason) => post(base, { id, data, reason });
export const updateItem = (id, data, reason) => requestAdminJson(`${base}/${encodeURIComponent(id)}`, { method: "PUT", body: JSON.stringify({ data, reason }) });
export const validateItem = (id, reason) => post(`${base}/${encodeURIComponent(id)}/validate`, { reason });
export const itemLifecycle = (id, verb, reason) => post(`${base}/${encodeURIComponent(id)}/${verb}`, { reason });
export const hardDeleteItem = (id, confirm, reason) => requestAdminJson(`${base}/${encodeURIComponent(id)}`, { method: "DELETE", body: JSON.stringify({ confirm, reason }) });
