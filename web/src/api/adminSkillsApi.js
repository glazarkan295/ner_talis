// Admin V2 Skill Constructor API client (authoring skill definitions). Reuses V2 session.
import { requestAdminJson } from "./adminApi.js";

const t = () => Date.now();
const post = (url, body) => requestAdminJson(url, { method: "POST", body: JSON.stringify(body || {}) });
const base = "/api/admin/v2/skills";

export const fetchSkillMeta = () => requestAdminJson(`${base}/meta?_=${t()}`);
export const fetchSkills = (status = "") => requestAdminJson(`${base}?${new URLSearchParams(status ? { status } : {}).toString()}&_=${t()}`);
export const fetchSkill = (id) => requestAdminJson(`${base}/${encodeURIComponent(id)}?_=${t()}`);
export const createSkill = (id, data, reason) => post(base, { id, data, reason });
export const updateSkill = (id, data, reason) => requestAdminJson(`${base}/${encodeURIComponent(id)}`, { method: "PUT", body: JSON.stringify({ data, reason }) });
export const validateSkill = (id, reason) => post(`${base}/${encodeURIComponent(id)}/validate`, { reason });
export const skillLifecycle = (id, verb, reason) => post(`${base}/${encodeURIComponent(id)}/${verb}`, { reason });
export const deleteSkill = (id, confirm, reason) => requestAdminJson(`${base}/${encodeURIComponent(id)}`, { method: "DELETE", body: JSON.stringify({ confirm, reason }) });
export const importSkills = (overwrite, reason) => post(`${base}/import`, { overwrite, reason });
