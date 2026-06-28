// Общий API-клиент для каталог-конструкторов на EntityStore (черты/благословения/
// фазы). base — сегмент пути после /api/admin/v2/ (traits/blessings/phases).
import { requestAdminJson } from "./adminApi.js";

const t = () => Date.now();
const post = (base, path, body) => requestAdminJson(`/api/admin/v2/${base}${path}`, { method: "POST", body: JSON.stringify(body || {}) });

export const fetchLibMeta = (base) => requestAdminJson(`/api/admin/v2/${base}/meta?_=${t()}`);
export const fetchLibList = (base, status = "") => requestAdminJson(`/api/admin/v2/${base}?${new URLSearchParams(status ? { status } : {}).toString()}&_=${t()}`);
export const fetchLibItem = (base, id) => requestAdminJson(`/api/admin/v2/${base}/${encodeURIComponent(id)}?_=${t()}`);
export const createLibItem = (base, id, data, reason) => post(base, "", { id, data, reason });
export const updateLibItem = (base, id, data, reason) => requestAdminJson(`/api/admin/v2/${base}/${encodeURIComponent(id)}`, { method: "PUT", body: JSON.stringify({ data, reason }) });
export const validateLibItem = (base, id, reason) => post(base, `/${encodeURIComponent(id)}/validate`, { reason });
export const libLifecycle = (base, id, verb, reason) => post(base, `/${encodeURIComponent(id)}/${verb}`, { reason });
export const deleteLibItem = (base, id, confirm, reason) => requestAdminJson(`/api/admin/v2/${base}/${encodeURIComponent(id)}`, { method: "DELETE", body: JSON.stringify({ confirm, reason }) });
export const importLib = (base, mode, reason) => post(base, "/import", { mode, reason });
