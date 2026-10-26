# Feature engineering: current calculations and improvement plan

Updated: 2026-10-26. Scope: current working tree, including uncommitted implementation.

This is the current reference for feature definitions, formulas, sources, consumers, missing-data rules and remaining work. It replaces the earlier sequence of overlapping audit amendments. Implemented behavior, known limitations and proposed enhancements are distinguished below.

## 1. Current feature registry and processing

The implemented Gower registry contains **94 scalar dimensions: 81 numeric and 13 categorical**. Earlier 55/56/60 counts described older logical feature designs; 70/71/73/80 were intermediate implementation counts and are no longer current.

| Family | Numeric | Categorical | Total | Production of values |
|---|---:|---:|---:|---|
| Configuration | 6 | 9 | 15 | KPI-evidenced cells projected to plan; PRB capacity separate from legacy Mbps |
| Terrain | 4 | 1 | 5 | Static DEM extraction and optional relief classification |
| Clutter/buildings | 3 | 1 | 4 | Approved static land-cover/building estimates |
| Spatial | 8 | 0 | 8 | Time-bounded activity counts plus static absolute neighbor elevation |
| Angular Neighborhood Profile | 15 | 0 | 15 | Pre-cutoff evidenced site activity |
| Cluster context | 5 | 1 | 6 | Static site membership; ID and user-sum alias are display-only |
| Unsupported source KPI fields | 5 | 0 | 5 | UL, RSRP and hourly metrics stay unavailable |
| Cluster previous-month KPI baseline | 7 | 0 | 7 | Raw sums/weighted component ratios in the preceding calendar month |
| Site LTE profile/trends | 10 | 0 | 10 | Three complete pre-cutoff site months |
| Scoped edge / low-latency users | 9 | 0 | 9 | Pre-event sum-over-sum T1/T2/cluster context |
| Population | 3 | 0 | 3 | GHSL 2025 assumed static across event years |
| Road context | 6 | 1 | 7 | Optional current-context retrieval |
| **Total** | **81** | **13** | **94** | Declared fields; not all are weighted or populated |


The family counts above describe the feature catalog. The ranker's current name-based group mapping can place some fields in different weighting groups; see the remaining audit findings.

Flow: source imports -> services/models/features/pipeline.py -> persisted feature tables -> services/models/similarity/feature_vector.py plus pre-event reconstruction and population -> similarity/engine.py and weighting.py -> Similarity Explorer and CBR.

Models contain schema, serializers expose stored fields, and calculation/orchestration belongs in services/. Roads are registered in the shared pipeline used by both Features only and Full sync. Population is computed on demand and needs no feature backfill.

Usage below: similarity means a declared dimension, usable only when eligible, available and weighted. Current policy: geography, stored building-height estimates and population are static by user instruction. Event performance timing stays strict; actual KPI outcomes after the event never fill earlier windows. Cluster IDs and the duplicate user-sum alias are display-only. Earlier dated audit notes describe superseded policies when they conflict with this policy.

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

## 3. Configuration: 15 dimensions

Implementation: services/models/features/context.py::configuration_feature_values. Persisted in ConfigurationFeatures and displayed under KPIs & Config.

Let C be current cells and B be technologies with strictly positive DL traffic before the primary event. Configuration summaries use current inventory; activation events use first-positive traffic months. Historical vectors retain confirmed event labels and traffic-evidenced technology states. Physical configuration now uses KPI-confirmed cells projected to the plan and PRB observations at/before the event month, per the approved policy.

| Fields | Formula / source meaning |
|---|---|
| event_type | Primary persisted canonical event: SITE_ADDED, TECHNOLOGY_ADDED, FREQUENCY_BAND_ADDED, CELL_ADDED, BANDWIDTH_UPGRADE or BANDWIDTH_DOWNGRADE; BASELINE if none |
| tech_added | Technology label(s) of the confirmed TECHNOLOGY_ADDED event; historical vectors join multiple labels with /. The legacy persisted two-character field remains blank for multiple technologies |
| tech_before_2g, tech_before_3g, tech_before_4g | Vector aliases for persisted has_2g_before/has_3g_before/has_4g_before; membership in B |
| tech_after_2g, tech_after_3g, tech_after_4g | Aliases for technology membership in current C |
| bands_added | Historical event metadata supplies band labels for site, technology or frequency-band additions; these describe activated plan membership, not a dated configuration timestamp |
| sector_count_after | Distinct 5-degree azimuth buckets modulo 360, from KPI-confirmed active/added cells joined to the actual plan, no later than the event month |
| cells_per_sector_after | KPI-evidenced after-cell count / sector count; NULL without evidence |
| antenna_height_m | Mean positive plan height for eligible cells; approved 25 m fallback if no real positive value |
| total_bw_after_mhz | Sum LTE MHz mapped from latest PRB observations at/before event month: 25/50/75/100 -> 5/10/15/20, inclusive +/-5 tolerance. Any unknown/unmapped required cell keeps the total NULL |
| total_prb_available | SUM of reported available LTE PRBs over the KPI-evidenced site cells; capacity in PRBs, never Mbps |
| total_capacity_after_mbps | Retained legacy field; unavailable because PRBs are not Mbps. Hidden from the popup configuration; use total_prb_available |

Limits: current cell configuration does not establish event-time configuration. Cell-weighted height overweights sectors with more layers. Absence of 2G/3G activity is not proof of absence. New cells do not prove a new physical sector. Azimuth rounding does not merge 0 and 360 degrees. These require correction in current persisted extraction; historical vectors do not reuse their unsupported values.

## 4. Terrain: 5 dimensions

Implementation: services/models/features/geometric.py and services/visualization/dem_processor.py. Source: DEM and current cell height. Persisted fields appear under Terrain and are declared in similarity.

| Field | Implemented formula / support |
|---|---|
| z_antenna_m | DEM ground + stored building-height estimate + positive plan antenna height (25 m fallback); approved static context |
| terrain_slope_deg | Median degrees(atan(sqrt((dx/sx)^2 + (dy/sy)^2))) in approximate 200 m window |
| terrain_roughness_m | Standard deviation of valid elevation pixels in approximate 1 km window |
| terrain_relief_class | Optional slope-derived prior: <2 flat, 2-<5 rolling, 5-<15 hilly, >=15 steep |
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

All four are eligible for historical use under the explicit static-context assumption. Remaining issues: entropy name/radius mismatch, forest label includes crops/grass, missing cover can become rural/zero, missing building coverage can become zero, overlapping footprints are summed rather than unioned, and height is a synthetic proxy. Verify source CRS for the pre-reprojection footprint bounding-box filter.

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
| neighbor_avg_antenna_height_m | Mean supported absolute neighbor elevation within 2 km: DEM ground + stored building estimate + mast height. NULL with no supported neighbor; 25 m fallback applies only to mast height |

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

| Field | Current similarity/popup definition |
|---|---|
| cluster_id | Inherit Site.cluster_id for all sectors/cells; -1 for noise. Display only, never weighted |
| cluster_size | Number of sites with that static assigned cluster ID; a noise site is its own singleton |
| cluster_density_sites_per_km2 | Static group count / UTM 32N convex-hull area; degenerate hull buffered 100 m |
| cluster_avg_traffic_gb | Mean available site traffic in the cluster during the immediately preceding month |
| cluster_avg_users | Compatibility display alias of the full cluster active-user sum avg_users; not weighted twice |
| dist_to_cluster_centroid_m | UTM distance to the static member-point centroid |

Static membership is shared by user-context ratios, prior-month cluster KPIs and CBR cluster scope. CBR recipients still require pre-cutoff activity/baseline support and exclude the intervention site. The old ClusterFeatures table has latest-month legacy KPI summaries; dynamic similarity/popup baselines override them per requested event cutoff. Summed cell averages are load proxies, not distinct subscribers.

## 8. KPI schemas and user context: 31 declared dimensions

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

Four former legacy keys are now calculated from the immediately preceding cluster month: avg_traffic_dl_gb, avg_users (sum), avg_prb_util_pct and avg_cqi. Three additional cluster fields supply weighted throughput, latency and availability. The remaining five legacy dimensions stay NULL without UL/RSRP/hourly source counters. These values are calculated per cutoff by approved_context.py rather than read from undated PreLaunchKPI rows.

A separate KPIFeatures table is populated/displayed by the legacy pipeline but is not the nine-field similarity schema. Its default path calculates last-prelaunch-month average cell PRB/RRC, traffic per day, and average calendar-time traffic rate (stored as avg_throughput_pre, which is not user throughput). Coverage/gap/segmented-demand fields are not calculated by that path and can retain legacy defaults. Consolidate these schemas rather than treating default zeros as measurements.

### Scoped edge and low-latency users: 9 persisted dimensions (2026-10-26)

Implementation: services/models/features/maos_context.py and preprocessing/maos_aggregation.py. Raw source columns are persisted in MAOSMonthlyKPI; UserContextFeatures stores nine ratios, profile_as_of_date, paired-counter support and updated_at. Additive migration 0008_user_context_counters adds the raw fields and profile table. The requested eedge_user_share uses canonical name edge_user_share.

| Ratio | Numerator | Denominator | Scalar similarity fields |
|---|---|---|---|
| edge_user_share | L.Traffic.User.BorderUE.Avg | L.Traffic.User.Avg | tier1_edge_user_share, tier2_edge_user_share, cluster_edge_user_share |
| edge_user_peak_ratio | L.Traffic.User.BorderUE.Max | L.Traffic.User.BorderUE.Avg | tier1_edge_user_peak_ratio, tier2_edge_user_peak_ratio, cluster_edge_user_peak_ratio |
| lowlatency_user_share | L.Traffic.User.LowLatency.Avg | L.Traffic.User.Avg | tier1_lowlatency_user_share, tier2_lowlatency_user_share, cluster_lowlatency_user_share |

For each scope, ratio = sum(numerator) / sum(denominator), using only rows where both source components are present and nonnegative. Missing pairs are omitted from both sums. The summed denominator must be positive: zero numerator with positive denominator gives real zero; no pairs or zero denominator gives NULL. Do not average per-cell ratios. These are dimensionless ratios, not values multiplied by 100. Sum of cell maxima is not a concurrent network peak or unique subscriber count.

Monthly charts aggregate the paired raw components across cells/sites within each month. Pre-event features pool the components across the three complete calendar months before cutoff, then divide once; they do not take a median or mean of monthly ratios. T1 is distance <=2 km; T2 is 2<distance<=5 km; both exclude the origin. Total cluster includes the origin; noise sites are independent singleton clusters. Historical profile membership is reconstructed from pre-event LTE evidence and can differ from current map membership used in descriptive monthly charts.

The new user_context weighting group appears in the similarity picker and per-case comparison. Available dimensions default selected; unavailable dimensions remain disabled/red. These new dimensions honor explicit deselection in both weighting modes. Existing legacy non-road fallback behavior is otherwise unchanged. Features affect CBR analog ranking; the five existing predicted KPI targets remain unchanged.

KPIs & Config shows a three-ratio by three-scope table with cutoff and missing-reason support. Monthly MAOS Counters exposes the three metrics plus site, Tier 1, Tier 2, total cluster, compare-all-scopes, individual-cell and added-cell selectors. All three scopes can be plotted together. Dedicated Cluster analysis also exposes the three metrics. Charts retain null gaps, preserve real zeros, and show small nonzero shares without rounding them to false zero.

Actual refresh: 890,674 unique linked cell-month rows now contain all three source counters. The targeted import executed 890,925 matching source-row updates, including duplicate cell-month keys, without overwriting unrelated counters; 2,550 source rows remain unmatched. Recalculation persisted all 3,441 profiles: 3,318 have at least one available ratio, 123 have none, zero calculation errors. Across all nine dimensions, 814 unavailable entries have zero denominator and 5,292 lack paired eligible rows. No missing value was invented as zero.

BIZ_0033 pre-event profile, cutoff 2026-10-01:

| Ratio | T1 | T2 | Total reconstructed cluster |
|---|---:|---:|---:|
| Edge user share | 0.377510 | 0.384147 | 0.368182 |
| Edge user peak ratio | 3.643435 | 4.259082 | 4.082592 |
| Low-latency user share | 0 | 0 | 0.0195633 |

All principal persisted feature groups have 3,441 rows. Own-site history can be empty on 2G/3G-only sites because the source report is LTE-only; neighboring scopes can still be available. Legacy PreLaunchKPI has no active producer and historical configuration/clutter/road/population exclusions remain intentional. Recalculation cannot recover report-unsupported RSRP, RRC averages, busy-hour load or congestion duration.

Repeat refresh with python manage.py load_maos_monthly --user-counters-only followed by python manage.py extract_user_context, or recompute through the shared feature-sync pipeline. Recalculate stored profiles after changing source counters. Availability and refresh evidence are in docs/verification/user_context/.

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

All three dimensions are eligible across event years under the approved static-population assumption. They remain GHSL 2025 estimates, not reconstructed annual population. Cache keys include source version and catchment geometry.

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

- equal_per_feature (default): selected available dimensions receive weight 1 before normalization; existing legacy non-road fallback weights remain active until production. Deselected roads and the newly added user_context dimensions are explicit exceptions and contribute zero.
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

Checks executed for the current implementation, including the scoped-user extension on 2026-10-26:

| Check | Observed result |
|---|---|
| Full Django/numerical suite | 41 tests passed, including sum-over-sum, paired missing values, zero denominator, time boundaries, scope membership, import preservation and explicit new-field deselection |
| Django system check | Passed |
| Migration consistency | No pending model changes; additive road migration applied |
| Frontend production build | Passed; existing bundle-size advisory |
| Population/CBR browser checks | Desktop/mobile passed; 20 BIZ_0033 scope/KPI chart combinations compared with API arrays |
| Roads browser checks | Dedicated tab/bars/source date, seven default-off dimensions, explicit group-mode opt-in, actual table weights and <=5% road share passed; no page errors |
| Scoped-user browser checks | Twelve monthly scope/ratio combinations and three dedicated cluster charts matched API arrays; nine picker dimensions and desktop/mobile layout passed with no page errors |
| Scoped-user profile refresh | 3,441 processed; 3,318 have available ratios; 123 have no eligible data; zero calculation errors |
| Road backfill | 3,440 computed, 1 NULL, 0 errors |
| Historical forecast invariance | Future KPI/configuration changes do not alter tested historical forecasts |
| Predictive accuracy / road ablation | Not established; blocked as described above |

Artifacts: docs/verification/user_context/, docs/verification/population/, docs/verification/biz_0033/, docs/verification/roads/ (README, browser-report.json, diagnostics.json, screenshots).

Repeat commands:

```text
python manage.py check
python manage.py test tests
python manage.py makemigrations --check --dry-run
python manage.py extract_road_features
python manage.py extract_road_features --provenance-only
python manage.py road_diagnostics
python manage.py load_maos_monthly --user-counters-only
python manage.py extract_user_context
npm run build                         # from frontend/
python scripts/verify_population_browser.py
python scripts/verify_biz_population_cbr.py
python scripts/verify_road_browser.py
python scripts/verify_user_context_browser.py
```

Browser scripts require local backend/frontend servers, optional Playwright and installed Edge. Feature backfill commands write persisted values; diagnostics are read-only except their report artifact. Ask before destructive migrations. Document source/measurement-method changes and rerun relevant checks before claiming success.


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
| total_bw_after_mhz | For every evidenced LTE cell, use latest nonnegative available-PRB observation no later than event month; map 25/50/75/100 to 5/10/15/20 MHz within inclusive +/-5. Sum only when every required cell maps; otherwise NULL. User explicitly retained strict mapping, not PRB-equivalent estimates. |
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

Actual refresh: 3,441 sites updated, zero errors. Supported persisted counts: 2,706 sector counts, 2,706 PRB capacities, 1,818 complete strictly mapped MHz totals, 3,441 terrain classes, 2,631 neighbor absolute elevations. Missing counts reflect absent LTE evidence, unaligned PRBs or absent neighbors, not imputed zeros. Registry now has 94 declared fields: 81 numeric and 13 categorical, including display-only IDs/aliases and the retained unsupported legacy Mbps field.

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
