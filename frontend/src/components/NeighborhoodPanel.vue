<template>
  <section class="neighborhood-panel">
    <label>Membership version <select v-model="version" aria-label="Neighborhood membership version"><option value="event">Primary event cutoff (rebuilt)</option><option value="current">Current stored snapshot</option><option v-for="event in payload.events || []" :key="event.event_key" :value="'event:'+event.event_key">{{ event.date }} · {{ event.label }}</option></select></label>
    <p v-if="loading">Rebuilding selected event membership…</p><p v-if="error" role="alert">{{ error }}</p>
    <template v-if="context">
      <h4>{{ context.tier_scheme }} tiers · {{ context.labels?.tier1 }} / {{ context.labels?.tier2 }}</h4>
      <p>Real DBSCAN cluster: <strong>{{ context.cluster_id === -1 ? 'None (-1)' : context.cluster_id }}</strong>. Canonical location: {{ context.canonical_site_id }}.</p>
      <p>{{ version === 'current' ? 'Stored current version' : 'Rebuilt event-time membership' }} · cutoff {{ context.cutoff || 'Unavailable' }}</p>
      <p v-if="context.tier_scheme === 'standard'">This location belongs to its real DBSCAN cluster. Virtual traffic sampling applies to noise locations.</p>
      <template v-else>
        <h4>{{ context.virtual_name || 'Isolated: no eligible virtual members' }}</h4>
        <p v-if="context.virtual_id">{{ context.virtual_id }} · per-analysis neighborhood; the site keeps cluster_id=-1.</p>
        <p><strong>{{ context.vis_n_members ?? 0 }} / 12 filled bins</strong> · support: {{ context.support_level }}.</p>
        <div class="summary">
          <p>Sampled traffic: <strong>{{ number(context.vis_sampled_traffic_gb) }}</strong> GB/month</p>
          <p>Mean per selected location: <strong>{{ number(context.vis_mean_traffic_per_member_gb) }}</strong> GB/month</p>
          <p>All eligible locations within 10 km: <strong>{{ number(context.traffic_all_sites_within_R) }}</strong> GB/month</p>
          <p>Median / maximum member distance: {{ number(context.vis_median_dist_m) }} / {{ number(context.vis_max_dist_m) }} m</p>
        </div>
        <p>Traffic describes the previous complete month. One nearest location per 30° bin is sampled; this sample is distinct from the complete 10 km total. Missing member data leaves the total unavailable.</p>
        <div v-if="context.vis_members?.length" class="member-scroll"><table><thead><tr><th>Site</th><th>Bin</th><th>Distance</th><th>Bearing</th><th>Tier</th><th>Recent launch</th></tr></thead>
          <tbody><tr v-for="member in context.vis_members" :key="member.bin"><td>{{ member.site_name }}<small>{{ member.site_id }}</small></td><td>{{ member.bin }}</td><td>{{ member.distance_m.toFixed(1) }} m</td><td>{{ member.bearing_deg.toFixed(6) }}°</td><td>{{ member.tier }}</td><td :title="member.recent_launch_basis">{{ member.member_recent_launch == null ? 'Unknown' : member.member_recent_launch ? 'Yes' : 'No' }}<small v-if="member.member_recent_lte_activation">Recent first-positive LTE observation</small></td></tr></tbody></table></div>
        <p>Members need positive LTE traffic during the three complete baseline months. The event location, same-month launches and locations under 50 m away are excluded. A first-positive LTE month is labelled as a proxy when a site-launch date is unknown.</p>
      </template>
    </template>
  </section>
</template>
<script setup>
import { computed,ref,watch,onBeforeUnmount } from 'vue';
import axios from 'axios';
const props=defineProps({payload:{type:Object,default:()=>({})},siteId:{type:String,default:''}});
const version=ref('event');
const selected=ref(null),loading=ref(false),error=ref('');let request=0;
const context=computed(()=>version.value.startsWith('event:')?selected.value:props.payload[version.value]);
watch(version,async value=>{const token=++request;selected.value=null;error.value='';if(!value.startsWith('event:')){loading.value=false;return;}loading.value=true;try{const response=await axios.get(`http://localhost:8000/api/sites/${props.siteId}/neighborhood/`,{params:{event_key:value.slice(6)}});if(token===request)selected.value=response.data.event;}catch(e){if(token===request)error.value=e.response?.data?.error||'Could not rebuild membership.';}finally{if(token===request)loading.value=false;}});
onBeforeUnmount(()=>{request++;});
function number(value){return value==null?'Unavailable':Number(value).toLocaleString(undefined,{maximumFractionDigits:2});}
</script>
<style scoped>
.neighborhood-panel { font-size:12px; line-height:1.6; color:#334155; }.neighborhood-panel p { margin:10px 0; }.neighborhood-panel label { display:grid; gap:5px; }.neighborhood-panel select { padding:8px; max-width:100%; border:1px solid #cbd5e1; border-radius:6px; background:white; }.summary { background:#eff6ff; padding:10px; border-radius:8px; }.summary p { margin:5px 0; }.member-scroll { max-height:350px; overflow:auto; }table { width:100%; border-collapse:collapse; font-size:11px; }th,td { white-space:nowrap; padding:7px; border-bottom:1px solid #e2e8f0; text-align:left; }th { background:#f1f5f9; position:sticky; top:0; }small { display:block; color:#64748b; }
</style>
