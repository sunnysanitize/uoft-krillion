"""Runtime settings, read from the environment once at startup (12-factor)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

DEFAULT_DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/postgres"
DEFAULT_CORS_ORIGINS = "http://localhost:3000"
# Writes prompts, answers, aliases and a one-line explanation per answer.
DEFAULT_GENERATOR_MODEL = "google/gemini-3.6-flash"
# A different model family checks the generator's facts, so they don't share the same blind spots.
DEFAULT_VERIFIER_MODEL = "openai/gpt-5.4-mini"


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    database_url: str = DEFAULT_DATABASE_URL
    cors_origins: list[str] = field(default_factory=lambda: _csv(DEFAULT_CORS_ORIGINS))
    openrouter_api_key: str = field(default="", repr=False)
    generator_model: str = DEFAULT_GENERATOR_MODEL
    verifier_model: str = DEFAULT_VERIFIER_MODEL
    # Local testing only: exposes POST /api/dev/reset so a player can replay today. Never set in production.
    dev_reset: bool = False
    # The review bot (entrypoints/discord_bot.py). Reviewers with the role (or Manage Server) can apply changes.
    discord_bot_token: str = field(default="", repr=False)
    discord_guild_id: int = 0
    discord_review_channel_id: int = 0
    discord_reviewer_role_id: int = 0

    def __repr__(self) -> str:  # never print the database password
        return (
            f"Settings(cors_origins={self.cors_origins}, generator_model={self.generator_model}, "
            f"verifier_model={self.verifier_model})"
        )

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> Settings:
        env = os.environ if env is None else env
        # `or`: an empty value (e.g. a blank line in .env) means "use the default", not "connect to ''".
        return cls(
            database_url=env.get("DATABASE_URL") or DEFAULT_DATABASE_URL,
            cors_origins=_csv(env.get("CORS_ORIGINS") or DEFAULT_CORS_ORIGINS),
            openrouter_api_key=env.get("OPENROUTER_API_KEY", ""),
            generator_model=env.get("GENERATOR_MODEL") or DEFAULT_GENERATOR_MODEL,
            verifier_model=env.get("VERIFIER_MODEL") or DEFAULT_VERIFIER_MODEL,
            dev_reset=env.get("DEV_RESET") == "1",
            discord_bot_token=env.get("DISCORD_BOT_TOKEN", ""),
            discord_guild_id=int(env.get("DISCORD_GUILD_ID") or 0),
            discord_review_channel_id=int(env.get("DISCORD_REVIEW_CHANNEL_ID") or 0),
            discord_reviewer_role_id=int(env.get("DISCORD_REVIEWER_ROLE_ID") or 0),
        )
