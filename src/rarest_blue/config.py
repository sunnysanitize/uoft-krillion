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
# Rules on rejected guesses live. Smaller models rejected obvious answers ("coffee", "Red Bull"), so this one is bigger.
DEFAULT_JUDGE_MODEL = "anthropic/claude-sonnet-5.5"


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    database_url: str = DEFAULT_DATABASE_URL
    cors_origins: list[str] = field(default_factory=lambda: _csv(DEFAULT_CORS_ORIGINS))
    openrouter_api_key: str = field(default="", repr=False)
    generator_model: str = DEFAULT_GENERATOR_MODEL
    verifier_model: str = DEFAULT_VERIFIER_MODEL
    judge_model: str = DEFAULT_JUDGE_MODEL
    # Local testing only: exposes POST /api/dev/reset so a player can replay today. Never set in production.
    dev_reset: bool = False

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
            judge_model=env.get("JUDGE_MODEL") or DEFAULT_JUDGE_MODEL,
            dev_reset=env.get("DEV_RESET") == "1",
        )
