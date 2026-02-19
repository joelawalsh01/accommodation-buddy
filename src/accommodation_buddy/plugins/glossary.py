import logging
from typing import TYPE_CHECKING

from accommodation_buddy.core.base_plugin import (
    AccommodationResult,
    BasePlugin,
    ClassProfile,
    PluginCategory,
    PluginManifest,
    StudentProfile,
)

if TYPE_CHECKING:
    from fastapi import APIRouter

logger = logging.getLogger(__name__)


class GlossaryPlugin(BasePlugin):
    """Personal Language Glossary -- a non-LLM CRUD tool.

    Students build a personal glossary of terms they encounter across documents.
    The plugin reads and writes to the ``glossary_entries`` table through the
    database session.  ``generate()`` simply returns existing entries for the
    student so they can be rendered in the UI.
    """

    def manifest(self) -> PluginManifest:
        return PluginManifest(
            id="glossary",
            name="Personal Language Glossary",
            description=(
                "A personal vocabulary notebook where students collect terms, "
                "definitions, L1 translations, and context sentences across all "
                "their documents. No LLM required."
            ),
            category=PluginCategory.STUDENT_TOOL,
            icon="book-marked",
            default_enabled=True,
            requires_student_profile=True,
            requires_document=False,
            panel_template=None,
            order_hint=80,
        )

    async def generate(
        self,
        document_text: str,
        student_profile: StudentProfile | None,
        class_profile: ClassProfile | None,
        options: dict,
    ) -> AccommodationResult:
        """Return existing glossary entries for the student.

        This plugin does not use an LLM.  It reads glossary entries from the
        database.  The database session is passed via ``options["db"]``.  If no
        session is available (e.g., during testing), an empty list is returned.
        """
        if not student_profile:
            return AccommodationResult(
                plugin_id="glossary",
                generated_output={
                    "entries": [],
                    "message": "No student profile provided.",
                },
            )

        db = options.get("db")
        if db is None:
            logger.warning("No database session provided to glossary plugin")
            return AccommodationResult(
                plugin_id="glossary",
                generated_output={
                    "entries": [],
                    "student_id": student_profile.id,
                    "message": "Database session not available.",
                },
            )

        from sqlalchemy import select

        from accommodation_buddy.db.models import GlossaryEntry

        try:
            stmt = (
                select(GlossaryEntry)
                .where(GlossaryEntry.student_id == student_profile.id)
                .order_by(GlossaryEntry.created_at.desc())
            )
            result = await db.execute(stmt)
            rows = result.scalars().all()

            entries = [
                {
                    "id": entry.id,
                    "term": entry.term,
                    "definition": entry.definition,
                    "l1_translation": entry.l1_translation,
                    "context_sentence": entry.context_sentence,
                    "source_document_id": entry.source_document_id,
                    "created_at": entry.created_at.isoformat() if entry.created_at else None,
                }
                for entry in rows
            ]
        except Exception:
            logger.exception("Failed to fetch glossary entries from database")
            entries = []

        return AccommodationResult(
            plugin_id="glossary",
            generated_output={
                "entries": entries,
                "student_id": student_profile.id,
                "total_entries": len(entries),
            },
        )

    def register_routes(self, router: "APIRouter") -> None:
        """Register CRUD endpoints for glossary entries."""
        from fastapi import Depends
        from sqlalchemy import select
        from sqlalchemy.ext.asyncio import AsyncSession

        from accommodation_buddy.db.models import GlossaryEntry
        from accommodation_buddy.db.session import get_db

        @router.post("/plugins/glossary/entries")
        async def create_glossary_entry(
            payload: dict,
            db: AsyncSession = Depends(get_db),
        ) -> dict:
            """Create a new glossary entry.

            Expected payload:
            {
                "student_id": 1,
                "term": "hypothesis",
                "definition": "An educated guess...",
                "l1_translation": "hipotesis",
                "context_sentence": "We formed a hypothesis about...",
                "source_document_id": 5  (optional)
            }
            """
            student_id = payload.get("student_id")
            term = payload.get("term")

            if not student_id or not term:
                return {"error": "student_id and term are required."}

            entry = GlossaryEntry(
                student_id=student_id,
                term=term,
                definition=payload.get("definition"),
                l1_translation=payload.get("l1_translation"),
                context_sentence=payload.get("context_sentence"),
                source_document_id=payload.get("source_document_id"),
            )
            db.add(entry)
            await db.commit()
            await db.refresh(entry)

            return {
                "id": entry.id,
                "term": entry.term,
                "definition": entry.definition,
                "l1_translation": entry.l1_translation,
                "context_sentence": entry.context_sentence,
                "source_document_id": entry.source_document_id,
                "created_at": entry.created_at.isoformat() if entry.created_at else None,
            }

        @router.get("/plugins/glossary/entries/{student_id}")
        async def list_glossary_entries(
            student_id: int,
            db: AsyncSession = Depends(get_db),
        ) -> dict:
            """List all glossary entries for a student."""
            stmt = (
                select(GlossaryEntry)
                .where(GlossaryEntry.student_id == student_id)
                .order_by(GlossaryEntry.created_at.desc())
            )
            result = await db.execute(stmt)
            rows = result.scalars().all()

            entries = [
                {
                    "id": entry.id,
                    "term": entry.term,
                    "definition": entry.definition,
                    "l1_translation": entry.l1_translation,
                    "context_sentence": entry.context_sentence,
                    "source_document_id": entry.source_document_id,
                    "created_at": entry.created_at.isoformat() if entry.created_at else None,
                }
                for entry in rows
            ]

            return {"student_id": student_id, "entries": entries, "total": len(entries)}

        @router.put("/plugins/glossary/entries/{entry_id}")
        async def update_glossary_entry(
            entry_id: int,
            payload: dict,
            db: AsyncSession = Depends(get_db),
        ) -> dict:
            """Update an existing glossary entry.

            Expected payload (all fields optional):
            {
                "term": "...",
                "definition": "...",
                "l1_translation": "...",
                "context_sentence": "..."
            }
            """
            stmt = select(GlossaryEntry).where(GlossaryEntry.id == entry_id)
            result = await db.execute(stmt)
            entry = result.scalar_one_or_none()

            if not entry:
                return {"error": f"Glossary entry {entry_id} not found."}

            if "term" in payload:
                entry.term = payload["term"]
            if "definition" in payload:
                entry.definition = payload["definition"]
            if "l1_translation" in payload:
                entry.l1_translation = payload["l1_translation"]
            if "context_sentence" in payload:
                entry.context_sentence = payload["context_sentence"]

            await db.commit()
            await db.refresh(entry)

            return {
                "id": entry.id,
                "term": entry.term,
                "definition": entry.definition,
                "l1_translation": entry.l1_translation,
                "context_sentence": entry.context_sentence,
                "source_document_id": entry.source_document_id,
                "created_at": entry.created_at.isoformat() if entry.created_at else None,
            }

        @router.delete("/plugins/glossary/entries/{entry_id}")
        async def delete_glossary_entry(
            entry_id: int,
            db: AsyncSession = Depends(get_db),
        ) -> dict:
            """Delete a glossary entry."""
            stmt = select(GlossaryEntry).where(GlossaryEntry.id == entry_id)
            result = await db.execute(stmt)
            entry = result.scalar_one_or_none()

            if not entry:
                return {"error": f"Glossary entry {entry_id} not found."}

            await db.delete(entry)
            await db.commit()

            return {"deleted": True, "entry_id": entry_id}
