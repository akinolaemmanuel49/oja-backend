"""enable rls and add tenant isolation policies

Revision ID: 8158ab056750
Revises: 04ef0f10e1a6
Create Date: 2026-01-21 06:04:32.935977

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8158ab056750"
down_revision: Union[str, Sequence[str], None] = "04ef0f10e1a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Enable RLS on tenant-scoped tables
    op.execute("ALTER TABLE tenants ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE users ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE groups ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE storefronts ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE products ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE product_variants ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE storefront_products ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE user_groups ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE user_permissions ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE group_permissions ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE role_permissions ENABLE ROW LEVEL SECURITY;")

    # ---------------------------------------------------------------------------
    # Tenant isolation policies
    # ---------------------------------------------------------------------------

    # ---------------------------------------------------------------------------
    # Tenants
    # ---------------------------------------------------------------------------
    op.execute("""
        CREATE POLICY tenant_isolation_tenants ON tenants
        FOR ALL
        USING (
            id = current_setting('app.current_tenant_id')::UUID
        );
    """)

    # ---------------------------------------------------------------------------
    # Users
    # ---------------------------------------------------------------------------
    op.execute("""
        CREATE POLICY tenant_isolation_users ON users
        FOR ALL
        USING (
            tenant_id = current_setting('app.current_tenant_id')::UUID
            OR id = current_setting('app.current_user_id')::UUID
        );
    """)

    # ---------------------------------------------------------------------------
    # Groups
    # ---------------------------------------------------------------------------
    op.execute("""
        CREATE POLICY tenant_isolation_groups ON groups
        FOR ALL
        USING (
            tenant_id = current_setting('app.current_tenant_id')::UUID
        );
    """)

    # ---------------------------------------------------------------------------
    # Storefronts
    # ---------------------------------------------------------------------------
    op.execute("""
        CREATE POLICY public_read_storefronts ON storefronts
        FOR SELECT
        USING (true);  -- everyone can read
    """)

    op.execute("""
        CREATE POLICY tenant_write_storefronts ON storefronts
        FOR ALL
        USING (
            tenant_id = current_setting('app.current_tenant_id')::UUID
        )
        WITH CHECK (
            tenant_id = current_setting('app.current_tenant_id')::UUID
        );
    """)

    # ---------------------------------------------------------------------------
    # Products
    # ---------------------------------------------------------------------------
    op.execute("""
        CREATE POLICY public_read_products ON products
        FOR SELECT
        USING (true);
    """)

    op.execute("""
        CREATE POLICY tenant_write_products ON products
        FOR ALL
        USING (
            tenant_id = current_setting('app.current_tenant_id')::UUID
        )
        WITH CHECK (
            tenant_id = current_setting('app.current_tenant_id')::UUID
        );
    """)

    # ---------------------------------------------------------------------------
    # Product Variants
    # ---------------------------------------------------------------------------
    op.execute("""
        CREATE POLICY public_read_variants ON product_variants
        FOR SELECT
        USING (true);
    """)

    op.execute("""
        CREATE POLICY tenant_write_variants ON product_variants
        FOR ALL
        USING (
            EXISTS (
                SELECT 1 FROM products p
                WHERE p.id = product_id AND p.tenant_id = current_setting('app.current_tenant_id')::UUID
            )
        );
    """)

    # ---------------------------------------------------------------------------
    # Storefront ↔ Products (many-to-many join table)
    # ---------------------------------------------------------------------------
    op.execute("""
        CREATE POLICY tenant_read_storefront_products ON storefront_products
        FOR SELECT
        USING (true);  -- public read for catalog
    """)

    op.execute("""
        CREATE POLICY tenant_write_storefront_products ON storefront_products
        FOR ALL
        USING (
            EXISTS (
                SELECT 1 FROM storefronts s
                WHERE s.id = storefront_id AND s.tenant_id = current_setting('app.current_tenant_id')::UUID
            )
        )
        WITH CHECK (
            EXISTS (
                SELECT 1 FROM storefronts s
                WHERE s.id = storefront_id AND s.tenant_id = current_setting('app.current_tenant_id')::UUID
            )
        );
    """)

    # ---------------------------------------------------------------------------
    # User ↔ Group membership
    # ---------------------------------------------------------------------------
    op.execute("""
        CREATE POLICY tenant_isolation_user_groups ON user_groups
        FOR ALL
        USING (
            EXISTS (
                SELECT 1 FROM users u
                WHERE u.id = user_id AND u.tenant_id = current_setting('app.current_tenant_id')::UUID
            )
            OR EXISTS (
                SELECT 1 FROM groups g
                WHERE g.id = group_id AND g.tenant_id = current_setting('app.current_tenant_id')::UUID
            )
        )
        WITH CHECK (
            EXISTS (
                SELECT 1 FROM users u
                WHERE u.id = user_id AND u.tenant_id = current_setting('app.current_tenant_id')::UUID
            )
        );
    """)

    # ---------------------------------------------------------------------------
    # User permissions (direct assignments)
    # ---------------------------------------------------------------------------
    op.execute("""
        CREATE POLICY tenant_isolation_user_permissions ON user_permissions
        FOR ALL
        USING (
            EXISTS (
                SELECT 1 FROM users u
                WHERE u.id = user_id AND u.tenant_id = current_setting('app.current_tenant_id')::UUID
            )
        )
        WITH CHECK (
            EXISTS (
                SELECT 1 FROM users u
                WHERE u.id = user_id AND u.tenant_id = current_setting('app.current_tenant_id')::UUID
            )
        );
    """)

    # ---------------------------------------------------------------------------
    # Group permissions (join table)
    # ---------------------------------------------------------------------------
    op.execute("""
        CREATE POLICY tenant_isolation_group_permissions ON group_permissions
        FOR ALL
        USING (
            EXISTS (
                SELECT 1 FROM groups g
                WHERE g.id = group_id AND g.tenant_id = current_setting('app.current_tenant_id')::UUID
            )
        )
        WITH CHECK (
            EXISTS (
                SELECT 1 FROM groups g
                WHERE g.id = group_id AND g.tenant_id = current_setting('app.current_tenant_id')::UUID
            )
        );
    """)

    # ---------------------------------------------------------------------------
    # Role permissions (system table – root/admin only)
    # ---------------------------------------------------------------------------
    op.execute("""
        CREATE POLICY root_only_role_permissions ON role_permissions
        FOR ALL
        USING (current_setting('app.is_root')::BOOLEAN = TRUE)
        WITH CHECK (current_setting('app.is_root')::BOOLEAN = TRUE);
    """)


def downgrade() -> None:
    """Downgrade schema"""

    # Reverse RLS policies and disable RLS
    # Drop all policies in reverse order (dependencies are not strict here, but good practice)
    op.execute("DROP POLICY IF EXISTS tenant_write_variants ON product_variants;")
    op.execute("DROP POLICY IF EXISTS public_read_variants ON product_variants;")
    op.execute("DROP POLICY IF EXISTS tenant_write_products ON products;")
    op.execute("DROP POLICY IF EXISTS public_read_products ON products;")
    op.execute("DROP POLICY IF EXISTS tenant_write_storefronts ON storefronts;")
    op.execute("DROP POLICY IF EXISTS public_read_storefronts ON storefronts;")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_groups ON groups;")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_users ON users;")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_tenants ON tenants;")
    op.execute("DROP POLICY IF EXISTS root_only_role_permissions ON role_permissions;")
    op.execute(
        "DROP POLICY IF EXISTS tenant_isolation_group_permissions ON group_permissions;"
    )
    op.execute(
        "DROP POLICY IF EXISTS tenant_isolation_user_permissions ON user_permissions;"
    )
    op.execute("DROP POLICY IF EXISTS tenant_isolation_user_groups ON user_groups;")
    op.execute(
        "DROP POLICY IF EXISTS tenant_write_storefront_products ON storefront_products;"
    )
    op.execute(
        "DROP POLICY IF EXISTS tenant_read_storefront_products ON storefront_products;"
    )

    # Disable RLS on all affected tables
    op.execute("ALTER TABLE product_variants DISABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE products DISABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE storefronts DISABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE group_permissions DISABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE user_permissions DISABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE role_permissions DISABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE user_groups DISABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE groups DISABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE users DISABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE tenants DISABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE role_permissions DISABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE group_permissions DISABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE user_permissions DISABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE user_groups DISABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE storefront_products DISABLE ROW LEVEL SECURITY;")
