# Feature engineering: current calculations and improvement plan

Updated: 2026-10-26. Scope: current working tree, including uncommitted implementation.

This is the current reference for feature definitions, formulas, sources, consumers, missing-data rules and remaining work. It replaces the earlier sequence of overlapping audit amendments. Implemented behavior, known limitations and proposed enhancements are distinguished below.

## 1. Current feature registry and processing

The implemented Gower registry contains **80 scalar dimensions: 68 numeric and 12 categorical**. Earlier 55/56/60 counts described older logical feature designs; 70/71/73 were intermediate implementation counts and are no longer current.

| Family | Numeric | Categorical | Total | Production of values |
|---|---:|---:|---:|---|
| Configuration | 5 | 9 | 14 | Persisted current cell-plan summaries; unsupported historical values excluded |
| Terrain | 4 | 0 | 4 | Persisted DEM extraction |
| Clutter/buildings | 3 | 1 | 4 | Persisted WorldCover/OSM extraction; historical values excluded |
| Spatial | 8 | 0 | 8 | Persisted current values for inspection; reconstructed for similarity |
| Angular Neighborhood Profile (ANP) | 15 | 0 | 15 | Persisted current values; reconstructed for similarity |
| Cluster context | 5 | 1 | 6 | Current table for inspection; reconstructed historical context, label excluded |
| Legacy prelaunch KPI schema | 9 | 0 | 9 | Declared but excluded from vectors without verified measurement windows |
| Report-backed LTE profile/trends | 10 | 0 | 10 | Computed on demand from complete pre-cutoff months |
| Population | 3 | 0 | 3 | Computed on demand from local GHSL raster |
| Road context | 6 | 1 | 7 | Persisted RoadFeatures; optional current-context retrieval |
| **Total** | **68** | **12** | **80** | Declared dimensions, not a promise that all are populated |

The family counts above describe the feature catalog. The ranker's current name-based group mapping can place some fields in different weighting groups; see the remaining audit findings.

Flow: source imports -> services/models/features/pipeline.py -> persisted feature tables -> services/models/similarity/feature_vector.py plus pre-event reconstruction and population -> similarity/engine.py and weighting.py -> Similarity Explorer and CBR.

Models contain schema, serializers expose stored fields, and calculation/orchestration belongs in services/. Roads are registered in the shared pipeline used by both Features only and Full sync. Population is computed on demand and needs no feature backfill.

Usage below: similarity means a declared dimension, usable only when eligible, available and weighted. Historical exclusions take precedence over persisted values. Inspector values can describe today's inventory while historical vectors use reconstructed or unavailable values.

## 2. Source inventory and provenance

| Source | Location | Actual consumers / limits |
|---|---|---|
| Current cell plan | data/cellplan/Cell_Plan_Data_21102026.xlsx; Site and Cell | Coordinates, technology labels, azimuth, height, bandwidth; not a historical configuration snapshot |
| Monthly LTE report | MAOSMonthlyKPI; preprocessing/maos_report_loader.py | Pre-event profiles, activity evidence, observed outcomes; no equivalent 2G/3G history |
| Copernicus DEM | data/geographic/dem/copernicus_glo30.vrt | Terrain and antenna elevation; terrain shape treated as static |
| ESA WorldCover 2021 | data/geographic/worldcover/esa_worldcover_v200.vrt | Clutter; independent water classification for population coverage |
| OSM building footprints | data/geographic/osm/tunisia_buildings.gpkg | Footprint coverage, not measured building height |
| GHSL population 2025 | data/geographic/ghsl/ghs_pop_e2025_r2023a_54009_100_v1_0_tun.tif | Native 100 m equal-area counts per cell; modeled residential population |
| Geofabrik roads | data/geographic/osm/tunisia.gpkg, layer gis_osm_roads_free | Current road snapshot; verified data timestamp 2026-10-22T20:21:33Z |
| GHSL built-up surface | data/geographic/ghsl/ghs_built_s_e2025_r2023a_54009_100_v1_0_tun.tif | Present locally; not yet a feature input |
| GHSL height archive | data/geographic/ghsl/tiles/ | Present locally; usability/coverage must be verified before replacing height proxy |

Road source date comes from the existing ZIP's README, verified by matching the archived GeoPackage SHA-256 to the imported file. No road download was performed. Filesystem modification dates were not treated as extract dates.

- Source SHA-256: `2a149398d4d13f78def1189299110a3ef18c4dc9da20401f3b4f51a659f7ba8f`.
- Normalized indexed EPSG:32632 snapshot: data/geographic/osm/roads_utm32_2a149398d4d1.gpkg, layer roads.
- Normalized SHA-256: `66ac9c0aa0bf1ac8e34a031dd770000127aeccf261389d0847a573c62eb84a72`.
- Archive/source URL: https://download.geofabrik.de/africa/tunisia-latest-free.gpkg.zip . Historic download date is not established.
- Licence: ODbL 1.0; attribution: OpenStreetMap contributors and Geofabrik. Source manifest is stored alongside the normalized GeoPackage.

## 3. Configuration: 14 dimensions

Implementation: services/models/features/context.py::configuration_feature_values. Persisted in ConfigurationFeatures and displayed under KPIs & Config.

Let C be current cells; A be cells flagged launched with dates; B be technologies with nonzero monthly activity before the selected event. These persisted formulas are current-inventory summaries. Historical vectors clear unsupported configuration fields, retaining NEW_SITE only when supported by that event date.

| Fields | Formula / source meaning |
|---|---|
| event_type | NEW_SITE if site launched; otherwise TECH_ADD if launched-cell technologies extend B; SECTOR_ADD if launched cells exist without a newly serving technology; else BASELINE |
| tech_added | Single technology in technologies(A) minus B; blank if none/multiple or whole-site launch |
| tech_before_2g, tech_before_3g, tech_before_4g | Vector aliases for persisted has_2g_before/has_3g_before/has_4g_before; membership in B |
| tech_after_2g, tech_after_3g, tech_after_4g | Aliases for technology membership in current C |
| bands_added | Blank: no reliable historical band delta available |
| sector_count_after | Count distinct round(azimuth / 5) * 5 |
| cells_per_sector_after | Number of cells / sector count; current extractor returns 0 with no sectors |
| antenna_height_m | Arithmetic mean cell antenna height |
| total_bw_after_mhz | Sum cell bandwidth across sectors/layers; a cell-resource measure, not unique spectrum |
| total_capacity_after_mbps | Uncomputed placeholder 0 in storage; converted to unavailable in similarity |

Limits: current cell configuration does not establish event-time configuration. Cell-weighted height overweights sectors with more layers. Absence of 2G/3G activity is not proof of absence. New cells do not prove a new physical sector. Azimuth rounding does not merge 0 and 360 degrees. These require correction in current persisted extraction; historical vectors do not reuse their unsupported values.

## 4. Terrain: 4 dimensions

Implementation: services/models/features/geometric.py and services/visualization/dem_processor.py. Source: DEM and current cell height. Persisted fields appear under Terrain and are declared in similarity.

| Field | Implemented formula / support |
|---|---|
| z_antenna_m | DEM(site) + mean cell antenna height; unavailable in historical vectors |
| terrain_slope_deg | Median degrees(atan(sqrt((dx/sx)^2 + (dy/sy)^2))) in approximate 200 m window |
| terrain_roughness_m | Standard deviation of valid elevation pixels in approximate 1 km window |
| terrain_aspect_deg | Circular mean of (90 - degrees(atan2(dy,-dx))) mod 360, weighted by sqrt(dx^2+dy^2), in approximate 200 m window |

sx/sy are metric pixel spacing for slope. Aspect currently uses unscaled pixel gradients. Windows are rectangles, not circles, and the same latitude-adjusted angular extent is used on both axes. Flat-terrain aspect is arbitrary. Terrain shape remains an explicit static assumption in historical reconstruction. Legacy failure paths can store zeros; they have not been fully converted to nullable quality-aware results.

## 5. Clutter/buildings: 4 dimensions

Implementation: services/models/features/clutter.py. WorldCover is masked with a metric 1 km circle. Let u, v, w be built-up, vegetation and water fractions of valid pixels; o = 1-u-v-w. Vegetation groups classes 10/20/30/40/90/95; built-up is 50 and water is 80.

| Field | Implemented formula |
|---|---|
| dominant_clutter | Ordered rules: urban if u>0.50; suburban if u>0.20; water if w>0.50; forest if v>0.70; otherwise rural |
| clutter_entropy_2km | -sum(p*ln(p)) over positive u,v,w,o; actually computed at 1 km |
| pct_building_area_1km | 100 * summed clipped OSM footprint area / (pi * 1000^2), clamped to [0,100] |
| avg_building_height_m | Class lookup: urban 18, suburban 8, rural 4, water/forest 0; not measured height |

All four are available in the current inspector; historical vectors exclude them without event-time snapshots. Remaining issues: entropy name/radius mismatch, forest label includes crops/grass, missing cover can become rural/zero, missing building coverage can become zero, overlapping footprints are summed rather than unioned, and height is a synthetic proxy. Verify source CRS for the pre-reprojection footprint bounding-box filter.

## 6. Spatial and ANP: 23 dimensions

Sources: site coordinates and pre-cutoff LTE activity for similarity; current inventory for persisted inspector extraction. Haversine distance uses Earth radius approximately 6,371 km and excludes the query site ID. Current coordinates are assumed stable.

### Spatial fields

| Field | Formula |
|---|---|
| dist_nearest_site_m | Minimum distance to another evidenced site |
| n_sites_1km | Count distance <=1,000 m |
| n_sites_2km | Count distance <=2,000 m |
| n_sites_3km | Count distance <=3,000 m |
| n_2g_sites_2km, n_3g_sites_2km, n_4g_sites_2km | Technology-specific neighboring site counts; unsupported technologies remain unknown in reconstructed context |
| neighbor_avg_antenna_height_m | Persisted mean of neighbor site heights; historical similarity value unavailable |

Persisted spatial failure/singleton paths can still produce zero placeholders. Reconstructed context uses only the preceding three complete calendar months and leaves context unknown when there is insufficient activity evidence.

### ANP fields

Implementation: features/anp.py. T1 is distance <=2 km; T2 is 2<distance<=5 km. Use combined-tier bearings, 12 fixed 30-degree bins with counts c_j and probabilities p_j, and circular gaps g_j between sorted bearings, including wrap-around.

| Field | Formula |
|---|---|
| n_tier1 | T1 neighbor count |
| n_tier2 | T2 neighbor count |
| t1_to_t2_ratio | N1/N2; if N2=0 use N1, or 0 if both zero |
| t1_nearest_m, t2_nearest_m | Minimum distance within tier; legacy no-neighbor sentinel 9999 |
| avg_neighbor_dist_t1_m, avg_neighbor_dist_t2_m | Mean distance within tier; legacy empty-tier value 0 |
| angular_uniformity | -sum(p_j*ln(p_j))/ln(12) |
| max_empty_arc_deg | max(g_j); 360 for empty neighborhood |
| n_empty_bins | Number of zero-count bins |
| dominant_sector_deg | 30*argmax(c_j)+15; first maximal bin wins |
| dominant_sector_count | max(c_j) |
| coverage_asymmetry | (max(g_j)-min(g_j))/360; 1 for fewer than two bearings |
| bearing_stddev_deg | degrees(sqrt(-2*ln(Rbar))), Rbar = sqrt(mean(sin(theta))^2+mean(cos(theta))^2) |
| edge_score | clip(.3*min(max_gap/180,1) + .2*empty_bins/12 + .2*(1-uniformity) + .2*asymmetry + .1*(1-min(N1/6,1)), 0, 1) |

No-neighbor legacy ANP defaults include edge score 1; classification threshold is 0.5. Historical context avoids manufacturing isolation from an entirely unknown observation window and sanitizes nonfinite results.

Remaining persisted-extractor issues: the old 0.045-degree prefilter can drop valid east/west T2 neighbors; similarity reconstruction bypasses it. Sector-alignment flag does not change fixed bins. Spread uses both tiers. Asymmetry uses angular gaps, not quadrant densities. Distance sentinels and zero empty-tier means should eventually become explicit missing values. Correlated ANP components and edge_score can duplicate influence.

## 7. Cluster context: 6 dimensions

| Field | Current persisted formula | Similarity reconstruction |
|---|---|---|
| cluster_id | Current DBSCAN label | NULL: labels are not comparable across snapshots |
| cluster_size | Number of cluster sites; noise sites independent singletons | Rebuilt cluster size, including query location |
| cluster_density_sites_per_km2 | Count / projected convex-hull area; degenerate hull buffered 100 m | Recomputed on evidenced sites and query location |
| cluster_avg_traffic_gb | Latest-global-month average site traffic, with legacy missing-to-zero behavior | Mean available recipient traffic from the immediately preceding month; exclude intervention site and missing members |
| cluster_avg_users | Latest-global-month average summed cell active users | Same pre-cutoff recipient rule, without imputing missing users |
| dist_to_cluster_centroid_m | Projected distance to current point centroid | Rebuilt UTM geometry and centroid |

Implementation: features/context.py for stored values; similarity/historical.py for reconstruction. Rebuilt clusters use DBSCAN with 2 km radius and minimum three sites. Persisted geometry uses an equal-area projection; reconstruction uses UTM 32N. Hull density differs from map alpha-shape polygons. Summed cell user averages are load proxies, not unique subscribers.

## 8. KPI schemas and active LTE profile: 19 declared dimensions

### Active LTE profile: 10 dimensions

Implementation: similarity/feature_vector.py and preprocessing/maos_aggregation.py. For each of the three complete calendar months before cutoff, sum compatible cell components and calculate monthly site KPIs. Take the median of available monthly values for each profile metric.

| Field | Monthly formula | Report source |
|---|---|---|
| pre_dl_traffic_gb_day | sum(DL bits)/8e9/calendar_days | L.Thrp.bits.DL |
| pre_active_users | Sum cell average active users | L.Traffic.ActiveUser.Avg |
| pre_traffic_users | Sum cell average traffic users | L.Traffic.User.Avg |
| pre_prb_util_dl_pct | 100*sum(PRB used)/sum(PRB available) | L.ChMeas.PRB.DL.Used.Avg / Avail |
| pre_cqi_avg | sum(i*CQI_count_i)/sum(CQI_count_i), i=0..15 | L.ChMeas.CQI.DL.0..15 |
| pre_dl_throughput_kbps | sum(DL bits - LastTTI bits)/sum(DL time ms) | L.Thrp.bits.DL, LastTTI, L.Thrp.Time.DL.RmvLastTTI |
| pre_dl_packet_delay_ms | sum(delay time ms)/sum(packet count) | L.Traffic.DL.PktDelay.Time / Num |
| pre_cell_availability_pct | 100*(1-sum(unavailable seconds)/sum(observation seconds)) | L.Cell.Unavail.Dur.Sys; full-calendar-month observation assumption |
| pre_traffic_trend_3m_pct | 100*(last-first)/abs(first) over valid traffic/day values | Monthly traffic/day; NULL if <2 values or first=0 |
| pre_prb_trend_3m_pct | Same relative-change formula for PRB | Monthly PRB |

Ratio numerators/denominators use compatible rows; absent inputs and nonpositive denominators yield unavailable metrics. bits/ms is numerically decimal kbps. Profile completeness is available metric values / (3*8), so calendar gaps reduce coverage. Profile month count and completeness are metadata, not distance dimensions.

Limits: summed user averages are not unique users; trend is not normalized for elapsed months; assumed full-month availability can bias commissioning months. Cell-level importer downtime clamping and raw-component rollups need further consistency review.

### Legacy PreLaunchKPI: 9 dimensions

Declared fields: avg_traffic_dl_gb, avg_traffic_ul_gb, avg_users, avg_prb_util_pct, peak_hour_traffic_gb, peak_hour_users, avg_cqi, avg_rsrp_dbm, congestion_hours_per_day.

The current vector clears all nine because their measurement windows are unverified. The original audit found no populated PreLaunchKPI rows or active service producer. Busy-hour metrics, congestion hours and equivalent RSRP cannot be recovered from the monthly report alone.

A separate KPIFeatures table is populated/displayed by the legacy pipeline but is not the nine-field similarity schema. Its default path calculates last-prelaunch-month average cell PRB/RRC, traffic per day, and average calendar-time traffic rate (stored as avg_throughput_pre, which is not user throughput). Coverage/gap/segmented-demand fields are not calculated by that path and can retain legacy defaults. Consolidate these schemas rather than treating default zeros as measurements.

## 9. Population: 3 dimensions

Implementation: features/population.py. Native GHSL resolution is **100 m**, not 10 m. Detailed map zoom does not create finer population precision. Population has its own popup tab and optional map overlay with opacity/legend.

Construct local UTM disks/rings and intersect native equal-area raster cells. For native count P_i, cell area A_i and overlap A_ij, mapped count P = sum(P_i*A_ij/A_i) over finite nonnegative source cells.

| Field | Formula / support | Usage |
|---|---|---|
| population_density_1km_per_km2 | Mapped P / full 0-1 km catchment area in km^2, including water | Similarity, CBR ranking when epoch-eligible, Population tab, map density context |
| population_tier1 | Mapped P in 0-2 km disk, people | Similarity and CBR context; Population tab |
| population_tier2 | Mapped P in separate 2-5 km annulus, excluding T1 | Same |

WorldCover class 80 independently identifies water using categorical mode at native population-cell alignment. Never assume every missing population cell is water. Coverage = (valid population OR known-water area)/full area. Land coverage = valid nonwater population area/nonwater catchment area.

**The 90% rule is a quality classification, not a suppression threshold.** If overall and land coverage are at least 90%, status is calculated. Otherwise supported values remain numeric with incomplete_land_coverage and a partial mapped estimate label. Missing residents are not extrapolated or filled with zero. Entirely unsupported land or out-of-raster areas remain NULL; a fully supported all-water area has zero residents.

population_quality / quality exposes coverage, land_coverage, water_pct, status and observed_population. Metadata does not contribute to distance. Partial mapped values can understate complete catchment population and bias comparison; this limitation is shown in the UI.

All three dimensions are excluded from vectors before January 2025. Later historical use still treats population as fixed modeled 2025 context, not exact event-time population. Cache keys include source version and catchment geometry. The inspector can show current 2025 context separately from historical eligibility.

BIZ_0033 / 1534, 37.30341 N, 9.86391 E:

| Field | Mapped value | Land coverage |
|---|---:|---:|
| 1 km density | 2,841.7 people/km^2 | 72.7% |
| T1 count | 27,089.8 people | 78.8% |
| T2 count | 56,588.7 people | 74.3% |

All three are partial mapped estimates, not complete catchment totals.

## 10. Roads: 7 persisted dimensions

Implementation: features/road_loader.py and road_features.py. Settings: config/road_context.json. Storage: RoadFeatures, additive migration 0007_road_features. Calculation is registered in both feature-sync modes; extract_road_features supports a road-only backfill.

Use one 1 km EPSG:32632 buffer per site, explicit spatial-index queries, and geopandas.overlay(..., keep_geom_type=True). Retained length classes: motorway, trunk, primary, secondary, tertiary, residential, unclassified. Preserve all source classes separately as coverage evidence within 5 km. The source's fclass becomes highway; *_link variants map to their parent.

| Field | Formula | Type / units |
|---|---|---|
| road_km_total | sum(clipped length by retained class) | Numeric, km |
| road_km_weighted | sum(class weight * clipped length) | Numeric, weighted km |
| road_density_weighted_km_km2 | Weighted length / actual buffer polygon area | Numeric, km/km^2 |
| highway_km | Motorway + trunk clipped length | Numeric, km |
| highway_share | highway_km / road_km_total; NULL if total=0 | Numeric, 0-1 |
| n_road_intersections | Degree >=3 junction proxy inside buffer, from noded uncut local lines | Numeric count; explicitly an estimate |
| dominant_road_class | Greatest clipped length; alphabetical tie break; NULL with no retained roads | Categorical |

Prior, uncalibrated class weights: motorway/trunk 1.0, primary .7, secondary .5, tertiary .3, residential/unclassified .1. Unknown .05 is recorded but unknown classes are excluded from measured lengths. No log1p transform is added.

Topology uses separate layer/bridge/tunnel groups and a 1 cm coordinate tolerance; original OSM-node topology is absent. This avoids false overpass junctions but can miss connections across differently tagged segments. Buffer clipping endpoints do not create junctions. Parallel carriageways are distinct roads. Revisit duplicate contributions before introducing cell-level wedges.

NULL versus zero: no source road of any class within 5 km -> all measurements NULL. Nearby source coverage with no retained class inside 1 km -> zero lengths/density/highway/junction count, NULL highway_share and dominant class. Nearby mapping is only a coverage heuristic.

Rows persist source, source_hash, buffer_m, osm_extract_date, method_version, weights_version, coverage_status, class_lengths_km and updated_at. Pairwise road comparison requires matching source/buffer/method/weights signatures. Metadata/IDs never enter distance. Source and normalized hashes are verified; --provenance-only can attest unchanged source dates without recomputing geometry.

Roads are **unselected by default**. Current-context retrieval requires explicit opt-in. Historical CBR keeps them off by default, and the 2026-10-22 source cannot supply road values for earlier events. The uncalibrated road-group weight cap is 5%; at least one selected comparable non-road dimension is required.

Actual backfill: **3,441 rows; 3,440 computed; 1 NULL; 0 errors**, including ten valid zero-length sites. NULL site: KEB_0044 / 5295. BIZ_0033 has 34.1133 km total, 4.7659 weighted km, density 1.5172 km/km^2, 0 highway km/share, 287 estimated junctions, dominant residential.

## 11. Gower distance and actual feature weights

Implementation: similarity/engine.py, gower_distance.py, weighting.py and hierarchical_filter.py.

For pairwise available weighted dimensions, D(q,c) = sum(w_f*delta_f)/sum(w_f). Numeric delta = min(1, abs(q_f-c_f)/(P95_f-P5_f)); categorical delta = 0 for equality, otherwise 1. Ranges are fitted on the filtered candidate pool, excluding incompatible road values. Missing values are omitted from both sums. Existing zero-range behavior returns zero difference; see audit findings.

Hierarchical filtering tries event type, technology, then band Jaccard overlap >=0.5, relaxing when fewer than three cases remain. Gaussian kernel weights convert ranked distances into analog weights; these are separate from feature weights.

- equal_per_feature (default): selected available dimensions receive weight 1 before normalization; existing non-road fallback weights remain active until production. Deselected roads are an explicit exception and contribute zero.
- equal_per_group: selected pairwise-available dimensions in each group receive raw weight 1/n_available_in_group, then normalize.
- Road budget: if raw road weight is R and other weight O, cap raw road weight at O*.05/.95 before normalization. A road-only comparison is rejected instead of becoming 100% road weight. The cap is an uncalibrated safeguard, not learned importance.
- Source/buffer/method mismatches skip road dimensions and are reported. Actual per-case feature_weights are returned by the backend; the comparison table displays those values directly. used_features reports dimensions that actually contribute, including retained legacy non-road defaults where applicable.

Identifiers, source hashes, dates and population quality are metadata. Default-off behavior, missing values and provenance checks apply independently of the weighting mode.

## 12. Historical timing and CBR calculations

Implementation: similarity/historical.py, feature_vector.py and prediction/cbr_impact.py.

Cutoff = first day of query/event month. Use only the preceding three complete calendar months. Event-month values never enter the pre-event profile, even for a midmonth event date. Historical neighbor/ANP/cluster context is rebuilt from positive LTE activity evidence in that window, not today's full network inventory.

Historical configuration, antenna elevation, clutter/building snapshots and undated legacy KPIs are unavailable where data cannot establish them. Current coordinates and terrain shape remain explicit stability assumptions. Current-context retrieval can inspect later cases using each case's own pre-event profile; that is distinct from CBR forecast eligibility.

CBR only admits analog launches before the query event month. For each horizon, analog outcome month must also finish before that cutoff. Query post-event observations are display-only. Fewer than two completed analog responses yields no estimate.

For recipient s and KPI k, baseline b_s,k is the median of available values at offsets -3,-2,-1. Historical recipient change at horizon h is y_s,k,h - b_s,k. Each analog provides its mean recipient change. Kernel-weighted analog responses estimate mean recipient change for the query cohort, with 500 weighted bootstrap resamples for the interval.

- Traffic/users: cohort baseline = sum of recipient baselines; predicted cohort impact = estimated mean recipient change * number of baseline-eligible recipients.
- CQI/throughput/delay: cohort baseline and observed values = arithmetic mean of site KPIs; predicted change uses the same mean-site definition. Each site KPI still uses properly aggregated cell components.
- Observed cohort values use the fixed metric-specific baseline-eligible cohort. If any member is missing, show a gap rather than a partial total. Expose observed_sites, eligible_sites and analog_cases.
- Absolute level = baseline + impact, bounded below by 0; CQI is also bounded above by 15. Intervals are bounded likewise, and reported impact equals bounded level minus baseline.
- UI shows calendar months, event marker, actual null gaps (spanGaps false), shaded bootstrap interval, stable chart height, empty-data messages and a monthly support table.

These are observational analog estimates, not causal counterfactuals or empirically calibrated prediction intervals. Monthly publication delays, retrospective revisions, historical coordinates and precise event-time configuration cannot be established from current files.

## 13. Audit findings and enhancement priorities

| Priority | Finding / proposal | Current status |
|---|---|---|
| P0 | Prevent future KPI, launch and current-inventory reuse in historical CBR | Implemented and regression-tested; static-source assumptions remain explicit |
| P0 | Preserve unknown data rather than defaults | Roads and active monthly features preserve NULL; partial population has quality metadata; legacy persisted extractor defaults still need cleanup |
| P1 | Circular angle distance min(abs(a-b),360-abs(a-b))/180 | Proposed; current numeric Gower still treats angles linearly |
| P1 | Candidate zero percentile range hides an out-of-pool query difference | Unresolved; establish explicit domain-scale/constant-field policy |
| P1 | Explicit feature-to-group schema | Proposed; current name-based mapping can put ANP dominant-sector or neighbor-height fields into configuration |
| P1 | Remove exact duplicates from selection | Road weighted length/density are exact duplicates; prefer density. n_tier1 and n_sites_2km also overlap |
| P1 | Missing-information eligibility threshold | Proposed; sparse cases can compare favorably over too few dimensions |
| P1 | Neighbor pre-event pressure and population per serving site | Proposed using existing activity/coordinates/population; preserve cohort and epoch limits |
| P1 | Time-normalized trends and variability | Proposed: slope against actual month index, traffic log1p slope, PRB percentage-points/month, robust MAD with sufficient months |
| P1 | CQI distribution tails/entropy | Proposed from existing 16 histogram counters |
| P2 | Multi-scale WorldCover fractions and normalized entropy | Proposed; fix current entropy radius/name and retain source support |
| P2 | GHSL built-up fraction / validated real height | Proposed from existing local data, after checking units, epoch and coverage; replace synthetic height only when supported |
| P2 | Relative antenna prominence / terrain obstruction | Proposed from DEM and reliable height; geometry proxies, not measured RF coverage |
| P2 | Sector-aware resources | Proposed: modulo-360 azimuth grouping and per-sector/layer summaries; historical values remain unknown without snapshots |
| P2 | Nearby-event contamination and seasonal context | Proposed from existing event dates/monthly histories; avoid future observations |

No busy-hour load, congestion duration, P95 latency, daily launch timing, 2G/3G performance histories, segmented demand or financial NPV can be reconstructed reliably from the current monthly LTE data alone.

## 14. Diagnostics, verification and remaining validation

Road diagnostics were run on current persisted data: weighted length/density are perfectly collinear; VIF is 33.24 for total length and 20.94 for junction count. Weighted density versus n_sites_2km has Spearman 0.8653 (n=3,440). VIF uses 3,430 complete rows without imputation. Keep roads optional and avoid selecting duplicate length/density fields together.

Time-valid predictive road ablation remains **blocked**, not passed. The 2026-10-22 snapshot postdates the historical launch pool and earlier snapshots are absent. diagnostics.json records 17 whole-site launches, 783 cell-addition site/month groups, four with/without-road and weighting-mode conditions, and NULL KPI errors. No accuracy gain or default-on recommendation is supported. Historical road snapshots and validated addition targets are needed before meaningful ablation.

Previously executed implementation checks, not newly rerun for this documentation update:

| Check | Observed result |
|---|---|
| Full Django/numerical suite | 31 tests passed |
| Django system check | Passed |
| Migration consistency | No pending model changes; additive road migration applied |
| Frontend production build | Passed; existing bundle-size advisory |
| Population/CBR browser checks | Desktop/mobile passed; 20 BIZ_0033 scope/KPI chart combinations compared with API arrays |
| Roads browser checks | Dedicated tab/bars/source date, seven default-off dimensions, explicit group-mode opt-in, actual table weights and <=5% road share passed; no page errors |
| Road backfill | 3,440 computed, 1 NULL, 0 errors |
| Historical forecast invariance | Future KPI/configuration changes do not alter tested historical forecasts |
| Predictive accuracy / road ablation | Not established; blocked as described above |

Artifacts: docs/verification/population/, docs/verification/biz_0033/, docs/verification/roads/ (README, browser-report.json, diagnostics.json, screenshots).

Repeat commands:

```text
python manage.py check
python manage.py test tests
python manage.py makemigrations --check --dry-run
python manage.py extract_road_features
python manage.py extract_road_features --provenance-only
python manage.py road_diagnostics
npm run build                         # from frontend/
python scripts/verify_population_browser.py
python scripts/verify_biz_population_cbr.py
python scripts/verify_road_browser.py
```

Browser scripts require local backend/frontend servers, optional Playwright and installed Edge. Feature backfill commands write persisted values; diagnostics are read-only except their report artifact. Ask before destructive migrations. Document source/measurement-method changes and rerun relevant checks before claiming success.
