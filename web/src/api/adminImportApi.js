// Unified import-migration API client (full-import ТЗ §13 Этап 5).
import { requestAdminJson } from "./adminApi.js";

export const fetchImportMeta = () =>
  requestAdminJson(`/api/admin/v2/import/meta?_=${Date.now()}`);

export const runImportDryRun = (kinds, mode, reason = "") =>
  requestAdminJson("/api/admin/v2/import/dry-run", {
    method: "POST",
    body: JSON.stringify({ kinds: kinds || [], mode, reason }),
  });

export const runImport = (kinds, mode, reason = "") =>
  requestAdminJson("/api/admin/v2/import/run", {
    method: "POST",
    body: JSON.stringify({ kinds: kinds || [], mode, reason }),
  });

export const runImportCheck = (reason = "") =>
  requestAdminJson("/api/admin/v2/import/check", {
    method: "POST",
    body: JSON.stringify({ reason }),
  });

export const runImportRollback = (reason = "") =>
  requestAdminJson("/api/admin/v2/import/rollback", {
    method: "POST",
    body: JSON.stringify({ reason }),
  });

export const fetchImportReport = (format = "json") =>
  requestAdminJson(`/api/admin/v2/import/report?format=${format}&_=${Date.now()}`);

// Feature flags (use_v2_*) — постепенный переход игры на V2-данные (ТЗ §14).
export const fetchFeatureFlags = () =>
  requestAdminJson(`/api/admin/v2/feature-flags?_=${Date.now()}`);

export const setFeatureFlag = (name, enabled, reason = "") =>
  requestAdminJson("/api/admin/v2/feature-flags", {
    method: "PUT",
    body: JSON.stringify({ name, enabled, reason }),
  });
