from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Aegis API"
    admin_email: str = "noreply@aegis.com"
    debug: bool = False
    port: str = "8000"
    cors_origins_list: list = []

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

settings = Settings()