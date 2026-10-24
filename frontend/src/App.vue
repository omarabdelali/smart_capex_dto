<template>
  <div id="app">
    <header class="app-header">
      <h1>Smart CAPEX - Site Clustering</h1>
      <p>Phase 1: Tunisia Network Visualization</p>
    </header>
    
    <main class="app-main">
      <ClusterMapView />
    </main>
  </div>
</template>

<script>
import ClusterMapView from './components/ClusterMapView.vue';

export default {
  name: 'App',
  components: {
    ClusterMapView
  }
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

@media (max-width: 760px) {
  .app-header { padding: 8px 12px; }
  .app-header h1 { font-size: 17px; margin-bottom: 2px; }
  .app-header p { font-size: 11px; }
}
</style>
