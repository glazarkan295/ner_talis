import React from "react";

// «Поиск по созданным» (дополнение к ТЗ): единый клиентский фильтр по уже
// загруженному списку объектов конструктора. Ищет по id/статусу/коду и по всем
// строковым/числовым значениям data (название/тип/категория/описание/источник…).

export function itemSearchText(item) {
  if (!item || typeof item !== "object") return "";
  const bag = [];
  const push = (v) => { if (typeof v === "string" || typeof v === "number") bag.push(String(v)); };
  push(item.id); push(item.status); push(item.code);
  const data = item.data && typeof item.data === "object" ? item.data : item;
  for (const v of Object.values(data)) push(v);
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

// Сообщение «ничего не найдено» (когда фильтр задан, но список пуст).
export function NoResults({ query }) {
  if (!String(query || "").trim()) return null;
  return <p className="ntv2-hint">Ничего не найдено. Попробуйте изменить запрос или фильтры.</p>;
}
