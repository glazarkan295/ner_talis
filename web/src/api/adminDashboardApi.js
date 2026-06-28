// Admin V2 dashboard API client (ТЗ 11 §16).
import { requestAdminJson } from "./adminApi.js";

export const fetchDashboard = () => requestAdminJson(`/api/admin/v2/dashboard?_=${Date.now()}`);
