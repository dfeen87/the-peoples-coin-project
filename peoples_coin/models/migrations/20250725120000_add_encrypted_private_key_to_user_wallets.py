"""Add encrypted_private_key column to user_wallets table

Revision ID: 20250725120000_add_encrypted_private_key_to_user_wallets
Revises: 20250723201351_add_goodwill_coins_to_user_accounts
Create Date: 2025-07-25 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from peoples_coin.db_types import JSONType, UUIDType, EnumType

# revision identifiers, used by Alembic
revision = '20250725120000_add_encrypted_private_key_to_user_wallets'
down_revision = '20250723201351_add_goodwill_coins_to_user_accounts'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('user_wallets', sa.Column('encrypted_private_key', sa.Text(), nullable=True))

def downgrade():
    op.drop_column('user_wallets', 'encrypted_private_key')
