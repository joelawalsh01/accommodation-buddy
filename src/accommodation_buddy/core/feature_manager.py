from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from accommodation_buddy.core.base_plugin import PluginManifest
from accommodation_buddy.core.registry import PluginRegistry
from accommodation_buddy.db.models import FeatureToggle


@dataclass
class FeatureToggleView:
    plugin_id: str
    name: str
    description: str
    category: str
    icon: str
    enabled: bool
    always_on: bool
    config_overrides: dict | None


class FeatureManager:
    def __init__(self, registry: PluginRegistry) -> None:
        self.registry = registry

    async def get_enabled_plugins(
        self, class_id: int, db: AsyncSession
    ) -> list[PluginManifest]:
        result = await db.execute(
            select(FeatureToggle).where(FeatureToggle.class_id == class_id)
        )
        toggles = {t.plugin_id: t for t in result.scalars().all()}

        enabled = []
        for plugin in self.registry.get_all():
            m = plugin.manifest()
            if m.always_on:
                enabled.append(m)
                continue

            toggle = toggles.get(m.id)
            if toggle is not None:
                if toggle.enabled:
                    enabled.append(m)
            elif m.default_enabled:
                enabled.append(m)

        return sorted(enabled, key=lambda m: m.order_hint)

    async def set_enabled(
        self, class_id: int, plugin_id: str, enabled: bool, db: AsyncSession
    ) -> None:
        result = await db.execute(
            select(FeatureToggle).where(
                FeatureToggle.class_id == class_id,
                FeatureToggle.plugin_id == plugin_id,
            )
        )
        toggle = result.scalar_one_or_none()

        if toggle is None:
            toggle = FeatureToggle(
                class_id=class_id, plugin_id=plugin_id, enabled=enabled
            )
            db.add(toggle)
        else:
            toggle.enabled = enabled

        await db.commit()

    async def set_config(
        self, class_id: int, plugin_id: str, config: dict, db: AsyncSession
    ) -> None:
        result = await db.execute(
            select(FeatureToggle).where(
                FeatureToggle.class_id == class_id,
                FeatureToggle.plugin_id == plugin_id,
            )
        )
        toggle = result.scalar_one_or_none()

        if toggle is None:
            toggle = FeatureToggle(
                class_id=class_id,
                plugin_id=plugin_id,
                enabled=True,
                config_overrides=config,
            )
            db.add(toggle)
        else:
            toggle.config_overrides = config

        await db.commit()

    async def get_toggle_state(
        self, class_id: int, db: AsyncSession
    ) -> list[FeatureToggleView]:
        result = await db.execute(
            select(FeatureToggle).where(FeatureToggle.class_id == class_id)
        )
        toggles = {t.plugin_id: t for t in result.scalars().all()}

        views = []
        for plugin in self.registry.get_all():
            m = plugin.manifest()
            toggle = toggles.get(m.id)

            if toggle is not None:
                enabled = toggle.enabled
                config_overrides = toggle.config_overrides
            else:
                enabled = m.default_enabled
                config_overrides = None

            views.append(
                FeatureToggleView(
                    plugin_id=m.id,
                    name=m.name,
                    description=m.description,
                    category=m.category.value,
                    icon=m.icon,
                    enabled=enabled or m.always_on,
                    always_on=m.always_on,
                    config_overrides=config_overrides,
                )
            )

        return views
