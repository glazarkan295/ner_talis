// Admin V2 Tavern constructor API client (ТЗ таверны).
import { requestAdminJson } from "./adminApi.js";

const t = () => Date.now();
const base = "/api/admin/v2/taverns";
const post = (url, body) => requestAdminJson(url, { method: "POST", body: JSON.stringify(body || {}) });

export const fetchTavernMeta = () => requestAdminJson(`${base}/meta?_=${t()}`);
export const fetchTaverns = (status = "") => requestAdminJson(`${base}?${new URLSearchParams(status ? { status } : {}).toString()}&_=${t()}`);
export const fetchTavern = (id) => requestAdminJson(`${base}/${encodeURIComponent(id)}?_=${t()}`);
export const createTavern = (id, data, reason) => post(base, { id, data, reason });
export const updateTavern = (id, data, reason) => requestAdminJson(`${base}/${encodeURIComponent(id)}`, { method: "PUT", body: JSON.stringify({ data, reason }) });
export const tavernLifecycle = (id, verb, reason) => post(`${base}/${encodeURIComponent(id)}/${verb}`, { reason });
export const previewTavern = (id, mock) => post(`${base}/${encodeURIComponent(id)}/preview`, { mock });
export const fetchTavernUsage = (id) => requestAdminJson(`${base}/${encodeURIComponent(id)}/usage?_=${t()}`);
