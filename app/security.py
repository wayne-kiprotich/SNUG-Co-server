import threading
import time
from functools import wraps
from urllib.parse import urlparse

from flask import current_app, g, request, session

from .errors import ApiError
from .extensions import db
from .models import AdminUser

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
CSRF_HEADER = "X-Requested-With"
CSRF_VALUE = "snug-admin"


def csrf_guard():
    """Reject state-changing admin requests that didn't come from our own admin page."""
    if not request.path.startswith("/api/admin") or request.method in SAFE_METHODS:
        return
    if request.headers.get(CSRF_HEADER) != CSRF_VALUE:
        raise ApiError(403, "This request was blocked. Reload the admin page and try again.")
    origin = request.headers.get("Origin")
    if origin:
        allowed = {request.host_url.rstrip("/"), *current_app.config["ALLOWED_ORIGINS"]}
        parsed = urlparse(origin)
        if f"{parsed.scheme}://{parsed.netloc}" not in allowed:
            raise ApiError(403, "This request came from an address that isn’t allowed.")


def current_admin():
    admin_id = session.get("admin_id")
    if not admin_id:
        return None
    return db.session.get(AdminUser, admin_id)


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
    """Small in-memory limiter for sign-in attempts."""

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
