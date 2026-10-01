"""admin session version, so password changes sign out other browsers

Revision ID: c3d4e5f6a7b8
Revises: b7c1d2e3f4a5
Create Date: 2026-10-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'c3d4e5f6a7b8'
down_revision = 'b7c1d2e3f4a5'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('admin_users') as batch_op:
        batch_op.add_column(sa.Column('session_version', sa.Integer(), nullable=False, server_default='0'))


def downgrade():
    with op.batch_alter_table('admin_users') as batch_op:
        batch_op.drop_column('session_version')
