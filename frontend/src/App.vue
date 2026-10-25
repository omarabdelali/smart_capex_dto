<template>
  <div id="app">
    <header class="app-header">
      <h1>Smart CAPEX - Site Clustering</h1>
      <p>Phase 1: Tunisia Network Visualization</p>
    </header>

    <nav class="app-navigation" aria-label="Main pages">
      <button type="button" :aria-current="activePage === 'map' ? 'page' : null" @click="activePage = 'map'">Site map</button>
      <button type="button" :aria-current="activePage === 'clusters' ? 'page' : null" @click="activePage = 'clusters'">Cluster analysis</button>
      <button type="button" :aria-current="activePage === 'sync' ? 'page' : null" @click="activePage = 'sync'">Feature sync</button>
    </nav>
    
    <main class="app-main">
      <ClusterMapView v-if="activePage === 'map'" />
      <ClusterAnalysisView v-else-if="activePage === 'clusters'" />
      <FeatureSyncView v-else />
    </main>
  </div>
</template>

<script>
import { ref } from 'vue';
import ClusterMapView from './components/ClusterMapView.vue';
import ClusterAnalysisView from './components/ClusterAnalysisView.vue';
import FeatureSyncView from './components/FeatureSyncView.vue';

export default {
  name: 'App',
  components: {
    ClusterMapView,
    ClusterAnalysisView,
    FeatureSyncView
  },
  setup() {
    return { activePage: ref('map') };
  },
};
</script>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

#app {
  font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
  height: 100vh;
  height: 100dvh;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.app-header {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  flex: 0 0 auto;
  padding: clamp(10px, 1.5vw, 20px);
  box-shadow: 0 2px 10px rgba(0,0,0,0.1);
}

.app-header h1 {
  font-size: clamp(18px, 2vw, 28px);
  margin-bottom: 5px;
}

.app-header p {
  font-size: 14px;
  opacity: 0.9;
}

.app-main {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.app-navigation {
  display: flex;
  flex: 0 0 auto;
  gap: 6px;
  padding: 8px clamp(10px, 1.5vw, 20px);
  background: #f8fafc;
  border-bottom: 1px solid #dbe2ea;
}

.app-navigation button {
  padding: 8px 12px;
  border: 1px solid transparent;
  border-radius: 6px;
  background: transparent;
  color: #334155;
  font: inherit;
  cursor: pointer;
}

.app-navigation button[aria-current="page"] {
  border-color: #bfdbfe;
  background: #eff6ff;
  color: #1d4ed8;
  font-weight: 600;
}

@media (max-width: 760px) {
  .app-header { padding: 8px 12px; }
  .app-header h1 { font-size: 17px; margin-bottom: 2px; }
  .app-header p { font-size: 11px; }
}
</style>
