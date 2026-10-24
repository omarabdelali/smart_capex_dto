# Smart CAPEX Specification Changelog v1.0

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
**Author**: Smart CAPEX Development Team  
**Status**: Specification Finalized, Implementation In Progress