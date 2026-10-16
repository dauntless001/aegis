from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.database import db
from app.core.logging import setup_logging, get_logger
from app.core.exceptions import (
    AppException, ValidationError
)
from app.api.v1.router import api_router as v1_api_router

from app.core.exception_handlers import (
    http_exception_handler,
    app_exception_handler,
    general_exception_handler,
    pydantic_validation_exception_handler,
    validation_exception_handler,
    value_error_handler
)
from contextlib import asynccontextmanager


# setup loggin
setup_logging()
logger = get_logger("main")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events."""
    # Startup
    logger.info("Application Starting...")
    await db.connect()
    try:
        logger.info("Database connection established")
        yield
    finally:
        await db.disconnect()
        logger.info("Database connection closed")


app = FastAPI(
    title="Aegis API",
    description="A lightweight task processing system",
    version="0.1.0",
    lifespan=lifespan,
    debug=settings.debug,
)

# register middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register exceptions here
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(Exception, general_exception_handler)
app.add_exception_handler(ValidationError, pydantic_validation_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(ValueError, value_error_handler)

# Include Routers
app.include_router(v1_api_router, prefix="/api/v1")

@app.get("/", tags=["health"])
async def root():
    """Root endpoint."""
    return {"message": "Aegis API", "version": "0.1.0"}


@app.get("/health", tags=["health"])
async def health_check():
    """Check application and database health"""
    db_status = "disconnected"
    try:
        db_connected = await db.check_connection()
        if db_connected:
            db_status = "connected"
    except Exception:
        logger.exception("Database connection failed")
        pass

    overall_status = (
        "healthy" if db_status == "connected" else "degraded"
    )
    return {
        "status": overall_status,
        "database": db_status, 
        "version": "0.1.0"
    }