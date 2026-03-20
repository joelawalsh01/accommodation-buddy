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
    TRANSLATION_INSTRUCTIONS,
    TRANSLATION_SYSTEM_PROMPT,
    TRANSLATION_USER_PROMPT_TEMPLATE,
)
from accommodation_buddy.services.ollama_client import OllamaClient

logger = logging.getLogger(__name__)

# Grade level to age range mapping
GRADE_AGE_MAP = {
    "K": ("Kindergarten", "5-6"),
    "1": ("1st", "6-7"),
    "2": ("2nd", "7-8"),
    "3": ("3rd", "8-9"),
    "4": ("4th", "9-10"),
    "5": ("5th", "10-11"),
    "6": ("6th", "11-12"),
    "7": ("7th", "12-13"),
    "8": ("8th", "13-14"),
    "9": ("9th", "14-15"),
    "10": ("10th", "15-16"),
    "11": ("11th", "16-17"),
    "12": ("12th", "17-18"),
}


def _resolve_grade(grade_level: str | None) -> tuple[str, str]:
    """Return (grade_label, age_range) from a grade_level string."""
    if not grade_level:
        return ("5th", "10-11")

    cleaned = grade_level.strip().lower()
    # Strip suffixes like "th", "st", "nd", "rd", "grade"
    for suffix in ("th", "st", "nd", "rd", "grade", " "):
        cleaned = cleaned.replace(suffix, "")
    cleaned = cleaned.strip()

    if cleaned in GRADE_AGE_MAP:
        return GRADE_AGE_MAP[cleaned]

    # Fallback: try to parse as int
    try:
        n = int(cleaned)
        if n in range(0, 13):
            return GRADE_AGE_MAP.get(str(n), ("5th", "10-11"))
    except ValueError:
        pass

    return ("5th", "10-11")


class TranslationPlugin(BasePlugin):
    def manifest(self) -> PluginManifest:
        return PluginManifest(
            id="translation",
            name="Spanish Translation",
            description=(
                "Translates lesson content to Spanish at the appropriate "
                "grade level, preserving all formatting, scientific terminology, "
                "and educational structure."
            ),
            category=PluginCategory.DOCUMENT_ACCOMMODATION,
            icon="languages",
            default_enabled=True,
            always_on=False,
            requires_student_profile=False,
            requires_document=True,
            panel_template="plugin_panels/translation.html",
            config_schema={
                "type": "object",
                "properties": {
                    "domain": {
                        "type": "string",
                        "description": "Broad scientific area (e.g. Life Science, Earth Science)",
                        "default": "Science",
                    },
                    "subject": {
                        "type": "string",
                        "description": "Specific topic (e.g. Human Body Systems)",
                        "default": "General",
                    },
                },
            },
            order_hint=15,
        )

    async def generate(
        self,
        document_text: str,
        student_profile: StudentProfile | None,
        class_profile: ClassProfile | None,
        options: dict,
    ) -> AccommodationResult:
        if not document_text or not document_text.strip():
            return AccommodationResult(
                plugin_id="translation",
                generated_output={
                    "error": "No document text available for translation.",
                },
                status="failed",
            )

        # Resolve grade level (explicit override > class default)
        grade_level = options.get("grade_level")
        if not grade_level and class_profile and class_profile.grade_level:
            grade_level = class_profile.grade_level
        grade_label, age_range = _resolve_grade(grade_level)

        # Domain and subject from options or config overrides
        domain = options.get("domain", "Science")
        subject = options.get("subject", "General")

        # Build the user prompt
        user_prompt = TRANSLATION_USER_PROMPT_TEMPLATE.format(
            grade_label=grade_label,
            age_range=age_range,
            domain=domain,
            subject=subject,
            document_text=document_text,
        )

        # Combine system prompt with translation instructions
        full_system = f"{TRANSLATION_SYSTEM_PROMPT}\n\n{TRANSLATION_INSTRUCTIONS}"

        client = OllamaClient()

        from accommodation_buddy.config import settings

        ms = options.get("_model_settings")
        trans_model = ms.translation_model if ms else settings.translation_model
        keep_alive = ms.keep_alive if ms else None

        try:
            translated_text = await client.chat(
                messages=[
                    {"role": "system", "content": full_system},
                    {"role": "user", "content": user_prompt},
                ],
                model=trans_model,
                keep_alive=keep_alive,
            )

            return AccommodationResult(
                plugin_id="translation",
                generated_output={
                    "translated_text": translated_text,
                    "source_language": "English",
                    "target_language": "Spanish",
                    "grade_level": grade_label,
                    "age_range": age_range,
                    "domain": domain,
                    "subject": subject,
                },
            )
        except Exception as e:
            logger.exception("Translation failed")
            return AccommodationResult(
                plugin_id="translation",
                generated_output={
                    "error": f"Translation failed: {e}",
                },
                status="failed",
            )
