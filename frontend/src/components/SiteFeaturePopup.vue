<template>
  <div class="site-feature-popup">
    <!-- Loading state -->
    <div v-if="loading" class="loading-state">
      <p>Loading features...</p>
    </div>
    
    <!-- Error state -->
    <div v-else-if="error" class="error-state">
      <p>{{ error }}</p>
    </div>
    
    <!-- Feature data display -->
    <div v-else-if="features" class="feature-content">
      <!-- Site header -->
      <div class="site-header">
        <h3>{{ features.site_name }}</h3>
        <p class="site-id">ID: {{ features.site_id }}</p>
        <p class="coordinates">
          {{ features.latitude.toFixed(4) }}, {{ features.longitude.toFixed(4) }}
        </p>
        <div class="site-badges">
          <span class="badge" :class="clusterBadgeClass">
            {{ clusterLabel }}
          </span>
          <span class="badge" :class="positionBadgeClass">
            {{ positionLabel }}
          </span>
        </div>
      </div>
      
      <!-- Tab navigation -->
      <div class="tab-nav">
        <button 
          v-for="tab in tabs" 
          :key="tab.id"
          :class="['tab-button', { active: activeTab === tab.id }]"
          @click="activeTab = tab.id"
        >
          {{ tab.label }}
        </button>
      </div>
      
      <!-- Tab content -->
      <div class="tab-content">
        <!-- Overview Tab -->
        <div v-if="activeTab === 'overview'" class="tab-pane">
          <div class="info-grid">
            <div class="info-item">
              <span class="label">Cluster ID:</span>
              <span class="value">{{ features.cluster_id === -1 ? 'Noise' : features.cluster_id }}</span>
            </div>
            <div class="info-item">
              <span class="label">Position:</span>
              <span class="value">{{ features.is_cluster_edge ? 'Edge' : 'Interior' }}</span>
            </div>
            <div class="info-item">
              <span class="label">Cells:</span>
              <span class="value">{{ features.cell_count }}</span>
            </div>
            <div class="info-item">
              <span class="label">Technologies:</span>
              <span class="value">{{ features.technologies.join(', ') }}</span>
            </div>
          </div>
        </div>
        
        <!-- Geometric Tab -->
        <div v-if="activeTab === 'geometric'" class="tab-pane">
          <div v-if="features.geometric" class="feature-section">
            <div class="info-grid">
              <div class="info-item">
                <span class="label">Antenna Elevation:</span>
                <span class="value">{{ features.geometric.z_antenna_m?.toFixed(1) || 'N/A' }} m</span>
              </div>
              <div class="info-item">
                <span class="label">Terrain Slope:</span>
                <span class="value">{{ features.geometric.terrain_slope_deg?.toFixed(2) || 'N/A' }}°</span>
              </div>
              <div class="info-item">
                <span class="label">Terrain Aspect:</span>
                <span class="value">{{ features.geometric.terrain_aspect_deg?.toFixed(1) || 'N/A' }}°</span>
              </div>
              <div class="info-item">
                <span class="label">Terrain Roughness:</span>
                <span class="value">{{ features.geometric.terrain_roughness_m?.toFixed(2) || 'N/A' }} m</span>
              </div>
            </div>
          </div>
          <p v-else class="no-data">No geometric features available</p>
        </div>
        
        <!-- Clutter Tab -->
        <div v-if="activeTab === 'clutter'" class="tab-pane">
          <div v-if="features.clutter" class="feature-section">
            <!-- Highlighted Entropy -->
            <div class="entropy-highlight" :class="entropyClass">
              <div class="entropy-label">Clutter Entropy</div>
              <div class="entropy-value">{{ entropyDisplay }}</div>
              <div class="entropy-bar">
                <div class="entropy-fill" :style="{ width: entropyPercentage + '%' }"></div>
              </div>
              <div class="entropy-description">{{ entropyDescription }}</div>
            </div>
            
            <!-- Other clutter features -->
            <div class="info-grid">
              <div class="info-item">
                <span class="label">Dominant Clutter:</span>
                <span class="value dominant-type">{{ features.clutter.dominant_clutter || 'N/A' }}</span>
              </div>
              <div class="info-item">
                <span class="label">Building Area (1km):</span>
                <span class="value">{{ features.clutter.pct_building_area_1km?.toFixed(1) || 'N/A' }}%</span>
              </div>
              <div class="info-item">
                <span class="label">Avg Building Height:</span>
                <span class="value">{{ features.clutter.avg_building_height_m?.toFixed(1) || 'N/A' }} m</span>
              </div>
            </div>
          </div>
          <p v-else class="no-data">No clutter features available</p>
        </div>
        
        <!-- Spatial Tab -->
        <div v-if="activeTab === 'spatial'" class="tab-pane">
          <div v-if="features.spatial" class="feature-section">
            <div class="info-grid">
              <div class="info-item">
                <span class="label">Nearest Site:</span>
                <span class="value">{{ features.spatial.dist_nearest_site_m?.toFixed(0) || 'N/A' }} m</span>
              </div>
              <div class="info-item">
                <span class="label">Sites within 1km:</span>
                <span class="value">{{ features.spatial.n_sites_1km || 0 }}</span>
              </div>
              <div class="info-item">
                <span class="label">Sites within 2km:</span>
                <span class="value">{{ features.spatial.n_sites_2km || 0 }}</span>
              </div>
              <div class="info-item">
                <span class="label">Sites within 3km:</span>
                <span class="value">{{ features.spatial.n_sites_3km || 0 }}</span>
              </div>
              <div class="info-item">
                <span class="label">2G Sites (2km):</span>
                <span class="value">{{ features.spatial.n_2g_sites_2km || 0 }}</span>
              </div>
              <div class="info-item">
                <span class="label">3G Sites (2km):</span>
                <span class="value">{{ features.spatial.n_3g_sites_2km || 0 }}</span>
              </div>
              <div class="info-item">
                <span class="label">4G Sites (2km):</span>
                <span class="value">{{ features.spatial.n_4g_sites_2km || 0 }}</span>
              </div>
            </div>
          </div>
          <p v-else class="no-data">No spatial features available</p>
        </div>
        
        <!-- ANP Tab -->
        <div v-if="activeTab === 'anp'" class="tab-pane">
          <div v-if="features.anp" class="feature-section">
            <ANPPolarChart :anpData="features.anp" />
          </div>
          <p v-else class="no-data">No ANP features available</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, computed, watch } from 'vue';
import axios from 'axios';
import ANPPolarChart from './ANPPolarChart.vue';

export default {
  name: 'SiteFeaturePopup',
  
  components: {
    ANPPolarChart
  },
  
  props: {
    siteId: {
      type: String,
      required: true
    },
    apiBaseUrl: {
      type: String,
      default: 'http://localhost:8000/api'
    }
  },
  
  setup(props) {
    const features = ref(null);
    const loading = ref(false);
    const error = ref(null);
    const activeTab = ref('overview');
    
    const tabs = [
      { id: 'overview', label: 'Overview' },
      { id: 'geometric', label: 'Terrain' },
      { id: 'clutter', label: 'Clutter' },
      { id: 'spatial', label: 'Spatial' },
      { id: 'anp', label: 'ANP' }
    ];
    
    // Computed properties for site info
    const clusterLabel = computed(() => {
      if (!features.value) return '';
      return features.value.cluster_id === -1 ? 'Noise Point' : `Cluster ${features.value.cluster_id}`;
    });
    
    const clusterBadgeClass = computed(() => {
      if (!features.value) return '';
      return features.value.cluster_id === -1 ? 'noise' : 'cluster';
    });
    
    const positionLabel = computed(() => {
      if (!features.value) return '';
      return features.value.is_cluster_edge ? 'Edge Site' : 'Interior Site';
    });
    
    const positionBadgeClass = computed(() => {
      if (!features.value) return '';
      return features.value.is_cluster_edge ? 'edge' : 'interior';
    });
    
    // Entropy highlighting
    const entropyDisplay = computed(() => {
      const entropy = features.value?.clutter?.clutter_entropy_2km;
      return entropy !== null && entropy !== undefined ? entropy.toFixed(3) : 'N/A';
    });
    
    const entropyClass = computed(() => {
      const entropy = features.value?.clutter?.clutter_entropy_2km || 0;
      if (entropy < 0.5) return 'low-entropy';
      if (entropy < 1.0) return 'medium-entropy';
      return 'high-entropy';
    });
    
    const entropyPercentage = computed(() => {
      const entropy = features.value?.clutter?.clutter_entropy_2km || 0;
      // Scale 0-2 to 0-100%
      return Math.min((entropy / 2) * 100, 100);
    });
    
    const entropyDescription = computed(() => {
      const entropy = features.value?.clutter?.clutter_entropy_2km || 0;
      if (entropy < 0.5) return 'Homogeneous land cover';
      if (entropy < 1.0) return 'Mixed land cover';
      return 'Highly diverse land cover';
    });
    
    /**
     * Fetch site features from API
     */
    const fetchFeatures = async () => {
      loading.value = true;
      error.value = null;
      
      try {
        const response = await axios.get(`${props.apiBaseUrl}/sites/${props.siteId}/features/`);
        features.value = response.data;
      } catch (err) {
        console.error('Error fetching site features:', err);
        error.value = 'Failed to load site features';
      } finally {
        loading.value = false;
      }
    };
    
    // Watch for site ID changes
    watch(() => props.siteId, () => {
      if (props.siteId) {
        fetchFeatures();
      }
    }, { immediate: true });
    
    return {
      features,
      loading,
      error,
      activeTab,
      tabs,
      clusterLabel,
      clusterBadgeClass,
      positionLabel,
      positionBadgeClass,
      entropyDisplay,
      entropyClass,
      entropyPercentage,
      entropyDescription
    };
  }
};
</script>

<style scoped>
.site-feature-popup {
  min-width: 400px;
  max-width: 500px;
}

.loading-state,
.error-state {
  padding: 20px;
  text-align: center;
}

.error-state {
  color: #c00;
}

.feature-content {
  display: flex;
  flex-direction: column;
}

.site-header {
  padding: 15px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
}

.site-header h3 {
  margin: 0 0 5px 0;
  font-size: 18px;
}

.site-id {
  margin: 3px 0;
  font-size: 12px;
  opacity: 0.9;
}

.coordinates {
  margin: 3px 0 10px 0;
  font-size: 12px;
  opacity: 0.9;
  font-family: monospace;
}

.site-badges {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}

.badge {
  padding: 4px 10px;
  border-radius: 12px;
  font-size: 11px;
  font-weight: 600;
}

.badge.cluster {
  background-color: rgba(255, 255, 255, 0.2);
}

.badge.noise {
  background-color: rgba(255, 255, 255, 0.2);
}

.badge.edge {
  background-color: rgba(255, 152, 0, 0.9);
}

.badge.interior {
  background-color: rgba(76, 175, 80, 0.9);
}

.tab-nav {
  display: flex;
  background-color: #f5f5f5;
  border-bottom: 2px solid #ddd;
}

.tab-button {
  flex: 1;
  padding: 10px;
  background: none;
  border: none;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  color: #666;
  transition: all 0.2s;
}

.tab-button:hover {
  background-color: #e8e8e8;
}

.tab-button.active {
  background-color: white;
  color: #667eea;
  border-bottom: 2px solid #667eea;
  margin-bottom: -2px;
}

.tab-content {
  background: white;
}

.tab-pane {
  padding: 15px;
  animation: fadeIn 0.3s;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

.feature-section {
  /* Container for feature content */
}

.info-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.info-item {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.info-item .label {
  font-size: 11px;
  color: #666;
  font-weight: 500;
}

.info-item .value {
  font-size: 13px;
  color: #2c3e50;
  font-weight: 600;
}

.value.dominant-type {
  text-transform: capitalize;
}

.no-data {
  text-align: center;
  color: #999;
  font-style: italic;
  padding: 20px;
}

/* Entropy highlight styles */
.entropy-highlight {
  margin-bottom: 20px;
  padding: 20px;
  border-radius: 8px;
  text-align: center;
}

.entropy-highlight.low-entropy {
  background: linear-gradient(135deg, #e8f5e9 0%, #c8e6c9 100%);
  border: 2px solid #4caf50;
}

.entropy-highlight.medium-entropy {
  background: linear-gradient(135deg, #fff3e0 0%, #ffe0b2 100%);
  border: 2px solid #ff9800;
}

.entropy-highlight.high-entropy {
  background: linear-gradient(135deg, #ffebee 0%, #ffcdd2 100%);
  border: 2px solid #f44336;
}

.entropy-label {
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 1px;
  opacity: 0.8;
  margin-bottom: 8px;
}

.entropy-value {
  font-size: 36px;
  font-weight: bold;
  margin: 10px 0;
}

.low-entropy .entropy-value {
  color: #2e7d32;
}

.medium-entropy .entropy-value {
  color: #ef6c00;
}

.high-entropy .entropy-value {
  color: #c62828;
}

.entropy-bar {
  height: 10px;
  background-color: rgba(0, 0, 0, 0.1);
  border-radius: 5px;
  overflow: hidden;
  margin: 15px 0;
}

.entropy-fill {
  height: 100%;
  transition: width 0.3s ease;
}

.low-entropy .entropy-fill {
  background: linear-gradient(90deg, #4caf50, #66bb6a);
}

.medium-entropy .entropy-fill {
  background: linear-gradient(90deg, #ff9800, #ffa726);
}

.high-entropy .entropy-fill {
  background: linear-gradient(90deg, #f44336, #ef5350);
}

.entropy-description {
  font-size: 13px;
  font-weight: 600;
  margin-top: 8px;
}

.low-entropy .entropy-description {
  color: #2e7d32;
}

.medium-entropy .entropy-description {
  color: #ef6c00;
}

.high-entropy .entropy-description {
  color: #c62828;
}
</style>
