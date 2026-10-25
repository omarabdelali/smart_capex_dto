<template>
  <section class="cluster-analysis" aria-labelledby="cluster-analysis-title">
    <header class="analysis-header">
      <div>
        <h2 id="cluster-analysis-title">Cluster analysis</h2>
        <p>Explore cluster context, monthly KPI trends, and detected site or cell events.</p>
      </div>
      <label class="cluster-picker">
        <span>Cluster</span>
        <select v-model="selectedCluster" :disabled="!clusters.length" aria-label="Select a cluster">
          <option v-for="cluster in clusters" :key="cluster.cluster_id" :value="cluster.cluster_id">
            Cluster {{ cluster.cluster_id }} · {{ cluster.site_count }} sites
          </option>
        </select>
      </label>
    </header>

    <p v-if="loading" class="page-message" role="status">Loading cluster analysis…</p>
    <p v-else-if="error" class="page-message error-message" role="alert">{{ error }}</p>
    <p v-else-if="!clusters.length" class="page-message">No clusters are available.</p>

    <template v-else-if="analysis">
      <section class="context-grid" aria-label="Cluster context">
        <article class="context-value"><span>Sites</span><strong>{{ analysis.context.site_count }}</strong></article>
        <article class="context-value"><span>Edge / interior</span><strong>{{ analysis.context.edge_sites }} / {{ analysis.context.interior_sites }}</strong></article>
        <article class="context-value"><span>Sites with MAOS</span><strong>{{ analysis.context.sites_with_maos }}</strong></article>
        <article class="context-value"><span>Detected events</span><strong>{{ analysis.context.event_count }}</strong></article>
        <article class="context-value"><span>Cluster density</span><strong>{{ formatNumber(analysis.context.cluster_density_sites_per_km2) }} sites/km²</strong></article>
        <article class="context-value"><span>Mean centroid distance</span><strong>{{ formatNumber(analysis.context.avg_dist_to_centroid_m) }} m</strong></article>
      </section>

      <section class="timeline-section" aria-labelledby="cluster-kpi-title">
        <div class="section-heading">
          <div>
            <h3 id="cluster-kpi-title">Monthly cluster KPIs</h3>
            <p>Vertical markers show months with detected launches or additions.</p>
          </div>
          <label class="metric-picker">
            <span>KPI</span>
            <select v-model="selectedMetric" aria-label="Select cluster KPI">
              <option v-for="metric in metrics" :key="metric.key" :value="metric.key">{{ metric.label }}</option>
            </select>
          </label>
        </div>
        <div v-if="analysis.monthly_kpis.length" class="chart-frame">
          <canvas ref="chartCanvas" role="img" :aria-label="`${activeMetric.label} by month with event markers`"></canvas>
        </div>
        <p v-else class="empty-state">No linked MAOS history is available for this cluster.</p>
        <div class="timeline-legend"><span class="event-line-key" aria-hidden="true"></span><span>Detected event month</span></div>
      </section>

      <section class="events-section" aria-labelledby="cluster-events-title">
        <div class="section-heading">
          <div>
            <h3 id="cluster-events-title">Events in this cluster</h3>
            <p>All detected cell events are listed by date; events sharing a month share a chart marker.</p>
          </div>
          <span class="event-total">{{ analysis.events.length }} events</span>
        </div>
        <div v-if="analysis.events.length" class="events-table-wrap">
          <table class="events-table">
            <thead>
              <tr><th>Date</th><th>Event</th><th>Site</th><th>Cell</th><th>Technology</th></tr>
            </thead>
            <tbody>
              <tr v-for="event in analysis.events" :key="`${event.cell_id}-${event.event_date}`">
                <td>{{ event.event_date }}</td>
                <td><span class="event-kind" :class="eventClass(event.event_type)">{{ eventLabel(event.event_type) }}</span></td>
                <td><strong>{{ event.site_name }}</strong><small>{{ event.site_id }}</small></td>
                <td>{{ event.cell_name }}</td>
                <td>{{ event.technology }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-else class="empty-state">No detected launch or cell-addition events in this cluster.</p>
      </section>
    </template>
  </section>
</template>

<script>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import axios from 'axios';
import {
  Chart, LineController, LineElement, PointElement, LinearScale,
  CategoryScale, Tooltip, Legend
} from 'chart.js';

Chart.register(LineController, LineElement, PointElement, LinearScale, CategoryScale, Tooltip, Legend);

const eventTimelinePlugin = {
  id: 'clusterEventTimeline',
  afterDatasetsDraw(chart, _args, options) {
    const events = options.events || [];
    const labels = chart.data.labels || [];
    const xScale = chart.scales.x;
    const chartArea = chart.chartArea;
    if (!xScale || !chartArea || !events.length) return;

    const eventCounts = new Map();
    for (const event of events) {
      const month = event.event_date.slice(0, 7);
      eventCounts.set(month, (eventCounts.get(month) || 0) + 1);
    }

    const { ctx } = chart;
    ctx.save();
    ctx.strokeStyle = '#c2410c';
    ctx.fillStyle = '#9a3412';
    ctx.lineWidth = 1;
    ctx.setLineDash([4, 4]);
    ctx.font = '11px sans-serif';
    for (const [month, count] of eventCounts) {
      const index = labels.indexOf(month);
      if (index < 0) continue;
      const x = xScale.getPixelForValue(index);
      ctx.beginPath();
      ctx.moveTo(x, chartArea.top);
      ctx.lineTo(x, chartArea.bottom);
      ctx.stroke();
      ctx.fillText(count > 1 ? String(count) : '•', Math.min(x + 3, chartArea.right - 14), chartArea.top + 12);
    }
    ctx.restore();
  }
};

export default {
  name: 'ClusterAnalysisView',
  setup() {
    const API_BASE_URL = 'http://localhost:8000/api';
    const clusters = ref([]);
    const selectedCluster = ref(null);
    const analysis = ref(null);
    const selectedMetric = ref('downlink_traffic_gb');
    const chartCanvas = ref(null);
    const loading = ref(false);
    const error = ref('');
    let chart = null;

    const metrics = [
      { key: 'downlink_traffic_gb', label: 'Downlink traffic (GB/month)', color: '#2563eb' },
      { key: 'active_users_sum', label: 'Sum of cell average active users', color: '#7c3aed' },
      { key: 'traffic_users_sum', label: 'Sum of average traffic users', color: '#0891b2' },
      { key: 'downlink_prb_avg_pct', label: 'Mean downlink PRB use (%)', color: '#d97706' },
      { key: 'cqi_avg', label: 'Mean CQI', color: '#059669' }
    ];
    const activeMetric = computed(() => metrics.find(metric => metric.key === selectedMetric.value) || metrics[0]);

    const loadAnalysis = async clusterId => {
      if (clusterId === null || clusterId === undefined) return;
      loading.value = true;
      error.value = '';
      analysis.value = null;
      try {
        const response = await axios.get(`${API_BASE_URL}/sites/cluster_analysis/`, {
          params: { cluster_id: clusterId }
        });
        analysis.value = response.data;
      } catch (requestError) {
        error.value = requestError.response?.data?.error || 'Could not load cluster analysis.';
      } finally {
        loading.value = false;
      }
    };

    const renderChart = () => {
      if (chart) {
        chart.destroy();
        chart = null;
      }
      if (!chartCanvas.value || !analysis.value?.monthly_kpis?.length) return;
      const labels = analysis.value.monthly_kpis.map(row => row.month.slice(0, 7));
      chart = new Chart(chartCanvas.value, {
        type: 'line',
        data: {
          labels,
          datasets: [{
            label: activeMetric.value.label,
            data: analysis.value.monthly_kpis.map(row => row[activeMetric.value.key]),
            borderColor: activeMetric.value.color,
            backgroundColor: `${activeMetric.value.color}20`,
            borderWidth: 2,
            pointRadius: 2,
            tension: 0.2,
            fill: true,
            spanGaps: true
          }]
        },
        plugins: [eventTimelinePlugin],
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
            clusterEventTimeline: { events: analysis.value.events }
          },
          scales: {
            x: { title: { display: true, text: 'Month' }, ticks: { maxTicksLimit: 12, maxRotation: 0 } },
            y: { beginAtZero: true, title: { display: true, text: activeMetric.value.label } }
          }
        }
      });
    };

    const formatNumber = value => Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 2 });
    const eventLabel = eventType => ({
      SITE_ADDED: 'Site added', LTE_ADDED: 'LTE added', '3G_ADDED': '3G added', '2G_ADDED': '2G added'
    }[eventType] || eventType);
    const eventClass = eventType => eventType.toLowerCase().replace(/_/g, '-');

    onMounted(async () => {
      try {
        const response = await axios.get(`${API_BASE_URL}/sites/cluster_stats/`);
        clusters.value = response.data.clusters || [];
        if (clusters.value.length) selectedCluster.value = clusters.value[0].cluster_id;
      } catch (_error) {
        error.value = 'Could not load cluster list.';
      }
    });

    watch(selectedCluster, clusterId => loadAnalysis(clusterId));
    watch([analysis, selectedMetric], async () => {
      await nextTick();
      renderChart();
    }, { deep: true });
    onBeforeUnmount(() => { if (chart) chart.destroy(); });

    return {
      clusters, selectedCluster, analysis, selectedMetric, chartCanvas, loading, error,
      metrics, activeMetric, formatNumber, eventLabel, eventClass
    };
  }
};
</script>

<style scoped>
.cluster-analysis {
  height: 100%;
  overflow: auto;
  padding: clamp(14px, 2vw, 28px);
  color: #1e293b;
  background: #f8fafc;
}
.analysis-header, .section-heading { display: flex; align-items: end; justify-content: space-between; gap: 18px; }
.analysis-header { margin-bottom: 18px; }
h2, h3 { margin: 0; color: #172554; }
h2 { font-size: 24px; }
h3 { font-size: 17px; }
.analysis-header p, .section-heading p { margin: 5px 0 0; color: #64748b; font-size: 13px; }
.cluster-picker, .metric-picker { display: grid; gap: 5px; min-width: 220px; color: #475569; font-size: 12px; font-weight: 600; }
select { min-height: 38px; padding: 7px 10px; border: 1px solid #cbd5e1; border-radius: 7px; background: #fff; color: #1e293b; font: inherit; }
.context-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin-bottom: 18px; }
.context-value { display: grid; gap: 8px; min-height: 76px; padding: 12px 14px; border: 1px solid #e2e8f0; border-radius: 8px; background: #fff; }
.context-value span { color: #64748b; font-size: 12px; }
.context-value strong { color: #0f172a; font-size: 17px; font-variant-numeric: tabular-nums; }
.timeline-section, .events-section { margin-top: 16px; padding: 16px; border: 1px solid #e2e8f0; border-radius: 10px; background: #fff; }
.section-heading { align-items: center; margin-bottom: 14px; }
.metric-picker { min-width: 245px; }
.chart-frame { position: relative; width: 100%; height: 330px; }
.timeline-legend { display: flex; align-items: center; gap: 8px; margin-top: 10px; color: #64748b; font-size: 12px; }
.event-line-key { width: 18px; border-top: 2px dashed #c2410c; }
.event-total { color: #475569; font-size: 13px; font-variant-numeric: tabular-nums; }
.events-table-wrap { max-height: 480px; overflow: auto; border-top: 1px solid #e2e8f0; }
.events-table { width: 100%; border-collapse: collapse; text-align: left; font-size: 13px; }
.events-table th { position: sticky; top: 0; z-index: 1; padding: 10px; background: #f8fafc; color: #475569; font-size: 12px; }
.events-table td { padding: 9px 10px; border-top: 1px solid #edf2f7; vertical-align: top; }
.events-table td:first-child { white-space: nowrap; font-variant-numeric: tabular-nums; }
.events-table td strong, .events-table td small { display: block; }
.events-table td small { margin-top: 2px; color: #64748b; }
.event-kind { display: inline-block; padding: 3px 7px; border-radius: 999px; background: #f1f5f9; color: #334155; font-size: 11px; white-space: nowrap; }
.event-kind.site-added { background: #dcfce7; color: #166534; }
.event-kind.lte-added { background: #ede9fe; color: #6d28d9; }
.event-kind[class~="3g-added"] { background: #dbeafe; color: #1d4ed8; }
.event-kind[class~="2g-added"] { background: #ffedd5; color: #c2410c; }
.page-message, .empty-state { padding: 18px 0; color: #64748b; }
.error-message { color: #b91c1c; }
@media (max-width: 700px) {
  .analysis-header, .section-heading { align-items: stretch; flex-direction: column; }
  .cluster-picker, .metric-picker { min-width: 0; width: 100%; }
  .chart-frame { height: 270px; }
  .timeline-section, .events-section { padding: 12px; }
  .events-table { min-width: 640px; }
}
</style>
