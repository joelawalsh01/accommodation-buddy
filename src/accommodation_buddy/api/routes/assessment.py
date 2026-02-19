import json

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from accommodation_buddy.api.deps import get_current_teacher
from accommodation_buddy.core.prompts import (
    ASSESSMENT_ROUTE_START_TEMPLATE,
    ASSESSMENT_ROUTE_SYSTEM_PROMPT,
)
from accommodation_buddy.db.models import LanguageAssessment, Student, Teacher
from accommodation_buddy.db.session import get_db
from accommodation_buddy.services.model_settings import get_teacher_model_settings
from accommodation_buddy.services.ollama_client import OllamaClient

router = APIRouter(prefix="/assessment", tags=["assessment"])


@router.get("/{student_id}", response_class=HTMLResponse)
async def assessment_page(
    request: Request,
    student_id: int,
    teacher: Teacher = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db),
):
    if teacher is None:
        return RedirectResponse("/login", status_code=303)

    student = await db.get(Student, student_id)
    if student is None:
        return RedirectResponse("/classes", status_code=303)

    # Get existing assessments
    result = await db.execute(
        select(LanguageAssessment)
        .where(LanguageAssessment.student_id == student_id)
        .order_by(LanguageAssessment.assessed_at.desc())
    )
    assessments = result.scalars().all()

    templates = request.app.state.templates
    return templates.TemplateResponse(
        "assessment_chat.html",
        {
            "request": request,
            "teacher": teacher,
            "student": student,
            "assessments": assessments,
        },
    )


@router.post("/{student_id}/start")
async def start_assessment(
    student_id: int,
    language: str = Form("English"),
    teacher: Teacher = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db),
):
    if teacher is None:
        return HTMLResponse("Unauthorized", status_code=401)

    student = await db.get(Student, student_id)
    if student is None:
        return HTMLResponse("Student not found", status_code=404)

    system_prompt = ASSESSMENT_ROUTE_SYSTEM_PROMPT.format(
        language=language, max_turns=10
    )

    ms = await get_teacher_model_settings(teacher.id, db)

    client = OllamaClient()
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": ASSESSMENT_ROUTE_START_TEMPLATE.format(pseudonym=student.pseudonym)},
    ]

    response = await client.chat(
        messages=messages, model=ms.scaffolding_model, keep_alive=ms.keep_alive,
    )

    assessment = LanguageAssessment(
        student_id=student_id,
        conversation_log={
            "language": language,
            "messages": messages + [{"role": "assistant", "content": response}],
        },
    )
    db.add(assessment)
    await db.commit()
    await db.refresh(assessment)

    return HTMLResponse(f"""
    <div class="chat-message assistant" id="assessment-{assessment.id}">
        <div class="message-content">{response}</div>
    </div>
    <input type="hidden" name="assessment_id" value="{assessment.id}" id="assessment-id-input">
    """)


@router.post("/{student_id}/message", response_class=HTMLResponse)
async def send_message(
    request: Request,
    student_id: int,
    message: str = Form(...),
    assessment_id: int = Form(...),
    teacher: Teacher = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db),
):
    if teacher is None:
        return HTMLResponse("Unauthorized", status_code=401)

    assessment = await db.get(LanguageAssessment, assessment_id)
    if assessment is None or assessment.student_id != student_id:
        return HTMLResponse("Assessment not found", status_code=404)

    log = assessment.conversation_log or {"messages": []}
    messages = log.get("messages", [])
    messages.append({"role": "user", "content": message})

    ms = await get_teacher_model_settings(teacher.id, db)

    client = OllamaClient()
    response = await client.chat(
        messages=messages, model=ms.scaffolding_model, keep_alive=ms.keep_alive,
    )
    messages.append({"role": "assistant", "content": response})

    assessment.conversation_log = {**log, "messages": messages}

    # Check if assessment is complete (response contains JSON)
    assessment_result = None
    display_response = response
    try:
        if "{" in response and "proficiency_level" in response:
            # Try to extract JSON — may be inside a ```json code fence
            json_text = response
            fence_start = response.find("```json")
            if fence_start != -1:
                fence_end = response.find("```", fence_start + 7)
                json_text = response[fence_start + 7:fence_end] if fence_end != -1 else response[fence_start + 7:]
                display_response = response[:fence_start].rstrip()
            else:
                json_start = response.index("{")
                json_text = response[json_start:response.rindex("}") + 1]
                display_response = response[:json_start].rstrip()

            assessment_result = json.loads(json_text.strip())
            level = assessment_result.get("proficiency_level")
            if isinstance(level, int):
                level = max(1, min(4, level))  # ELPAC uses 1-4 scale
            assessment.english_score = level

            student = await db.get(Student, student_id)
            if student and log.get("language") == "English":
                student.english_proficiency_level = level
            elif student:
                student.l1_proficiency_level = level
    except (json.JSONDecodeError, ValueError):
        pass

    await db.commit()

    # Build the result card if assessment is complete
    result_card = ""
    if assessment_result:
        level = assessment_result.get("proficiency_level", "?")
        evidence = assessment_result.get("evidence", "")
        strengths = assessment_result.get("strengths", [])
        growth = assessment_result.get("areas_for_growth", [])

        strengths_html = "".join(f"<li>{s}</li>" for s in strengths)
        growth_html = "".join(f"<li>{g}</li>" for g in growth)

        result_card = f"""
        <div class="card" style="margin-top: 1rem; border-left: 3px solid var(--primary);">
            <h3>Assessment Complete — ELPAC Level {level}</h3>
            <p style="margin: .5rem 0; color: var(--text-muted); font-size: .9rem;">{evidence}</p>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-top: .75rem;">
                <div>
                    <strong style="color: var(--success); font-size: .85rem;">Strengths</strong>
                    <ul style="margin-top: .25rem; padding-left: 1.25rem; font-size: .85rem;">{strengths_html}</ul>
                </div>
                <div>
                    <strong style="color: var(--warning); font-size: .85rem;">Areas for Growth</strong>
                    <ul style="margin-top: .25rem; padding-left: 1.25rem; font-size: .85rem;">{growth_html}</ul>
                </div>
            </div>
        </div>
        """

    return HTMLResponse(f"""
    <div class="chat-message user">
        <div class="message-content">{message}</div>
    </div>
    <div class="chat-message assistant">
        <div class="message-content">{display_response}</div>
    </div>
    {result_card}
    """)
