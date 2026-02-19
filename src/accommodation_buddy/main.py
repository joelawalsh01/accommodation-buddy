import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from accommodation_buddy.config import settings
from accommodation_buddy.core.registry import PluginRegistry

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
PLUGINS_DIR = BASE_DIR / "plugins"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: discover plugins
    registry = PluginRegistry.get_instance()
    registry.discover(PLUGINS_DIR)
    logger.info(
        f"Discovered {len(registry.get_all())} plugins: "
        f"{[p.manifest().id for p in registry.get_all()]}"
    )

    # Register plugin routes
    from fastapi import APIRouter

    plugin_router = APIRouter(prefix="/api/plugin-routes")
    for plugin in registry.get_all():
        plugin.register_routes(plugin_router)
    app.include_router(plugin_router)

    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Accommodation Buddy",
        description="Helping teachers accommodate lesson materials for multilingual learners",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Templates
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    app.state.templates = templates

    # Static files
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # Upload directory
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)

    # Include routers
    from accommodation_buddy.api.routes import auth, classes, documents, features, students, assessment
    from accommodation_buddy.api.routes import settings as settings_routes

    app.include_router(auth.router)
    app.include_router(classes.router)
    app.include_router(students.router)
    app.include_router(documents.router)
    app.include_router(features.router)
    app.include_router(assessment.router)
    app.include_router(settings_routes.router)

    @app.get("/")
    async def root():
        return RedirectResponse("/dashboard")

    @app.get("/dashboard")
    async def dashboard(request: Request):
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        from accommodation_buddy.api.deps import get_current_teacher
        from accommodation_buddy.db.models import Class, Teacher
        from accommodation_buddy.db.session import async_session_factory

        # Get teacher from session
        from itsdangerous import URLSafeSerializer

        serializer = URLSafeSerializer(settings.secret_key)
        cookie = request.cookies.get("session")
        teacher = None
        if cookie:
            try:
                data = serializer.loads(cookie)
                teacher_id = data.get("teacher_id")
                if teacher_id:
                    async with async_session_factory() as db:
                        teacher = await db.get(Teacher, teacher_id)
                        if teacher:
                            result = await db.execute(
                                select(Class)
                                .where(Class.teacher_id == teacher.id)
                                .options(selectinload(Class.students))
                                .order_by(Class.created_at.desc())
                            )
                            classes = result.scalars().all()
                            return templates.TemplateResponse(
                                "dashboard.html",
                                {"request": request, "teacher": teacher, "classes": classes},
                            )
            except Exception:
                pass

        return RedirectResponse("/login")

    return app


app = create_app()
