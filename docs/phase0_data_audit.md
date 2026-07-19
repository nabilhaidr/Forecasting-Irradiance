# S0-5 — Historical Coverage Audit (PLTS-IKN)

**Sprint 0 · Task S0-5 · Deliverable.** How many months of data exist, which
seasons are present **as read from the data's own cloud-regime distribution
(never a textbook monsoon calendar, ML-002)**, the gap profile, and the
maintenance / outage / curtailment periods.

**S0-5 acceptance status: YELLOW.** The audit methodology, deterministic
artifacts, empirical monthly `k_c`/regime distributions, gap and outage
profiles, and full-period operational corroboration are delivered. Acceptance
is held at YELLOW pending two items: (1) the **full-history** sensor-coverage
refresh over the complete Drive inventory — the local run measured only the
**2025-12-01 → 2026-06-30** window, so the operator-reported **WS-3 GHI outage
of March–June 2025** is not yet sensor-measured (it is corroborated here only
by the maintenance log); and (2) the **historian timezone/clock offset is still
unconfirmed** (S0-2 open item), so every local-time claim below — daylight
hours, calendar months, seasonal regime — is provisional under the
`Asia/Makassar` (WITA) working assumption.

This audit builds **no model** and commits **no raw plant data or credentials**.
Phase 1 and every model remain **NO-GO** until Gate M0 passes.

---

## 1. Sources and provenance

| Source | Scope used | Files | Role |
|---|---|---|---|
| Raw COV ZIP export (`gdrive:raw_data`) | June 2026 | 145 ZIP (23,776,109 bytes) | High-resolution per-channel event cross-check |
| `Data Weather Station` instantaneous XLSX | locally-available 2025-12 → 2026-06 | 207 workbooks | Continuous historical coverage / gap / `k_c` / regime |
| `Maintenance Record PLTS IKN 50 MW.xlsx` | 2024-11 → 2026-07 | 1,212 log rows | Maintenance-period corroboration |
| `DCM Manual Calucation Rekon PLTS IKN.xlsx` | 2024-12 → 2026-06 | 1,784 intervals | Outage / limitation periods |
| `IKN Generation.xlsx` | 2025 | 47 curtailment-days | Curtailment periods |

Every file's byte size and SHA-256 are recorded in
`artifacts/phase0_data_audit/source_manifest.csv` (XLSX coverage source) and
`artifacts/phase0_data_audit/operational/operational_source_manifest.csv`
(operator workbooks). Readers consume only the raw `date_time`, raw sensor
value, and `object_caeid` columns of each workbook — never helper/resampled
grids. Accumulation workbooks are excluded by filename.

**Coverage window measured locally:** `2025-12-01 06:07:32` →
`2026-06-30 23:52:08` (7 calendar months). The full 2025 history
(January–November) lives only on the Drive and is measured by the CI workflow
`.github/workflows/s0-5-data-audit.yml` (see §7).

---

## 2. Method (deterministic, backward-only)

- **Grid:** the S0-2 measured `canonical_freq = 1 min`. Each channel's events
  are placed on a 1-minute grid.
- **Alignment:** backward-only zero-order-hold (ZOH). A minute is *covered
  (strict)* when an event falls inside it, and *covered (ZOH)* when the latest
  event at or before the minute end is younger than a 15-minute staleness. No
  future information is ever consulted.
- **Daylight:** computed per minute from the pvlib solar position at the site
  (apparent elevation > 0). Coverage fractions below are **daylight** fractions.
- **`k_c`:** `GHI / GHI_cs`, where `GHI_cs` is pvlib Ineichen with the bundled
  Linke turbidity climatology (ML-004 default). `k_c` is **NaN** wherever
  `GHI_cs < 20 W/m²` (twilight-singularity guard); cloud enhancement `k_c > 1`
  is **not** clipped and is reported (`frac_kc_gt_1`); a `k_c_max = 1.5` outlier
  guard clips and **counts** rather than discards (`kc_clip_count`).
- **Regime:** deterministic rule set (`artifacts/phase0_data_audit/regime_rules.json`,
  version `s0-5-audit-v1`) over `k_c` and its trailing 30-minute variability →
  `CLEAR / MOSTLY_CLEAR / PARTLY_CLOUDY / OVERCAST / HIGHLY_VARIABLE / UNKNOWN`.
  The distribution is normalised over **daylight minutes only**; `RAIN_DEGRADED`
  needs rain-gauge semantics not audited in S0-5 and is not emitted.

> **The haze caveat (PRD §16.6) stands.** The Linke climatology under-states
> dry-season biomass-burning aerosol; on those days modelled `GHI_cs` is too
> high, `k_c` reads artificially low, and the model "sees cloud" where there is
> smoke. `k_c` here is an audit diagnostic, not yet a corrected modelling target.

---

## 3. Coverage timeline (daylight ZOH fraction, GHI)

| EMI ↔ WS | 2025-12 | 2026-01 | 2026-02 | 2026-03 | 2026-04 | 2026-05 | 2026-06 |
|---|---|---|---|---|---|---|---|
| EMI01 (WS-1) | 0.98 | 0.93 | 0.97 | 0.98 | 0.81 | **0.44** | 0.66 |
| EMI02 (WS-2) | 0.98 | 0.98 | 0.81 | **0.00** | **0.00** | **0.02** | 0.68 |
| EMI03 (WS-3) | 0.98 | 0.98 | 0.97 | 0.98 | 0.98 | 0.98 | 0.99 |
| EMI04 (WS-4) | 0.98 | 0.98 | 0.98 | 0.98 | 0.98 | 0.98 | 0.99 |
| EMI05 (WS-5) | **0.25** | 0.99 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

(Per-channel daily and monthly detail: `coverage_daily.csv`,
`coverage_monthly.csv`; heatmap `figures/coverage_timeline.png`. The
EMI↔WS mapping is the S0-3 hypothesis and is still **assumed**.)

Findings:

- **WS-2 GHI is a measured outage, March–May 2026** (coverage 0.00/0.00/0.02).
  This was **not** among the S0-4 leads — a new finding surfaced by the audit.
  It coincides with the maintenance entry *"WS1 and WS2 — Parameter cannot be
  monitored at SCADA"* (2026-05-26).
- **WS-5 GHI starts partial (0.25) in December 2025 then jumps to full from
  January 2026**, consistent with the reported WS-5 pyranometer replacement and
  the RSI head moved into WS-5 (operator: back to normal 2026-01-05).
- **WS-1 GHI degrades in May–June 2026** (0.44 / 0.66), consistent with the
  WS-1 *"GHI … cannot be monitored"* maintenance ticket (opened 2026-01-20).
- **WS-3 and WS-4 GHI are continuous (~0.98)** across the local window.

---

## 4. Gap and outage profile

Inter-event gap statistics per channel are in `gap_profile.csv`; zero-daylight
runs of ≥3 days are in `outage_candidates.csv` (**63 candidates** in the local
window). The longest runs:

| EMI ↔ WS | Channel | Start | End | Days |
|---|---|---|---|---|
| EMI03 (WS-3) | POA, RSI_01/02/03 | 2025-12-01 | 2026-03-12 | 102 |
| EMI04 (WS-4) | RSI_01 | 2025-12-02 | 2026-03-12 | 101 |
| EMI03 (WS-3) | DNIcosZ | 2025-12-06 | 2026-02-14 | 71 |
| EMI01 (WS-1) & EMI02 (WS-2) | GHI, POA, RSI_01/02/03 | 2026-03-14 | 2026-05-20 | 68 |

- The **WS-3 rear/POA/DNIcosZ block absence (Dec 2025 → mid-March 2026)** is
  consistent with the reported WS-3 RSI removals (2025-06-30) persisting into
  the window; the channels reappear from ~2026-03-13, which the full-history CI
  run and an operator confirmation should explain (re-installation vs mapping).
- The **WS-1 + WS-2 cluster outage (2026-03-14 → 2026-05-20)** across GHI/POA/RSI
  is a coherent multi-channel event and the single largest coverage loss in the
  local window.
- **DNIcosZ is intrinsically sparse** (EMI03 DNIcosZ: 1,714 events, max gap
  ~1,730 h), consistent with the S0-3 event-driven behaviour — not itself an
  outage but a reporting-cadence property.

### Operator-lead cross-check (`operator_lead_crosscheck.csv`)

| Lead | Reported | Measured status (window 2025-12 → 2026-06) |
|---|---|---|
| WS-3 GHI outage | down Mar 2025 → 2025-06-25 | **not_found** — outside the local window; see CI full-history |
| WS-3 RSI 01/02/03 removed | 2025-06-30 | **absent_from_window_start** — zero for the whole window (consistent with pre-window removal) |
| WS-4 RSI_01 removed | 2025-09-01 | zero from 2025-12-02 (effectively whole window) |
| WS-4 RSI_02 removed | 2026-01-05 | **corroborated** — data ends and channel goes to zero from **2026-01-06** (a genuine in-window measurement matching the reported date) |

The WS-4 RSI_02 transition is the one operator lead the local window can
directly measure, and it lands one day after the reported removal — a clean
corroboration. The 2025 leads require the full-history CI run.

---

## 5. Empirical monthly `k_c` and cloud-regime — read from the data

Monthly `k_c` distribution (EMI01/WS-1 GHI; full per-EMI table in
`kc_monthly.csv`, figure `figures/kc_monthly.png`):

| Month | valid min | `k_c` mean | p10 | p50 | p90 | frac `k_c`>1 |
|---|---|---|---|---|---|---|
| 2025-12 | 20,875 | 0.59 | 0.18 | 0.52 | 1.07 | 0.15 |
| 2026-01 | 19,933 | 0.64 | 0.23 | 0.58 | 1.08 | 0.16 |
| 2026-02 | 18,827 | 0.56 | 0.16 | 0.49 | 1.06 | 0.14 |
| 2026-03 | 20,806 | 0.66 | 0.21 | 0.60 | 1.14 | 0.21 |
| 2026-04 | 16,585 | 0.68 | 0.20 | 0.70 | 1.14 | 0.26 |
| 2026-05 | 9,215 | 0.56 | 0.09 | 0.46 | 1.10 | 0.19 |
| 2026-06 | 13,390 | 0.66 | 0.00 | 0.64 | 1.19 | 0.28 |

Monthly regime distribution over daylight minutes (EMI01/WS-1; full table
`regime_monthly.csv`, figure `figures/regime_monthly.png`):

| Month | CLEAR | MOSTLY_CLEAR | PARTLY_CLOUDY | OVERCAST | HIGHLY_VARIABLE | UNKNOWN |
|---|---|---|---|---|---|---|
| 2025-12 | 0.11 | 0.06 | 0.21 | 0.32 | 0.22 | 0.08 |
| 2026-01 | 0.11 | 0.07 | 0.23 | 0.22 | 0.25 | 0.12 |
| 2026-02 | 0.07 | 0.03 | 0.21 | 0.36 | 0.25 | 0.07 |
| 2026-03 | 0.13 | 0.06 | 0.20 | 0.23 | 0.31 | 0.07 |
| 2026-04 | 0.13 | 0.05 | 0.07 | 0.18 | 0.34 | 0.24 |
| 2026-05 | 0.04 | 0.02 | 0.05 | 0.15 | 0.16 | 0.59 |
| 2026-06 | 0.07 | 0.02 | 0.06 | 0.10 | 0.37 | 0.38 |

**What the data says (not the calendar):**

- The site is **overwhelmingly cloudy**: pure `CLEAR` minutes never exceed ~13%
  of daylight in any month; `OVERCAST` + `HIGHLY_VARIABLE` + `PARTLY_CLOUDY`
  dominate. A forecaster's "clear day" prior would be wrong here.
- **December–February** carry the heaviest `OVERCAST` mass (0.32 / 0.22 / 0.36)
  and the lowest `k_c` medians — the wettest, most-attenuated stretch in the
  window.
- **March–April** shift toward `HIGHLY_VARIABLE` (0.31 / 0.34) with higher `k_c`
  medians and the most cloud-enhancement (`frac k_c>1` up to 0.26) — a
  convective, ramp-heavy regime.
- Elevated `UNKNOWN` in **May–June** is a **coverage** artefact (WS-1 daylight
  gaps), not a sky state — it tracks §3/§4, not weather.

> **Caveat on "season".** This is **one partial wet-season window (7 months)**,
> and every month label is provisional under the unconfirmed historian timezone.
> The full annual cloud-regime cycle — and therefore the honest definition of an
> "unseen season" for the test split (ML-002, MASTER_CONTEXT §12) — requires the
> full-history CI run. **No textbook monsoon calendar is assumed anywhere.**

---

## 6. Maintenance, outage, and curtailment periods (operator corroboration)

Extracted deterministically from the operator workbooks (no personal names are
retained). Artifacts under `artifacts/phase0_data_audit/operational/`:

- **`maintenance_periods.csv`** — 1,212 rows (2024-11 → 2026-07); **20**
  weather-station-related. The WS timeline strongly corroborates the sensor
  findings and the S0-4 leads:
  - **WS-3:** 2025-03-06 *"Communication Loss"* (Open) → 2025-07-07
    *"Troubleshooting and normalization"* (Close) — corroborates the corrected
    lead (WS-3 GHI down March 2025, back ~25 June 2025), superseding the earlier
    survey remark that misdated it as "March 2026".
  - **WS-5:** a run of pyranometer-cable / STS-2 shutdown entries (Aug 2025),
    then *"new pyranometer at WS 5 … lower than other stations"* on
    2026-01-02/03/05 — corroborates the RSI head moved into WS-5 and the WS-4
    RSI_02 removal on 2026-01-05.
  - **WS-1:** 2026-01-20 *"GHI … cannot be monitored"* (Open); **WS-1 & WS-2**
    2026-05-26 *"Parameter cannot be monitored at SCADA"* — corroborates the
    measured WS-1 (May–June) and WS-2 (March–May) coverage losses.
- **`dcm_outage_limitation.csv`** — 1,784 external-outage / external-limitation
  intervals with equipment, panel, and minute-lost. These are **grid/plant**
  outages (OG/STS feeders), distinct from the **sensor** outages in §3–§4.
- **`curtailment_periods.csv`** — 47 days with positive curtailed energy
  (from `IKN Generation.xlsx`). Curtailment is a plant-dispatch state, not a
  sky state, and must be excluded when learning `k_c` dynamics.

---

## 7. Full-history run and reproduction

- **Local (this deliverable):**
  `python -m src.characterisation.data_audit_cli --scope irradiance
  --xlsx-root "<Data Weather Station>" --cov-dir raw_data
  --site-config configs/site_plts-ikn.yaml
  --output-dir artifacts/phase0_data_audit`
  and `--scope operational --spec-raw-dir "spec raw"
  --output-dir artifacts/phase0_data_audit/operational`.
- **Full history (authoritative coverage timeline):** the manual, read-only,
  pinned workflow `.github/workflows/s0-5-data-audit.yml` stages the 145 COV
  ZIPs and **every** instantaneous XLSX channel (GHI/DHI/DNIcosZ/POA/RSI/WS-5
  `Total_Irradiance`, accumulation excluded) over the complete Drive inventory
  via rclone, runs the same `--scope irradiance` CLI, and uploads only the
  deterministic evidence. It measures the March–June 2025 WS-3 GHI outage and
  the 2025 RSI removals directly. Its artifacts supersede the local-window
  numbers here once attached.

Each artifact set carries a `run_manifest.json` with a per-file SHA-256 map and
the explicit `timezone_caveat`. Every run is deterministic.

---

## 8. Open items forwarded

| Item | Owner | Why |
|---|---|---|
| Full-history CI coverage refresh (measure Mar–Jun 2025 WS-3 outage + 2025 RSI removals from sensors) | Data Eng | Local window starts 2025-12; 2025 is Drive-only |
| Historian timezone/clock confirmation (S0-2) | Data Eng | Makes every local-time / month / season claim final |
| WS-3 rear/POA channel reappearance ~2026-03-13 — re-install or mapping? | O&M | Reconciles measured runs with the reported permanent removals |
| EMI↔WS mapping confirmation (S0-4) | Data Eng | All per-WS attributions assume EMI0x ↔ WS-x |
| Which RSI head served WS-5, and WS4.3 status | O&M | S0-4 open item; affects rear-side channel provenance |

Until these close and the full-history CI evidence is attached, S0-5 acceptance
stays **YELLOW** and Gate M0 remains **2/7**.
