"""seed initial permissions including wildcard

Revision ID: 04ef0f10e1a6
Revises: cae7ebc34ffe
Create Date: 2026-01-20 10:31:37.185671

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "04ef0f10e1a6"
down_revision: Union[str, Sequence[str], None] = "cae7ebc34ffe"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # ---------------------------------------------------------------------------
    # 1. Seed initial permissions including system-defined, reusable permissions
    # ---------------------------------------------------------------------------
    op.execute("""
        -- Preset permissions (system-defined, reusable)
        INSERT INTO permissions (code, name, resource, action, description)
        VALUES
            ('*', 'Superuser Access', '*', '*', 'Unrestricted access to all system resources'),
            ('users:create', 'Create Users', 'users', 'create', 'Create new users in tenant'),
            ('users:read', 'View Users', 'users', 'read', 'View user list and details'),
            ('users:update', 'Update Users', 'users', 'update', 'Edit user profiles'),
            ('users:delete', 'Delete Users', 'users', 'delete', 'Soft-delete users'),
            ('tenants:manage', 'Tenant Administration', 'tenants', 'manage', 'Full tenant control'),
            ('products:*', 'Product Administration', 'products', '*', 'Full product lifecycle management'),
            ('storefronts:*', 'Storefront Administration', 'storefronts', '*', 'Full storefront configuration and management'),
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
            '*',
            'users:create',
            'users:read',
            'users:update',
            'users:delete',
            'tenants:manage',
            'products:*',
            'storefronts:*',
            'permissions:grant',
            'permissions:revoke',
            'permissions:list'
        );
    """)
