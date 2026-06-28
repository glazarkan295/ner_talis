import React from "react";

// «Поиск по созданным» (дополнение к ТЗ): единый клиентский фильтр по уже
// загруженному списку объектов конструктора. Ищет по id/статусу/коду и по всем
// строковым/числовым значениям data (название/тип/категория/описание/источник…).

export function itemSearchText(item) {
  if (!item || typeof item !== "object") return "";
  const bag = [];
  // Рекурсивно собираем вложенные примитивы: значения могут лежать в массивах/
  // объектах (ingredients[].item_id, conditions[].target, rewards, special_loot…),
  // и без обхода поиск по связанным id никогда бы не находил их.
  const visit = (v, depth) => {
    if (v == null || depth > 6) return;
    if (typeof v === "string" || typeof v === "number") { bag.push(String(v)); return; }
    if (Array.isArray(v)) { for (const x of v) visit(x, depth + 1); return; }
    if (typeof v === "object") { for (const x of Object.values(v)) visit(x, depth + 1); return; }
  };
  visit(item.id, 0); visit(item.status, 0); visit(item.code, 0);
  const data = item.data && typeof item.data === "object" ? item.data : item;
  visit(data, 0);
  return bag.join(" ").toLowerCase();
}

export function filterEntities(items, query) {
  const q = String(query || "").trim().toLowerCase();
  if (!q) return Array.isArray(items) ? items : [];
  return (Array.isArray(items) ? items : []).filter((i) => itemSearchText(i).includes(q));
}

// Поле поиска. value/onChange управляют строкой запроса.
export function SearchBox({ value, onChange, placeholder = "Поиск по созданным (название, ID, тип, статус…)" }) {
  return (
    <input
      className="ntv2-search-box"
      type="search"
      value={value}
      placeholder={placeholder}
      onChange={(e) => onChange(e.target.value)}
      aria-label="Поиск по созданным"
    />
  );
}

// Сообщение «ничего не найдено» — только когда фильтр задан И ОТФИЛЬТРОВАННЫЙ
// список пуст (иначе сообщение ошибочно показывалось над найденными строками).
export function NoResults({ items, query }) {
  const q = String(query || "").trim();
  if (!q) return null;
  if (filterEntities(items, q).length > 0) return null;
  return <p className="ntv2-hint">Ничего не найдено. Попробуйте изменить запрос или фильтры.</p>;
}
