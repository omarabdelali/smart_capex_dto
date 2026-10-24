<template>
  <section class="maos-history">
    <div class="history-heading">
      <div>
        <h4>Monthly MAOS Counters</h4>
          <p v-if="activeRecords.length">{{ activeRecords.length }} months · {{ sourceDescription }}</p>
      </div>
      <select v-if="records.length" v-model="selectedMetric" aria-label="MAOS metric">
        <option v-for="metric in metrics" :key="metric.key" :value="metric.key">{{ metric.label }}</option>
      </select>
      <select v-if="cellRecords.length" v-model="selectedSource" aria-label="MAOS values by site or cell">
        <option value="site">Site aggregate</option>
        <option value="all_cells">Individual cells</option>
        <option value="added_cells">Added cells only</option>
      </select>
    </div>
    <p v-if="!activeRecords.length" class="no-data">
      {{ selectedSource === 'added_cells' ? 'No detected added cells with linked MAOS history.' : 'No monthly MAOS records are linked to this site.' }}
    </p>
    <canvas v-else ref="canvas"></canvas>
  </section>
</template>

<script>
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue';
import {
  Chart, LineController, LineElement, PointElement, LinearScale,
  CategoryScale, Tooltip, Legend
} from 'chart.js';

Chart.register(LineController, LineElement, PointElement, LinearScale, CategoryScale, Tooltip, Legend);

export default {
  name: 'MAOSMonthlyChart',
  props: {
    records: { type: Array, default: () => [] },
    cellRecords: { type: Array, default: () => [] }
  },
  setup(props) {
    const canvas = ref(null);
    const selectedMetric = ref('prb_util_dl_pct');
    const selectedSource = ref('site');
    let chart = null;
    const metrics = [
      { key: 'prb_util_dl_pct', label: 'Downlink PRB used' },
      { key: 'prb_util_ul_pct', label: 'Uplink PRB used' },
      { key: 'traffic_user_avg', label: 'Average traffic users' },
      { key: 'active_users_avg', label: 'Average active users' },
      { key: 'rrc_conn_avg', label: 'Average RRC connections' },
      { key: 'cqi_avg', label: 'Average downlink CQI' },
      { key: 'rsrp_avg_dbm', label: 'Average RSRP (dBm)' },
      { key: 'thrp_dl_gb', label: 'Downlink traffic (GB)' },
      { key: 'thrp_ul_gb', label: 'Uplink traffic (GB)' }
    ];
    const activeMetric = computed(() => metrics.find(metric => metric.key === selectedMetric.value));
    const chosenCells = computed(() => selectedSource.value === 'added_cells'
      ? props.cellRecords.filter(cell => cell.is_added)
      : props.cellRecords);
    const activeRecords = computed(() => selectedSource.value === 'site'
      ? props.records
      : chosenCells.value.flatMap(cell => cell.records));
    const sourceDescription = computed(() => selectedSource.value === 'site'
      ? 'aggregated across this site\'s cells'
      : `${chosenCells.value.length} cell series${selectedSource.value === 'added_cells' ? ' (detected additions)' : ''}`);

    const renderChart = () => {
      if (!canvas.value || !activeRecords.value.length) return;
      if (chart) chart.destroy();
      const metric = activeMetric.value;
      const labels = [...new Set(activeRecords.value.map(row => row.month))].sort();
      const datasets = selectedSource.value === 'site'
        ? [{
            label: metric.label,
            data: props.records.map(row => row[metric.key] ?? null),
            borderColor: '#2563eb', backgroundColor: 'rgba(37, 99, 235, 0.12)',
            pointRadius: 2, borderWidth: 2, tension: 0.2, fill: true, spanGaps: true
          }]
        : chosenCells.value.map((cell, index) => ({
            label: `${cell.cell_name} (${cell.technology}${cell.is_added ? ', added' : ''})`,
            data: labels.map(month => cell.records.find(row => row.month === month)?.[metric.key] ?? null),
            borderColor: cell.is_added ? '#dc2626' : `hsl(${(index * 67) % 360} 58% 45%)`,
            pointRadius: cell.is_added ? 2 : 0,
            borderWidth: cell.is_added ? 2.5 : 1.3,
            tension: 0.2, fill: false, spanGaps: true
          }));
      chart = new Chart(canvas.value, {
        type: 'line',
        data: {
          labels,
          datasets
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: selectedSource.value !== 'site', position: 'bottom' } },
          scales: {
            x: { ticks: { maxTicksLimit: 8 } },
            y: { beginAtZero: true, title: { display: true, text: metric.label } }
          }
        }
      });
    };

    onMounted(renderChart);
    watch(() => [props.records, props.cellRecords, selectedMetric.value, selectedSource.value], renderChart, { deep: true });
    onBeforeUnmount(() => { if (chart) chart.destroy(); });

    return { canvas, selectedMetric, selectedSource, metrics, activeRecords, sourceDescription };
  }
};
</script>

<style scoped>
.maos-history { margin-top: 20px; padding-top: 14px; border-top: 1px solid #e5e7eb; }
.history-heading { display: flex; justify-content: space-between; align-items: center; gap: 10px; margin-bottom: 8px; }
.history-heading h4 { margin: 0; color: #2c3e50; }
.history-heading p { margin: 4px 0 0; color: #6b7280; font-size: 11px; }
select { max-width: 165px; padding: 6px; border: 1px solid #d1d5db; border-radius: 5px; background: white; }
canvas { height: 220px; max-height: 220px; }
@media (max-width: 480px) {
  .history-heading { align-items: flex-start; flex-direction: column; }
  select { width: 100%; max-width: none; }
  canvas { height: 190px; max-height: 190px; }
}
</style>
