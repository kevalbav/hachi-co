from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str
    API_KEY: str = "dev-key"
    API_KEY_HEADER: str = "x-api-key"

    class Config:
        env_file = ".env"

settings = Settings()