"""add slug_updated_at to storefronts table

Revision ID: a89d80bbc98d
Revises: 8158ab056750
Create Date: 2026-01-25 10:46:48.097787

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a89d80bbc98d"
down_revision: Union[str, Sequence[str], None] = "8158ab056750"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("""
        ALTER TABLE storefronts
        ADD COLUMN slug_updated_at TIMESTAMPTZ,
        ADD COLUMN deleted_at TIMESTAMPTZ;
    """)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("""
        ALTER TABLE storefronts
        DROP COLUMN slug_updated_at,
        DROP COLUMN deleted_at;
    """)
