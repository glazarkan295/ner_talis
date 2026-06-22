// Единый справочник русских названий ПРЕДМЕТОВ для профиля игрока (ТЗ
// «русские названия предметов»). Технические значения (англ. id/коды) остаются
// в данных, а в интерфейсе профиля показываются понятные русские названия.
// Значения уже на русском проходят без изменений (passthrough) — один код = одно
// название во всём профиле (инвентарь/экипировка/карточка/передача/продажа).

// Тип предмета.
export const ITEM_TYPE = {
  weapon: "Оружие", armor: "Броня", shield: "Щит", artifact: "Артефакт",
  one_time_artifact: "Одноразовый артефакт", special_slot: "Особый слот",
  consumable: "Расходуемый предмет", potion: "Зелье", food: "Еда", material: "Материал",
  resource: "Ресурс", ingredient: "Ингредиент", recipe: "Рецепт", quest: "Квестовый предмет",
  quest_item: "Квестовый предмет", ammo: "Боеприпас", ammunition: "Боеприпас", quiver: "Колчан",
  tool: "Инструмент", ring: "Кольцо", necklace: "Ожерелье", accessory: "Аксессуар",
  jewelry: "Украшение", scroll: "Свиток", book: "Книга", key: "Ключ", currency: "Валюта",
  container: "Контейнер", bag: "Подсумок", gem: "Камень", rune: "Руна", trophy: "Трофей",
  normal: "Обычный предмет", equippable: "Экипируемый", craft: "Ремесленный",
};

// Категория предмета.
export const ITEM_CATEGORY = {
  weapon: "Оружие", one_handed_weapon: "Одноручное оружие", two_handed_weapon: "Двуручное оружие",
  armor: "Броня", light_armor: "Лёгкая броня", medium_armor: "Средняя броня", heavy_armor: "Тяжёлая броня",
  cloth_armor: "Тканевая броня", accessory: "Аксессуар", consumable: "Расходники", consumables: "Расходники",
  material: "Материалы", materials: "Материалы", resource: "Ресурсы", resources: "Ресурсы",
  ingredient: "Ингредиенты", recipe: "Рецепты", quest: "Квестовые", quest_item: "Квестовые",
  jewelry: "Украшения", ammo: "Боеприпасы", ammunition: "Боеприпасы", tool: "Инструменты",
  potion: "Зелья", food: "Еда", artifact: "Артефакты", special: "Особые", gem: "Камни", trophy: "Трофеи",
};

// Качество / редкость.
export const ITEM_QUALITY = {
  trash: "Хлам", poor: "Плохое", common: "Обычный", uncommon: "Необычный", rare: "Редкий",
  epic: "Эпический", legendary: "Легендарный", mythic: "Мифический", divine: "Божественный",
  unique: "Уникальный", artifact: "Артефактное", set: "Комплектное",
};

// Слот экипировки (включает ключи слотов профиля).
export const ITEM_SLOT = {
  head: "Голова", helmet: "Шлем", chest: "Нагрудник", body: "Нагрудник", legs: "Штаны", pants: "Штаны",
  gloves: "Перчатки", hands: "Перчатки", boots: "Ботинки", feet: "Ботинки", belt: "Пояс",
  main_hand: "Основная рука", off_hand: "Вторая рука", two_hands: "Две руки", weapon: "Оружие",
  weapon1: "Оружие 1", weapon2: "Оружие 2", staff: "Посох", spellbook: "Магическая книга",
  shield: "Щит", ring: "Кольцо", ring1: "Кольцо 1", ring2: "Кольцо 2", necklace: "Ожерелье",
  amulet: "Амулет", special: "Особый слот", bag: "Подсумок", arrow_quiver: "Колчан стрел",
  bolt_quiver: "Колчан болтов",
};

// Свойства/характеристики предмета.
export const ITEM_PROPERTY = {
  strength: "Сила", stamina: "Выносливость", endurance: "Выносливость", agility: "Ловкость",
  dexterity: "Ловкость", perception: "Восприятие", intelligence: "Интеллект", wisdom: "Мудрость",
  hp: "Здоровье", health: "Здоровье", mana: "Мана", spirit: "Дух", energy: "Энергия",
  physical_damage: "Физический урон", magic_damage: "Магический урон", phys_defense: "Физическая защита",
  mag_defense: "Магическая защита", armor: "Броня", accuracy: "Точность", evasion: "Уклонение",
  crit_chance: "Шанс крита", crit_damage: "Урон крита", hp_regen: "Реген. здоровья",
  mana_regen: "Реген. маны",
};

// Источник получения предмета.
export const ITEM_SOURCE = {
  promo_code: "Промокод", promo: "Промокод", quest: "Задание", craft: "Ремесло", crafting: "Ремесло",
  market: "Рынок", shop: "Магазин", drop: "Добыча с монстра", mob_drop: "Добыча с монстра",
  loot: "Добыча", search: "Поиск", gather: "Сбор", fishing: "Рыбалка", chest: "Сундук",
  event: "Событие", reward: "Награда", gift: "Подарок", admin: "От администрации", starter: "Стартовый набор",
  starter_pack: "Стартовый набор", achievement: "За достижение",
};

const _norm = (v) => String(v == null ? "" : v).trim();

// Перевод значения по таблице: код → русское; русское/неизвестное — как есть.
export function trItem(map, value) {
  const raw = _norm(value);
  if (!raw) return "";
  return map[raw] || map[raw.toLowerCase()] || raw;
}

export const itemTypeRu = (v) => trItem(ITEM_TYPE, v);
export const itemCategoryRu = (v) => trItem(ITEM_CATEGORY, v);
export const itemQualityRu = (v) => trItem(ITEM_QUALITY, v);
export const itemSlotRu = (v) => trItem(ITEM_SLOT, v);
export const itemPropertyRu = (v) => trItem(ITEM_PROPERTY, v);
export const itemSourceRu = (v) => trItem(ITEM_SOURCE, v);

// Да/Нет для булевых характеристик (передача/продажа/использование/стак).
export function yesNo(value) {
  return value ? "Да" : "Нет";
}
