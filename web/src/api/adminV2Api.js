// Admin Panel V2 API client. Reuses the V1 session-token plumbing
// (sessionStorage + Bearer header + activation-token exchange) from adminApi.js
// so both panels share one login. All calls hit the RBAC-aware /api/admin/v2/*
// router; permission errors surface as thrown Error(detail).
import { getAdminSessionToken, requestAdminJson } from "./adminApi.js";

export function isAdminPanelV2Path() {
  return window.location.pathname.startsWith("/admin_panel_v2");
}

export { getAdminSessionToken };

export function fetchMe() {
  return requestAdminJson(`/api/admin/v2/me?_=${Date.now()}`);
}

export function fetchAudit(filters = {}) {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value === "" || value === null || value === undefined || value === false) return;
    params.set(key, String(value));
  });
  params.set("_", String(Date.now()));
  return requestAdminJson(`/api/admin/v2/audit?${params.toString()}`);
}

export function fetchRoles() {
  return requestAdminJson(`/api/admin/v2/roles?_=${Date.now()}`);
}

export function assignRole(platform, adminUserId, role, reason) {
  return requestAdminJson("/api/admin/v2/roles", {
    method: "POST",
    body: JSON.stringify({ platform, admin_user_id: adminUserId, role, reason }),
  });
}

export function clearRole(platform, adminUserId) {
  const params = new URLSearchParams({ platform, admin_user_id: adminUserId });
  return requestAdminJson(`/api/admin/v2/roles?${params.toString()}`, { method: "DELETE" });
}

export function fetchSessions() {
  return requestAdminJson(`/api/admin/v2/sessions?_=${Date.now()}`);
}

export function revokeSession(id, reason) {
  return requestAdminJson("/api/admin/v2/sessions/revoke", {
    method: "POST",
    body: JSON.stringify({ id, reason }),
  });
}
