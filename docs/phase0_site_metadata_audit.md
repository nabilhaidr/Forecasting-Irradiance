# Phase 0 Site Metadata Audit

S0-4 acceptance status: **YELLOW**

The canonical `site_configuration` + `sensor_metadata` are now populated in
[`configs/site_plts-ikn.yaml`](../configs/site_plts-ikn.yaml) — the single
canonical location — with per-field provenance, derived geometry (row pitch,
GCR, module height), bifaciality, albedo default, RSI mounting survey data,
and the weather-station instrument inventory. The task remains **yellow**, not
green, because per-unit serial numbers and calibration date/due/factor records
were not among the available sources, the RSI sensor model and the
EMI↔WS SCADA mapping are unconfirmed, and the survey-derived pitch/GCR still
needs design-drawing confirmation. Every unresolved field carries an owner,
reason, and due date in `unresolved_metadata`.

This is a Sprint 0 discovery deliverable. No forecasting model, persistence
baseline, resampler, or feature pipeline was created. Raw sources stay outside
Git; only derived audit evidence is committed.

## Sources audited

| Source | Type | Role |
|---|---|---|
| `spec raw/Backside Irradiance Sensor Data (raw).xlsx` | Field survey workbook | RSI mounting positions/heights/tilt, PV string/row geometry (both phases) |
| `spec raw/Surface Albedo Forecast TMY NSRDB PLTS IKN.xlsx` | Modelled TMY workbook | `albedo_default` (annual mean of half-hourly NSRDB TMY series, n=35,040) |
| `spec raw/Jinko Solar JKM625N 78HL4-BDV datasheet.pdf` | Vendor datasheet | Module model, dimensions, bifacial factor 80% ± 5% |
| `spec raw/panel_spec.yaml` | Extracted spec | Cross-check of the Jinko datasheet values |
| `spec raw/IKN-CI-PP-MT-009 Material Specification for Weather Station WS-1 sampai WS-4.pdf` | As-built material spec (BOM + vendor manuals) | WS-1..WS-4 instrument inventory (SR20-D2, DR20, HQB-TG1, HQC/HQY family) |
| `spec raw/1005-016 - Weather Station Datasheet WS-5.pdf` | As-built datasheet (ISPP-PSC-SPC-1005-016 Rev 2, 2024-02-25) | WS-5 instrument inventory (Hukseflux SR30-M2-D1, Class A) |
| `spec raw/strings.yaml`, `spec raw/IKN Generation.xlsx` | Plant layout/ops workbooks | Context only (electrical layout, capacity); no canonical metadata taken |
| Normative docs v1.3 + S0-2/S0-3 evidence | Repository | Core site facts, `canonical_freq`, DNI·cosZ decision |

File path, byte size, and SHA-256 of every `spec raw/` source are recorded in
[`artifacts/phase0_site_metadata/source_manifest.csv`](../artifacts/phase0_site_metadata/source_manifest.csv).

## Consolidated `site_configuration`

| Field | Value | Method | Source | Confidence |
|---|---|---|---|---|
| `latitude_deg` / `longitude_deg` | −0.99117…, 116.63811… | supplied | Product owner statement (docs v1.3) | medium |
| `elevation_m` | 85.0 | supplied | Product owner statement (mean site elevation) | medium |
| `timezone` | Asia/Makassar | supplied | Product owner (WITA); historian clock semantics still unconfirmed (S0-2) | high |
| `canonical_freq` | 1min | measured | S0-2 | high |
| `racking_type` | fixed | supplied | Product owner; consistent with survey geometry | high |
| `surface_tilt_deg` | 10.0 nominal | supplied | Product owner; survey measured 9–10° at the four RSI strings | medium |
| `surface_azimuth_deg` | 0.0 (pvlib convention 0=N) | supplied | Product owner | medium |
| `poa_is_coplanar_with_modules` | true | supplied | Product owner; POA heads WS1.4–WS4.4 sit on array structures | medium |
| `collector_width_m` | 5.00 | measured | Survey "PV String" sheet (Lebar 500 cm, both phases) | high |
| `row_clear_gap_front_m` | 2.50 | measured | Survey "PV String" sheet (both phases) | high |
| `row_pitch_m` | 7.424 | calculated | `width·cos(tilt) + gap` | medium |
| `gcr` | 0.6735 (0.6722 at 9°) | calculated | `width / pitch` | medium |
| `module_height_m` | 1.46 (range 0.97–1.96) | calculated | Mean of 12 surveyed module-edge heights | medium |
| `bifaciality_factor` | 0.80 ± 0.05 | supplied | Jinko JKM625N-78HL4-BDV datasheet | high |
| `albedo_default` | 0.153 | supplied (modelled) | NSRDB TMY annual mean 0.152975; **not a site measurement** | low |
| `has_albedometer` | false | supplied | Product owner | high |
| `horizons_min`, `daylight_elev_threshold_deg`, `clearsky_model`, `nrmse_denominator` | null (deferred) | — | Phase 1 modelling-policy decisions, owner ML Engineering | — |

### GCR and row-pitch derivation

The survey records, for both construction phases, a table (collector) width of
500 cm and a front row-to-row spacing of 250 cm. Reading the 250 cm as a
centre-to-centre pitch would give GCR = 5.0/2.5 = **2.0 > 1**, which is
physically impossible; the value is therefore interpreted as the **clear gap**
between rows. With the nominal 10° tilt:

```
row_pitch_m = 5.00 · cos(10°) + 2.50 = 7.424
gcr         = 5.00 / 7.424        = 0.6735   (0.6722 at the surveyed 9°)
```

The 5.00 m table width is consistent with two JKM625N modules in portrait
(2 × 2.465 m = 4.93 m plus mounting gaps), and the 14 m / 16 m table lengths
with 12–14 modules landscape per table. Full inputs, formula, and the rejected
interpretation are recorded in
[`artifacts/phase0_site_metadata/site_metadata_audit.json`](../artifacts/phase0_site_metadata/site_metadata_audit.json);
the per-phase survey rows are in
[`artifacts/phase0_site_metadata/row_geometry_survey.csv`](../artifacts/phase0_site_metadata/row_geometry_survey.csv).
Design-drawing confirmation of nominal pitch/GCR remains an open action
(Performance Engineering, due 2026-07-31).

### Module height derivation

At every surveyed RSI point the pyranometer sits 29 cm below the module rear
surface, so `module_edge_height = pyranometer_height + 0.29 m` is a direct
measurement of the array surface height at that point. The mean over the 12
surveyed points is **1.46 m**, with a large terrain-driven spread
(0.97–1.96 m). The per-point values are preserved in
[`artifacts/phase0_site_metadata/rsi_mounting_survey.csv`](../artifacts/phase0_site_metadata/rsi_mounting_survey.csv);
a design-basis height remains to be confirmed from the racking drawings.

### Albedo

There is **no albedometer** on site. The only supplied albedo source is the
NSRDB TMY *forecast* series (half-hourly, 2025-01-01 → 2026-12-31, n=35,040):
annual mean **0.152975**, monthly means 0.1447–0.1563, extremes 0.134–0.166
([`artifacts/phase0_site_metadata/albedo_tmy_monthly.csv`](../artifacts/phase0_site_metadata/albedo_tmy_monthly.csv)).
`albedo_default = 0.153` is recorded with **low** confidence and is only the
fallback default; per ADR-014 the Phase 1 rear-side model must fit an
effective monthly albedo against measured RSI on clear-sky periods rather than
trust this modelled constant.

## Consolidated `sensor_metadata`

### Instrument inventory

| Stations | Source | Irradiance instruments | Other instruments |
|---|---|---|---|
| WS-1..WS-4 | IKN-CI-PP-MT-009 (as-built BOM) | Hukseflux **SR20-D2** pyranometers (ISO 9060 secondary standard / Class A); Hukseflux **DR20** pyrheliometer on **HQB-TG1** automatic sun tracker | HQC-EA1 temp/RH, HQC-FS1 wind speed, HQC-FX1 wind direction, HQC-WT1 module temp, HQY-DZG1 environment monitor, HQC-YF12 rain gauge |
| WS-5 | ISPP-PSC-SPC-1005-016 Rev 2 | Hukseflux **SR30-M2-D1** (ISO 9060 Class A, spectrally flat, heated, tilt sensor) | RY-FSX family temp/RH/wind (per datasheet header) |

The presence of a pyrheliometer + sun tracker in the WS-1..WS-4 BOM
independently corroborates the S0-3 conclusion that DNI·cosZ is a measured
channel, not a SCADA derivation. Vendor guidance in both the SR20-D2 manual
and the SR30 brochure recommends a **2-year recalibration interval**.

### Channel table

| Channel | Instrument | Mounting | Open items |
|---|---|---|---|
| GHI | SR20-D2 (WS-1..4), SR30-M2-D1 (WS-5) | horizontal | serials/calibration; WS-3 GHI reported down March 2025 → 2025-06-25 (operator correction 2026-07-18) |
| DHI | SR20-D2 assumed (shaded, on tracker) | horizontal | shading configuration not explicitly documented |
| DNI·cosZ | DR20 pyrheliometer + HQB-TG1 tracker | tracker | pyrheliometer ISO class not extracted (scanned attachment); serials/calibration |
| POA (front) | SR20-D2 assumed; heads WS1.4–WS4.4 | co-planar, 10°/0° | serials/calibration |
| RSI | 12 rear-facing heads (WS1.1–WS4.3), model unconfirmed | 29 cm below module rear surface | model, serials/calibration |

### RSI mounting survey (measured)

| Sensor | String | Module edge height (m) | Sensor height AGL (m) | Tilt (°) | Note |
|---|---|---|---|---|---|
| WS1.1 / WS1.2 / WS1.3 | WB09-INV07-ST15 | 1.76 / 1.96 / 1.74 | 1.47 / 1.67 / 1.45 | 9 | — |
| WS2.1 / WS2.2 / WS2.3 | WB05-INV02-ST13 | 1.22 / 1.25 / 1.30 | 0.93 / 0.96 / 1.01 | 10 | — |
| WS3.1 / WS3.2 / WS3.3 | WB06-INV18-ST01 | 1.71 / 1.73 / 1.73 | — | 10 | all three reported removed 2025-06-30 (operator correction 2026-07-18); WS3.2/3.3 heights not recorded |
| WS4.1 / WS4.2 / WS4.3 | WB04-INV15-ST11 | 1.11 / 1.04 / 0.97 | 0.82 / 0.75 / — | 9 | WS4.1 reported removed 2025-09-01 and WS4.2 removed 2026-01-05 (operator correction 2026-07-18); earlier record attributed the WS-5 replacement move (and later STS-2 overcurrent failure) to WS4.3 — attribution unresolved (owner: O&M) |

The RSI representativeness caveat stands: these are single-point sensors and
are **not** an array-average rear irradiance (FR-020).

### Operational findings forwarded to S0-5

- WS-3 GHI pyranometer reported shut down from March 2025 and back to normal
  since 2025-06-25 (operator correction 2026-07-18; the earlier survey remark
  misdated this as March 2026) — expect a WS-3 GHI coverage hole over
  March–June 2025 in the historical audit.
- RSI heads reported removed: WS3.1/WS3.2/WS3.3 on 2025-06-30, WS4.1 on
  2025-09-01, WS4.2 on 2026-01-05 (operator correction 2026-07-18) — expect
  stepwise RSI channel loss; which head served WS-5 remains unresolved.

## SCADA tag mapping (hypothesis, unconfirmed)

EMI01..EMI05 ↔ WS-1..WS-5 is recorded as an **assumed** mapping with low
confidence. Supporting evidence: S0-3 found EMI05 lacks the GHI/DHI/DNIcosZ
triplet, which matches the single-pyranometer WS-5 datasheet. Confirmation
needs SCADA/historian configuration evidence (Data Engineering, due
2026-07-24).

## Conflicts and discrepancies (recorded, not hidden)

| Topic | Values | Resolution |
|---|---|---|
| Tilt | 10° nominal (supplied) vs 9–10° surveyed | 10° kept as nominal design value; both recorded; GCR sensitivity 0.6722–0.6735 |
| Module height | single design value expected vs 0.97–1.96 m surveyed spread | survey mean 1.46 m recorded as calculated with the full range preserved |
| Albedo | modelled TMY constant vs known monsoon-driven variability | recorded as low-confidence default; ADR-014 monthly fitting mandated for Phase 1 |
| RSI fleet | BOM implies SR20 family vs no explicit rear-sensor model | `model_status: unconfirmed`; O&M to confirm |

## Unresolved fields (owner / due date)

| Field | Owner | Due |
|---|---|---|
| Per-unit serials (all channels) | O&M Engineering | 2026-07-24 |
| Calibration date / due / factor (all channels) | O&M Engineering | 2026-07-24 |
| RSI sensor model | O&M Engineering | 2026-07-24 |
| DHI shading configuration | O&M Engineering | 2026-07-24 |
| DR20 ISO 9060 class | Performance Engineering | 2026-07-24 |
| EMI↔WS SCADA mapping | Data Engineering | 2026-07-24 |
| Design confirmation of pitch/GCR/module height | Performance Engineering | 2026-07-31 |
| Modelling-policy fields (horizons, clear-sky model, …) | ML Engineering | 2026-08-07 |

## Validation and tests

`src/characterisation/site_metadata.py` enforces the metadata contract:
FR-004 core facts present and physical (refuse, never default — including the
0,0 placeholder), valid IANA timezone, racking vocabulary, tilt/azimuth
required for fixed racking, physical ranges for GCR/bifaciality/albedo/module
height, internal consistency of the derived pitch/GCR against their own
formula, the locked S0-3 `is_derived_tag=false` boolean, provenance
method/confidence vocabularies, and owner+reason+ISO due date on every
unresolved entry. Coverage:

- `tests/unit/test_site_metadata.py` — 22 contract tests on synthetic configs.
- `tests/integration/test_site_metadata_pipeline.py` — cross-consistency of
  the committed config against `artifacts/phase0_site_metadata/` and the
  documentation status contract.

Artifacts are rebuilt deterministically from the local sources with
`python scripts/build_site_metadata_artifacts.py` (requires the untracked
`spec raw/` folder; CI validates the committed artifacts instead).

## Acceptance assessment

Met: single canonical location; validated lat/lon/elevation/timezone; racking,
tilt/azimuth, POA co-planarity with provenance; row geometry and module height
with units; GCR calculated from verified survey values; bifaciality with
datasheet source; RSI mounting recorded; albedometer status explicit;
manufacturer/model/class recorded where available; every unresolved field has
owner+reason+due; conflicts recorded; schema validation and tests green.

Not met (blocks GREEN): per-sensor serial and calibration date/due/factor
records; RSI model confirmation; EMI↔WS mapping evidence; design-drawing
confirmation of the survey-derived geometry. **S0-4 therefore remains 🟡.**
