// Admin V2 Workshop message constructor API client (ТЗ 14).
import { requestAdminJson } from "./adminApi.js";

const t = () => Date.now();
const base = "/api/admin/v2/workshop-messages";
const post = (url, body) => requestAdminJson(url, { method: "POST", body: JSON.stringify(body || {}) });

export const fetchWmMeta = () => requestAdminJson(`${base}/meta?_=${t()}`);
export const fetchWmList = (status = "") => requestAdminJson(`${base}?${new URLSearchParams(status ? { status } : {}).toString()}&_=${t()}`);
export const fetchWm = (id) => requestAdminJson(`${base}/${encodeURIComponent(id)}?_=${t()}`);
export const createWm = (id, data, reason) => post(base, { id, data, reason });
export const updateWm = (id, data, reason) => requestAdminJson(`${base}/${encodeURIComponent(id)}`, { method: "PUT", body: JSON.stringify({ data, reason }) });
export const wmLifecycle = (id, verb, reason) => post(`${base}/${encodeURIComponent(id)}/${verb}`, { reason });
export const previewWmAdhoc = (data, state) => post(`${base}/preview`, { data, state });
