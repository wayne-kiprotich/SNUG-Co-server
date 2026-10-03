"""Development stays away from live data; production keeps its database settings."""

import importlib.util

import pytest
import sqlalchemy as sa
from werkzeug.security import generate_password_hash

from app import create_app
from app.config import BASE_DIR, build_config
from app.extensions import db
from app.models import AdminUser, Product

from conftest import ADMIN_EMAIL, HEADERS

SUPABASE = "postgresql+psycopg://postgres.ref:pw@aws-1-eu-west-1.pooler.supabase.com:5432/postgres"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ("RENDER", "ALLOW_REMOTE_DATABASE", "DATABASE_URL", "FLASK_DEBUG"):
        monkeypatch.delenv(name, raising=False)


def make_app(tmp_path, uri, **extra):
    return create_app(
        {"TESTING": True, "SECRET_KEY": "t", "SQLALCHEMY_DATABASE_URI": uri, "UPLOAD_DIR": str(tmp_path / "up"), **extra}
    )


# ---- Which database ---------------------------------------------------------


def test_empty_database_url_means_local_sqlite():
    config = build_config()
    assert config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite:///")
    assert config["SQLALCHEMY_ENGINE_OPTIONS"] == {}


def test_remote_database_is_refused_outside_render(tmp_path):
    with pytest.raises(RuntimeError, match="ALLOW_REMOTE_DATABASE=1"):
        make_app(tmp_path, SUPABASE)


def test_remote_database_is_allowed_on_render_or_with_an_explicit_opt_in(tmp_path, monkeypatch):
    monkeypatch.setenv("RENDER", "true")
    make_app(tmp_path, SUPABASE)
    monkeypatch.delenv("RENDER")
    monkeypatch.setenv("ALLOW_REMOTE_DATABASE", "1")
    make_app(tmp_path, SUPABASE)


def test_local_postgres_needs_no_opt_in(tmp_path):
    app = make_app(tmp_path, "postgresql+psycopg://snug:pw@localhost:5432/snug")
    assert "sslmode" not in app.config["SQLALCHEMY_ENGINE_OPTIONS"]["connect_args"]


def test_supabase_connections_require_tls_and_survive_idle_drops(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgres://postgres.ref:pw@aws-1-eu-west-1.pooler.supabase.com:5432/postgres")
    config = build_config()
    assert config["SQLALCHEMY_DATABASE_URI"].startswith("postgresql+psycopg://")
    options = config["SQLALCHEMY_ENGINE_OPTIONS"]
    assert options["pool_pre_ping"] is True
    assert options["connect_args"] == {"connect_timeout": 10, "sslmode": "require"}

    monkeypatch.setenv("DATABASE_URL", SUPABASE + "?sslmode=verify-full")
    assert "sslmode" not in build_config()["SQLALCHEMY_ENGINE_OPTIONS"]["connect_args"]


# ---- Development and live Cloudinary folders --------------------------------


def test_development_uses_its_own_cloudinary_folder(monkeypatch):
    assert build_config()["CLOUDINARY_FOLDER"] == "snug-co"
    monkeypatch.setenv("FLASK_DEBUG", "1")
    assert build_config()["CLOUDINARY_FOLDER"] == "snug-co-dev"


# ---- Commands ---------------------------------------------------------------


def empty_app(tmp_path, **extra):
    app = make_app(tmp_path, f"sqlite:///{tmp_path / 'empty.db'}", **extra)
    with app.app_context():
        db.create_all()
    return app


def test_seed_asks_before_loading_samples_outside_development(tmp_path):
    app = empty_app(tmp_path)
    refused = app.test_cli_runner().invoke(args=["seed"], input="n\n")
    assert refused.exit_code != 0
    with app.app_context():
        assert Product.query.count() == 0

    loaded = app.test_cli_runner().invoke(args=["seed"], input="y\n")
    assert loaded.exit_code == 0, loaded.output
    with app.app_context():
        assert Product.query.count() > 0


def test_seed_does_not_ask_in_development(tmp_path, monkeypatch):
    app = empty_app(tmp_path)
    monkeypatch.setenv("FLASK_DEBUG", "1")  # the flask command sets app.debug from this
    result = app.test_cli_runner().invoke(args=["seed"])
    assert result.exit_code == 0 and "Loaded" in result.output


def test_list_and_delete_admins(app, admin):
    runner = app.test_cli_runner()
    only = runner.invoke(args=["delete-admin", "--email", ADMIN_EMAIL], input="y\n")
    assert only.exit_code != 0 and "only admin" in only.output

    with app.app_context():
        db.session.add(AdminUser(email="client@example.com", password_hash=generate_password_hash("x" * 12)))
        db.session.commit()
    listed = runner.invoke(args=["list-admins"])
    assert ADMIN_EMAIL in listed.output and "client@example.com" in listed.output

    deleted = runner.invoke(args=["delete-admin", "--email", ADMIN_EMAIL], input="y\n")
    assert deleted.exit_code == 0, deleted.output
    with app.app_context():
        assert [u.email for u in AdminUser.query.all()] == ["client@example.com"]
    # The deleted admin's browser is signed out at once.
    assert admin.get("/api/admin/me").get_json() == {"email": None}
    assert admin.get("/api/admin/products", headers=HEADERS).status_code == 401


# ---- Migrations -------------------------------------------------------------


def test_migrations_run_and_row_level_security_covers_every_table(tmp_path):
    from flask_migrate import upgrade

    app = make_app(tmp_path, f"sqlite:///{tmp_path / 'migrated.db'}")
    with app.app_context():
        upgrade(directory=str(BASE_DIR / "migrations"))
        tables = set(sa.inspect(db.engine).get_table_names())

    path = BASE_DIR / "migrations" / "versions" / "e5f6a7b8c9d0_row_level_security.py"
    spec = importlib.util.spec_from_file_location("rls_migration", path)
    rls = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rls)
    assert "alembic_version" in tables
    assert tables <= set(rls.TABLES), "a new table needs a migration that enables row level security"
    assert set(db.metadata.tables) <= set(rls.TABLES)
