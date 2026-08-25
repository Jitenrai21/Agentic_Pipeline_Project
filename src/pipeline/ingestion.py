from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber
import pytesseract
from PIL import Image, ImageEnhance

from .config import TEXT_LAYER_MIN_CHARS, CONFIDENCE_MEDIUM


# ── Data classes ────────────────────────────────────────────────────

@dataclass
class ExtractedTable:
    id: str
    headers: list[str]
    rows: list[list[str]]
    source_method: str  # "pdfplumber" | "tesseract"
    confidence: float
    page_number: int


@dataclass
class PageData:
    page_number: int
    raw_text: str
    tables: list[ExtractedTable] = field(default_factory=list)
    words: list[dict] = field(default_factory=list)
    extraction_method: str = "text"  # "text" | "ocr"
    confidence: float = 0.0


# ── Source classification ───────────────────────────────────────────

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".webp"}
PDF_EXTENSIONS = {".pdf", ".pdfa"}


def classify_source(file_path: Path) -> str:
    ext = file_path.suffix.lower()
    if ext in PDF_EXTENSIONS:
        return "pdf"
    if ext in IMAGE_EXTENSIONS:
        return "image"
    raise ValueError(f"Unsupported file type: {ext}")


# ── Text layer detection ───────────────────────────────────────────

def has_text_layer(pdf_path: Path, sample_pages: int = 2) -> bool:
    with pdfplumber.open(pdf_path) as pdf:
        pages_to_check = min(sample_pages, len(pdf.pages))
        total_chars = 0
        for i in range(pages_to_check):
            text = pdf.pages[i].extract_text() or ""
            total_chars += len(text.strip())
    return total_chars >= TEXT_LAYER_MIN_CHARS


# ── PDF parsing (text layer exists) ────────────────────────────────

def parse_pdf(pdf_path: Path) -> list[PageData]:
    results = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            raw_text = page.extract_text() or ""

            words = []
            for w in page.extract_words() or []:
                words.append({
                    "text": w["text"],
                    "x0": w["x0"],
                    "y0": w["top"],
                    "x1": w["x1"],
                    "y1": w["bottom"],
                })

            tables = []
            extracted_tables = page.extract_tables() or []
            for idx, table_data in enumerate(extracted_tables):
                if not table_data or len(table_data) < 2:
                    continue
                headers = [str(c) if c else "" for c in table_data[0]]
                rows = []
                for row in table_data[1:]:
                    rows.append([str(c) if c else "" for c in row])

                total_cells = len(rows) * len(headers)
                filled_cells = sum(1 for r in rows for c in r if c.strip())
                confidence = filled_cells / total_cells if total_cells > 0 else 0.0

                tables.append(ExtractedTable(
                    id=f"table_{idx + 1}",
                    headers=headers,
                    rows=rows,
                    source_method="pdfplumber",
                    confidence=confidence,
                    page_number=page_num,
                ))

            text_conf = min(len(raw_text) / 200, 1.0) if raw_text else 0.0
            table_conf = (
                sum(t.confidence for t in tables) / len(tables) if tables else 0.0
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


# ── OCR fallback (Tesseract) ───────────────────────────────────────

def _pdf_page_to_image(pdf_path: Path, page_number: int) -> Image.Image:
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[page_number - 1]
        im = page.to_image(resolution=300)
        img = im.original
        img = ImageEnhance.Contrast(img).enhance(1.5)
        img = ImageEnhance.Brightness(img).enhance(1.2)
        return img


def _image_to_text(img: Image.Image) -> str:
    custom_config = r"--oem 3 --psm 6"
    text = pytesseract.image_to_string(img, config=custom_config)
    return text


def _image_to_data(img: Image.Image) -> dict:
    data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
    return data


def _cluster_words_from_ocr(data: dict) -> list[dict]:
    words = []
    for i in range(len(data["text"])):
        text = data["text"][i].strip()
        conf = int(data["conf"][i])
        if text and conf > 0:
            words.append({
                "text": text,
                "x0": data["left"][i],
                "y0": data["top"][i],
                "x1": data["left"][i] + data["width"][i],
                "y1": data["top"][i] + data["height"][i],
                "conf": conf,
            })
    return words


def _words_to_text(words: list[dict]) -> str:
    sorted_words = sorted(words, key=lambda w: (w["y0"], w["x0"]))
    lines = []
    current_line = []
    current_y = None

    for w in sorted_words:
        if current_y is None or abs(w["y0"] - current_y) > 5:
            if current_line:
                lines.append(" ".join(current_line))
            current_line = [w["text"]]
            current_y = w["y0"]
        else:
            current_line.append(w["text"])

    if current_line:
        lines.append(" ".join(current_line))

    return "\n".join(lines)


def parse_with_ocr(pdf_path: Path) -> list[PageData]:
    results = []
    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)

    for page_num in range(1, total_pages + 1):
        print(f"  OCR extraction: page {page_num}/{total_pages}")
        img = _pdf_page_to_image(pdf_path, page_num)
        text = _image_to_text(img)
        ocr_data = _image_to_data(img)
        words = _cluster_words_from_ocr(ocr_data)

        words_conf = [w["conf"] for w in words] if words else [0]
        avg_conf = sum(words_conf) / len(words_conf) / 100.0

        results.append(PageData(
            page_number=page_num,
            raw_text=text,
            tables=[],
            words=words,
            extraction_method="ocr",
            confidence=avg_conf,
        ))
    return results


def ocr_image_file(image_path: Path) -> list[PageData]:
    img = Image.open(image_path)
    text = _image_to_text(img)
    ocr_data = _image_to_data(img)
    words = _cluster_words_from_ocr(ocr_data)

    words_conf = [w["conf"] for w in words] if words else [0]
    avg_conf = sum(words_conf) / len(words_conf) / 100.0

    return [PageData(
        page_number=1,
        raw_text=text,
        tables=[],
        words=words,
        extraction_method="ocr",
        confidence=avg_conf,
    )]


# ── Main ingestion entry point ─────────────────────────────────────

def ingest_document(pdf_path: Path) -> list[PageData]:
    source_type = classify_source(pdf_path)
    print(f"Source type: {source_type}")

    if source_type == "image":
        print("Image detected -- using OCR extraction")
        return ocr_image_file(pdf_path)

    if has_text_layer(pdf_path):
        print("Text layer detected -- using pdfplumber")
        pages = parse_pdf(pdf_path)

        low_conf_pages = [p for p in pages if p.confidence < CONFIDENCE_MEDIUM]
        if low_conf_pages:
            print(f"  {len(low_conf_pages)} pages have low confidence -- OCR fallback")
            ocr_pages = parse_with_ocr(pdf_path)
            for op in ocr_pages:
                idx = op.page_number - 1
                if pages[idx].confidence < CONFIDENCE_MEDIUM:
                    pages[idx] = op
    else:
        print("No text layer -- using OCR extraction")
        pages = parse_with_ocr(pdf_path)

    return pages
