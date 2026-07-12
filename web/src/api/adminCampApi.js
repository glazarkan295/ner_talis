// Admin V2 Camp constructor API client (доп. ТЗ §4). Reuses shared V2 session.
import { requestAdminJson } from "./adminApi.js";

const t = () => Date.now();
const post = (url, body) => requestAdminJson(url, { method: "POST", body: JSON.stringify(body || {}) });
const base = "/api/admin/v2/camps";

export const fetchCampMeta = () => requestAdminJson(`${base}/meta?_=${t()}`);
export const fetchCamps = (status = "") => requestAdminJson(`${base}?${new URLSearchParams(status ? { status } : {}).toString()}&_=${t()}`);
export const fetchCamp = (id) => requestAdminJson(`${base}/${encodeURIComponent(id)}?_=${t()}`);
export const fetchCampUsage = (id) => requestAdminJson(`${base}/${encodeURIComponent(id)}/usage?_=${t()}`);
export const createCamp = (id, data, reason) => post(base, { id, data, reason });
export const updateCamp = (id, data, reason) => requestAdminJson(`${base}/${encodeURIComponent(id)}`, { method: "PUT", body: JSON.stringify({ data, reason }) });
export const validateCamp = (id, reason) => post(`${base}/${encodeURIComponent(id)}/validate`, { reason });
export const campLifecycle = (id, verb, reason) => post(`${base}/${encodeURIComponent(id)}/${verb}`, { reason });
export const deleteCamp = (id, confirm, reason) => requestAdminJson(`${base}/${encodeURIComponent(id)}`, { method: "DELETE", body: JSON.stringify({ confirm, reason }) });
export const importCamps = (mode, reason) => post(`${base}/import`, { mode, reason });
