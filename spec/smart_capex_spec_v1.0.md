# Smart CAPEX Specification v1.0

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
Configuration is summarized from the current cell plan and the MAOS history
available before the detected event. A launch observation is the first month
in which the object's recorded KPIs are all zero or absent; this is the event
date stored by addition detection. For monthly data, the stored date is the
month date, not an inferred day within that month.

1. `event_type`: `NEW_SITE` when all technologies in the site plan launch in
   the same month; `TECH_ADD` when the event introduces a technology with no
   pre-event MAOS KPI activity; `SECTOR_ADD` when a cell is added on a
   technology with prior activity; otherwise `BASELINE`. `BAND_ADD`,
   `CAPACITY_ADD`, and `TECH_SUNSET` are reserved until historical cell-plan
   snapshots or explicit event records are available.
2. `tech_added`: The sole newly serving technology (2G/3G/4G), when exactly
   one can be identified; blank for multiple or no technologies.
3. `tech_before`: Binary vector `[has_2g, has_3g, has_4g]`, true only when a
   pre-event MAOS record for that technology has at least one nonzero KPI.
   Zero/absent-only history does not count as prior service.
4. `tech_after`: Binary vector `[has_2g, has_3g, has_4g]` from technologies
   present in the current cell plan.
5. `bands_added`: Historical band additions. Leave blank when there is no
   pre-event cell-plan snapshot to establish that a band is new; current band
   names alone are not evidence of an addition.
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
- **Launch Detection**: KPI-observation-based. The event date is the first monthly observation in which all nine modeled KPIs for the object are zero or absent; the first collected month is the observation baseline and cannot itself establish a later addition.

#### Cell Addition Detection
  - Evaluate each cell independently across all nine modeled KPI fields. A cell's addition date is its first monthly observation where all KPIs are zero or absent, provided that observation is after the first collected month; do not wait for a subsequent nonzero month to date the addition.
  - Detect qualifying new cells even when the same technology already serves the site. Classify a whole site as `SITE_ADDED` only when all technologies in its cell plan have the same qualifying zero-KPI observation month. Otherwise classify added-cell events by technology.
  - The popup supports both site aggregates and per-cell monthly KPI series, with detected cells highlighted.
    - Detection results are joined to existing cell-plan cell IDs. Map markers use addition icons while their popups retain the site's previously calculated terrain, clutter, spatial, ANP, and KPI features and show cell-plan configuration for each sector.
- Evaluate all nine modeled monthly MAOS KPI fields per cell. The addition date is the first post-baseline month with all KPI values zero or absent.
- A cell with any nonzero KPI in an earlier month is not considered newly added at a later zero month.
- If every technology currently present at a site has the same qualifying zero-KPI observation month, classify the event as `SITE_ADDED`; otherwise classify detected cell events by technology.
- A technology can have a newly added cell even if it was already active through another cell.
- Store the detected month on each added cell; a new site stores its common first-activity month.
- The map provides distinct event icons and an event-type filter. Site and cell name searches open the matching site's popup and identify matching cells.
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
Progressive filtering to find similar cases:
1. **Tier 1**: Same event_type (e.g., NEW_SITE)
2. **Tier 2**: Same dominant_clutter (e.g., urban)
3. **Tier 3**: Similar ANP edge_score (±0.2)
4. **Tier 4**: Geographic proximity (<20km)

### 6.3 Kernel Weights
Gaussian kernel for distance-based weighting:
```
w(d) = exp(-d² / (2σ²))
```
Where σ = bandwidth parameter (tuned via validation)

### 6.4 Prediction Output
For each target site, provide:
- Top-K similar cases (K=10-20)
- Predicted impact (coverage, PRB, users)
- Bootstrap confidence intervals (95%)
- Local linear model coefficients
- Feature importance for explanation

---

## 7. Visualization Requirements

### 7.1 Cluster Maps (Folium)
Interactive HTML maps showing:
- Site markers color-coded by cluster_id
- Cluster polygon boundaries (alpha shapes)
- Out-of-bounds sites highlighted in RED
- Edge sites with orange markers
- Interior sites with green markers
- Popups with site details and cluster stats

### 7.2 Edge Score Heatmap
Heatmap visualization of ANP edge_score:
- Color gradient: green (infill) → yellow → red (edge)
- Circle markers at site locations
- Tooltip with edge_score value

### 7.3 GeoJSON Export
Export clustering results to standard GeoJSON format:
- Point geometries for sites
- Properties: All cluster features
- Compatible with GIS tools (QGIS, ArcGIS)

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
