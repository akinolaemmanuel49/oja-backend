from typing import Any, Dict, Optional

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.responses import PaginatedResponse
from src.core.security import hash_password
from src.core.utils import ALPHANUMERIC, ALPHANUMERIC_LOWER, generate_random_string
from src.permissions.service import list_user_permissions
from src.users.schemas import UserCreate, UserOut

INSERT_TENANT_QUERY = text("""
    INSERT INTO tenants (slug, name, status, created_at, updated_at)
    VALUES (:slug, :name, 'active', NOW(), NOW())
    RETURNING id
""")

INSERT_USER_QUERY = text("""
    INSERT INTO users (
        email,
        password_hash,
        first_name,
        last_name,
        full_name,
        tenant_id,
        is_root,
        created_at,
        updated_at
    )
    VALUES (
        :email,
        :password_hash,
        :first_name,
        :last_name,
        :full_name,
        :tenant_id,
        :is_root,
        NOW(),
        NOW()
    )
    RETURNING
        id,
        email,
        first_name,
        last_name,
        full_name,
        is_active,
        is_root,
        tenant_id,
        created_at
""")

UPDATE_TENANT_QUERY = text("""
    UPDATE tenants
    SET owner_id = :owner_id, updated_at = NOW()
    WHERE id = :tenant_id
""")

READ_USER_QUERY_BY_ID = text("""
     SELECT id, email, first_name, last_name, full_name, tenant_id, is_active, is_root, created_at, updated_at
     FROM users
     WHERE id = :user_id
 """)

READ_USER_QUERY_BY_EMAIL = text("""
     SELECT id, email, first_name, last_name, full_name, tenant_id, is_active, is_root, created_at, updated_at
     FROM users
     WHERE email = :email
 """)

READ_USERS_QUERY_BY_TENANT_ID = text("""
    SELECT id, email, first_name, last_name, full_name, tenant_id,
           is_active, is_root, created_at, updated_at
    FROM users
    WHERE tenant_id = :tenant_id
    ORDER BY created_at DESC
    LIMIT :limit OFFSET :offset
""")

COUNT_USERS_QUERY_BY_TENANT_ID = text("""
    SELECT COUNT(*)
    FROM users
    WHERE tenant_id = :tenant_id
""")


async def create_user_service(
    db: AsyncSession,
    user_in: UserCreate,
    is_root: bool = False,
    tenant_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a new user with hashed password.

    - If tenant_id is provided → use it (normal user in existing tenant)
    - If tenant_id is None and is_root=True → create a new tenant atomically
    - Full transaction: rollback on any failure

    Returns:
        {
            "user": {...},
            "tenant": {...}  # only if a new tenant was created
        }
    """
    try:
        hashed_pw = hash_password(user_in.password)

        new_tenant_id: Optional[str] = None

        # Explicit initialization for static analysis
        slug: Optional[str] = None
        name: Optional[str] = None

        # Root user case: create tenant first
        if is_root and tenant_id is None:
            slug = generate_random_string(
                pattern="XXXX-XXXX-XXXX",
                chars=ALPHANUMERIC_LOWER,
            )
            name = generate_random_string(
                pattern="Tenant-XXXXXX",
                chars=ALPHANUMERIC,
            )

            tenant_result = await db.execute(
                INSERT_TENANT_QUERY,
                {"slug": slug, "name": name},
            )
            tenant_row = tenant_result.mappings().first()
            if not tenant_row:
                raise RuntimeError("Failed to create root tenant")

            new_tenant_id = str(tenant_row["id"])
            tenant_id = new_tenant_id

        # Create user
        user_result = await db.execute(
            INSERT_USER_QUERY,
            {
                "email": user_in.email,
                "password_hash": hashed_pw,
                "first_name": user_in.first_name,
                "last_name": user_in.last_name,
                "full_name": f"{user_in.first_name} {user_in.last_name}".strip(),
                "tenant_id": tenant_id,
                "is_root": is_root,
            },
        )

        user_row = user_result.mappings().first()
        if not user_row:
            raise RuntimeError("Failed to create user")

        new_user_id = user_row["id"]

        if is_root:
            # Assign existing wildcard permission
            await db.execute(
                text("""
                INSERT INTO user_permissions (user_id, permission_id, created_at)
                SELECT :user_id, p.id, NOW()
                FROM permissions p
                WHERE p.code = '*'
                ON CONFLICT DO NOTHING;
            """),
                {"user_id": new_user_id},
            )

        # If we created a tenant, set its owner
        if new_tenant_id is not None:
            await db.execute(
                UPDATE_TENANT_QUERY,
                {
                    "owner_id": new_user_id,
                    "tenant_id": new_tenant_id,
                },
            )

        await db.commit()  # Explicitly commit the transaction

        result: Dict[str, Any] = {
            "user": dict(user_row),
        }

        # Include tenant info only if a tenant was actually created
        if new_tenant_id is not None:
            result["tenant"] = {
                "id": tenant_id,
                "slug": slug,
                "name": name,
            }

        return result

    except IntegrityError as e:
        if "users_email_key" in str(e):
            raise ValueError("Email already registered")
        raise ValueError("Database constraint violation") from e
    except Exception as e:
        await db.rollback()
        raise RuntimeError(f"User creation failed: {str(e)}") from e


async def get_user_by_id_service(user_id: str, db: AsyncSession) -> Dict[str, Any]:
    user_result = await db.execute(READ_USER_QUERY_BY_ID, {"user_id": user_id})
    user_row = user_result.mappings().first()
    if not user_row:
        raise ValueError(f"User not found: {user_id}")

    permissions = await list_user_permissions(db, user_id)

    result: Dict[str, Any] = {
        "user": dict(user_row),
        "permissions": permissions,
    }

    return result


async def get_user_by_email_service(email: str, db: AsyncSession) -> Dict[str, Any]:
    user_result = await db.execute(READ_USER_QUERY_BY_EMAIL, {"email": email})
    user_row = user_result.mappings().first()
    if not user_row:
        raise ValueError(f"User not found: {email}")

    result: Dict[str, Any] = {
        "user": dict(user_row),
    }

    return result


async def get_users_service(
    tenant_id: str,
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
) -> PaginatedResponse:
    offset = (page - 1) * page_size

    # Fetch users
    users_result = await db.execute(
        READ_USERS_QUERY_BY_TENANT_ID,
        {
            "tenant_id": tenant_id,
            "limit": page_size,
            "offset": offset,
        },
    )

    user_rows = users_result.mappings().all()
    users = [UserOut(**row) for row in user_rows]

    # Fetch total count
    count_result = await db.execute(
        COUNT_USERS_QUERY_BY_TENANT_ID,
        {"tenant_id": tenant_id},
    )
    total = count_result.scalar_one()

    return PaginatedResponse[UserOut](
        data=users,
        total=total,
        page=page,
        page_size=page_size,
    )
