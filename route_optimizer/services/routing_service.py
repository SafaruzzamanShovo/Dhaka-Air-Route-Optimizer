import openrouteservice
from django.conf import settings
from typing import List, Dict, Optional, Tuple
import numpy as np
import logging

logger = logging.getLogger(__name__)


class RoutingService:
    """Service to handle routing using OpenRouteService"""
    
    def __init__(self):
        self.client = openrouteservice.Client(key=settings.ORS_API_KEY)
    
    def get_route(self, start_coords: Tuple[float, float], 
                  end_coords: Tuple[float, float], 
                  profile: str = 'driving-car') -> Optional[Dict]:
        """
        Get route between two coordinates.
        start_coords, end_coords: (longitude, latitude)
        """
        try:
            coords = [start_coords, end_coords]
            route = self.client.directions(
                coordinates=coords,
                profile=profile,
                format='geojson',
                instructions=True,
                elevation=False
            )
            
            return self._parse_route_data(route)
        except Exception as e:
            logger.error("Error getting route: %s", e)
            return None
    
    def get_alternative_routes(self, start_coords: Tuple[float, float],
                              end_coords: Tuple[float, float],
                              profile: str = 'driving-car') -> List[Dict]:
        """
        Get multiple alternative routes using OpenRouteService.
        Returns up to 3 different routes.
        """
        try:
            coords = [start_coords, end_coords]
            
            # Request with alternative routes parameter
            route = self.client.directions(
                coordinates=coords,
                profile=profile,
                format='geojson',
                instructions=True,
                elevation=False,
                alternative_routes={
                    'target_count': 2,  # Request 2 alternatives (total 3 routes)
                    'weight_factor': 1.4,  # How different routes should be
                    'share_factor': 0.6  # How much routes can overlap
                }
            )
            
            # OpenRouteService returns multiple routes in features array
            routes = []
            if 'features' in route:
                for feature in route['features']:
                    parsed = self._parse_single_feature(feature)
                    if parsed:
                        routes.append(parsed)
            
            return routes if routes else [self.get_route(start_coords, end_coords)]
            
        except Exception as e:
            logger.info("Alternative routes not available, using standard route: %s", e)
            # Fallback to standard route
            standard = self.get_route(start_coords, end_coords)
            return [standard] if standard else []
    
    def get_route_with_waypoints(self, coordinates: List[Tuple[float, float]], 
                                  profile: str = 'driving-car', 
                                  priority: str = 'balanced') -> Optional[Dict]:
        """
        Get route with strategic waypoints based on priority.
        """
        try:
            # For shortest, use direct route
            if priority == 'shortest':
                route = self.client.directions(
                    coordinates=[coordinates[0], coordinates[-1]],
                    profile=profile,
                    format='geojson',
                    instructions=True,
                    elevation=False
                )
                return self._parse_route_data(route)
            
            # For cleanest/pollutant routes, use waypoints with preference parameters
            elif priority in ['cleanest', 'pm25', 'pm10', 'co', 'o3', 'so2']:
                # Simplify waypoints - too many waypoints force same route
                selected_coords = self._select_strategic_waypoints(
                    coordinates, 
                    max_waypoints=4,  # Limit to 4 intermediate waypoints
                    priority=priority
                )
                
                route = self.client.directions(
                    coordinates=selected_coords,
                    profile=profile,
                    format='geojson',
                    instructions=True,
                    elevation=False,
                    options={
                        'avoid_features': []  # Can add 'highways' to avoid major roads
                    }
                )
                return self._parse_route_data(route)
            
            # For balanced
            else:
                selected_coords = self._select_strategic_waypoints(
                    coordinates, 
                    max_waypoints=3,
                    priority=priority
                )
                
                route = self.client.directions(
                    coordinates=selected_coords,
                    profile=profile,
                    format='geojson',
                    instructions=True,
                    elevation=False
                )
                return self._parse_route_data(route)
                
        except Exception as e:
            logger.warning("Error with waypoints: %s", e)
            # Fallback to direct route
            try:
                route = self.client.directions(
                    coordinates=[coordinates[0], coordinates[-1]],
                    profile=profile,
                    format='geojson',
                    instructions=True,
                    elevation=False
                )
                return self._parse_route_data(route)
            except Exception as fallback_error:
                logger.error("Fallback route also failed: %s", fallback_error)
                return None
    
    def _select_strategic_waypoints(self, coordinates: List[Tuple[float, float]],
                                   max_waypoints: int = 4,
                                   priority: str = 'balanced') -> List[Tuple[float, float]]:
        """
        Select most strategic waypoints to create different routes.
        """
        if len(coordinates) <= max_waypoints + 2:
            return coordinates
        
        # Always include start and end
        selected = [coordinates[0]]
        
        # For cleanest routes, prefer waypoints furthest from direct line
        if priority in ['cleanest', 'pm25', 'pm10', 'co', 'o3', 'so2']:
            # Calculate deviation from direct line for each waypoint
            start = np.array(coordinates[0])
            end = np.array(coordinates[-1])
            
            deviations = []
            for i in range(1, len(coordinates) - 1):
                point = np.array(coordinates[i])
                # Calculate perpendicular distance from line
                deviation = self._point_line_distance(point, start, end)
                deviations.append((i, deviation))
            
            # Sort by deviation (largest first) and select top waypoints
            deviations.sort(key=lambda x: x[1], reverse=True)
            selected_indices = sorted([idx for idx, _ in deviations[:max_waypoints]])
            
            for idx in selected_indices:
                selected.append(coordinates[idx])
        
        # For balanced, evenly distribute waypoints
        else:
            step = (len(coordinates) - 2) / (max_waypoints + 1)
            for i in range(1, max_waypoints + 1):
                idx = int(i * step)
                selected.append(coordinates[idx])
        
        # Add end point
        selected.append(coordinates[-1])
        
        return selected
    
    def _point_line_distance(self, point: np.ndarray, 
                            line_start: np.ndarray, 
                            line_end: np.ndarray) -> float:
        """Calculate perpendicular distance from point to line."""
        # Vector from line_start to line_end
        line_vec = line_end - line_start
        # Vector from line_start to point
        point_vec = point - line_start
        
        # Normalize line vector
        line_len = np.linalg.norm(line_vec)
        if line_len == 0:
            return np.linalg.norm(point_vec)
        
        line_unit = line_vec / line_len
        
        # Project point onto line
        projection_length = np.dot(point_vec, line_unit)
        projection = projection_length * line_unit
        
        # Distance is perpendicular component
        perpendicular = point_vec - projection
        return np.linalg.norm(perpendicular)
    
    def _parse_single_feature(self, feature: Dict) -> Optional[Dict]:
        """Parse a single route feature."""
        try:
            properties = feature['properties']
            geometry = feature['geometry']
            
            return {
                'distance': round(properties.get('summary', {}).get('distance', 0) / 1000, 2),
                'duration': round(properties.get('summary', {}).get('duration', 0) / 60, 2),
                'coordinates': geometry['coordinates'],
                'steps': properties.get('segments', [{}])[0].get('steps', []),
                'bbox': properties.get('bbox', []),
                'geometry': geometry
            }
        except Exception as e:
            logger.error("Error parsing feature: %s", e)
            return None
    
    def get_isochrones(self, location: Tuple[float, float], 
                       range_seconds: List[int] = [600, 1200, 1800]) -> Optional[Dict]:
        """Get isochrones (reachability areas) from a location."""
        try:
            isochrones = self.client.isochrones(
                locations=[location],
                profile='driving-car',
                range=range_seconds,
                range_type='time'
            )
            return isochrones
        except Exception as e:
            logger.error("Error getting isochrones: %s", e)
            return None
    
    def geocode_address(self, address: str) -> Optional[Tuple[float, float]]:
        """
        Convert address to coordinates using Pelias geocoding.
        Returns: (longitude, latitude) or None
        """
        try:
            result = self.client.pelias_search(text=address, focus_point=[90.4125, 23.8103])  # Dhaka focus
            if result and 'features' in result and len(result['features']) > 0:
                coords = result['features'][0]['geometry']['coordinates']
                return tuple(coords)  # (lng, lat)
            return None
        except Exception as e:
            logger.error("Error geocoding address: %s", e)
            return None
    
    def reverse_geocode(self, lng: float, lat: float) -> Optional[str]:
        """Convert coordinates to address."""
        try:
            result = self.client.pelias_reverse(point=(lng, lat))
            if result and 'features' in result and len(result['features']) > 0:
                return result['features'][0]['properties'].get('label', 'Unknown')
            return None
        except Exception as e:
            logger.error("Error reverse geocoding: %s", e)
            return None
    
    def _parse_route_data(self, route_geojson: Dict) -> Optional[Dict]:
        """Parse route GeoJSON data."""
        if not route_geojson or 'features' not in route_geojson:
            return None
        
        feature = route_geojson['features'][0]
        return self._parse_single_feature(feature)
    
    def sample_route_points(self, coordinates: List[List[float]], 
                           num_samples: int = 10) -> List[Tuple[float, float]]:
        """
        Sample points along a route for AQI checking.
        Returns: List of (lat, lng) tuples
        """
        if len(coordinates) <= num_samples:
            return [(coord[1], coord[0]) for coord in coordinates]
        
        indices = np.linspace(0, len(coordinates) - 1, num_samples, dtype=int)
        sampled = [coordinates[i] for i in indices]
        
        return [(coord[1], coord[0]) for coord in sampled]

    def get_route_via_waypoint(self, start_coords: Tuple[float, float],
                           waypoint_coords: Tuple[float, float],
                           end_coords: Tuple[float, float],
                           profile: str = 'driving-car') -> Optional[Dict]:
        """
        Get route through a single waypoint.
        All coordinates: (longitude, latitude)
        """
        try:
            coords = [start_coords, waypoint_coords, end_coords]
            
            route = self.client.directions(
                coordinates=coords,
                profile=profile,
                format='geojson',
                instructions=True,
                elevation=False,
                radiuses=[350, 350, 350]  # Allow 350m search radius for waypoints
            )
            
            return self._parse_route_data(route)
            
        except Exception as e:
            logger.warning("Waypoint routing failed: %s", e)
            return None

