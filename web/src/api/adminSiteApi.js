// Admin V2 Site Constructor API client. Reuses the shared V2 session.
import { requestAdminJson } from "./adminApi.js";

const t = () => Date.now();
const post = (url, body) => requestAdminJson(url, { method: "POST", body: JSON.stringify(body || {}) });
const base = "/api/admin/v2/site";

export const fetchSiteMeta = () => requestAdminJson(`${base}/meta?_=${t()}`);
export const fetchSiteItems = (kind, status = "") => requestAdminJson(`${base}/${encodeURIComponent(kind)}?${new URLSearchParams(status ? { status } : {}).toString()}&_=${t()}`);
export const fetchSiteItem = (kind, id) => requestAdminJson(`${base}/${encodeURIComponent(kind)}/${encodeURIComponent(id)}?_=${t()}`);
export const createSiteItem = (kind, id, data, reason) => post(`${base}/${encodeURIComponent(kind)}`, { id, data, reason });
export const updateSiteItem = (kind, id, data, reason) => requestAdminJson(`${base}/${encodeURIComponent(kind)}/${encodeURIComponent(id)}`, { method: "PUT", body: JSON.stringify({ data, reason }) });
export const validateSiteItem = (kind, id, reason) => post(`${base}/${encodeURIComponent(kind)}/${encodeURIComponent(id)}/validate`, { reason });
export const siteLifecycle = (kind, id, verb, reason) => post(`${base}/${encodeURIComponent(kind)}/${encodeURIComponent(id)}/${verb}`, { reason });
