"""Authentication service."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import create_access_token, hash_password, verify_password
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.auth import TokenResponse


def _normalize_login(identifier: str) -> str:
    """Map display names / short usernames to emails when needed."""
    raw = (identifier or "").strip()
    lower = raw.lower()
    aliases = {
        "saurabh": "saurabh@harness.local",
        "admin": "admin@harness.local",
    }
    if "@" in raw:
        return raw
    return aliases.get(lower, raw)


async def authenticate_user(db: AsyncSession, email: str, password: str) -> TokenResponse:
    settings = get_settings()
    # Autofill / paste often adds trailing spaces — strip before lookup
    email = _normalize_login(email)
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


async def _ensure_tenant(db: AsyncSession) -> Tenant:
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
    return tenant


async def _ensure_user(
    db: AsyncSession,
    *,
    tenant: Tenant,
    email: str,
    password: str,
    full_name: str,
    role: str = "admin",
    sync_password: bool = False,
) -> User:
    result = await db.execute(select(User).where(User.email == email))
    existing = result.scalar_one_or_none()
    if existing:
        if sync_password:
            existing.hashed_password = hash_password(password)
            existing.full_name = full_name
            existing.role = role
            existing.is_active = True
            await db.flush()
        return existing
    user = User(
        tenant_id=tenant.id,
        email=email,
        hashed_password=hash_password(password),
        full_name=full_name,
        role=role,
        is_active=True,
    )
    db.add(user)
    await db.flush()
    return user


async def ensure_demo_admin(db: AsyncSession) -> User | None:
    """Create demo tenant + local users when AUTH_DEMO=true."""
    settings = get_settings()
    if not settings.auth_demo:
        return None

    tenant = await _ensure_tenant(db)

    # Primary local login: Saurabh / admin123 (also accepts saurabh@harness.local)
    saurabh = await _ensure_user(
        db,
        tenant=tenant,
        email="saurabh@harness.local",
        password="admin123",
        full_name="Saurabh",
        role="admin",
        sync_password=True,
    )

    # Keep legacy demo admin for scripts that still use it
    await _ensure_user(
        db,
        tenant=tenant,
        email=settings.demo_admin_email,
        password=settings.demo_admin_password,
        full_name="Harness Admin",
        role="admin",
        sync_password=False,
    )

    from app.skills.service import ensure_builtin_skills
    from app.workflows.service import ensure_builtin_workflows

    await ensure_builtin_skills(db, tenant.id)
    await ensure_builtin_workflows(db, tenant.id)
    return saurabh
