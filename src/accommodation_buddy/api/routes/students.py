from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from accommodation_buddy.api.deps import get_current_teacher
from accommodation_buddy.db.models import Class, Student, Teacher
from accommodation_buddy.db.session import get_db

router = APIRouter(prefix="/students", tags=["students"])


@router.get("/{class_id}", response_class=HTMLResponse)
async def student_list(
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

    students_result = await db.execute(
        select(Student).where(Student.class_id == class_id).order_by(Student.pseudonym)
    )
    students = students_result.scalars().all()

    templates = request.app.state.templates
    return templates.TemplateResponse(
        "student_list.html",
        {
            "request": request,
            "teacher": teacher,
            "class_obj": class_obj,
            "students": students,
        },
    )


@router.post("/{class_id}")
async def add_student(
    class_id: int,
    pseudonym: str = Form(...),
    heritage_language: str = Form(""),
    english_proficiency_level: int = Form(1),
    l1_proficiency_level: int = Form(1),
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

    student = Student(
        class_id=class_id,
        pseudonym=pseudonym,
        heritage_language=heritage_language or None,
        english_proficiency_level=english_proficiency_level,
        l1_proficiency_level=l1_proficiency_level,
    )
    db.add(student)
    await db.commit()
    return RedirectResponse(f"/students/{class_id}", status_code=303)


@router.post("/{class_id}/{student_id}/update")
async def update_student(
    class_id: int,
    student_id: int,
    pseudonym: str = Form(...),
    heritage_language: str = Form(""),
    english_proficiency_level: int = Form(1),
    l1_proficiency_level: int = Form(1),
    teacher: Teacher = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db),
):
    if teacher is None:
        return RedirectResponse("/login", status_code=303)

    student = await db.get(Student, student_id)
    if student and student.class_id == class_id:
        student.pseudonym = pseudonym
        student.heritage_language = heritage_language or None
        student.english_proficiency_level = english_proficiency_level
        student.l1_proficiency_level = l1_proficiency_level
        await db.commit()

    return RedirectResponse(f"/students/{class_id}", status_code=303)


@router.post("/{class_id}/{student_id}/delete")
async def delete_student(
    class_id: int,
    student_id: int,
    teacher: Teacher = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db),
):
    if teacher is None:
        return RedirectResponse("/login", status_code=303)

    student = await db.get(Student, student_id)
    if student and student.class_id == class_id:
        await db.delete(student)
        await db.commit()

    return RedirectResponse(f"/students/{class_id}", status_code=303)
