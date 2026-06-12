import React, { useEffect, useMemo, useState } from "react";
import { profileMockData } from "./profileMockData.js";

const TABS = [
  { id: "character", label: "Персонаж", icon: "head" },
  { id: "inventory", label: "Инвентарь", icon: "bag" },
  { id: "skills", label: "Навыки", icon: "star" },
  { id: "info", label: "Информация", icon: "scroll" },
];

const INVENTORY_CATEGORIES = ["Всё", "Снаряжение", "Оружие", "Бижутерия", "Расходники", "Ресурсы", "Материалы", "Добыча", "Прочее", "Особое"];

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
  { key: "arrow_quiver", label: "Колчан стрел" },
  { key: "bolt_quiver", label: "Колчан болтов" },
  { key: "special", label: "Особый слот" },
];

const RACE_INFO = {
  human: {
    name: "Человек",
    stats: "Сила 3 · Ловкость 3 · Выносливость 4 · Интеллект 3 · Мудрость 3 · Восприятие 4",
    bonuses: ["Возврат золота у NPC", "+2% получаемого опыта", "+1% к основным характеристикам"],
  },
  elf: {
    name: "Эльф",
    stats: "Сила 2 · Ловкость 4 · Выносливость 2 · Интеллект 5 · Мудрость 4 · Восприятие 3",
    bonuses: ["+3% наносимого магического урона", "+4% к алхимии", "+3% к сбору алхимических ингредиентов"],
  },
  dwarf: {
    name: "Дворф",
    stats: "Сила 5 · Ловкость 2 · Выносливость 5 · Интеллект 3 · Мудрость 3 · Восприятие 2",
    bonuses: ["+4% к созданию оружия и брони", "-3% расхода руды и металла при создании снаряжения и оружия", "+3% к выносливости"],
  },
  undead: {
    name: "Нежить",
    stats: "Сила 3 · Ловкость 2 · Выносливость 6 · Интеллект 3 · Мудрость 4 · Восприятие 2",
    bonuses: ["+4% к здоровью", "-5% шанс получить негативный эффект", "-3% получаемого периодического урона"],
  },
  lizardfolk: {
    name: "Ящеролюд",
    stats: "Сила 4 · Ловкость 4 · Выносливость 4 · Интеллект 1 · Мудрость 2 · Восприятие 5",
    bonuses: ["0.5% регенерации HP в бою", "-2% получаемого физического урона", "+4% к поиску добычи и ресурсов"],
  },
};

const RACE_NAME_TO_KEY = {
  человек: "human",
  эльф: "elf",
  дворф: "dwarf",
  нежить: "undead",
  ящеролюд: "lizardfolk",
};

function TabIcon({ type }) {
  const common = {
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: "1.7",
    strokeLinecap: "round",
    strokeLinejoin: "round",
    "aria-hidden": "true",
    focusable: "false",
  };
  if (type === "bag") {
    return (
      <svg {...common}>
        <path d="M7.5 9.2h9l1.1 10.1H6.4L7.5 9.2Z" />
        <path d="M9 9.2V7.8a3 3 0 0 1 6 0v1.4" />
        <path d="M8.4 13.2h7.2" />
      </svg>
    );
  }
  if (type === "star") {
    return (
      <svg {...common}>
        <path d="m12 3.8 2.3 5 5.2.7-3.8 3.7.9 5.3L12 16l-4.6 2.5.9-5.3-3.8-3.7 5.2-.7L12 3.8Z" />
        <path d="M12 8.3v4.2" />
      </svg>
    );
  }
  if (type === "scroll") {
    return (
      <svg {...common}>
        <path d="M7.8 4.4h8.1a2.4 2.4 0 0 1 2.4 2.4v11.5" />
        <path d="M7.8 4.4a2.4 2.4 0 0 0-2.4 2.4v11a1.8 1.8 0 0 0 1.8 1.8h8.3" />
        <path d="M8.4 9.2h6.2M8.4 12.3h5.4M8.4 15.4h4.2" />
        <path d="M15.5 19.6a2.1 2.1 0 0 0 2.1-2.1h-4.2a2.1 2.1 0 0 0 2.1 2.1Z" />
      </svg>
    );
  }
  return (
    <svg {...common}>
      <path d="M12 12.1a3.7 3.7 0 1 0 0-7.4 3.7 3.7 0 0 0 0 7.4Z" />
      <path d="M5.2 20.2a6.8 6.8 0 0 1 13.6 0" />
      <path d="M8.7 15.6c.9.6 1.9.9 3.3.9s2.4-.3 3.3-.9" />
    </svg>
  );
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(value, max));
}

function getProfileBounds(target, gap) {
  if (typeof window === "undefined") {
    return { left: gap, top: gap, right: 560, bottom: 720, width: 560, height: 720 };
  }

  const viewportWidth = window.innerWidth || document.documentElement.clientWidth || 360;
  const viewportHeight = window.innerHeight || document.documentElement.clientHeight || 640;
  const shell = target?.closest?.(".nt-shell");
  const rect = shell?.getBoundingClientRect?.();

  const rawBounds = rect && rect.width > 0 && rect.height > 0
    ? rect
    : { left: 0, top: 0, right: viewportWidth, bottom: viewportHeight, width: viewportWidth, height: viewportHeight };

  const left = clamp(rawBounds.left, gap, viewportWidth - gap);
  const top = clamp(rawBounds.top, gap, viewportHeight - gap);
  const right = clamp(rawBounds.right, left + 1, viewportWidth - gap);
  const bottom = clamp(rawBounds.bottom, top + 1, viewportHeight - gap);

  return { left, top, right, bottom, width: right - left, height: bottom - top };
}

function getFloatingPosition(event, preferredWidth = 500, preferredHeight = 420) {
  if (!event?.currentTarget || typeof window === "undefined") {
    return null;
  }

  const target = event.currentTarget;
  const anchor = target.getBoundingClientRect();
  const gap = 8;
  const bounds = getProfileBounds(target, gap);
  const viewportWidth = window.innerWidth || document.documentElement.clientWidth || preferredWidth;
  const isMobile = viewportWidth <= 560;

  const modalWidth = Math.max(260, Math.min(preferredWidth, bounds.width - gap * 2));
  const modalMaxHeight = Math.max(220, Math.min(preferredHeight, bounds.height - gap * 2));

  let left;
  if (isMobile || bounds.width < preferredWidth + gap * 2) {
    left = bounds.left + gap;
  } else {
    left = anchor.right + gap;
    if (left + modalWidth > bounds.right - gap) {
      left = anchor.left - modalWidth - gap;
    }
  }
  left = clamp(left, bounds.left + gap, bounds.right - modalWidth - gap);

  let top = anchor.top;
  const preferredBottom = anchor.bottom + gap;
  const preferredAbove = anchor.top - modalMaxHeight - gap;

  if (isMobile) {
    top = preferredBottom;
    if (top + modalMaxHeight > bounds.bottom - gap) {
      top = preferredAbove;
    }
  } else if (top + modalMaxHeight > bounds.bottom - gap && preferredAbove >= bounds.top + gap) {
    top = preferredAbove;
  }

  top = clamp(top, bounds.top + gap, bounds.bottom - modalMaxHeight - gap);

  return {
    top,
    left,
    width: modalWidth,
    maxHeight: modalMaxHeight,
  };
}

function floatingModalStyle(position) {
  if (!position) return undefined;
  return {
    "--nt-modal-top": `${Math.round(position.top)}px`,
    "--nt-modal-left": `${Math.round(position.left)}px`,
    "--nt-modal-width": `${Math.round(position.width)}px`,
    "--nt-modal-max-height": `${Math.round(position.maxHeight)}px`,
    "--nt-modal-right": "auto",
  };
}


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

function itemSellPriceText(item) {
  const text = item?.sellPriceText ?? item?.sell_price_text ?? item?.sellPriceFormatted ?? item?.sell_price_formatted;
  if (text) return text;

  const canSell = item?.canSell ?? item?.can_sell;
  if (canSell === false) return "не продаётся";

  const rawPrice = item?.sellPriceCopper ?? item?.sell_price_copper ?? item?.sellPrice ?? item?.sell_price;
  if (rawPrice === undefined || rawPrice === null || rawPrice === "") return "";

  const price = Number(rawPrice);
  if (!Number.isFinite(price) || price < 0) return "";
  return `${price} медных`;
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
    arrow_quiver: "Колчан стрел",
    bolt_quiver: "Колчан болтов",
    special: "Особый слот",
  };
  return map[slotKey] || slotKey || "—";
}

function inventoryCapacity(profile) {
  return Number(
    profile.player?.inventoryCapacity ??
    profile.player?.maxInventorySlots ??
    profile.inventoryCapacity ??
    profile.inventory?.capacity ??
    20
  ) || 20;
}

function inventoryUsedSlots(inventory) {
  return Array.isArray(inventory) ? inventory.length : 0;
}

function inventoryFreeSlots(profile, inventory) {
  const capacity = inventoryCapacity(profile);
  const used = Number(
    profile.player?.inventoryUsedSlots ??
    profile.inventoryUsedSlots ??
    inventoryUsedSlots(inventory)
  ) || 0;
  return Math.max(0, capacity - used);
}

function skillKey(skill) {
  return String(skill?.id || skill?.name || "").trim();
}

function itemKey(item, fallbackIndex = 0) {
  const base = item?.id || item?.item_id || item?.name || "item";
  const index = Number.isInteger(item?.inventoryIndex) ? item.inventoryIndex : fallbackIndex;
  return `${base}-${index}`;
}

function hasConcentrationText(value) {
  const text = String(value || "").toLowerCase();
  return text.includes("концентрац") || text.includes("concentration");
}

function skillCostText(skill) {
  const rawText = skill?.resourceText || skill?.cost;
  if (rawText && !hasConcentrationText(rawText)) return rawText;
  const mana = Number(skill?.mana_cost ?? skill?.manaCost ?? 0);
  const spirit = Number(skill?.spirit_cost ?? skill?.spiritCost ?? 0);
  const parts = [];
  if (mana > 0) parts.push(`Мана: ${mana}`);
  if (spirit > 0) parts.push(`Дух: ${spirit}`);
  if (!parts.length) return "Расход: не требует маны и духа";
  return `Расход: ${parts.join(" · ")}`;
}

function skillCooldownText(skill) {
  if (skill?.cooldownText) return skill.cooldownText;
  const turns = Number(skill?.cooldown_turns ?? skill?.cooldownTurns ?? skill?.cooldown ?? 0) || 0;
  return `Откат: ${turns} ходов`;
}

function isPassiveSkill(skill) {
  const rawType = String(skill?.skill_type || skill?.type || "").toLowerCase();
  return rawType === "passive" || rawType === "пассивный";
}

function canEquipSkill(skill) {
  if (!skill) return false;
  if (skill.equippable === false) return false;
  if (isPassiveSkill(skill)) return Boolean(skill.equippable);
  return true;
}

function skillEquipCapacity(profile) {
  return Number(profile.player?.skillEquipCapacity ?? profile.player?.maxEquippedSkills ?? 2) || 2;
}

function skillEquipUsed(profile, equipped) {
  return Number(profile.player?.skillEquipUsed ?? equipped.length ?? 0) || 0;
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


function effectSummary(effects = []) {
  const list = Array.isArray(effects) ? effects : [];
  if (!list.length) return "нет";
  const positive = list.filter((effect) => effect?.kind === "positive").length;
  const negative = list.filter((effect) => effect?.kind === "negative").length;
  const parts = [];
  if (positive) parts.push(`+${positive}`);
  if (negative) parts.push(`-${negative}`);
  const neutral = list.length - positive - negative;
  if (neutral) parts.push(`${neutral}`);
  return parts.length ? parts.join(" / ") : `${list.length}`;
}

function effectExpiresText(effect) {
  if (!effect?.expiresAt) return "постоянно";
  const date = new Date(effect.expiresAt);
  if (Number.isNaN(date.getTime())) return String(effect.expiresAt);
  return date.toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

function EffectsPopover({ effects = [], onClose }) {
  const list = Array.isArray(effects) ? effects : [];
  return (
    <aside className="nt-race-popover nt-effects-popover" role="dialog" aria-label="Активные эффекты">
      <button className="nt-popover-close" type="button" onClick={onClose} aria-label="Закрыть">×</button>
      <div className="nt-modal-kicker">Активные эффекты</div>
      <h3>Эффекты персонажа</h3>
      {list.length ? (
        <div className="nt-effects-list">
          {list.map((effect, index) => (
            <article className={`nt-effect-card ${effect.kind === "negative" ? "negative" : effect.kind === "positive" ? "positive" : "neutral"}`} key={effect.id || effect.name || index}>
              <div className="nt-effect-title-row">
                <strong>{effect.name || "Активный эффект"}</strong>
                <span>{effect.kind === "negative" ? "штраф" : effect.kind === "positive" ? "бонус" : "эффект"}</span>
              </div>
              <p>{effect.description || "Описание эффекта пока не добавлено."}</p>
              {Array.isArray(effect.modifiers) && effect.modifiers.length ? (
                <ul>{effect.modifiers.map((modifier) => <li key={modifier.key || modifier.text}>{modifier.text}</li>)}</ul>
              ) : null}
              <small>Действует: {effectExpiresText(effect)}</small>
            </article>
          ))}
        </div>
      ) : <p className="nt-empty-text">Активных положительных или отрицательных эффектов нет.</p>}
    </aside>
  );
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

function RaceInfoPopover({ profile, onClose }) {
  if (!profile) return null;
  const race = RACE_INFO[raceKey(profile.player)] || RACE_INFO.human;
  return (
    <aside className="nt-race-popover" role="dialog" aria-label="Бонусы расы">
      <button className="nt-popover-close" type="button" onClick={onClose} aria-label="Закрыть">×</button>
      <div className="nt-modal-kicker">Бонусы расы</div>
      <h3>{race.name}</h3>
      <div className="nt-modal-block">
        <h4>Стартовые характеристики</h4>
        <p className="nt-race-stats">{race.stats}</p>
      </div>
      <div className="nt-modal-block">
        <h4>Бонусы</h4>
        <ul>{race.bonuses.map((bonus) => <li key={bonus}>{bonus}</li>)}</ul>
      </div>
    </aside>
  );
}

function ItemModal({ item, slotKey, position, readOnly = false, onClose, onEquipItem, onUnequipItem, onUseItem, onRequestDrop, onRequestSell }) {
  if (!item) return null;
  const actions = item.actions || [];
  const itemStats = statLines(item);
  const sellPriceText = itemSellPriceText(item);
  return (
    <div className="nt-modal-layer" onMouseDown={onClose}>
      <article className={`nt-modal ${qualityClass(item.quality)}`} style={floatingModalStyle(position)} onMouseDown={(event) => event.stopPropagation()}>
        <button className="nt-modal-close" type="button" onClick={onClose}>×</button>
        <div className="nt-modal-kicker">{item.category || "Предмет"}</div>
        <div className="nt-modal-title-row">
          <span className="nt-modal-item-icon"><ItemArt item={item} /></span>
          <div>
            <h3>{item.name || "Предмет"}</h3>
            <div className="nt-modal-subtitle">{item.quality || "обычный"}{item.level ? ` · ур. ${item.level}` : ""}</div>
          </div>
        </div>
        <div className="nt-modal-grid">
          <span>Тип</span><strong>{item.type || item.category || "—"}</strong>
          <span>Слот</span><strong>{compactSlotName(slotKey || itemSlot(item))}</strong>
          <span>Количество</span><strong>×{item.amount || 1}</strong>
          {sellPriceText ? <><span>Цена продажи</span><strong>{sellPriceText}</strong></> : null}
        </div>
        <p>{item.description || "Описание предмета пока не добавлено."}</p>
        {itemStats.length ? <div className="nt-modal-block"><h4>Свойства</h4><StatLines lines={itemStats} /></div> : null}
        {Array.isArray(item.enchantments) && item.enchantments.length ? (
          <div className="nt-modal-block"><h4>Зачарования</h4><StatLines lines={item.enchantments} /></div>
        ) : null}
        <footer className="nt-modal-actions">
          {!readOnly && (actions.includes("Надеть") || (!slotKey && itemSlot(item))) ? <button type="button" onClick={() => onEquipItem?.(item)}>Надеть</button> : null}
          {!readOnly && (actions.includes("Снять") || slotKey) ? <button type="button" onClick={() => onUnequipItem?.(slotKey || itemSlot(item), item)}>Снять</button> : null}
          {!readOnly && actions.includes("Использовать") ? <button type="button" onClick={() => onUseItem?.(item)}>Использовать</button> : null}
          {!readOnly && !slotKey && actions.includes("Продать") ? <button type="button" onClick={() => onRequestSell?.(item)}>Продать</button> : null}
          {!readOnly && !slotKey ? <button className="nt-danger" type="button" onClick={() => onRequestDrop?.(item)}>Выбросить</button> : null}
          {readOnly ? <span className="nt-readonly-note">Только просмотр</span> : null}
          <button className="nt-secondary" type="button" onClick={onClose}>Закрыть</button>
        </footer>
      </article>
    </div>
  );
}

function DropItemModal({ item, position, onClose, onConfirm }) {
  const maxAmount = Math.max(1, Number(item?.amount || 1));
  const [amount, setAmount] = useState(1);
  if (!item) return null;

  function submit() {
    onConfirm?.(item, clamp(Number(amount) || 1, 1, maxAmount));
  }

  return (
    <div className="nt-modal-layer" onMouseDown={onClose}>
      <article className="nt-modal nt-small-modal" style={floatingModalStyle(position)} onMouseDown={(event) => event.stopPropagation()}>
        <button className="nt-modal-close" type="button" onClick={onClose}>×</button>
        <div className="nt-modal-kicker">Выброс предмета</div>
        <h3>{item.name}</h3>
        <p>Доступно: ×{maxAmount}</p>
        <label className="nt-field-label">
          <span>Количество</span>
          <input type="number" min="1" max={maxAmount} value={amount} onChange={(event) => setAmount(event.target.value)} autoFocus />
        </label>
        <footer className="nt-modal-actions">
          <button className="nt-danger" type="button" onClick={submit}>Выбросить</button>
          <button className="nt-secondary" type="button" onClick={onClose}>Отмена</button>
        </footer>
      </article>
    </div>
  );
}

function SellItemModal({ item, position, onClose, onConfirm }) {
  const maxAmount = Math.max(1, Number(item?.amount || 1));
  const [amount, setAmount] = useState(1);
  const sellPriceText = itemSellPriceText(item);
  if (!item) return null;

  function submit() {
    onConfirm?.(item, clamp(Number(amount) || 1, 1, maxAmount));
  }

  return (
    <div className="nt-modal-layer" onMouseDown={onClose}>
      <article className="nt-modal nt-small-modal" style={floatingModalStyle(position)} onMouseDown={(event) => event.stopPropagation()}>
        <button className="nt-modal-close" type="button" onClick={onClose}>×</button>
        <div className="nt-modal-kicker">Продажа на рынке</div>
        <h3>{item.name}</h3>
        <p>Введите количество продаваемых предметов.</p>
        <div className="nt-modal-grid">
          <span>Доступно</span><strong>×{maxAmount}</strong>
          {sellPriceText ? <><span>Цена за 1</span><strong>{sellPriceText}</strong></> : null}
        </div>
        <label className="nt-field-label">
          <span>Количество</span>
          <input type="number" min="1" max={maxAmount} value={amount} onChange={(event) => setAmount(event.target.value)} autoFocus />
        </label>
        <footer className="nt-modal-actions">
          <button type="button" onClick={submit}>Продать</button>
          <button className="nt-secondary" type="button" onClick={onClose}>Отмена</button>
        </footer>
      </article>
    </div>
  );
}

function SlotItemsModal({ slot, items, selectedItem, position, readOnly = false, onSelectItem, onClose, onEquipItem }) {
  if (!slot) return null;
  return (
    <div className="nt-modal-layer" onMouseDown={onClose}>
      <article className="nt-modal nt-slot-modal" style={floatingModalStyle(position)} onMouseDown={(event) => event.stopPropagation()}>
        <button className="nt-modal-close" type="button" onClick={onClose}>×</button>
        <div className="nt-modal-kicker">Пустой слот</div>
        <h3>{slot.label}</h3>
        {items.length ? (
          <div className="nt-slot-modal-grid">
            <div className="nt-slot-items-list">
              {items.map((item, index) => (
                <button key={itemKey(item, index)} className={`nt-slot-choice ${selectedItem?.inventoryIndex === item.inventoryIndex ? "active" : ""} ${qualityClass(item.quality)}`} type="button" onClick={() => onSelectItem(item)}>
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
                    {!readOnly ? <button type="button" onClick={() => onEquipItem?.(selectedItem)}>Надеть</button> : <span className="nt-readonly-note">Только просмотр</span>}
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

function EquipmentPanel({ profile, readOnly = false, onOpenItem, onOpenSlot }) {
  const slots = profile.equipmentSlots?.length ? profile.equipmentSlots : DEFAULT_SLOTS;
  const equipment = profile.equipment || {};
  return (
    <Panel title="Экипировка">
      <div className="nt-equipment-grid">
        {slots.map((slot) => {
          const item = equipment[slot.key];
          const blocked = Boolean(slot.blocked) && !item;
          const slotClass = [`nt-equip-slot`, item ? qualityClass(item.quality) : "empty", blocked ? "blocked" : ""].filter(Boolean).join(" ");
          return (
            <button
              key={slot.key}
              className={slotClass}
              type="button"
              disabled={blocked}
              title={blocked ? slot.blockedReason || "Слот заблокирован" : undefined}
              onClick={(event) => item ? onOpenItem(item, slot.key, event) : (!readOnly ? onOpenSlot(slot, event) : null)}
            >
              <ItemArt item={item} fallback={blocked ? "×" : "+"} className="nt-equip-art" />
              {blocked ? <span className="nt-slot-blocked-badge">блок</span> : null}
              <span className="nt-equip-label">{item?.name || slot.statusLabel || slot.label}</span>
            </button>
          );
        })}
      </div>
    </Panel>
  );
}

function RaceRow({ profile }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="nt-row nt-race-row">
      <span>Раса</span>
      <strong className="nt-race-cell">
        <span className="nt-race-value">{profile.player?.raceName || "—"}</span>
        <button className="nt-race-info-button" type="button" onClick={() => setOpen((value) => !value)} aria-expanded={open} aria-label="Показать бонусы расы">!</button>
      </strong>
      {open ? <RaceInfoPopover profile={profile} onClose={() => setOpen(false)} /> : null}
    </div>
  );
}


function EffectsRow({ profile }) {
  const [open, setOpen] = useState(false);
  const effects = Array.isArray(profile.effects) ? profile.effects : [];
  return (
    <div className="nt-row nt-effects-row">
      <span>Эффекты</span>
      <strong className="nt-race-cell">
        <span className="nt-race-value">{effectSummary(effects)}</span>
        <button className="nt-race-info-button" type="button" onClick={() => setOpen((value) => !value)} aria-expanded={open} aria-label="Показать активные эффекты">!</button>
      </strong>
      {open ? <EffectsPopover effects={effects} onClose={() => setOpen(false)} /> : null}
    </div>
  );
}

function CharacterTab({ profile, readOnly = false, onOpenItem, onOpenSlot, onConfirmAttributePoints }) {
  const [attributeAmounts, setAttributeAmounts] = useState({});
  const [pendingAttributes, setPendingAttributes] = useState({});
  const xpCurrent = Number(profile.player?.experienceCurrent || 0);
  const xpNext = Math.max(1, Number(profile.player?.experienceToNext || 1));
  const xpPercent = Math.min(100, Math.max(0, Math.round((xpCurrent / xpNext) * 100)));
  const freeStats = Number(profile.player?.freeAttributePoints || 0);
  const pendingTotal = Object.values(pendingAttributes).reduce((sum, value) => sum + Math.max(0, Number(value || 0)), 0);
  const remainingFreeStats = Math.max(0, freeStats - pendingTotal);
  const hasPendingAttributes = pendingTotal > 0;

  function changeAttribute(key, value) {
    const maxValue = Math.max(1, remainingFreeStats + Math.max(0, Number(pendingAttributes[key] || 0)));
    setAttributeAmounts((current) => ({ ...current, [key]: clamp(Number(value) || 1, 1, maxValue) }));
  }

  function spend(attributeKey) {
    const currentPending = Math.max(0, Number(pendingAttributes[attributeKey] || 0));
    const maxAdd = remainingFreeStats;
    if (maxAdd <= 0) return;
    const amount = clamp(Math.max(1, Number(attributeAmounts[attributeKey] || 1)), 1, maxAdd);
    setPendingAttributes((current) => ({ ...current, [attributeKey]: currentPending + amount }));
  }

  function resetPendingAttributes() {
    setPendingAttributes({});
  }

  async function confirmPendingAttributes() {
    if (!hasPendingAttributes) return;
    const allocations = Object.fromEntries(Object.entries(pendingAttributes).filter(([, value]) => Number(value) > 0));
    await onConfirmAttributePoints?.(allocations);
    // Clear staged points only after the API action really succeeds.
    setPendingAttributes({});
  }

  return (
    <div className="nt-stack">
      <Panel title="Сводка">
        <div className="nt-lines">
          <Row label="Имя" value={profile.player?.nickname || "—"} />
          <RaceRow profile={profile} />
          <Row label="Уровень" value={profile.player?.level || 1} />
          <Row label="Баланс" value={profile.player?.balanceText || "0 мед."} />
          <EffectsRow profile={profile} />
        </div>
        <div className="nt-progress-label">Опыт: {xpCurrent} / {xpNext}</div>
        <div className="nt-progress"><i style={{ width: `${xpPercent}%` }} /></div>
      </Panel>
      <EquipmentPanel profile={profile} readOnly={readOnly} onOpenItem={onOpenItem} onOpenSlot={onOpenSlot} />
      <Panel title="Характеристики" right={<span className="nt-badge">Свободно: {remainingFreeStats}</span>}>
        <div className="nt-lines">
          {(profile.attributes || []).map((attribute) => {
            const pending = Math.max(0, Number(pendingAttributes[attribute.key] || 0));
            const displayValue = pending > 0 ? `${attribute.value} + ${pending}` : attribute.value;
            return (
              <Row key={attribute.key || attribute.label} label={attribute.label} value={displayValue}>
                {!readOnly && remainingFreeStats > 0 ? (
                  <div className="nt-attribute-controls">
                    <input type="number" min="1" max={Math.max(1, remainingFreeStats)} value={attributeAmounts[attribute.key] || 1} onChange={(event) => changeAttribute(attribute.key, event.target.value)} />
                    <button type="button" onClick={() => spend(attribute.key)}>+</button>
                  </div>
                ) : null}
              </Row>
            );
          })}
        </div>
        {!readOnly && hasPendingAttributes ? (
          <div className="nt-attribute-actions">
            <button type="button" className="nt-secondary-button" onClick={resetPendingAttributes}>Сбросить</button>
            <button type="button" className="nt-primary-button" onClick={confirmPendingAttributes}>Подтвердить</button>
          </div>
        ) : null}
      </Panel>
      <Panel title="Параметры"><div className="nt-lines">{(profile.parameters || []).map((row) => <Row key={row.label} label={row.label} value={row.value} />)}</div></Panel>
      <Panel title="Активные сеты">
        {(profile.activeSets || []).length ? <div className="nt-column-list">{profile.activeSets.map((set) => <div key={set.name} className="nt-mini-card"><CardRow label={set.name} value="активен" /><p>{set.bonus}</p></div>)}</div> : <p className="nt-empty-text">Активных сетов нет.</p>}
      </Panel>
    </div>
  );
}

function InventoryTab({ profile, onOpenItem }) {
  const [category, setCategory] = useState("Всё");
  const [query, setQuery] = useState("");
  const inventory = profile.inventory || [];
  const freeSlots = inventoryFreeSlots(profile, inventory);
  const capacity = inventoryCapacity(profile);
  const filtered = useMemo(() => inventory.filter((item) => {
    const categoryOk = category === "Всё" || item.category === category || (category === "Материалы" && item.isMaterial);
    const queryOk = !query || String(item.name || "").toLowerCase().includes(query.toLowerCase());
    return categoryOk && queryOk;
  }), [inventory, category, query]);

  return (
    <div className="nt-stack">
      <Panel title="Инвентарь" right={<span className="nt-badge">Свободно: {freeSlots} / {capacity}</span>}>
        {!profile.readOnly && !profile.adminView && profile.market?.sellFromProfile ? <p className="nt-market-sell-hint">Вы на рынке в разделе продажи: откройте предмет и нажмите «Продать».</p> : null}
        <div className="nt-toolbar">
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Поиск предмета" />
          <div className="nt-category-row">{INVENTORY_CATEGORIES.map((item) => <button key={item} className={category === item ? "active" : ""} type="button" onClick={() => setCategory(item)}>{item}</button>)}</div>
        </div>
        <div className="nt-icon-grid">
          {filtered.map((item, index) => (
            <button key={itemKey(item, index)} className={`nt-item-icon-card ${qualityClass(item.quality)} ${item.overflowSlot ? "overflow-slot" : ""}`.trim()} type="button" onClick={(event) => onOpenItem(item, null, event)}>
              <ItemArt item={item} />
              {item.amount > 1 ? <span className="nt-item-amount">×{item.amount}</span> : null}
              {item.overflowSlot ? <span className="nt-overflow-badge">доп</span> : null}
              <span className="nt-item-name">{item.name}</span>
            </button>
          ))}
        </div>
        {!filtered.length ? <p className="nt-empty-text">Предметов не найдено.</p> : null}
      </Panel>
    </div>
  );
}

function ModifierHelpModal({ modifier, position, onClose }) {
  if (!modifier) return null;
  return (
    <div className="nt-modal-layer" onMouseDown={onClose}>
      <article className="nt-modal nt-small-modal" style={floatingModalStyle(position)} onMouseDown={(event) => event.stopPropagation()}>
        <button className="nt-modal-close" type="button" onClick={onClose}>×</button>
        <div className="nt-modal-kicker">Модификатор</div>
        <h3>{modifier.name || modifier.label}</h3>
        <p>{modifier.description || modifier.effect || "Описание модификатора пока не добавлено."}</p>
        <div className="nt-modal-grid"><span>Уровень</span><strong>{modifier.level || modifier.points || 0}</strong></div>
      </article>
    </div>
  );
}

function SkillUpgradeModal({ skill, freePoints, position, onClose, onSpendSkillPoints }) {
  const [amount, setAmount] = useState(1);
  const modifiers = skill?.modifiers || [];
  const [selectedModifier, setSelectedModifier] = useState(modifiers[0]?.id || modifiers[0]?.name || "main");
  useEffect(() => {
    setSelectedModifier(modifiers[0]?.id || modifiers[0]?.name || "main");
    setAmount(1);
  }, [skill?.id, skill?.name]);
  if (!skill) return null;

  function submit() {
    onSpendSkillPoints?.(skill, selectedModifier, Math.max(1, Number(amount || 1)));
    onClose();
  }

  return (
    <div className="nt-modal-layer" onMouseDown={onClose}>
      <article className="nt-modal nt-small-modal" style={floatingModalStyle(position)} onMouseDown={(event) => event.stopPropagation()}>
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

function SkillCard({ skill, freePoints, mode = "available", readOnly = false, onShowModifier, onOpenUpgrade, onEquipSkill, onUnequipSkill }) {
  const modifiers = skill.modifiers || [];
  const canUpgrade = !readOnly && freePoints > 0 && skill.upgradeable;
  const details = [
    skill.damage !== undefined && skill.damage !== null ? `Урон: ${skill.damage}` : null,
    skillCostText(skill),
    skillCooldownText(skill),
  ].filter(Boolean);
  const actionLabel = mode === "equipped" ? "Снять" : "Использовать";
  const actionHandler = mode === "equipped" ? onUnequipSkill : onEquipSkill;
  const showAction = !readOnly && (mode === "equipped" || canEquipSkill(skill));
  return (
    <article className="nt-skill-card">
      <div className="nt-skill-main">
        <h3>{skill.name}</h3>
        <p>{skill.description || "Описание навыка пока не добавлено."}</p>
        {details.length ? <div className="nt-skill-details">{details.map((detail) => <span key={detail}>{detail}</span>)}</div> : null}
        {modifiers.length ? <div className="nt-modifiers">{modifiers.map((modifier) => <button key={modifier.id || modifier.name} type="button" onClick={(event) => onShowModifier(modifier, event)}>{modifier.name || modifier.label} <b>{modifier.level || modifier.points || 0}</b></button>)}</div> : null}
      </div>
      <div className="nt-skill-side">
        <div className="nt-skill-level"><span>Уровень</span><strong>{skill.level || 0}</strong></div>
        {canUpgrade ? <button className="nt-skill-plus" type="button" onClick={(event) => onOpenUpgrade(skill, event)}>+</button> : null}
        {showAction ? <button className="nt-skill-action" type="button" onClick={() => actionHandler?.(skill)}>{actionLabel}</button> : null}
      </div>
    </article>
  );
}

function SkillsTab({ profile, readOnly = false, onSpendSkillPoints, onEquipSkill, onUnequipSkill }) {
  const [modifierHelp, setModifierHelp] = useState(null);
  const [upgradeSkill, setUpgradeSkill] = useState(null);
  const freePoints = profile.player?.freeSkillPoints || 0;
  const equipped = profile.skills?.equipped || [];
  const equippedKeys = new Set(equipped.map(skillKey));
  const active = (profile.skills?.active || []).filter((skill) => !equippedKeys.has(skillKey(skill)));
  const passive = (profile.skills?.passive || []).filter((skill) => !equippedKeys.has(skillKey(skill)));
  const sharedProps = {
    freePoints,
    readOnly,
    onShowModifier: (modifier, event) => setModifierHelp({ modifier, position: getFloatingPosition(event, 360, 300) }),
    onOpenUpgrade: !readOnly ? (skillToUpgrade, event) => setUpgradeSkill({ skill: skillToUpgrade, position: getFloatingPosition(event, 390, 360) }) : undefined,
    onEquipSkill: !readOnly ? onEquipSkill : undefined,
    onUnequipSkill: !readOnly ? onUnequipSkill : undefined,
  };
  const equipCapacity = skillEquipCapacity(profile);
  const equipUsed = skillEquipUsed(profile, equipped);
  const emptySlots = Math.max(0, equipCapacity - equipUsed);
  return (
    <div className="nt-stack">
      <Panel title="Навыки">
        <div className="nt-lines">
          <Row label="Свободные очки навыков" value={freePoints} />
          <Row label="Ветка" value={profile.player?.skillBranch || "Без ветви"} />
          <Row label="Основной путь" value={profile.player?.mainSkillPath ? `${profile.player.mainSkillPath} · ур. ${profile.player.mainSkillPathLevel || 0}` : "не выбран"} />
          <Row label="Дополнительный путь" value={profile.player?.secondarySkillPath ? `${profile.player.secondarySkillPath} · ур. ${profile.player.secondarySkillPathLevel || 0} / лимит ${profile.player.secondarySkillPathLimit || 0}` : "не выбран"} />
        </div>
      </Panel>
      <Panel title="Экипированные" right={<span className="nt-badge">{equipUsed} / {equipCapacity}</span>}>
        <div className="nt-skills-list nt-equipped-skills-list">
          {equipped.map((skill) => <SkillCard key={skill.id || skill.name} skill={skill} mode="equipped" {...sharedProps} />)}
          {Array.from({ length: emptySlots }).map((_, index) => (
            <div className="nt-empty-skill-slot" key={`empty-skill-${index}`}>
              <span>Слот навыка {equipUsed + index + 1}</span>
              <strong>пусто</strong>
            </div>
          ))}
        </div>
      </Panel>
      <Panel title="Активные навыки"><div className="nt-skills-list">{active.length ? active.map((skill) => <SkillCard key={skill.id || skill.name} skill={skill} mode="available" {...sharedProps} />) : <p className="nt-empty-text">Активных навыков пока нет.</p>}</div></Panel>
      <Panel title="Пассивные навыки"><div className="nt-skills-list">{passive.length ? passive.map((skill) => <SkillCard key={skill.id || skill.name} skill={skill} mode="available" {...sharedProps} />) : <p className="nt-empty-text">Пассивных навыков пока нет.</p>}</div></Panel>
      <ModifierHelpModal modifier={modifierHelp?.modifier} position={modifierHelp?.position} onClose={() => setModifierHelp(null)} />
      {!readOnly ? <SkillUpgradeModal skill={upgradeSkill?.skill} freePoints={freePoints} position={upgradeSkill?.position} onClose={() => setUpgradeSkill(null)} onSpendSkillPoints={onSpendSkillPoints} /> : null}
    </div>
  );
}

function InfoTab({ profile }) {
  const info = profile.information || {};
  const activity = info.activity || {};
  const crafts = activity.craftingLevels || [];
  return (
    <div className="nt-stack">
      <Panel title="Активность"><div className="nt-lines"><Row label="Дата регистрации" value={profile.player?.registrationDate || "—"} /><Row label="PVE убийства" value={activity.pveKills || 0} /><Row label="PVP убийства" value={activity.pvpKills || 0} /><Row label="Частицы душ" value={activity.soulParticlesAbsorbed || 0} /><Row label="Штрафы" value={activity.fines || "нет активных штрафов"} /></div></Panel>
      <Panel title="Ремёсла"><div className="nt-card-list nt-column-list">{crafts.length ? crafts.map((craft) => <div key={craft.name} className="nt-mini-card"><CardRow label={craft.name} value={`ур. ${craft.level}`} /><p>{craft.exp}</p></div>) : <p className="nt-empty-text">Ремёсла пока не развиты.</p>}</div></Panel>
      <Panel title="Достижения"><div className="nt-card-list nt-column-list">{(info.achievements || []).length ? info.achievements.map((achievement) => <div key={achievement.name || achievement} className="nt-mini-card"><CardRow label={achievement.name || achievement} value="Получено" /><p>{achievement.description || "—"}</p></div>) : <p className="nt-empty-text">Достижений пока нет.</p>}</div></Panel>
    </div>
  );
}

export function PlayerProfile({ profile, readOnly = false, onSpendAttributePoints, onConfirmAttributePoints, onSpendSkillPoints, onEquipItem, onUnequipItem, onUseItem, onDropItem, onSellItem, onEquipSkill, onUnequipSkill }) {
  const data = profileOrMock(profile);
  const [tab, setTab] = useState("character");
  const [modal, setModal] = useState(null);
  const [slotModal, setSlotModal] = useState(null);
  const [dropModal, setDropModal] = useState(null);
  const [sellModal, setSellModal] = useState(null);
  const effectiveReadOnly = Boolean(readOnly || data.readOnly || data.adminView);
  const background = data.assets?.background || "/assets/profile/backgrounds/1.png";

  const equipmentBySlot = data.equipment || {};
  const inventory = data.inventory || [];

  function openItem(item, slotKey = null, event = null) {
    setModal({ item, slotKey, position: getFloatingPosition(event, 500, 520) });
  }

  function openSlot(slot, event = null) {
    if (effectiveReadOnly || slot?.blocked) return;
    const items = inventory.filter((item) => {
      const target = itemSlot(item);
      if (target === slot.key) return true;
      if ((slot.key === "ring1" || slot.key === "ring2") && (target === "ring" || item.type === "Кольцо" || item.type === "ring")) return true;
      return false;
    });
    setSlotModal({ slot, items, selectedItem: items[0] || null, position: getFloatingPosition(event, 520, 540) });
  }

  async function equipFromSlot(item) {
    if (effectiveReadOnly) return;
    await onEquipItem?.(item, slotModal?.slot?.key || null);
    setSlotModal(null);
  }

  async function equipAndClose(item) {
    if (effectiveReadOnly) return;
    await onEquipItem?.(item);
    setModal(null);
  }

  async function unequipAndClose(slotKey, item) {
    if (effectiveReadOnly) return;
    await onUnequipItem?.(slotKey || itemSlot(item), item);
    setModal(null);
  }

  async function useAndClose(item) {
    if (effectiveReadOnly) return;
    await onUseItem?.(item);
    setModal(null);
  }

  async function dropAndClose(item, amount) {
    if (effectiveReadOnly) return;
    await onDropItem?.(item, amount);
    setDropModal(null);
    setModal(null);
  }

  async function sellAndClose(item, amount) {
    if (effectiveReadOnly) return;
    await onSellItem?.(item, amount);
    setSellModal(null);
    setModal(null);
  }

  function requestDrop(item) {
    if (effectiveReadOnly) return;
    setDropModal({ item, position: modal?.position || null });
  }

  function requestSell(item) {
    if (effectiveReadOnly) return;
    setSellModal({ item, position: modal?.position || null });
  }

  return (
    <main className={`nt-profile ${effectiveReadOnly ? "nt-profile-readonly" : ""}`.trim()} style={{ backgroundImage: `linear-gradient(rgba(5, 7, 7, .32), rgba(4, 4, 4, .50)), url(${background})` }}>
      <div className="nt-shell">
        <header className="nt-top">
          <div className="nt-title-block"><h1>Профиль персонажа</h1>{effectiveReadOnly ? <p className="nt-readonly-banner">Админский режим: только просмотр, изменения отключены.</p> : null}</div>
          <div className="nt-id">{data.player?.userGlobalId || data.player?.publicId || "NT-UNKNOWN"}</div>
        </header>
        <nav className="nt-tabs" aria-label="Разделы профиля">
          {TABS.map(({ id, label, icon }) => <button key={id} className={tab === id ? "active" : ""} type="button" onClick={() => setTab(id)} title={label} aria-label={label}><span className="nt-tab-icon"><TabIcon type={icon} /></span><span className="nt-tab-text">{label}</span></button>)}
        </nav>
        <section className="nt-content">
          {tab === "character" ? <CharacterTab profile={{ ...data, equipment: equipmentBySlot }} readOnly={effectiveReadOnly} onOpenItem={openItem} onOpenSlot={openSlot} onSpendAttributePoints={onSpendAttributePoints} onConfirmAttributePoints={onConfirmAttributePoints} /> : null}
          {tab === "inventory" ? <InventoryTab profile={data} onOpenItem={openItem} /> : null}
          {tab === "skills" ? <SkillsTab profile={data} readOnly={effectiveReadOnly} onSpendSkillPoints={onSpendSkillPoints} onEquipSkill={onEquipSkill} onUnequipSkill={onUnequipSkill} /> : null}
          {tab === "info" ? <InfoTab profile={data} /> : null}
        </section>
      </div>
      <ItemModal item={modal?.item} slotKey={modal?.slotKey} position={modal?.position} readOnly={effectiveReadOnly} onClose={() => setModal(null)} onEquipItem={equipAndClose} onUnequipItem={unequipAndClose} onUseItem={useAndClose} onRequestDrop={requestDrop} onRequestSell={requestSell} />
      {!effectiveReadOnly ? <DropItemModal item={dropModal?.item} position={dropModal?.position} onClose={() => setDropModal(null)} onConfirm={dropAndClose} /> : null}
      {!effectiveReadOnly ? <SellItemModal item={sellModal?.item} position={sellModal?.position} onClose={() => setSellModal(null)} onConfirm={sellAndClose} /> : null}
      <SlotItemsModal slot={slotModal?.slot} items={slotModal?.items || []} selectedItem={slotModal?.selectedItem} position={slotModal?.position} onSelectItem={(item) => setSlotModal((current) => ({ ...current, selectedItem: item }))} onClose={() => setSlotModal(null)} readOnly={effectiveReadOnly} onEquipItem={equipFromSlot} />
    </main>
  );
}

export default PlayerProfile;
