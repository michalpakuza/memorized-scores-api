from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ScoreCreate(BaseModel):
    id: str | None = Field(default=None, min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=32)
    score: int = Field(ge=0, le=2_000_000_000)
    player_id: str = Field(alias="playerId", min_length=1, max_length=80)
    session_id: str = Field(alias="sessionId", min_length=1, max_length=80)

    model_config = ConfigDict(populate_by_name=True, extra="ignore")


class ScoreOut(BaseModel):
    id: str
    name: str
    score: int
    created_at: datetime = Field(alias="createdAt")
    player_id: str = Field(alias="playerId")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    

class GameSessionCreate(BaseModel):
    player_id: str = Field(alias="playerId", min_length=1, max_length=80)

    model_config = ConfigDict(populate_by_name=True, extra="ignore")


class GameSessionOut(BaseModel):
    session_id: str = Field(alias="sessionId")
    server_started_at: datetime = Field(alias="serverStartedAt")
    expires_at: datetime = Field(alias="expiresAt")

    model_config = ConfigDict(populate_by_name=True)
