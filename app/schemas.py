from typing import Annotated
from datetime import datetime
import re
from pydantic import BaseModel, ConfigDict, Field, field_validator


GROUP_CODE_PATTERN = re.compile(r"^[A-Z0-9-]{3,16}$")

class ScoreCreate(BaseModel):
    id: str | None = Field(default=None, min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=32)
    score: int = Field(ge=0, le=2_000_000_000)
    player_id: Annotated[str, Field(alias="playerId", min_length=1, max_length=80)]
    session_id: Annotated[str, Field(alias="sessionId", min_length=1, max_length=80)]
    group_code: Annotated[str | None, Field(default=None, alias="groupCode", min_length=3, max_length=16)]
    
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    @field_validator("group_code")
    @classmethod
    def validate_group_code(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None

        normalized = value.strip().upper()
        if not GROUP_CODE_PATTERN.match(normalized):
            raise ValueError("Group code must contain only A-Z, 0-9 or '-'")
        return normalized


class ScoreOut(BaseModel):
    id: str
    name: str
    score: int
    created_at: Annotated[datetime, Field(alias="createdAt")]
    player_id: Annotated[str, Field(alias="playerId")]
    group_code: Annotated[str | None, Field(default=None, alias="groupCode")]
    
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class GameSessionCreate(BaseModel):
    player_id: Annotated[str, Field(alias="playerId", min_length=1, max_length=80)]
    
    model_config = ConfigDict(populate_by_name=True, extra="ignore")


class GameSessionOut(BaseModel):
    session_id: Annotated[str, Field(alias="sessionId")]
    server_started_at: Annotated[datetime, Field(alias="serverStartedAt")]
    expires_at: Annotated[datetime, Field(alias="expiresAt")]
    
    model_config = ConfigDict(populate_by_name=True)


class GroupJoin(BaseModel):
    player_id: str = Field(alias="playerId", min_length=1, max_length=80)
    group_code: str = Field(alias="groupCode", min_length=3, max_length=16)

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    @field_validator("group_code")
    @classmethod
    def validate_group_code(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not GROUP_CODE_PATTERN.match(normalized):
            raise ValueError("Group code must contain only A-Z, 0-9 or '-'")
        return normalized


class GroupLeave(BaseModel):
    player_id: str = Field(alias="playerId", min_length=1, max_length=80)

    model_config = ConfigDict(populate_by_name=True, extra="ignore")


class PlayerGroupOut(BaseModel):
    player_id: str = Field(alias="playerId")
    group_code: str | None = Field(alias="groupCode")

    model_config = ConfigDict(populate_by_name=True)
