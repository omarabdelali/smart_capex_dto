<template>
  <div class="elevation-legend" v-if="visible">
    <h5>Elevation (m)</h5>
    <div class="legend-gradient"></div>
    <div class="legend-labels">
      <span class="legend-label">{{ minElev }}</span>
      <span class="legend-label">{{ midElev }}</span>
      <span class="legend-label">{{ maxElev }}</span>
    </div>
  </div>
</template>

<script>
import { computed } from 'vue';

export default {
  name: 'ElevationLegend',
  
  props: {
    visible: {
      type: Boolean,
      default: false
    },
    minElevation: {
      type: Number,
      default: 0
    },
    maxElevation: {
      type: Number,
      default: 1544  // Jebel ech Chambi - Tunisia's highest peak
    }
  },
  
  setup(props) {
    const minElev = computed(() => Math.round(props.minElevation));
    const midElev = computed(() => Math.round((props.minElevation + props.maxElevation) / 2));
    const maxElev = computed(() => Math.round(props.maxElevation));
    
    return {
      minElev,
      midElev,
      maxElev
    };
  }
};
</script>

<style scoped>
.elevation-legend {
  position: absolute;
  bottom: 30px;
  right: 10px;
  background: rgba(255, 255, 255, 0.95);
  padding: 12px;
  border-radius: 5px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
  min-width: 180px;
  z-index: 1000;
}

.elevation-legend h5 {
  margin: 0 0 8px 0;
  font-size: 13px;
  font-weight: 600;
  color: #2c3e50;
  text-align: center;
}

.legend-gradient {
  height: 150px;
  background: linear-gradient(
    to top,
    #1a9850,  /* Low elevation - green */
    #91cf60,
    #d9ef8b,
    #fee08b,
    #fc8d59,
    #d73027   /* High elevation - red */
  );
  border: 1px solid #999;
  border-radius: 3px;
  margin-bottom: 5px;
}

.legend-labels {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  color: #555;
}

.legend-label {
  flex: 1;
  text-align: center;
  font-weight: 500;
}

.legend-label:first-child {
  text-align: left;
}

.legend-label:last-child {
  text-align: right;
}
</style>