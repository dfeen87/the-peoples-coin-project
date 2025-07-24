"""Add goodwill_coins to user_accounts

Revision ID: eaa8dc007009
Revises: 
Create Date: 2025-07-23 17:08:15.123456

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'eaa8dc007009'
# UPDATED: This is the crucial fix. It should be 'None' for the first migration.
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    """
    Applies the migration to the database.
    """
    op.execute("""
    ALTER TABLE user_accounts
    ADD COLUMN goodwill_coins INTEGER NOT NULL DEFAULT 0;
    """)
    op.execute("""
    COMMENT ON COLUMN user_accounts.goodwill_coins IS 'A non-spendable keepsake token awarded for each verified act of goodwill.';
    """)


def downgrade():
    """
    Reverts the migration from the database.
    """
    op.execute("""
    ALTER TABLE user_accounts
    DROP COLUMN goodwill_coins;
    """)
