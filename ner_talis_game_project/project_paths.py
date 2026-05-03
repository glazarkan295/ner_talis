from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parent


def project_path(*parts: str) -> Path:
    return PROJECT_ROOT.joinpath(*parts)


def resolve_project_path(path: str | Path) -> Path:
    value = Path(path)
    if value.is_absolute():
        return value
    return PROJECT_ROOT / value


def load_project_env() -> None:
    """Load .env from the repo root, with package-local .env as a fallback."""
    try:
        from dotenv import load_dotenv
    except Exception:
        return

    for env_path in (PROJECT_ROOT / ".env", PACKAGE_ROOT / ".env"):
        if env_path.exists():
            load_dotenv(env_path, override=False)
