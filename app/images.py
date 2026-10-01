"""Photo processing and storage."""

import io
import os
import secrets
import tempfile
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from .errors import ApiError

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
WIDTHS = (480, 800, 1080)
RATIO = 4 / 5
MIN_WIDTH = 600
Image.MAX_IMAGE_PIXELS = 80_000_000


def new_image_id():
    return "u" + secrets.token_hex(6)


def process_image(data, focus_y=0.5):
    """Return (widths, {width: webp_bytes}) for an uploaded photo."""
    try:
        img = Image.open(io.BytesIO(data))
        fmt = img.format
        img.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, ValueError):
        raise ApiError(422, "That file isn’t a photo we can read. Use a JPEG, PNG or WebP image.")
    if fmt not in ALLOWED_FORMATS:
        raise ApiError(422, "Use a JPEG, PNG or WebP photo.")

    img = ImageOps.exif_transpose(img)
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        background = Image.new("RGBA", img.size, (255, 255, 255, 255))
        img = Image.alpha_composite(background, img)
    img = img.convert("RGB")

    if img.width < MIN_WIDTH:
        raise ApiError(422, f"That photo is too small. Use one at least {MIN_WIDTH}px wide.")

    w, h = img.size
    if w / h > RATIO:
        new_w = round(h * RATIO)
        left = (w - new_w) // 2
        img = img.crop((left, 0, left + new_w, h))
    else:
        new_h = round(w / RATIO)
        top = round((h - new_h) * min(1.0, max(0.0, focus_y)))
        img = img.crop((0, top, w, top + new_h))

    widths = [x for x in WIDTHS if x <= img.width]
    if img.width < WIDTHS[-1] and img.width not in widths:
        widths.append(img.width)
    files = {}
    for width in widths:
        out = img if width == img.width else img.resize((width, round(width / RATIO)), Image.LANCZOS)
        buf = io.BytesIO()
        out.save(buf, "WEBP", quality=80, method=4)
        files[width] = buf.getvalue()
    return widths, files


class LocalStorage:
    def __init__(self, directory):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def filename(image_id, width):
        return f"{image_id}-{width}.webp"

    def save(self, image_id, files):
        """Write every width."""
        written = []
        try:
            for width, blob in files.items():
                final = self.dir / self.filename(image_id, width)
                fd, tmp = tempfile.mkstemp(dir=self.dir, suffix=".part")
                with os.fdopen(fd, "wb") as fh:
                    fh.write(blob)
                os.replace(tmp, final)
                written.append(final)
        except OSError:
            for path in written:
                path.unlink(missing_ok=True)
            raise ApiError(500, "The photo couldn’t be saved. Check the server’s upload folder.")

    def delete(self, image_id, widths):
        for width in widths or []:
            (self.dir / self.filename(image_id, width)).unlink(missing_ok=True)


def _ssl_context():
    """Verify HTTPS against certifi's CA bundle, so it works the same on macOS and on Render."""
    import ssl

    import certifi

    return ssl.create_default_context(cafile=certifi.where())


class SupabaseStorage:
    """Stores photos in a Supabase Storage bucket, over its plain REST API."""

    def __init__(self, url, service_key, bucket):
        self.base = f"{url.rstrip('/')}/storage/v1"
        self.headers = {"Authorization": f"Bearer {service_key}", "apikey": service_key}
        self.bucket = bucket

    @staticmethod
    def filename(image_id, width):
        return f"{image_id}-{width}.webp"

    def save(self, image_id, files):
        import urllib.error
        import urllib.request

        written = []
        try:
            for width, blob in files.items():
                req = urllib.request.Request(
                    f"{self.base}/object/{self.bucket}/{self.filename(image_id, width)}",
                    data=blob,
                    method="POST",
                    headers={**self.headers, "Content-Type": "image/webp", "x-upsert": "true"},
                )
                urllib.request.urlopen(req, timeout=20, context=_ssl_context())
                written.append(width)
        except (urllib.error.URLError, OSError) as err:
            from flask import current_app

            detail = err.read().decode(errors="replace")[:200] if isinstance(err, urllib.error.HTTPError) else err
            current_app.logger.error("Supabase Storage upload failed: %s", detail)
            self.delete(image_id, written)
            raise ApiError(502, "The photo couldn’t be uploaded. Try again.")

    def delete(self, image_id, widths):
        import urllib.error
        import urllib.request

        for width in widths or []:
            req = urllib.request.Request(
                f"{self.base}/object/{self.bucket}/{self.filename(image_id, width)}",
                method="DELETE",
                headers=self.headers,
            )
            try:
                urllib.request.urlopen(req, timeout=20, context=_ssl_context())
            except (urllib.error.URLError, OSError):
                pass


def get_storage(app):
    url, key, bucket = app.config["SUPABASE_URL"], app.config["SUPABASE_SERVICE_KEY"], app.config["SUPABASE_BUCKET"]
    if url and key:
        return SupabaseStorage(url, key, bucket)
    return LocalStorage(app.config["UPLOAD_DIR"])
