"""Cloudinary asset details on product images

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-10-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'd4e5f6a7b8c9'
down_revision = 'c3d4e5f6a7b8'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('product_images') as batch_op:
        batch_op.add_column(sa.Column('cloudinary_public_id', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('cloudinary_version', sa.BigInteger(), nullable=True))
        batch_op.add_column(sa.Column('crop_x', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('crop_y', sa.Integer(), nullable=True))
        batch_op.create_index('ix_product_images_cloudinary_public_id', ['cloudinary_public_id'])


def downgrade():
    with op.batch_alter_table('product_images') as batch_op:
        batch_op.drop_index('ix_product_images_cloudinary_public_id')
        batch_op.drop_column('crop_y')
        batch_op.drop_column('crop_x')
        batch_op.drop_column('cloudinary_version')
        batch_op.drop_column('cloudinary_public_id')
