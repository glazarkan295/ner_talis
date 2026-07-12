// Admin V2 «Конструктор мира» API client. Generic over content `kind`
// (first kind: "location"). Reuses the shared V2 session plumbing.
import { requestAdminJson } from "./adminApi.js";

export function fetchWorldMeta() {
  return requestAdminJson(`/api/admin/v2/world/kinds?_=${Date.now()}`);
}

export function importExistingContent(kinds, overwrite, reason) {
  return requestAdminJson(`/api/admin/v2/world/import`, {
    method: "POST",
    body: JSON.stringify({ kinds: kinds || [], overwrite: Boolean(overwrite), reason: reason || "" }),
  });
}

export function fetchWorldItems(kind, status = "") {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  params.set("_", String(Date.now()));
  return requestAdminJson(`/api/admin/v2/world/${encodeURIComponent(kind)}?${params.toString()}`);
}

export function fetchWorldItem(kind, id) {
  return requestAdminJson(`/api/admin/v2/world/${encodeURIComponent(kind)}/${encodeURIComponent(id)}?_=${Date.now()}`);
}

export function fetchWorldUsage(kind, id) {
  return requestAdminJson(`/api/admin/v2/world/${encodeURIComponent(kind)}/${encodeURIComponent(id)}/usage?_=${Date.now()}`);
}

export function deleteWorldItem(kind, id, reason) {
  return requestAdminJson(`/api/admin/v2/world/${encodeURIComponent(kind)}/${encodeURIComponent(id)}`, {
    method: "DELETE",
    body: JSON.stringify({ confirm: id, reason: reason || "" }),
  });
}

export function createWorldItem(kind, id, data, reason) {
  return requestAdminJson(`/api/admin/v2/world/${encodeURIComponent(kind)}`, {
    method: "POST",
    body: JSON.stringify({ id, data, reason }),
  });
}

export function updateWorldItem(kind, id, data, reason) {
  return requestAdminJson(`/api/admin/v2/world/${encodeURIComponent(kind)}/${encodeURIComponent(id)}`, {
    method: "PUT",
    body: JSON.stringify({ data, reason }),
  });
}

export function setWorldStatus(kind, id, status, reason) {
  return requestAdminJson(`/api/admin/v2/world/${encodeURIComponent(kind)}/${encodeURIComponent(id)}/status`, {
    method: "POST",
    body: JSON.stringify({ status, reason }),
  });
}

export function validateWorldItem(kind, id) {
  return requestAdminJson(`/api/admin/v2/world/${encodeURIComponent(kind)}/${encodeURIComponent(id)}/validate`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}

function lifecycle(kind, id, verb, reason) {
  return requestAdminJson(`/api/admin/v2/world/${encodeURIComponent(kind)}/${encodeURIComponent(id)}/${verb}`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
}

export const publishWorldItem = (kind, id, reason) => lifecycle(kind, id, "publish", reason);
export const disableWorldItem = (kind, id, reason) => lifecycle(kind, id, "disable", reason);
export const archiveWorldItem = (kind, id, reason) => lifecycle(kind, id, "archive", reason);

// --- Версионирование (Этап 1): история/откат и draft-overlay ---------------
export function fetchWorldHistory(kind, id) {
  return requestAdminJson(`/api/admin/v2/world/${encodeURIComponent(kind)}/${encodeURIComponent(id)}/history?_=${Date.now()}`);
}

export function rollbackWorldItem(kind, id, version, reason) {
  return requestAdminJson(`/api/admin/v2/world/${encodeURIComponent(kind)}/${encodeURIComponent(id)}/rollback`, {
    method: "POST",
    body: JSON.stringify({ version, reason }),
  });
}

export function editWorldDraft(kind, id, data, reason) {
  return requestAdminJson(`/api/admin/v2/world/${encodeURIComponent(kind)}/${encodeURIComponent(id)}/draft`, {
    method: "PUT",
    body: JSON.stringify({ data, reason }),
  });
}

export const publishWorldDraft = (kind, id, reason) => lifecycle(kind, id, "publish-draft", reason);
export const discardWorldDraft = (kind, id, reason) => lifecycle(kind, id, "discard-draft", reason);

export function previewWorldItem(kind, id) {
  return requestAdminJson(`/api/admin/v2/world/${encodeURIComponent(kind)}/${encodeURIComponent(id)}/preview?_=${Date.now()}`);
}

export function testRunWorldItem(kind, id) {
  return requestAdminJson(`/api/admin/v2/world/${encodeURIComponent(kind)}/${encodeURIComponent(id)}/test-run`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export function fetchLocationLimitRuntime(locationId, week = "") {
  const params = new URLSearchParams({ location_id: locationId, _: String(Date.now()) });
  if (week) params.set("week", week);
  return requestAdminJson(`/api/admin/v2/world/limits/runtime?${params.toString()}`);
}

export function setLocationLimitRemaining(limitId, locationId, value, week, reason) {
  return requestAdminJson(`/api/admin/v2/world/limits/runtime/${encodeURIComponent(limitId)}/set`, {
    method: "POST",
    body: JSON.stringify({ location_id: locationId, value: Number(value), week: week || null, reason: reason || "" }),
  });
}

// Тестовый бой моба (ТЗ §28): симуляция против эталонного игрока.
export function mobTestBattle(id, { player = {}, count = 200 } = {}) {
  return requestAdminJson(`/api/admin/v2/world/mob/${encodeURIComponent(id)}/test-battle`, {
    method: "POST",
    body: JSON.stringify({ player, count }),
  });
}
