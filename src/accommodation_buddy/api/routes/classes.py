from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from accommodation_buddy.api.deps import get_current_teacher
from accommodation_buddy.db.models import Class, Teacher
from accommodation_buddy.db.session import get_db

router = APIRouter(prefix="/classes", tags=["classes"])


@router.get("", response_class=HTMLResponse)
async def list_classes(
    request: Request,
    teacher: Teacher = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db),
):
    if teacher is None:
        return RedirectResponse("/login", status_code=303)

    result = await db.execute(
        select(Class)
        .where(Class.teacher_id == teacher.id)
        .options(selectinload(Class.students))
        .order_by(Class.created_at.desc())
    )
    classes = result.scalars().all()

    templates = request.app.state.templates
    return templates.TemplateResponse(
        "classes.html",
        {"request": request, "teacher": teacher, "classes": classes},
    )


@router.post("")
async def create_class(
    name: str = Form(...),
    grade_level: str = Form(""),
    teacher: Teacher = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db),
):
    if teacher is None:
        return RedirectResponse("/login", status_code=303)

    new_class = Class(
        teacher_id=teacher.id,
        name=name,
        grade_level=grade_level or None,
    )
    db.add(new_class)
    await db.commit()
    return RedirectResponse("/classes", status_code=303)


@router.get("/{class_id}", response_class=HTMLResponse)
async def view_class(
    request: Request,
    class_id: int,
    teacher: Teacher = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db),
):
    if teacher is None:
        return RedirectResponse("/login", status_code=303)

    result = await db.execute(
        select(Class)
        .where(Class.id == class_id, Class.teacher_id == teacher.id)
        .options(selectinload(Class.students), selectinload(Class.documents))
    )
    class_obj = result.scalar_one_or_none()
    if class_obj is None:
        return RedirectResponse("/classes", status_code=303)

    templates = request.app.state.templates
    return templates.TemplateResponse(
        "class_detail.html",
        {"request": request, "teacher": teacher, "class_obj": class_obj},
    )


@router.post("/{class_id}/delete")
async def delete_class(
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
    if class_obj:
        await db.delete(class_obj)
        await db.commit()
    return RedirectResponse("/classes", status_code=303)
