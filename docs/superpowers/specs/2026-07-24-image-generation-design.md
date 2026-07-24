# Image Generation via Abacus AI — Design Spec

**Date:** 2026-07-24
**Project:** Travel Content Factory
**API:** Abacus AI RouteLLM (`https://routellm.abacus.ai/v1`)

## Overview

Add AI image generation to Travel Content Factory using Abacus AI's RouteLLM API
(access to FLUX, DALL-E, MidJourney, and 20+ models). Follow existing project
patterns: async httpx service + FastAPI router + Vanilla JS frontend.

## Scenarios

| # | Scenario | Trigger | Output |
|---|----------|---------|--------|
| 1 | Thumbnail generation | Render dialog: «Generate Cover» button | Cover image saved, attached to project |
| 2 | Content illustration | Content Factory: «Generate Image» near script result | Image matching topic, shown in result |
| 3 | Standalone generator | New «Image Factory» tab | Prompt → image, gallery of results |

## Architecture

Following the existing `deepseek.py` + `ai.py` pattern:

```
backend/services/abacus.py       — AbacusImageClient (BaseImageClient → async httpx + retry)
backend/routers/images.py        — /api/images/*  (generate, list, serve, generate-cover)
backend/models.py                — GeneratedImage ORM model (optional catalog)
generated/                       — output directory for saved images
frontend/index.html              — new «Image Factory» tab + buttons in existing UI
frontend/js/app.js               — new API calls + image factory logic
frontend/css/style.css           — new styles for image factory
```

## API Endpoints

### POST /api/images/generate
Generate image from prompt.
```
Request:  {prompt: str, aspect_ratio?: "square"|"landscape"|"portrait", model?: str}
Response: {id: int, path: str, url: str, prompt: str, model: str, width: int, height: int}
```
Errors: 400 (no prompt), 502 (API failure), 503 (no API key).

### GET /api/images/list
List generated images.
```
Response: {images: [{id, filename, prompt, model, aspect_ratio, created_at, size_bytes}, ...]}
```
Supports `?page=1&page_size=20` pagination.

### GET /api/images/{id}/file
Serve the image file (Content-Type: image/png).

### POST /api/images/generate-cover
Generate a cover image for a project.
```
Request:  {project_id: int, prompt_override?: str}
Response: {id: int, path: str, url: str}
```
Uses project name + platform as prompt if no override.

## Backend: AbacusImageClient

```python
class BaseImageClient:
    async def generate(prompt, aspect_ratio, model, **kwargs) -> GeneratedImageResult: ...

class AbacusImageClient(BaseImageClient):
    BASE_URL = "https://routellm.abacus.ai/v1"
    # httpx.AsyncClient, retry (3 attempts, exponential backoff)
    # Reads ABACUS_AI_API_KEY from .env
    # Default model: flux2_pro
    # Saves base64 data-URI to generated/ directory
```

Response parsing: extract base64 from `choices[0].message.images[0].image_url.url`,
decode, save as PNG to `generated/<timestamp>_<model>.png`.

## Aspect Ratios

| User choice | FLUX format | DALL-E/MidJourney format |
|-------------|-------------|--------------------------|
| square      | square_hd   | 1:1                      |
| landscape   | landscape_16_9 | 16:9                  |
| portrait    | portrait_16_9  | 9:16                   |

## Frontend Changes

### New: Image Factory tab
- Prompt textarea
- Aspect ratio buttons (square/landscape/portrait), default square
- Model selector dropdown (optional, advanced)
- Generate button → loading spinner → result image
- Gallery grid of previously generated images (paginated)
- Click image → full-size preview / download

### Modified: Content Factory tab
- After script generation, add «Generate Image» button
- Injects topic into prompt, shows result below script

### Modified: Render Dialog
- New checkbox «Generate AI cover image»
- On render, generates cover using project name + platform as prompt

## Data Model (optional)

```python
class GeneratedImage(Base):
    __tablename__ = "generated_images"
    id, project_id (FK, nullable), prompt, model, aspect_ratio,
    file_path, width, height, size_bytes, created_at
```

If we skip the ORM model, list endpoint reads the `generated/` directory directly.
Decision: start without ORM (filesystem is the catalog), add DB later if needed.

## Error Handling

- Missing API key → 503 with clear message
- API timeout (120s) → 502 with retry info
- API returns no image → 502 with raw response snippet logged
- Invalid aspect ratio → 400

## Environment

`.env` addition: `ABACUS_AI_API_KEY=s2_1cdc555034a7493aa20e1984ea7eb694`
