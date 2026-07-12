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


def create_public_site_router(get_storage=None) -> APIRouter:
    router = APIRouter(prefix="/api/public/site", tags=["public-site"])

    @router.get("/menu")
    def menu() -> dict[str, Any]:
        return {"ok": True, "menu": site.published_menu()}

    @router.get("/theme")
    def theme() -> dict[str, Any]:
        themes = site.published(site.KIND_THEME)
        return {"ok": True, "theme": themes[0] if themes else None}

    @router.get("/settings")
    def settings() -> dict[str, Any]:
        raw = site.active_site_settings()
        public = {key: raw.get(key) for key in ("maintenance_enabled", "maintenance_page_id", "error_page_id", "environment")}
        # Отдаём уже отфильтрованные опубликованные страницы, а не технические
        # данные настроек. Клиент использует их для штатных состояний сайта.
        public["maintenance_page"] = site.published_page(str(raw.get("maintenance_page_id") or ""))
        public["error_page"] = site.published_page(str(raw.get("error_page_id") or ""))
        return {"ok": True, "settings": public if raw else None}

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
        return {"ok": True, "ratings": [_rating_view(row) for row in site.published(site.KIND_RATING)]}

    @router.get("/rating/{rating_id}")
    def rating(rating_id: str) -> dict[str, Any]:
        row = next((x for x in site.published(site.KIND_RATING) if str(x.get("id")) == rating_id), None)
        if row is None:
            raise HTTPException(status_code=404, detail="Рейтинг не найден или скрыт.")
        return {"ok": True, "rating": _rating_view(row)}

    def _rating_view(row: dict[str, Any]) -> dict[str, Any]:
        result = dict(row)
        result["entries"] = []
        if get_storage is None or row.get("visible") is False:
            return result
        storage = get_storage()
        rows = storage.list_player_audience_rows() if hasattr(storage, "list_player_audience_rows") else []
        rating_type = str(row.get("rating_type") or "level")
        paths = {
            "level": ("level",), "exp": ("experience",), "pve": ("pve_wins",),
            "wins": ("pve_wins",), "pvp": ("pvp_wins",), "craft": ("craft_count",),
            "events": ("event_points",), "raids": ("raid_wins",), "wealth": ("wealth",),
        }
        key = paths.get(rating_type, (rating_type,))[0]
        entries = []
        for brief in rows[:5000]:
            player = storage.get_player_by_game_id(str(brief.get("game_id") or "")) or {}
            value = player.get(key, brief.get(key, 0))
            if key == "wealth" and not row.get("allow_wealth"):
                continue
            try: score = float(value or 0)
            except (TypeError, ValueError): score = 0.0
            entries.append({"name": str(player.get("name") or "Игрок"), "value": score})
        entries.sort(key=lambda x: (-x["value"], x["name"]))
        limit = max(1, min(int(row.get("limit") or 100), 500))
        show_values = row.get("show_values", True) is not False
        result["entries"] = [
            {"place": index, "name": item["name"], **({"value": item["value"]} if show_values else {})}
            for index, item in enumerate(entries[:limit], 1)
        ]
        return result

    @router.get("/banners")
    def banners() -> dict[str, Any]:
        return {"ok": True, "banners": site.published(site.KIND_BANNER), "announcements": site.published(site.KIND_ANNOUNCEMENT)}

    return router
