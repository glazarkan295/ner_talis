// Admin V2 City/Fortress constructor API client (ТЗ §4–§6). Reuses V2 session.
import { requestAdminJson } from "./adminApi.js";

const t = () => Date.now();
const post = (url, body) => requestAdminJson(url, { method: "POST", body: JSON.stringify(body || {}) });
const base = "/api/admin/v2/city";

export const fetchCityMeta = () => requestAdminJson(`${base}/meta?_=${t()}`);
export const fetchCityTree = () => requestAdminJson(`${base}/tree?_=${t()}`);
export const fetchCityItems = (kind, status = "") => requestAdminJson(`${base}/${kind}?${new URLSearchParams(status ? { status } : {}).toString()}&_=${t()}`);
export const fetchCityItem = (kind, id) => requestAdminJson(`${base}/${kind}/${encodeURIComponent(id)}?_=${t()}`);
export const fetchCityWhereUsed = (kind, id) => requestAdminJson(`${base}/${kind}/${encodeURIComponent(id)}/where-used?_=${t()}`);
export const fetchCityNodeRuntime = (id) => requestAdminJson(`${base}/node/${encodeURIComponent(id)}/runtime?_=${t()}`);
export const createCityItem = (kind, id, data, reason) => post(`${base}/${kind}`, { id, data, reason });
export const updateCityItem = (kind, id, data, reason) => requestAdminJson(`${base}/${kind}/${encodeURIComponent(id)}`, { method: "PUT", body: JSON.stringify({ data, reason }) });
export const validateCityItem = (kind, id, reason) => post(`${base}/${kind}/${encodeURIComponent(id)}/validate`, { reason });
export const cityLifecycle = (kind, id, verb, reason) => post(`${base}/${kind}/${encodeURIComponent(id)}/${verb}`, { reason });
export const deleteCityItem = (kind, id, confirm, reason) => requestAdminJson(`${base}/${kind}/${encodeURIComponent(id)}`, { method: "DELETE", body: JSON.stringify({ confirm, reason }) });
