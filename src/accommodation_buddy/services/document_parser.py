import io
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def extract_docx_text(file_path: str | Path) -> str:
    from docx import Document

    doc = Document(str(file_path))
    paragraphs = []
    for para in doc.paragraphs:
        if para.text.strip():
            if para.style and para.style.name.startswith("Heading"):
                level = para.style.name.replace("Heading ", "").strip()
                try:
                    level = int(level)
                except ValueError:
                    level = 1
                paragraphs.append(f"{'#' * level} {para.text}")
            else:
                paragraphs.append(para.text)
    return "\n\n".join(paragraphs)


def extract_pptx_text(file_path: str | Path) -> str:
    from pptx import Presentation

    prs = Presentation(str(file_path))
    slides_text = []
    for i, slide in enumerate(prs.slides, 1):
        slide_parts = [f"## Slide {i}"]
        for shape in slide.shapes:
            if shape.has_text_frame:
                for paragraph in shape.text_frame.paragraphs:
                    text = paragraph.text.strip()
                    if text:
                        slide_parts.append(text)
        slides_text.append("\n\n".join(slide_parts))
    return "\n\n---\n\n".join(slides_text)


def extract_pdf_pages_as_images(file_path: str | Path) -> list[bytes]:
    from pdf2image import convert_from_path

    images = convert_from_path(str(file_path), dpi=200)
    result = []
    for img in images:
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        result.append(buf.getvalue())
    return result


def detect_file_type(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    type_map = {
        ".pdf": "pdf",
        ".docx": "docx",
        ".doc": "docx",
        ".pptx": "pptx",
        ".ppt": "pptx",
        ".png": "image",
        ".jpg": "image",
        ".jpeg": "image",
        ".gif": "image",
        ".bmp": "image",
        ".tiff": "image",
        ".webp": "image",
    }
    return type_map.get(ext, "pdf")
