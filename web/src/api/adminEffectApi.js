// Admin V2 Effect Constructor API client. Reuses the shared V2 session.
import { requestAdminJson } from "./adminApi.js";

const t = () => Date.now();
const post = (url, body) => requestAdminJson(url, { method: "POST", body: JSON.stringify(body || {}) });
const base = "/api/admin/v2/effects";

export const fetchEffectMeta = () => requestAdminJson(`${base}/meta?_=${t()}`);
export const fetchEffects = (status = "") => requestAdminJson(`${base}?${new URLSearchParams(status ? { status } : {}).toString()}&_=${t()}`);
export const fetchEffect = (id) => requestAdminJson(`${base}/${encodeURIComponent(id)}?_=${t()}`);
export const createEffect = (id, data, reason) => post(base, { id, data, reason });
export const updateEffect = (id, data, reason) => requestAdminJson(`${base}/${encodeURIComponent(id)}`, { method: "PUT", body: JSON.stringify({ data, reason }) });
export const validateEffect = (id, reason) => post(`${base}/${encodeURIComponent(id)}/validate`, { reason });
export const effectLifecycle = (id, verb, reason) => post(`${base}/${encodeURIComponent(id)}/${verb}`, { reason });
export const deleteEffect = (id, confirm, reason) => requestAdminJson(`${base}/${encodeURIComponent(id)}`, { method: "DELETE", body: JSON.stringify({ confirm, reason }) });
export const fetchEffectUsage = (id) => requestAdminJson(`${base}/${encodeURIComponent(id)}/usage?_=${t()}`);
export const importExistingEffects = (overwrite, reason) => post(`${base}/import`, { overwrite, reason });
