from datetime import datetime, timezone

from .extensions import db


def _now():
    return datetime.now(timezone.utc)


product_collections = db.Table(
    "product_collections",
    db.Column("product_id", db.Integer, db.ForeignKey("products.id", ondelete="CASCADE"), primary_key=True),
    db.Column("collection_id", db.Integer, db.ForeignKey("collections.id", ondelete="CASCADE"), primary_key=True),
)


class AdminUser(db.Model):
    __tablename__ = "admin_users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(254), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=_now, nullable=False)
    last_login_at = db.Column(db.DateTime(timezone=True))


class Category(db.Model):
    __tablename__ = "categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    slug = db.Column(db.String(80), unique=True, nullable=False)
    description = db.Column(db.String(300))
    # An image id: either a bundled site image or an uploaded one.
    image_id = db.Column(db.String(80))
    sort_order = db.Column(db.Integer, default=0, nullable=False)

    products = db.relationship("Product", back_populates="category")


class Collection(db.Model):
    __tablename__ = "collections"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    slug = db.Column(db.String(80), unique=True, nullable=False)
    description = db.Column(db.String(300))
    image_id = db.Column(db.String(80))
    sort_order = db.Column(db.Integer, default=0, nullable=False)

    products = db.relationship("Product", secondary=product_collections, back_populates="collections")


class Product(db.Model):
    __tablename__ = "products"

    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(80), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    name_confirmed = db.Column(db.Boolean, default=True, nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=False)
    description = db.Column(db.Text, nullable=False)
    price_kes = db.Column(db.Integer)
    compare_at_price_kes = db.Column(db.Integer)
    colors = db.Column(db.JSON)  # [{name, swatch: [#hex, #hex?]}] or null
    sizes = db.Column(db.JSON)  # ["S", "M"] or null
    sizes_note = db.Column(db.String(200))
    options = db.Column(db.JSON, default=list, nullable=False)  # [{name, values|type:text, required}]
    details = db.Column(db.JSON, default=list, nullable=False)
    material = db.Column(db.String(200))
    care = db.Column(db.String(400))
    tags = db.Column(db.JSON, default=list, nullable=False)
    availability = db.Column(db.String(20), default="available", nullable=False)
    made_to_order = db.Column(db.Boolean, default=False, nullable=False)
    badge = db.Column(db.String(20))
    featured = db.Column(db.Boolean, default=False, nullable=False)
    new_arrival = db.Column(db.Boolean, default=False, nullable=False)
    published = db.Column(db.Boolean, default=True, nullable=False)
    # Lower recency means more recently added. Lower sort_order shows earlier.
    recency = db.Column(db.Integer, default=0, nullable=False)
    sort_order = db.Column(db.Integer, default=0, nullable=False)
    source_post = db.Column(db.String(300))
    created_at = db.Column(db.DateTime(timezone=True), default=_now, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)

    category = db.relationship("Category", back_populates="products")
    collections = db.relationship(
        "Collection", secondary=product_collections, back_populates="products", order_by="Collection.sort_order"
    )
    images = db.relationship(
        "ProductImage",
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="ProductImage.position",
    )


class ProductImage(db.Model):
    __tablename__ = "product_images"

    # For bundled site images this is the image name. For uploads it is "u" plus random hex.
    id = db.Column(db.String(80), primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    position = db.Column(db.Integer, default=0, nullable=False)
    alt = db.Column(db.String(300), default="", nullable=False)
    is_upload = db.Column(db.Boolean, default=False, nullable=False)
    # Set only for uploads: the widths written to disk and the largest size.
    widths = db.Column(db.JSON)
    width = db.Column(db.Integer)
    height = db.Column(db.Integer)

    product = db.relationship("Product", back_populates="images")
