from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    api_key: str
    database_url: str = "sqlite:///./scores.db"
    leaderboard_tz: str = "Europe/Warsaw"
    allowed_origins: str = "*"
    game_session_ttl_seconds: int
    min_seconds_per_score: float
    max_score: int
    player_save_limit: int
    player_save_window_seconds: int

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def cors_origins(self) -> list[str]:
        if self.allowed_origins.strip() == "*":
            return ["*"]
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]


settings = Settings()
