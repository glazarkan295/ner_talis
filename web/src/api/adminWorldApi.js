// Admin V2 «Конструктор мира» API client. Generic over content `kind`
// (first kind: "location"). Reuses the shared V2 session plumbing.
import { requestAdminJson } from "./adminApi.js";

export function fetchWorldMeta() {
  return requestAdminJson(`/api/admin/v2/world/kinds?_=${Date.now()}`);
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

export function previewWorldItem(kind, id) {
  return requestAdminJson(`/api/admin/v2/world/${encodeURIComponent(kind)}/${encodeURIComponent(id)}/preview?_=${Date.now()}`);
}

export function testRunWorldItem(kind, id) {
  return requestAdminJson(`/api/admin/v2/world/${encodeURIComponent(kind)}/${encodeURIComponent(id)}/test-run`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}
