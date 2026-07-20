"""Media routes — scan, list, delete, thumbnail."""

import os
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete as sa_delete

from database import get_db
from models import MediaFile, MediaType
from services.scanner import scan_directory

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/media", tags=["media"])

MEDIA_ROOT = os.getenv("MEDIA_ROOT", "./uploads")


@router.post("/scan")
async def scan_folder(path: str, db: AsyncSession = Depends(get_db)):
    """Scan a folder for media files and import metadata."""
    if not os.path.isdir(path):
        raise HTTPException(status_code=400, detail=f"Not a directory: {path}")

    results = await scan_directory(path, MEDIA_ROOT)
    if not results:
        return {"imported": 0, "message": "No media files found"}

    imported = 0
    skipped = 0

    for meta in results:
        # Check for duplicate by original_path
        existing = await db.execute(
            select(MediaFile).where(MediaFile.original_path == meta["original_path"])
        )
        if existing.scalar_one_or_none():
            skipped += 1
            continue

        mf = MediaFile(
            filename=meta["filename"],
            original_path=meta["original_path"],
            stored_path=os.path.join(MEDIA_ROOT, meta["stored_name"]),
            media_type=MediaType(meta["media_type"]),
            duration=meta["duration"],
            width=meta["width"],
            height=meta["height"],
            size_bytes=meta["size_bytes"],
            date_taken=meta["date_taken"],
            latitude=meta["latitude"],
            longitude=meta["longitude"],
            country=meta.get("country"),
            city=meta.get("city"),
        )
        db.add(mf)
        imported += 1

    await db.commit()
    return {"imported": imported, "skipped": skipped, "total": len(results)}


@router.get("/list")
async def list_media(
    media_type: str = Query(None, description="photo or video"),
    country: str = Query(None),
    year: int = Query(None),
    hashtag: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """List media files with optional filters."""
    q = select(MediaFile)

    if media_type:
        q = q.where(MediaFile.media_type == MediaType(media_type))
    if country:
        q = q.where(MediaFile.country == country)
    if year:
        q = q.where(func.strftime("%Y", MediaFile.date_taken) == str(year))
    if hashtag:
        # SQLite JSON search
        q = q.where(MediaFile.hashtags.contains(hashtag))

    # Count total
    count_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    # Paginate
    offset = (page - 1) * page_size
    q = q.order_by(MediaFile.date_taken.desc().nullslast(), MediaFile.created_at.desc())
    q = q.offset(offset).limit(page_size)

    result = await db.execute(q)
    items = result.scalars().all()

    return {
        "items": [
            {
                "id": m.id,
                "filename": m.filename,
                "media_type": m.media_type.value if m.media_type else None,
                "duration": m.duration,
                "width": m.width,
                "height": m.height,
                "size_bytes": m.size_bytes,
                "date_taken": m.date_taken.isoformat() if m.date_taken else None,
                "latitude": m.latitude,
                "longitude": m.longitude,
                "country": m.country,
                "city": m.city,
                "hashtags": m.hashtags or [],
            }
            for m in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/countries")
async def list_countries(db: AsyncSession = Depends(get_db)):
    """Get distinct countries from media."""
    q = select(MediaFile.country).where(MediaFile.country.isnot(None)).distinct()
    result = await db.execute(q)
    return [r[0] for r in result.all() if r[0]]


@router.get("/years")
async def list_years(db: AsyncSession = Depends(get_db)):
    """Get distinct years from media."""
    q = select(func.strftime("%Y", MediaFile.date_taken)).where(
        MediaFile.date_taken.isnot(None)
    ).distinct().order_by(func.strftime("%Y", MediaFile.date_taken).desc())
    result = await db.execute(q)
    return [r[0] for r in result.all() if r[0]]


@router.get("/{media_id}")
async def get_media(media_id: int, db: AsyncSession = Depends(get_db)):
    q = select(MediaFile).where(MediaFile.id == media_id)
    result = await db.execute(q)
    m = result.scalar_one_or_none()
    if not m:
        raise HTTPException(status_code=404, detail="Media not found")
    return {
        "id": m.id,
        "filename": m.filename,
        "original_path": m.original_path,
        "stored_path": m.stored_path,
        "media_type": m.media_type.value,
        "duration": m.duration,
        "width": m.width,
        "height": m.height,
        "size_bytes": m.size_bytes,
        "date_taken": m.date_taken.isoformat() if m.date_taken else None,
        "latitude": m.latitude,
        "longitude": m.longitude,
        "country": m.country,
        "city": m.city,
        "hashtags": m.hashtags or [],
    }


@router.get("/{media_id}/thumbnail")
async def get_thumbnail(media_id: int, db: AsyncSession = Depends(get_db)):
    """Serve thumbnail for a media file."""
    q = select(MediaFile).where(MediaFile.id == media_id)
    result = await db.execute(q)
    m = result.scalar_one_or_none()
    if not m:
        raise HTTPException(status_code=404, detail="Media not found")

    source = m.original_path if os.path.exists(m.original_path) else m.stored_path
    if not os.path.exists(source):
        raise HTTPException(status_code=404, detail="Source file not found")

    thumb_dir = os.path.join(MEDIA_ROOT, "thumbnails")
    os.makedirs(thumb_dir, exist_ok=True)
    thumb_path = os.path.join(thumb_dir, f"{m.id}.jpg")

    if not os.path.exists(thumb_path):
        from services.ffmpeg import create_thumbnail
        try:
            await create_thumbnail(source, thumb_path)
        except Exception as e:
            logger.error(f"Thumbnail failed for {media_id}: {e}")
            raise HTTPException(status_code=500, detail="Thumbnail generation failed")

    return FileResponse(thumb_path, media_type="image/jpeg")


@router.delete("/{media_id}")
async def delete_media(media_id: int, db: AsyncSession = Depends(get_db)):
    q = select(MediaFile).where(MediaFile.id == media_id)
    result = await db.execute(q)
    m = result.scalar_one_or_none()
    if not m:
        raise HTTPException(status_code=404, detail="Media not found")

    await db.delete(m)
    await db.commit()
    return {"deleted": media_id}
