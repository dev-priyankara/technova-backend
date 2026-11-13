from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    DB_HOST: str = "127.0.0.1"
    DB_PORT: int = 3307

    DB_USER: str = "root"
    DB_PASSWORD: str = ""

    DB_NAME: str

    FRONTEND_ORIGIN: str = "http://localhost:3000"
    COOKIE_SECURE: bool = False
    # Local development only. When true and no email provider is configured,
    # password reset codes are written to the server log instead of being
    # emailed. Codes are still hashed in the database, so this does not weaken
    # stored data. Never enable it on a shared or public deployment.
    EMAIL_DEV_MODE: bool = False
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USERNAME: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_FROM_EMAIL: str | None = None
    SMTP_USE_TLS: bool = True
    SMTP_USE_SSL: bool = False
    EMAILJS_SERVICE_ID: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "EMAILJS_SERVICE_ID", "NEXT_PUBLIC_EMAILJS_SERVICE_ID"
        ),
    )
    EMAILJS_TEMPLATE_ID: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "EMAILJS_TEMPLATE_ID", "NEXT_PUBLIC_EMAILJS_TEMPLATE_ID"
        ),
    )
    EMAILJS_PUBLIC_KEY: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "EMAILJS_PUBLIC_KEY", "NEXT_PUBLIC_EMAILJS_PUBLIC_KEY"
        ),
    )

    model_config = SettingsConfigDict(
        env_file=(".env", "../frontend/.env.local"),
        extra="ignore",
    )


settings = Settings()