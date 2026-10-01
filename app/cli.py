import json
from pathlib import Path

import click
from werkzeug.security import generate_password_hash

from .extensions import db
from .models import AdminUser, Category, Collection, Product, ProductImage
from .routes.auth import MIN_PASSWORD

SEED_FILE = Path(__file__).resolve().parent.parent / "seed" / "catalog.json"


def load_catalog(data):
    """Insert categories, collections and products from the seed file's JSON."""
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
        """Load the starter catalog (from the storefront's bundled data). Only runs on an empty database."""
        if Product.query.first() or Category.query.first():
            raise click.ClickException("The database already has a catalog. Seeding was skipped.")
        count = load_catalog(json.loads(Path(path).read_text()))
        click.echo(f"Loaded {count} products.")

    @app.cli.command("create-admin")
    @click.option("--email", prompt=True)
    @click.password_option(confirmation_prompt=True)
    def create_admin(email, password):
        """Create a person who can sign in to the admin."""
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
        """Upload the storefront's bundled product photos to storage, once.

        The seeded catalog points at photo ids that ship inside the client's own
        repo (client/public/images). Run this once, from a machine with both
        repos checked out, so those same photos also exist in SUPABASE_URL
        storage. Products then stop depending on the client bundling them.
        """
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
                storage.save(image.id, files)
                image.is_upload = True
                image.widths, image.width, image.height = meta["widths"], meta["width"], meta["height"]
                db.session.commit()
                done += 1
        click.echo(f"Uploaded {done} photos. {skipped} skipped.")

    @app.cli.command("reset-password")
    @click.option("--email", prompt=True)
    @click.password_option(confirmation_prompt=True)
    def reset_password(email, password):
        """Set a new password for an existing admin."""
        user = AdminUser.query.filter_by(email=email.strip().lower()).first()
        if user is None:
            raise click.ClickException("No admin has that email.")
        if len(password) < MIN_PASSWORD:
            raise click.ClickException(f"Use a password of at least {MIN_PASSWORD} characters.")
        user.password_hash = generate_password_hash(password)
        db.session.commit()
        click.echo("Password updated.")

