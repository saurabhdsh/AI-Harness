"""Authentication service."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import create_access_token, hash_password, verify_password
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.auth import TokenResponse


async def authenticate_user(db: AsyncSession, email: str, password: str) -> TokenResponse:
    settings = get_settings()
    # Autofill / paste often adds trailing spaces — strip before lookup
    email = (email or "").strip()
    password = password or ""
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user is None and settings.auth_demo and email == settings.demo_admin_email:
        raise PermissionError(
            "Demo admin user not seeded. Run seed script or enable auto-seed on startup."
        )

    if user is None or not verify_password(password, user.hashed_password):
        raise PermissionError("Invalid email or password")

    if not user.is_active:
        raise PermissionError("User is inactive")

    token = create_access_token(
        subject=user.email,
        tenant_id=user.tenant_id,
        user_id=user.id,
        extra={"role": user.role},
    )
    return TokenResponse(
        access_token=token,
        tenant_id=str(user.tenant_id),
        user_id=str(user.id),
        email=user.email,
    )


async def ensure_demo_admin(db: AsyncSession) -> User | None:
    """Create demo tenant + admin when AUTH_DEMO=true and missing."""
    settings = get_settings()
    if not settings.auth_demo:
        return None

    result = await db.execute(select(User).where(User.email == settings.demo_admin_email))
    existing = result.scalar_one_or_none()
    if existing:
        return existing

    tenant_result = await db.execute(select(Tenant).where(Tenant.slug == "demo"))
    tenant = tenant_result.scalar_one_or_none()
    if tenant is None:
        tenant = Tenant(
            name="Demo Tenant",
            slug="demo",
            description="Auto-seeded demo tenant for local development",
        )
        db.add(tenant)
        await db.flush()

    user = User(
        tenant_id=tenant.id,
        email=settings.demo_admin_email,
        hashed_password=hash_password(settings.demo_admin_password),
        full_name="Harness Admin",
        role="admin",
        is_active=True,
    )
    db.add(user)
    await db.flush()

    from app.skills.service import ensure_builtin_skills

    await ensure_builtin_skills(db, tenant.id)
    return user
