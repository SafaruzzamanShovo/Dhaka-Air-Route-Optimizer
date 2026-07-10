// ============================================================================
// CSRF Token Helper
// ============================================================================

/**
 * Get CSRF token from Django cookie for secure POST requests.
 */
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

const csrftoken = getCookie('csrftoken');

// ============================================================================
// Map Initialization
// ============================================================================

// Initialize map centered on Dhaka
let map = L.map('map').setView([23.8103, 90.4125], 11);

// Add OpenStreetMap tiles
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© OpenStreetMap contributors',
    maxZoom: 19
}).addTo(map);

// Store markers and layers
let sourceMarker = null;
let destMarker = null;
let routeLayer = null;
let aqiMarkers = [];
let currentRouteData = null;

// Comparison mode variables
let comparisonMode = false;
let comparisonRoutes = [];
let comparisonLayers = [];

// Priority colors for comparison
const priorityColors = {
    'shortest': '#00e400',      // Green - fastest
    'balanced': '#ffff00',       // Yellow - balanced
    'cleanest': '#00b4d8',       // Blue - cleanest air
    'pm25': '#ff7e00',           // Orange - PM2.5
    'pm10': '#ff0000',           // Red - PM10
    'co': '#8f3f97',             // Purple - CO
    'o3': '#06d6a0',             // Teal - O3
    'so2': '#7e0023'             // Dark red - SO2
};

// ============================================================================
// AQI Helpers
// ============================================================================

function getAQIColor(aqi) {
    if (aqi <= 50) return '#00e400';
    if (aqi <= 100) return '#ffff00';
    if (aqi <= 150) return '#ff7e00';
    if (aqi <= 200) return '#ff0000';
    if (aqi <= 300) return '#8f3f97';
    return '#7e0023';
}

function getAQICategory(aqi) {
    if (aqi <= 50) return 'Good';
    if (aqi <= 100) return 'Moderate';
    if (aqi <= 150) return 'Unhealthy for Sensitive Groups';
    if (aqi <= 200) return 'Unhealthy';
    if (aqi <= 300) return 'Very Unhealthy';
    return 'Hazardous';
}

function getAQICategoryClass(aqi) {
    if (aqi <= 50) return 'status-good';
    if (aqi <= 100) return 'status-moderate';
    if (aqi <= 150) return 'status-unhealthy-sensitive';
    if (aqi <= 200) return 'status-unhealthy';
    if (aqi <= 300) return 'status-very-unhealthy';
    return 'status-hazardous';
}

// ============================================================================
// Loading Overlay
// ============================================================================

function showLoading() {
    document.getElementById('loadingOverlay').style.display = 'flex';
}

function hideLoading() {
    document.getElementById('loadingOverlay').style.display = 'none';
}

// ============================================================================
// Map Controls
// ============================================================================

function clearMap() {
    if (routeLayer) {
        map.removeLayer(routeLayer);
        routeLayer = null;
    }
    aqiMarkers.forEach(marker => map.removeLayer(marker));
    aqiMarkers = [];
}

function clearComparison() {
    comparisonLayers.forEach(layer => map.removeLayer(layer));
    comparisonLayers = [];
    comparisonRoutes = [];
    comparisonMode = false;
    document.getElementById('comparisonPanel').style.display = 'none';
    document.getElementById('routeInfo').style.display = 'none';
    document.getElementById('pollutantDetails').style.display = 'none';
    document.getElementById('waypointDetails').style.display = 'none';
}

function flyToLocation(lat, lng, zoom = 15) {
    map.flyTo([lat, lng], zoom, {
        animate: true,
        duration: 1.5,
        easeLinearity: 0.25
    });
}

function highlightWaypoint(index) {
    document.querySelectorAll('.waypoint-item').forEach(item => {
        item.classList.remove('waypoint-active');
    });
    
    const selectedWaypoint = document.querySelector(`[data-waypoint-index="${index}"]`);
    if (selectedWaypoint) {
        selectedWaypoint.classList.add('waypoint-active');
        
        if (aqiMarkers[index]) {
            aqiMarkers[index].openPopup();
        }
    }
}

// ============================================================================
// Pollutant Details
// ============================================================================

function updatePollutantDetails(aqiData) {
    const pollutantList = document.getElementById('pollutantList');
    
    if (!aqiData || aqiData.length === 0) {
        document.getElementById('pollutantDetails').style.display = 'none';
        return;
    }
    
    const avgPollutants = {
        pm25: 0,
        pm10: 0,
        no2: 0,
        co: 0,
        o3: 0
    };
    
    let count = 0;
    aqiData.forEach(data => {
        if (data) {
            avgPollutants.pm25 += data.pm25 || 0;
            avgPollutants.pm10 += data.pm10 || 0;
            avgPollutants.no2 += data.no2 || 0;
            avgPollutants.co += data.co || 0;
            avgPollutants.o3 += data.o3 || 0;
            count++;
        }
    });
    
    if (count > 0) {
        Object.keys(avgPollutants).forEach(key => {
            avgPollutants[key] = Math.round(avgPollutants[key] / count);
        });
    }
    
    pollutantList.innerHTML = `
        <div class="pollutant-item">
            <span class="pollutant-name">
                <span class="pollutant-icon">🌫️</span>
                PM2.5
            </span>
            <span class="pollutant-value" style="background: ${getAQIColor(avgPollutants.pm25 * 2)}; color: ${avgPollutants.pm25 > 75 ? '#fff' : '#000'};">
                ${avgPollutants.pm25} µg/m³
            </span>
        </div>
        <div class="pollutant-item">
            <span class="pollutant-name">
                <span class="pollutant-icon">💨</span>
                PM10
            </span>
            <span class="pollutant-value" style="background: ${getAQIColor(avgPollutants.pm10)}; color: ${avgPollutants.pm10 > 100 ? '#fff' : '#000'};">
                ${avgPollutants.pm10} µg/m³
            </span>
        </div>
        <div class="pollutant-item">
            <span class="pollutant-name">
                <span class="pollutant-icon">🏭</span>
                NO₂
            </span>
            <span class="pollutant-value" style="background: ${getAQIColor(avgPollutants.no2 * 2)}; color: ${avgPollutants.no2 > 60 ? '#fff' : '#000'};">
                ${avgPollutants.no2} µg/m³
            </span>
        </div>
        <div class="pollutant-item">
            <span class="pollutant-name">
                <span class="pollutant-icon">🚗</span>
                CO
            </span>
            <span class="pollutant-value" style="background: ${getAQIColor(avgPollutants.co * 10)}; color: ${avgPollutants.co > 15 ? '#fff' : '#000'};">
                ${avgPollutants.co} mg/m³
            </span>
        </div>
        <div class="pollutant-item">
            <span class="pollutant-name">
                <span class="pollutant-icon">☀️</span>
                O₃
            </span>
            <span class="pollutant-value" style="background: ${getAQIColor(avgPollutants.o3)}; color: ${avgPollutants.o3 > 75 ? '#fff' : '#000'};">
                ${avgPollutants.o3} µg/m³
            </span>
        </div>
    `;
    
    document.getElementById('pollutantDetails').style.display = 'block';
}

// ============================================================================
// Waypoint List (with delegated event handling to prevent listener accumulation)
// ============================================================================

// Set up waypoint event delegation once
const waypointListEl = document.getElementById('waypointList');

waypointListEl.addEventListener('click', function(e) {
    const waypointItem = e.target.closest('.waypoint-item');
    if (waypointItem) {
        const index = parseInt(waypointItem.getAttribute('data-waypoint-index'));
        const lat = parseFloat(waypointItem.getAttribute('data-lat'));
        const lng = parseFloat(waypointItem.getAttribute('data-lng'));
        
        flyToLocation(lat, lng, 15);
        highlightWaypoint(index);
        
        waypointItem.style.transform = 'scale(0.98)';
        setTimeout(() => {
            waypointItem.style.transform = 'scale(1)';
        }, 150);
    }
});

waypointListEl.addEventListener('mouseover', function(e) {
    const waypointItem = e.target.closest('.waypoint-item');
    if (waypointItem) {
        waypointItem.style.backgroundColor = 'rgba(53, 122, 180, 0.1)';
        waypointItem.style.transform = 'translateX(5px)';
    }
});

waypointListEl.addEventListener('mouseout', function(e) {
    const waypointItem = e.target.closest('.waypoint-item');
    if (waypointItem) {
        if (!waypointItem.classList.contains('waypoint-active')) {
            waypointItem.style.backgroundColor = '';
        }
        waypointItem.style.transform = 'translateX(0)';
    }
});

function updateWaypointList(aqiData) {
    if (!aqiData || aqiData.length === 0) {
        document.getElementById('waypointDetails').style.display = 'none';
        return;
    }
    
    let html = '';
    aqiData.forEach((data, index) => {
        if (data && data.location) {
            const aqi = data.aqi || 0;
            const category = getAQICategory(aqi);
            const color = getAQIColor(aqi);
            
            html += `
                <div class="waypoint-item" 
                     data-waypoint-index="${index}"
                     data-lat="${data.location.lat}"
                     data-lng="${data.location.lng}"
                     style="border-left-color: ${color}; cursor: pointer;">
                    <div class="waypoint-number">Checkpoint ${index + 1}</div>
                    <div class="waypoint-aqi">
                        AQI: <strong>${Math.round(aqi)}</strong> (${category})
                    </div>
                    <div class="waypoint-location">
                        📍 ${data.location.name || 'Unknown Location'}
                    </div>
                    <div class="waypoint-hint">
                        👆 Click to view on map
                    </div>
                </div>
            `;
        }
    });
    
    waypointListEl.innerHTML = html;
    document.getElementById('waypointDetails').style.display = 'block';
}

// ============================================================================
// Route Display
// ============================================================================

function displayRoute(routeData) {
    clearMap();
    clearComparison();
    
    const { route } = routeData;
    currentRouteData = route;
    
    if (sourceMarker) map.removeLayer(sourceMarker);
    sourceMarker = L.marker([route.source.lat, route.source.lng], {
        icon: L.icon({
            iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-green.png',
            shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-shadow.png',
            iconSize: [25, 41],
            iconAnchor: [12, 41],
            popupAnchor: [1, -34],
            shadowSize: [41, 41]
        })
    }).addTo(map);
    sourceMarker.bindPopup(`<b>Source:</b><br>${route.source.name}`);
    
    if (destMarker) map.removeLayer(destMarker);
    destMarker = L.marker([route.destination.lat, route.destination.lng], {
        icon: L.icon({
            iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-red.png',
            shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-shadow.png',
            iconSize: [25, 41],
            iconAnchor: [12, 41],
            popupAnchor: [1, -34],
            shadowSize: [41, 41]
        })
    }).addTo(map);
    destMarker.bindPopup(`<b>Destination:</b><br>${route.destination.name}`);
    
    const coordinates = route.coordinates.map(coord => [coord[1], coord[0]]);
    routeLayer = L.polyline(coordinates, {
        color: getAQIColor(route.average_aqi),
        weight: 6,
        opacity: 0.8
    }).addTo(map);
    
    if (route.aqi_data && route.aqi_data.length > 0) {
        route.aqi_data.forEach((aqiPoint, index) => {
            if (aqiPoint && aqiPoint.location) {
                const marker = L.circleMarker(
                    [aqiPoint.location.lat, aqiPoint.location.lng],
                    {
                        radius: 10,
                        fillColor: getAQIColor(aqiPoint.aqi),
                        color: '#fff',
                        weight: 2,
                        opacity: 1,
                        fillOpacity: 0.9
                    }
                ).addTo(map);
                
                marker.bindPopup(`
                    <div style="font-family: Inter, sans-serif; min-width: 200px;">
                        <h4 style="margin: 0 0 10px 0; color: #224F76;">Checkpoint ${index + 1}</h4>
                        <div style="margin: 6px 0;">
                            <strong>AQI:</strong> ${Math.round(aqiPoint.aqi)} 
                            <span style="background: ${getAQIColor(aqiPoint.aqi)}; padding: 2px 6px; border-radius: 4px; font-size: 0.85em; color: ${aqiPoint.aqi > 150 ? '#fff' : '#000'};">
                                ${getAQICategory(aqiPoint.aqi)}
                            </span>
                        </div>
                        <hr style="margin: 8px 0; border: none; border-top: 1px solid #e0e0e0;">
                        <div style="margin: 4px 0;"><strong>PM2.5:</strong> ${aqiPoint.pm25 || 'N/A'} µg/m³</div>
                        <div style="margin: 4px 0;"><strong>PM10:</strong> ${aqiPoint.pm10 || 'N/A'} µg/m³</div>
                        <div style="margin: 4px 0;"><strong>NO₂:</strong> ${aqiPoint.no2 || 'N/A'} µg/m³</div>
                        <div style="margin: 4px 0;"><strong>CO:</strong> ${aqiPoint.co || 'N/A'} mg/m³</div>
                        <div style="margin: 4px 0;"><strong>O₃:</strong> ${aqiPoint.o3 || 'N/A'} µg/m³</div>
                    </div>
                `);
                
                marker.on('click', function() {
                    highlightWaypoint(index);
                    const waypointElement = document.querySelector(`[data-waypoint-index="${index}"]`);
                    if (waypointElement) {
                        waypointElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    }
                });
                
                aqiMarkers.push(marker);
            }
        });
    }
    
    map.fitBounds(routeLayer.getBounds(), { padding: [50, 50] });
    
    document.getElementById('routeInfo').style.display = 'block';
    document.getElementById('routePriority').textContent = route.priority.charAt(0).toUpperCase() + route.priority.slice(1);
    document.getElementById('distance').textContent = `${route.distance} km`;
    document.getElementById('duration').textContent = `${Math.round(route.duration)} minutes`;
    
    const aqiBadge = document.getElementById('avgAqi');
    aqiBadge.textContent = `${Math.round(route.average_aqi)}`;
    aqiBadge.className = 'value aqi-badge ' + getAQICategoryClass(route.average_aqi);
    
    document.getElementById('aqiStatus').textContent = getAQICategory(route.average_aqi);
    
    updatePollutantDetails(route.aqi_data);
    updateWaypointList(route.aqi_data);
}

// ============================================================================
// Comparison Display
// ============================================================================

function displayComparisonRoutes(routes) {
    clearMap();
    clearComparison();
    comparisonMode = true;
    comparisonRoutes = routes;
    
    let bounds = null;
    
    const firstRoute = routes[0];
    if (sourceMarker) map.removeLayer(sourceMarker);
    if (destMarker) map.removeLayer(destMarker);
    
    sourceMarker = L.marker([firstRoute.source.lat, firstRoute.source.lng], {
        icon: L.icon({
            iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-green.png',
            shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-shadow.png',
            iconSize: [25, 41],
            iconAnchor: [12, 41],
            popupAnchor: [1, -34],
            shadowSize: [41, 41]
        })
    }).addTo(map);
    sourceMarker.bindPopup(`<b>Source:</b><br>${firstRoute.source.name}`);
    
    destMarker = L.marker([firstRoute.destination.lat, firstRoute.destination.lng], {
        icon: L.icon({
            iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-red.png',
            shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-shadow.png',
            iconSize: [25, 41],
            iconAnchor: [12, 41],
            popupAnchor: [1, -34],
            shadowSize: [41, 41]
        })
    }).addTo(map);
    destMarker.bindPopup(`<b>Destination:</b><br>${firstRoute.destination.name}`);
    
    // Draw each route with different color
    routes.forEach(route => {
        const coordinates = route.coordinates.map(coord => [coord[1], coord[0]]);
        const color = priorityColors[route.priority] || '#999999';
        
        const routePolyline = L.polyline(coordinates, {
            color: color,
            weight: 5,
            opacity: 0.7
        }).addTo(map);
        
        routePolyline.bindPopup(`
            <div style="font-family: Inter, sans-serif;">
                <h4 style="margin: 0 0 10px 0; color: ${color};">
                    ${route.priority.toUpperCase()} Route
                </h4>
                <div><strong>Distance:</strong> ${route.distance} km</div>
                <div><strong>Duration:</strong> ${Math.round(route.duration)} min</div>
                <div><strong>Avg AQI:</strong> ${Math.round(route.average_aqi)}</div>
            </div>
        `);
        
        comparisonLayers.push(routePolyline);
        
        if (!bounds) {
            bounds = routePolyline.getBounds();
        } else {
            bounds.extend(routePolyline.getBounds());
        }
    });
    
    if (bounds) {
        map.fitBounds(bounds, { padding: [50, 50] });
    }
    
    displayComparisonPanel(routes);
}

function displayComparisonPanel(routes) {
    const panel = document.getElementById('comparisonPanel');
    const list = document.getElementById('comparisonList');
    
    let html = '';
    
    routes.forEach(route => {
        const color = priorityColors[route.priority] || '#999999';
        
        html += `
            <div class="comparison-item" style="border-left: 4px solid ${color};">
                <div class="comparison-header">
                    <span class="comparison-priority" style="color: ${color};">
                        ● ${route.priority.toUpperCase()}
                    </span>
                </div>
                <div class="comparison-stats">
                    <div class="comparison-stat">
                        <span class="stat-label">📏 Distance</span>
                        <span class="stat-value">${route.distance} km</span>
                    </div>
                    <div class="comparison-stat">
                        <span class="stat-label">⏱️ Duration</span>
                        <span class="stat-value">${Math.round(route.duration)} min</span>
                    </div>
                    <div class="comparison-stat">
                        <span class="stat-label">💨 Avg AQI</span>
                        <span class="stat-value" style="background: ${getAQIColor(route.average_aqi)}; padding: 4px 8px; border-radius: 4px; color: ${route.average_aqi > 150 ? '#fff' : '#000'};">
                            ${Math.round(route.average_aqi)}
                        </span>
                    </div>
                </div>
            </div>
        `;
    });
    
    list.innerHTML = html;
    panel.style.display = 'block';
}

// ============================================================================
// API Calls
// ============================================================================

async function compareAllRoutes() {
    const source = document.getElementById('source').value;
    const destination = document.getElementById('destination').value;
    
    if (!source || !destination) {
        alert('Please enter both source and destination');
        return;
    }
    
    showLoading();
    
    try {
        const priorities = ['shortest', 'balanced', 'cleanest', 'pm25', 'pm10', 'co', 'o3', 'so2'];
        const routes = [];
        
        console.log('🔄 Fetching all route priorities...');
        
        for (const priority of priorities) {
            console.log(`  → Fetching ${priority} route...`);
            const response = await fetch('/api/find-route/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrftoken,
                },
                body: JSON.stringify({
                    source_address: source,
                    destination_address: destination,
                    priority: priority,
                    pollutant_type: ['pm25', 'pm10', 'co', 'o3', 'so2'].includes(priority) ? priority : null
                })
            });
            
            const data = await response.json();
            if (data.success) {
                routes.push(data.route);
                console.log(`  ✓ ${priority}: ${data.route.distance}km, AQI ${Math.round(data.route.average_aqi)}`);
            }
        }
        
        if (routes.length > 0) {
            console.log(`✓ Displaying ${routes.length} routes`);
            displayComparisonRoutes(routes);
        } else {
            alert('Could not compare routes. Please try again.');
        }
        
    } catch (error) {
        console.error('Error:', error);
        alert('Failed to compare routes. Please try again.');
    } finally {
        hideLoading();
    }
}

async function findRoute() {
    // Clear comparison mode if active
    if (comparisonMode) {
        clearComparison();
    }
    
    const source = document.getElementById('source').value;
    const destination = document.getElementById('destination').value;
    const priority = document.getElementById('priority').value;
    
    if (!source || !destination) {
        alert('Please enter both source and destination');
        return;
    }
    
    showLoading();
    
    try {
        const response = await fetch('/api/find-route/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrftoken,
            },
            body: JSON.stringify({
                source_address: source,
                destination_address: destination,
                priority: priority,
                pollutant_type: ['pm25', 'pm10', 'co', 'o3', 'so2'].includes(priority) ? priority : null
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            displayRoute(data);
        } else {
            alert('Error: ' + data.error);
        }
    } catch (error) {
        console.error('Error:', error);
        alert('Failed to find route. Please try again.');
    } finally {
        hideLoading();
    }
}

// ============================================================================
// Event Listeners
// ============================================================================

document.getElementById('findRouteBtn').addEventListener('click', findRoute);
document.getElementById('compareAllBtn').addEventListener('click', compareAllRoutes);

document.getElementById('priority').addEventListener('change', function() {
    const source = document.getElementById('source').value;
    const destination = document.getElementById('destination').value;
    
    if (source && destination) {
        console.log('Priority changed to:', this.value);
        findRoute();
    }
});

document.getElementById('source').addEventListener('keypress', function(e) {
    if (e.key === 'Enter') {
        findRoute();
    }
});

document.getElementById('destination').addEventListener('keypress', function(e) {
    if (e.key === 'Enter') {
        findRoute();
    }
});

console.log('Dhaka AQI Route Optimizer loaded successfully!');
