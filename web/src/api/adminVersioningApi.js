// Общий клиент версионирования для EntityStore-конструкторов (Этап 1).
// base — сегмент пути после /api/admin/v2/ (например "effects", "fines").
import { requestAdminJson } from "./adminApi.js";

export function fetchEntityHistory(base, id) {
  return requestAdminJson(`/api/admin/v2/${base}/${encodeURIComponent(id)}/history?_=${Date.now()}`);
}

export function rollbackEntity(base, id, version, reason) {
  return requestAdminJson(`/api/admin/v2/${base}/${encodeURIComponent(id)}/rollback`, {
    method: "POST",
    body: JSON.stringify({ version, reason: reason || "" }),
  });
}
