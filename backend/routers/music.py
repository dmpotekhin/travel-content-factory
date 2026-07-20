"""Music library routes — list and upload background tracks."""

import os
import logging
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/music", tags=["music"])

MUSIC_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "music")
MUSIC_DIR = os.path.abspath(MUSIC_DIR)

AUDIO_EXTENSIONS = {".mp3", ".m4a", ".aac", ".wav", ".ogg", ".flac", ".wma"}


@router.get("/list")
async def list_tracks():
    """List all music files in the music/ directory."""
    os.makedirs(MUSIC_DIR, exist_ok=True)

    tracks = []
    for f in sorted(Path(MUSIC_DIR).iterdir()):
        if f.is_file() and f.suffix.lower() in AUDIO_EXTENSIONS:
            size_mb = f.stat().st_size / (1024 * 1024)

            # Try to get duration via ffprobe
            duration = None
            try:
                import asyncio
                proc = await asyncio.create_subprocess_exec(
                    "ffprobe", "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    str(f),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
                if proc.returncode == 0:
                    duration = round(float(stdout.decode().strip()), 1)
            except Exception:
                pass

            tracks.append({
                "path": f"music/{f.name}",
                "filename": f.name,
                "size_mb": round(size_mb, 2),
                "duration": duration,
            })

    return {"tracks": tracks}


@router.post("/upload")
async def upload_track(file: UploadFile = File(...)):
    """Upload a music file to the music/ directory."""
    ext = Path(file.filename or "unknown").suffix.lower()
    if ext not in AUDIO_EXTENSIONS:
        raise HTTPException(400, f"Unsupported format: {ext}. Use: {', '.join(AUDIO_EXTENSIONS)}")

    os.makedirs(MUSIC_DIR, exist_ok=True)

    # Sanitize filename
    safe_name = "".join(c for c in file.filename if c.isalnum() or c in "._- ")
    if not safe_name:
        safe_name = f"track{ext}"

    dest = os.path.join(MUSIC_DIR, safe_name)

    # Avoid overwriting: append number
    counter = 1
    base, ext_part = os.path.splitext(safe_name)
    while os.path.exists(dest):
        dest = os.path.join(MUSIC_DIR, f"{base}_{counter}{ext_part}")
        counter += 1

    content = await file.read()
    with open(dest, "wb") as f:
        f.write(content)

    size_mb = len(content) / (1024 * 1024)
    logger.info(f"Uploaded music: {safe_name} ({size_mb:.1f} MB)")

    return {
        "path": f"music/{os.path.basename(dest)}",
        "filename": os.path.basename(dest),
        "size_mb": round(size_mb, 2),
    }


@router.delete("/{filename}")
async def delete_track(filename: str):
    """Delete a music file."""
    safe = "".join(c for c in filename if c.isalnum() or c in "._- ")
    if safe != filename:
        raise HTTPException(400, "Invalid filename")

    dest = os.path.join(MUSIC_DIR, safe)
    if not os.path.exists(dest):
        raise HTTPException(404, "Track not found")

    os.remove(dest)
    return {"deleted": filename}
