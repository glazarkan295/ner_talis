"""FastAPI website for Ner-Talis.

The app serves:
- health checks for Timeweb;
- temporary bot links: /profile?token=... and /profile/<token>;
- React profile UI from web/dist when it is built;
- JSON API for the React UI;
- small fallback HTML profile when web/dist is absent.
"""

from __future__ import annotations

import html
import logging
import os
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from project_paths import resolve_project_path
from services.web_profile import PAVILION_SCOPE, PROFILE_SCOPE
from admin_panel_api import create_admin_panel_router
from admin_panel_v2_api import create_admin_panel_v2_router
from admin_world_api import create_admin_world_router
from admin_community_api import create_admin_community_router
from admin_achievement_api import create_admin_achievement_router
from admin_messages_api import create_admin_messages_router
from admin_item_api import create_admin_item_router
from admin_effect_api import create_admin_effect_router
from admin_fines_api import create_admin_fines_router
from admin_skills_api import create_admin_skills_router
from admin_promos_api import create_admin_promos_router
from admin_profile_layout_api import create_admin_profile_layout_router
from admin_city_api import create_admin_city_router
from admin_recipes_api import create_admin_recipes_router
from admin_camp_api import create_admin_camp_router
from admin_graph_api import create_admin_graph_router
from admin_sublocation_api import create_admin_sublocation_router
from admin_formula_api import create_admin_formula_router
from admin_trait_api import create_admin_trait_router
from admin_blessing_api import create_admin_blessing_router
from admin_phase_api import create_admin_phase_router
from admin_progression_api import (
    create_admin_levels_router,
    create_admin_exp_router,
    create_admin_registration_router,
    create_admin_races_router,
)
from admin_import_api import create_admin_import_router
from admin_uploads_api import create_admin_uploads_router
from admin_site_api import create_admin_site_router
from public_site_api import create_public_site_router
from site_api import (
    create_profile_api_router,
    frontend_profile,
    get_player_by_public_id,
)
from storage.storage_factory import create_storage

logger = logging.getLogger(__name__)

WEB_DIR = resolve_project_path("web")
WEB_DIST_DIR = WEB_DIR / "dist"
WEB_PUBLIC_DIR = WEB_DIR / "public"
WEB_INDEX_FILE = WEB_DIST_DIR / "index.html"
PUBLIC_UPLOADS_ASSETS_DIR = resolve_project_path(os.getenv("PUBLIC_UPLOADS_ASSETS_DIR", "data/public_uploads/assets"))


def _safe_text(value: Any, default: str = "—") -> str:
    if value is None or value == "":
        return default
    return html.escape(str(value))


def _public_player(player: dict[str, Any]) -> dict[str, Any]:
    # Public view intentionally excludes inventory, equipment, money, stats,
    # linked accounts and other gameplay details. Full profile data is private
    # and available only through a bot-issued active session.
    return {
        "public_id": player.get("public_id"),
        "name": player.get("name"),
        "race_name": player.get("race_name"),
        "level": player.get("level", 1),
    }


def _stat_label(key: str) -> str:
    return {
        "strength": "Сила",
        "dexterity": "Ловкость",
        "endurance": "Выносливость",
        "intelligence": "Интеллект",
        "wisdom": "Мудрость",
        "perception": "Восприятие",
    }.get(key, key)


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _render_profile_html(player: dict[str, Any], session: dict[str, Any] | None = None) -> str:
    public_player = _public_player(player)
    stats = public_player.get("stats") or {}
    stat_rows = "".join(
        f"<tr><td>{_safe_text(_stat_label(key))}</td><td>{_safe_text(value)}</td></tr>"
        for key, value in stats.items()
    ) or "<tr><td colspan='2'>Характеристики пока не заполнены.</td></tr>"
    linked_accounts = ", ".join(public_player.get("linked_accounts") or []) or "—"
    expires_text = _safe_text((session or {}).get("expires_at")) if session else "публичная ссылка"
    return f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Профиль Нер-Талис</title><style>
:root{{color-scheme:dark}}body{{margin:0;min-height:100vh;font-family:Georgia,'Times New Roman',serif;color:#f1dfbd;background:radial-gradient(circle at top,#2a2019 0,#0d0b0a 52%,#050403 100%)}}
.wrap{{max-width:920px;margin:0 auto;padding:36px 18px}}.card{{border:1px solid rgba(214,172,91,.45);border-radius:22px;padding:28px;background:linear-gradient(145deg,rgba(43,31,22,.94),rgba(16,13,11,.96));box-shadow:0 24px 70px rgba(0,0,0,.55),inset 0 1px rgba(255,255,255,.08)}}
h1{{margin:0 0 8px;font-size:34px;color:#ffd98f}}h2{{margin-top:28px;color:#ffd98f}}.muted{{color:#b9a27c}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px;margin-top:22px}}.box{{border:1px solid rgba(255,217,143,.18);border-radius:16px;padding:16px;background:rgba(255,255,255,.035)}}.label{{color:#a99471;font-size:13px}}.value{{font-size:20px;margin-top:4px}}table{{width:100%;border-collapse:collapse;margin-top:14px}}td{{border-bottom:1px solid rgba(255,217,143,.12);padding:10px 0}}td:last-child{{text-align:right;color:#ffd98f}}.footer{{margin-top:18px;font-size:13px;color:#8f7c5d}}
</style></head><body><main class="wrap"><section class="card">
<div class="muted">Мир Нер-Талис</div><h1>{_safe_text(public_player.get('name'))}</h1>
<div class="muted">Профиль открыт по защищённой временной ссылке.</div>
<div class="grid"><div class="box"><div class="label">Раса</div><div class="value">{_safe_text(public_player.get('race_name'))}</div></div><div class="box"><div class="label">Уровень</div><div class="value">{_safe_text(public_player.get('level'))}</div></div></div>
<div class="footer">Сессия: {expires_text}</div>
</section></main></body></html>"""


def _error_html(title: str, message: str, status_code: int = 400) -> HTMLResponse:
    content = f"""<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{_safe_text(title)}</title><style>body{{margin:0;min-height:100vh;background:#0d0b0a;color:#f1dfbd;font-family:Georgia,'Times New Roman',serif;display:grid;place-items:center}}.card{{max-width:720px;margin:24px;padding:28px;border:1px solid rgba(214,172,91,.45);border-radius:22px;background:#1b1511}}h1{{color:#ffd98f}}</style></head><body><section class="card"><h1>{_safe_text(title)}</h1><p>{_safe_text(message)}</p><p>Создайте новую ссылку кнопкой «Профиль на сайте» в боте.</p></section></body></html>"""
    return HTMLResponse(content, status_code=status_code)


def _react_index_or_none() -> FileResponse | None:
    if WEB_INDEX_FILE.exists():
        return FileResponse(WEB_INDEX_FILE)
    return None


def _csv_env(name: str, default: str) -> list[str]:
    raw = os.getenv(name, default)
    return [part.strip() for part in raw.split(",") if part.strip()]

def _truthy_env(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().casefold() in {"1", "true", "yes", "on", "да"}


def _client_ip_for_rate_limit(request: Request) -> str:
    direct_ip = request.client.host if request.client else "unknown"
    # Do not trust spoofable proxy headers by default. X-Forwarded-For is used
    # only when explicitly enabled and the immediate peer is a known proxy.
    if _truthy_env("TRUST_PROXY_HEADERS", "false"):
        trusted_proxies = set(_csv_env("TRUSTED_PROXY_IPS", "127.0.0.1,::1"))
        if direct_ip in trusted_proxies:
            forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
            if forwarded:
                return forwarded
    return direct_ip


def _request_is_https(request: Request) -> bool:
    """HTTPS ли запрос. X-Forwarded-Proto подделывается прямым HTTP-клиентом,
    поэтому доверяем ему только при TRUST_PROXY_HEADERS и доверенном ближайшем
    узле — та же модель доверия, что и для IP в _client_ip_for_rate_limit.
    Иначе FORCE_HTTPS обходится спуфом заголовка на любом прямом развёртывании."""
    if request.url.scheme == "https":
        return True
    if _truthy_env("TRUST_PROXY_HEADERS", "false"):
        direct_ip = request.client.host if request.client else "unknown"
        trusted_proxies = set(_csv_env("TRUSTED_PROXY_IPS", "127.0.0.1,::1"))
        if direct_ip in trusted_proxies:
            proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
            if proto == "https":
                return True
    return False


def _safe_uploaded_asset_path(asset_path: str) -> Path | None:
    relative = Path(str(asset_path or ""))
    if relative.is_absolute() or ".." in relative.parts:
        return None
    candidate = (PUBLIC_UPLOADS_ASSETS_DIR / "admin_uploads" / relative).resolve()
    base = (PUBLIC_UPLOADS_ASSETS_DIR / "admin_uploads").resolve()
    try:
        candidate.relative_to(base)
    except ValueError:
        return None
    return candidate


def _security_headers_for(path: str) -> dict[str, str]:
    headers = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer",
        "Permissions-Policy": "geolocation=(), microphone=(), camera=(), payment=(), usb=()",
        "Content-Security-Policy": (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "font-src 'self' data:; "
            "connect-src 'self'; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "form-action 'self'; "
            "frame-ancestors 'none'"
        ),
    }
    if os.getenv("ENABLE_HSTS", "true").strip().casefold() in {"1", "true", "yes", "on", "да"}:
        headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    if path.startswith("/api/") or path.startswith("/profile") or path.startswith("/pavilion"):
        headers["Cache-Control"] = "no-store, max-age=0"
        headers["Pragma"] = "no-cache"
    return headers


_web_background_workers_started = False


def _start_web_background_workers() -> None:
    """Start the courier + player-effect workers inside the web process.

    Courier parcels are CREATED by the website API and queued to a file, so the
    delivery worker must run wherever that file is written — otherwise a
    site-only deployment (or a site process separate from the bots) would charge
    players for parcels that are never delivered. Both workers are safe to run in
    several processes at once: the courier queue uses a lock-file claim and the
    effect worker catches up by timestamps, so duplicate ticks do no harm.
    """
    global _web_background_workers_started
    if _web_background_workers_started:
        return
    if not _truthy_env("WEB_START_BACKGROUND_WORKERS", "true"):
        return
    try:
        from services.player_time_service import start_persistent_player_effect_worker
        from services.courier_service import start_persistent_courier_worker

        st = create_storage()
        effect_interval = int(os.getenv("PLAYER_EFFECT_TICK_INTERVAL_SECONDS", "60") or 60)
        courier_interval = int(os.getenv("COURIER_TICK_INTERVAL_SECONDS", "60") or 60)
        start_persistent_player_effect_worker(st, interval_seconds=effect_interval)
        start_persistent_courier_worker(st, interval_seconds=courier_interval)
        _web_background_workers_started = True
        logger.info("Started background workers in web process (effect=%ss, courier=%ss)", effect_interval, courier_interval)
    except Exception:
        logger.exception("Failed to start background workers in web process")


def create_app() -> FastAPI:
    # OpenAPI/Swagger в проде закрыты: они не дают данных без токена, но
    # раскрывают все admin/profile-ручки и схемы. Включаются осознанно для
    # разработки флагом ENABLE_API_DOCS=true.
    docs_enabled = _truthy_env("ENABLE_API_DOCS", "false")
    app = FastAPI(
        title="Ner-Talis",
        version="0.4.2",
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )

    @app.on_event("startup")
    def _on_startup() -> None:
        _start_web_background_workers()

    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=_csv_env(
            "ALLOWED_HOSTS",
            "ner-talis-game.ru,www.ner-talis-game.ru,localhost,127.0.0.1,testserver",
        ),
    )
    app.state.storage = None
    app.state.storage_error = None
    app.state.rate_limit_hits = defaultdict(deque)

    @app.middleware("http")
    async def security_and_rate_limit_middleware(request: Request, call_next):
        path = request.url.path
        if _truthy_env("FORCE_HTTPS", "false") and path != "/health":
            is_https = _request_is_https(request)
            host = request.headers.get("host", "")
            if not is_https and not host.startswith(("localhost", "127.0.0.1")):
                secure_url = request.url.replace(scheme="https")
                return JSONResponse({"detail": "HTTPS required", "redirect": str(secure_url)}, status_code=426)
        now = time.monotonic()
        window_seconds = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60") or "60")
        if request.method.upper() == "POST" and path.startswith("/api/profile"):
            max_requests = int(os.getenv("PROFILE_POST_RATE_LIMIT", "40") or "40")
        elif request.method.upper() == "POST" and path.startswith("/api/admin"):
            max_requests = int(os.getenv("ADMIN_POST_RATE_LIMIT", "60") or "60")
        elif path.startswith("/api/admin"):
            max_requests = int(os.getenv("ADMIN_GET_RATE_LIMIT", "180") or "180")
        elif path.startswith("/api/profile") or path.startswith("/api/player/profile"):
            max_requests = int(os.getenv("PROFILE_GET_RATE_LIMIT", "120") or "120")
        else:
            max_requests = 0

        if max_requests > 0:
            client_ip = _client_ip_for_rate_limit(request)
            bucket_key = (client_ip, request.method.upper(), path.rsplit("/", 1)[0] if "/" in path else path)
            buckets = app.state.rate_limit_hits
            hits = buckets[bucket_key]
            while hits and now - hits[0] > window_seconds:
                hits.popleft()
            if len(hits) >= max_requests:
                response = JSONResponse(
                    {"detail": "Слишком много запросов. Подождите немного и повторите действие."},
                    status_code=429,
                )
            else:
                hits.append(now)
                response = await call_next(request)
            # Periodically drop empty/stale buckets so per-IP keys do not pile up
            # forever (slow memory growth over weeks of uptime).
            app.state.rate_limit_sweep_counter = getattr(app.state, "rate_limit_sweep_counter", 0) + 1
            if app.state.rate_limit_sweep_counter >= int(os.getenv("RATE_LIMIT_SWEEP_EVERY", "500") or "500"):
                app.state.rate_limit_sweep_counter = 0
                for stale_key, stale_hits in list(buckets.items()):
                    while stale_hits and now - stale_hits[0] > window_seconds:
                        stale_hits.popleft()
                    if not stale_hits:
                        buckets.pop(stale_key, None)
        else:
            response = await call_next(request)

        for header, value in _security_headers_for(path).items():
            response.headers.setdefault(header, value)
        return response

    def storage():
        if getattr(app.state, "storage", None) is None:
            try:
                app.state.storage = create_storage()
                app.state.storage_error = None
            except Exception as exc:
                app.state.storage = None
                app.state.storage_error = str(exc)
                logger.exception("Storage is not ready")
                raise HTTPException(
                    status_code=503,
                    detail=(
                        "Хранилище игроков недоступно. Проверьте DATABASE_URL/STORAGE_BACKEND "
                        "в переменных окружения Timeweb."
                    ),
                ) from exc
        return app.state.storage

    app.include_router(create_profile_api_router(storage))
    app.include_router(create_admin_panel_router(storage))
    app.include_router(create_admin_panel_v2_router(storage))
    app.include_router(create_admin_world_router(storage))
    app.include_router(create_admin_community_router(storage))
    app.include_router(create_admin_achievement_router(storage))
    app.include_router(create_admin_messages_router(storage))
    app.include_router(create_admin_item_router(storage))
    app.include_router(create_admin_effect_router(storage))
    app.include_router(create_admin_fines_router(storage))
    app.include_router(create_admin_skills_router(storage))
    app.include_router(create_admin_promos_router(storage))
    app.include_router(create_admin_profile_layout_router(storage))
    app.include_router(create_admin_city_router(storage))
    app.include_router(create_admin_recipes_router(storage))
    app.include_router(create_admin_camp_router(storage))
    app.include_router(create_admin_trait_router(storage))
    app.include_router(create_admin_blessing_router(storage))
    app.include_router(create_admin_phase_router(storage))
    app.include_router(create_admin_levels_router(storage))
    app.include_router(create_admin_exp_router(storage))
    app.include_router(create_admin_registration_router(storage))
    app.include_router(create_admin_races_router(storage))
    app.include_router(create_admin_import_router(storage))
    app.include_router(create_admin_uploads_router(storage))
    app.include_router(create_admin_site_router(storage))
    app.include_router(create_admin_graph_router(storage))
    app.include_router(create_admin_sublocation_router(storage))
    app.include_router(create_admin_formula_router(storage))
    app.include_router(create_public_site_router())

    # Очередь сообщений читает/пишет ту же БД, что и боты (SQLite/Postgres),
    # чтобы админка видела реальный статус доставки. На json-хранилище остаётся
    # файловый backend.
    try:
        from services import bot_message_queue
        bot_message_queue.configure_queue(storage())
    except Exception:
        logging.getLogger(__name__).warning("Failed to configure message queue backend", exc_info=True)

    @app.get("/favicon.svg", include_in_schema=False)
    async def favicon_svg():
        # Vite копирует web/public/* в корень dist; на python-only прогоне берём
        # из web/public. Иначе — пусто (без 404-шума в логах).
        for candidate in (WEB_DIST_DIR / "favicon.svg", WEB_PUBLIC_DIR / "favicon.svg"):
            if candidate.is_file():
                return FileResponse(candidate, media_type="image/svg+xml")
        return Response(status_code=204)

    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon_ico():
        # Браузеры с тегом <link rel=icon> используют favicon.svg; legacy-запрос
        # /favicon.ico закрываем 204, чтобы не было 404 в логах.
        return Response(status_code=204)

    @app.get("/assets/admin_uploads/{asset_path:path}", include_in_schema=False)
    async def runtime_uploaded_asset(asset_path: str):
        file_path = _safe_uploaded_asset_path(asset_path)
        if file_path is None or not file_path.is_file():
            raise HTTPException(status_code=404, detail="Ассет не найден.")
        return FileResponse(file_path)

    @app.get("/favicon.svg", include_in_schema=False)
    async def favicon_svg():
        # Vite копирует web/public/* в корень dist; на dev-сборке без dist
        # отдаём из public. Если файла нет — 204 (без шума 404 в логах).
        for base in (WEB_DIST_DIR, WEB_PUBLIC_DIR):
            candidate = base / "favicon.svg"
            if candidate.is_file():
                return FileResponse(candidate, media_type="image/svg+xml")
        return Response(status_code=204)

    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon_ico():
        # Legacy-автозапрос браузеров: современные используют <link> на svg,
        # старым отвечаем 204 вместо 404.
        return Response(status_code=204)

    # Static files generated by Vite. During local Python-only checks web/dist may
    # be absent; in that case /profile falls back to server-rendered HTML.
    if (WEB_DIST_DIR / "assets").exists():
        app.mount("/assets", StaticFiles(directory=WEB_DIST_DIR / "assets"), name="assets")
    elif (WEB_PUBLIC_DIR / "assets").exists():
        app.mount("/assets", StaticFiles(directory=WEB_PUBLIC_DIR / "assets"), name="assets")

    def get_session_and_player(token: str, scope: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        st = storage()
        if hasattr(st, "get_player_by_web_token"):
            return st.get_player_by_web_token(token, scope=scope)

        data = st.load()
        sessions = data.get("web_sessions") or data.get("site_sessions") or {}
        session = sessions.get(token)
        if not session or (scope and session.get("scope") != scope):
            return None, None
        expires_at = _parse_datetime(session.get("expires_at"))
        if expires_at and expires_at <= datetime.now(timezone.utc):
            return None, None
        game_id = session.get("game_id")
        if not game_id:
            return None, None
        return st.get_player_by_game_id(game_id), session

    def render_profile_by_token(token: str) -> str:
        player, session = get_session_and_player(token, PROFILE_SCOPE)
        if player is None or session is None:
            raise HTTPException(status_code=401, detail="Недействительная или истёкшая ссылка.")
        return _render_profile_html(player, session)

    def render_profile_by_identifier(identifier: str) -> str:
        player, session = get_session_and_player(identifier, PROFILE_SCOPE)
        if player is not None and session is not None:
            return _render_profile_html(player, session)
        raise HTTPException(status_code=401, detail="Профиль доступен только по свежей ссылке из бота.")

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception):
        logger.exception("Unhandled web error on %s", request.url.path)
        return _error_html(
            "Внутренняя ошибка сайта",
            "Сайт открылся, но обработчик получил ошибку. Проверьте DATABASE_URL, STORAGE_BACKEND и logs/ner_talis.log.",
            status_code=500,
        )

    @app.get("/health", response_class=PlainTextResponse)
    @app.get("/healthz", response_class=PlainTextResponse)
    def health() -> str:
        return "OK"

    @app.get("/ready")
    def ready() -> JSONResponse:
        try:
            st = storage()
            if hasattr(st, "check_connection"):
                st.check_connection()
            return JSONResponse({"status": "ready"})
        except HTTPException as exc:
            return JSONResponse({"status": "storage_error", "detail": exc.detail}, status_code=503)
        except Exception as exc:
            logger.exception("Readiness check failed")
            return JSONResponse({"status": "error", "detail": str(exc)}, status_code=503)

    @app.get("/", response_class=HTMLResponse, response_model=None)
    def index():
        react = _react_index_or_none()
        if react:
            return react
        return HTMLResponse("<h1>Нер-Талис</h1><p>Откройте профиль по ссылке из бота.</p>")

    @app.get("/profile", response_class=HTMLResponse, response_model=None)
    def profile_page(token: str | None = Query(default=None)):
        react = _react_index_or_none()
        if react:
            return react
        if not token:
            raise HTTPException(status_code=400, detail="В ссылке нет token.")
        return HTMLResponse(render_profile_by_token(token))

    @app.get("/profile/{identifier}", response_class=HTMLResponse, response_model=None)
    def profile_page_path(identifier: str):
        react = _react_index_or_none()
        if react:
            return react
        if len(identifier) < 8:
            raise HTTPException(status_code=400, detail="Некорректная ссылка профиля.")
        return HTMLResponse(render_profile_by_identifier(identifier))

    @app.get("/admin_panel", response_class=HTMLResponse, response_model=None)
    def admin_panel_page(token: str | None = Query(default=None)):
        react = _react_index_or_none()
        if react:
            return react
        if not token:
            raise HTTPException(status_code=400, detail="В ссылке нет token админ-панели.")
        return HTMLResponse("<h1>Админ-панель Нер-Талис</h1><p>Соберите web/dist, чтобы открыть React-интерфейс админ-панели.</p>")

    @app.get("/admin_panel_v2", response_class=HTMLResponse, response_model=None)
    def admin_panel_v2_page(token: str | None = Query(default=None)):
        react = _react_index_or_none()
        if react:
            return react
        if not token:
            raise HTTPException(status_code=400, detail="В ссылке нет token админ-панели.")
        return HTMLResponse(
            "<h1>Админ-консоль Нер-Талис V2</h1>"
            "<p>Соберите web/dist, чтобы открыть React-интерфейс админ-панели V2.</p>"
        )

    @app.get("/admin_view_profile", response_class=HTMLResponse, response_model=None)
    def admin_view_profile_page(token: str | None = Query(default=None)):
        react = _react_index_or_none()
        if react:
            return react
        if not token:
            raise HTTPException(status_code=400, detail="В ссылке нет token просмотра профиля.")
        return HTMLResponse("<h1>Просмотр профиля игрока</h1><p>Соберите web/dist, чтобы открыть профиль в стиле сайта.</p>")

    # Публичный сайт проекта (рантайм конструктора сайта, ТЗ §2): React-страница
    # читает /api/public/site/*. Открыт всем; данные — только опубликованные.
    @app.get("/site", response_class=HTMLResponse, response_model=None)
    @app.get("/site/{slug}", response_class=HTMLResponse, response_model=None)
    def public_site_page(slug: str | None = None):
        react = _react_index_or_none()
        if react:
            return react
        return HTMLResponse("<h1>Нер-Талис</h1><p>Соберите web/dist, чтобы открыть публичный сайт.</p>")

    @app.get("/api/player/profile", response_model=None)
    def profile_api(token: str = Query(..., min_length=16)):
        player, session = get_session_and_player(token, PROFILE_SCOPE)
        if player is None or session is None:
            raise HTTPException(status_code=401, detail="Недействительная или истёкшая ссылка.")
        profile = frontend_profile(player)
        if session.get("token"):
            profile["sessionToken"] = session.get("token")
        return JSONResponse({"player": _public_player(player), "profile": profile, "session": session})

    @app.get("/api/player/profile/{identifier}", response_model=None)
    def profile_api_path(identifier: str):
        player, session = get_session_and_player(identifier, PROFILE_SCOPE)
        if player is None or session is None:
            raise HTTPException(status_code=401, detail="Профиль доступен только по свежей ссылке из бота.")
        profile = frontend_profile(player)
        if session.get("token"):
            profile["sessionToken"] = session.get("token")
        return JSONResponse({"player": _public_player(player), "profile": profile, "session": session})

    def render_pavilion_by_token(token: str) -> str:
        player, session = get_session_and_player(token, PAVILION_SCOPE)
        if player is None or session is None:
            raise HTTPException(status_code=401, detail="Недействительная или истёкшая ссылка павильона.")
        return "<h1>Торговый павильон</h1>" f"<p>Вход подтверждён для игрока: {_safe_text(player.get('name'))}</p>" "<p>Полный интерфейс павильона будет подключён отдельным модулем сайта.</p>"

    @app.get("/pavilion", response_class=HTMLResponse, response_model=None)
    def pavilion_page(token: str = Query(..., min_length=16)):
        return render_pavilion_by_token(token)

    @app.get("/pavilion/{token}", response_class=HTMLResponse, response_model=None)
    def pavilion_page_path_token(token: str):
        if len(token) < 16:
            raise HTTPException(status_code=400, detail="Некорректный token павильона.")
        return render_pavilion_by_token(token)

    return app


app = create_app()

