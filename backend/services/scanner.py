"""Media scanner — walks directories, runs exiftool, extracts metadata."""

import os
import json
import logging
import asyncio
import hashlib
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

MEDIA_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp", ".heic", ".heif",
    ".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".3gp", ".wmv", ".flv",
}

VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".3gp", ".wmv", ".flv"}
PHOTO_EXTENSIONS = MEDIA_EXTENSIONS - VIDEO_EXTENSIONS


def _compute_file_hash(path: str) -> str:
    """SHA-256 of first 64KB + file size — fast unique ID."""
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        head = f.read(65536)
    return hashlib.sha256(head + str(size).encode()).hexdigest()[:16]


async def run_exiftool(filepath: str) -> dict:
    """Run exiftool -json on a single file, return parsed dict."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "exiftool", "-json", "-n", "-api", "QuickTimeUTC=1",
            filepath,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            err = stderr.decode("utf-8", errors="replace").strip()
            if "Error: File not found" not in err:
                logger.warning(f"exiftool warning for {filepath}: {err}")
            return {}

        data = json.loads(stdout.decode("utf-8", errors="replace"))
        if data and isinstance(data, list):
            return data[0]
        return {}
    except FileNotFoundError:
        logger.error("exiftool not found. Install: brew install exiftool")
        return {}
    except json.JSONDecodeError as e:
        logger.warning(f"exiftool JSON parse error for {filepath}: {e}")
        return {}
    except Exception as e:
        logger.error(f"exiftool error for {filepath}: {e}")
        return {}


def _parse_exif_date(exif: dict) -> Optional[datetime]:
    """Extract best date from EXIF."""
    date_keys = [
        "DateTimeOriginal", "CreateDate", "ModifyDate",
        "TrackCreateDate", "MediaCreateDate",
    ]
    for key in date_keys:
        val = exif.get(key)
        if val:
            try:
                if isinstance(val, (int, float)):
                    return datetime.utcfromtimestamp(val)
                # String: "2024:07:15 14:30:00" or "2024-07-15T14:30:00"
                s = str(val).replace(":", "-", 2).replace(" ", "T", 1)
                # Handle fractional seconds
                if "." in s:
                    s = s.split(".")[0]
                return datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S")
            except (ValueError, TypeError, OSError):
                continue
    return None


def _parse_gps(exif: dict) -> tuple[Optional[float], Optional[float]]:
    """Extract GPS coordinates."""
    lat = exif.get("GPSLatitude")
    lon = exif.get("GPSLongitude")
    lat_ref = exif.get("GPSLatitudeRef", "N")
    lon_ref = exif.get("GPSLongitudeRef", "E")

    try:
        if lat is not None:
            lat = float(lat)
            if lat_ref == "S":
                lat = -lat
    except (ValueError, TypeError):
        lat = None

    try:
        if lon is not None:
            lon = float(lon)
            if lon_ref == "W":
                lon = -lon
    except (ValueError, TypeError):
        lon = None

    if lat == 0.0 and lon == 0.0:
        return None, None

    return lat, lon


async def scan_file(filepath: str, media_root: str) -> Optional[dict]:
    """Scan a single file, return metadata dict or None if not media."""
    ext = Path(filepath).suffix.lower()
    if ext not in MEDIA_EXTENSIONS:
        return None

    if not os.path.isfile(filepath):
        return None

    stat = os.stat(filepath)
    exif = await run_exiftool(filepath)

    filename = os.path.basename(filepath)
    file_hash = _compute_file_hash(filepath)
    stored_name = f"{file_hash}{ext}"

    is_video = ext in VIDEO_EXTENSIONS
    media_type = "video" if is_video else "photo"

    # Duration (video only)
    duration = None
    if is_video:
        dur = exif.get("Duration") or exif.get("MediaDuration")
        if dur:
            try:
                duration = float(dur)
            except (ValueError, TypeError):
                pass

    # Dimensions
    width = None
    height = None
    w = exif.get("ImageWidth") or exif.get("SourceImageWidth")
    h = exif.get("ImageHeight") or exif.get("SourceImageHeight")
    if w and h:
        try:
            width = int(float(w))
            height = int(float(h))
        except (ValueError, TypeError):
            pass

    date_taken = _parse_exif_date(exif)
    lat, lon = _parse_gps(exif)

    return {
        "filename": filename,
        "original_path": filepath,
        "stored_name": stored_name,
        "media_type": media_type,
        "duration": duration,
        "width": width,
        "height": height,
        "size_bytes": stat.st_size,
        "date_taken": date_taken,
        "latitude": lat,
        "longitude": lon,
        "country": None,   # Can be filled via reverse geocoding later
        "city": None,
    }


async def scan_directory(dir_path: str, media_root: str) -> list[dict]:
    """Recursively scan directory, return list of metadata dicts."""
    results = []
    tasks = []

    for root, dirs, files in os.walk(dir_path):
        # Skip hidden dirs
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for fname in files:
            if fname.startswith("."):
                continue
            fpath = os.path.join(root, fname)
            ext = Path(fname).suffix.lower()
            if ext in MEDIA_EXTENSIONS:
                tasks.append(scan_file(fpath, media_root))

    if tasks:
        scanned = await asyncio.gather(*tasks, return_exceptions=True)
        for item in scanned:
            if isinstance(item, Exception):
                logger.error(f"Scan error: {item}")
            elif item is not None:
                results.append(item)

    logger.info(f"Scanned {len(results)} media files from {dir_path}")
    return results
