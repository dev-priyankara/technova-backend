from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    DB_HOST: str = "127.0.0.1"
    DB_PORT: int = 3307

    DB_USER: str = "root"
    DB_PASSWORD: str = ""

    DB_NAME: str

    FRONTEND_ORIGIN: str = "http://localhost:3000"
    COOKIE_SECURE: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore"
    )


settings = Settings()