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


def get_storage(app):
    return LocalStorage(app.config["UPLOAD_DIR"])
