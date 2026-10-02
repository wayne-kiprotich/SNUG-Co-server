import secrets
import threading
import time
from functools import wraps
from urllib.parse import urlparse

from flask import current_app, g, request, session
from flask.sessions import SecureCookieSessionInterface

from .errors import ApiError
from .extensions import db
from .models import AdminUser

class StorefrontSessionInterface(SecureCookieSessionInterface):
    """Never send the admin session cookie on public storefront responses.

    Flask re-sends a permanent session's cookie on every request. The storefront routes are
    cached by the CDN, so a signed-in admin's cookie there could be stored and handed to every
    visitor. Admin and sign-in routes keep the normal behaviour.
    """

    def save_session(self, app, session, response):
        if request.blueprint == "public":
            return
        super().save_session(app, session, response)


SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
CSRF_HEADER = "X-Requested-With"
CSRF_VALUE = "snug-admin"
# Other sites can't send a custom header without CORS approval, so it proves the request
# came from our own pages.
CSRF_VALUES = {"/api/admin": CSRF_VALUE, "/api/shopper": "snug-shop"}


def csrf_guard():
    """Block admin and shopper writes not sent by our own pages."""
    if request.method in SAFE_METHODS:
        return
    expected = next((v for prefix, v in CSRF_VALUES.items() if request.path.startswith(prefix)), None)
    if expected is None:
        return
    if request.headers.get(CSRF_HEADER) != expected:
        raise ApiError(403, "This request was blocked. Reload the admin page and try again.")
    origin = request.headers.get("Origin")
    if origin:
        allowed = {request.host_url.rstrip("/"), *current_app.config["ALLOWED_ORIGINS"]}
        parsed = urlparse(origin)
        if f"{parsed.scheme}://{parsed.netloc}" not in allowed:
            raise ApiError(403, "This request came from an address that isn’t allowed.")


def start_session(admin):
    session.clear()
    session["admin_id"] = admin.id
    session["v"] = admin.session_version
    session["t"] = int(time.time())
    session.permanent = True


def current_admin():
    admin_id = session.get("admin_id")
    if not admin_id:
        return None
    age = time.time() - session.get("t", 0)
    if age > current_app.config["SESSION_MAX_AGE"].total_seconds():
        session.clear()
        return None
    admin = db.session.get(AdminUser, admin_id)
    if admin is None or session.get("v") != admin.session_version:
        session.clear()
        return None
    return admin


DEVICE_COOKIE = "snug_device"


def _device_serializer():
    from itsdangerous import URLSafeSerializer

    return URLSafeSerializer(current_app.config["SECRET_KEY"], salt="snug-device")


def device_id():
    """Id from the signed device cookie, or None."""
    raw = request.cookies.get(DEVICE_COOKIE)
    if not raw:
        return None
    try:
        return _device_serializer().loads(raw)
    except Exception:
        return None


def set_device_cookie(response):
    value = _device_serializer().dumps(secrets.token_hex(16))
    response.set_cookie(
        DEVICE_COOKIE,
        value,
        max_age=365 * 24 * 3600,
        httponly=True,
        secure=current_app.config["SESSION_COOKIE_SECURE"],
        samesite=current_app.config["SESSION_COOKIE_SAMESITE"],
    )
    return response


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        admin = current_admin()
        if admin is None:
            raise ApiError(401, "Sign in to continue.")
        g.admin = admin
        return fn(*args, **kwargs)

    return wrapper


class LoginThrottle:
    """In-memory sign-in rate limit."""

    def __init__(self):
        self._attempts = {}
        self._lock = threading.Lock()

    def _recent(self, key, window):
        now = time.monotonic()
        recent = [t for t in self._attempts.get(key, []) if now - t < window]
        self._attempts[key] = recent
        return recent

    def blocked(self, key, limit, window):
        with self._lock:
            return len(self._recent(key, window)) >= limit

    def fail(self, key, window):
        with self._lock:
            self._recent(key, window).append(time.monotonic())

    def clear(self, key):
        with self._lock:
            self._attempts.pop(key, None)


login_throttle = LoginThrottle()
