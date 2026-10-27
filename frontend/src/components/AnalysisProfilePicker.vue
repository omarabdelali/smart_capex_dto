<template>
<section class="profile-picker" aria-label="Analysis profile">
  <label>Configuration profile<select aria-label="Configuration profile" v-model="selected" @change="choose"><option value="">Scenario default (automatic)</option><option value="manual">Manual (ignore defaults)</option><option v-for="p in profiles" :key="p.id" :value="p.id">{{p.name}} · {{p.is_shared?'shared':'this browser'}} · v{{p.revision}}{{p.event_type!=='ANY'?' · '+p.event_type:''}}</option></select></label>
  <button type="button" @click="refresh">Reload templates</button>
  <details><summary>Save current settings for future use</summary><label>Preset name<input v-model="name" maxlength="120" placeholder="My analysis preset"></label><button type="button" :disabled="busy || !name.trim()" @click="save">Save personal preset</button><p>Personal presets belong to this browser. Shared templates and scenario defaults are managed in Administration.</p><p v-if="currentSettings?.representation==='pca'">PCA presets save the original input fields and variance target. Components are refitted for each query; individual PC checkboxes are not saved.</p></details>
  <p v-if="applied?.name">Applied: {{applied.name}} · revision {{applied.revision}}. Changes to controls are unsaved until you save a preset.</p>
  <p v-if="message" role="status">{{message}}</p><p v-if="error" role="alert">{{error}}</p>
</section>
</template>
<script setup>
import {ref,onMounted,onBeforeUnmount} from 'vue';
import {loadProfiles,writeProfile} from '../analysisProfiles';
const props=defineProps({purpose:String,currentSettings:Object,applied:Object});
const emit=defineEmits(['change']);
const selected=ref(''),profiles=ref([]),name=ref(''),message=ref(''),error=ref(''),busy=ref(false);
let base={};
async function refresh(){try{const data=await loadProfiles();profiles.value=data.profiles.filter(p=>p.is_active && [props.purpose,'both'].includes(p.purpose));base=data.catalog.defaults;}catch(e){error.value=e.response?.data?.error||'Cannot load templates.';}}
function choose(){error.value='';const p=profiles.value.find(p=>p.id===selected.value);emit('change',{id:selected.value,settings:p?.settings||null});}
async function save(){busy.value=true;error.value='';try{const p=await writeProfile('/analysis/profiles/',{name:name.value,purpose:props.purpose,is_shared:false,settings:{...base,...props.currentSettings}});await refresh();selected.value=p.id;choose();message.value='Preset saved.';}catch(e){error.value=e.response?.data?.error||'Could not save preset.';}finally{busy.value=false;}}

onMounted(()=>{refresh();window.addEventListener('analysis-profiles-updated',refresh);});
onBeforeUnmount(()=>window.removeEventListener('analysis-profiles-updated',refresh));
</script>
<style scoped>
.profile-picker{border:1px solid #cbd5e1;background:#f8fafc;border-radius:8px;padding:12px;margin:12px 0}.profile-picker label{display:inline-flex;flex-direction:column;gap:5px;margin-right:10px}select,input{padding:8px;max-width:100%;border:1px solid #94a3b8;border-radius:5px}button{padding:8px;margin:6px;background:#1d4ed8;color:white;border:0;border-radius:5px}p{font-size:12px}details{margin-top:10px}[role=alert]{color:#b91c1c}
</style>
