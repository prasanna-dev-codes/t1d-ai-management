"""Validated process configuration. No clinical or credential defaults."""

from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="T1D_", extra="forbid", frozen=True, hide_input_in_errors=True
    )

    database_url: SecretStr | None = None
    vision_artifact_dir: Path | None = Field(default=None, repr=False)

    @field_validator("vision_artifact_dir")
    @classmethod
    def vision_root(cls, value: Path | None) -> Path | None:
        if value is not None and not value.is_absolute():
            raise ValueError("Absolute local artifact root required")
        return value

    @field_validator("database_url")
    @classmethod
    def database_boundary(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None:
            try:
                url = make_url(value.get_secret_value())
                if (
                    url.drivername != "postgresql+psycopg"
                    or url.username != "t1d_runtime"
                    or not url.password
                    or url.host not in {"127.0.0.1", "localhost"}
                    or (
                        url.database != "t1d_phase02"
                        and not (url.database or "").startswith("t1d_test_")
                    )
                ):
                    raise ValueError()
            except Exception as exc:
                raise ValueError("Explicit isolated runtime database URL required") from exc
        return value

    environment: Literal["development", "test", "production"] = "development"
    api_host: Literal["127.0.0.1", "localhost", "::1"] = "127.0.0.1"
    api_port: int = Field(default=8001, ge=1024, le=65535)
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"]
    )
    readiness_timeout_seconds: float = Field(default=1.0, gt=0, le=10)

    @field_validator("cors_origins")
    @classmethod
    def validate_origins(cls, origins: list[str]) -> list[str]:
        for origin in origins:
            parsed = urlsplit(origin)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path
                or parsed.query
                or parsed.fragment
                or "*" in origin
            ):
                raise ValueError("CORS origins must be exact HTTP(S) origins without credentials")
            try:
                _ = parsed.port
            except ValueError as exc:
                raise ValueError("Invalid origin port") from exc
        return origins

    @model_validator(mode="after")
    def restrict_local_defaults(self) -> "Settings":
        if self.environment == "production":
            # No production identity, exposure, or deployment design has been approved.
            raise ValueError("Production operation is not supported by this research foundation")
        if any(
            urlsplit(o).hostname not in {"localhost", "127.0.0.1", "::1"} for o in self.cors_origins
        ):
            raise ValueError("Only loopback frontend origins are supported in Phase 01")
        return self
