// Admin V2 Profile Layout constructor API client (ТЗ §3). Reuses V2 session.
import { requestAdminJson } from "./adminApi.js";

const t = () => Date.now();
const post = (url, body) => requestAdminJson(url, { method: "POST", body: JSON.stringify(body || {}) });
const base = "/api/admin/v2/profile-layout";

export const fetchLayoutMeta = () => requestAdminJson(`${base}/meta?_=${t()}`);
export const fetchLayoutItems = (kind, status = "") => requestAdminJson(`${base}/${kind}?${new URLSearchParams(status ? { status } : {}).toString()}&_=${t()}`);
export const fetchLayoutItem = (kind, id) => requestAdminJson(`${base}/${kind}/${encodeURIComponent(id)}?_=${t()}`);
export const fetchLayoutWhereUsed = (kind, id) => requestAdminJson(`${base}/${kind}/${encodeURIComponent(id)}/where-used?_=${t()}`);
export const createLayoutItem = (kind, id, data, reason) => post(`${base}/${kind}`, { id, data, reason });
export const updateLayoutItem = (kind, id, data, reason) => requestAdminJson(`${base}/${kind}/${encodeURIComponent(id)}`, { method: "PUT", body: JSON.stringify({ data, reason }) });
export const validateLayoutItem = (kind, id, reason) => post(`${base}/${kind}/${encodeURIComponent(id)}/validate`, { reason });
export const layoutLifecycle = (kind, id, verb, reason) => post(`${base}/${kind}/${encodeURIComponent(id)}/${verb}`, { reason });
export const deleteLayoutItem = (kind, id, confirm, reason) => requestAdminJson(`${base}/${kind}/${encodeURIComponent(id)}`, { method: "DELETE", body: JSON.stringify({ confirm, reason }) });
