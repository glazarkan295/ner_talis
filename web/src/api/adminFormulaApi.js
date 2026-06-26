// Admin V2 Formula constructor API client (ТЗ 13 §2).
import { requestAdminJson } from "./adminApi.js";

const t = () => Date.now();
const base = "/api/admin/v2/formulas";
const post = (url, body) => requestAdminJson(url, { method: "POST", body: JSON.stringify(body || {}) });

export const fetchFormulaMeta = () => requestAdminJson(`${base}/meta?_=${t()}`);
export const fetchFormulas = (status = "") => requestAdminJson(`${base}?${new URLSearchParams(status ? { status } : {}).toString()}&_=${t()}`);
export const fetchFormula = (id) => requestAdminJson(`${base}/${encodeURIComponent(id)}?_=${t()}`);
export const createFormula = (id, data, reason) => post(base, { id, data, reason });
export const updateFormula = (id, data, reason) => requestAdminJson(`${base}/${encodeURIComponent(id)}`, { method: "PUT", body: JSON.stringify({ data, reason }) });
export const validateFormula = (id, reason) => post(`${base}/${encodeURIComponent(id)}/validate`, { reason });
export const formulaLifecycle = (id, verb, reason) => post(`${base}/${encodeURIComponent(id)}/${verb}`, { reason });
export const deleteFormula = (id, confirm, reason) => requestAdminJson(`${base}/${encodeURIComponent(id)}`, { method: "DELETE", body: JSON.stringify({ confirm, reason }) });
export const testFormula = (id, values) => post(`${base}/${encodeURIComponent(id)}/test`, { values });
export const evaluateFormula = (data, values) => post(`${base}/evaluate`, { data, values });
export const fetchFormulaWhereUsed = (id) => requestAdminJson(`${base}/${encodeURIComponent(id)}/where-used?_=${t()}`);
