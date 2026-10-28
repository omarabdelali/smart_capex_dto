<template>
  <div class="planning">
    <aside>
      <h2>Candidate site planning</h2>
      <p>Plan a new site or an addition at an existing site. Saved exercises do not change the live network.</p>
      <label class="saved">Planning scenario<select v-model="form.mode" @change="modeChanged"><option value="new">New physical site</option><option value="existing">Existing site</option></select></label>
      <form @submit.prevent="searchSite" class="search">
        <label>Find an existing site</label>
        <div><input v-model="search" placeholder="Site or cell name"><button>Search</button></div>
        <button v-for="item in searchResults" :key="item.properties.site_id" type="button" class="search-result" @click="goToSite(item)">{{ form.mode === 'existing' ? 'Select' : 'Go to' }} {{ item.properties.site_name }} · {{ item.properties.site_id }}</button>
      </form>
      <form @submit.prevent="submit" class="fields">
        <label>Candidate name<input v-model="form.name" required maxlength="120"></label>
        <p v-if="form.mode==='existing'">Selected site: <strong>{{ selectedSiteName || 'Search and select a site above' }}</strong></p>
        <label v-if="form.mode==='existing'">Change type<select v-model="form.action"><option value="technology">Technology addition</option><option value="band">Frequency-band addition</option><option value="cell">Cell addition</option><option value="bandwidth">LTE bandwidth upgrade or downgrade</option></select></label>
        <div class="row"><label>Latitude<input v-model.number="form.latitude" type="number" step="any" :readonly="form.mode==='existing'" required></label><label>Longitude<input v-model.number="form.longitude" type="number" step="any" :readonly="form.mode==='existing'" required></label></div>
        <label>Sectors after the change<input v-model.number="form.sector_count" type="number" min="1" max="12" required></label>
        <div v-for="(entry,index) in form.technologies" :key="index" class="technology-entry">
          <div class="row"><label>Technology<select v-model="entry.technology"><option>4G</option><option>3G</option><option>2G</option></select></label><label>Frequency bands<input v-model="entry.bands" placeholder="L1800; L800" required></label></div>
          <button v-if="form.technologies.length>1" type="button" @click="form.technologies.splice(index,1)">Remove technology</button>
        </div>
        <button type="button" @click="form.technologies.push({technology:'3G',bands:''})">Add another technology</button>
        <template v-if="form.mode==='existing' && form.action==='bandwidth'"><label>Existing LTE cell ID<input v-model="form.cell_id" required placeholder="Cell ID from the site details"></label><div class="row"><label>Previous bandwidth (MHz)<select v-model.number="form.previous_bandwidth_mhz" required><option :value="null">Choose</option><option v-for="n in [5,10,15,20]" :key="n" :value="n">{{n}}</option></select></label><label>New bandwidth (MHz)<select v-model.number="form.new_bandwidth_mhz" required><option :value="null">Choose</option><option v-for="n in [5,10,15,20]" :key="n" :value="n">{{n}}</option></select></label></div><small>Enter the existing cell's band above. The direction follows the supplied bandwidth values.</small></template>
        <label>Feature template<select v-model="form.profile_id"><option value="">Scenario default (automatic)</option><option value="manual">Built-in defaults</option><option v-for="profile in profiles" :key="profile.id" :value="profile.id">{{ profile.name }} · v{{ profile.revision }}</option></select></label>
        <label>Planned month <input v-model="form.event_month" type="month"></label>
        <small>Blank month uses the month after the latest KPI report. Sector bearings and unmeasured site KPIs remain unavailable.</small>
        <button :disabled="busy">{{ busy ? 'Calculating features and similarity…' : 'Calculate and save' }}</button>
      </form>
      <p v-if="error" class="error">{{ error }}</p>
      <label class="saved">Saved exercises<select :value="selected?.id || ''" @change="loadSaved($event.target.value)"><option value="">Choose an exercise</option><option v-for="item in saved" :key="item.id" :value="item.id">{{ item.name }} · {{ item.inputs.event_month }}</option></select></label>
      <section v-if="selected">
        <h3>{{ selected.name }}</h3>
        <p>{{ scenarioDescription(selected.inputs) }} · {{ selected.inputs.sector_count }} sectors · {{ selected.inputs.event_type || 'SITE_ADDED' }}</p>
        <p v-if="selected.inputs.action==='bandwidth'">Cell {{ selected.inputs.cell_id }}: {{ selected.inputs.previous_bandwidth_mhz }} → {{ selected.inputs.new_bandwidth_mhz }} MHz</p>
        <p>Template: {{ selected.result.similarity?.profile?.name || 'Built-in defaults' }}<span v-if="selected.result.similarity?.profile?.revision"> · v{{ selected.result.similarity.profile.revision }}</span></p>
        <p>Cluster: {{ selected.features.cluster_id === -1 ? 'Virtual / noise' : selected.features.cluster_id === -2 ? 'Hypothetical ' + selected.result.assignment.kind + ' cluster' : selected.features.cluster_id }} · {{ selected.features.tier_scheme }} tiers</p>
        <p v-if="selected.result.assignment?.kind === 'merged'" class="error">This point would connect existing clusters {{ selected.result.assignment.nearby_clusters.join(', ') }}. The operational labels have not been changed.</p>
        <p v-if="selected.features.cluster_id === -1">{{ selected.features.virtual_cluster_context?.vis_n_members || 0 }} event-time virtual members; the candidate is excluded.</p>
        <details><summary>Calculated features and unavailable values</summary><dl><template v-for="(value,key) in displayFeatures" :key="key"><dt>{{ key.replaceAll('_',' ') }}</dt><dd>{{ format(value) }}</dd></template></dl></details>
        <h3>Similar historical sites</h3>
        <p>Eligible pool: {{ selected.result.similarity?.pool_size ?? 0 }} historical sites. Results are retrieval, not a gain prediction.</p>
        <p v-if="selected.result.similarity?.pool_size < 3" class="error">Low support: fewer than three eligible historical sites.</p>
        <p>{{ selected.result.similarity?.filter_explanation }}</p>
        <p v-if="!selected.result.similarity?.cases?.length">No eligible analogues met the current filters and available-feature threshold.</p>
        <button v-for="item in selected.result.similarity?.cases || []" :key="item.event_key || item.site_id" type="button" class="case" @click="exploreAnalogue(item)">
          <strong>{{ item.site_name }}</strong><span>{{ (item.similarity*100).toFixed(1) }}% · {{ item.event_date }}</span>
        </button>
        <div v-if="detailSiteId" class="analogue-detail"><button type="button" @click="detailSiteId=null">Close site details</button><SiteFeaturePopup :site-id="String(detailSiteId)" /></div>
      </section>
    </aside>
    <div ref="mapElement" class="map" aria-label="Candidate location map"></div>
  </div>
</template>

<script setup>
import { ref, shallowRef, reactive, onMounted, onBeforeUnmount, computed } from 'vue';
import axios from 'axios';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import SiteFeaturePopup from './SiteFeaturePopup.vue';
import { loadProfiles, writeProfile } from '../analysisProfiles';

const API='http://localhost:8000/api';
const mapElement=ref(null), map=shallowRef(null), saved=ref([]), selected=ref(null), busy=ref(false), error=ref('');
const search=ref(''),searchResults=ref([]),profiles=ref([]),selectedSiteName=ref(''),detailSiteId=ref(null);
const form=reactive({name:'Candidate site',latitude:null,longitude:null,mode:'new',action:'technology',site_id:'',technologies:[{technology:'4G',bands:''}],sector_count:3,profile_id:'',event_month:'',cell_id:'',previous_bandwidth_mhz:null,new_bandwidth_mhz:null});
let candidateMarker=null, savedLayer=null, caseLayer=null, neighborhoodLayer=null;
const star=L.divIcon({className:'candidate-icon',html:'★',iconSize:[30,30],iconAnchor:[15,15]});
const displayFeatures=computed(()=>Object.fromEntries(Object.entries(selected.value?.features || {}).filter(([,v])=>v===null || ['number','string','boolean'].includes(typeof v))));
function format(v){return v===null || v===undefined ? 'Unavailable' : typeof v==='number' ? Number(v.toFixed(3)) : String(v)}
function place(lat,lon){form.latitude=Number(lat.toFixed(6));form.longitude=Number(lon.toFixed(6));if(candidateMarker) candidateMarker.remove();candidateMarker=L.marker([lat,lon],{icon:star}).addTo(map.value).bindTooltip('Candidate location').on('click',showCandidateCluster);}
function modeChanged(){form.site_id='';selectedSiteName.value='';}
function scenarioDescription(inputs){return (inputs.technologies || [{technology:inputs.technology,bands:[inputs.band]}]).map(entry=>`${entry.technology}: ${(entry.bands || []).join ? entry.bands.join(', ') : entry.bands}`).join(' · ');}
async function refresh(){saved.value=(await axios.get(`${API}/candidates/`)).data;renderSaved();}
function renderSaved(){if(!map.value)return;if(savedLayer)savedLayer.remove();savedLayer=L.layerGroup().addTo(map.value);for(const item of saved.value){if(item.inputs?.latitude!=null)L.marker([item.inputs.latitude,item.inputs.longitude],{icon:star}).addTo(savedLayer).bindTooltip(item.name).on('click',()=>loadSaved(item.id));}}
function renderCases(){if(caseLayer)caseLayer.remove();caseLayer=L.layerGroup().addTo(map.value);for(const item of selected.value?.result?.similarity?.cases || []) L.circleMarker([item.latitude,item.longitude],{radius:7,color:'#0f766e',fillOpacity:.8}).addTo(caseLayer).bindTooltip(`${item.site_name}: ${(item.similarity*100).toFixed(1)}%`).on('click',()=>exploreAnalogue(item));}
function loadSaved(id){selected.value=saved.value.find(item=>item.id===id)||null;detailSiteId.value=null;if(!selected.value){renderCases();return;}const input=selected.value.inputs;Object.assign(form,input,{mode:input.mode || 'new',action:input.action || 'technology',site_id:input.site_id || '',profile_id:input.profile_id || '',technologies:(input.technologies || [{technology:input.technology,bands:[input.band]}]).map(x=>({technology:x.technology,bands:Array.isArray(x.bands)?x.bands.join('; '):x.bands})),event_month:input.event_month?.slice(0,7)});selectedSiteName.value=input.site_id || '';place(form.latitude,form.longitude);map.value.setView([form.latitude,form.longitude],11);renderCases();showCandidateCluster();}
async function searchSite(){error.value='';try{const r=await axios.get(`${API}/sites/clusters/`,{params:{search:search.value}});searchResults.value=r.data.features || [];}catch(e){error.value=e.message;}}
function goToSite(item){const [lon,lat]=item.geometry.coordinates;map.value.setView([lat,lon],14);if(form.mode==='existing'){form.site_id=String(item.properties.site_id);selectedSiteName.value=item.properties.site_name;place(lat,lon);}searchResults.value=[];}
function drawMembers(origin,members,connect){if(neighborhoodLayer)neighborhoodLayer.remove();neighborhoodLayer=L.layerGroup().addTo(map.value);for(const member of members || []){if(member.latitude==null||member.longitude==null)continue;const point=[member.latitude,member.longitude];L.circleMarker(point,{radius:5,color:'#7c3aed',fillOpacity:.6}).addTo(neighborhoodLayer).bindTooltip(member.site_name || member.site_id || 'Cluster member');if(connect)L.polyline([origin,point],{color:'#7c3aed',weight:1,opacity:.5}).addTo(neighborhoodLayer);}}
function showCandidateCluster(){if(!selected.value)return;drawMembers([selected.value.inputs.latitude,selected.value.inputs.longitude],selected.value.result.assignment?.members || selected.value.features.virtual_cluster_context?.vis_members,selected.value.features.cluster_id===-1);}
async function exploreAnalogue(item){detailSiteId.value=String(item.site_id);map.value.setView([item.latitude,item.longitude],13,{animate:false});try{if(item.cluster_id===-1){const r=await axios.get(`${API}/sites/${item.site_id}/map-links/`);drawMembers([item.latitude,item.longitude],r.data.members,true);}else{const r=await axios.get(`${API}/sites/clusters/`,{params:{cluster_id:item.cluster_id}});drawMembers([item.latitude,item.longitude],r.data.features.map(f=>({latitude:f.geometry.coordinates[1],longitude:f.geometry.coordinates[0],site_name:f.properties.site_name})),false);}}catch(e){error.value='Could not load the analogue cluster: '+e.message;}}
async function submit(){busy.value=true;error.value='';try{if(form.mode==='existing'&&!form.site_id)throw new Error('Search and select an existing site first.');const result=await writeProfile('/candidates/',form);await refresh();loadSaved(result.id);}catch(e){error.value=e.response?.data?.error || e.message;}finally{busy.value=false;}}
onMounted(async()=>{map.value=L.map(mapElement.value).setView([34,9],7);L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{attribution:'© OpenStreetMap contributors',maxZoom:19}).addTo(map.value);map.value.on('click',e=>{if(form.mode==='new')place(e.latlng.lat,e.latlng.lng)});try{const [r,config]=await Promise.all([axios.get(`${API}/sites/clusters/`),loadProfiles()]);profiles.value=config.profiles.filter(p=>p.is_active && ['similarity','both'].includes(p.purpose));L.geoJSON(r.data,{pointToLayer:(_,latlng)=>L.circleMarker(latlng,{radius:3,color:'#64748b',weight:1,fillOpacity:.55}),onEachFeature:(feature,layer)=>layer.bindTooltip(feature.properties.site_name || '').on('click',()=>{if(form.mode==='existing')goToSite(feature)})}).addTo(map.value);await refresh();}catch(e){error.value='Could not load map data: '+e.message;}});
onBeforeUnmount(()=>map.value?.remove());
</script>

<style scoped>
.planning{display:flex;height:100%;min-height:0}.planning aside{width:390px;flex-shrink:0;overflow:auto;padding:18px;background:#f8fafc;color:#1e293b}.map{flex:1;min-width:0}.planning h2,.planning h3{margin:8px 0}.planning p,.planning small{font-size:13px;line-height:1.45;margin:8px 0}.fields,.search,.saved{display:grid;gap:8px;margin:16px 0}.fields label,.saved{display:grid;gap:4px;font-size:13px;font-weight:600}.row{display:flex;gap:8px}.row label{flex:1;min-width:0}input,select,button{font:inherit;padding:8px;border:1px solid #cbd5e1;border-radius:5px;min-width:0}button{cursor:pointer;background:#1d4ed8;color:white}button:disabled{opacity:.6}.search div{display:flex}.search input{flex:1}.search-result,.case{display:flex;justify-content:space-between;text-align:left;background:white;color:#1e293b;margin:4px 0;width:100%}.error{color:#b91c1c}.case span{font-size:12px}dl{display:grid;grid-template-columns:2fr 1fr;gap:4px;font-size:12px}dt{text-transform:capitalize}dd{text-align:right}:deep(.candidate-icon){font-size:30px;line-height:30px;text-align:center;color:#f59e0b;text-shadow:0 0 3px #111,0 1px 3px #111}@media(max-width:700px){.planning{flex-direction:column}.planning aside{width:auto;max-height:55%;}.map{min-height:280px}}
</style>
