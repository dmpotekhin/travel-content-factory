"""Travel Content Factory — FastAPI application."""

import os
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from database import engine
from models import Base
from routers import media, projects, ai, music

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown."""
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables ready")

    # Ensure directories
    for d in [os.getenv("MEDIA_ROOT", "./uploads"),
              os.getenv("EXPORT_ROOT", "./exports"),
              "./data"]:
        Path(d).mkdir(parents=True, exist_ok=True)

    yield

    # Shutdown
    from services.deepseek import _ai_client
    if _ai_client:
        await _ai_client.close()
    await engine.dispose()
    logger.info("Shutdown complete")


app = FastAPI(
    title="Travel Content Factory",
    description="Local media archive & content creation tool for TikTok/Reels/Facebook",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS for local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
app.include_router(media.router)
app.include_router(projects.router)
app.include_router(ai.router)
app.include_router(music.router)

# Health check — must be before static mount
@app.get("/api/health")
async def health():
    return {"status": "ok", "app": "Travel Content Factory"}

# Static frontend
frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.isdir(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
