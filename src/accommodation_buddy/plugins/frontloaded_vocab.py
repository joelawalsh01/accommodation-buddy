import json
import logging
import re

from accommodation_buddy.core.base_plugin import (
    AccommodationResult,
    BasePlugin,
    ClassProfile,
    PluginCategory,
    PluginManifest,
    StudentProfile,
)
from accommodation_buddy.core.prompts import VOCAB_PROMPT_TEMPLATE, VOCAB_SYSTEM_PROMPT
from accommodation_buddy.services.ollama_client import OllamaClient

logger = logging.getLogger(__name__)


def _extract_words(text: str) -> list[str]:
    """Extract unique words from text, lowercased and stripped of punctuation."""
    words = re.findall(r"[a-zA-Z]+(?:[-'][a-zA-Z]+)*", text)
    seen: set[str] = set()
    unique: list[str] = []
    for w in words:
        lower = w.lower()
        if lower not in seen and len(lower) > 2:
            seen.add(lower)
            unique.append(lower)
    return unique


def _find_rare_words(text: str, threshold: float = 3.5) -> list[tuple[str, float]]:
    """Use wordfreq's zipf_frequency to identify rare words below the threshold.

    A zipf frequency below ~3.5 indicates a word that is uncommon in everyday
    English and likely unfamiliar to ELL students. Academic vocabulary typically
    falls in the 2.0-3.5 range.
    """
    try:
        from wordfreq import zipf_frequency
    except ImportError:
        logger.warning(
            "wordfreq library not installed; falling back to returning all long words"
        )
        words = _extract_words(text)
        return [(w, 0.0) for w in words if len(w) >= 6][:40]

    words = _extract_words(text)
    rare: list[tuple[str, float]] = []
    for word in words:
        freq = zipf_frequency(word, "en")
        if freq < threshold:
            rare.append((word, round(freq, 2)))

    # Sort by frequency ascending (rarest first), limit to top 30
    rare.sort(key=lambda x: x[1])
    return rare[:30]


class FrontloadedVocabPlugin(BasePlugin):
    def manifest(self) -> PluginManifest:
        return PluginManifest(
            id="frontloaded_vocab",
            name="Frontloaded Language Identifier",
            description=(
                "Identifies rare and academic vocabulary in a document using "
                "frequency analysis, then generates student-friendly vocabulary "
                "cards with definitions, L1 analogues, and teaching strategies."
            ),
            category=PluginCategory.DOCUMENT_ACCOMMODATION,
            icon="book-open",
            default_enabled=True,
            requires_student_profile=True,
            requires_document=True,
            panel_template="plugin_panels/vocab_card.html",
            order_hint=20,
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

        if student_profile:
            if student_profile.english_proficiency_level:
                proficiency_level = student_profile.english_proficiency_level
            if student_profile.heritage_language:
                heritage_language = student_profile.heritage_language

        # Override threshold from options if provided
        threshold = options.get("frequency_threshold", 3.5)

        # Stage 1: frequency-based filtering
        rare_words = _find_rare_words(document_text, threshold=threshold)

        if not rare_words:
            return AccommodationResult(
                plugin_id="frontloaded_vocab",
                generated_output={
                    "vocab_cards": [],
                    "message": "No rare vocabulary found in this document.",
                },
            )

        word_list = "\n".join(
            f"- {word} (zipf frequency: {freq})" for word, freq in rare_words
        )

        prompt = VOCAB_PROMPT_TEMPLATE.format(
            proficiency_level=proficiency_level,
            heritage_language=heritage_language,
            word_list=word_list,
        )

        # Stage 2: LLM enrichment
        client = OllamaClient()

        try:
            raw_response = await client.generate(
                prompt=prompt,
                system=VOCAB_SYSTEM_PROMPT,
            )
        except Exception:
            logger.exception("LLM call failed for frontloaded_vocab plugin")
            # Return frequency data even if LLM fails
            fallback_cards = [
                {"word": word, "frequency_score": freq, "definition": None,
                 "l1_analogue": None, "teaching_strategy": None}
                for word, freq in rare_words
            ]
            return AccommodationResult(
                plugin_id="frontloaded_vocab",
                generated_output={
                    "vocab_cards": fallback_cards,
                    "warning": "LLM enrichment failed; frequency data only.",
                },
                status="generated",
            )

        try:
            parsed = json.loads(raw_response)
        except json.JSONDecodeError:
            logger.warning("Failed to parse LLM JSON for frontloaded_vocab, returning raw text")
            parsed = {
                "vocab_cards": [
                    {"word": word, "frequency_score": freq, "definition": None,
                     "l1_analogue": None, "teaching_strategy": None}
                    for word, freq in rare_words
                ],
                "raw_llm_response": raw_response,
                "parse_warning": "LLM response was not valid JSON.",
            }

        parsed["proficiency_level"] = proficiency_level
        parsed["heritage_language"] = heritage_language
        parsed["frequency_threshold"] = threshold
        parsed["total_rare_words_found"] = len(rare_words)

        return AccommodationResult(
            plugin_id="frontloaded_vocab",
            generated_output=parsed,
        )
