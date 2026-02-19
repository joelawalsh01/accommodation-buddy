import json
import logging
import uuid

from accommodation_buddy.core.base_plugin import (
    AccommodationResult,
    BasePlugin,
    ClassProfile,
    PluginCategory,
    PluginManifest,
    StudentProfile,
)
from accommodation_buddy.core.prompts import ASSESSMENT_START_PROMPT, WIDA_ASSESSMENT_SYSTEM_PROMPT
from accommodation_buddy.services.ollama_client import OllamaClient

logger = logging.getLogger(__name__)

# In-memory store for active assessment sessions.
# In production, this would be backed by Redis or the database.
_active_sessions: dict[str, dict] = {}


class LanguageAssessmentPlugin(BasePlugin):
    def manifest(self) -> PluginManifest:
        return PluginManifest(
            id="language_assessment",
            name="Language Assessment Dialogue",
            description=(
                "Conducts an informal, multi-turn conversational assessment to "
                "estimate a student's WIDA English proficiency level (1-6) through "
                "natural dialogue progressing from social to academic language."
            ),
            category=PluginCategory.STUDENT_TOOL,
            icon="mic",
            default_enabled=True,
            requires_student_profile=True,
            requires_document=False,
            panel_template=None,
            order_hint=70,
        )

    async def generate(
        self,
        document_text: str,
        student_profile: StudentProfile | None,
        class_profile: ClassProfile | None,
        options: dict,
    ) -> AccommodationResult:
        """Start a new assessment session and return the opening message."""
        pseudonym = "Student"
        heritage_language = "not specified"
        current_level = "unknown"

        if student_profile:
            pseudonym = student_profile.pseudonym
            if student_profile.heritage_language:
                heritage_language = student_profile.heritage_language
            if student_profile.english_proficiency_level:
                current_level = f"WIDA {student_profile.english_proficiency_level}"

        start_prompt = ASSESSMENT_START_PROMPT.format(
            pseudonym=pseudonym,
            heritage_language=heritage_language,
            current_level=current_level,
        )

        client = OllamaClient()

        messages = [
            {"role": "system", "content": WIDA_ASSESSMENT_SYSTEM_PROMPT},
            {"role": "user", "content": start_prompt},
        ]

        try:
            opening_message = await client.chat(messages=messages)
        except Exception:
            logger.exception("LLM call failed for language_assessment plugin")
            return AccommodationResult(
                plugin_id="language_assessment",
                generated_output={"error": "Failed to start assessment session"},
                status="failed",
            )

        # Create a session
        session_id = str(uuid.uuid4())
        messages.append({"role": "assistant", "content": opening_message})

        _active_sessions[session_id] = {
            "messages": messages,
            "student_id": student_profile.id if student_profile else None,
            "turn_count": 1,
            "assessment_complete": False,
            "estimated_level": None,
        }

        return AccommodationResult(
            plugin_id="language_assessment",
            generated_output={
                "session_id": session_id,
                "opening_message": opening_message,
                "turn_count": 1,
                "assessment_complete": False,
                "instructions": (
                    "Use the /api/plugins/language_assessment/chat endpoint "
                    "to continue the conversation."
                ),
            },
        )

    def register_routes(self, router: "APIRouter") -> None:
        """Register the chat endpoint for multi-turn assessment."""
        from fastapi import APIRouter

        @router.post("/plugins/language_assessment/chat")
        async def assessment_chat(payload: dict) -> dict:
            """Continue an assessment conversation.

            Expected payload:
            {
                "session_id": "<uuid>",
                "student_message": "<what the student said>"
            }
            """
            session_id = payload.get("session_id")
            student_message = payload.get("student_message", "")

            if not session_id or session_id not in _active_sessions:
                return {
                    "error": "Invalid or expired session_id. Start a new assessment.",
                    "session_id": session_id,
                }

            session = _active_sessions[session_id]

            if session["assessment_complete"]:
                return {
                    "error": "This assessment session is already complete.",
                    "session_id": session_id,
                    "estimated_level": session["estimated_level"],
                }

            # Add the student's message to conversation history
            session["messages"].append({"role": "user", "content": student_message})
            session["turn_count"] += 1

            client = OllamaClient()

            try:
                assistant_reply = await client.chat(messages=session["messages"])
            except Exception:
                logger.exception("LLM call failed during assessment chat")
                return {
                    "error": "LLM call failed. Please try again.",
                    "session_id": session_id,
                }

            session["messages"].append({"role": "assistant", "content": assistant_reply})

            # Check if the assessment is complete by looking for the JSON block
            assessment_data = None
            try:
                # Look for JSON in the response
                json_start = assistant_reply.rfind("{")
                json_end = assistant_reply.rfind("}") + 1
                if json_start != -1 and json_end > json_start:
                    candidate = assistant_reply[json_start:json_end]
                    parsed = json.loads(candidate)
                    if parsed.get("assessment_complete"):
                        assessment_data = parsed
                        session["assessment_complete"] = True
                        session["estimated_level"] = parsed.get("estimated_wida_level")
            except (json.JSONDecodeError, ValueError):
                pass  # Not yet complete, continue conversation

            response = {
                "session_id": session_id,
                "assistant_message": assistant_reply,
                "turn_count": session["turn_count"],
                "assessment_complete": session["assessment_complete"],
            }

            if assessment_data:
                response["assessment_result"] = assessment_data

            return response

        @router.get("/plugins/language_assessment/session/{session_id}")
        async def get_assessment_session(session_id: str) -> dict:
            """Retrieve the current state of an assessment session."""
            if session_id not in _active_sessions:
                return {"error": "Session not found.", "session_id": session_id}

            session = _active_sessions[session_id]
            # Return conversation without the system prompt for privacy
            conversation = [
                msg for msg in session["messages"] if msg["role"] != "system"
            ]

            return {
                "session_id": session_id,
                "conversation": conversation,
                "turn_count": session["turn_count"],
                "assessment_complete": session["assessment_complete"],
                "estimated_level": session["estimated_level"],
            }
