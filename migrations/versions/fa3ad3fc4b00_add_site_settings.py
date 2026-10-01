"""add site settings

Revision ID: fa3ad3fc4b00
Revises: 070fef70c06e
Create Date: 2026-09-30 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'fa3ad3fc4b00'
down_revision = '070fef70c06e'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('site_settings',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('announcement_text', sa.String(length=200), nullable=True),
    sa.Column('announcement_href', sa.String(length=300), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade():
    op.drop_table('site_settings')
