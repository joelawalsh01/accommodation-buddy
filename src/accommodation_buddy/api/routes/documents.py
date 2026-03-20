import logging
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from accommodation_buddy.api.deps import get_current_teacher, get_feature_manager, get_panel_host
from accommodation_buddy.config import settings
from accommodation_buddy.core.feature_manager import FeatureManager
from accommodation_buddy.core.panel_host import PanelHost
from accommodation_buddy.core.registry import PluginRegistry
from accommodation_buddy.db.models import Accommodation, Class, Document, Student, Teacher
from accommodation_buddy.db.session import get_db
from accommodation_buddy.services.document_parser import detect_file_type
from accommodation_buddy.services.model_settings import get_teacher_model_settings
from accommodation_buddy.tasks.plugin_tasks import process_document_ocr, run_plugin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("/{class_id}", response_class=HTMLResponse)
async def document_list(
    request: Request,
    class_id: int,
    teacher: Teacher = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db),
):
    if teacher is None:
        return RedirectResponse("/login", status_code=303)

    result = await db.execute(
        select(Class).where(Class.id == class_id, Class.teacher_id == teacher.id)
    )
    class_obj = result.scalar_one_or_none()
    if class_obj is None:
        return RedirectResponse("/classes", status_code=303)

    docs_result = await db.execute(
        select(Document)
        .where(Document.class_id == class_id)
        .order_by(Document.created_at.desc())
    )
    documents = docs_result.scalars().all()

    templates = request.app.state.templates
    return templates.TemplateResponse(
        "documents.html",
        {
            "request": request,
            "teacher": teacher,
            "class_obj": class_obj,
            "documents": documents,
        },
    )


@router.post("/{class_id}/upload")
async def upload_document(
    class_id: int,
    file: UploadFile = File(...),
    ocr_mode: str = Form("fast"),
    teacher: Teacher = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db),
):
    if teacher is None:
        return RedirectResponse("/login", status_code=303)

    result = await db.execute(
        select(Class).where(Class.id == class_id, Class.teacher_id == teacher.id)
    )
    if result.scalar_one_or_none() is None:
        return RedirectResponse("/classes", status_code=303)

    # Save file
    upload_dir = Path(settings.upload_dir) / str(class_id)
    upload_dir.mkdir(parents=True, exist_ok=True)

    file_ext = Path(file.filename).suffix
    safe_name = f"{uuid.uuid4().hex}{file_ext}"
    file_path = upload_dir / safe_name

    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    file_type = detect_file_type(file.filename)
    doc = Document(
        class_id=class_id,
        teacher_id=teacher.id,
        filename=file.filename,
        file_path=str(file_path),
        file_type=file_type,
        ocr_status="pending",
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    # Dispatch OCR task
    process_document_ocr.delay(doc.id, teacher.id, ocr_mode)

    return RedirectResponse(f"/documents/{class_id}", status_code=303)


@router.post("/{class_id}/{document_id}/cancel")
async def cancel_document_ocr(
    class_id: int,
    document_id: int,
    teacher: Teacher = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db),
):
    if teacher is None:
        return RedirectResponse("/login", status_code=303)

    doc = await db.get(Document, document_id)
    if doc is None or doc.class_id != class_id or doc.teacher_id != teacher.id:
        return RedirectResponse(f"/documents/{class_id}", status_code=303)

    if doc.ocr_status in ("pending", "processing"):
        doc.ocr_status = "failed"
        doc.status_detail = "Cancelled by user"
        doc.ocr_progress = 0
        await db.commit()

    return RedirectResponse(f"/documents/{class_id}", status_code=303)


@router.post("/{class_id}/{document_id}/delete")
async def delete_document(
    class_id: int,
    document_id: int,
    teacher: Teacher = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db),
):
    if teacher is None:
        return RedirectResponse("/login", status_code=303)

    doc = await db.get(Document, document_id)
    if doc is None or doc.class_id != class_id or doc.teacher_id != teacher.id:
        return RedirectResponse(f"/documents/{class_id}", status_code=303)

    # Delete the uploaded file
    try:
        file_path = Path(doc.file_path)
        if file_path.exists():
            file_path.unlink()
    except Exception:
        logger.warning(f"Could not delete file {doc.file_path}")

    # Delete associated accommodations
    acc_result = await db.execute(
        select(Accommodation).where(Accommodation.document_id == document_id)
    )
    for acc in acc_result.scalars().all():
        await db.delete(acc)

    await db.delete(doc)
    await db.commit()

    return RedirectResponse(f"/documents/{class_id}", status_code=303)


@router.get("/{class_id}/status/{document_id}", response_class=HTMLResponse)
async def document_status_row(
    request: Request,
    class_id: int,
    document_id: int,
    teacher: Teacher = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db),
):
    """Return a single table row HTML for HTMX polling."""
    if teacher is None:
        return HTMLResponse("", status_code=401)

    doc = await db.get(Document, document_id)
    if doc is None or doc.class_id != class_id:
        return HTMLResponse("", status_code=404)

    # Determine if we should keep polling
    is_terminal = doc.ocr_status in ("complete", "failed")
    hx_attrs = ""
    if not is_terminal:
        hx_attrs = (
            f'hx-get="/documents/{class_id}/status/{document_id}" '
            f'hx-trigger="every 2s" hx-swap="outerHTML"'
        )

    # Progress bar HTML
    progress_html = ""
    if doc.ocr_status == "processing" and doc.ocr_progress is not None:
        progress_html = (
            f'<div class="progress-bar-container">'
            f'<div class="progress-bar" style="width: {doc.ocr_progress}%"></div>'
            f'<span class="progress-text">{doc.ocr_progress}%</span>'
            f'</div>'
        )

    # Elapsed time
    elapsed_html = ""
    if doc.created_at:
        import datetime
        now = datetime.datetime.now(datetime.timezone.utc)
        created = doc.created_at if doc.created_at.tzinfo else doc.created_at.replace(tzinfo=datetime.timezone.utc)
        elapsed_secs = int((now - created).total_seconds())
        if elapsed_secs >= 0:
            minutes, secs = divmod(elapsed_secs, 60)
            time_str = f"{minutes}m {secs}s" if minutes else f"{secs}s"
            if not is_terminal:
                elapsed_html = f'<div class="status-detail">Elapsed: {time_str}</div>'

    # Status detail
    detail_html = ""
    if doc.status_detail:
        detail_html = f'<div class="status-detail">{doc.status_detail}</div>'

    # Action column
    delete_btn = (
        f'<form method="post" action="/documents/{class_id}/{doc.id}/delete" '
        f'style="display:inline" onsubmit="return confirm(\'Delete this document?\')">'
        f'<button type="submit" class="btn btn-sm btn-danger">Delete</button></form>'
    )
    if doc.ocr_status == "complete":
        action = f'<a href="/documents/{class_id}/{doc.id}" class="btn btn-sm btn-primary">View &amp; Accommodate</a> {delete_btn}'
    elif doc.ocr_status == "failed":
        action = f'<span class="text-error">Failed</span> {delete_btn}'
    else:
        cancel_btn = (
            f'<form method="post" action="/documents/{class_id}/{doc.id}/cancel" '
            f'style="display:inline">'
            f'<button type="submit" class="btn btn-sm btn-warning">Cancel</button></form>'
        )
        processing_label = doc.status_detail if (doc.status_detail and "page" in doc.status_detail) else "Processing"
        action = f'<span class="text-muted processing-indicator"><span class="spinner"></span> {processing_label}</span> {cancel_btn} {delete_btn}'

    created = doc.created_at.strftime('%Y-%m-%d %H:%M') if doc.created_at else ''

    html = (
        f'<tr id="doc-row-{doc.id}" {hx_attrs}>'
        f'<td>{doc.filename}</td>'
        f'<td><span class="badge">{doc.file_type}</span></td>'
        f'<td class="status-cell">'
        f'<span class="status-badge status-{doc.ocr_status}">{doc.ocr_status}</span>'
        f'{detail_html}{elapsed_html}{progress_html}'
        f'</td>'
        f'<td>{created}</td>'
        f'<td class="actions-cell">{action}</td>'
        f'</tr>'
    )
    return HTMLResponse(html)


@router.get("/{class_id}/{document_id}", response_class=HTMLResponse)
async def document_view(
    request: Request,
    class_id: int,
    document_id: int,
    student_id: int | None = None,
    teacher: Teacher = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db),
    panel_host: PanelHost = Depends(get_panel_host),
):
    if teacher is None:
        return RedirectResponse("/login", status_code=303)

    doc = await db.get(Document, document_id)
    if doc is None or doc.class_id != class_id:
        return RedirectResponse(f"/documents/{class_id}", status_code=303)

    # Get students for the student picker
    students_result = await db.execute(
        select(Student).where(Student.class_id == class_id).order_by(Student.pseudonym)
    )
    students = students_result.scalars().all()

    # Get existing accommodations for this document
    acc_result = await db.execute(
        select(Accommodation).where(
            Accommodation.document_id == document_id,
            Accommodation.target_student_id == student_id if student_id else True,
        )
    )
    accommodations = {a.plugin_id: a for a in acc_result.scalars().all()}

    # Render sidebar panels
    panels = await panel_host.render_sidebar(document_id, class_id, student_id, db)

    templates = request.app.state.templates
    return templates.TemplateResponse(
        "document_view.html",
        {
            "request": request,
            "teacher": teacher,
            "document": doc,
            "class_id": class_id,
            "students": students,
            "selected_student_id": student_id,
            "panels": panels,
            "accommodations": accommodations,
        },
    )


@router.post("/api/plugins/{plugin_id}/run", response_class=HTMLResponse)
async def run_plugin_endpoint(
    request: Request,
    plugin_id: str,
    document_id: int = Form(...),
    student_id: str | None = Form(None),
    class_id: int = Form(...),
    custom_text: str | None = Form(None),
    grade_level: str | None = Form(None),
    teacher: Teacher = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db),
):
    # Coerce empty strings to None
    student_id = int(student_id) if student_id and student_id.strip() else None
    grade_level = grade_level if grade_level and grade_level.strip() else None
    custom_text = custom_text if custom_text and custom_text.strip() else None

    if teacher is None:
        return HTMLResponse("<div class='error'>Not authenticated</div>", status_code=401)

    registry = PluginRegistry.get_instance()
    plugin = registry.get(plugin_id)
    if plugin is None:
        return HTMLResponse(f"<div class='error'>Plugin {plugin_id} not found</div>", status_code=404)

    # Run synchronously for HTMX response (or dispatch to Celery for long tasks)
    from accommodation_buddy.core.base_plugin import ClassProfile, StudentProfile

    doc = await db.get(Document, document_id)
    if doc is None:
        return HTMLResponse("<div class='error'>Document not found</div>", status_code=404)

    student_profile = None
    if student_id:
        student = await db.get(Student, student_id)
        if student:
            student_profile = StudentProfile(
                id=student.id,
                pseudonym=student.pseudonym,
                heritage_language=student.heritage_language,
                english_proficiency_level=student.english_proficiency_level,
                l1_proficiency_level=student.l1_proficiency_level,
                proficiency_notes=student.proficiency_notes,
            )

    class_obj = await db.get(Class, class_id)
    class_profile = ClassProfile(
        id=class_obj.id, name=class_obj.name, grade_level=class_obj.grade_level
    ) if class_obj else None

    model_settings = await get_teacher_model_settings(teacher.id, db)

    # Use custom text if provided (e.g., selected text for translation)
    text_to_process = custom_text.strip() if custom_text and custom_text.strip() else (doc.extracted_text or "")

    plugin_options = {"_model_settings": model_settings}
    if grade_level:
        plugin_options["grade_level"] = grade_level

    try:
        result = await plugin.generate(
            document_text=text_to_process,
            student_profile=student_profile,
            class_profile=class_profile,
            options=plugin_options,
        )

        # Save accommodation
        accommodation = Accommodation(
            document_id=document_id,
            plugin_id=plugin_id,
            target_student_id=student_id,
            input_context={"document_text_length": len(doc.extracted_text or "")},
            generated_output=result.generated_output,
            status=result.status,
        )
        db.add(accommodation)
        await db.commit()

        # Render the plugin's panel with results
        from accommodation_buddy.core.panel_host import PanelHost
        from accommodation_buddy.core.feature_manager import FeatureManager

        jinja_env = request.app.state.templates.env
        manifest = plugin.manifest()
        if manifest.panel_template:
            template = jinja_env.get_template(manifest.panel_template)
            html = template.render(
                plugin_id=manifest.id,
                plugin_name=manifest.name,
                plugin_icon=manifest.icon,
                document_id=document_id,
                student_id=student_id,
                class_id=class_id,
                result=result.generated_output,
                accommodation=accommodation,
            )
            return HTMLResponse(html)

        return HTMLResponse(f"<div class='success'>Generated successfully</div>")
    except Exception as e:
        return HTMLResponse(f"<div class='error'>Error: {e}</div>", status_code=500)


@router.post("/api/plugins/run-all")
async def run_all_plugins(
    document_id: int = Form(...),
    student_id: int | None = Form(None),
    class_id: int = Form(...),
    teacher: Teacher = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db),
    feature_manager: FeatureManager = Depends(get_feature_manager),
):
    if teacher is None:
        return HTMLResponse("<div class='error'>Not authenticated</div>", status_code=401)

    enabled = await feature_manager.get_enabled_plugins(class_id, db)
    task_ids = []
    for manifest in enabled:
        if manifest.always_on or not manifest.requires_document:
            continue
        task = run_plugin.delay(manifest.id, document_id, student_id, None, teacher.id)
        task_ids.append({"plugin_id": manifest.id, "task_id": task.id})

    return {"status": "dispatched", "tasks": task_ids}


@router.post("/api/accommodations/{accommodation_id}/status")
async def update_accommodation_status(
    accommodation_id: int,
    status: str = Form(...),
    revised_text: str | None = Form(None),
    teacher: Teacher = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db),
):
    if teacher is None:
        return HTMLResponse("<div class='error'>Not authenticated</div>", status_code=401)

    acc = await db.get(Accommodation, accommodation_id)
    if acc is None:
        return HTMLResponse("<div class='error'>Not found</div>", status_code=404)

    if status in ("accepted", "revised", "rejected"):
        acc.status = status
        if revised_text:
            acc.revised_text = revised_text
        await db.commit()

    return HTMLResponse(f'<span class="badge badge-{status}">{status}</span>')
