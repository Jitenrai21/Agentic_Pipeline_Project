from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber
from PIL import Image

from .config import TEXT_LAYER_MIN_CHARS, CONFIDENCE_MEDIUM, FORCE_VISION
from .vision import extract_with_vision


#  Data classes 

@dataclass
class ExtractedTable:
    id: str
    headers: list[str]
    rows: list[list[str]]
    source_method: str  # "pdfplumber" | "vision_llm"
    confidence: float
    page_number: int


@dataclass
class PageData:
    page_number: int
    raw_text: str
    tables: list[ExtractedTable] = field(default_factory=list)
    words: list[dict] = field(default_factory=list)
    extraction_method: str = "text"  # "text" | "ocr" | "vision"
    confidence: float = 0.0


#  Source classification 

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".webp"}
PDF_EXTENSIONS = {".pdf", ".pdfa"}


def classify_source(file_path: Path) -> str:
    """Return 'pdf' or 'image' based on file extension."""
    ext = file_path.suffix.lower()
    if ext in PDF_EXTENSIONS:
        return "pdf"
    if ext in IMAGE_EXTENSIONS:
        return "image"
    raise ValueError(f"Unsupported file type: {ext}")


#  Text layer detection 

def has_text_layer(pdf_path: Path, sample_pages: int = 2) -> bool:
    """
    Check if PDF has extractable text.
    Returns False if pages are mostly empty (scanned images).
    """
    with pdfplumber.open(pdf_path) as pdf:
        pages_to_check = min(sample_pages, len(pdf.pages))
        total_chars = 0
        for i in range(pages_to_check):
            text = pdf.pages[i].extract_text() or ""
            total_chars += len(text.strip())
    return total_chars >= TEXT_LAYER_MIN_CHARS


#  PDF parsing (text layer exists) 

def parse_pdf(pdf_path: Path) -> list[PageData]:
    """
    Extract text, tables, and word coordinates from a text-based PDF.
    """
    results = []

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            # Full text
            raw_text = page.extract_text() or ""

            # Words with coordinates
            words = []
            for w in page.extract_words() or []:
                words.append({
                    "text": w["text"],
                    "x0": w["x0"],
                    "y0": w["top"],
                    "x1": w["x1"],
                    "y1": w["bottom"],
                })

            # Tables
            tables = []
            extracted_tables = page.extract_tables() or []
            for idx, table_data in enumerate(extracted_tables):
                if not table_data or len(table_data) < 2:
                    continue

                headers = [str(c) if c else "" for c in table_data[0]]
                rows = []
                for row in table_data[1:]:
                    rows.append([str(c) if c else "" for c in row])

                # Confidence heuristic: more complete rows = higher confidence
                total_cells = len(rows) * len(headers)
                filled_cells = sum(
                    1 for r in rows for c in r if c.strip()
                )
                confidence = filled_cells / total_cells if total_cells > 0 else 0.0

                tables.append(ExtractedTable(
                    id=f"table_{idx + 1}",
                    headers=headers,
                    rows=rows,
                    source_method="pdfplumber",
                    confidence=confidence,
                    page_number=page_num,
                ))

            # Page-level confidence
            text_conf = min(len(raw_text) / 200, 1.0) if raw_text else 0.0
            table_conf = (
                sum(t.confidence for t in tables) / len(tables)
                if tables
                else 0.0
            )
            confidence = 0.6 * text_conf + 0.4 * table_conf if tables else text_conf

            results.append(PageData(
                page_number=page_num,
                raw_text=raw_text,
                tables=tables,
                words=words,
                extraction_method="text",
                confidence=confidence,
            ))

    return results


#  Image-based OCR via Vision LLM 

def _pdf_page_to_image(pdf_path: Path, page_number: int) -> Image.Image:
    """
    Render a single PDF page to a PIL Image with enhanced contrast.
    """
    from PIL import ImageEnhance

    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[page_number - 1]
        im = page.to_image(resolution=300)
        img = im.original

        # Enhance contrast and brightness for better OCR
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(1.5)

        enhancer = ImageEnhance.Brightness(img)
        img = enhancer.enhance(1.2)

        return img


def parse_with_vision(pdf_path: Path) -> list[PageData]:
    """
    Fallback: render each PDF page to image, then use Groq Vision.
    """
    results = []

    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)

    for page_num in range(1, total_pages + 1):
        print(f"  Vision extraction: page {page_num}/{total_pages}")

        # Render page to image
        img = _pdf_page_to_image(pdf_path, page_num)

        # Save to temp buffer
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)

        # Save temp file for vision
        tmp_path = Path(f"_tmp_page_{page_num}.png")
        tmp_path.write_bytes(buf.read())

        try:
            vision_result = extract_with_vision(tmp_path)
        finally:
            tmp_path.unlink(missing_ok=True)

        # Parse vision output into PageData
        raw_text = vision_result.get("page_text", "")
        tables = []
        for idx, tbl in enumerate(vision_result.get("tables", [])):
            tables.append(ExtractedTable(
                id=f"table_{idx + 1}",
                headers=tbl.get("headers", []),
                rows=tbl.get("rows", []),
                source_method="vision_llm",
                confidence=CONFIDENCE_MEDIUM,
                page_number=page_num,
            ))

        results.append(PageData(
            page_number=page_num,
            raw_text=raw_text,
            tables=tables,
            extraction_method="vision",
            confidence=CONFIDENCE_MEDIUM,
        ))

    return results


#  Main ingestion entry point 

def ingest_document(pdf_path: Path) -> list[PageData]:
    """
    Classify → Check text layer → Parse or OCR → Return structured data.
    """
    source_type = classify_source(pdf_path)
    print(f"Source type: {source_type}")

    if source_type == "image":
        print("Image detected — using vision extraction")
        img = Image.open(pdf_path)
        return [_image_to_pagedata(img, 1, pdf_path.name)]

    # FORCE_VISION mode: skip pdfplumber, go straight to vision
    if FORCE_VISION:
        print("FORCE_VISION=True — using vision extraction for all pages")
        return parse_with_vision(pdf_path)

    # PDF path
    if has_text_layer(pdf_path):
        print("Text layer detected — using pdfplumber")
        pages = parse_pdf(pdf_path)

        # Check if any page has low confidence → trigger vision fallback
        low_conf_pages = [p for p in pages if p.confidence < CONFIDENCE_MEDIUM]
        if low_conf_pages:
            print(f"  {len(low_conf_pages)} pages have low confidence — vision fallback")
            vision_pages = parse_with_vision(pdf_path)
            # Merge: keep pdfplumber for good pages, vision for bad ones
            for vp in vision_pages:
                idx = vp.page_number - 1
                if pages[idx].confidence < CONFIDENCE_MEDIUM:
                    pages[idx] = vp
    else:
        print("No text layer — using vision extraction")
        pages = parse_with_vision(pdf_path)

    return pages


def _image_to_pagedata(img: Image.Image, page_number: int, source_name: str = "") -> PageData:
    """Convert a PIL Image to PageData using vision extraction."""
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    tmp_path = Path(f"_tmp_img_{page_number}.png")
    tmp_path.write_bytes(buf.read())

    try:
        vision_result = extract_with_vision(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)

    raw_text = vision_result.get("page_text", "")
    tables = []
    for idx, tbl in enumerate(vision_result.get("tables", [])):
        tables.append(ExtractedTable(
            id=f"table_{idx + 1}",
            headers=tbl.get("headers", []),
            rows=tbl.get("rows", []),
            source_method="vision_llm",
            confidence=CONFIDENCE_MEDIUM,
            page_number=page_number,
        ))

    return PageData(
        page_number=page_number,
        raw_text=raw_text,
        tables=tables,
        extraction_method="vision",
        confidence=CONFIDENCE_MEDIUM,
    )
