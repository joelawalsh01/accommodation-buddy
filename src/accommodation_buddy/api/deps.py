from collections.abc import AsyncGenerator

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from accommodation_buddy.core.feature_manager import FeatureManager
from accommodation_buddy.core.panel_host import PanelHost
from accommodation_buddy.core.registry import PluginRegistry
from accommodation_buddy.db.session import get_db
from accommodation_buddy.services.ollama_client import OllamaClient


async def get_registry() -> PluginRegistry:
    return PluginRegistry.get_instance()


async def get_ollama() -> OllamaClient:
    return OllamaClient()


async def get_feature_manager(
    registry: PluginRegistry = Depends(get_registry),
) -> FeatureManager:
    return FeatureManager(registry)


async def get_panel_host(
    request: Request,
    feature_manager: FeatureManager = Depends(get_feature_manager),
) -> PanelHost:
    jinja_env = request.app.state.templates.env
    return PanelHost(feature_manager, jinja_env)


async def get_current_teacher(request: Request, db: AsyncSession = Depends(get_db)):
    from itsdangerous import URLSafeSerializer

    from accommodation_buddy.config import settings
    from accommodation_buddy.db.models import Teacher

    serializer = URLSafeSerializer(settings.secret_key)
    cookie = request.cookies.get("session")
    if cookie:
        try:
            data = serializer.loads(cookie)
            teacher_id = data.get("teacher_id")
            if teacher_id:
                return await db.get(Teacher, teacher_id)
        except Exception:
            return None
    return None
