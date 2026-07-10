import numpy as np
from typing import Dict, List, Tuple, Optional
import logging

from .air_quality_service import AirQualityService
from .routing_service import RoutingService

logger = logging.getLogger(__name__)


class RouteOptimizer:
    """
    Route finder that evaluates multiple routing strategies (direct, detour-based)
    and selects the best route based on distance and air quality priority.
    """
    
    def __init__(self):
        self.aqi_service = AirQualityService()
        self.routing_service = RoutingService()
    
    def find_optimal_route(self, start_lat: float, start_lng: float,
                      end_lat: float, end_lng: float,
                      priority: str = 'balanced',
                      pollutant_type: str = None,
                      num_waypoints: int = 10) -> Dict:
        """
        Find optimal route based on priority using different routing strategies.
        
        Args:
            start_lat: Source latitude
            start_lng: Source longitude
            end_lat: Destination latitude
            end_lng: Destination longitude
            priority: One of 'shortest', 'balanced', 'cleanest', 'pm25', 'pm10', 'co', 'o3', 'so2'
            pollutant_type: Specific pollutant to minimize (optional)
            num_waypoints: Number of waypoints for AQI sampling
            
        Returns:
            Dict with route data including geometry, AQI, distance, duration
        """
        
        logger.info("Finding %s route...", priority.upper())
        
        # Get base route
        base_route = self.routing_service.get_route(
            (start_lng, start_lat),
            (end_lng, end_lat)
        )
        
        if not base_route:
            logger.error("Could not get base route")
            return None
        
        # For shortest priority - return direct route
        if priority == 'shortest':
            logger.info("Using DIRECT shortest path")
            sampled_points = self.routing_service.sample_route_points(
                base_route['coordinates'],
                num_samples=8
            )
            aqi_data_list = self.aqi_service.get_multiple_aqi_for_route(sampled_points)
            avg_aqi = np.mean([data['aqi'] for data in aqi_data_list if data.get('aqi', 0) > 0]) if aqi_data_list else 100
            
            return {
                'distance': base_route['distance'],
                'duration': base_route['duration'],
                'average_aqi': float(avg_aqi),
                'aqi_data': aqi_data_list,
                'geometry': base_route['geometry'],
                'coordinates': base_route['coordinates'],
                'sampled_points': sampled_points,
                'optimal_path_indices': list(range(len(sampled_points))),
                'dijkstra_cost': base_route['distance'],
                'priority': priority
            }
        
        # For other priorities, calculate different detours
        logger.info("Generating alternative route for %s...", priority)
        
        mid_lat = (start_lat + end_lat) / 2
        mid_lng = (start_lng + end_lng) / 2
        bearing = self._calculate_bearing(start_lat, start_lng, end_lat, end_lng)
        
        # Different detour parameters for each priority to ensure distinct routes
        detour_configs = {
            'balanced': {
                'distance': min(1.0, base_route['distance'] * 0.15),
                'angle': 50,
                'side': 'right',
                'description': 'Moderate right detour'
            },
            'cleanest': {
                'distance': min(3.0, base_route['distance'] * 0.35),
                'angle': 80,
                'side': 'left',
                'description': 'Large left detour for clean air'
            },
            'pm25': {
                'distance': min(2.5, base_route['distance'] * 0.30),
                'angle': 70,
                'side': 'right',
                'description': 'Right detour avoiding PM2.5'
            },
            'pm10': {
                'distance': min(2.8, base_route['distance'] * 0.32),
                'angle': 75,
                'side': 'left',
                'description': 'Left detour avoiding PM10'
            },
            'co': {
                'distance': min(2.2, base_route['distance'] * 0.28),
                'angle': 65,
                'side': 'right',
                'description': 'Right detour avoiding CO'
            },
            'o3': {
                'distance': min(2.6, base_route['distance'] * 0.31),
                'angle': 72,
                'side': 'left',
                'description': 'Left detour avoiding O3'
            },
            'so2': {
                'distance': min(2.4, base_route['distance'] * 0.29),
                'angle': 68,
                'side': 'right',
                'description': 'Right detour avoiding SO2'
            }
        }
        
        config = detour_configs.get(priority, detour_configs['balanced'])
        
        logger.info("%s: %.1fkm at %d°", config['description'], config['distance'], config['angle'])
        
        # Calculate detour angle based on side
        if config['side'] == 'right':
            detour_bearing = (bearing + config['angle']) % 360
        else:
            detour_bearing = (bearing - config['angle']) % 360
        
        # Calculate waypoint
        waypoint_lat, waypoint_lng = self._calculate_destination_point(
            mid_lat, mid_lng,
            config['distance'],
            detour_bearing
        )
        
        logger.debug("Trying waypoint at (%.4f, %.4f)...", waypoint_lat, waypoint_lng)
        
        # Try the detour route
        alternative_route = None
        try:
            route = self.routing_service.get_route_via_waypoint(
                (start_lng, start_lat),
                (waypoint_lng, waypoint_lat),
                (end_lng, end_lat)
            )
            if route and route['distance'] > base_route['distance'] * 1.05:  # At least 5% longer
                logger.info("Detour successful: %.2fkm vs %.2fkm direct",
                           route['distance'], base_route['distance'])
                alternative_route = route
            else:
                logger.info("Detour too similar, using direct route")
        except Exception as e:
            logger.warning("Detour failed: %s", e)
        
        # Use alternative route if found, otherwise use base route
        final_route = alternative_route if alternative_route else base_route
        
        # Sample and get AQI data
        sampled_points = self.routing_service.sample_route_points(
            final_route['coordinates'],
            num_samples=12
        )
        
        aqi_data_list = self.aqi_service.get_multiple_aqi_for_route(sampled_points)
        avg_aqi = np.mean([data['aqi'] for data in aqi_data_list if data.get('aqi', 0) > 0]) if aqi_data_list else 100
        
        logger.info("Route AQI: %.1f", avg_aqi)
        
        return {
            'distance': final_route['distance'],
            'duration': final_route['duration'],
            'average_aqi': float(avg_aqi),
            'aqi_data': aqi_data_list,
            'geometry': final_route['geometry'],
            'coordinates': final_route['coordinates'],
            'sampled_points': sampled_points,
            'optimal_path_indices': list(range(len(sampled_points))),
            'dijkstra_cost': final_route['distance'],
            'priority': priority
        }

    def _calculate_bearing(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate bearing between two points in degrees."""
        lat1_rad = np.radians(lat1)
        lat2_rad = np.radians(lat2)
        dlon = np.radians(lon2 - lon1)
        
        x = np.sin(dlon) * np.cos(lat2_rad)
        y = np.cos(lat1_rad) * np.sin(lat2_rad) - np.sin(lat1_rad) * np.cos(lat2_rad) * np.cos(dlon)
        
        bearing = np.degrees(np.arctan2(x, y))
        return (bearing + 360) % 360
    
    def _calculate_destination_point(self, lat: float, lon: float, 
                                     distance_km: float, bearing: float) -> Tuple[float, float]:
        """
        Calculate destination point given start point, distance (in km), and bearing.
        Uses the Haversine formula.
        """
        R = 6371  # Earth's radius in kilometers
        
        lat_rad = np.radians(lat)
        lon_rad = np.radians(lon)
        bearing_rad = np.radians(bearing)
        
        new_lat_rad = np.arcsin(
            np.sin(lat_rad) * np.cos(distance_km / R) +
            np.cos(lat_rad) * np.sin(distance_km / R) * np.cos(bearing_rad)
        )
        
        new_lon_rad = lon_rad + np.arctan2(
            np.sin(bearing_rad) * np.sin(distance_km / R) * np.cos(lat_rad),
            np.cos(distance_km / R) - np.sin(lat_rad) * np.sin(new_lat_rad)
        )
        
        new_lat = np.degrees(new_lat_rad)
        new_lon = np.degrees(new_lon_rad)
        
        return new_lat, new_lon
    
    def compare_routes(self, start_lat: float, start_lng: float,
                      end_lat: float, end_lng: float) -> Dict:
        """
        Compare routes with different priorities.
        
        Returns a dict keyed by priority name with route data for each.
        """
        priorities = ['shortest', 'balanced', 'cleanest']
        results = {}
        
        for priority in priorities:
            route = self.find_optimal_route(
                start_lat, start_lng, end_lat, end_lng,
                priority=priority
            )
            results[priority] = route
        
        return results


# Backward-compatible alias for imports that still use the old name
DijkstraOptimizer = RouteOptimizer

