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
    INSTRUCTION_EXPLAINER_PROMPT_TEMPLATE,
    INSTRUCTION_EXPLAINER_SYSTEM_PROMPT,
)
from accommodation_buddy.services.ollama_client import OllamaClient

logger = logging.getLogger(__name__)


class InstructionExplainerPlugin(BasePlugin):
    def manifest(self) -> PluginManifest:
        return PluginManifest(
            id="instruction_explainer",
            name="Instruction Explainer",
            description=(
                "Generates heritage-language explanations of activity instructions "
                "at the appropriate WIDA proficiency level, including step-by-step "
                "task flow descriptions and comprehension checks for the teacher."
            ),
            category=PluginCategory.DOCUMENT_ACCOMMODATION,
            icon="languages",
            default_enabled=True,
            requires_student_profile=True,
            requires_document=True,
            panel_template="plugin_panels/instruction_explainer.html",
            order_hint=30,
        )

    async def generate(
        self,
        document_text: str,
        student_profile: StudentProfile | None,
        class_profile: ClassProfile | None,
        options: dict,
    ) -> AccommodationResult:
        proficiency_level = 3
        heritage_language = "not specified"
        l1_proficiency = "unknown"

        if student_profile:
            if student_profile.english_proficiency_level:
                proficiency_level = student_profile.english_proficiency_level
            if student_profile.heritage_language:
                heritage_language = student_profile.heritage_language
            if student_profile.l1_proficiency_level:
                l1_proficiency = str(student_profile.l1_proficiency_level)

        prompt = INSTRUCTION_EXPLAINER_PROMPT_TEMPLATE.format(
            proficiency_level=proficiency_level,
            heritage_language=heritage_language,
            l1_proficiency=l1_proficiency,
            document_text=document_text[:8000],
        )

        client = OllamaClient()

        try:
            raw_response = await client.generate(
                prompt=prompt,
                system=INSTRUCTION_EXPLAINER_SYSTEM_PROMPT,
            )
        except Exception:
            logger.exception("LLM call failed for instruction_explainer plugin")
            return AccommodationResult(
                plugin_id="instruction_explainer",
                generated_output={"error": "LLM generation failed"},
                status="failed",
            )

        try:
            parsed = json.loads(raw_response)
        except json.JSONDecodeError:
            logger.warning(
                "Failed to parse LLM JSON for instruction_explainer, returning raw text"
            )
            parsed = {
                "l1_instructions": raw_response,
                "task_flow_description": "",
                "comprehension_checks": [],
                "parse_warning": "LLM response was not valid JSON; raw text included in l1_instructions.",
            }

        parsed["proficiency_level"] = proficiency_level
        parsed["heritage_language"] = heritage_language

        return AccommodationResult(
            plugin_id="instruction_explainer",
            generated_output=parsed,
        )
