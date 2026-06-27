// Global admin search API client (ТЗ 11 §4.2).
import { requestAdminJson } from "./adminApi.js";

export const globalSearch = (q, limit = 8) =>
  requestAdminJson(`/api/admin/v2/search?${new URLSearchParams({ q, limit: String(limit) }).toString()}&_=${Date.now()}`);
