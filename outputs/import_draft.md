### Field Comparison Table
| Field | Status | Confidence | Source 1 | Source 2 | Notes |
| --- | --- | --- | --- | --- | --- |
| rated_power_kw | source_1_only | high | 5.0 kW | - |  |
| max_dc_input_power_kw | agrees | high | 6.5 kW | 6.5 kW |  |
| max_dc_voltage_v | agrees | high | 1100 V | 1100 V |  |
| start_up_voltage_v | agrees | high | 140 V | 140 V |  |
| rated_pv_input_voltage_v | source_2_only | high | - | 600 V |  |
| mppt_range_v | agrees | high | [120.0, 1000.0] V | [120.0, 1000.0] V |  |
| max_dc_input_current_a | conflict | high | [20.0, 20.0] A | [13.0, 13.0] A |  |
| max_short_circuit_current_a | conflict | high | [30.0, 30.0] A | [19.5, 19.5] A |  |
| strings_per_tracker | source_1_only | high | [1, 1] | - |  |
| num_mppt_trackers | agrees | high | 2 | 2 |  |
| max_active_power_kw | agrees | high | 5.5 kW | 5.5 kW |  |
| rated_ac_current_a | agrees | high | [7.6, 7.3] A | [7.6, 7.3] A |  |
| max_ac_current_a | agrees | high | [8.4, 8.0] A | [8.4, 8.0] A |  |
| output_voltage_range | conflict | high | 3L/N/PE 220/380V, 230/400V 0.85Un-1.1Un | 220/380V, 230/400V 0.85Un-1.1Un |  |
| grid_frequency_hz | conflict | high | 50 / 60 (Optional) Hz | 50/45-55 Hz |  |
| power_factor_range | agrees | high | 0.8 leading to 0.8 lagging | 0.8 leading to 0.8 lagging |  |
| thdi_pct | agrees | high | 0.03 % | 0.03 % |  |
| dc_injection_current | agrees | high | 0.005 % | 0.005 % |  |
| max_efficiency_pct | agrees | high | 0.982 % | 0.982 % |  |
| euro_efficiency_pct | conflict | high | 0.975 % | 0.976 % |  |
| mppt_efficiency_pct | agrees | high | 0.99 % | 0.99 % |  |
| ip_rating | agrees | high | IP65 | IP65 |  |
| cabinet_size_mm | agrees | high | 283×463×178 (Excluding connectors and brackets) mm | 283×463×178 (Excluding Connectors and Brackets) mm | values considered equal after normalization |
| weight_kg | agrees | high | 11.0 kg | 11.0 kg |  |
| topology | conflict | high | Transformerless | Non-Isolated |  |
| internal_consumption_w | source_1_only | high | <1W (Night) W | - |  |
| operating_temp_range_c | agrees | high | -25 to +60 , >45 Derating °C | -25 to +60 , >45 Derating °C |  |
| humidity_pct | agrees | medium | [0.0, 100.0] % | [0.0, 100.0] % |  |
| altitude_m | agrees | high | 4000.0 m | 4000.0 m |  |
| noise_db | agrees | high | <45 dB | <45 dB |  |
| cooling | conflict | high | Free Cooling Smart Cooling | Natural Cooling |  |
| warranty_years | agrees | high | 5 years | 5 years |  |
| surge_protection | agrees | high | AC Type II, DC Type II | AC Type II, DC Type II |  |
| grid_standards | conflict | high | [IEC 61727, IEC 62116, EN 50549] | [IEC 61727, IEC 62116, CEI 0-21, EN 50549, NRS 097, RD 140, UNE 217002, OVE-Richtlinie R25, G99, VDE-AR-N 4105] | am2 lists superset of standards (10 vs 3 codes) |
| safety_emc_standards | agrees | high | [IEC/EN 61000-6-1/2/3/4, IEC/EN 62109-1, IEC/EN 62109-2] | [IEC/EN 61000-6-1/2/3/4, IEC/EN 62109-1, IEC/EN 62109-2] |  |

### Conflicts
- max_dc_input_current_a: [20.0, 20.0] A (AM2-P1) vs [13.0, 13.0] A (AM2)
- max_short_circuit_current_a: [30.0, 30.0] A (AM2-P1) vs [19.5, 19.5] A (AM2)
- output_voltage_range: 3L/N/PE 220/380V, 230/400V 0.85Un-1.1Un (AM2-P1) vs 220/380V, 230/400V 0.85Un-1.1Un (AM2)
- grid_frequency_hz: 50 / 60 (Optional) Hz (AM2-P1) vs 50/45-55 Hz (AM2)
- euro_efficiency_pct: 0.975 % (AM2-P1) vs 0.976 % (AM2)
- topology: Transformerless (AM2-P1) vs Non-Isolated (AM2)
- cooling: Free Cooling Smart Cooling (AM2-P1) vs Natural Cooling (AM2)
- grid_standards: [IEC 61727, IEC 62116, EN 50549] (AM2-P1) vs [IEC 61727, IEC 62116, CEI 0-21, EN 50549, NRS 097, RD 140, UNE 217002, OVE-Richtlinie R25, G99, VDE-AR-N 4105] (AM2)

### Present in one source only
- rated_power_kw: 5.0 kW (AM2-P1)
- rated_pv_input_voltage_v: 600 V (AM2)
- strings_per_tracker: [1, 1] (AM2-P1)
- internal_consumption_w: <1W (Night) W (AM2-P1)

### Unclear / low confidence
- humidity_pct: [0.0, 100.0] % (confidence: medium)

### Recommended verification questions
- What is the correct value for max_dc_input_current_a?
- What is the correct value for max_short_circuit_current_a?
- What is the correct output voltage range?
- What is the correct grid frequency?
- What is the correct euro efficiency percentage?
- What is the correct topology?
- What is the correct cooling method?
- What are the correct grid standards?
- Can you confirm the humidity percentage range?
