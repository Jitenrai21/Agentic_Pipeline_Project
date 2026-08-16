import re

from .mapper import find_spec
from .schemas import CanonicalValue, Confidence, EvidenceRecord

_CONF_RANK = {Confidence.LOW: 0, Confidence.MEDIUM: 1, Confidence.HIGH: 2}


def _covers(ev: EvidenceRecord, target: str) -> bool:
    if not target:
        return False
    if "shared across all model columns" in ev.notes:
        return True
    m = re.search(r"merged cell covers: ([^;]+)", ev.notes)
    if m:
        return target in m.group(1)
    return False


def _cap(conf: Confidence, rank: int) -> Confidence:
    return conf if _CONF_RANK[conf] <= rank else {
        0: Confidence.LOW, 1: Confidence.MEDIUM, 2: Confidence.HIGH
    }[rank]


def validate(canonical: list[CanonicalValue],
             evidence: list[EvidenceRecord],
             target_model: str | None = None) -> list[CanonicalValue]:
    """Validate LLM/proposed field assignments.

    - Cross-checks each assignment against the deterministic mapper's label match.
    - Caps confidence of assignments that disagree with the deterministic mapper.
    - Caps confidence of merged cells that do not cover the target model.
    Deterministic-mapper output passes through with provenance; LLM assignments
    are checked record-by-record.
    """
    out: list[CanonicalValue] = []
    for cv in canonical:
        notes = cv.notes
        conf = cv.confidence
        if cv.evidence_index is None:
            out.append(cv)
            continue

        ev = evidence[cv.evidence_index]
        det = find_spec(ev.raw_label)

        if det is not None and det.field == cv.field:
            notes = "; ".join(filter(None, [notes, "validated: deterministic mapper agrees"]))
        elif det is not None:
            conf = _cap(conf, 1)
            notes = "; ".join(filter(None, [
                notes, f"LLM assignment disagrees with deterministic mapper ({det.field}); "
                       f"confidence capped at {conf.value}"]))
        else:
            notes = "; ".join(filter(None, [
                notes, "no deterministic mapping for this label; assignment relies on LLM"]))

        if ev.is_merged and not _covers(ev, target_model):
            conf = _cap(conf, 0)
            notes = "; ".join(filter(None, [
                notes, f"merged cell does not cover target model {target_model}; "
                       f"confidence capped at {conf.value}"]))

        out.append(cv.model_copy(update={"confidence": conf, "notes": notes}))
    return out