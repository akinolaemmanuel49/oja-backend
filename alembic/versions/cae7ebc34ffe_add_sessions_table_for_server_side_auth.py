"""add sessions table for server-side auth

Revision ID: cae7ebc34ffe
Revises: 6dd429c167cf
Create Date: 2026-01-19 16:12:34.932524

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "cae7ebc34ffe"
down_revision: Union[str, Sequence[str], None] = "6dd429c167cf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # ---------------------------------------------------------------------------
    # 1. Sessions
    # ---------------------------------------------------------------------------
    op.execute("""
        CREATE TABLE sessions (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token           TEXT NOT NULL UNIQUE,              -- signed session identifier
            ip_address      TEXT,
            user_agent      TEXT,
            expires_at      TIMESTAMPTZ NOT NULL,
            created_at      TIMESTAMPTZ DEFAULT NOW(),
            updated_at      TIMESTAMPTZ DEFAULT NOW()
        );
    """)

    op.execute("CREATE INDEX idx_sessions_user_id ON sessions(user_id);")
    op.execute("CREATE INDEX idx_sessions_expires_at ON sessions(expires_at);")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TABLE IF EXISTS sessions CASCADE;")
