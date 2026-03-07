// Auth0 configuration
const auth0Config = {
    domain: 'dev-x417ljvag4ramrdf.us.auth0.com',
    clientId: 'ArOSpOmzgJ9JMyAJqEPOj8jE1Tv8H7uE',
    audience: 'https://dev-x417ljvag4ramrdf.us.auth0.com/api/v2/',
    redirectUri: window.location.origin
};

let auth0Client = null;
let accessToken = null;
let isAuthenticated = false;

// Initialize Auth0
async function initAuth0() {
    auth0Client = await auth0.createAuth0Client({
        domain: auth0Config.domain,
        clientId: auth0Config.clientId,
        authorizationParams: {
            audience: auth0Config.audience,
            redirect_uri: auth0Config.redirectUri
        }
    });

    // Check if user is authenticated
    isAuthenticated = await auth0Client.isAuthenticated();

    if (isAuthenticated) {
        accessToken = await auth0Client.getTokenSilently();
        unlockChat();
        return;
    }

    // Check for callback
    const query = window.location.search;
    if (query.includes('code=') && query.includes('state=')) {
        await auth0Client.handleRedirectCallback();
        accessToken = await auth0Client.getTokenSilently();
        isAuthenticated = true;
        window.history.replaceState({}, document.title, '/');
        unlockChat();
        return;
    }

    // Keep chat locked
    lockChat();
}

function lockChat() {
    document.getElementById('lockedInput').style.display = 'flex';
    document.getElementById('unlockedInput').style.display = 'none';
    document.getElementById('authButton').textContent = 'Login';
    document.getElementById('authButton').onclick = login;
}

function unlockChat() {
    document.getElementById('lockedInput').style.display = 'none';
    document.getElementById('unlockedInput').style.display = 'flex';
    document.getElementById('authButton').textContent = 'Logout';
    document.getElementById('authButton').onclick = logout;

    // Update welcome message
    const chatMessages = document.getElementById('chatMessages');
    chatMessages.innerHTML = `
        <div class="message agent-message">
            <div class="message-content">
                Welcome back! I'm your navigation assistant. Where would you like to go?
            </div>
        </div>
    `;
}

async function login() {
    await auth0Client.loginWithRedirect();
}

async function logout() {
    await auth0Client.logout({
        logoutParams: {
            returnTo: window.location.origin
        }
    });
}

function handleAuth() {
    if (isAuthenticated) {
        logout();
    } else {
        login();
    }
}

// Get access token for API calls
function getAccessToken() {
    return accessToken;
}

// Initialize on page load
window.addEventListener('DOMContentLoaded', initAuth0);
