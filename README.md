# Smart CAPEX Phase 1 - Similarity-Based Site Attribution

**Predict telecom network site impact using case-based reasoning and geographic analysis**

Version: 0.1.0  
Status: Development  
Scope: 2G/3G/4G (Phase 1)

---

## 📋 Overview

Smart CAPEX Phase 1 answers one critical question:

> *"If I build this site at this location with this configuration, what will the impact be — and what is the NPV?"*

The system uses **similarity-based reasoning** to find the most similar historical launches from the past 3 years and uses their measured, causal-cleaned outcomes to predict a proposed site's impact.

### Key Innovation: Angular Neighborhood Profile (ANP)

The system distinguishes **edge sites** (coverage extension) from **infill sites** (capacity relief) using 360° spatial analysis of neighboring sites. This 15-feature profile is the key differentiator that enables accurate predictions.

---

## 🏗️ Architecture

**Django MVT + Services Layer (MVC Pattern):**

Smart CAPEX follows a strict Model-View-Controller architecture with clear separation of concerns:

```
project_smart_capex/
├── core/                    # Django app (Models + Views)
│   ├── models/              # DATABASE MODELS ONLY
│   │   ├── site.py          # Site model
│   │   ├── cell.py          # Cell model
│   │   ├── features.py      # Feature models (Config, Geo, Clutter, Spatial, ANP, Cluster)
│   │   ├── kpi.py           # KPI models (PreLaunch, MAOS)
│   │   └── __init__.py      # Public exports
│   ├── views/               # API ENDPOINTS ONLY
│   │   ├── site_views.py    # Site API (SiteViewSet)
│   │   ├── cell_views.py    # Cell API (CellViewSet)
│   │   └── __init__.py      # Public exports
│   ├── serializers/         # DATA TRANSFORMATION
│   │   ├── site_serializers.py   # Site, GeoJSON serializers
│   │   ├── cell_serializers.py   # Cell serializer
│   │   └── __init__.py      # Public exports
│   ├── management/commands/ # Django commands
│   ├── admin.py             # Admin site config
│   └── urls.py              # URL routing
├── services/                # BUSINESS LOGIC ONLY
│   ├── models/              # Data processing & ML
│   │   ├── preprocessing/   # Launch detection, DiD cleaning, clustering
│   │   ├── features/        # ANP, geography, spatial, config extraction
│   │   ├── similarity/      # Gower distance, hierarchical CBR
│   │   └── prediction/      # Kernel weights, bootstrap CI
│   ├── visualization/       # Map rendering
│   │   └── geo_visualization/  # Folium map generation
│   └── utils/               # Shared utilities (geo, config)
├── frontend/                # Vue.js frontend
│   ├── src/
│   │   ├── components/      # Vue components (ClusterMapView)
│   │   ├── App.vue          # Main app
│   │   └── main.js          # Entry point
│   └── index.html           # HTML template
├── smart_capex_backend/     # Django project settings
│   ├── settings.py          # Project configuration
│   └── urls.py              # Root URL config
├── data/                    # Data storage
│   ├── cellplan/            # Cell plan history
│   ├── geographic/          # DEM, clutter, buildings
│   └── maos/                # Huawei MAOS counters
├── spec/                    # Detailed specification
├── tests/                   # Test suite
├── notebooks/               # Jupyter notebooks
├── scripts/                 # Utility scripts
├── .clinerules/             # Development guidelines
└── .tracking/               # Progress tracking
```

### Architecture Principles

**Three-Layer Separation:**
1. **Models (core/models/)** - Django ORM models, database schema ONLY
2. **Views (core/views/)** - REST API endpoints, HTTP request/response ONLY  
3. **Services (services/)** - ALL business logic (data loading, feature engineering, clustering, similarity, prediction)

**Key Rules:**
- ❌ NO business logic in models or views
- ✅ ALL data processing, calculations, ML algorithms in services/
- ✅ Views call services layer for business logic
- ✅ Models define database structure only
- ✅ Clean imports: Models → Serializers → Views → Services (one-way)

See `.clinerules/mvc-architecture.md` for detailed architecture guidelines.

---

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- 8GB RAM minimum
- Git

### Installation

1. **Clone the repository:**
```bash
cd "c:\My Program Files\E2E\smart capex"
# Repository already exists at project_smart_capex/
```

2. **Create virtual environment:**
```bash
cd project_smart_capex
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac
```

3. **Install dependencies:**
```bash
pip install -r requirements.txt
```

4. **Download geographic data** (see [Data Acquisition](#data-acquisition))

5. **Configure project:**
```bash
cp config.example.yaml config.yaml
# Edit config.yaml with your data paths
```

---

## 📊 Data Requirements

### Cell Plan Data
- **Format:** Excel (.xlsx)
- **Location:** `data/cellplan/`
- **Contents:** Site locations, azimuths, antenna heights, bands, technologies
- **History:** 3 years minimum

### MAOS Counters (Huawei M2000)
- **Format:** CSV or Parquet
- **Location:** `data/maos/`
- **Granularity:** Daily minimum
- **KPIs Required:** 
  - `L.Traffic.User.Avg` (traffic users)
  - `L.Thrp.bits.DL` (throughput)
  - PRB utilization
  - RRC connected users
  - Latency (P95)

### Geographic Data

#### 1. Copernicus DEM GLO-30
- **Source:** https://portal.opentopography.org/
- **Coverage:** Tunisia tiles N30E007 to N38E012
- **Resolution:** 30m
- **Location:** `data/geographic/dem/`

#### 2. ESA WorldCover v200
- **Source:** https://esa-worldcover.org/
- **Coverage:** Tunisia
- **Resolution:** 10m
- **Location:** `data/geographic/worldcover/`

#### 3. OSM Buildings
- **Source:** https://download.geofabrik.de/africa/tunisia.html
- **Format:** GeoJSON/Shapefile
- **Location:** `data/geographic/osm/`

#### 4. GHSL Built Heights
- **Source:** https://ghsl.jrc.ec.europa.eu/
- **Resolution:** 100m
- **Location:** `data/geographic/ghsl/`

---

## 🔧 Development Workflow

### Phase 1a: Foundation (Current)
- [x] MVC project structure
- [x] Progress tracking system
- [ ] Geographic utilities (haversine, bearing)
- [ ] Data loaders (Excel, CSV, GeoTIFF)
- [ ] Configuration management

### Phase 1b: Feature Engineering (Weeks 3-5)
- [ ] **ANP computation** (KEY INNOVATION)
- [ ] Geographic features (DEM, clutter, buildings)
- [ ] Spatial features (neighbor counts)
- [ ] Pre-launch KPI features

### Phase 1c: Similarity Engine (Weeks 6-8)
- [ ] Gower distance (mixed features)
- [ ] Hierarchical CBR filter
- [ ] Kernel weighting

### Phase 1d: Prediction & API (Weeks 9-10)
- [ ] Prediction orchestrator
- [ ] Bootstrap confidence intervals
- [ ] Local linear explanation
- [ ] REST API (POST /api/predict/)

### Phase 1e: Validation & UI (Weeks 11-12)
- [ ] LOO cross-validation
- [ ] ANP ablation test
- [ ] Folium map visualization

**See `.tracking/progress.md` for detailed task tracking.**

---

## 🎯 Key Features

### 57 Features in Phase 1

| Group | Weight | Count | Examples |
|-------|--------|-------|----------|
| Configuration | 0.28 | 10 | event_type, tech_added, bands, antenna_height |
| Pre-launch State | 0.27 | 9 | coverage_gap, PRB, RRC, throughput |
| **Spatial (ANP)** | **0.20** | **23** | **edge_score, angular_gap, sector_imbalance** |
| Clutter | 0.13 | 4 | dominant_clutter, building_area, building_height |
| Geometry | 0.05 | 4 | z_antenna, slope, roughness, aspect |
| Cluster | 0.05 | 6 | cluster_size, tech_mix |

### Angular Neighborhood Profile (15 features)

**The Innovation:**
- Distinguishes edge sites (neighbors in 120° arc) from infill sites (neighbors in 360°)
- 360° rotation analysis with 12 bins of 30°
- Key metrics: `edge_score` (1=edge, 0=infill), `angular_gap`, `sector_empty_count`

**Why it matters:**
- Two sites with same `n_sites_2km=5` can have radically different economics
- Edge sites → coverage gain
- Infill sites → capacity relief
- Without ANP, model predicts average → wrong for both

---

## 🧪 Testing

### Run Unit Tests
```bash
pytest tests/ -v
```

### Run ANP Validation
```bash
pytest tests/test_anp.py -v
```

### Visual Validation
```bash
jupyter notebook notebooks/03_anp_visualization.ipynb
```

---

## 📖 Documentation

- **Full Specification:** `spec/smart_capex_spec_v0.md` (1,679 lines)
- **Feature Schema:** `spec/smart_capex_features.csv` (60 features)
- **Progress Tracker:** `.tracking/progress.md`
- **Cline Rules:** `.clinerules/smart-capex-project.md`

---

## 🎓 API Usage

### Predict Site Impact

**Endpoint:** `POST /api/predict/`

**Request:**
```json
{
  "proposal": {
    "lon": 10.242,
    "lat": 36.852,
    "antenna_height_m": 25,
    "sector_count": 3,
    "technology": "4G",
    "bands": ["B3_1800", "B20_800"]
  }
}
```

**Response:**
```json
{
  "anp": {
    "edge_score": 0.575,
    "angular_gap_deg": 240,
    "classification": "EDGE_SITE"
  },
  "prediction": {
    "delta_coverage_ratio": {"point": 0.172, "low": 0.13, "high": 0.21},
    "delta_prb": {"point": -18.3, "low": -22.0, "high": -14.0}
  },
  "financial": {
    "npv_usd": 78000,
    "payback_years": 1.8
  },
  "similar_cases": [
    {"site": "SITE_0089", "distance": 0.018, "npv": 78000}
  ],
  "explanation": {
    "summary": "Coverage gain of +17.2pp driven by high pre-launch PRB (78%), empty sector facing 240°, and edge_score 0.58."
  }
}
```

---

## 🎯 Validation Targets

| Metric | Target MAE | Target MAPE | Target R² |
|--------|-----------|-------------|-----------|
| Δ Coverage | ≤ 0.03 | ≤ 15% | ≥ 0.65 |
| Δ PRB | ≤ 4 pts | ≤ 20% | ≥ 0.55 |
| NPV | ≤ $20K | ≤ 25% | ≥ 0.60 |

---

## 🔒 Project Scope

**Phase 1 (Current):**
- Technologies: 2G, 3G, 4G
- Event types: NEW_SITE, TECH_ADD, BAND_ADD, SECTOR_ADD, CAPACITY_ADD
- Method: Hierarchical CBR + Kernel weights + Bootstrap CI

**Deferred to Phase 2:**
- 5G NSA (n41, n78)
- Synthetic Control Method
- GBDT on similarity features
- Segment-specific traffic (MBB/FWA/Boxies)

---

## 👥 Contributing

1. Read `.clinerules/smart-capex-project.md` for project guidelines
2. Check `.tracking/progress.md` for current status
3. All work must remain within `project_smart_capex/` directory
4. Update progress tracker after completing milestones
5. Write tests for new features

---

## 📝 License

Internal E2E Project - Proprietary

---

## 📧 Contact

**Project Owner:** Smart CAPEX Team  
**Status:** Phase 1 Development

---

## 🗺️ Roadmap

- **Week 2:** Geographic utilities + ANP implementation
- **Week 5:** Feature extraction complete
- **Week 8:** Similarity engine complete
- **Week 10:** API operational with predictions
- **Week 12:** Validation complete, production-ready

**Track progress:** `.tracking/progress.md`