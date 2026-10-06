"""Request and response models used to generate the auth OpenAPI document."""

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    error: str = Field(description="Human-readable error message.")


class RegisterBody(BaseModel):
    username: str = Field(description="Unique account username.")
    password: str = Field(min_length=8, description="Password, at least 8 characters.")
    email: str | None = Field(default=None, description="Optional account email.")


class LoginBody(BaseModel):
    email: str = Field(description="Email address associated with the account.")
    password: str = Field(description="Account password.")
    device_name: str | None = Field(default=None, description="Optional name for this login session.")


class ChangePasswordBody(BaseModel):
    current_password: str | None = Field(default=None, description="Required for accounts with a password.")
    new_password: str = Field(min_length=8, description="New password, at least 8 characters.")
    device_name: str | None = Field(default=None, description="Optional name for the replacement session.")


class AuthCodeBody(BaseModel):
    auth_code: str = Field(description="One-time code received from the Discord redirect.")


class DiscordCallbackQuery(BaseModel):
    code: str | None = Field(default=None, description="Authorization code returned by Discord.")
    state: str | None = Field(default=None, description="OAuth state value used for CSRF protection.")
    error: str | None = Field(default=None, description="OAuth error returned by Discord, if any.")


class SessionPath(BaseModel):
    session_id: str = Field(description="ID of the session to revoke.")


class KeyPath(BaseModel):
    key_id: int = Field(description="ID of the API key to update or revoke.")


class KeyCreateBody(BaseModel):
    name: str = Field(max_length=128, description="Name used to identify this key.")
    scope: list[str] | None = Field(
        default=None,
        description="Optional permission-key allowlist; null grants the user's full permissions.",
    )
    expires_at: str | None = Field(
        default=None,
        description="Optional ISO 8601 expiration timestamp; null means no expiration.",
    )


class KeyUpdateBody(BaseModel):
    name: str | None = Field(default=None, max_length=128, description="Replacement key name.")
    scope: list[str] | None = Field(
        default=None,
        description="Replacement permission-key allowlist; null restores full user permissions.",
    )


class RegisterResponse(BaseModel):
    success: bool
    message: str


class LoginResponse(BaseModel):
    token: str = Field(description="Short-lived bearer session token.")
    session_id: str = Field(description="ID of the created login session.")


class TokenResponse(BaseModel):
    token: str = Field(description="Short-lived bearer session token.")


class ChangePasswordResponse(BaseModel):
    success: bool
    message: str
    token: str = Field(description="Replacement short-lived bearer session token.")


class LogoutResponse(BaseModel):
    success: bool
    message: str


class LogoutAllResponse(BaseModel):
    success: bool
    sessions_revoked: int


class SessionItem(BaseModel):
    id: str
    created_at: str | None
    last_used_at: str | None
    expires_at: str | None
    ip_address: str | None
    device_name: str | None
    is_current: bool


class SessionsResponse(BaseModel):
    sessions: list[SessionItem]


class SuccessResponse(BaseModel):
    success: bool


class KeyItem(BaseModel):
    id: int
    key_prefix: str = Field(description="Non-secret key prefix for identifying the key.")
    name: str
    created_at: str | None
    last_used_at: str | None
    expires_at: str | None
    scope: list[str] | None


class KeysResponse(BaseModel):
    keys: list[KeyItem]


class KeyCreateResponse(BaseModel):
    id: int
    key: str = Field(description="Raw API key; returned only once.")
    name: str
    scope: list[str] | None
    message: str


class DiscordExchangeResponse(BaseModel):
    token: str = Field(description="Short-lived bearer session token.")
