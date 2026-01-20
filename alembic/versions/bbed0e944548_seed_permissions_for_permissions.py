"""seed permissions for permissions

Revision ID: bbed0e944548
Revises: 04ef0f10e1a6
Create Date: 2026-01-20 13:15:59.322102

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "bbed0e944548"
down_revision: Union[str, Sequence[str], None] = "04ef0f10e1a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # ---------------------------------------------------------------------------
    # 1. Seed permissions table with permissions for grants
    # ---------------------------------------------------------------------------
    op.execute("""
        -- Insert permissions for grants
        INSERT INTO permissions (code, name, resource, action, description)
        VALUES
            ('permissions:grant', 'Grant Permissions', 'permissions', 'grant', 'Grant permissions to an entity'),
            ('permissions:revoke', 'Revoke Permissions', 'permissions', 'revoke', 'Revoke permissions from an entity'),
            ('permissions:list', 'List Permissions', 'permissions', 'list', 'List permissions for an entity that is not itself')
        ON CONFLICT (code) DO NOTHING;
        """)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("""
        -- Remove seeded permission-management permissions.
        DELETE FROM permissions
        WHERE code IN (
            'permissions:grant',
            'permissions:revoke',
            'permissions:list'
        );
    """)
