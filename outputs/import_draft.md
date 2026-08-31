# Import Review Draft
**Generated:** 2026-08-31 08:42
**Target Model:** SUN-5K-G06P3
**Task:** Nepal Import (China → Nepal)

## Summary

| Metric | Count |
|--------|-------|
| Total Fields | 28 |
| Agreements | 2 |
| Conflicts | 2 |
| Source Only | 6 |
| Missing | 18 |

## Source Comparison

| Source | Variant | Fields Extracted |
|--------|---------|------------------|
| Source 1 | AM2-P1 | 22 |
| Source 2 | AM2 | 22 |

## Verified Fields (Agreement)

These fields match across both sources:

- **product.max_pv_input_power**: 7.8
- **product.max_efficiency**: 98.3%

## Conflicts (Requires Review)

**These fields differ between sources. Manual review required.**

### product.rated_output_voltage
- **AM2-P1:** (V) 3L/N/PE 220/380V, 230/400V 0.85Un-1.1Un (this may vary with grid standards)
- **AM2:** (V) 220/380V, 230/400V 0.85Un-1.1Un
- **Reason:** Values differ - manual review needed

### compliance.surge_protection
- **AM2-P1:** DC Type II / AC Type II
- **AM2:** TYPE II(DC), TYPE II(AC)
- **Reason:** Values differ - manual review needed

## Source-Only Fields

These fields were found in only one source:

- **product.rated_output_power**: 6 (from AM2)
- **product.rated_output_current**: 9.1/8.7 (from AM2)
- **product.euro_efficiency**: 97.8% (from AM2)
- **product.operating_temperature**: +60 (from AM2)
- **compliance.grid_standards**: IEC 61727, IEC 62116, CEI 0-21, EN 50549, NRS 097, RD 140, UNE 217002, (from AM2)
- **compliance.safety_emc_standards**: IEC/EN 61000-6-1/2/3/4, IEC/EN 62109-1, IEC/EN 62109-2 (from AM2)

## Missing Fields

These fields were not found in either source:

- product.model
- product.variant
- product.rated_power
- product.max_pv_input_voltage
- product.mppt_voltage_range
- product.startup_voltage
- product.grid_frequency
- product.weight
- product.ip_rating
- product.warranty
- product.topology
- manufacturer.legal_name
- manufacturer.factory_address
- manufacturer.country
- protection.dc_reverse_polarity
- protection.ac_short_circuit
- protection.thermal
- protection.islanding

## Import Checklist Coverage

### Product Identity [COMPLETE]
- Extracted: 13/13
  - product.model
  - product.variant
  - product.rated_power
  - product.max_pv_input_power
  - product.max_pv_input_voltage
  - product.mppt_voltage_range
  - product.rated_output_power
  - product.rated_output_voltage
  - product.grid_frequency
  - product.max_efficiency
  - product.euro_efficiency
  - product.weight
  - product.ip_rating

### Manufacturer Identity [COMPLETE]
- Extracted: 3/3
  - manufacturer.legal_name
  - manufacturer.factory_address
  - manufacturer.country

### Test Evidence [COMPLETE]
- Extracted: 2/2
  - compliance.grid_standards
  - compliance.safety_emc_standards

### Labeling [PARTIAL]
- Extracted: 0/5

## Notes

- Values are presented as-is from source documents
- Conflicts require manual verification before import
- Source-only fields may indicate document differences
