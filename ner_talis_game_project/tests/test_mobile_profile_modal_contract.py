"""Static regression guards for mobile-safe profile dialogs (TZ 23)."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / "web" / "src" / "components" / "player-profile" / "PlayerProfile.jsx"
STYLES = ROOT / "web" / "src" / "components" / "player-profile" / "PlayerProfile.css"


def test_profile_dialogs_use_one_portal_and_no_anchor_positioning():
    source = COMPONENT.read_text(encoding="utf-8")
    assert 'import { createPortal } from "react-dom"' in source
    assert "function ProfileModal(" in source
    assert "createPortal(" in source
    assert "document.body" in source
    assert 'role="dialog"' in source
    assert 'aria-modal="true"' in source
    assert "getFloatingPosition" not in source
    assert "floatingModalStyle" not in source
    assert source.count("<ProfileModal") >= 10


def test_profile_dialog_css_is_viewport_safe():
    css = STYLES.read_text(encoding="utf-8")
    assert "place-items: center" in css
    assert "min-height: 100dvh" in css
    assert "env(safe-area-inset-top)" in css
    assert "env(safe-area-inset-bottom)" in css
    assert "overflow-y: auto" in css
    assert "overscroll-behavior: none" in css
    assert "overflow-x: clip" in css
    assert "*::before, *::after" in css

