# Smart CAPEX Specification v1.0

Current policy (2026-10-26): static geography/population, KPI-projected after configuration, PRB capacity and previous-month cluster KPIs are authoritative; see the latest approved-context section. Registry: 94 fields (81 numeric, 13 categorical). Earlier timing-exclusion policies/counts below are historical milestones.

## Scoped edge and low-latency users (2026-10-26)

- Import nullable `L.Traffic.User.BorderUE.Avg`, `L.Traffic.User.BorderUE.Max` and `L.Traffic.User.LowLatency.Avg` alongside existing `L.Traffic.User.Avg`. Additive migration 0008 adds raw fields and persisted `UserContextFeatures`.
- For T1 (0-2 km), T2 (2-5 km annulus) and total cluster calculate `edge_user_share = sum(BorderUE.Avg)/sum(User.Avg)`, `edge_user_peak_ratio = sum(BorderUE.Max)/sum(BorderUE.Avg)`, and `lowlatency_user_share = sum(LowLatency.Avg)/sum(User.Avg)`. Use paired nonmissing nonnegative input rows for each ratio; omit missing pairs from both sums. Zero denominator stays NULL; real zero numerator with positive denominator stays zero.
- Persist nine `tier1_`, `tier2_`, `cluster_` dimensions, a first-of-month cutoff and support/reasons. Pool source components across the three complete pre-cutoff months, then divide once; do not average cell/month ratios. Tiers exclude origin; full cluster includes it, with noise sites independent. Historical membership comes from pre-event LTE evidence; monthly descriptive charts use current map membership.
- Add the `user_context` similarity group, pairwise missing-value handling and explicit selection behavior for these new dimensions. Canonical registry is now **89 scalar dimensions: 77 numeric, 12 categorical**. Existing predicted CBR outcome targets remain unchanged.
- KPIs & Config displays the 3-by-3 scope table. Monthly MAOS Counters exposes all three metrics and site/T1/T2/cluster/compare-scopes/cell selectors. Dedicated cluster analysis also exposes the ratios. Retain null chart gaps and nonzero small-number precision; source zero must not become unavailable.
- Targeted import updated new raw counters without changing unrelated KPIs. Recalculation processed all 3,441 profiles: 3,318 with at least one available value, 123 without eligible data, no errors. Missing-data audit and browser evidence are in `docs/verification/user_context/`.

Documentation reconciliation (2026-10-26): `feature_eng.md` is the current calculation reference. The scoped-user extension brings the registry to 89 dimensions; earlier 80-dimension and older feature-count entries below describe preceding implementation milestones.

## Persisted road feature group (2026-10-26)

- Canonical scalar similarity schema: **80 dimensions, 68 numeric and 12 categorical**, including seven road dimensions. Earlier 55/56/60 feature counts are historical design counts, not the current implemented scalar registry.
- Persist six nullable numeric road measurements and categorical dominant class in `RoadFeatures`: total/weighted length, weighted density, motorway+trunk length/share, and estimated degree≥3 junction count. Use a 1 km UTM 32N buffer, configured class priors, spatial index and clipped line overlay. Keep any-class 5 km source coverage evidence separate from retained-class measurement.
- With no source road within 5 km, measurements stay NULL. With coverage evidence and no retained roads inside 1 km, zero lengths/counts are valid; share and dominant class remain NULL.
- Keep source/hash/buffer/extract-date/method/weight versions and class lengths. Exact original OSM-node degree is unavailable from the free line extract; label the grade-aware geometry count as a junction estimate.
- Both feature sync modes recompute roads. Provide a Roads inspector tab with values, bars, source attribution and limitations; include the group in similarity picker/comparisons and dimensions-used reports.
- Roads default off, require explicit opt-in and compatible provenance, and have a configured uncalibrated 5% group cap. Support API/picker `equal_per_feature` (default, legacy non-road behavior retained) and `equal_per_group`; show actual normalized pairwise weights.
- Archive README and source hash establish extract date 2026-10-22. Do not assign this later snapshot to earlier CBR events. Current-context retrieval is exploratory. Predictive ablation remains blocked pending earlier snapshots; diagnostics do not establish prediction accuracy or justify default-on.

## Latest population coverage and CBR cohort rules (2026-10-26)

These rules supersede earlier coverage suppression and cohort aggregation text below.

- Population belongs in a separate site-inspector tab, not Overview. Show 1 km density and T1/T2 mapped counts, units, source epoch and land/water coverage.
- Return calculated sums from valid population cells even under partial coverage, labeled **partial mapped estimates**, without extrapolating missing land. Density uses full geometric catchment area. Independently classify water with WorldCover; at least 90% overall and land coverage gives complete status, not a prerequisite for displaying a supported count. Entirely unknown land remains unavailable.
- Expose population coverage/status in API metadata and similarity/CBR UI. Partial mapped inputs may understate full catchment population; source-epoch eligibility is unchanged.
- CBR additive baselines are sums of recipient medians; nonadditive baselines and observations are means of site KPIs, consistent with predicted mean site changes. Use a fixed baseline-eligible cohort and omit incomplete observed totals.
- Bound absolute predictions/intervals at zero, and CQI at 15. Show actual null gaps, a bootstrap confidence band and monthly analog/cohort support; do not connect unsupported horizons.

## Tier population and historical snapshots (2026-10-26)

- Add `population_tier1` (people in 0–2 km disk) and `population_tier2` (people in separate 2–5 km ring), using fractional overlap of the existing 100 m GHSL source. Require 90% valid coverage independently. Retain 1 km density; expose all fields and units in feature selection, comparisons, site inspector and CBR UI.
- Exclude epoch-2025 population before 2025. Mark unsupported event-time configuration/building/clutter and undated legacy values missing instead of reusing current measurements.
- Use three complete calendar months before event-month start; completeness includes calendar gaps. Reconstruct spatial, ANP and cluster context using pre-event LTE activity, with stable coordinates/terrain as explicit assumptions. No current cluster IDs contribute to distance.
- For CBR, analog launch and completed outcome month must precede the query event month. Require two available outcomes per metric/horizon; later query observations are display-only. Reconstruct cluster recipients from pre-event activity.
- Preserve existing deselected-feature behavior until production. Full formulas, limitations and validation are in `feature_eng.md`.

## Population context (2026-10-26)

- Preserve deselected features and existing calculation behavior until production; defer the audit's selected-feature correction.
- Offer an optional Tunisia population-density map overlay, independent opacity and density legend, using existing GHSL GHS-POP R2023A epoch-2025 **100 m** cells. User selected native 100 m with detailed zoom; do not label zoomed pixels as 10 m population precision.
- Include `population_density_1km_per_km2` in the numeric similarity schema and CBR ranking. In a locally constructed 1 km circle, sum native population counts apportioned by fractional cell overlap, then divide by valid overlap area in km². Require at least 90% valid coverage; missing remains missing and observed zero remains zero.
- Use existing robust numeric scaling and requested per-feature weighting. Show population under a separate source-labeled feature group. Population is static 2025 context for historical cases, not reconstructed event-time population.
- Serve population PNG tiles at `/api/population/tiles/{z}/{x}/{y}.png`; retain native values at detailed zoom and source attribution.

## Version History

- **v1.0 (2026-10-24)**: Updated specification reflecting requirement changes:
  - Excluded building_height feature from Phase 1 (56→55 features total)
  - Fixed alpha shape parameter at 0.05 for cluster polygon generation
  - Added cluster_id, is_cluster_edge, out_of_bounds fields to Site model
  - Clarified noise point handling: cluster_id=-1 assigned per site (not shared)
  - Added Tunisia boundary validation requirement
  - Specified 50m deduplication threshold for sites
  - Updated cluster feature computation requirements
- **Configuration clarification (2026-10-25)**: Defined pre-event technology status from nonzero MAOS history, current-plan after status, event classification, and unavailable historical band/capacity values.
- **UX clarification (2026-10-25)**: Site feature inspection uses a resizable docked panel on wide screens and a bottom sheet on mobile, keeping map selection and neighbor links visible.
- **Cluster analysis clarification (2026-10-25)**: Add a cluster analysis page with cluster context, monthly aggregated MAOS KPIs, and a complete event list; event months are marked on the KPI timeline.
- **LTE KPI analysis confirmation (2026-10-25)**: Extend cell, site, and cluster analysis with report-supported monthly LTE traffic, load, CQI, throughput, delay, and availability. Preserve aggregation denominators and missing values for reliable similarity inputs.
- **Feature synchronization clarification (2026-10-25)**: Add Features only and Full sync actions, persisted background job status/progress, and full sync addition redetection followed by feature recomputation.
- **Similarity inspection clarification (2026-10-25)**: Use all declared mixed similarity dimensions, show unavailable query/case values in red, and focus the map on a selected query plus its retrieved cases.

- **v0 (2026-10-23)**: Initial specification draft

---

## 1. Project Overview

Smart CAPEX is a case-based reasoning (CBR) system for predicting the impact of new telecom network sites on existing site performance. Phase 1 focuses on 2G/3G/4G networks in Tunisia using site-level predictions with **55 features** per site.

### Key Innovation
**Angular Neighborhood Profile (ANP)**: A novel 15-feature representation using 360° rotation analysis to classify sites as edge vs infill locations, critical for accurate impact prediction.

---

## 2. System Architecture

### Technology Stack
- **Backend**: Django 4.2+ with PostgreSQL/PostGIS (or SQLite/SpatiaLite for development)
- **Data Processing**: Polars, NumPy, GeoPandas, Rasterio
- **Machine Learning**: Scikit-learn (DBSCAN, utilities)
- **Geospatial**: Shapely, PyProj, Geopy
- **Visualization**: Folium (interactive maps), Matplotlib
- **Clustering**: Alphashape (concave hulls with α=0.05)

### MVC Architecture
```
project_smart_capex/
├── src/
│   ├── models/              # Data processing & ML logic
│   │   ├── preprocessing/   # Data loaders, clustering
│   │   ├── features/        # Feature extraction (ANP, etc.)
│   │   ├── similarity/      # Gower distance, filtering
│   │   └── prediction/      # CBR prediction logic
│   ├── views/               # Visualization & API responses
│   │   ├── geo_visualization/  # Folium maps
│   │   └── api_responses/
│   └── controllers/         # Workflow orchestration
│       ├── data_pipeline/
│       └── prediction_api/
├── core/                    # Django models
├── data/                    # Data storage
├── spec/                    # Documentation
└── tests/                   # Test suite
```

---

## 3. Feature Set (55 Features Total)

### 3.1 Configuration Features (10 features)
Configuration is summarized from the current plan. Operational additions use the
first month with strictly positive cell DL traffic, never a zero or missing
month. A complete group becomes effective at the latest first-positive month
among all required cells. Dates are month starts, not inferred exact days.

1. `event_type`: Apply `SITE_ADDED` > `TECHNOLOGY_ADDED` >
   `FREQUENCY_BAND_ADDED` > `CELL_ADDED`, consuming each added cell once.
   Apply precedence within each activation-month action, using earlier active
   cells as context. Future additions never merge into an earlier action.
   LTE PRB changes produce separate `BANDWIDTH_UPGRADE`/`BANDWIDTH_DOWNGRADE`
   events on the same cell identity, effective only with positive traffic.
   Cells already positive at dataset start are baseline/left-censored.
2. `tech_added`: The sole newly serving technology (2G/3G/4G), when exactly
   one can be identified; blank for multiple or no technologies.
3. `tech_before`: Binary vector `[has_2g, has_3g, has_4g]`, true only when a
   pre-event MAOS record for that technology has strictly positive DL traffic.
   Zero or missing traffic does not count as prior service.
4. `tech_after`: Binary vector `[has_2g, has_3g, has_4g]` from technologies
   present in the current cell plan.
5. `bands_added`: Bands in the primary traffic-confirmed frequency-band event.
   This uses current-plan membership, not a dated historical configuration delta.
6. `sector_count_after`: Number of distinct azimuth directions in the current
   plan; azimuths are grouped to the nearest 5 degrees.
7. `cells_per_sector_after`: Current cell count divided by sector count.
8. `antenna_height_m`: Mean antenna height across current cell-plan rows.
9. `total_bw_after_mhz`: Sum of configured bandwidth across current cell-plan
   rows.
10. `total_capacity_after_mbps`: Reserved theoretical capacity value. Store
    zero until a documented capacity formula and its required spectral
    efficiency/vendor inputs are available; do not present zero as measured
    capacity.

The current cell plan describes the after state only. Exact historical bands,
capacity changes, and sunset events require dated cell-plan snapshots or an
event ledger. Missing history must not be inferred from the present plan.

### 3.2 Geometric Features (4 features)
DEM-derived terrain characteristics:
11. `z_antenna_m`: Antenna elevation above sea level (30-200m)
12. `terrain_slope_deg`: Median slope in 200m buffer (0-25°)
13. `terrain_roughness_m`: Elevation std dev in 1km buffer (0-40m)
14. `terrain_aspect_deg`: Dominant slope direction (0-360°)

**NOTE**: `building_height` feature **excluded** from Phase 1 (was feature 15 in v0).

### 3.3 Clutter/Topology Features (4 features)
Land cover and building characteristics:
15. `dominant_clutter`: Categorical (urban/suburban/rural/water/forest)
16. `clutter_entropy_2km`: Land use diversity (0-1.5)
17. `pct_building_area_1km`: Building coverage percentage (0-90%)
18. `avg_building_height_m`: Average building height from GHSL (0-40m)

### 3.4 Spatial Context - Legacy Features (8 features)
Traditional neighbor analysis:
19. `dist_nearest_site_m`: Distance to nearest site (50-2950m)
20. `n_sites_1km`: Site count within 1km (0-10)
21. `n_sites_2km`: Site count within 2km (0-25)
22. `n_sites_3km`: Site count within 3km (0-50)
23. `n_2g_sites_2km`: 2G sites within 2km
24. `n_3g_sites_2km`: 3G sites within 2km
25. `n_4g_sites_2km`: 4G sites within 2km
26. `neighbor_avg_antenna_height_m`: Mean antenna height of neighbors

### 3.5 Angular Neighborhood Profile - ANP (15 features)
**Key Innovation**: 360° rotation analysis for edge/infill classification:

27. `n_tier1`: Neighbors within 2km (0-25)
28. `n_tier2`: Neighbors 2-5km (0-100)
29. `t1_to_t2_ratio`: Tier1/Tier2 ratio (0-5)
30. `t1_nearest_m`: Nearest neighbor in tier1 (50-2000m)
31. `t2_nearest_m`: Nearest neighbor in tier2 (2000-5000m)
32. `angular_uniformity`: Angular distribution uniformity (0-1)
33. `max_empty_arc_deg`: Largest gap with no neighbors (0-360°)
34. `n_empty_bins`: Empty 30° bins out of 12 (0-12)
35. `dominant_sector_deg`: Bin with most neighbors (0-330°)
36. `dominant_sector_count`: Neighbors in dominant sector (0-15)
37. `edge_score`: **Composite edge/infill score (0-1, higher=edge)**
38. `bearing_stddev_deg`: Angular spread of tier1 neighbors (0-180°)
39. `avg_neighbor_dist_t1_m`: Mean distance to tier1 neighbors
40. `avg_neighbor_dist_t2_m`: Mean distance to tier2 neighbors
41. `coverage_asymmetry`: Quadrant density difference (0-1)

### 3.6 Pre-Launch KPI Features (9 features)
Computed from MAOS data 30 days before launch:
42. `avg_traffic_dl_gb`: Average downlink traffic
43. `avg_traffic_ul_gb`: Average uplink traffic
44. `avg_users`: Average connected users
45. `avg_prb_util_pct`: PRB utilization percentage
46. `peak_hour_traffic_gb`: Peak hour traffic
47. `peak_hour_users`: Peak hour user count
48. `avg_cqi`: Channel Quality Indicator
49. `avg_rsrp_dbm`: Reference Signal Received Power
50. `congestion_hours_per_day`: Hours with >80% PRB util

### 3.7 Cluster Context Features (6 features)
Neighborhood cluster characteristics:
51. `cluster_id`: Cluster ID from DBSCAN (-1 for noise/single-site)
52. `cluster_size`: Number of sites in cluster (1-50)
53. `cluster_density_sites_per_km2`: Spatial density (0-20)
54. `cluster_avg_traffic_gb`: Mean traffic across cluster
55. `cluster_avg_users`: Mean users across cluster
56. `dist_to_cluster_centroid_m`: Distance to cluster center (0-5000m)

**Total: 55 features** (10 + 4 + 4 + 8 + 15 + 9 + 6 - 1 excluded)

---

## 4. Site Clustering Module

### 4.1 Deduplication
**Requirement**: Remove duplicate sites within 50m proximity.
- **Method**: DBSCAN with eps=50m, min_samples=1
- **Priority**: Keep first occurrence when duplicates found
- **Purpose**: Clean cell plan data where multiple cells map to same physical location

### 4.2 Spatial Clustering
**Algorithm**: DBSCAN with haversine distance metric

**Parameters**:
- `eps`: 2.0 km (maximum distance between neighbors)
- `min_samples`: 3 (minimum sites to form dense cluster)
- **Distance metric**: Haversine (accounts for Earth curvature)

**Noise Point Handling**:
- DBSCAN labels noise points as -1
- **Each noise point gets cluster_id=-1** (not shared between sites)
- Noise points treated as single-site clusters for feature computation
- Noise points considered "edge" sites by default

### 4.3 Cluster Polygon Generation
**Method**: Alpha shapes for concave hull boundaries

**Parameters**:
- **α (alpha): 0.05** (FIXED per specification)
- Purpose: Create tighter boundaries than convex hull
- Fallback: Use convex hull if alpha shape fails

**Special Cases**:
- Single-site clusters: 100m circular buffer
- Two-site clusters: Line with 100m buffer
- Multi-site clusters: Alpha shape with α=0.05

### 4.4 Edge Site Identification
**Definition**: Site is "edge" if close to cluster polygon boundary

**Criteria**:
- Distance to polygon boundary < 111m (≈0.001° at Tunisia latitude)
- Noise points always classified as edge sites
- Interior sites: Well within cluster polygon

### 4.5 Tunisia Boundary Validation
**Requirement**: Validate all sites are within Tunisia geographic boundaries

**Bounding Box** (simplified validation):
- Latitude: 30.2°N to 37.5°N
- Longitude: 7.5°E to 11.6°E

**Production**: Use detailed Tunisia polygon from Natural Earth or OSM

**Site Model Fields**:
- `out_of_bounds`: Boolean field (True if outside Tunisia)
- Out-of-bounds sites highlighted in red on maps

### 4.6 Cluster Feature Computation
For each site, compute 6 cluster-level features:

1. **cluster_id**: ID from DBSCAN (-1 for noise)
2. **cluster_size**: Number of sites in same cluster
3. **cluster_density_sites_per_km2**: Sites per km² in polygon area
4. **cluster_avg_traffic_gb**: Mean traffic across all cluster sites
5. **cluster_avg_users**: Mean users across all cluster sites
6. **dist_to_cluster_centroid_m**: Distance to cluster geographic center

**Area Calculation**:
- Convert polygon area from deg² to km²
- Tunisia latitude ≈35°: 1° ≈ 111km (lat) × 91km (lon)

---

## 5. Data Sources

### 5.1 Cell Plan Data
- **Source**: Excel file with cell-level configuration
- **Format**: One row per cell (site_id, cell_id, lat/lon, technology, etc.)
- **Aggregation**: Cells grouped by site_id to create Site objects
- **Deduplication**: 50m threshold applied after aggregation

### 5.2 MAOS KPI Data
- **Source**: Huawei MAOS monthly counters
- **Format**: CSV/Excel with monthly aggregates per cell
- **Key Counters**: Traffic (DL/UL), Users, PRB util, CQI, RSRP
- **Launch Detection**: Strictly positive DL traffic is required. The first collected month is a left-censored baseline; positive traffic there does not establish a new addition.

#### Radio Network Event Detection
- For every cell retain `effective_activation_month = MIN(month WHERE thrp_bits_dl > 0)`. Missing records/counters are unknown, never zero.
- A zero October followed by positive November is effective in November. Nontraffic KPIs cannot confirm activation.
- Complete-group precedence: site, technology, frequency band, cell. Each added cell appears in one addition event only; bandwidth changes are independent events, not duplicate additions.
- Activation month defines the action boundary because there are no rollout/batch IDs. Apply the hierarchy separately per month. Site creation suppresses its same-month child additions; a later new technology is a separate action. A technology addition suppresses its same-month bands/cells; later additions to that technology remain separate band/cell actions. Retain all member activation dates and use the maximum within the action. Do not combine independent months into one lifetime group.
- Technology labels include `4G_ADDED` and, when completed together, `2G/3G_ADDED`; canonical type is `TECHNOLOGY_ADDED`.
- Band membership is scoped by site, technology, band label and frequency to distinguish source-plan carriers. An incomplete or unobserved group cannot be classified as complete.
- LTE available PRBs map to MHz as 25->5, 50->10, 75->15, 100->20 with inclusive +/-5 tolerance. Values outside these disjoint windows are unknown, not rounded arbitrarily.
- A change requires adjacent valid monthly PRB evidence, an already traffic-active cell at the old bandwidth, and positive traffic at the new bandwidth. Zero-traffic changed-PRB months remain pending until positive traffic at that bandwidth. Missing/unmapped PRB months break exact transition dating; observable jumps across gaps are counted and excluded.
- Store previous/new bandwidth, direction, first changed-PRB observation, per-cell activation dates, detector version and source basis. Historical configuration dates remain NULL: monthly PRBs are operational inference, and the plan is only a current snapshot.
- The map filter, popup and cluster timeline share persisted events. Whole-group events appear once. Popups distinguish cell activation from group completion and show bandwidth values. Detection updates existing cell/site launch fields to effective months and retains superseded event records as inactive.
- Current imported MAOS reports are LTE-only; 2G and 3G events require corresponding MAOS history.

### 5.3 Geographic Data
All data already available in `data/geographic/`:
- **DEM**: Copernicus 30m resolution
- **Land Cover**: ESA WorldCover 10m (2020/2021)
- **Buildings**: OSM building footprints
- **Building Heights**: GHSL Built-C R2022 (composite raster)

---

## 6. Similarity-Based Prediction

### 6.1 Gower Distance
Mixed data type distance metric for numeric + categorical features:
```
d_Gower(x, y) = Σ w_i * δ_i(x_i, y_i) / Σ w_i
```

Where:
- δ_i = |x_i - y_i| / range_i for numeric features
- δ_i = 0 if x_i == y_i, 1 otherwise for categorical
- w_i = feature weights (from config)

### 6.2 Hierarchical Filtering
Gower numeric ranges are fitted to the candidate pool using the 5th and 95th percentiles; numeric distances are clipped to [0,1]. Missing feature values are omitted from both weighted sums, and identifiers/profile metadata are excluded.

The current ranker matches event type, then technology, then a minimum 50% Jaccard overlap of added bands when dated band data is available. It relaxes the band filter, then technology, when fewer than three candidates remain, falling back to all cases when event matches are insufficient.

### 6.3 Kernel Weights
Gaussian kernel for distance-based weighting:
```
w(d) = exp(-d² / (2σ²))
```
Where σ = bandwidth parameter (tuned via validation)

### 6.4 Prediction Output
For each target site, provide:
- Top-K similar cases (K=10-20)
- CBR-estimated receiver-site KPI changes for downlink traffic, RSRP, CQI, RRC users, active users, user throughput, and latency when those measurements are available.
- Bootstrap confidence intervals (95%)
- Local linear model coefficients
- Feature importance for explanation

### 6.5 LTE Pre-Event Similarity Profile
- Build an as-of-date vector from persisted configuration, geometry, clutter, spatial, ANP, and cluster context plus the three latest valid pre-event LTE months.
- Use the median of available monthly DL traffic/day, active/traffic users, weighted DL PRB, weighted CQI, DL throughput, packet delay, and availability. One available month is a valid fallback.
- Add three-month relative trends for traffic and PRB when at least two valid months and a nonzero baseline exist.
- Expose profile month count and metric completeness as data-quality metadata, not similarity dimensions.
- Exclude observations at or after the event date. Omit missing metrics from Gower distance.
- Rank retrieved cases using hierarchical filtering, Gower distance, and Gaussian kernel weights. Retrieval is separate from prediction until outcome targets and training cases are validated.

### 6.6 CBR Event Impact Page
- Select a site and estimate recipient KPI changes from similar historical site-launch cases.
- Show the observed pre-event trend and CBR estimate from event month through six post-event months, with an event marker and bootstrap interval.
- Allow display of an individual neighboring site, the Tier 1 cohort (within 2 km), the Tier 2 cohort (2-5 km), or all eligible sites in the selected site's DBSCAN cluster. Exclude the event site itself from recipient groups; noise sites have no cluster aggregate.
- Use each historical recipient's median from up to three pre-event months as its baseline. The CBR response is the similarity/kernel-weighted historical mean change per recipient. Sum traffic and user-count changes across recipients; report CQI, throughput, and latency as cohort mean changes.
- The imported MAOS report supports downlink traffic, CQI, active users, throughput, and packet delay. RSRP and average RRC users remain unavailable until a report supplies those counters. The current import is LTE-only.
- Label predictions as observational estimates associated with similar launches; without matched untreated controls, they are not causal impact estimates. If the selected site has no detected event, use the month after the latest MAOS data as a scenario date.

---

## 7. Visualization Requirements

### 7.1 Cluster Maps (Vue + Leaflet)
Interactive maps showing:
- Site markers color-coded by cluster_id
- Cluster polygon boundaries (alpha shapes)
- Out-of-bounds sites highlighted in RED
- Edge sites with orange markers
- Interior sites with green markers
- Site selection opens a docked, resizable feature inspector on wide screens and a dismissible bottom sheet on mobile; selected site markers and neighbor links remain visible
- Map controls remain responsive and do not prevent access to the selected site's feature tabs

### 7.2 Cluster Analysis Page
- Select a DBSCAN cluster and show its site count, edge/interior split, MAOS coverage, density, and centroid context.
- Plot cluster-aggregated monthly downlink traffic, active users, traffic users, downlink PRB, or CQI.
- Draw a vertical event marker at each month containing a detected site/cell launch event; show same-month event counts and retain every event in the event list.
- List each event's date, type, site, cell, and technology. Treat noise sites (`cluster_id=-1`) as independent, not as one cluster.

### 7.3 Edge Score Heatmap
Heatmap visualization of ANP edge_score:
- Color gradient: green (infill) → yellow → red (edge)
- Circle markers at site locations
- Tooltip with edge_score value

### 7.4 GeoJSON Export
Export clustering results to standard GeoJSON format:
- Point geometries for sites
- Properties: All cluster features
- Compatible with GIS tools (QGIS, ArcGIS)

### 7.5 LTE Monthly KPI Analysis
- Keep cell-month values and raw aggregation components for downlink traffic, PRB use, CQI, throughput, packet delay, and cell availability.
- Roll up ratio/average metrics using their source numerators and denominators; do not take a plain average of cell-level percentages or averages.
- Compute DL user throughput from `(L.Thrp.bits.DL - L.Thrp.bits.DL.LastTTI) / L.Thrp.Time.DL.RmvLastTTI` per the eRAN KPI reference.
- Keep metrics unavailable from the selected report as missing, not zero. The current LTE report does not provide equivalent 2G/3G KPI histories.
- Use only pre-event observations for historical similarity profiles; display post-event changes descriptively and do not claim causal effect.

### 7.6 Similarity Explorer
- Search for a query site by site ID, site name, or cell name.
- Let the user select similarity features from grouped query-site features. Disable unavailable query features and mark them red; default all available features to selected.
- Use equal per-feature weights over the selected, query-available features until trained weights are available. Exclude selected features unavailable across the candidate pool, and omit candidate-specific missing values from that case's denominator. Report the features used for each ranked case.
- In the feature comparison table, display each feature's normalized weight for that query-case comparison; show no weight for unselected or unavailable features.
- Retrieve up to 20 closest detected launch/addition site cases and show event date/type, distance, similarity score, kernel weight, and profile coverage.
- Compare the query site's pre-event LTE profile against each retrieved case.
- Calculate mixed-type Gower distance over every declared similarity field from the configuration, terrain, clutter, spatial, ANP, pre-launch KPI, and cluster-context groups plus the report-backed pre-event LTE profile and trends. Identifiers and profile quality metadata do not contribute to distance; missing values are omitted from the pairwise denominator.
- Expand each case to compare every similarity field side by side with the query site. Mark the row red when either value is unavailable.
- Allow a case to open the map focused on the query site and the returned similar sites only; provide a control to restore the full map.
- Identify the interface as case retrieval only; do not present similarity scores as predicted impact.

### 7.7 CBR Event Impact Page
- Provide site/cell-name search, event date context, metric selection, and scope selection for a neighbor site, Tier 1, Tier 2, or full cluster.
- Plot observed monthly values and CBR-estimated values around the event month, with a vertical event marker and 95% bootstrap interval.
- Keep unsupported KPI choices visible as unavailable with their source-data reason.

---

## 8. Model Database Schema Updates

### Site Model (core/models.py)
```python
class Site(BaseModel):
    # Existing fields
    site_id = models.CharField(max_length=50, unique=True)
    site_name = models.CharField(max_length=200)
    location = PointField(srid=4326)
    latitude = models.FloatField()
    longitude = models.FloatField()
    is_launched = models.BooleanField(default=False)
    launch_date = models.DateField(null=True, blank=True)
    
    # NEW: Clustering fields (v1.0)
    cluster_id = models.IntegerField(default=-1, 
        help_text="Cluster ID from DBSCAN (-1 for noise/single-site)")
    is_cluster_edge = models.BooleanField(default=False,
        help_text="True if site is on edge of cluster polygon")
    out_of_bounds = models.BooleanField(default=False,
        help_text="True if site is outside Tunisia boundaries")
```

### ClusterFeatures Model
```python
class ClusterFeatures(BaseModel):
    site = models.OneToOneField(Site, on_delete=models.CASCADE)
    cluster_id = models.IntegerField(default=0)
    cluster_size = models.IntegerField(default=0)
    cluster_density_sites_per_km2 = models.FloatField(default=0)
    cluster_avg_traffic_gb = models.FloatField


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


## 2026-10-26 - Similarity review, PCA representation and Data Explorer

The original registry remains **94 fields (81 numeric, 13 categorical)**. PCA creates a separate, query/pool-specific list of principal components; it does not delete or rename original features. Cluster ID and the duplicate cluster user-sum alias never contribute to distance. Unsupported inputs remain NULL. Original per-feature mode retains the pre-production fallback weights for some deselected fields; the picker now explains this. Equal-per-group and PCA score explicitly selected dimensions only.

### Calculation review

The review follows the actual event-safe vector service, not undated persisted legacy rows. Site performance uses up to three complete pre-event months; cluster baselines use exactly the preceding calendar month. Users are summed across reporting cells. CQI, PRB utilization, throughput, delay, availability and the three user ratios pool their paired numerator/denominator components. PRB capacity has PRB units, not Mbps. Strict +/-5 PRB-to-MHz mapping and honest NULL bandwidth remain unchanged. Geography, estimated building height and population retain the approved static assumption; antenna height uses positive plan values or the approved 25 m fallback.

Remaining interpretation limits: availability exposure is calendar-month seconds, not independently measured uptime exposure; retained CQI histogram statistics do not record partial-bin coverage; site labels represent the primary detected event, not every later action at that site; current road context is optional and uncalibrated. The legacy Gower name-based grouping and linear treatment of directional angles remain unchanged for compatibility. PCA encodes azimuth/aspect as sine and cosine to avoid the 0/360 discontinuity. PCA variance is not evidence of predictive value; CBR still uses the existing temporal safeguards and ranking.

### PCA method and selection

Implementation: services/models/similarity/pca.py. Fit uses the same frozen-event hierarchy as retrieval. Query values never train the scaler or PCA; query availability selects the usable input mask. Numeric road fields stay outside PCA to retain a separately enforceable 5% budget. Categorical fields remain categorical. Display-only aliases/IDs, query-missing fields, fields with <95% observed candidate coverage, and constant fields are excluded with reasons. At least two varying encoded inputs and three complete candidates are required. Complete rows must cover at least 50% of the filtered pool; if necessary, greedily remove inputs whose removal recovers most complete rows. No mean/zero/median imputation is performed. These coverage and variance thresholds are explicit modelling priors, not calibrated guarantees.

For candidate-only mean mu_j and population standard deviation sigma_j, z_ij = (x_ij - mu_j) / sigma_j. Directions are first mapped to sin(theta) and cos(theta). Full-SVD PCA produces component scores PC_ik = sum_j(z_ij * loading_kj). Component signs are fixed by making the largest absolute loading positive. Retain the smallest leading set reaching **90% cumulative explained variance**; show each component's variance, cumulative variance, complete loading list and leading contributors. A candidate-matrix fingerprint prevents the picker and search from silently using different fits. Missing-candidate exclusions and source-column exclusions are visible.

Retrieval distance on selected PCs is min(1, abs(query_PC - case_PC)/(candidate_PC_p95 - candidate_PC_p5)); zero-range dimensions contribute zero. Categorical distance is 0/1. Selected, compatible roads use existing robust original-feature ranges. Weights normalize per pair: equal per dimension or equal per group (all PCs share one group); road total is capped at 5%, and roads alone cannot rank. The comparison table exposes scores, actual weights and dimensions used. This is an optional PCA/Gower-style retrieval representation, not PCA added invisibly to the original features and not a CBR prediction model.

A local disposable profile cache avoids repeated raster intersections. SQLite/source/config/code revisions invalidate it; it expires after 24 hours. Non-file databases bypass this cache. Frozen event labels filter the candidate set before expensive raster/KPI extraction, without reading current configuration labels. The cache stores calculated profiles only; each PCA is fitted on the current filtered candidates. This is retrospective case exploration: later historical cases can be retrieved, so PCA is not used for event-time prediction validation.

Reference for centring, full-SVD PCA, loadings and explained variance: https://scikit-learn.org/stable/modules/generated/sklearn.decomposition.PCA.html . Scaling: https://scikit-learn.org/stable/modules/generated/sklearn.preprocessing.StandardScaler.html . Missingness policy and road caps are project rules, not sklearn defaults.

### Data Explorer

New navigation page with three datasets: **16 retained monthly raw counters/components**, **11 calculated monthly KPI metrics**, and **94 event-safe similarity fields**. Raw means imported cell-month values; CQI sufficient statistics and calendar exposure are explicitly labelled import-derived components, not untouched instrument samples. Individual CQI histogram bins and other unimported CSV columns are not represented as stored counters.

Filters: site/cell text, exact site ID, cell name/ID, cluster (including -1), technology, inclusive month range, selected columns, numeric thresholds/exact values, categorical equality and NULL/present. Calculated scopes: cell, site, cluster, Tier 1 (0-2 km), Tier 2 (2-5 km); tiers require an origin site and exclude it. Noise sites remain independent singleton clusters. Filters apply before aggregation and reporting-cell/site counts describe the filtered population. Profile mode uses an optional cutoff month instead of a measurement-month range; technology/cell filters select whole-site profiles. Missing values remain NULL and actual zeros display as zero. Pagination is deterministic, limited to 200 rows per page. CSV exports only the displayed page and protects string cells against spreadsheet formula execution.

Read-only API: /api/explore/metadata/ and /api/explore/. Similarity adds representation=original|pca to both availability and search; search accepts pca_fit_id from the picker (409 if changed). Logic lives in services/data_explorer.py and services/models/similarity/, with thin HTTP views. No schema migration or raw-counter rewrite is required.

Validation evidence and measured candidate statistics are recorded in the dated audit below when complete; no pending check is marked passed.


### 2026-10-26 - Measured feature review (1,380 detected-event site profiles)

The audit ran the actual event-safe feature builder for all 1,380 detected-event sites in the 3,441-site inventory (890,674 monthly KPI records). These are one primary-event profile per site, not 4,566 independent event observations. Evidence: docs/verification/similarity_pca/review.json; reproduce with scripts/audit_similarity_pca.py through manage.py shell.

- **12 all-missing fields**: legacy total_capacity_after_mbps; n_2g_sites_2km/n_3g_sites_2km; avg_traffic_ul_gb, peak_hour_traffic_gb, peak_hour_users, avg_rsrp_dbm, congestion_hours_per_day; tech_before_2g/3g and tech_after_2g/3g. These remain visible and unavailable, not zero-filled.
- **3 constant-when-observed fields**: antenna_height_m (25 m fallback), tech_added (4G), tech_after_4g (true). They add no observed discrimination in this pool. Keep them for later real height/multi-technology data; PCA drops constant numeric inputs.
- **25 numeric pairs with abs(Pearson r) >= 0.95**, measured on available paired profiles (minimum 20). Perfect duplicates include n_sites_2km, n_4g_sites_2km and n_tier1 in this LTE-only reconstruction; fixed-buffer road_km_weighted and road_density_weighted_km_km2; and the already display-only cluster_avg_users alias of avg_users. BW vs PRB capacity has r=0.999841 on 513 supported pairs. These are observational correlations, not causal or predictive validation.
- Recommend avoiding duplicate dimensions in the production original-feature defaults, using group-balanced weights during exploration, retaining PRB capacity when strict MHz is unavailable, and calibrating high-correlation ANP/road subsets using event-level ablation before changing CBR. No original field is deleted by this change.

**Actual PCA example - TAT_0055 / 6306:** 301 hierarchy-matched candidate sites, 297 complete rows, four excluded cases, 38 encoded numeric inputs -> 13 principal components, 90.3588% retained variance. PC1's leading loadings describe edge score, empty angular bins and the largest empty arc; PC4 is led by terrain roughness and slope. This specific fit excludes several performance KPIs because their candidate coverage is below 95%; the reduced list is therefore mainly structural/geographic. Use the original list when those sparse KPI inputs matter. The input exclusions and complete loading matrix are shown in the UI. Component counts/loadings vary with the query's supported inputs and matching pool; 13 is not a global fixed schema.

There is no claim that PCA improves KPI prediction accuracy. The PCA option is exploratory retrieval; CBR remains on its existing feature representation. The next modelling step is event-level, time-separated evaluation of original/group-balanced/PCA representations, with complete-case coverage reported alongside prediction errors.


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


### 2026-10-27 - Mandatory hierarchy, frozen reference and recipient calibration

Event type and tier scheme may never relax. Technology/band relaxation is explicit (picker/API allow_filter_relaxation). Original numeric Gower ranges come from an explicitly versioned global P5-P95 reference, selected from tables with only pre-query profiles; query/candidate pools cannot refit them. Default available selected-weight share is 0.6 before pair renormalisation; low-support pairs are excluded and reported. Gaussian width remains adaptive and normalisation is stable. PCA remains exploratory and candidate-fitted, with the same hierarchy/coverage policy. Preserve legacy deselected non-road fallback until production, but exclude it from selected-feature support.

Add reproducible event-recipient exports and offline nested chronological event-origin-grouped validation. Rows require pre-event inputs, separate +1..+6 targets, NULL preservation, canonical identity, geometry/band/load context and sample provenance. Training labels must be observable before validation cutoffs. Optional RF proximity/local ridge alternatives require complete inputs; do not promote without evidence. Current study: 143,103 exported pairs, 320 events/893 pairs sampled for nested validation. Mixed evidence supports retaining Gaussian Gower. Pair-feature tuned budgets are not site-picker weights. Full details/formulas: feature_eng.md and docs/verification/pair_cbr/README.md. Registry remains 95 fields. No schema migration.


Final live verification - 2026-10-27: browser checks passed for original-feature searches with relaxation on/off and for strict PCA. Each returned 10 cases matching the mandatory event type/scheme and >=0.6 available selected weight, with frozen reference df7aa5a2043bf2359d9e55ee reported. No page errors. Evidence: docs/verification/pair_cbr/browser.json and similarity-safeguards.png. The final frontend production build passed. Full tests: 114 passed; system and migration checks passed. The full pair export audit reports zero mismatches.


### 2026-10-27 - Recipient CBR prediction contract

Implement services-owned recipient forecasts at /api/cbr/recipients/ with recorded-event ownership checks and selectable Gaussian, control-adjusted, local-ridge and supported-horizon ramp methods; retain the legacy benchmark. Normal baselines require three complete months. Median baseline applies to raw CBR; mean baseline applies to DiD. Train on completed pre-query targets only, hard partition by event type/scheme, use frozen global pair ranges, require >=0.6 available weight, >=3 physical event origins and >=2 effective origins. The pair model's 8 numeric +1 categorical dimensions are separate from the 95-field site picker.

Controls match known LTE bands, scheme, pre-load and six-month trends; primary exclusion is 10 km from any event over the six-month baseline/event window, with explicit 5/10/15 km sensitivity. Require three controls and censor subsequent exposure. Query counterfactual growth uses pre-event slopes only; never future control observations. Treat the output as control-adjusted observational prediction, not a proven causal effect.

Use 500 correlated physical-origin bootstrap draws; label conditional mean intervals separately from prediction bands. Rolling residual prediction bands require prior independent-origin support, dataset/version consistency and a prior-time coverage gate. No aggregate prediction interval is claimed. Ramp smoothing must preserve unsupported gaps and allow negative/offloading responses. Sum traffic/users; observed ratios pool counters and forecast ratios use explicitly labelled pre-period exposure weights. Missing inputs or support remain NULL with reasons. Full formulas and actual tests are in feature_eng.md; validation evidence is under docs/verification/recipient_cbr/. No schema migration.


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
