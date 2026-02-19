import bcrypt as _bcrypt
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from itsdangerous import URLSafeSerializer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from accommodation_buddy.config import settings
from accommodation_buddy.db.models import Teacher
from accommodation_buddy.db.session import get_db

router = APIRouter(tags=["auth"])


def _set_session(response, teacher_id: int):
    serializer = URLSafeSerializer(settings.secret_key)
    cookie = serializer.dumps({"teacher_id": teacher_id})
    response.set_cookie("session", cookie, httponly=True, max_age=86400 * 7)


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    templates = request.app.state.templates
    return templates.TemplateResponse("login.html", {"request": request})


@router.post("/login")
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Teacher).where(Teacher.email == email))
    teacher = result.scalar_one_or_none()

    if teacher is None or not _bcrypt.checkpw(
        password.encode("utf-8"), teacher.password_hash.encode("utf-8")
    ):
        templates = request.app.state.templates
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Invalid email or password"},
            status_code=401,
        )

    response = RedirectResponse("/dashboard", status_code=303)
    _set_session(response, teacher.id)
    return response


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    templates = request.app.state.templates
    return templates.TemplateResponse("register.html", {"request": request})


@router.post("/register")
async def register(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(select(Teacher).where(Teacher.email == email))
    if existing.scalar_one_or_none():
        templates = request.app.state.templates
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "error": "Email already registered"},
            status_code=400,
        )

    teacher = Teacher(
        name=name,
        email=email,
        password_hash=_bcrypt.hashpw(
            password.encode("utf-8"), _bcrypt.gensalt()
        ).decode("utf-8"),
    )
    db.add(teacher)
    await db.commit()
    await db.refresh(teacher)

    response = RedirectResponse("/dashboard", status_code=303)
    _set_session(response, teacher.id)
    return response


@router.get("/logout")
async def logout():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie("session")
    return response
