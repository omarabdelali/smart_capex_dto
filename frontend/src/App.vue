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
  display: flex;
  flex-direction: column;
}

.app-header {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  padding: 20px;
  box-shadow: 0 2px 10px rgba(0,0,0,0.1);
}

.app-header h1 {
  font-size: 28px;
  margin-bottom: 5px;
}

.app-header p {
  font-size: 14px;
  opacity: 0.9;
}

.app-main {
  flex: 1;
  overflow: hidden;
}
</style>