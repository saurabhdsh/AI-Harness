"""FastAPI application entrypoint."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import api_router
from app.core.config import get_settings
from app.db.session import AsyncSessionLocal, init_db
from app.services.auth import ensure_demo_admin


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if settings.auto_create_tables:
        try:
            await init_db()
        except Exception as exc:
            # Surface clearly — do not pretend DB is ready
            print(f"[control-plane] auto_create_tables failed: {exc}")
            raise

    if settings.auth_demo:
        async with AsyncSessionLocal() as session:
            try:
                await ensure_demo_admin(session)
                await session.commit()
            except Exception as exc:
                await session.rollback()
                print(f"[control-plane] demo admin seed failed: {exc}")
                raise
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()
