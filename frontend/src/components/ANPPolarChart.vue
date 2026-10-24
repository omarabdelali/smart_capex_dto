<template>
  <div class="anp-chart-container">
    <div class="chart-header">
      <h4>Angular Neighborhood Profile</h4>
      <div class="edge-score" :class="edgeScoreClass">
        <span class="score-label">Edge Score:</span>
        <span class="score-value">{{ edgeScoreDisplay }}</span>
      </div>
    </div>
    
    <canvas ref="chartCanvas"></canvas>
    
    <div class="chart-info">
      <p class="info-item">
        <strong>Max Empty Arc:</strong> {{ maxEmptyArc }}°
      </p>
      <p class="info-item">
        <strong>Angular Uniformity:</strong> {{ angularUniformity }}
      </p>
      <p class="info-text">
        Shows neighbor distribution in 12 angular bins (30° each). 
        Higher values = more neighbors in that direction.
      </p>
    </div>
  </div>
</template>

<script>
import { ref, onMounted, onBeforeUnmount, watch, computed } from 'vue';
import {
  Chart,
  PolarAreaController,
  RadialLinearScale,
  ArcElement,
  Tooltip,
  Legend
} from 'chart.js';

// Register Chart.js components
Chart.register(
  PolarAreaController,
  RadialLinearScale,
  ArcElement,
  Tooltip,
  Legend
);

export default {
  name: 'ANPPolarChart',
  
  props: {
    anpData: {
      type: Object,
      required: true,
      validator: (value) => {
        return value && 
               Array.isArray(value.angular_bins) && 
               value.angular_bins.length === 12;
      }
    }
  },
  
  setup(props) {
    const chartCanvas = ref(null);
    let chartInstance = null;
    
    // Computed properties for display
    const edgeScoreDisplay = computed(() => {
      return props.anpData.edge_score?.toFixed(3) || 'N/A';
    });
    
    const edgeScoreClass = computed(() => {
      const score = props.anpData.edge_score || 0;
      if (score >= 0.7) return 'edge-site';
      if (score >= 0.3) return 'intermediate-site';
      return 'infill-site';
    });
    
    const maxEmptyArc = computed(() => {
      return props.anpData.max_empty_arc_deg?.toFixed(1) || 'N/A';
    });
    
    const angularUniformity = computed(() => {
      return props.anpData.angular_uniformity?.toFixed(3) || 'N/A';
    });
    
    /**
     * Create polar area chart showing angular neighbor distribution
     */
    const createChart = () => {
      if (!chartCanvas.value) return;
      
      // Destroy existing chart
      if (chartInstance) {
        chartInstance.destroy();
      }
      
      const ctx = chartCanvas.value.getContext('2d');
      
      // Prepare data
      const angularBins = props.anpData.angular_bins || Array(12).fill(0);
      const labels = [
        '0-30°', '30-60°', '60-90°', '90-120°',
        '120-150°', '150-180°', '180-210°', '210-240°',
        '240-270°', '270-300°', '300-330°', '330-360°'
      ];
      
      // Color scale based on neighbor density
      const maxNeighbors = Math.max(...angularBins, 1);
      const colors = angularBins.map(count => {
        const intensity = count / maxNeighbors;
        if (intensity === 0) return 'rgba(200, 200, 200, 0.5)'; // Gray for empty
        if (intensity < 0.33) return 'rgba(76, 175, 80, 0.7)'; // Green for low
        if (intensity < 0.67) return 'rgba(255, 193, 7, 0.7)'; // Yellow for medium
        return 'rgba(244, 67, 54, 0.7)'; // Red for high
      });
      
      chartInstance = new Chart(ctx, {
        type: 'polarArea',
        data: {
          labels: labels,
          datasets: [{
            label: 'Neighbors per 30° Bin',
            data: angularBins,
            backgroundColor: colors,
            borderColor: 'rgba(0, 0, 0, 0.5)',
            borderWidth: 1
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: true,
          plugins: {
            legend: {
              display: false
            },
            tooltip: {
              callbacks: {
                label: (context) => {
                  const label = context.label || '';
                  const value = context.parsed.r || 0;
                  return `${label}: ${value} neighbors`;
                }
              }
            }
          },
          scales: {
            r: {
              beginAtZero: true,
              ticks: {
                stepSize: 1,
                font: {
                  size: 10
                }
              },
              pointLabels: {
                font: {
                  size: 11
                }
              }
            }
          }
        }
      });
    };
    
    /**
     * Initialize chart on mount
     */
    onMounted(() => {
      createChart();
    });
    
    /**
     * Recreate chart when data changes
     */
    watch(() => props.anpData, () => {
      createChart();
    }, { deep: true });

    onBeforeUnmount(() => {
      if (chartInstance) chartInstance.destroy();
    });
    
    return {
      chartCanvas,
      edgeScoreDisplay,
      edgeScoreClass,
      maxEmptyArc,
      angularUniformity
    };
  }
};
</script>

<style scoped>
.anp-chart-container {
  padding: 15px;
  background: white;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.chart-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 15px;
  padding-bottom: 10px;
  border-bottom: 2px solid #e0e0e0;
}

.chart-header h4 {
  margin: 0;
  color: #2c3e50;
  font-size: 16px;
}

.edge-score {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  border-radius: 20px;
  font-weight: 600;
}

.edge-score.edge-site {
  background-color: #ffebee;
  color: #c62828;
}

.edge-score.intermediate-site {
  background-color: #fff3e0;
  color: #ef6c00;
}

.edge-score.infill-site {
  background-color: #e8f5e9;
  color: #2e7d32;
}

.score-label {
  font-size: 12px;
  opacity: 0.8;
}

.score-value {
  font-size: 16px;
  font-weight: bold;
}

canvas {
  max-height: 300px;
  width: 100%;
  max-width: 300px;
  margin: 0 auto;
  display: block;
}

@media (max-width: 480px) {
  .anp-chart-container { padding: 10px; }
  canvas { max-height: 250px; }
  .chart-info { margin-top: 10px; }
}

.chart-info {
  margin-top: 15px;
  padding-top: 10px;
  border-top: 1px solid #e0e0e0;
}

.info-item {
  margin: 8px 0;
  font-size: 13px;
  color: #555;
}

.info-item strong {
  color: #2c3e50;
  margin-right: 4px;
}

.info-text {
  margin-top: 10px;
  font-size: 11px;
  color: #777;
  font-style: italic;
  line-height: 1.4;
}
</style>
