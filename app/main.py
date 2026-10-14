from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events."""
    # Startup
    yield

    # Shutdown


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


# Include Routers


@app.get("/", tags=["health"])
async def root():
    """Root endpoint."""
    return {"message": "Aegis API", "version": "0.1.0"}