import React, { useMemo, useState } from "react";
import { profileMockData } from "./profileMockData.js";

const TABS = [
  { id: "character", label: "Персонаж", icon: "👤" },
  { id: "inventory", label: "Инвентарь", icon: "🎒" },
  { id: "skills", label: "Навыки", icon: "✦" },
  { id: "info", label: "Информация", icon: "📜" },
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
    description: "Сбалансированная раса без сильных слабостей, быстро обучается и умеет извлекать выгоду из покупок.",
    stats: "Сила 3 · Ловкость 3 · Выносливость 4 · Интеллект 3 · Мудрость 3 · Восприятие 4",
    bonuses: ["Возврат золота у NPC", "+2% получаемого опыта", "+1% к основным характеристикам"],
  },
  elf: {
    name: "Эльф",
    description: "Ловкая и разумная раса, хорошо чувствует магию, природу и алхимию.",
    stats: "Сила 2 · Ловкость 4 · Выносливость 2 · Интеллект 5 · Мудрость 4 · Восприятие 3",
    bonuses: ["+3% магического урона", "+4% к алхимии", "+3% к сбору алхимических ингредиентов"],
  },
  dwarf: {
    name: "Дворф",
    description: "Крепкая раса мастеров, сильна в кузнечном деле и работе с металлом.",
    stats: "Сила 5 · Ловкость 2 · Выносливость 5 · Интеллект 3 · Мудрость 3 · Восприятие 2",
    bonuses: ["+4% к созданию оружия и брони", "-3% расхода руды и металла", "+3% к выносливости"],
  },
  undead: {
    name: "Нежить",
    description: "Мрачная и живучая раса, устойчивая к боли, ядам и проклятиям.",
    stats: "Сила 3 · Ловкость 2 · Выносливость 6 · Интеллект 3 · Мудрость 4 · Восприятие 2",
    bonuses: ["+4% к здоровью", "-5% шанс получить негативный эффект", "-3% периодического урона"],
  },
  lizardfolk: {
    name: "Ящеролюд",
    description: "Сильная дикая раса с крепкой чешуёй, боевой регенерацией и чутьём на добычу.",
    stats: "Сила 4 · Ловкость 4 · Выносливость 4 · Интеллект 1 · Мудрость 2 · Восприятие 5",
    bonuses: ["0.5% регенерации HP в бою", "-2% физического урона", "+4% к поиску добычи и ресурсов"],
  },
};

const RACE_NAME_TO_KEY = {
  человек: "human",
  эльф: "elf",
  дворф: "dwarf",
  нежить: "undead",
  ящеролюд: "lizardfolk",
};

function profileOrMock(profile) {
  return profile || profileMockData;
}

function raceKey(player) {
  return player?.raceKey || RACE_NAME_TO_KEY[String(player?.raceName || "").toLowerCase()] || "human";
}

function qualityClass(quality = "обычный") {
  return `quality-${String(quality).toLowerCase().replace(/\s+/g, "-")}`;
}

function itemIcon(item) {
  return item?.icon || item?.asset_icon || item?.assetIcon || item?.image || item?.imageUrl || null;
}

function itemSlot(item) {
  return item?.targetSlotKey || item?.slotKey || item?.slot || item?.target_slot || "";
}

function compactSlotName(slotKey = "") {
  const map = {
    helmet: "Шлем",
    necklace: "Ожерелье",
    chest: "Нагрудник",
    belt: "Пояс",
    pants: "Штаны",
    boots: "Ботинки",
    gloves: "Перчатки",
    ring1: "Кольцо 1",
    ring2: "Кольцо 2",
    weapon1: "Оружие 1",
    weapon2: "Оружие 2",
    special: "Особый слот",
  };
  return map[slotKey] || slotKey || "—";
}

function statLines(item) {
  if (!item) return [];
  if (Array.isArray(item.stats)) return item.stats;
  if (Array.isArray(item.properties)) return item.properties;
  if (item.statsText) return [item.statsText];
  return [];
}

function lineParts(line) {
  const text = String(line || "");
  const [label, ...rest] = text.split(":");
  return rest.length ? [label.trim(), rest.join(":").trim()] : [text, ""];
}

function Panel({ title, right, children, className = "" }) {
  return (
    <section className={`nt-panel ${className}`.trim()}>
      <header className="nt-panel-head">
        <h2>{title}</h2>
        {right ? <div className="nt-panel-right">{right}</div> : null}
      </header>
      {children}
    </section>
  );
}

function Row({ label, value, children }) {
  return (
    <div className="nt-row">
      <span>{label}</span>
      <strong>{value}</strong>
      {children}
    </div>
  );
}

function CardRow({ label, value }) {
  return (
    <div className="nt-card-row">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function StatLines({ lines = [] }) {
  if (!lines.length) return null;
  return (
    <div className="nt-stat-lines">
      {lines.map((line, index) => {
        const [label, value] = lineParts(line);
        return (
          <div className="nt-stat-line" key={`${line}-${index}`}>
            <span>{label}</span>
            <strong>{value}</strong>
          </div>
        );
      })}
    </div>
  );
}

function ItemArt({ item, fallback = "◇", className = "nt-item-art" }) {
  const icon = itemIcon(item);
  return <span className={className}>{icon ? <img src={icon} alt="" /> : fallback}</span>;
}

function RaceInfoModal({ profile, onClose }) {
  if (!profile) return null;
  const race = RACE_INFO[raceKey(profile.player)] || RACE_INFO.human;
  return (
    <div className="nt-modal-layer" onMouseDown={onClose}>
      <article className="nt-modal nt-race-modal" onMouseDown={(event) => event.stopPropagation()}>
        <button className="nt-modal-close" type="button" onClick={onClose}>×</button>
        <div className="nt-modal-kicker">Бонусы расы</div>
        <h3>{race.name}</h3>
        <p>{race.description}</p>
        <div className="nt-modal-block">
          <h4>Стартовые характеристики</h4>
          <p className="nt-race-stats">{race.stats}</p>
        </div>
        <div className="nt-modal-block">
          <h4>Бонусы</h4>
          <ul>{race.bonuses.map((bonus) => <li key={bonus}>{bonus}</li>)}</ul>
        </div>
      </article>
    </div>
  );
}

function ItemModal({ item, slotKey, onClose, onEquipItem, onUnequipItem, onUseItem }) {
  if (!item) return null;
  const actions = item.actions || [];
  const itemStats = statLines(item);
  return (
    <div className="nt-modal-layer" onMouseDown={onClose}>
      <article className={`nt-modal ${qualityClass(item.quality)}`} onMouseDown={(event) => event.stopPropagation()}>
        <button className="nt-modal-close" type="button" onClick={onClose}>×</button>
        <div className="nt-modal-kicker">{item.category || "Предмет"}</div>
        <div className="nt-modal-title-row">
          <span className="nt-modal-item-icon"><ItemArt item={item} /></span>
          <div>
            <h3>{item.name || "Предмет"}</h3>
            <div className="nt-modal-subtitle">{item.quality || "обычный"} · ур. {item.level || 1}</div>
          </div>
        </div>
        <div className="nt-modal-grid">
          <span>Тип</span><strong>{item.type || item.category || "—"}</strong>
          <span>Слот</span><strong>{compactSlotName(slotKey || itemSlot(item))}</strong>
          <span>Количество</span><strong>×{item.amount || 1}</strong>
        </div>
        <p>{item.description || "Описание предмета пока не добавлено."}</p>
        {itemStats.length ? <div className="nt-modal-block"><h4>Свойства</h4><StatLines lines={itemStats} /></div> : null}
        {Array.isArray(item.enchantments) && item.enchantments.length ? (
          <div className="nt-modal-block"><h4>Зачарования</h4><StatLines lines={item.enchantments} /></div>
        ) : null}
        <footer className="nt-modal-actions">
          {actions.includes("Надеть") || (!slotKey && itemSlot(item)) ? <button type="button" onClick={() => onEquipItem?.(item)}>Надеть</button> : null}
          {actions.includes("Снять") || slotKey ? <button type="button" onClick={() => onUnequipItem?.(slotKey || itemSlot(item), item)}>Снять</button> : null}
          {actions.includes("Использовать") ? <button type="button" onClick={() => onUseItem?.(item)}>Использовать</button> : null}
          <button className="nt-secondary" type="button" onClick={onClose}>Закрыть</button>
        </footer>
      </article>
    </div>
  );
}

function SlotItemsModal({ slot, items, selectedItem, onSelectItem, onClose, onEquipItem }) {
  if (!slot) return null;
  return (
    <div className="nt-modal-layer" onMouseDown={onClose}>
      <article className="nt-modal nt-slot-modal" onMouseDown={(event) => event.stopPropagation()}>
        <button className="nt-modal-close" type="button" onClick={onClose}>×</button>
        <div className="nt-modal-kicker">Пустой слот</div>
        <h3>{slot.label}</h3>
        {items.length ? (
          <div className="nt-slot-modal-grid">
            <div className="nt-slot-items-list">
              {items.map((item) => (
                <button key={item.id || item.name} className={`nt-slot-choice ${selectedItem?.id === item.id ? "active" : ""} ${qualityClass(item.quality)}`} type="button" onClick={() => onSelectItem(item)}>
                  <ItemArt item={item} className="nt-choice-icon" />
                  <span>{item.name}</span>
                </button>
              ))}
            </div>
            <div className="nt-slot-preview">
              {selectedItem ? (
                <>
                  <h4>{selectedItem.name}</h4>
                  <p>{selectedItem.description || "Можно надеть в выбранный слот."}</p>
                  <StatLines lines={statLines(selectedItem)} />
                  <footer className="nt-modal-actions">
                    <button type="button" onClick={() => onEquipItem?.(selectedItem)}>Надеть</button>
                  </footer>
                </>
              ) : null}
            </div>
          </div>
        ) : <p className="nt-empty-text">В инвентаре нет предметов для этого слота.</p>}
      </article>
    </div>
  );
}

function EquipmentPanel({ profile, onOpenItem, onOpenSlot }) {
  const slots = profile.equipmentSlots?.length ? profile.equipmentSlots : DEFAULT_SLOTS;
  const equipment = profile.equipment || {};
  return (
    <Panel title="Экипировка">
      <div className="nt-equipment-grid">
        {slots.slice(0, 12).map((slot) => {
          const item = equipment[slot.key];
          return (
            <button key={slot.key} className={`nt-equip-slot ${item ? qualityClass(item.quality) : "empty"}`} type="button" onClick={() => item ? onOpenItem(item, slot.key) : onOpenSlot(slot)}>
              <ItemArt item={item} fallback="+" className="nt-equip-art" />
              <span className="nt-equip-label">{item?.name || slot.label}</span>
            </button>
          );
        })}
      </div>
    </Panel>
  );
}

function CharacterTab({ profile, onOpenItem, onOpenSlot, onSpendAttributePoints }) {
  const [raceOpen, setRaceOpen] = useState(false);
  const [attributeAmounts, setAttributeAmounts] = useState({});
  const xpCurrent = Number(profile.player?.experienceCurrent || 0);
  const xpNext = Math.max(1, Number(profile.player?.experienceToNext || 1));
  const xpPercent = Math.min(100, Math.max(0, Math.round((xpCurrent / xpNext) * 100)));
  const freeStats = Number(profile.player?.freeAttributePoints || 0);

  function changeAttribute(key, value) {
    setAttributeAmounts((current) => ({ ...current, [key]: value }));
  }

  function spend(attributeKey) {
    const amount = Math.max(1, Number(attributeAmounts[attributeKey] || 1));
    onSpendAttributePoints?.(attributeKey, amount);
  }

  return (
    <div className="nt-stack">
      <Panel title="Сводка">
        <div className="nt-lines">
          <Row label="Имя" value={profile.player?.nickname || "—"} />
          <Row label="Раса" value={<span className="nt-race-value">{profile.player?.raceName || "—"}<button className="nt-race-info-button" type="button" onClick={() => setRaceOpen(true)}>!</button></span>} />
          <Row label="Ветка" value={profile.player?.branch || "—"} />
          <Row label="Уровень" value={profile.player?.level || 1} />
          <Row label="Баланс" value={profile.player?.balanceText || "0 мед."} />
        </div>
        <div className="nt-progress-label">Опыт: {xpCurrent} / {xpNext}</div>
        <div className="nt-progress"><i style={{ width: `${xpPercent}%` }} /></div>
      </Panel>
      <EquipmentPanel profile={profile} onOpenItem={onOpenItem} onOpenSlot={onOpenSlot} />
      <Panel title="Характеристики" right={<span className="nt-badge">Свободно: {freeStats}</span>}>
        <div className="nt-lines">
          {(profile.attributes || []).map((attribute) => (
            <Row key={attribute.key || attribute.label} label={attribute.label} value={attribute.value}>
              {freeStats > 0 ? (
                <div className="nt-attribute-controls">
                  <input type="number" min="1" max={freeStats} value={attributeAmounts[attribute.key] || 1} onChange={(event) => changeAttribute(attribute.key, event.target.value)} />
                  <button type="button" onClick={() => spend(attribute.key)}>+</button>
                </div>
              ) : null}
            </Row>
          ))}
        </div>
      </Panel>
      <Panel title="Параметры"><div className="nt-lines">{(profile.parameters || []).map((row) => <Row key={row.label} label={row.label} value={row.value} />)}</div></Panel>
      <Panel title="Активные сеты">
        {(profile.activeSets || []).length ? <div className="nt-column-list">{profile.activeSets.map((set) => <div key={set.name} className="nt-mini-card"><CardRow label={set.name} value="активен" /><p>{set.bonus}</p></div>)}</div> : <p className="nt-empty-text">Активных сетов нет.</p>}
      </Panel>
      {raceOpen ? <RaceInfoModal profile={profile} onClose={() => setRaceOpen(false)} /> : null}
    </div>
  );
}

function InventoryTab({ profile, onOpenItem }) {
  const [category, setCategory] = useState("Всё");
  const [query, setQuery] = useState("");
  const inventory = profile.inventory || [];
  const filtered = useMemo(() => inventory.filter((item) => {
    const categoryOk = category === "Всё" || item.category === category;
    const queryOk = !query || String(item.name || "").toLowerCase().includes(query.toLowerCase());
    return categoryOk && queryOk;
  }), [inventory, category, query]);

  return (
    <div className="nt-stack">
      <Panel title="Инвентарь">
        <div className="nt-toolbar">
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Поиск предмета" />
          <div className="nt-category-row">{INVENTORY_CATEGORIES.map((item) => <button key={item} className={category === item ? "active" : ""} type="button" onClick={() => setCategory(item)}>{item}</button>)}</div>
        </div>
        <div className="nt-icon-grid">
          {filtered.map((item) => (
            <button key={item.id || item.name} className={`nt-item-icon-card ${qualityClass(item.quality)}`} type="button" onClick={() => onOpenItem(item)}>
              <ItemArt item={item} />
              {item.amount > 1 ? <span className="nt-item-amount">×{item.amount}</span> : null}
              <span className="nt-item-name">{item.name}</span>
            </button>
          ))}
        </div>
        {!filtered.length ? <p className="nt-empty-text">Предметов не найдено.</p> : null}
      </Panel>
    </div>
  );
}

function ModifierHelpModal({ modifier, onClose }) {
  if (!modifier) return null;
  return (
    <div className="nt-modal-layer" onMouseDown={onClose}>
      <article className="nt-modal nt-small-modal" onMouseDown={(event) => event.stopPropagation()}>
        <button className="nt-modal-close" type="button" onClick={onClose}>×</button>
        <div className="nt-modal-kicker">Модификатор</div>
        <h3>{modifier.name || modifier.label}</h3>
        <p>{modifier.description || modifier.effect || "Описание модификатора пока не добавлено."}</p>
        <div className="nt-modal-grid"><span>Уровень</span><strong>{modifier.level || modifier.points || 0}</strong></div>
      </article>
    </div>
  );
}

function SkillUpgradeModal({ skill, freePoints, onClose, onSpendSkillPoints }) {
  const [amount, setAmount] = useState(1);
  const modifiers = skill?.modifiers || [];
  const [selectedModifier, setSelectedModifier] = useState(modifiers[0]?.id || modifiers[0]?.name || "main");
  if (!skill) return null;

  function submit() {
    onSpendSkillPoints?.(skill, selectedModifier, Math.max(1, Number(amount || 1)));
    onClose();
  }

  return (
    <div className="nt-modal-layer" onMouseDown={onClose}>
      <article className="nt-modal nt-small-modal" onMouseDown={(event) => event.stopPropagation()}>
        <button className="nt-modal-close" type="button" onClick={onClose}>×</button>
        <div className="nt-modal-kicker">Улучшение навыка</div>
        <h3>{skill.name}</h3>
        <p>Свободные очки навыков: {freePoints}</p>
        {modifiers.length ? (
          <label className="nt-field-label"><span>Модификатор</span><select value={selectedModifier} onChange={(event) => setSelectedModifier(event.target.value)}>{modifiers.map((modifier) => <option key={modifier.id || modifier.name} value={modifier.id || modifier.name}>{modifier.name || modifier.label}</option>)}</select></label>
        ) : null}
        <label className="nt-field-label"><span>Сколько очков вложить</span><input type="number" min="1" max={freePoints} value={amount} onChange={(event) => setAmount(event.target.value)} /></label>
        <footer className="nt-modal-actions"><button type="button" onClick={submit}>Вложить</button><button className="nt-secondary" type="button" onClick={onClose}>Отмена</button></footer>
      </article>
    </div>
  );
}

function SkillCard({ skill, freePoints, onShowModifier, onOpenUpgrade }) {
  const modifiers = skill.modifiers || [];
  const canUpgrade = freePoints > 0 && skill.upgradeable;
  const details = [skill.damage !== undefined && skill.damage !== null ? `Урон: ${skill.damage}` : null, skill.cooldown !== undefined && skill.cooldown !== null ? `Откат: ${skill.cooldown}` : null, skill.cost ? `Затраты: ${skill.cost}` : null].filter(Boolean);
  return (
    <article className="nt-skill-card">
      <div className="nt-skill-main">
        <h3>{skill.name}</h3>
        <p>{skill.description || "Описание навыка пока не добавлено."}</p>
        {details.length ? <div className="nt-skill-details">{details.map((detail) => <span key={detail}>{detail}</span>)}</div> : null}
        {modifiers.length ? <div className="nt-modifiers">{modifiers.map((modifier) => <button key={modifier.id || modifier.name} type="button" onClick={() => onShowModifier(modifier)}>{modifier.name || modifier.label} <b>{modifier.level || modifier.points || 0}</b></button>)}</div> : null}
      </div>
      <div className="nt-skill-side"><span>Уровень</span><strong>{skill.level || 0}</strong>{canUpgrade ? <button className="nt-skill-plus" type="button" onClick={() => onOpenUpgrade(skill)}>+</button> : null}</div>
    </article>
  );
}

function SkillsTab({ profile, onSpendSkillPoints }) {
  const [modifierHelp, setModifierHelp] = useState(null);
  const [upgradeSkill, setUpgradeSkill] = useState(null);
  const freePoints = profile.player?.freeSkillPoints || 0;
  const active = profile.skills?.active || [];
  const passive = profile.skills?.passive || [];
  return (
    <div className="nt-stack">
      <Panel title="Развитие" right={<span className="nt-badge">Свободно: {freePoints}</span>}><div className="nt-lines"><Row label="Свободные очки навыков" value={freePoints} /><Row label="Ветвь развития" value={profile.player?.branch || "—"} /></div></Panel>
      <Panel title="Активные навыки"><div className="nt-skills-list">{active.length ? active.map((skill) => <SkillCard key={skill.id || skill.name} skill={skill} freePoints={freePoints} onShowModifier={setModifierHelp} onOpenUpgrade={setUpgradeSkill} />) : <p className="nt-empty-text">Активных навыков пока нет.</p>}</div></Panel>
      <Panel title="Пассивные навыки"><div className="nt-skills-list">{passive.length ? passive.map((skill) => <SkillCard key={skill.id || skill.name} skill={skill} freePoints={freePoints} onShowModifier={setModifierHelp} onOpenUpgrade={setUpgradeSkill} />) : <p className="nt-empty-text">Пассивных навыков пока нет.</p>}</div></Panel>
      <ModifierHelpModal modifier={modifierHelp} onClose={() => setModifierHelp(null)} />
      <SkillUpgradeModal skill={upgradeSkill} freePoints={freePoints} onClose={() => setUpgradeSkill(null)} onSpendSkillPoints={onSpendSkillPoints} />
    </div>
  );
}

function InfoTab({ profile }) {
  const info = profile.information || {};
  const activity = info.activity || {};
  const crafts = activity.craftingLevels || [];
  return (
    <div className="nt-stack">
      <Panel title="Активность"><div className="nt-lines"><Row label="Дата регистрации" value={profile.player?.registrationDate || "—"} /><Row label="PVE убийства" value={activity.pveKills || 0} /><Row label="PVP убийства" value={activity.pvpKills || 0} /><Row label="Частицы душ" value={activity.soulParticlesAbsorbed || 0} /></div></Panel>
      <Panel title="Ремёсла"><div className="nt-card-list nt-column-list">{crafts.length ? crafts.map((craft) => <div key={craft.name} className="nt-mini-card"><CardRow label={craft.name} value={`ур. ${craft.level}`} /><p>{craft.exp}</p></div>) : <p className="nt-empty-text">Ремёсла пока не развиты.</p>}</div></Panel>
      <Panel title="Достижения"><div className="nt-card-list nt-column-list">{(info.achievements || []).length ? info.achievements.map((achievement) => <div key={achievement.name || achievement} className="nt-mini-card"><CardRow label={achievement.name || achievement} value="Получено" /><p>{achievement.description || "—"}</p></div>) : <p className="nt-empty-text">Достижений пока нет.</p>}</div></Panel>
    </div>
  );
}

export function PlayerProfile({ profile, onSpendAttributePoints, onSpendSkillPoints, onEquipItem, onUnequipItem, onUseItem }) {
  const data = profileOrMock(profile);
  const [tab, setTab] = useState("character");
  const [modal, setModal] = useState(null);
  const [slotModal, setSlotModal] = useState(null);
  const background = data.assets?.background || "/assets/profile/backgrounds/1.png";

  const equipmentBySlot = data.equipment || {};
  const inventory = data.inventory || [];

  function openItem(item, slotKey = null) {
    setModal({ item, slotKey });
  }

  function openSlot(slot) {
    const items = inventory.filter((item) => {
      const target = itemSlot(item);
      if (target === slot.key) return true;
      if ((slot.key === "ring1" || slot.key === "ring2") && (target === "ring" || item.type === "Кольцо" || item.type === "ring")) return true;
      return false;
    });
    setSlotModal({ slot, items, selectedItem: items[0] || null });
  }

  async function equipFromSlot(item) {
    await onEquipItem?.(item);
    setSlotModal(null);
  }

  async function equipAndClose(item) {
    await onEquipItem?.(item);
    setModal(null);
  }

  async function unequipAndClose(slotKey, item) {
    await onUnequipItem?.(slotKey || itemSlot(item), item);
    setModal(null);
  }

  async function useAndClose(item) {
    await onUseItem?.(item);
    setModal(null);
  }

  return (
    <main className="nt-profile" style={{ backgroundImage: `linear-gradient(rgba(5, 7, 7, .32), rgba(4, 4, 4, .50)), url(${background})` }}>
      <div className="nt-shell">
        <header className="nt-top">
          <div className="nt-title-block"><h1>Профиль персонажа</h1></div>
          <div className="nt-id">{data.player?.userGlobalId || data.player?.publicId || "NT-UNKNOWN"}</div>
        </header>
        <nav className="nt-tabs" aria-label="Разделы профиля">
          {TABS.map(({ id, label, icon }) => <button key={id} className={tab === id ? "active" : ""} type="button" onClick={() => setTab(id)} title={label} aria-label={label}><span className="nt-tab-icon">{icon}</span><span className="nt-tab-text">{label}</span></button>)}
        </nav>
        <section className="nt-content">
          {tab === "character" ? <CharacterTab profile={{ ...data, equipment: equipmentBySlot }} onOpenItem={openItem} onOpenSlot={openSlot} onSpendAttributePoints={onSpendAttributePoints} /> : null}
          {tab === "inventory" ? <InventoryTab profile={data} onOpenItem={openItem} /> : null}
          {tab === "skills" ? <SkillsTab profile={data} onSpendSkillPoints={onSpendSkillPoints} /> : null}
          {tab === "info" ? <InfoTab profile={data} /> : null}
        </section>
      </div>
      <ItemModal item={modal?.item} slotKey={modal?.slotKey} onClose={() => setModal(null)} onEquipItem={equipAndClose} onUnequipItem={unequipAndClose} onUseItem={useAndClose} />
      <SlotItemsModal slot={slotModal?.slot} items={slotModal?.items || []} selectedItem={slotModal?.selectedItem} onSelectItem={(item) => setSlotModal((current) => ({ ...current, selectedItem: item }))} onClose={() => setSlotModal(null)} onEquipItem={equipFromSlot} />
    </main>
  );
}

export default PlayerProfile;
