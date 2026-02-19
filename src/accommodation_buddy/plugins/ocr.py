import base64
import logging

from accommodation_buddy.core.base_plugin import (
    AccommodationResult,
    BasePlugin,
    ClassProfile,
    PluginCategory,
    PluginManifest,
    StudentProfile,
)
from accommodation_buddy.services.document_parser import (
    extract_docx_text,
    extract_pdf_pages_as_images,
    extract_pptx_text,
)
from accommodation_buddy.core.prompts import OCR_SYSTEM_PROMPT, OCR_USER_PROMPT
from accommodation_buddy.services.ollama_client import OllamaClient

logger = logging.getLogger(__name__)


class OCRPlugin(BasePlugin):
    def manifest(self) -> PluginManifest:
        return PluginManifest(
            id="ocr",
            name="Document OCR / Text Extraction",
            description="Extracts structured text from uploaded documents using DeepSeek OCR",
            category=PluginCategory.DOCUMENT_ACCOMMODATION,
            icon="scan-text",
            default_enabled=True,
            always_on=True,
            requires_student_profile=False,
            requires_document=True,
            panel_template=None,
            order_hint=0,
        )

    async def generate(
        self,
        document_text: str,
        student_profile: StudentProfile | None,
        class_profile: ClassProfile | None,
        options: dict,
    ) -> AccommodationResult:
        file_path = options.get("file_path", "")
        file_type = options.get("file_type", "pdf")
        client = OllamaClient()

        from accommodation_buddy.config import settings

        ms = options.get("_model_settings")
        ocr_model = ms.ocr_model if ms else settings.ocr_model
        keep_alive = ms.keep_alive if ms else None

        if file_type == "docx":
            text = extract_docx_text(file_path)
            return AccommodationResult(
                plugin_id="ocr",
                generated_output={"text": text, "method": "python-docx"},
            )

        if file_type == "pptx":
            text = extract_pptx_text(file_path)
            return AccommodationResult(
                plugin_id="ocr",
                generated_output={"text": text, "method": "python-pptx"},
            )

        # PDF and images use DeepSeek OCR via Ollama
        if file_type == "pdf":
            page_images = extract_pdf_pages_as_images(file_path)
        elif file_type == "image":
            with open(file_path, "rb") as f:
                page_images = [f.read()]
        else:
            return AccommodationResult(
                plugin_id="ocr",
                generated_output={"text": "", "error": f"Unsupported file type: {file_type}"},
                status="failed",
            )

        all_text = []
        for i, img_bytes in enumerate(page_images):
            b64 = base64.b64encode(img_bytes).decode("utf-8")
            try:
                page_text = await client.generate(
                    prompt=OCR_USER_PROMPT,
                    model=ocr_model,
                    images=[b64],
                    system=OCR_SYSTEM_PROMPT,
                    keep_alive=keep_alive,
                )
                all_text.append(f"## Page {i + 1}\n\n{page_text}")
            except Exception:
                logger.exception(f"OCR failed for page {i + 1}")
                all_text.append(f"## Page {i + 1}\n\n[OCR extraction failed]")

        combined = "\n\n---\n\n".join(all_text)
        return AccommodationResult(
            plugin_id="ocr",
            generated_output={"text": combined, "method": "deepseek-ocr", "pages": len(page_images)},
        )
