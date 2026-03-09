// Session ID for this conversation
let currentSessionId = null;
let userLocation = null;
let userLocationMarker = null;

// Initialize map (will be centered on user location)
const map = L.map('map').setView([40.7128, -74.006], 13); // Default: New York

// Add OpenStreetMap tiles
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© OpenStreetMap contributors',
    maxZoom: 19
}).addTo(map);

// Get user's GPS location
function getUserLocation() {
    const locationStatus = document.getElementById('locationStatus');
    
    if ('geolocation' in navigator) {
        navigator.geolocation.getCurrentPosition(
            (position) => {
                userLocation = {
                    lat: position.coords.latitude,
                    lng: position.coords.longitude
                };
                
                // Center map on user location
                map.setView([userLocation.lat, userLocation.lng], 15);
                
                // Add user location marker
                const userIcon = L.divIcon({
                    className: 'user-location-marker',
                    html: '<div style="background: #3b82f6; width: 16px; height: 16px; border-radius: 50%; border: 3px solid white; box-shadow: 0 0 10px rgba(59, 130, 246, 0.5);"></div>',
                    iconSize: [16, 16]
                });
                
                userLocationMarker = L.marker([userLocation.lat, userLocation.lng], {icon: userIcon})
                    .bindPopup('📍 You are here')
                    .addTo(map);
                
                locationStatus.innerHTML = '✓ Location found';
                locationStatus.style.background = '#10b981';
                
                setTimeout(() => {
                    locationStatus.style.display = 'none';
                }, 3000);
            },
            (error) => {
                console.error('Geolocation error:', error);
                locationStatus.innerHTML = '⚠️ Location access denied';
                locationStatus.style.background = '#ef4444';
                
                setTimeout(() => {
                    locationStatus.style.display = 'none';
                }, 5000);
            },
            {
                enableHighAccuracy: true,
                timeout: 10000,
                maximumAge: 0
            }
        );
    } else {
        locationStatus.innerHTML = '⚠️ Geolocation not supported';
        locationStatus.style.background = '#ef4444';
    }
}

// Call on page load
getUserLocation();

// Store map layers
let routeLayer = null;
let markersLayer = L.layerGroup().addTo(map);

// Chat elements
const chatMessages = document.getElementById('chatMessages');
const chatInput = document.getElementById('chatInput');
const sendButton = document.getElementById('sendButton');

// Add message to chat
function addMessage(content, isUser = false, routeData = null) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${isUser ? 'user-message' : 'agent-message'}`;
    
    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    contentDiv.textContent = content;
    
    messageDiv.appendChild(contentDiv);
    
    // Add route info if available
    if (routeData) {
        const routeInfo = document.createElement('div');
        routeInfo.className = 'route-info';
        routeInfo.innerHTML = `
            <strong>Distance:</strong> ${routeData.distance_km} km<br>
            <strong>Duration:</strong> ${routeData.time_minutes} minutes<br>
            <strong>From:</strong> ${routeData.from}<br>
            <strong>To:</strong> ${routeData.to}
        `;
        messageDiv.appendChild(routeInfo);
    }
    
    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// Add loading indicator
function addLoadingMessage() {
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message agent-message';
    messageDiv.id = 'loading-message';
    
    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    contentDiv.innerHTML = 'Thinking<span class="loading"></span>';
    
    messageDiv.appendChild(contentDiv);
    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function removeLoadingMessage() {
    const loadingMsg = document.getElementById('loading-message');
    if (loadingMsg) {
        loadingMsg.remove();
    }
}

// Draw route on map
function drawRoute(routeData) {
    // Clear existing route
    if (routeLayer) {
        map.removeLayer(routeLayer);
    }
    markersLayer.clearLayers();
    
    // Draw polyline
    const polyline = routeData.polyline;
    routeLayer = L.polyline(polyline, {
        color: '#2563eb',
        weight: 5,
        opacity: 0.7
    }).addTo(map);
    
    // Add start marker
    const startIcon = L.divIcon({
        className: 'custom-marker',
        html: '<div style="background: #10b981; width: 24px; height: 24px; border-radius: 50%; border: 3px solid white; box-shadow: 0 2px 4px rgba(0,0,0,0.3);"></div>',
        iconSize: [24, 24]
    });
    
    L.marker([routeData.start_point.lat, routeData.start_point.lng], {icon: startIcon})
        .bindPopup(`<b>Start:</b> ${routeData.from}`)
        .addTo(markersLayer);
    
    // Add end marker
    const endIcon = L.divIcon({
        className: 'custom-marker',
        html: '<div style="background: #ef4444; width: 24px; height: 24px; border-radius: 50%; border: 3px solid white; box-shadow: 0 2px 4px rgba(0,0,0,0.3);"></div>',
        iconSize: [24, 24]
    });
    
    L.marker([routeData.end_point.lat, routeData.end_point.lng], {icon: endIcon})
        .bindPopup(`<b>Destination:</b> ${routeData.to}`)
        .addTo(markersLayer);
    
    // Fit map to route
    map.fitBounds(routeLayer.getBounds(), {padding: [50, 50]});
}

// Add POI markers
function addPOIMarkers(pois) {
    pois.forEach(poi => {
        const poiIcon = L.divIcon({
            className: 'custom-marker',
            html: '<div style="background: #f59e0b; width: 20px; height: 20px; border-radius: 50%; border: 2px solid white; box-shadow: 0 2px 4px rgba(0,0,0,0.3);"></div>',
            iconSize: [20, 20]
        });
        
        L.marker([poi.lat, poi.lng], {icon: poiIcon})
            .bindPopup(`<b>${poi.name}</b><br>${poi.type}`)
            .addTo(markersLayer);
    });
}

// Send message to backend
async function sendMessage() {
    const message = chatInput.value.trim();
    if (!message) return;
    
    // Add user message
    addMessage(message, true);
    chatInput.value = '';
    
    // Add loading indicator
    addLoadingMessage();
    
    try {
        const token = getAccessToken();
        
        if (!token) {
            throw new Error('Not authenticated');
        }
        
        console.log('Sending message with token:', token ? 'Token present' : 'No token');
        
        // Send to backend API with auth
        const response = await fetch('http://localhost:8000/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({ 
                message,
                session_id: currentSessionId,
                user_location: userLocation  // Send GPS location
            })
        });
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        const data = await response.json();
        
        // Store session ID
        currentSessionId = data.session_id;
        
        removeLoadingMessage();
        
        // Add agent response
        addMessage(data.message, false, data.route_data);
        
        // Draw route if available
        if (data.route_data && data.route_data.polyline) {
            drawRoute(data.route_data);
        }
        
        // Add POI markers if available
        if (data.pois && data.pois.length > 0) {
            addPOIMarkers(data.pois);
        }
        
        // Display location candidates if available
        if (data.location_candidates && data.location_candidates.length > 0) {
            displayLocationCandidates(data.location_candidates);
        }
        
    } catch (error) {
        removeLoadingMessage();
        console.error('Full error:', error);
        if (error.message.includes('401') || error.message.includes('Not authenticated')) {
            addMessage('Authentication failed. Please login again.', false);
            setTimeout(() => login(), 2000);
        } else {
            addMessage(`Sorry, I encountered an error: ${error.message}. Please try again.`, false);
        }
    }
}

// Event listeners
sendButton.addEventListener('click', sendMessage);
chatInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
        sendMessage();
    }
});

// Display location candidates on map
function displayLocationCandidates(candidates) {
    // Clear existing markers
    markersLayer.clearLayers();
    
    // Add markers for each candidate
    candidates.forEach((candidate, index) => {
        const icon = L.divIcon({
            className: 'custom-marker',
            html: `<div style="background: #3b82f6; width: 32px; height: 32px; border-radius: 50%; border: 3px solid white; box-shadow: 0 2px 4px rgba(0,0,0,0.3); display: flex; align-items: center; justify-content: center; color: white; font-weight: bold; font-size: 16px;">${candidate.id}</div>`,
            iconSize: [32, 32]
        });
        
        const marker = L.marker([candidate.coordinates.lat, candidate.coordinates.lng], {icon: icon})
            .bindPopup(`
                <div style="min-width: 200px;">
                    <strong>${candidate.name}</strong><br>
                    <small>${candidate.address}</small><br>
                    ${candidate.distance_text ? `<small>📏 ${candidate.distance_text}</small>` : ''}
                </div>
            `)
            .addTo(markersLayer);
        
        // Open popup for first marker
        if (index === 0) {
            marker.openPopup();
        }
    });
    
    // Fit map to show all candidates
    if (candidates.length > 0) {
        const bounds = L.latLngBounds(
            candidates.map(c => [c.coordinates.lat, c.coordinates.lng])
        );
        map.fitBounds(bounds, {padding: [50, 50]});
    }
}

