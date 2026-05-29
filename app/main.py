from datetime import datetime, time, timezone, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, inspect, select, text, update
from sqlalchemy.orm import Session

from app.config import settings
from app.database import Base, engine, get_db
from app.models import GameSession, PlayerGroup, PlayerGroupChange, Score
from app.schemas import (
    GameSessionCreate,
    GameSessionOut,
    GroupJoin,
    GroupLeave,
    PlayerGroupOut,
    ScoreCreate,
    ScoreOut,
)
from app.security import require_api_key, simple_rate_limit

Base.metadata.create_all(bind=engine)

def ensure_schema() -> None:
    inspector = inspect(engine)
    if "scores" not in inspector.get_table_names():
        return

    score_columns = {column["name"] for column in inspector.get_columns("scores")}
    if "group_code" not in score_columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE scores ADD COLUMN group_code VARCHAR(16) NULL"))
            connection.execute(text("CREATE INDEX ix_scores_group_code ON scores (group_code)"))


ensure_schema()

app = FastAPI(
    title="Game Scores API",
    version="0.1.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["X-API-Key", "Content-Type"],
)


def protect(request: Request) -> None:
    simple_rate_limit(request)
    require_api_key(request.headers.get("X-API-Key"))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post(
    "/game-sessions/start",
    response_model=GameSessionOut,
    dependencies=[Depends(protect)],
)
def start_game_session(
    payload: GameSessionCreate,
    db: Session = Depends(get_db),
) -> GameSessionOut:
    now = datetime.now(timezone.utc)
    session = GameSession(
        id=str(uuid4()),
        player_id=payload.player_id.strip(),
        created_at=now,
        expires_at=now + timedelta(seconds=settings.game_session_ttl_seconds),
        used_at=None,
    )
    db.add(session)
    db.commit()

    return GameSessionOut(
        sessionId=session.id,
        serverStartedAt=session.created_at,
        expiresAt=session.expires_at,
    )



@app.post("/scores", response_model=ScoreOut, dependencies=[Depends(protect)])
def create_score(payload: ScoreCreate, db: Session = Depends(get_db)) -> Score:
    score_id = payload.id or str(uuid4())
    existing_score = db.get(Score, score_id)
    if existing_score:
        return existing_score

    now = datetime.now(timezone.utc)
    _validate_score(payload=payload, now=now, db=db)

    score = Score(
        id=score_id,
        name=payload.name.strip(),
        score=payload.score,
        created_at=now,
        player_id=payload.player_id.strip(),
        group_code=payload.group_code,
    )
    db.add(score)
    db.commit()
    db.refresh(score)
    return score

@app.post(
    "/groups/join",
    response_model=PlayerGroupOut,
    dependencies=[Depends(protect)],
)
def join_group(payload: GroupJoin, db: Session = Depends(get_db)) -> PlayerGroupOut:
    now = datetime.now(timezone.utc)
    player_id = payload.player_id.strip()
    group_code = payload.group_code
    membership = db.get(PlayerGroup, player_id)

    if membership and membership.group_code == group_code:
        return PlayerGroupOut(playerId=player_id, groupCode=group_code)

    _validate_group_change_limit(player_id=player_id, now=now, db=db)

    old_group_code = membership.group_code if membership else None
    if old_group_code:
        _remove_player_group_scores(
            player_id=player_id,
            group_code=old_group_code,
            db=db,
        )

    if membership:
        membership.group_code = group_code
        membership.updated_at = now
    else:
        membership = PlayerGroup(
            player_id=player_id,
            group_code=group_code,
            created_at=now,
            updated_at=now,
        )
        db.add(membership)

    _add_group_change(
        player_id=player_id,
        old_group_code=old_group_code,
        new_group_code=group_code,
        now=now,
        db=db,
    )
    db.commit()
    return PlayerGroupOut(playerId=player_id, groupCode=group_code)


@app.post(
    "/groups/leave",
    response_model=PlayerGroupOut,
    dependencies=[Depends(protect)],
)
def leave_group(payload: GroupLeave, db: Session = Depends(get_db)) -> PlayerGroupOut:
    now = datetime.now(timezone.utc)
    player_id = payload.player_id.strip()
    membership = db.get(PlayerGroup, player_id)

    if not membership or not membership.group_code:
        return PlayerGroupOut(playerId=player_id, groupCode=None)

    old_group_code = membership.group_code
    _remove_player_group_scores(
        player_id=player_id,
        group_code=old_group_code,
        db=db,
    )
    membership.group_code = None
    membership.updated_at = now
    _add_group_change(
        player_id=player_id,
        old_group_code=old_group_code,
        new_group_code=None,
        now=now,
        db=db,
    )
    db.commit()
    return PlayerGroupOut(playerId=player_id, groupCode=None)


@app.get(
    "/groups/current/{player_id}",
    response_model=PlayerGroupOut,
    dependencies=[Depends(protect)],
)
def get_current_group(player_id: str, db: Session = Depends(get_db)) -> PlayerGroupOut:
    membership = db.get(PlayerGroup, player_id.strip())
    return PlayerGroupOut(
        playerId=player_id.strip(),
        groupCode=membership.group_code if membership else None,
    )

def _validate_score(payload: ScoreCreate, now: datetime, db: Session) -> None:
    if payload.score > settings.max_score:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Score is above the allowed maximum",
        )

    player_id = payload.player_id.strip()
    if payload.group_code is not None:
        membership = db.get(PlayerGroup, player_id)
        if not membership or membership.group_code != payload.group_code:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Player is not in this group",
            )
    window_start = now - timedelta(seconds=settings.player_save_window_seconds)
    recent_scores = db.scalar(
        select(func.count())
        .select_from(Score)
        .where(Score.player_id == player_id, Score.created_at >= window_start)
    )

    if recent_scores is not None and recent_scores >= settings.player_save_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many scores saved for this player",
        )

    session = db.get(GameSession, payload.session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid game session",
        )

    if session.player_id != player_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Game session does not belong to this player",
        )

    if session.used_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Game session has already been used",
        )

    if _as_utc(session.expires_at) < now:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Game session has expired",
        )

    duration_seconds = (now - _as_utc(session.created_at)).total_seconds()
    minimum_seconds = payload.score * settings.min_seconds_per_score
    if duration_seconds < minimum_seconds:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Score was submitted too quickly",
        )

    session.used_at = now

def _validate_group_change_limit(player_id: str, now: datetime, db: Session) -> None:
    window_start = now - timedelta(seconds=settings.group_change_window_seconds)
    changes = db.scalar(
        select(func.count())
        .select_from(PlayerGroupChange)
        .where(
            PlayerGroupChange.player_id == player_id,
            PlayerGroupChange.created_at >= window_start,
        )
    )

    if changes is not None and changes >= settings.group_change_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many group changes for this player",
        )


def _remove_player_group_scores(player_id: str, group_code: str, db: Session) -> None:
    db.execute(
        update(Score)
        .where(
            Score.player_id == player_id,
            Score.group_code == group_code,
        )
        .values(group_code=None)
    )


def _add_group_change(
    player_id: str,
    old_group_code: str | None,
    new_group_code: str | None,
    now: datetime,
    db: Session,
) -> None:
    db.add(
        PlayerGroupChange(
            id=str(uuid4()),
            player_id=player_id,
            old_group_code=old_group_code,
            new_group_code=new_group_code,
            created_at=now,
        )
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


@app.get(
    "/scores/today", response_model=list[ScoreOut], dependencies=[Depends(protect)]
)
def get_today_scores(
    db: Session = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100),
) -> list[Score]:
    tz = ZoneInfo(settings.leaderboard_tz)
    today_local = datetime.now(tz).date()
    start_local = datetime.combine(today_local, time.min, tzinfo=tz)
    end_local = datetime.combine(today_local, time.max, tzinfo=tz)
    start_utc = start_local.astimezone(timezone.utc)
    end_utc = end_local.astimezone(timezone.utc)

    statement = (
        select(Score)
        .where(Score.created_at >= start_utc, Score.created_at <= end_utc)
        .order_by(Score.score.desc(), Score.created_at.asc())
        .limit(limit)
    )
    return list(db.scalars(statement))


@app.get(
    "/scores/groups/{group_code}/today",
    response_model=list[ScoreOut],
    dependencies=[Depends(protect)],
)
def get_group_today_scores(
    group_code: str,
    db: Session = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100),
) -> list[Score]:
    normalized_group_code = _normalize_group_code(group_code)
    tz = ZoneInfo(settings.leaderboard_tz)
    today_local = datetime.now(tz).date()
    start_local = datetime.combine(today_local, time.min, tzinfo=tz)
    end_local = datetime.combine(today_local, time.max, tzinfo=tz)
    start_utc = start_local.astimezone(timezone.utc)
    end_utc = end_local.astimezone(timezone.utc)

    statement = (
        select(Score)
        .where(
            Score.group_code == normalized_group_code,
            Score.created_at >= start_utc,
            Score.created_at <= end_utc,
        )
        .order_by(Score.score.desc(), Score.created_at.asc())
        .limit(limit)
    )
    return list(db.scalars(statement))


@app.get(
    "/scores/groups/{group_code}/all-time",
    response_model=list[ScoreOut],
    dependencies=[Depends(protect)],
)
def get_group_all_time_scores(
    group_code: str,
    db: Session = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100),
) -> list[Score]:
    normalized_group_code = _normalize_group_code(group_code)
    statement = (
        select(Score)
        .where(Score.group_code == normalized_group_code)
        .order_by(Score.score.desc(), Score.created_at.asc())
        .limit(limit)
    )
    return list(db.scalars(statement))


def _normalize_group_code(group_code: str) -> str:
    normalized = group_code.strip().upper()
    if len(normalized) < 3 or len(normalized) > 16:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid group code",
        )

    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-")
    if any(character not in allowed for character in normalized):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid group code",
        )

    return normalized


@app.get(
    "/scores/all-time", response_model=list[ScoreOut], dependencies=[Depends(protect)]
)
def get_all_time_scores(
    db: Session = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100),
) -> list[Score]:
    statement = (
        select(Score).order_by(Score.score.desc(), Score.created_at.asc()).limit(limit)
    )
    return list(db.scalars(statement))
