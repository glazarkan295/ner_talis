export function getProfileIdentifierFromUrl() {
  const params = new URLSearchParams(window.location.search);
  const fromQuery =
    params.get("token") ||
    params.get("player") ||
    params.get("public_id") ||
    params.get("id");
  if (fromQuery) return fromQuery;

  const parts = window.location.pathname.split("/").filter(Boolean);
  return parts[parts.length - 1] || "";
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
