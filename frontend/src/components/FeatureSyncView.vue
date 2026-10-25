<template>
  <section class="sync-page">
    <div class="intro">
      <p class="eyebrow">DATA OPERATIONS</p>
      <h2>Feature synchronization</h2>
      <p>Recompute the persisted site features from the current cell plan and available geographic and MAOS data.</p>
    </div>

    <div class="actions">
      <article>
        <h3>Features only</h3>
        <p>Recalculate all stored feature families for every site.</p>
        <button :disabled="busy || loading" @click="start('features')">Recompute features</button>
      </article>
      <article class="full-sync">
        <h3>Full sync</h3>
        <p>Redetect cell and site additions from MAOS history, then recompute all site features.</p>
        <button :disabled="busy || loading" @click="start('full')">Detect additions and recompute</button>
      </article>
    </div>

    <div v-if="errorMessage" class="notice error">{{ errorMessage }}</div>
    <section v-if="job" class="job-card" aria-live="polite">
      <div class="job-heading">
        <div><p class="eyebrow">LATEST RUN · #{{ job.id }}</p><h3>{{ modeLabel }} <span :class="['status', job.status]">{{ job.status }}</span></h3></div>
        <time v-if="job.created_at">{{ formatDate(job.created_at) }}</time>
      </div>
      <p class="stage">{{ stageLabel }}</p>
      <div v-if="job.total" class="progress-track" role="progressbar" :aria-valuenow="job.processed" :aria-valuemax="job.total">
        <div class="progress-fill" :style="{ width: `${Math.min(100, (job.processed / job.total) * 100)}%` }"></div>
      </div>
      <p v-if="job.total" class="progress-copy">{{ job.processed.toLocaleString() }} / {{ job.total.toLocaleString() }} sites<span v-if="job.current_site"> · Current site {{ job.current_site }}</span></p>
      <p v-if="job.error" class="notice error">{{ job.error }}</p>
      <div v-if="job.result" class="results">
        <div v-if="job.result.detection"><strong>{{ job.result.detection.detected_cells?.toLocaleString() ?? 0 }}</strong><span>added cells detected</span></div>
        <div v-if="job.result.detection"><strong>{{ job.result.detection.detected_sites?.toLocaleString() ?? 0 }}</strong><span>sites detected</span></div>
        <div v-if="job.result.features"><strong>{{ job.result.features.successful?.toLocaleString() ?? 0 }}</strong><span>sites recomputed</span></div>
        <div v-if="job.result.features"><strong>{{ job.result.features.failed?.toLocaleString() ?? 0 }}</strong><span>site failures</span></div>
      </div>
    </section>
    <p v-else-if="!loading" class="empty">No synchronization runs yet.</p>
  </section>
</template>

<script>
import axios from 'axios';
import { computed, onMounted, onUnmounted, ref } from 'vue';

export default {
  name: 'FeatureSyncView',
  setup() {
    const API = 'http://localhost:8000/api/features/sync/';
    const job = ref(null);
    const loading = ref(true);
    const errorMessage = ref('');
    let pollTimer = null;
    const busy = computed(() => job.value && ['queued', 'running'].includes(job.value.status));
    const modeLabel = computed(() => job.value?.mode === 'full' ? 'Full sync' : 'Features only');
    const stageLabel = computed(() => ({
      queued: 'Waiting for the sync worker', starting: 'Preparing feature extraction',
      detecting_additions: 'Detecting additions from MAOS history', features: 'Recomputing site features',
      complete: 'Synchronization complete', failed: 'Synchronization failed',
    }[job.value?.stage] || job.value?.stage || 'Status unavailable'));

    async function refresh() {
      try {
        const response = await axios.get(API);
        job.value = response.data.job;
        errorMessage.value = '';
      } catch (error) {
        errorMessage.value = error.response?.data?.error || 'Could not load synchronization status. Check that the backend is running.';
      } finally { loading.value = false; }
      if (job.value && ['queued', 'running'].includes(job.value.status)) startPolling();
      else stopPolling();
    }
    function startPolling() {
      if (!pollTimer) pollTimer = window.setInterval(refresh, 2000);
    }
    function stopPolling() {
      if (pollTimer) window.clearInterval(pollTimer);
      pollTimer = null;
    }
    async function start(mode) {
      errorMessage.value = '';
      try {
        const response = await axios.post(API, { mode });
        job.value = response.data.job;
        startPolling();
        refresh();
      } catch (error) {
        job.value = error.response?.data?.job || job.value;
        errorMessage.value = error.response?.data?.error || 'Could not start synchronization.';
        if (job.value && ['queued', 'running'].includes(job.value.status)) startPolling();
      }
    }
    function formatDate(value) { return new Date(value).toLocaleString(); }
    onMounted(refresh);
    onUnmounted(stopPolling);
    return { job, busy, loading, errorMessage, modeLabel, stageLabel, start, formatDate };
  },
};
</script>

<style scoped>
.sync-page { height: 100%; overflow: auto; padding: clamp(18px, 4vw, 42px); background: #f5f7fb; color: #1e293b; }
.intro { max-width: 740px; margin-bottom: 26px; }
.eyebrow { color: #64748b; font-size: 11px; font-weight: 700; letter-spacing: .12em; }
h2 { margin: 7px 0; font-size: clamp(23px, 3vw, 32px); }
.intro > p:last-child, .actions p { color: #64748b; line-height: 1.5; }
.actions { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; max-width: 960px; }
.actions article, .job-card { background: white; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; box-shadow: 0 4px 16px #0f172a08; }
.actions h3 { margin-bottom: 8px; }
.actions p { min-height: 44px; margin-bottom: 16px; }
button { border: 0; border-radius: 7px; padding: 10px 14px; background: #2563eb; color: white; font: inherit; font-weight: 600; cursor: pointer; }
button:disabled { opacity: .5; cursor: wait; }
.full-sync button { background: #6d28d9; }
.job-card { max-width: 960px; margin-top: 22px; }
.job-heading { display: flex; justify-content: space-between; align-items: start; gap: 10px; }
.job-heading h3 { margin-top: 5px; }
.job-heading time, .progress-copy { color: #64748b; font-size: 13px; }
.status { display: inline-block; margin-left: 7px; padding: 3px 8px; border-radius: 99px; background: #e2e8f0; color: #334155; font-size: 11px; text-transform: uppercase; vertical-align: middle; }
.status.running { color: #1d4ed8; background: #dbeafe; }.status.succeeded { color: #15803d; background: #dcfce7; }.status.failed { color: #b91c1c; background: #fee2e2; }
.stage { margin: 18px 0 10px; font-weight: 600; }
.progress-track { height: 9px; overflow: hidden; border-radius: 9px; background: #e2e8f0; }
.progress-fill { height: 100%; background: linear-gradient(90deg, #3b82f6, #8b5cf6); transition: width .25s; }
.progress-copy { margin-top: 7px; }
.results { display: flex; flex-wrap: wrap; gap: 24px; margin-top: 18px; padding-top: 15px; border-top: 1px solid #e2e8f0; }
.results div { display: grid; gap: 3px; }.results strong { font-size: 20px; }.results span { color: #64748b; font-size: 12px; }
.notice { max-width: 960px; margin-top: 16px; padding: 12px; border-radius: 8px; }.error { color: #991b1b; background: #fee2e2; }.empty { margin-top: 24px; color: #64748b; }
@media(max-width: 700px) { .actions { grid-template-columns: 1fr; }.actions p { min-height: 0; }.job-heading { flex-direction: column; } }
</style>
