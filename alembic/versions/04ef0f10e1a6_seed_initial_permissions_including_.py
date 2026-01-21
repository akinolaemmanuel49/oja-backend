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
            -- Superuser Access
            ('*', 'Superuser Access', '*', '*', 'Unrestricted access to all system resources'),

            -- Users
            ('users:create', 'Create Users', 'users', 'create', 'Create new users in tenant'),
            ('users:read', 'View Users', 'users', 'read', 'View user list and details'),
            ('users:update', 'Update Users', 'users', 'update', 'Edit user profiles'),
            ('users:delete', 'Delete Users', 'users', 'delete', 'Soft-delete users'),

            -- Tenants
            ('tenants:manage', 'Tenant Administration', 'tenants', 'manage', 'Full tenant control'),

            -- Legacy permissions
            ('products:*', 'Product Administration', 'products', '*', 'Full product lifecycle management'),
            ('storefronts:*', 'Storefront Administration', 'storefronts', '*', 'Full storefront configuration and management'),

            -- Permissions
            ('permissions:grant', 'Grant Permissions', 'permissions', 'grant', 'Grant permissions to an entity'),
            ('permissions:revoke', 'Revoke Permissions', 'permissions', 'revoke', 'Revoke permissions from an entity'),
            ('permissions:list', 'List Permissions', 'permissions', 'list', 'List permissions for an entity that is not itself'),

            -- Products
            ('products:create', 'Create Products', 'products', 'create', 'Create new products for the tenant'),
            ('products:read',   'View Products',   'products', 'read',   'View products and product details'),
            ('products:update', 'Update Products', 'products', 'update', 'Update existing products'),
            ('products:delete', 'Delete Products', 'products', 'delete', 'Delete products'),

            -- Storefronts
            ('storefronts:create', 'Create Storefronts', 'storefronts', 'create', 'Create storefronts'),
            ('storefronts:read',   'View Storefronts',   'storefronts', 'read',   'View storefronts and details'),
            ('storefronts:update', 'Update Storefronts', 'storefronts', 'update', 'Update storefront configuration'),
            ('storefronts:delete', 'Delete Storefronts', 'storefronts', 'delete', 'Delete storefronts')
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
            'permissions:list',
            'products:create',
            'products:read',
            'products:update',
            'products:delete',
            'storefronts:create',
            'storefronts:read',
            'storefronts:update',
            'storefronts:delete'
        );
    """)
