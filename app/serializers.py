"""Turns database rows into the JSON shape the React client already uses."""

from flask import current_app

from .models import ProductImage


def image_meta(image):
    base = f"{current_app.config['UPLOAD_URL_BASE']}/{image.id}"
    return {"widths": image.widths, "width": image.width, "height": image.height, "base": base}


def image_registry(image_ids):
    """Metadata for uploaded images. Bundled site images are resolved by the client itself."""
    ids = {i for i in image_ids if i}
    if not ids:
        return {}
    rows = ProductImage.query.filter(ProductImage.id.in_(ids), ProductImage.is_upload.is_(True)).all()
    return {row.id: image_meta(row) for row in rows}


def product_json(p, admin=False):
    data = {
        "id": p.id if admin else f"p{p.id}",
        "slug": p.slug,
        "name": p.name,
        "nameConfirmed": p.name_confirmed,
        "category": p.category.slug,
        "collections": [c.slug for c in p.collections],
        "description": p.description,
        "priceKES": p.price_kes,
        "compareAtPriceKES": p.compare_at_price_kes,
        "images": [{"id": i.id, "alt": i.alt} for i in p.images],
        "colors": p.colors or None,
        "sizes": p.sizes or None,
        "sizesNote": p.sizes_note,
        "options": p.options or [],
        "details": p.details or [],
        "material": p.material,
        "care": p.care,
        "tags": p.tags or [],
        "availability": p.availability,
        "madeToOrder": p.made_to_order,
        "badge": p.badge,
        "featured": p.featured,
        "newArrival": p.new_arrival,
        "recency": p.recency,
        "sortOrder": p.sort_order,
        "sourcePost": p.source_post,
    }
    if admin:
        data["published"] = p.published
        data["updatedAt"] = p.updated_at.isoformat() if p.updated_at else None
    return data


def settings_json(row):
    return {
        "announcementText": row.announcement_text,
        "announcementHref": row.announcement_href,
    }


def taxonomy_json(item, admin=False):
    data = {
        "id": item.id if admin else f"{'c' if item.__tablename__ == 'categories' else 'k'}{item.id}",
        "name": item.name,
        "slug": item.slug,
        "description": item.description or "",
        "image": item.image_id,
        "sortOrder": item.sort_order,
    }
    if admin:
        data["productCount"] = len(item.products)
    return data
