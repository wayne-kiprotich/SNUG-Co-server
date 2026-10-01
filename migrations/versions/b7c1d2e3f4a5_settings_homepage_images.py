"""homepage images in site settings

Revision ID: b7c1d2e3f4a5
Revises: fa3ad3fc4b00
Create Date: 2026-10-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'b7c1d2e3f4a5'
down_revision = 'fa3ad3fc4b00'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('site_settings') as batch_op:
        batch_op.add_column(sa.Column('hero_image', sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column('hero_alt', sa.String(length=300), nullable=True))
        batch_op.add_column(sa.Column('feature_image', sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column('feature_image_small', sa.String(length=80), nullable=True))


def downgrade():
    with op.batch_alter_table('site_settings') as batch_op:
        batch_op.drop_column('feature_image_small')
        batch_op.drop_column('feature_image')
        batch_op.drop_column('hero_alt')
        batch_op.drop_column('hero_image')
