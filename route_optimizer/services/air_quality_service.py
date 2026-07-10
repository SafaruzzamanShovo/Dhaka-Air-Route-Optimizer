import logging
import time
from typing import Dict, List, Optional

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class AirQualityService:
    """
    Service for retrieving air quality information from the
    World Air Quality Index (WAQI) API.
    """

    BASE_URL = "https://api.waqi.info"

    def __init__(self):
        self.api_key = settings.WAQI_API_KEY
        self.headers = {
            "User-Agent": "DhakaAQIRouteOptimizer/1.0"
        }

    def get_aqi_by_coordinates(self, lat: float, lng: float) -> Optional[Dict]:
        """
        Fetch AQI data using latitude and longitude.
        """
        url = f"{self.BASE_URL}/feed/geo:{lat};{lng}/"

        try:
            response = requests.get(
                url,
                params={"token": self.api_key},
                headers=self.headers,
                timeout=10,
            )

            response.raise_for_status()
            data = response.json()

            if data.get("status") == "ok":
                return self._parse_aqi_data(data["data"])

            logger.warning("WAQI returned status: %s", data.get("status"))
            return None

        except requests.RequestException as e:
            logger.exception("Failed to fetch AQI for (%s, %s): %s", lat, lng, e)
            return None

    def get_aqi_by_city(self, city_name: str) -> Optional[Dict]:
        """
        Fetch AQI data using a city name.
        Example:
            Dhaka
            Chittagong
            Delhi
        """
        url = f"{self.BASE_URL}/feed/{city_name}/"

        try:
            response = requests.get(
                url,
                params={"token": self.api_key},
                headers=self.headers,
                timeout=10,
            )

            response.raise_for_status()
            data = response.json()

            if data.get("status") == "ok":
                return self._parse_aqi_data(data["data"])

            logger.warning(
                "No AQI data found for city: %s (status=%s)",
                city_name,
                data.get("status"),
            )
            return None

        except requests.RequestException as e:
            logger.exception("Error fetching AQI for city '%s': %s", city_name, e)
            return None

    def get_multiple_aqi_for_route(
        self,
        coordinates: List[tuple]
    ) -> List[Dict]:
        """
        Fetch AQI for multiple coordinates along a route.
        """

        results = []

        for lat, lng in coordinates:
            data = self.get_aqi_by_coordinates(lat, lng)

            if data:
                results.append(data)

            # Prevent hitting WAQI rate limits
            time.sleep(0.2)

        return results

    def _parse_aqi_data(self, data: Dict) -> Dict:
        """
        Convert raw WAQI response into a cleaner structure.
        """

        iaqi = data.get("iaqi", {})
        city = data.get("city", {})
        geo = city.get("geo", [0.0, 0.0])

        lat = geo[0] if len(geo) > 0 else 0.0
        lng = geo[1] if len(geo) > 1 else 0.0

        # Validate coordinates
        if not (-90 <= lat <= 90):
            lat = 0.0

        if not (-180 <= lng <= 180):
            lng = 0.0

        return {
            "aqi": data.get("aqi", 0),

            "pm25": iaqi.get("pm25", {}).get("v", 0),
            "pm10": iaqi.get("pm10", {}).get("v", 0),
            "no2": iaqi.get("no2", {}).get("v", 0),
            "co": iaqi.get("co", {}).get("v", 0),
            "o3": iaqi.get("o3", {}).get("v", 0),

            "location": {
                "name": city.get("name", "Unknown"),
                "lat": lat,
                "lng": lng,
            },

            "time": data.get("time", {}).get("s", ""),
        }

    def calculate_weighted_aqi(self, aqi_data: Dict) -> float:
        """
        Calculate a weighted AQI score using pollutant concentrations.
        Falls back to the overall AQI if pollutant data is unavailable.
        """

        weights = {
            "pm25": 0.35,
            "pm10": 0.25,
            "no2": 0.20,
            "co": 0.10,
            "o3": 0.10,
        }

        weighted_sum = 0.0
        total_weight = 0.0

        for pollutant, weight in weights.items():
            value = aqi_data.get(pollutant, 0)

            if value and value > 0:
                weighted_sum += value * weight
                total_weight += weight

        if total_weight > 0:
            return round(weighted_sum / total_weight, 2)

        return float(aqi_data.get("aqi", 0))
