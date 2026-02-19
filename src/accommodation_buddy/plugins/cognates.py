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
from accommodation_buddy.core.prompts import COGNATES_PROMPT_TEMPLATE, COGNATES_SYSTEM_PROMPT
from accommodation_buddy.services.ollama_client import OllamaClient

logger = logging.getLogger(__name__)

# Built-in English-Spanish cognate dictionary for the most common academic cognates.
# Each entry: english_term -> (spanish_cognate, shared_root, teaching_note)
ENGLISH_SPANISH_COGNATES: dict[str, tuple[str, str, str]] = {
    "analyze": ("analizar", "Greek: analyein", "Same structure; stress difference on last syllable in Spanish"),
    "animal": ("animal", "Latin: animalis", "Identical spelling; pronunciation differs (ah-nee-MAHL)"),
    "area": ("area", "Latin: area", "Nearly identical; Spanish uses accent: area"),
    "article": ("articulo", "Latin: articulus", "Stress shifts to second syllable in Spanish"),
    "cause": ("causa", "Latin: causa", "Add -a ending; discuss false friend 'because/porque'"),
    "celebrate": ("celebrar", "Latin: celebrare", "Drop -ate, add -ar; verb conjugation differs"),
    "central": ("central", "Latin: centralis", "Identical spelling; pronunciation differs"),
    "circle": ("circulo", "Latin: circulus", "Add -o ending; connect to 'circular'"),
    "civilization": ("civilizacion", "Latin: civilis", "Replace -tion with -cion; accent on final syllable"),
    "classify": ("clasificar", "Latin: classis + facere", "Replace -fy with -ficar"),
    "collaborate": ("colaborar", "Latin: collaborare", "Simplify double-l; drop -ate, add -ar"),
    "community": ("comunidad", "Latin: communitas", "Replace -ty with -dad"),
    "compare": ("comparar", "Latin: comparare", "Add -ar ending"),
    "complete": ("completar", "Latin: completus", "Add -ar for verb form"),
    "concentrate": ("concentrar", "Latin: concentrare", "Drop -ate, add -ar"),
    "conclusion": ("conclusion", "Latin: conclusio", "Nearly identical; accent on final syllable in Spanish"),
    "confirm": ("confirmar", "Latin: confirmare", "Add -ar ending"),
    "connect": ("conectar", "Latin: connectere", "Simplify double-n; add -ar"),
    "consequence": ("consecuencia", "Latin: consequentia", "Replace -ce with -cia"),
    "consider": ("considerar", "Latin: considerare", "Add -ar ending"),
    "construct": ("construir", "Latin: construere", "Replace -ct with -ir; irregular verb"),
    "contain": ("contener", "Latin: continere", "Replace -tain with -tener"),
    "context": ("contexto", "Latin: contextus", "Add -o ending"),
    "contribute": ("contribuir", "Latin: contribuere", "Replace -te with -ir"),
    "control": ("control", "Latin: contrarotulus", "Identical spelling"),
    "convert": ("convertir", "Latin: convertere", "Add -ir ending"),
    "correct": ("correcto", "Latin: correctus", "Add -o ending"),
    "create": ("crear", "Latin: creare", "Drop -ate, add -ar"),
    "culture": ("cultura", "Latin: cultura", "Add -a ending"),
    "decision": ("decision", "Latin: decisio", "Identical structure; accent on final syllable"),
    "define": ("definir", "Latin: definire", "Replace -e with -ir"),
    "describe": ("describir", "Latin: describere", "Replace -e with -ir"),
    "determine": ("determinar", "Latin: determinare", "Replace -e with -ar"),
    "develop": ("desarrollar", "Latin: dis + falupare", "False cognate warning: forms differ significantly"),
    "difference": ("diferencia", "Latin: differentia", "Replace -ce with -cia; simplify double-f"),
    "distribute": ("distribuir", "Latin: distribuere", "Replace -te with -ir"),
    "economy": ("economia", "Greek: oikonomia", "Add -ia ending; accent shifts"),
    "education": ("educacion", "Latin: educatio", "Replace -tion with -cion"),
    "element": ("elemento", "Latin: elementum", "Add -o ending"),
    "energy": ("energia", "Greek: energeia", "Replace -y with -ia"),
    "establish": ("establecer", "Latin: stabilire", "Replace -ish with -ecer"),
    "evaluate": ("evaluar", "Latin: evaluare", "Drop -ate, add -ar"),
    "evidence": ("evidencia", "Latin: evidentia", "Replace -ce with -cia"),
    "examine": ("examinar", "Latin: examinare", "Replace -e with -ar"),
    "example": ("ejemplo", "Latin: exemplum", "Significant spelling change; highlight similarity"),
    "experiment": ("experimento", "Latin: experimentum", "Add -o ending"),
    "explain": ("explicar", "Latin: explicare", "Replace -ain with -icar"),
    "explore": ("explorar", "Latin: explorare", "Add -ar ending"),
    "expression": ("expresion", "Latin: expressio", "Replace -ssion with -sion"),
    "factor": ("factor", "Latin: factor", "Identical spelling"),
    "family": ("familia", "Latin: familia", "Replace -y with -ia"),
    "final": ("final", "Latin: finalis", "Identical spelling"),
    "formula": ("formula", "Latin: formula", "Identical spelling; accent differs"),
    "fraction": ("fraccion", "Latin: fractio", "Replace -tion with -cion"),
    "function": ("funcion", "Latin: functio", "Replace -tion with -cion"),
    "fundamental": ("fundamental", "Latin: fundamentalis", "Identical spelling"),
    "generate": ("generar", "Latin: generare", "Drop -ate, add -ar"),
    "geography": ("geografia", "Greek: geographia", "Replace -y with -ia"),
    "history": ("historia", "Greek: historia", "Add -ia ending"),
    "identify": ("identificar", "Latin: identificare", "Replace -fy with -ficar"),
    "illustrate": ("ilustrar", "Latin: illustrare", "Simplify double-l; drop -ate"),
    "imagine": ("imaginar", "Latin: imaginare", "Replace -e with -ar"),
    "important": ("importante", "Latin: importans", "Add -e ending"),
    "include": ("incluir", "Latin: includere", "Replace -de with -ir"),
    "indicate": ("indicar", "Latin: indicare", "Drop -ate, add -ar"),
    "individual": ("individual", "Latin: individualis", "Identical spelling"),
    "influence": ("influencia", "Latin: influentia", "Replace -ce with -cia"),
    "information": ("informacion", "Latin: informatio", "Replace -tion with -cion"),
    "initial": ("inicial", "Latin: initialis", "Replace -tial with -cial"),
    "interpret": ("interpretar", "Latin: interpretari", "Add -ar ending"),
    "introduce": ("introducir", "Latin: introducere", "Replace -ce with -cir"),
    "investigate": ("investigar", "Latin: investigare", "Drop -ate, add -ar"),
    "laboratory": ("laboratorio", "Latin: laboratorium", "Add -io ending"),
    "language": ("lenguaje", "Latin: lingua", "Significant spelling change; highlight root"),
    "literary": ("literario", "Latin: literarius", "Replace -ary with -ario"),
    "material": ("material", "Latin: materialis", "Identical spelling"),
    "mathematics": ("matematicas", "Greek: mathematikos", "Replace -ics with -icas"),
    "method": ("metodo", "Greek: methodos", "Add -o ending"),
    "model": ("modelo", "Latin: modulus", "Add -o ending"),
    "modify": ("modificar", "Latin: modificare", "Replace -fy with -ficar"),
    "multiple": ("multiple", "Latin: multiplex", "Identical spelling"),
    "natural": ("natural", "Latin: naturalis", "Identical spelling"),
    "necessary": ("necesario", "Latin: necessarius", "Replace -ary with -ario"),
    "observe": ("observar", "Latin: observare", "Replace -e with -ar"),
    "obtain": ("obtener", "Latin: obtinere", "Replace -tain with -tener"),
    "occur": ("ocurrir", "Latin: occurrere", "Simplify double-c; add -ir"),
    "opinion": ("opinion", "Latin: opinio", "Identical spelling; accent on final syllable"),
    "opportunity": ("oportunidad", "Latin: opportunitas", "Replace -ty with -dad"),
    "organize": ("organizar", "Greek: organon", "Replace -ize with -izar"),
    "original": ("original", "Latin: originalis", "Identical spelling"),
    "participate": ("participar", "Latin: participare", "Drop -ate, add -ar"),
    "percent": ("por ciento", "Latin: per centum", "Two words in Spanish; same root"),
    "period": ("periodo", "Greek: periodos", "Add -o ending"),
    "permit": ("permitir", "Latin: permittere", "Add -ir ending"),
    "physical": ("fisico", "Greek: physikos", "Spelling changes significantly; ph->f"),
    "population": ("poblacion", "Latin: populatio", "Replace -tion with -cion; root changes"),
    "positive": ("positivo", "Latin: positivus", "Replace -ive with -ivo"),
    "possible": ("posible", "Latin: possibilis", "Simplify double-s; drop one letter"),
    "president": ("presidente", "Latin: praesidens", "Add -e ending"),
    "principle": ("principio", "Latin: principium", "Replace -le with -io"),
    "problem": ("problema", "Greek: problema", "Add -a ending; masculine in Spanish despite -a"),
    "process": ("proceso", "Latin: processus", "Add -o ending; simplify double-s"),
    "produce": ("producir", "Latin: producere", "Replace -ce with -cir"),
    "professional": ("profesional", "Latin: professionalis", "Simplify double-s"),
    "program": ("programa", "Greek: programma", "Add -a ending"),
    "project": ("proyecto", "Latin: projectum", "Spelling changes; highlight shared root"),
    "protect": ("proteger", "Latin: protegere", "Replace -ct with -ger"),
    "reduce": ("reducir", "Latin: reducere", "Replace -ce with -cir"),
    "region": ("region", "Latin: regio", "Identical spelling; accent on final syllable"),
    "represent": ("representar", "Latin: repraesentare", "Add -ar ending"),
    "require": ("requerir", "Latin: requirere", "Replace -e with -ir"),
    "respond": ("responder", "Latin: respondere", "Add -er ending"),
    "result": ("resultado", "Latin: resultare", "Add -ado ending"),
    "revolution": ("revolucion", "Latin: revolutio", "Replace -tion with -cion"),
    "science": ("ciencia", "Latin: scientia", "Replace sc- with c-; -ce with -cia"),
    "select": ("seleccionar", "Latin: selectus", "Add -ionar; double-c in Spanish"),
    "similar": ("similar", "Latin: similis", "Identical spelling"),
    "solution": ("solucion", "Latin: solutio", "Replace -tion with -cion"),
    "structure": ("estructura", "Latin: structura", "Add e- prefix"),
    "substitute": ("sustituir", "Latin: substituere", "Replace -ute with -uir"),
    "temperature": ("temperatura", "Latin: temperatura", "Add -a ending"),
    "theory": ("teoria", "Greek: theoria", "Replace -y with -ia"),
    "tradition": ("tradicion", "Latin: traditio", "Replace -tion with -cion"),
    "transfer": ("transferir", "Latin: transferre", "Add -ir ending"),
    "transform": ("transformar", "Latin: transformare", "Add -ar ending"),
    "variety": ("variedad", "Latin: varietas", "Replace -ty with -dad"),
    "vocabulary": ("vocabulario", "Latin: vocabularium", "Replace -ary with -ario"),
    "volume": ("volumen", "Latin: volumen", "Replace -e with -en"),
}

class CognatesPlugin(BasePlugin):
    def manifest(self) -> PluginManifest:
        return PluginManifest(
            id="cognates",
            name="Cognates Identifier",
            description=(
                "Identifies cognate pairs between English and the student's heritage "
                "language to leverage L1 knowledge for vocabulary acquisition. Uses a "
                "built-in dictionary for English-Spanish and LLM for other language pairs."
            ),
            category=PluginCategory.DOCUMENT_ACCOMMODATION,
            icon="link",
            default_enabled=True,
            requires_student_profile=True,
            requires_document=True,
            panel_template="plugin_panels/cognates.html",
            order_hint=40,
        )

    def _extract_document_words(self, text: str) -> list[str]:
        """Extract unique lowercase words from the document."""
        words = re.findall(r"[a-zA-Z]+(?:[-'][a-zA-Z]+)*", text)
        seen: set[str] = set()
        unique: list[str] = []
        for w in words:
            lower = w.lower()
            if lower not in seen and len(lower) > 2:
                seen.add(lower)
                unique.append(lower)
        return unique

    def _lookup_spanish_cognates(
        self, document_words: list[str],
    ) -> list[dict[str, str]]:
        """Look up cognates from the built-in English-Spanish dictionary."""
        results: list[dict[str, str]] = []
        for word in document_words:
            if word in ENGLISH_SPANISH_COGNATES:
                spanish, root, note = ENGLISH_SPANISH_COGNATES[word]
                results.append({
                    "english_term": word,
                    "l1_cognate": spanish,
                    "root": root,
                    "teaching_note": note,
                })
        return results

    async def generate(
        self,
        document_text: str,
        student_profile: StudentProfile | None,
        class_profile: ClassProfile | None,
        options: dict,
    ) -> AccommodationResult:
        proficiency_level = 3
        heritage_language = "Spanish"

        if student_profile:
            if student_profile.english_proficiency_level:
                proficiency_level = student_profile.english_proficiency_level
            if student_profile.heritage_language:
                heritage_language = student_profile.heritage_language

        document_words = self._extract_document_words(document_text)

        # Use built-in dictionary for Spanish
        if heritage_language.lower() in ("spanish", "espanol", "espanol", "es"):
            cognate_pairs = self._lookup_spanish_cognates(document_words)
            return AccommodationResult(
                plugin_id="cognates",
                generated_output={
                    "cognate_pairs": cognate_pairs,
                    "heritage_language": heritage_language,
                    "proficiency_level": proficiency_level,
                    "source": "built-in dictionary",
                    "total_found": len(cognate_pairs),
                },
            )

        # Fall back to LLM for all other language pairs
        prompt = COGNATES_PROMPT_TEMPLATE.format(
            heritage_language=heritage_language,
            proficiency_level=proficiency_level,
            document_text=document_text[:8000],
        )

        client = OllamaClient()

        try:
            raw_response = await client.generate(
                prompt=prompt,
                system=COGNATES_SYSTEM_PROMPT,
            )
        except Exception:
            logger.exception("LLM call failed for cognates plugin")
            return AccommodationResult(
                plugin_id="cognates",
                generated_output={
                    "error": "LLM generation failed",
                    "heritage_language": heritage_language,
                },
                status="failed",
            )

        try:
            parsed = json.loads(raw_response)
        except json.JSONDecodeError:
            logger.warning("Failed to parse LLM JSON for cognates, returning raw text")
            parsed = {
                "cognate_pairs": [],
                "raw_llm_response": raw_response,
                "parse_warning": "LLM response was not valid JSON.",
            }

        parsed["heritage_language"] = heritage_language
        parsed["proficiency_level"] = proficiency_level
        parsed["source"] = "llm"

        return AccommodationResult(
            plugin_id="cognates",
            generated_output=parsed,
        )
