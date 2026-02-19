import logging

from accommodation_buddy.core.base_plugin import (
    AccommodationResult,
    BasePlugin,
    ClassProfile,
    PluginCategory,
    PluginManifest,
    StudentProfile,
)

logger = logging.getLogger(__name__)


class PauseTeacherPlugin(BasePlugin):
    """Pause the Teacher -- STUB for future live-mode feature.

    This plugin will eventually allow students to signal the teacher (via a
    real-time channel) that they need the pace slowed down, a concept
    re-explained, or a vocabulary term clarified -- without raising a hand
    in front of the class.

    Currently unimplemented; ``generate()`` raises ``NotImplementedError``.
    """

    def manifest(self) -> PluginManifest:
        return PluginManifest(
            id="pause_teacher",
            name="Pause the Teacher",
            description=(
                "Allows students to anonymously signal the teacher during live "
                "instruction when they need the pace adjusted or a concept "
                "re-explained. (Planned for a future release.)"
            ),
            category=PluginCategory.LIVE_MODE,
            icon="pause-circle",
            default_enabled=False,
            requires_student_profile=True,
            requires_document=False,
            panel_template="plugin_panels/pause_teacher.html",
            order_hint=90,
        )

    async def generate(
        self,
        document_text: str,
        student_profile: StudentProfile | None,
        class_profile: ClassProfile | None,
        options: dict,
    ) -> AccommodationResult:
        raise NotImplementedError(
            "Pause the Teacher is planned for a future release"
        )
