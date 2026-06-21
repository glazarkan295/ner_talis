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

export function getProfileIdentifierFromUrl() {
  clearLegacyPersistentToken();
  const params = new URLSearchParams(window.location.search);
  const activationToken = params.get("token");
  if (activationToken) {
    removeSensitiveTokenFromAddressBar();
    return activationToken;
  }

  const rememberedToken = getRememberedActiveProfileSession();
  if (rememberedToken) return "me";

  return "";
}

export const getPublicIdFromUrl = getProfileIdentifierFromUrl;

function profileAuthHeaders() {
  const token = getRememberedActiveProfileSession();
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
  if (payload?.sessionToken) {
    rememberActiveProfileSession(payload.sessionToken);
  }
  if (payload?.profile?.sessionToken) {
    rememberActiveProfileSession(payload.profile.sessionToken);
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

export function editProfileField(identifier, field, value) {
  return requestJson(profileEndpoint("/profile/edit-field"), {
    method: "POST",
    body: JSON.stringify({ field, value: String(value) }),
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
