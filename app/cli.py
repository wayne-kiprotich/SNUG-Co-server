import json
from pathlib import Path

import click
from werkzeug.security import generate_password_hash

from .errors import ApiError
from .extensions import db
from .models import AdminUser, Category, Collection, Product, ProductImage
from .routes.auth import MIN_PASSWORD

SEED_FILE = Path(__file__).resolve().parent.parent / "seed" / "catalog.json"


def load_catalog(data):
    """Insert the seed catalog."""
    categories = {}
    for i, c in enumerate(data["categories"]):
        row = Category(
            name=c["name"], slug=c["slug"], description=c.get("description"), image_id=c.get("image"), sort_order=i
        )
        db.session.add(row)
        categories[c["slug"]] = row
    collections = {}
    for i, c in enumerate(data["collections"]):
        row = Collection(
            name=c["name"], slug=c["slug"], description=c.get("description"), image_id=c.get("image"), sort_order=i
        )
        db.session.add(row)
        collections[c["slug"]] = row

    for p in data["products"]:
        product = Product(
            slug=p["slug"],
            name=p["name"],
            name_confirmed=p.get("nameConfirmed", True),
            category=categories[p["category"]],
            collections=[collections[s] for s in p.get("collections", [])],
            description=p["description"],
            price_kes=p.get("priceKES"),
            compare_at_price_kes=p.get("compareAtPriceKES"),
            colors=p.get("colors"),
            sizes=p.get("sizes"),
            sizes_note=p.get("sizesNote"),
            options=p.get("options") or [],
            details=p.get("details") or [],
            material=p.get("material"),
            care=p.get("care"),
            tags=p.get("tags") or [],
            availability=p.get("availability", "available"),
            made_to_order=p.get("madeToOrder", False),
            badge=p.get("badge"),
            featured=p.get("featured", False),
            new_arrival=p.get("newArrival", False),
            recency=p.get("recency", 0),
            sort_order=p.get("sortOrder", 0),
            source_post=p.get("sourcePost"),
        )
        for position, image in enumerate(p.get("images", [])):
            product.images.append(ProductImage(id=image["id"], position=position, alt=image["alt"], is_upload=False))
        db.session.add(product)
    db.session.commit()
    return len(data["products"])


def register_cli(app):
    @app.cli.command("seed")
    @click.option("--file", "path", type=click.Path(exists=True, dir_okay=False), default=str(SEED_FILE))
    def seed(path):
        """Load the starter catalog into an empty database."""
        if Product.query.first() or Category.query.first():
            raise click.ClickException("The database already has a catalog. Seeding was skipped.")
        count = load_catalog(json.loads(Path(path).read_text()))
        click.echo(f"Loaded {count} products.")

    @app.cli.command("create-admin")
    @click.option("--email", prompt=True)
    @click.password_option(confirmation_prompt=True)
    def create_admin(email, password):
        """Create an admin account."""
        email = email.strip().lower()
        if "@" not in email:
            raise click.ClickException("Enter a valid email address.")
        if len(password) < MIN_PASSWORD:
            raise click.ClickException(f"Use a password of at least {MIN_PASSWORD} characters.")
        if AdminUser.query.filter_by(email=email).first():
            raise click.ClickException("An admin with that email already exists. Use reset-password instead.")
        db.session.add(AdminUser(email=email, password_hash=generate_password_hash(password)))
        db.session.commit()
        click.echo(f"Created admin {email}.")

    @app.cli.command("import-bundled-photos")
    @click.option(
        "--client-dir",
        type=click.Path(exists=True, file_okay=False),
        default=str(SEED_FILE.parent.parent.parent / "client"),
        help="Path to the client repo (default: ../client next to this one, on this machine).",
    )
    def import_bundled_photos(client_dir):
        """Upload the client's bundled photos to storage. Safe to re-run."""
        from flask import current_app

        from .images import SupabaseStorage, get_storage

        storage = get_storage(current_app)
        if not isinstance(storage, SupabaseStorage):
            raise click.ClickException("Set SUPABASE_URL and SUPABASE_SERVICE_KEY in server/.env first.")

        client_dir = Path(client_dir)
        images_dir = client_dir / "public" / "images"
        manifest_file = client_dir / "src" / "data" / "image-manifest.json"
        if not manifest_file.exists():
            raise click.ClickException(f"Can't find {manifest_file}. Pass --client-dir.")
        manifest = json.loads(manifest_file.read_text())

        images = ProductImage.query.filter_by(is_upload=False).all()
        done = skipped = 0
        for image in images:
            meta = manifest.get(image.id)
            if not meta:
                click.echo(f"skip {image.id}: not in image-manifest.json")
                skipped += 1
                continue
            files = {}
            for width in meta["widths"]:
                path = images_dir / f"{image.id}-{width}.webp"
                if not path.exists():
                    click.echo(f"skip {image.id}: missing {path.name}")
                    break
                files[width] = path.read_bytes()
            else:
                try:
                    storage.save(image.id, files)
                except ApiError as err:
                    raise click.ClickException(
                        f"Stopped at {image.id}: {err.message} {done} photos were saved; run the command again to continue."
                    )
                image.is_upload = True
                image.widths, image.width, image.height = meta["widths"], meta["width"], meta["height"]
                db.session.commit()
                done += 1
        click.echo(f"Uploaded {done} photos. {skipped} skipped.")

    @app.cli.command("migrate-images-to-cloudinary")
    @click.option("--dry-run", is_flag=True, help="List what would be copied, change nothing.")
    @click.option("--limit", type=int, default=0, help="Copy at most this many photos (0 = all).")
    @click.option(
        "--client-dir",
        type=click.Path(file_okay=False),
        default=str(SEED_FILE.parent.parent.parent / "client"),
        help="Client repo, for photos still bundled with the site (default: ../client).",
    )
    def migrate_images_to_cloudinary(dry_run, limit, client_dir):
        """Copy every photo into Cloudinary. Safe to re-run; deletes nothing."""
        from flask import current_app

        from .images import PRODUCT_FOLDER, check_delivery, cloudinary_storage, cloudinary_url

        cloud = cloudinary_storage(current_app)
        if cloud is None:
            raise click.ClickException(
                "Set CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY and CLOUDINARY_API_SECRET first."
            )
        manifest_file = Path(client_dir) / "src" / "data" / "image-manifest.json"
        manifest = json.loads(manifest_file.read_text()) if manifest_file.exists() else {}

        pending = (
            ProductImage.query.filter(ProductImage.cloudinary_public_id.is_(None))
            .order_by(ProductImage.product_id, ProductImage.position)
            .all()
        )
        total = ProductImage.query.count()
        click.echo(f"{total - len(pending)} of {total} photos are already in Cloudinary. {len(pending)} to go.")
        if limit:
            pending = pending[:limit]

        done = failed = skipped = 0
        for image in pending:
            source, width, height = legacy_source(current_app, image, manifest, Path(client_dir))
            if source is None:
                click.echo(f"skip {image.id}: no stored copy found")
                skipped += 1
                continue
            if dry_run:
                click.echo(f"would copy {image.id} ({width}x{height}) from {source}")
                continue
            try:
                asset = cloud.upload(source, PRODUCT_FOLDER, image.id)
            except ApiError as err:
                click.echo(f"FAILED {image.id}: {err.message}")
                failed += 1
                continue
            check = cloudinary_url(cloud.cloud_name, asset["public_id"], asset["version"], 320)
            if not check_delivery(check):
                click.echo(f"FAILED {image.id}: uploaded, but {check} didn’t return an image")
                failed += 1
                continue
            # Old columns (is_upload, widths) are kept so IMAGE_DELIVERY=legacy can roll back.
            image.cloudinary_public_id = asset["public_id"]
            image.cloudinary_version = asset["version"]
            image.width, image.height = width, height
            db.session.commit()
            done += 1
            click.echo(f"copied {image.id} -> {asset['public_id']}")

        click.echo(f"Copied {done}, failed {failed}, skipped {skipped}." + (" (dry run)" if dry_run else ""))
        if failed:
            raise click.ClickException("Some photos failed. Run the command again to retry them.")

    @app.cli.command("reset-password")
    @click.option("--email", prompt=True)
    @click.password_option(confirmation_prompt=True)
    def reset_password(email, password):
        """Set a new admin password."""
        user = AdminUser.query.filter_by(email=email.strip().lower()).first()
        if user is None:
            raise click.ClickException("No admin has that email.")
        if len(password) < MIN_PASSWORD:
            raise click.ClickException(f"Use a password of at least {MIN_PASSWORD} characters.")
        user.password_hash = generate_password_hash(password)
        user.session_version += 1
        db.session.commit()
        click.echo("Password updated.")



def legacy_source(app, image, manifest, client_dir):
    """Where a photo is stored today, as (bytes or URL, width, height), or (None, None, None).

    Uses the largest size kept: originals were never stored before Cloudinary.
    """
    if image.is_upload and image.widths:
        width = max(image.widths)
        name = f"{image.id}-{width}.webp"
        base = app.config["UPLOAD_URL_BASE"]
        if base.startswith(("https://", "http://")):
            source = f"{base}/{name}"
        elif app.config["SUPABASE_URL"]:
            source = f"{app.config['SUPABASE_URL'].rstrip('/')}/storage/v1/object/public/{app.config['SUPABASE_BUCKET']}/{name}"
        else:
            path = Path(app.config["UPLOAD_DIR"]) / name
            if not path.exists():
                return None, None, None
            source = path.read_bytes()
        return source, image.width or width, image.height or round(width * 5 / 4)
    meta = manifest.get(image.id)
    if meta:
        path = client_dir / "public" / "images" / f"{image.id}-{meta['width']}.webp"
        if path.exists():
            return path.read_bytes(), meta["width"], meta["height"]
    return None, None, None
