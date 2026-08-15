from .schemas import Confidence, EvidenceRecord, RawDocument

def _conf(row, cell_conf):
    if row.label_confidence == Confidence.LOW:
        return Confidence.LOW
    return cell_conf

def to_evidence(doc: RawDocument, target_model: str) -> list[EvidenceRecord]:
    records = []
    for row in doc.rows:
        if row.is_section:
            continue
        if target_model in row.values:
            cell = row.values[target_model]
            records.append(EvidenceRecord(
                source_id=doc.source_id, page=doc.page,
                raw_label=row.label, model=target_model,
                raw_value=cell.raw, confidence=_conf(row, cell.confidence),
                is_merged=cell.is_merged,
                notes="uncertain label (overlapping text)" if row.label_confidence == Confidence.LOW else "",
            ))
        if row.shared is not None:
            records.append(EvidenceRecord(
                source_id=doc.source_id, page=doc.page,
                raw_label=row.label, model=target_model,
                raw_value=row.shared.raw, confidence=_conf(row, row.shared.confidence),
                is_merged=True,
                notes="shared across all model columns" + ("; uncertain label (overlapping text)" if row.label_confidence == Confidence.LOW else ""),
            ))
        for cell in row.merged:
            if cell.covers and target_model not in cell.covers:
                continue
            records.append(EvidenceRecord(
                source_id=doc.source_id, page=doc.page,
                raw_label=row.label, model=target_model,
                raw_value=cell.raw, confidence=_conf(row, cell.confidence),
                is_merged=True,
                notes="merged cell covers: " + (", ".join(cell.covers) or "all columns")
                      + ("; uncertain label (overlapping text)" if row.label_confidence == Confidence.LOW else ""),
            ))
    return records