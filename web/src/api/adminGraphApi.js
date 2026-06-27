// Admin V2 interactive graph API client (ТЗ 12). Read-only map of all entities.
import { requestAdminJson } from "./adminApi.js";

const t = () => Date.now();
const base = "/api/admin/v2/graph";

export const fetchGraphLegend = () => requestAdminJson(`${base}/legend?_=${t()}`);
export const fetchFullGraph = (types = "", statuses = "") =>
  requestAdminJson(`${base}?${new URLSearchParams({ ...(types ? { types } : {}), ...(statuses ? { statuses } : {}) }).toString()}&_=${t()}`);
export const fetchErrorGraph = () => requestAdminJson(`${base}/errors?_=${t()}`);
export const fetchGraphValidation = () => requestAdminJson(`${base}/validate?_=${t()}`);
export const fetchGraphAround = (nodeType, entityId, depth = 2) =>
  requestAdminJson(`${base}/around/${encodeURIComponent(nodeType)}/${encodeURIComponent(entityId)}?depth=${depth}&_=${t()}`);
export const fetchLocationGraph = (locationId) =>
  requestAdminJson(`${base}/location/${encodeURIComponent(locationId)}?_=${t()}`);
export const fetchGraphPath = (source, target) =>
  requestAdminJson(`${base}/path?${new URLSearchParams({ source, target }).toString()}&_=${t()}`);
export const fetchGraphNode = (nodeType, entityId) =>
  requestAdminJson(`${base}/node/${encodeURIComponent(nodeType)}/${encodeURIComponent(entityId)}?_=${t()}`);
export const runGraphSandbox = (node, values, target) =>
  requestAdminJson(`${base}/sandbox`, { method: "POST", body: JSON.stringify({ node, values, target }) });
export const fetchEditableEdges = () => requestAdminJson(`${base}/editable-edges?_=${t()}`);
export const editGraphEdge = (action, from, edgeType, to, reason) =>
  requestAdminJson(`${base}/edge`, { method: "POST", body: JSON.stringify({ action, from, edge_type: edgeType, to, reason }) });
