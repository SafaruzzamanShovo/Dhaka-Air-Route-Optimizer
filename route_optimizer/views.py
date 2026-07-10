from django.shortcuts import render
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
import json
import traceback
import logging

from .services.dijkstra_optimizer import RouteOptimizer
from .services.routing_service import RoutingService
from .services.air_quality_service import AirQualityService
from .models import RouteHistory

# Set up logging
logger = logging.getLogger(__name__)


def index(request):
    """Main page"""
    return render(request, 'route_optimizer/index.html')


@require_http_methods(["POST"])
def find_route(request):
    """
    API endpoint to find optimal route.
    """
    try:
        # Parse request data
        data = json.loads(request.body)
        
        # Extract parameters
        source_address = data.get('source_address')
        dest_address = data.get('destination_address')
        source_lat = data.get('source_lat')
        source_lng = data.get('source_lng')
        dest_lat = data.get('dest_lat')
        dest_lng = data.get('dest_lng')
        priority = data.get('priority', 'balanced')
        pollutant_type = data.get('pollutant_type')
        
        logger.info("Route request: %s → %s (priority=%s)", source_address, dest_address, priority)
        
        # Initialize services
        routing_service = RoutingService()
        optimizer = RouteOptimizer()
        
        # Geocode addresses if coordinates not provided
        if not (source_lat and source_lng) and source_address:
            logger.info("Geocoding source: %s", source_address)
            source_coords = routing_service.geocode_address(f"{source_address}, Dhaka")
            if source_coords:
                source_lng, source_lat = source_coords  # Returns (lng, lat)
                logger.info("Source coords: (%.4f, %.4f)", source_lat, source_lng)
            else:
                logger.warning("Failed to geocode source: %s", source_address)
                return JsonResponse({
                    'success': False,
                    'error': f'Could not geocode source address: {source_address}'
                }, status=400)
        
        if not (dest_lat and dest_lng) and dest_address:
            logger.info("Geocoding destination: %s", dest_address)
            dest_coords = routing_service.geocode_address(f"{dest_address}, Dhaka")
            if dest_coords:
                dest_lng, dest_lat = dest_coords  # Returns (lng, lat)
                logger.info("Destination coords: (%.4f, %.4f)", dest_lat, dest_lng)
            else:
                logger.warning("Failed to geocode destination: %s", dest_address)
                return JsonResponse({
                    'success': False,
                    'error': f'Could not geocode destination address: {dest_address}'
                }, status=400)
        
        # Validate coordinates
        if not all([source_lat, source_lng, dest_lat, dest_lng]):
            logger.warning("Invalid coordinates: source=(%s, %s) dest=(%s, %s)",
                          source_lat, source_lng, dest_lat, dest_lng)
            return JsonResponse({
                'success': False,
                'error': 'Invalid coordinates or addresses. Please provide valid locations.'
            }, status=400)
        
        # Convert to float
        source_lat = float(source_lat)
        source_lng = float(source_lng)
        dest_lat = float(dest_lat)
        dest_lng = float(dest_lng)
        
        logger.info("Finding route: (%.4f, %.4f) → (%.4f, %.4f) [%s]",
                    source_lat, source_lng, dest_lat, dest_lng, priority)
        
        # Find optimal route
        route_result = optimizer.find_optimal_route(
            source_lat, source_lng,
            dest_lat, dest_lng,
            priority=priority,
            pollutant_type=pollutant_type
        )
        
        if not route_result:
            logger.warning("Could not find route")
            return JsonResponse({
                'success': False,
                'error': 'Could not find route. Please try different locations.'
            }, status=400)
        
        logger.info("Route found: %.2fkm, %dmin, AQI %.1f",
                    route_result['distance'], route_result['duration'], route_result['average_aqi'])
        
        # Reverse geocode for names (with fallback)
        try:
            source_name = routing_service.reverse_geocode(source_lng, source_lat) or source_address or "Source"
            dest_name = routing_service.reverse_geocode(dest_lng, dest_lat) or dest_address or "Destination"
        except Exception as e:
            logger.warning("Could not reverse geocode: %s", e)
            source_name = source_address or "Source"
            dest_name = dest_address or "Destination"
        
        # Save to history
        try:
            RouteHistory.objects.create(
                source_name=source_name,
                source_lat=source_lat,
                source_lng=source_lng,
                destination_name=dest_name,
                destination_lat=dest_lat,
                destination_lng=dest_lng,
                priority=priority,
                total_distance=route_result['distance'],
                estimated_time=route_result['duration'],
                average_aqi=route_result['average_aqi'],
                route_geometry=route_result['geometry']
            )
            logger.debug("Route saved to history")
        except Exception as e:
            logger.warning("Could not save to history: %s", e)
            # Don't fail the request if history save fails
        
        # Return response
        return JsonResponse({
            'success': True,
            'route': {
                'source': {
                    'lat': source_lat, 
                    'lng': source_lng, 
                    'name': source_name
                },
                'destination': {
                    'lat': dest_lat, 
                    'lng': dest_lng, 
                    'name': dest_name
                },
                'distance': round(route_result['distance'], 2),
                'duration': round(route_result['duration'], 2),
                'average_aqi': round(route_result['average_aqi'], 2),
                'geometry': route_result['geometry'],
                'coordinates': route_result['coordinates'],
                'aqi_data': route_result['aqi_data'],
                'priority': priority
            }
        })
        
    except json.JSONDecodeError as e:
        logger.error("JSON decode error: %s", e)
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON in request body'
        }, status=400)
        
    except ValueError as e:
        logger.error("Value error: %s", e, exc_info=True)
        return JsonResponse({
            'success': False,
            'error': f'Invalid data format: {str(e)}'
        }, status=400)
        
    except Exception as e:
        logger.error("Unexpected error in find_route: %s", e, exc_info=True)
        
        error_response = {
            'success': False,
            'error': str(e),
            'type': type(e).__name__,
        }
        
        # Only include traceback in debug mode
        if settings.DEBUG:
            error_response['traceback'] = traceback.format_exc().split('\n')
        
        return JsonResponse(error_response, status=500)


@require_http_methods(["POST"])
def compare_routes(request):
    """
    API endpoint to compare routes with different priorities.
    """
    try:
        data = json.loads(request.body)
        
        source_lat = float(data.get('source_lat'))
        source_lng = float(data.get('source_lng'))
        dest_lat = float(data.get('dest_lat'))
        dest_lng = float(data.get('dest_lng'))
        
        logger.info("Comparing routes: (%.4f, %.4f) → (%.4f, %.4f)",
                    source_lat, source_lng, dest_lat, dest_lng)
        
        optimizer = RouteOptimizer()
        comparison = optimizer.compare_routes(
            source_lat, source_lng, dest_lat, dest_lng
        )
        
        logger.info("Route comparison complete")
        
        return JsonResponse({
            'success': True,
            'comparison': comparison
        })
        
    except Exception as e:
        logger.error("Error comparing routes: %s", e, exc_info=True)
        
        error_response = {
            'success': False,
            'error': str(e),
        }
        
        if settings.DEBUG:
            error_response['traceback'] = traceback.format_exc().split('\n')
        
        return JsonResponse(error_response, status=500)


@require_http_methods(["GET"])
def get_history(request):
    """
    Get route history.
    """
    try:
        history = RouteHistory.objects.all().order_by('-created_at')[:20]
        
        data = [{
            'id': h.id,
            'source': h.source_name,
            'destination': h.destination_name,
            'distance': h.total_distance,
            'duration': h.estimated_time,
            'average_aqi': h.average_aqi,
            'priority': h.priority,
            'created_at': h.created_at.isoformat()
        } for h in history]
        
        return JsonResponse({'success': True, 'history': data})
        
    except Exception as e:
        logger.error("Error fetching history: %s", e)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@require_http_methods(["POST"])
def get_aqi(request):
    """
    Get AQI for specific location.
    """
    try:
        data = json.loads(request.body)
        lat = float(data.get('lat'))
        lng = float(data.get('lng'))
        
        logger.info("Fetching AQI for (%.4f, %.4f)", lat, lng)
        
        aqi_service = AirQualityService()
        aqi_data = aqi_service.get_aqi_by_coordinates(lat, lng)
        
        if aqi_data:
            logger.info("AQI: %s", aqi_data.get('aqi', 'N/A'))
            return JsonResponse({
                'success': True,
                'aqi_data': aqi_data
            })
        else:
            logger.warning("Could not fetch AQI data for (%.4f, %.4f)", lat, lng)
            return JsonResponse({
                'success': False,
                'error': 'Could not fetch AQI data for this location'
            }, status=400)
            
    except Exception as e:
        logger.error("Error fetching AQI: %s", e, exc_info=True)
        
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

