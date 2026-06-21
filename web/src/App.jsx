import React, { useCallback, useEffect, useState } from "react";
import { PlayerProfile } from "./components/player-profile";
import { AdminPanel } from "./components/admin-panel";
import { AdminShell } from "./components/admin-shell";
import { isAdminPanelV2Path } from "./api/adminV2Api.js";
import "./components/player-profile/PlayerProfile.css";
import {
  dropItem,
  sellItem,
  editProfileField,
  equipItem,
  equipSkill,
  getProfileIdentifierFromUrl,
  loadPlayerProfile,
  confirmAttributePoints,
  redeemPromoCode,
  searchCourierRecipients,
  sendCourierTransfer,
  setActiveProfileSession,
  spendAttributePoints,
  spendSkillPoints,
  unequipItem,
  unequipSkill,
  useItem,
} from "./api/profileApi.js";
import { isAdminPanelPath, isAdminViewProfilePath, getAdminViewTokenFromUrl, loadAdminPlayerView } from "./api/adminApi.js";

function AdminProfileView() {
  const [profile, setProfile] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const reload = useCallback(async () => {
    const token = getAdminViewTokenFromUrl();
    if (!token) throw new Error("Нет token для админского просмотра профиля.");
    const payload = await loadAdminPlayerView(token);
    const canEdit = Boolean(payload.editToken);
    if (canEdit) setActiveProfileSession(payload.editToken);
    setProfile({ ...(payload.profile || {}), readOnly: !canEdit, adminView: true, adminEdit: canEdit });
  }, []);

  useEffect(() => {
    reload()
      .catch((requestError) => setError(requestError.message || "Не удалось открыть профиль игрока."))
      .finally(() => setLoading(false));
  }, [reload]);

  async function runAction(action) {
    try {
      setError("");
      const payload = await action();
      if (payload?.profile) {
        setProfile({ ...payload.profile, adminView: true, adminEdit: true });
      } else {
        await reload();
      }
      return payload;
    } catch (requestError) {
      setError(requestError.message || "Действие не выполнено.");
      throw requestError;
    }
  }

  if (loading) return <div className="nt-profile-loading">Загрузка профиля...</div>;
  if (error || !profile) return <div className="nt-profile-loading nt-profile-error">{error || "Профиль недоступен."}</div>;
  return (
    <>
      {error ? <div className="nt-api-error">{error}</div> : null}
      <PlayerProfile
        profile={profile}
        readOnly={!profile.adminEdit}
        onSpendAttributePoints={(attributeKey, amount) => runAction(() => spendAttributePoints("me", attributeKey, amount))}
        onConfirmAttributePoints={(allocations) => runAction(() => confirmAttributePoints("me", allocations))}
        onSpendSkillPoints={(skill, modifierId, amount) => runAction(() => spendSkillPoints("me", skill.id || skill.name, modifierId, amount))}
        onEquipItem={(item, slotKey = null) => runAction(() => equipItem("me", item.id, slotKey, item.inventoryIndex))}
        onUnequipItem={(slotKey) => runAction(() => unequipItem("me", slotKey))}
        onUseItem={(item) => runAction(() => useItem("me", item.id, item.inventoryIndex))}
        onDropItem={(item, amount) => runAction(() => dropItem("me", item.id, amount, item.inventoryIndex))}
        onSellItem={(item, amount) => runAction(() => sellItem("me", item.id, amount, item.inventoryIndex))}
        onEquipSkill={(skill) => runAction(() => equipSkill("me", skill.id || skill.name))}
        onUnequipSkill={(skill) => runAction(() => unequipSkill("me", skill.id || skill.name))}
        onEditProfileField={(field, value) => runAction(() => editProfileField("me", field, value))}
        onAdminRemoveItem={(item) => runAction(() => dropItem("me", item.id, Math.max(1, Number(item.amount) || 1), item.inventoryIndex))}
      />
    </>
  );
}

function ProfileApp() {
  const [profile, setProfile] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [profileIdentifier] = useState(() => getProfileIdentifierFromUrl());

  const reloadProfile = useCallback(async () => {
    if (!profileIdentifier || profileIdentifier === "profile") {
      setError("В ссылке нет token игрока. Открой профиль кнопкой «Профиль» в боте.");
      setLoading(false);
      return;
    }

    try {
      setError("");
      const payload = await loadPlayerProfile(profileIdentifier);
      setProfile(payload);
    } catch (requestError) {
      setError(requestError.message || "Не удалось загрузить профиль игрока.");
    } finally {
      setLoading(false);
    }
  }, [profileIdentifier]);

  useEffect(() => {
    reloadProfile();
  }, [reloadProfile]);

  useEffect(() => {
    if (!profile?.market?.sellFromProfile) return undefined;
    // Poll less aggressively (20s) to save mobile traffic, and refresh on tab
    // focus so the player still sees fresh state when they come back.
    const intervalId = window.setInterval(() => {
      if (!document.hidden) reloadProfile();
    }, 20000);
    const onVisible = () => { if (!document.hidden) reloadProfile(); };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      window.clearInterval(intervalId);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [profile?.market?.sellFromProfile, reloadProfile]);

  async function runProfileAction(action) {
    try {
      setError("");
      const payload = await action();
      if (payload?.profile) {
        setProfile(payload.profile);
      } else {
        await reloadProfile();
      }
      return payload;
    } catch (requestError) {
      setError(requestError.message || "Действие не выполнено.");
      throw requestError;
    }
  }

  if (loading) {
    return <div className="nt-profile-loading">Загрузка профиля...</div>;
  }

  if (!profile) {
    // No real profile loaded: never fall back to demo/mock data on the live site.
    return <div className="nt-profile-loading nt-profile-error">{error || "Профиль недоступен. Откройте новую ссылку из бота."}</div>;
  }

  return (
    <>
      {error ? <div className="nt-api-error">{error}</div> : null}
      <PlayerProfile
        profile={profile}
        onSpendAttributePoints={(attributeKey, amount) => {
          return runProfileAction(() => spendAttributePoints(profileIdentifier, attributeKey, amount));
        }}
        onConfirmAttributePoints={(allocations) => {
          return runProfileAction(() => confirmAttributePoints(profileIdentifier, allocations));
        }}
        onSpendSkillPoints={(skill, modifierId, amount) => {
          return runProfileAction(() => spendSkillPoints(profileIdentifier, skill.id || skill.name, modifierId, amount));
        }}
        onEquipItem={(item, slotKey = null) => {
          return runProfileAction(() => equipItem(profileIdentifier, item.id, slotKey, item.inventoryIndex));
        }}
        onUnequipItem={(slotKey) => {
          return runProfileAction(() => unequipItem(profileIdentifier, slotKey));
        }}
        onUseItem={(item) => {
          return runProfileAction(() => useItem(profileIdentifier, item.id, item.inventoryIndex));
        }}
        onDropItem={(item, amount) => {
          return runProfileAction(() => dropItem(profileIdentifier, item.id, amount, item.inventoryIndex));
        }}
        onSellItem={(item, amount) => {
          return runProfileAction(() => sellItem(profileIdentifier, item.id, amount, item.inventoryIndex));
        }}
        onEquipSkill={(skill) => {
          return runProfileAction(() => equipSkill(profileIdentifier, skill.id || skill.name));
        }}
        onUnequipSkill={(skill) => {
          return runProfileAction(() => unequipSkill(profileIdentifier, skill.id || skill.name));
        }}
        onEditProfileField={(field, value) => {
          return runProfileAction(() => editProfileField(profileIdentifier, field, value));
        }}
        onSearchCourierRecipients={(query) => searchCourierRecipients(query)}
        onSendCourierTransfer={(receiver, items, coins, letter) => {
          return runProfileAction(() => sendCourierTransfer(receiver, items, coins, letter));
        }}
        onRedeemPromo={(code) => runProfileAction(() => redeemPromoCode(profileIdentifier, code))}
      />
    </>
  );
}

function App() {
  if (isAdminPanelV2Path()) return <AdminShell />;
  if (isAdminPanelPath()) return <AdminPanel />;
  if (isAdminViewProfilePath()) return <AdminProfileView />;
  return <ProfileApp />;
}

export default App;
