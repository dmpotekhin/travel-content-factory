"""DeepSeek API client — async HTTP via httpx."""

import os
import json
import logging
from dataclasses import dataclass
from typing import Optional

import httpx
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


@dataclass
class AIGenerationResult:
    script: str
    caption: str
    hashtags: list[str]


@dataclass
class SceneBreakdown:
    scenes: list[dict]   # [{"index": 0, "description": "...", "duration_hint": 5.0}, ...]


class BaseAIClient:
    """Abstract base for AI backends — swap DeepSeek for local LLM later."""

    async def generate(self, system_prompt: str, user_prompt: str, **kwargs) -> str:
        raise NotImplementedError

    async def generate_json(self, system_prompt: str, user_prompt: str, **kwargs) -> dict:
        """Generate and parse JSON response."""
        raw = await self.generate(system_prompt, user_prompt, **kwargs)
        # Strip markdown code fences if present
        raw = raw.strip()
        if raw.startswith("```"):
            lines = raw.split("\n")
            # Remove first line (```json or ```) and last line (```)
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            raw = "\n".join(lines)
        return json.loads(raw)


class DeepSeekClient(BaseAIClient):
    """DeepSeek API via HTTP."""

    BASE_URL = "https://api.deepseek.com/v1"

    def __init__(self, api_key: Optional[str] = None, model: str = "deepseek-chat"):
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY", "")
        self.model = model
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

    async def generate(self, system_prompt: str, user_prompt: str, **kwargs) -> str:
        client = await self._get_client()
        max_retries = 3
        last_error = None

        for attempt in range(max_retries):
            try:
                resp = await client.post(
                    "/chat/completions",
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        "temperature": kwargs.get("temperature", 0.7),
                        "max_tokens": kwargs.get("max_tokens", 4096),
                        "response_format": kwargs.get("response_format"),
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"]
            except (httpx.HTTPError, KeyError, IndexError) as e:
                last_error = e
                logger.warning(f"DeepSeek API attempt {attempt + 1}/{max_retries} failed: {e}")
                if attempt < max_retries - 1:
                    import asyncio
                    await asyncio.sleep(2 ** attempt)

        raise RuntimeError(f"DeepSeek API failed after {max_retries} attempts: {last_error}")

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None


# Singleton — created at app startup
_ai_client: Optional[DeepSeekClient] = None


def get_ai_client() -> DeepSeekClient:
    global _ai_client
    if _ai_client is None:
        _ai_client = DeepSeekClient()
    return _ai_client
