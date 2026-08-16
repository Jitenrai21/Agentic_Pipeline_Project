import re
from dataclasses import dataclass

from .normalizer import normalize
from .schemas import CanonicalValue, EvidenceRecord

@dataclass(frozen=True)
class FieldSpec:
    field: str
    groups: tuple[tuple[str, ...], ...]
    value_type: str
    unit: str = ""

FIELDS: list[FieldSpec] = [
    FieldSpec("rated_power_kw", (("rated", "output", "power"), ("rated", "ac", "output", "active", "power")), "float", "kW"),
    FieldSpec("max_dc_input_power_kw", (("max", "dc", "input", "power"), ("max", "pv", "input", "power")), "float", "kW"),
    FieldSpec("max_dc_voltage_v", (("max", "dc", "input", "voltage"), ("max", "pv", "input", "voltage")), "int", "V"),
    FieldSpec("start_up_voltage_v", (("start", "up", "voltage"),), "int", "V"),
    FieldSpec("rated_pv_input_voltage_v", (("rated", "pv", "input", "voltage"),), "int", "V"),
    FieldSpec("mppt_range_v", (("mppt", "range"),), "range", "V"),
    FieldSpec("max_dc_input_current_a", (("max", "dc", "input", "current"), ("max", "operating", "pv", "input", "current")), "split_float", "A"),
    FieldSpec("max_short_circuit_current_a", (("short", "circuit", "current"),), "split_float", "A"),
    FieldSpec("strings_per_tracker", (("strings", "per", "mpp"), ("strings", "mpp", "tracker")), "split_int", ""),
    FieldSpec("num_mppt_trackers", (("mpp", "tracker"),), "int", ""),
    FieldSpec("max_active_power_kw", (("max", "active", "power"), ("max", "ac", "output", "apparent", "power")), "float", "kW"),
    FieldSpec("rated_ac_current_a", (("rated", "ac", "output", "current"), ("rated", "ac", "grid", "output", "current")), "split_float", "A"),
    FieldSpec("max_ac_current_a", (("max", "ac", "output", "current"),), "split_float", "A"),
    FieldSpec("output_voltage_range", (("output", "voltage"),), "text", ""),
    FieldSpec("grid_frequency_hz", (("rated", "frequency"),), "text", "Hz"),
    FieldSpec("power_factor_range", (("power", "factor"),), "text", ""),
    FieldSpec("thdi_pct", (("harmonic", "distortion"), ("thdi",)), "percent", "%"),
    FieldSpec("dc_injection_current", (("dc", "injection", "current"),), "percent", "%"),
    FieldSpec("max_efficiency_pct", (("max", "efficiency"),), "percent", "%"),
    FieldSpec("euro_efficiency_pct", (("euro", "efficiency"),), "percent", "%"),
    FieldSpec("mppt_efficiency_pct", (("mppt", "efficiency"),), "percent", "%"),
    FieldSpec("ip_rating", (("ingress", "protection"), ("ip", "rating")), "ip", ""),
    FieldSpec("cabinet_size_mm", (("cabinet", "size"),), "text", "mm"),
    FieldSpec("weight_kg", (("weight",),), "float", "kg"),
    FieldSpec("topology", (("topology",),), "text", ""),
    FieldSpec("internal_consumption_w", (("internal", "consumption"),), "text", "W"),
    FieldSpec("operating_temp_range_c", (("operating", "temperature"), ("running", "temperature"), ("temperature", "range")), "text", "°C"),
    FieldSpec("humidity_pct", (("humidity",),), "range", "%"),
    FieldSpec("altitude_m", (("altitude",),), "float", "m"),
    FieldSpec("noise_db", (("noise",),), "noise", "dB"),
    FieldSpec("cooling", (("cooling",),), "text", ""),
    FieldSpec("warranty_years", (("warranty",),), "int", "years"),
    FieldSpec("surge_protection", (("surge", "protection"),), "surge", ""),
    FieldSpec("grid_standards", (("grid", "regulation"), ("grid", "connection", "standard"), ("grid", "standard")), "standards", ""),
    FieldSpec("safety_emc_standards", (("safety", "emc"), ("emc", "standard")), "standards", ""),
]

def _norm_label(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", label.lower()).strip()

def _match(spec: FieldSpec, label: str) -> bool:
    norm = _norm_label(label)
    if not norm:
        return False
    for group in spec.groups:
        if all(re.search(r"\b" + re.escape(kw) + r"s?\b", norm) for kw in group):
            return True
    return False

def find_spec(label: str) -> FieldSpec | None:
    for spec in FIELDS:
        if _match(spec, label):
            return spec
    return None

def map_evidence(evidence: list[EvidenceRecord], target_model: str) -> list[CanonicalValue]:
    out: list[CanonicalValue] = []
    for i, ev in enumerate(evidence):
        spec = find_spec(ev.raw_label)
        if spec is None:
            continue
        value, note = normalize(spec.value_type, ev.raw_value)
        if value is None:
            continue
        notes = "; ".join(filter(None, [note, ev.notes]))
        out.append(CanonicalValue(
            field=spec.field, source_id=ev.source_id, page=ev.page,
            raw=ev.raw_value, value=value, unit=spec.unit,
            confidence=ev.confidence, notes=notes, evidence_index=i,
        ))
    return out