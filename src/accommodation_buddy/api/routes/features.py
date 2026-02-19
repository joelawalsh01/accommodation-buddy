from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from accommodation_buddy.api.deps import get_current_teacher, get_feature_manager
from accommodation_buddy.core.feature_manager import FeatureManager
from accommodation_buddy.db.models import Class, Teacher
from accommodation_buddy.db.session import get_db

router = APIRouter(prefix="/features", tags=["features"])


@router.get("/{class_id}", response_class=HTMLResponse)
async def feature_manager_page(
    request: Request,
    class_id: int,
    teacher: Teacher = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db),
    feature_manager: FeatureManager = Depends(get_feature_manager),
):
    if teacher is None:
        return RedirectResponse("/login", status_code=303)

    class_obj = await db.get(Class, class_id)
    if class_obj is None or class_obj.teacher_id != teacher.id:
        return RedirectResponse("/classes", status_code=303)

    toggles = await feature_manager.get_toggle_state(class_id, db)

    # Group by category
    categories = {}
    for t in toggles:
        cat = t.category
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(t)

    templates = request.app.state.templates
    return templates.TemplateResponse(
        "feature_manager.html",
        {
            "request": request,
            "teacher": teacher,
            "class_obj": class_obj,
            "categories": categories,
        },
    )


@router.post("/{class_id}/toggle", response_class=HTMLResponse)
async def toggle_feature(
    request: Request,
    class_id: int,
    plugin_id: str = Form(...),
    enabled: bool = Form(False),
    teacher: Teacher = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db),
    feature_manager: FeatureManager = Depends(get_feature_manager),
):
    if teacher is None:
        return HTMLResponse("Unauthorized", status_code=401)

    await feature_manager.set_enabled(class_id, plugin_id, enabled, db)

    status = "enabled" if enabled else "disabled"
    return HTMLResponse(
        f'<span class="toggle-status" id="status-{plugin_id}">{status}</span>'
    )
