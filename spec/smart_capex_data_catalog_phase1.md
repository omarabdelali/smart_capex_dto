# Smart CAPEX Phase 1 Data Catalog

## Scoped user ratios and source refresh (2026-10-26)

Source: the existing monthly CSV under `data/maos/smart_capex_LTE_monthly_Query_Result_20261023105420501/`. Header and report XML confirm all four source counters. Canonical requested `eedge_user_share` is named `edge_user_share`.

| Source counter | Nullable model field | Ratio use |
|---|---|---|
| L.Traffic.User.BorderUE.Avg | border_user_avg | Edge-share numerator, peak-ratio denominator |
| L.Traffic.User.BorderUE.Max | border_user_max | Peak-ratio numerator |
| L.Traffic.User.LowLatency.Avg | lowlatency_user_avg | Low-latency-share numerator |
| L.Traffic.User.Avg | traffic_user_avg | Edge/low-latency-share denominator |

Calculate each ratio as sum over sum on paired, nonnegative, nonmissing rows. All values are dimensionless ratios, not percentages. Sum of cell maxima is not a simultaneous network peak. Zero numerator is retained; a zero denominator or absent pairs stays NULL. Store nine scoped features in UserContextFeatures, with cutoff and numerator/denominator/support metadata. Pre-event features pool components over three complete calendar months; monthly scope series divide each month's sums. Tier 1 <=2 km, Tier 2 >2 to <=5 km exclude origin; total cluster includes origin. Historical and current geographic membership are labeled separately.

Targeted import: 893,475 source rows read, 890,925 linked update operations, 2,550 unmatched rows, one invalid-date row. Update operations include duplicate cell-month keys; there are **890,674 unique stored cell-months**, all now populated with the three raw counters. Existing unrelated KPIs were preserved.

Persisted profile refresh: 3,441 processed, 3,318 with at least one available ratio, 123 all unavailable, zero errors. Across nine dimensions, unavailable reasons are 814 zero denominators and 5,292 no paired eligible rows. Available counts (T1/T2/cluster): edge share 2,568/2,778/3,213; peak ratio 2,375/2,533/2,837; low-latency share 2,568/2,778/3,213.

Current registry: **89 scalar dimensions, 77 numeric and 12 categorical**. Repeat source update with `load_maos_monthly --user-counters-only`, then `extract_user_context` or the shared feature-sync pipeline. Reports: `docs/verification/user_context/`.

## Road source and persisted features (2026-10-26)

- Source: existing `data/geographic/osm/tunisia.gpkg`, `gis_osm_roads_free`; source class field `fclass`. Local archive: `data/geographic/osm/tunisia-latest-free.gpkg.zip`. README attests data as of **2026-10-22T20:21:33Z**, verified by matching the archived GeoPackage SHA-256 to the imported file. No download performed; historic download date unknown. Recorded URL: https://download.geofabrik.de/africa/tunisia-latest-free.gpkg.zip . Normalized/prepared on 2026-10-26; all rows store extract date 2026-10-22.
- Licence: ODbL 1.0, attribution **© OpenStreetMap contributors; Geofabrik**. Retain attribution and applicable derived-database obligations when distributing data.
- Source SHA-256: `2a149398d4d13f78def1189299110a3ef18c4dc9da20401f3b4f51a659f7ba8f`.
- Normalized EPSG:32632 file: `data/geographic/osm/roads_utm32_2a149398d4d1.gpkg`, layer `roads`, spatial index enabled. SHA-256: `66ac9c0aa0bf1ac8e34a031dd770000127aeccf261389d0847a573c62eb84a72`. Manifest is stored alongside it as JSON. Source normalization retains 397,936 road features including any-class coverage evidence. `_link` maps to parent; retained length classes are motorway, trunk, primary, secondary, tertiary, residential, unclassified.
- Optional attributes retained: maxspeed, bridge, tunnel, layer; lanes absent → NULL. Original OSM-node topology is unavailable.
- Configuration: `config/road_context.json`; priors motorway/trunk 1, primary .7, secondary .5, tertiary .3, residential/unclassified .1, unknown .05 (excluded unknown classes). Calibration: **prior, uncalibrated**. Similarity road cap .05 is also an uncalibrated safeguard.
- Persisted fields: `road_km_total`, `road_km_weighted`, `road_density_weighted_km_km2`, `highway_km`, `highway_share` (0–1), `n_road_intersections` (estimated), `dominant_road_class`; source/hash, buffer, method/weights versions, coverage status, class lengths and update timestamp. See `feature_eng.md` for exact formulas and topology limits.
- No source road within 5 km → all measurements NULL; nearby mapping with no retained class in 1 km → zero lengths/counts, NULL share/dominant. One buffer per site; revisit duplicate contributions before any cell-wedge footprint implementation.
- Actual backfill: 3,441 sites; 3,440 computed (including ten zero-length sites), one NULL (KEB_0044 / 5295), zero errors. Seven new dimensions bring the scalar registry to 80 (68 numeric, 12 categorical).
- Correlation/VIF report: `docs/verification/roads/diagnostics.json`. Weighted length and density are exact duplicates at fixed buffer area; keep optional. Historical predictive ablation is blocked because the 2026-10-22 source postdates the historical launches and earlier snapshots are absent; no KPI errors or model gains are asserted.

## Latest coastal coverage correction (2026-10-26)

This supersedes the 90%-coverage exclusion rule below. Population fields now return the mapped fractional-overlap count whenever source population cells exist. Partial land coverage is disclosed in `quality` (site inspector) / `population_quality` (similarity and CBR) with per-catchment `coverage`, `land_coverage`, `water_pct`, `status` and `observed_population`. Independently identified WorldCover water supports coverage; unknown land is never filled or extrapolated. Density divides mapped counts by full catchment area. Ninety percent overall and land coverage marks complete status; lower coverage returns supported numeric values explicitly labeled partial. With no supported cells or known water, values remain unavailable.

For BIZ_0033: density ≈2,841.7 people/km², T1 ≈27,089.8 people and T2 ≈56,588.7 people; these are partial mapped estimates with land coverage ≈72.7%, 78.8% and 74.3% respectively, not complete catchment totals.

## Population similarity extension (2026-10-26)

Source: local `data/geographic/ghsl/ghs_pop_e2025_r2023a_54009_100_v1_0_tun.tif`, GHSL R2023A epoch 2025, native 100 m Mollweide equal-area grid, residents per cell; nodata -200. Computed on demand in `services/models/features/population.py` with fractional cell-overlap weighting and at least 90% valid coverage per catchment.

| Field | Unit | Spatial support | Availability / consumer |
|---|---|---|---|
| `population_density_1km_per_km2` | people/km² | 0–1 km disk | Similarity/CBR numeric feature, missing before 2025 or insufficient coverage |
| `population_tier1` | people | 0–2 km disk | Similarity/CBR numeric feature; picker/comparison, CBR page and current site inspector |
| `population_tier2` | people | 2–5 km annulus excluding T1 | Same; independently subject to coverage/epoch rules |

Measured zero is retained; missing remains NULL in API vectors. Population is fixed 2025 modeled context, not historical event-time reconstruction. Current inspector values are source-labeled and separate from as-of eligibility. Numeric/categorical similarity schema now has 62/11 declared dimensions. Existing deselected-feature behavior is retained until production.

Historical features use the three complete pre-event calendar months. Current configuration and undated legacy fields do not supply historical inputs. Neighbor/ANP/cluster context is rebuilt from pre-event LTE activity; CBR cases and outcome months must precede the query event month. See `feature_eng.md` for formulas and source limitations.

**Version:** 1.1
**Date:** 2026-10-23
**Scope:** 2G / 3G / 4G Feature Data Sources & Requirements
**Owner:** Smart CAPEX Project Team

---

## Table of Contents

1. [Overview](#1-overview)
2. [Data Source Summary](#2-data-source-summary)
3. [Configuration Features (10)](#3-configuration-features-10)
4. [Geometry Features (4)](#4-geometry-features-4)
5. [Clutter/Topology Features (4)](#5-cluttertopology-features-4)
6. [Spatial Context Features (23)](#6-spatial-context-features-23)
7. [Pre-Launch State Features (9 Phase 1, 3 Phase 2)](#7-pre-launch-state-features-9-phase-1-3-phase-2)
8. [Cluster Context Features (6)](#8-cluster-context-features-6)
9. [Phase 2 Exclusions](#9-phase-2-exclusions)
10. [Data Quality Requirements](#10-data-quality-requirements)
11. [Known Limitations](#11-known-limitations)
12. [LTE Monthly Operational KPI Extension](#12-lte-monthly-operational-kpi-extension-increment-1)

---

## 1. Overview

This catalog maps all 56 Phase 1 features to their data sources, formulas, and availability status. Phase 1 covers 2G/3G/4G technologies using Huawei MAOS LTE counters.

**Phase 1 feature count:** 56 (59 total including 3 Phase 2 features)

---

## 2. Data Source Summary

| Data Source                     | Type                 | Update Frequency | Availability | Notes                                                    |
| ------------------------------- | -------------------- | ---------------- | ------------ | -------------------------------------------------------- |
| **Cell Plan**                   | Database/CSV         | Daily            | ✓ Available  | Historical snapshots required (3 years)                  |
| **Huawei MAOS**                 | Performance counters | 15-min intervals | ✓ Available  | MAOS LTE daily/weekly/monthly counters                   |
| **Copernicus DEM GLO-30**       | GeoTIFF              | Static           | ✓ Available  | 30m resolution, ~2m vertical accuracy                    |
| **ESA WorldCover v200**         | GeoTIFF              | Annual           | ✓ Available  | 10m land cover, 11 classes                               |
| **OSM Buildings (Tunisia)**     | Vector (GeoJSON/SHP) | Annual           | ✓ Available  | Building footprints with variable completeness           |
| **GHSL Built Heights**          | GeoTIFF              | Static           | ✓ Available  | 100m mean building height (GHS-BUILT-H R2023A)           |
| **IMEI-Subscriber DB**          | Database             | Real-time        | ✗ Phase 2    | Required for device segmentation                         |

**Source Files:** `spec/data_spec/smart_capex_LTE_daily_1792747652750.xml` (report counter selection), `eRAN_KPI_Reference_22.1.xlsx`, and `counter_summary_ratL_22.1_en.xlsx`. The monthly CSV export contains 132 report-selected counter headers plus report metadata/derived columns.

---

## 3. Configuration Features (10)

### 3.1 event_type

**Description:** Type of launch event
**Data Source:** Cell Plan History (KPI-based launch detection)
**Type:** Categorical
**Values:** NEW_SITE, TECH_ADD, BAND_ADD, SECTOR_ADD, CAPACITY_ADD, TECH_SUNSET
**Computation:**

```python
# KPI-based detection: first timestamp where cell had data traffic
# Cell "never had data before T" = L.Traffic.User.Avg == 0 AND L.Thrp.bits.DL == 0 for all T' < T
if site_id not in cellplan_T_minus_30:
    event_type = "NEW_SITE"
elif new_tech in (cellplan_T_plus_1 - cellplan_T_minus_30):
    event_type = "TECH_ADD"
elif new_band in (cellplan_T_plus_1 - cellplan_T_minus_30):
    event_type = "BAND_ADD"
elif len(sectors_T_plus_1) > len(sectors_T_minus_30):
    event_type = "SECTOR_ADD"
elif total_bw_T_plus_1 > total_bw_T_minus_30:
    event_type = "CAPACITY_ADD"
elif old_tech in (cellplan_T_minus_30 - cellplan_T_plus_1):
    event_type = "TECH_SUNSET"
```

### 3.2 tech_added

**Description:** Technology being added
**Data Source:** Cell Plan diff
**Type:** Categorical
**Values:** 2G, 3G, 4G
**Computation:** Set difference of active technologies between T-30d and T+1d

### 3.3 tech_before

**Description:** Technologies active before launch
**Data Source:** Cell Plan at T-30d
**Type:** Binary vector [2G, 3G, 4G]
**Computation:**

```python
tech_before = [
    any(cell.technology == "2G" for cell in active_cells_T_minus_30),
    any(cell.technology == "3G" for cell in active_cells_T_minus_30),
    any(cell.technology == "4G" for cell in active_cells_T_minus_30)
]
```

### 3.4 tech_after

**Description:** Technologies active after launch
**Data Source:** Derived from tech_before ∪ tech_added
**Type:** Binary vector [2G, 3G, 4G]
**Computation:** Union of tech_before and tech_added

### 3.5 bands_added

**Description:** Frequency bands being added
**Data Source:** Cell Plan diff
**Type:** Binary vector [GSM900, GSM1800, UMTS900, UMTS2100, B20, B3, B1]
**Computation:** Set difference of active bands between T-30d and T+1d

### 3.6 sector_count_after

**Description:** Number of sectors after launch
**Data Source:** Cell Plan at T+1d
**Type:** Integer
**Range:** 1-6
**Computation:**

```python
sector_count_after = len(set(cell.azimuth for cell in active_cells_T_plus_1))
```

### 3.7 cells_per_sector_after

**Description:** Average cells per sector
**Data Source:** Cell Plan at T+1d
**Type:** Float
**Range:** 1-8
**Computation:**

```python
cells_per_sector_after = total_cells_T_plus_1 / sector_count_after
```

### 3.8 antenna_height_m

**Description:** Physical antenna height above ground
**Data Source:** Cell Plan
**Type:** Float
**Range:** 10-55 m
**Unit:** meters
**Availability:** ✓ Available in cell plan

### 3.9 total_bw_after_mhz

**Description:** Total bandwidth after launch
**Data Source:** Cell Plan at T+1d
**Type:** Float
**Range:** 5-100 MHz
**Computation:**

```python
total_bw_after_mhz = sum(cell.bandwidth_mhz for cell in active_cells_T_plus_1)
```

### 3.10 total_capacity_after_mbps

**Description:** Total theoretical capacity
**Data Source:** Computed from cell plan
**Type:** Float
**Range:** 50-2000 Mbps
**Computation:**

```python
total_capacity_after_mbps = sum(
    cell.bandwidth_mhz * spectral_efficiency[cell.tech] * mimo_layers[cell.tech]
    for cell in active_cells_T_plus_1
)
# spectral_efficiency: {2G: 0.3, 3G: 0.8, 4G: 3.5} bps/Hz
# mimo_layers: {2G: 1, 3G: 1, 4G: 2}
```

---

## 4. Geometry Features (4)

### 4.1 z_antenna_m

**Description:** Antenna elevation above sea level
**Data Source:** Copernicus DEM GLO-30 + Cell Plan
**Type:** Float
**Range:** 30-200 m
**Computation:**

```python
z_antenna_m = DEM.sample(site.lon, site.lat) + site.antenna_height_m
```

**DEM Requirements:** Copernicus DEM GLO-30 (30m horizontal resolution, ~2m vertical accuracy)

### 4.2 terrain_slope_deg

**Description:** Median terrain slope around site
**Data Source:** Copernicus DEM GLO-30
**Type:** Float
**Range:** 0-25°
**Computation:**

```python
# Compute gradient in 200m buffer
gradient_x, gradient_y = np.gradient(DEM_200m_buffer)
slope_rad = np.arctan(np.sqrt(gradient_x**2 + gradient_y**2))
terrain_slope_deg = np.median(np.degrees(slope_rad))
```

### 4.3 terrain_roughness_m

**Description:** Terrain elevation variability
**Data Source:** Copernicus DEM GLO-30
**Type:** Float
**Range:** 0-40 m
**Computation:**

```python
terrain_roughness_m = np.std(DEM.sample_buffer(site.lon, site.lat, radius=1000))
```

### 4.4 terrain_aspect_deg

**Description:** Direction of terrain slope
**Data Source:** Copernicus DEM GLO-30
**Type:** Float (circular)
**Range:** 0-360°
**Computation:**

```python
gradient_x, gradient_y = np.gradient(DEM_200m_buffer)
terrain_aspect_deg = (np.degrees(np.arctan2(-gradient_y, gradient_x)) + 360) % 360
```

---

## 5. Clutter/Topology Features (4)

### 5.1 dominant_clutter

**Description:** Most common land use type
**Data Source:** ESA WorldCover v200
**Type:** Categorical
**Values:** urban, suburban, rural, water, forest
**Computation:**

```python
clutter_buffer = clutter_raster.sample_buffer(site.lon, site.lat, radius=500)
dominant_clutter = mode(clutter_buffer)
```

**WorldCover Classes (remapped to 5 categories):**
- Urban: Built-up (50)
- Suburban: Herbaceous wetland (90), Moss and lichen (100)
- Rural: Cropland (40), Grassland (30)
- Water: Permanent water bodies (80)
- Forest: Tree cover (10), Shrubland (20), Mangroves (95)

### 5.2 clutter_entropy_2km

**Description:** Diversity of land use types
**Data Source:** ESA WorldCover v200
**Type:** Float
**Range:** 0-1.5
**Computation:**

```python
clutter_buffer = clutter_raster.sample_buffer(site.lon, site.lat, radius=2000)
counts = np.bincount(clutter_buffer)
probabilities = counts / counts.sum()
clutter_entropy_2km = -sum(p * np.log2(p) for p in probabilities if p > 0)
```

### 5.3 pct_building_area_1km

**Description:** Percentage covered by buildings
**Data Source:** OSM Buildings (Tunisia extract)
**Type:** Float
**Range:** 0-90%
**Computation:**

```python
buffer_area = np.pi * 1000**2  # 1km radius
buildings_in_buffer = building_footprints.intersect(buffer_1km)
building_area = sum(building.area for building in buildings_in_buffer)
pct_building_area_1km = (building_area / buffer_area) * 100
```

### 5.4 avg_building_height_m

**Description:** Average building height
**Data Source:** GHSL Built Heights (GHS-BUILT-H R2023A)
**Type:** Float
**Range:** 0-40 m
**Computation:**

```python
# Sample 100m resolution mean building height raster
avg_building_height_m = GHSL_height_raster.sample(site.lon, site.lat)

# If no GHSL data, fallback to OSM building height attribute
if avg_building_height_m is None and OSM_buildings_available:
    buildings_in_buffer = building_footprints.intersect(buffer_1km)
    avg_building_height_m = mean(building.height for building in buildings_in_buffer if building.height > 0)

# If still no data, use clutter-based default
if avg_building_height_m is None:
    height_defaults = {"urban": 18, "suburban": 8, "rural": 4, "water": 0, "forest": 0}
    avg_building_height_m = height_defaults[dominant_clutter]
```

**Note:** GHSL provides mean building height at 100m resolution; OSM buildings may have height tags but coverage is variable

---

## 6. Spatial Context Features (23)

### 6.1-6.8 Legacy Spatial Features (8)

#### 6.1 dist_nearest_site_m

**Data Source:** Cell Plan
**Computation:** `min(haversine(site, neighbor) for neighbor in all_sites)`
**Range:** 50-2950 m

#### 6.2 n_sites_1km

**Data Source:** Cell Plan
**Computation:** Count of sites with `haversine(site, neighbor) <= 1000`
**Range:** 0-10

#### 6.3 n_sites_2km

**Data Source:** Cell Plan
**Computation:** Count of sites with `haversine(site, neighbor) <= 2000`
**Range:** 0-25

#### 6.4 n_sites_3km

**Data Source:** Cell Plan
**Computation:** Count of sites with `haversine(site, neighbor) <= 3000`
**Range:** 0-50

#### 6.5 n_2g_sites_2km

**Data Source:** Cell Plan
**Computation:** Count of sites with 2G technology within 2km
**Range:** 0-25

#### 6.6 n_3g_sites_2km

**Data Source:** Cell Plan
**Computation:** Count of sites with 3G technology within 2km
**Range:** 0-25

#### 6.7 n_4g_sites_2km

**Data Source:** Cell Plan
**Computation:** Count of sites with 4G technology within 2km
**Range:** 0-25

#### 6.8 neighbor_avg_antenna_height_m

**Data Source:** Cell Plan
**Computation:** Mean antenna height of sites within 2km
**Range:** 10-55 m

### 6.9-6.23 Angular Neighborhood Profile (ANP) Features (15)

**All ANP features are computed from Cell Plan using the following algorithm:**

```python
def compute_anp(site, all_sites, tier1_m=2000, tier2_m=5000):
    # Compute distances and bearings
    neighbors = []
    for neighbor in all_sites:
        if neighbor.id == site.id:
            continue
        dist = haversine(site.lat, site.lon, neighbor.lat, neighbor.lon)
        bearing = compute_bearing(site.lat, site.lon, neighbor.lat, neighbor.lon)
        neighbors.append({'dist': dist, 'bearing': bearing})
  
    tier1 = [n for n in neighbors if n['dist'] <= tier1_m]
    tier2 = [n for n in neighbors if tier1_m < n['dist'] <= tier2_m]
  
    return {
        'n_tier1': len(tier1),
        'n_tier2': len(tier2),
        't1_to_t2_ratio': len(tier1) / max(len(tier2), 1),
        't1_nearest_m': min((n['dist'] for n in tier1), default=tier1_m),
    }
```

## 12. LTE Monthly Operational KPI Extension (Increment 1)

This operational profile is an extension for analysis and similarity inputs; it does not silently redefine the existing 55-feature specification. It uses fields confirmed in the monthly LTE CSV and records unobservable KPIs as NULL rather than zero.

| Cell-month measure | CSV input(s) | Derivation / aggregation basis |
| --- | --- | --- |
| Downlink traffic | `L.Thrp.bits.DL(bit)` | Retain raw bits; site/cluster values sum cell counters. |
| Average users and active users | `L.Traffic.User.Avg`, `L.Traffic.ActiveUser.Avg` | Retain cell averages; site/cluster sum concurrent cell averages for network-level totals. |
| DL PRB utilization | `L.ChMeas.PRB.DL.Used.Avg`, `L.ChMeas.PRB.DL.Avail` | `used / available * 100`; retain both inputs so rollups use `sum(used) / sum(available)`. |
| CQI | `L.ChMeas.CQI.DL.0` through `.15` | Weighted mean from the 16-bin histogram; retain weighted sum and sample count for rollups. |
| DL throughput | `L.Thrp.bits.DL(bit)`, `L.Thrp.bits.DL.LastTTI(bit)`, `L.Thrp.Time.DL.RmvLastTTI(ms)` | `(DL bits - LastTTI bits) / milliseconds` gives kbit/s; retain components for weighted rollups, as defined in the eRAN KPI reference. |
| DL packet delay | `L.Traffic.DL.PktDelay.Time(ms)`, `L.Traffic.DL.PktDelay.Num(packet)` | `delay time / packet count` in ms; retain both components for weighted rollups. |
| Cell availability | `L.Cell.Unavail.Dur.Sys(s)` | `100 * (1 - downtime / calendar month seconds)`; retain downtime and observation duration for rollups. |

Current LTE export limitations: UL throughput, UL PRB, downlink RSRP average, RRC connection average, and several accessibility/handover rates are not derived from this report. A KPI in the reference workbook is not considered populated unless its input counters are actually present in the export.


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
