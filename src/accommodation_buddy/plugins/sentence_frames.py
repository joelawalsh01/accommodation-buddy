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
    SENTENCE_FRAMES_PROMPT_TEMPLATE,
    SENTENCE_FRAMES_SYSTEM_PROMPT,
)
from accommodation_buddy.services.ollama_client import OllamaClient

logger = logging.getLogger(__name__)

ELPAC_LEVEL_DESCRIPTORS = {
    1: "Beginning/Minimally Developed – isolated words or phrases, limited coherence, severe grammar limitations",
    2: "Somewhat Developed – partial account, somewhat coherent, frequent errors impede meaning",
    3: "Moderately Developed – generally complete, mostly coherent, can write expanded sentences",
    4: "Well Developed – full and complete, readily coherent, varied grammar with minor errors",
}


class SentenceFramesPlugin(BasePlugin):
    def manifest(self) -> PluginManifest:
        return PluginManifest(
            id="sentence_frames",
            name="Sentence Frames Generator",
            description=(
                "Generates sentence frames and starters aligned to a student's "
                "ELPAC proficiency level, helping multilingual learners respond to "
                "grade-level questions with appropriate linguistic scaffolding."
            ),
            category=PluginCategory.DOCUMENT_ACCOMMODATION,
            icon="message-square",
            default_enabled=True,
            requires_student_profile=True,
            requires_document=True,
            panel_template="plugin_panels/sentence_frames.html",
            order_hint=10,
        )

    async def generate(
        self,
        document_text: str,
        student_profile: StudentProfile | None,
        class_profile: ClassProfile | None,
        options: dict,
    ) -> AccommodationResult:
        proficiency_level = 3  # sensible default
        heritage_language = "not specified"

        if student_profile:
            if student_profile.english_proficiency_level:
                proficiency_level = student_profile.english_proficiency_level
            if student_profile.heritage_language:
                heritage_language = student_profile.heritage_language

        level_descriptor = ELPAC_LEVEL_DESCRIPTORS.get(proficiency_level, ELPAC_LEVEL_DESCRIPTORS[3])

        prompt = SENTENCE_FRAMES_PROMPT_TEMPLATE.format(
            proficiency_level=proficiency_level,
            level_descriptor=level_descriptor,
            heritage_language=heritage_language,
            document_text=document_text[:8000],
        )

        client = OllamaClient()

        ms = options.get("_model_settings")
        model = ms.scaffolding_model if ms else None
        keep_alive = ms.keep_alive if ms else None

        try:
            raw_response = await client.generate(
                prompt=prompt,
                system=SENTENCE_FRAMES_SYSTEM_PROMPT,
                model=model,
                keep_alive=keep_alive,
            )
        except Exception:
            logger.exception("LLM call failed for sentence_frames plugin")
            return AccommodationResult(
                plugin_id="sentence_frames",
                generated_output={"error": "LLM generation failed"},
                status="failed",
            )

        try:
            parsed = json.loads(raw_response)
        except json.JSONDecodeError:
            logger.warning("Failed to parse LLM JSON for sentence_frames, returning raw text")
            parsed = {
                "frames": [],
                "scaffolding_rationale": raw_response,
                "parse_warning": "LLM response was not valid JSON; raw text included in scaffolding_rationale.",
            }

        parsed["proficiency_level"] = proficiency_level
        parsed["heritage_language"] = heritage_language

        return AccommodationResult(
            plugin_id="sentence_frames",
            generated_output=parsed,
        )
