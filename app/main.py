from datetime import datetime, time, timezone, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import Base, engine, get_db
from app.models import GameSession, Score
from app.schemas import GameSessionCreate, GameSessionOut, ScoreCreate, ScoreOut
from app.security import require_api_key, simple_rate_limit

Base.metadata.create_all(bind=engine)

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
    )
    db.add(score)
    db.commit()
    db.refresh(score)
    return score

def _validate_score(payload: ScoreCreate, now: datetime, db: Session) -> None:
    if payload.score > settings.max_score:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Score is above the allowed maximum",
        )

    player_id = payload.player_id.strip()
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
