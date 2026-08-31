# Import Review Draft
**Generated:** 2026-08-31 08:14
**Target Model:** SUN-5K-G06P3
**Task:** Nepal Import (China → Nepal)

## Summary

| Metric | Count |
|--------|-------|
| Total Fields | 28 |
| Agreements | 2 |
| Conflicts | 4 |
| Source Only | 15 |
| Missing | 7 |

## Source Comparison

| Source | Variant | Fields Extracted |
|--------|---------|------------------|
| Source 1 | AM2-P1 | 22 |
| Source 2 | AM2 | 22 |

## Verified Fields (Agreement)

These fields match across both sources:

- **product.weight**: 11 kg
- **product.warranty**: 5 Years

## Conflicts (Requires Review)

**These fields differ between sources. Manual review required.**

### product.rated_output_voltage
- **AM2-P1:** 3L/N/PE 220/380V, 230/400V 0.85Un-1.1Un (this may vary with grid standards) V
- **AM2:** 220/380V, 230/400V 0.85Un-1.1Un V
- **Reason:** Values differ - manual review needed

### product.euro_efficiency
- **AM2-P1:** 97.5%
- **AM2:** 97.8%
- **Reason:** Values differ - manual review needed

### product.ip_rating
- **AM2-P1:** IP65
- **AM2:** 65 IP
- **Reason:** Values differ - manual review needed

### compliance.surge_protection
- **AM2-P1:** DC Type II / AC Type II
- **AM2:** TYPE II(DC), TYPE II(AC)
- **Reason:** Values differ - manual review needed

## Source-Only Fields

These fields were found in only one source:

- **product.max_pv_input_power**: 7.8 kW (from AM2)
- **product.max_pv_input_voltage**: 1100 V (from AM2)
- **product.mppt_voltage_range**: 120-1000 V (from AM2)
- **product.startup_voltage**: 140 V (from AM2)
- **product.rated_output_power**: 6 kW (from AM2)
- **product.rated_output_current**: 9.1/8.7 A (from AM2)
- **product.grid_frequency**: 50/45-55, 60/55-65 Hz (from AM2)
- **product.max_efficiency**: 98.3% (from AM2)
- **product.operating_temperature**: +60 °C (from AM2)
- **product.topology**: Non-Isolated (from AM2)
- **compliance.safety_emc_standards**: IEC/EN 61000-6-1/2/3/4, IEC/EN 62109-1, IEC/EN 62109-2 (from AM2)
- **protection.dc_reverse_polarity**: Yes (from AM2)
- **protection.ac_short_circuit**: Yes (from AM2)
- **protection.thermal**: Yes (from AM2)
- **protection.islanding**: Yes (from AM2)

## Missing Fields

These fields were not found in either source:

- product.model
- product.variant
- product.rated_power
- manufacturer.legal_name
- manufacturer.factory_address
- manufacturer.country
- compliance.grid_standards

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
