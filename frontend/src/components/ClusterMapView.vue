<template>
  <div class="cluster-map-container">
    <div class="mobile-map-toolbar">
      <button type="button" @click="toggleControls" :aria-expanded="controlsOpen">
        {{ controlsOpen ? 'Hide controls' : 'Map controls' }}
      </button>
      <strong>Smart CAPEX</strong>
    </div>
    <!-- Map controls panel -->
    <div class="map-controls" :class="{ 'controls-open': controlsOpen }">
      <h3>Cluster Visualization</h3>
      <div v-if="focusSites" class="focus-banner">
        <strong>Similarity map</strong><span>{{ focusSites.siteIds.length }} sites shown</span>
        <button type="button" @click="$emit('clear-focus')">Show all sites</button>
      </div>
      
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

      <div class="dem-controls">
        <h4>Population</h4>
        <label><input type="checkbox" v-model="populationVisible" @change="togglePopulation"> Tunisia population density</label>
        <template v-if="populationVisible">
          <label>Opacity: {{ populationOpacity }}%
            <input type="range" min="0" max="100" v-model="populationOpacity" @input="populationLayer?.setOpacity(populationOpacity / 100)">
          </label>
          <p>People/km²: 🟨 0–100 · 🟧 100–1,000 · 🟥 1,000–10,000 · 🟪 10,000+</p>
          <small>GHSL 2025 estimate · native 100 m cells. Zooming does not add population precision. Transparent: zero or no data.</small>
          <p v-if="populationError" role="status">{{ populationError }}</p>
        </template>
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

    <aside
      v-if="selectedSiteId"
      class="site-inspector"
      :style="{ '--inspector-width': `${inspectorWidth}px` }"
      aria-label="Selected site details"
    >
      <div
        class="inspector-resize"
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize site details panel"
        :aria-valuenow="inspectorWidth"
        tabindex="0"
        @pointerdown="startInspectorResize"
        @pointermove="moveInspectorResize"
        @pointerup="stopInspectorResize"
        @pointercancel="stopInspectorResize"
        @keydown="resizeInspectorWithKeyboard"
      ></div>
      <div class="inspector-toolbar">
        <strong>Site details</strong>
        <button type="button" aria-label="Close site details" @click="closeSiteDetails">Close</button>
      </div>
      <div class="inspector-content">
        <SiteFeaturePopup
          :key="selectedSiteId"
          :site-id="selectedSiteId"
          :api-base-url="apiBaseUrl"
          :search-query="selectedSearchQuery"
          :layout-update="refreshMapLayout"
        />
      </div>
    </aside>
  </div>
</template>

<script>
import { ref, onMounted, watch, nextTick } from 'vue';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import axios from 'axios';
import ElevationLegend from './ElevationLegend.vue';
import SiteFeaturePopup from './SiteFeaturePopup.vue';

export default {
  name: 'ClusterMapView',
  props: { focusSites: { type: Object, default: null } },
  emits: ['clear-focus'],
  
  components: {
    ElevationLegend,
    SiteFeaturePopup
  },
  
  setup(props) {
    const mapContainer = ref(null);
    const map = ref(null);
    const sitesLayer = ref(null);
    const neighborLayer = ref(null);
    const stats = ref(null);
    const loading = ref(false);
    const error = ref(null);
    const selectedCluster = ref(null);
    const selectedEventType = ref('ALL');
    const siteSearch = ref('');
    const searchQuery = ref('');
    const searchResultCount = ref(null);
    const controlsOpen = ref(typeof window === 'undefined' || window.innerWidth > 1024);
    const selectedSiteId = ref(null);
    const selectedSearchQuery = ref('');
    const inspectorWidth = ref(440);
    let inspectorDrag = null;
    let selectedMarker = null;
    let mapResizeFrame = null;
    
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
    const populationVisible = ref(false);
    const populationOpacity = ref(65);
    const populationLayer = ref(null);
    const populationError = ref('');
    const togglePopulation = () => {
      if (!populationVisible.value) {
        populationLayer.value?.remove();
        return;
      }
      populationError.value = '';
      if (!populationLayer.value) {
        populationLayer.value = L.tileLayer(`${API_BASE_URL}/population/tiles/{z}/{x}/{y}.png`, {
          opacity: populationOpacity.value / 100,
          maxZoom: 18, zIndex: 350,
          bounds: [[30.0, 7.0], [37.8, 12.0]],
          attribution: 'European Commission JRC · GHSL population 2025 (100 m)'
        });
        populationLayer.value.on('tileerror', () => { populationError.value = 'Population layer could not load. Please retry.'; });
      }
      populationLayer.value.addTo(map.value);
    };

    // API base URL (configure this based on your Django backend)
    const API_BASE_URL = 'http://localhost:8000/api';
    const apiBaseUrl = API_BASE_URL;

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
        if (props.focusSites?.siteIds?.length) {
          params.site_ids = props.focusSites.siteIds.join(',');
        } else if (selectedCluster.value !== null && !searchQuery.value) {
          params.cluster_id = selectedCluster.value;
        }
        if (!props.focusSites?.siteIds?.length && searchQuery.value) params.search = searchQuery.value;

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

    const markSelectedMarker = layer => {
      if (selectedMarker && selectedMarker !== layer) {
        selectedMarker.getElement?.()?.classList.remove('site-marker-selected');
        if (selectedMarker instanceof L.CircleMarker) {
          selectedMarker.setStyle({ radius: 6, color: '#000', weight: 1 });
        }
      }
      selectedMarker = layer;
      if (layer instanceof L.CircleMarker) {
        layer.setStyle({ radius: 9, color: '#111827', weight: 3 });
      }
      layer.getElement?.()?.classList.add('site-marker-selected');
    };

    const selectSite = (feature, layer, allFeatures) => {
      selectedSiteId.value = String(feature.properties.site_id);
      selectedSearchQuery.value = searchQuery.value;
      controlsOpen.value = false;
      markSelectedMarker(layer);
      showNeighborLinks(feature, allFeatures);
      nextTick(() => map.value?.invalidateSize({ pan: false }));
    };

    const closeSiteDetails = () => {
      selectedSiteId.value = null;
      selectedSearchQuery.value = '';
      selectedMarker?.getElement?.()?.classList.remove('site-marker-selected');
      if (selectedMarker instanceof L.CircleMarker) {
        selectedMarker.setStyle({ radius: 6, color: '#000', weight: 1 });
      }
      selectedMarker = null;
      neighborLayer.value?.clearLayers();
      nextTick(() => map.value?.invalidateSize({ pan: false }));
    };

    const refreshMapLayout = () => nextTick(() => {
      if (mapResizeFrame !== null) cancelAnimationFrame(mapResizeFrame);
      mapResizeFrame = requestAnimationFrame(() => {
        mapResizeFrame = null;
        map.value?.invalidateSize({ pan: false, debounceMoveend: true });
      });
    });

    const toggleControls = () => {
      controlsOpen.value = !controlsOpen.value;
      if (controlsOpen.value && selectedSiteId.value && window.innerWidth <= 1024) {
        closeSiteDetails();
      }
    };

    const startInspectorResize = event => {
      if (window.innerWidth <= 1024 || event.button !== 0) return;
      event.preventDefault();
      inspectorDrag = { pointerId: event.pointerId, startX: event.clientX, startWidth: inspectorWidth.value };
      event.currentTarget.setPointerCapture(event.pointerId);
    };

    const moveInspectorResize = event => {
      if (!inspectorDrag || inspectorDrag.pointerId !== event.pointerId) return;
      const maxWidth = Math.max(360, Math.min(720, window.innerWidth - 560));
      inspectorWidth.value = Math.max(360, Math.min(maxWidth, inspectorDrag.startWidth + inspectorDrag.startX - event.clientX));
      refreshMapLayout();
    };

    const stopInspectorResize = event => {
      if (!inspectorDrag || inspectorDrag.pointerId !== event.pointerId) return;
      inspectorDrag = null;
      refreshMapLayout();
    };

    const resizeInspectorWithKeyboard = event => {
      if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
      event.preventDefault();
      const maxWidth = Math.max(360, Math.min(720, window.innerWidth - 560));
      const delta = event.key === 'ArrowLeft' ? 24 : -24;
      inspectorWidth.value = Math.max(360, Math.min(maxWidth, inspectorWidth.value + delta));
      refreshMapLayout();
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
      neighborLayer.value.clearLayers();
      selectedMarker = null;

      // Fetch new data
      const geojson = await fetchClusterData();
      if (!geojson || !geojson.features || geojson.features.length === 0) {
        console.warn('No features to display');
        if (searchQuery.value && !props.focusSites?.siteIds?.length) {
          searchResultCount.value = 0;
          closeSiteDetails();
        }
        return;
      }
      if (searchQuery.value && !props.focusSites?.siteIds?.length) searchResultCount.value = geojson.features.length;

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
          const shouldShow = props.focusSites?.siteIds?.length ? true : shouldDisplaySite(feature.properties);
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
          layer.on('click', () => selectSite(feature, layer, geojson.features));
        }
      }).addTo(sitesLayer.value);

      console.log(`After filtering: ${filteredCount} sites (${edgeCount} edge, ${interiorCount} interior, ${noiseCount} noise)`);
      console.log(`Leaflet layers created: ${geoJsonLayer.getLayers().length}`);

      // Auto-zoom to fit all displayed markers
      if (geoJsonLayer.getLayers().length > 0) {
        const bounds = geoJsonLayer.getBounds();
        console.log('Zooming to bounds:', bounds);
        map.value.fitBounds(bounds, { padding: [50, 50], maxZoom: 14 });
        const layers = geoJsonLayer.getLayers();
        if (props.focusSites?.querySiteId) {
          const queryLayer = layers.find(layer => String(layer.feature?.properties?.site_id) === String(props.focusSites.querySiteId));
          if (queryLayer) selectSite(queryLayer.feature, queryLayer, geojson.features);
        } else if (searchQuery.value && layers.length) {
          selectSite(layers[0].feature, layers[0], geojson.features);
        } else if (selectedSiteId.value) {
          const selectedLayer = layers.find(layer => String(layer.feature?.properties?.site_id) === selectedSiteId.value);
          if (selectedLayer) selectSite(selectedLayer.feature, selectedLayer, geojson.features);
        }
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
    watch(() => props.focusSites, async () => {
      selectedCluster.value = null;
      siteSearch.value = '';
      searchQuery.value = '';
      await nextTick();
      updateMap();
    }, { deep: true });

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
      selectedSiteId,
      selectedSearchQuery,
      inspectorWidth,
      apiBaseUrl,
      demLayers,
      populationVisible, populationOpacity, populationLayer, populationError, togglePopulation,
      updateMap,
      searchSites,
      clearSearch,
      closeSiteDetails,
      toggleControls,
      startInspectorResize,
      moveInspectorResize,
      stopInspectorResize,
      resizeInspectorWithKeyboard,
      refreshMapLayout,
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
.focus-banner { display: grid; gap: 5px; margin: 12px 0; padding: 11px; border: 1px solid #99f6e4; border-radius: 7px; background: #f0fdfa; color: #115e59; font-size: 12px; }
.focus-banner button { width: max-content; margin-top: 3px; padding: 7px 9px; border: 0; border-radius: 5px; background: #0f766e; color: white; cursor: pointer; }

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

.site-inspector {
  position: relative;
  display: flex;
  flex: 0 0 var(--inspector-width);
  flex-direction: column;
  width: var(--inspector-width);
  min-width: 0;
  height: 100%;
  background: #fff;
  border-left: 1px solid #d9dee8;
  box-shadow: -3px 0 14px rgba(15, 23, 42, .12);
  z-index: 900;
}

.inspector-resize {
  position: absolute;
  z-index: 2;
  top: 0;
  bottom: 0;
  left: -5px;
  width: 10px;
  cursor: col-resize;
  touch-action: none;
}

.inspector-resize:focus-visible {
  outline: 2px solid #2563eb;
  outline-offset: -2px;
}

.inspector-toolbar {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 48px;
  padding: 8px 14px;
  border-bottom: 1px solid #e2e8f0;
  color: #1e293b;
}

.inspector-toolbar button {
  padding: 7px 10px;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  background: #fff;
  color: #334155;
  cursor: pointer;
}

.inspector-content {
  flex: 1;
  min-height: 0;
  overflow: auto;
  overscroll-behavior: contain;
}

:deep(.site-feature-popup) { width: 100%; max-width: none; }
:deep(.tab-nav) { position: sticky; top: 0; z-index: 2; }

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
:deep(.site-addition-marker.site-marker-selected .site-addition-icon) {
  outline: 3px solid #111827;
  outline-offset: 2px;
}

@media (max-width: 1024px) {
  .site-inspector {
    position: absolute;
    top: auto;
    right: 0;
    bottom: 0;
    left: 0;
    width: 100%;
    height: min(74dvh, 720px);
    padding-bottom: env(safe-area-inset-bottom);
    border: 0;
    border-radius: 16px 16px 0 0;
    box-shadow: 0 -5px 24px rgba(15, 23, 42, .28);
    overflow: hidden;
  }
  .inspector-resize { display: none; }
}

@media (max-width: 1024px) {
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
  .inspector-toolbar { min-height: 44px; padding: 7px 12px; }
}
</style>
