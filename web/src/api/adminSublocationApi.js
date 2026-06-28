// Sublocation constructor helpers (ТЗ 09). CRUD идёт через adminWorldApi по
// kind: sublocation / sublocation_node / sublocation_transition.
import { requestAdminJson } from "./adminApi.js";

const t = () => Date.now();
const base = "/api/admin/v2/sublocations";

export const fetchSublocationMeta = () => requestAdminJson(`${base}/meta?_=${t()}`);
export const fetchSublocationSchema = (id) => requestAdminJson(`${base}/${encodeURIComponent(id)}/schema?_=${t()}`);
export const fetchSublocationNodes = (id) => requestAdminJson(`${base}/${encodeURIComponent(id)}/nodes?_=${t()}`);
