"""add new permissions for storefront and products

Revision ID: 6f3e96f3cc9b
Revises: 8158ab056750
Create Date: 2026-01-21 11:31:10.314254

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6f3e96f3cc9b"
down_revision: Union[str, Sequence[str], None] = "8158ab056750"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("""
        INSERT INTO permissions (code, name, resource, action, description)
        VALUES
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
        -- Remove seeded permission-management permissions
        DELETE FROM permissions
        WHERE code IN (
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
