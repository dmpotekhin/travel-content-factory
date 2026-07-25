"""Image generation routes — Abacus AI."""

import os
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from services.abacus import get_image_client, GENERATED_DIR
from database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/images", tags=["images"])


@router.post("/generate")
async def generate_image(data: dict):
    """Generate an image from a prompt."""
    prompt = data.get("prompt", "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt is required")

    aspect_ratio = data.get("aspect_ratio", "square")
    if aspect_ratio not in ("square", "landscape", "portrait"):
        raise HTTPException(status_code=400, detail=f"Invalid aspect_ratio: {aspect_ratio}")

    model = data.get("model")

    client = get_image_client()
    if not client.api_key:
        raise HTTPException(status_code=503, detail="ABACUS_AI_API_KEY not configured")

    try:
        result = await client.generate(prompt, aspect_ratio=aspect_ratio, model=model)
    except RuntimeError as e:
        logger.error(f"Image generation failed: {e}")
        raise HTTPException(status_code=502, detail=str(e))

    return {
        "path": result.file_path,
        "url": f"/api/images/file/{os.path.basename(result.file_path)}",
        "prompt": result.prompt,
        "model": result.model,
        "width": result.width,
        "height": result.height,
        "size_bytes": result.size_bytes,
    }


@router.get("/list")
async def list_images(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List generated images from the generated/ directory."""
    if not GENERATED_DIR.exists():
        return {"images": [], "total": 0, "page": page, "page_size": page_size}

    files = sorted(
        GENERATED_DIR.glob("*"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    files = [f for f in files if f.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")]

    total = len(files)
    start = (page - 1) * page_size
    page_files = files[start:start + page_size]

    images = []
    for f in page_files:
        stat = f.stat()
        # Try to extract model from filename: YYYYMMDD_HHMMSS_<model>_<hash>.ext
        parts = f.stem.split("_", 2)
        model = parts[1] if len(parts) >= 2 else "unknown"
        images.append({
            "filename": f.name,
            "url": f"/api/images/file/{f.name}",
            "model": model,
            "size_bytes": stat.st_size,
            "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        })

    return {
        "images": images,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/file/{filename}")
async def serve_image(filename: str):
    """Serve a generated image file."""
    file_path = GENERATED_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(str(file_path))


@router.post("/generate-cover")
async def generate_cover(data: dict, db=Depends(get_db)):
    """Generate a cover image for a project."""
    from sqlalchemy import select
    from models import Project

    project_id = data.get("project_id")
    prompt_override = data.get("prompt_override", "").strip()

    if not project_id:
        raise HTTPException(status_code=400, detail="project_id is required")

    # Build prompt from project info
    prompt = prompt_override
    if not prompt:
        q = select(Project).where(Project.id == project_id)
        result = await db.execute(q)
        project = result.scalar_one_or_none()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        platform = project.platform or "social media"
        name = project.name or "travel"
        prompt = f"Eye-catching thumbnail for a {platform} video titled '{name}'. Travel theme, vibrant colors, cinematic style, 16:9 composition."

    client = get_image_client()
    if not client.api_key:
        raise HTTPException(status_code=503, detail="ABACUS_AI_API_KEY not configured")

    try:
        result = await client.generate(prompt, aspect_ratio="landscape")
    except RuntimeError as e:
        logger.error(f"Cover generation failed: {e}")
        raise HTTPException(status_code=502, detail=str(e))

    return {
        "path": result.file_path,
        "url": f"/api/images/file/{os.path.basename(result.file_path)}",
        "prompt": result.prompt,
        "model": result.model,
        "width": result.width,
        "height": result.height,
        "size_bytes": result.size_bytes,
    }
