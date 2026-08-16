import re
from collections import defaultdict

from .mapper import FIELDS
from .schemas import CanonicalValue, Comparison, Confidence, SourceValue, Status


_CONF_RANK = {Confidence.LOW: 0, Confidence.MEDIUM: 1, Confidence.HIGH: 2}


def _norm_text(value: str) -> str:
    return " ".join(value.lower().split())

def _values_equal(a, b) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) < 1e-9
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(_values_equal(x, y) for x, y in zip(a, b))
    if isinstance(a, str) and isinstance(b, str):
        return _norm_text(a) == _norm_text(b)
    return a == b


def _is_standard_list(v) -> bool:
    return isinstance(v, list) and bool(v) and all(isinstance(x, str) for x in v)


def _best(records: list[CanonicalValue]) -> tuple[CanonicalValue | None, str]:
    if not records:
        return None, ""
    top = max(_CONF_RANK[r.confidence] for r in records)
    best = [r for r in records if _CONF_RANK[r.confidence] == top]
    distinct = {repr(r.value) for r in best}
    if len(distinct) > 1:
        return best[0], "internal inconsistency: multiple conflicting values in the same source"
    return best[0], ""

def _to_source_value(cv: CanonicalValue) -> SourceValue:
    return SourceValue(source_id=cv.source_id, page=cv.page, raw=cv.raw,
                       value=cv.value, unit=cv.unit,
                       confidence=cv.confidence, notes=cv.notes)


def _merge_conf(a: Confidence, b: Confidence) -> Confidence:
    return a if _CONF_RANK[a] <= _CONF_RANK[b] else b


def _compare(a, b) -> tuple[Status, str]:
    if _is_standard_list(a) and _is_standard_list(b):
        return Status.AGREES, ""

    if _values_equal(a, b):
        if isinstance(a, str) and isinstance(b, str) and a != b:
            return Status.AGREES, f"values considered equal after normalization: {a!r} vs {b!r}"
        return Status.AGREES, ""

    return Status.CONFLICT, ""

def _compare_standards(a, b) -> tuple[Status, str]:
    sa, sb = set(a.value), set(b.value)
    if sa == sb:
        return Status.AGREES, ""
    if sa < sb:
        return Status.CONFLICT, f"{b.source_id} lists superset of standards ({len(sb)} vs {len(sa)} codes)"
    if sb < sa:
        return Status.CONFLICT, f"{a.source_id} lists superset of standards ({len(sa)} vs {len(sb)} codes)"
    return Status.CONFLICT, "different standard sets"


def _covers_target(cv: CanonicalValue, target: str | None) -> bool:
    if not target:
        return False
    if "shared across all model columns" in cv.notes:
        return True
    m = re.search(r"merged cell covers: ([^;]+)", cv.notes)
    if m:
        return target in m.group(1)
    return False


def reconcile(values: list[CanonicalValue],
              source_order: tuple[str, str] = ("am2_p1", "am2"),
              target_model: str | None = None) -> list[Comparison]:
    s1_id, s2_id = source_order
    grouped: dict[str, dict[str, list[CanonicalValue]]] = defaultdict(lambda: defaultdict(list))
    for v in values:
        grouped[v.field][v.source_id].append(v)

    ordered = [spec.field for spec in FIELDS if spec.field in grouped]
    ordered += sorted(set(grouped) - set(ordered))

    results: list[Comparison] = []
    for field in ordered:
        g = grouped[field]
        r1, note1 = _best(g.get(s1_id, []))
        r2, note2 = _best(g.get(s2_id, []))

        if r1 is None and r2 is None:
            continue
        if r2 is None:
            results.append(Comparison(field=field, source_1=_to_source_value(r1),
                                      source_2=None, status=Status.SOURCE_1_ONLY,
                                      confidence=r1.confidence, notes=note1))
            continue
        if r1 is None:
            results.append(Comparison(field=field, source_1=None, source_2=_to_source_value(r2),
                                      status=Status.SOURCE_2_ONLY,
                                      confidence=r2.confidence, notes=note2))
            continue

        if _is_standard_list(r1.value) and _is_standard_list(r2.value):
            status, note = _compare_standards(r1, r2)
        else:
            status, note = _compare(r1.value, r2.value)

        conf = _merge_conf(r1.confidence, r2.confidence)
        bits = [note1, note2, note]
        if status == Status.CONFLICT and _CONF_RANK[conf] < 2:
            if _covers_target(r1, target_model) and _covers_target(r2, target_model):
                bits.append("merged/shared cells explicitly cover target model; conflict kept at low confidence")
            else:
                status = Status.UNCERTAIN
                bits.append("low-confidence value(s); cannot assert a firm conflict")
        results.append(Comparison(field=field, source_1=_to_source_value(r1),
                                  source_2=_to_source_value(r2),
                                  status=status, confidence=conf,
                                  notes="; ".join(b for b in bits if b)))
    return results