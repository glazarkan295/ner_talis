const ADMIN_SESSION_STORAGE_KEY = "ner_talis_admin_panel_session_token";
const ADMIN_VIEW_STORAGE_KEY = "ner_talis_admin_view_token";

function remember(key, value) {
  if (!value) return;
  try { window.sessionStorage.setItem(key, value); } catch {}
}
function read(key) {
  try { return window.sessionStorage.getItem(key) || ""; } catch { return ""; }
}
function clear(key) {
  try { window.sessionStorage.removeItem(key); } catch {}
}
function stripTokenFromUrl(fallbackPath) {
  try {
    const url = new URL(window.location.href);
    if (!url.searchParams.has("token")) return;
    url.searchParams.delete("token");
    url.searchParams.delete("t");
    window.history.replaceState({}, document.title, `${url.pathname}${url.search}${url.hash}` || fallbackPath);
  } catch {}
}
function authHeaders(token = read(ADMIN_SESSION_STORAGE_KEY)) {
  return token ? { Authorization: `Bearer ${token}` } : {};
}
export function isAdminPanelPath() {
  return window.location.pathname.startsWith("/admin_panel");
}
export function isAdminViewProfilePath() {
  return window.location.pathname.startsWith("/admin_view_profile");
}
export async function requestAdminJson(url, options = {}) {
  const token = options.authToken === undefined ? read(ADMIN_SESSION_STORAGE_KEY) : options.authToken;
  const { authToken, ...fetchOptions } = options;
  const response = await fetch(url, {
    cache: "no-store",
    headers: { "Content-Type": "application/json", "Cache-Control": "no-cache", ...authHeaders(token), ...(fetchOptions.headers || {}) },
    ...fetchOptions,
  });
  if (!response.ok) {
    let message = `Ошибка запроса: ${response.status}`;
    try { const payload = await response.json(); message = payload.detail || payload.message || message; } catch {}
    if (response.status === 401 || response.status === 403) clear(ADMIN_SESSION_STORAGE_KEY);
    throw new Error(message);
  }
  const payload = await response.json();
  if (payload?.sessionToken) remember(ADMIN_SESSION_STORAGE_KEY, payload.sessionToken);
  return payload;
}
export async function getAdminSessionToken() {
  const params = new URLSearchParams(window.location.search);
  const activation = params.get("token");
  if (activation) {
    stripTokenFromUrl("/admin_panel");
    const payload = await requestAdminJson(`/api/admin/session/${encodeURIComponent(activation)}?_=${Date.now()}`, { authToken: "" });
    return payload.sessionToken;
  }
  return read(ADMIN_SESSION_STORAGE_KEY);
}
export function getStoredAdminSessionToken() { return read(ADMIN_SESSION_STORAGE_KEY); }
export function getAdminViewTokenFromUrl() {
  const params = new URLSearchParams(window.location.search);
  const token = params.get("token");
  if (token) { remember(ADMIN_VIEW_STORAGE_KEY, token); stripTokenFromUrl("/admin_view_profile"); return token; }
  return read(ADMIN_VIEW_STORAGE_KEY);
}
export function loadCatalog(token, q = "", category = "") {
  const params = new URLSearchParams({ q, category });
  return requestAdminJson(`/api/admin/catalog?${params.toString()}&_=${Date.now()}`);
}
export function loadCatalogItem(token, itemId) {
  return requestAdminJson(`/api/admin/catalog/${encodeURIComponent(itemId)}?_=${Date.now()}`);
}
export function changeCatalogItemImage(token, itemId, file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = async () => {
      try {
        const payload = await requestAdminJson(`/api/admin/catalog/${encodeURIComponent(itemId)}/image`, {
          method: "POST",
          body: JSON.stringify({ filename: file.name, content_type: file.type, content_base64: String(reader.result || "") }),
        });
        resolve(payload);
      } catch (error) { reject(error); }
    };
    reader.onerror = () => reject(new Error("Не удалось прочитать файл."));
    reader.readAsDataURL(file);
  });
}
export function loadPlayers(token, q = "") {
  const params = new URLSearchParams({ q });
  return requestAdminJson(`/api/admin/players?${params.toString()}&_=${Date.now()}`);
}
export function loadPlayer(token, gameId) {
  return requestAdminJson(`/api/admin/players/${encodeURIComponent(gameId)}?_=${Date.now()}`);
}
export function deletePlayer(token, gameId) {
  return requestAdminJson(`/api/admin/players/${encodeURIComponent(gameId)}`, { method: "DELETE", body: JSON.stringify({ confirm: "CONFIRM_DELETE" }) });
}
export function createPlayerViewToken(token, gameId) {
  return requestAdminJson(`/api/admin/players/${encodeURIComponent(gameId)}/view-token`, { method: "POST", body: JSON.stringify({}) });
}
export function loadPlayerLogs(token, gameId) {
  return requestAdminJson(`/api/admin/players/${encodeURIComponent(gameId)}/logs?_=${Date.now()}`);
}
export function loadPlayerChat(token, gameId) {
  return requestAdminJson(`/api/admin/players/${encodeURIComponent(gameId)}/chat?_=${Date.now()}`);
}
export function sendDelivery(token, targetGameId, rewards) {
  return requestAdminJson("/api/admin/delivery/send", { method: "POST", body: JSON.stringify({ target_game_id: targetGameId, rewards }) });
}
export function loadPromos(token) {
  return requestAdminJson(`/api/admin/promos?_=${Date.now()}`);
}
export function createPromo(token, code, usesLeft, duration, rewards) {
  return requestAdminJson("/api/admin/promos", { method: "POST", body: JSON.stringify({ code, uses_left: usesLeft, duration, rewards }) });
}
export function deletePromo(token, code) {
  return requestAdminJson(`/api/admin/promos/${encodeURIComponent(code)}`, { method: "DELETE" });
}
export function loadAdminPlayerView(token) {
  return requestAdminJson(`/api/admin/player-view?_=${Date.now()}`, { authToken: token });
}
