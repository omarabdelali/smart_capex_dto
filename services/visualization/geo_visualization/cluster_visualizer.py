"""
Cluster Visualization Module for Smart CAPEX Phase 2.
Creates interactive Folium maps displaying clustering results.

Features:
- Display site locations with cluster-based color coding
- Show cluster polygons (alpha shape boundaries)
- Highlight out-of-bounds sites in red
- Show edge sites vs interior sites with different markers
- Include popups with site details and cluster features
- Export maps to HTML for exploration

Uses Folium for interactive web-based mapping.
"""

import folium
from folium import plugins
import numpy as np
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import logging
from shapely.geometry import Polygon
import json

from services.models.preprocessing.site_clustering import Site, ClusterResult

logger = logging.getLogger(__name__)


class ClusterVisualizer:
    """
    Create interactive maps visualizing clustering results.
    
    Uses Folium to generate HTML maps showing:
    - Site locations with cluster colors
    - Cluster polygon boundaries
    - Out-of-bounds sites highlighted
    - Edge sites marked differently from interior sites
    """
    
    # Color palette for clusters (supports up to 20 clusters)
    CLUSTER_COLORS = [
        '#e6194b', '#3cb44b', '#ffe119', '#4363d8', '#f58231',
        '#911eb4', '#46f0f0', '#f032e6', '#bcf60c', '#fabebe',
        '#008080', '#e6beff', '#9a6324', '#fffac8', '#800000',
        '#aaffc3', '#808000', '#ffd8b1', '#000075', '#808080'
    ]
    
    # Special colors
    NOISE_COLOR = '#999999'  # Gray for noise points
    OUT_OF_BOUNDS_COLOR = '#ff0000'  # Red for out-of-bounds sites
    EDGE_COLOR = '#ff8c00'  # Orange for edge sites
    
    def __init__(self, center_lat: float = 36.0, center_lon: float = 9.5, zoom_start: int = 7):
        """
        Initialize visualizer.
        
        Args:
            center_lat: Map center latitude (default: Tunisia center ~36°N)
            center_lon: Map center longitude (default: Tunisia center ~9.5°E)
            zoom_start: Initial zoom level (default: 7 for country view)
        """
        self.center_lat = center_lat
        self.center_lon = center_lon
        self.zoom_start = zoom_start
        logger.info(f"Initialized ClusterVisualizer centered at ({center_lat}, {center_lon})")
    
    def _get_cluster_color(self, cluster_id: int, out_of_bounds: bool = False) -> str:
        """
        Get color for cluster ID.
        
        Args:
            cluster_id: Cluster ID
            out_of_bounds: Whether site is out of bounds
            
        Returns:
            Hex color string
        """
        if out_of_bounds:
            return self.OUT_OF_BOUNDS_COLOR
        elif cluster_id == -1:
            return self.NOISE_COLOR
        else:
            return self.CLUSTER_COLORS[cluster_id % len(self.CLUSTER_COLORS)]
    
    def create_cluster_map(
        self,
        sites: List[Site],
        cluster_results: List[ClusterResult],
        polygons: Optional[Dict[int, Polygon]] = None,
        title: str = "Site Clustering Results"
    ) -> folium.Map:
        """
        Create interactive map showing clustering results.
        
        Args:
            sites: List of Site objects
            cluster_results: List of ClusterResult objects
            polygons: Optional dictionary of cluster polygons
            title: Map title
            
        Returns:
            Folium Map object
        """
        logger.info(f"Creating cluster map with {len(sites)} sites")
        
        # Create result lookup
        result_map = {r.site_id: r for r in cluster_results}
        
        # Create base map
        m = folium.Map(
            location=[self.center_lat, self.center_lon],
            zoom_start=self.zoom_start,
            tiles='OpenStreetMap'
        )
        
        # Add title
        title_html = f'''
        <div style="position: fixed; 
                    top: 10px; left: 50px; width: 400px; height: 50px; 
                    background-color: white; border:2px solid grey; z-index:9999; 
                    font-size:16px; font-weight: bold; padding: 10px">
            {title}
        </div>
        '''
        m.get_root().html.add_child(folium.Element(title_html))
        
        # Add cluster polygons if provided
        if polygons:
            logger.info(f"Adding {len(polygons)} cluster polygons to map")
            for cluster_id, polygon in polygons.items():
                if cluster_id == -1:
                    continue  # Skip noise points
                
                color = self._get_cluster_color(cluster_id)
                
                # Convert shapely polygon to folium format
                coords = list(polygon.exterior.coords)
                folium_coords = [(lat, lon) for lon, lat in coords]
                
                folium.Polygon(
                    locations=folium_coords,
                    color=color,
                    fill=True,
                    fill_color=color,
                    fill_opacity=0.2,
                    weight=2,
                    popup=f"Cluster {cluster_id}"
                ).add_to(m)
        
        # Add site markers
        for site in sites:
            result = result_map.get(site.site_id)
            
            if not result:
                continue
            
            # Determine marker color and icon
            color = self._get_cluster_color(result.cluster_id, result.out_of_bounds)
            
            if result.out_of_bounds:
                icon_color = 'red'
                icon = 'exclamation-sign'
            elif result.is_cluster_edge:
                icon_color = 'orange'
                icon = 'record'
            else:
                icon_color = 'green'
                icon = 'circle'
            
            # Create popup with site details
            popup_html = f"""
            <div style="width: 250px;">
                <h4>{site.site_name}</h4>
                <b>Site ID:</b> {site.site_id}<br>
                <b>Coordinates:</b> ({site.latitude:.4f}, {site.longitude:.4f})<br>
                <hr>
                <b>Cluster ID:</b> {result.cluster_id}<br>
                <b>Cluster Size:</b> {result.cluster_size} sites<br>
                <b>Cluster Density:</b> {result.cluster_density_sites_per_km2:.2f} sites/km²<br>
                <b>Avg Traffic:</b> {result.cluster_avg_traffic_gb:.2f} GB<br>
                <b>Avg Users:</b> {result.cluster_avg_users:.0f}<br>
                <hr>
                <b>Distance to Centroid:</b> {result.dist_to_cluster_centroid_m:.0f} m<br>
                <b>Is Edge Site:</b> {'Yes' if result.is_cluster_edge else 'No'}<br>
                <b>Out of Bounds:</b> {'<span style="color:red;">YES</span>' if result.out_of_bounds else 'No'}<br>
            </div>
            """
            
            # Add marker
            folium.Marker(
                location=[site.latitude, site.longitude],
                popup=folium.Popup(popup_html, max_width=300),
                icon=folium.Icon(color=icon_color, icon=icon, prefix='glyphicon'),
                tooltip=site.site_name
            ).add_to(m)
        
        # Add legend
        legend_html = self._create_legend(cluster_results)
        m.get_root().html.add_child(folium.Element(legend_html))
        
        # Add layer control
        folium.LayerControl().add_to(m)
        
        logger.info("Cluster map created successfully")
        return m
    
    def _create_legend(self, cluster_results: List[ClusterResult]) -> str:
        """
        Create HTML legend for the map.
        
        Args:
            cluster_results: List of ClusterResult objects
            
        Returns:
            HTML string for legend
        """
        # Count sites by cluster
        cluster_counts = {}
        for result in cluster_results:
            cluster_counts[result.cluster_id] = cluster_counts.get(result.cluster_id, 0) + 1
        
        # Count special categories
        n_edge = sum(1 for r in cluster_results if r.is_cluster_edge)
        n_out_of_bounds = sum(1 for r in cluster_results if r.out_of_bounds)
        n_noise = cluster_counts.get(-1, 0)
        
        legend_html = f'''
        <div style="position: fixed; 
                    bottom: 50px; left: 50px; width: 250px; 
                    background-color: white; border:2px solid grey; z-index:9999; 
                    font-size:12px; padding: 10px">
            <h4 style="margin-top:0;">Legend</h4>
            <p><b>Total Sites:</b> {len(cluster_results)}</p>
            <p><b>Clusters:</b> {len(cluster_counts) - (1 if -1 in cluster_counts else 0)}</p>
            <p><b>Noise Points:</b> {n_noise}</p>
            <p><b>Edge Sites:</b> {n_edge}</p>
            <p style="color:red;"><b>Out of Bounds:</b> {n_out_of_bounds}</p>
            <hr>
            <p><i class="glyphicon glyphicon-circle" style="color:green;"></i> Interior Site</p>
            <p><i class="glyphicon glyphicon-record" style="color:orange;"></i> Edge Site</p>
            <p><i class="glyphicon glyphicon-exclamation-sign" style="color:red;"></i> Out of Bounds</p>
        </div>
        '''
        return legend_html
    
    def create_edge_score_heatmap(
        self,
        sites: List[Site],
        edge_scores: Dict[str, float],
        title: str = "Edge Score Heatmap"
    ) -> folium.Map:
        """
        Create heatmap showing edge scores.
        
        Args:
            sites: List of Site objects
            edge_scores: Dictionary mapping site_id -> edge_score (0-1)
            title: Map title
            
        Returns:
            Folium Map object
        """
        logger.info(f"Creating edge score heatmap for {len(sites)} sites")
        
        # Create base map
        m = folium.Map(
            location=[self.center_lat, self.center_lon],
            zoom_start=self.zoom_start,
            tiles='OpenStreetMap'
        )
        
        # Add title
        title_html = f'''
        <div style="position: fixed; 
                    top: 10px; left: 50px; width: 400px; height: 50px; 
                    background-color: white; border:2px solid grey; z-index:9999; 
                    font-size:16px; font-weight: bold; padding: 10px">
            {title}
        </div>
        '''
        m.get_root().html.add_child(folium.Element(title_html))
        
        # Prepare heatmap data
        heat_data = []
        for site in sites:
            score = edge_scores.get(site.site_id, 0.0)
            heat_data.append([site.latitude, site.longitude, score])
        
        # Add heatmap layer
        plugins.HeatMap(
            heat_data,
            min_opacity=0.2,
            max_val=1.0,
            radius=15,
            blur=20,
            gradient={0.0: 'green', 0.5: 'yellow', 1.0: 'red'}
        ).add_to(m)
        
        # Add markers for sites
        for site in sites:
            score = edge_scores.get(site.site_id, 0.0)
            
            popup_html = f"""
            <div style="width: 200px;">
                <h4>{site.site_name}</h4>
                <b>Site ID:</b> {site.site_id}<br>
                <b>Edge Score:</b> {score:.3f}<br>
                <b>Type:</b> {'Edge' if score > 0.5 else 'Interior'}
            </div>
            """
            
            folium.CircleMarker(
                location=[site.latitude, site.longitude],
                radius=5,
                popup=folium.Popup(popup_html, max_width=250),
                color='black',
                fill=True,
                fill_color='red' if score > 0.5 else 'green',
                fill_opacity=0.6,
                tooltip=f"{site.site_name}: {score:.2f}"
            ).add_to(m)
        
        logger.info("Edge score heatmap created successfully")
        return m
    
    def save_map(self, folium_map: folium.Map, output_path: str) -> None:
        """
        Save Folium map to HTML file.
        
        Args:
            folium_map: Folium Map object
            output_path: Path to save HTML file
        """
        folium_map.save(output_path)
        logger.info(f"Map saved to {output_path}")
    
    def export_cluster_geojson(
        self,
        sites: List[Site],
        cluster_results: List[ClusterResult],
        output_path: str
    ) -> None:
        """
        Export clustering results to GeoJSON format.
        
        Args:
            sites: List of Site objects
            cluster_results: List of ClusterResult objects
            output_path: Path to save GeoJSON file
        """
        logger.info(f"Exporting {len(sites)} sites to GeoJSON")
        
        # Create result lookup
        result_map = {r.site_id: r for r in cluster_results}
        
        # Build GeoJSON structure
        features = []
        for site in sites:
            result = result_map.get(site.site_id)
            
            if not result:
                continue
            
            feature = {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [site.longitude, site.latitude]
                },
                "properties": {
                    "site_id": site.site_id,
                    "site_name": site.site_name,
                    "cluster_id": result.cluster_id,
                    "is_cluster_edge": result.is_cluster_edge,
                    "out_of_bounds": result.out_of_bounds,
                    "cluster_size": result.cluster_size,
                    "cluster_density_sites_per_km2": result.cluster_density_sites_per_km2,
                    "cluster_avg_traffic_gb": result.cluster_avg_traffic_gb,
                    "cluster_avg_users": result.cluster_avg_users,
                    "dist_to_cluster_centroid_m": result.dist_to_cluster_centroid_m
                }
            }
            features.append(feature)
        
        geojson = {
            "type": "FeatureCollection",
            "features": features
        }
        
        # Write to file
        with open(output_path, 'w') as f:
            json.dump(geojson, f, indent=2)
        
        logger.info(f"GeoJSON exported to {output_path}")
