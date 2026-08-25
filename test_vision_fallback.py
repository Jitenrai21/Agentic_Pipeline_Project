"""Test vision fallback: render PDF page to image, then extract with Groq Vision."""
import json
import sys
from pathlib import Path

import pdfplumber
from PIL import ImageEnhance

from src.pipeline.vision import extract_with_vision


def render_and_test(pdf_path: str, page_number: int = 2):
    """Render a PDF page to image and run vision extraction."""
    pdf = Path(pdf_path)
    if not pdf.exists():
        print(f"File not found: {pdf}")
        return

    print(f"Rendering page {page_number} from: {pdf.name}")

    with pdfplumber.open(pdf) as doc:
        page = doc.pages[page_number - 1]
        im = page.to_image(resolution=300)
        img = im.original

        # Enhance for better visibility
        img = ImageEnhance.Contrast(img).enhance(1.5)
        img = ImageEnhance.Brightness(img).enhance(1.2)

        # Save as PNG
        out_path = Path(f"test_page_{page_number}.png")
        img.save(str(out_path))
        print(f"Saved enhanced image: {out_path}")

    print("\nRunning Groq Vision extraction...")

    result = extract_with_vision(out_path)
    print(json.dumps(result, indent=2))

    print(f"\nImage saved at: {out_path.resolve()}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_vision_fallback.py <pdf_path> [page_number]")
        print("Example: python test_vision_fallback.py cache/source_1/datasheet_sun-4-12k-g06p3-eu-am2-p1_231007_en.pdf 2")
    else:
        pdf_path = sys.argv[1]
        page = int(sys.argv[2]) if len(sys.argv) > 2 else 2
        render_and_test(pdf_path, page)
