import React, { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { profileMockData } from "./profileMockData.js";
import {
  itemTypeRu, itemCategoryRu, itemQualityRu, itemSlotRu, itemSourceRu, yesNo,
} from "../../i18n/itemLabels.js";

const TABS = [
  // Вкладка «Обзор» убрана (ТЗ §1): её данные перенесены — параметры/эффекты в
  // «Персонаж», предупреждения/статус/рейтинги в «Журнал».
  { id: "character", label: "Персонаж", icon: "head" },
  { id: "inventory", label: "Инвентарь", icon: "bag" },
  { id: "skills", label: "Навыки", icon: "star" },
  { id: "info", label: "Информация", icon: "scroll" },
];

// Вкладка «Сервисы» объединяет Передачу (гонец) и Промокод. Список доступных
// сервисов приходит с бэкенда (profile.services), но даже без него показываем
// курьерскую передачу для совместимости со старым ответом API.
const SERVICES_TAB = { id: "services", label: "Сервисы", icon: "courier" };

// Вкладка «Гильдии» появляется только когда бэкенд вернул блок guild
// (profile.guild != null). Гильдейская система пока в разработке — без блока
// вкладка скрыта (ТЗ §14).
const GUILD_TAB = { id: "guild", label: "Гильдия", icon: "star" };

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
    bonuses: ["Торговая жилка: 5% шанс +3% монет у NPC", "Обучаемость: +2% получаемого опыта", "Универсальность: +1% к основным характеристикам"],
  },
  elf: {
    name: "Эльф",
    stats: "Сила 2 · Ловкость 4 · Выносливость 2 · Интеллект 5 · Мудрость 4 · Восприятие 3",
    bonuses: ["Чутьё зельевара: 10% шанс не потратить часть ингредиентов", "Врождённая магия: +3% магического урона", "Знание трав: +3% к сбору алхимических ингредиентов"],
  },
  dwarf: {
    name: "Дворф",
    stats: "Сила 5 · Ловкость 2 · Выносливость 5 · Интеллект 3 · Мудрость 3 · Восприятие 2",
    bonuses: ["Каменное чутьё: 4% шанс камня при добыче руды", "Мастерская закалка: шанс +1 эффект на оружии/броне", "Каменная выносливость: +3% к выносливости"],
  },
  undead: {
    name: "Нежить",
    stats: "Сила 3 · Ловкость 2 · Выносливость 6 · Интеллект 3 · Мудрость 4 · Восприятие 2",
    bonuses: ["Мёртвая плоть: +4% к здоровью", "Мёртвое сопротивление: -5% яд/кровотечение/оглушение/проклятие", "Холодная плоть: -3% периодического урона"],
  },
  lizardfolk: {
    name: "Ящеролюд",
    stats: "Сила 4 · Ловкость 4 · Выносливость 4 · Интеллект 1 · Мудрость 2 · Восприятие 5",
    bonuses: ["Природная регенерация: 0.5% HP за ход в бою", "Плотная чешуя: -2% физического урона", "Охотничье чутьё: +4% к поиску добычи и ресурсов"],
  },
};

const RACE_NAME_TO_KEY = {
  человек: "human",
  эльф: "elf",
  дворф: "dwarf",
  нежить: "undead",
  ящеролюд: "lizardfolk",
};

let profileModalLocks = 0;
let profileModalScrollY = 0;
let profileModalBodyStyles = null;

function lockProfileScroll() {
  if (typeof document === "undefined" || profileModalLocks++ > 0) return;
  profileModalScrollY = window.scrollY || 0;
  profileModalBodyStyles = {
    position: document.body.style.position,
    top: document.body.style.top,
    width: document.body.style.width,
    overflow: document.body.style.overflow,
  };
  document.body.style.position = "fixed";
  document.body.style.top = `-${profileModalScrollY}px`;
  document.body.style.width = "100%";
  document.body.style.overflow = "hidden";
}

function unlockProfileScroll() {
  if (typeof document === "undefined" || profileModalLocks === 0 || --profileModalLocks > 0) return;
  const saved = profileModalBodyStyles || {};
  document.body.style.position = saved.position || "";
  document.body.style.top = saved.top || "";
  document.body.style.width = saved.width || "";
  document.body.style.overflow = saved.overflow || "";
  window.scrollTo(0, profileModalScrollY);
  profileModalBodyStyles = null;
}

function ProfileModal({ children, className = "", onClose, closeOnBackdrop = true, label = "Диалог", layerClassName = "" }) {
  const dialogRef = useRef(null);
  const returnFocusRef = useRef(null);
  const [viewport, setViewport] = useState(null);

  useEffect(() => {
    returnFocusRef.current = document.activeElement;
    lockProfileScroll();
    const updateViewport = () => {
      const vv = window.visualViewport;
      setViewport(vv ? { height: vv.height, top: vv.offsetTop } : null);
    };
    updateViewport();
    window.visualViewport?.addEventListener("resize", updateViewport);
    window.visualViewport?.addEventListener("scroll", updateViewport);
    const dialog = dialogRef.current;
    const focusables = dialog?.querySelectorAll?.('button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [href], [tabindex]:not([tabindex="-1"])');
    (focusables?.[0] || dialog)?.focus?.({ preventScroll: true });
    return () => {
      window.visualViewport?.removeEventListener("resize", updateViewport);
      window.visualViewport?.removeEventListener("scroll", updateViewport);
      unlockProfileScroll();
      returnFocusRef.current?.focus?.({ preventScroll: true });
    };
  }, []);

  function onKeyDown(event) {
    if (event.key === "Escape") { event.preventDefault(); onClose?.(); return; }
    if (event.key !== "Tab") return;
    const focusables = [...(dialogRef.current?.querySelectorAll?.('button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [href], [tabindex]:not([tabindex="-1"])') || [])];
    if (!focusables.length) { event.preventDefault(); dialogRef.current?.focus(); return; }
    const first = focusables[0];
    const last = focusables[focusables.length - 1];
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  }

  if (typeof document === "undefined") return null;
  const layerStyle = viewport ? { height: `${viewport.height}px`, minHeight: `${viewport.height}px`, top: `${viewport.top}px`, bottom: "auto" } : undefined;
  return createPortal(
    <div className={`nt-modal-layer ${layerClassName}`.trim()} style={layerStyle} onMouseDown={(event) => { if (closeOnBackdrop && event.target === event.currentTarget) onClose?.(); }}>
      <article ref={dialogRef} className={`nt-modal ${className}`.trim()} role="dialog" aria-modal="true" aria-label={label} tabIndex={-1} onKeyDown={onKeyDown} onMouseDown={(event) => event.stopPropagation()}>
        {children}
      </article>
    </div>,
    document.body,
  );
}

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
  if (type === "courier") {
    return (
      <svg {...common}>
        <path d="M4.5 8.2 12 4.4l7.5 3.8-7.5 3.8-7.5-3.8Z" />
        <path d="M4.5 8.2v7.6l7.5 3.8 7.5-3.8V8.2" />
        <path d="M12 12v7.6" />
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

function profileOrMock(profile) {
  return profile || profileMockData;
}

function raceKey(player) {
  return player?.raceKey || RACE_NAME_TO_KEY[String(player?.raceName || "").toLowerCase()] || "human";
}

function qualityClass(quality = "обычный") {
  return `quality-${String(quality).toLowerCase().replace(/\s+/g, "-")}`;
}

const QUALITY_RANK = { обычный: 0, необычный: 1, редкий: 2, эпический: 3, легендарный: 4, мифический: 5, божественный: 6, уникальный: 7 };
function qualityRank(item) { return QUALITY_RANK[String(item?.quality || "").toLowerCase()] ?? 0; }

const INVENTORY_SORTS = [
  { id: "new", label: "По новизне" },
  { id: "quality", label: "По качеству" },
  { id: "level", label: "По уровню" },
  { id: "price", label: "По цене" },
  { id: "amount", label: "По количеству" },
  { id: "type", label: "По типу" },
  { id: "name", label: "По названию" },
];
const INVENTORY_FILTERS = [
  { id: "all", label: "Все" },
  { id: "equip", label: "Можно надеть" },
  { id: "use", label: "Можно использовать" },
  { id: "sell", label: "Можно продать" },
  { id: "overflow", label: "В перегрузе" },
];

function itemActionList(item) { return Array.isArray(item?.actions) ? item.actions : []; }
function matchesInventoryFilter(item, filter) {
  if (filter === "equip") return itemActionList(item).includes("Надеть");
  if (filter === "use") return itemActionList(item).includes("Использовать");
  if (filter === "sell") return item.marketSellAvailable || itemActionList(item).includes("Продать");
  if (filter === "overflow") return Boolean(item.overflowSlot);
  return true;
}
function sortInventory(items, sort) {
  if (sort === "new") return items;
  const copy = [...items];
  const num = (v) => Number(v) || 0;
  const sorters = {
    quality: (a, b) => qualityRank(b) - qualityRank(a),
    level: (a, b) => num(b.level) - num(a.level),
    price: (a, b) => num(b.sellPrice || b.price) - num(a.sellPrice || a.price),
    amount: (a, b) => num(b.amount) - num(a.amount),
    type: (a, b) => String(a.type || a.category || "").localeCompare(String(b.type || b.category || "")),
    name: (a, b) => String(a.name || "").localeCompare(String(b.name || "")),
  };
  return sorters[sort] ? copy.sort(sorters[sort]) : copy;
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

// Доступ к локации, который открывает предмет (ТЗ §4) — показываем, если задан.
function accessTarget(item) {
  if (!item || item.opens_access === false) return "";
  return String(item.access_target_name || item.access_target || item.accessTarget || "").trim();
}
function accessCondition(item) {
  if (!item) return "";
  return String(item.access_text_condition || item.access_condition || item.accessCondition || "").trim();
}
// Источник получения (русское название).
function itemSourceText(item) {
  const raw = item?.source ?? item?.origin ?? item?.source_type;
  return raw ? itemSourceRu(raw) : "";
}
// Можно ли передать/продать (Да/Нет). Неизвестно → не показываем строку.
function canTransferText(item) {
  const v = item?.canTransfer ?? item?.can_transfer ?? item?.transferable;
  if (v === undefined || v === null) return "";
  return yesNo(v);
}
function canSellText(item) {
  const v = item?.canSell ?? item?.can_sell;
  return v === false ? "Нет" : "Да";
}

// Применить опубликованную раскладку (ТЗ §3) к базовым вкладкам: порядок/подпись/
// иконка/скрытие для известных вкладок. Аддитивно: при пустой раскладке — как есть.
function profileCondition(condition, profile) {
  const value = String(condition || "").trim(); if (!value) return true;
  if (value === "has_services") return Boolean(profile?.services?.length);
  if (value === "has_fines") return Boolean(profile?.information?.activity?.fineList?.length);
  if (value === "has_achievements") return Boolean(profile?.information?.achievements?.length);
  if (value === "has_pavilion") return Boolean(profile?.services?.some((s) => s.id === "pavilion"));
  if (value === "admin_only") return Boolean(profile?.adminView);
  const match = value.match(/^level\s*>=\s*(\d+)$/); if (match) return Number(profile?.player?.level || 0) >= Number(match[1]);
  return true;
}
function applyProfileLayoutTabs(baseTabs, layout, profile) {
  const enabled = String(layout?.settings?.enabled_tabs || "").split(",").map((v) => v.trim()).filter(Boolean);
  if (enabled.length) baseTabs = baseTabs.filter((tab) => enabled.includes(tab.id));
  const tabs = Array.isArray(layout?.tabs) ? layout.tabs : [];
  if (!tabs.length) return baseTabs;
  const byId = new Map(baseTabs.map((t) => [t.id, t]));
  const used = new Set();
  const result = [];
  for (const lt of tabs) {
    const base = byId.get(String(lt.key || "").trim());
    if (!base) continue;                       // нет рендера для такого ключа — пропускаем
    if (String(lt.visibility || "") === "hidden" || (profile?.adminView ? lt.show_admin === false : lt.show_player === false || lt.hide_player) || !profileCondition(lt.condition, profile)) { used.add(base.id); continue; }
    result.push({ ...base, label: lt.label || base.label, emoji: lt.icon || null });
    used.add(base.id);
  }
  // Базовые вкладки, не упомянутые в раскладке, не теряем — добавляем в конце.
  for (const base of baseTabs) if (!used.has(base.id)) result.push(base);
  return result.length ? result : baseTabs;
}

// Применение раскладки на уровне БЛОКОВ (ТЗ §3, рантайм): опубликованная
// раскладка вкладки задаёт видимость/порядок известных блоков. Аддитивно, как и
// для вкладок: блок с visibility "hidden" скрывается, перечисленные блоки идут в
// заданном порядке, неизвестные раскладке блоки сохраняются в конце (контент не
// теряется). Нет раскладки для вкладки → дефолтный порядок без изменений.
// defaultBlocks: [{ type, node }]. layout: data.profileLayout.
function planProfileBlocks(tabKey, layout, defaultBlocks, profile = null) {
  const layoutTab = (Array.isArray(layout?.tabs) ? layout.tabs : []).find(
    (t) => String(t.key || "").trim() === tabKey,
  );
  const blocks = Array.isArray(layoutTab?.blocks) ? layoutTab.blocks : [];
  if (!blocks.length) return defaultBlocks;
  const byType = new Map(defaultBlocks.map((b) => [b.type, b]));
  const used = new Set();
  const result = [];
  for (const lb of blocks) {
    const base = byType.get(String(lb.type || "").trim());
    if (!base) continue;                 // нет такого блока в рендере — игнорируем
    used.add(base.type);                 // упомянут (даже скрытый) — не дублируем ниже
    if (String(lb.visibility || "") === "hidden" || (profile?.adminView ? lb.show_admin === false : lb.show_player === false || lb.hide_player) || !profileCondition(lb.condition, profile)) continue;
    result.push(base);
  }
  for (const base of defaultBlocks) if (!used.has(base.type)) result.push(base);
  return result.length ? result : defaultBlocks;
}

// Оформление профиля из раскладки → CSS-переменные (только заданные значения).
function profileThemeStyle(theme) {
  if (!theme) return {};
  const v = {};
  if (theme.card_background) v["--nt-card"] = theme.card_background;
  if (theme.button_color) v["--nt-gold"] = theme.button_color;
  if (theme.text_color) v["--nt-text"] = theme.text_color;
  if (theme.border_color) v["--nt-line"] = theme.border_color;
  if (theme.primary_color) v["--nt-primary"] = theme.primary_color;
  if (theme.secondary_color) v["--nt-secondary"] = theme.secondary_color;
  if (theme.background_color) v["--nt-bg"] = theme.background_color;
  if (theme.positive_color) v["--nt-positive"] = theme.positive_color;
  if (theme.negative_color) v["--nt-negative"] = theme.negative_color;
  if (theme.warning_color) v["--nt-warning"] = theme.warning_color;
  if (theme.danger_color) v["--nt-danger"] = theme.danger_color;
  if (theme.border_radius) v["--nt-radius"] = `${Math.max(0, Number(theme.border_radius))}px`;
  if (theme.icon_size) v["--nt-icon-size"] = `${Math.max(16, Math.min(96, Number(theme.icon_size)))}px`;
  if (theme.item_image_size) v["--nt-item-image-size"] = `${Math.max(48, Math.min(180, Number(theme.item_image_size)))}px`;
  return v;
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
  return map[slotKey] || itemSlotRu(slotKey) || "—";
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
    <ProfileModal className="nt-race-popover nt-effects-popover" onClose={onClose} label="Активные эффекты">
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
    </ProfileModal>
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

function CollapsiblePanel({ title, right, children, className = "", defaultOpen = true }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <section className={`nt-panel ${className}`.trim()}>
      <header className="nt-panel-head nt-panel-collapsible" onClick={() => setOpen((value) => !value)} role="button" tabIndex={0} aria-expanded={open}>
        <h2>{title}</h2>
        <div className="nt-panel-right">
          {right}
          <span className={`nt-collapse-arrow ${open ? "open" : ""}`.trim()} aria-hidden="true">▾</span>
        </div>
      </header>
      {open ? children : null}
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
  // Источник истины — бэкенд (raceInfo из data/races.json). Захардкоженный
  // RACE_INFO остаётся лишь запасным вариантом для старого ответа API.
  const backend = profile.player?.raceInfo;
  const fallback = RACE_INFO[raceKey(profile.player)] || RACE_INFO.human;
  const race = {
    name: backend?.name || fallback.name,
    stats: backend?.statsText || fallback.stats,
    description: backend?.description || "",
    bonuses: (backend?.bonuses && backend.bonuses.length) ? backend.bonuses : fallback.bonuses,
  };
  return (
    <ProfileModal className="nt-race-popover" onClose={onClose} label="Бонусы расы">
      <button className="nt-popover-close" type="button" onClick={onClose} aria-label="Закрыть">×</button>
      <div className="nt-modal-kicker">Бонусы расы</div>
      <h3>{race.name}</h3>
      {race.description ? <p className="nt-race-desc">{race.description}</p> : null}
      <div className="nt-modal-block">
        <h4>Стартовые характеристики</h4>
        <p className="nt-race-stats">{race.stats}</p>
      </div>
      <div className="nt-modal-block">
        <h4>Бонусы</h4>
        <ul>{race.bonuses.map((bonus) => <li key={bonus}>{bonus}</li>)}</ul>
      </div>
    </ProfileModal>
  );
}

function ItemModal({ item, slotKey, position, readOnly = false, adminEdit = false, actionPermissions = {}, onClose, onEquipItem, onUnequipItem, onUseItem, onRepairItem, onProfileItemAction, onOpenTransfer, onCraftOperation, onRequestDrop, onRequestSell, onAdminRemoveItem }) {
  const [profileActionText, setProfileActionText] = useState("");
  useEffect(() => { setProfileActionText(""); }, [item?.id, item?.inventoryIndex]);
  if (!item) return null;
  const actions = item.actions || [];
  const itemStats = statLines(item);
  const sellPriceText = itemSellPriceText(item);
  return (
    <ProfileModal className={qualityClass(item.quality)} onClose={onClose} label={item.name || "Карточка предмета"}>
        <button className="nt-modal-close" type="button" onClick={onClose}>×</button>
        <div className="nt-modal-kicker">{itemCategoryRu(item.category) || "Предмет"}</div>
        <div className="nt-modal-title-row">
          <span className="nt-modal-item-icon"><ItemArt item={item} /></span>
          <div>
            <h3>{item.name || "Предмет"}</h3>
            <div className="nt-modal-subtitle">{itemQualityRu(item.quality) || "Обычный"}{item.level ? ` · ур. ${item.level}` : ""}</div>
          </div>
        </div>
        <div className="nt-modal-grid">
          <span>Тип</span><strong>{itemTypeRu(item.type) || itemCategoryRu(item.category) || "—"}</strong>
          <span>Слот</span><strong>{compactSlotName(slotKey || itemSlot(item))}</strong>
          <span>Количество</span><strong>×{item.amount || 1}</strong>
          {accessTarget(item) ? <><span>Открывает доступ</span><strong>{accessTarget(item)}</strong></> : null}
          {accessCondition(item) ? <><span>Условие</span><strong>{accessCondition(item)}</strong></> : null}
          {itemSourceText(item) ? <><span>Источник</span><strong>{itemSourceText(item)}</strong></> : null}
          {canTransferText(item) ? <><span>Можно передать</span><strong>{canTransferText(item)}</strong></> : null}
          <span>Можно продать</span><strong>{canSellText(item)}</strong>
          {actions.includes("Использовать") ? <><span>Можно использовать</span><strong>Да</strong></> : null}
          {sellPriceText ? <><span>Цена продажи</span><strong>{sellPriceText}</strong></> : null}
        </div>
        <p>{item.description || "Описание предмета пока не добавлено."}</p>
        {itemStats.length ? <div className="nt-modal-block"><h4>Свойства</h4><StatLines lines={itemStats} /></div> : null}
        {Array.isArray(item.enchantments) && item.enchantments.length ? (
          <div className="nt-modal-block"><h4>Зачарования</h4><StatLines lines={item.enchantments} /></div>
        ) : null}
        {profileActionText ? <div className="nt-modal-block"><h4>Предмет</h4><p>{profileActionText}</p></div> : null}
        <footer className="nt-modal-actions">
          {!readOnly && actionPermissions.allow_equip !== false && (actions.includes("Надеть") || (!slotKey && itemSlot(item))) ? <button type="button" onClick={() => onEquipItem?.(item)}>Надеть</button> : null}
          {!readOnly && actionPermissions.allow_equip !== false && (actions.includes("Снять") || slotKey) ? <button type="button" onClick={() => onUnequipItem?.(slotKey || itemSlot(item), item)}>Снять</button> : null}
          {!readOnly && actionPermissions.allow_item_use !== false && (actions.includes("Использовать") || actions.includes("Открыть")) ? <button type="button" onClick={() => onUseItem?.(item)}>{actions.includes("Открыть") ? "Открыть" : "Использовать"}</button> : null}
          {!readOnly && actionPermissions.allow_craft_actions !== false && actions.includes("Ремонт") ? <button type="button" onClick={() => onRepairItem?.(item)}>Отремонтировать</button> : null}
          {!readOnly && actions.includes("Осмотреть") ? <button type="button" onClick={() => setProfileActionText(item.inspect_text || item.technical_description || item.description || "Вы внимательно осмотрели предмет.")}>Осмотреть</button> : null}
          {!readOnly && actions.includes("Прочитать") ? <button type="button" onClick={() => setProfileActionText(item.read_text || item.content_text || item.description || "На предмете нет читаемого текста.")}>Прочитать</button> : null}
          {!readOnly && [["Зарядить","charge"],["Разрядить","discharge"],["Положить в подсумок","pouch_store"],["Убрать из подсумка","pouch_remove"],["Положить в хранилище","storage_store"]].map(([label, action]) => actions.includes(label) ? <button type="button" key={action} onClick={() => onProfileItemAction?.(item, action)}>{label}</button> : null)}
          {!readOnly && actionPermissions.allow_transfer !== false && (actions.includes("Передать") || actions.includes("Отправить доставкой")) ? <button type="button" onClick={() => onOpenTransfer?.(item)}>Передать доставкой</button> : null}
          {!readOnly && actionPermissions.allow_craft_actions !== false && (item.craftOperations || []).map((rule) => <button type="button" key={`${rule.operation}:${rule.rule_id}`} onClick={() => onCraftOperation?.(item, rule)}>{rule.operation === "upgrade" ? "Улучшить" : rule.operation === "enchant" ? "Зачаровать" : rule.operation === "purify" ? "Очистить" : rule.operation === "repair" ? "Починить" : "Разобрать"}: {rule.name}</button>)}
          {!readOnly && !slotKey && actions.includes("Продать") ? <button type="button" onClick={() => onRequestSell?.(item)}>Продать</button> : null}
          {readOnly ? <span className="nt-readonly-note">Только просмотр</span> : null}
          <button className="nt-secondary" type="button" onClick={onClose}>Закрыть</button>
        </footer>
        {(!readOnly && !slotKey) || (adminEdit && !slotKey) ? (
          <div className="nt-danger-zone">
            <span className="nt-danger-zone-label">Опасная зона</span>
            <div className="nt-danger-zone-actions">
              {!readOnly && actionPermissions.allow_item_drop !== false && !slotKey && item.profileCanDrop !== false ? <button className="nt-danger" type="button" onClick={() => onRequestDrop?.(item)}>Выбросить</button> : null}
              {adminEdit && !slotKey ? <button className="nt-danger" type="button" onClick={() => onAdminRemoveItem?.(item)}>Удалить из профиля игрока</button> : null}
            </div>
          </div>
        ) : null}
    </ProfileModal>
  );
}

function DropItemModal({ item, position, onClose, onConfirm }) {
  const maxAmount = Math.max(1, Number(item?.amount || 1));
  const [amount, setAmount] = useState(1);
  const [confirmed, setConfirmed] = useState(false);
  // Reset the quantity (and the danger-confirm checkbox) whenever a different
  // item stack is opened, otherwise the field keeps the previous item's state.
  useEffect(() => { setAmount(1); setConfirmed(false); }, [item?.id, item?.inventoryIndex]);
  if (!item) return null;

  // Rare and above are easy to lose by accident, so they require an explicit
  // second confirmation before the «Выбросить» button unlocks.
  const precious = qualityRank(item) >= 2 || Boolean(item.dropWarning);
  const blocked = precious && !confirmed;

  function submit() {
    if (blocked) return;
    onConfirm?.(item, clamp(Number(amount) || 1, 1, maxAmount));
  }

  return (
    <ProfileModal className="nt-small-modal" onClose={onClose} closeOnBackdrop={false} label="Подтверждение выброса предмета">
        <button className="nt-modal-close" type="button" onClick={onClose}>×</button>
        <div className="nt-modal-kicker">Выброс предмета</div>
        <h3 className={qualityClass(item.quality)}>{item.name}</h3>
        <p>Доступно: ×{maxAmount}</p>
        <label className="nt-field-label">
          <span>Количество</span>
          <input type="number" min="1" max={maxAmount} value={amount} onChange={(event) => setAmount(event.target.value)} autoFocus />
        </label>
        {precious ? (
          <label className="nt-confirm-check">
            <input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />
            <span>{item.dropWarning || <>Это <strong>{itemQualityRu(item.quality)}</strong> предмет.</>} Я понимаю, что выброшенный предмет восстановить нельзя.</span>
          </label>
        ) : null}
        <footer className="nt-modal-actions">
          <button className="nt-danger" type="button" onClick={submit} disabled={blocked}>Выбросить</button>
          <button className="nt-secondary" type="button" onClick={onClose}>Отмена</button>
        </footer>
    </ProfileModal>
  );
}

function SellItemModal({ item, position, onClose, onConfirm }) {
  const maxAmount = Math.max(1, Number(item?.amount || 1));
  const [amount, setAmount] = useState(1);
  const sellPriceText = itemSellPriceText(item);
  // Reset the quantity when switching to a different item stack.
  useEffect(() => { setAmount(1); }, [item?.id, item?.inventoryIndex]);
  if (!item) return null;

  function submit() {
    onConfirm?.(item, clamp(Number(amount) || 1, 1, maxAmount));
  }

  return (
    <ProfileModal className="nt-small-modal" onClose={onClose} closeOnBackdrop={false} label="Продажа предмета">
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
    </ProfileModal>
  );
}

function SlotItemsModal({ slot, items, selectedItem, position, readOnly = false, onSelectItem, onClose, onEquipItem }) {
  if (!slot) return null;
  return (
    <ProfileModal className="nt-slot-modal" onClose={onClose} label="Выбор предмета для слота">
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
    </ProfileModal>
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

function EditPencil({ onClick }) {
  return (
    <button className="nt-edit-pencil" type="button" onClick={onClick} aria-label="Изменить" title="Изменить">✎</button>
  );
}

const LEGACY_RACE_EDIT_CHOICES = [["human", "Человек"], ["elf", "Эльф"], ["dwarf", "Дворф"], ["undead", "Нежить"], ["lizardfolk", "Ящеролюд"]];
const GENDER_EDIT_CHOICES = [["male", "Муж."], ["female", "Жен."]];

function ProfileEditModal({ field, player, onClose, onSubmit }) {
  const [name, setName] = useState(field === "name" ? (player?.nickname || "") : "");
  // Подтверждение: единственная бесплатная попытка тратится только после «Да».
  const [pending, setPending] = useState(null); // { value, label }
  const titles = { name: "Изменить имя", race: "Изменить расу", gender: "Изменить пол" };
  const raceChoices = (player?.raceChangeOptions || []).length ? player.raceChangeOptions.map((row) => [row.id, row.name]) : LEGACY_RACE_EDIT_CHOICES;
  return (
    <ProfileModal className="nt-small-modal" onClose={onClose} closeOnBackdrop={false} label="Редактирование сводки">
        <button className="nt-modal-close" type="button" onClick={onClose}>×</button>
        <div className="nt-modal-kicker">Сводка</div>
        <h3>{titles[field] || "Изменить"}</h3>
        {pending ? (
          <div className="nt-edit-confirm">
            <p>Использовать единственную бесплатную попытку и изменить на «{pending.label}»? Отменить будет нельзя.</p>
            <div className="nt-edit-choices">
              <button className="nt-edit-choice" type="button" onClick={() => onSubmit(field, pending.value)}>Да, изменить</button>
              <button className="nt-edit-choice" type="button" onClick={() => setPending(null)}>Отмена</button>
            </div>
          </div>
        ) : (
          <>
            <p className="nt-edit-hint">Доступна 1 бесплатная попытка.</p>
            {field === "name" ? (
              <div className="nt-edit-form">
                <input className="nt-edit-input" value={name} maxLength={24} onChange={(event) => setName(event.target.value)} placeholder="Новое имя" />
                <button className="nt-edit-save" type="button" disabled={!name.trim()} onClick={() => setPending({ value: name.trim(), label: name.trim() })}>Сохранить</button>
              </div>
            ) : null}
            {field === "gender" ? (
              <div className="nt-edit-choices">{GENDER_EDIT_CHOICES.map(([id, label]) => <button key={id} className="nt-edit-choice" type="button" onClick={() => setPending({ value: id, label })}>{label}</button>)}</div>
            ) : null}
            {field === "race" ? (
              <div className="nt-edit-choices">{raceChoices.map(([id, label]) => <button key={id} className="nt-edit-choice" type="button" onClick={() => setPending({ value: id, label })}>{label}</button>)}</div>
            ) : null}
          </>
        )}
    </ProfileModal>
  );
}

function RaceRow({ profile, readOnly = false, canEdit = false, onEdit }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="nt-row nt-race-row">
      <span>Раса</span>
      <strong className="nt-race-cell">
        <span className="nt-race-value">{profile.player?.raceName || "—"}</span>
        <button className="nt-race-info-button" type="button" onClick={() => setOpen((value) => !value)} aria-expanded={open} aria-label="Показать бонусы расы">!</button>
        {!readOnly ? <EditPencil onClick={(event) => onEdit?.("race", event, canEdit)} /> : null}
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

function CharacterTab({ profile, readOnly = false, onOpenItem, onOpenSlot, onConfirmAttributePoints, onEditProfileField }) {
  const [attributeAmounts, setAttributeAmounts] = useState({});
  const [pendingAttributes, setPendingAttributes] = useState({});
  const [editField, setEditField] = useState(null);
  const [editNotice, setEditNotice] = useState("");
  const fieldEdits = profile.player?.profileFieldEdits || {};

  function openFieldEditor(field, event) {
    if (!fieldEdits[field]) {
      setEditNotice("У вас закончились попытки изменить это поле.");
      setEditField(null);
      return;
    }
    setEditNotice("");
    setEditField({ field });
  }

  async function submitFieldEdit(field, value) {
    try {
      await onEditProfileField?.(field, value);
      setEditField(null);
    } catch (error) {
      setEditField(null);
      setEditNotice(error?.message || "Не удалось изменить поле.");
    }
  }
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

  // Блоки вкладки в дефолтном порядке; раскладка может скрыть/переставить их.
  const defaultBlocks = [
    { type: "main_info", node: (
      <Panel title="Сводка">
        <div className="nt-lines">
          <div className="nt-row">
            <span>Имя</span>
            <strong className="nt-summary-value"><span className="nt-summary-text">{profile.player?.nickname || "—"}</span>{!readOnly ? <EditPencil onClick={(event) => openFieldEditor("name", event)} /> : null}</strong>
          </div>
          <RaceRow profile={profile} readOnly={readOnly} canEdit={Boolean(fieldEdits.race)} onEdit={(field, event) => openFieldEditor("race", event)} />
          <div className="nt-row">
            <span>Пол</span>
            <strong className="nt-summary-value"><span className="nt-summary-text">{profile.player?.genderLabel || "—"}</span>{!readOnly ? <EditPencil onClick={(event) => openFieldEditor("gender", event)} /> : null}</strong>
          </div>
          <Row label="Уровень" value={profile.player?.level || 1} />
          <Row label="Баланс" value={profile.player?.balanceText || "0 мед."} />
          <EffectsRow profile={profile} />
        </div>
        {editNotice ? <div className="nt-edit-notice">{editNotice}</div> : null}
        <div className="nt-progress-label">Опыт: {xpCurrent} / {xpNext}</div>
        <div className="nt-progress"><i style={{ width: `${xpPercent}%` }} /></div>
      </Panel>
    ) },
    { type: "equipment", node: (
      <EquipmentPanel profile={profile} readOnly={readOnly} onOpenItem={onOpenItem} onOpenSlot={onOpenSlot} />
    ) },
    { type: "stats", node: (
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
    ) },
    { type: "resources", node: (
      <Panel title="Параметры"><div className="nt-lines">{(profile.parameters || []).map((row) => <Row key={row.label} label={row.label} value={row.value} />)}</div></Panel>
    ) },
    { type: "active_sets", node: (
      <Panel title="Активные сеты">
        {(profile.activeSets || []).length ? <div className="nt-column-list">{profile.activeSets.map((set) => <div key={set.name} className="nt-mini-card"><CardRow label={set.name} value="активен" /><p>{set.bonus}</p></div>)}</div> : <p className="nt-empty-text">Активных сетов нет.</p>}
      </Panel>
    ) },
  ];
  const blocks = planProfileBlocks("character", profile.profileLayout, defaultBlocks, profile);
  return (
    <div className="nt-stack">
      {blocks.map((b) => <React.Fragment key={b.type}>{b.node}</React.Fragment>)}
      {editField ? <ProfileEditModal field={editField.field} player={profile.player} position={editField.position} onClose={() => setEditField(null)} onSubmit={submitFieldEdit} /> : null}
    </div>
  );
}

function InventoryTab({ profile, onOpenItem, readOnly = false, onClaimCraftDelivery, onProfileItemAction }) {
  const [category, setCategory] = useState("Всё");
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState("new");
  const [filter, setFilter] = useState("all");
  const inventory = profile.inventory || [];
  const freeSlots = inventoryFreeSlots(profile, inventory);
  const capacity = inventoryCapacity(profile);
  const overloaded = Boolean(profile.player?.inventoryOverloaded);
  const overflowCount = profile.player?.inventoryOverflowUsed || inventory.filter((i) => i.overflowSlot).length;
  const filtered = useMemo(() => {
    const base = inventory.filter((item) => {
      const categoryOk = category === "Всё" || item.category === category || (category === "Материалы" && item.isMaterial);
      const queryOk = !query || String(item.name || "").toLowerCase().includes(query.toLowerCase());
      return categoryOk && queryOk && matchesInventoryFilter(item, filter);
    });
    return sortInventory(base, sort);
  }, [inventory, category, query, filter, sort]);

  return (
    <div className="nt-stack">
      {overloaded ? <div className="nt-warning nt-warning-warning"><span className="nt-warning-dot" />Инвентарь перегружен: {overflowCount} предметов находятся в дополнительных слотах.</div> : null}
      {profile.craftDelivery?.pendingAmount > 0 ? <div className="nt-warning nt-warning-warning"><span className="nt-warning-dot" />В доставке ремесла: ×{profile.craftDelivery.pendingAmount}. {!readOnly ? <button type="button" className="ntv2-btn" onClick={() => onClaimCraftDelivery?.()}>Получить доступное</button> : null}</div> : null}
      <Panel title="Инвентарь" right={<span className="nt-badge">Свободно: {freeSlots} / {capacity}</span>}>
        {!profile.readOnly && !profile.adminView && profile.market?.sellFromProfile ? <p className="nt-market-sell-hint">Вы на рынке в разделе продажи: откройте предмет и нажмите «Продать».</p> : null}
        <div className="nt-toolbar">
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Поиск предмета" />
          <div className="nt-inv-controls">
            <select value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="Фильтр">{INVENTORY_FILTERS.map((f) => <option key={f.id} value={f.id}>{f.label}</option>)}</select>
            <select value={sort} onChange={(e) => setSort(e.target.value)} aria-label="Сортировка">{INVENTORY_SORTS.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}</select>
          </div>
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
      {(profile.personalStorage || []).length ? <Panel title="Персональное хранилище" right={<span className="nt-badge">{(profile.personalStorage || []).length}</span>}>
        <div className="nt-inventory-grid">{profile.personalStorage.map((item) => <article className={`nt-item-icon-card ${qualityClass(item.quality)}`} key={`${item.id}:${item.storageIndex}`}><ItemArt item={item} /><span>{item.name}</span>{!readOnly ? <button type="button" onClick={() => onProfileItemAction?.(item, "storage_remove")}>Забрать</button> : null}</article>)}</div>
      </Panel> : null}
    </div>
  );
}

function ModifierHelpModal({ modifier, position, onClose }) {
  if (!modifier) return null;
  return (
    <ProfileModal className="nt-small-modal" onClose={onClose} label="Информация о модификаторе">
        <button className="nt-modal-close" type="button" onClick={onClose}>×</button>
        <div className="nt-modal-kicker">Модификатор</div>
        <h3>{modifier.name || modifier.label}</h3>
        <p>{modifier.description || modifier.effect || "Описание модификатора пока не добавлено."}</p>
        <div className="nt-modal-grid"><span>Уровень</span><strong>{modifier.level || modifier.points || 0}</strong></div>
    </ProfileModal>
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
    <ProfileModal className="nt-small-modal" onClose={onClose} closeOnBackdrop={false} label="Улучшение навыка">
        <button className="nt-modal-close" type="button" onClick={onClose}>×</button>
        <div className="nt-modal-kicker">Улучшение навыка</div>
        <h3>{skill.name}</h3>
        <p>Свободные очки навыков: {freePoints}</p>
        {modifiers.length ? (
          <label className="nt-field-label"><span>Модификатор</span><select value={selectedModifier} onChange={(event) => setSelectedModifier(event.target.value)}>{modifiers.map((modifier) => <option key={modifier.id || modifier.name} value={modifier.id || modifier.name}>{modifier.name || modifier.label}</option>)}</select></label>
        ) : null}
        <label className="nt-field-label"><span>Сколько очков вложить</span><input type="number" min="1" max={freePoints} value={amount} onChange={(event) => setAmount(event.target.value)} /></label>
        <footer className="nt-modal-actions"><button type="button" onClick={submit}>Вложить</button><button className="nt-secondary" type="button" onClick={onClose}>Отмена</button></footer>
    </ProfileModal>
  );
}

function SkillCard({ skill, freePoints, mode = "available", readOnly = false, onShowModifier, onOpenUpgrade, onEquipSkill, onUnequipSkill, onUseSkillOutside }) {
  const modifiers = skill.modifiers || [];
  const canUpgrade = !readOnly && freePoints > 0 && skill.upgradeable;
  const details = [
    skill.damage !== undefined && skill.damage !== null ? `Урон: ${skill.damage}` : null,
    skillCostText(skill),
    skillCooldownText(skill),
  ].filter(Boolean);
  const isEquipped = mode === "equipped" || mode === "passive_equipped";
  const actionLabel = isEquipped ? "Снять" : mode === "passive" ? "В пассивный слот" : "В слот";
  const actionHandler = isEquipped ? onUnequipSkill : onEquipSkill;
  // Несовместимое с текущим оружием — только в списке доступных (в слоте уже стоит).
  const weaponBlocked = !isEquipped && skill.weaponRequirementText && skill.weaponCompatible === false;
  const showAction = !readOnly && (isEquipped || mode === "passive" || (canEquipSkill(skill) && !weaponBlocked));
  return (
    <article className="nt-skill-card">
      <div className="nt-skill-main">
        <h3>{skill.name}</h3>
        <p>{skill.description || "Описание навыка пока не добавлено."}</p>
        {skill.weaponRequirementText ? (
          <p className={`nt-skill-weapon-req${weaponBlocked ? " blocked" : ""}`}>
            {weaponBlocked ? "⚠ " : ""}Нужно оружие: {skill.weaponRequirementText}
          </p>
        ) : null}
        {details.length ? <div className="nt-skill-details">{details.map((detail) => <span key={detail}>{detail}</span>)}</div> : null}
        {modifiers.length ? <div className="nt-modifiers">{modifiers.map((modifier) => <button key={modifier.id || modifier.name} type="button" onClick={(event) => onShowModifier(modifier, event)}>{modifier.name || modifier.label} <b>{modifier.level || modifier.points || 0}</b></button>)}</div> : null}
      </div>
      <div className="nt-skill-side">
        <div className="nt-skill-level"><span>Уровень</span><strong>{skill.level || 0}</strong></div>
        {canUpgrade ? <button className="nt-skill-plus" type="button" onClick={(event) => onOpenUpgrade(skill, event)}>+</button> : null}
        {showAction ? <button className="nt-skill-action" type="button" onClick={() => actionHandler?.(skill)}>{actionLabel}</button> : null}
        {!readOnly && skill.works_outside_battle ? <button className="nt-skill-action" type="button" onClick={() => onUseSkillOutside?.(skill)}>Применить</button> : null}
      </div>
    </article>
  );
}

function SkillsTab({ profile, readOnly = false, onSpendSkillPoints, onEquipSkill, onUnequipSkill, onUseSkillOutside }) {
  const [modifierHelp, setModifierHelp] = useState(null);
  const [upgradeSkill, setUpgradeSkill] = useState(null);
  const freePoints = profile.player?.freeSkillPoints || 0;
  const equipped = profile.skills?.equipped || [];
  const equippedKeys = new Set(equipped.map(skillKey));
  const active = (profile.skills?.active || []).filter((skill) => !equippedKeys.has(skillKey(skill)));
  const passive = (profile.skills?.passive || []).filter((skill) => !equippedKeys.has(skillKey(skill)));
  const passiveEquipped = profile.skills?.passiveEquipped || [];
  const sharedProps = {
    freePoints,
    readOnly,
    onShowModifier: (modifier) => setModifierHelp({ modifier }),
    onOpenUpgrade: !readOnly ? (skillToUpgrade) => setUpgradeSkill({ skill: skillToUpgrade }) : undefined,
    onEquipSkill: !readOnly ? onEquipSkill : undefined,
    onUnequipSkill: !readOnly ? onUnequipSkill : undefined,
    onUseSkillOutside: !readOnly ? onUseSkillOutside : undefined,
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
      <CollapsiblePanel title="Активные навыки"><div className="nt-skills-list">{active.length ? active.map((skill) => <SkillCard key={skill.id || skill.name} skill={skill} mode="available" {...sharedProps} />) : <p className="nt-empty-text">Активных навыков пока нет.</p>}</div></CollapsiblePanel>
      <CollapsiblePanel title="Пассивные слоты" right={<span className="nt-badge">{profile.player?.passiveSkillSlotsUsed || 0} / {profile.player?.passiveSkillSlots || 2}</span>}><div className="nt-skills-list">{passiveEquipped.length ? passiveEquipped.map((skill) => <SkillCard key={skill.id || skill.name} skill={skill} mode="passive_equipped" {...sharedProps} />) : <p className="nt-empty-text">Пассивные слоты пусты.</p>}</div></CollapsiblePanel>
      <CollapsiblePanel title="Пассивные навыки"><div className="nt-skills-list">{passive.length ? passive.map((skill) => <SkillCard key={skill.id || skill.name} skill={skill} mode="passive" {...sharedProps} />) : <p className="nt-empty-text">Пассивных навыков пока нет.</p>}</div></CollapsiblePanel>
      <ModifierHelpModal modifier={modifierHelp?.modifier} position={modifierHelp?.position} onClose={() => setModifierHelp(null)} />
      {!readOnly ? <SkillUpgradeModal skill={upgradeSkill?.skill} freePoints={freePoints} position={upgradeSkill?.position} onClose={() => setUpgradeSkill(null)} onSpendSkillPoints={onSpendSkillPoints} /> : null}
    </div>
  );
}

function FinesModal({ fines, onClose }) {
  const placeRu = { city: "городской Управляющий", fortress: "Крепостной Управляющий", profile: "профиль", npc: "NPC", button: "кнопка" };
  const restrictionRu = { block_city: "закрыт город", block_starting: "закрыты стартовые локации", block_market: "закрыт рынок", block_black_market: "закрыт чёрный рынок", block_casino: "закрыто казино", block_transfer: "запрещена передача", block_craft: "запрещено ремесло", force_fortress: "принудительное взыскание" };
  return (
    <ProfileModal className="nt-small-modal" onClose={onClose} label="Городские штрафы">
        <button className="nt-modal-close" type="button" onClick={onClose}>×</button>
        <div className="nt-modal-kicker">Городские штрафы</div>
        <h3>Активные штрафы</h3>
        {fines.length ? fines.map((fine) => (
          <div className="nt-modal-block" key={fine.number}>
            <h4>Штраф №{fine.number}{fine.source ? ` · ${fine.source}` : ""}</h4>
            <div className="nt-modal-grid">
              <span>Сумма</span><strong>{fine.amount}</strong>
              <span>Срок</span><strong>{fine.term}</strong>
              <span>Стадия</span><strong>{fine.stage || fine.status}</strong>
              <span>Получен</span><strong>{fine.createdAt || "—"}</strong>
              <span>Статус</span><strong>{fine.permanent ? "Бессрочный" : fine.status}</strong>
              <span>Где оплатить</span><strong>{(fine.paymentPlaces || []).map((x) => placeRu[x] || x).join(", ") || "—"}</strong>
              {(fine.restrictions || []).length ? <><span>Запреты</span><strong>{fine.restrictions.map((x) => restrictionRu[x] || x).join(", ")}</strong></> : null}
              {(fine.consequences || []).length ? <><span>Последствия</span><strong>{fine.consequences.join(", ")}</strong></> : null}
            </div>
          </div>
        )) : <p>Активных штрафов нет.</p>}
    </ProfileModal>
  );
}

function InfoTab({ profile }) {
  const info = profile.information || {};
  const activity = info.activity || {};
  const crafts = activity.craftingLevels || [];
  const settings=profile.profileLayout?.settings || {};
  const fineList = settings.show_fines === false ? [] : (activity.fineList || []);
  const status = profile.status || null;
  const places = (profile.ratingPlaces || []).filter((p) => p.place !== "—" && p.place != null);
  const reputations = Array.isArray(profile.reputations) ? profile.reputations : [];
  const eventCampaigns = Array.isArray(profile.eventCampaigns) ? profile.eventCampaigns : [];
  const [finesModal, setFinesModal] = useState(null);
  // Блоки вкладки «Журнал» в дефолтном порядке; раскладка может скрыть/переставить.
  const defaultBlocks = [
    // Предупреждения/статус/рейтинги перенесены из убранной вкладки «Обзор» (ТЗ §1).
    { type: "warnings", node: <ProfileWarnings warnings={profile.warnings} /> },
    { type: "activity", node: (
      <Panel title="Активность"><div className="nt-lines">{status ? <Row label="Статус" value={status.label} /> : null}<Row label="Дата регистрации" value={profile.player?.registrationDate || "—"} /><Row label="PVE убийства" value={activity.pveKills || 0} /><Row label="PVP убийства" value={activity.pvpKills || 0} /><Row label="Частицы душ" value={activity.soulParticlesAbsorbed || 0} /><div className="nt-row"><span>Штрафы</span>{fineList.length ? <button type="button" className="nt-fines-button" onClick={() => setFinesModal({ open: true })}>{`${fineList.length} активн. — подробнее`}</button> : <strong>нет активных штрафов</strong>}</div></div></Panel>
    ) },
    { type: "ratings", node: places.length ? (
      <Panel title="Мои места в рейтингах">
        <div className="nt-rating-places">
          {places.map((p) => <div className="nt-rating-place" key={p.key}><span>{p.label}</span><b>{p.place} место</b></div>)}
        </div>
      </Panel>
    ) : null },
    { type: "reputation", node: reputations.length ? (
      <CollapsiblePanel title="Репутация"><div className="nt-card-list nt-column-list">{reputations.map((row) => <div key={row.id} className="nt-mini-card"><CardRow label={row.name || row.id} value={row.stage || (row.value ?? "—")} />{row.value !== undefined && row.stage ? <p>Значение: {row.value}</p> : null}</div>)}</div></CollapsiblePanel>
    ) : null },
    { type: "events", node: eventCampaigns.length ? (
      <CollapsiblePanel title="Эвенты"><div className="nt-card-list nt-column-list">{eventCampaigns.map((row) => <div key={row.id} className="nt-mini-card"><CardRow label={row.name} value={row.status === "completed" ? "Завершён" : `Этап: ${row.stageId || "—"}`} /><p>Очки: {row.points || 0}{row.place ? ` · место: ${row.place}` : ""}</p></div>)}</div></CollapsiblePanel>
    ) : null },
    { type: "crafting", node: (
      <CollapsiblePanel title="Ремёсла"><div className="nt-card-list nt-column-list">{crafts.length ? crafts.map((craft) => <div key={craft.name} className="nt-mini-card"><CardRow label={craft.name} value={`ур. ${craft.level}`} /><p>{craft.exp}</p></div>) : <p className="nt-empty-text">Ремёсла пока не развиты.</p>}</div></CollapsiblePanel>
    ) },
    { type: "achievements", node: (
      <CollapsiblePanel title="Достижения"><div className="nt-card-list nt-column-list">{(info.achievements || []).length ? info.achievements.map((achievement) => <div key={achievement.name || achievement} className="nt-mini-card"><CardRow label={achievement.name || achievement} value="Получено" /><p>{achievement.description || "—"}</p></div>) : <p className="nt-empty-text">Достижений пока нет.</p>}</div></CollapsiblePanel>
    ) },
  ];
  const allowedBlocks=defaultBlocks.filter((block)=>block.type==="ratings" ? settings.show_ratings!==false : block.type==="achievements" ? settings.show_achievements!==false : block.type==="activity" ? settings.show_activity!==false : true);
  const blocks = planProfileBlocks("info", profile.profileLayout, allowedBlocks, profile);
  return (
    <div className="nt-stack">
      {blocks.map((b) => <React.Fragment key={b.type}>{b.node}</React.Fragment>)}
      {finesModal ? <FinesModal fines={fineList} position={finesModal.position} onClose={() => setFinesModal(null)} /> : null}
    </div>
  );
}

function CourierTab({ profile, onSearchRecipients, onSendTransfer }) {
  const courier = profile.courier || {};
  const inventory = profile.inventory || [];
  const balanceCopper = Math.max(0, Number(courier.balanceCopper || 0));
  const letterMax = Math.max(1, Number(courier.letterMaxLength || 30));

  const [receiverQuery, setReceiverQuery] = useState("");
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [receiver, setReceiver] = useState(null);
  const [itemQuery, setItemQuery] = useState("");
  const [selected, setSelected] = useState([]);
  const [letter, setLetter] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const filteredInventory = useMemo(() => inventory.filter((item) => {
    if (!itemQuery) return true;
    return String(item.name || "").toLowerCase().includes(itemQuery.toLowerCase());
  }), [inventory, itemQuery]);

  async function runSearch() {
    const query = receiverQuery.trim();
    if (!query) return;
    setSearching(true);
    setError("");
    try {
      const payload = await onSearchRecipients?.(query);
      setResults(payload?.players || []);
    } catch (requestError) {
      setError(requestError.message || "Поиск не выполнен.");
    } finally {
      setSearching(false);
    }
  }

  function chooseReceiver(entry) {
    setReceiver(entry);
    setReceiverQuery(entry.name || entry.gameId || "");
    setResults([]);
  }

  function addItem(item) {
    const key = `item-${item.inventoryIndex}`;
    if (selected.some((row) => row.key === key)) return;
    setSelected((rows) => [...rows, {
      key,
      isCoins: false,
      itemId: item.id,
      inventoryIndex: item.inventoryIndex,
      name: item.name,
      amount: 1,
      max: Math.max(1, Number(item.amount) || 1),
    }]);
  }

  function addCoins() {
    if (selected.some((row) => row.isCoins)) return;
    if (balanceCopper <= 0) {
      setError("У вас нет монет для отправки.");
      return;
    }
    setSelected((rows) => [...rows, {
      key: "coins",
      isCoins: true,
      name: "Монеты (медные)",
      amount: 1,
      max: balanceCopper,
    }]);
  }

  function setAmount(key, value) {
    setSelected((rows) => rows.map((row) => (
      row.key === key ? { ...row, amount: clamp(Math.floor(Number(value) || 1), 1, row.max) } : row
    )));
  }

  function removeRow(key) {
    setSelected((rows) => rows.filter((row) => row.key !== key));
  }

  function resetForm() {
    setReceiver(null);
    setReceiverQuery("");
    setResults([]);
    setSelected([]);
    setLetter("");
    setItemQuery("");
    setConfirming(false);
  }

  const canSend = Boolean((receiver || receiverQuery.trim()) && selected.length && !busy);

  async function submit() {
    setBusy(true);
    setError("");
    setMessage("");
    const items = selected
      .filter((row) => !row.isCoins)
      .map((row) => ({ item_id: row.itemId, inventory_index: row.inventoryIndex, amount: row.amount }));
    const coinsRow = selected.find((row) => row.isCoins);
    const coins = coinsRow ? coinsRow.amount : 0;
    const target = receiver?.gameId || receiverQuery.trim();
    try {
      const payload = await onSendTransfer?.(target, items, coins, letter.trim());
      setMessage(payload?.message || "Посылка передана гонцу.");
      resetForm();
    } catch (requestError) {
      setError(requestError.message || "Не удалось отправить посылку.");
    } finally {
      setBusy(false);
      setConfirming(false);
    }
  }

  return (
    <div className="nt-stack">
      <Panel title="Передача предметов">
        <p className="nt-courier-warning">{courier.warningText || "Передача предметов через городского гонца."}</p>

        <div className="nt-courier-section">
          <h4>Получатель</h4>
          <div className="nt-toolbar">
            <input
              value={receiverQuery}
              onChange={(event) => { setReceiverQuery(event.target.value); setReceiver(null); }}
              onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); runSearch(); } }}
              placeholder="Ник или игровой ID"
            />
            <button type="button" className="nt-courier-btn" onClick={runSearch} disabled={searching}>
              {searching ? "Поиск…" : "Найти"}
            </button>
          </div>
          {receiver ? (
            <p className="nt-courier-chosen">Выбран получатель: <strong>{receiver.name}</strong> · {receiver.gameId}</p>
          ) : null}
          {results.length ? (
            <div className="nt-courier-results">
              {results.map((entry) => (
                <button type="button" className="nt-courier-result" key={entry.gameId} onClick={() => chooseReceiver(entry)}>
                  <span>{entry.name}</span>
                  <span className="nt-courier-result-meta">ур. {entry.level} · {entry.gameId}</span>
                </button>
              ))}
            </div>
          ) : null}
        </div>

        <div className="nt-courier-section">
          <h4>Что отправить</h4>
          <div className="nt-toolbar">
            <input
              value={itemQuery}
              onChange={(event) => setItemQuery(event.target.value)}
              placeholder="Поиск предмета в инвентаре"
            />
            <button type="button" className="nt-courier-btn" onClick={addCoins}>+ Монеты</button>
          </div>
          <p className="nt-courier-hint">Баланс: {courier.balanceText || "0 мед."}</p>
          <div className="nt-courier-pick-grid">
            {filteredInventory.map((item, index) => (
              <button
                type="button"
                key={itemKey(item, index)}
                className="nt-courier-pick"
                onClick={() => addItem(item)}
                disabled={selected.some((row) => row.key === `item-${item.inventoryIndex}`)}
              >
                <ItemArt item={item} className="nt-courier-pick-art" />
                <span className="nt-courier-pick-name">{item.name}</span>
                <span className="nt-courier-pick-amount">×{item.amount || 1}</span>
              </button>
            ))}
          </div>
          {!filteredInventory.length ? <p className="nt-empty-text">Предметов не найдено.</p> : null}
        </div>

        {selected.length ? (
          <div className="nt-courier-section">
            <h4>В посылке</h4>
            <div className="nt-courier-selected">
              {selected.map((row) => (
                <div className="nt-courier-selected-row" key={row.key}>
                  <span className="nt-courier-selected-name">{row.name}</span>
                  <input
                    type="number"
                    min={1}
                    max={row.max}
                    value={row.amount}
                    onChange={(event) => setAmount(row.key, event.target.value)}
                  />
                  <button type="button" className="nt-courier-remove" onClick={() => removeRow(row.key)} aria-label="Удалить из списка">×</button>
                </div>
              ))}
            </div>
          </div>
        ) : null}

        <div className="nt-courier-section">
          <h4>Письмо</h4>
          <input
            value={letter}
            maxLength={letterMax}
            onChange={(event) => setLetter(event.target.value)}
            placeholder={`Короткое сообщение до ${letterMax} символов`}
          />
          <p className="nt-courier-hint">{letter.length} / {letterMax}</p>
        </div>

        <div className="nt-courier-footer">
          <span className="nt-courier-cost">Стоимость доставки: <strong>{courier.deliveryCostText || "—"}</strong></span>
          {confirming ? (
            <div className="nt-courier-confirm">
              <p>Списать {courier.deliveryCostText} и выбранные вложения сразу. Отправить посылку?</p>
              <div className="nt-courier-confirm-actions">
                <button type="button" className="nt-courier-btn primary" onClick={submit} disabled={busy}>
                  {busy ? "Отправка…" : "Отправить гонцу"}
                </button>
                <button type="button" className="nt-courier-btn" onClick={() => setConfirming(false)} disabled={busy}>Отмена</button>
              </div>
            </div>
          ) : (
            <button type="button" className="nt-courier-btn primary" onClick={() => { setMessage(""); setError(""); setConfirming(true); }} disabled={!canSend}>
              Отправить игроку
            </button>
          )}
        </div>

        {message ? <p className="nt-courier-feedback success">{message}</p> : null}
        {error ? <p className="nt-courier-feedback error">{error}</p> : null}
      </Panel>
    </div>
  );
}

// --- Профиль V2: Промокод (ТЗ §22, сервис «promo») ------------------------
function PromoForm({ onRedeemPromo }) {
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function submit() {
    const value = code.trim();
    if (!value || busy) return;
    setBusy(true);
    setMessage("");
    setError("");
    try {
      const payload = await onRedeemPromo?.(value);
      setMessage(payload?.message || "Промокод успешно применён.");
      setCode("");
    } catch (requestError) {
      setError(requestError.message || "Не удалось применить промокод.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="nt-stack">
      <Panel title="Промокод">
        <p className="nt-courier-hint">Введите промокод, чтобы получить награду. Каждый код можно применить ограниченное число раз.</p>
        <div className="nt-toolbar">
          <input
            value={code}
            onChange={(event) => setCode(event.target.value)}
            onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); submit(); } }}
            placeholder="Например, START100"
            autoComplete="off"
          />
          <button type="button" className="nt-courier-btn primary" onClick={submit} disabled={!code.trim() || busy}>
            {busy ? "Применяем…" : "Применить"}
          </button>
        </div>
        {message ? <p className="nt-courier-feedback success">{message}</p> : null}
        {error ? <p className="nt-courier-feedback error">{error}</p> : null}
      </Panel>
    </div>
  );
}

// --- Профиль V2: вкладка «Сервисы» (ТЗ §22, Передача + Промокод) ----------
function ReferralLinkRow({ label, link }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    try { await navigator.clipboard.writeText(link); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch { /* буфер может быть недоступен */ }
  }
  return (
    <div className="nt-row">
      <span>{label}</span>
      <strong className="nt-summary-value"><span className="nt-summary-text nt-mono">{link}</span><button type="button" className="nt-fines-button" onClick={copy}>{copied ? "Скопировано" : "Копировать"}</button></strong>
    </div>
  );
}

function ReferralPanel({ referral }) {
  const data = referral || {};
  const link = data.link || "";
  const vkLink = data.vkLink || "";
  return (
    <Panel title="Реферальная программа">
      <div className="nt-lines">
        <Row label="Приглашено игроков" value={data.count || 0} />
        {data.code ? <Row label="Ваш код" value={data.code} /> : null}
        {link ? <ReferralLinkRow label="Ссылка Telegram" link={link} /> : null}
        {vkLink ? <ReferralLinkRow label="Ссылка VK" link={vkLink} /> : null}
        {!link && !vkLink ? <p className="nt-empty-text">Ссылка появится после настройки бота. Передайте новичку ваш код — он привяжется при регистрации.</p> : null}
      </div>
    </Panel>
  );
}
function PavilionPanel() {
  const [data,setData]=useState(null);const [error,setError]=useState("");const [pavilionToken,setPavilionToken]=useState("");const profileToken=new URLSearchParams(window.location.search).get("token") || "";
  const load=async()=>{try{let token=pavilionToken;if(!token){const linkResponse=await fetch(`/api/profile/${encodeURIComponent(profileToken)}/pavilion-link`);const linkBody=await linkResponse.json();if(!linkResponse.ok)throw new Error(linkBody.detail || "Павильон недоступен.");token=new URL(linkBody.url,window.location.origin).searchParams.get("token") || "";setPavilionToken(token);}const response=await fetch(`/api/pavilion?token=${encodeURIComponent(token)}`);const body=await response.json();if(!response.ok)throw new Error(body.detail || "Павильон недоступен.");setData(body);}catch(e){setError(e.message)}};
  useEffect(()=>{load()},[]);
  const rent=async()=>{try{const response=await fetch(`/api/pavilion/rent?token=${encodeURIComponent(pavilionToken)}`,{method:"POST"});const body=await response.json();if(!response.ok)throw new Error(body.detail || "Не удалось арендовать павильон.");await load();}catch(e){setError(e.message)}};
  return <Panel title="Торговый павильон">{error?<p className="nt-courier-feedback error">{error}</p>:null}{!data?<p>Загрузка павильона…</p>:<><p>{data.accessActive?"Павильон активен.":"Павильон пока не активирован."}</p>{!data.accessActive?<button type="button" className="nt-courier-btn primary" onClick={rent}>Арендовать павильон</button>:null}<div className="nt-card-list">{(data.items || []).slice(0,20).map(row=><div className="nt-mini-card" key={row.id || row.listing_id}><CardRow label={row.item_name || row.item_id || "Товар"} value={`${row.price || 0} меди`} /></div>)}</div></>}</Panel>;
}

function ServicesTab({ profile, onSearchRecipients, onSendTransfer, onRedeemPromo }) {
  const settings=profile.profileLayout?.settings || {};
  const services = (profile.services || []).filter((service) => service.id === "transfer" ? settings.transfer_enabled !== false && settings.allow_transfer !== false : service.id === "promo" ? settings.promo_enabled !== false : service.id === "pavilion" ? settings.pavilion_enabled !== false : true);
  const [active, setActive] = useState(services[0]?.id || "transfer");
  // Если набор сервисов изменился и текущий пропал — откатываемся на первый.
  useEffect(() => {
    if (!services.some((s) => s.id === active)) setActive(services[0]?.id || "transfer");
  }, [services, active]);

  return (
    <div className="nt-stack">
      {services.length > 1 ? (
        <nav className="nt-subtabs" aria-label="Сервисы">
          {services.map((service) => (
            <button
              key={service.id}
              type="button"
              className={active === service.id ? "active" : ""}
              onClick={() => setActive(service.id)}
            >
              {service.label}
            </button>
          ))}
        </nav>
      ) : null}
      {active === "transfer" ? <CourierTab profile={profile} onSearchRecipients={onSearchRecipients} onSendTransfer={onSendTransfer} /> : null}
      {active === "promo" ? <PromoForm onRedeemPromo={onRedeemPromo} /> : null}
      {active === "pavilion" ? <PavilionPanel /> : null}
      <ReferralPanel referral={profile.referral} />
    </div>
  );
}

// --- Профиль V2: вкладка «Гильдия» (ТЗ §14) ------------------------------
function GuildTab({ guild }) {
  if (!guild) return <div className="nt-stack"><p className="nt-empty-text">Вы не состоите в гильдии.</p></div>;
  const members = Array.isArray(guild.members) ? guild.members : [];
  const rows = [
    ["Название", guild.name],
    ["Ранг", guild.rankLabel || guild.rank],
    ["Уровень", guild.level],
    ["Участники", guild.memberCount ?? (members.length || undefined)],
  ].filter(([, value]) => value !== undefined && value !== null && value !== "");
  return (
    <div className="nt-stack">
      <Panel title={guild.name || "Гильдия"}>
        {rows.length ? <div className="nt-lines">{rows.map(([label, value]) => <Row key={label} label={label} value={value} />)}</div> : null}
        {guild.description ? <p>{guild.description}</p> : null}
      </Panel>
      {members.length ? (
        <CollapsiblePanel title="Состав гильдии">
          <div className="nt-card-list nt-column-list">
            {members.map((member) => (
              <div className="nt-mini-card" key={member.gameId || member.id || member.name}>
                <CardRow label={member.name || member.gameId || "—"} value={member.rankLabel || member.rank || ""} />
                {member.level ? <p>ур. {member.level}</p> : null}
              </div>
            ))}
          </div>
        </CollapsiblePanel>
      ) : null}
    </div>
  );
}

// --- Профиль V2: вкладка «Обзор» (ТЗ §5) ----------------------------------
const RESOURCE_BAR_META = [
  { label: "HP", cls: "nt-bar-hp" },
  { label: "Мана", cls: "nt-bar-mana" },
  { label: "Дух", cls: "nt-bar-spirit" },
  { label: "Энергия", cls: "nt-bar-energy" },
];

function parseResourceValue(value) {
  // "156 / 156" -> { current: 156, max: 156 }
  const parts = String(value || "").split("/");
  const current = Number(String(parts[0] || "").replace(/[^\d.-]/g, "")) || 0;
  const max = Number(String(parts[1] || "").replace(/[^\d.-]/g, "")) || 0;
  return { current, max };
}

function ResourceBars({ parameters = [] }) {
  const byLabel = new Map(parameters.map((p) => [p.label, p.value]));
  return (
    <div className="nt-resource-bars">
      {RESOURCE_BAR_META.map(({ label, cls }) => {
        if (!byLabel.has(label)) return null;
        const { current, max } = parseResourceValue(byLabel.get(label));
        const pct = max > 0 ? Math.max(0, Math.min(100, Math.round((current / max) * 100))) : 0;
        return (
          <div className="nt-resource-bar" key={label}>
            <div className="nt-resource-bar-head"><span>{label}</span><span>{current} / {max}</span></div>
            <div className="nt-resource-bar-track"><div className={`nt-resource-bar-fill ${cls}`} style={{ width: `${pct}%` }} /></div>
          </div>
        );
      })}
    </div>
  );
}

function ProfileWarnings({ warnings = [] }) {
  if (!warnings.length) return null;
  return (
    <div className="nt-warnings">
      {warnings.map((w, i) => (
        <div className={`nt-warning nt-warning-${w.level || "info"}`} key={(w.type || "") + i}>
          <span className="nt-warning-dot" />{w.text}
        </div>
      ))}
    </div>
  );
}


export function PlayerProfile({ profile, readOnly = false, onSpendAttributePoints, onConfirmAttributePoints, onSpendSkillPoints, onEquipItem, onUnequipItem, onUseItem, onRepairItem, onProfileItemAction, onCraftOperation, onClaimCraftDelivery, onDropItem, onSellItem, onEquipSkill, onUnequipSkill, onUseSkillOutside, onEditProfileField, onSearchCourierRecipients, onSendCourierTransfer, onRedeemPromo, onAdminRemoveItem }) {
  const data = profileOrMock(profile);
  const profileSettings = data.profileLayout?.settings || {};
  const [tab, setTab] = useState("character");
  const [modal, setModal] = useState(null);
  const [slotModal, setSlotModal] = useState(null);
  const [dropModal, setDropModal] = useState(null);
  const [sellModal, setSellModal] = useState(null);
  const adminEdit = Boolean(data.adminEdit);
  const effectiveReadOnly = Boolean(readOnly || data.readOnly || profileSettings.allow_profile_edit === false || (data.adminView && !adminEdit));
  const inventoryReadOnly = effectiveReadOnly || profileSettings.allow_inventory_actions === false;
  const skillsReadOnly = effectiveReadOnly || profileSettings.allow_skill_actions === false;
  const hasAvailableServices=(data.services || []).some((service)=>service.id==="transfer" ? profileSettings.transfer_enabled!==false && profileSettings.allow_transfer!==false : service.id==="promo" ? profileSettings.promo_enabled!==false : service.id==="pavilion" ? profileSettings.pavilion_enabled!==false : true);
  // Сервисы (Передача/Промокод) недоступны в админ-просмотре/редактировании
  // чужого профиля — это личные действия игрока от своего лица.
  // «Гильдии» зарезервированы на будущее и пока скрыты.
  const baseTabs = [
    ...TABS,
    ...((effectiveReadOnly || adminEdit || profileSettings.services_enabled === false || !hasAvailableServices) ? [] : [SERVICES_TAB]),
  ];
  // Опубликованная раскладка профиля (ТЗ §3, рантайм) аддитивно переопределяет
  // порядок/подпись/иконку/видимость ИЗВЕСТНЫХ вкладок. Контент рендерится по id,
  // поэтому показываем только вкладки с готовым рендером; неизвестные ключи из
  // конструктора игнорируются. Нет опубликованной раскладки → дефолт без изменений.
  const visibleTabs = applyProfileLayoutTabs(baseTabs, data.profileLayout, data);
  const layoutTheme = data.profileLayout?.theme || null;
  // Защита: если текущая вкладка недоступна (напр. старое состояние «overview»),
  // показываем первую доступную, чтобы профиль не оставался пустым (ТЗ §1).
  const configuredDefault = String(profileSettings.default_tab || "").trim();
  const fallbackTab = visibleTabs.some((t) => t.id === configuredDefault) ? configuredDefault : (visibleTabs[0]?.id || "character");
  const activeTab = visibleTabs.some((t) => t.id === tab) ? tab : fallbackTab;
  const background = data.assets?.background || "/assets/profile/backgrounds/1.png";

  const equipmentBySlot = data.equipment || {};
  const inventory = data.inventory || [];

  function openItem(item, slotKey = null, event = null) {
    setModal({ item, slotKey });
  }

  function openSlot(slot, event = null) {
    if (inventoryReadOnly || slot?.blocked) return;
    const items = inventory.filter((item) => {
      const target = itemSlot(item);
      if (target === slot.key) return true;
      if ((slot.key === "ring1" || slot.key === "ring2") && (target === "ring" || item.type === "Кольцо" || item.type === "ring")) return true;
      return false;
    });
    setSlotModal({ slot, items, selectedItem: items[0] || null });
  }

  async function equipFromSlot(item) {
    if (inventoryReadOnly) return;
    await onEquipItem?.(item, slotModal?.slot?.key || null);
    setSlotModal(null);
  }

  async function equipAndClose(item) {
    if (inventoryReadOnly) return;
    await onEquipItem?.(item);
    setModal(null);
  }

  async function unequipAndClose(slotKey, item) {
    if (inventoryReadOnly) return;
    await onUnequipItem?.(slotKey || itemSlot(item), item);
    setModal(null);
  }

  async function useAndClose(item) {
    if (inventoryReadOnly) return;
    await onUseItem?.(item);
    setModal(null);
  }

  async function dropAndClose(item, amount) {
    if (inventoryReadOnly) return;
    await onDropItem?.(item, amount);
    setDropModal(null);
    setModal(null);
  }

  async function sellAndClose(item, amount) {
    if (inventoryReadOnly) return;
    await onSellItem?.(item, amount);
    setSellModal(null);
    setModal(null);
  }

  async function adminRemoveAndClose(item) {
    if (!adminEdit) return;
    await onAdminRemoveItem?.(item);
    setModal(null);
  }

  function requestDrop(item) {
    if (inventoryReadOnly) return;
    setDropModal({ item, position: modal?.position || null });
  }

  function requestSell(item) {
    if (effectiveReadOnly) return;
    setSellModal({ item, position: modal?.position || null });
  }

  return (
    <main className={`nt-profile ${effectiveReadOnly ? "nt-profile-readonly" : ""}`.trim()} style={{ backgroundImage: `linear-gradient(rgba(5, 7, 7, .32), rgba(4, 4, 4, .50)), url(${layoutTheme?.profile_background || background})`, ...profileThemeStyle(layoutTheme) }}>
      <div className="nt-shell">
        <header className="nt-top">
          <div className="nt-title-block"><h1>{profileSettings.profile_title || "Профиль персонажа"}</h1>{effectiveReadOnly ? <p className="nt-readonly-banner">{profileSettings.readonly_text || "Админский режим: только просмотр, изменения отключены."}</p> : null}</div>
          {profileSettings.show_public_id !== false ? <div className="nt-id">{data.player?.userGlobalId || data.player?.publicId || "NT-UNKNOWN"}</div> : null}
        </header>
        <nav className="nt-tabs" aria-label="Разделы профиля">
          {visibleTabs.map(({ id, label, icon, emoji }) => <button key={id} className={activeTab === id ? "active" : ""} type="button" onClick={() => setTab(id)} title={label} aria-label={label}><span className="nt-tab-icon">{emoji ? <span className="nt-tab-emoji">{emoji}</span> : <TabIcon type={icon} />}</span><span className="nt-tab-text">{label}</span></button>)}
        </nav>
        <section className="nt-content">
          {activeTab === "character" ? <CharacterTab profile={{ ...data, equipment: equipmentBySlot }} readOnly={effectiveReadOnly} onOpenItem={openItem} onOpenSlot={openSlot} onSpendAttributePoints={onSpendAttributePoints} onConfirmAttributePoints={onConfirmAttributePoints} onEditProfileField={onEditProfileField} /> : null}
          {activeTab === "inventory" ? <InventoryTab profile={data} onOpenItem={openItem} readOnly={inventoryReadOnly} onClaimCraftDelivery={onClaimCraftDelivery} onProfileItemAction={onProfileItemAction} /> : null}
          {activeTab === "skills" ? <SkillsTab profile={data} readOnly={skillsReadOnly} onSpendSkillPoints={onSpendSkillPoints} onEquipSkill={onEquipSkill} onUnequipSkill={onUnequipSkill} onUseSkillOutside={onUseSkillOutside} /> : null}
          {activeTab === "info" ? <InfoTab profile={data} /> : null}
          {activeTab === "guild" ? <GuildTab guild={data.guild} /> : null}
          {activeTab === "services" ? <ServicesTab profile={data} onSearchRecipients={onSearchCourierRecipients} onSendTransfer={onSendCourierTransfer} onRedeemPromo={onRedeemPromo} /> : null}
        </section>
      </div>
      <ItemModal item={modal?.item} slotKey={modal?.slotKey} position={modal?.position} readOnly={inventoryReadOnly} adminEdit={adminEdit} actionPermissions={profileSettings} onClose={() => setModal(null)} onEquipItem={equipAndClose} onUnequipItem={unequipAndClose} onUseItem={useAndClose} onRepairItem={async (item) => { await onRepairItem?.(item); setModal(null); }} onProfileItemAction={async (item, action) => { await onProfileItemAction?.(item, action); setModal(null); }} onOpenTransfer={() => { setModal(null); setTab("services"); }} onCraftOperation={async (item, rule) => { await onCraftOperation?.(item, rule); setModal(null); }} onRequestDrop={requestDrop} onRequestSell={requestSell} onAdminRemoveItem={adminRemoveAndClose} />
      {!inventoryReadOnly ? <DropItemModal item={dropModal?.item} position={dropModal?.position} onClose={() => setDropModal(null)} onConfirm={dropAndClose} /> : null}
      {!inventoryReadOnly ? <SellItemModal item={sellModal?.item} position={sellModal?.position} onClose={() => setSellModal(null)} onConfirm={sellAndClose} /> : null}
      <SlotItemsModal slot={slotModal?.slot} items={slotModal?.items || []} selectedItem={slotModal?.selectedItem} position={slotModal?.position} onSelectItem={(item) => setSlotModal((current) => ({ ...current, selectedItem: item }))} onClose={() => setSlotModal(null)} readOnly={inventoryReadOnly} onEquipItem={equipFromSlot} />
    </main>
  );
}

export default PlayerProfile;
