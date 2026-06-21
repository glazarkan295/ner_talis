// Admin V2 Fine Constructor API client (authoring fine TYPES). Reuses V2 session.
import { requestAdminJson } from "./adminApi.js";

const t = () => Date.now();
const post = (url, body) => requestAdminJson(url, { method: "POST", body: JSON.stringify(body || {}) });
const base = "/api/admin/v2/fines";

export const fetchFineMeta = () => requestAdminJson(`${base}/meta?_=${t()}`);
export const fetchFines = (status = "") => requestAdminJson(`${base}?${new URLSearchParams(status ? { status } : {}).toString()}&_=${t()}`);
export const fetchFine = (id) => requestAdminJson(`${base}/${encodeURIComponent(id)}?_=${t()}`);
export const createFine = (id, data, reason) => post(base, { id, data, reason });
export const updateFine = (id, data, reason) => requestAdminJson(`${base}/${encodeURIComponent(id)}`, { method: "PUT", body: JSON.stringify({ data, reason }) });
export const validateFine = (id, reason) => post(`${base}/${encodeURIComponent(id)}/validate`, { reason });
export const fineLifecycle = (id, verb, reason) => post(`${base}/${encodeURIComponent(id)}/${verb}`, { reason });
export const deleteFine = (id, confirm, reason) => requestAdminJson(`${base}/${encodeURIComponent(id)}`, { method: "DELETE", body: JSON.stringify({ confirm, reason }) });
