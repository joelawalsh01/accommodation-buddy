import asyncio
import base64
import logging
import time

from accommodation_buddy.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _update_doc_status(db, doc, status, detail, progress=None):
    """Helper to update document status in the database."""
    doc.ocr_status = status
    doc.status_detail = detail
    if progress is not None:
        doc.ocr_progress = progress
    await db.commit()


@celery_app.task(bind=True, name="process_document_ocr")
def process_document_ocr(self, document_id: int, teacher_id: int | None = None, ocr_mode: str = "fast"):
    async def _run():
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy.ext.asyncio import async_sessionmaker

        from accommodation_buddy.config import settings
        from accommodation_buddy.db.models import Document
        from accommodation_buddy.services.document_parser import (
            extract_docx_text,
            extract_image_text_fast,
            extract_pdf_pages_as_images,
            extract_pdf_text_fast,
            extract_pptx_text,
        )
        from accommodation_buddy.services.model_settings import get_teacher_model_settings
        from accommodation_buddy.services.ollama_client import OllamaClient

        engine = create_async_engine(settings.database_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)

        async with session_factory() as db:
            doc = await db.get(Document, document_id)
            if doc is None:
                return {"error": "Document not found"}

            # Resolve model settings
            tid = teacher_id or doc.teacher_id
            ms = await get_teacher_model_settings(tid, db)
            ocr_model = ms.ocr_model
            keep_alive = ms.keep_alive

            file_path = doc.file_path
            file_type = doc.file_type

            await _update_doc_status(db, doc, "processing", "Initializing...", 0)
            t0 = time.monotonic()

            try:
                # DOCX extraction
                if file_type == "docx":
                    await _update_doc_status(db, doc, "processing", "Extracting text from DOCX...", 30)
                    text = extract_docx_text(file_path)
                    await _update_doc_status(db, doc, "processing", "Finalizing...", 90)
                    doc.extracted_text = text
                    elapsed = int(time.monotonic() - t0)
                    await _update_doc_status(db, doc, "complete", f"Extracted {len(text)} characters in {elapsed}s", 100)
                    return {"status": "complete", "document_id": document_id}

                # PPTX extraction
                if file_type == "pptx":
                    await _update_doc_status(db, doc, "processing", "Extracting text from PPTX...", 30)
                    text = extract_pptx_text(file_path)
                    await _update_doc_status(db, doc, "processing", "Finalizing...", 90)
                    doc.extracted_text = text
                    elapsed = int(time.monotonic() - t0)
                    await _update_doc_status(db, doc, "complete", f"Extracted {len(text)} characters in {elapsed}s", 100)
                    return {"status": "complete", "document_id": document_id}

                # Fast OCR mode: use Tesseract (no LLM needed)
                if ocr_mode == "fast":
                    if file_type == "pdf":
                        await _update_doc_status(db, doc, "processing", "Fast OCR (Tesseract)...", 30)
                        text = extract_pdf_text_fast(file_path)
                    elif file_type == "image":
                        await _update_doc_status(db, doc, "processing", "Fast OCR (Tesseract)...", 30)
                        text = extract_image_text_fast(file_path)
                    else:
                        await _update_doc_status(db, doc, "failed", f"Unsupported file type: {file_type}", 0)
                        return {"error": f"Unsupported file type: {file_type}"}

                    doc.extracted_text = text
                    elapsed = int(time.monotonic() - t0)
                    await _update_doc_status(
                        db, doc, "complete",
                        f"Extracted {len(text)} characters in {elapsed}s (fast mode)",
                        100,
                    )
                    return {"status": "complete", "document_id": document_id}

                # LLM Vision OCR mode: use Ollama
                if file_type == "pdf":
                    await _update_doc_status(db, doc, "processing", "Converting PDF to images...", 10)
                    page_images = extract_pdf_pages_as_images(file_path)
                elif file_type == "image":
                    await _update_doc_status(db, doc, "processing", "Loading image...", 10)
                    with open(file_path, "rb") as f:
                        page_images = [f.read()]
                else:
                    await _update_doc_status(db, doc, "failed", f"Unsupported file type: {file_type}", 0)
                    return {"error": f"Unsupported file type: {file_type}"}

                total_pages = len(page_images)
                await _update_doc_status(
                    db, doc, "processing",
                    f"Loading OCR model ({ocr_model})...",
                    15,
                )

                from accommodation_buddy.core.prompts import OCR_SYSTEM_PROMPT, OCR_USER_PROMPT

                client = OllamaClient()

                all_text = []
                for i, img_bytes in enumerate(page_images):
                    page_num = i + 1
                    pct = 20 + int(70 * page_num / total_pages)
                    await _update_doc_status(
                        db, doc, "processing",
                        f"OCR processing page {page_num} of {total_pages}...",
                        pct,
                    )

                    b64 = base64.b64encode(img_bytes).decode("utf-8")
                    # Prepend system prompt to user prompt because the
                    # deepseek-ocr Modelfile template ({{ .Prompt }}) drops
                    # the system parameter entirely.
                    combined_prompt = f"{OCR_SYSTEM_PROMPT}\n\n{OCR_USER_PROMPT}"
                    try:
                        page_text = await client.generate(
                            prompt=combined_prompt,
                            model=ocr_model,
                            images=[b64],
                            keep_alive=keep_alive,
                            options={"num_predict": 4096},
                        )
                        logger.info(f"Page {page_num} OCR result: {len(page_text)} chars, preview: {repr(page_text[:100])}")
                        all_text.append(f"## Page {page_num}\n\n{page_text}")
                    except Exception:
                        logger.exception(f"OCR failed for page {page_num}")
                        all_text.append(f"## Page {page_num}\n\n[OCR extraction failed]")

                await _update_doc_status(db, doc, "processing", "Finalizing extraction...", 95)

                combined = "\n\n---\n\n".join(all_text)
                doc.extracted_text = combined
                elapsed = int(time.monotonic() - t0)
                minutes, secs = divmod(elapsed, 60)
                time_str = f"{minutes}m {secs}s" if minutes else f"{secs}s"
                await _update_doc_status(
                    db, doc, "complete",
                    f"Extracted {len(combined)} characters from {total_pages} page(s) in {time_str}",
                    100,
                )
                return {"status": "complete", "document_id": document_id}

            except Exception as e:
                await _update_doc_status(db, doc, "failed", f"Error: {e}", 0)
                logger.exception(f"OCR failed for document {document_id}")
                return {"error": str(e)}

        await engine.dispose()

    return _run_async(_run())


@celery_app.task(bind=True, name="run_plugin")
def run_plugin(
    self,
    plugin_id: str,
    document_id: int,
    student_id: int | None = None,
    options: dict | None = None,
    teacher_id: int | None = None,
):
    from accommodation_buddy.core.registry import PluginRegistry

    registry = PluginRegistry.get_instance()
    plugin = registry.get(plugin_id)
    if plugin is None:
        return {"error": f"Plugin {plugin_id} not found"}

    async def _run():
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

        from accommodation_buddy.config import settings
        from accommodation_buddy.core.base_plugin import ClassProfile, StudentProfile
        from accommodation_buddy.db.models import (
            Accommodation,
            Document,
            Student,
            Class,
        )
        from accommodation_buddy.services.model_settings import get_teacher_model_settings

        engine = create_async_engine(settings.database_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)

        async with session_factory() as db:
            doc = await db.get(Document, document_id)
            if doc is None:
                return {"error": "Document not found"}

            # Resolve model settings
            tid = teacher_id or doc.teacher_id
            ms = await get_teacher_model_settings(tid, db)

            student_profile = None
            if student_id:
                student = await db.get(Student, student_id)
                if student:
                    student_profile = StudentProfile(
                        id=student.id,
                        pseudonym=student.pseudonym,
                        heritage_language=student.heritage_language,
                        english_proficiency_level=student.english_proficiency_level,
                        l1_proficiency_level=student.l1_proficiency_level,
                        proficiency_notes=student.proficiency_notes,
                    )

            class_obj = await db.get(Class, doc.class_id)
            class_profile = ClassProfile(
                id=class_obj.id,
                name=class_obj.name,
                grade_level=class_obj.grade_level,
            ) if class_obj else None

            merged_options = dict(options or {})
            merged_options["_model_settings"] = ms

            result = await plugin.generate(
                document_text=doc.extracted_text or "",
                student_profile=student_profile,
                class_profile=class_profile,
                options=merged_options,
            )

            accommodation = Accommodation(
                document_id=document_id,
                plugin_id=plugin_id,
                target_student_id=student_id,
                input_context={"document_text_length": len(doc.extracted_text or "")},
                generated_output=result.generated_output,
                status=result.status,
            )
            db.add(accommodation)
            await db.commit()

            return {
                "status": result.status,
                "accommodation_id": accommodation.id,
                "output": result.generated_output,
            }
        await engine.dispose()

    return _run_async(_run())
