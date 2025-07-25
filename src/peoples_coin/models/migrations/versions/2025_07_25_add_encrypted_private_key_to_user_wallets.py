"""Add encrypted_private_key column to user_wallets table

Revision ID: add_encrypted_private_key_to_user_wallets
Revises: <previous_revision_id>
Create Date: 2025-07-25 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_encrypted_private_key_to_user_wallets'
down_revision = '<previous_revision_id>'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('user_wallets', sa.Column('encrypted_private_key', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('user_wallets', 'encrypted_private_key')

