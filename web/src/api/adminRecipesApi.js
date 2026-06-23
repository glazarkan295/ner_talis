// Admin V2 Recipe (crafting) constructor API client. Reuses the shared V2 session.
import { requestAdminJson } from "./adminApi.js";

const t = () => Date.now();
const post = (url, body) => requestAdminJson(url, { method: "POST", body: JSON.stringify(body || {}) });
const base = "/api/admin/v2/recipes";

export const fetchRecipeMeta = () => requestAdminJson(`${base}/meta?_=${t()}`);
export const fetchRecipes = (status = "") => requestAdminJson(`${base}?${new URLSearchParams(status ? { status } : {}).toString()}&_=${t()}`);
export const fetchRecipe = (id) => requestAdminJson(`${base}/${encodeURIComponent(id)}?_=${t()}`);
export const createRecipe = (id, data, reason) => post(base, { id, data, reason });
export const updateRecipe = (id, data, reason) => requestAdminJson(`${base}/${encodeURIComponent(id)}`, { method: "PUT", body: JSON.stringify({ data, reason }) });
export const validateRecipe = (id, reason) => post(`${base}/${encodeURIComponent(id)}/validate`, { reason });
export const recipeLifecycle = (id, verb, reason) => post(`${base}/${encodeURIComponent(id)}/${verb}`, { reason });
export const deleteRecipe = (id, confirm, reason) => requestAdminJson(`${base}/${encodeURIComponent(id)}`, { method: "DELETE", body: JSON.stringify({ confirm, reason }) });
export const importRecipes = (mode, reason) => post(`${base}/import`, { mode, reason });
export const fetchRecipeUsage = (id) => requestAdminJson(`${base}/${encodeURIComponent(id)}/usage?_=${t()}`);
