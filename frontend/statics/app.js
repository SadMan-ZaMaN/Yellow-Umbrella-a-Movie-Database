// Shared helpers loaded on every page.

const API_BASE = ''; // same origin - FastAPI serves both the API and these pages

// Anything a user typed (usernames, reviews, comments, event titles) has to go
// through this before it's dropped into innerHTML, otherwise a review like
// <img src=x onerror=...> would run in every visitor's browser.
function escapeHtml(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

// --- Auth Utilities ---
function getToken() {
    return localStorage.getItem('access_token');
}

function getUser() {
    const userStr = localStorage.getItem('user');
    return userStr ? JSON.parse(userStr) : null;
}

function isLoggedIn() {
    return !!getToken() && !!getUser();
}

/**
 * Use on PERSONAL pages (profile, watchlist, lists, admin).
 * Redirects unauthenticated users to the login page.
 * Preserves the current URL so we can redirect back after login.
 */
function requireAuth() {
    if (!isLoggedIn()) {
        window.location.href = '/login.html?next=' + encodeURIComponent(window.location.pathname + window.location.search);
    }
}

function logout() {
    localStorage.removeItem('access_token');
    localStorage.removeItem('user');
    window.location.href = '/';
}

// --- Dynamic Navigation ---
// Updates the navigation bar based on auth state
async function updateNavigation() {
    const isAuth = isLoggedIn();
    const guestOnlyElements = document.querySelectorAll('.guest-only');
    const authOnlyElements = document.querySelectorAll('.auth-only');
    const usernameDisplays = document.querySelectorAll('.display-username');

    if (isAuth) {
        guestOnlyElements.forEach(el => el.classList.add('auth-hidden'));
        authOnlyElements.forEach(el => el.classList.remove('auth-hidden'));
        
        const user = getUser();
        if (user && user.username) {
            usernameDisplays.forEach(el => el.textContent = user.username);
        }

        // Only show the Admin link if the server agrees we're an admin.
        // (The role in localStorage is just for display - anyone can edit it.)
        try {
            await apiFetch('/admin/dashboard'); // Will throw error if not admin
            
            const logoutBtn = document.getElementById('logout-btn');
            if (logoutBtn && !document.getElementById('admin-nav-link')) {
                const adminLink = document.createElement('a');
                adminLink.id = 'admin-nav-link';
                adminLink.href = '/admin.html';
                // Clean button styling similar to logout but distinctive
                adminLink.className = 'px-4 py-2 rounded-lg font-semibold text-[0.9rem] cursor-pointer transition bg-red-600/20 border border-red-500 text-red-500 hover:bg-red-500 hover:text-white shadow-[0_0_10px_rgba(239,68,68,0.2)] auth-only flex items-center justify-center';
                adminLink.innerHTML = 'Admin Dashboard';
                logoutBtn.parentNode.insertBefore(adminLink, logoutBtn);
            }
        } catch (e) {
            // 403 Forbidden or general error means not an admin
            const adminLink = document.getElementById('admin-nav-link');
            if (adminLink) adminLink.remove();
        }

    } else {
        guestOnlyElements.forEach(el => el.classList.remove('auth-hidden'));
        authOnlyElements.forEach(el => el.classList.add('auth-hidden'));
        
        // Remove admin link if user logs out
        const adminLink = document.getElementById('admin-nav-link');
        if (adminLink) {
            adminLink.remove();
        }
    }
}

// --- API calls ---
// fetch() plus the JWT header. Use this for anything that touches a user's
// own data - plain fetch() sends no token, so the server will refuse it.
async function apiFetch(endpoint, options = {}) {
    const token = getToken();
    const headers = {
        'Content-Type': 'application/json',
        ...options.headers,
    };

    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }

    const config = {
        ...options,
        headers,
    };

    try {
        const response = await fetch(`${API_BASE}${endpoint}`, config);
        
        // Handle unauthorized (expired token or invalid)
        if (response.status === 401) {
            // Only auto-logout if we thought we were logged in
            if (isLoggedIn()) {
                console.warn("Session expired or unauthorized. Logging out.");
                logout();
            }
            throw new Error("Unauthorized");
        }
        
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.error || data.detail || 'API Error');
        }
        
        return data;
    } catch (error) {
        console.error('API Fetch failed:', error.message);
        throw error;
    }
}

// Ensure the navbar updates immediately when scripts load
document.addEventListener('DOMContentLoaded', () => {
    updateNavigation();
    
    // Attach global logout listener
    const logoutBtn = document.getElementById('logout-btn');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', (e) => {
            e.preventDefault();
            logout();
        });
    }
});

// Global Number Input Clamping
document.addEventListener('input', function(e) {
    if (e.target.type === 'number' && e.target.max) {
        let val = parseFloat(e.target.value);
        let max = parseFloat(e.target.max);
        if (val > max) {
            e.target.value = max;
        }
    }
});
