"""Turn on row level security for every table (PostgreSQL only)

Defense in depth: a table is reachable through Supabase's Data API only if its schema (or the
table) is exposed there and the anon or authenticated roles have grants on it. If that ever
happens, RLS with no public policies means the Data API sees no rows and can change nothing.
Flask is unaffected: it connects as the tables' owner, and owners bypass RLS. ALTER TABLE only
succeeds for the owner, so if this migration runs, the app's own access is unchanged.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-10-03 00:00:00.000000

"""
from alembic import op


revision = 'e5f6a7b8c9d0'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None

# Every table, including Alembic's own. A new table needs its own migration that does the same.
TABLES = (
    'admin_users',
    'categories',
    'collections',
    'products',
    'product_collections',
    'product_images',
    'site_settings',
    'alembic_version',
)


def upgrade():
    if op.get_bind().dialect.name != 'postgresql':
        return
    for table in TABLES:
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')


def downgrade():
    if op.get_bind().dialect.name != 'postgresql':
        return
    for table in TABLES:
        op.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')
