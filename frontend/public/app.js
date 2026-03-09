// ──────────────────────────────────────────────
// Nav AI — Interactive Map Application
// ──────────────────────────────────────────────

let currentSessionId = null;
let userLocation = null;
let userLocationMarker = null;

// Navigation state
let navigationActive = false;
let navigationWatchId = null;
let navigationRoute = null;
let navigationStepIndex = 0;

// Initialize map
const map = L.map('map').setView([20.5937, 78.9629], 5);

L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© OpenStreetMap contributors',
    maxZoom: 19
}).addTo(map);

// Layer Groups
let routeLayer = null;
let routeMarkersLayer = L.layerGroup().addTo(map);
let altRoutesLayer = L.layerGroup().addTo(map);
let poiLayer = L.layerGroup().addTo(map);
let candidateLayer = L.layerGroup().addTo(map);

let currentPrimaryRoute = null;
let currentAlternatives = [];

// ── POI Type Icons ──
const POI_ICONS = {
    hospital: { emoji: '🏥', color: '#ef4444', label: 'Hospital' },
    fuel: { emoji: '⛽', color: '#f97316', label: 'Gas Station' },
    gas_station: { emoji: '⛽', color: '#f97316', label: 'Gas Station' },
    restaurant: { emoji: '🍽️', color: '#8b5cf6', label: 'Restaurant' },
    cafe: { emoji: '☕', color: '#a16207', label: 'Café' },
    hotel: { emoji: '🏨', color: '#0ea5e9', label: 'Hotel' },
    parking: { emoji: '🅿️', color: '#6366f1', label: 'Parking' },
    atm: { emoji: '🏧', color: '#059669', label: 'ATM' },
    charging_station: { emoji: '🔌', color: '#22c55e', label: 'EV Charging' },
    ev_charging: { emoji: '🔌', color: '#22c55e', label: 'EV Charging' },
    pharmacy: { emoji: '💊', color: '#ec4899', label: 'Pharmacy' },
    default: { emoji: '📍', color: '#6b7280', label: 'Place' }
};

function getPoiStyle(type) {
    return POI_ICONS[type?.toLowerCase()] || POI_ICONS.default;
}

// ── Haversine distance helper ──
function toRad(deg) { return (deg * Math.PI) / 180; }

function haversineMeters(a, b) {
    const R = 6371000;
    const dLat = toRad(b.lat - a.lat);
    const dLng = toRad(b.lng - a.lng);
    const h = Math.sin(dLat / 2) ** 2 +
        Math.cos(toRad(a.lat)) * Math.cos(toRad(b.lat)) * Math.sin(dLng / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(h));
}

// ── User Location ──
function getUserLocation() {
    const locationStatus = document.getElementById('locationStatus');
    if ('geolocation' in navigator) {
        navigator.geolocation.getCurrentPosition(
            (position) => {
                userLocation = {
                    lat: position.coords.latitude,
                    lng: position.coords.longitude
                };
                map.setView([userLocation.lat, userLocation.lng], 14);

                const userIcon = L.divIcon({
                    className: 'user-marker',
                    html: '<div class="user-marker-dot"><div class="user-marker-pulse"></div></div>',
                    iconSize: [20, 20],
                    iconAnchor: [10, 10]
                });
                userLocationMarker = L.marker([userLocation.lat, userLocation.lng], { icon: userIcon, zIndexOffset: 1000 })
                    .bindPopup('<b>📍 You are here</b>')
                    .addTo(map);

                if (locationStatus) {
                    locationStatus.innerHTML = '✓ Location found';
                    locationStatus.style.background = '#10b981';
                    setTimeout(() => { locationStatus.style.display = 'none'; }, 3000);
                }
            },
            (error) => {
                console.error('Geolocation error:', error);
                if (locationStatus) {
                    locationStatus.innerHTML = '⚠️ Location access denied';
                    locationStatus.style.background = '#ef4444';
                    setTimeout(() => { locationStatus.style.display = 'none'; }, 5000);
                }
            },
            { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
        );
    }
}
getUserLocation();

// ── DOM Elements ──
const chatMessages = document.getElementById('chatMessages');
const chatInput = document.getElementById('chatInput');
const sendButton = document.getElementById('sendButton');
const startNavButton = document.getElementById('startNavigationButton');
const navigationPanel = document.getElementById('navigationPanel');
const navigationInstructionEl = document.getElementById('navigationInstruction');
const navigationMetaEl = document.getElementById('navigationMeta');
const stopNavButton = document.getElementById('stopNavigationButton');

// Sign icons for turn-by-turn
const SIGN_ICONS = {
    '-98': '↩️', '-8': '↰', '-7': '↖️', '-6': '🔄', '-3': '⬅️', '-2': '⬅️', '-1': '↙️',
    '0': '⬆️', '1': '↗️', '2': '➡️', '3': '➡️', '4': '🏁', '5': '📍', '6': '🔄', '7': '↗️', '8': '↪️'
};
function getSignIcon(sign) { return SIGN_ICONS[String(sign)] || '▶️'; }
function formatDistance(m) { return m >= 1000 ? `${(m / 1000).toFixed(1)} km` : `${Math.round(m)} m`; }
function formatDuration(ms) {
    const min = ms / 60000;
    if (min < 60) return `${Math.round(min)} min`;
    const h = Math.floor(min / 60);
    const m = Math.round(min % 60);
    return m > 0 ? `${h}h ${m}min` : `${h}h`;
}

// ── Simple markdown formatting ──
function formatAgentMessageContent(raw) {
    if (!raw) return '';
    const escaped = raw
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
    let html = escaped.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\*\*/g, '');
    html = html
        .replace(/\r\n/g, '\n')
        .replace(/\n{2,}/g, '<br><br>')
        .replace(/\n/g, '<br>');
    return html;
}

// ── Add Message to Chat ──
function addMessage(content, isUser = false, routeData = null) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${isUser ? 'user-message' : 'agent-message'}`;

    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    if (isUser) {
        contentDiv.textContent = content;
    } else {
        contentDiv.innerHTML = formatAgentMessageContent(content);
    }
    messageDiv.appendChild(contentDiv);

    if (routeData) {
        const routeInfo = document.createElement('div');
        routeInfo.className = 'route-info';
        routeInfo.innerHTML = `
            <strong>Distance:</strong> ${routeData.distance_km} km<br>
            <strong>Duration:</strong> ${Math.round(routeData.time_minutes)} min<br>
            <strong>From:</strong> ${routeData.from}<br>
            <strong>To:</strong> ${routeData.to}
        `;
        messageDiv.appendChild(routeInfo);

        if (routeData.detailed_instructions && routeData.detailed_instructions.length > 0) {
            const directionsPanel = document.createElement('div');
            directionsPanel.className = 'directions-panel';

            const toggleBtn = document.createElement('button');
            toggleBtn.className = 'directions-toggle';
            toggleBtn.innerHTML = `📋 Turn-by-Turn Directions (${routeData.detailed_instructions.length} steps) <span class="toggle-arrow">▼</span>`;
            toggleBtn.onclick = () => {
                const list = directionsPanel.querySelector('.directions-list');
                const arrow = toggleBtn.querySelector('.toggle-arrow');
                list.style.display = list.style.display === 'none' ? 'block' : 'none';
                arrow.textContent = list.style.display === 'none' ? '▼' : '▲';
            };
            directionsPanel.appendChild(toggleBtn);

            const directionsList = document.createElement('div');
            directionsList.className = 'directions-list';
            directionsList.style.display = 'none';

            routeData.detailed_instructions.forEach((step, index) => {
                const stepDiv = document.createElement('div');
                if (step.sign === 4 || step.sign === 5) {
                    stepDiv.className = 'direction-step direction-step-finish';
                    stepDiv.innerHTML = `<span class="step-icon">${getSignIcon(step.sign)}</span><span class="step-text">${step.text}</span>`;
                } else {
                    stepDiv.className = 'direction-step';
                    stepDiv.innerHTML = `
                        <span class="step-number">${index + 1}</span>
                        <span class="step-icon">${getSignIcon(step.sign)}</span>
                        <div class="step-details">
                            <span class="step-text">${step.text}</span>
                            ${step.street_name ? `<span class="step-road">${step.street_name}</span>` : ''}
                            <span class="step-meta">${formatDistance(step.distance_m)} · ${formatDuration(step.time_ms)}</span>
                        </div>
                    `;
                }
                directionsList.appendChild(stepDiv);
            });

            directionsPanel.appendChild(directionsList);
            messageDiv.appendChild(directionsPanel);
        }
    }

    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

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
    if (loadingMsg) loadingMsg.remove();
}


// ──────────────────────────────────────────────
// MAP RENDERING
// ──────────────────────────────────────────────

function drawRoute(routeData) {
    if (routeLayer) map.removeLayer(routeLayer);
    routeMarkersLayer.clearLayers();
    altRoutesLayer.clearLayers();
    currentPrimaryRoute = routeData;

    const polyline = routeData.polyline;
    if (!polyline || polyline.length === 0) return;

    L.polyline(polyline, {
        color: '#1e3a5f', weight: 8, opacity: 0.3,
        lineCap: 'round', lineJoin: 'round'
    }).addTo(routeMarkersLayer);

    routeLayer = L.polyline(polyline, {
        color: '#3b82f6', weight: 5, opacity: 0.85,
        lineCap: 'round', lineJoin: 'round'
    }).addTo(map);

    const startIcon = L.divIcon({
        className: 'route-marker',
        html: '<div class="route-marker-pin route-start"><span class="route-marker-icon">🟢</span></div><div class="route-marker-label">Start</div>',
        iconSize: [40, 50], iconAnchor: [20, 50], popupAnchor: [0, -50]
    });
    L.marker([routeData.start_point.lat, routeData.start_point.lng], { icon: startIcon })
        .bindPopup(`<b>📍 Start</b><br>${routeData.from}`)
        .addTo(routeMarkersLayer);

    const endIcon = L.divIcon({
        className: 'route-marker',
        html: '<div class="route-marker-pin route-end"><span class="route-marker-icon">🔴</span></div><div class="route-marker-label">End</div>',
        iconSize: [40, 50], iconAnchor: [20, 50], popupAnchor: [0, -50]
    });
    L.marker([routeData.end_point.lat, routeData.end_point.lng], { icon: endIcon })
        .bindPopup(`<b>🏁 Destination</b><br>${routeData.to}`)
        .addTo(routeMarkersLayer);

    map.fitBounds(routeLayer.getBounds(), { padding: [60, 60] });

    // Show the "Start Navigation" button on the map
    showStartNavButton();
}


function addPOIMarkers(pois) {
    poiLayer.clearLayers();
    if (!pois || pois.length === 0) return;
    const bounds = [];

    pois.forEach((poi, index) => {
        const style = getPoiStyle(poi.type);
        const distText = poi.distance_km ? ` (${poi.distance_km} km)` : '';

        const icon = L.divIcon({
            className: 'poi-marker',
            html: `<div class="poi-marker-pin" style="background: ${style.color};"><span class="poi-marker-emoji">${style.emoji}</span></div><div class="poi-marker-number" style="background: ${style.color};">${index + 1}</div>`,
            iconSize: [36, 44], iconAnchor: [18, 44], popupAnchor: [0, -44]
        });

        L.marker([poi.lat, poi.lng], { icon })
            .bindPopup(`<div class="poi-popup"><div class="poi-popup-header" style="background: ${style.color};"><span>${style.emoji}</span> ${style.label}</div><div class="poi-popup-body"><b>${poi.name}</b>${distText}</div></div>`)
            .addTo(poiLayer);
        bounds.push([poi.lat, poi.lng]);
    });

    if (userLocation) bounds.push([userLocation.lat, userLocation.lng]);
    if (bounds.length > 0) map.fitBounds(L.latLngBounds(bounds), { padding: [50, 50], maxZoom: 14 });
}


function displayLocationCandidates(candidates) {
    candidateLayer.clearLayers();
    const bounds = [];

    candidates.forEach((candidate) => {
        const icon = L.divIcon({
            className: 'candidate-marker',
            html: `<div class="candidate-marker-pin"><span class="candidate-marker-number">${candidate.id}</span></div>`,
            iconSize: [36, 44], iconAnchor: [18, 44], popupAnchor: [0, -44]
        });

        const distText = candidate.distance_text ? `<br>📏 ${candidate.distance_text}` : '';
        L.marker([candidate.coordinates.lat, candidate.coordinates.lng], { icon })
            .bindPopup(`<div class="candidate-popup"><b>${candidate.id}. ${candidate.name}</b><br><small>📍 ${candidate.address}</small>${distText}<br><button class="candidate-select-btn" onclick="selectCandidate(${candidate.id}, '${candidate.name.replace(/'/g, "\\'")}')">✅ Select this location</button></div>`)
            .addTo(candidateLayer);
        bounds.push([candidate.coordinates.lat, candidate.coordinates.lng]);
    });

    if (userLocation) bounds.push([userLocation.lat, userLocation.lng]);
    if (bounds.length > 0) map.fitBounds(L.latLngBounds(bounds), { padding: [50, 50], maxZoom: 12 });
}

function selectCandidate(id, name) {
    chatInput.value = `${id}`;
    sendMessage();
}


// ──────────────────────────────────────────────
// START NAVIGATION BUTTON (on the map)
// ──────────────────────────────────────────────

function showStartNavButton() {
    if (startNavButton && !navigationActive) {
        startNavButton.style.display = 'block';
    }
}

function hideStartNavButton() {
    if (startNavButton) {
        startNavButton.style.display = 'none';
    }
}

if (startNavButton) {
    startNavButton.addEventListener('click', () => {
        if (currentPrimaryRoute && currentPrimaryRoute.detailed_instructions) {
            startNavigation(currentPrimaryRoute);
        }
    });
}


// ──────────────────────────────────────────────
// LIVE NAVIGATION
// ──────────────────────────────────────────────

function updateNavigationUI() {
    if (!navigationActive || !navigationRoute) return;
    const steps = navigationRoute.detailed_instructions || [];
    if (!steps.length) return;

    const step = steps[navigationStepIndex] || steps[steps.length - 1];
    const icon = getSignIcon(step.sign);

    if (navigationInstructionEl) {
        navigationInstructionEl.textContent = `${icon}  ${step.text}${step.street_name ? ' onto ' + step.street_name : ''}`;
    }
    if (navigationMetaEl) {
        navigationMetaEl.textContent = `${formatDistance(step.distance_m || 0)} · ${formatDuration(step.time_ms || 0)}`;
    }
}

function handleNavigationPosition(position) {
    userLocation = {
        lat: position.coords.latitude,
        lng: position.coords.longitude
    };

    if (userLocationMarker) {
        userLocationMarker.setLatLng([userLocation.lat, userLocation.lng]);
    }

    if (navigationActive) {
        const zoom = map.getZoom() < 16 ? 16 : map.getZoom();
        map.setView([userLocation.lat, userLocation.lng], zoom);
    }

    if (!navigationActive || !navigationRoute) return;

    const steps = navigationRoute.detailed_instructions || [];
    const polyline = navigationRoute.polyline || [];
    if (!steps.length || !polyline.length) return;

    const currentStep = steps[navigationStepIndex];
    if (!currentStep || !currentStep.interval || currentStep.interval.length < 2) return;

    // Target the END of the current step's interval (where the maneuver happens)
    const targetIdx = currentStep.interval[1];
    const targetPt = polyline[targetIdx];
    if (!targetPt) return;

    const target = { lat: targetPt[0], lng: targetPt[1] };
    const dist = haversineMeters(userLocation, target);
    const threshold = 40;

    if (dist < threshold && navigationStepIndex < steps.length - 1) {
        navigationStepIndex += 1;
    }

    // Arrived at destination
    if (navigationStepIndex === steps.length - 1) {
        const end = { lat: navigationRoute.end_point.lat, lng: navigationRoute.end_point.lng };
        if (haversineMeters(userLocation, end) < threshold) {
            if (navigationInstructionEl) navigationInstructionEl.textContent = '🏁 You have arrived at your destination!';
            if (navigationMetaEl) navigationMetaEl.textContent = '';
            stopNavigation(false);
            return;
        }
    }

    updateNavigationUI();
}

function startNavigation(routeData) {
    if (!routeData || !routeData.detailed_instructions || !routeData.detailed_instructions.length) return;

    navigationRoute = routeData;
    navigationStepIndex = 0;
    navigationActive = true;

    hideStartNavButton();

    if (navigationPanel) navigationPanel.style.display = 'block';

    updateNavigationUI();

    if ('geolocation' in navigator) {
        if (navigationWatchId !== null) navigator.geolocation.clearWatch(navigationWatchId);
        navigationWatchId = navigator.geolocation.watchPosition(
            handleNavigationPosition,
            (err) => console.error('Navigation GPS error:', err),
            { enableHighAccuracy: true, maximumAge: 0, timeout: 10000 }
        );
    }
}

function stopNavigation(hidePanel = true) {
    navigationActive = false;
    navigationRoute = null;
    navigationStepIndex = 0;

    if (navigationWatchId !== null && 'geolocation' in navigator) {
        navigator.geolocation.clearWatch(navigationWatchId);
        navigationWatchId = null;
    }

    if (navigationPanel && hidePanel) navigationPanel.style.display = 'none';

    // Show start button again if there's still a route
    if (currentPrimaryRoute && currentPrimaryRoute.detailed_instructions) {
        showStartNavButton();
    }
}

if (stopNavButton) {
    stopNavButton.addEventListener('click', () => stopNavigation(true));
}


// ──────────────────────────────────────────────
// SEND MESSAGE
// ──────────────────────────────────────────────

async function sendMessage() {
    const message = chatInput.value.trim();
    if (!message) return;

    addMessage(message, true);
    chatInput.value = '';
    addLoadingMessage();

    try {
        const token = window.getAccessToken ? window.getAccessToken() : null;
        if (!token) throw new Error('Not authenticated');

        const response = await fetch('http://localhost:8000/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({
                message,
                session_id: currentSessionId,
                user_location: userLocation
            })
        });

        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const data = await response.json();
        currentSessionId = data.session_id;
        removeLoadingMessage();

        addMessage(data.message, false, data.route_data);

        if (data.route_data && data.route_data.polyline) {
            candidateLayer.clearLayers();
            drawRoute(data.route_data);

            if (data.alternative_routes && data.alternative_routes.length > 0) {
                drawAlternativeRoutes(data.alternative_routes);
            }
        }

        if (data.pois && data.pois.length > 0) {
            addPOIMarkers(data.pois);
        }

        if (data.location_candidates && data.location_candidates.length > 0) {
            displayLocationCandidates(data.location_candidates);
        }

    } catch (error) {
        removeLoadingMessage();
        console.error('Error:', error);
        if (error.message.includes('401') || error.message.includes('Not authenticated')) {
            addMessage('Authentication failed. Please login again.', false);
        } else {
            addMessage(`Sorry, I encountered an error: ${error.message}. Please try again.`, false);
        }
    }
}

if (sendButton) sendButton.addEventListener('click', sendMessage);
if (chatInput) chatInput.addEventListener('keypress', (e) => { if (e.key === 'Enter') sendMessage(); });


// ──────────────────────────────────────────────
// ALTERNATIVE ROUTES
// ──────────────────────────────────────────────

function drawAlternativeRoutes(alternatives) {
    altRoutesLayer.clearLayers();
    currentAlternatives = alternatives;

    alternatives.forEach((alt, index) => {
        if (!alt.polyline || alt.polyline.length === 0) return;

        const timeDiff = alt.time_diff_minutes || 0;
        const sign = timeDiff >= 0 ? '+' : '';
        const label = `Route ${index + 2}: ${alt.distance_km} km (${sign}${timeDiff} min)`;

        const altLine = L.polyline(alt.polyline, {
            color: '#94a3b8', weight: 5, opacity: 0.5,
            dashArray: '10, 8', lineCap: 'round', lineJoin: 'round'
        }).addTo(altRoutesLayer);

        altLine.bindTooltip(label, { sticky: true, className: 'alt-route-tooltip' });

        altLine.on('mouseover', function () { this.setStyle({ opacity: 0.85, weight: 6, color: '#64748b' }); });
        altLine.on('mouseout', function () { this.setStyle({ opacity: 0.5, weight: 5, color: '#94a3b8' }); });
        altLine.on('click', function () { switchToAlternativeRoute(index); });
    });
}

function switchToAlternativeRoute(altIndex) {
    if (!currentPrimaryRoute || !currentAlternatives[altIndex]) return;

    const oldPrimary = currentPrimaryRoute;
    const newPrimary = currentAlternatives[altIndex];

    const newAlternatives = currentAlternatives.filter((_, i) => i !== altIndex);
    const oldPrimaryAsAlt = { ...oldPrimary };
    oldPrimaryAsAlt.time_diff_minutes = Math.round((oldPrimary.time_minutes - newPrimary.time_minutes) * 10) / 10;
    oldPrimaryAsAlt.route_label = 'Previous route';
    newAlternatives.push(oldPrimaryAsAlt);

    drawRoute(newPrimary);
    drawAlternativeRoutes(newAlternatives);

    addMessage(
        `Switched to Route ${altIndex + 2}: ${newPrimary.distance_km} km, ~${Math.round(newPrimary.time_minutes)} min.`,
        false,
        newPrimary
    );
}
