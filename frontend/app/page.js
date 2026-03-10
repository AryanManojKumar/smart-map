'use client';

import Script from 'next/script';

export default function HomePage() {
  return (
    <>
      <Script
        src="https://cdn.auth0.com/js/auth0-spa-js/2.1/auth0-spa-js.production.js"
        strategy="beforeInteractive"
      />
      <Script
        src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
        strategy="afterInteractive"
      />
      {/* Use Next-specific copies of the legacy scripts */}
      <Script src="/auth-client.js" strategy="afterInteractive" />
      <Script src="/app.js" strategy="afterInteractive" />

      <div className="container">
        {/* Chat Panel */}
        <div className="chat-panel">
          <div className="chat-header">
            <h2>Nav AI Assistant</h2>
            <button
              id="authButton"
              className="auth-button"
            >
              Login
            </button>
          </div>

          <div className="chat-messages" id="chatMessages">
            <div className="message agent-message">
              <div className="message-content">
                Hi! I&apos;m your navigation assistant. Please login to start chatting.
              </div>
            </div>
          </div>

          {/* Locked Chat Input */}
          <div id="lockedInput" className="chat-input-locked">
            <div className="lock-overlay">
              <div className="lock-icon">🔒</div>
              <p>Sign in to unlock chat</p>
              <button
                className="unlock-button"
              >
                Sign In / Sign Up
              </button>
            </div>
          </div>

          {/* Unlocked Chat Input */}
          <div
            id="unlockedInput"
            className="chat-input-container"
            style={{ display: 'none' }}
          >
            <input
              type="text"
              id="chatInput"
              placeholder="Ask me for directions or search for places..."
              autoComplete="off"
            />
            <button id="sendButton">Send</button>
          </div>
        </div>

        {/* Map Panel (Always visible) */}
        <div className="map-panel">
          <div id="map" />
          <div id="locationStatus" className="location-status">
            📍 Getting your location...
          </div>

          {/* Start Navigation — shown when a route is active */}
          <button
            id="startNavigationButton"
            className="start-navigation-btn"
            style={{ display: 'none' }}
          >
            ▶ Start Navigation
          </button>

          {/* Live Navigation HUD — shown during active navigation */}
          <div
            id="navigationPanel"
            className="navigation-panel"
            style={{ display: 'none' }}
          >
            <div className="navigation-header">
              <span className="navigation-title">Navigation</span>
              <button id="stopNavigationButton" className="stop-navigation-btn">
                Stop
              </button>
            </div>
            <div className="navigation-body">
              <div id="navigationInstruction" className="navigation-instruction">
                Starting navigation...
              </div>
              <div id="navigationMeta" className="navigation-meta">
                Distance: -- · ETA: --
              </div>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

