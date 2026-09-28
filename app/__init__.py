from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, abort, request, send_from_directory
from sqlalchemy import event
from sqlalchemy.engine import Engine
from werkzeug.middleware.proxy_fix import ProxyFix

from .cli import register_cli
from .config import BASE_DIR, build_config
from .errors import register_errors
from .extensions import db, migrate
from .routes import admin, auth, public
from .security import csrf_guard


@event.listens_for(Engine, "connect")
def _sqlite_foreign_keys(dbapi_connection, _record):
    # SQLite ignores foreign keys unless asked to enforce them.
    if dbapi_connection.__class__.__module__.startswith("sqlite3"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def create_app(test_config=None):
    if test_config is None:
        load_dotenv(BASE_DIR / ".env")
    app = Flask(__name__)
    app.config.update(build_config(test_config))

    if not app.config["SECRET_KEY"]:
        raise RuntimeError(
            "SECRET_KEY is not set. Copy .env.example to .env and set it to a long random value."
        )
    if app.config["TRUSTED_PROXIES"]:
        n = app.config["TRUSTED_PROXIES"]
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=n, x_proto=n, x_host=n)

    Path(app.config["UPLOAD_DIR"]).mkdir(parents=True, exist_ok=True)
    db.init_app(app)
    migrate.init_app(app, db, render_as_batch=True, compare_type=True)
    register_errors(app)
    register_cli(app)

    app.before_request(csrf_guard)
    app.register_blueprint(public.bp)
    app.register_blueprint(auth.bp)
    app.register_blueprint(admin.bp)

    @app.get("/uploads/<path:filename>")
    def uploads(filename):
        # Only the WebP files this app writes. Names are random, so they can be cached for a year.
        if not filename.endswith(".webp"):
            abort(404)
        response = send_from_directory(app.config["UPLOAD_DIR"], filename, max_age=31536000)
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        if request.path.startswith("/api/admin"):
            response.headers["Cache-Control"] = "no-store"
        return response

    return app
