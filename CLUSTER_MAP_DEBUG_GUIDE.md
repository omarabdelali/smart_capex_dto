# Cluster Map Debugging Guide

## Problem Summary
When selecting a cluster from the "Filter by Cluster" dropdown in the Vue.js frontend, sites are not displaying on the Leaflet map, even though the Django backend API is successfully returning GeoJSON data (676 features for cluster 0, 162KB response).

## Deep Investigation Completed

### 1. Backend Verification ✓
- **API Endpoint**: `GET /api/sites/clusters/?cluster_id=0` returns HTTP 200
- **Data Structure**: Valid GeoJSON FeatureCollection with correct format
- **Feature Count**: 676 sites in cluster 0
- **Coordinate Format**: `[longitude, latitude]` in GeoJSON (correct format)
- **Sample Coordinates**: `[10.31656, 36.86978]` (Tunisia region)

### 2. Frontend Code Fixes Applied

#### Fix #1: Popup Content Bug (Line 212)
**Problem**: Trying to access `props.latitude` and `props.longitude` which don't exist
**Solution**: Use `feature.geometry.coordinates` array
```javascript
// BEFORE (BROKEN):
<p><strong>Coordinates:</strong> ${props.latitude}, ${props.longitude}</p>

// AFTER (FIXED):
const coords = feature.geometry.coordinates; // [lon, lat]
<p><strong>Coordinates:</strong> ${coords[1].toFixed(4)}, ${coords[0].toFixed(4)}</p>
```

#### Fix #2: Enhanced Logging
Added extensive console logging to track:
- API fetch parameters and response
- Total features received
- Filter application results
- Marker creation (per-site logging)
- Layer count verification
- Bounds calculation

### 3. Coordinate System Analysis ✓
- **GeoJSON format**: `[longitude, latitude]` array in geometry.coordinates
- **Leaflet format**: Automatically converts to LatLng object [lat, lon]
- **No manual conversion needed**: Leaflet's L.geoJSON handles this automatically
- The `latlng` parameter in `pointToLayer` is already in correct Leaflet format

## Debug Tools Created

### Tool 1: Debug HTML Page
**Location**: `frontend/debug_cluster_map.html`

**Features**:
- Standalone HTML file (no Vue.js complexity)
- Three test buttons:
  1. **Test API**: Verifies backend returns valid GeoJSON
  2. **Test Leaflet**: Creates manual test markers to verify Leaflet works
  3. **Test Full Pipeline**: Complete integration test with real API data
- Real-time logging panel showing each step
- Console output for detailed debugging

### Tool 2: Enhanced Vue Component
**Location**: `frontend/src/components/ClusterMapView.vue`

**Enhancements**:
- Per-marker creation logging
- Filter application tracking
- Layer count verification
- Bounds calculation logging

## Testing Instructions

### Step 1: Use Debug HTML Tool
1. Ensure Django backend is running on `http://localhost:8000`
2. Open `frontend/debug_cluster_map.html` in browser
3. Click "Test API" button → Should show 676 features
4. Click "Test Leaflet" button → Should show 3 green test markers on map
5. Click "Test Full Pipeline" button → Should show filtered cluster 0 interior sites

**Expected Output**:
- Console logs showing marker creation for each site
- Map automatically zooms to Tunisia region
- Green circle markers appear on map
- Clicking markers shows popup with site info

### Step 2: Test Vue Component
1. Hard refresh browser (Ctrl+Shift+F5 or Cmd+Shift+R)
2. Open browser DevTools Console (F12)
3. Select cluster 0 from dropdown
4. Check console for these logs:
   ```
   Fetching cluster data with params: {cluster_id: 0}
   API Response: {type: 'FeatureCollection', featuresCount: 676, ...}
   Total features fetched: 676
   Creating marker at 36.86978, 10.31656 for site TUN_0001
   ...
   After filtering: 514 sites (0 edge, 514 interior, 0 noise)
   Leaflet layers created: 514
   Zooming to bounds: ...
   ```

### Step 3: Verify Frontend Build
If Vue component still doesn't work after hard refresh:

```bash
cd frontend
npm run build
# or for dev server
npm run dev
```

Then refresh browser and check console again.

## Potential Root Causes (If Still Not Working)

### Issue A: Vue Component Not Loading Updated Code
**Symptoms**: Console shows old logs or no logs at all
**Solution**: 
- Clear browser cache completely
- Stop and restart Vite dev server
- Try incognito/private browsing window

### Issue B: CORS Error
**Symptoms**: Console shows network error fetching from API
**Solution**: Check Django CORS settings in `settings.py`:
```python
CORS_ALLOWED_ORIGINS = ['http://localhost:5173', 'http://127.0.0.1:5173']
```

### Issue C: Layer Not Added to Map
**Symptoms**: Console shows "Leaflet layers created: 514" but nothing on map
**Solution**: 
- Check if `sitesLayer` is added to map: `sitesLayer.value.addTo(map.value)`
- Verify map container has proper dimensions in CSS
- Check browser console for CSS/rendering errors

### Issue D: Filter Removing All Sites
**Symptoms**: Console shows "After filtering: 0 sites"
**Solution**: Check filter checkbox states and logic in `shouldDisplaySite()`

## Expected Console Output (Success Case)

```javascript
// When selecting Cluster 0:
Fetching cluster data with params: {cluster_id: 0}
API Response: {type: "FeatureCollection", featuresCount: 676, firstFeature: {...}}
Total features fetched: 676
Current filters: {showEdge: true, showInterior: true, showNoise: true, showOutOfBounds: false}
Creating marker at 36.86978, 10.31656 for site TUN_0001
Creating marker at 35.12345, 9.67890 for site TUN_0002
...
After filtering: 676 sites (162 edge, 514 interior, 0 noise)
Leaflet layers created: 676
Zooming to bounds: LatLngBounds {_southWest: LatLng, _northEast: LatLng}
```

## Next Steps

1. **Test debug HTML first** - This isolates Vue.js from the equation
2. **If debug HTML works but Vue doesn't** - Issue is in Vue component lifecycle or build
3. **If debug HTML doesn't work** - Issue is in API, CORS, or Leaflet itself
4. **Report findings** - Share console output from both debug HTML and Vue component

## Files Modified in This Debug Session

1. `frontend/src/components/ClusterMapView.vue` - Fixed popup bug, added logging
2. `frontend/debug_cluster_map.html` - Created standalone debug tool
3. `CLUSTER_MAP_DEBUG_GUIDE.md` - This comprehensive debugging guide