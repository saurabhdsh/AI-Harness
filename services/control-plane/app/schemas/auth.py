"""Auth schemas."""

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    # Plain str — demo emails like admin@harness.local are rejected by EmailStr
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    tenant_id: str
    user_id: str
    email: str
