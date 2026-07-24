"""Abacus AI image generation client — async HTTP via httpx."""

import os
import base64
import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

GENERATED_DIR = Path(__file__).parent.parent.parent / "generated"

FLUX_ASPECT_RATIOS = {
    "square": "square_hd",
    "landscape": "landscape_16_9",
    "portrait": "portrait_16_9",
}

STANDARD_ASPECT_RATIOS = {
    "square": "1:1",
    "landscape": "16:9",
    "portrait": "9:16",
}

STANDARD_ASPECT_MODELS = {"midjourney", "dalle", "flux_pro_ultra", "seedream"}


@dataclass
class GeneratedImageResult:
    file_path: str       # relative path from project root, e.g. "generated/20260724_120000_flux2_pro.png"
    prompt: str
    model: str
    width: int
    height: int
    size_bytes: int


def _resolve_aspect_ratio(aspect_ratio: str, model_id: str) -> str:
    """Map user-facing aspect ratio to model-specific format."""
    model_key = model_id.lower().replace("_", "").replace("-", "")
    for std_model in STANDARD_ASPECT_MODELS:
        if std_model.replace("_", "") in model_key:
            return STANDARD_ASPECT_RATIOS.get(aspect_ratio, "1:1")
    return FLUX_ASPECT_RATIOS.get(aspect_ratio, "square_hd")


def _get_image_dimensions(data: bytes) -> tuple[int, int]:
    """Get PNG/JPEG dimensions from raw bytes. Returns (0, 0) on failure."""
    import struct
    try:
        if data[:8] == b'\x89PNG\r\n\x1a\n':
            # PNG: IHDR at offset 16
            w, h = struct.unpack('>II', data[16:24])
            return w, h
        elif data[:2] == b'\xff\xd8':
            # JPEG: scan for SOF0/SOF2 marker
            i = 2
            while i < len(data) - 8:
                marker = data[i]
                if marker != 0xFF:
                    break
                segment_type = data[i + 1]
                if segment_type in (0xC0, 0xC2):
                    h, w = struct.unpack('>HH', data[i + 5:i + 9])
                    return w, h
                length = struct.unpack('>H', data[i + 2:i + 4])[0]
                i += 2 + length
    except Exception:
        pass
    return 0, 0


class BaseImageClient:
    """Abstract base for image generation backends."""

    async def generate(
        self, prompt: str, aspect_ratio: str = "square",
        model: Optional[str] = None, **kwargs
    ) -> GeneratedImageResult:
        raise NotImplementedError

    async def close(self):
        pass


class AbacusImageClient(BaseImageClient):
    """Image generation via Abacus AI RouteLLM."""

    BASE_URL = "https://routellm.abacus.ai/v1"

    def __init__(self, api_key: Optional[str] = None, default_model: str = "flux2_pro"):
        self.api_key = api_key or os.getenv("ABACUS_AI_API_KEY", "")
        self.default_model = default_model
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.BASE_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=httpx.Timeout(120.0),
            )
        return self._client

    async def generate(
        self, prompt: str, aspect_ratio: str = "square",
        model: Optional[str] = None, **kwargs
    ) -> GeneratedImageResult:
        if not self.api_key:
            raise RuntimeError("ABACUS_AI_API_KEY not configured")

        model_id = (model or self.default_model).strip()
        or_aspect = _resolve_aspect_ratio(aspect_ratio, model_id)

        payload = {
            "model": model_id,
            "modalities": ["image", "text"],
            "messages": [
                {"role": "user", "content": [{"type": "text", "text": prompt}]}
            ],
            "image_config": {"aspect_ratio": or_aspect},
        }

        client = await self._get_client()
        max_retries = 3
        last_error = None

        for attempt in range(max_retries):
            try:
                resp = await client.post("/chat/completions", json=payload)
                resp.raise_for_status()
                data = resp.json()
                break
            except (httpx.HTTPError, KeyError, IndexError) as e:
                last_error = e
                logger.warning(f"Abacus AI attempt {attempt + 1}/{max_retries} failed: {e}")
                if attempt < max_retries - 1:
                    import asyncio
                    await asyncio.sleep(2 ** attempt)
        else:
            raise RuntimeError(f"Abacus AI failed after {max_retries} attempts: {last_error}")

        # Extract base64 image from response
        try:
            images = data["choices"][0]["message"]["images"]
            img_url = images[0]["image_url"]["url"]
        except (KeyError, IndexError, TypeError) as e:
            raise RuntimeError(f"No image in Abacus AI response: {e}") from e

        # Decode base64
        if not img_url.startswith("data:image"):
            raise RuntimeError(f"Unexpected image URL format: {img_url[:80]}...")

        # data:image/png;base64,<data>
        header, b64_data = img_url.split(",", 1)
        image_data = base64.b64decode(b64_data)

        # Determine extension
        ext = "png"
        if "jpeg" in header or "jpg" in header:
            ext = "jpg"
        elif "webp" in header:
            ext = "webp"

        # Save to generated/
        GENERATED_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_prompt = hashlib.md5(prompt.encode()).hexdigest()[:6]
        filename = f"{ts}_{model_id}_{safe_prompt}.{ext}"
        file_path = GENERATED_DIR / filename
        file_path.write_bytes(image_data)

        w, h = _get_image_dimensions(image_data)

        return GeneratedImageResult(
            file_path=str(file_path.relative_to(GENERATED_DIR.parent.parent)),
            prompt=prompt,
            model=model_id,
            width=w,
            height=h,
            size_bytes=len(image_data),
        )

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None


# Singleton
_image_client: Optional[AbacusImageClient] = None


def get_image_client() -> AbacusImageClient:
    global _image_client
    if _image_client is None:
        _image_client = AbacusImageClient()
    return _image_client
