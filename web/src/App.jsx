import React, { useCallback, useEffect, useState } from "react";
import { PlayerProfile } from "./components/player-profile";
import "./components/player-profile/PlayerProfile.css";
import {
  equipItem,
  equipSkill,
  getProfileIdentifierFromUrl,
  loadPlayerProfile,
  spendAttributePoints,
  spendSkillPoints,
  unequipItem,
  unequipSkill,
  useItem,
} from "./api/profileApi.js";

function App() {
  const [profile, setProfile] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const profileIdentifier = getProfileIdentifierFromUrl();

  const reloadProfile = useCallback(async () => {
    if (!profileIdentifier || profileIdentifier === "profile") {
      setError("В ссылке нет token или public_id игрока. Открой профиль кнопкой «Профиль» в боте.");
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

  async function runProfileAction(action) {
    try {
      setError("");
      const payload = await action();
      if (payload?.profile) {
        setProfile(payload.profile);
      } else {
        await reloadProfile();
      }
    } catch (requestError) {
      setError(requestError.message || "Действие не выполнено.");
    }
  }

  if (loading) {
    return <div className="nt-profile-loading">Загрузка профиля...</div>;
  }

  if (error && !profile) {
    return <div className="nt-profile-loading nt-profile-error">{error}</div>;
  }

  return (
    <>
      {error ? <div className="nt-api-error">{error}</div> : null}
      <PlayerProfile
        profile={profile}
        onSpendAttributePoints={(attributeKey, amount) => {
          return runProfileAction(() => spendAttributePoints(profileIdentifier, attributeKey, amount));
        }}
        onSpendSkillPoints={(skill, modifierId, amount) => {
          return runProfileAction(() => spendSkillPoints(profileIdentifier, skill.id || skill.name, modifierId, amount));
        }}
        onEquipItem={(item) => {
          return runProfileAction(() => equipItem(profileIdentifier, item.id));
        }}
        onUnequipItem={(slotKey) => {
          return runProfileAction(() => unequipItem(profileIdentifier, slotKey));
        }}
        onUseItem={(item) => {
          return runProfileAction(() => useItem(profileIdentifier, item.id));
        }}
        onEquipSkill={(skill) => {
          return runProfileAction(() => equipSkill(profileIdentifier, skill.id || skill.name));
        }}
        onUnequipSkill={(skill) => {
          return runProfileAction(() => unequipSkill(profileIdentifier, skill.id || skill.name));
        }}
      />
    </>
  );
}

export default App;
