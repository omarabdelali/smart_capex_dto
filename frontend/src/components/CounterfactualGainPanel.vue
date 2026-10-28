<template>
<section class="gain-panel">
  <h3>Counterfactual gains · experimental</h3>
  <p>Compare a modelled no-event trajectory with an episode forecast. Signed losses stay negative. This is an observational scenario estimate; matching does not prove causality.</p>
  <AnalysisProfilePicker purpose="prediction" :current-settings="currentSettings" :applied="result?.analysis_profile || autoProfile" @change="changeProfile" />
  <p class="note">Feature presets reuse recipient similarity inputs and weights. Select the gain scope and horizon below. The gain estimator always uses matched-control residuals.</p>
  <details><summary>Similarity features ({{features.length}} selected)</summary><div class="feature-list"><label v-for="f in catalog" :key="f.key"><input type="checkbox" v-model="features" :value="f.key">{{f.label}}</label></div><label>Weighting<select v-model="weighting"><option value="equal_per_feature">Equal per feature</option><option value="equal_per_group">Equal per group</option></select></label></details>
  <div class="controls">
    <label>Episode<select v-model="eventKey" aria-label="Gain episode"><option v-for="e in metadata.events || []" :key="e.event_key" :value="e.event_key">{{e.label}}</option></select></label>
    <label>Scope<select v-model="scope" aria-label="Gain scope"><option v-for="(label,key) in metadata.scopes || {}" :key="key" :value="key" :disabled="key==='cluster_total' && metadata.cluster_id===-1 || key==='virtual_cluster' && metadata.cluster_id!==-1">{{label}}</option></select></label>
    <label>KPI<select v-model="metric" aria-label="Gain KPI"><option value="downlink_traffic_gb">Downlink traffic (GB/month)</option><option value="active_users" :disabled="scope==='virtual_cluster'">Active users (monthly average counts)</option></select></label>
    <label>Complete months after event<select v-model.number="horizon" aria-label="Gain horizon"><option v-for="h in 6" :key="h" :value="h">{{h}}</option></select></label>
    <label><input type="checkbox" v-model="ramp">Smooth supported gain ramp</label>
  </div>
  <button @click="calculate" :disabled="loading || !eventKey || !features.length">{{loading?'Calculating gains…':'Calculate counterfactual gains'}}</button>
  <p v-if="error" role="alert">{{error}}</p>
  <template v-if="result">
    <div class="summary"><strong>Cumulative {{selected?.site_name || 'scope'}} gain over {{displayCumulative.horizon_months}} months: {{number(displayCumulative.gain)}} {{result.cumulative_unit}}</strong><span>Conditional mean interval: {{range(displayCumulative.mean_interval_95)}}</span><span>{{displayCumulative.supported_months}} / {{displayCumulative.horizon_months}} supported months. Incomplete scope totals stay unavailable.</span></div>
    <label>Display<select v-model="recipient" aria-label="Gain display"><option value="scope">Complete selected scope</option><option v-for="r in result.recipients" :key="r.site_id" :value="r.site_id">{{r.site_name}} · {{r.recipient_role}} · {{r.site_id}}</option></select></label>
    <p>{{result.scope_label}} · cutoff {{result.query.event_date}}. {{result.recipients.length}} fixed cohort members.</p>
    <div v-if="points.length" class="chart"><canvas ref="canvas" aria-label="With-event and no-event forecasts" role="img"></canvas></div>
    <div class="table-scroll"><table><thead><tr><th>Month</th><th>No-event forecast</th><th>With-event forecast</th><th>Monthly gain</th><th>Cumulative gain</th><th>Gain mean interval</th><th>Observed level (context)</th><th>Support</th></tr></thead><tbody><tr v-for="p in points" :key="p.horizon"><td>+{{p.horizon}} · {{p.month.slice(0,7)}}</td><td>{{number(p.no_event_forecast)}}</td><td>{{number(p.with_event_forecast)}}</td><td>{{number(p.monthly_gain)}}</td><td>{{number(p.cumulative_gain)}}</td><td>{{range(p.gain_mean_interval_95)}}</td><td>{{number(p.observed)}}</td><td>{{p.support?.reason || (p.monthly_gain==null?'Incomplete member predictions or controls':'Supported observational scenario')}}</td></tr></tbody></table></div>
    <aside><p>{{result.no_event_definition}}</p><p>{{result.gain_definition}}</p><p>{{result.scope_note}}</p><p>{{result.uncertainty_note}}</p><p v-if="result.scope_series.some(p=>p.confounding_actions?.length)">Later origin actions occur during this horizon. Displayed observations include those actions and cannot isolate this episode's effect.</p><p>Missing origin prehistory is unknown, including newly launched sites; no zero baseline is invented. Cluster members beyond the trained radius remain unsupported. Do not sum gains from overlapping episodes as separate network benefits.</p></aside>
  </template>
</section>
</template>
<script setup>
import {ref,computed,watch,nextTick,onBeforeUnmount} from 'vue';
import {Chart} from 'chart.js';
import AnalysisProfilePicker from './AnalysisProfilePicker.vue';
import {analysisApi,loadProfiles} from '../analysisProfiles';
const props=defineProps({siteId:String});
const metadata=ref({}),eventKey=ref(''),scope=ref('tier1'),metric=ref('downlink_traffic_gb'),horizon=ref(6),ramp=ref(false),loading=ref(false),error=ref(''),result=ref(null),recipient=ref('scope'),canvas=ref(null);
const profileId=ref(''),features=ref([]),catalog=ref([]),weighting=ref('equal_per_group'),autoProfile=ref(null);
let request=0,metadataRequest=0,chart=null;
const currentSettings=computed(()=>({prediction_features:features.value,weighting_mode:weighting.value,prediction_method:'control_adjusted'}));
loadProfiles().then(d=>{catalog.value=d.catalog.prediction_features;if(!features.value.length)features.value=[...d.catalog.defaults.prediction_features];}).catch(()=>{});
function applySettings(settings){if(!settings)return;features.value=[...settings.prediction_features];weighting.value=settings.weighting_mode;ramp.value=settings.ramp;const target=settings.scope==='cluster'?'cluster_total':settings.scope;if(target in (metadata.value.scopes || {}))scope.value=target;}
function applyDefault(){if(profileId.value)return;autoProfile.value=metadata.value.events?.find(e=>e.event_key===eventKey.value)?.analysis_profile;applySettings(autoProfile.value?.settings);}
function changeProfile(p){profileId.value=p.id;autoProfile.value=null;if(p.settings)applySettings(p.settings);else if(!p.id)applyDefault();result.value=null;}
watch(eventKey,applyDefault);
watch(()=>props.siteId,async id=>{const token=++metadataRequest;request++;result.value=null;eventKey.value='';try{const {data}=await analysisApi.get('/cbr/gains/',{params:{site_id:id,metadata:'true'}});if(token!==metadataRequest)return;metadata.value=data;eventKey.value=data.default_event_key || '';}catch(e){error.value=e.response?.data?.error || 'Cannot load episodes.';}},{immediate:true});
watch([eventKey,scope,metric,horizon,ramp,features,weighting,profileId],()=>{request++;loading.value=false;result.value=null;error.value='';});
watch(scope,s=>{if(s==='virtual_cluster')metric.value='downlink_traffic_gb';});
const selected=computed(()=>result.value?.recipients.find(r=>r.site_id===recipient.value));
const displayCumulative=computed(()=>selected.value?.cumulative || result.value?.cumulative);
const points=computed(()=>(recipient.value==='scope'?result.value?.scope_series:selected.value?.points)?.slice(0,result.value?.cumulative.horizon_months) || []);
function number(v){return v==null?'Unavailable':Number(v).toLocaleString(undefined,{maximumFractionDigits:2});}
function range(v){return v?`${number(v[0])} to ${number(v[1])}`:'Unavailable';}
async function calculate(){const token=++request;loading.value=true;error.value='';result.value=null;try{const {data}=await analysisApi.get('/cbr/gains/',{params:{site_id:props.siteId,event_key:eventKey.value,scope:scope.value,metric:metric.value,horizon:horizon.value,ramp:String(ramp.value),profile_id:profileId.value,features:features.value.join(','),weighting_mode:weighting.value}});if(token===request){result.value=data;recipient.value='scope';}}catch(e){if(token===request)error.value=e.response?.data?.error || 'Counterfactual gain calculation failed.';}finally{if(token===request)loading.value=false;}}
watch(points,async()=>{await nextTick();if(chart){chart.destroy();chart=null;}if(!canvas.value)return;chart=new Chart(canvas.value,{type:'line',data:{labels:points.value.map(p=>'+'+p.horizon+' '+p.month.slice(0,7)),datasets:[{label:'No-event forecast',data:points.value.map(p=>p.no_event_forecast),borderColor:'#64748b',borderDash:[5,4]},{label:'With-event forecast',data:points.value.map(p=>p.with_event_forecast),borderColor:'#2563eb'},{label:'Observed level (context only)',data:points.value.map(p=>p.observed),borderColor:'#94a3b8',pointRadius:2}]},options:{responsive:true,maintainAspectRatio:false,animation:false,scales:{y:{min:0}},plugins:{legend:{position:'bottom'}}}});});
onBeforeUnmount(()=>{request++;metadataRequest++;if(chart)chart.destroy();});
</script>
<style scoped>
.gain-panel{padding:18px;background:white;border:1px solid #cbd5e1;border-radius:8px}.controls{display:flex;gap:12px;flex-wrap:wrap;margin:16px 0}label{display:grid;gap:5px;min-width:0;max-width:100%;font-size:13px}select{padding:8px;max-width:100%;min-width:0;border:1px solid #94a3b8;border-radius:5px}button{padding:10px;background:#2563eb;color:white;border:0;border-radius:5px}button:disabled{opacity:.5}.summary{display:grid;gap:6px;margin:16px 0;padding:14px;background:#eff6ff;border-radius:7px}.note,aside{font-size:12px;color:#475569}aside p{margin:8px 0}.feature-list{max-height:220px;overflow:auto;display:grid;gap:8px}.feature-list label{display:block}.chart{height:320px;margin:12px 0}.table-scroll{overflow:auto}table{width:100%;border-collapse:collapse;font-size:12px}th,td{padding:8px;border-bottom:1px solid #e2e8f0;text-align:left;white-space:nowrap}[role=alert]{color:#b91c1c}
</style>
