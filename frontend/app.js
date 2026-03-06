// Initialize map
const map = L.map('map').setView([40.7128, -74.0060], 13); // Default: New York

// Add OpenStreetMap tiles
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© OpenStreetMap contributors',
    maxZoom: 19
}).addTo(map);

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
        // Send to backend API
        const response = await fetch('http://localhost:8000/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ message })
        });
        
        const data = await response.json();
        
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
        
    } catch (error) {
        removeLoadingMessage();
        addMessage('Sorry, I encountered an error. Please try again.', false);
        console.error('Error:', error);
    }
}

// Event listeners
sendButton.addEventListener('click', sendMessage);
chatInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
        sendMessage();
    }
});
