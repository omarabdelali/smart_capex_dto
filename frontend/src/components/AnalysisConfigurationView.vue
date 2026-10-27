<template>
<section class="configuration">
  <h2>Administration · configuration and templates</h2>
  <p>Create shared scenario templates and workspace defaults for similarity and prediction. Personal presets are saved for this browser. This page follows the app's existing shared-workspace access model.</p>
  <p v-if="error" role="alert">{{error}}</p><p v-if="message" role="status">{{message}}</p>
  <template v-if="data.catalog">
  <div class="toolbar"><label>Template<select aria-label="Template" v-model="selected" @change="edit"><option value="">New template</option><option v-for="p in data.profiles" :key="p.id" :value="p.id">{{p.name}} · {{p.is_shared?'shared':'personal'}} · v{{p.revision}}{{p.is_active?'':' · archived'}}</option></select></label><button @click="newProfile">New template</button><button @click="reload">Reload</button></div>
  <form @submit.prevent="save(false)">
  <div class="fields">
    <label>Name<input v-model="form.name" required maxlength="120"></label><label>Purpose<select v-model="form.purpose"><option v-for="p in data.catalog.purposes" :key="p">{{p}}</option></select></label>
    <label>Event scenario<select v-model="form.event_type"><option v-for="v in data.catalog.event_types" :key="v">{{v}}</option></select></label>
    <label>Tier scheme<select v-model="form.tier_scheme"><option v-for="v in data.catalog.tier_schemes" :key="v">{{v}}</option></select></label>
    <label>Technology<select v-model="form.technology"><option v-for="v in data.catalog.technologies" :key="v">{{v}}</option></select></label>
    <label><input type="checkbox" v-model="form.is_shared" :disabled="!!selected">Shared workspace template</label><label><input type="checkbox" v-model="form.is_active">Active</label>
  </div>
  <label>Description<textarea v-model="form.description" maxlength="5000"></textarea></label>
  <div class="fields">
    <label>Similarity representation<select v-model="form.settings.representation"><option value="original">Original features</option><option value="pca">PCA + separate categorical / road fields</option></select></label>
    <label>PCA retained variance<input type="number" min="0.5" max="0.99" step="0.01" v-model.number="form.settings.pca_variance_target"></label>
    <label>Weighting<select v-model="form.settings.weighting_mode"><option value="equal_per_feature">Equal per feature</option><option value="equal_per_group">Equal per group</option></select></label>
    <label>Minimum available weight<input type="number" min="0.6" max="1" step="0.05" v-model.number="form.settings.minimum_available_weight_share"></label>
    <label><input type="checkbox" v-model="form.settings.allow_filter_relaxation">Allow technology/band relaxation</label>
    <label>Prediction method<select v-model="form.settings.prediction_method"><option value="pair_cbr">Gaussian CBR</option><option value="control_adjusted">Matched controls</option><option value="local_linear">Local ridge</option><option value="did_local_linear">Matched controls + local ridge</option></select></label>
    <label>Default scope<select v-model="form.settings.scope"><option v-for="v in scopes" :key="v">{{v}}</option></select></label>
    <label><input type="checkbox" v-model="form.settings.ramp">Smooth supported ramp</label>
  </div>
  <p>Event type and tier scheme remain mandatory. Missing values stay NULL. Saved profiles use only selected fields. PCA is exploratory site retrieval; recipient prediction uses its separate pair features. Road weight remains capped at 5% in site similarity.</p>
  <label>Find feature<input v-model="filter" type="search" placeholder="Filter feature lists"></label>
  <div class="feature-columns"><section v-for="kind in kinds" :key="kind.key"><h3>{{kind.label}} ({{form.settings[kind.key].length}} selected)</h3><p>{{kind.note}}</p><div class="scroll"><label v-for="f in data.catalog[kind.key].filter(f=>`${f.key} ${f.group}`.toLowerCase().includes(filter.toLowerCase()))" :key="f.key"><input type="checkbox" :value="f.key" v-model="form.settings[kind.key]">{{f.label}} <small>{{f.group}} · {{f.type}}</small></label></div></section></div>
  <div class="toolbar"><button type="submit" :disabled="busy">{{selected?'Save revision':'Create template'}}</button><button type="button" :disabled="busy || !form.name" @click="save(true)">Save as new copy</button><button type="button" @click="exportTemplate">Export JSON</button><label>Import JSON<input type="file" accept="application/json" @change="importTemplate"></label></div>
  </form>
  <section v-if="selected"><h3>Use as scenario default</h3><p>Personal defaults take precedence over workspace defaults; more specific scenarios take precedence within each scope.</p><div class="toolbar"><template v-for="purpose in ['similarity','prediction']" :key="purpose"><button v-if="[purpose,'both'].includes(form.purpose)" @click="setDefault(purpose,'personal')">My {{purpose}} default</button><button v-if="form.is_shared && [purpose,'both'].includes(form.purpose)" @click="setDefault(purpose,'system')">Workspace {{purpose}} default</button></template></div></section>
  <section><h3>Default assignments</h3><ul><li v-for="d in data.defaults" :key="d.id">{{d.scope==='system'?'Workspace':'This browser'}} · {{d.purpose}} · {{d.scenario_key}} → {{data.profiles.find(p=>p.id===d.profile_id)?.name}} <button @click="clearDefault(d.id)">Clear assignment</button></li></ul></section>
  </template>
</section>
</template>
<script setup>
import {ref,onMounted} from 'vue';
import {loadProfiles,writeProfile} from '../analysisProfiles';
const clone=value=>JSON.parse(JSON.stringify(value));
const data=ref({}),selected=ref(''),form=ref({}),filter=ref(''),error=ref(''),message=ref(''),busy=ref(false);
const kinds=[{key:'similarity_features',label:'Site similarity / legacy CBR',note:'PCA stores these original source fields; PC numbers are fitted for each query.'},{key:'prediction_features',label:'Recipient prediction',note:'Event-to-recipient geometry, load and action magnitude.'}];
const scopes=['tier1','tier2','cluster','virtual_cluster','distance_0_2','distance_2_5','distance_5_10'];
function newProfile(){selected.value='';form.value={name:'',description:'',purpose:'both',event_type:'ANY',tier_scheme:'ANY',technology:'ANY',is_shared:true,is_active:true,settings:clone(data.value.catalog.defaults)};}
function edit(){const p=data.value.profiles.find(p=>p.id===selected.value);if(!p){newProfile();return;}form.value=Object.fromEntries(['name','description','purpose','event_type','tier_scheme','technology','is_shared','is_active','settings','revision'].map(k=>[k,clone(p[k])]));}
async function reload(){try{data.value=await loadProfiles();if(selected.value)edit();else newProfile();}catch(e){error.value=e.response?.data?.error||'Could not load configuration.';}}
async function save(copy){busy.value=true;error.value='';try{const body=clone(form.value);if(copy)delete body.revision;const p=await writeProfile(`/analysis/profiles/${selected.value&&!copy?selected.value+'/':''}`,body,selected.value&&!copy?'put':'post');selected.value=p.id;await reload();message.value='Template saved with its revision.';}catch(e){error.value=e.response?.data?.error||'Could not save template.';}finally{busy.value=false;}}
async function setDefault(purpose,scope){try{await writeProfile('/analysis/defaults/',{profile_id:selected.value,purpose,scope});await reload();message.value='Default saved.';}catch(e){error.value=e.response?.data?.error||'Could not assign default.';}}
async function clearDefault(id){try{await writeProfile(`/analysis/defaults/${id}/`,null,'delete');await reload();}catch(e){error.value=e.response?.data?.error||'Could not clear assignment.';}}
function exportTemplate(){const blob=new Blob([JSON.stringify(form.value,null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='analysis-template.json';a.click();URL.revokeObjectURL(url);}
async function importTemplate(event){try{const body=JSON.parse(await event.target.files[0].text());if(!body || typeof body!=='object' || Array.isArray(body) || !body.settings || ['similarity_features','prediction_features'].some(k=>!Array.isArray(body.settings[k]) || body.settings[k].some(f=>typeof f!=='string')))throw new Error('Invalid template');newProfile();Object.assign(form.value,body);form.value.settings={...data.value.catalog.defaults,...body.settings};delete form.value.revision;message.value='Imported as an unsaved copy. Review and save.';}catch{error.value='Invalid JSON template.';}event.target.value='';}
onMounted(reload);
</script>
<style scoped>
.configuration{height:100%;overflow:auto;background:#f8fafc;color:#1e293b;padding:24px;box-sizing:border-box}.fields,.toolbar{display:flex;flex-wrap:wrap;gap:14px;margin:15px 0}label{display:flex;flex-direction:column;gap:5px;min-width:0;max-width:100%}input,select,textarea{padding:8px;border:1px solid #94a3b8;border-radius:5px;max-width:100%}input[type=checkbox]{width:auto}label:has(input[type=checkbox]){flex-direction:row;align-items:center}textarea{min-height:60px}.feature-columns{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px}.scroll{height:330px;overflow:auto;background:white;border:1px solid #cbd5e1;padding:10px}.scroll label{padding:7px;border-bottom:1px solid #e2e8f0;flex-wrap:wrap}.scroll small{color:#64748b}button{padding:9px;background:#1d4ed8;border:0;border-radius:5px;color:white;cursor:pointer}button:disabled{opacity:.5}[role=alert]{color:#b91c1c}li{margin:8px 0}@media(max-width:750px){.feature-columns{grid-template-columns:1fr}}
</style>
