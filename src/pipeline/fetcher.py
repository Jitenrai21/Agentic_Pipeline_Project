import urllib.request
from pathlib import Path

from .schemas import Source

class FetchError(RuntimeError):
    pass

def fetch(source: Source, dest_dir: Path, expected_family: str = "SUN-") -> Path:
    """Download source.url -> dest_dir/{id}.pdf, validate, or raise FetchError."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{source.id}.pdf"

    req = urllib.request.Request(source.url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read()
    except Exception as exc:
        raise FetchError(f"[{source.id}] download failed: {exc}") from exc

    if not body.startswith(b"%PDF"):
        raise FetchError(
            f"[{source.id}] downloaded file is not a PDF "
            f"(bad magic bytes, {len(body)} bytes) - got HTML error page?"
        )
    dest.write_bytes(body)

    import pdfplumber
    try:
        with pdfplumber.open(dest) as pdf:
            if not pdf.pages:
                raise FetchError(f"[{source.id}] PDF has no pages")
            text = "\n".join(p.extract_text() or "" for p in pdf.pages)
    except FetchError:
        raise
    except Exception as exc:
        raise FetchError(f"[{source.id}] PDF cannot be parsed: {exc}") from exc

    if expected_family and expected_family not in text:
        raise FetchError(
            f"[{source.id}] family marker '{expected_family}' not found in PDF - "
            f"wrong document? (fetched from {source.url})"
        )
    return dest