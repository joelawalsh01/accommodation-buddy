from dataclasses import dataclass

from jinja2 import Environment
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from accommodation_buddy.core.base_plugin import BasePlugin
from accommodation_buddy.core.feature_manager import FeatureManager
from accommodation_buddy.db.models import PluginState


@dataclass
class RenderedPanel:
    plugin_id: str
    name: str
    icon: str
    order: int
    collapsed: bool
    html: str


class PanelHost:
    def __init__(
        self, feature_manager: FeatureManager, jinja_env: Environment
    ) -> None:
        self.feature_manager = feature_manager
        self.jinja_env = jinja_env

    async def render_sidebar(
        self,
        document_id: int,
        class_id: int,
        student_id: int | None,
        db: AsyncSession,
    ) -> list[RenderedPanel]:
        from accommodation_buddy.core.registry import PluginRegistry

        registry = PluginRegistry.get_instance()
        enabled_manifests = await self.feature_manager.get_enabled_plugins(
            class_id, db
        )

        # Get panel states for ordering/collapse
        result = await db.execute(
            select(PluginState).where(PluginState.document_id == document_id)
        )
        states = {s.plugin_id: s for s in result.scalars().all()}

        panels = []
        for manifest in enabled_manifests:
            if not manifest.panel_template:
                continue
            if not manifest.requires_document:
                continue

            plugin = registry.get(manifest.id)
            if plugin is None:
                continue

            state = states.get(manifest.id)
            order = state.panel_order if state else manifest.order_hint
            collapsed = state.collapsed if state else False

            context = plugin.get_panel_context(document_id, student_id)
            context.update({
                "plugin_id": manifest.id,
                "plugin_name": manifest.name,
                "plugin_icon": manifest.icon,
                "document_id": document_id,
                "student_id": student_id,
                "collapsed": collapsed,
            })

            try:
                template = self.jinja_env.get_template(manifest.panel_template)
                html = template.render(**context)
            except Exception:
                html = f'<div class="panel-error">Failed to render {manifest.name}</div>'

            panels.append(
                RenderedPanel(
                    plugin_id=manifest.id,
                    name=manifest.name,
                    icon=manifest.icon,
                    order=order,
                    collapsed=collapsed,
                    html=html,
                )
            )

        return sorted(panels, key=lambda p: p.order)

    async def render_single_panel(
        self,
        plugin: BasePlugin,
        document_id: int,
        student_id: int | None,
        result_data: dict | None = None,
    ) -> str:
        manifest = plugin.manifest()
        if not manifest.panel_template:
            return ""

        context = plugin.get_panel_context(document_id, student_id)
        context.update({
            "plugin_id": manifest.id,
            "plugin_name": manifest.name,
            "plugin_icon": manifest.icon,
            "document_id": document_id,
            "student_id": student_id,
            "result": result_data,
        })

        template = self.jinja_env.get_template(manifest.panel_template)
        return template.render(**context)
