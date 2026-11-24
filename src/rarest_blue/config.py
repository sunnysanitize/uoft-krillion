"""Runtime settings, read from the environment once at startup (12-factor)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

DEFAULT_DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/postgres"
DEFAULT_CORS_ORIGINS = "http://localhost:3000"
# Tried in order, one per attempt. Free models are rate-limited and come and go, so list a few.
DEFAULT_MODELS = "particle-ai/particle-1:free,nvidia/nemotron-3.5-super-vl:free,openrouter/free"


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    database_url: str = DEFAULT_DATABASE_URL
    cors_origins: list[str] = field(default_factory=lambda: _csv(DEFAULT_CORS_ORIGINS))
    openrouter_api_key: str = field(default="", repr=False)
    openrouter_models: list[str] = field(default_factory=lambda: _csv(DEFAULT_MODELS))
    # Local testing only: exposes POST /api/dev/reset so a player can replay today. Never set in production.
    dev_reset: bool = False

    def __repr__(self) -> str:  # never print the database password
        return f"Settings(cors_origins={self.cors_origins}, openrouter_models={self.openrouter_models})"

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> Settings:
        env = os.environ if env is None else env
        # `or`: an empty value (e.g. a blank line in .env) means "use the default", not "connect to ''".
        return cls(
            database_url=env.get("DATABASE_URL") or DEFAULT_DATABASE_URL,
            cors_origins=_csv(env.get("CORS_ORIGINS") or DEFAULT_CORS_ORIGINS),
            openrouter_api_key=env.get("OPENROUTER_API_KEY", ""),
            openrouter_models=_csv(env.get("OPENROUTER_MODELS") or DEFAULT_MODELS),
            dev_reset=env.get("DEV_RESET") == "1",
        )
