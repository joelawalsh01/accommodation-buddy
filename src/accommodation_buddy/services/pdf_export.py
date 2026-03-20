import io
import logging
import re
from pathlib import Path

from jinja2 import Environment
from weasyprint import HTML

logger = logging.getLogger(__name__)


def split_text_by_pages(text: str) -> list[tuple[int, str]]:
    """Split text by '## Page N' markers. Returns [(page_num, text), ...].

    If no page markers found, returns empty list (caller should fall back).
    """
    # Match ## Page N headers (with optional trailing whitespace)
    pattern = r"##\s+Page\s+(\d+)\s*\n"
    splits = re.split(pattern, text)

    # splits alternates: [preamble, page_num, text, page_num, text, ...]
    if len(splits) < 3:
        return []

    pages = []
    # Skip splits[0] (preamble before first page marker)
    for i in range(1, len(splits), 2):
        page_num = int(splits[i])
        page_text = splits[i + 1].strip().rstrip("-").strip() if i + 1 < len(splits) else ""
        pages.append((page_num, page_text))

    return pages


def split_translation_by_english_pages(
    english_pages: list[tuple[int, str]],
    translated_text: str,
) -> list[tuple[int, str]]:
    """Split translated text to match English page structure.

    First tries to split by ## Page N markers. If that fails or the count
    doesn't match, splits the translation proportionally based on English
    page lengths (by character count).
    """
    # Try marker-based split first
    trans_pages = split_text_by_pages(translated_text)
    if trans_pages and len(trans_pages) >= len(english_pages):
        return trans_pages

    # Strip any page markers from translation before proportional split
    clean_trans = re.sub(r"##\s+Page\s+\d+\s*\n", "", translated_text)
    # Also strip --- separators
    clean_trans = re.sub(r"\n*---\n*", "\n\n", clean_trans).strip()

    if not english_pages or not clean_trans:
        return []

    # Single page — no splitting needed
    if len(english_pages) == 1:
        return [(english_pages[0][0], clean_trans)]

    # Proportional split based on English page character lengths
    eng_lengths = [len(text) for _, text in english_pages]
    total_eng = sum(eng_lengths) or 1

    # Split translation into paragraphs to avoid cutting mid-sentence
    paragraphs = re.split(r"\n\s*\n", clean_trans)

    result = []
    para_idx = 0
    for page_i, (page_num, _) in enumerate(english_pages):
        if page_i == len(english_pages) - 1:
            # Last page gets all remaining paragraphs
            page_text = "\n\n".join(paragraphs[para_idx:])
        else:
            # Calculate target character count for this page
            target_chars = int(len(clean_trans) * eng_lengths[page_i] / total_eng)
            collected = []
            chars_so_far = 0
            while para_idx < len(paragraphs) and chars_so_far < target_chars:
                collected.append(paragraphs[para_idx])
                chars_so_far += len(paragraphs[para_idx])
                para_idx += 1
            # Ensure at least one paragraph per page if available
            if not collected and para_idx < len(paragraphs):
                collected.append(paragraphs[para_idx])
                para_idx += 1
            page_text = "\n\n".join(collected)

        result.append((page_num, page_text.strip()))

    return result


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


def render_inline_translation_pdf(
    jinja_env: Environment,
    document,
    teacher,
    class_obj,
    student,
    english_pages: list[tuple[int, str]],
    translation_pages: list[tuple[int, str]],
    non_translation_accommodations: list,
    plugin_names: dict[str, str],
    show_english: bool = True,
) -> bytes:
    """Render per-page translation pages plus remaining accommodations.

    When show_english is False (e.g. original PDF pages are interleaved),
    only the translation text is rendered per page.
    """
    import datetime

    template = jinja_env.get_template("export_pdf_inline.html")

    # Build a dict for quick lookup of translation by page number
    trans_by_page = {num: text for num, text in translation_pages}

    # Pair up pages
    page_pairs = []
    for page_num, eng_text in english_pages:
        page_pairs.append({
            "page_num": page_num,
            "english": eng_text,
            "translation": trans_by_page.get(page_num, ""),
        })

    html_str = template.render(
        document=document,
        teacher=teacher,
        class_obj=class_obj,
        student=student,
        page_pairs=page_pairs,
        show_english=show_english,
        accommodations=non_translation_accommodations,
        plugin_names=plugin_names,
        export_date=datetime.datetime.now().strftime("%B %d, %Y at %I:%M %p"),
    )

    return HTML(string=html_str).write_pdf()


def merge_with_original(
    original_path: str,
    accommodations_pdf: bytes,
    inline_page_pdfs: list[bytes] | None = None,
) -> bytes:
    """Merge accommodation pages with the original PDF.

    If inline_page_pdfs is provided, interleave original pages with
    per-page translation PDFs, then append the accommodations PDF at end.
    Otherwise, prepend original pages then append accommodations.
    """
    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter()

    original = Path(original_path)
    orig_reader = None
    if original.exists() and original.suffix.lower() == ".pdf":
        try:
            orig_reader = PdfReader(str(original))
        except Exception:
            logger.warning(f"Could not read original PDF: {original_path}")

    if inline_page_pdfs and orig_reader:
        # Interleave: [orig_page_N] [inline_translation_page_N] ...
        num_orig = len(orig_reader.pages)
        num_inline = len(inline_page_pdfs)
        max_pages = max(num_orig, num_inline)

        for i in range(max_pages):
            if i < num_orig:
                writer.add_page(orig_reader.pages[i])
            if i < num_inline:
                inline_reader = PdfReader(io.BytesIO(inline_page_pdfs[i]))
                for page in inline_reader.pages:
                    writer.add_page(page)

        # Append remaining accommodation pages (non-translation)
        if accommodations_pdf:
            acc_reader = PdfReader(io.BytesIO(accommodations_pdf))
            for page in acc_reader.pages:
                writer.add_page(page)
    else:
        # Default append mode: original pages first, then accommodations
        if orig_reader:
            for page in orig_reader.pages:
                writer.add_page(page)

        acc_reader = PdfReader(io.BytesIO(accommodations_pdf))
        for page in acc_reader.pages:
            writer.add_page(page)

    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()
