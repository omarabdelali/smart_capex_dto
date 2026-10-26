# Smart CAPEX Specification Changelog v1.0

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
