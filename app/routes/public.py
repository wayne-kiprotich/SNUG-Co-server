from flask import Blueprint, jsonify

from ..extensions import db
from ..models import Category, Collection, Product, SiteSettings
from ..serializers import image_registry, product_json, settings_json, taxonomy_json

bp = Blueprint("public", __name__, url_prefix="/api")


@bp.get("/health")
def health():
    return jsonify({"status": "ok"})


@bp.get("/settings")
def settings():
    row = db.session.get(SiteSettings, 1)
    response = jsonify(settings_json(row))
    response.headers["Cache-Control"] = "public, max-age=60"
    return response


@bp.get("/catalog")
def catalog():
    """Everything the storefront needs in one request. Hidden products are left out."""
    products = (
        Product.query.filter_by(published=True).order_by(Product.sort_order, Product.id).all()
    )
    categories = Category.query.order_by(Category.sort_order, Category.id).all()
    collections = Collection.query.order_by(Collection.sort_order, Collection.id).all()

    image_ids = [i.id for p in products for i in p.images]
    image_ids += [c.image_id for c in categories] + [c.image_id for c in collections]

    response = jsonify(
        {
            "products": [product_json(p) for p in products],
            "categories": [taxonomy_json(c) for c in categories],
            "collections": [taxonomy_json(c) for c in collections],
            "images": image_registry(image_ids),
        }
    )
    response.headers["Cache-Control"] = "public, max-age=60"
    return response
