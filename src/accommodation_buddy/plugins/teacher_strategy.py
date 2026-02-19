import json
import logging

from accommodation_buddy.core.base_plugin import (
    AccommodationResult,
    BasePlugin,
    ClassProfile,
    PluginCategory,
    PluginManifest,
    StudentProfile,
)
from accommodation_buddy.core.prompts import (
    TEACHER_STRATEGY_PROMPT_TEMPLATE,
    TEACHER_STRATEGY_SYSTEM_PROMPT,
)
from accommodation_buddy.services.ollama_client import OllamaClient

logger = logging.getLogger(__name__)


class TeacherStrategyPlugin(BasePlugin):
    def manifest(self) -> PluginManifest:
        return PluginManifest(
            id="teacher_strategy",
            name="Teacher Strategy Talk",
            description=(
                "Provides whole-class instructional strategies including student "
                "grouping recommendations, activity modifications by proficiency "
                "level, and a list of materials to prepare."
            ),
            category=PluginCategory.TEACHER_TOOL,
            icon="users",
            default_enabled=True,
            requires_student_profile=False,
            requires_document=True,
            panel_template="plugin_panels/strategy_panel.html",
            order_hint=60,
        )

    def _build_roster_text(self, class_profile: ClassProfile | None) -> str:
        """Build a text representation of the class roster for the prompt."""
        if not class_profile or not class_profile.students:
            return "No class roster data available."

        lines: list[str] = []
        for student in class_profile.students:
            lang = student.heritage_language or "unknown"
            eng = student.english_proficiency_level or "unknown"
            l1 = student.l1_proficiency_level or "unknown"
            lines.append(
                f"- {student.pseudonym}: Heritage language={lang}, "
                f"English ELPAC level={eng}, L1 proficiency={l1}"
            )
        return "\n".join(lines)

    async def generate(
        self,
        document_text: str,
        student_profile: StudentProfile | None,
        class_profile: ClassProfile | None,
        options: dict,
    ) -> AccommodationResult:
        roster_text = self._build_roster_text(class_profile)

        # Use document_text as summary; truncate for prompt size
        document_summary = document_text[:4000] if document_text else "No document provided."

        # Existing accommodations can be passed in options
        existing_accommodations = options.get("existing_accommodations", "None generated yet.")
        if isinstance(existing_accommodations, list):
            existing_accommodations = "\n".join(
                f"- {acc}" for acc in existing_accommodations
            )

        prompt = TEACHER_STRATEGY_PROMPT_TEMPLATE.format(
            roster_text=roster_text,
            document_summary=document_summary,
            existing_accommodations=existing_accommodations,
        )

        client = OllamaClient()

        ms = options.get("_model_settings")
        model = ms.scaffolding_model if ms else None
        keep_alive = ms.keep_alive if ms else None

        try:
            raw_response = await client.generate(
                prompt=prompt,
                system=TEACHER_STRATEGY_SYSTEM_PROMPT,
                model=model,
                keep_alive=keep_alive,
            )
        except Exception:
            logger.exception("LLM call failed for teacher_strategy plugin")
            return AccommodationResult(
                plugin_id="teacher_strategy",
                generated_output={"error": "LLM generation failed"},
                status="failed",
            )

        try:
            parsed = json.loads(raw_response)
        except json.JSONDecodeError:
            logger.warning(
                "Failed to parse LLM JSON for teacher_strategy, returning raw text"
            )
            parsed = {
                "grouping_strategy": raw_response,
                "groups": [],
                "activity_modifications": [],
                "materials_to_generate": [],
                "parse_warning": "LLM response was not valid JSON; raw text included in grouping_strategy.",
            }

        parsed["class_name"] = class_profile.name if class_profile else "unknown"
        parsed["student_count"] = len(class_profile.students) if class_profile else 0

        return AccommodationResult(
            plugin_id="teacher_strategy",
            generated_output=parsed,
        )
