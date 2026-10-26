# Smart CAPEX Phase 1 Data Catalog

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
