import io
import logging
from pathlib import Path

from jinja2 import Environment
from weasyprint import HTML

logger = logging.getLogger(__name__)


def render_accommodations_pdf(
    jinja_env: Environment,
    document,
    teacher,
    class_obj,
    student,
    accommodations: list,
    plugin_names: dict[str, str],
) -> bytes:
    """Render accommodations as a standalone PDF."""
    import datetime

    template = jinja_env.get_template("export_pdf.html")
    html_str = template.render(
        document=document,
        teacher=teacher,
        class_obj=class_obj,
        student=student,
        accommodations=accommodations,
        plugin_names=plugin_names,
        export_date=datetime.datetime.now().strftime("%B %d, %Y at %I:%M %p"),
    )

    acc_pdf_bytes = HTML(string=html_str).write_pdf()
    return acc_pdf_bytes


def merge_with_original(
    original_path: str,
    accommodations_pdf: bytes,
    mode: str = "append",
) -> bytes:
    """Merge accommodation pages with the original PDF.

    Modes:
        append: Original pages first, then accommodation pages
        interleave: After each original page, insert accommodation pages
    """
    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter()

    # Add original pages
    original = Path(original_path)
    if original.exists() and original.suffix.lower() == ".pdf":
        try:
            orig_reader = PdfReader(str(original))
            for page in orig_reader.pages:
                writer.add_page(page)
        except Exception:
            logger.warning(f"Could not read original PDF: {original_path}")

    # Add accommodation pages
    acc_reader = PdfReader(io.BytesIO(accommodations_pdf))
    for page in acc_reader.pages:
        writer.add_page(page)

    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()
