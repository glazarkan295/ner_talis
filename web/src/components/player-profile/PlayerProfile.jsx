import React, { useMemo, useState } from "react";
import { profileMockData } from "./profileMockData.js";

const TABS = [
  { id: "character", label: "Персонаж" },
  { id: "inventory", label: "Инвентарь" },
  { id: "skills", label: "Навыки" },
  { id: "info", label: "Информация" },
];

const INVENTORY_CATEGORIES = ["Всё", "Снаряжение", "Оружие", "Бижутерия", "Алхимия", "Ресурсы", "Прочее", "Особое"];

const DEFAULT_SLOTS = [
  { key: "helmet", label: "Шлем" },
  { key: "necklace", label: "Ожерелье" },
  { key: "chest", label: "Нагрудник" },
  { key: "belt", label: "Пояс" },
  { key: "pants", label: "Штаны" },
  { key: "boots", label: "Ботинки" },
  { key: "gloves", label: "Перчатки" },
  { key: "ring1", label: "Кольцо 1" },
  { key: "ring2", label: "Кольцо 2" },
  { key: "weapon1", label: "Оружие 1" },
  { key: "weapon2", label: "Оружие 2" },
  { key: "special", label: "Особый слот" },
];

const RACE_INFO = {
  human: {
    name: "Человек",
    text: "Сбалансированная раса без сильных слабостей. Бонусы: возврат золота у NPC, +2% опыта, +1% к основным характеристикам.",
  },
  elf: {
    name: "Эльф",
    text: "Ловкая и разумная раса. Бонусы: +3% магического урона, +4% к качеству зелий, +3% к дополнительным алхимическим ингредиентам.",
  },
  dwarf: {
    name: "Дворф",
    text: "Крепкая раса мастеров. Бонусы: +4% к созданию оружия/брони повышенного качества, -3% расхода руды и металла, +3% к выносливости.",
  },
  undead: {
    name: "Нежить",
    text: "Живучая раса. Бонусы: +4% к здоровью, -5% шанс получить яд/кровотечение/оглушение/проклятие, -3% периодического урона.",
  },
  lizardfolk: {
    name: "Ящеролюд",
    text: "Дикая чешуйчатая раса. Бонусы: 0.5% регенерации HP в бою за ход, -2% физического урона, +4% к поиску добычи и ресурсов.",
  },
};

function normalizeProfile(profile) {
  return profile || profileMockData;
}

function raceKey(profile) {
  return profile?.player?.raceKey || String(profile?.player?.raceName || "human").toLowerCase();
}

function itemSlotKey(item) {
  return item?.slotKey || item?.targetSlotKey || item?.slot || item?.target_slot || "";
}

function itemImage(item) {
  return item?.icon || item?.image || item?.imageUrl || item?.model || "";
}

function itemStats(item) {
  if (!item) return [];
  if (Array.isArray(item.stats)) return item.stats;
  if (Array.isArray(item.properties)) return item.properties;
  if (item.statsText) return [item.statsText];
  return [];
}

function canEquipToSlot(item, slotKey) {
  const target = itemSlotKey(item);
  return target === slotKey;
}

function FieldList({ items }) {
  return (
    <div className="nt-field-list">
      {(items || []).map((item) => (
        <div className="nt-field" key={`${item.label}-${item.key || item.value}`}>
          <span>{item.label}</span>
          <b>{item.value}</b>
        </div>
      ))}
    </div>
  );
}

function ItemIcon({ item, slot, onClick }) {
  const image = itemImage(item);
  return (
    <button type="button" className={`nt-item-icon ${slot ? "nt-item-icon--slot" : ""}`} onClick={onClick} title={item?.name || "Предмет"}>
      {image ? <img src={image} alt={item?.name || "Предмет"} /> : <span>{item?.icon || "◈"}</span>}
      {item?.amount > 1 ? <em>{item.amount}</em> : null}
    </button>
  );
}

function ItemModal({ modal, onClose, onEquipItem, onUnequipItem, onUseItem }) {
  if (!modal) return null;
  const { item, mode, slotKey, slotLabel, suitableItems = [] } = modal;

  if (mode === "slot-list") {
    return (
      <div className="nt-modal-backdrop" onClick={onClose}>
        <div className="nt-modal" onClick={(event) => event.stopPropagation()}>
          <div className="nt-modal-head">
            <h3>{slotLabel}</h3>
            <button type="button" onClick={onClose}>×</button>
          </div>
          <p className="nt-muted">Подходящие предметы из инвентаря для этой ячейки.</p>
          {suitableItems.length ? (
            <div className="nt-slot-pick-list">
              {suitableItems.map((candidate) => (
                <button type="button" className="nt-slot-pick" key={candidate.id} onClick={() => modal.openItem(candidate, slotKey)}>
                  <ItemIcon item={candidate} />
                  <span>
                    <b>{candidate.name}</b>
                    <small>{candidate.quality || candidate.type || "предмет"}</small>
                  </span>
                </button>
              ))}
            </div>
          ) : (
            <p className="nt-empty-text">В инвентаре нет подходящих предметов.</p>
          )}
        </div>
      </div>
    );
  }

  const stats = itemStats(item);
  const isEquipped = mode === "equipped";
  const canUse = !isEquipped && (item?.actions || []).includes("Использовать");
  const canEquip = !isEquipped && itemSlotKey(item);

  async function runAction(action) {
    await action?.();
    onClose();
  }

  return (
    <div className="nt-modal-backdrop" onClick={onClose}>
      <div className="nt-modal" onClick={(event) => event.stopPropagation()}>
        <div className="nt-modal-head">
          <h3>{item?.name || "Предмет"}</h3>
          <button type="button" onClick={onClose}>×</button>
        </div>
        <div className="nt-modal-body">
          <ItemIcon item={item} />
          <div>
            <p className="nt-item-line"><b>Тип:</b> {item?.type || item?.category || "—"}</p>
            <p className="nt-item-line"><b>Качество:</b> {item?.quality || "—"}</p>
            {item?.level ? <p className="nt-item-line"><b>Уровень:</b> {item.level}</p> : null}
            {slotKey ? <p className="nt-item-line"><b>Слот:</b> {slotKey}</p> : null}
          </div>
        </div>
        {item?.description ? <p className="nt-description">{item.description}</p> : null}
        {stats.length ? (
          <ul className="nt-stat-list">
            {stats.map((stat, index) => <li key={`${stat}-${index}`}>{stat}</li>)}
          </ul>
        ) : null}
        {Array.isArray(item?.enchantments) && item.enchantments.length ? (
          <div className="nt-enchants">Зачарования: {item.enchantments.join(", ")}</div>
        ) : null}
        <div className="nt-modal-actions">
          {isEquipped ? <button type="button" onClick={() => runAction(() => onUnequipItem?.(slotKey || itemSlotKey(item)))}>Снять</button> : null}
          {canEquip ? <button type="button" onClick={() => runAction(() => onEquipItem?.(item))}>Надеть</button> : null}
          {canUse ? <button type="button" onClick={() => runAction(() => onUseItem?.(item))}>Использовать</button> : null}
        </div>
      </div>
    </div>
  );
}

function EquipmentPanel({ profile, onEquipItem, onUnequipItem }) {
  const [modal, setModal] = useState(null);
  const slots = profile.equipmentSlots?.length ? profile.equipmentSlots : DEFAULT_SLOTS;
  const equipment = profile.equipment || {};
  const inventory = profile.inventory || [];

  function openSlot(slot) {
    const equipped = equipment[slot.key];
    if (equipped) {
      setModal({ mode: "equipped", item: equipped, slotKey: slot.key });
      return;
    }
    const suitableItems = inventory.filter((item) => canEquipToSlot(item, slot.key));
    setModal({
      mode: "slot-list",
      slotKey: slot.key,
      slotLabel: slot.label,
      suitableItems,
      openItem: (item, selectedSlotKey) => setModal({ mode: "inventory", item, slotKey: selectedSlotKey }),
    });
  }

  return (
    <section className="nt-card nt-equipment-card">
      <h2>Экипировка</h2>
      <div className="nt-equipment-grid">
        {slots.slice(0, 12).map((slot) => {
          const equipped = equipment[slot.key];
          return (
            <button type="button" className="nt-equip-slot" key={slot.key} onClick={() => openSlot(slot)}>
              {equipped ? <ItemIcon item={equipped} slot /> : <span className="nt-slot-empty">+</span>}
              <small>{slot.label}</small>
            </button>
          );
        })}
      </div>
      <ItemModal modal={modal} onClose={() => setModal(null)} onEquipItem={onEquipItem} onUnequipItem={onUnequipItem} />
    </section>
  );
}

function CharacterTab({ profile, onSpendAttributePoints, onEquipItem, onUnequipItem }) {
  const [raceOpen, setRaceOpen] = useState(false);
  const key = raceKey(profile);
  const race = RACE_INFO[key] || RACE_INFO.human;
  const model = profile.assets?.raceModels?.[key];

  return (
    <div className="nt-tab-layout">
      <section className="nt-card nt-hero-card">
        <h2>Персонаж</h2>
        <div className="nt-model-frame">
          {model ? <img src={model} alt={profile.player?.raceName || race.name} /> : <span className="nt-model-empty">?</span>}
        </div>
        <div className="nt-player-title">
          <h1>{profile.player?.nickname || "Игрок"}</h1>
          <p>{profile.player?.userGlobalId || profile.player?.publicId || "NT-UNKNOWN"}</p>
        </div>
      </section>

      <EquipmentPanel profile={profile} onEquipItem={onEquipItem} onUnequipItem={onUnequipItem} />

      <section className="nt-card">
        <h2>Сводка</h2>
        <div className="nt-field-list">
          <div className="nt-field"><span>Раса</span><b>{profile.player?.raceName || race.name} <button className="nt-info-btn" type="button" onClick={() => setRaceOpen(true)}>!</button></b></div>
          <div className="nt-field"><span>Ветка</span><b>{profile.player?.branch || "Не выбрана"}</b></div>
          <div className="nt-field"><span>Уровень</span><b>{profile.player?.level ?? 1}</b></div>
          <div className="nt-field"><span>Опыт</span><b>{profile.player?.experienceCurrent ?? 0} / {profile.player?.experienceToNext ?? 100}</b></div>
          <div className="nt-field"><span>Баланс</span><b>{profile.player?.balanceText || "0 мед."}</b></div>
        </div>
      </section>

      <section className="nt-card">
        <h2>Характеристики</h2>
        <FieldList items={profile.attributes} />
        {profile.player?.freeAttributePoints ? <button className="nt-soft-button" onClick={() => onSpendAttributePoints?.("strength", 1)}>Вложить 1 очко в силу</button> : null}
      </section>

      <section className="nt-card"><h2>Параметры</h2><FieldList items={profile.parameters} /></section>
      <section className="nt-card"><h2>Активные сеты</h2>{profile.activeSets?.length ? profile.activeSets.map((set) => <p key={set.name}><b>{set.name}</b> — {set.bonus}</p>) : <p className="nt-empty-text">Активных сетов нет.</p>}</section>

      {raceOpen ? (
        <div className="nt-modal-backdrop" onClick={() => setRaceOpen(false)}>
          <div className="nt-modal" onClick={(event) => event.stopPropagation()}>
            <div className="nt-modal-head"><h3>{race.name}</h3><button type="button" onClick={() => setRaceOpen(false)}>×</button></div>
            <p>{race.text}</p>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function InventoryTab({ profile, onEquipItem, onUseItem }) {
  const [category, setCategory] = useState("Всё");
  const [modal, setModal] = useState(null);
  const items = useMemo(() => {
    const source = profile.inventory || [];
    if (category === "Всё") return source;
    return source.filter((item) => item.category === category);
  }, [profile.inventory, category]);

  return (
    <section className="nt-card nt-full-card">
      <h2>Инвентарь</h2>
      <div className="nt-category-row">
        {INVENTORY_CATEGORIES.map((item) => <button type="button" className={category === item ? "active" : ""} onClick={() => setCategory(item)} key={item}>{item}</button>)}
      </div>
      <div className="nt-inventory-grid">
        {items.map((item) => (
          <button type="button" className="nt-inventory-cell" key={item.id || item.name} onClick={() => setModal({ mode: "inventory", item })}>
            <ItemIcon item={item} />
            <span>{item.name}</span>
          </button>
        ))}
      </div>
      {!items.length ? <p className="nt-empty-text">В этой категории предметов нет.</p> : null}
      <ItemModal modal={modal} onClose={() => setModal(null)} onEquipItem={onEquipItem} onUseItem={onUseItem} />
    </section>
  );
}

function SkillsTab({ profile }) {
  const active = profile.skills?.active || [];
  const passive = profile.skills?.passive || [];
  return (
    <section className="nt-card nt-full-card">
      <h2>Навыки</h2>
      <p className="nt-free-points">Свободные очки навыков: <b>{profile.player?.freeSkillPoints ?? 0}</b></p>
      <h3>Активные</h3>
      <div className="nt-skill-list">
        {active.map((skill) => <div className="nt-skill" key={skill.id || skill.name}><b>{skill.name}</b><span>{skill.description}</span>{skill.damage ? <em>Урон: {skill.damage}</em> : null}</div>)}
      </div>
      <h3>Пассивные</h3>
      <div className="nt-skill-list">
        {passive.map((skill) => <div className="nt-skill" key={skill.id || skill.name}><b>{skill.name}</b><span>{skill.description}</span></div>)}
      </div>
    </section>
  );
}

function InfoTab({ profile }) {
  const info = profile.information || {};
  return (
    <section className="nt-card nt-full-card">
      <h2>Информация</h2>
      <h3>Достижения</h3>
      {info.achievements?.length ? info.achievements.map((item) => <p key={item.name}><b>{item.name}</b> — {item.description}</p>) : <p className="nt-empty-text">Достижений пока нет.</p>}
      <h3>Активность</h3>
      <FieldList items={[
        { label: "PvE убийства", value: info.activity?.pveKills ?? 0 },
        { label: "PvP убийства", value: info.activity?.pvpKills ?? 0 },
        { label: "Поглощено частиц душ", value: info.activity?.soulParticlesAbsorbed ?? 0 },
      ]} />
    </section>
  );
}

export function PlayerProfile({ profile, onSpendAttributePoints, onEquipItem, onUnequipItem, onUseItem }) {
  const data = normalizeProfile(profile);
  const [activeTab, setActiveTab] = useState("character");
  const background = data.assets?.background;

  return (
    <main className="nt-profile" style={background ? { backgroundImage: `url(${background})` } : undefined}>
      <div className="nt-shell">
        <nav className="nt-tabs">
          {TABS.map((tab) => <button type="button" className={activeTab === tab.id ? "active" : ""} key={tab.id} onClick={() => setActiveTab(tab.id)}>{tab.label}</button>)}
        </nav>
        {activeTab === "character" ? <CharacterTab profile={data} onSpendAttributePoints={onSpendAttributePoints} onEquipItem={onEquipItem} onUnequipItem={onUnequipItem} /> : null}
        {activeTab === "inventory" ? <InventoryTab profile={data} onEquipItem={onEquipItem} onUseItem={onUseItem} /> : null}
        {activeTab === "skills" ? <SkillsTab profile={data} /> : null}
        {activeTab === "info" ? <InfoTab profile={data} /> : null}
      </div>
    </main>
  );
}

export default PlayerProfile;
