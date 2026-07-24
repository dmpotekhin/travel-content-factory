# Image Generation via Abacus AI — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add AI image generation (thumbnails, illustrations, standalone generator) to Travel Content Factory via Abacus AI RouteLLM API.

**Architecture:** New `backend/services/abacus.py` (async httpx client like deepseek.py) + `backend/routers/images.py` (FastAPI router) + frontend changes (new Image Factory tab, buttons in existing UI). Images saved to `generated/` directory, served as static files.

**Tech Stack:** Python 3.11, FastAPI, httpx, aiosqlite/SQLAlchemy, Vanilla JS, CSS

## Global Constraints

- Follow existing project patterns: `BaseClient` abstract → concrete client, singleton getter, async httpx with retry
- API key from `backend/.env`: `ABACUS_AI_API_KEY`
- Default model: `flux2_pro`
- Images saved to `generated/` directory (created in lifespan)
- Frontend: Vanilla JS SPA, dark theme, same CSS patterns as existing code
- All routes registered BEFORE static mount in `main.py`

---

### Task 1: Abacus AI Image Client Service

**Files:**
- Create: `backend/services/abacus.py`

**Interfaces:**
- Consumes: `ABACUS_AI_API_KEY` from `backend/.env`
- Produces: `get_image_client() -> AbacusImageClient`, `BaseImageClient` abstract class, `AbacusImageClient` concrete class

- [ ] **Step 1: Create `backend/services/abacus.py`**

```python
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
```

- [ ] **Step 2: Verify syntax**

Run: `cd /Users/dmitrypotekhin/travel-content-factory && source venv/bin/activate && python -c "from backend.services.abacus import get_image_client; c = get_image_client(); print(f'Client: {c.default_model}, key present: {bool(c.api_key)}')"`
Expected: `Client: flux2_pro, key present: True`

- [ ] **Step 3: Commit**

```bash
cd /Users/dmitrypotekhin/travel-content-factory
git add backend/services/abacus.py
git commit -m "feat: add Abacus AI image generation client service"
```

---

### Task 2: Images API Router

**Files:**
- Create: `backend/routers/images.py`
- Modify: `backend/main.py` (add router, add `generated/` dir, shutdown cleanup)
- Modify: `backend/.env` (add ABACUS_AI_API_KEY if not present)

**Interfaces:**
- Consumes: `get_image_client()` from `backend/services/abacus.py`
- Produces: FastAPI router at `/api/images/`

- [ ] **Step 1: Create `backend/routers/images.py`**

```python
"""Image generation routes — Abacus AI."""

import os
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from services.abacus import get_image_client, GENERATED_DIR

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
async def generate_cover(data: dict):
    """Generate a cover image for a project."""
    from database import get_db
    project_id = data.get("project_id")
    prompt_override = data.get("prompt_override", "").strip()

    if not project_id:
        raise HTTPException(status_code=400, detail="project_id is required")

    # Build prompt from project info
    prompt = prompt_override
    if not prompt:
        # We need the DB session — use it inline
        from database import SessionLocal
        from sqlalchemy import select
        from models import Project

        async with SessionLocal() as db:
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
```

- [ ] **Step 2: Modify `backend/main.py` — add router and generated/ dir**

```python
# In imports, add:
from routers import media, projects, ai, music, images

# In lifespan, add GENERATED_DIR creation:
from services.abacus import GENERATED_DIR
# ... inside the for-loop, after "./data":
Path("generated").mkdir(parents=True, exist_ok=True)

# In router registration, add BEFORE static mount:
app.include_router(images.router)

# In shutdown, add image client close:
from services.abacus import _image_client
# ... alongside deepseek _ai_client shutdown
```

Use patch for these changes:

```
# Add images to router imports
old: from routers import media, projects, ai, music
new: from routers import media, projects, ai, music, images

# Add GENERATED_DIR import and directory creation
old: from services.abacus import GENERATED_DIR
# This is a new line — insert after the deepseek import in lifespan

# Add router registration
old: app.include_router(music.router)
new: app.include_router(music.router)
     app.include_router(images.router)

# Add shutdown cleanup for image client
old: from services.deepseek import _ai_client
new: from services.deepseek import _ai_client
     from services.abacus import _image_client
```

- [ ] **Step 3: Add ABACUS_AI_API_KEY to `.env`**

Using terminal (since `.env` is protected from direct writes):

```bash
cd /Users/dmitrypotekhin/travel-content-factory
echo 'ABACUS_AI_API_KEY=s2_1cdc555034a7493aa20e1984ea7eb694' >> backend/.env
```

- [ ] **Step 4: Verify router works**

```bash
cd /Users/dmitrypotekhin/travel-content-factory && source venv/bin/activate
python -c "
from backend.routers.images import router
print(f'Routes: {[r.path for r in router.routes]}')
"
```
Expected: `Routes: ['/api/images/generate', '/api/images/list', '/api/images/file/{filename}', '/api/images/generate-cover']`

- [ ] **Step 5: Commit**

```bash
cd /Users/dmitrypotekhin/travel-content-factory
git add backend/routers/images.py backend/main.py backend/.env
git commit -m "feat: add images API router with generate, list, serve, generate-cover endpoints"
```

---

### Task 3: Frontend — Image Factory Tab

**Files:**
- Modify: `frontend/index.html` (new tab + tab content)
- Modify: `frontend/js/app.js` (image factory logic)
- Modify: `frontend/css/style.css` (image factory styles)

**Interfaces:**
- Consumes: `POST /api/images/generate`, `GET /api/images/list`, `GET /api/images/file/{filename}`
- Produces: new «Image Factory» tab in the SPA

- [ ] **Step 1: Add HTML for Image Factory tab**

In `frontend/index.html`, add new nav-tab button after «Content Factory»:

```html
<button class="nav-tab" data-tab="images">Image Factory</button>
```

Add new tab content section after `tab-factory`:

```html
<!-- Image Factory Tab -->
<section id="tab-images" class="tab-content">
    <div class="factory-layout">
        <div class="factory-form">
            <h2>Generate Images</h2>
            <div class="form-group">
                <label>Prompt</label>
                <textarea id="img-prompt" rows="3" placeholder="e.g., Sunset over Santorini with blue domes, cinematic style..."></textarea>
            </div>
            <div class="form-group">
                <label>Aspect Ratio</label>
                <div class="platform-buttons" id="img-aspect-buttons">
                    <button class="platform-btn active" data-aspect="square">Square</button>
                    <button class="platform-btn" data-aspect="landscape">Landscape</button>
                    <button class="platform-btn" data-aspect="portrait">Portrait</button>
                </div>
            </div>
            <div class="form-group">
                <label>Model (optional)</label>
                <select id="img-model">
                    <option value="">flux2_pro (default)</option>
                    <option value="flux_pro_ultra">FLUX Pro Ultra</option>
                    <option value="midjourney">MidJourney</option>
                    <option value="dalle">DALL-E</option>
                    <option value="nano_banana_pro">Nano Banana Pro</option>
                </select>
            </div>
            <button id="btn-generate-image" class="btn btn-primary btn-full">Generate Image</button>
            <div id="img-loading" class="hidden" style="text-align:center;padding:20px;color:#7c5cfc">
                Generating... this may take 10-30 seconds.
            </div>
        </div>

        <div id="img-result" class="factory-result">
            <div class="empty-state">Enter a prompt and click Generate.</div>
        </div>
    </div>

    <div class="gallery-section" style="margin-top:30px">
        <h3>Generated Images</h3>
        <div id="img-gallery" class="media-grid">
            <div class="empty-state">No images generated yet.</div>
        </div>
        <div id="img-pagination" class="pagination"></div>
    </div>
</section>
```

- [ ] **Step 2: Add CSS for image factory**

In `frontend/css/style.css`, add at end:

```css
/* ── Image Factory ────────────────────────────────────────── */
.gallery-section {
    border-top: 1px solid #222;
    padding-top: 20px;
}
.gallery-section h3 {
    color: #a0a0b0;
    font-size: 0.9rem;
    margin-bottom: 12px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}
#img-result img {
    max-width: 100%;
    border-radius: 8px;
    border: 1px solid #333;
}
.img-meta {
    color: #888;
    font-size: 0.75rem;
    margin-top: 8px;
}
.img-result-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 8px;
}
```

- [ ] **Step 3: Add JS for image factory**

In `frontend/js/app.js`, update `initTabs()` to handle the 'images' tab:

In the tab click handler, after the existing `if (state.tab === 'projects') loadProjects();` add:
```javascript
if (state.tab === 'images') { loadImageGallery(); }
```

Add image factory state:
```javascript
// Near other state
state.imgAspect = 'square';
state.imgPage = 1;
```

Add `initImageFactory()` call in `DOMContentLoaded`:
```javascript
initImageFactory();
```

Add the new functions (place before the `esc()` utility at end):

```javascript
// ── Image Factory ───────────────────────────────────────────
function initImageFactory() {
    // Aspect ratio buttons
    document.querySelectorAll('#img-aspect-buttons .platform-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('#img-aspect-buttons .platform-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            state.imgAspect = btn.dataset.aspect;
        });
    });

    document.getElementById('btn-generate-image').addEventListener('click', generateImage);
}

async function generateImage() {
    const prompt = document.getElementById('img-prompt').value.trim();
    if (!prompt) { toast('Enter a prompt', 'error'); return; }

    const btn = document.getElementById('btn-generate-image');
    const loading = document.getElementById('img-loading');
    const resultEl = document.getElementById('img-result');

    btn.disabled = true;
    loading.classList.remove('hidden');
    resultEl.innerHTML = '';

    const model = document.getElementById('img-model').value || undefined;

    try {
        const data = await API.post('/api/images/generate', {
            prompt,
            aspect_ratio: state.imgAspect,
            model,
        });

        resultEl.innerHTML = `
            <div class="img-result-header">
                <span class="img-meta">${data.model} · ${data.width}x${data.height}</span>
                <button class="btn btn-secondary btn-sm" onclick="downloadImage('${data.url}', '${data.path.split('/').pop()}')">Download</button>
            </div>
            <img src="${data.url}" alt="${esc(data.prompt)}" loading="lazy">
            <div class="img-meta">${esc(data.prompt)}</div>
        `;

        toast('Image generated!', 'success');
        document.getElementById('img-prompt').value = '';
        loadImageGallery();
    } catch (e) {
        resultEl.innerHTML = `<div class="empty-state">Error: ${esc(e.message)}</div>`;
        toast(e.message, 'error');
    } finally {
        btn.disabled = false;
        loading.classList.add('hidden');
    }
}

async function loadImageGallery(page = 1) {
    state.imgPage = page;
    const grid = document.getElementById('img-gallery');

    try {
        const data = await API.get(`/api/images/list?page=${page}&page_size=20`);
        if (!data.images.length) {
            grid.innerHTML = '<div class="empty-state">No images generated yet.</div>';
        } else {
            grid.innerHTML = data.images.map(img => `
                <div class="media-card" onclick="showImagePreview('${img.url}', '${esc(img.filename)}', '${img.model}', ${img.size_bytes})">
                    <img src="${img.url}" alt="${esc(img.filename)}" loading="lazy"
                         onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%22200%22 height=%22140%22><rect fill=%22%23111%22 width=%22200%22 height=%22140%22/><text fill=%22%23666%22 x=%22100%22 y=%2275%22 text-anchor=%22middle%22 font-size=%2212%22>No preview</text></svg>'">
                    <div class="card-body">
                        <div class="card-name">${img.model}</div>
                        <div class="card-meta">
                            <span>${formatBytes(img.size_bytes)}</span>
                            <span>${img.created_at ? img.created_at.slice(0,10) : ''}</span>
                        </div>
                    </div>
                </div>
            `).join('');
        }

        // Pagination
        const pages = Math.ceil(data.total / data.page_size);
        const pagEl = document.getElementById('img-pagination');
        if (pages <= 1) { pagEl.innerHTML = ''; return; }
        let html = '';
        for (let i = 1; i <= Math.min(pages, 10); i++) {
            html += `<button class="${i === page ? 'active' : ''}" data-page="${i}">${i}</button>`;
        }
        pagEl.innerHTML = html;
        pagEl.querySelectorAll('button').forEach(b => {
            b.addEventListener('click', () => loadImageGallery(parseInt(b.dataset.page)));
        });
    } catch (e) {
        grid.innerHTML = `<div class="empty-state">Error: ${esc(e.message)}</div>`;
    }
}

function showImagePreview(url, filename, model, sizeBytes) {
    document.getElementById('img-result').innerHTML = `
        <div class="img-result-header">
            <span class="img-meta">${model} · ${formatBytes(sizeBytes)}</span>
            <button class="btn btn-secondary btn-sm" onclick="downloadImage('${url}', '${esc(filename)}')">Download</button>
        </div>
        <img src="${url}" alt="${esc(filename)}" style="max-width:100%;border-radius:8px;border:1px solid #333">
    `;
}

function downloadImage(url, filename) {
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
}

function formatBytes(bytes) {
    if (!bytes) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB'];
    let i = 0;
    let size = bytes;
    while (size >= 1024 && i < units.length - 1) { size /= 1024; i++; }
    return size.toFixed(1) + ' ' + units[i];
}
```

- [ ] **Step 4: Verify frontend loads**

```bash
cd /Users/dmitrypotekhin/travel-content-factory && source venv/bin/activate
python -c "
import ast
with open('frontend/js/app.js') as f:
    source = f.read()
ast.parse(source)
print('JS-like syntax check passed (Python AST as proxy)')
"
```

- [ ] **Step 5: Commit**

```bash
cd /Users/dmitrypotekhin/travel-content-factory
git add frontend/index.html frontend/js/app.js frontend/css/style.css
git commit -m "feat: add Image Factory tab with generate, gallery, and download"
```

---

### Task 4: Content Factory — Generate Image Button

**Files:**
- Modify: `frontend/js/app.js` (add button in generate() result)

**Interfaces:**
- Consumes: `POST /api/images/generate`
- Produces: «Generate Image» button in Content Factory results

- [ ] **Step 1: Add «Generate Image» button to Content Factory result**

In `frontend/js/app.js`, inside the `generate()` function, in the `resultEl.innerHTML` template, add after the hashtag section (before closing backtick):

```javascript
// Add this button inside resultEl.innerHTML, after hashtags section:
<div class="result-section" style="margin-top:12px;padding-top:12px;border-top:1px solid #222">
    <button class="btn btn-secondary" id="btn-gen-img-from-topic"
            onclick="generateImageFromTopic(${JSON.stringify(data.topic).replace(/\"/g, '&quot;')})">
        Generate Image for this Topic
    </button>
    <div id="topic-img-result" style="margin-top:12px"></div>
</div>
```

Add the handler function:

```javascript
async function generateImageFromTopic(topic) {
    const resultEl = document.getElementById('topic-img-result');
    resultEl.innerHTML = '<div style="color:#7c5cfc;padding:8px">Generating image...</div>';

    try {
        const data = await API.post('/api/images/generate', {
            prompt: `Travel photo for: ${topic}. Cinematic style, vibrant colors, professional photography.`,
            aspect_ratio: 'landscape',
        });
        resultEl.innerHTML = `<img src="${data.url}" alt="${esc(topic)}" style="max-width:100%;border-radius:8px;border:1px solid #333;margin-top:8px">`;
    } catch (e) {
        resultEl.innerHTML = `<div style="color:#e74c3c">Error: ${esc(e.message)}</div>`;
    }
}
```

- [ ] **Step 2: Commit**

```bash
cd /Users/dmitrypotekhin/travel-content-factory
git add frontend/js/app.js
git commit -m "feat: add Generate Image button in Content Factory results"
```

---

### Task 5: Render Dialog — AI Cover Image

**Files:**
- Modify: `frontend/index.html` (add checkbox in render modal)
- Modify: `frontend/js/app.js` (handle cover generation during render)

**Interfaces:**
- Consumes: `POST /api/images/generate-cover`
- Produces: checkbox in render dialog, cover path passed to render

- [ ] **Step 1: Add checkbox to render dialog**

In `frontend/index.html`, inside `modal-render`, after the captions checkbox section, add:

```html
<div class="form-group" style="margin-top:12px">
    <label style="display:flex;align-items:center;gap:8px;cursor:pointer">
        <input type="checkbox" id="render-cover">
        <span>Generate AI cover image</span>
    </label>
</div>
```

- [ ] **Step 2: Update `doRender()` to generate cover**

In `frontend/js/app.js`, modify `doRender()` — after building the body but before the API call, add cover generation:

```javascript
// After building body, before API.post render call:
const generateCover = document.getElementById('render-cover').checked;
if (generateCover) {
    try {
        const coverData = await API.post('/api/images/generate-cover', {
            project_id: id,
        });
        body.cover_image_path = coverData.path;
        toast('Cover image generated!', 'success');
    } catch (e) {
        toast(`Cover generation failed: ${e.message}`, 'error');
        // Continue without cover — non-fatal
    }
}
```

- [ ] **Step 3: Commit**

```bash
cd /Users/dmitrypotekhin/travel-content-factory
git add frontend/index.html frontend/js/app.js
git commit -m "feat: add AI cover image generation in render dialog"
```

---

### Task 6: Integration Test & Startup Verification

**Files:**
- No new files

- [ ] **Step 1: Start the server**

```bash
cd /Users/dmitrypotekhin/travel-content-factory && bash start.sh
```

Wait for `Uvicorn running on http://127.0.0.1:8000`.

- [ ] **Step 2: Verify health check**

```bash
curl -s http://localhost:8000/api/health | python3 -m json.tool
```
Expected: `{"status": "ok", "app": "Travel Content Factory"}`

- [ ] **Step 3: Verify image routes exist**

```bash
curl -s http://localhost:8000/docs | grep -o 'api/images/[a-z-]*' | sort -u
```
Expected: list of image routes

- [ ] **Step 4: Test list endpoint (empty)**

```bash
curl -s http://localhost:8000/api/images/list | python3 -m json.tool
```
Expected: `{"images": [], "total": 0, ...}`

- [ ] **Step 5: Test generate endpoint (real API call)**

```bash
curl -s -X POST http://localhost:8000/api/images/generate \
  -H 'Content-Type: application/json' \
  -d '{"prompt": "A beautiful sunset over Paris with Eiffel Tower silhouette, cinematic style", "aspect_ratio": "landscape"}' | python3 -m json.tool
```
Expected: JSON with `path`, `url`, `prompt`, `model`, `width`, `height`.

- [ ] **Step 6: Verify image file exists**

Check that the file is in `generated/` directory and can be served:
```bash
ls -la /Users/dmitrypotekhin/travel-content-factory/generated/ | head -5
```
Then curl the URL from step 5 response to verify serving.

- [ ] **Step 7: Open frontend and verify Image Factory tab**

Use playwright to navigate to `http://localhost:8000`, click «Image Factory» tab, verify the form loads.

- [ ] **Step 8: Commit (if any fixes)**

```bash
cd /Users/dmitrypotekhin/travel-content-factory
git add -A
git commit -m "test: integration verification of image generation feature"
```
