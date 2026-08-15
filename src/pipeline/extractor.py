import re
import statistics
from dataclasses import dataclass
from pathlib import Path

import pdfplumber

from .schemas import Confidence, RawCell, RawDocument, RawRow

class ExtractionError(RuntimeError):
    pass

def derive_family_matcher(target_model: str):
    """SUN-5K-G06P3 -> SUN-\\d+K-G06P3. Generated from config, never literal."""
    m = re.fullmatch(r"(.*?)(\d+)(.*)", target_model)
    if not m:
        return None
    prefix, _, suffix = m.groups()
    return re.compile(re.escape(prefix) + r"\d+" + re.escape(suffix))

@dataclass
class TableGeometry:
    columns: list[tuple[str, float, float]]    # (model id, x0, x1)
    intervals: list[tuple[str, float, float]]  # (model id, lo, hi) contiguous tiling
    value_start: float
    row_tol: float

    def column_for(self, x0: float) -> str | None:
        if x0 < self.value_start:
            return None
        for cid, lo, hi in self.intervals:
            if lo <= x0 < hi:
                return cid
        return None

def _measure(page, matcher) -> TableGeometry | None:
    words = page.extract_words()
    cols = sorted((w for w in words if matcher and matcher.search(w["text"])),
                  key=lambda w: w["x0"])
    if not cols:
        return None
    columns = [(w["text"], w["x0"], w["x1"]) for w in cols]
    centers = [(c0 + c1) / 2 for _, c0, c1 in columns]
    half = (centers[1] - centers[0]) / 2
    intervals = [(cid, centers[i] - half, centers[i] + half)
                 for i, (cid, _c0, _c1) in enumerate(columns)]

    label_tops = sorted({round(w["top"], 1) for w in words if w["x0"] < centers[0] - half})
    gaps = [b - a for a, b in zip(label_tops, label_tops[1:]) if b - a > 1.0]
    row_tol = 0.5 * statistics.median(gaps) if gaps else half
    return TableGeometry(columns=columns, intervals=intervals,
                         value_start=centers[0] - half, row_tol=row_tol)

def _cluster_rows(words, row_tol: float) -> list[list[dict]]:
    bands = []
    for w in sorted(words, key=lambda w: w["top"]):
        if bands and w["top"] - bands[-1]["top"] <= row_tol:
            bands[-1]["words"].append(w)
        else:
            bands.append({"words": [w], "top": w["top"]})
    return [b["words"] for b in bands]


_LIGATURES = {
    "\ufb00": "ff", "\ufb01": "fi", "\ufb02": "fl",
    "\ufb03": "ffi", "\ufb04": "ffl", "\ufb05": "st", "\ufb06": "st",
}

def _decompose(s: str) -> str:
    return "".join(_LIGATURES.get(ch, ch) for ch in s)

def _label_overlap(page, label_words) -> bool:
    if not label_words:
        return False
    lo_x = min(w["x0"] for w in label_words) - 1
    hi_x = max(w["x1"] for w in label_words) + 1
    lo_t = min(w["top"] for w in label_words) - 1
    hi_b = max(w["bottom"] for w in label_words) + 1
    chars = [c for c in page.chars if lo_x <= c["x0"] <= hi_x and lo_t <= c["top"] <= hi_b]

    def norm(s):
        return "".join(ch for ch in s if not ch.isspace())

    word_text = _decompose(norm(" ".join(w["text"] for w in sorted(label_words, key=lambda w: w["x0"]))))
    char_text = _decompose(norm("".join(c["text"] for c in sorted(chars, key=lambda c: (round(c["top"], 1), c["x0"])))))
    return word_text != char_text

def _assign_values(tokens, geo: TableGeometry):
    tokens = sorted(tokens, key=lambda w: w["x0"])
    n_cols = len(geo.columns)
    span_of = lambda w: geo.column_for(w["x0"])

    def make(w, model=None, is_merged=False, confidence=Confidence.HIGH, covers=()):
        return RawCell(model=model, raw=w["text"],
                       x_center=(w["x0"] + w["x1"]) / 2,
                       is_merged=is_merged, confidence=confidence,
                       covers=list(covers))

    if len(tokens) == 1:
        return {}, make(tokens[0], is_merged=True), []

    if any(any(ch.isalpha() for ch in w["text"]) for w in tokens):
        return {}, make({"text": " ".join(w["text"] for w in tokens),
                         "x0": tokens[0]["x0"], "x1": tokens[-1]["x1"]},
                        is_merged=True), []

    per_col, seen = {}, set()
    if len(tokens) == n_cols:
        ok = True
        for w in tokens:
            cid = span_of(w)
            if cid is None or cid in seen:
                ok = False
                break
            seen.add(cid)
            per_col[cid] = make(w, model=cid)
        if ok:
            return per_col, None, []

    groups = []
    for w in tokens:
        if groups and span_of(groups[-1][-1]) == span_of(w):
            groups[-1].append(w)
        else:
            groups.append([w])

    merged = []
    for gi, g in enumerate(groups):
        left = 0.0 if gi == 0 else (groups[gi - 1][-1]["x1"] + g[0]["x0"]) / 2
        right = (groups[-1][-1]["x1"] + 1) if gi == len(groups) - 1 else (g[-1]["x1"] + groups[gi + 1][0]["x0"]) / 2
        covers = [cid for cid, c0, c1 in geo.columns if left <= (c0 + c1) / 2 < right]
        merged.append(make({"text": " ".join(x["text"] for x in g),
                            "x0": g[0]["x0"], "x1": g[-1]["x1"]},
                           is_merged=True, confidence=Confidence.LOW, covers=covers))
    return per_col, None, merged

def extract(path: Path, source_id: str, target_model: str,
            page_index: int | None = None) -> RawDocument:
    with pdfplumber.open(path) as pdf:
        matcher = derive_family_matcher(target_model)
        if page_index is None:
            page_index = next(
                (i for i, p in enumerate(pdf.pages)
                 if matcher and _measure(p, matcher) is not None),
                None,
            )
            if page_index is None:
                raise ExtractionError(f"[{source_id}] no model columns found for {target_model!r}")

        page = pdf.pages[page_index]
        words = page.extract_words()
        geo = _measure(page, matcher)
        if geo is None:
            raise ExtractionError(f"[{source_id}] could not locate model columns on page {page_index + 1}")

        bands = _cluster_rows(words, geo.row_tol)
        header_idx = next(i for i, b in enumerate(bands)
                          if any(matcher.search(w["text"]) for w in b))
        header_bottom = max(w["bottom"] for w in bands[header_idx])

        start = header_idx + 1
        while start < len(bands):
            top = min(w["top"] for w in bands[start])
            if top <= header_bottom + geo.row_tol:
                header_bottom = max(header_bottom, max(w["bottom"] for w in bands[start]))
                start += 1
            else:
                break

        band_tops = [min(w["top"] for w in b) for b in bands[start:]]
        gaps = [b - a for a, b in zip(band_tops, band_tops[1:])]
        gap_limit = 2.5 * statistics.median(gaps) if gaps else geo.row_tol * 6

        table_bands, footer = [], []
        prev = None
        for b in bands[start:]:
            top = min(w["top"] for w in b)
            if prev is not None and top - prev > gap_limit:
                footer.extend(b)
                continue
            table_bands.append(b)
            prev = top

        merged_bands = []
        for b in table_bands:
            has_label = any(w["x0"] < geo.value_start for w in b)
            if not has_label and merged_bands:
                merged_bands[-1].extend(b)
            else:
                merged_bands.append(list(b))
        table_bands = merged_bands

        out_rows, notes = [], []
        for band in table_bands:
            if any(matcher.search(w["text"]) for w in band):
                continue
            labels = [w for w in band if w["x0"] < geo.value_start]
            values = [w for w in band if w["x0"] >= geo.value_start]
            label = " ".join(w["text"] for w in sorted(labels, key=lambda w: w["x0"])).strip()
            if not values:
                if label:
                    out_rows.append(RawRow(label=label, is_section=True))
                continue
            per_col, shared, merged = _assign_values(values, geo)
            overlap = _label_overlap(page, labels)
            row = RawRow(label=label,
                         label_confidence=Confidence.LOW if overlap else Confidence.HIGH,
                         values=per_col, shared=shared, merged=merged)
            if overlap:
                notes.append(f"label overlap detected: {label!r}")
            if merged:
                notes.append(f"merged cells in row: {label!r}")
            out_rows.append(row)

        footer_text = " ".join(w["text"] for w in sorted(footer, key=lambda w: (w["top"], w["x0"]))).strip()
        return RawDocument(source_id=source_id, page=page_index + 1,
                           columns=[c[0] for c in geo.columns],
                           rows=out_rows, footer=footer_text, notes=notes)   