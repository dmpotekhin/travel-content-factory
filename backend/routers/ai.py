"""AI routes — content generation via DeepSeek."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import get_db
from models import Project, Generation
from services.deepseek import get_ai_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ai", tags=["ai"])


PLATFORM_CONFIG = {
    "tiktok": {
        "max_duration": 60,
        "style": "short, punchy, vertical 9:16, hook in first 2 seconds, trending audio cues",
        "hashtag_count": 5,
    },
    "reels": {
        "max_duration": 90,
        "style": "polished, vertical 9:16, storytelling, strong visual transitions",
        "hashtag_count": 7,
    },
    "facebook": {
        "max_duration": 120,
        "style": "narrative-driven, horizontal or square, detailed captions, shareable",
        "hashtag_count": 3,
    },
}


@router.post("/generate")
async def generate_content(data: dict, db: AsyncSession = Depends(get_db)):
    """
    Generate script, caption, hashtags for a topic + platform.
    data = {"topic": "...", "platform": "tiktok|reels|facebook", "project_id": null}
    """
    topic = data.get("topic", "").strip()
    platform = data.get("platform", "tiktok").lower()
    project_id = data.get("project_id")

    if not topic:
        raise HTTPException(status_code=400, detail="Topic is required")
    if platform not in PLATFORM_CONFIG:
        raise HTTPException(status_code=400, detail=f"Unknown platform: {platform}")

    cfg = PLATFORM_CONFIG[platform]

    system = (
        f"You are a professional content creator for {platform}. "
        f"Create engaging content optimized for {platform}: {cfg['style']}. "
        f"Maximum duration: {cfg['max_duration']}s. "
        "Respond in JSON format with these fields: "
        '"script" (the video script, scene by scene), '
        '"caption" (the post caption/description), '
        '"hashtags" (array of strings). '
        "Script should be concise and visual."
    )

    user = (
        f"Create a {platform} video about: {topic}\n"
        f"Target duration: {data.get('duration_target', cfg['max_duration'])}s\n"
        f"Language: {data.get('language', 'Russian' if any(c in 'абвгдеёжзийклмнопрстуфхцчшщъыьэюя' for c in topic) else 'English')}"
    )

    ai = get_ai_client()

    try:
        result = await ai.generate_json(system, user)
    except Exception as e:
        logger.error(f"AI generation error: {e}")
        raise HTTPException(status_code=502, detail=f"AI generation failed: {e}")

    script = result.get("script", "")
    caption = result.get("caption", "")
    hashtags = result.get("hashtags", [])

    # Save to DB if project_id provided
    if project_id:
        q = select(Project).where(Project.id == project_id)
        proj_result = await db.execute(q)
        project = proj_result.scalar_one_or_none()
        if project:
            gen = Generation(
                project_id=project_id,
                platform=platform,
                topic=topic,
                generated_script=script,
                generated_caption=caption,
                generated_hashtags=hashtags,
            )
            db.add(gen)
            # Also update project script
            project.script_text = script
            await db.commit()

    return {
        "platform": platform,
        "topic": topic,
        "script": script,
        "caption": caption,
        "hashtags": hashtags,
    }


@router.post("/script-to-scenes")
async def script_to_scenes(data: dict):
    """
    Break a script into scenes.
    data = {"script": "...", "platform": "tiktok|reels|facebook"}
    """
    script = data.get("script", "").strip()
    platform = data.get("platform", "tiktok")

    if not script:
        raise HTTPException(status_code=400, detail="Script is required")

    system = (
        "Break the video script into individual scenes. "
        "For each scene, provide: index (1-based), description (what to show visually), "
        "duration_hint (seconds). Return JSON array only."
    )
    user = f"Script:\n\n{script}"

    ai = get_ai_client()
    try:
        scenes = await ai.generate_json(system, user)
    except Exception as e:
        logger.error(f"Script-to-scenes error: {e}")
        raise HTTPException(status_code=502, detail=str(e))

    if isinstance(scenes, dict):
        scenes = scenes.get("scenes", [])

    return {"scenes": scenes}
