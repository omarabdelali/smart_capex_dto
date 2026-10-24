## Brief overview

Backend and frontend development coordination guidelines for Smart CAPEX. This ensures that when implementing features, both the Django backend API and Vue.js frontend UI are developed together in the same work session, creating a cohesive full-stack implementation workflow.

## Development approach

- **Unified feature development**: When implementing a feature, develop both backend and frontend components in the same session
- **No sequential separation**: Avoid completing all backend work first and then starting frontend work later
- **Full-stack iterations**: Each feature should be complete (backend + frontend) before moving to the next feature
- **Test both layers**: Validate backend API endpoints and frontend UI integration together

## Backend-frontend workflow

When implementing a feature:

1. **Design the API contract first**: Define REST endpoint, request/response schemas, validation rules
2. **Implement backend logic**: Django models, views, serializers, business logic
3. **Create API endpoint**: FastAPI or Django REST Framework endpoint with proper error handling
4. **Test backend independently**: Use curl, Postman, or pytest to validate API functionality
5. **Implement frontend UI**: Vue.js components, Leaflet map integration, form handling
6. **Wire frontend to backend**: Axios/fetch calls to backend API, state management
7. **Test full integration**: Verify end-to-end workflow from user interaction to database

## Technology stack coordination

- **Backend**: Django 4.2+, Django REST Framework or FastAPI, PostGIS/SpatiaLite
- **Frontend**: Vue.js 3, Leaflet for maps, Axios for API calls
- **Communication**: RESTful JSON APIs
- **Geospatial**: Backend processes GeoJSON, frontend renders with Leaflet

## Example: Site clustering feature

When implementing site clustering visualization:

**Backend (Django/FastAPI)**:
- Model: Site with cluster_id, is_cluster_edge fields ✓
- API endpoint: `/api/sites/clusters/` returning clustered sites as GeoJSON
- Business logic: SiteClusteringPipeline in src/models/preprocessing/
- Serializer: Convert Django QuerySet to GeoJSON FeatureCollection

**Frontend (Vue.js)**:
- Component: ClusterMapView.vue with Leaflet map
- API integration: Fetch GeoJSON from `/api/sites/clusters/`
- Visualization: Render cluster polygons, color-code edge/interior sites
- Interactivity: Click site marker to show cluster features popup

**Both developed together in same session**, not backend complete → then frontend later.

## API design patterns

- **RESTful conventions**: GET for read, POST for create, PUT/PATCH for update, DELETE for remove
- **GeoJSON format**: For geographic features (sites, clusters, polygons)
- **Pagination**: For large datasets (sites, KPIs)
- **Error handling**: Consistent JSON error responses with status codes
- **Validation**: Backend validates inputs, frontend provides user-friendly error messages

## Frontend-backend contract

- **Data format**: Backend provides GeoJSON FeatureCollection for map rendering
- **Coordinate system**: WGS84 (EPSG:4326) for all geographic data
- **Feature properties**: Include all site metadata in GeoJSON properties for popup display
- **API versioning**: Use `/api/v1/` prefix for future compatibility

## Testing strategy

- **Backend tests**: Unit tests for models, integration tests for API endpoints
- **Frontend tests**: Component tests with Vue Test Utils, E2E tests with Cypress
- **Integration tests**: Test full workflow from frontend UI action → backend API → database → frontend display
- **Visual validation**: Manual testing with real data on development server

## Development session structure

For each feature implementation session:

1. Define feature scope (backend + frontend)
2. Implement backend API endpoint
3. Test backend with curl or pytest
4. Implement frontend component
5. Wire frontend to backend API
6. Test full integration
7. Update progress tracking for both layers
8. Move to next feature

## Progress tracking

- Track both backend and frontend completion in `.tracking/progress.md`
- Mark feature complete only when both layers are functional
- Example:
  ```markdown
  - [x] Clustering Backend: API endpoint, GeoJSON serialization
  - [x] Clustering Frontend: ClusterMapView component, Leaflet rendering
  - [ ] Prediction Backend: Similarity engine API endpoint
  - [ ] Prediction Frontend: PredictionForm component, result display
  ```

## Communication with user

- When presenting completion, include both backend and frontend deliverables
- Provide backend API endpoint documentation and frontend component usage
- Include example API calls and frontend screenshots/demos when applicable

## Benefits of coordinated development

- **Immediate validation**: Test full workflow without waiting for frontend implementation later
- **Early integration issues**: Discover API contract mismatches early
- **Consistent progress**: Avoid having complete backend with no UI, or UI with no API
- **User-facing demos**: Can demonstrate working features immediately with both layers functional