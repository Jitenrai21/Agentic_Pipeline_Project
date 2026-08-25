from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")


# Paths
CACHE_DIR = PROJECT_ROOT / "cache"
OUTPUT_DIR = PROJECT_ROOT / "outputs"

# Source URLs (Task 1 -- China -> Nepal)
SOURCES = {
    "source_1": {
        "url": "https://www.deyeinverter.com/deyeinverter/2023/10/07/datasheet_sun-4-12k-g06p3-eu-am2-p1_231007_en.pdf",
        "variant": "AM2-P1",
        "revision_date": "2023-10-07",
    },
    "source_2": {
        "url": "https://www.deyeinverter.com/deyeinverter/2024/03/20/datasheet_sun-4-15k-g06p3-eu-am2_240318_en.pdf",
        "variant": "AM2",
        "revision_date": "2024-03-18",
    },
}

# Extraction thresholds
TEXT_LAYER_MIN_CHARS = 100
CONFIDENCE_HIGH = 0.85
CONFIDENCE_MEDIUM = 0.60
