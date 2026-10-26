<template>
  <section class="similarity-page">
    <header class="page-header">
      <div>
        <p class="eyebrow">HISTORICAL CASE RETRIEVAL</p>
        <h2>Site similarity</h2>
        <p>Find detected launch or addition sites with similar configuration, location context, and pre-event LTE performance.</p>
      </div>
      <span class="mode-badge">Retrieval only</span>
    </header>

    <section class="search-card" aria-label="Choose a query site">
      <label for="site-search">Search by site ID, site name, or cell name</label>
      <div class="search-row">
        <input id="site-search" v-model="searchText" type="search" autocomplete="off" placeholder="Enter at least 2 characters" @keydown.enter.prevent="chooseFirst" />
        <button type="button" :disabled="!selectedSite || availabilityLoading || loading || !selectedFeatures.length" @click="runSearch">{{ results ? 'Update similarity' : 'Find similar sites' }}</button>
      </div>
      <div v-if="suggestions.length" class="suggestions" role="listbox" aria-label="Matching sites">
        <button v-for="site in suggestions" :key="site.site_id" type="button" role="option" @click="selectSite(site)">
          <strong>{{ site.site_name }}</strong><span>{{ site.site_id }}</span>
        </button>
      </div>
      <p v-if="selectedSite" class="selected-site">Selected: <strong>{{ selectedSite.site_name }}</strong> Â· {{ selectedSite.site_id }}</p>
      <section v-if="selectedSite" class="feature-picker" aria-label="Select similarity features">
        <label>Weighting mode <select v-model="weightingMode"><option value="equal_per_feature">Equal per feature (current default)</option><option value="equal_per_group">Equal per group</option></select></label>
        <p class="scope-note">Roads are optional and uncalibrated, capped at 5% of distance weight. Select a non-road feature too. Road values describe the current snapshot, not verified event-time conditions.</p>
        <div class="picker-heading"><div><strong>Features used for similarity</strong><p>Select available query features. Missing candidate values are skipped for that case.</p></div>
          <span>{{ selectedFeatures.length }} selected</span></div>
        <p v-if="availabilityLoading" class="picker-status" role="status">Checking feature availabilityâ€¦</p>
        <p v-else-if="featureError" class="error-message" role="alert">{{ featureError }}</p>
        <template v-else-if="featureOptions.length">
          <div class="picker-actions"><button type="button" @click="selectAllAvailable">Select available</button><button type="button" @click="clearFeatureSelection">Clear</button></div>
          <div class="feature-groups">
            <fieldset v-for="group in featureGroups" :key="group.key">
              <legend>{{ group.label }}</legend>
              <label v-for="feature in group.features" :key="feature.key" class="feature-choice" :class="{ 'feature-choice-unavailable': !feature.available }">
                <input v-model="selectedFeatures" type="checkbox" :value="feature.key" :disabled="!feature.available || availabilityLoading">
                <span>{{ feature.label || feature.key.replaceAll('_', ' ') }}</span>
                <small v-if="!feature.available" class="unavailable-label">Unavailable</small>
                <small v-else class="feature-choice-value">{{ displayFeature(feature.value) }} {{ feature.unit }}</small>
              </label>
            </fieldset>
          </div>
        </template>
      </section>
      <p v-if="resultsStale" class="selection-stale" role="status">Feature selection changed. Run the search again to update the scores.</p>
      <p v-if="searchError" class="error-message" role="alert">{{ searchError }}</p>
    </section>

    <p class="scope-note">The available MAOS history is LTE-only. Similarity scores rank historical cases; they are not predicted KPI impacts. Tier 1 population covers 0–2 km; Tier 2 covers the separate 2–5 km ring. Population uses native 100 m GHSL 2025 estimates and is unavailable for events before 2025.</p>
    <p v-if="results?.query.feature_timing_note" class="scope-note">{{ results.query.feature_timing_note }}</p>
    <p v-if="results" class="scope-note">Population features are mapped counts, without extrapolating missing land. Query land coverage: T1 {{ results.query.population_quality?.tier1?.land_coverage == null ? 'Unavailable' : (100 * results.query.population_quality.tier1.land_coverage).toFixed(1) + '%' }}, T2 {{ results.query.population_quality?.tier2?.land_coverage == null ? 'Unavailable' : (100 * results.query.population_quality.tier2.land_coverage).toFixed(1) + '%' }}. Partial estimates may understate full catchment population.</p>
    <p v-if="loading" class="state-message" role="status">Building pre-event profiles and ranking casesâ€¦</p>
    <p v-else-if="error" class="state-message error-message" role="alert">{{ error }}</p>

    <template v-else-if="results">
      <section class="query-summary">
        <div>
          <p class="eyebrow">QUERY SITE</p>
          <h3>{{ results.query.site_name }}</h3>
          <p>{{ results.query.site_id }}<span v-if="results.query.event_date"> Â· Event {{ results.query.event_date }}</span><span v-else> Â· Current site profile as of {{ results.query.as_of_date }}</span></p>
        </div>
        <div class="coverage"><strong>{{ results.query.profile_months_available }} / 3</strong><span>pre-event months</span><strong>{{ percent(results.query.profile_completeness) }}</strong><span>profile coverage</span></div>
      </section>

      <div class="ranking-summary">
        <strong>{{ results.candidate_pool_size.toLocaleString() }}</strong> cases scored from {{ results.total_detected_event_sites.toLocaleString() }} detected event sites
        <span>{{ results.filter_explanation }}</span>
        <span>{{ results.active_features.length }} selected dimensions · {{ results.weighting_method === 'equal_per_group' ? 'group-balanced weights' : 'per-feature weights with existing non-road defaults' }} · road weight capped at 5%.</span>
        <span v-if="Object.keys(results.excluded_features).some(key => results.excluded_features[key] === 'unavailable_for_all_candidates')">Some selected features were unavailable across the candidate pool and were excluded.</span>
      </div>
      <p v-if="!results.active_features.length" class="state-message">None of the selected features are available across the filtered candidate pool. Choose different features and rerun the search.</p>
      <p v-else-if="!results.cases.length" class="state-message">No eligible historical cases were found.</p>

      <section v-else class="case-list" aria-label="Most similar historical cases">
        <article v-for="(item, index) in results.cases" :key="item.site_id" class="case-card">
          <div class="case-heading">
            <div class="rank">{{ index + 1 }}</div>
            <div class="case-title"><h3>{{ item.site_name }}</h3><p>{{ item.site_id }} Â· {{ item.event_date || 'Event date unavailable' }} Â· {{ eventLabel(item.event_type) }}<span v-if="item.technology"> Â· {{ item.technology }}</span></p></div>
            <div class="score"><strong>{{ percent(item.similarity) }}</strong><span>similarity</span></div>
          </div>
          <div class="case-meta">
            <span>Distance {{ item.distance.toFixed(3) }}</span>
            <span>Kernel weight {{ percent(item.weight) }}</span>
            <span>{{ item.profile_months_available }} / 3 months</span>
            <span>{{ percent(item.profile_completeness) }} profile coverage</span>
            <span>{{ item.used_features.length }} dimensions used</span>
            <span>Current map cluster {{ item.cluster_id }}</span>
          </div>
          <button type="button" class="map-button" @click="showOnMap">Show query and similar sites on map</button>
          <details class="feature-details">
            <summary>All specification similarity features ({{ featureRows.length }})</summary>
            <div class="feature-table-wrap"><table><thead><tr><th>Feature</th><th>Query site</th><th>Similar site</th><th>Weight</th><th>Score</th></tr></thead>
              <tbody><tr v-for="feature in featureRows" :key="feature.key" :class="{ unavailable: isUnavailable(results.query.similarity_features[feature.key]) || isUnavailable(item.similarity_features[feature.key]) }">
                <th scope="row">{{ feature.label }}</th><td>{{ displayFeature(results.query.similarity_features[feature.key]) }}</td><td>{{ displayFeature(item.similarity_features[feature.key]) }}</td><td>{{ featureWeight(feature.key, item) }}</td><td>{{ featureStatus(feature.key, item) }}</td>
              </tr></tbody></table></div>
          </details>
          <div class="metric-grid">
            <div v-for="metric in metrics" :key="metric.key" class="metric-compare">
              <span>{{ metric.label }}</span>
              <strong>{{ formatMetric(results.query.profile[metric.key], metric) }}</strong>
              <small>Case: {{ formatMetric(item.profile[metric.key], metric) }}</small>
            </div>
          </div>
        </article>
      </section>
    </template>
    <p v-else-if="!loading" class="state-message">Choose a site to retrieve its closest historical cases.</p>
  </section>
</template>

<script>
import axios from 'axios';
import { computed, onBeforeUnmount, ref, watch } from 'vue';

export default {
  name: 'SimilarityExplorerView',
  emits: ['show-on-map'],
  setup(_props, { emit }) {
    const API = 'http://localhost:8000/api';
    const searchText = ref('');
    const suggestions = ref([]);
    const selectedSite = ref(null);
    const results = ref(null);
    const loading = ref(false);
    const availabilityLoading = ref(false);
    const featureOptions = ref([]);
    const selectedFeatures = ref([]);
    const weightingMode = ref('equal_per_feature');
    const featureError = ref('');
    const error = ref('');
    const searchError = ref('');
    let searchTimer = null;
    let selectedLabel = '';
    let availabilityRequest = 0;
    const metrics = [
      { key: 'pre_dl_traffic_gb_day', label: 'DL traffic / day', unit: 'GB/day' },
      { key: 'pre_prb_util_dl_pct', label: 'DL PRB utilization', unit: '%' },
      { key: 'pre_cqi_avg', label: 'Weighted CQI', unit: '' },
      { key: 'pre_dl_throughput_kbps', label: 'DL throughput', unit: 'kbit/s' },
      { key: 'pre_dl_packet_delay_ms', label: 'DL packet delay', unit: 'ms' },
      { key: 'pre_cell_availability_pct', label: 'Cell availability', unit: '%' },
    ];
      const populationLabels = { population_density_1km_per_km2: 'Population density (1 km) · people/km²', population_tier1: 'Tier 1 population (0–2 km) · people', population_tier2: 'Tier 2 population (2–5 km) · people' };
      const featureRows = computed(() => Object.keys(results.value?.query?.similarity_features || {}).map(key => ({ key, label: populationLabels[key] || featureOptions.value.find(f => f.key === key)?.label || key.replaceAll('_', ' ') })));
    const featureGroups = computed(() => {
      const labels = { configuration: 'Configuration', prelaunch: 'Pre-launch and LTE KPIs', spatial: 'Spatial context', anp: 'Angular Neighborhood Profile', cluster: 'Cluster context', clutter: 'Terrain and clutter', population: 'Population · GHSL 2025 · 100 m', road_context: 'Road context · optional current snapshot', other: 'Other' };
      const groups = new Map();
      for (const feature of featureOptions.value) {
        if (!groups.has(feature.group)) groups.set(feature.group, { key: feature.group, label: labels[feature.group] || feature.group, features: [] });
        groups.get(feature.group).features.push(feature);
      }
      return [...groups.values()];
    });
    const resultsStale = computed(() => results.value && (
      [...selectedFeatures.value].sort().join('|') !== [...results.value.selected_features].sort().join('|') || weightingMode.value !== results.value.weighting_method
    ));

    watch(searchText, value => {
      if (selectedLabel && value === selectedLabel) {
        selectedLabel = '';
        return;
      }
      selectedSite.value = null;
      results.value = null;
      featureOptions.value = [];
      selectedFeatures.value = [];
      featureError.value = '';
      availabilityRequest += 1;
      availabilityLoading.value = false;
      searchError.value = '';
      suggestions.value = [];
      if (searchTimer) window.clearTimeout(searchTimer);
      const term = value.trim();
      if (term.length < 2) return;
      searchTimer = window.setTimeout(async () => {
        try {
          const response = await axios.get(`${API}/sites/`, { params: { search: term } });
          suggestions.value = (response.data.results || []).slice(0, 8);
        } catch (_error) {
          searchError.value = 'Could not search sites. Check that the backend is running.';
        }
      }, 250);
    });

    function selectSite(site) {
      selectedSite.value = site;
      selectedLabel = `${site.site_name} (${site.site_id})`;
      searchText.value = selectedLabel;
      suggestions.value = [];
      searchError.value = '';
      results.value = null;
      featureOptions.value = [];
      selectedFeatures.value = [];
      featureError.value = '';
      void loadFeatureAvailability(site);
    }
    async function loadFeatureAvailability(site) {
      const requestId = ++availabilityRequest;
      availabilityLoading.value = true;
      featureError.value = '';
      try {
        const response = await axios.get(`${API}/similarity/features/`, { params: { site_id: site.site_id } });
        if (requestId !== availabilityRequest || selectedSite.value?.site_id !== site.site_id) return;
        featureOptions.value = response.data.features || [];
        selectedFeatures.value = featureOptions.value.filter(feature => feature.available && feature.default_selected !== false).map(feature => feature.key);
      } catch (requestError) {
        if (requestId === availabilityRequest) {
          featureError.value = requestError.response?.data?.error || 'Could not load feature availability.';
        }
      } finally {
        if (requestId === availabilityRequest) availabilityLoading.value = false;
      }
    }
    function selectAllAvailable() {
      selectedFeatures.value = featureOptions.value.filter(feature => feature.available).map(feature => feature.key);
    }
    function clearFeatureSelection() { selectedFeatures.value = []; }
    function chooseFirst() { if (suggestions.value.length) selectSite(suggestions.value[0]); }
    async function runSearch() {
      if (!selectedSite.value) return;
      loading.value = true;
      error.value = '';
      results.value = null;
      try {
        const response = await axios.get(`${API}/similarity/search/`, {
          params: { site_id: selectedSite.value.site_id, k: 10, features: selectedFeatures.value.join(','), weighting_mode: weightingMode.value },
        });
        results.value = response.data;
      } catch (requestError) {
        error.value = requestError.response?.data?.error || 'Could not rank similar sites.';
      } finally { loading.value = false; }
    }
    function percent(value) { return value == null ? 'Unavailable' : `${(Number(value) * 100).toFixed(1)}%`; }
    function formatMetric(value, metric) {
      if (value == null || !Number.isFinite(Number(value))) return 'Unavailable';
      const number = Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 });
      return metric.unit ? `${number} ${metric.unit}` : number;
    }
    function eventLabel(value) {
      return ({ NEW_SITE: 'New site', TECH_ADD: 'Technology addition', SECTOR_ADD: 'Sector addition', BASELINE: 'Baseline' })[value] || value || 'Unknown event';
    }
    function isUnavailable(value) { return value === null || value === undefined || value === ''; }
    function featureStatus(key, item) {
      if (item.feature_exclusions?.[key] === 'road_context_mismatch') return 'Skipped: different road snapshot';
      if (results.value.excluded_features[key] === 'unavailable_for_all_candidates') return 'Unavailable in candidates';
      if (!results.value.selected_features.includes(key)) return item.feature_weights?.[key] ? 'Legacy default' : 'Not selected';
      return item.used_features.includes(key) ? 'Used' : 'Skipped: missing';
    }
    function featureWeight(key, item) {
      const weight = item.feature_weights?.[key];
      return weight ? `${(100 * weight).toFixed(2)}%` : '—';
    }
    function displayFeature(value) {
      if (isUnavailable(value)) return 'Unavailable';
      if (typeof value === 'boolean') return value ? 'Yes' : 'No';
      return typeof value === 'number' ? value.toLocaleString(undefined, { maximumFractionDigits: 3 }) : String(value);
    }
    function showOnMap() {
      if (!results.value || !selectedSite.value) return;
      emit('show-on-map', { querySiteId: selectedSite.value.site_id, siteIds: [...new Set([selectedSite.value.site_id, ...results.value.cases.map(item => item.site_id)])] });
    }
    onBeforeUnmount(() => { if (searchTimer) window.clearTimeout(searchTimer); });
    return { weightingMode, searchText, suggestions, selectedSite, results, loading, error, searchError, availabilityLoading, featureOptions, selectedFeatures, featureError, featureGroups, featureRows, resultsStale, selectSite, chooseFirst, runSearch, selectAllAvailable, clearFeatureSelection, percent, formatMetric, eventLabel, isUnavailable, displayFeature, featureStatus, featureWeight, showOnMap };
  },
};
</script>

<style scoped>
.similarity-page { height: 100%; overflow: auto; padding: clamp(16px, 3vw, 34px); background: #f5f7fb; color: #1e293b; }
.page-header, .case-heading, .ranking-summary { display: flex; align-items: center; gap: 14px; }
.page-header { justify-content: space-between; margin-bottom: 20px; }
.eyebrow { color: #64748b; font-size: 10px; font-weight: 700; letter-spacing: .12em; }
h2 { margin: 5px 0; font-size: clamp(23px, 3vw, 30px); } h3 { margin: 0; font-size: 16px; }
.page-header p:last-child { max-width: 760px; color: #64748b; line-height: 1.45; }
.mode-badge { flex: 0 0 auto; padding: 7px 10px; border-radius: 99px; color: #075985; background: #e0f2fe; font-size: 12px; font-weight: 700; }
.search-card, .query-summary, .case-card { border: 1px solid #e2e8f0; border-radius: 11px; background: white; box-shadow: 0 4px 14px #0f172a08; }
.search-card { position: relative; max-width: 920px; padding: 16px; }
.search-card label { display: block; margin-bottom: 7px; color: #475569; font-size: 12px; font-weight: 700; }
.search-row { display: flex; gap: 8px; }
input { min-width: 0; flex: 1; height: 40px; padding: 8px 11px; border: 1px solid #cbd5e1; border-radius: 7px; font: inherit; }
button { border: 0; border-radius: 7px; padding: 9px 13px; background: #2563eb; color: #fff; font: inherit; font-weight: 600; cursor: pointer; }
button:disabled { opacity: .45; cursor: not-allowed; }
.suggestions { position: absolute; z-index: 3; top: 84px; left: 16px; right: 16px; max-height: 280px; overflow: auto; border: 1px solid #cbd5e1; border-radius: 8px; background: white; box-shadow: 0 10px 24px #0f172a1c; }
.suggestions button { display: flex; width: 100%; justify-content: space-between; border-radius: 0; border-bottom: 1px solid #f1f5f9; background: white; color: #1e293b; text-align: left; }
.suggestions button:hover { background: #eff6ff; }.suggestions span { color: #64748b; font-size: 12px; }
.selected-site { margin-top: 10px; color: #475569; font-size: 12px; }
.feature-picker { margin-top: 14px; padding-top: 13px; border-top: 1px solid #e2e8f0; }
.picker-heading { display: flex; justify-content: space-between; gap: 10px; color: #334155; font-size: 12px; }
.picker-heading p { margin-top: 4px; color: #64748b; font-size: 11px; font-weight: 400; }
.picker-heading > span { flex: 0 0 auto; color: #1d4ed8; font-size: 11px; font-weight: 700; }
.picker-status { padding: 12px 0; color: #64748b; font-size: 12px; }
.picker-actions { display: flex; gap: 7px; margin: 10px 0; }
.picker-actions button { padding: 6px 9px; background: #e2e8f0; color: #334155; font-size: 11px; }
.feature-groups { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 8px; max-height: 370px; overflow: auto; padding: 2px; }
.feature-groups fieldset { min-width: 0; padding: 8px; border: 1px solid #e2e8f0; border-radius: 7px; }
.feature-groups legend { padding: 0 4px; color: #475569; font-size: 10px; font-weight: 700; }
.feature-choice { display: flex; min-width: 0; align-items: center; gap: 6px; padding: 4px 2px; color: #334155; font-size: 10px; cursor: pointer; }
.feature-choice input { flex: 0 0 auto; width: 13px; height: 13px; margin: 0; padding: 0; }
.feature-choice > span { flex: 1; text-transform: capitalize; }
.feature-choice-value { max-width: 80px; overflow: hidden; color: #64748b; text-overflow: ellipsis; white-space: nowrap; }
.feature-choice-unavailable, .unavailable-label { color: #b91c1c !important; }
.feature-choice input:disabled { cursor: not-allowed; }
.selection-stale { margin: 10px 0; padding: 9px 11px; border-radius: 6px; background: #fff7ed; color: #9a3412; font-size: 11px; }
.scope-note { margin: 14px 0; color: #64748b; font-size: 12px; line-height: 1.45; }
.state-message { padding: 18px 0; color: #64748b; }.error-message { color: #b91c1c; }
.query-summary { display: flex; align-items: center; justify-content: space-between; gap: 14px; padding: 15px 18px; }
.query-summary p:last-child { margin-top: 5px; color: #64748b; font-size: 12px; }
.coverage { display: grid; grid-template-columns: auto auto; align-items: baseline; gap: 3px 8px; color: #64748b; font-size: 11px; }
.coverage strong { color: #0f172a; font-size: 15px; font-variant-numeric: tabular-nums; }
.ranking-summary { flex-wrap: wrap; margin: 14px 0; color: #475569; font-size: 12px; }.ranking-summary strong { color: #0f172a; font-size: 16px; }.ranking-summary span { flex-basis: 100%; color: #64748b; }
.case-list { display: grid; gap: 12px; }.case-card { padding: 14px; }
.rank { display: grid; width: 29px; height: 29px; flex: 0 0 auto; place-items: center; border-radius: 50%; background: #eff6ff; color: #1d4ed8; font-weight: 700; }
.case-heading { align-items: center; }.case-title { min-width: 0; flex: 1; }.case-title p { margin-top: 4px; color: #64748b; font-size: 12px; }
.score { display: grid; justify-items: end; gap: 2px; }.score strong { color: #047857; font-size: 20px; font-variant-numeric: tabular-nums; }.score span { color: #64748b; font-size: 10px; text-transform: uppercase; }
.case-meta { display: flex; flex-wrap: wrap; gap: 7px; margin: 12px 0; }.case-meta span { padding: 4px 7px; border-radius: 5px; background: #f1f5f9; color: #475569; font-size: 10px; }
.map-button { margin: 0 0 10px; background: #0f766e; font-size: 12px; }
.feature-details { margin: 0 0 12px; border: 1px solid #e2e8f0; border-radius: 7px; }
.feature-details summary { padding: 10px; color: #334155; cursor: pointer; font-size: 12px; font-weight: 700; }
.feature-table-wrap { max-height: 380px; overflow: auto; }
.feature-table-wrap table { width: 100%; min-width: 620px; border-collapse: collapse; font-size: 11px; }
.feature-table-wrap th, .feature-table-wrap td { padding: 7px 9px; border-top: 1px solid #e2e8f0; text-align: left; }
.feature-table-wrap thead { position: sticky; top: 0; background: #f1f5f9; }
.feature-table-wrap tbody th { color: #475569; font-weight: 500; text-transform: capitalize; }
.feature-table-wrap td:nth-child(4) { font-variant-numeric: tabular-nums; white-space: nowrap; }
.feature-table-wrap tr.unavailable { background: #fff1f2; color: #b91c1c; }
.feature-table-wrap tr.unavailable th, .feature-table-wrap tr.unavailable td { color: #b91c1c; }
.metric-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 7px; }
.metric-compare { display: grid; gap: 4px; padding: 9px; border-radius: 7px; background: #f8fafc; }.metric-compare > span { color: #64748b; font-size: 10px; }.metric-compare strong { font-size: 13px; font-variant-numeric: tabular-nums; }.metric-compare small { color: #475569; font-size: 11px; }
@media(max-width: 620px) { .page-header, .query-summary { align-items: stretch; flex-direction: column; }.mode-badge { align-self: start; }.search-row { flex-direction: column; }.suggestions { top: 108px; }.score { align-self: start; }.case-heading { flex-wrap: wrap; }.case-title { flex-basis: calc(100% - 50px); }.score { margin-left: 43px; }.coverage { align-self: start; }.picker-heading { align-items: flex-start; }.feature-groups { grid-template-columns: 1fr; max-height: 330px; } }
</style>
