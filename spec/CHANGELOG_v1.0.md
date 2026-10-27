# Smart CAPEX Specification Changelog v1.0

## Scoped edge / low-latency user context (2026-10-26)

- Added three nullable raw MAOS counters and nine persisted T1/T2/cluster user-ratio dimensions, using paired sum-over-sum aggregation and strict pre-event windows.
- Imported all 890,674 unique linked cell-months' source values without overwriting unrelated KPIs; recalculated profiles for all 3,441 sites (3,318 available, 123 no eligible ratio data, zero errors).
- Added scope table, monthly metric/scope/compare selectors, cluster chart metrics, null gaps and small-ratio precision. Moved monthly MAOS aggregation into services.
- Added the user_context similarity group; new fields honor explicit deselection. Registry grows from 80 to 89 dimensions. Historical timing and existing road/default constraints remain intact.
- Saved source-availability/backfill reports and verified fifteen live chart combinations against API data with no page errors. Updated feature engineering reference, specification and data catalog.

## Feature engineering reference consolidation (2026-10-26)

- Replaced overlapping amendments in `feature_eng.md` with one current 80-dimension catalog covering formulas, sources, storage, actual consumers, missing-data rules, weighting and historical eligibility.
- Reconciled population partial-coverage behavior, verified road provenance, CBR cohort calculations and remaining audit findings; separated implemented checks from proposed enhancements and blocked ablation.
- Documentation-only update; implementation checks are recorded as previously executed, not newly rerun.

## Persisted road context (2026-10-26)

- Added local Geofabrik road ingestion, indexed UTM GeoPackage and hash/licence/source manifest; configured uncalibrated class priors.
- Added nullable `RoadFeatures` and additive migration 0007 (shown before application); backfilled 3,441 sites: 3,440 computed, one NULL, zero errors.
- Registered roads in feature sync; added a separate Roads popup tab, class-length visualization and optional similarity fields.
- Added explicit road opt-in, provenance matching, a 5% road-group cap, selectable per-feature/group weighting and actual comparison weights. Preserved legacy non-road defaults.
- Verified source timestamp 2026-10-22T20:21:33Z from archive README with matching GeoPackage hash and attested all 3,441 stored rows.
- Ran redundancy diagnostics; weighted length/density are collinear. Historical ablation is blocked by missing earlier snapshots; roads remain default-off.

## BIZ_0033 population and CBR corrections (2026-10-26)

- Moved population from Overview to its own site-inspector tab, with density, T1/T2 counts and coverage.
- Retain calculated mapped population under partial land coverage; independently identify water with WorldCover. Never invent missing residents. Source-supported BIZ_0033 totals are about 27,090 (T1) and 56,589 (T2), explicitly labeled partial.
- Align CBR baseline/observed/predicted cohort aggregation, suppress incomplete observed totals, enforce physical bounds, retain chart gaps and show monthly analog/cohort support.
- Added six numerical regression checks and a live BIZ_0033 popup/chart verification script; nineteen automated tests pass.

## Tier population and historical feature timing (2026-10-26)

- Added native GHSL counts for Tier 1 (0–2 km disk) and Tier 2 (2–5 km ring) to similarity and CBR ranking, feature picker/comparison, site inspector and CBR page; retain 1 km density.
- Use three complete pre-event calendar months; reconstruct LTE neighbor/ANP/cluster context from activity evidence, and mark unsupported historical configuration/building/legacy KPI values missing.
- Exclude 2025 population before 2025; preserve the source epoch label and coverage requirements.
- Limit CBR analogs and each outcome horizon to launches/completed months before the query event month. Keep later query observations display-only; insufficient prior analogs produce no estimate.
- Preserve existing deselected-feature behavior. See `feature_eng.md` for formulas, source assumptions and 13 regression checks.

## Population context (2026-10-26)

- Added optional Tunisia population-density map layer with opacity and legend, using GHSL 2025 native 100 m cells and detailed zoom, as selected by the user.
- Added `population_density_1km_per_km2` to similarity and CBR ranking: fractional cell-overlap counts divided by valid area in a 1 km catchment, requiring 90% coverage.
- Preserved existing deselected-feature behavior until production per user instruction; no dimensions removed.
- Historical cases use fixed 2025 population context. Detailed zoom does not add population precision.

## Document Purpose
This changelog tracks all requirement and specification changes from v0 (initial draft) to v1.0 (first implementation release).

## Change Date
2026-10-24

---

## Summary of Changes

### Feature Count Update
- **Previous**: 56 features total in Phase 1
- **Current**: **55 features total** in Phase 1
- **Reason**: Building height feature excluded (see details below)

## Implementation Update: Added Cell Detection

- The 2026-10-25 clarification defines an addition date as the first post-baseline monthly observation where all nine modeled KPIs are zero or absent. A later zero month does not qualify if an earlier month had nonzero KPI activity.
- Evaluate cells independently, including cells in an already active technology. A whole site is `SITE_ADDED` only when every technology in its plan has the same qualifying observation month.
- Provide site-aggregate, all-cell, and added-cell monthly KPI chart modes in the popup.
- Project addition status onto matching cell-plan records by cell ID; retain precomputed site features and show cell-plan configuration beside addition dates in the map popup.
- Provide an event-type map filter, technology-specific icons, and site/cell partial-name search that opens the matching site's popup.
- The current imported report is LTE-only; 2G/3G event detection awaits matching MAOS history.

## Implementation Update: Configuration Features (2026-10-25)

- Define `tech_before` from nonzero MAOS activity before the event date and `tech_after` from technologies in the current cell plan.
- Classify a cell addition on a previously active technology as `SECTOR_ADD`; classify a technology with no prior activity as `TECH_ADD`.
- Keep `bands_added` blank without a dated cell-plan snapshot. Keep theoretical capacity at zero until a documented calculation and its inputs are available.

## UX Update: Adaptive Site Inspector (2026-10-25)

- Replace map-anchored site-detail popups with a persistent selected-site inspector.
- Use a resizable side panel on wide screens and a dismissible, scrollable bottom sheet on mobile.
- Keep the selected marker and nearby-site links visible while feature tabs are inspected.

## Cluster Analysis Page (2026-10-25)

- Add a cluster analysis page showing cluster context and monthly aggregated MAOS KPIs.
- Mark months containing detected launch/addition events with vertical lines and expose the complete cell-event list for the selected cluster.
- Preserve noise-site semantics by excluding `cluster_id=-1` from cluster selection.

## Similarity Feature Inspection (2026-10-25)

- Include all declared mixed-type Gower features plus the report-backed LTE pre-event profile and trends in the similarity vector.
- Show every vector field beside each case; mark comparisons red when either side is unavailable.
- Let a case focus the map on the query site and retrieved similar sites, with a control to return to all sites.
- Add a grouped feature picker that disables unavailable query features, uses equal weights across selected features until trained weights are available, and reports the dimensions used per case.

## CBR Event Impact Page (2026-10-25)

- Retrieve similar historical site launches and predict recipient KPI changes for individual Tier 1/Tier 2 neighbors or the full cluster.
- Plot observed and CBR-estimated monthly KPI trends around the event with a bootstrap interval.
- Keep RSRP and RRC users unavailable because the current LTE report does not supply those measurements; mark the estimate observational rather than causal.

### New Model Fields
Added three new fields to Site model for clustering support:
1. `cluster_id` (IntegerField)
2. `is_cluster_edge` (BooleanField)  
3. `out_of_bounds` (BooleanField)

### Algorithm Parameters
- **Alpha shape parameter**: Fixed at α=0.05 (was configurable in v0)
- **Deduplication threshold**: Specified as 50m (was undefined in v0)
- **Noise point handling**: Clarified that cluster_id=-1 is per-site, not shared

---

## Detailed Changes

### 1. Building Height Feature Exclusion ❌

**Change**: Removed `building_height` from Phase 1 feature set

**Previous State (v0)**:
- Feature #15: `building_height` - Building height at site location
- Total features: 56

**Current State (v1.0)**:
- Feature #15: **EXCLUDED**
- Renumbered subsequent features
- Total features: **55**

**Rationale**:
- Data quality concerns with GHSL building height raster
- Redundancy with `avg_building_height_m` (feature #18) which covers 1km buffer
- Point-level building height less informative than area average
- Simplifies feature engineering pipeline

**Impact**:
- All feature numbering after #14 shifted down by 1
- Data catalog needs update
- No impact on core algorithms (Gower distance handles variable feature counts)

---

### 2. Cluster ID Added to Site Model ✅

**Change**: Added `cluster_id` field directly to Site model

**Previous State (v0)**:
- cluster_id only in ClusterFeatures model (separate table)
- Site model had no clustering information

**Current State (v1.0)**:
```python
class Site(BaseModel):
    # ... existing fields ...
    cluster_id = models.IntegerField(default=-1, 
        help_text="Cluster ID from DBSCAN (-1 for noise/single-site)")
    is_cluster_edge = models.BooleanField(default=False)
    out_of_bounds = models.BooleanField(default=False)
```

**Rationale**:
- Enables direct querying of sites by cluster
- Improves database query performance
- Simplifies API responses (no need for JOIN)
- cluster_id still computed in ClusterFeatures for 6 cluster features

**Impact**:
- Database migration required
- Both Site and ClusterFeatures models contain cluster_id
- No breaking changes to existing code

---

### 3. Alpha Shape Parameter Fixed at 0.05 🔒

**Change**: Fixed alpha parameter for cluster polygon generation

**Previous State (v0)**:
- Alpha parameter configurable
- No default value specified
- Could vary between runs

**Current State (v1.0)**:
- **α = 0.05** (FIXED)
- Hardcoded in ClusterPolygonBuilder class
- Documented in specification

**Rationale**:
- Ensures reproducible cluster polygon generation
- Prevents user error from inappropriate alpha values
- Simplifies configuration (one less parameter to tune)
- Empirically validated value for Tunisia network density

**Impact**:
- Cluster polygons will be consistent across runs
- No user configuration needed
- Can still be changed in code if needed for other regions

---

### 4. Noise Point Handling Clarification 📋

**Change**: Clarified how DBSCAN noise points are treated

**Previous State (v0)**:
- Ambiguous whether noise points share cluster_id=-1
- Unclear if noise points are considered clusters

**Current State (v1.0)**:
- **Each noise point gets cluster_id=-1** (not shared between sites)
- Noise points treated as single-site clusters for feature computation
- Noise points always classified as "edge" sites
- Each noise point has unique cluster with size=1

**Rationale**:
- Prevents confusion in cluster feature computation
- Each site gets unique cluster statistics
- Aligns with CBR requirement that every site must have features
- Noise points are by definition isolated (edge sites)

**Impact**:
- ClusterAnalyzer treats noise points as individual clusters
- cluster_size=1 for all noise points
- cluster_density computed based on 100m buffer polygon

---

### 5. Tunisia Boundary Validation Added 🗺️

**Change**: Added requirement to validate sites within Tunisia boundaries

**Previous State (v0)**:
- No boundary validation
- Assumed all sites are valid

**Current State (v1.0)**:
- TunisiaBoundsValidator class implemented
- Bounding box validation: 30.2°N-37.5°N, 7.5°E-11.6°E
- New field: `out_of_bounds` (Boolean)
- Out-of-bounds sites highlighted in red on maps

**Rationale**:
- Data quality check for cell plan imports
- Identifies coordinate errors (e.g., wrong projection, data entry errors)
- Critical for production deployment
- Prevents invalid predictions from out-of-region sites

**Impact**:
- All sites flagged as in/out of bounds
- Visualization highlights problematic sites
- Can filter out-of-bounds sites from training data

---

### 6. Site Deduplication Threshold Specified 🎯

**Change**: Specified exact deduplication distance threshold

**Previous State (v0)**:
- Deduplication mentioned but threshold undefined
- Implementation details unclear

**Current State (v1.0)**:
- **Threshold: 50 meters**
- First occurrence priority when duplicates found
- Uses DBSCAN with eps=50m, min_samples=1

**Rationale**:
- Cell plan data often has multiple cells at same physical site
- 50m chosen based on typical site clustering in Tunisia
- Prevents double-counting of sites in neighbor analysis
- Standard threshold used in telecom network analysis

**Impact**:
- SiteDeduplicator class removes sites within 50m
- Typical reduction: ~1000 cells → ~100 unique sites
- Must run before spatial clustering (DBSCAN)

---

### 7. Edge Site Identification Criteria 📍

**Change**: Added precise definition of "edge site"

**Previous State (v0)**:
- Edge sites mentioned in ANP but no formal definition
- Unclear how to identify edge vs interior sites

**Current State (v1.0)**:
- **Criterion**: Distance to cluster polygon boundary < 111m (≈0.001°)
- Implemented in ClusterPolygonBuilder.identify_edge_sites()
- Noise points always classified as edge
- New field: `is_cluster_edge` (Boolean)

**Rationale**:
- Edge sites have different network dynamics than interior sites
- Important for similarity matching and prediction
- 111m threshold (~0.001° at Tunisia latitude) chosen as reasonable boundary proximity
- Aligns with ANP edge_score concept

**Impact**:
- Every site labeled as edge or interior
- Can filter similar cases by edge/interior status
- Visualization differentiates edge (orange) vs interior (green) markers

---

## Migration Guide

### Database Migrations
```bash
# Create migration for new Site model fields
python manage.py makemigrations core

# Apply migration
python manage.py migrate core
```

### Code Updates Required
1. **Update data catalog**: Change feature count 56→55
2. **Update feature extraction**: Remove building_height computation
3. **Update clustering pipeline**: Use fixed alpha=0.05
4. **Update visualizations**: Handle out_of_bounds and is_cluster_edge fields

### Configuration Changes
- No config file changes needed (alpha now hardcoded)
- Optional: Add Tunisia polygon file path to config for detailed boundary

---

## Backward Compatibility

### Breaking Changes ⚠️
1. Feature indices shifted after exclusion of building_height
2. Database schema change requires migration
3. GeoJSON exports include new fields (cluster_id, is_cluster_edge, out_of_bounds)

### Non-Breaking Changes ✅
1. Existing feature extraction code still works (just computes 55 instead of 56)
2. Gower distance handles variable feature counts automatically
3. Clustering pipeline is new functionality (no existing code to break)

---

## Validation Checklist

- [x] Site model updated with new fields
- [x] Clustering module implemented (site_clustering.py)
- [x] Visualization module implemented (cluster_visualizer.py)
- [x] Progress tracking updated
- [x] Specification v1.0 created
- [x] Changelog documented
- [ ] Database migration tested
- [ ] Integration with cellplan_loader completed
- [ ] Unit tests written
- [ ] End-to-end test with real data
- [ ] Data catalog updated to 55 features

---

## Feature Synchronization Update (2026-10-25)

- Added an incremental feature synchronization page with Features only and Full sync actions.
- Added persisted job state, stage, site-level progress, start/finish timestamps, and extraction results.
- Full sync reruns MAOS addition detection before recomputing persisted features; only one active sync job is accepted at a time.
- Added the optional feature pipeline progress callback used by the background job.

## LTE KPI Analysis Update (2026-10-25)

- Confirmed the CSV header against the 132 report-selected XML counters and the two Excel reference workbooks.
- Added nullable cell-month fields for LTE throughput, PRB components, CQI support counts, packet delay, and availability inputs/results.
- Updated the monthly importer to derive these values, preserve aggregation components, and report missing source counters.
- Specified weighted site/cluster rollups and missing-is-not-zero behavior for the next increment.
- Reimported 890,674 linked monthly cell records; 26 report counters were present, with 2,550 unmatched source rows retained as unresolved.
- Applied the eRAN throughput formula with LastTTI correction and added weighted site/cluster analysis chart measures.
- Added an as-of-date similarity vector with a one-to-three-month LTE pre-event profile, trends, and completeness metadata.
- Connected profile vectors to a reusable ranker using hierarchical filtering, robust-range Gower distance, and kernel weights; missing metrics are omitted from distance calculations.
- Added `/api/similarity/search/` and a frontend similarity page with site/cell search, top-case ranking, event context, profile coverage, and side-by-side LTE profile values.
- The page labels the results as retrieval only; impact prediction remains pending outcome-target definition.

## References

- **Specification v0**: `spec/smart_capex_spec_v0.md`
- **Specification v1.0**: `spec/smart_capex_spec_v1.0.md`
- **Data Catalog**: `spec/smart_capex_data_catalog_phase1.md` (needs update)
- **Change Management Rules**: `.clinerules/change-management.md`
- **Progress Tracking**: `.tracking/progress.md`

---

## Sign-Off

**Version**: 1.0  
**Date**: 2026-10-24  


### 2026-10-26 ? MAOS aggregation validation and active-user sums

For each month and scope S (site, Tier 1, Tier 2, total cluster), active users = SUM(cell.active_users_avg for cells in S). The source values are already cell averages: do not average across cells/sites, round before summing, or sum across months. This is a sum of average users, not distinct subscribers. Tier 1 excludes the query site and covers <=2 km; Tier 2 covers >2 to <=5 km. The descriptive cluster includes the query site. All-missing measurements remain NULL; measured zero remains zero; partial sums include only reporting cells.

| MAOS feature | Spatial aggregation used by monthly charts and site rollups |
|---|---|
| Active users / traffic users | SUM(cell average counter) |
| DL traffic GB | SUM(bits) / 8e9 |
| PRB utilization % | 100 ? SUM(used) / SUM(available) |
| CQI | SUM(weighted histogram total) / SUM(sample count) |
| DL user throughput kbit/s | SUM(bits ? last-TTI bits) / SUM(time ms) |
| Packet delay ms | SUM(delay time) / SUM(packet count) |
| Availability % | 100 ? (1 ? SUM(unavailable seconds) / SUM(observed seconds)) |
| Edge share | SUM(BorderUE.Avg) / SUM(Traffic.User.Avg) |
| Edge peak ratio | SUM(BorderUE.Max) / SUM(BorderUE.Avg); this is not a simultaneous scope peak |
| Low-latency share | SUM(LowLatency.Avg) / SUM(Traffic.User.Avg) |

Ratios use paired reporting components and positive aggregate denominator. The shared `monthly_annotations()` service now supplies monthly charts, pre-event similarity site profiles and CBR site-month inputs, eliminating duplicated formulas. Similarity `pre_active_users` remains the median of the preceding three complete monthly site sums (a temporal summary). User-context ratios pool their three-month raw components. Neither operation admits event-month/future counters.

`cluster_avg_users` remains a separately named contextual average of site user sums, not the total-cluster monthly KPI. CBR totals concern its fixed baseline-eligible recipient cohort, excluding the intervention site; they are not interchangeable with current descriptive map membership. CBR nonadditive outcomes are means of recipient site KPI responses, whereas descriptive monthly scope ratios pool raw components.

Audit scope: the active monthly/chart, similarity and CBR site-month paths. Legacy `prelaunch_maos_values` still uses average cell PRB and zero defaults, and persisted `ClusterFeatures` still has nonnullable/default-zero fields; those older schema paths are not certified by this audit and require a separate nullable-schema correction before being treated as authoritative measured KPIs.

Validation actually run: Django check; full 43-test suite; production frontend build (existing >500 kB chunk advisory). Added unequal-cell-count active-user tests for all four scopes, NULL/zero tests and pooled PRB/CQI/throughput/delay/availability fixtures. Read-only raw-cell reconciliation for BIZ_0033: all 36 months in Tier 1, Tier 2 and cluster matched (108 monthly comparisons, zero mismatches). September 2026 active users: Tier 1 157.867; Tier 2 499.9962; cluster 540.0614. The 3G-only query site has no imported LTE records, so its own value is unavailable. Evidence: `docs/verification/user_context/active-users-audit.json`; reproduce with `python manage.py shell -c "import runpy; runpy.run_path('scripts/audit_maos_aggregation.py')"`. No data migration or raw-counter rewrite was required.


### 2026-10-26 - Strict traffic-confirmed radio network events

Replaced all-zero launch dating with first strictly positive monthly DL traffic (`thrp_bits_dl`, Huawei `L.Thrp.bits.DL`). Missing traffic never becomes zero; nontraffic counters cannot confirm activation. Cell effective month is the minimum positive month; complete groups use the maximum of their member activation months and retain each member date. Positive cells at the dataset baseline are left censored and excluded from new additions; later first-positive records without earlier measured zeros are explicitly `first_positive_observed`, not proof of a known configuration change.

Canonical addition precedence is SITE_ADDED > TECHNOLOGY_ADDED > FREQUENCY_BAND_ADDED > CELL_ADDED. Current-plan membership defines completeness; unknown/unactivated members prevent a complete-group event. Each added cell is consumed once. Technology events retain labels such as 4G_ADDED or 2G/3G_ADDED (combined when their completion month matches). Band identity includes technology, band and frequency. Current imported traffic is LTE-only, so 2G/3G plan membership without corresponding KPIs cannot establish complete activation.

LTE bandwidth uses `L.ChMeas.PRB.DL.Avail` (`prb_dl_available`): 25/50/75/100 PRBs map to 5/10/15/20 MHz with inclusive +/-5 PRBs. A qualifying change on the same cell requires adjacent valid monthly PRB states and an old traffic-active state. Its effective date is the first positive-traffic observation at the new bandwidth; changed PRBs with zero traffic remain pending. Unknown/unmapped PRBs or missing months break transition dating. Configuration dates stay NULL because no dated configuration snapshots exist. Current configured bandwidth is preserved separately from inferred historic PRB bandwidth. Upgrades/downgrades retain old/new MHz, direction, prior observation and first changed-PRB month.

Implementation: `services/models/preprocessing/network_events.py`; `MAOSLaunchDetector` delegates to it. New additive migration `core/migrations/0009_strict_radio_events.py` adds cell evidence/activation fields and `RadioNetworkEvent`, widens canonical event types, and removes no data. Events persist with deterministic keys; recomputation deactivates superseded records rather than deleting them. Serializers and the cluster endpoint delegate classification to the service. Map filters, site popup, cluster rows and markers use canonical group events; the popup shows cell activation, group completion and bandwidth before/after. Similarity, CBR and user-context cutoffs use official group dates instead of the earliest member date.

Applied to current data: 29,613 cells have monthly history; 51,032 cell states evaluated; 8,511 added cells. Saved 4,798 events: 20 site, 332 technology, 1,482 band, 653 cell, 1,964 bandwidth upgrade and 347 downgrade. Sixteen identifiable bandwidth jumps across gaps were excluded. Activation evidence counts: 19,289 baseline-left-censored, 2,815 zero-to-positive, 5,696 first-positive-observed without a preceding zero, 23,232 without positive traffic. All 3,441 existing configuration summaries refreshed. Reproduce with `python manage.py detect_site_additions --dry-run` or persist with `python manage.py detect_site_additions --refresh-configuration` (Full sync uses the same service).

Validation actually run: full 54-test suite; Django check; migration consistency; frontend production build (existing >500 kB chunk advisory). Independent persisted-data audit checked all 51,032 activation fields, all 4,798 event dates/PRB directions and exact-once coverage for 8,511 added cells, with zero mismatches: `scripts/verify_network_events.py`, report `docs/verification/network_events/validation.json`. These observed operational dates are month-level evidence; unobserved prehistory or the exact day of a configuration change cannot be reconstructed from this dataset.


2026-10-26 verification follow-up: Headless Edge verified all six event classes in live popups, all six event filter options, bandwidth values, member activation months, NULL configuration dates, desktop/mobile layouts, and 626 unique cluster timeline rows; no browser errors (`docs/verification/network_events/browser-report.json`). Fixed stale map/popup responses so a previous request cannot replace a newer site's events. Event badges wrap and event details stack within the inspector. The date-dependent user-context backfill completed for all 3,441 sites: 3,276 with available features, 165 entirely unavailable, zero errors; missing pre-event support remains NULL. Final full suite: 54 tests passed; migration consistency and production frontend build passed. No destructive migration was performed.


### 2026-10-26 - Monthly action hierarchy and grouped map icons

Corrected the whole-history grouping introduced earlier today. The action boundary is the observed activation month (the source has no rollout/batch identifiers). At each site, classify the month's activated cells against only earlier positive-traffic inventory. The first qualifying site action suppresses its same-month technology/band/cell children; later technology additions remain separate. A new technology suppresses same-month band/cell children, while later cells on that technology remain eligible for band/cell additions. Unknown plan members still block unsupported complete-group claims. Future known activations never get swallowed into an earlier event. Strict positive-traffic dating and missing-data handling are unchanged; every action retains its actual member dates and uses the maximum within that monthly cohort.

Multiple CELL_ADDED cells at one site in one month now persist as a single action containing their cell IDs. Different months remain separate actions in the detailed history. On the map, each site has one marker and at most one icon per event type, even when that type has multiple historical actions. Icon tooltips retain action counts. All-events mode shows all distinct types; an individual filter includes a site whenever that type occurs there. Event filters now also apply during a site-name search, which previously bypassed them.

Detector version: positive-traffic-monthly-v2. Recomputed and refreshed all 3,441 configuration summaries without a schema migration; superseded records remain inactive. Current totals: 4,566 active events (20 site, 332 technology, 1,531 frequency-band, 372 grouped cell-addition, 1,964 bandwidth upgrade and 347 downgrade). Independent reconciliation still covers every one of the 8,511 added cells exactly once, and all 51,032 cell activation dates, with zero mismatches. The date-dependent user-context backfill completed with zero errors: 3,260 sites have supported features and 181 remain unavailable; all 3,441 persisted profile cutoff dates match the current official event dates.

Validation run: full 57-test suite passed, including same-month parent suppression, a site followed by a later technology, a technology followed by later cells, and grouping multiple cells in one monthly action. Frontend production build passed with the existing large-chunk advisory. This entry supersedes the earlier whole-history/staggered-group interpretation; separate months cannot be assumed to belong to one rollout without batch evidence.


2026-10-26 map verification: Live Edge checks passed for all six canonical event filters, one icon per distinct type in All-events mode, exactly one matching icon in a selected filter, and exclusion under absent-type filters even during site-name search. Examples: ZAG_0017 has nine actions but two distinct icons; SFA_0088 has six actions but two icons. All six popup classes and 606 unique cluster rows were verified, with zero page errors. Evidence: docs/verification/network_events/browser-report.json. Django system check, migration consistency (no schema change), full 57-test suite and frontend build passed. Independent event reconciliation and the 3,441-site profile-cutoff consistency check both reported zero mismatches.


### 2026-10-26 - Explain historical feature availability and recover event evidence

Investigated the reported values and matched TAT_0055, site 6306, to its TECHNOLOGY_ADDED event on 2023-12-01. The stored feature rows still exist: 4 sectors, 6 cells/sector, 25 m antenna height, 180.8 MHz configured bandwidth, z_antenna 272.367935 m, urban clutter, entropy 0.862930 and building coverage 5.495949%. The broad historical mask deliberately excluded these snapshots because their event-time configuration/provenance is not established. GHSL 2025 catchments also calculate successfully (1-km density 2188.915719 people/km2, Tier 1 15902.946226 people, Tier 2 57381.752876 people), but 2025 context cannot enter a December 2023 feature vector. These are exclusions, not failed extraction or lost data.

Corrected unnecessary exclusion of supported event information: event metadata now restores tech_added=4G and bands_added=L1800,L2100,L800. Technology before/after states use strictly pre-cutoff measured traffic plus the event's confirmed technology labels; for this site LTE before=False (observed zeros), after=True (confirmed activation). Missing 2G/3G history remains NULL, not False. Event fields can be recovered for an explicitly selected later event cutoff as well as the primary event. Actual historical heights, physical configuration and unverified clutter/building snapshots remain excluded. Event band labels come from the detector's frozen plan-membership metadata; they are not proof of a dated bandwidth/antenna configuration snapshot.

TAT_0055 has only one complete pre-event reporting month: November 2023, 16 cells. Raw sums of DL bits, active users, available PRBs, CQI samples, throughput time and delay packets are all zero. Thus traffic/users legitimately equal zero, while PRB/CQI/throughput/delay ratios have zero denominators and remain unavailable. Neighbor scoped edge shares of zero are valid measured ratios; their edge peak ratio is undefined when SUM(BorderUE.Avg)=0. Trends need at least two supported months and a nonzero first value. Legacy avg_*/peak-hour/congestion fields have no verified measurement windows or source counters; supported pre_* fields replace them. Total capacity is an uncomputed zero placeholder, not measured capacity. Cluster ID is deliberately excluded as an identifier. The stored 18 m building height is a class-based urban prior, not an OSM height measurement.

Added services/models/similarity/availability.py with per-feature reason codes and explanations. Query availability now includes the actual feature cutoff and separately labelled inspection-only current values where available. These values never replace NULL model inputs or become eligible for historical distance. The frontend picker shows cutoff, reason, current source context, and disabled unsafe features; comparison tables show exclusion reasons for query and candidate. Both availability and search use the same official event-date helper. Canonical SITE_ADDED now receives the existing whole-site candidate-pool filter formerly limited to NEW_SITE. Candidate vector source selections/prefetches preserve service-based calculation; no data migration or raw-counter rewrite was required.

Validation actually run: 60 tests passed, including event-label recovery, observed false versus unknown technology, future-KPI invariance, inspection metadata preserving NULL inputs, and zero-share versus undefined-ratio reasons. Live headless Edge verified TAT_0055 at the 2023-12-01 cutoff, all recovered event values, disabled excluded features, reason text and current population/configuration inspection on desktop and mobile, with no page errors. Frontend production build passed (existing large-chunk advisory). Evidence: docs/verification/feature_availability/browser-report.json and desktop/mobile screenshots; reproduce with python scripts/verify_feature_availability_browser.py.


### 2026-10-26 - Approved static context and KPI-derived after configuration

User-approved policy: all geographic inputs, stored land-cover/building-height estimates, and GHSL 2025 population are stable across event years. This supersedes the earlier historical masks and population-before-2025 exclusion. KPI performance retains strict timing. The antenna-height fallback is explicitly 25 m until a positive real plan value is available. Policy and uncalibrated relief thresholds are in config/feature_context.json. Implementation: services/models/features/approved_context.py.

| Feature | Formula, source and use |
|---|---|
| sector_count_after | Select cells with positive KPI traffic at/before the event, including the detected action's cell IDs, join to actual cell-plan azimuths, count distinct round((azimuth modulo 360)/5) modulo 72. Never include later cells. Used by similarity and popup configuration. |
| cells_per_sector_after | Number of KPI-evidenced after cells divided by sector count. No evidence stays NULL. Unreported 2G/3G cells are not invented as active. |
| total_bw_after_mhz | For every evidenced LTE cell, use latest positive available-PRB observation no later than event month; map 25/50/75/100 to 5/10/15/20 MHz within inclusive +/-5. Sum only when every required cell maps; otherwise NULL. User explicitly retained strict mapping, not PRB-equivalent estimates. |
| total_prb_available | Sum actual available-PRB counter values across evidenced LTE cells, preserving fractional report averages. New correctly named PRB capacity field; no conversion to Mbps. Legacy total_capacity_after_mbps remains unsupported. |
| z_antenna_m | DEM ground elevation + stored land-cover building-height estimate + mean positive plan antenna height or 25 m fallback. Each component added once; missing DEM/building stays NULL. Persisted for fast static reuse. |
| neighbor_avg_antenna_height_m | Mean supported absolute antenna elevations of other sites within 2 km, same ground + building + mast formula. Missing neighbors/components stay NULL; name retained for compatibility, label says absolute elevation in m ASL. |
| terrain_relief_class | Separate from dominant_clutter. DEM slope <2 flat, 2-<5 rolling, 5-<15 hilly, >=15 steep. Configurable uncalibrated prior; optional/off by default in similarity. Hillshade/elevation colours remain terrain visualizations. |
| dominant_clutter and other clutter fields | Retain static WorldCover/OSM/land-cover estimates. Urban building-height 18 m is an estimate, not a measured roof height. |
| population dimensions | Native 100 m GHSL 2025 catchments now eligible for earlier events under the explicit stability assumption. No change to mapped-area calculations or missing-land rules. |
| avg_users | SUM(active_users_avg) over all reporting cells in the static site cluster during the immediately preceding calendar month; never average users across sites. |
| avg_traffic_dl_gb | SUM(DL bits) / 8e9 in that cluster/month. |
| avg_prb_util_pct, avg_cqi | Pooled raw component ratios in that cluster/month, preserving paired-counter masks and undefined zero denominators. |
| cluster_pre_dl_throughput_kbps | SUM(bits-last-TTI bits) / SUM(time ms), previous cluster month. |
| cluster_pre_dl_packet_delay_ms | SUM(delay time ms) / SUM(packet count), previous cluster month. |
| cluster_pre_cell_availability_pct | 100 * (1 - SUM(unavailable seconds)/SUM(observed seconds)), previous cluster month. |
| cluster_id | Inherit the site's calculated spatial cluster on every cell/sector. Noise stays -1 and each noise site is an independent singleton. Display only, excluded from Gower and weights. |
| cluster_avg_users | Compatibility display alias for avg_users; excluded from weights to avoid counting the same cluster-user sum twice. |

The three-month own-site pre_* profiles remain separate, clearly labelled site metrics; they do not silently change to cluster scope. Cluster baselines use exactly month -1, not the nearest available older month. UL, RSRP and hourly peak/congestion fields remain NULL without source counters. Event-month PRBs are configuration observations; event-month/future KPI performance is not used in pre-event baselines or outcome training.

Additive migrations 0010_approved_static_context and 0011_nullable_absolute_antenna_heights were shown before applying. They add PRB capacity and terrain class, allow honest NULL configuration/height fields, and remove no data. The shared extraction pipeline now preserves PRB-based configuration and the absolute-elevation formula. Run python manage.py refresh_approved_context to recalculate stored configuration/height context; cluster pre-event baselines are calculated per requested cutoff, not stored as undated legacy KPIs.

Actual refresh: 3,441 sites updated, zero errors. Supported persisted counts: 2,706 sector counts, 2,706 PRB capacities, 1,820 complete strictly mapped MHz totals, 3,441 terrain classes, 2,631 neighbor absolute elevations. Missing counts reflect absent LTE evidence, unaligned PRBs or absent neighbors, not imputed zeros. Registry now has 94 declared fields: 81 numeric and 13 categorical, including display-only IDs/aliases and the retained unsupported legacy Mbps field.

Independent TAT_0055 (6306), cutoff 2023-12-01: 16 evidenced LTE cells out of 24 plan cells; sectors 4; cells/sector 4; antenna 25 m; capacity 572.6143 PRBs; absolute antenna elevation 290.367935 m; mean neighbor absolute elevation 284.098386 m; terrain relief rolling, land-cover clutter urban; population T1 15902.946226, T2 57381.752876. Twelve cells have PRB averages outside strict mapping windows, so total MHz is correctly NULL. Cluster 81 has nine member sites, seven reporting sites and 76 reporting cells in November 2023; user sum 75.4926, DL traffic 87050.895392 GB/month, PRB utilization 29.159101%, CQI 9.835623. Independent raw reconciliation reported zero mismatches (docs/verification/approved_context/data-audit.json).

Checks actually run so far: full 66-test suite passed, including missing versus zero, modulo-360 sectors, PRB mapping and future-month exclusion, cluster sum/weighted ratios, isolated noise clusters, absolute elevation and display-only identifier weighting. Django system check and migration consistency passed. Browser and final frontend build verification are recorded separately when completed.


2026-10-26 final approved-context verification: measured zero PRBs are preserved as zero capacity rather than replaced by an older positive value; strict MHz mapping still rejects zero/unmapped PRBs. The KPI-only bulk refresh (python manage.py refresh_approved_context --configuration-only) updated all 3,441 configuration rows with zero errors. Final supported MHz count is 1,818 (supersedes the earlier 1,820 count); sector/PRB capacity counts remain 2,706. Static cluster membership is now shared by cluster baselines, scoped user ratios and CBR cluster scope; outcome recipients still require pre-cutoff activity and noise sites never pool together. All 3,441 scoped user profiles were refreshed: 3,260 have supported values, 181 remain unavailable, zero errors.

Final full suite: 68 tests passed; Django check and migration consistency passed. Frontend production build passed with the existing large-chunk advisory. Live Edge verified all 94 feature fields, historical-year static population/geography eligibility, KPI-projected sectors, correctly labelled PRB capacity, strict unmapped MHz exclusion, previous-month summed cluster users, sector inheritance of cluster ID, display-only identifiers/aliases, optional terrain relief distinct from land-cover clutter, and matching popup/similarity values on desktop/mobile, with zero page errors. Independent TAT_0055 raw-cell/cluster/DEM reconciliation reported zero mismatches. Evidence: docs/verification/approved_context/data-audit.json and browser-report.json. feature_eng.md is the current formula reference; older dated exclusion policies are superseded by this approved static-context policy.


### 2026-10-26 - PCA similarity and Data Explorer (implementation)

Added an optional, explained PCA component picker alongside all original features, a candidate-only complete-case PCA service, explicit actual comparison weights, and a raw/calculated/profile Data Explorer with filters, pagination and displayed-page CSV export. Similarity orchestration moved from views into services. Preserved original fallback behavior, static-context assumptions, strict KPI timing, NULL handling, PRB units and the road cap. No migration. Detailed formulas/policy are in feature_eng.md and the data catalog; plan is docs/similarity_pca_explorer_plan.md.

Checks so far: 79-test full suite passed before the final API round-trip test; all 12 focused PCA/explorer tests passed afterward. Initial frontend production build and Django checks passed. Full real-data audit and live browser verification are in progress; final results will be recorded separately.


### 2026-10-26 - Final PCA / Data Explorer validation

Completed the planned review and implementation. The audit calculated all 1,380 candidate-site profiles and reported 12 entirely unsupported fields, three constant-when-observed fields and 25 high-correlation pairs. The data catalog contains the full 94-field availability table and correlation table. TAT_0055 PCA retained 13 components from 38 encoded inputs, explaining 90.3588% variance across 297 complete candidates out of 301 matching cases. All original dimensions remain inspectable. Sparse performance fields excluded from this example PCA are explicitly disclosed; PCA is optional retrieval, not a validated replacement for CBR.

Checks actually completed on the final implementation:
- All 80 Django tests passed (including 12 new PCA/explorer tests).
- Django system check and migration consistency passed; no migration required.
- Final Vite production build passed (93 modules); existing >500 kB bundle advisory remains.
- Live headless Edge passed raw filters and CSV export, calculated cluster sums, missing-feature filtering, cutoff visibility, mobile explorer layout, PCA variance/loadings, real top-10 ranking/comparison, and switching back to all 94 original fields. Zero page errors.
- Live original-feature equal-per-group search returned ten cases with normalized actual weights summing to one; cluster users remained 75.4926.
- git diff --check passed (line-ending conversion notices only).

Artifacts: docs/verification/similarity_pca/review.json, browser-report.json, raw-example.csv, and desktop/mobile screenshots. Reproduction: scripts/audit_similarity_pca.py and scripts/verify_pca_explorer_browser.py. Source formulas and assumptions are documented in feature_eng.md and spec/smart_capex_data_catalog_phase1.md. The local backend was refreshed to serve the new APIs.


### 2026-10-26 - Investigation of repeated 18 m building height

Audited all 3,441 ClutterFeatures rows: urban 18 m = 1,887 sites; suburban 8 m = 666; rural 4 m = 262; forest 0 m = 612; water 0 m = 14. These are deterministic land-cover class priors in ClutterFeatureExtractor.to_dict(), not observed averages of building heights. The field varies only when the dominant class varies and therefore adds no independent information beyond that class. It also influences absolute antenna elevation and neighboring antenna-elevation estimates through the approved DEM + estimated building height + mast-height formula.

Read-only fresh extraction reproduced BIZ_0033 (1534): 50.232912% built-up WorldCover, urban -> 18 m; TAT_0055 (6306): 54.757968% built-up, urban -> 18 m. The class threshold is >50% urban, >20% suburban. The displayed repetition is caused by the lookup, not rounding or stale calculation in these examples.

Local source inspection: the OSM GeoPackage has fid, geometry, osm_id, code, fclass, name and type, with no height or building:levels attributes. The installed ghs_built_s_e2025_r2023a_54009_100_v1_0_tun.tif is built-up surface area in square metres, not height. Corrected the misleading settings alias: GHSL_BUILT_SURFACE points to that file; GHSL_HEIGHTS is None until an actual height product is installed. Official product descriptions: https://human-settlement.emergency.copernicus.eu/ghs_buS2023.php (surface) and https://human-settlement.emergency.copernicus.eu/ghs_buH2023.php (estimated height).

Corrected popup and shared similarity/Data Explorer labels to Building height estimate (land-cover class prior), with visible provenance. Forest/water zero is explicitly a prior convention, not proof of absent buildings. Kept existing user-approved static estimates and dependent calculations; no source data, feature values or schema were rewritten. Recommendation: replace this class proxy with footprint-weighted positive building-height observations/estimates from a real height product when acquired, report coverage, and avoid double-counting the class proxy alongside dominant_clutter in production selection.

Validation actually run: complete stored-value distribution; local OSM schema and raster inspection; fresh WorldCover/OSM extraction for sites 1534 and 6306; Django system check; 20 approved-context/PCA/explorer regression tests; frontend production build. All passed; the existing large-bundle advisory remains. No new measurement-based height calculation is claimed.


### 2026-10-27 - Event-rule compliance audit (read-only)

Request audited: first strictly positive traffic month is the event month; site/technology/band group taxonomy; PRB-inferred bandwidth changes with persistence; partial activation month excluded from effect measurement (start at +1).

Evidence: scripts/audit_event_rule_compliance.py and docs/verification/event_rule_compliance/2026-10-27.json. Read all 51,032 cells and 4,566 active events (20 SITE_ADDED, 332 TECHNOLOGY_ADDED, 1,531 FREQUENCY_BAND_ADDED, 372 CELL_ADDED, 1,964 upgrades, 347 downgrades). No database updates or event reclassification were performed.

Passed checks: zero mismatches between persisted cell activation and MIN(month_date) where DL traffic >0; zero addition dates differing from the latest activation among their assigned member cells; zero per-member date metadata mismatches; no duplicated added-cell assignment; zero bandwidth dates differing from first positive traffic at the new inferred PRB state. Missing traffic is never treated as zero. Mapping uses inclusive +/-5 windows around 25/50/75/100 PRBs -> 5/10/15/20 MHz. First-dataset-month positive cells are left-censored baseline inventory, not asserted new launches.

Gaps against the requested rules:
1. No sustained-shift requirement is enforced: a single positive-traffic month at a changed mapped bandwidth generates an event. In a diagnostic scenario requiring at least two consecutive mapped months at the new state, 2,039/2,311 stored bandwidth events have persistence; 33 revert after one month; 239 have no consecutive confirming followup (missing/unmapped/different next state or end of data). The latter are unconfirmed rather than proven false. A synthetic 25 ->100 ->25 PRB sequence produces both events in the current detector. A persistence threshold and separate confirmation month must be implemented before claiming compliance; two months is an audit scenario, not a silently adopted production rule.
2. CBR PREDICT_OFFSETS is 0..6. Both analog response calculation and group/per-neighbor output include estimates for offset 0. The UI labels it Event month without excluding it from effect calculation. Required behaviour: preserve the first-positive activation month, retain month-0 observations as partial/context only, and measure/predict effects from +1. November 2023 activation stays November; the first complete effect month is December 2023.
3. Taxonomy is currently based on activation-month cohorts, following the earlier approved requirement that later technology/cell actions stay separate. Under a literal complete-current-plan group interpretation, 46 technology, 74 band and two site events have later-activated members of the same site/technology/band. Existing tests intentionally accept these monthly cohorts. These counts are a policy mismatch under the strict full-plan interpretation, not a reason to silently combine unrelated future additions or move an initial site launch later.
4. Band identity currently includes frequency: (site, technology, band, frequency), rather than only (site, technology, band). Twenty-two band events already have earlier active cells with the same technology/band at a different frequency. A strict band-level taxonomy would treat those as additions within an existing band.
5. All 332 technology actions expose technology-specific labels (e.g. 4G_ADDED). Band labels remain generic FREQUENCY_BAND_ADDED, and bandwidth labels remain generic BANDWIDTH_UPGRADE/DOWNGRADE. Member bands and previous/new MHz are stored, so descriptive <band>_added and bandwidth_<from>_to_<to>_upgrade/downgrade labels can be generated while keeping canonical event_type values for filters/API compatibility.

Regression checks actually run: 18 event/CBR tests passed and Django system check passed during the run. These validate existing behaviour; they do not establish compliance with the new persistence/+1 rules. No frontend build was needed because this turn only added an audit and documentation. No sustained filtering, effect-window change or taxonomy change is claimed implemented.


### 2026-10-27 - Sustained bandwidth, band identity and full-month effects

Implemented detector version positive-traffic-sustained-v3. Config: config/event_rules.json (two consecutive mapped bandwidth months; effect_start_offset=1; monthly addition cohorts; band identity site/technology/band). User explicitly confirmed keeping the November initial addition and separate December cells; the strict entire-future-plan interpretation from the earlier audit is superseded by that clarification.

Bandwidth inference splits history at missing months or unmapped PRBs, then requires a sustained new mapped state across at least two consecutive calendar months. The effective date is the first positive-traffic month within that sustained state. confirmation_month is recorded separately and can be later than the effective month; confirmation_observation_months records its evidence, and confirmed_at records the earliest month boundary after the confirmation month, not an observed report-publication timestamp. Existing positive-traffic state is required to assert a change. One-month spikes are rejected and their return does not generate a phantom reverse event. Final unconfirmed runs are omitted. PRB mapping still uses inclusive +/-5 around 25/50/75/100 -> 5/10/15/20 MHz. No missing counter becomes zero.

Band events now group by site + technology + band, with frequency retained only as cell configuration. Multiple carriers in the same band are one band group; extra carriers in an already active band are CELL_ADDED. Monthly SITE > TECHNOLOGY > BAND > CELL suppression and exact-once assignment are preserved. Metadata explicitly says completion_scope=activation_month_cohort and later_additions=separate_monthly_actions. Band labels now include the band (e.g. L800_ADDED); bandwidth labels expose values and direction (e.g. bandwidth_5_to_20_upgrade). Canonical event_type enums remain the API/map filter keys. Popups and cluster rows expose the descriptive labels and bandwidth confirmation evidence.

CBR analog response horizons are now +1..+6, with three pre-event baseline months unchanged. Month 0 stays in charts/tables as observed partial-month context only: predicted level, impact and both interval bounds are NULL, analog count zero, effect_eligible=false. Both group and per-neighbor calculations enforce this; _predict_delta rejects offsets outside the full-month horizon. The frontend explicitly labels the partial event month, retains its marker, and explains that effect measurement starts the next month. A November activation remains November, with first complete effects in December. This change does not expand CBR's current site-launch analog pool to other action types.

Recomputed 3,737 active events: 20 sites, 332 technology additions, 986 band additions, 384 grouped cell additions, 1,882 bandwidth upgrades and 133 downgrades. All 8,511 added cells remain covered exactly once. Superseded detections are retained inactive; no schema/data-destructive migration occurred. Refreshed all 3,441 configuration summaries. Independent raw audit reports zero activation/group-date/metadata/duplicate mismatches; every one of the 2,015 bandwidth events has at least two consecutive mapped observations; no band event has an earlier active cell in its same technology/band; every band and bandwidth event has its specific label.

Checks actually completed so far: all 86 tests passed, Django check and migration consistency passed, frontend production build passed (existing large-bundle advisory). The independent network-event validator and current compliance audit passed. Live map/popup and CBR chart verification, and scoped user-profile refresh, are recorded in the final followup when complete. Evidence: docs/verification/network_events/validation.json and docs/verification/event_rule_compliance/2026-10-27-current.json. The pre-change 2026-10-27.json remains available as audit history.


2026-10-27 final sustained-event verification: scoped user-profile backfill completed for all 3,441 sites (3,260 supported, 181 unavailable, zero errors); all profile cutoff dates match current official event dates (zero mismatches). Live headless Edge passed all six event-class popups, positive/negative map filters, one icon per distinct site event type, specific band/from-to labels, sustained confirmation dates, 577 unique cluster timeline rows, and desktop/mobile displays with no page errors. CBR API and charts passed all 20 scope/KPI combinations (T1/T2/cluster/single neighbor x traffic/CQI/users/throughput/latency), with arrays and NULL gaps matching API output. Every month-0 row has no prediction/impact/interval and zero analog support; its observed value remains context. First complete effects start at +1.

Final checks: full 86-test suite, Django system check, migration consistency, independent 51,032-cell/3,737-event reconciliation, all 11 post-change compliance assertions, frontend production build and git diff --check passed. No migration was needed. Existing frontend bundle-size advisory remains. Evidence: docs/verification/event_rule_compliance/2026-10-27-current.json, docs/verification/network_events/validation.json and browser-report.json, docs/verification/biz_0033/report.json and docs/verification/user_context/backfill.json. Reproduce live browser checks with scripts/verify_event_rules_browser.py. The user's confirmed monthly grouping rule is implemented: November initial addition and separate December cells; future additions never postpone an initial launch.


### 2026-10-27 - Extended tiers and virtual noise-cluster audit / required pre-check

User requested a compliance check and pre-check before implementation. This turn performs a read-only audit and reference selection; application behaviour, stored cluster labels and schema were not modified.

Inventory discrepancy: 3,441 stored Site rows include 1,822 with cluster_id=-1. Grouping all current coordinates into connected components within 50 m gives 2,606 location groups. Exactly 987 groups contain only noise-labelled rows, matching the requested physical-noise count; another 712 location groups contain both a noise-labelled row and a real-cluster row. Thus a literal count of noise-labelled database rows differs from the 987 noise-only location groups. This identity/label issue must be addressed explicitly before enabling extended tiers for every raw cluster_id=-1 row. The diagnostic chooses the smallest numeric site ID as representative of each all-noise component and preserves all raw IDs/labels.

Pre-check reference: one nearest site per 30-degree true-north bearing bin, normalized and rounded to six decimals, floor(bearing/30)%12. Round-to-360 is normalized back to zero. Exclude self and distance<50 m; use actual distance<R for R=5/10 km. Distance ties are defined for this audit as nearest whole metre (floor(distance+0.5)), with smaller numeric site ID first. Maximum 12 members; 0 bins isolated, 1-2 low, 3+ ok. These reference calculations are audit outputs, not production virtual-cluster support. Boundary assertions verified exactly 30 degrees -> bin 1, wrap-around, metre ties, exclusion below 50 m, and strict exclusion at 10 km.

For the 987 noise-only location representatives:

| Candidate eligibility | Radius | 0 bins | 1-2 bins | 3+ bins | Median nearest selected member | Median of per-site member-distance medians |
|---|---|---:|---:|---:|---:|---:|
| Current inventory (spatial only) | <5 km | 502 (50.86%) | 340 (34.45%) | 145 (14.69%) | 2.859 km | 3.633 km |
| Current inventory (spatial only) | <10 km | 61 (6.18%) | 309 (31.31%) | 617 (62.51%) | 4.715 km | 7.076 km |
| Current positive-LTE baseline | <5 km | 507 (51.37%) | 336 (34.04%) | 144 (14.59%) | 2.859 km | 3.639 km |
| Current positive-LTE baseline | <10 km | 66 (6.69%) | 318 (32.22%) | 603 (61.09%) | 4.744 km | 7.080 km |
| Per-site event cutoff, or current scenario if undated | <5 km | 527 (53.39%) | 326 (33.03%) | 134 (13.58%) | 2.855 km | 3.629 km |
| Per-site event cutoff, or current scenario if undated | <10 km | 86 (8.71%) | 322 (32.62%) | 579 (58.66%) | 4.798 km | 7.094 km |

Distance medians exclude isolated cases. The JSON also contains pooled member medians, extrema, all per-site selected members and raw-row summaries for all 1,822 noise-labelled rows. Current LTE cutoff is 2026-10-01; positive traffic in any of July/August/September establishes eligibility. Per-site event-cutoff diagnostics rebuild the same baseline mask and exclude same-month known site launches. The diagnostic recent-launch flag uses first-positive LTE month as an explicitly labelled activation proxy; this is not proof of the first launch of other technologies. The reference pre-check does not compute or persist sampled traffic totals.

Compliance findings:
- Standard T1 <=2 km and T2 >2 to <=5 km are present in ANP, MAOS scopes and CBR. Stored non-noise cluster IDs supply real DBSCAN membership. Site cluster_id is preserved, including -1.
- Extended noise tiers (<5 km, 5-<10 km) are absent. All sites currently use the standard thresholds, and frontend scope labels are fixed to 0-2/2-5 km. The population catchments are also fixed at 2/5 km.
- No production virtual-cluster builder, V_<site_id> identity, <site_name>_vis_cluster name, nearest-per-bin sampling, support_level or isolation policy exists. ANP histogram bins describe all neighbors; they do not select one virtual member per bin. Co-located neighbors below 50 m are still allowed by existing neighbor paths.
- No Site fields tier_scheme, vis_members, vis_n_bins_filled, vis_n_members, vis_max_dist_m, vis_median_dist_m, vis_sampled_traffic_gb or support_level exist. Mean sampled traffic, complete traffic_all_sites_within_R, current-list labelling and historical-list provenance are absent.
- Historical context does rebuild three complete pre-event months and excludes the origin from neighbor scopes, but its eligibility uses positive traffic OR other KPIs, not strictly positive LTE DL traffic. No virtual membership, same-month launch guard for that membership or member_recent_launch flag is produced.
- Noise currently uses itself as a singleton in MAOS cluster scopes and cluster prelaunch baselines; CBR excludes the origin and therefore has no noise-cluster recipients. This is neither a real DBSCAN cluster nor the requested virtual sample; the two concepts need distinct API/UI fields.
- Neither original Gower retrieval nor PCA has tier_scheme in the registry or an unconditional scheme filter. A categorical penalty alone would not guarantee that standard/extended cases never compare; use a hard partition before hierarchy relaxation and PCA fitting to satisfy the requested guarantee.
- Separate event responses for 0-2, 2-5 and 5-10 km are absent; only current T1/T2 and cluster responses exist.

Evidence: scripts/audit_noise_virtual_clusters.py; docs/verification/noise_virtual_clusters/precheck-2026-10-27.json and precheck-2026-10-27.csv. Executed the full read-only pre-check with boundary/tie assertions and inspected model/schema, tier consumers, historical membership, Gower/PCA and frontend labels. No migration or production feature implementation is claimed by this audit. Recommended implementation order: resolve canonical location/cluster membership; add explicit standard/extended tier policy; implement event-safe virtual membership and traffic sample reporting; show an additive migration before applying; integrate current snapshots and per-event membership, hard similarity partitions and distance-band response reporting; then validate boundary/temporal behaviour and UI.


### 2026-10-27 - Implemented extended tiers and virtual traffic neighborhoods

This implementation supersedes the preceding read-only gap audit. Shared policy/calculation: services/models/features/neighborhood.py and config/neighborhood.json. The additive migration core/migrations/0012_site_neighborhood_context.py was shown before applying and is applied. Models hold schema only; services compute and persist the context.

**Physical identity and labels.** Retained all 3,441 raw Site rows and their cells/events. Reconciled 2,606 canonical location groups using the existing 50 m connected-component convention. A group with one real DBSCAN label propagates that label to its co-located source rows; conflicting real labels are rejected without mutation. The actual correction affected 756 noise-labelled source rows across 712 mixed groups. original_cluster_id preserves the prior label, and canonical_site_id exposes the location identity. Exactly 987 canonical locations remain noise, represented by 1,066 source rows; every genuine noise location keeps cluster_id=-1. No V_* label is stored as a DBSCAN cluster.

**Tiers.** standard: T1 50 m through 2 km inclusive, T2 >2 through 5 km inclusive. extended: T1 50 m through <5 km, T2 5 through <10 km. Under-50 m locations and the origin's canonical location are excluded from neighbor scopes. Real-cluster scope remains actual DBSCAN membership; noise has no real-cluster scope. Reporting adds separate 0-2, >2-<5 and 5-<10 km distance bands. Population catchments also follow the site's scheme (2/5 km or 5/10 km); 1 km population density and fixed-buffer road features keep their own explicit units/radii.

**Virtual selection.** For noise analyses, choose one eligible location per 30-degree true-north bearing bin within strict R<10 km, at most 12. Normalize bearing to [0,360), round to six decimals, normalize a rounded 360 back to zero, then floor(bearing/30)%12; exactly 30 goes to bin 1. Same-metre ties use nearest whole metre, floor(distance+0.5), followed by the smaller numeric site ID (lexical fallback for nonnumeric IDs). Keep actual unrounded distances for the radius and summary statistics. support_level: isolated for zero filled bins, low for one/two, ok for three or more. A nonempty sample has virtual_name=<site_name>_vis_cluster and virtual_id=V_<selected_site_id>, a per-analysis identity only.

**Time validity and flags.** Rebuild membership from strictly positive LTE DL traffic in any of the three complete months before the chosen event/scenario cutoff. Exclude the event's whole physical location and known same-month site launches. Current coordinates and DBSCAN membership retain the approved static-geography assumption. Known site launches within the baseline set member_recent_launch=true; known older launches set false. Unknown site-launch dates remain NULL, with first-positive LTE recency separately flagged as member_recent_lte_activation and labelled as a proxy. Future launch metadata cannot influence earlier membership/flags. Members retain raw site_ids for counter aggregation across aliases without counting a physical location twice.

**Traffic.** vis_sampled_traffic_gb is the previous complete month's summed DL bits /8e9 for selected locations, not an estimate of all demand. vis_mean_traffic_per_member_gb divides that sample by selected physical member count. traffic_all_sites_within_R separately sums all eligible locations in 10 km. If any fixed member lacks that month's traffic, the total/mean stay NULL; reported zero is preserved. Current-membership historical traffic charts apply the same complete-sample mask. Virtual scope exposes traffic only; it supplies no manufactured CQI, user, throughput or latency sample metric. T1/T2 and the separate distance bands continue to support the existing KPIs.

**Persistence.** Site now stores tier_scheme, canonical_site_id, original_cluster_id, vis_members (canonical/raw IDs, bin, distance, rounded bearing, tier, recency/source flags), vis_n_bins_filled, vis_n_members, vis_max_dist_m, vis_median_dist_m, vis_sampled_traffic_gb, vis_mean_traffic_per_member_gb, traffic_all_sites_within_R, support_level, vis_snapshot_cutoff and vis_snapshot_kind=current. The stored list is explicitly a current version. Historical event membership is rebuilt on request, never substituted with that list. Features only and Full sync refresh current snapshots; python manage.py refresh_neighborhoods performs the standalone snapshot/ANP/radius-context refresh.

**Similarity and PCA.** Added mandatory tier_scheme metadata to the registry: now 95 declared fields, 81 numeric /14 categorical. Its value is displayed but not weighted or deselectable. A hard partition runs before every hierarchy relaxation, original Gower retrieval and PCA fitting; even global fallback cannot cross standard/extended. Co-located aliases of the query are excluded from candidate retrieval. Virtual traffic/support fields remain analysis metadata, outside the distance. Scope labels and population radii are explicit in the picker, comparisons and explorer.

**Frontend / per-event use.** Added a Neighborhood tab showing current versus rebuilt event versions, membership table, virtual identity, support, sample/mean/full traffic and provenance. Any recorded event can be selected; GET /api/sites/<site_id>/neighborhood/?event_key=... (or as_of=YYYY-MM) rebuilds that analysis and validates site ownership/month syntax. CBR accepts event_key and exposes an event selector, so membership and outcomes can be rebuilt for later site actions. Its forecast analog pool still consists of historical site launches, with the existing temporal and minimum-support safeguards. CBR and monthly charts show scheme-aware tier labels, real versus virtual scopes, traffic-only virtual options and three distance bands. Data Explorer adds scheme filtering and origin-dependent tiers/virtual traffic scopes. The source-counter, ratio, NULL and month +1 rules are preserved.

**Final verification - 2026-10-27.** Refreshed all 3,441 current snapshots, ANP rows and persisted spatial rows, with zero refresh errors. Global nearest-eligible-site distance remains available beyond 10 km; empty tier distance statistics are exposed as NULL. All 3,441 user-context profiles were refreshed (3,354 supported, 87 unavailable, zero errors). Across 987 canonical noise locations: 603 have ok support, 318 low support, and 66 are isolated. Independent reference validation checked all 1,066 noise snapshot rows and 1,356 event cutoffs with zero mismatches. All 103 Django tests passed; system checks and migration consistency passed. The production frontend build passed (existing bundle-size advisory). Live browser checks passed for current/event membership, virtual MAOS traffic, mandatory scheme partitioning in original/PCA similarity, CBR distance bands, and Data Explorer; no page errors were recorded. The exercised standard PCA fit reduced 51 numeric inputs to 8 components retaining 90.37% variance, within its standard-only candidate pool. Some extended event queries have fewer than two compatible completed analogs; their forecasts remain unavailable with support reported.

Evidence: docs/verification/noise_virtual_clusters/browser-report.json and desktop/mobile screenshots, validation.json and backfill.json. The dated read-only pre-check above describes the former implementation and is superseded by this implementation and verification.

Evidence: docs/verification/noise_virtual_clusters/validation.json, backfill.json, and the retained pre-implementation precheck-2026-10-27.json/CSV. Reproduce independent validation with scripts/verify_virtual_neighborhoods.py through manage.py shell. Live workflow verification: scripts/verify_neighborhood_browser.py. The separate current snapshot and event cutoff must be retained when exporting or interpreting results.


### 2026-10-27 - Map links follow calculated tier and virtual membership

Replaced the map-only nearest-30 / 3 km heuristic with a service-owned current neighborhood projection at GET /api/sites/<site_id>/map-links/. Standard sites draw eligible canonical Tier 1 and Tier 2 neighbors (2/5 km). Noise sites draw only their at-most-12 selected virtual members, coloured by extended Tier 1 (<5 km) and Tier 2 (5-<10 km); their real cluster ID remains -1. Membership uses the same current cutoff, positive-LTE baseline, exclusion and bin/tie rules as the neighborhood panel. This map overlay is explicitly current, independent of a historical event selected in the panel.

Blue solid links show Tier 1 and orange dashed links Tier 2. The legend reports membership type, cutoff and count; tooltips include tier and distance. Coordinates come from the neighborhood service, so links also work when map search hides member markers. Closing selection clears links, and stale responses cannot overwrite newer selections or map refreshes. Failed loads show an unavailable message rather than reverting to approximate neighbors.

Validation: all 18 neighborhood tests and Django system checks passed, including API coverage of virtual-only versus full standard tier membership. Production frontend build passed with the existing bundle-size advisory. Live browser verification passed: MED_0007 (106008) rendered exactly 11 virtual links, GAB_0033 (105784) rendered exactly 4 standard tier links, closing selection cleared every link, and no page errors occurred. Evidence: docs/verification/noise_virtual_clusters/map-links-browser.json.


### 2026-10-27 - Similarity safeguards and recipient CBR experiments

- Made event type and tier scheme mandatory; added explicit technology/band relaxation control, frozen historical global P5-P95 reference tables and default 0.6 pre-renormalisation selected-weight guard. Added API/UI support, rejection and reference reporting; stabilised Gaussian normalisation.
- Exported 143,103 event-recipient cases across 3,737 events with strict baselines, NULLs, geometry/band/load context and +1..+6 outcomes. Added replayable build/reference/validation commands.
- Added nested chronological event-origin-grouped group/bandwidth calibration and offline RF-proximity/local-ridge comparisons. Initial sampled study (320 events/893 pairs) is mixed; live CBR remains Gaussian Gower. Detailed results: docs/verification/pair_cbr/README.md. No migration.
- Actual checks: 114 tests, Django system/migration checks, frontend build, full export structure/hash audit and 143 independent traffic arithmetic cases passed. Browser verification passed; see the final entry below.


Final live verification - 2026-10-27: browser checks passed for original-feature searches with relaxation on/off and for strict PCA. Each returned 10 cases matching the mandatory event type/scheme and >=0.6 available selected weight, with frozen reference df7aa5a2043bf2359d9e55ee reported. No page errors. Evidence: docs/verification/pair_cbr/browser.json and similarity-safeguards.png. The final frontend production build passed. Full tests: 114 passed; system and migration checks passed. The full pair export audit reports zero mismatches.


### 2026-10-27 - Live recipient CBR, controls, ramp and honest uncertainty

- Added recipient/event-specific CBR API and frontend engine with raw/control-adjusted/local-ridge methods and optional supported-horizon ramp; retained the legacy benchmark.
- Added strict three-month baselines, explicit median versus DiD mean semantics, frozen global pair ranges, event magnitude and affected-cell bandwidth band recovery.
- Added six-month matched controls, 10 km exposure exclusion with 5/10/15 km sensitivity, later-exposure censoring and pre-event-only control-growth forecasts.
- Added 500 correlated physical-origin bootstrap draws, separate gated prediction bands, complete-cohort aggregation and transparent support/control diagnostics.
- Rebuilt/audited all 143,103 pair cases: all 82,986 bandwidth rows have bands; zero audit mismatches. Actual checks: 125 tests, system/migration checks, frontend build and live browser workflows pass. A rolling 260-event study is recorded under docs/verification/recipient_cbr/. No database migration or destructive change.


Final recipient-CBR evidence - 2026-10-27: 260 recorded events/260 sampled recipients, five KPIs and six horizons were evaluated with rolling cutoff/origin purging, 500 physical-origin bootstrap draws and recipient-disjoint baseline sensitivity. Saved 1,277 event-type/scheme/horizon matched-case comparisons. At +1, raw Gaussian CBR supported 175/253 observed cases (69.2%); control-adjusted traffic supported 75/253 (29.6%). On those same 75 cases, traffic MAE improved from 2,885.424 to 2,795.980 GB/month (~3.1%); user/CQI/throughput/latency comparisons did not improve consistently. Raw Gaussian remains the reference; local/control/ramp alternatives are selectable, not assumed superior. Control match feasibility at 5/10/15 km was 1,055/1,049/1,036 of 1,300 KPI-recipient combinations, distinct from clean-analog forecast availability.

The calibrated prediction-band audit found 0/1,277 checked historical method/KPI/horizon/type/scheme configurations ready: 1,202 lacked 20 prior independent calibration origins; 75 lacked the required later prior-time coverage checks (at most two checks available versus ten required). This is a validation-support limitation, not evidence of nominal 95% coverage. Those prediction bands remain NULL. Conditional mean-bootstrap intervals are a separate displayed quantity. Scope-total prediction bands have no calibration and remain unavailable. Real-cluster members beyond the trained 5/10 km radii also remain unsupported instead of being extrapolated or omitted from a purported complete total.

Actual engineering checks: all 125 Django tests passed, system check passed, no pending model migrations, full export structure/hash and 143 independent traffic arithmetic audits passed, production build passed (existing bundle-size advisory). Live desktop checks passed for raw/ramp/control methods, explicit unavailable support, interval separation and noise virtual traffic-only selection without page errors. Final responsive checks passed at 390 px after the chart resized; evidence is recorded in docs/verification/recipient_cbr/browser.json and recipient-mobile.png. Detailed formulas, matched-case errors, control sensitivity, limitations and replay commands: docs/verification/recipient_cbr/README.md, validation.json, stratified-comparisons.json and interval-readiness.json. The new dataset/reference/calibration are derived files; no destructive migration or new external download was needed.


### 2026-10-27 - Accuracy audit and BAR_0196 ramp diagnosis

Added a reproducible saved-rolling-forecast audit against three-month median, last-month persistence, six-month linear trend and prior-year seasonal baselines. Comparisons use common cases and pre-event inputs; report MAE/RMSE, event-macro MAE, WAPE, bias and largest misses. New command: python manage.py audit_cbr_accuracy. Artifacts: docs/verification/recipient_cbr/accuracy-audit.json/.md and version/dataset-linked data/calibration/recipient_accuracy.json.

BAR_0196 (1002): audited the September 2025 4G_ADDED event and all six smoothed Tier-1 neighboring-site traffic totals. December observed 165,719.6 GB versus 136,255.4 GB predicted: 17.8% error using observations, 21.6% relative to prediction. Six-month MAPE is about 13.0% versus 6.6% for last-month persistence (147,584.2 GB). The October 2025 three cell bandwidth upgrades are later co-interventions; causal attribution to the September action is not established. Current event detections also contain 639 physical-site/month groups with multiple actions (2,141 of 3,737 raw events), motivating episode-level prediction labels without deleting raw records or merging separate months.

Across the 175 same +1 traffic validation cases, raw CBR MAE is 31.6% higher than last-month persistence. Advanced method tests and passing software checks do not establish forecast skill. Production prediction values/weights are unchanged by this accuracy investigation. The frontend/API now expose the last-month benchmark, predicted/observed changes, absolute percentage error with observed denominator, and retrospective same-site concurrent/later actions. Zero observations retain absolute errors; percentage error stays NULL for a zero denominator. Diagnostic post-event information never enters prediction inputs. Observed changes are not labelled causal impacts.

The next numerical revision should separate background demand from event residuals, test relative-load/capacity transfer, and model simultaneous actions as analysis episodes. Evaluate on chronological site-grouped holdouts before promoting it; do not tune against BAR_0196's future observations. Full case evidence: docs/verification/recipient_cbr/BAR_0196-accuracy.md. Targeted baseline/date/zero/exposure tests actually passed (14 recipient tests); final checks and browser evidence are recorded below when executed.


Accuracy-diagnostic verification - 2026-10-27: all 128 Django tests passed; system and migration checks passed; frontend production build passed with the existing bundle advisory. Live BAR_0196 desktop/mobile checks verified all six ramp forecasts stayed numerically unchanged, the last-month benchmark and error/change columns rendered, October's three later bandwidth actions were visible, and no page errors occurred. Evidence: docs/verification/recipient_cbr/accuracy-browser.json and BAR_0196-accuracy-ui.png. These are verified diagnostics, not a numerical accuracy improvement. The audit confirms a required model revision; no weights were tuned to BAR_0196's observed outcomes.


### 2026-10-27 - Workspace analysis templates and physical-site/month episodes

Administration is a configuration/templates page in the existing trusted workspace. There is no sign-in or account administration. Shared profiles and workspace defaults persist in Django; personal profiles/defaults use an opaque server-owned browser session (365-day cookie). Clearing cookies loses personal access; JSON export/import supports moving a preset. Shared templates are collaboratively editable, not staff-authorised resources. Writes require CSRF. Profile fields and calculations are validated in services/analysis_profiles.py; models are schema and views delegate.

Profiles store purpose (similarity/prediction/both), event type, standard/extended scheme, technology, original site-feature mask, separate nine-field recipient mask, original/PCA representation, PCA retained variance, weighting mode, minimum available-weight share (>=0.6), technology/band relaxation, prediction method, scope and ramp. Personal defaults precede workspace defaults; within a scope, specific matching scenarios precede ANY. Defaults are purpose-specific. Explicit incompatible profiles fail. Manual bypasses defaults. Save creates an immutable revision; stale updates return 409. Archive preserves history and removes a profile from default resolution. Default scenario/purpose assignments must be cleared before changing them. Visibility changes require a new copy.

Saved-profile site Gower uses selected fields only, including equal-per-feature mode; the existing manual fallback remains for compatibility. Recipient masks change actual pair Gower and local-ridge inputs. Missing dimensions are skipped and zero stays zero. Mandatory event/scheme partitions, chronological eligibility, global frozen ranges and the 5% site-road cap remain. PCA uses selected original sources and a query-specific candidate-only fit; presets save original inputs/variance, not PC numbers. PCA applies to exploratory site retrieval; recipient predictions use their separate nine pair dimensions. Custom profile forecasts require profile-specific prediction-interval calibration; raw-model accuracy reports are not presented as custom-profile validation.

Step 1 creates versioned AnalysisEpisode / AnalysisEpisodeMember records from canonical physical site + effective calendar month. Same-month actions form one analysis unit; separate months never merge. Homogeneous actions keep their type; mixed actions use COMPOUND_EVENT and an action-type signature. Raw detector records, strict KPI activation dates, per-cell activation months, old/new bandwidth and raw action snapshots are retained. Rebuilds preserve inactive episode versions. Addition-cell counts and bandwidth transitions are deduplicated for magnitude calculation; missing PRBs keep the aggregate NULL. Noise sites keep cluster_id=-1.

Backfill actually run: 3,737 current raw events -> 2,235 current episodes; 639 have multiple actions, containing 2,141 raw events. Types: 861 frequency-band, 592 bandwidth upgrades, 329 technology, 325 cell, 18 site, 64 compound, 46 bandwidth downgrades. BAR_0196 September 2025 technology and October 2025 three bandwidth actions remain two episodes. Episode rebuilding is included after event detection. The prediction UI exposes raw-event benchmark and experimental grouped site/month choices, with original action details.

The separate episode export was built using `python manage.py build_pair_cases --episodes`: data/calibration/episode_recipient_cases.jsonl, 82,123 episode-recipient rows, 2,235 episodes, latest complete month 2026-09. SHA256 ba7ff676934355c08367d220e3d1c295faffa2c53be145f7ee484c6b2b49edf8. Separate frozen reference recipient_episode_reference.json, ID 6318d2c850865098d0788c86. Event and episode datasets/ranges are never mixed; compound signatures are mandatory compatibility. The old raw-event dataset/reference and default analysis unit remain available. Episode/profile changes invalidate reuse of previous individual prediction-interval calibration. No accuracy improvement or causal gain is claimed from grouping alone.

Non-destructive migrations 0013/0014 (profiles/browser ownership) and 0015 (episodes) were displayed before application and applied. No raw data was deleted. Configuration and episode services have targeted tests; final executed verification is recorded separately below. The remaining model work is counterfactual background demand, the event site's own response, and additive monthly/cumulative gain with chronological validation; these are not yet implemented by this step.


Verification/performance follow-up - 2026-10-27: cold profile requests exposed two existing extraction bottlenecks. Positive-traffic history now clears implicit model ordering before DISTINCT so the database returns unique site/month pairs; Python eligibility sets and event timing are unchanged. Population pixel intersections now assign exact full-cell areas to contained pixels and perform polygon overlay only on boundary pixels, using prepared catchments. A circle/ring synthetic comparison against full exact overlay passed at 1e-12 tolerance. Browser-session bootstrap requests are coalesced to avoid competing initial sessions; open profile pickers reload after template/default saves. A technology-specific scenario uses the recorded event technologies, including bandwidth events whose tech_added feature is NULL. The targeted profile/neighbourhood/population tests actually passed. Final suite/build/browser results follow once executed.


Executed verification - 2026-10-27: all 149 Django tests passed; system checks and migration consistency passed. The explicit recipient equal-per-group mode divides each group among common selected dimensions after checking coverage against the query's original budget; the unset legacy raw-model configuration is unchanged. A dedicated test verifies a group with one surviving field retains its group share. The browser workflow actually passed preset creation, personal default resolution, ten site-similarity matches scored only on n_sites_1km/n_sites_2km (normalised weights sum to one), recipient prediction scored only on distance_m, BAR_0196 October's three actions represented by one available episode forecast using the separate reference, revision saves, archive, and mobile configuration rendering. No page errors occurred. Evidence: docs/verification/analysis_profiles/browser.json and configuration-mobile.png; script scripts/verify_analysis_profiles_browser.py. Feature checklist initialisation and event metadata now use separate request counters so switching analysis units cannot cancel its own event list. Accessible labels were added to the profile/template selectors. Browser checks establish functional integration, not forecast accuracy or causal identification. Final frontend build result is recorded below.


Final build - 2026-10-27: frontend production build passed (102 modules; existing >500 kB bundle-size advisory). The final 149-test backend suite, migration consistency, system check and complete browser workflow all passed. The backend was restarted with the completed implementation. Episode mode remains an explicit experimental choice; individual/profile/episode prediction intervals require new calibration, and counterfactual/cumulative gain remains the next planned modelling step.
