"""FFmpeg operations — async subprocess wrapper."""

import os
import asyncio
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class FFmpegError(Exception):
    def __init__(self, message: str, stderr: str = ""):
        self.stderr = stderr
        super().__init__(message)


async def _run_ffmpeg(args: list[str], timeout: int = 300) -> tuple[int, str, str]:
    """Run ffmpeg as subprocess, return (returncode, stdout, stderr)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
        out = stdout.decode("utf-8", errors="replace").strip()
        err = stderr.decode("utf-8", errors="replace").strip()
        return proc.returncode or 0, out, err
    except FileNotFoundError:
        raise FFmpegError("ffmpeg not found. Install: brew install ffmpeg")
    except asyncio.TimeoutError:
        raise FFmpegError(f"ffmpeg timed out after {timeout}s")
    except Exception as e:
        raise FFmpegError(f"ffmpeg error: {e}")


async def get_video_info(filepath: str) -> dict:
    """Get video metadata using ffprobe."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_format", "-show_streams", filepath,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
        if proc.returncode != 0:
            return {}
        import json
        return json.loads(stdout.decode("utf-8", errors="replace"))
    except Exception as e:
        logger.warning(f"ffprobe error for {filepath}: {e}")
        return {}


async def trim_video(
    input_path: str,
    output_path: str,
    start: float,
    duration: float,
    reencode: bool = True,
) -> str:
    """Extract a clip. Returns output path on success."""
    args = ["-y", "-ss", str(start)]
    if not reencode:
        args += ["-i", input_path, "-t", str(duration), "-c", "copy"]
    else:
        args += ["-i", input_path, "-t", str(duration),
                 "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                 "-c:a", "aac", "-b:a", "128k"]

    args.append(output_path)

    rc, _, stderr = await _run_ffmpeg(args, timeout=120)
    if rc != 0:
        raise FFmpegError(f"trim_video failed for {input_path}", stderr)

    return output_path


async def concat_videos(
    input_files: list[str],
    output_path: str,
    transition: str = "cut",
) -> str:
    """Concatenate video clips using concat demuxer. Returns output path."""

    if not input_files:
        raise FFmpegError("No input files for concat")

    if len(input_files) == 1:
        # Single file — just copy
        args = ["-y", "-i", input_files[0], "-c", "copy", output_path]
        rc, _, stderr = await _run_ffmpeg(args, timeout=120)
        if rc != 0:
            raise FFmpegError("concat_videos (single) failed", stderr)
        return output_path

    # Write concat file list
    concat_list_path = output_path + ".concat.txt"
    with open(concat_list_path, "w") as f:
        for fp in input_files:
            f.write(f"file '{os.path.abspath(fp)}'\n")

    try:
        args = [
            "-y", "-f", "concat", "-safe", "0",
            "-i", concat_list_path,
            "-c", "copy", output_path,
        ]
        rc, _, stderr = await _run_ffmpeg(args, timeout=300)

        if rc != 0:
            # Fallback: re-encode
            logger.warning("concat with -c copy failed, trying re-encode")
            args = [
                "-y", "-f", "concat", "-safe", "0",
                "-i", concat_list_path,
                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                "-c:a", "aac", "-b:a", "128k",
                output_path,
            ]
            rc, _, stderr = await _run_ffmpeg(args, timeout=600)
            if rc != 0:
                raise FFmpegError("concat_videos re-encode failed", stderr)
    finally:
        if os.path.exists(concat_list_path):
            os.unlink(concat_list_path)

    return output_path


async def extract_frame(
    input_path: str,
    output_path: str,
    time_sec: float = 1.0,
) -> str:
    """Extract a single frame as JPEG. Returns output path."""
    args = [
        "-y", "-ss", str(time_sec),
        "-i", input_path,
        "-vframes", "1",
        "-q:v", "2",
        output_path,
    ]
    rc, _, stderr = await _run_ffmpeg(args, timeout=30)
    if rc != 0:
        raise FFmpegError(f"extract_frame failed for {input_path}", stderr)
    return output_path


async def create_thumbnail(
    input_path: str,
    output_path: str,
    size: str = "320x240",
) -> str:
    """Create a thumbnail image from video or photo."""
    ext = Path(input_path).suffix.lower()
    video_exts = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".3gp", ".wmv", ".flv"}

    if ext in video_exts:
        # Extract frame and scale
        args = [
            "-y", "-ss", "1",
            "-i", input_path,
            "-vframes", "1",
            "-vf", f"scale={size}:force_original_aspect_ratio=decrease,pad={size}:(ow-iw)/2:(oh-ih)/2",
            output_path,
        ]
    else:
        # Scale image
        args = [
            "-y", "-i", input_path,
            "-vf", f"scale={size}:force_original_aspect_ratio=decrease,pad={size}:(ow-iw)/2:(oh-ih)/2",
            output_path,
        ]

    rc, _, stderr = await _run_ffmpeg(args, timeout=30)
    if rc != 0:
        raise FFmpegError(f"create_thumbnail failed for {input_path}", stderr)
    return output_path


async def get_duration(filepath: str) -> float:
    """Get media duration in seconds via ffprobe. Returns 0.0 on failure."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            filepath,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        if proc.returncode == 0:
            return float(stdout.decode("utf-8", errors="replace").strip())
    except Exception as e:
        logger.warning(f"get_duration failed for {filepath}: {e}")
    return 0.0


async def overlay_audio(
    video_path: str,
    music_path: str,
    output_path: str,
    music_volume: float = 0.3,
    original_volume: float = 0.8,
    fade_in: float = 1.5,
    fade_out: float = 2.0,
) -> str:
    """
    Overlay background music onto a video.

    - Loops music to match video duration
    - Fades music in/out
    - Mixes original audio with music at specified volumes
    - Preserves video stream (copy)
    """
    if not os.path.exists(music_path):
        raise FFmpegError(f"Music file not found: {music_path}")
    if not os.path.exists(video_path):
        raise FFmpegError(f"Video file not found: {video_path}")

    duration = await get_duration(video_path)
    if duration <= 0:
        raise FFmpegError(f"Cannot determine duration of: {video_path}")

    # Build filter: loop music → fade in/out → adjust volume → mix with original
    # Strategy: use amovie to loop music, then amix with original audio
    args = [
        "-y",
        "-i", video_path,
        "-stream_loop", "-1",           # loop music infinitely
        "-i", music_path,
        "-filter_complex",
        (
            f"[1:a]volume={music_volume},"
            f"afade=t=in:d={fade_in},"
            f"afade=t=out:st={duration - fade_out}:d={fade_out}"
            f"[music];"
            f"[0:a]volume={original_volume}[orig];"
            f"[orig][music]amix=inputs=2:duration=first:dropout_transition=2[audio]"
        ),
        "-map", "0:v",                  # keep video from first input
        "-map", "[audio]",              # use mixed audio
        "-c:v", "copy",                 # no video re-encode
        "-c:a", "aac", "-b:a", "192k",  # encode mixed audio
        "-shortest",                    # stop at shortest input (video)
        "-t", str(duration),            # explicit duration cap
        output_path,
    ]

    rc, _, stderr = await _run_ffmpeg(args, timeout=600)
    if rc != 0:
        raise FFmpegError(f"overlay_audio failed", stderr)

    return output_path


async def normalize_audio(
    video_path: str,
    output_path: str,
    target_level: float = -14.0,   # LUFS target for social media
) -> str:
    """
    Normalize audio loudness to a target LUFS level.
    Uses loudnorm filter. Good for social media consistency.
    """
    args = [
        "-y",
        "-i", video_path,
        "-af", f"loudnorm=I={target_level}:TP=-1.0:LRA=11",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        output_path,
    ]

    rc, _, stderr = await _run_ffmpeg(args, timeout=300)
    if rc != 0:
        raise FFmpegError(f"normalize_audio failed", stderr)

    return output_path
