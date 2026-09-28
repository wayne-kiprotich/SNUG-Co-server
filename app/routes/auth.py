from datetime import datetime, timezone

from flask import Blueprint, current_app, g, jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from ..errors import ApiError, ValidationError
from ..extensions import db
from ..models import AdminUser
from ..security import current_admin, login_required, login_throttle

bp = Blueprint("auth", __name__, url_prefix="/api/admin")

# Checked when the email is unknown, so a wrong email and a wrong password take the same time.
_DUMMY_HASH = generate_password_hash("not-a-real-password")
MIN_PASSWORD = 12


def check_new_password(password):
    if not isinstance(password, str) or len(password) < MIN_PASSWORD:
        raise ValidationError({"newPassword": f"Use at least {MIN_PASSWORD} characters."})
    if len(password) > 200:
        raise ValidationError({"newPassword": "That password is too long."})


@bp.post("/login")
def login():
    body = request.get_json(silent=True) or {}
    email = str(body.get("email", "")).strip().lower()
    password = body.get("password", "")
    cfg = current_app.config
    limit, window = cfg["LOGIN_MAX_ATTEMPTS"], cfg["LOGIN_WINDOW_SECONDS"]
    key = (request.remote_addr, email)

    if login_throttle.blocked(key, limit, window) or login_throttle.blocked((request.remote_addr, "*"), limit * 4, window):
        raise ApiError(429, "Too many attempts. Wait 15 minutes and try again.")

    user = AdminUser.query.filter_by(email=email).first() if email else None
    valid = check_password_hash(user.password_hash if user else _DUMMY_HASH, password if isinstance(password, str) else "")
    if not (user and valid):
        login_throttle.fail(key, window)
        login_throttle.fail((request.remote_addr, "*"), window)
        raise ApiError(401, "Email or password is incorrect.")

    login_throttle.clear(key)
    session.clear()
    session["admin_id"] = user.id
    session.permanent = True
    user.last_login_at = datetime.now(timezone.utc)
    db.session.commit()
    return jsonify({"email": user.email})


@bp.post("/logout")
def logout():
    session.clear()
    return jsonify({"ok": True})


@bp.get("/me")
def me():
    admin = current_admin()
    if admin is None:
        raise ApiError(401, "Sign in to continue.")
    return jsonify({"email": admin.email})


@bp.post("/password")
@login_required
def change_password():
    body = request.get_json(silent=True) or {}
    if not check_password_hash(g.admin.password_hash, body.get("currentPassword") or ""):
        raise ValidationError({"currentPassword": "That isn’t your current password."})
    check_new_password(body.get("newPassword"))
    g.admin.password_hash = generate_password_hash(body["newPassword"])
    db.session.commit()
    # Sessions are signed cookies, so a stolen cookie stays valid until it expires (8 hours)
    # or SECRET_KEY changes. Rotate SECRET_KEY to sign everyone out.
    session.clear()
    session["admin_id"] = g.admin.id
    session.permanent = True
    return jsonify({"ok": True})
