from pathlib import Path


def test_timeweb_postgresql_env_template_exists_and_uses_postgres():
    root = Path(__file__).resolve().parents[2]
    env_file = root / ".env.timeweb.postgresql.example"
    assert env_file.exists()
    text = env_file.read_text(encoding="utf-8")
    assert "STORAGE_BACKEND=postgres" in text
    assert "DATABASE_URL=postgresql://" in text
    assert "PUBLIC_UPLOADS_ASSETS_DIR=data/public_uploads/assets" in text


def test_postgres_storage_contains_idempotent_schema_upgrade():
    root = Path(__file__).resolve().parents[2]
    source = (root / "ner_talis_game_project" / "storage" / "postgres_storage.py").read_text(encoding="utf-8")
    assert "def ensure_schema_compatibility" in source
    assert "ALTER TABLE players ADD COLUMN IF NOT EXISTS inventory JSONB" in source
    assert "ALTER TABLE web_sessions ADD COLUMN IF NOT EXISTS used BOOLEAN" in source
    assert "ALTER TABLE admin_panel_sessions ADD COLUMN IF NOT EXISTS expires_at" in source
    assert "ALTER TABLE promo_codes ADD COLUMN IF NOT EXISTS updated_at" in source
