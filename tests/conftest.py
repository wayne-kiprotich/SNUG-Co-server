import io
import json
from pathlib import Path

import pytest
from PIL import Image
from werkzeug.security import generate_password_hash

from app import create_app
from app.cli import load_catalog
from app.extensions import db
from app.models import AdminUser
from app.security import login_throttle

SEED = Path(__file__).resolve().parent.parent / "seed" / "catalog.json"
ADMIN_EMAIL = "owner@example.com"
ADMIN_PASSWORD = "correct horse battery staple"
HEADERS = {"X-Requested-With": "snug-admin"}


@pytest.fixture()
def app(tmp_path):
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'test.db'}",
            "UPLOAD_DIR": str(tmp_path / "uploads"),
            "SESSION_COOKIE_SECURE": False,
        }
    )
    with app.app_context():
        db.create_all()
        db.session.add(AdminUser(email=ADMIN_EMAIL, password_hash=generate_password_hash(ADMIN_PASSWORD)))
        db.session.commit()
        load_catalog(json.loads(SEED.read_text()))
    login_throttle._attempts.clear()
    yield app


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def admin(client):
    res = client.post("/api/admin/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, headers=HEADERS)
    assert res.status_code == 200
    return client


def photo(width=1200, height=1600, color=(120, 80, 60), fmt="JPEG"):
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buf, fmt)
    buf.seek(0)
    return buf


NEW_PRODUCT = {
    "name": "Test Lounge Set",
    "category": "lounge-sets",
    "description": "A soft test set.",
    "priceKES": 4500,
}
