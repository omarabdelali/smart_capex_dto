<template>
<section class="cbr">
<header><h2>Event impact prediction</h2><p>Case-based estimate from historical site launches.</p></header>
<div class="search"><input v-model="text" placeholder="Search site ID, name, or cell name" @keydown.enter.prevent="choose"><button :disabled="!site||loading" @click="predict">Predict impact</button><div v-if="matches.length" class="matches"><button v-for="s in matches" :key="s.site_id" @click="select(s)">{{s.site_name}} · {{s.site_id}}</button></div></div>
<p v-if="site">Selected {{site.site_name}} · {{site.site_id}}</p><p v-if="error" class="error">{{error}}</p><p v-if="loading">Building cases…</p>
<template v-if="result">
<aside>{{result.query.date_note}}: {{result.query.event_date}}<p>{{result.method_note}}</p><p>{{result.data_note}}</p><p>{{result.feature_timing_note}}</p></aside>
<p>{{ result.scope_labels?.tier1 }} population: {{populationLabel('population_tier1')}} · {{ result.scope_labels?.tier2 }} population: {{populationLabel('population_tier2')}}</p>
<p v-if="hasPartialPopulation" class="population-note">Population is a partial mapped estimate. Missing land is excluded; full catchment totals may be higher.</p>
<div class="controls"><label>Scope<select v-model="scope"><option value="tier1">{{ result.scope_labels?.tier1 }}</option><option value="tier2">{{ result.scope_labels?.tier2 }}</option><option value="cluster" :disabled="result.query.cluster_id === -1">Real DBSCAN cluster</option><option value="virtual_cluster" :disabled="result.query.cluster_id !== -1">Virtual sampled traffic</option><option value="distance_0_2">0-2 km</option><option value="distance_2_5">2-5 km</option><option value="distance_5_10">5-10 km</option><option value="site">Single neighbor</option></select></label>
<label v-if="scope==='site'">Neighbor<select v-model="target"><option v-for="s in result.site_predictions" :key="s.site_id" :value="s.site_id">{{s.site_name}} ({{s.tier}})</option></select></label>
<label>KPI<select v-model="metric"><option v-for="m in available" :key="m.key" :value="m.key" :disabled="scope==='virtual_cluster' && m.key!=='downlink_traffic_gb'">{{m.label}} {{m.unit}}</option></select></label></div>
<label v-if="result.available_events?.length">Analysis event<select v-model="eventKey" aria-label="CBR analysis event"><option v-for="event in result.available_events" :key="event.event_key" :value="event.event_key">{{event.date}} - {{event.label}}</option></select></label><p v-if="eventKey !== (result.query.event_key || '')">Event selection changed. Predict impact to rebuild membership and outcomes for that month.</p>
<p class="unavailable">Unavailable in current report: <span v-for="m in unavailable" :key="m.key" :title="m.reason">{{m.label}}</span></p>
<p>{{activeScope?.site_count||0}} affected sites · {{result.case_count}} historical analogs · 3 pre / 6 post months</p>
<p>No estimate is shown where fewer than two analog outcomes were available before the prediction cutoff ({{result.prediction_cutoff}}).</p>
<p>{{result.aggregation_note}}</p><p v-if="scope==='virtual_cluster'">One location per 30-degree bin: {{result.neighborhood?.vis_n_members}} members, support {{result.neighborhood?.support_level}}. These traffic results describe a sample. Complete 10 km baseline traffic: {{number(result.neighborhood?.traffic_all_sites_within_R)}} GB/month.</p>
<p class="partial-month-note">{{result.event_month_note || 'The event month is partial and shown for context. Effect estimates start at +1.'}}</p>
<section class="chart"><h3>{{activeMetric?.label}} — {{scopeLabel}}</h3><p v-if="activeScope?.status!=='available'">{{scopeMessage}}</p><p v-else-if="!hasChartData">No observed or predicted values are available for this scope and KPI.</p><div v-else class="chart-frame"><canvas ref="canvas" role="img" :aria-label="`${activeMetric?.label} observed and CBR estimated values`"></canvas></div></section>
<details v-if="points.length" class="series-table"><summary>Monthly values and analog support</summary><div class="table-scroll"><table><thead><tr><th>Month</th><th>Observed</th><th>CBR estimate</th><th>95% interval</th><th>Analogs</th><th>Observed / eligible sites</th></tr></thead><tbody><tr v-for="p in points" :key="p.month"><th>{{p.month}}{{p.offset===0?' - partial event month':''}}</th><td>{{number(p.observed)}}</td><td>{{number(p.predicted)}}</td><td>{{p.lower_95 == null ? 'Unavailable' : `${number(p.lower_95)} – ${number(p.upper_95)}`}}</td><td>{{p.offset <= 0 ? '—' : p.analog_cases}}</td><td>{{p.observed_sites ?? '—'}} / {{p.eligible_sites ?? '—'}}</td></tr></tbody></table></div></details>
<section><h3>Similar launches</h3><p>{{result.filter_explanation}}</p><p v-for="c in result.cases" :key="c.site_id">{{c.site_id}} · {{c.event_date}} · {{(c.similarity*100).toFixed(1)}}% similar · weight {{(c.weight*100).toFixed(1)}}%</p></section>
</template><p v-else>Choose a site to estimate neighboring KPI changes.</p>
</section>
</template>
<script>
import axios from 'axios';
import {computed,nextTick,onBeforeUnmount,ref,watch} from 'vue';
import {Chart,LineController,LineElement,PointElement,LinearScale,CategoryScale,Tooltip,Legend,Filler} from 'chart.js';
Chart.register(LineController,LineElement,PointElement,LinearScale,CategoryScale,Tooltip,Legend,Filler);
const eventLine={id:'eventline',afterDatasetsDraw(c){const i=(c.data.labels||[]).indexOf('Event month (partial)');if(i<0)return;const x=c.scales.x.getPixelForValue(i);c.ctx.save();c.ctx.strokeStyle='#c2410c';c.ctx.setLineDash([5,4]);c.ctx.beginPath();c.ctx.moveTo(x,c.chartArea.top);c.ctx.lineTo(x,c.chartArea.bottom);c.ctx.stroke();c.ctx.restore()}};
export default{name:'CBRPredictionView',setup(){
const API='http://localhost:8000/api',text=ref(''),matches=ref([]),site=ref(null),result=ref(null),loading=ref(false),error=ref(''),canvas=ref(null),scope=ref('tier1'),target=ref(''),metric=ref('downlink_traffic_gb'),eventKey=ref('');let timer=null,label='',chart=null;
const hasChartData=computed(()=>points.value.some(p=>p.observed!=null||p.predicted!=null));
const hasPartialPopulation=computed(()=>Object.values(result.value?.population_quality||{}).some(q=>q?.status==='incomplete_land_coverage'));
function number(value){return value==null?'Unavailable':Number(value).toLocaleString(undefined,{maximumFractionDigits:2})}
function populationLabel(key){const value=result.value?.population_features?.[key];return value==null?'Unavailable':Math.round(value).toLocaleString()+' people'}
const available=computed(()=>Object.entries(result.value?.metrics||{}).filter(([,m])=>m.available).map(([key,m])=>({key,...m}))),unavailable=computed(()=>Object.entries(result.value?.metrics||{}).filter(([,m])=>!m.available).map(([key,m])=>({key,...m}))),activeMetric=computed(()=>available.value.find(m=>m.key===metric.value)||available.value[0]),activeScope=computed(()=>scope.value==='site'?result.value?.site_predictions.find(s=>s.site_id===target.value):result.value?.scopes[scope.value]),points=computed(()=>activeScope.value?.series?.[metric.value]||[]),scopeLabel=computed(()=>scope.value==='site'?(activeScope.value?.site_name||'Neighbor'):(result.value?.scope_labels?.[scope.value] || scope.value.toUpperCase())),scopeMessage=computed(()=>activeScope.value?.status==='no_historical_cluster'?'No cluster can be reconstructed from pre-event LTE activity.':'No active neighbors with pre-event data.');
watch(text,v=>{if(label&&v===label){label='';return}site.value=null;result.value=null;matches.value=[];if(timer)clearTimeout(timer);if(v.trim().length<2)return;timer=setTimeout(async()=>{try{let r=await axios.get(API+'/sites/',{params:{search:v.trim()}});matches.value=(r.data.results||[]).slice(0,8)}catch{error.value='Site search failed.'}},250)});
watch(scope,value=>{if(value==='virtual_cluster')metric.value='downlink_traffic_gb';});
watch([scope,target,metric],async()=>{await nextTick();draw()});watch(result,async v=>{if(!v){if(chart){chart.destroy();chart=null}return;}if((scope.value==='virtual_cluster'&&v.query.cluster_id!==-1)||(scope.value==='cluster'&&v.query.cluster_id===-1))scope.value='tier1';eventKey.value=v.query.event_key||'';target.value=v.site_predictions[0]?.site_id||'';metric.value=available.value[0]?.key||'';await nextTick();draw()});
function select(s){eventKey.value='';site.value=s;label=s.site_name+' ('+s.site_id+')';text.value=label;matches.value=[];result.value=null;error.value=''}function choose(){if(matches.value.length)select(matches.value[0])}
async function predict(){if(!site.value)return;loading.value=true;error.value='';result.value=null;try{let r=await axios.get(API+'/cbr/impact/',{params:{site_id:site.value.site_id,event_key:eventKey.value||undefined}});result.value=r.data}catch(e){error.value=e.response?.data?.error||'CBR prediction failed.'}finally{loading.value=false}}
function draw(){
  if(chart){chart.destroy();chart=null}
  if(!canvas.value||!hasChartData.value||!activeMetric.value)return;
  const d=points.value;
  chart=new Chart(canvas.value,{
    type:'line',
    data:{labels:d.map(p=>p.offset===0?'Event month (partial)':p.month),datasets:[
      {label:'Observed',data:d.map(p=>p.observed),borderColor:'#64748b',spanGaps:false},
      {label:'CBR estimate',data:d.map(p=>p.predicted),borderColor:'#2563eb',borderDash:[6,3],spanGaps:false},
      {label:'95% lower',data:d.map(p=>p.lower_95),borderColor:'#93c5fd',pointRadius:0,spanGaps:false},
      {label:'95% bootstrap interval',data:d.map(p=>p.upper_95),borderColor:'#93c5fd',pointRadius:0,fill:2,backgroundColor:'rgba(59,130,246,0.12)',spanGaps:false}
    ]},plugins:[eventLine],
    options:{responsive:true,maintainAspectRatio:false,animation:false,interaction:{mode:'index',intersect:false},plugins:{legend:{position:'bottom'},tooltip:{callbacks:{
      title:items=>d[items[0]?.dataIndex]?.month||'',
      footer:items=>{const p=d[items[0]?.dataIndex];return !p?'':p.offset<0?'Pre-event observation':p.offset===0?'Partial activation month; effects start at +1':p.analog_cases+' completed analog outcomes; '+p.observed_sites+'/'+p.eligible_sites+' recipient sites observed'}
    }}},scales:{x:{title:{display:true,text:'Calendar month (event marked)'}},y:{min:0,max:metric.value==='cqi_avg'?15:undefined,title:{display:true,text:activeMetric.value.label+' '+activeMetric.value.unit}}}}
  });
}
onBeforeUnmount(()=>{if(timer)clearTimeout(timer);if(chart)chart.destroy()});return{eventKey,number,populationLabel,hasPartialPopulation,hasChartData,text,matches,site,result,loading,error,canvas,scope,target,metric,available,unavailable,activeMetric,activeScope,points,scopeLabel,scopeMessage,select,choose,predict}
}};
</script>
<style scoped>
.cbr{height:100%;overflow:auto;padding:clamp(16px,3vw,34px);background:#f5f7fb;color:#1e293b}header{display:flex;align-items:center;justify-content:space-between}header p{color:#64748b}.search,.chart,section:not(.search){margin:14px 0;padding:14px;border:1px solid #e2e8f0;border-radius:9px;background:white}.search{position:relative;max-width:850px}input,select{padding:9px;border:1px solid #cbd5e1;border-radius:6px;background:#fff;font:inherit}.search input{width:70%}button{padding:9px 12px;border:0;border-radius:6px;background:#2563eb;color:white}.matches{position:absolute;z-index:2;left:14px;right:14px;top:70px;background:#fff;box-shadow:0 5px 15px #0002}.matches button{display:block;width:100%;text-align:left;background:white;color:#1e293b;border-bottom:1px solid #eee}.controls{display:flex;flex-wrap:wrap;gap:12px}.controls label{display:grid;gap:5px}.unavailable{color:#991b1b}.unavailable span{margin-left:7px;padding:4px;background:#fee2e2}.chart-frame{height:360px;position:relative}.chart-frame canvas{display:block}.population-note{color:#92400e}.table-scroll{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:12px}th,td{padding:8px;text-align:left;border-bottom:1px solid #e2e8f0;white-space:nowrap}.series-table{margin:12px 0}.error{color:#b91c1c}aside{padding:12px;background:#fff7ed;border-radius:7px;font-size:12px}aside p{margin-top:6px}
@media(max-width:620px){header,.search input{width:100%}.controls{flex-direction:column}}
</style>
