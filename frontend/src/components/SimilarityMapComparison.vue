<template>
<section class="map-comparison" aria-label="Side by side site comparison">
  <header><div><h2>Compare site surroundings</h2><p>Query site on the left; choose a similar site on the right. Each map has its own zoom, layers and site details. Links show current neighborhoods.</p></div><button @click="$emit('close')">Return to all sites</button><button @click="$emit('back')">Back to similarity</button></header>
  <div class="comparison-panes">
    <section class="comparison-pane" aria-label="Query site map"><div class="pane-heading"><strong>Query: {{focus.querySiteName || focus.querySiteId}}</strong><span>ID {{focus.querySiteId}}</span></div><ClusterMapView compact :focus-sites="leftFocus" /></section>
    <section class="comparison-pane" aria-label="Similar site map"><div class="pane-heading"><label>Similar site<select aria-label="Similar site to compare" v-model="selectedId"><option v-for="site in cases" :key="site.site_id" :value="String(site.site_id)">{{site.site_name || site.site_id}} · {{site.site_id}}{{site.similarity==null?'':' · '+(100*site.similarity).toFixed(1)+'%'}}</option></select></label><span v-if="selected">{{selected.event_date || ''}} · {{selected.event_type || ''}}</span></div><ClusterMapView v-if="rightFocus" compact :focus-sites="rightFocus" /></section>
  </div>
</section>
</template>
<script setup>
import {computed,ref,watch} from 'vue';
import ClusterMapView from './ClusterMapView.vue';
const props=defineProps({focus:{type:Object,required:true}});
defineEmits(['close','back']);
const cases=computed(()=>props.focus.cases || props.focus.siteIds.filter(id=>String(id)!==String(props.focus.querySiteId)).map(id=>({site_id:id})));
const selectedId=ref('');
watch(()=>props.focus,()=>{selectedId.value=String(props.focus.selectedCaseId || cases.value[0]?.site_id || '');},{immediate:true});
const selected=computed(()=>cases.value.find(site=>String(site.site_id)===selectedId.value));
const leftFocus=computed(()=>({querySiteId:String(props.focus.querySiteId),siteIds:[String(props.focus.querySiteId)]}));
const rightFocus=computed(()=>selected.value?{querySiteId:selectedId.value,siteIds:[selectedId.value]}:null);
</script>
<style scoped>
.map-comparison{height:100%;display:flex;flex-direction:column;min-height:0;background:#f8fafc;color:#1e293b}header{display:flex;gap:12px;align-items:center;padding:12px 18px;flex-wrap:wrap}header div{flex:1}header p{font-size:12px;margin-top:5px}button{padding:8px;border:1px solid #94a3b8;border-radius:5px;background:white;color:#1e293b;cursor:pointer}.comparison-panes{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);flex:1;min-height:0;gap:8px;padding:0 8px 8px}.comparison-pane{display:flex;flex-direction:column;min-height:0;min-width:0;border:1px solid #cbd5e1;border-radius:7px;overflow:hidden}.pane-heading{padding:10px;background:white;display:grid;gap:5px;min-height:80px;font-size:13px}.pane-heading label{display:flex;align-items:center;gap:8px;min-width:0}select{padding:7px;min-width:0;width:100%;border:1px solid #94a3b8;border-radius:5px}.pane-heading span{color:#64748b;font-size:12px}.comparison-pane :deep(.cluster-map-container){flex:1;height:auto}@media(max-width:720px){.map-comparison{overflow:auto;display:block}.comparison-panes{grid-template-columns:1fr;min-height:1000px}.comparison-pane{min-height:480px}header h2{font-size:17px}}
</style>
