// Admin V2 bot-text constructor API client (full-import ТЗ §5.18).
import { requestAdminJson } from "./adminApi.js";

const t = () => Date.now();
const base = "/api/admin/v2/texts";
const post = (url, body) => requestAdminJson(url, { method: "POST", body: JSON.stringify(body || {}) });

export const fetchTextMeta = () => requestAdminJson(`${base}/meta?_=${t()}`);
export const fetchTextList = (status = "") => requestAdminJson(`${base}?${new URLSearchParams(status ? { status } : {}).toString()}&_=${t()}`);
export const fetchText = (id) => requestAdminJson(`${base}/${encodeURIComponent(id)}?_=${t()}`);
export const createText = (id, data, reason) => post(base, { id, data, reason });
export const updateText = (id, data, reason) => requestAdminJson(`${base}/${encodeURIComponent(id)}`, { method: "PUT", body: JSON.stringify({ data, reason }) });
export const textLifecycle = (id, verb, reason) => post(`${base}/${encodeURIComponent(id)}/${verb}`, { reason });
export const previewText = (id, variables) => post(`${base}/${encodeURIComponent(id)}/preview`, { variables });
export const importTexts = (mode, reason) => post(`${base}/import`, { mode, reason });
