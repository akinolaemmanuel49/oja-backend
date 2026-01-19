"""initial schema: tenants, users, groups, permissions, roles, storefronts, products

Revision ID: 6dd429c167cf
Revises:
Create Date: 2026-01-19 08:09:15.967312
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6dd429c167cf"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # Enable UUID generation (included in postgres:16-alpine)
    op.execute("""
        CREATE EXTENSION IF NOT EXISTS "pgcrypto";
    """)

    # ---------------------------------------------------------------------------
    # 1. Tenants (top-level isolation unit / organization / account)
    # ---------------------------------------------------------------------------
    op.execute("""
        CREATE TABLE tenants (
            id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            slug       TEXT NOT NULL UNIQUE,
            name       TEXT NOT NULL UNIQUE,
            owner_id   UUID UNIQUE,
            status     TEXT NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'suspended', 'deleted')),
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        );
    """)

    # ---------------------------------------------------------------------------
    # 2. Users (individuals – soft-deleted)
    # ---------------------------------------------------------------------------
    op.execute("""
        CREATE TABLE users (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            email           TEXT NOT NULL UNIQUE,
            password_hash   TEXT NOT NULL,
            first_name      TEXT NOT NULL,
            last_name       TEXT NOT NULL,
            full_name       TEXT,
            is_active       BOOLEAN DEFAULT TRUE,
            is_root         BOOLEAN DEFAULT FALSE,          -- global platform emergency admin
            tenant_id       UUID REFERENCES tenants(id)
                ON DELETE RESTRICT
                ON UPDATE CASCADE,
            deleted_at      TIMESTAMPTZ,                     -- NULL = active, non-NULL = soft-deleted
            created_at      TIMESTAMPTZ DEFAULT NOW(),
            updated_at      TIMESTAMPTZ DEFAULT NOW()
        );
    """)

    # ---------------------------------------------------------------------------
    # 3. Groups (optional – users can be standalone or belong to multiple groups)
    # ---------------------------------------------------------------------------
    op.execute("""
        CREATE TABLE groups (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id   UUID NOT NULL REFERENCES tenants(id)
                ON DELETE CASCADE,
            name        TEXT NOT NULL,
            description TEXT,
            created_at  TIMESTAMPTZ DEFAULT NOW(),
            updated_at  TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE (tenant_id, name)
        );
    """)

    # ---------------------------------------------------------------------------
    # 4. User ↔ Group membership (many-to-many)
    # Deleting group → removes all its membership rows
    # Deleting user (soft) → membership rows remain (application decides cleanup)
    # ---------------------------------------------------------------------------
    op.execute("""
        CREATE TABLE user_groups (
            user_id     UUID NOT NULL REFERENCES users(id)
                ON DELETE RESTRICT,
            group_id    UUID NOT NULL REFERENCES groups(id)
                ON DELETE CASCADE,
            created_at  TIMESTAMPTZ DEFAULT NOW(),
            PRIMARY KEY (user_id, group_id)
        );
    """)

    # ---------------------------------------------------------------------------
    # 5. Permissions (atomic rights)
    # ---------------------------------------------------------------------------
    op.execute("""
        CREATE TABLE permissions (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            code        TEXT NOT NULL UNIQUE,
            name        TEXT NOT NULL,
            resource    TEXT NOT NULL,
            action      TEXT NOT NULL,
            description TEXT,
            created_at  TIMESTAMPTZ DEFAULT NOW()
        );
    """)

    # ---------------------------------------------------------------------------
    # 6. Direct user permissions (optional)
    # ---------------------------------------------------------------------------
    op.execute("""
        CREATE TABLE user_permissions (
            user_id         UUID NOT NULL REFERENCES users(id)
                ON DELETE CASCADE,
            permission_id   UUID NOT NULL REFERENCES permissions(id)
                ON DELETE CASCADE,
            created_at      TIMESTAMPTZ DEFAULT NOW(),
            PRIMARY KEY (user_id, permission_id)
        );
    """)

    # ---------------------------------------------------------------------------
    # 7. Group permissions (inherited by members)
    # ---------------------------------------------------------------------------
    op.execute("""
        CREATE TABLE group_permissions (
            group_id        UUID NOT NULL REFERENCES groups(id)
                ON DELETE CASCADE,
            permission_id   UUID NOT NULL REFERENCES permissions(id)
                ON DELETE CASCADE,
            created_at      TIMESTAMPTZ DEFAULT NOW(),
            PRIMARY KEY (group_id, permission_id)
        );
    """)

    # ---------------------------------------------------------------------------
    # 8. Roles (system / internal use only – not assigned to users)
    # ---------------------------------------------------------------------------
    op.execute("""
        CREATE TABLE roles (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name        TEXT NOT NULL UNIQUE,
            description TEXT,
            created_at  TIMESTAMPTZ DEFAULT NOW()
        );
    """)

    # ---------------------------------------------------------------------------
    # 9. Role ↔ Permission (system roles only)
    # ---------------------------------------------------------------------------
    op.execute("""
        CREATE TABLE role_permissions (
            role_id         UUID NOT NULL REFERENCES roles(id)
                ON DELETE CASCADE,
            permission_id   UUID NOT NULL REFERENCES permissions(id)
                ON DELETE CASCADE,
            PRIMARY KEY (role_id, permission_id)
        );
    """)

    # ---------------------------------------------------------------------------
    # 10. Storefronts (a tenant can own multiple storefronts)
    # ---------------------------------------------------------------------------
    op.execute("""
        CREATE TABLE storefronts (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id   UUID NOT NULL REFERENCES tenants(id)
                ON DELETE CASCADE,
            slug        TEXT NOT NULL,
            name        TEXT NOT NULL,
            domain      TEXT,
            status      TEXT NOT NULL DEFAULT 'active',
            created_at  TIMESTAMPTZ DEFAULT NOW(),
            updated_at  TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE (tenant_id, slug)
        );
    """)

    # ---------------------------------------------------------------------------
    # 11. Products (scoped to storefront and tenant)
    # ---------------------------------------------------------------------------
    op.execute("""
        CREATE TABLE products (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            storefront_id   UUID NOT NULL REFERENCES storefronts(id)
                ON DELETE CASCADE,
            tenant_id       UUID NOT NULL REFERENCES tenants(id)
                ON DELETE CASCADE,
            name            TEXT NOT NULL,
            price           NUMERIC(12,2) NOT NULL,
            description     TEXT,
            created_at      TIMESTAMPTZ DEFAULT NOW(),
            updated_at      TIMESTAMPTZ DEFAULT NOW()
        );
    """)

    # ---------------------------------------------------------------------------
    # 12. Others
    # ---------------------------------------------------------------------------
    op.execute("""
        -- Enforce only one root user per tenant (or globally if tenant_id IS NULL)
        CREATE UNIQUE INDEX idx_users_unique_root_per_tenant
            ON users (tenant_id, is_root)
            WHERE is_root = TRUE;
        """)

    op.execute("""
        ALTER TABLE tenants
        ADD CONSTRAINT fk_tenants_owner_id
        FOREIGN KEY (owner_id)
        REFERENCES users(id)
        ON DELETE RESTRICT;
    """)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TABLE IF EXISTS products CASCADE;")
    op.execute("DROP TABLE IF EXISTS storefronts CASCADE;")
    op.execute("DROP TABLE IF EXISTS role_permissions CASCADE;")
    op.execute("DROP TABLE IF EXISTS roles CASCADE;")
    op.execute("DROP TABLE IF EXISTS group_permissions CASCADE;")
    op.execute("DROP TABLE IF EXISTS user_permissions CASCADE;")
    op.execute("DROP TABLE IF EXISTS permissions CASCADE;")
    op.execute("DROP TABLE IF EXISTS user_groups CASCADE;")
    op.execute("DROP TABLE IF EXISTS groups CASCADE;")
    op.execute("DROP INDEX IF EXISTS idx_users_unique_root_per_tenant;")
    op.execute("ALTER TABLE tenants DROP CONSTRAINT IF EXISTS fk_tenants_owner_id;")
    op.execute("DROP TABLE IF EXISTS users CASCADE;")
    op.execute("DROP TABLE IF EXISTS tenants CASCADE;")
