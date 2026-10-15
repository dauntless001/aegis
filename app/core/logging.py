import logging, sys
from app.core.config import settings


def setup_logging() -> None:
    """Configure application logging."""
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    # Build handlers list
    handlers: list[logging.Handler] = [
        logging.StreamHandler(sys.stdout),
    ]

    # Add Slack handler if alerts are enabled
    # if settings.slack_alert and settings.slack_webhook_url:
    #     pass

    # Configure root logger
    logging.basicConfig(
        level=log_level,
        format=settings.log_format,
        datefmt=settings.log_date_format,
        handlers=handlers,
    )

    # Set log levels for third-party libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)
    logging.getLogger("motor").setLevel(logging.WARNING)
    logging.getLogger("pymongo").setLevel(logging.WARNING)

    # Get application logger
    logger = logging.getLogger("luoma")
    logger.setLevel(log_level)

    if settings.debug:
        logger.debug("Debug mode enabled")


def get_logger(name: str | None = None) -> logging.Logger:
    """Get a logger instance for the given name."""
    if name:
        return logging.getLogger(f"aegis.{name}")
    return logging.getLogger("aegis")
