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
    FEEDBACK_PROMPT_TEMPLATE,
    NEW_LANGUAGE_DIALOGUE_PROMPT_TEMPLATE,
    NEW_LANGUAGE_DIALOGUE_SYSTEM_PROMPT,
)
from accommodation_buddy.services.ollama_client import OllamaClient

logger = logging.getLogger(__name__)


class NewLanguageDialoguePlugin(BasePlugin):
    def manifest(self) -> PluginManifest:
        return PluginManifest(
            id="new_language_dialogue",
            name="New Language Dialogue",
            description=(
                "Provides structured practice conversations for newly taught "
                "language concepts, with feedback summaries and glossary entries "
                "to reinforce learning."
            ),
            category=PluginCategory.STUDENT_TOOL,
            icon="message-circle",
            default_enabled=True,
            requires_student_profile=True,
            requires_document=False,
            panel_template=None,
            order_hint=75,
        )

    async def generate(
        self,
        document_text: str,
        student_profile: StudentProfile | None,
        class_profile: ClassProfile | None,
        options: dict,
    ) -> AccommodationResult:
        """Run a complete practice dialogue session.

        The practice conversation is conducted as a series of LLM chat turns.
        The student's messages are provided in options["student_messages"] as a list
        of strings. If not provided, a single opening message is generated for the
        student to respond to via a separate chat mechanism.
        """
        pseudonym = "Student"
        heritage_language = "not specified"
        proficiency_level = 3

        if student_profile:
            pseudonym = student_profile.pseudonym
            if student_profile.heritage_language:
                heritage_language = student_profile.heritage_language
            if student_profile.english_proficiency_level:
                proficiency_level = student_profile.english_proficiency_level

        practice_topic = options.get("practice_topic", "general English conversation practice")
        teacher_notes = options.get("teacher_notes", "None provided.")
        student_messages: list[str] = options.get("student_messages", [])

        start_prompt = NEW_LANGUAGE_DIALOGUE_PROMPT_TEMPLATE.format(
            pseudonym=pseudonym,
            heritage_language=heritage_language,
            proficiency_level=proficiency_level,
            practice_topic=practice_topic,
            teacher_notes=teacher_notes,
        )

        client = OllamaClient()

        messages = [
            {"role": "system", "content": NEW_LANGUAGE_DIALOGUE_SYSTEM_PROMPT},
            {"role": "user", "content": start_prompt},
        ]

        # If no student messages provided, just generate the opening and return
        if not student_messages:
            try:
                opening = await client.chat(messages=messages)
            except Exception:
                logger.exception("LLM call failed for new_language_dialogue opening")
                return AccommodationResult(
                    plugin_id="new_language_dialogue",
                    generated_output={"error": "Failed to start practice session"},
                    status="failed",
                )

            return AccommodationResult(
                plugin_id="new_language_dialogue",
                generated_output={
                    "opening_message": opening,
                    "practice_topic": practice_topic,
                    "session_started": True,
                    "awaiting_student_response": True,
                    "conversation_transcript": [
                        {"role": "assistant", "content": opening},
                    ],
                    "feedback_summary": None,
                    "glossary_entries": [],
                },
            )

        # Conduct the full conversation with provided student messages
        transcript_parts: list[dict[str, str]] = []

        try:
            opening = await client.chat(messages=messages)
        except Exception:
            logger.exception("LLM call failed for new_language_dialogue opening")
            return AccommodationResult(
                plugin_id="new_language_dialogue",
                generated_output={"error": "Failed to start practice session"},
                status="failed",
            )

        messages.append({"role": "assistant", "content": opening})
        transcript_parts.append({"role": "assistant", "content": opening})

        for student_msg in student_messages:
            messages.append({"role": "user", "content": student_msg})
            transcript_parts.append({"role": "student", "content": student_msg})

            try:
                reply = await client.chat(messages=messages)
            except Exception:
                logger.exception("LLM call failed during dialogue turn")
                break

            messages.append({"role": "assistant", "content": reply})
            transcript_parts.append({"role": "assistant", "content": reply})

        # Generate structured feedback
        transcript_text = "\n".join(
            f"{turn['role'].upper()}: {turn['content']}" for turn in transcript_parts
        )

        feedback_prompt = FEEDBACK_PROMPT_TEMPLATE.format(
            proficiency_level=proficiency_level,
            practice_topic=practice_topic,
            transcript=transcript_text,
        )

        try:
            raw_feedback = await client.generate(prompt=feedback_prompt)
        except Exception:
            logger.exception("LLM call failed for dialogue feedback generation")
            return AccommodationResult(
                plugin_id="new_language_dialogue",
                generated_output={
                    "conversation_transcript": transcript_parts,
                    "feedback_summary": {"error": "Feedback generation failed"},
                    "glossary_entries": [],
                    "practice_topic": practice_topic,
                },
            )

        try:
            parsed_feedback = json.loads(raw_feedback)
        except json.JSONDecodeError:
            logger.warning("Failed to parse feedback JSON for new_language_dialogue")
            parsed_feedback = {
                "feedback_summary": {
                    "raw_feedback": raw_feedback,
                    "parse_warning": "Feedback was not valid JSON.",
                },
                "glossary_entries": [],
            }

        return AccommodationResult(
            plugin_id="new_language_dialogue",
            generated_output={
                "conversation_transcript": transcript_parts,
                "feedback_summary": parsed_feedback.get("feedback_summary", {}),
                "glossary_entries": parsed_feedback.get("glossary_entries", []),
                "practice_topic": practice_topic,
                "proficiency_level": proficiency_level,
                "heritage_language": heritage_language,
            },
        )
