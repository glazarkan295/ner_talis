// Публичный сайт: чтение опубликованного контента (ТЗ §2). Без авторизации.
const base = "/api/public/site";

async function getJson(url) {
  const res = await fetch(url, { headers: { Accept: "application/json" } });
  if (!res.ok) throw new Error(`Запрос не выполнен (${res.status}).`);
  return res.json();
}

export const fetchMenu = () => getJson(`${base}/menu`);
export const fetchTheme = () => getJson(`${base}/theme`);
export const fetchSettings = () => getJson(`${base}/settings`);
export const fetchPages = () => getJson(`${base}/pages`);
export const fetchPage = (slug) => getJson(`${base}/page/${encodeURIComponent(slug)}`);
export const fetchNews = () => getJson(`${base}/news`);
export const fetchGuides = () => getJson(`${base}/guides`);
export const fetchFaq = () => getJson(`${base}/faq`);
export const fetchLore = () => getJson(`${base}/lore`);
export const fetchWhereIs = () => getJson(`${base}/where-is`);
export const fetchRatings = () => getJson(`${base}/ratings`);
export const fetchBanners = () => getJson(`${base}/banners`);

// Текущий slug из пути /site/<slug> (или null → главная/первая страница).
export function currentSlug() {
  const m = String(window.location.pathname || "").match(/^\/site\/([^/?#]+)/);
  return m ? decodeURIComponent(m[1]) : null;
}

export function isPublicSitePath() {
  return /^\/site(\/|$)/.test(String(window.location.pathname || ""));
}
