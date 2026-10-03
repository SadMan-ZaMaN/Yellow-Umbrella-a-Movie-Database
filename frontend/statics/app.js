// Shared code loaded on every page: auth helpers, API calls, the site nav,
// search suggestions and the poster cards used in every grid.

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

// --- Auth ---
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

// For personal pages (profile, lists, admin): send guests to the login page
// and bring them back here afterwards.
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

    const response = await fetch(`${API_BASE}${endpoint}`, { ...options, headers });

    if (response.status === 401) {
        // the token expired or was tampered with
        if (isLoggedIn()) logout();
        throw new Error('Unauthorized');
    }
    const data = await response.json();
    if (!response.ok) {
        throw new Error(data.error || data.detail || 'API Error');
    }
    return data;
}

// --- Images ---
const POSTER_FALLBACK = 'https://placehold.co/342x513/1f2833/c5c6c7?text=No+Poster';

// Older rows store bare TMDB paths ("/abc.jpg"), newer ones full URLs.
// Grids ask for a smaller size than the w500 we store.
function imageUrl(url, size = 'w342') {
    if (!url || url === 'None' || url === 'null') return null;
    if (url.startsWith('/')) return `https://image.tmdb.org/t/p/${size}${url}`;
    return url.replace(/image\.tmdb\.org\/t\/p\/w\d+\//, `image.tmdb.org/t/p/${size}/`);
}

const PAGE_FOR = { movie: 'movie', series: 'series', anime: 'anime', game: 'game', person: 'person' };

// A poster card. `item` can come from /search, /discover or the list
// endpoints; they name their fields slightly differently.
function mediaCard(item, { rank } = {}) {
    const type = item.type || item._type || 'movie';
    const url = item.url || `/${PAGE_FOR[type] || 'movie'}.html?id=${item.id}`;
    const poster = imageUrl(item.poster || item.posterurl) || POSTER_FALLBACK;
    const rating = item.rating ?? item.avgrating;
    const year = item.year || (item.releasedate || '').slice(0, 4);
    const meta = item.meta ?? [year, type === 'person' ? item.subtitle : type].filter(Boolean).join(' · ');

    return `
        <a href="${url}" class="poster-card">
            <img src="${poster}" alt="" loading="lazy" decoding="async"
                 onerror="this.onerror=null;this.src='${POSTER_FALLBACK}'">
            ${rank ? `<span class="absolute top-2 left-2 text-lg font-black text-brand-gold drop-shadow">#${rank}</span>` : ''}
            ${rating ? `<span class="poster-rating">★ ${Number(rating).toFixed(1)}</span>` : ''}
            <div class="poster-info">
                <h3 class="poster-title">${escapeHtml(item.title || item.name)}</h3>
                ${meta ? `<p class="poster-meta">${escapeHtml(meta)}</p>` : ''}
            </div>
        </a>`;
}

function skeletonCards(count) {
    return Array.from({ length: count }, () => '<div class="skeleton"></div>').join('');
}

// Cast list on title pages; each person links to their page (which pulls in
// the rest of their best-known work the first time it's opened).
function renderCast(container, cast) {
    if (!cast || !cast.length) {
        container.innerHTML = '<span class="text-brand-gray">No cast details yet.</span>';
        return;
    }
    container.innerHTML = cast.map(actor => {
        const initials = (actor.name || '?').split(/\s+/).map(w => w[0]).slice(0, 2).join('');
        const fallback = `https://placehold.co/88x88/1f2833/c5c6c7?text=${encodeURIComponent(initials)}`;
        const photo = imageUrl(actor.photourl, 'w185') || fallback;
        return `
            <a href="/person.html?id=${actor.id}" class="group bg-black/40 border border-white/10 pl-1.5 pr-4 py-1.5 rounded-full flex items-center gap-3 hover:border-brand-gold/50 hover:bg-white/5 transition-colors">
                <img src="${photo}" alt="" loading="lazy" onerror="this.onerror=null;this.src='${fallback}'"
                     class="w-11 h-11 rounded-full object-cover bg-brand-second flex-none">
                <span class="flex flex-col min-w-0">
                    <strong class="text-white text-sm leading-tight group-hover:text-brand-gold transition-colors">${escapeHtml(actor.name)}</strong>
                    ${actor.role ? `<span class="text-brand-gray text-xs mt-0.5 truncate max-w-[180px]">as <span class="italic text-brand-gold/80">${escapeHtml(actor.role)}</span></span>` : ''}
                </span>
            </a>`;
    }).join('');
}

// Detail pages (movie / series / anime / game): the title's backdrop behind
// the header, and its synopsis under the title.
function showDetailExtras(item, titleEl) {
    if (item.backdropurl) {
        const backdrop = document.createElement('div');
        backdrop.className = 'absolute inset-x-0 top-16 h-[460px] overflow-hidden pointer-events-none';
        backdrop.innerHTML = `
            <img src="${imageUrl(item.backdropurl, 'w1280')}" alt="" class="w-full h-full object-cover opacity-30">
            <div class="absolute inset-0 bg-gradient-to-t from-brand-dark via-brand-dark/60 to-brand-dark/20"></div>`;
        document.body.prepend(backdrop);
        document.querySelector('main').classList.add('relative', 'z-10');
    }
    if (item.overview) {
        const p = document.createElement('p');
        p.className = 'text-brand-gray leading-relaxed max-w-3xl mb-6 line-clamp-4 cursor-pointer';
        p.title = 'Click to read more';
        p.textContent = item.overview;
        p.addEventListener('click', () => p.classList.toggle('line-clamp-4'));
        // under the year / runtime / rating row
        titleEl.nextElementSibling.after(p);
    }
}

// --- Search suggestions ---
// Hooks a text input up to /search and shows a dropdown under it.
// Enter (with nothing highlighted) goes to the full results page.
function attachSuggest(input) {
    const wrap = input.parentElement;
    wrap.classList.add('relative');
    const box = document.createElement('div');
    box.className = 'suggest-box hidden';
    wrap.appendChild(box);

    let timer = null;
    let controller = null;
    let active = -1;

    const close = () => { box.classList.add('hidden'); active = -1; };
    const items = () => [...box.querySelectorAll('.suggest-item')];
    const highlight = (i) => {
        items().forEach((el, n) => el.classList.toggle('is-active', n === i));
        active = i;
    };

    const render = (results, q) => {
        if (!results.length) {
            box.innerHTML = `<p class="px-3 py-2 text-sm text-brand-gray">Nothing found for "${escapeHtml(q)}"</p>`;
            return;
        }
        box.innerHTML = results.map(r => {
            const thumb = imageUrl(r.poster, 'w92') || POSTER_FALLBACK;
            const meta = [r.type === 'person' ? (r.subtitle || 'Person') : r.type, r.year].filter(Boolean).join(' · ');
            return `
                <a href="${r.url}" class="suggest-item">
                    <img src="${thumb}" alt="" class="w-9 h-[52px] object-cover rounded-md bg-brand-second flex-none"
                         onerror="this.onerror=null;this.src='${POSTER_FALLBACK}'">
                    <span class="min-w-0">
                        <span class="block text-sm font-semibold text-white truncate">${escapeHtml(r.title)}</span>
                        <span class="block text-xs text-brand-gold capitalize">${escapeHtml(meta)}</span>
                    </span>
                    ${r.rating ? `<span class="ml-auto text-xs text-brand-gray">★ ${r.rating}</span>` : ''}
                </a>`;
        }).join('') + `
            <a href="/search.html?q=${encodeURIComponent(q)}" class="suggest-item justify-center text-sm text-brand-gold font-semibold">
                See all results for "${escapeHtml(q)}"
            </a>`;
    };

    input.addEventListener('input', () => {
        const q = input.value.trim();
        clearTimeout(timer);
        if (q.length < 2) return close();
        timer = setTimeout(async () => {
            // drop the previous request, otherwise a slow answer for "inc"
            // can arrive after the answer for "inception"
            if (controller) controller.abort();
            controller = new AbortController();
            box.classList.remove('hidden');
            box.innerHTML = '<p class="px-3 py-2 text-sm text-brand-gray">Searching…</p>';
            try {
                const res = await fetch(`/search?q=${encodeURIComponent(q)}&limit=7`, { signal: controller.signal });
                render((await res.json()).results || [], q);
                active = -1;
            } catch (e) {
                if (e.name !== 'AbortError') box.innerHTML = '<p class="px-3 py-2 text-sm text-red-400">Search failed, try again.</p>';
            }
        }, 250);
    });

    input.addEventListener('keydown', (e) => {
        const list = items();
        if (e.key === 'ArrowDown' && list.length) {
            e.preventDefault();
            highlight((active + 1) % list.length);
        } else if (e.key === 'ArrowUp' && list.length) {
            e.preventDefault();
            highlight((active - 1 + list.length) % list.length);
        } else if (e.key === 'Enter') {
            e.preventDefault();
            const q = input.value.trim();
            if (active >= 0 && list[active]) window.location.href = list[active].href;
            else if (q) window.location.href = `/search.html?q=${encodeURIComponent(q)}`;
        } else if (e.key === 'Escape') {
            close();
        }
    });

    document.addEventListener('click', (e) => {
        if (!wrap.contains(e.target)) close();
    });
}

// --- Site nav ---
// Pages put an empty <nav id="site-nav"></nav> where the bar goes.
const NAV_LINKS = [
    ['/', 'Home'],
    ['/top_rated.html', 'Top Rated'],
    ['/celebrities.html', 'Celebrities'],
    ['/events.html', 'Awards'],
];

function renderSiteNav() {
    const nav = document.getElementById('site-nav');
    if (!nav) return;

    const here = window.location.pathname;
    const isActive = (href) => href === here || (href === '/events.html' && here === '/award.html');
    const links = NAV_LINKS.map(([href, label]) =>
        `<a href="${href}" class="nav-link ${isActive(href) ? 'is-active' : ''}">${label}</a>`).join('');

    const user = isLoggedIn() ? getUser() : null;
    const account = user
        ? `<a href="/lists.html" class="nav-link">My Lists</a>
           <a href="/admin.html" class="nav-link text-red-400 hover:text-red-300 hidden" data-admin-link>Admin</a>
           <a href="/profile.html" class="nav-link font-bold text-white">${escapeHtml(user.username)}</a>
           <button type="button" class="btn-outline" data-logout>Logout</button>`
        : `<a href="/login.html" class="btn-outline">Sign In</a>
           <a href="/login.html" class="btn-gold">Sign Up</a>`;

    const searchBox = (id) => `
        <div class="relative w-full">
            <svg class="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-brand-gray pointer-events-none" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>
            <input id="${id}" type="search" autocomplete="off" placeholder="Search movies, shows, anime, games, people…" class="search-field">
        </div>`;

    nav.className = 'site-nav';
    nav.innerHTML = `
        <div class="site-nav-inner">
            <a href="/" class="site-logo">Yellow<span class="text-white">Umbrella</span></a>
            <div class="hidden lg:flex items-center gap-6">${links}</div>
            <div class="hidden md:block flex-1 max-w-md ml-auto">${searchBox('nav-search')}</div>
            <div class="hidden lg:flex items-center gap-4">${account}</div>
            <button type="button" class="lg:hidden ml-auto md:ml-0 p-2 -mr-2 text-brand-gray hover:text-white" aria-label="Menu" data-nav-toggle>
                <svg class="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 7h16M4 12h16M4 17h16"/></svg>
            </button>
        </div>
        <div class="nav-drawer hidden lg:hidden border-t border-white/10 px-[4%] pb-4">
            <div class="md:hidden pt-4">${searchBox('nav-search-mobile')}</div>
            <div class="pt-2">${links}</div>
            <div class="flex flex-wrap items-center gap-4 pt-4">${account}</div>
        </div>`;

    nav.querySelector('[data-nav-toggle]').addEventListener('click', () => {
        nav.querySelector('.nav-drawer').classList.toggle('hidden');
    });
    nav.querySelectorAll('[data-logout]').forEach(btn => btn.addEventListener('click', logout));
    nav.querySelectorAll('.search-field').forEach(attachSuggest);
}

// Shows/hides .guest-only / .auth-only elements anywhere on the page and
// reveals the Admin link if the server says we're an admin.
async function updateNavigation() {
    const user = isLoggedIn() ? getUser() : null;
    document.querySelectorAll('.guest-only').forEach(el => el.classList.toggle('auth-hidden', !!user));
    document.querySelectorAll('.auth-only').forEach(el => el.classList.toggle('auth-hidden', !user));
    if (!user) return;
    document.querySelectorAll('.display-username').forEach(el => el.textContent = user.username);

    // the role in localStorage is only for display - anyone can edit it -
    // so ask the server
    try {
        const me = await apiFetch('/users/me');
        if (me.role === 'admin') {
            document.querySelectorAll('[data-admin-link]').forEach(el => el.classList.remove('hidden'));
        }
    } catch (e) {
        // not logged in any more, or offline
    }
}

renderSiteNav();
document.addEventListener('DOMContentLoaded', () => {
    updateNavigation();
    const logoutBtn = document.getElementById('logout-btn');
    if (logoutBtn) logoutBtn.addEventListener('click', (e) => { e.preventDefault(); logout(); });
});

// Number inputs (ratings) can't go above their max
document.addEventListener('input', (e) => {
    if (e.target.type === 'number' && e.target.max && parseFloat(e.target.value) > parseFloat(e.target.max)) {
        e.target.value = e.target.max;
    }
});
