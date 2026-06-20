// Admin V2 Achievements API client. Reuses the shared V2 session.
import { requestAdminJson } from "./adminApi.js";

const t = () => Date.now();
const post = (url, body) => requestAdminJson(url, { method: "POST", body: JSON.stringify(body || {}) });
const put = (url, body) => requestAdminJson(url, { method: "PUT", body: JSON.stringify(body || {}) });
const base = "/api/admin/v2/achievements";

export const fetchAchievementMeta = () => requestAdminJson(`${base}/meta?_=${t()}`);
export const fetchAchievements = (status = "") => requestAdminJson(`${base}?${new URLSearchParams(status ? { status } : {}).toString()}&_=${t()}`);
export const fetchAchievement = (id) => requestAdminJson(`${base}/${encodeURIComponent(id)}?_=${t()}`);
export const createAchievement = (id, data, reason) => post(base, { id, data, reason });
export const updateAchievement = (id, data, reason) => put(`${base}/${encodeURIComponent(id)}`, { data, reason });
export const achievementLifecycle = (id, verb, reason) => post(`${base}/${encodeURIComponent(id)}/${verb}`, { reason });

export const fetchPlayerAchievements = (gameId) => requestAdminJson(`${base}/players/${encodeURIComponent(gameId)}?_=${t()}`);
export const grantAchievementToPlayer = (achId, gameId, reason) => post(`${base}/${encodeURIComponent(achId)}/grant`, { game_id: gameId, reason });
export const revokeAchievementFromPlayer = (achId, gameId, reason) => post(`${base}/${encodeURIComponent(achId)}/revoke`, { game_id: gameId, reason });

export const fetchAchievementCategories = () => requestAdminJson(`${base}/categories?_=${t()}`);
export const createAchievementCategory = (id, data, reason) => post(`${base}/categories`, { id, data, reason });
export const updateAchievementCategory = (id, data, reason) => put(`${base}/categories/${encodeURIComponent(id)}`, { data, reason });
