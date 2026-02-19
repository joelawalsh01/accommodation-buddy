import importlib
import logging
from pathlib import Path

from accommodation_buddy.core.base_plugin import BasePlugin, PluginCategory

logger = logging.getLogger(__name__)


class PluginRegistry:
    _instance: "PluginRegistry | None" = None
    _plugins: dict[str, BasePlugin]

    def __init__(self) -> None:
        self._plugins = {}

    @classmethod
    def get_instance(cls) -> "PluginRegistry":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def discover(self, plugins_dir: Path) -> None:
        for f in plugins_dir.glob("*.py"):
            if f.name.startswith("_"):
                continue
            module_name = f"accommodation_buddy.plugins.{f.stem}"
            try:
                module = importlib.import_module(module_name)
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (
                        isinstance(attr, type)
                        and issubclass(attr, BasePlugin)
                        and attr is not BasePlugin
                    ):
                        instance = attr()
                        manifest = instance.manifest()
                        self._plugins[manifest.id] = instance
                        logger.info(f"Registered plugin: {manifest.id} ({manifest.name})")
            except Exception:
                logger.exception(f"Failed to load plugin from {f.name}")

    def register(self, plugin: BasePlugin) -> None:
        manifest = plugin.manifest()
        self._plugins[manifest.id] = plugin

    def get(self, plugin_id: str) -> BasePlugin | None:
        return self._plugins.get(plugin_id)

    def get_all(self) -> list[BasePlugin]:
        return list(self._plugins.values())

    def get_by_category(self, category: PluginCategory) -> list[BasePlugin]:
        return [
            p for p in self._plugins.values()
            if p.manifest().category == category
        ]

    def get_manifests(self) -> list[dict]:
        results = []
        for plugin in self._plugins.values():
            m = plugin.manifest()
            results.append({
                "id": m.id,
                "name": m.name,
                "description": m.description,
                "category": m.category.value,
                "icon": m.icon,
                "default_enabled": m.default_enabled,
                "always_on": m.always_on,
                "requires_student_profile": m.requires_student_profile,
                "requires_document": m.requires_document,
                "order_hint": m.order_hint,
            })
        return sorted(results, key=lambda x: x["order_hint"])
