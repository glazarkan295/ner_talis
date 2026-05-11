"""FastAPI website for Ner-Talis."""

from __future__ import annotations

import html
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

from services.web_profile import PAVILION_SCOPE, PROFILE_SCOPE
from storage.storage_factory import create_storage


def _safe_text(value: Any, default: str = "—") -> str:
    if value is None or value == "":
        return default
    return html.escape(str(value))


def _stat_label(key: str) -> str:
    labels = {
        "strength": "Сила",
        "dexterity": "Ловкость",
        "endurance": "Выносливость",
        "intelligence": "Интеллект",
        "wisdom": "Мудрость",
        "perception": "Восприятие",
    }
    return labels.get(key, key)


def _public_player(player: dict[str, Any]) -> dict[str, Any]:
    return {
        "game_id": player.get("game_id"),
        "public_id": player.get("public_id"),
        "name": player.get("name"),
        "race_name": player.get("race_name"),
        "level": player.get("level", 1),
        "experience": player.get("experience", 0),
        "current_city": player.get("current_city", "seldar"),
        "current_zone": player.get("current_zone"),
        "money": player.get("money", 0),
        "debt": player.get("debt", 0),
        "energy": player.get("energy", 100),
        "max_energy": player.get("max_energy", 100),
        "stats": player.get("stats", {}),
        "linked_accounts": sorted((player.get("linked_accounts") or {}).keys()),
    }


def _render_profile_html(player: dict[str, Any], session: dict[str, Any]) -> str:
    public_player = _public_player(player)
    stats = public_player.get("stats") or {}
    stat_rows = "".join(
        f"<tr><td>{_safe_text(_stat_label(key))}</td><td>{_safe_text(value)}</td></tr>"
        for key, value in stats.items()
    ) or "<tr><td colspan='2'>Характеристики пока не заполнены.</td></tr>"
    linked_accounts = ", ".join(public_player.get("linked_accounts") or []) or "—"

    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Профиль Нер-Талис</title>
  <style>
    :root {{ color-scheme: dark; }}
    body {{
      margin: 0;
      min-height: 100vh;
      font-family: Georgia, 'Times New Roman', serif;
      color: #f1dfbd;
      background: radial-gradient(circle at top, #2a2019 0, #0d0b0a 52%, #050403 100%);
    }}
    .wrap {{ max-width: 920px; margin: 0 auto; padding: 36px 18px; }}
    .card {{
      border: 1px solid rgba(214, 172, 91, .45);
      border-radius: 22px;
      padding: 28px;
      background: linear-gradient(145deg, rgba(43, 31, 22, .94), rgba(16, 13, 11, .96));
      box-shadow: 0 24px 70px rgba(0,0,0,.55), inset 0 1px rgba(255,255,255,.08);
    }}
    h1 {{ margin: 0 0 8px; font-size: 34px; color: #ffd98f; }}
    h2 {{ margin-top: 28px; color: #ffd98f; }}
    .muted {{ color: #b9a27c; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 14px; margin-top: 22px; }}
    .box {{ border: 1px solid rgba(255,217,143,.18); border-radius: 16px; padding: 16px; background: rgba(255,255,255,.035); }}
    .label {{ color: #a99471; font-size: 13px; }}
    .value {{ font-size: 20px; margin-top: 4px; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 14px; }}
    td {{ border-bottom: 1px solid rgba(255,217,143,.12); padding: 10px 0; }}
    td:last-child {{ text-align: right; color: #ffd98f; }}
    .footer {{ margin-top: 18px; font-size: 13px; color: #8f7c5d; }}
  </style>
</head>
<body>
  <main class="wrap">
    <section class="card">
      <div class="muted">Мир Нер-Талис</div>
      <h1>{_safe_text(public_player.get('name'))}</h1>
      <div class="muted">Единый игровой ID: {_safe_text(public_player.get('game_id'))}</div>
      <div class="grid">
        <div class="box"><div class="label">Раса</div><div class="value">{_safe_text(public_player.get('race_name'))}</div></div>
        <div class="box"><div class="label">Уровень</div><div class="value">{_safe_text(public_player.get('level'))}</div></div>
        <div class="box"><div class="label">Опыт</div><div class="value">{_safe_text(public_player.get('experience'))}</div></div>
        <div class="box"><div class="label">Энергия</div><div class="value">{_safe_text(public_player.get('energy'))}/{_safe_text(public_player.get('max_energy'))}</div></div>
        <div class="box"><div class="label">Город</div><div class="value">{_safe_text(public_player.get('current_city'))}</div></div>
        <div class="box"><div class="label">Зона</div><div class="value">{_safe_text(public_player.get('current_zone'))}</div></div>
      </div>
      <h2>Характеристики</h2>
      <table>{stat_rows}</table>
      <div class="footer">Платформы: {_safe_text(linked_accounts)} · Сессия действует до {_safe_text(session.get('expires_at'))}</div>
    </section>
  </main>
</body>
</html>"""


def create_app() -> FastAPI:
    app = FastAPI(title="Ner-Talis", version="0.2.0")

    @app.on_event("startup")
    def startup() -> None:
        app.state.storage = create_storage()

    def storage():
        if not hasattr(app.state, "storage"):
            app.state.storage = create_storage()
        return app.state.storage

    def require_player_by_token(token: str, scope: str) -> tuple[dict[str, Any], dict[str, Any]]:
        player, session = storage().get_player_by_web_token(token, scope=scope)
        if player is None or session is None:
            raise HTTPException(status_code=401, detail="Недействительная или истёкшая ссылка.")
        return player, session

    @app.get("/health", response_class=PlainTextResponse)
    @app.get("/healthz", response_class=PlainTextResponse)
    def health() -> str:
        return "OK"

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return "<h1>Нер-Талис</h1><p>Откройте профиль по ссылке из бота.</p>"

    def render_profile_by_token(token: str) -> str:
        player, session = require_player_by_token(token, PROFILE_SCOPE)
        return _render_profile_html(player, session)

    @app.get("/profile", response_class=HTMLResponse)
    def profile_page(token: str = Query(..., min_length=16)) -> str:
        return render_profile_by_token(token)

    @app.get("/profile/{token}", response_class=HTMLResponse)
    def profile_page_path_token(token: str) -> str:
        if len(token) < 16:
            raise HTTPException(status_code=400, detail="Некорректный token профиля.")
        return render_profile_by_token(token)

    @app.get("/api/player/profile")
    def profile_api(token: str = Query(..., min_length=16)) -> JSONResponse:
        player, session = require_player_by_token(token, PROFILE_SCOPE)
        return JSONResponse({"player": _public_player(player), "session": session})

    @app.get("/api/player/profile/{token}")
    def profile_api_path_token(token: str) -> JSONResponse:
        if len(token) < 16:
            raise HTTPException(status_code=400, detail="Некорректный token профиля.")
        player, session = require_player_by_token(token, PROFILE_SCOPE)
        return JSONResponse({"player": _public_player(player), "session": session})

    def render_pavilion_by_token(token: str) -> str:
        player, session = require_player_by_token(token, PAVILION_SCOPE)
        return (
            "<h1>Торговый павильон</h1>"
            f"<p>Вход подтверждён для игрока: {_safe_text(player.get('name'))}</p>"
            "<p>Полный интерфейс павильона будет подключён отдельным модулем сайта.</p>"
        )

    @app.get("/pavilion", response_class=HTMLResponse)
    def pavilion_page(token: str = Query(..., min_length=16)) -> str:
        return render_pavilion_by_token(token)

    @app.get("/pavilion/{token}", response_class=HTMLResponse)
    def pavilion_page_path_token(token: str) -> str:
        if len(token) < 16:
            raise HTTPException(status_code=400, detail="Некорректный token павильона.")
        return render_pavilion_by_token(token)

    return app


app = create_app()
