import React, { useCallback, useEffect, useMemo, useState } from "react";
import "./PublicSite.css";
import {
  currentSlug,
  fetchFaq,
  fetchGuides,
  fetchLore,
  fetchMenu,
  fetchNews,
  fetchPage,
  fetchPages,
  fetchRatings,
  fetchTheme,
  fetchWhereIs,
} from "../../api/publicSiteApi.js";

// Применить опубликованное оформление сайта (цвета/фон) как CSS-переменные.
function themeVars(theme) {
  if (!theme) return {};
  const v = {};
  if (theme.panel_color) v["--ps-panel"] = theme.panel_color;
  if (theme.card_color) v["--ps-card"] = theme.card_color;
  if (theme.button_color) v["--ps-button"] = theme.button_color;
  if (theme.text_color) v["--ps-text"] = theme.text_color;
  if (theme.link_color) v["--ps-link"] = theme.link_color;
  if (theme.warning_color) v["--ps-warning"] = theme.warning_color;
  if (theme.site_background) v["--ps-bg-image"] = `url(${theme.site_background})`;
  return v;
}

function navigate(slug) {
  const path = slug ? `/site/${encodeURIComponent(slug)}` : "/site";
  window.history.pushState({}, "", path);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

function MenuLink({ item }) {
  const go = (e) => {
    if (item.page_id || item.slug) { e.preventDefault(); navigate(item.slug || item.page_id); }
  };
  const href = item.link || (item.slug || item.page_id ? `/site/${item.slug || item.page_id}` : "#");
  return (
    <span className="ps-nav-item">
      <a href={href} onClick={go} {...(item.link ? { target: "_blank", rel: "noreferrer" } : {})}>
        {item.icon ? `${item.icon} ` : ""}{item.label}
      </a>
      {Array.isArray(item.children) && item.children.length ? (
        <div className="ps-nav-children">{item.children.map((c) => <MenuLink key={c.id} item={c} />)}</div>
      ) : null}
    </span>
  );
}

// Рендер одного блока страницы по типу (ТЗ §2.4).
function Block({ block, dynamic }) {
  const t = block.block_type;
  const text = block.content || "";
  if (t === "heading") return <h2 className="ps-block-heading">{text || block.title}</h2>;
  if (t === "quote") return <blockquote className="ps-block-quote">{text}</blockquote>;
  if (t === "warning") return <div className="ps-block-warning">⚠️ {text}</div>;
  if (t === "image" || t === "gallery") return block.image ? <img className="ps-block-image" src={block.image} alt={block.title || ""} /> : null;
  if (t === "banner") return <div className="ps-block-banner">{block.image ? <img src={block.image} alt="" /> : null}<div>{text}</div></div>;
  if (t === "button" || t === "link") {
    const href = block.link || "#";
    return <a className="ps-block-button" href={href} target="_blank" rel="noreferrer">{block.title || text || "Подробнее"}</a>;
  }
  if (t === "card") return <div className="ps-block-card"><h3>{block.title}</h3><p>{text}</p></div>;
  // Динамические блоки — подставляем опубликованные списки.
  if (dynamic && dynamic[t]) return <DynamicList kind={t} items={dynamic[t]} title={block.title} />;
  // text / list / table / прочее — как текст с переносами строк.
  return <div className="ps-block-text">{block.title ? <h3>{block.title}</h3> : null}<p>{text}</p></div>;
}

function DynamicList({ kind, items, title }) {
  const heading = title || { news: "Новости", guide: "Гайды", faq: "Вопросы и ответы", lore: "Лор", rating: "Рейтинги", where_is: "Что где находится" }[kind] || "";
  return (
    <div className="ps-dynamic">
      {heading ? <h3>{heading}</h3> : null}
      <div className="ps-cards">
        {items.map((it) => (
          <div className="ps-card" key={it.id}>
            <b>{it.title || it.question || it.label || it.id}</b>
            <p>{it.short_description || it.answer || it.text || it.description || it.body || ""}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

export function PublicSite() {
  const [menu, setMenu] = useState([]);
  const [theme, setTheme] = useState(null);
  const [pages, setPages] = useState([]);
  const [page, setPage] = useState(null);
  const [dynamic, setDynamic] = useState({});
  const [slug, setSlug] = useState(() => currentSlug());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const onPop = () => setSlug(currentSlug());
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  // Базовые данные (меню/оформление/список страниц + динамические списки) — один раз.
  useEffect(() => {
    (async () => {
      try {
        const [m, th, pg, news, guides, faq, lore, where_is, ratings] = await Promise.all([
          fetchMenu().catch(() => ({ menu: [] })),
          fetchTheme().catch(() => ({ theme: null })),
          fetchPages().catch(() => ({ pages: [] })),
          fetchNews().catch(() => ({ news: [] })),
          fetchGuides().catch(() => ({ guides: [] })),
          fetchFaq().catch(() => ({ faq: [] })),
          fetchLore().catch(() => ({ lore: [] })),
          fetchWhereIs().catch(() => ({ items: [] })),
          fetchRatings().catch(() => ({ ratings: [] })),
        ]);
        setMenu(m.menu || []);
        setTheme(th.theme || null);
        setPages(pg.pages || []);
        setDynamic({
          news: [...(news.news || []), ...(news.posts || [])], guide: guides.guides || [],
          faq: faq.faq || [], lore: lore.lore || [], where_is: where_is.items || [], rating: ratings.ratings || [],
        });
      } catch (e) {
        setError(e.message || "Не удалось загрузить сайт.");
      }
    })();
  }, []);

  const loadPage = useCallback(async (targetSlug) => {
    setLoading(true);
    setError("");
    try {
      const effective = targetSlug || (pages[0] && (pages[0].slug || pages[0].id));
      if (!effective) { setPage(null); setLoading(false); return; }
      const resp = await fetchPage(effective);
      setPage(resp.page || null);
    } catch (e) {
      setPage(null);
      setError(e.message?.includes("404") ? "Страница не найдена." : (e.message || "Ошибка загрузки страницы."));
    } finally {
      setLoading(false);
    }
  }, [pages]);

  useEffect(() => { loadPage(slug); }, [slug, loadPage]);

  const style = useMemo(() => themeVars(theme), [theme]);

  return (
    <div className="ps-root" style={style}>
      <header className="ps-header">
        <div className="ps-brand" onClick={() => navigate(null)} role="button" tabIndex={0}>Нер-Талис</div>
        <nav className="ps-nav">{menu.map((m) => <MenuLink key={m.id} item={m} />)}</nav>
      </header>

      <main className="ps-main">
        {loading ? <p className="ps-hint">Загрузка…</p> : null}
        {error ? <p className="ps-error">{error}</p> : null}
        {!loading && page ? (
          <article className="ps-page">
            <h1>{page.title}</h1>
            {page.short_description ? <p className="ps-lead">{page.short_description}</p> : null}
            {page.image ? <img className="ps-block-image" src={page.image} alt="" /> : null}
            {page.body ? <div className="ps-block-text"><p>{page.body}</p></div> : null}
            {(page.blocks || []).map((b) => <Block key={b.id} block={b} dynamic={dynamic} />)}
          </article>
        ) : null}
        {!loading && !page && !error ? (
          <div className="ps-page">
            <h1>Нер-Талис</h1>
            <p className="ps-lead">Добро пожаловать. Выберите раздел в меню.</p>
            {pages.length ? (
              <div className="ps-cards">
                {pages.map((p) => (
                  <div className="ps-card ps-card-link" key={p.id} onClick={() => navigate(p.slug || p.id)} role="button" tabIndex={0}>
                    <b>{p.title}</b><p>{p.short_description || ""}</p>
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        ) : null}
      </main>

      <footer className="ps-footer">Нер-Талис · игровой проект</footer>
    </div>
  );
}
