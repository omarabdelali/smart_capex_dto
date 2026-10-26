<template>
  <section class="explorer-page">
    <header><p class="eyebrow">DATA EXPLORER</p><h2>Inspect counters, KPIs and features</h2><p>Filter the source data and inspect the calculations used by the project.</p></header>
    <p v-if="metadataError" role="alert" class="error">{{ metadataError }} <button @click="loadMetadata">Retry</button></p>
    <form class="explorer-card" @submit.prevent="loadRows(1)">
      <div class="filter-grid">
        <label>Dataset<select aria-label="Dataset" v-model="dataset" data-testid="dataset"><option value="raw">Raw monthly counters</option><option value="calculated">Calculated monthly KPIs</option><option value="features">Similarity feature profiles</option></select></label>
        <label>Site / cell search<input v-model="filters.search" placeholder="Site ID, site name or cell name" /></label>
        <label>Exact site ID<input v-model="filters.site_id" placeholder="All matching sites" /></label>
        <label>Cluster<select aria-label="Cluster" v-model="filters.cluster_id"><option value="">All clusters</option><option v-for="id in catalog?.clusters || []" :key="id" :value="String(id)">{{ id === -1 ? 'Noise sites (-1)' : id }}</option></select></label>
        <label>Technology<select aria-label="Technology" v-model="filters.technology"><option value="">All technologies</option><option v-for="tech in catalog?.technologies || []" :key="tech">{{ tech }}</option></select></label>
        <label>Cell name / ID<input v-model="filters.cell" placeholder="Optional cell filter" /></label>
        <template v-if="dataset !== 'features'">
          <label>From month<input v-model="filters.month_from" type="month" /></label><label>To month<input v-model="filters.month_to" type="month" /></label>
        </template>
        <label v-else>Profile cutoff (optional)<input v-model="filters.as_of" type="month" /><small>Blank uses each site's event cutoff; current sites use their latest history.</small></label>
        <label v-if="dataset === 'calculated'">Aggregation<select aria-label="Aggregation" v-model="filters.scope"><option value="cell">Cell</option><option value="site">Site</option><option value="cluster">Cluster</option><option value="tier1">Tier 1 · 0–2 km</option><option value="tier2">Tier 2 · 2–5 km</option></select></label>
        <label v-if="dataset === 'calculated' && ['tier1', 'tier2'].includes(filters.scope)">Tier origin site ID<input v-model="filters.origin_site_id" required placeholder="Required for distance tiers" /></label>
      </div>
      <details open class="column-picker"><summary>Columns · {{ columns.length }} selected</summary>
        <input v-model="columnSearch" type="search" placeholder="Find a counter, KPI or feature" aria-label="Find columns" />
        <div class="column-scroll"><label v-for="field in visibleFields" :key="field.key" :title="field.formula"><input v-model="columns" type="checkbox" :value="field.key" />{{ field.label }} <small>{{ field.unit }}</small></label></div>
      </details>
      <div class="filter-grid value-filters">
        <label>Filter by value<select aria-label="Filter by value" v-model="filters.value_field"><option value="">No value filter</option><option v-for="field in fields" :key="field.key" :value="field.key">{{ field.label }}</option></select></label>
        <label v-if="filters.value_field">Condition<select aria-label="Condition" v-model="filters.value_op"><option v-if="valueType !== 'categorical'" value="gte">At least</option><option v-if="valueType !== 'categorical'" value="lte">At most</option><option value="eq">Equals</option><option value="missing">Missing (NULL)</option><option value="present">Available (including zero)</option></select></label>
        <label v-if="filters.value_field && !['missing', 'present'].includes(filters.value_op)">Value<input v-model="filters.value" :type="valueType === 'categorical' ? 'text' : 'number'" step="any" required /></label>
      </div>
      <div class="actions"><button type="submit" :disabled="loading || !catalog || !columns.length">{{ loading ? 'Loading data…' : 'Apply filters' }}</button><label>Rows per page<select aria-label="Rows per page" v-model="pageSize"><option :value="25">25</option><option :value="50">50</option><option :value="100">100</option><option :value="200">200</option></select></label></div>
      <p>{{ catalog?.note }}</p><p v-if="dataset === 'calculated'">Filters apply before aggregation. Ratios pool paired raw counters. Active users are summed. Tier scopes exclude the origin site; noise sites stay separate in cluster totals.</p>
      <p v-if="dataset === 'features'">Technology and cell filters select whole-site profiles. Geography and population use the approved static assumption. Performance uses only months before the cutoff. Filtering feature values can take longer because profiles must be calculated.</p>
    </form>
    <p v-if="error" role="alert" class="error">{{ error }}</p><p v-if="stale && results" role="status" class="stale">Filters or columns changed. Apply filters to update the table.</p>
    <section v-if="results" class="explorer-card results" aria-label="Exploration results">
      <div class="result-heading"><strong>{{ results.count.toLocaleString() }} matching rows · {{ results.scope }} scope</strong><button type="button" @click="downloadCsv" :disabled="!results.rows.length">Export displayed page (CSV)</button></div>
      <p>{{ results.note }}</p>
      <div class="table-scroll"><table><thead><tr><th v-for="key in tableColumns" :key="key">{{ fieldLabel(key) }}<small>{{ fieldUnit(key) }}</small></th></tr></thead>
        <tbody><tr v-for="(row, index) in results.rows" :key="index"><td v-for="key in tableColumns" :key="key" :class="{ missing: row[key] == null }">{{ display(row[key]) }}</td></tr></tbody>
      </table></div>
      <p v-if="!results.rows.length" class="empty">No data matches these filters.</p>
      <div class="pagination"><button :disabled="loading || results.page <= 1 || stale" @click="loadRows(results.page - 1)">Previous</button><span>Page {{ results.page }} of {{ Math.max(1, Math.ceil(results.count / results.page_size)) }}</span><button :disabled="loading || results.page * results.page_size >= results.count || stale" @click="loadRows(results.page + 1)">Next</button></div>
      <details><summary>Sources and formulas for displayed columns</summary><dl><template v-for="key in results.columns" :key="key"><dt>{{ fieldLabel(key) }}</dt><dd>{{ fieldInfo(key)?.source }} · {{ fieldInfo(key)?.formula }}</dd></template></dl></details>
    </section>
  </section>
</template>

<script setup>
import axios from 'axios';
import { computed, onMounted, onBeforeUnmount, reactive, ref, watch } from 'vue';
const API = 'http://localhost:8000/api';
const catalog = ref(null), metadataError = ref(''), error = ref(''), loading = ref(false), results = ref(null);
const dataset = ref('raw'), columns = ref([]), columnSearch = ref(''), pageSize = ref(50), applied = ref('');
const filters = reactive({ search: '', site_id: '', cluster_id: '', technology: '', cell: '', month_from: '', month_to: '', as_of: '', scope: 'site', origin_site_id: '', value_field: '', value_op: 'gte', value: '' });
const fields = computed(() => catalog.value?.datasets?.[dataset.value] || []);
const visibleFields = computed(() => fields.value.filter(f => `${f.key} ${f.label}`.toLowerCase().includes(columnSearch.value.toLowerCase())));
const valueType = computed(() => fields.value.find(f => f.key === filters.value_field)?.type);
const signature = computed(() => JSON.stringify([dataset.value, columns.value, filters, pageSize.value]));
const stale = computed(() => applied.value !== signature.value);
let requestId = 0;
watch(dataset, () => { columns.value = fields.value.slice(0, 6).map(f => f.key); filters.value_field = ''; columnSearch.value = ''; });
watch(valueType, value => { if (value === 'categorical' && ['gte', 'lte'].includes(filters.value_op)) filters.value_op = 'eq'; });
async function loadMetadata() {
  metadataError.value = '';
  try { catalog.value = (await axios.get(`${API}/explore/metadata/`)).data; columns.value = fields.value.slice(0, 6).map(f => f.key); }
  catch (e) { metadataError.value = e.response?.data?.error || 'Could not load the data catalog.'; }
}
async function loadRows(page = 1) {
  const token = ++requestId, submitted = signature.value;
  loading.value = true; error.value = '';
  const params = { ...filters, dataset: dataset.value, columns: columns.value.join(','), page, page_size: pageSize.value };
  if (dataset.value === 'features') { delete params.month_from; delete params.month_to; } else delete params.as_of;
  try {
    const response = await axios.get(`${API}/explore/`, { params });
    if (token === requestId) { results.value = response.data; applied.value = submitted; }
  } catch (e) { if (token === requestId) error.value = e.response?.data?.error || 'Could not load filtered data.'; }
  finally { if (token === requestId) loading.value = false; }
}
const tableColumns = computed(() => {
  const identity = results.value?.dataset === 'features' ? ['site_id', 'site_name', 'cluster_id', 'as_of', 'event_date'] : ['month', 'site_id', 'site_name', 'cluster_id', 'cell', 'technology', 'reporting_cells', 'reporting_sites'];
  return [...new Set([...identity.filter(key => results.value?.rows.some(row => row[key] != null)), ...(results.value?.columns || [])])];
});
function fieldInfo(key) { return catalog.value?.datasets?.[results.value?.dataset || dataset.value]?.find(f => f.key === key); }
function fieldLabel(key) { return fieldInfo(key)?.label || key.replaceAll('_', ' '); }
function fieldUnit(key) { return fieldInfo(key)?.unit || ''; }
function display(value) { return value == null ? 'NULL' : typeof value === 'number' ? value.toLocaleString(undefined, { maximumSignificantDigits: 12 }) : String(value); }
function downloadCsv() {
  function quote(value) { const str = value == null ? '' : String(value); const safe = typeof value === 'string' && /^[=+\-@\t\r]/.test(str) ? `'${str}` : str; return `"${safe.replaceAll('"', '""')}"`; }
  const text = [tableColumns.value.map(quote).join(','), ...results.value.rows.map(row => tableColumns.value.map(key => quote(row[key])).join(','))].join('\r\n');
  const url = URL.createObjectURL(new Blob(['\ufeff', text], { type: 'text/csv;charset=utf-8;' }));
  const link = document.createElement('a'); link.href = url; link.download = `smart-capex-${results.value.dataset}-page-${results.value.page}.csv`; link.click(); URL.revokeObjectURL(url);
}
onMounted(loadMetadata);
onBeforeUnmount(() => { requestId += 1; });
</script>

<style scoped>
.explorer-page { height: 100%; overflow: auto; padding: clamp(16px, 3vw, 32px); background: #f5f7fb; color: #1e293b; }
header { margin-bottom: 20px; } h2 { margin: 6px 0; font-size: 27px; } p { font-size: 13px; line-height: 1.6; color: #526175; margin: 8px 0; }
.eyebrow { font-size: 11px; letter-spacing: .12em; font-weight: 700; }
.explorer-card { border: 1px solid #dbe2ea; border-radius: 12px; background: white; padding: 18px; margin-bottom: 16px; }
.filter-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 14px; }
label { display: flex; flex-direction: column; gap: 5px; font-size: 12px; font-weight: 600; } input, select { min-width: 0; border: 1px solid #cbd5e1; border-radius: 6px; padding: 9px; background: white; color: #1e293b; font: inherit; }
small { display: block; color: #64748b; font-size: 11px; font-weight: normal; } button { background: #2563eb; color: white; border: 0; border-radius: 6px; padding: 10px 14px; font: inherit; cursor: pointer; } button:disabled { opacity: .45; cursor: not-allowed; }
.column-picker { margin: 18px 0; } summary { font-size: 13px; font-weight: 600; cursor: pointer; margin-bottom: 10px; } .column-picker > input { width: 100%; margin-bottom: 8px; }
.column-scroll { max-height: 220px; overflow: auto; display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); border: 1px solid #e2e8f0; padding: 10px; gap: 10px; }
.column-scroll label { flex-direction: row; align-items: center; gap: 8px; font-weight: 400; }.column-scroll input { flex-shrink: 0; }
.actions, .result-heading, .pagination { display: flex; gap: 14px; align-items: center; flex-wrap: wrap; margin: 15px 0; }.actions label { flex-direction: row; align-items: center; }.result-heading { justify-content: space-between; }
.table-scroll { overflow: auto; max-height: 530px; border: 1px solid #dbe2ea; } table { border-collapse: collapse; width: 100%; font-size: 12px; } th, td { padding: 10px 12px; border-bottom: 1px solid #e2e8f0; white-space: nowrap; text-align: left; } th { background: #f1f5f9; position: sticky; top: 0; } tr:hover { background: #f8fafc; }.missing { color: #b45309; font-style: italic; }.pagination { justify-content: center; font-size: 13px; }
.error { color: #b91c1c; }.stale { color: #92400e; }.empty { padding: 24px; text-align: center; } dt { font-size: 13px; font-weight: 600; margin-top: 10px; } dd { font-size: 12px; color: #526175; line-height: 1.5; }
@media (max-width: 600px) { .filter-grid { grid-template-columns: 1fr; }.explorer-card { padding: 12px; }h2 { font-size: 22px; } }
</style>
