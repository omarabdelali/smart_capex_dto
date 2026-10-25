<template>
  <div class="cluster-map-container">
    <div class="mobile-map-toolbar">
      <button type="button" @click="controlsOpen = !controlsOpen" :aria-expanded="controlsOpen">
        {{ controlsOpen ? 'Hide controls' : 'Map controls' }}
      </button>
      <strong>Smart CAPEX</strong>
    </div>
    <!-- Map controls panel -->
    <div class="map-controls" :class="{ 'controls-open': controlsOpen }">
      <h3>Cluster Visualization</h3>
      
      <!-- Cluster statistics -->
      <div v-if="stats" class="stats-panel">
        <div class="stat-item">
          <span class="stat-label">Total Sites:</span>
          <span class="stat-value">{{ stats.total_sites }}</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">Clusters:</span>
          <span class="stat-value">{{ stats.total_clusters }}</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">Noise Sites:</span>
          <span class="stat-value">{{ stats.noise_sites }}</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">Edge Sites:</span>
          <span class="stat-value">{{ stats.edge_sites }}</span>
        </div>
      </div>

      <!-- Filters -->
      <div class="filters">
        <label>
          <input type="checkbox" v-model="filters.showEdge" @change="updateMap">
          Show Edge Sites
        </label>
        <label>
          <input type="checkbox" v-model="filters.showInterior" @change="updateMap">
          Show Interior Sites
        </label>
        <label>
          <input type="checkbox" v-model="filters.showNoise" @change="updateMap">
          Show Noise Sites
        </label>
        <label>
          <input type="checkbox" v-model="filters.showOutOfBounds" @change="updateMap">
          Show Out-of-Bounds
        </label>
        <div class="addition-legend">
          <span class="addition-legend-icon event-site">S</span><span>Site added</span>
          <span class="addition-legend-icon event-lte">4G</span><span>LTE added</span>
          <span class="addition-legend-icon event-3g">3G</span><span>3G added</span>
          <span class="addition-legend-icon event-2g">2G</span><span>2G added</span>
        </div>
      </div>

      <div class="event-filter">
        <label for="event-type-select">Show event:</label>
        <select id="event-type-select" v-model="selectedEventType" @change="updateMap">
          <option value="ALL">All events</option>
          <option value="SITE_ADDED">Site added</option>
          <option value="LTE_ADDED">LTE added</option>
          <option value="3G_ADDED">3G added</option>
          <option value="2G_ADDED">2G added</option>
        </select>
      </div>

      <form class="site-search" @submit.prevent="searchSites">
        <label for="site-search-input">Find a site or cell</label>
        <div class="search-row">
          <input id="site-search-input" v-model="siteSearch" type="search" placeholder="Name or partial name">
          <button type="submit">Find</button>
        </div>
        <button v-if="searchQuery" type="button" class="clear-search" @click="clearSearch">Clear search</button>
        <p v-if="searchResultCount !== null" class="search-result-count">
          {{ searchResultCount ? `${searchResultCount} matching site(s)` : 'No matching sites or cells' }}
        </p>
      </form>

      <!-- DEM Layer Controls -->
      <div class="dem-controls">
        <h4>Terrain Layers</h4>
        <label>
          <input type="checkbox" v-model="demLayers.showHillshade" @change="toggleHillshade">
          Hillshade (3D Relief)
        </label>
        <label>
          <input type="checkbox" v-model="demLayers.showElevation" @change="toggleElevation">
          Elevation Colors
        </label>
        <div v-if="demLayers.showHillshade || demLayers.showElevation" class="layer-opacity">
          <label>Layer Opacity:</label>
          <input 
            type="range" 
            min="0" 
            max="100" 
            v-model="demLayers.opacity" 
            @input="updateDEMOpacity"
          >
          <span>{{ demLayers.opacity }}%</span>
        </div>
      </div>

      <!-- Cluster selector -->
      <div class="cluster-selector" v-if="stats && stats.clusters">
        <label for="cluster-select">Filter by Cluster:</label>
        <select id="cluster-select" v-model="selectedCluster" @change="updateMap">
          <option :value="null">All Clusters</option>
          <option v-for="cluster in stats.clusters" :key="cluster.cluster_id" :value="cluster.cluster_id">
            Cluster {{ cluster.cluster_id }} ({{ cluster.site_count }} sites)
          </option>
        </select>
      </div>

      <!-- Loading indicator -->
      <div v-if="loading" class="loading">Loading cluster data...</div>
      <div v-if="error" class="error">{{ error }}</div>
    </div>

    <!-- Leaflet map -->
    <div id="cluster-map" ref="mapContainer">
      <!-- Elevation legend overlay -->
      <ElevationLegend :visible="demLayers.showElevation" />
    </div>
  </div>
</template>

<script>
import { ref, onMounted, watch, createApp, nextTick } from 'vue';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import axios from 'axios';
import ElevationLegend from './ElevationLegend.vue';
import SiteFeaturePopup from './SiteFeaturePopup.vue';

export default {
  name: 'ClusterMapView',
  
  components: {
    ElevationLegend
  },
  
  setup() {
    const mapContainer = ref(null);
    const map = ref(null);
    const sitesLayer = ref(null);
    const neighborLayer = ref(null);
    let activeFeatureApp = null;
    const stats = ref(null);
    const loading = ref(false);
    const error = ref(null);
    const selectedCluster = ref(null);
    const selectedEventType = ref('ALL');
    const siteSearch = ref('');
    const searchQuery = ref('');
    const searchResultCount = ref(null);
    const controlsOpen = ref(typeof window === 'undefined' || window.innerWidth > 760);
    
    const filters = ref({
      showEdge: true,
      showInterior: true,
      showNoise: true,
      showOutOfBounds: false
    });

    // DEM layer controls
    const demLayers = ref({
      showHillshade: false,
      showElevation: false,
      opacity: 60
    });
    
    const hillshadeLayer = ref(null);
    const elevationLayer = ref(null);

    // API base URL (configure this based on your Django backend)
    const API_BASE_URL = 'http://localhost:8000/api';

    /**
     * Initialize Leaflet map
     */
    const initMap = () => {
      // Center on Tunisia
      map.value = L.map('cluster-map').setView([34.0, 9.0], 7);

      // Add OpenStreetMap tile layer
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap contributors',
        maxZoom: 18
      }).addTo(map.value);

      // Create layer group for sites
      sitesLayer.value = L.layerGroup().addTo(map.value);
      neighborLayer.value = L.layerGroup().addTo(map.value);
    };

    /**
     * Fetch cluster statistics from API
     */
    const fetchStats = async () => {
      try {
        const response = await axios.get(`${API_BASE_URL}/sites/cluster_stats/`);
        stats.value = response.data;
      } catch (err) {
        console.error('Error fetching cluster stats:', err);
        error.value = 'Failed to load cluster statistics';
      }
    };

    /**
     * Fetch site cluster data from API
     */
    const fetchClusterData = async () => {
      loading.value = true;
      error.value = null;

      try {
        // Build query parameters
        const params = {};
        if (selectedCluster.value !== null && !searchQuery.value) {
          params.cluster_id = selectedCluster.value;
        }
        if (searchQuery.value) params.search = searchQuery.value;

        console.log('Fetching cluster data with params:', params);

        // Fetch GeoJSON data
        const response = await axios.get(`${API_BASE_URL}/sites/clusters/`, { params });
        
        console.log('API Response:', {
          type: response.data?.type,
          featuresCount: response.data?.features?.length,
          firstFeature: response.data?.features?.[0]
        });
        
        return response.data;
      } catch (err) {
        console.error('Error fetching cluster data:', err);
        error.value = 'Failed to load cluster data';
        return null;
      } finally {
        loading.value = false;
      }
    };

    /**
     * Get marker color based on site properties
     */
    const getMarkerColor = (properties) => {
      if (properties.out_of_bounds) {
        return '#FF0000'; // Red for out-of-bounds
      } else if (properties.cluster_id === -1) {
        return '#808080'; // Gray for noise points
      } else if (properties.is_cluster_edge) {
        return '#FFA500'; // Orange for edge sites
      } else {
        return '#00FF00'; // Green for interior sites
      }
    };

    /**
     * Check if site should be displayed based on filters
     */
    const shouldDisplaySite = (properties) => {
      if (searchQuery.value) return true;

      // Filter out-of-bounds sites
      if (properties.out_of_bounds && !filters.value.showOutOfBounds) {
        return false;
      }
      
      // Filter noise sites (cluster_id === -1)
      if (properties.cluster_id === -1 && !filters.value.showNoise) {
        return false;
      }
      
      // For non-noise sites, apply edge/interior filters
      if (properties.cluster_id !== -1) {
        if (properties.is_cluster_edge && !filters.value.showEdge) {
          return false;
        }
        if (!properties.is_cluster_edge && !filters.value.showInterior) {
          return false;
        }
      }

      if (selectedEventType.value !== 'ALL' &&
          !(properties.addition_events || []).some(event => event.event_type === selectedEventType.value)) {
        return false;
      }
      
      return true;
    };

    const distanceMeters = (a, b) => {
      const toRad = value => value * Math.PI / 180;
      const dLat = toRad(b[1] - a[1]);
      const dLon = toRad(b[0] - a[0]);
      const lat1 = toRad(a[1]);
      const lat2 = toRad(b[1]);
      const h = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;
      return 6371000 * 2 * Math.atan2(Math.sqrt(h), Math.sqrt(1 - h));
    };

    const showNeighborLinks = (selected, features) => {
      neighborLayer.value.clearLayers();
      const origin = selected.geometry.coordinates;
      const neighbors = features.map(candidate => ({
        feature: candidate,
        distance: distanceMeters(origin, candidate.geometry.coordinates)
      })).filter(item => item.feature.properties.site_id !== selected.properties.site_id && item.distance <= 3000)
        .sort((a, b) => a.distance - b.distance).slice(0, 30);

      neighbors.forEach(({ feature: candidate, distance }) => {
        const target = candidate.geometry.coordinates;
        L.polyline([[origin[1], origin[0]], [target[1], target[0]]], {
          color: '#2563eb', weight: 1.5, opacity: 0.65, dashArray: '5, 5'
        }).bindTooltip(`${candidate.properties.site_name} · ${(distance / 1000).toFixed(2)} km`)
          .addTo(neighborLayer.value);
      });
    };

    /**
     * Update map with cluster data
     */
    const updateMap = async () => {
      if (!map.value || !sitesLayer.value) {
        console.error('Map or sitesLayer not initialized');
        return;
      }

      // Clear existing markers
      sitesLayer.value.clearLayers();

      // Fetch new data
      const geojson = await fetchClusterData();
      if (!geojson || !geojson.features || geojson.features.length === 0) {
        console.warn('No features to display');
        if (searchQuery.value) searchResultCount.value = 0;
        return;
      }
      if (searchQuery.value) searchResultCount.value = geojson.features.length;

      console.log(`Total features fetched: ${geojson.features.length}`);
      console.log('Current filters:', filters.value);

      // Count features by type for debugging
      let filteredCount = 0;
      let edgeCount = 0;
      let interiorCount = 0;
      let noiseCount = 0;

      // Add GeoJSON layer
      const geoJsonLayer = L.geoJSON(geojson, {
        filter: (feature) => {
          const shouldShow = shouldDisplaySite(feature.properties);
          if (shouldShow) {
            filteredCount++;
            if (feature.properties.cluster_id === -1) noiseCount++;
            else if (feature.properties.is_cluster_edge) edgeCount++;
            else interiorCount++;
          }
          return shouldShow;
        },
        
        pointToLayer: (feature, latlng) => {
          // CRITICAL: Leaflet automatically converts GeoJSON [lon, lat] to L.LatLng [lat, lon]
          // The latlng parameter here is already in correct Leaflet format
          console.log(`Creating marker at ${latlng.lat}, ${latlng.lng} for site ${feature.properties.site_name}`);
          if (feature.properties.added_cell_count > 0) {
            const events = feature.properties.addition_events || [];
            const shownEvents = selectedEventType.value === 'ALL'
              ? events
              : events.filter(event => event.event_type === selectedEventType.value);
            const icons = shownEvents.map(event => {
              const details = {
                SITE_ADDED: ['site', 'S'],
                LTE_ADDED: ['lte', '4G'],
                '3G_ADDED': ['3g', '3G'],
                '2G_ADDED': ['2g', '2G']
              }[event.event_type];
              return details ? `<span class="site-addition-icon event-${details[0]}">${details[1]}</span>` : '';
            }).join('');
            return L.marker(latlng, {
              title: `${feature.properties.site_name} · ${feature.properties.added_cell_count} added cell(s) · ${shownEvents.map(event => event.event_type.replace('_ADDED', ' added')).join(', ')}`,
              icon: L.divIcon({
                className: 'site-addition-marker',
                html: `<span class="site-addition-icons">${icons}</span>`,
                iconSize: [Math.max(28, shownEvents.length * 27), 30],
                iconAnchor: [Math.max(14, shownEvents.length * 27 / 2), 15]
              })
            });
          }
          const color = getMarkerColor(feature.properties);
          const marker = L.circleMarker(latlng, {
            radius: 6,
            fillColor: color,
            color: '#000',
            weight: 1,
            opacity: 1,
            fillOpacity: 0.7
          });
          console.log(`Marker created:`, marker);
          return marker;
        },
        
        onEachFeature: (feature, layer) => {
          const mountNode = document.createElement('div');
          const viewportWidth = window.visualViewport?.width || window.innerWidth;
          const viewportHeight = window.visualViewport?.height || window.innerHeight;
          const popupWidth = Math.max(260, viewportWidth - 32);
          layer.bindPopup(mountNode, {
            maxWidth: Math.min(540, popupWidth),
            minWidth: Math.min(420, popupWidth),
            maxHeight: Math.max(120, viewportHeight - 64),
            autoPan: true,
            keepInView: true,
            autoPanPadding: [16, 16]
          });
          layer.on('click', () => showNeighborLinks(feature, geojson.features));
          layer.on('popupopen', event => {
            if (activeFeatureApp) activeFeatureApp.unmount();
            activeFeatureApp = createApp(SiteFeaturePopup, {
              siteId: String(feature.properties.site_id),
              apiBaseUrl: API_BASE_URL,
              searchQuery: searchQuery.value,
              layoutUpdate: () => nextTick(() => {
                if (event.popup.isOpen()) event.popup.update();
              })
            });
            activeFeatureApp.mount(event.popup.getContent());
            nextTick(() => event.popup.update());
          });
          layer.on('popupclose', () => {
            if (activeFeatureApp) {
              activeFeatureApp.unmount();
              activeFeatureApp = null;
            }
            neighborLayer.value.clearLayers();
          });
        }
      }).addTo(sitesLayer.value);

      console.log(`After filtering: ${filteredCount} sites (${edgeCount} edge, ${interiorCount} interior, ${noiseCount} noise)`);
      console.log(`Leaflet layers created: ${geoJsonLayer.getLayers().length}`);

      // Auto-zoom to fit all displayed markers
      if (geoJsonLayer.getLayers().length > 0) {
        const bounds = geoJsonLayer.getBounds();
        console.log('Zooming to bounds:', bounds);
        map.value.fitBounds(bounds, { padding: [50, 50], maxZoom: 14 });
        if (searchQuery.value) geoJsonLayer.getLayers()[0].openPopup();
      } else {
        console.warn('No layers to display after filtering!');
      }
    };

    const searchSites = () => {
      searchQuery.value = siteSearch.value.trim();
      searchResultCount.value = null;
      updateMap();
    };

    const clearSearch = () => {
      siteSearch.value = '';
      searchQuery.value = '';
      searchResultCount.value = null;
      updateMap();
    };

    /**
     * Toggle hillshade DEM layer
     */
    const toggleHillshade = () => {
      if (!map.value) return;

      if (demLayers.value.showHillshade) {
        // Add hillshade layer
        if (!hillshadeLayer.value) {
          hillshadeLayer.value = L.tileLayer(
            `${API_BASE_URL}/dem/hillshade/{z}/{x}/{y}.png`,
            {
              opacity: demLayers.value.opacity / 100,
              maxZoom: 18,
              attribution: '© Copernicus DEM'
            }
          );
        }
        hillshadeLayer.value.addTo(map.value);
      } else {
        // Remove hillshade layer
        if (hillshadeLayer.value) {
          map.value.removeLayer(hillshadeLayer.value);
        }
      }
    };

    /**
     * Toggle elevation DEM layer
     */
    const toggleElevation = () => {
      if (!map.value) return;

      if (demLayers.value.showElevation) {
        // Add elevation layer
        if (!elevationLayer.value) {
          elevationLayer.value = L.tileLayer(
            `${API_BASE_URL}/dem/elevation_tile/{z}/{x}/{y}.png`,
            {
              opacity: demLayers.value.opacity / 100,
              maxZoom: 18,
              attribution: '© Copernicus DEM'
            }
          );
        }
        elevationLayer.value.addTo(map.value);
      } else {
        // Remove elevation layer
        if (elevationLayer.value) {
          map.value.removeLayer(elevationLayer.value);
        }
      }
    };

    /**
     * Update DEM layer opacity
     */
    const updateDEMOpacity = () => {
      const opacity = demLayers.value.opacity / 100;
      if (hillshadeLayer.value && demLayers.value.showHillshade) {
        hillshadeLayer.value.setOpacity(opacity);
      }
      if (elevationLayer.value && demLayers.value.showElevation) {
        elevationLayer.value.setOpacity(opacity);
      }
    };

    /**
     * Initialize component on mount
     */
    onMounted(async () => {
      initMap();
      await fetchStats();
      await updateMap();
    });

    /**
     * Watch for cluster selection changes
     */
    watch(selectedCluster, () => {
      updateMap();
    });

    return {
      mapContainer,
      stats,
      loading,
      error,
      filters,
      selectedCluster,
      selectedEventType,
      siteSearch,
      searchQuery,
      searchResultCount,
      controlsOpen,
      demLayers,
      updateMap,
      searchSites,
      clearSearch,
      toggleHillshade,
      toggleElevation,
      updateDEMOpacity
    };
  }
};
</script>

<style scoped>
.cluster-map-container {
  position: relative;
  display: flex;
  height: 100%;
  min-height: 0;
  width: 100%;
  overflow: hidden;
}

.map-controls {
  flex: 0 0 clamp(250px, 24vw, 320px);
  padding: clamp(12px, 1.5vw, 20px);
  background-color: #f5f5f5;
  overflow-y: auto;
  box-shadow: 2px 0 5px rgba(0,0,0,0.1);
  min-height: 0;
}

.mobile-map-toolbar { display: none; }

.map-controls h3 {
  margin-top: 0;
  color: #333;
}

.stats-panel {
  background: white;
  padding: 15px;
  border-radius: 5px;
  margin-bottom: 20px;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

.stat-item {
  display: flex;
  justify-content: space-between;
  padding: 5px 0;
  border-bottom: 1px solid #eee;
}

.stat-item:last-child {
  border-bottom: none;
}

.stat-label {
  font-weight: 600;
  color: #666;
}

.stat-value {
  font-weight: bold;
  color: #2c3e50;
}

.filters {
  background: white;
  padding: 15px;
  border-radius: 5px;
  margin-bottom: 20px;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

.filters label {
  display: block;
  margin-bottom: 10px;
  cursor: pointer;
}

.filters input[type="checkbox"] {
  margin-right: 8px;
}

.addition-legend { display: flex; align-items: center; flex-wrap: wrap; gap: 7px; margin-top: 12px; color: #475569; font-size: 11px; }
.addition-legend-icon { display: grid; place-items: center; width: 22px; height: 22px; border-radius: 50%; background: #087f5b; color: #fff; font-size: 11px; font-weight: 800; line-height: 1; }
.event-filter { margin: 0 0 18px; padding: 12px; background: #fff; border-radius: 5px; box-shadow: 0 2px 4px rgba(0,0,0,.1); }
.event-filter label { display: block; margin-bottom: 7px; color: #333; font-size: 13px; font-weight: 600; }
.event-filter select { width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px; background: white; font-size: 14px; }
.site-search { margin: 0 0 18px; padding: 12px; background: #fff; border-radius: 5px; box-shadow: 0 2px 4px rgba(0,0,0,.1); }
.site-search label { display: block; margin-bottom: 7px; color: #333; font-size: 13px; font-weight: 600; }
.search-row { display: flex; gap: 6px; }
.search-row input { width: 100%; min-width: 0; padding: 8px; border: 1px solid #cbd5e1; border-radius: 4px; }
.search-row button, .clear-search { padding: 8px 10px; border: 0; border-radius: 4px; background: #334155; color: white; cursor: pointer; }
.clear-search { margin-top: 7px; background: #64748b; font-size: 12px; }
.search-result-count { margin-top: 7px; color: #475569; font-size: 12px; }

.dem-controls {
  background: white;
  padding: 15px;
  border-radius: 5px;
  margin-bottom: 20px;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

.dem-controls h4 {
  margin-top: 0;
  margin-bottom: 12px;
  color: #2c3e50;
  font-size: 14px;
  border-bottom: 2px solid #27ae60;
  padding-bottom: 5px;
}

.dem-controls label {
  display: block;
  margin-bottom: 10px;
  cursor: pointer;
  font-size: 13px;
}

.dem-controls input[type="checkbox"] {
  margin-right: 8px;
}

.layer-opacity {
  margin-top: 12px;
  padding: 10px;
  background-color: #f9f9f9;
  border-radius: 4px;
  border: 1px solid #e0e0e0;
}

.layer-opacity label {
  display: inline-block;
  margin-right: 8px;
  margin-bottom: 5px;
  font-size: 12px;
  font-weight: 600;
}

.layer-opacity input[type="range"] {
  width: calc(100% - 50px);
  margin-right: 8px;
  vertical-align: middle;
}

.layer-opacity span {
  display: inline-block;
  min-width: 35px;
  font-size: 12px;
  font-weight: bold;
  color: #27ae60;
}

.cluster-selector {
  background: white;
  padding: 15px;
  border-radius: 5px;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

.cluster-selector label {
  display: block;
  margin-bottom: 8px;
  font-weight: 600;
  color: #333;
}

.cluster-selector select {
  width: 100%;
  padding: 8px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 14px;
}

#cluster-map {
  flex: 1;
  height: 100%;
  min-width: 0;
}

.loading {
  text-align: center;
  padding: 20px;
  color: #666;
  font-style: italic;
}

.error {
  background-color: #fee;
  color: #c00;
  padding: 15px;
  border-radius: 5px;
  margin-top: 10px;
}

:deep(.leaflet-popup-content) {
  overflow-y: auto;
  overscroll-behavior: contain;
}

:deep(.site-addition-marker) {
  background: transparent;
  border: 0;
}

:deep(.site-addition-icon) {
  display: grid;
  place-items: center;
  width: 27px;
  height: 27px;
  border: 2px solid white;
  border-radius: 50%;
  background: #087f5b;
  color: white;
  font-size: 21px;
  font-weight: 800;
  line-height: 1;
  box-shadow: 0 1px 5px rgba(0, 0, 0, .55);
}

:deep(.site-addition-icons) { display: flex; gap: 2px; white-space: nowrap; }
:deep(.site-addition-icon.event-site), .addition-legend-icon.event-site { background: #087f5b; }
:deep(.site-addition-icon.event-lte), .addition-legend-icon.event-lte { background: #7c3aed; }
:deep(.site-addition-icon.event-3g), .addition-legend-icon.event-3g { background: #2563eb; }
:deep(.site-addition-icon.event-2g), .addition-legend-icon.event-2g { background: #d97706; }

/* Popup styling */
:deep(.site-popup) {
  min-width: 200px;
}

:deep(.site-popup h4) {
  margin-top: 0;
  color: #2c3e50;
  border-bottom: 2px solid #3498db;
  padding-bottom: 5px;
}

:deep(.site-popup p) {
  margin: 8px 0;
  font-size: 13px;
}

:deep(.site-popup .warning) {
  color: #c00;
  font-weight: bold;
  background-color: #fee;
  padding: 5px;
  border-radius: 3px;
}

@media (max-width: 760px) {
  .cluster-map-container { display: block; }
  #cluster-map { position: absolute; inset: 0; width: 100%; height: 100%; }
  .mobile-map-toolbar {
    position: absolute;
    z-index: 1100;
    top: max(8px, env(safe-area-inset-top));
    left: 8px;
    right: 8px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    pointer-events: none;
  }
  .mobile-map-toolbar button,
  .mobile-map-toolbar strong {
    pointer-events: auto;
    border: 0;
    border-radius: 8px;
    padding: 9px 12px;
    background: #fff;
    color: #24324a;
    box-shadow: 0 2px 10px rgba(15, 23, 42, .2);
    font-size: 13px;
  }
  .map-controls {
    display: none;
    position: absolute;
    z-index: 1050;
    top: 52px;
    left: 8px;
    width: min(360px, calc(100% - 16px));
    max-height: min(58dvh, 560px);
    padding: 12px;
    border-radius: 10px;
    box-shadow: 0 4px 18px rgba(15, 23, 42, .25);
  }
  .map-controls.controls-open { display: block; }
  .map-controls h3 { font-size: 16px; margin-bottom: 10px; }
  .stats-panel, .filters, .dem-controls, .event-filter, .site-search { margin-bottom: 10px; padding: 10px; }
  .stat-item { padding: 3px 0; font-size: 12px; }
  .filters label, .dem-controls label { margin-bottom: 6px; font-size: 12px; }
  .cluster-selector { padding: 10px; }
  .leaflet-popup { max-width: calc(100vw - 24px) !important; }
  .leaflet-popup-content-wrapper { max-width: calc(100vw - 24px); }
  .leaflet-popup-content { width: auto !important; max-width: calc(100vw - 56px); margin: 10px; }
}
</style>
