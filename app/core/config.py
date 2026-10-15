from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Aegis API"
    admin_email: str = "noreply@aegis.com"
    cors_origins_list: list = []
    database_url: str
    debug: bool = False
    log_level: str = "INFO"
    log_format: str = (
        "%(asctime)s - %(funcName)s() - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s"
    )
    log_date_format: str = "%Y-%m-%d %H:%M:%S"
    port: str = "8000"


    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

settings = Settings()