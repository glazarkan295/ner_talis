"""Публичный API сайта (рантайм конструктора сайта, ТЗ §2).

Только ЧТЕНИЕ и только ОПУБЛИКОВАННЫЙ контент: страницы/блоки/меню/новости/гайды/
FAQ/лор/«что где находится»/рейтинги/оформление. Без авторизации — это публичный
сайт проекта, на который может зайти любой посетитель. Авторинг и черновики — в
admin_site_api (под RBAC); здесь отдаётся уже опубликованное, без технических
полей. Не затрагивает игровой процесс (бой/экономику).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from services import site_content_registry as site


def create_public_site_router() -> APIRouter:
    router = APIRouter(prefix="/api/public/site", tags=["public-site"])

    @router.get("/menu")
    def menu() -> dict[str, Any]:
        return {"ok": True, "menu": site.published_menu()}

    @router.get("/theme")
    def theme() -> dict[str, Any]:
        themes = site.published(site.KIND_THEME)
        return {"ok": True, "theme": themes[0] if themes else None}

    @router.get("/pages")
    def pages() -> dict[str, Any]:
        # Список страниц без тяжёлого тела — для навигации/карты сайта.
        items = [
            {"id": p["id"], "slug": p.get("slug") or p["id"], "title": p.get("title"),
             "short_description": p.get("short_description"), "menu_order": p.get("menu_order")}
            for p in site.published(site.KIND_PAGE)
        ]
        return {"ok": True, "pages": items}

    @router.get("/page/{slug}")
    def page(slug: str) -> dict[str, Any]:
        found = site.published_page(slug)
        if found is None:
            raise HTTPException(status_code=404, detail="Страница не найдена.")
        return {"ok": True, "page": found}

    @router.get("/news")
    def news() -> dict[str, Any]:
        return {"ok": True, "news": site.published(site.KIND_NEWS), "posts": site.published(site.KIND_POST)}

    @router.get("/guides")
    def guides() -> dict[str, Any]:
        return {"ok": True, "guides": site.published(site.KIND_GUIDE)}

    @router.get("/faq")
    def faq() -> dict[str, Any]:
        return {"ok": True, "faq": site.published(site.KIND_FAQ)}

    @router.get("/lore")
    def lore() -> dict[str, Any]:
        return {"ok": True, "lore": site.published(site.KIND_LORE)}

    @router.get("/where-is")
    def where_is() -> dict[str, Any]:
        return {"ok": True, "items": site.published(site.KIND_WHERE_IS)}

    @router.get("/ratings")
    def ratings() -> dict[str, Any]:
        return {"ok": True, "ratings": site.published(site.KIND_RATING)}

    @router.get("/banners")
    def banners() -> dict[str, Any]:
        return {"ok": True, "banners": site.published(site.KIND_BANNER), "announcements": site.published(site.KIND_ANNOUNCEMENT)}

    return router
