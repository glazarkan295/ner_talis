const PROFILE_SESSION_STORAGE_KEY = "ner_talis_profile_session_token";
const LEGACY_PROFILE_TOKEN_STORAGE_KEY = "ner_talis_profile_token";

function clearLegacyPersistentToken() {
  try {
    window.localStorage.removeItem(LEGACY_PROFILE_TOKEN_STORAGE_KEY);
  } catch {
    // Embedded browsers can block localStorage.
  }
}

function rememberActiveProfileSession(token) {
  if (!token) return;
  try {
    window.sessionStorage.setItem(PROFILE_SESSION_STORAGE_KEY, token);
  } catch {
    // VK/embedded browsers can block sessionStorage. Persistence intentionally
    // stays session-only and is never written to localStorage.
  }
}

function getRememberedActiveProfileSession() {
  try {
    return window.sessionStorage.getItem(PROFILE_SESSION_STORAGE_KEY) || "";
  } catch {
    return "";
  }
}

function clearActiveProfileSession() {
  try {
    window.sessionStorage.removeItem(PROFILE_SESSION_STORAGE_KEY);
  } catch {
    // ignore storage errors
  }
}

function removeSensitiveTokenFromAddressBar() {
  try {
    const url = new URL(window.location.href);
    if (!url.searchParams.has("token")) return;
    url.searchParams.delete("token");
    url.searchParams.delete("t");
    const cleaned = `${url.pathname}${url.search}${url.hash}`;
    window.history.replaceState({}, document.title, cleaned || "/profile");
  } catch {
    // History can be restricted in embedded browsers. Server-side token reuse
    // protection still remains active.
  }
}

export function setActiveProfileSession(token) {
  rememberActiveProfileSession(token);
}

// Админский edit-token цели держим ТОЛЬКО в памяти этого модуля и НЕ пишем в
// общий слот сессии профиля: иначе, открыв затем /profile в той же вкладке,
// админ аутентифицировался бы как просматриваемый игрок (Codex P2). Токен
// живёт только пока открыт AdminProfileView (сбрасывается при перезагрузке).
let adminProfileToken = "";

export function setAdminProfileToken(token) {
  adminProfileToken = String(token || "");
}

export function clearAdminProfileToken() {
  adminProfileToken = "";
}

function removePathTokenFromAddressBar() {
  try {
    window.history.replaceState({}, document.title, "/profile");
  } catch {
    // History can be restricted in embedded browsers.
  }
}

export function getProfileIdentifierFromUrl() {
  clearLegacyPersistentToken();
  const params = new URLSearchParams(window.location.search);
  const activationToken = params.get("token");
  if (activationToken) {
    removeSensitiveTokenFromAddressBar();
    return activationToken;
  }

  // Path-форма ссылки: /profile/<token>. Сервер принимает её как активацию
  // (как и ?token=), поэтому фронт тоже должен её распознавать.
  const pathMatch = window.location.pathname.match(/^\/profile\/([^/]+)\/?$/);
  if (pathMatch && pathMatch[1] && pathMatch[1].length >= 8) {
    const pathToken = decodeURIComponent(pathMatch[1]);
    removePathTokenFromAddressBar();
    return pathToken;
  }

  const rememberedToken = getRememberedActiveProfileSession();
  if (rememberedToken) return "me";

  return "";
}

export const getPublicIdFromUrl = getProfileIdentifierFromUrl;

function profileAuthHeaders() {
  // Админский edit-token (если активен AdminProfileView) имеет приоритет, но
  // живёт только в памяти — общий слот сессии им не затирается.
  const token = adminProfileToken || getRememberedActiveProfileSession();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, {
    cache: "no-store",
    headers: {
      "Content-Type": "application/json",
      "Cache-Control": "no-cache",
      Pragma: "no-cache",
      ...profileAuthHeaders(),
      ...(options.headers || {}),
    },
    ...options,
  });

  if (!response.ok) {
    let message = `Ошибка запроса: ${response.status}`;
    try {
      const payload = await response.json();
      message = payload.detail || payload.message || message;
    } catch {
      // ignore json parse errors
    }
    if (response.status === 401 || response.status === 403) {
      clearActiveProfileSession();
    }
    throw new Error(message);
  }

  const payload = await response.json();
  // В админском режиме НЕ переносим возвращённый sessionToken в общий слот —
  // иначе токен цели «прилип» бы к собственной сессии профиля админа.
  if (!adminProfileToken) {
    if (payload?.sessionToken) {
      rememberActiveProfileSession(payload.sessionToken);
    }
    if (payload?.profile?.sessionToken) {
      rememberActiveProfileSession(payload.profile.sessionToken);
    }
  }
  return payload;
}

export function loadPlayerProfile(identifier) {
  if (identifier && identifier !== "me") {
    // The bot URL token is a one-time activation key. It is used only here;
    // all following API calls go through Authorization: Bearer sessionToken.
    return requestJson(`/api/profile/session/${encodeURIComponent(identifier)}?_=${Date.now()}`);
  }
  return requestJson(`/api/profile/me?_=${Date.now()}`);
}

function profileEndpoint(path) {
  return `/api/profile/me${path}`;
}

export function spendAttributePoints(identifier, attributeKey, amount) {
  return requestJson(profileEndpoint("/attributes/spend"), {
    method: "POST",
    body: JSON.stringify({ attribute_key: attributeKey, amount }),
  });
}

export function confirmAttributePoints(identifier, allocations) {
  return requestJson(profileEndpoint("/attributes/confirm"), {
    method: "POST",
    body: JSON.stringify({ allocations }),
  });
}

export function equipItem(identifier, itemId, slotKey = null, inventoryIndex = null) {
  const payload = { item_id: itemId, slot_key: slotKey };
  if (Number.isInteger(inventoryIndex) && inventoryIndex >= 0) {
    payload.inventory_index = inventoryIndex;
  }
  return requestJson(profileEndpoint("/equipment/equip"), {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function unequipItem(identifier, slotKey) {
  return requestJson(profileEndpoint("/equipment/unequip"), {
    method: "POST",
    body: JSON.stringify({ slot_key: slotKey }),
  });
}

export function useItem(identifier, itemId, inventoryIndex = null) {
  const payload = { item_id: itemId };
  if (Number.isInteger(inventoryIndex) && inventoryIndex >= 0) {
    payload.inventory_index = inventoryIndex;
  }
  return requestJson(profileEndpoint("/inventory/use"), {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function repairItem(identifier, itemId, inventoryIndex = null) {
  const payload = { item_id: itemId };
  if (Number.isInteger(inventoryIndex) && inventoryIndex >= 0) payload.inventory_index = inventoryIndex;
  return requestJson(profileEndpoint("/inventory/repair"), { method: "POST", body: JSON.stringify(payload) });
}

export function runProfileItemAction(identifier, itemId, inventoryIndex, action) {
  const payload = { item_id: itemId, action };
  if (Number.isInteger(inventoryIndex) && inventoryIndex >= 0) payload.inventory_index = inventoryIndex;
  return requestJson(profileEndpoint("/inventory/profile-action"), { method: "POST", body: JSON.stringify(payload) });
}

export function useSkillOutside(identifier, skillId) {
  return requestJson(profileEndpoint("/skills/use-outside"), { method: "POST", body: JSON.stringify({ skill_id: skillId }) });
}

export function runCraftOperation(identifier, itemId, inventoryIndex, operation, ruleId) {
  return requestJson(profileEndpoint("/inventory/craft-operation"), {
    method: "POST",
    body: JSON.stringify({ item_id: itemId, inventory_index: inventoryIndex, operation, rule_id: ruleId }),
  });
}

export function claimCraftDelivery(identifier) {
  return requestJson(profileEndpoint("/inventory/craft-delivery/claim"), { method: "POST", body: "{}" });
}

export function editProfileField(identifier, field, value) {
  return requestJson(profileEndpoint("/profile/edit-field"), {
    method: "POST",
    body: JSON.stringify({ field, value: String(value) }),
  });
}

export async function changeRace(identifier, targetRaceId) {
  const preview = await requestJson(profileEndpoint("/race/change-preview"), {
    method: "POST", body: JSON.stringify({ target_race_id: targetRaceId, method: "service" }),
  });
  const warning = preview?.preview?.warning || "Смена расы заменит постоянные бонусы персонажа.";
  if (!window.confirm(`${warning}\n\nСтоимость: ${preview?.preview?.cost || 0}. Подтвердить смену?`)) {
    throw new Error("Смена расы отменена.");
  }
  return requestJson(profileEndpoint("/race/change-confirm"), {
    method: "POST", body: JSON.stringify({ confirmation_token: preview.preview.confirmation_token }),
  });
}

export function spendSkillPoints(identifier, skillId, modifierId, amount) {
  return requestJson(profileEndpoint("/skills/spend"), {
    method: "POST",
    body: JSON.stringify({ skill_id: skillId, modifier_id: modifierId, amount }),
  });
}

export function equipSkill(identifier, skillId) {
  return requestJson(profileEndpoint("/skills/equip"), {
    method: "POST",
    body: JSON.stringify({ skill_id: skillId }),
  });
}

export function unequipSkill(identifier, skillId) {
  return requestJson(profileEndpoint("/skills/unequip"), {
    method: "POST",
    body: JSON.stringify({ skill_id: skillId }),
  });
}

export function sellItem(identifier, itemId, amount, inventoryIndex = null) {
  const payload = { item_id: itemId, amount };
  if (Number.isInteger(inventoryIndex) && inventoryIndex >= 0) {
    payload.inventory_index = inventoryIndex;
  }
  return requestJson(profileEndpoint("/inventory/sell"), {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function dropItem(identifier, itemId, amount, inventoryIndex = null) {
  const payload = { item_id: itemId, amount };
  if (Number.isInteger(inventoryIndex) && inventoryIndex >= 0) {
    payload.inventory_index = inventoryIndex;
  }
  return requestJson(profileEndpoint("/inventory/drop"), {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function redeemPromoCode(identifier, code) {
  return requestJson(profileEndpoint("/promo/redeem"), {
    method: "POST",
    body: JSON.stringify({ code: String(code || "") }),
  });
}

export function searchCourierRecipients(query) {
  const params = new URLSearchParams({ q: String(query || ""), _: Date.now() });
  return requestJson(profileEndpoint(`/courier/search?${params.toString()}`));
}

export function sendCourierTransfer(receiver, items, coins, letter) {
  return requestJson(profileEndpoint("/courier/send"), {
    method: "POST",
    body: JSON.stringify({
      receiver: String(receiver || ""),
      items: items || [],
      coins: Math.max(0, Number(coins) || 0),
      letter: String(letter || ""),
    }),
  });
}
