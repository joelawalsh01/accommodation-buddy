import logging

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from accommodation_buddy.api.deps import get_current_teacher
from accommodation_buddy.config import settings
from accommodation_buddy.db.models import Teacher
from accommodation_buddy.db.session import get_db
from accommodation_buddy.services.model_settings import (
    get_teacher_model_settings,
    save_teacher_model_settings,
)
from accommodation_buddy.services.ollama_client import OllamaClient

logger = logging.getLogger(__name__)

router = APIRouter(tags=["settings"])


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(
    request: Request,
    saved: str | None = None,
    teacher: Teacher = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db),
):
    if teacher is None:
        return RedirectResponse("/login", status_code=303)

    resolved = await get_teacher_model_settings(teacher.id, db)

    client = OllamaClient()
    available_models: list[dict] = []
    running_models: list[dict] = []
    ollama_online = False

    try:
        available_models = await client.list_models()
        running_models = await client.list_running_models()
        ollama_online = True
    except Exception:
        logger.warning("Ollama is not reachable — settings page will show offline warning")

    templates = request.app.state.templates
    return templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "teacher": teacher,
            "resolved": resolved,
            "available_models": available_models,
            "running_models": running_models,
            "ollama_online": ollama_online,
            "system_defaults": {
                "scaffolding": settings.scaffolding_model,
                "ocr": settings.ocr_model,
                "translation": settings.translation_model,
            },
            "saved": saved == "1",
        },
    )


@router.post("/settings/save")
async def save_settings(
    request: Request,
    scaffolding_model: str = Form(""),
    ocr_model: str = Form(""),
    translation_model: str = Form(""),
    keep_alive: str = Form("5m"),
    teacher: Teacher = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db),
):
    if teacher is None:
        return RedirectResponse("/login", status_code=303)

    await save_teacher_model_settings(
        teacher_id=teacher.id,
        db=db,
        scaffolding_model=scaffolding_model if scaffolding_model else None,
        ocr_model=ocr_model if ocr_model else None,
        translation_model=translation_model if translation_model else None,
        keep_alive=keep_alive,
    )

    return RedirectResponse("/settings?saved=1", status_code=303)


@router.get("/settings/running-models", response_class=HTMLResponse)
async def running_models_fragment(
    request: Request,
    teacher: Teacher = Depends(get_current_teacher),
):
    if teacher is None:
        return HTMLResponse("", status_code=401)

    client = OllamaClient()
    try:
        models = await client.list_running_models()
    except Exception:
        return HTMLResponse(
            '<p class="text-muted">Ollama is offline</p>'
        )

    if not models:
        return HTMLResponse(
            '<p class="text-muted">No models currently loaded in memory.</p>'
        )

    rows = []
    for m in models:
        name = m.get("name", "unknown")
        size_bytes = m.get("size", 0)
        size_gb = f"{size_bytes / (1024**3):.1f} GB" if size_bytes else "—"
        rows.append(
            f'<tr>'
            f'<td><strong>{name}</strong></td>'
            f'<td>{size_gb}</td>'
            f'<td>'
            f'<button class="btn btn-xs btn-danger" '
            f'hx-post="/settings/unload-model" '
            f'hx-vals=\'{{"model_name": "{name}"}}\' '
            f'hx-target="#running-models" '
            f'hx-swap="innerHTML">'
            f'Unload</button>'
            f'</td>'
            f'</tr>'
        )

    html = (
        '<table class="mini-table">'
        '<thead><tr><th>Model</th><th>Size</th><th></th></tr></thead>'
        '<tbody>' + ''.join(rows) + '</tbody>'
        '</table>'
    )
    return HTMLResponse(html)


@router.post("/settings/unload-model", response_class=HTMLResponse)
async def unload_model(
    request: Request,
    model_name: str = Form(""),
    teacher: Teacher = Depends(get_current_teacher),
):
    if teacher is None:
        return HTMLResponse("", status_code=401)

    client = OllamaClient()
    try:
        await client.unload_model(model_name)
    except Exception:
        logger.exception(f"Failed to unload model {model_name}")

    # Return updated running models list
    return await running_models_fragment(request=request, teacher=teacher)
