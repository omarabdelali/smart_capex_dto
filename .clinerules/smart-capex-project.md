## Brief overview

Project-specific guidelines for the Smart CAPEX Phase 1 telecom network site impact prediction system. This is an MVC modular architecture project that processes geographic data, KPI data, performs similarity-based predictions, and visualizes geographic results. All work must be confined to the `project_smart_capex` directory and its subfolders.

## Project scope and boundaries

- **Working directory**: All code, data, and artifacts must reside within `c:\My Program Files\E2E\smart capex\project_smart_capex`
- **Read-only access**: Only read and work with files under `project_smart_capex` and its subfolders
- **No external dependencies**: Do not reference or create files outside the project directory
- **Scope**: Phase 1 covers 2G/3G/4G only (no 5G NSA)

## Architecture pattern

- **MVC modular structure**: Organize code using Model-View-Controller pattern with clear separation of concerns
- **Module organization**:
  - **Models**: Data processing, feature extraction, similarity computation, prediction logic
  - **Views**: Geographic visualization, UI components, API responses
  - **Controllers**: Orchestration, workflow management, API endpoints
- **Modular design**: Each major component (geo processing, KPI processing, ANP computation, similarity engine) should be a separate module with clear interfaces

## Project structure

```
project_smart_capex/
├── src/
│   ├── models/           # Data models and business logic
│   │   ├── preprocessing/
│   │   ├── features/
│   │   ├── similarity/
│   │   └── prediction/
│   ├── views/            # Visualization and presentation
│   │   ├── geo_visualization/
│   │   └── api_responses/
│   ├── controllers/      # Orchestration and workflows
│   │   ├── data_pipeline/
│   │   └── prediction_api/
│   └── utils/            # Shared utilities
├── data/                 # Data storage
│   ├── cellplan/
│   ├── geographic/
│   └── maos/
├── spec/                 # Specifications
├── tests/                # Test suite
├── notebooks/            # Exploration notebooks
└── .tracking/            # Progress tracking files
```

## Data processing workflow

- **Geographic data processing**: Handle DEM (Copernicus), land cover (ESA WorldCover), buildings (OSM), heights (GHSL)
- **KPI data processing**: Process Huawei MAOS counters for launch detection, pre/post metrics
- **Processing stages**: Raw data → Feature extraction → Case construction → DiD cleaning → Training set
- **Key features**: Implement Angular Neighborhood Profile (ANP) - 15 features for edge vs infill classification

## Progress tracking

- **Tracking file**: Maintain `.tracking/progress.md` to record completion status of each development step
- **Update frequency**: Update tracking file after completing each significant milestone
- **Tracking format**:
  ```markdown
  ## Module: [Name]
  - [x] Component A completed
  - [ ] Component B in progress
  - [ ] Component C pending
  
  Last updated: [Date/Time]
  Notes: [Key decisions, blockers, next steps]
  ```
- **Mandatory updates**: Update tracking file whenever a module, feature, or processing pipeline is completed

## Geographic visualization

- **Visualization library**: Use Folium for interactive maps
- **Display requirements**: Show site locations, neighbor bearings, ANP features (edge_score color-coded), coverage areas
- **Map outputs**: Generate HTML maps for exploration and validation
- **Coordinate system**: WGS84 (EPSG:4326) for Tunisia geographic data

## Development priorities

1. **Foundation first**: Set up project structure, utilities, data loaders
2. **Data pipeline**: Implement geographic and KPI data processing
3. **Core innovation**: Prioritize Angular Neighborhood Profile (ANP) implementation - this is the key differentiator
4. **Validation early**: Implement validation framework (LOO cross-validation) by Week 8
5. **Explainability**: Ensure local linear models and top-K similar cases are part of prediction output

## Key technical specifications

- **Feature count**: 57 features in Phase 1 (60 in Phase 2)
- **ANP features**: 15 features using 360° rotation analysis with 12 bins of 30°
- **Similarity metric**: Gower distance for mixed numeric/categorical features
- **Prediction method**: Hierarchical CBR + Kernel weights (Gaussian) + Bootstrap CI
- **Launch detection**: KPI-based (not cell plan diffs) - traffic > 0 with no prior history
- **Label cleaning**: Difference-in-Differences (DiD) to remove network trends

## Code organization principles

- **Modularity**: Each processing step (launch detection, feature extraction, ANP computation) is a separate module
- **Clear interfaces**: Define input/output contracts between modules
- **Configuration-driven**: Use config files for feature weights, validation parameters, data paths
- **Reusability**: Write functions that can be reused across training and prediction pipelines

## Testing strategy

- **Unit tests**: Test individual components (ANP computation, Gower distance, feature extraction)
- **Integration tests**: Test full pipeline (data loading → feature extraction → prediction)
- **Validation tests**: Implement LOO cross-validation, ablation tests (ANP on/off)
- **Visual validation**: Plot edge_score on maps to manually verify edge vs infill classification

## Communication and documentation

- **Code comments**: Include mathematical formulas in comments where applicable (e.g., Gower distance, kernel weights)
- **Reference spec**: Link to spec sections in code comments (e.g., "See Section 7.4 for ANP reference implementation")
- **Progress updates**: Provide clear status after completing each module or milestone
- **Technical decisions**: Document why choices were made (e.g., why Gower over Euclidean distance)

## Technology stack

- **Primary language**: Python 3.11+
- **Core libraries**: polars (DataFrames), geopandas (geospatial), rasterio (DEM), scikit-learn (ML utilities)
- **API framework**: FastAPI or Flask for REST endpoints
- **Visualization**: folium (maps), matplotlib/seaborn (charts)
- **Testing**: pytest
- **Geospatial**: shapely, pyproj for coordinate transformations

## Implementation phases

- **Phase 1a (Weeks 1-2)**: Foundation - project structure, data loaders, geographic utilities
- **Phase 1b (Weeks 3-5)**: Feature engineering - ANP, geographic features, KPI features
- **Phase 1c (Weeks 6-8)**: Similarity engine - Gower distance, hierarchical filter, kernel weights
- **Phase 1d (Weeks 9-10)**: API and explanation - prediction endpoint, local linear models
- **Phase 1e (Weeks 11-12)**: Validation and UI - LOO CV, ablation tests, map integration

## Critical success factors

- **ANP implementation**: The Angular Neighborhood Profile is the key innovation - must work correctly
- **Explainability**: Predictions must come with top-K similar cases and local linear explanations
- **Validation targets**: MAPE ≤ 15% for coverage, ≤ 20% for PRB, R² ≥ 0.65 for coverage
- **Geographic accuracy**: Correct handling of Tunisia coordinate system, DEM sampling, distance calculations