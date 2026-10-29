"""Async SQLAlchemy engine and session factory."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def _ensure_sqlite_columns(sync_conn) -> None:
    """Add columns create_all skips on existing SQLite tables (local demo DBs)."""
    from sqlalchemy import text

    dialect = sync_conn.dialect.name
    if dialect != "sqlite":
        return

    def cols(table: str) -> set[str]:
        rows = sync_conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
        return {r[1] for r in rows}

    alters: list[tuple[str, str, str]] = [
        ("platform_connections", "last_synced_at", "DATETIME"),
        ("platform_connections", "last_sync_status", "VARCHAR(64)"),
        ("platform_connections", "last_sync_error", "TEXT"),
        ("platform_connections", "synced_agent_count", "INTEGER NOT NULL DEFAULT 0"),
        ("agents", "blueprint_id", "CHAR(32)"),
        ("platform_connections", "collect_observability", "BOOLEAN NOT NULL DEFAULT 1"),
    ]
    for table, col, decl in alters:
        existing = cols(table)
        if not existing or col in existing:
            continue
        sync_conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {decl}"))

    # Best-effort unique identity key (skip if duplicates already exist)
    try:
        sync_conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_agents_tenant_external_id "
                "ON agents (tenant_id, external_id)"
            )
        )
    except Exception:  # noqa: BLE001
        pass
    try:
        sync_conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_agents_blueprint_id ON agents (blueprint_id)")
        )
    except Exception:  # noqa: BLE001
        pass


async def init_db() -> None:
    """Fallback create_all for demo environments when migrations are not applied."""
    from app.db.base import Base
    import app.models  # noqa: F401 — register models

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_ensure_sqlite_columns)
