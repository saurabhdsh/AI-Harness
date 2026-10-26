"""Authentication endpoints."""

from fastapi import APIRouter, HTTPException, status

from app.core.deps import DbSession
from app.schemas.auth import LoginRequest, TokenResponse
from app.services import auth as auth_service

router = APIRouter()


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: DbSession) -> TokenResponse:
    try:
        return await auth_service.authenticate_user(db, body.email, body.password)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
