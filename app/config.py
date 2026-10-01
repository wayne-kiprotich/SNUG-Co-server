import os
from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _database_uri(url):
    if not url:
        instance = BASE_DIR / "instance"
        instance.mkdir(exist_ok=True)
        return f"sqlite:///{instance / 'snug.db'}"
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


def build_config(overrides=None):
    env = os.environ.get
    debug = env("FLASK_DEBUG", "0") == "1"
    upload_dir = env("UPLOAD_DIR") or str(BASE_DIR / "uploads")

    config = {
        "SITE_URL": env("SITE_URL") or env("VITE_SITE_URL") or "",
        "SECRET_KEY": env("SECRET_KEY"),
        "DEBUG": debug,
        "SQLALCHEMY_DATABASE_URI": _database_uri(env("DATABASE_URL")),
        "UPLOAD_DIR": upload_dir,
        "CLIENT_DIST": env("CLIENT_DIST") or str(BASE_DIR.parent / "client" / "dist"),
        "UPLOAD_URL_BASE": (env("UPLOAD_URL_BASE") or "/uploads").rstrip("/"),
        "MAX_CONTENT_LENGTH": 40 * 1024 * 1024,  # whole request; each photo is checked to 16 MB below
        "MAX_UPLOAD_BYTES": 16 * 1024 * 1024,
        "MAX_IMAGES_PER_PRODUCT": 12,
        "SESSION_COOKIE_NAME": "snug_admin",
        "SESSION_COOKIE_HTTPONLY": True,
        "SESSION_COOKIE_SAMESITE": "Lax",
        "SESSION_COOKIE_SECURE": not debug,
        "PERMANENT_SESSION_LIFETIME": timedelta(hours=8),
        "ALLOWED_ORIGINS": [o.strip() for o in (env("ALLOWED_ORIGINS") or "").split(",") if o.strip()],
        "TRUSTED_PROXIES": int(env("TRUSTED_PROXIES") or 0),
        "LOGIN_MAX_ATTEMPTS": 5,
        "LOGIN_WINDOW_SECONDS": 15 * 60,
    }
    if overrides:
        config.update(overrides)
    return config
