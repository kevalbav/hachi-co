from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # existing fields
    api_key: str = "dev-key"
    database_url: str = "sqlite:///app.db"

    # OAuth (optional for dev)
    google_client_id: str | None = None
    google_client_secret: str | None = None
    oauth_redirect_base: str | None = "http://localhost:8000"
    
    # Instagram OAuth
    instagram_client_id: str | None = None
    instagram_client_secret: str | None = None
    frontend_url: str = "http://localhost:3000"

    # load .env, ignore unknown keys so new vars don't break boot
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- Back-compat so old code using UPPERCASE keeps working ----
    @property
    def API_KEY(self) -> str:
        return self.api_key

    @property
    def DATABASE_URL(self) -> str:
        return self.database_url
    
    @property
    def INSTAGRAM_CLIENT_ID(self) -> str | None:
        return self.instagram_client_id
    
    @property
    def INSTAGRAM_CLIENT_SECRET(self) -> str | None:
        return self.instagram_client_secret
    
    @property
    def OAUTH_REDIRECT_BASE(self) -> str | None:
        return self.oauth_redirect_base
    
    @property
    def FRONTEND_URL(self) -> str:
        return self.frontend_url

settings = Settings()