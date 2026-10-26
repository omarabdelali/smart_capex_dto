<template>
  <section class="maos-history">
    <div class="history-heading">
      <div><h4>Monthly MAOS Counters</h4><p>{{ months.length }} months - {{ sourceDescription }}</p></div>
      <label>Metric<select v-model="selectedMetric" aria-label="MAOS metric"><option v-for="metric in metrics" :key="metric.key" :value="metric.key">{{ metric.label }}</option></select></label>
      <label>Scope<select v-model="selectedSource" aria-label="MAOS scope">
        <option value="site">Site aggregate</option><option value="tier1">Tier 1 (0-2 km)</option><option value="tier2">Tier 2 (2-5 km)</option><option value="cluster">Total cluster</option><option value="all_scopes">Compare Tier 1 / Tier 2 / cluster</option><option value="all_cells">Individual cells</option><option value="added_cells">Added cells only</option>
      </select></label>
    </div>
    <p class="scope-note">Ratios use sums of paired source counters, not averages of cell ratios. A zero denominator or missing counters leaves a gap. Tier 1/2 exclude this site; total cluster includes it. Monthly charts use current geographic membership.</p>
    <p v-if="!hasMetricData" class="no-data">No available values for {{ activeMetric.label }} in this scope. Counters may be missing or the denominator may be zero; measured zero is retained.</p>
    <div v-else class="chart-frame"><canvas ref="canvas" role="img" :aria-label="`${activeMetric.label} monthly values`"></canvas></div>
    <details v-if="months.length" class="monthly-values"><summary>Monthly values</summary><div class="table-scroll"><table><thead><tr><th>Month</th><th v-for="series in activeSeries" :key="series.key">{{ series.label }}</th></tr></thead><tbody><tr v-for="month in months" :key="month"><th>{{ month }}</th><td v-for="series in activeSeries" :key="series.key">{{ display(series.records.find(row => row.month === month)?.[selectedMetric]) }}</td></tr></tbody></table></div></details>
  </section>
</template>
<script>
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue';
import { Chart, LineController, LineElement, PointElement, LinearScale, CategoryScale, Tooltip, Legend } from 'chart.js';
Chart.register(LineController,LineElement,PointElement,LinearScale,CategoryScale,Tooltip,Legend);
const scopeLabels={site:'Site aggregate',tier1:'Tier 1 (0-2 km)',tier2:'Tier 2 (2-5 km)',cluster:'Total cluster'};
export default {
  name:'MAOSMonthlyChart',
  props:{records:{type:Array,default:()=>[]},cellRecords:{type:Array,default:()=>[]},scopes:{type:Object,default:()=>({})}},
  setup(props){
    const canvas=ref(null), selectedMetric=ref('prb_util_dl_pct');
    const selectedSource=ref(props.records.length?'site':props.scopes.tier1?.records?.length?'tier1':'site');
    let chart=null, renderRequest=0;
    const metrics=[
      {key:'edge_user_share',label:'Edge user share (ratio)'},
      {key:'edge_user_peak_ratio',label:'Edge user peak ratio (sum Max / sum Avg)'},
      {key:'lowlatency_user_share',label:'Low-latency user share (ratio)'},
      {key:'prb_util_dl_pct',label:'DL PRB utilization (%)'},
      {key:'traffic_user_avg',label:'Sum of cell traffic users'},
      {key:'active_users_avg',label:'Sum of cell average active users'},
      {key:'cqi_avg',label:'Weighted downlink CQI'},
      {key:'dl_throughput_kbps',label:'DL user throughput (kbit/s)'},
      {key:'dl_packet_delay_ms',label:'DL packet delay (ms)'},
      {key:'cell_availability_pct',label:'Cell availability (%)'},
      {key:'thrp_dl_gb',label:'Downlink traffic (GB)'}
    ];
    const activeMetric=computed(()=>metrics.find(m=>m.key===selectedMetric.value)||metrics[0]);
    const activeSeries=computed(()=>{
      if(selectedSource.value==='all_cells'||selectedSource.value==='added_cells'){
        return props.cellRecords.filter(cell=>selectedSource.value!=='added_cells'||cell.is_added).map((cell,index)=>({key:cell.cell_name,label:cell.cell_name+' ('+cell.technology+')',records:cell.records,color:cell.is_added?'#dc2626':`hsl(${(index*67)%360} 58% 45%)`}));
      }
      const keys=selectedSource.value==='all_scopes'?['tier1','tier2','cluster']:[selectedSource.value];
      return keys.map((key,index)=>({key,label:scopeLabels[key],records:key==='site'?props.records:(props.scopes[key]?.records||[]),color:['#2563eb','#d97706','#059669'][index]}));
    });
    const months=computed(()=>{
      const known=[...new Set(activeSeries.value.flatMap(s=>s.records.map(row=>row.month)))].sort();
      if(!known.length)return [];
      const result=[], first=known[0].split('-').map(Number), last=known.at(-1);
      let year=first[0],month=first[1];
      while(`${year}-${String(month).padStart(2,'0')}`<=last){result.push(`${year}-${String(month).padStart(2,'0')}`);month++;if(month>12){month=1;year++}}
      return result;
    });
    const hasMetricData=computed(()=>activeSeries.value.some(s=>s.records.some(row=>row[selectedMetric.value]!=null)));
    const sourceDescription=computed(()=>selectedSource.value==='all_scopes'?'separate geographic scope totals':scopeLabels[selectedSource.value]||'cell series');
    function display(value){return value==null?'Unavailable':Number(value).toLocaleString(undefined,{maximumSignificantDigits:6})}
    async function renderChart(){
      const request=++renderRequest;
      if(chart){chart.destroy();chart=null}
      await nextTick();
      if(request!==renderRequest||!canvas.value||!hasMetricData.value)return;
      chart=new Chart(canvas.value,{type:'line',data:{labels:months.value,datasets:activeSeries.value.map(s=>({label:s.label,data:months.value.map(month=>s.records.find(row=>row.month===month)?.[selectedMetric.value]??null),borderColor:s.color,pointRadius:2,borderWidth:2,tension:0,fill:false,spanGaps:false}))},options:{responsive:true,maintainAspectRatio:false,animation:false,plugins:{legend:{display:activeSeries.value.length>1,position:'bottom'}},scales:{x:{ticks:{maxTicksLimit:8}},y:{beginAtZero:true,title:{display:true,text:activeMetric.value.label}}}}});
    }
    onMounted(renderChart);
    watch(()=>[props.records,props.cellRecords,props.scopes,selectedMetric.value,selectedSource.value],renderChart,{deep:true,flush:'post'});
    onBeforeUnmount(()=>{renderRequest++;if(chart)chart.destroy()});
    return {canvas,selectedMetric,selectedSource,metrics,activeMetric,activeSeries,months,hasMetricData,sourceDescription,display};
  }
};
</script>
<style scoped>
.maos-history{margin-top:20px;padding-top:14px;border-top:1px solid #e5e7eb}.history-heading{display:flex;flex-wrap:wrap;align-items:center;gap:10px;margin-bottom:8px}.history-heading h4{margin:0;color:#334155}.history-heading label{display:grid;gap:4px;font-size:11px;flex:1 1 220px;min-width:0}.history-heading p,.scope-note{color:#64748b;font-size:11px;line-height:1.5}.scope-note{margin:8px 0}select{max-width:100%;width:100%;padding:6px;border:1px solid #cbd5e1;border-radius:5px;background:white}.chart-frame{height:250px;position:relative}.no-data{font-size:12px;color:#92400e}.table-scroll{overflow:auto;max-height:260px}table{border-collapse:collapse;width:100%;font-size:11px}th,td{padding:6px;white-space:nowrap;text-align:left;border-bottom:1px solid #e2e8f0}.monthly-values{margin-top:10px;font-size:12px}@media(max-width:480px){.history-heading{align-items:stretch;flex-direction:column}select{width:100%;max-width:none}.chart-frame{height:220px}}
</style>
