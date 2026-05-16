const PROFILE_TOKEN_STORAGE_KEY = "ner_talis_profile_token";

function rememberPrivateProfileToken(token) {
  if (!token) return;
  try {
    window.localStorage.setItem(PROFILE_TOKEN_STORAGE_KEY, token);
  } catch {
    // VK/embedded browsers can block localStorage. The URL token still works.
  }
}

function getRememberedPrivateProfileToken() {
  try {
    return window.localStorage.getItem(PROFILE_TOKEN_STORAGE_KEY) || "";
  } catch {
    return "";
  }
}

export function getProfileIdentifierFromUrl() {
  const params = new URLSearchParams(window.location.search);
  const token = params.get("token");
  if (token) {
    rememberPrivateProfileToken(token);
    return token;
  }

  const explicitPublicId =
    params.get("player") ||
    params.get("public_id") ||
    params.get("id");
  if (explicitPublicId) return explicitPublicId;

  const parts = window.location.pathname.split("/").filter(Boolean);
  const pathIdentifier = parts[parts.length - 1] || "";

  // In VK's embedded browser the query string can be lost after internal
  // navigation. Keep using the short-lived token from the bot if the page is
  // still the profile page and there is no explicit public id in the URL.
  if (!pathIdentifier || pathIdentifier === "profile") {
    const rememberedToken = getRememberedPrivateProfileToken();
    if (rememberedToken) return rememberedToken;
  }

  return pathIdentifier;
}

export const getPublicIdFromUrl = getProfileIdentifierFromUrl;

async function requestJson(url, options = {}) {
  const response = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
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
    throw new Error(message);
  }

  return response.json();
}

export function loadPlayerProfile(identifier) {
  return requestJson(`/api/profile/${encodeURIComponent(identifier)}`);
}

export function spendAttributePoints(identifier, attributeKey, amount) {
  return requestJson(`/api/profile/${encodeURIComponent(identifier)}/attributes/spend`, {
    method: "POST",
    body: JSON.stringify({ attribute_key: attributeKey, amount }),
  });
}

export function equipItem(identifier, itemId) {
  return requestJson(`/api/profile/${encodeURIComponent(identifier)}/equipment/equip`, {
    method: "POST",
    body: JSON.stringify({ item_id: itemId }),
  });
}

export function unequipItem(identifier, slotKey) {
  return requestJson(`/api/profile/${encodeURIComponent(identifier)}/equipment/unequip`, {
    method: "POST",
    body: JSON.stringify({ slot_key: slotKey }),
  });
}

export function useItem(identifier, itemId) {
  return requestJson(`/api/profile/${encodeURIComponent(identifier)}/inventory/use`, {
    method: "POST",
    body: JSON.stringify({ item_id: itemId }),
  });
}


export function spendSkillPoints(identifier, skillId, modifierId, amount) {
  return requestJson(`/api/profile/${encodeURIComponent(identifier)}/skills/spend`, {
    method: "POST",
    body: JSON.stringify({ skill_id: skillId, modifier_id: modifierId, amount }),
  });
}


export function equipSkill(identifier, skillId) {
  return requestJson(`/api/profile/${encodeURIComponent(identifier)}/skills/equip`, {
    method: "POST",
    body: JSON.stringify({ skill_id: skillId }),
  });
}

export function unequipSkill(identifier, skillId) {
  return requestJson(`/api/profile/${encodeURIComponent(identifier)}/skills/unequip`, {
    method: "POST",
    body: JSON.stringify({ skill_id: skillId }),
  });
}
