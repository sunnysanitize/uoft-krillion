"""Request bodies. The limits here are mirrored by CHECK constraints in the Supabase migration."""

from typing import Annotated

from pydantic import BaseModel, Field

PlayerId = Annotated[str, Field(min_length=8, max_length=64)]


class CheckIn(BaseModel):
    prompt_id: str
    answer: str = Field(max_length=80)


class GuessIn(BaseModel):
    player_id: PlayerId
    prompt_id: str
    answer: str = Field(max_length=80)


class PlayerIn(BaseModel):
    player_id: PlayerId


class PlayerPromptIn(BaseModel):
    player_id: PlayerId
    prompt_id: str


class FinishIn(BaseModel):
    player_id: PlayerId
    nickname: str = Field(min_length=1, max_length=20)
