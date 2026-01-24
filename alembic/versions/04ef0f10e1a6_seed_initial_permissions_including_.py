"""seed initial permissions including wildcard

Revision ID: 04ef0f10e1a6
Revises: cae7ebc34ffe
Create Date: 2026-01-20 10:31:37.185671

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "04ef0f10e1a6"
down_revision: Union[str, Sequence[str], None] = "6dd429c167cf"
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
            ('users:*', 'User Administration', 'users', '*', 'Full user management'),

            -- Tenants
            ('tenants:manage', 'Tenant Administration', 'tenants', 'manage', 'Full tenant control'),

            -- Permissions
            ('permissions:grant', 'Grant Permissions', 'permissions', 'grant', 'Grant permissions to an entity'),
            ('permissions:revoke', 'Revoke Permissions', 'permissions', 'revoke', 'Revoke permissions from an entity'),
            ('permissions:list', 'List Permissions', 'permissions', 'list', 'List permissions for an entity that is not itself'),
            ('permissions:*', 'Permission Administration', 'permissions', '*', 'Full permission management'),

            -- Products
            ('products:create', 'Create Products', 'products', 'create', 'Create new products for the tenant'),
            ('products:read',   'View Products',   'products', 'read',   'View products and product details'),
            ('products:update', 'Update Products', 'products', 'update', 'Update existing products'),
            ('products:delete', 'Delete Products', 'products', 'delete', 'Delete products'),
            ('products:*', 'Product Administration', 'products', '*', 'Full product lifecycle management'),

            -- Storefronts
            ('storefronts:create', 'Create Storefronts', 'storefronts', 'create', 'Create storefronts'),
            ('storefronts:read',   'View Storefronts',   'storefronts', 'read',   'View storefronts and details'),
            ('storefronts:update', 'Update Storefronts', 'storefronts', 'update', 'Update storefront configuration'),
            ('storefronts:delete', 'Delete Storefronts', 'storefronts', 'delete', 'Delete storefronts'),
            ('storefronts:*', 'Storefront Administration', 'storefronts', '*', 'Full storefront configuration and management'),

             -- Groups
            ('groups:create', 'Create Groups', 'groups', 'create', 'Create new groups'),
            ('groups:read',   'View Groups',   'groups', 'read',   'View groups and their details'),
            ('groups:update', 'Update Groups', 'groups', 'update', 'Update group details and manage members'),
            ('groups:delete', 'Delete Groups', 'groups', 'delete', 'Delete groups'),
            ('groups:*',      'Group Administration', 'groups', '*', 'Full group management access')
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
            'users:*',
            'tenants:manage',
            'permissions:grant',
            'permissions:revoke',
            'permissions:list',
            'permissions:*',
            'products:create',
            'products:read',
            'products:update',
            'products:delete',
            'products:*',
            'storefronts:create',
            'storefronts:read',
            'storefronts:update',
            'storefronts:delete',
            'storefronts:*',
            'groups:create',
            'groups:read',
            'groups:update',
            'groups:delete',
            'groups:*'
        );
    """)
