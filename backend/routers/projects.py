"""Project routes — CRUD, auto/manual montage, render."""

import os
import logging
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from database import get_db
from models import Project, ProjectClip, ProjectMode, ProjectStatus, MediaFile, MediaType
from services.ffmpeg import trim_video, concat_videos, overlay_audio, normalize_audio, overlay_text
from services.deepseek import get_ai_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/projects", tags=["projects"])

EXPORT_ROOT = os.getenv("EXPORT_ROOT", "./exports")


def _project_to_dict(p: Project) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "mode": p.mode.value if p.mode else None,
        "platform": p.platform,
        "status": p.status.value if p.status else None,
        "script_text": p.script_text,
        "duration_target": p.duration_target,
        "country_filter": p.country_filter,
        "year_filter": p.year_filter,
        "export_path": p.export_path,
        "clip_count": len(p.clips) if p.clips else 0,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
        "clips": [
            {
                "id": c.id,
                "media_id": c.media_id,
                "start_time": c.start_time,
                "duration": c.duration,
                "order_index": c.order_index,
                "transition": c.transition,
                "scene_description": c.scene_description,
                "media": {
                    "id": c.media.id,
                    "filename": c.media.filename,
                    "media_type": c.media.media_type.value if c.media.media_type else None,
                    "duration": c.media.duration,
                    "country": c.media.country,
                } if c.media else None,
            }
            for c in (p.clips or [])
        ],
    }


# ── CRUD ──────────────────────────────────────────────────────────

@router.get("/")
async def list_projects(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    q = select(Project).options(
        selectinload(Project.clips).selectinload(ProjectClip.media)
    ).order_by(Project.updated_at.desc())
    count_q = select(func.count()).select_from(Project)
    total = (await db.execute(count_q)).scalar() or 0

    offset = (page - 1) * page_size
    q = q.offset(offset).limit(page_size)
    result = await db.execute(q)
    projects = result.scalars().all()

    return {
        "items": [_project_to_dict(p) for p in projects],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/")
async def create_project(data: dict, db: AsyncSession = Depends(get_db)):
    p = Project(
        name=data.get("name", "Untitled"),
        mode=ProjectMode(data.get("mode", "manual")),
        platform=data.get("platform"),
        script_text=data.get("script_text"),
        duration_target=data.get("duration_target"),
        country_filter=data.get("country_filter"),
        year_filter=data.get("year_filter"),
    )
    db.add(p)
    await db.commit()
    await db.refresh(p)

    # If mode is "auto", run auto-matching
    if p.mode == ProjectMode.auto:
        await _auto_match_clips(p, db)
    # If mode is "script" and has script_text, split into scenes
    elif p.mode == ProjectMode.script and p.script_text:
        await _script_to_scenes(p, db)

    # Re-query with eager loading
    q = select(Project).options(
        selectinload(Project.clips).selectinload(ProjectClip.media)
    ).where(Project.id == p.id)
    result = await db.execute(q)
    p = result.scalar_one()
    return _project_to_dict(p)


@router.get("/{project_id}")
async def get_project(project_id: int, db: AsyncSession = Depends(get_db)):
    q = select(Project).options(
        selectinload(Project.clips).selectinload(ProjectClip.media)
    ).where(Project.id == project_id)
    result = await db.execute(q)
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    return _project_to_dict(p)


@router.put("/{project_id}")
async def update_project(project_id: int, data: dict, db: AsyncSession = Depends(get_db)):
    q = select(Project).where(Project.id == project_id)
    result = await db.execute(q)
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")

    for field in ("name", "script_text", "duration_target", "country_filter", "year_filter", "platform"):
        if field in data:
            setattr(p, field, data[field])
    if "mode" in data:
        p.mode = ProjectMode(data["mode"])

    await db.commit()
    # Re-query with eager loading
    q = select(Project).options(
        selectinload(Project.clips).selectinload(ProjectClip.media)
    ).where(Project.id == project_id)
    result = await db.execute(q)
    p = result.scalar_one()
    return _project_to_dict(p)


@router.delete("/{project_id}")
async def delete_project(project_id: int, db: AsyncSession = Depends(get_db)):
    q = select(Project).where(Project.id == project_id)
    result = await db.execute(q)
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    await db.delete(p)
    await db.commit()
    return {"deleted": project_id}


# ── Clips management ──────────────────────────────────────────────

@router.post("/{project_id}/clips")
async def set_clips(project_id: int, data: dict, db: AsyncSession = Depends(get_db)):
    """Set manual clip list. data = {"clips": [{"media_id": 1, "start_time": 0, "duration": 5}, ...]}"""
    q = select(Project).where(Project.id == project_id)
    result = await db.execute(q)
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")

    # Clear existing
    for c in p.clips:
        await db.delete(c)

    clips_data = data.get("clips", [])
    for i, cd in enumerate(clips_data):
        clip = ProjectClip(
            project_id=project_id,
            media_id=cd["media_id"],
            start_time=cd.get("start_time", 0),
            duration=cd.get("duration", 5),
            order_index=i,
            transition=cd.get("transition", "cut"),
        )
        db.add(clip)

    p.status = ProjectStatus.draft
    await db.commit()
    # Re-query with eager loading
    q = select(Project).options(
        selectinload(Project.clips).selectinload(ProjectClip.media)
    ).where(Project.id == project_id)
    result = await db.execute(q)
    p = result.scalar_one()
    return _project_to_dict(p)


# ── Auto matching ─────────────────────────────────────────────────

async def _auto_match_clips(project: Project, db: AsyncSession):
    """Find media matching project filters and create default clips."""
    q = select(MediaFile).where(MediaFile.media_type == MediaType.video)

    if project.country_filter:
        q = q.where(MediaFile.country == project.country_filter)
    if project.year_filter:
        q = q.where(func.strftime("%Y", MediaFile.date_taken) == str(project.year_filter))

    result = await db.execute(q.order_by(func.random()).limit(20))
    media_list = result.scalars().all()

    if not media_list:
        project.status = ProjectStatus.error
        return

    target_duration = project.duration_target or 30.0
    clip_duration = min(5.0, target_duration / max(len(media_list), 1))

    # Clear existing
    for c in project.clips:
        await db.delete(c)

    total = 0.0
    for i, m in enumerate(media_list):
        if total >= target_duration:
            break
        dur = min(clip_duration, (m.duration or clip_duration), target_duration - total)
        clip = ProjectClip(
            project_id=project.id,
            media_id=m.id,
            start_time=0.0,
            duration=dur,
            order_index=i,
            transition="cut",
        )
        db.add(clip)
        total += dur

    project.status = ProjectStatus.ready


# ── Script to scenes ──────────────────────────────────────────────

async def _script_to_scenes(project: Project, db: AsyncSession):
    """Use AI to break script into scenes, then match media by metadata."""
    if not project.script_text:
        project.status = ProjectStatus.error
        return

    ai = get_ai_client()
    system = (
        "You are a video editor AI. Break the user's script into scenes. "
        "For each scene, provide: index, description (what should be shown visually), "
        "duration_hint (seconds, 3-10). Return JSON array only."
    )
    user = (
        f"Break this script into scenes for a {project.platform or 'social media'} video "
        f"(target duration: {project.duration_target or 30}s):\n\n{project.script_text}"
    )

    try:
        scenes = await ai.generate_json(system, user)
    except Exception as e:
        logger.error(f"Script-to-scenes AI error: {e}")
        project.status = ProjectStatus.error
        return

    if not isinstance(scenes, list):
        scenes = scenes.get("scenes", [])

    # Clear existing
    for c in project.clips:
        await db.delete(c)

    # Find matching media for each scene
    q = select(MediaFile).where(MediaFile.media_type == MediaType.video)
    if project.country_filter:
        q = q.where(MediaFile.country == project.country_filter)
    if project.year_filter:
        q = q.where(func.strftime("%Y", MediaFile.date_taken) == str(project.year_filter))

    result = await db.execute(q.order_by(func.random()).limit(30))
    available = result.scalars().all()

    for i, scene in enumerate(scenes[:15]):  # Max 15 scenes
        dur = scene.get("duration_hint", 5)
        if isinstance(dur, str):
            try:
                dur = float(dur)
            except ValueError:
                dur = 5

        # Pick a media file — round-robin through available
        media = available[i % len(available)] if available else None

        clip = ProjectClip(
            project_id=project.id,
            media_id=media.id if media else None,
            start_time=0.0,
            duration=dur,
            order_index=i,
            transition="cut",
            scene_description=scene.get("description", f"Scene {i+1}"),
        )
        db.add(clip)

    project.status = ProjectStatus.ready


# ── Render ────────────────────────────────────────────────────────

@router.post("/{project_id}/render")
async def render_project(
    project_id: int,
    data: dict = {},
    db: AsyncSession = Depends(get_db),
):
    """Render final video from project clips. Optional: data = {"music_path": "music/track.mp3", "music_volume": 0.3}"""
    q = select(Project).where(Project.id == project_id)
    result = await db.execute(q)
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    if not p.clips:
        raise HTTPException(status_code=400, detail="Project has no clips")

    music_path = data.get("music_path")
    music_volume = float(data.get("music_volume", 0.25))
    add_captions = data.get("add_captions", False)
    caption_text = data.get("caption_text", "").strip()

    p.status = ProjectStatus.processing
    await db.commit()

    os.makedirs(EXPORT_ROOT, exist_ok=True)

    try:
        # ── AI caption generation ──────────────────────────────
        captions = {}
        if add_captions:
            clips_list = sorted(p.clips, key=lambda c: c.order_index)
            for clip in clips_list:
                if clip.scene_description:
                    captions[clip.order_index] = clip.scene_description
                elif clip.media:
                    # Generate caption from media metadata via AI
                    captions[clip.order_index] = None  # placeholder

            # If we have clips without descriptions and no manual caption, call AI
            need_ai = [k for k, v in captions.items() if v is None]
            if need_ai and not caption_text:
                try:
                    ai = get_ai_client()
                    clip_infos = []
                    for clip in clips_list:
                        if clip.order_index in need_ai and clip.media:
                            loc = clip.media.country or clip.media.city or "unknown"
                            date = clip.media.date_taken.strftime("%Y-%m-%d") if clip.media.date_taken else ""
                            clip_infos.append(
                                f"Clip {clip.order_index}: {clip.media.filename}, "
                                f"location={loc}, date={date}, duration={clip.duration}s"
                            )
                    if clip_infos:
                        prompt = (
                            "Generate a short on-screen caption (5-8 words max, engaging, "
                            "suitable for TikTok/Reels) for each clip. "
                            "Return JSON: {\"captions\": [{\"clip_index\": 0, \"text\": \"...\"}, ...]}"
                        )
                        user = "Clips:\n" + "\n".join(clip_infos)
                        result = await ai.generate_json(prompt, user)
                        ai_captions = result.get("captions", [])
                        for ac in ai_captions:
                            idx = ac.get("clip_index", 0)
                            txt = ac.get("text", "")
                            if idx in captions:
                                captions[idx] = txt
                except Exception as e:
                    logger.warning(f"AI caption generation failed: {e}")
                    # Continue without captions for these clips

        # ── Render pipeline ────────────────────────────────────
        trimmed_paths = []
        with tempfile.TemporaryDirectory() as tmpdir:
            for clip in sorted(p.clips, key=lambda c: c.order_index):
                if not clip.media:
                    continue
                source = clip.media.original_path
                if not os.path.exists(source):
                    source = clip.media.stored_path
                if not os.path.exists(source):
                    continue

                trim_out = os.path.join(tmpdir, f"clip_{clip.order_index:03d}.mp4")
                await trim_video(
                    source, trim_out,
                    start=clip.start_time,
                    duration=clip.duration,
                )

                # Overlay text if captions enabled
                clip_text = caption_text or captions.get(clip.order_index, "")
                if add_captions and clip_text:
                    text_out = os.path.join(tmpdir, f"clip_{clip.order_index:03d}_text.mp4")
                    await overlay_text(trim_out, clip_text, text_out)
                    trimmed_paths.append(text_out)
                else:
                    trimmed_paths.append(trim_out)

            if not trimmed_paths:
                raise HTTPException(400, "No valid clips to render")

            export_name = f"project_{p.id}_{p.name.replace(' ', '_')}.mp4"
            export_path = os.path.join(EXPORT_ROOT, export_name)

            # Step 1: concat clips
            concat_out = export_path
            if music_path:
                concat_out = os.path.join(tmpdir, "concat_temp.mp4")
            await concat_videos(trimmed_paths, concat_out)

            # Step 2: overlay music (optional)
            if music_path:
                music_abs = music_path
                if not os.path.isabs(music_abs):
                    music_abs = os.path.join(os.path.dirname(__file__), "..", "..", music_path)
                    music_abs = os.path.abspath(music_abs)
                if not os.path.exists(music_abs):
                    raise HTTPException(400, f"Music file not found: {music_abs}")

                with_music = os.path.join(tmpdir, "with_music.mp4")
                await overlay_audio(concat_out, music_abs, with_music, music_volume=music_volume)

                # Step 3: normalize
                await normalize_audio(with_music, export_path)

            elif not music_path:
                # Still normalize even without music
                normalized = os.path.join(tmpdir, "normalized.mp4")
                await normalize_audio(concat_out, normalized)
                os.rename(normalized, export_path)

        p.export_path = export_path
        p.status = ProjectStatus.ready
        await db.commit()

        return {
            "status": "ready",
            "export_path": export_path,
            "download_url": f"/api/projects/{project_id}/download",
            "music_applied": bool(music_path),
            "captions_applied": add_captions and any(captions.values()),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Render failed for project {project_id}: {e}")
        p.status = ProjectStatus.error
        await db.commit()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{project_id}/download")
async def download_project(project_id: int, db: AsyncSession = Depends(get_db)):
    """Download rendered video."""
    from fastapi.responses import FileResponse

    q = select(Project).where(Project.id == project_id)
    result = await db.execute(q)
    p = result.scalar_one_or_none()
    if not p or not p.export_path:
        raise HTTPException(status_code=404, detail="Export not found")
    if not os.path.exists(p.export_path):
        raise HTTPException(status_code=404, detail="Export file missing")

    return FileResponse(p.export_path, media_type="video/mp4",
                        filename=os.path.basename(p.export_path))
