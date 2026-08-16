from enum import Enum

from pydantic import BaseModel, Field

class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

class Source(BaseModel):
    id: str
    label: str
    url: str
    variant_hint: str = ""

class RawCell(BaseModel):
    model: str | None = None            # column model if attributed, else None (shared/merged)
    raw: str
    x_center: float
    is_merged: bool = False
    confidence: Confidence = Confidence.HIGH
    covers: list[str] = Field(default_factory=list)   # models this merged cell covers

class RawRow(BaseModel):
    label: str
    label_confidence: Confidence = Confidence.HIGH
    values: dict[str, RawCell] = Field(default_factory=dict)   # model -> cell (per-column)
    shared: RawCell | None = None       # single whole-row value (applies to all columns)
    merged: list[RawCell] = Field(default_factory=list)        # merged multi-model cells
    is_section: bool = False

class RawDocument(BaseModel):
    source_id: str
    page: int
    columns: list[str]
    rows: list[RawRow]
    footer: str = ""
    notes: list[str] = Field(default_factory=list)

class EvidenceRecord(BaseModel):
    source_id: str
    page: int
    raw_label: str
    model: str | None
    raw_value: str
    confidence: Confidence
    is_merged: bool = False
    notes: str = ""

class CanonicalValue(BaseModel):
    field: str
    source_id: str
    page: int
    raw: str
    value: object
    unit: str = ""
    confidence: Confidence = Confidence.HIGH
    notes: str = ""
    evidence_index: int | None = None 

class Status(str, Enum):
    AGREES = "agrees"
    CONFLICT = "conflict"
    SOURCE_1_ONLY = "source_1_only"
    SOURCE_2_ONLY = "source_2_only"
    UNCERTAIN = "uncertain"

class SourceValue(BaseModel):
    source_id: str
    page: int
    raw: str
    value: object
    unit: str = ""
    confidence: Confidence = Confidence.HIGH
    notes: str = ""

class Comparison(BaseModel):
    field: str
    source_1: SourceValue | None = None
    source_2: SourceValue | None = None
    status: Status
    confidence: Confidence = Confidence.HIGH
    notes: str = ""