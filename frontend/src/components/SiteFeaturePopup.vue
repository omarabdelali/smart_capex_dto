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
          <span v-for="event in features.network_events" :key="event.event_key" class="badge addition">
            {{ eventTitle(event) }}
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
            <div v-if="features.launch_date" class="info-item launch-date-item">
              <span class="label">Launch / addition date:</span>
              <span class="value">{{ features.launch_date }}</span>
            </div>
          </div>
          <section v-if="features.network_events?.length" class="added-cells radio-events">
            <h4>Traffic-confirmed radio events</h4>
            <p>Effective dates are monthly KPI observations. Configuration dates are unknown unless recorded separately.</p>
            <ul>
              <li v-for="event in features.network_events" :key="event.event_key">
                <strong>{{ eventTitle(event) }} · effective {{ event.event_date }}</strong>
                <span v-if="event.previous_bandwidth_mhz != null">{{ event.previous_bandwidth_mhz }} → {{ event.new_bandwidth_mhz }} MHz · PRB change observed {{ event.first_changed_prb_month }}</span>
                <span v-for="(month, cellId) in event.cell_activation_months" :key="cellId">{{ cellId }} · first positive traffic {{ month }}</span>
                <span>Configuration date: {{ event.configuration_date || 'Unknown' }}</span>
              </li>
            </ul>
          </section>
          <section v-if="features.added_cells?.length" class="added-cells">
            <h4>Detected cell additions</h4>
            <ul>
              <li v-for="cell in features.added_cells" :key="cell.cell_name">
                <strong>{{ cell.cell_name }} ({{ cell.technology }})</strong>
                <span>Cell active {{ cell.launch_date }} · group complete {{ cell.group_effective_date }}</span>
              </li>
            </ul>
          </section>
          <section v-if="features.cell_plan?.length" class="cell-plan">
            <h4>Cell plan at this site</h4>
            <p class="cell-plan-note">Existing cell-plan configuration is retained; additions are overlaid on the matching cell records.</p>
            <div class="cell-plan-list">
              <article
                v-for="cell in features.cell_plan"
                :key="cell.cell_id"
                class="cell-plan-card"
                :class="{ 'cell-plan-added': cell.is_added }"
              >
                <div class="cell-plan-heading">
                  <strong>{{ cell.cell_name }}</strong>
                  <span>{{ cell.technology }}</span>
                  <span v-if="cell.is_added" class="cell-plan-status">{{ eventLabel(cell.event_type) }} · active {{ cell.launch_date }}</span>
                </div>
                <div class="cell-plan-features">
                  <span>{{ cell.band }} · {{ cell.frequency_mhz }} MHz · {{ cell.bandwidth_mhz }} MHz BW</span>
                  <span>Azimuth {{ cell.azimuth_deg }}° · Antenna {{ cell.antenna_height_m }} m</span>
                </div>
              </article>
            </div>
          </section>
          <section v-if="features.matched_cells?.length" class="matched-cells">
            <h4>Matching cells</h4>
            <ul>
              <li v-for="cell in features.matched_cells" :key="cell.cell_name">
                <strong>{{ cell.cell_name }}</strong><span>{{ cell.technology }}</span>
              </li>
            </ul>
          </section>
        </div>
        
        <!-- Geometric Tab -->
        <div v-if="activeTab === 'roads'" class="tab-pane population-panel">
          <h4>Road context · {{ features.roads?.buffer_m || 1000 }} m buffer</h4>
          <template v-if="features.roads">
            <p>{{ features.roads.source }} · © OpenStreetMap contributors · ODbL</p>
            <div v-for="item in roadRows" :key="item.key" class="info-item">
              <span class="label">{{ item.label }}</span>
              <span class="value">{{ item.value == null ? 'Unavailable' : typeof item.value === 'number' ? item.value.toLocaleString(undefined, { maximumFractionDigits: 3 }) + ' ' + item.unit : item.value }}</span>
            </div>
            <h4>Road length by class</h4>
            <div v-for="item in roadClasses" :key="item.name" class="road-class"><span>{{ item.name }} · {{ item.km.toFixed(2) }} km</span><div class="road-bar" :style="{ width: `${item.share}%` }"></div></div>
            <p>{{ features.roads.coverage_status === 'nearby_osm_evidence' ? 'OSM roads exist within 5 km. This is a coverage heuristic, not proof of complete mapping.' : 'No source roads within 5 km: measurements remain unavailable.' }}</p>
            <p>Extract date: {{ features.roads.osm_extract_date || 'Unknown' }}. Junctions are estimated from geometry and separated by layer/bridge/tunnel; original OSM node IDs are unavailable.</p>
            <small>Class weights are prior, uncalibrated. Current snapshot only; roads are optional in similarity and excluded from historical CBR unless source timing is known.</small>
          </template>
          <p v-else>Road features have not been synchronized for this site.</p>
        </div>
        <div v-if="activeTab === 'population'" class="tab-pane population-panel">
          <h4>Population context</h4>
          <p>GHSL 2025 · native 100 m population estimates</p>
          <div v-for="item in populationRows" :key="item.key" class="info-item">
            <span class="label">{{ item.label }}</span>
            <span class="value">{{ item.value == null ? 'Unavailable' : Number(item.value).toLocaleString(undefined, { maximumFractionDigits: item.unit === 'people' ? 0 : 1 }) + ' ' + item.unit }}</span>
            <small v-if="item.quality?.land_coverage != null">Land coverage {{ (100 * item.quality.land_coverage).toFixed(1) }}% · water {{ item.quality.water_pct.toFixed(1) }}%</small>
            <small v-if="item.quality?.status === 'incomplete_land_coverage'">Partial mapped estimate: missing land is excluded, so the full catchment population may be higher.</small>
            <small v-if="item.value == null">{{ item.quality?.status === 'outside_raster' ? 'Outside population raster coverage.' : 'Insufficient population data on land; no missing residents have been invented.' }}</small>
          </div>
          <p>Counts are calculated from covered population cells. Tier 2 excludes Tier 1. Water is identified using WorldCover; missing land is not filled. Density is mapped population divided by the full catchment area.</p>
          <small>GHSL 2025 context is assumed stable across event years under the approved static-population policy.</small>
        </div>
        <div v-if="activeTab === 'geometric'" class="tab-pane">
          <div v-if="features.geometric" class="feature-section">
            <p class="cell-plan-note">Absolute antenna elevation = DEM ground + stored building-height estimate + antenna height (25 m fallback).</p>
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
              <div class="info-item">
                <span class="label">Terrain relief (DEM slope):</span>
                <span class="value">{{ features.geometric.terrain_relief_class || 'Unavailable' }}</span>
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

        <!-- KPI and configuration features -->
        <div v-if="activeTab === 'network'" class="tab-pane">
          <section v-if="features.cluster_prelaunch" class="cluster-prelaunch-panel">
            <h4>Cluster KPIs · month before event</h4>
            <p class="cell-plan-note">{{ features.cluster_prelaunch.cluster_prelaunch_support.month }} · {{ features.cluster_prelaunch.cluster_prelaunch_support.reporting_sites }} / {{ features.cluster_prelaunch.cluster_prelaunch_support.member_sites }} reporting sites. Active users are summed across cells; ratios use summed components.</p>
            <div class="info-grid">
              <div v-for="metric in clusterBaselineMetrics" :key="metric.key" class="info-item">
                <span class="label">{{ metric.label }}</span>
                <span class="value">{{ formatValue(features.cluster_prelaunch[metric.key]) }} {{ metric.unit }}</span>
              </div>
            </div>
          </section>
          <h4>Legacy own-site KPI fields</h4>
          <div v-if="features.kpi" class="info-grid">
            <div v-for="(value, key) in features.kpi" :key="key" class="info-item">
              <span class="label">{{ formatLabel(key) }}:</span>
              <span class="value">{{ formatValue(value) }}</span>
            </div>
          </div>
          <p v-else class="no-data">No eligible own-site pre-launch KPI record. Use the Tier 1 / Tier 2 / cluster context and monthly scope selector below.</p>

          <h4>Site configuration</h4>
          <p v-if="features.configuration_support" class="cell-plan-note">{{ features.configuration_support.evidenced_cells }} KPI-confirmed cells / {{ features.configuration_support.plan_cells }} plan cells. Capacity is the sum of reported LTE PRBs. Missing 2G/3G evidence is not filled.</p>
          <p v-if="features.configuration_support && Object.keys(features.configuration_support.unmapped_bandwidth_prbs || {}).length" class="cell-plan-note">Some PRB averages do not match 25/50/75/100 within ±5; total MHz bandwidth stays unknown under the strict mapping policy.</p>
          <div v-if="features.configuration" class="info-grid">
            <div v-for="(value, key) in features.configuration" :key="key" class="info-item">
              <span class="label">{{ formatLabel(key) }}:</span>
              <span class="value">{{ formatValue(value) }}</span>
            </div>
          </div>
          <p v-else class="no-data">No configuration features stored for this site</p>

          <h4>Static cluster context · KPI month before event</h4>
          <div v-if="features.cluster_features" class="info-grid">
            <div v-for="(value, key) in features.cluster_features" :key="key" class="info-item">
              <span class="label">{{ formatLabel(key) }}:</span>
              <span class="value">{{ formatValue(value) }}</span>
            </div>
          </div>
          <p v-else class="no-data">No cluster feature values stored for this site</p>

          <section v-if="features.user_context" class="user-context-panel">
            <h4>Pre-event edge and low-latency users</h4>
            <p>Three complete months before {{ features.user_context.profile_as_of_date }}. Ratios are sum over sum; unavailable means no paired data or a zero denominator. Pre-event membership is reconstructed from LTE activity and may differ from current map membership used in monthly charts.</p>
            <div class="user-table-scroll"><table><thead><tr><th>Feature</th><th>Tier 1 (0-2 km)</th><th>Tier 2 (2-5 km)</th><th>Total cluster</th></tr></thead><tbody>
              <tr v-for="metric in userRatioRows" :key="metric.key"><th>{{ metric.label }}</th><td v-for="scope in ['tier1','tier2','cluster']" :key="scope" :title="features.user_context.support?.[scope]?.ratios?.[metric.key]?.unavailable_reason || 'Calculated from paired source counters'">{{ formatUserRatio(features.user_context[scope + '_' + metric.key]) }}</td></tr>
            </tbody></table></div>
          </section>
          <MAOSMonthlyChart :records="features.maos_monthly || []" :cell-records="features.maos_cells || []" :scopes="features.maos_scopes || {}" />
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
import MAOSMonthlyChart from './MAOSMonthlyChart.vue';

export default {
  name: 'SiteFeaturePopup',
  
  components: {
    ANPPolarChart,
    MAOSMonthlyChart
  },
  
  props: {
    siteId: {
      type: String,
      required: true
    },
    apiBaseUrl: {
      type: String,
      default: 'http://localhost:8000/api'
    },
    layoutUpdate: {
      type: Function,
      default: () => {}
    },
    searchQuery: {
      type: String,
      default: ''
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
      { id: 'population', label: 'Population' },
      { id: 'roads', label: 'Roads' },
      { id: 'network', label: 'KPIs & Config' },
      { id: 'anp', label: 'ANP' }
    ];
    
    const formatUserRatio = value => value == null ? 'Unavailable' : Number(value).toLocaleString(undefined, { maximumSignificantDigits: 6 });
    const userRatioRows = [{ key: 'edge_user_share', label: 'Edge user share' }, { key: 'edge_user_peak_ratio', label: 'Edge user peak ratio' }, { key: 'lowlatency_user_share', label: 'Low-latency user share' }];
    const roadRows = computed(() => [
      ['road_km_total', 'Total road length', 'km'], ['road_km_weighted', 'Weighted road length', 'km'],
      ['road_density_weighted_km_km2', 'Weighted road density', 'km/km²'], ['highway_km', 'Motorway + trunk length', 'km'],
      ['highway_share', 'Motorway + trunk share', '(0–1)'], ['n_road_intersections', 'Estimated road junctions', ''],
      ['dominant_road_class', 'Dominant road class', ''],
    ].map(([key,label,unit]) => ({ key,label,unit,value: features.value?.roads?.[key] })));
    const roadClasses = computed(() => {
      const values = Object.entries(features.value?.roads?.class_lengths_km || {});
      const max = Math.max(0.001, ...values.map(([,km]) => km));
      return values.sort((a,b) => b[1]-a[1]).map(([name,km]) => ({ name,km,share: 100*km/max }));
    });
    const populationRows = computed(() => [
      { key: 'population_density_1km_per_km2', label: 'Density within 1 km', unit: 'people/km²', quality: features.value?.population?.quality?.density_1km },
      { key: 'population_tier1', label: 'Tier 1 population (0–2 km)', unit: 'people', quality: features.value?.population?.quality?.tier1 },
      { key: 'population_tier2', label: 'Tier 2 population (2–5 km)', unit: 'people', quality: features.value?.population?.quality?.tier2 },
    ].map(item => ({ ...item, value: features.value?.population?.[item.key] })));
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

    const clusterBaselineMetrics = [
      {key:'avg_users',label:'Cluster active users (sum)',unit:'users'},
      {key:'avg_traffic_dl_gb',label:'Cluster DL traffic',unit:'GB/month'},
      {key:'avg_prb_util_pct',label:'Cluster DL PRB utilization',unit:'%'},
      {key:'avg_cqi',label:'Cluster weighted CQI',unit:''},
      {key:'cluster_pre_dl_throughput_kbps',label:'Cluster DL throughput',unit:'kbit/s'},
      {key:'cluster_pre_dl_packet_delay_ms',label:'Cluster latency',unit:'ms'},
      {key:'cluster_pre_cell_availability_pct',label:'Cluster availability',unit:'%'}
    ];
    const formatLabel = key => ({ total_prb_available: 'Site LTE capacity (PRBs)', neighbor_avg_antenna_height_m: 'Mean neighbor absolute antenna elevation (m ASL)', terrain_relief_class: 'Terrain relief (DEM slope)', z_antenna_m: 'Absolute antenna elevation (m ASL)' }[key] || key.replace(/_/g, ' ').replace(/\b\w/g, letter => letter.toUpperCase()));
    const eventLabel = eventType => ({
      SITE_ADDED: 'Site added', TECHNOLOGY_ADDED: 'Technology added', FREQUENCY_BAND_ADDED: 'Frequency band added', CELL_ADDED: 'Cell added', BANDWIDTH_UPGRADE: 'Bandwidth upgrade', BANDWIDTH_DOWNGRADE: 'Bandwidth downgrade',
      LTE_ADDED: 'LTE added',
      '3G_ADDED': '3G added',
      '2G_ADDED': '2G added'
    }[eventType] || eventType);
    const eventTitle = event => event.event_type === 'TECHNOLOGY_ADDED'
      ? `${event.technologies.join('/')} added` : eventLabel(event.event_type);
    const formatValue = value => {
      if (value === null || value === undefined || value === '') return 'N/A';
      if (typeof value === 'boolean') return value ? 'Yes' : 'No';
      return typeof value === 'number' ? Number(value.toFixed(3)).toString() : value;
    };
    
    /**
     * Fetch site features from API
     */
    let featureRequest = 0;
    const fetchFeatures = async () => {
      const request = ++featureRequest;
      loading.value = true;
      error.value = null;
      
      try {
        const response = await axios.get(`${props.apiBaseUrl}/sites/${props.siteId}/features/`, {
          params: props.searchQuery ? { search: props.searchQuery } : {}
        });
        if (request === featureRequest) features.value = response.data;
      } catch (err) {
        console.error('Error fetching site features:', err);
        if (request === featureRequest) error.value = 'Failed to load site features';
      } finally {
        if (request === featureRequest) loading.value = false;
        props.layoutUpdate();
      }
    };
    
    // Watch for site ID changes
    watch(() => props.siteId, () => {
      if (props.siteId) {
        fetchFeatures();
      }
    }, { immediate: true });

    watch(activeTab, () => props.layoutUpdate());
    
    return {
      features,
      loading,
      error,
      activeTab,
      tabs,
      populationRows,
      roadRows, roadClasses, userRatioRows, formatUserRatio,
      clusterLabel,
      clusterBadgeClass,
      positionLabel,
      positionBadgeClass,
      entropyDisplay,
      entropyClass,
      entropyPercentage,
      entropyDescription,
      formatLabel,
      formatValue,
      eventLabel, eventTitle, clusterBaselineMetrics
    };
  }
};
</script>

<style scoped>
.user-context-panel{margin:16px 0}.user-context-panel p{font-size:11px;color:#64748b;line-height:1.5}.user-table-scroll{overflow:auto}.user-context-panel table{font-size:11px;border-collapse:collapse;width:100%}.user-context-panel th,.user-context-panel td{padding:7px;text-align:left;border-bottom:1px solid #e2e8f0;white-space:nowrap}

.road-bar { height: 6px; background: #6366f1; border-radius: 3px; margin-top: 4px; }
.road-class { font-size: 12px; color: #475569; }
.population-panel { display: grid; gap: 12px; }
.population-panel .info-item { display: grid; gap: 5px; padding: 10px; background: #f8fafc; border-radius: 7px; }
.population-panel small, .population-panel p { color: #64748b; font-size: 12px; line-height: 1.5; }
.site-feature-popup {
  width: 100%;
  min-width: 0;
  max-width: none;
  overflow-wrap: anywhere;
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
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
}

.badge {
  flex: 0 0 auto;
  white-space: nowrap;
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

.badge.addition {
  background: #087f5b;
  color: #fff;
}

.added-cells {
  margin-top: 14px;
  padding: 12px;
  border: 1px solid #a7f3d0;
  border-radius: 8px;
  background: #ecfdf5;
}

.added-cells h4 { margin-bottom: 8px; color: #065f46; font-size: 13px; }
.added-cells ul { list-style: none; display: grid; gap: 6px; }
.added-cells li { display: flex; justify-content: space-between; gap: 12px; font-size: 12px; color: #1f2937; }
.added-cells li strong { overflow-wrap: anywhere; }
.added-cells li span { flex: 0 0 auto; font-variant-numeric: tabular-nums; }
.radio-events p { font-size: 12px; line-height: 1.5; margin-bottom: 10px; }
.radio-events li { flex-direction: column; gap: 5px; border-top: 1px solid #a7f3d0; padding-top: 8px; }
.radio-events li strong, .radio-events li span { overflow-wrap: anywhere; min-width: 0; }
.cell-plan { margin-top: 14px; }
.cell-plan h4 { margin-bottom: 4px; color: #374151; font-size: 13px; }
.cell-plan-note { margin: 0 0 8px; color: #6b7280; font-size: 11px; }
.cell-plan-list { display: grid; gap: 6px; max-height: 220px; overflow: auto; }
.cell-plan-card { padding: 8px; border: 1px solid #e5e7eb; border-radius: 6px; background: #fff; }
.cell-plan-added { border-color: #10b981; background: #ecfdf5; }
.cell-plan-heading { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; font-size: 12px; }
.cell-plan-heading strong { overflow-wrap: anywhere; }
.cell-plan-status { color: #047857; font-weight: 600; }
.cell-plan-features { display: flex; flex-wrap: wrap; gap: 4px 12px; margin-top: 4px; color: #6b7280; font-size: 11px; }
.matched-cells { margin-top: 12px; padding: 12px; border: 1px solid #bfdbfe; border-radius: 8px; background: #eff6ff; }
.matched-cells h4 { margin-bottom: 8px; color: #1d4ed8; font-size: 13px; }
.matched-cells ul { list-style: none; display: grid; gap: 6px; }
.matched-cells li { display: flex; justify-content: space-between; gap: 8px; font-size: 12px; }
.matched-cells li strong { overflow-wrap: anywhere; }

.tab-nav {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(72px, 1fr));
  background-color: #f5f5f5;
  border-bottom: 2px solid #ddd;
}

.tab-button {
  min-width: 0;
  padding: 9px 5px;
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

@media (max-width: 480px) {
  .site-header { padding: 11px; }
  .site-header h3 { font-size: 16px; }
  .tab-pane { padding: 10px; }
  .tab-button { font-size: 11px; padding: 8px 3px; }
  .info-grid { grid-template-columns: minmax(0, 1fr); gap: 9px; }
  .entropy-highlight { padding: 12px; margin-bottom: 12px; }
  .entropy-value { font-size: 28px; }
  .chart-header { align-items: flex-start; gap: 8px; }
  .chart-header h4 { font-size: 14px; }
  .edge-score { padding: 5px 7px; gap: 4px; }
  .score-label { font-size: 10px; }
  .score-value { font-size: 13px; }
  .maos-history .history-heading { align-items: flex-start; flex-direction: column; }
  .maos-history select { max-width: 100%; width: 100%; }
}
</style>
