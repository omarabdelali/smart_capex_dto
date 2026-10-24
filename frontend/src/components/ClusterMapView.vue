<template>
  <div class="cluster-map-container">
    <!-- Map controls panel -->
    <div class="map-controls">
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
    <div id="cluster-map" ref="mapContainer"></div>
  </div>
</template>

<script>
import { ref, onMounted, watch } from 'vue';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import axios from 'axios';

export default {
  name: 'ClusterMapView',
  
  setup() {
    const mapContainer = ref(null);
    const map = ref(null);
    const sitesLayer = ref(null);
    const stats = ref(null);
    const loading = ref(false);
    const error = ref(null);
    const selectedCluster = ref(null);
    
    const filters = ref({
      showEdge: true,
      showInterior: true,
      showNoise: true,
      showOutOfBounds: false
    });

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
        if (selectedCluster.value !== null) {
          params.cluster_id = selectedCluster.value;
        }

        // Fetch GeoJSON data
        const response = await axios.get(`${API_BASE_URL}/sites/clusters/`, { params });
        
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
      if (properties.out_of_bounds && !filters.value.showOutOfBounds) {
        return false;
      }
      if (properties.cluster_id === -1 && !filters.value.showNoise) {
        return false;
      }
      if (properties.is_cluster_edge && !filters.value.showEdge) {
        return false;
      }
      if (!properties.is_cluster_edge && !filters.value.showInterior) {
        return false;
      }
      return true;
    };

    /**
     * Create popup content for site marker
     */
    const createPopupContent = (feature) => {
      const props = feature.properties;
      return `
        <div class="site-popup">
          <h4>${props.site_name}</h4>
          <p><strong>Site ID:</strong> ${props.site_id}</p>
          <p><strong>Coordinates:</strong> ${props.latitude.toFixed(4)}, ${props.longitude.toFixed(4)}</p>
          <p><strong>Cluster ID:</strong> ${props.cluster_id === -1 ? 'Noise' : props.cluster_id}</p>
          <p><strong>Position:</strong> ${props.is_cluster_edge ? 'Edge' : 'Interior'}</p>
          <p><strong>Cells:</strong> ${props.cell_count}</p>
          <p><strong>Technologies:</strong> ${props.technologies.join(', ')}</p>
          ${props.out_of_bounds ? '<p class="warning"><strong>⚠ Out of Bounds</strong></p>' : ''}
        </div>
      `;
    };

    /**
     * Update map with cluster data
     */
    const updateMap = async () => {
      if (!map.value || !sitesLayer.value) return;

      // Clear existing markers
      sitesLayer.value.clearLayers();

      // Fetch new data
      const geojson = await fetchClusterData();
      if (!geojson) return;

      // Add GeoJSON layer
      L.geoJSON(geojson, {
        filter: (feature) => shouldDisplaySite(feature.properties),
        
        pointToLayer: (feature, latlng) => {
          const color = getMarkerColor(feature.properties);
          return L.circleMarker(latlng, {
            radius: 6,
            fillColor: color,
            color: '#000',
            weight: 1,
            opacity: 1,
            fillOpacity: 0.7
          });
        },
        
        onEachFeature: (feature, layer) => {
          layer.bindPopup(createPopupContent(feature));
        }
      }).addTo(sitesLayer.value);
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
      updateMap
    };
  }
};
</script>

<style scoped>
.cluster-map-container {
  display: flex;
  height: 100vh;
  width: 100%;
}

.map-controls {
  width: 300px;
  padding: 20px;
  background-color: #f5f5f5;
  overflow-y: auto;
  box-shadow: 2px 0 5px rgba(0,0,0,0.1);
}

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
</style>