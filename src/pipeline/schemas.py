from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# Status definitions 
class Status(str, Enum):
    """Lifecycle status for every extracted field."""

    VERIFIED = "verified"          # value confirmed by text/table extraction
    CONFLICT = "conflict"          # sources disagree on this field
    SOURCE_ONLY = "source_only"   # present in only one source
    UNCERTAIN = "uncertain"        # LLM inference or low-confidence extraction
    MISSING = "missing"            # expected but not found in any source
    NOT_APPLICABLE = "not_applicable"  # field does not apply to this product/task


#  Provenance 
class SourceLocation(BaseModel):
    """Where a value was found inside a document."""

    document: str = Field(..., description="Filename of the source PDF")
    page: int = Field(..., ge=1)
    section: Optional[str] = Field(
        None, description="Table or heading name, e.g. 'AC Output Side'"
    )
    row: Optional[str] = Field(
        None, description="Table row label if applicable"
    )
    column: Optional[str] = Field(
        None, description="Table column header if applicable"
    )


class Evidence(BaseModel):
    """Raw extracted text that supports a field value."""

    raw_text: str = Field(..., description="Exact text snippet from the document")
    extraction_method: str = Field(
        ...,
        description="How the text was obtained: 'text', 'table', 'vision', 'llm_inference'",
    )


#  Field-level output 
class ExtractedField(BaseModel):
    """A single extracted data point with full provenance."""

    field_name: str = Field(
        ..., description="Dot-notation key, e.g. 'electrical.max_efficiency'"
    )
    value: Any = Field(
        None, description="Extracted value (str, float, int, list, or None)"
    )
    unit: Optional[str] = Field(None, description="Unit of measurement if applicable")
    sources: list[SourceLocation] = Field(
        default_factory=list,
        description="All source locations that contributed to this value",
    )
    evidence: list[Evidence] = Field(
        default_factory=list, description="Supporting raw text snippets"
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="0.0 (no confidence) to 1.0 (certain)"
    )
    status: Status = Field(
        ..., description="Current lifecycle status of this field"
    )
    notes: Optional[str] = Field(
        None,
        description="Free-text note: why status is CONFLICT, what is uncertain, etc.",
    )


#  Conflict record 
class ConflictRecord(BaseModel):
    """Documents a disagreement between sources."""

    field_name: str
    source_a: SourceLocation
    source_b: SourceLocation
    value_a: Any
    value_b: Any
    resolution: Optional[str] = Field(
        None,
        description="How the conflict was resolved or why it remains unresolved",
    )


#  Source document metadata 
class SourceDocument(BaseModel):
    """Metadata about an ingested source document."""

    filename: str
    url: Optional[str] = None
    variant: Optional[str] = Field(
        None, description="Model variant this document covers, e.g. 'AM2', 'AM2-P1'"
    )
    revision_date: Optional[str] = None
    page_count: int = 0
    parse_quality: Optional[str] = Field(
        None, description="'good', 'partial', 'poor', 'failed'"
    )


#  Top-level extraction output 
class ExtractionOutput(BaseModel):
    """Complete pipeline output for one import task."""

    task_id: str = Field(..., description="Task identifier, e.g. 'task1_nepal'")
    requested_model: str = Field(
        ..., description="The model the client asked about, e.g. 'SUN-5K-G06P3'"
    )
    sources: list[SourceDocument] = Field(default_factory=list)
    fields: dict[str, ExtractedField] = Field(
        default_factory=dict,
        description="All extracted fields keyed by dot-notation field name",
    )
    conflicts: list[ConflictRecord] = Field(default_factory=list)
    missing: list[str] = Field(
        default_factory=list,
        description="Field names that are expected but not found in any source",
    )
    import_checklist_coverage: dict[str, list[str]] = Field(
        default_factory=dict,
        description="Maps checklist category to list of field_names that address it",
    )


#  Import checklist field mapping 
# Based on the assessment's "import-side checklist"
IMPORT_CHECKLIST = {
    "product_identity": [
        "product.model",
        "product.variant",
        "product.rated_power",
        "product.max_pv_input_power",
        "product.mppt_voltage_range",
        "product.max_pv_input_voltage",
        "product.rated_output_voltage",
        "product.rated_grid_frequency",
        "product.num_mppt_trackers",
        "product.num_strings_per_mppt",
        "product.max_efficiency",
        "product.euro_efficiency",
        "product.mppt_efficiency",
        "product.topology",
        "product.weight",
        "product.dimensions",
        "product.ip_rating",
        "product.operating_temperature",
        "product.noise",
        "product.cooling",
        "product.warranty",
    ],
    "manufacturer_identity": [
        "manufacturer.legal_name",
        "manufacturer.factory_address",
        "manufacturer.country",
        "manufacturer.phone",
        "manufacturer.email",
        "manufacturer.stock_code",
    ],
    "test_evidence": [
        "compliance.grid_standards",
        "compliance.safety_emc_standards",
        "compliance.certificates",
    ],
    "labeling": [
        "labeling.required_markings",
    ],
    "importer_paperwork": [
        "importer.sunbridge_checklist",
    ],
}


#  Expected fields
TASK1_FIELDS = [
    # Product identity
    "product.model",
    "product.variant",
    "product.rated_power",
    "product.max_pv_input_power",
    "product.mppt_voltage_range",
    "product.max_pv_input_voltage",
    "product.startup_voltage",
    "product.rated_input_voltage",
    "product.max_input_current",
    "product.max_short_circuit_current",
    "product.rated_output_power",
    "product.max_output_apparent_power",
    "product.rated_output_current",
    "product.max_output_current",
    "product.rated_output_voltage",
    "product.grid_frequency",
    "product.num_mppt_trackers",
    "product.num_strings_per_mppt",
    "product.max_efficiency",
    "product.euro_efficiency",
    "product.mppt_efficiency",
    "product.thd_current",
    "product.power_factor_range",
    "product.dc_injection_current",
    "product.topology",
    "product.weight",
    "product.dimensions",
    "product.ip_rating",
    "product.operating_temperature",
    "product.permitted_humidity",
    "product.permitted_altitude",
    "product.noise",
    "product.cooling",
    "product.warranty",
    "product.overvoltage_category",
    # Manufacturer
    "manufacturer.legal_name",
    "manufacturer.factory_address",
    "manufacturer.country",
    "manufacturer.phone",
    "manufacturer.email",
    "manufacturer.stock_code",
    # Compliance
    "compliance.grid_standards",
    "compliance.safety_emc_standards",
    "compliance.surge_protection",
    # Protection features
    "protection.dc_reverse_polarity",
    "protection.ac_short_circuit",
    "protection.ac_overcurrent",
    "protection.ac_overvoltage",
    "protection.thermal",
    "protection.islanding",
    "protection.ground_fault",
    "protection.insulation_impedance",
    "protection.dc_switch",
    # Labeling
    "labeling.required_markings",
    # Importer
    "importer.sunbridge_checklist",
]


def build_empty_output(task_id: str, requested_model: str) -> ExtractionOutput:
    """Create an ExtractionOutput with all expected fields pre-populated as MISSING."""
    fields = {}
    for field_name in TASK1_FIELDS:
        fields[field_name] = ExtractedField(
            field_name=field_name,
            value=None,
            confidence=0.0,
            status=Status.MISSING,
        )

    checklist_coverage = {}
    for category, field_names in IMPORT_CHECKLIST.items():
        checklist_coverage[category] = field_names

    return ExtractionOutput(
        task_id=task_id,
        requested_model=requested_model,
        fields=fields,
        missing=TASK1_FIELDS.copy(),
        import_checklist_coverage=checklist_coverage,
    )
