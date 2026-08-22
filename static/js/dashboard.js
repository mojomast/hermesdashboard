// Theme management
function initTheme() {
    const saved = localStorage.getItem('hermes-theme');
    if (saved) {
        setTheme(saved);
    } else if (window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches) {
        setTheme('light');
    } else {
        setTheme('dark');
    }
    // Listen for system preference changes
    if (window.matchMedia) {
        window.matchMedia('(prefers-color-scheme: light)').addEventListener('change', e => {
            if (!localStorage.getItem('hermes-theme')) {
                setTheme(e.matches ? 'light' : 'dark');
            }
        });
    }
}

function setTheme(theme) {
    document.documentElement.dataset.theme = theme;
    window.hermesTerminalController?.applyTheme(theme);
    const icon = document.getElementById('theme-icon');
    if (icon) icon.innerHTML = theme === 'light' ? '&#9788;' : '&#9790;';
    // Swap highlight.js theme
    const hljsLink = document.getElementById('hljs-theme');
    if (hljsLink) {
        hljsLink.href = theme === 'light'
            ? 'https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github.min.css'
            : 'https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github-dark.min.css';
    }
}

function toggleTheme() {
    const current = document.documentElement.dataset.theme || 'dark';
    const next = current === 'dark' ? 'light' : 'dark';
    localStorage.setItem('hermes-theme', next);
    setTheme(next);
}

const DASHBOARD_BRAND_STORAGE_KEY = 'hermes_dashboard_brand_concept_v1';

function getDashboardBrandSelection() {
    try {
        const value = Number.parseInt(localStorage.getItem(DASHBOARD_BRAND_STORAGE_KEY) || '', 10);
        return Number.isInteger(value) && value >= 1 && value <= 110 ? value : null;
    } catch (error) {
        return null;
    }
}

function applyDashboardBrandSelection() {
    const frame = document.getElementById('dashboard-logo-preview');
    const fallback = document.getElementById('dashboard-logo-default');
    if (!frame || !fallback) return;
    const selectedId = getDashboardBrandSelection();
    if (!selectedId) {
        frame.hidden = true;
        frame.removeAttribute('src');
        fallback.hidden = false;
        return;
    }
    const nextSrc = `/brand-gallery?embed=${selectedId}`;
    fallback.hidden = false;
    frame.hidden = true;
    frame.onload = () => {
        if (getDashboardBrandSelection() !== selectedId) return;
        fallback.hidden = true;
        frame.hidden = false;
    };
    frame.onerror = () => {
        fallback.hidden = false;
        frame.hidden = true;
    };
    if (!frame.src.endsWith(nextSrc)) frame.src = nextSrc;
}

window.addEventListener('storage', event => {
    if (event.key === DASHBOARD_BRAND_STORAGE_KEY) applyDashboardBrandSelection();
});

function getDefaultHiddenDashboardTabs() {
    return new Set(
        DASHBOARD_TABS
            .filter(tab => !DEFAULT_VISIBLE_DASHBOARD_TABS.has(tab.id))
            .map(tab => tab.id)
    );
}

function getLockedDashboardTabIds() {
    return new Set(DASHBOARD_TABS.filter(tab => tab.locked).map(tab => tab.id));
}

function getHiddenDashboardTabs() {
    try {
        const lockedTabs = getLockedDashboardTabIds();
        const raw = localStorage.getItem(DASHBOARD_TAB_SETTINGS_KEY);
        if (raw === null) return getDefaultHiddenDashboardTabs();
        const parsed = JSON.parse(raw || '[]');
        return new Set(Array.isArray(parsed) ? parsed.filter(id => !lockedTabs.has(id)) : []);
    } catch (error) {
        console.warn('Failed to parse dashboard tab settings:', error);
        return getDefaultHiddenDashboardTabs();
    }
}

function saveHiddenDashboardTabs(hiddenTabs) {
    const lockedTabs = getLockedDashboardTabIds();
    const values = Array.from(hiddenTabs).filter(id => !lockedTabs.has(id));
    localStorage.setItem(DASHBOARD_TAB_SETTINGS_KEY, JSON.stringify(values));
}

function isDashboardTabVisible(panel) {
    return !getHiddenDashboardTabs().has(panel);
}

function applyDashboardTabSettings() {
    const hiddenTabs = getHiddenDashboardTabs();
    DASHBOARD_TABS.forEach(tab => {
        document.querySelectorAll(`[data-panel="${tab.id}"]`).forEach(el => {
            el.classList.toggle('dashboard-tab-hidden', hiddenTabs.has(tab.id));
        });
    });
    const activePanel = document.querySelector('.panel.active');
    if (activePanel) {
        const activeId = activePanel.id.replace(/-panel$/, '');
        if (hiddenTabs.has(activeId)) navigateTo('chat');
    }
}

function renderDashboardTabSettings() {
    const container = document.getElementById('dashboard-tab-settings');
    if (!container) return;
    const hiddenTabs = getHiddenDashboardTabs();
    container.innerHTML = DASHBOARD_TABS.map(tab => `
        <label class="dashboard-tab-setting ${tab.experimental ? 'dashboard-tab-setting-experimental' : ''}" for="dashboard-tab-${tab.id}">
            <span class="dashboard-tab-setting-label">
                <span>${escapeHtml(tab.label)}${tab.experimental ? '<span class="dashboard-tab-warning-badge">Experimental</span>' : ''}</span>
                ${tab.warning ? `<small class="dashboard-tab-warning">${escapeHtml(tab.warning || EXPERIMENTAL_LOCAL_TOOLING_WARNING)}</small>` : ''}
            </span>
            <input id="dashboard-tab-${tab.id}" type="checkbox" ${hiddenTabs.has(tab.id) ? '' : 'checked'} ${tab.locked ? 'disabled' : ''} onchange="setDashboardTabVisible('${tab.id}', this.checked)">
        </label>
    `).join('');
}

function setDashboardTabVisible(panel, visible) {
    if (panel === 'chat') return;
    const hiddenTabs = getHiddenDashboardTabs();
    if (visible) hiddenTabs.delete(panel);
    else hiddenTabs.add(panel);
    saveHiddenDashboardTabs(hiddenTabs);
    applyDashboardTabSettings();
    renderDashboardTabSettings();
}

function resetDashboardTabs() {
    localStorage.removeItem(DASHBOARD_TAB_SETTINGS_KEY);
    applyDashboardTabSettings();
    renderDashboardTabSettings();
    showToast('Dashboard tabs reset to safe defaults');
}

function showAllDashboardTabs() {
    localStorage.setItem(DASHBOARD_TAB_SETTINGS_KEY, JSON.stringify([]));
    applyDashboardTabSettings();
    renderDashboardTabSettings();
    showToast('All dashboard tabs are visible');
}

function openUpdateInstructions() {
    closeDashboardSettings();
    const modal = document.getElementById('update-instructions-modal');
    if (modal) modal.classList.add('active');
}

function closeUpdateInstructions(event) {
    if (event && event.target && event.currentTarget && event.target !== event.currentTarget) return;
    const modal = document.getElementById('update-instructions-modal');
    if (modal) modal.classList.remove('active');
}

async function copyDashboardUpdateCommand() {
    const command = document.getElementById('dashboard-update-command')?.textContent?.trim() || 'git pull --ff-only && python -m pip install -r requirements.txt';
    try {
        if (!navigator.clipboard) throw new Error('Clipboard API unavailable');
        await navigator.clipboard.writeText(command);
        showToast('Update command copied');
    } catch (error) {
        console.warn('Failed to copy update command:', error);
        showToast(command);
    }
}

function summarizeDashboardUpdateResult(data) {
    const lines = [];
    if (data.message) lines.push(data.message);
    if (data.error) lines.push(data.error);
    if (data.branch) lines.push(`Branch: ${data.branch}`);
    if (data.before && data.after && data.before !== data.after) {
        lines.push(`Commit: ${data.before.slice(0, 8)} → ${data.after.slice(0, 8)}`);
    }
    if (Array.isArray(data.dirty_files) && data.dirty_files.length) {
        lines.push(`Local changes: ${data.dirty_files.slice(0, 5).join(', ')}${data.dirty_files.length > 5 ? '…' : ''}`);
    }
    if (data.restart_required) lines.push('Restart the dashboard process, then click Reload Dashboard.');
    return lines.join('\n') || 'Update request finished.';
}

async function startDashboardAutoUpdate() {
    closeDashboardSettings();
    const modal = document.getElementById('update-instructions-modal');
    if (modal) modal.classList.add('active');
    const status = document.getElementById('dashboard-auto-update-status');
    const button = document.getElementById('dashboard-auto-update-button');
    if (!window.confirm('Run dashboard auto-update now? This will run git fetch, git pull --ff-only, and pip install requirements on the dashboard server. It refuses dirty local changes.')) {
        if (status) status.textContent = 'Auto-update cancelled.';
        return;
    }
    if (button) button.disabled = true;
    if (status) status.textContent = 'Updating… checking git status, fetching origin, and applying fast-forward updates.';
    try {
        const response = await fetch('/api/dashboard/update', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ install_dependencies: true })
        });
        const data = await response.json().catch(() => ({}));
        const summary = summarizeDashboardUpdateResult(data);
        if (status) status.textContent = summary;
        showToast(response.ok ? (data.updated ? 'Dashboard updated — restart required' : 'Dashboard already up to date') : 'Auto-update blocked');
    } catch (error) {
        console.error('Dashboard auto-update failed:', error);
        if (status) status.textContent = `Auto-update failed: ${error.message || error}`;
        showToast('Auto-update failed');
    } finally {
        if (button) button.disabled = false;
    }
}

async function hardRefreshDashboard() {
    try {
        invalidateCache();
        if ('caches' in window) {
            const names = await caches.keys();
            await Promise.all(names.map(name => caches.delete(name)));
        }
    } catch (error) {
        console.warn('Dashboard cache cleanup failed:', error);
    }
    const url = new URL(window.location.href);
    url.searchParams.set('dashboard_reload', Date.now().toString());
    window.location.replace(url.toString());
}

function toggleDashboardSettings(event) {
    if (event) event.stopPropagation();
    const menu = document.getElementById('dashboard-settings-menu');
    const button = document.getElementById('dashboard-settings-button');
    if (!menu || !button) return;
    const open = !menu.classList.contains('open');
    menu.classList.toggle('open', open);
    button.classList.toggle('active', open);
    button.setAttribute('aria-expanded', open ? 'true' : 'false');
    if (open) renderDashboardTabSettings();
}

function closeDashboardSettings() {
    const menu = document.getElementById('dashboard-settings-menu');
    const button = document.getElementById('dashboard-settings-button');
    if (!menu || !button) return;
    menu.classList.remove('open');
    button.classList.remove('active');
    button.setAttribute('aria-expanded', 'false');
}

// Initialize theme immediately to avoid flash
initTheme();
applyDashboardBrandSelection();

// API cache with TTL
const apiCache = {};
function cachedFetch(url, ttlMs = 30000) {
    const now = Date.now();
    if (apiCache[url] && (now - apiCache[url].time) < ttlMs) {
        log('inf', 'Cache hit: ' + url);
        return Promise.resolve(apiCache[url].data);
    }
    log('inf', 'Cache miss: ' + url);
    return fetch(url).then(r => r.json()).then(data => {
        apiCache[url] = { data, time: now };
        return data;
    });
}
function invalidateCache(url) {
    if (url) {
        Object.keys(apiCache).forEach(k => {
            if (k === url || k.startsWith(url + '?')) delete apiCache[k];
        });
        log('inf', 'Cache invalidated: ' + url);
    }
    else { Object.keys(apiCache).forEach(k => delete apiCache[k]); log('inf', 'Cache invalidated: all'); }
}

function formatTokenCount(value) {
    const n = Number(value);
    if (!Number.isFinite(n) || n < 0) return '--';
    if (n < 1000) return String(Math.round(n));
    if (n < 1000000) return `${(n / 1000).toFixed(n < 10000 ? 1 : 0)}k`;
    if (n < 1000000000) return `${(n / 1000000).toFixed(n < 10000000 ? 1 : 0)}M`;
    return `${(n / 1000000000).toFixed(n < 10000000000 ? 1 : 0)}B`;
}

function tokenTotal(window) {
    const n = Number(window && window.total_tokens);
    return Number.isFinite(n) && n > 0 ? n : 0;
}

function tokenUsageTopline(windows) {
    const sessionTotal = tokenTotal(windows.current_session);
    const dayTotal = tokenTotal(windows.current_day);
    const weekTotal = tokenTotal(windows.current_week);
    const monthTotal = tokenTotal(windows.current_month);
    const overallTotal = tokenTotal(windows.overall);
    if (sessionTotal > 0 || dayTotal > 0) {
        return `S ${formatTokenCount(sessionTotal)} · D ${formatTokenCount(dayTotal)}`;
    }
    if (weekTotal > 0) {
        return `W ${formatTokenCount(weekTotal)} · O ${formatTokenCount(overallTotal)}`;
    }
    if (monthTotal > 0) {
        return `M ${formatTokenCount(monthTotal)} · O ${formatTokenCount(overallTotal)}`;
    }
    if (overallTotal > 0) {
        return `O ${formatTokenCount(overallTotal)}`;
    }
    return 'S 0 · D 0';
}

function formatTokenExact(value) {
    const n = Number(value);
    if (!Number.isFinite(n) || n < 0) return '--';
    return new Intl.NumberFormat().format(Math.round(n));
}

function getCurrentTokenUsageSessionId() {
    return getActiveRun()?.sessionId || activeChatSessionId || '';
}

function contextGaugeLevel(percent) {
    if (percent > 90) return 'crit';
    if (percent > 70) return 'warn';
    return 'ok';
}

function contextGaugeColor(percent) {
    const level = contextGaugeLevel(percent);
    if (level === 'crit') return '#ef4444';
    if (level === 'warn') return '#f59e0b';
    return 'var(--accent, #4ade80)';
}

function renderContextGaugeHtml(percent, title, variant = '') {
    const level = contextGaugeLevel(percent);
    const levelClass = level === 'crit' ? ' context-gauge-crit' : level === 'warn' ? ' context-gauge-warn' : '';
    const width = Math.max(0, Math.min(100, percent));
    const variantClass = variant === 'chat' ? ' context-gauge-chat' : '';
    return `<div class="context-gauge${levelClass}${variantClass}" role="progressbar" aria-label="Context usage" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${width.toFixed(1)}" aria-valuetext="${escapeHtml(title)}" title="${escapeHtml(title)}"><div class="context-gauge-fill${levelClass}" style="width:${width.toFixed(1)}%;background:${contextGaugeColor(percent)};"></div></div>`;
}

function normalizeContextInfo(context) {
    if (!context || typeof context !== 'object') return null;
    const max = Number(context.context_max);
    if (!Number.isFinite(max) || max <= 0) return null;
    const used = Number(context.context_used);
    let percent = Number(context.percent);
    if (!Number.isFinite(percent) && Number.isFinite(used)) percent = (used / max) * 100;
    if (!Number.isFinite(percent) || percent < 0) return null;
    return {
        used: Number.isFinite(used) && used >= 0 ? used : null,
        max,
        percent,
        stale: context.stale === true,
    };
}

function contextGaugeTooltip(info) {
    const usedText = info.used !== null ? formatTokenCount(info.used) : '?';
    return `${usedText} / ${formatTokenCount(info.max)} tokens (${Math.round(info.percent)}%)${info.stale ? ' (stale)' : ''}`;
}

let sessionContextCache = { sessionId: null, info: null };

async function refreshSessionContextInfo(sessionId) {
    const targetId = sessionId || null;
    sessionContextCache = { sessionId: targetId, info: null };
    if (targetId === getCurrentTokenUsageSessionId()) {
        updateContextDisplay({ usage: null, last_prompt_tokens: 0 });
    }
    if (!targetId) return;
    try {
        const response = await fetch(`/api/sessions/${encodeURIComponent(targetId)}/context`, {
            headers: { 'Accept': 'application/json' },
        });
        if (!response.ok) return;
        const data = await response.json();
        if (sessionContextCache.sessionId !== targetId) return;
        sessionContextCache.info = normalizeContextInfo(data);
        if (targetId === getCurrentTokenUsageSessionId()) {
            const lastAssistant = [...conversation].reverse().find(msg => msg.role === 'assistant');
            updateContextDisplay(lastAssistant ? normalizeAssistantMessage(lastAssistant) : { usage: null, last_prompt_tokens: 0 });
        }
    } catch (error) {
        console.warn('Failed to load session context:', error);
    }
}

function renderTokenUsageSummary(data) {
    lastTokenUsagePayload = data || null;
    const windows = (data && data.windows) || {};
    const session = windows.current_session || {};
    const day = windows.current_day || {};
    const week = windows.current_week || {};
    const month = windows.current_month || {};
    const overall = windows.overall || {};

    const sessionTotal = session.total_tokens;
    const dayTotal = day.total_tokens;
    const summary = document.getElementById('token-usage-summary');
    if (summary) {
        summary.textContent = tokenUsageTopline(windows);
    }

    const fields = {
        'token-usage-current-session': sessionTotal,
        'token-usage-current-day': dayTotal,
        'token-usage-current-week': week.total_tokens,
        'token-usage-current-month': month.total_tokens,
        'token-usage-overall': overall.total_tokens,
    };
    Object.entries(fields).forEach(([id, value]) => {
        const el = document.getElementById(id);
        if (el) el.textContent = formatTokenExact(value);
    });

    const widget = document.getElementById('token-usage-widget');
    if (widget) {
        const contextInfo = normalizeContextInfo(data && data.context);
        widget.title = [
            `Session: ${formatTokenExact(sessionTotal)} tokens`,
            `Today: ${formatTokenExact(dayTotal)} tokens`,
            `Week: ${formatTokenExact(week.total_tokens)} tokens`,
            `Month: ${formatTokenExact(month.total_tokens)} tokens`,
            `Overall: ${formatTokenExact(overall.total_tokens)} tokens`,
            contextInfo ? `Context: ${contextGaugeTooltip(contextInfo)}` : null,
        ].filter(Boolean).join('\n');

        let gaugeHost = widget.querySelector(':scope > .context-gauge-host');
        if (contextInfo) {
            if (!gaugeHost) {
                gaugeHost = document.createElement('div');
                gaugeHost.className = 'context-gauge-host';
                gaugeHost.style.width = '100%';
                widget.appendChild(gaugeHost);
            }
            gaugeHost.innerHTML = renderContextGaugeHtml(contextInfo.percent, contextGaugeTooltip(contextInfo));
        } else if (gaugeHost) {
            gaugeHost.remove();
        }
    }
}

async function loadTokenUsageSummary() {
    if (tokenUsagePollInFlight) return;
    tokenUsagePollInFlight = true;
    try {
        const sessionId = getCurrentTokenUsageSessionId();
        const qs = sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : '';
        const response = await fetch(`/api/token-usage${qs}`, {
            headers: { 'Accept': 'application/json' },
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        renderTokenUsageSummary(await response.json());
    } catch (error) {
        console.warn('Failed to load token usage:', error);
        if (!lastTokenUsagePayload) {
            const summary = document.getElementById('token-usage-summary');
            if (summary) summary.textContent = 'S -- · D --';
        }
    } finally {
        tokenUsagePollInFlight = false;
    }
}

function startTokenUsagePolling() {
    if (tokenUsagePollTimer) return;
    void loadTokenUsageSummary();
    tokenUsagePollTimer = setInterval(() => {
        void loadTokenUsageSummary();
    }, 30000);
}

function refreshTokenUsageSoon() {
    setTimeout(() => void loadTokenUsageSummary(), 500);
}

// Tool call timing
const toolCallTimers = new Map();  // call_id -> start timestamp
const toolCallCompletionTimes = new Map();  // call_id -> elapsed string

function startToolTimer(callId) {
    if (!toolCallTimers.has(callId)) {
        toolCallTimers.set(callId, Date.now());
        log('inf', 'Timer start: ' + callId);
    }
}

function stopToolTimer(callId) {
    const start = toolCallTimers.get(callId);
    if (start) {
        const elapsed = ((Date.now() - start) / 1000).toFixed(1) + 's';
        toolCallCompletionTimes.set(callId, elapsed);
        log('inf', 'Timer stop: ' + callId + ' (' + elapsed + ')');
    }
    toolCallTimers.delete(callId);
}

function getToolElapsed(callId) {
    const start = toolCallTimers.get(callId);
    if (!start) return '';
    const elapsed = (Date.now() - start) / 1000;
    if (elapsed < 60) return elapsed.toFixed(1) + 's';
    return Math.floor(elapsed / 60) + 'm ' + Math.floor(elapsed % 60) + 's';
}

// Timer update interval for in-flight tool calls
let toolTimerInterval = null;

function startToolTimerUpdates() {
    if (toolTimerInterval) return;
    toolTimerInterval = setInterval(() => {
        document.querySelectorAll('.tool-timer[data-call-id]').forEach(el => {
            const callId = el.dataset.callId;
            const elapsed = getToolElapsed(callId);
            if (elapsed) el.textContent = elapsed;
        });
    }, 100);
}

function stopToolTimerUpdates() {
    if (toolTimerInterval) {
        clearInterval(toolTimerInterval);
        toolTimerInterval = null;
    }
}

const DEFAULT_VISIBLE_DASHBOARD_TABS = new Set([
    'chat',
    'bots',
    'kanban',
    'message-board',
    'parallel-arena',
    'config',
    'secrets',
    'sessions',
    'memory',
    'skills',
    'capabilities',
    'files',
    'cron',
    'schedule',
    'graph',
]);

const EXPERIMENTAL_LOCAL_TOOLING_WARNING = "Experimental: built on the maintainer's local tooling and may not work in a fresh install without extra setup.";

const DASHBOARD_TABS = [
    { id: 'chat', label: 'Chat', locked: true },
    { id: 'bots', label: 'Bots' },
    { id: 'kanban', label: 'Kanban' },
    { id: 'message-board', label: 'Message Board' },
    { id: 'dashboard-chat', label: 'Dashboard Chat', experimental: true, warning: 'Optional IRC bridge: connects to external IRC hosts only after it is explicitly enabled and connected.' },
    { id: 'parallel-arena', label: 'Parallel Arena', locked: true },
    { id: 'config', label: 'Config' },
    { id: 'secrets', label: 'Secrets' },
    { id: 'sessions', label: 'Sessions' },
    { id: 'agent-observability', label: 'Agent Ops', experimental: true, warning: 'Experimental: depends on local observability/session tooling.' },
    { id: 'memory', label: 'Memory' },
    { id: 'skills', label: 'Skills' },
    { id: 'capabilities', label: 'Capabilities' },
    { id: 'files', label: 'Files' },
    { id: 'games', label: 'Games', experimental: true, warning: 'Experimental: depends on local game/emulator tooling.' },
    { id: 'roguelike', label: 'Roguelike', experimental: true, warning: 'Experimental: local dashboard-only game experiment.' },
    { id: 'diagnostics', label: 'Diagnostics', experimental: true, warning: 'Experimental: depends on local diagnostic tooling.' },
    { id: 'dnd', label: 'Campaigns', experimental: true, warning: 'Experimental: depends on local campaign/game tooling.' },
    { id: 'self-improvement', label: 'Self-Improvement', experimental: true, warning: 'Experimental: depends on local Hermes self-improvement tooling.' },
    { id: 'autonomous-development', label: 'Autonomous Development', experimental: true, warning: 'Experimental: depends on local autonomous-development tooling.' },
    { id: 'nexussy', label: 'Nexussy', experimental: true, warning: 'Experimental: depends on the local Nexussy sidecar.' },
    { id: 'scrolls', label: 'Vesuvius AutoResearch', experimental: true, warning: 'Experimental: depends on local Vesuvius/autoresearch tooling.' },
    { id: 'cron', label: 'Cron' },
    { id: 'schedule', label: 'Schedule' },
    { id: 'graph', label: 'Graph' },
];
const DASHBOARD_TAB_SETTINGS_KEY = 'hermes_dashboard_hidden_tabs_v1';
const DASHBOARD_NOTIFICATION_SETTINGS_KEY = 'hermes_dashboard_browser_notifications_v1';
const DEFAULT_DASHBOARD_NOTIFICATION_SETTINGS = Object.freeze({
    enabled: false,
    approvals: true,
    runs: true,
    subagents: true,
    errors: true,
    whileVisible: false,
});
const dashboardNotificationKeys = new Set();

function getDashboardNotificationSettings() {
    try {
        const stored = JSON.parse(localStorage.getItem(DASHBOARD_NOTIFICATION_SETTINGS_KEY) || '{}');
        return { ...DEFAULT_DASHBOARD_NOTIFICATION_SETTINGS, ...(stored && typeof stored === 'object' ? stored : {}) };
    } catch (error) {
        console.warn('Failed to read browser notification settings:', error);
        return { ...DEFAULT_DASHBOARD_NOTIFICATION_SETTINGS };
    }
}

function saveDashboardNotificationSettings(settings) {
    localStorage.setItem(DASHBOARD_NOTIFICATION_SETTINGS_KEY, JSON.stringify(settings));
    renderDashboardNotificationSettings();
}

function browserNotificationPermission() {
    return typeof Notification === 'undefined' ? 'unsupported' : Notification.permission;
}

function renderDashboardNotificationSettings() {
    const settings = getDashboardNotificationSettings();
    const permission = browserNotificationPermission();
    const status = document.getElementById('dashboard-notification-status');
    const toggle = document.getElementById('dashboard-notification-toggle');
    const labels = {
        approvals: 'dashboard-notification-approvals',
        runs: 'dashboard-notification-runs',
        subagents: 'dashboard-notification-subagents',
        errors: 'dashboard-notification-errors',
        whileVisible: 'dashboard-notification-visible',
    };
    Object.entries(labels).forEach(([key, id]) => {
        const input = document.getElementById(id);
        if (input) {
            input.checked = Boolean(settings[key]);
            input.disabled = permission === 'unsupported';
        }
    });
    if (toggle) {
        toggle.disabled = permission === 'unsupported' || permission === 'denied';
        toggle.textContent = settings.enabled && permission === 'granted'
            ? 'Disable browser notifications'
            : 'Enable browser notifications';
    }
    if (!status) return;
    if (permission === 'unsupported') status.textContent = 'Browser notifications are not supported here.';
    else if (permission === 'denied') status.textContent = 'Notifications are blocked. Allow them in this site\'s browser settings.';
    else if (settings.enabled && permission === 'granted') status.textContent = 'Browser notifications are enabled.';
    else status.textContent = 'Notifications are off. Enable them to receive approval and attention alerts.';
}

async function toggleDashboardNotifications() {
    const settings = getDashboardNotificationSettings();
    if (browserNotificationPermission() === 'unsupported') {
        showToast('Browser notifications are not supported', true);
        return;
    }
    if (settings.enabled && Notification.permission === 'granted') {
        saveDashboardNotificationSettings({ ...settings, enabled: false });
        showToast('Browser notifications disabled');
        return;
    }
    const permission = Notification.permission === 'granted'
        ? 'granted'
        : await Notification.requestPermission();
    const enabled = permission === 'granted';
    saveDashboardNotificationSettings({ ...settings, enabled });
    showToast(enabled ? 'Browser notifications enabled' : 'Notification permission was not granted', !enabled);
}

function updateDashboardNotificationSetting(name, value) {
    if (!Object.prototype.hasOwnProperty.call(DEFAULT_DASHBOARD_NOTIFICATION_SETTINGS, name) || name === 'enabled') return;
    const settings = getDashboardNotificationSettings();
    saveDashboardNotificationSettings({ ...settings, [name]: Boolean(value) });
}

function sendDashboardNotification(kind, title, body, options = {}) {
    const settings = getDashboardNotificationSettings();
    if (!settings.enabled || !settings[kind] || browserNotificationPermission() !== 'granted') return false;
    if (!settings.whileVisible && document.visibilityState === 'visible' && !options.force) return false;
    const key = options.key || `${kind}:${title}:${body}`;
    if (dashboardNotificationKeys.has(key)) return false;
    dashboardNotificationKeys.add(key);
    if (dashboardNotificationKeys.size > 250) dashboardNotificationKeys.delete(dashboardNotificationKeys.values().next().value);
    const notification = new Notification(title, {
        body: String(body || '').slice(0, 240),
        tag: options.tag || key,
    });
    notification.onclick = () => {
        window.focus();
        if (options.panel) navigateTo(options.panel);
        notification.close();
    };
    return true;
}

function sendDashboardNotificationTest() {
    const sent = sendDashboardNotification('approvals', 'Hermes Dashboard', 'Browser notifications are working.', {
        key: `test:${Date.now()}`,
        tag: 'hermes-dashboard-test',
        panel: 'chat',
        force: true,
    });
    if (!sent) showToast('Enable notifications first, or allow notifications while the dashboard is visible', true);
}

// Lazy loading: track which tabs have been loaded
const tabLoaded = DASHBOARD_TABS.reduce((acc, tab) => {
    acc[tab.id] = tab.id === 'chat';
    return acc;
}, {});

// Sessions pagination state
let sessionsPage = 0;
const sessionsPerPage = 50;

const chat = document.getElementById('chat');
const userInput = document.getElementById('user-input');
const sendBtn = document.getElementById('send-btn');
const chatImageInput = document.getElementById('chat-image-input');
const chatImageBtn = document.getElementById('chat-image-btn');
const chatAttachmentPreviewBar = document.getElementById('chat-attachment-preview-bar');
const debugLog = document.getElementById('debug-log');
const contextPanel = document.getElementById('chat-context-panel');
const contextSummary = document.getElementById('chat-context-summary');
const chatRunStatus = document.getElementById('chat-run-status');
const chatRunStatusDetails = document.getElementById('chat-run-status-details');
const chatRunStatusTitle = document.getElementById('chat-run-status-title');
const chatRunStatusText = document.getElementById('chat-run-status-text');
const chatRunStatusMeta = document.getElementById('chat-run-status-meta');
const chatRunStopBtn = document.getElementById('chat-run-stop-btn');
const chatRunReattachBtn = document.getElementById('chat-run-reattach-btn');
const chatRunResumeBtn = document.getElementById('chat-run-resume-btn');
const chatRoomList = document.getElementById('chat-room-list');
const chatRoomTitle = document.getElementById('chat-room-title');
const chatRoomSubtitle = document.getElementById('chat-room-subtitle');
const chatRoomEyebrow = document.getElementById('chat-room-eyebrow');
const chatRoomProfile = document.getElementById('chat-room-profile');
const chatRoomRail = document.getElementById('chat-room-rail');
const chatRoomRailToggle = document.getElementById('chat-room-rail-toggle');
let chatRoomAvatar = document.getElementById('chat-room-avatar');
let conversation = [];
let models = {};
let currentConfig = {};
let settingsData = null;
let debugVisible = false;
let currentSessionFiles = [];
let currentSessionTraceContext = null;
let pendingSessionExecutionTarget = null;
let activeSessionDetailRequestId = 0;
let activeSessionDetailId = null;
let activeRuns = {};
let recoveredLegacyRunRoomId = null;
let activeChatSessionId = null;
let activeChatRoomId = 'main';
let botRegistry = [];
let chatRoomSwitchInFlight = false;
let sharedRoomRequestInFlight = false;
let chatResetInFlight = false;
const streamResumeRooms = new Set();
const connectedChatRunRooms = new Set();
let tokenUsagePollTimer = null;
let tokenUsagePollInFlight = false;
let lastTokenUsagePayload = null;
let pendingImageAttachments = [];
let pendingImageAttachmentSeq = 0;
let pendingImageAttachmentGeneration = 0;
let approvalPollTimer = null;
let approvalsInFlight = false;
let lastApprovalIds = new Set();
let autoApprovalUntil = 0;
let autoApprovalDecision = 'once';
let approvalPassphraseRequired = false;
const APPROVAL_PASSPHRASE_STORAGE_KEY = 'hermes_dashboard_approval_passphrase_v1';
const APPROVAL_POLL_MS = 2000;

// Dashboard state persistence
// Legacy localStorage keys are read once for migration only. Rich chat/run
// payloads now live server-side in ~/.hermes/dashboard_state.db so long
// tool outputs/traces cannot exhaust the browser's tiny localStorage quota.
const STORAGE_KEY = 'hermes_dashboard_conversation_v2';
const ACTIVE_RUN_KEY = 'hermes_dashboard_active_run_v1';
const ACTIVE_CHAT_SESSION_KEY = 'hermes_dashboard_active_chat_session_v1';
const ACTIVE_CHAT_ROOM_KEY = 'hermes_dashboard_active_chat_room_v1';
const CHAT_ROOM_RAIL_EXPANDED_KEY = 'hermes_dashboard_chat_room_rail_expanded_v1';
const DASHBOARD_STATE_ENDPOINT = '/api/dashboard-state';
const dashboardStateSaveTimers = new Map();
const dashboardStateWriteChains = new Map();
const botRoomWriteChains = new Map();

async function saveDashboardState(key, value, options = {}) {
    const immediate = Boolean(options.immediate);
    const delay = Number.isFinite(options.delay) ? options.delay : 350;
    if (dashboardStateSaveTimers.has(key)) {
        clearTimeout(dashboardStateSaveTimers.get(key));
        dashboardStateSaveTimers.delete(key);
    }
    const write = () => {
        const previous = dashboardStateWriteChains.get(key) || Promise.resolve();
        const pending = previous.catch(() => {}).then(async () => {
            try {
                const response = await fetch(`${DASHBOARD_STATE_ENDPOINT}/${encodeURIComponent(key)}`, {
                    method: value === null || typeof value === 'undefined' ? 'DELETE' : 'PUT',
                    headers: value === null || typeof value === 'undefined' ? {} : { 'Content-Type': 'application/json' },
                    body: value === null || typeof value === 'undefined' ? undefined : JSON.stringify({ value }),
                });
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                return true;
            } catch (e) {
                console.warn(`Failed to save dashboard state ${key}:`, e);
                log('warn', `Failed to save dashboard state ${key}: ${e.message}`);
                return false;
            }
        });
        dashboardStateWriteChains.set(key, pending);
        void pending.finally(() => {
            if (dashboardStateWriteChains.get(key) === pending) dashboardStateWriteChains.delete(key);
        });
        return pending;
    };
    if (immediate) {
        return await write();
    } else {
        dashboardStateSaveTimers.set(key, setTimeout(write, delay));
        return true;
    }
}

async function loadDashboardState(key) {
    try {
        const response = await fetch(`${DASHBOARD_STATE_ENDPOINT}/${encodeURIComponent(key)}`, {
            headers: { 'Accept': 'application/json' },
        });
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        const data = await response.json();
        if (data && data.found) {
            return { found: true, value: data.value };
        }
    } catch (e) {
        console.warn(`Failed to load dashboard state ${key}:`, e);
        log('warn', `Failed to load dashboard state ${key}: ${e.message}`);
    }
    return { found: false, value: null };
}

function loadLegacyLocalStorageValue(storageKey) {
    try {
        const saved = localStorage.getItem(storageKey);
        return saved ? JSON.parse(saved) : null;
    } catch (e) {
        console.warn(`Failed to load legacy localStorage ${storageKey}:`, e);
        log('warn', `Failed to load legacy localStorage ${storageKey}: ${e.message}`);
        return null;
    }
}

function removeLegacyLocalStorageValue(storageKey) {
    try {
        localStorage.removeItem(storageKey);
    } catch (e) {
        console.warn(`Failed to remove legacy localStorage ${storageKey}:`, e);
    }
}

function saveConversation() {
    if (activeChatRoomId === 'main') {
        void saveDashboardState('conversation', conversation);
    } else {
        void saveBotRoom(activeChatRoomId, conversation, activeChatSessionId);
    }
}

async function saveBotRoom(roomId, roomConversation, sessionId) {
    if (!roomId || roomId === 'main') return false;
    const previous = botRoomWriteChains.get(roomId) || Promise.resolve();
    const pending = previous.catch(() => {}).then(async () => {
        try {
            const response = await fetch(`/api/bot-rooms/${encodeURIComponent(roomId)}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ conversation: roomConversation || [], session_id: sessionId || null }),
            });
            const data = await response.json().catch(() => ({}));
            if (!response.ok || data.ok === false) throw new Error(data.error || `HTTP ${response.status}`);
            return true;
        } catch (error) {
            log('warn', `Failed to save room ${roomId}: ${error.message || error}`);
            return false;
        }
    });
    botRoomWriteChains.set(roomId, pending);
    void pending.finally(() => {
        if (botRoomWriteChains.get(roomId) === pending) botRoomWriteChains.delete(roomId);
    });
    return await pending;
}

async function loadConversation() {
    const serverState = await loadDashboardState('conversation');
    if (serverState.found && Array.isArray(serverState.value)) {
        conversation = serverState.value;
        removeLegacyLocalStorageValue(STORAGE_KEY);
        return true;
    }
    const legacyConversation = loadLegacyLocalStorageValue(STORAGE_KEY);
    if (Array.isArray(legacyConversation)) {
        conversation = legacyConversation;
        void saveDashboardState('conversation', conversation, { immediate: true });
        removeLegacyLocalStorageValue(STORAGE_KEY);
        return true;
    }
    return false;
}

function getActiveRun(roomId = activeChatRoomId) {
    return activeRuns[roomId] || null;
}

function saveActiveRuns() {
    const value = Object.keys(activeRuns).length ? { version: 2, runs: activeRuns } : null;
    void saveDashboardState('active_run', value, { delay: 500 });
}

async function loadActiveRuns() {
    const serverState = await loadDashboardState('active_run');
    if (serverState.found && serverState.value && typeof serverState.value === 'object') {
        const stored = serverState.value;
        if (stored.version === 2 && stored.runs && typeof stored.runs === 'object') {
            activeRuns = stored.runs;
        } else if (stored.runId) {
            const roomId = stored.roomId || 'main';
            activeRuns = { [roomId]: stored };
            recoveredLegacyRunRoomId = roomId;
            saveActiveRuns();
        }
        removeLegacyLocalStorageValue(ACTIVE_RUN_KEY);
        return Object.keys(activeRuns).length > 0;
    }
    const legacyActiveRun = loadLegacyLocalStorageValue(ACTIVE_RUN_KEY);
    if (legacyActiveRun && typeof legacyActiveRun === 'object' && legacyActiveRun.runId) {
        const roomId = legacyActiveRun.roomId || 'main';
        activeRuns = { [roomId]: legacyActiveRun };
        recoveredLegacyRunRoomId = roomId;
        void saveDashboardState('active_run', { version: 2, runs: activeRuns }, { immediate: true });
        removeLegacyLocalStorageValue(ACTIVE_RUN_KEY);
        return true;
    }
    activeRuns = {};
    return false;
}

function clearActiveRun(roomId = activeChatRoomId, expectedRunId = null) {
    const run = getActiveRun(roomId);
    if (!run || (expectedRunId && run.runId !== expectedRunId)) return;
    delete activeRuns[roomId];
    const value = Object.keys(activeRuns).length ? { version: 2, runs: activeRuns } : null;
    void saveDashboardState('active_run', value, { immediate: true });
    updateActiveRunBanner();
    renderChatRoomRail();
}

function saveActiveChatSession() {
    if (activeChatRoomId !== 'main') {
        void saveBotRoom(activeChatRoomId, conversation, activeChatSessionId);
        return;
    }
    saveMainChatSession(activeChatSessionId);
}

function saveMainChatSession(sessionId) {
    try {
        if (sessionId) {
            localStorage.setItem(ACTIVE_CHAT_SESSION_KEY, sessionId);
        } else {
            localStorage.removeItem(ACTIVE_CHAT_SESSION_KEY);
        }
    } catch (e) {
        log('warn', 'Failed to save active chat session: ' + e.message);
    }
}

function loadActiveChatSession() {
    try {
        activeChatSessionId = localStorage.getItem(ACTIVE_CHAT_SESSION_KEY) || null;
    } catch (e) {
        activeChatSessionId = null;
        log('warn', 'Failed to load active chat session: ' + e.message);
    }
    void refreshSessionContextInfo(activeChatSessionId);
}

function saveActiveChatRoom() {
    try {
        localStorage.setItem(ACTIVE_CHAT_ROOM_KEY, activeChatRoomId);
    } catch (error) {
        log('warn', 'Failed to save active chat room: ' + error.message);
    }
}

function updateActiveChatBanner() {
    const banner = document.getElementById('current-personality');
    if (!banner) return;
    const base = banner.dataset.baseText || banner.textContent;
    banner.dataset.baseText = base;
    banner.textContent = activeChatSessionId ? `${base} • Continuing session ${activeChatSessionId.slice(0, 8)}` : base;
}

function attachChatToSession(sessionId) {
    hydrateChatFromSession(sessionId).catch((error) => {
        showToast('Failed to load session into chat: ' + error.message, true);
        log('err', 'Failed to attach chat to session: ' + error.message, true);
    });
}

function summarizeActiveRunPreview() {
    const state = getActiveRun()?.assistantState || null;
    if (!state) return '';
    const tools = Array.isArray(state.tools) ? state.tools : [];
    const latestTool = [...tools].reverse().find(Boolean);
    if (latestTool) {
        const parsedArgs = parseToolPayload(latestTool.arguments);
        const target = getToolTargetSummary(latestTool.name || 'tool', parsedArgs.parsed, parsedArgs.raw);
        const status = getToolStatusText(getToolStatusClass(latestTool));
        return [latestTool.name || 'tool', target, status].filter(Boolean).join(' • ');
    }
    if (state.content) {
        return summarizeValue(state.content, 160).replace(/\s+/g, ' ').trim();
    }
    return '';
}

function updateActiveRunBanner() {
    if (!chatRunStatus) return;
    const activeRun = getActiveRun();
    const streamResumeInFlight = streamResumeRooms.has(activeChatRoomId);
    const streamConnected = connectedChatRunRooms.has(activeChatRoomId);
    const hasActive = Boolean(activeRun && activeRun.runId);
    chatRunStatus.classList.toggle('visible', hasActive);
    chatRunStatus.classList.toggle('is-live', hasActive && streamConnected);
    if (!hasActive) {
        if (chatRunStatusDetails) chatRunStatusDetails.open = false;
        return;
    }
    const preview = summarizeActiveRunPreview();
    const sessionLabel = activeRun.sessionId ? `session ${String(activeRun.sessionId).slice(0, 8)}` : 'no session attached yet';
    const ageSeconds = activeRun.startedAt ? Math.max(0, Math.floor((Date.now() - activeRun.startedAt) / 1000)) : null;
    chatRunStatusTitle.textContent = streamResumeInFlight
        ? 'Hermes is reconnecting to the live run'
        : (streamConnected ? 'Hermes is currently working' : 'Hermes has a run to follow');
    chatRunStatusText.textContent = preview || 'A previous chat run is still in progress or waiting to resume.';
    chatRunStatusMeta.textContent = [
        sessionLabel,
        ageSeconds !== null ? `started ${ageSeconds}s ago` : '',
        activeRun.eventOffset ? `${activeRun.eventOffset} events cached` : '',
    ].filter(Boolean).join(' • ');
    if (chatRunStopBtn) {
        chatRunStopBtn.hidden = false;
        const stopQueued = liveRunInterruptState.queued && liveRunInterruptState.roomId === activeChatRoomId;
        chatRunStopBtn.disabled = stopQueued;
        chatRunStopBtn.textContent = stopQueued ? 'Stopping...' : 'Stop main agent';
    }
    if (chatRunReattachBtn) {
        chatRunReattachBtn.hidden = !activeRun.sessionId;
        chatRunReattachBtn.disabled = streamResumeInFlight;
    }
    if (chatRunResumeBtn) {
        chatRunResumeBtn.hidden = streamConnected;
        chatRunResumeBtn.disabled = streamResumeInFlight;
    }
}

function dismissActiveRunBanner() {
    if (!chatRunStatus) return;
    chatRunStatus.classList.remove('visible');
}

function reattachActiveRunSession() {
    const activeRun = getActiveRun();
    if (!activeRun?.sessionId) {
        showToast('No active run session to reattach', true);
        return;
    }
    hydrateChatFromSession(activeRun.sessionId, { preserveActiveRun: true }).catch((error) => {
        showToast('Failed to reattach session: ' + error.message, true);
        log('err', 'Failed to reattach active run session: ' + error.message, true);
    });
}

function resumeActiveRunFromBanner() {
    const activeRun = getActiveRun();
    const roomId = activeChatRoomId;
    const streamResumeInFlight = streamResumeRooms.has(roomId);
    if (!activeRun?.runId || streamResumeInFlight) {
        showToast('No resumable run found', true);
        return;
    }
    navigateTo('chat');
    streamResumeRooms.add(roomId);
    syncChatInputState();
    updateActiveRunBanner();
    streamChatRun({
        runId: activeRun.runId,
        messagesPayload: conversation,
        resume: true,
        eventOffset: activeRun.eventOffset || 0,
        sessionId: activeRun.sessionId || null,
        assistantSeed: activeRun.assistantState || null,
        roomId,
        profile: activeRun.profile || 'default',
    }).catch((error) => {
        log('err', `Resume failed: ${error.message}`, true);
        clearActiveRun(roomId, activeRun.runId);
    }).finally(() => {
        streamResumeRooms.delete(roomId);
        syncChatInputState();
        updateActiveRunBanner();
    });
}

function activeApprovalSessionId() {
    const activeRun = getActiveRun();
    return activeRun?.approvalSessionId || activeRun?.sessionId || activeChatSessionId || '';
}

function updateAutoApprovalSettings(resetDeadline = true) {
    const toggle = document.getElementById('approval-auto-toggle');
    const slider = document.getElementById('approval-auto-minutes');
    const label = document.getElementById('approval-auto-minutes-label');
    const decision = document.getElementById('approval-auto-decision');
    const minutes = Math.max(1, Math.min(60, Number(slider?.value || 5)));
    if (label) label.textContent = `${minutes}m`;
    autoApprovalDecision = decision?.value === 'session' ? 'session' : 'once';
    if (toggle?.checked) {
        if (resetDeadline || autoApprovalUntil <= Date.now()) {
            autoApprovalUntil = Date.now() + minutes * 60 * 1000;
        }
    } else {
        autoApprovalUntil = 0;
    }
    updateAutoApprovalStatus();
}

function updateAutoApprovalStatus() {
    const status = document.getElementById('approval-auto-status');
    const toggle = document.getElementById('approval-auto-toggle');
    if (!status) return;
    if (!autoApprovalUntil || autoApprovalUntil <= Date.now()) {
        if (toggle) toggle.checked = false;
        autoApprovalUntil = 0;
        status.textContent = 'Auto-approve is off.';
        return;
    }
    const seconds = Math.max(0, Math.ceil((autoApprovalUntil - Date.now()) / 1000));
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    status.textContent = `Auto-approve ${autoApprovalDecision} is ON for ${mins}:${String(secs).padStart(2, '0')} more. It only resolves visible pending Hermes tool prompts.`;
}

function stopAutoApproval() {
    autoApprovalUntil = 0;
    const toggle = document.getElementById('approval-auto-toggle');
    if (toggle) toggle.checked = false;
    updateAutoApprovalStatus();
}

function approvalPassphraseInput() {
    return document.getElementById('approval-passphrase');
}

function cacheApprovalPassphrase(force = false) {
    const input = approvalPassphraseInput();
    const remember = document.getElementById('approval-passphrase-remember');
    if (!input || !remember) return;
    if (remember.checked || force) {
        try {
            if (input.value) sessionStorage.setItem(APPROVAL_PASSPHRASE_STORAGE_KEY, input.value);
            else sessionStorage.removeItem(APPROVAL_PASSPHRASE_STORAGE_KEY);
        } catch (_) {}
    }
    updateApprovalPassphraseStatus();
}

function currentApprovalPassphrase() {
    const input = approvalPassphraseInput();
    if (input && input.value) return input.value;
    try { return sessionStorage.getItem(APPROVAL_PASSPHRASE_STORAGE_KEY) || ''; } catch (_) { return ''; }
}

function clearApprovalPassphrase() {
    const input = approvalPassphraseInput();
    const remember = document.getElementById('approval-passphrase-remember');
    if (input) input.value = '';
    if (remember) remember.checked = false;
    try { sessionStorage.removeItem(APPROVAL_PASSPHRASE_STORAGE_KEY); } catch (_) {}
    updateApprovalPassphraseStatus();
}

function updateApprovalPassphraseStatus() {
    const status = document.getElementById('approval-passphrase-status');
    if (!status) return;
    const hasPassphrase = Boolean(currentApprovalPassphrase());
    if (approvalPassphraseRequired) {
        status.textContent = hasPassphrase ? 'Passphrase cached for this tab.' : 'Passphrase required for approve/deny.';
        status.style.color = hasPassphrase ? 'var(--text-dim)' : 'var(--warning, #fbbf24)';
    } else {
        status.textContent = 'No passphrase required by dashboard config.';
        status.style.color = 'var(--text-dim)';
    }
}

function hydrateApprovalPassphrase() {
    const input = approvalPassphraseInput();
    const remember = document.getElementById('approval-passphrase-remember');
    let stored = '';
    try { stored = sessionStorage.getItem(APPROVAL_PASSPHRASE_STORAGE_KEY) || ''; } catch (_) {}
    if (stored && input) input.value = stored;
    if (stored && remember) remember.checked = true;
    updateApprovalPassphraseStatus();
}

function removeApprovalChatBubble() {
    const existing = document.getElementById('approval-chat-bubble');
    if (existing) existing.remove();
}

function renderApprovalChatBubble(approvals) {
    if (!chat || !approvals.length) {
        removeApprovalChatBubble();
        return;
    }
    const signature = JSON.stringify(approvals.map((approval) => [
        approval.id || '',
        approval.request_id || '',
        approval.session_key || approval.session_id || '',
        approval.command || '',
        approval.description || approval.pattern_key || '',
        Boolean(approval.allow_session),
        Boolean(approval.allow_permanent),
        JSON.stringify(approval.always_patterns || {}),
        JSON.stringify(approval.choices || []),
    ]));
    const existing = document.getElementById('approval-chat-bubble');
    if (existing?.dataset.approvalSignature === signature) return;
    removeApprovalChatBubble();
    const stick = shouldStickToBottom(chat);
    const div = document.createElement('div');
    div.id = 'approval-chat-bubble';
    div.className = 'message assistant approval-chat-bubble';
    div.dataset.approvalSignature = signature;
    const count = approvals.length;
    div.innerHTML = `
        <div class="message-header approval-chat-header">
            <div class="message-title">Tool approval needed</div>
            <div class="message-meta">${count} pending</div>
        </div>
        ${approvals.map((approval, index) => {
            const session = approval.session_key || approval.session_id || '';
            const command = approval.command || '';
            const alwaysPatterns = approval.always_patterns && typeof approval.always_patterns === 'object'
                ? approval.always_patterns
                : {};
            const choices = new Set(Array.isArray(approval.choices) ? approval.choices.map(choice => String(choice).toLowerCase()) : []);
            const allowSession = approval.allow_session === true || choices.has('session') || choices.has('approve-session') || choices.has('allow-session');
            const allowPermanent = approval.allow_permanent === true || choices.has('always') || choices.has('permanent') || choices.has('approve-always');
            const hasScopedAlways = Boolean(alwaysPatterns.exact || alwaysPatterns.prefix);
            const desc = approval.description || approval.pattern_key || 'Tool approval required';
            const id = approval.id || `${session}:${approval.index || 0}`;
            return `<div class="approval-inline-card">
                <div class="approval-inline-main">
                    <strong>${escapeHtml(desc)}</strong>
                    <span>session ${escapeHtml(String(session).slice(0, 12))} · ${escapeHtml(id)}</span>
                </div>
                <div class="approval-inline-actions">
                    <button class="btn primary" type="button" data-approval-index="${index}" data-approval-decision="once">Approve Once</button>
                    ${allowSession ? `<button class="btn" type="button" data-approval-index="${index}" data-approval-decision="session" title="Approve matching requests for this Hermes session">Approve Session</button>` : ''}
                    ${alwaysPatterns.exact ? `<button class="btn" type="button" data-approval-index="${index}" data-approval-decision="always" data-approval-scope="exact">Always Exact</button>` : ''}
                    ${alwaysPatterns.prefix ? `<button class="btn" type="button" data-approval-index="${index}" data-approval-decision="always" data-approval-scope="prefix">Always Prefix</button>` : ''}
                    ${allowPermanent && !hasScopedAlways ? `<button class="btn" type="button" data-approval-index="${index}" data-approval-decision="always" title="Permanently approve this safety-rule class">Always This Type</button>` : ''}
                    <button class="btn danger" type="button" data-approval-index="${index}" data-approval-decision="deny">Deny</button>
                </div>
                ${alwaysPatterns.prefix ? `<div class="approval-inline-prefix">Prefix: <code>${escapeHtml(alwaysPatterns.prefix)}</code></div>` : ''}
                <div class="approval-inline-command">
                    <span>Command</span>
                    <pre>${escapeHtml(command || 'No command provided')}</pre>
                </div>
            </div>`;
        }).join('')}
        <div class="approval-inline-foot">Auto-approve controls live in the gear/options menu.</div>
    `;
    div.querySelectorAll('[data-approval-index]').forEach((button) => {
        button.addEventListener('click', async () => {
            const approval = approvals[Number(button.dataset.approvalIndex)];
            const session = approval?.session_key || approval?.session_id || '';
            const cardButtons = button.closest('.approval-inline-card')?.querySelectorAll('button') || [];
            cardButtons.forEach((item) => { item.disabled = true; });
            const resolved = await respondToApproval(session, button.dataset.approvalDecision || 'once', {
                requestId: approval?.request_id || '',
                alwaysScope: button.dataset.approvalScope || '',
            });
            if (!resolved) cardButtons.forEach((item) => { item.disabled = false; });
        });
    });
    chat.appendChild(div);
    scrollChatToBottom(false, stick);
}

function renderApprovals(approvals) {
    const summary = document.getElementById('approval-summary');
    if (summary) summary.textContent = approvals.length ? `${approvals.length} pending approval${approvals.length === 1 ? '' : 's'} — approve/deny in the chat bubble.` : 'No pending safety approvals.';
    renderApprovalChatBubble(approvals);
}

async function respondToApproval(sessionId, decision = 'once', options = {}) {
    if (!sessionId) {
        showToast('No approval session id found', true);
        return false;
    }
    try {
        const passphrase = currentApprovalPassphrase();
        if (approvalPassphraseRequired && !passphrase) {
            showToast('Approval passphrase required', true);
            const input = approvalPassphraseInput();
            if (input) input.focus();
            return false;
        }
        const response = await fetch('/api/approvals/respond', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: sessionId,
                request_id: options.requestId || undefined,
                decision,
                always_scope: options.alwaysScope || undefined,
                all: Boolean(options.all),
                passphrase,
            }),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok || !data.ok) {
            if (response.status === 403) {
                try { sessionStorage.removeItem(APPROVAL_PASSPHRASE_STORAGE_KEY); } catch (_) {}
                const input = approvalPassphraseInput();
                if (input) input.focus();
            }
            throw new Error(data.error || `HTTP ${response.status}`);
        }
        if (passphrase) cacheApprovalPassphrase(false);
        showToast(data.resolved ? `Approval ${decision}: ${data.resolved} command(s)` : 'No pending approval found');
        await refreshApprovals(true);
        return Boolean(data.resolved);
    } catch (error) {
        showToast(`Approval failed: ${error.message || error}`, true);
        return false;
    }
}

async function refreshApprovals(userInitiated = false) {
    if (approvalsInFlight) return;
    approvalsInFlight = true;
    try {
        const sessionId = activeApprovalSessionId();
        const url = sessionId ? `/api/approvals/pending?session_id=${encodeURIComponent(sessionId)}` : '/api/approvals/pending';
        const response = await fetch(url, { headers: { 'Accept': 'application/json' } });
        const data = await response.json().catch(() => ({}));
        if (!response.ok || !data.ok) throw new Error(data.error || `HTTP ${response.status}`);
        const approvals = Array.isArray(data.approvals) ? data.approvals : [];
        approvalPassphraseRequired = Boolean(data.passphrase_required);
        updateApprovalPassphraseStatus();
        renderApprovals(approvals);
        const ids = new Set(approvals.map(a => a.id || `${a.session_key}:${a.index || 0}`));
        approvals.forEach((approval) => {
            const id = approval.id || `${approval.session_key}:${approval.index || 0}`;
            if (!lastApprovalIds.has(id)) {
                const description = approval.description || approval.pattern_key || 'Tool command';
                showToast(`Approval needed: ${description}`);
                sendDashboardNotification('approvals', 'Hermes approval required', description, {
                    key: `approval:${id}`,
                    tag: `hermes-approval-${id}`,
                    panel: 'chat',
                });
            }
        });
        lastApprovalIds = ids;
        updateAutoApprovalStatus();
        if (autoApprovalUntil > Date.now() && approvals.length) {
            for (const approval of approvals) {
                await respondToApproval(approval.session_key || approval.session_id, autoApprovalDecision);
            }
        } else if (userInitiated && !approvals.length) {
            showToast('No pending approvals');
        }
    } catch (error) {
        const summary = document.getElementById('approval-summary');
        if (summary) summary.textContent = `Approval polling unavailable: ${error.message || error}`;
        if (userInitiated) showToast(`Approval refresh failed: ${error.message || error}`, true);
    } finally {
        approvalsInFlight = false;
    }
}

function startApprovalPolling() {
    hydrateApprovalPassphrase();
    if (approvalPollTimer) clearInterval(approvalPollTimer);
    refreshApprovals(false);
    approvalPollTimer = setInterval(() => refreshApprovals(false), APPROVAL_POLL_MS);
    setInterval(updateAutoApprovalStatus, 1000);
}

function safeBotColor(value, fallback = '#60a5fa') {
    return /^#[0-9a-f]{6}$/i.test(String(value || '')) ? value : fallback;
}

function firstVisibleInitial(value, fallback = '?') {
    const character = Array.from(String(value || '').trim()).find(char => !/\s/u.test(char));
    return (character || fallback).toLocaleUpperCase();
}

function safeAvatarUrl(value, version) {
    const raw = String(value || '').trim();
    if (!raw) return '';
    try {
        const url = new URL(raw, window.location.origin);
        if (!['http:', 'https:'].includes(url.protocol)) return '';
        if (version !== null && typeof version !== 'undefined' && String(version)) {
            url.searchParams.set('v', String(version));
        }
        return url.href;
    } catch (_error) {
        return '';
    }
}

function botTooltip(identity = {}) {
    const name = identity.display_name || identity.name || 'Hermes';
    const handle = identity.name && identity.name !== 'all-bots' ? `@${identity.name}` : '';
    const description = String(identity.description || '').trim();
    const model = [identity.provider, identity.model].filter(Boolean).join(' / ');
    const skills = Number.isFinite(Number(identity.skill_count)) ? `${Number(identity.skill_count)} skills` : '';
    return [handle ? `${name} (${handle})` : name, description, model ? `Model: ${model}` : '', skills]
        .filter(Boolean)
        .join(' | ');
}

function avatarHtml(identity = {}, options = {}) {
    const label = identity.display_name || identity.name || options.fallbackLabel || 'Hermes';
    const color = safeBotColor(identity.color, options.fallbackColor || '#60a5fa');
    const url = safeAvatarUrl(identity.avatar_url, identity.avatar_version);
    const classes = ['bot-avatar', options.className || ''].filter(Boolean).join(' ');
    const tooltip = options.tooltip || botTooltip(identity);
    return `<span class="${classes}" style="--bot-color:${color}" title="${escapeHtml(tooltip)}"${options.decorative ? ' aria-hidden="true"' : ` role="img" aria-label="${escapeHtml(label)} avatar"`}>
        <span class="bot-avatar-initial">${escapeHtml(firstVisibleInitial(label))}</span>
        ${url ? `<img src="${escapeHtml(url)}" alt="" decoding="async">` : ''}
    </span>`;
}

function bindAvatarFallbacks(root = document) {
    root.querySelectorAll?.('.bot-avatar img:not([data-avatar-bound])').forEach((image) => {
        image.dataset.avatarBound = 'true';
        image.addEventListener('load', () => image.classList.add('is-loaded'), { once: true });
        image.addEventListener('error', () => {
            image.remove();
        }, { once: true });
        if (image.complete && image.naturalWidth > 0) image.classList.add('is-loaded');
    });
}

function defaultBotIdentity() {
    return botRegistry.find(bot => bot.is_default || bot.name === 'default') || {
        name: 'default', display_name: 'Hermes', color: '#ffd700',
    };
}

function identityForRoom(roomId = activeChatRoomId) {
    if (roomId === 'shared') return { name: 'all-bots', display_name: 'All Bots', color: '#a78bfa', description: 'A bounded shared room where profiles can answer and ask one another questions.' };
    if (roomId === 'main') return defaultBotIdentity();
    return botForRoom(roomId) || { name: profileForRoom(roomId), display_name: profileForRoom(roomId), color: '#60a5fa' };
}

function botForRoom(roomId = activeChatRoomId) {
    if (!String(roomId).startsWith('bot:')) return null;
    const name = String(roomId).slice(4);
    return botRegistry.find(bot => bot.name === name) || null;
}

function profileForRoom(roomId = activeChatRoomId) {
    return String(roomId).startsWith('bot:') ? String(roomId).slice(4) : 'default';
}

function sharedMessageHtml(entry) {
    const role = entry?.role === 'user' ? 'user' : 'assistant';
    const profile = entry?.bot || entry?.profile || entry?.name || entry?.speaker || (role === 'user' ? 'You' : 'default');
    const bot = botRegistry.find(item => item.name === profile || item.display_name === profile);
    const identity = role === 'user'
        ? { name: 'you', display_name: 'You', color: '#ffd700' }
        : { ...(bot || {}), name: bot?.name || profile, display_name: entry?.display_name || entry?.speaker || bot?.display_name || profile || 'Hermes', color: entry?.color || bot?.color };
    const color = safeBotColor(identity.color, role === 'user' ? '#ffd700' : '#60a5fa');
    const content = typeof entry?.content === 'string' ? entry.content : '';
    return `<div class="message ${role} shared-message" style="--speaker-color:${color}">
        <div class="shared-message-speaker">${avatarHtml(identity, { className: 'bot-avatar-message', decorative: true })}<span class="shared-speaker-name">${escapeHtml(identity.display_name)}</span>${role === 'assistant' && profile ? `<small>@${escapeHtml(profile)}</small>` : ''}</div>
        <div class="shared-message-content">${formatMessageContent(content)}</div>
    </div>`;
}

function renderSharedConversation() {
    chat.innerHTML = conversation.map(sharedMessageHtml).join('');
    bindAvatarFallbacks(chat);
    scrollChatToBottom(true);
}

function renderConversation() {
    if (activeChatRoomId === 'shared') {
        renderSharedConversation();
        return;
    }
    const rows = conversation.filter((msg) => {
        const hasRenderableAssistantState = msg.role === 'assistant' && (
            (typeof msg.content === 'string' && msg.content.length > 0)
            || (Array.isArray(msg.events) && msg.events.length > 0)
            || (Array.isArray(msg.tools) && msg.tools.length > 0)
            || (msg.trace && (
                (Array.isArray(msg.trace.toolNodes) && msg.trace.toolNodes.length > 0)
                || (Array.isArray(msg.trace.items) && msg.trace.items.length > 0)
                || msg.trace.contentNode
            ))
        );
        return msg.role === 'user' || hasRenderableAssistantState;
    });
    chat.innerHTML = renderTranscriptSegments(buildTranscriptRenderSegments(rows), {
        assistant: (body, segment) => {
            const source = segment.message || segment.updates?.[0]?.message || {};
            const normalized = segment.normalized || segment.updates?.[0]?.normalized || normalizeAssistantMessage(source);
            const roomBot = botForRoom();
            const fallbackBot = roomBot || (activeChatRoomId === 'main' ? defaultBotIdentity() : null);
            const identifiedSource = fallbackBot && !source.bot ? { ...source, bot: fallbackBot.name } : source;
            return `<div class="message assistant">${renderAssistantMessageShell({ ...identifiedSource, traceNode: null }, normalized, body)}</div>`;
        },
        boundary: (row) => `<div class="message ${escapeHtml(row?.role || 'user')}">${renderUserMessageContent(row?.content || '')}</div>`,
    });
    bindAvatarFallbacks(chat);
    bindToolCardInteractions(chat);
    highlightToolCode(chat);
    renderActiveRunProjection();
    log('inf', `Restored ${conversation.length} messages from cache`);
}

function renderActiveRunProjection() {
    const activeRun = getActiveRun();
    if (!activeRun?.assistantState) return null;
    const existing = Array.from(chat.querySelectorAll('[data-chat-run-id]'))
        .find(node => node.dataset.chatRunId === activeRun.runId);
    if (existing) return existing;
    const div = addMessage('assistant', activeRun.assistantState, false);
    div.dataset.chatRunId = activeRun.runId;
    return div;
}

function makeExecutionNodeId(kind, sessionId, value, fallbackIndex = 0) {
    const cleanedSession = String(sessionId || 'session').replace(/[^A-Za-z0-9_-]/g, '_');
    const cleanedValue = String(value || `${kind}_${fallbackIndex}`).replace(/[^A-Za-z0-9_-]/g, '_');
    return `${kind}-${cleanedSession}-${cleanedValue}`;
}

function normalizeExecutionTarget(target) {
    if (!target || typeof target !== 'object') return null;
    const kind = String(target.kind || '').trim();
    const id = String(target.id || '').trim();
    if (!kind || !id) return null;
    return { kind, id };
}

function routeForExecutionTarget(sessionId, target) {
    const normalized = normalizeExecutionTarget(target);
    if (!sessionId || !normalized) return null;
    return `sessions/detail/${encodeURIComponent(sessionId)}/${encodeURIComponent(normalized.kind)}/${encodeURIComponent(normalized.id)}`;
}

function normalizeActivityTarget(item) {
    const explicit = normalizeExecutionTarget(item?.target);
    if (explicit) return explicit;
    if (item?.tool_call_id) return { kind: 'tool', id: item.tool_call_id };
    return null;
}

function summarizeParallelGroupLabel(tools) {
    const names = Array.from(new Set((tools || []).map(tool => tool?.name || 'tool')));
    if (!names.length) return 'Parallel tool batch';
    if (names.length === 1) return `${names[0]} batch: ${tools.length} parallel calls`;
    if (names.length <= 3) return `${names.join(', ')} batch`;
    return `${tools.length} parallel calls`;
}

function createAssistantTraceState(seed = {}) {
    const traceNode = seed.traceNode || null;
    const stepNode = traceNode?.kind === 'assistant_step'
        ? traceNode
        : (seed.trace?.stepNode?.kind === 'assistant_step' ? seed.trace.stepNode : null);
    return {
        role: 'assistant',
        content: '',
        tools: [],
        events: [],
        usage: seed.usage || null,
        last_prompt_tokens: seed.last_prompt_tokens || 0,
        prompt_breakdown: Array.isArray(seed.prompt_breakdown) ? seed.prompt_breakdown.map(item => item && typeof item === 'object' ? { ...item } : item) : [],
        traceNode: traceNode || stepNode || null,
        trace: {
            sessionId: seed.sessionId || traceNode?.session_id || seed.trace?.sessionId || null,
            stepNode: stepNode || null,
            contentNode: seed.trace?.contentNode || stepNode?.payload?.contentNode || null,
            toolNodes: Array.isArray(seed.trace?.toolNodes)
                ? seed.trace.toolNodes
                : (Array.isArray(stepNode?.payload?.toolNodes) ? stepNode.payload.toolNodes : []),
            orphanNodes: Array.isArray(seed.trace?.orphanNodes)
                ? seed.trace.orphanNodes
                : (Array.isArray(stepNode?.payload?.orphanNodes) ? stepNode.payload.orphanNodes : []),
            items: Array.isArray(seed.trace?.items)
                ? seed.trace.items
                : (Array.isArray(stepNode?.payload?.items) ? stepNode.payload.items : []),
            toolIndexByCallId: seed.trace?.toolIndexByCallId && typeof seed.trace.toolIndexByCallId === 'object'
                ? { ...seed.trace.toolIndexByCallId }
                : (stepNode?.payload?.toolIndexByCallId && typeof stepNode.payload.toolIndexByCallId === 'object'
                    ? { ...stepNode.payload.toolIndexByCallId }
                    : {}),
            contentOrder: seed.trace?.contentOrder === 'after_tools' ? 'after_tools' : 'before_tools',
            pendingDelegateChildren: seed.trace?.pendingDelegateChildren && typeof seed.trace.pendingDelegateChildren === 'object'
                ? JSON.parse(JSON.stringify(seed.trace.pendingDelegateChildren))
                : {},
            contentSequence: Number.isInteger(seed.trace?.contentSequence) ? seed.trace.contentSequence : 0,
            toolSequence: Number.isInteger(seed.trace?.toolSequence) ? seed.trace.toolSequence : 0,
            orphanSequence: Number.isInteger(seed.trace?.orphanSequence) ? seed.trace.orphanSequence : 0,
        },
    };
}

function buildAssistantContentNode(sessionId, stepNode, message, sortKey, fallbackIndex = 0) {
    return {
        kind: 'assistant_content',
        node_id: makeExecutionNodeId('content', sessionId, message?.id ?? `assistant_${fallbackIndex}`, fallbackIndex),
        dom_id: null,
        session_id: sessionId,
        timestamp: message?.timestamp || null,
        sort_key: sortKey,
        parent_node_id: stepNode?.node_id || null,
        call_id: null,
        label: 'assistant content',
        payload: { text: message?.content || '' },
    };
}

function ensureAssistantTraceCollections(state) {
    if (!state.trace || typeof state.trace !== 'object') {
        state.trace = {};
    }
    const trace = state.trace;
    if (!Array.isArray(trace.toolNodes)) trace.toolNodes = [];
    if (!Array.isArray(trace.orphanNodes)) trace.orphanNodes = [];
    if (!Array.isArray(trace.items)) trace.items = [];
    if (!trace.toolIndexByCallId || typeof trace.toolIndexByCallId !== 'object') {
        trace.toolIndexByCallId = {};
    }
    if (!trace.pendingDelegateChildren || typeof trace.pendingDelegateChildren !== 'object') {
        trace.pendingDelegateChildren = {};
    }
    if (!Number.isInteger(trace.contentSequence)) trace.contentSequence = 0;
    if (!Number.isInteger(trace.toolSequence)) trace.toolSequence = 0;
    if (!Number.isInteger(trace.orphanSequence)) trace.orphanSequence = 0;
    return trace;
}

function buildAssistantTraceContentSegmentNode(state, details = {}) {
    const trace = ensureAssistantTraceCollections(state);
    const sessionId = details.sessionId || trace.sessionId || state.traceNode?.session_id || 'live';
    const stepNode = trace.stepNode || state.traceNode || null;
    const sequence = Number.isInteger(details.sequence) ? details.sequence : trace.contentSequence++;
    return buildAssistantContentNode(
        sessionId,
        stepNode,
        {
            id: details.id || `segment_${sequence}`,
            content: details.text || '',
            timestamp: Object.prototype.hasOwnProperty.call(details, 'timestamp') ? details.timestamp : null,
        },
        Object.prototype.hasOwnProperty.call(details, 'sortKey') ? details.sortKey : null,
        sequence,
    );
}

function collectAssistantTraceContentText(trace, fallbackText = '') {
    const items = Array.isArray(trace?.items) ? trace.items : [];
    if (items.length) {
        return items
            .filter(node => node?.kind === 'assistant_content')
            .map(node => node?.payload?.text || '')
            .join('');
    }
    return fallbackText || trace?.contentNode?.payload?.text || '';
}

function populateAssistantTraceItemsFromLegacyState(state) {
    const trace = ensureAssistantTraceCollections(state);
    if (trace.items.length) return;
    const items = [];
    const text = state?.content || trace.contentNode?.payload?.text || '';
    const contentNode = text
        ? (trace.contentNode || buildAssistantTraceContentSegmentNode(state, { text, sortKey: trace.stepNode?.sort_key || null }))
        : null;
    if (contentNode?.payload) contentNode.payload.text = text;
    if (contentNode && (trace.contentOrder !== 'after_tools' || !trace.toolNodes.length)) {
        items.push(contentNode);
    }
    trace.toolNodes.forEach(node => items.push(node));
    if (contentNode && trace.contentOrder === 'after_tools' && trace.toolNodes.length) {
        items.push(contentNode);
    }
    trace.orphanNodes.forEach(node => items.push(node));
    trace.items = items;
}

function rebuildAssistantTraceToolIndex(trace) {
    trace.toolIndexByCallId = {};
    trace.toolNodes.forEach((node, index) => {
        const callId = node?.payload?.tool?.call_id || node?.call_id || '';
        if (callId) trace.toolIndexByCallId[callId] = index;
    });
}

function removeAssistantTraceNode(nodes, targetNode) {
    if (!Array.isArray(nodes) || !targetNode) return;
    const index = nodes.indexOf(targetNode);
    if (index >= 0) nodes.splice(index, 1);
}

function normalizeAssistantTraceToolIdentityValue(value) {
    if (value === null || value === undefined || value === '') return '';
    if (typeof value === 'string') {
        const trimmed = value.trim();
        if (!trimmed) return '';
        try {
            return JSON.stringify(JSON.parse(trimmed));
        } catch {
            return trimmed;
        }
    }
    if (typeof value === 'object') {
        try {
            return JSON.stringify(value);
        } catch {
            return summarizeValue(value, 500);
        }
    }
    return String(value);
}

function normalizeAssistantTracePreviewText(value) {
    const normalized = normalizeAssistantTraceToolIdentityValue(value)
        .toLowerCase()
        .replace(/^[^:]+:\s*/, '')
        .replace(/^['"]|['"]$/g, '')
        .replace(/\.\.\.$/, '')
        .replace(/\s+/g, ' ')
        .trim();
    return normalized;
}

function collectAssistantTraceScalarArgumentValues(value, bucket = []) {
    if (value === null || value === undefined || value === '') return bucket;
    if (typeof value === 'string') {
        const trimmed = value.trim();
        if (!trimmed) return bucket;
        try {
            const parsed = JSON.parse(trimmed);
            if (parsed && typeof parsed === 'object') {
                return collectAssistantTraceScalarArgumentValues(parsed, bucket);
            }
        } catch {
            // Keep raw string below.
        }
        bucket.push(trimmed);
        return bucket;
    }
    if (Array.isArray(value)) {
        value.forEach(item => collectAssistantTraceScalarArgumentValues(item, bucket));
        return bucket;
    }
    if (typeof value === 'object') {
        Object.values(value).forEach(item => collectAssistantTraceScalarArgumentValues(item, bucket));
        return bucket;
    }
    bucket.push(String(value));
    return bucket;
}

function assistantTracePreviewMatchesToolArguments(previewValue, toolArguments) {
    const preview = normalizeAssistantTracePreviewText(previewValue);
    if (!preview) return false;
    const candidates = collectAssistantTraceScalarArgumentValues(toolArguments)
        .map(value => normalizeAssistantTracePreviewText(value))
        .filter(Boolean);
    return candidates.some((candidate) => candidate === preview || candidate.startsWith(preview));
}

function findPromotableProgressDiagnosticNode(state, toolEvent) {
    const trace = ensureAssistantTraceCollections(state);
    const orphanNodes = Array.isArray(trace.orphanNodes) ? trace.orphanNodes : [];
    const toolName = toolEvent?.name || '';
    if (!toolName) return null;
    const normalizedArgs = normalizeAssistantTraceToolIdentityValue(toolEvent.arguments);
    const candidates = orphanNodes.filter((node) => {
        if (node?.payload?.reason !== 'unmatched_tool_progress') return false;
        const orphanTool = node?.payload?.tool || {};
        if ((orphanTool.name || '') !== toolName) return false;
        if (orphanTool.output) return false;
        if (orphanTool.call_id) return false;
        return true;
    });
    if (!candidates.length) return null;
    if (normalizedArgs) {
        const exact = candidates.filter((node) => normalizeAssistantTraceToolIdentityValue(node?.payload?.tool?.arguments) === normalizedArgs);
        if (exact.length === 1) return exact[0];
        const adjacent = trace.items[trace.items.length - 1] || null;
        if (
            adjacent
            && candidates.includes(adjacent)
            && assistantTracePreviewMatchesToolArguments(adjacent?.payload?.tool?.arguments, toolEvent.arguments)
        ) {
            return adjacent;
        }
        return null;
    }
    return candidates.length === 1 ? candidates[0] : null;
}

function promoteAssistantDiagnosticToToolNode(state, diagnosticNode, tool, options = {}) {
    const trace = ensureAssistantTraceCollections(state);
    const preserveOutput = options.preserveOutput === true;
    const preserveProgress = options.preserveProgress !== false;
    const normalizedTool = {
        ...(diagnosticNode?.payload?.tool || {}),
        ...tool,
        progress: normalizeToolProgressEntries(tool?.progress || diagnosticNode?.payload?.tool?.progress),
    };
    if (preserveOutput && hasCapturedToolOutput(diagnosticNode?.payload?.tool)) {
        normalizedTool.output = diagnosticNode.payload.tool.output;
    }
    if (preserveProgress && (!Array.isArray(normalizedTool.progress) || !normalizedTool.progress.length)) {
        normalizedTool.progress = normalizeToolProgressEntries(diagnosticNode?.payload?.tool?.progress);
    }
    diagnosticNode.kind = 'tool_run';
    diagnosticNode.parent_node_id = trace.stepNode?.node_id || state.traceNode?.node_id || null;
    diagnosticNode.call_id = normalizedTool.call_id || diagnosticNode.call_id || null;
    diagnosticNode.label = normalizedTool.name || diagnosticNode.label || 'tool';
    diagnosticNode.session_id = diagnosticNode.session_id || trace.sessionId || state.traceNode?.session_id || 'live';
    diagnosticNode.timestamp = Object.prototype.hasOwnProperty.call(options, 'timestamp') ? options.timestamp : diagnosticNode.timestamp;
    diagnosticNode.sort_key = Object.prototype.hasOwnProperty.call(options, 'sortKey') ? options.sortKey : diagnosticNode.sort_key;
    if (options.node?.dom_id && !diagnosticNode.dom_id) diagnosticNode.dom_id = options.node.dom_id;
    diagnosticNode.payload = {
        tool: normalizedTool,
    };
    if (Object.prototype.hasOwnProperty.call(options, 'sourceMessage')) {
        diagnosticNode.payload.sourceMessage = options.sourceMessage;
    }
    if (Object.prototype.hasOwnProperty.call(options, 'toolRow')) {
        diagnosticNode.payload.toolRow = options.toolRow;
    }
    removeAssistantTraceNode(trace.orphanNodes, diagnosticNode);
    if (!trace.toolNodes.includes(diagnosticNode)) {
        trace.toolNodes.push(diagnosticNode);
    }
    return diagnosticNode;
}

function buildAssistantTraceToolNode(state, tool, options = {}) {
    const trace = state.trace || {};
    const sessionId = options.sessionId || trace.sessionId || state.traceNode?.session_id || 'live';
    const stepNode = trace.stepNode || state.traceNode || null;
    const sequence = Number.isInteger(options.sequence) ? options.sequence : (trace.toolSequence || 0);
    if (!Number.isInteger(options.sequence)) {
        trace.toolSequence = sequence + 1;
    }
    const normalizedTool = {
        ...tool,
        call_id: tool.call_id || tool.id || `${stepNode?.node_id || 'tool'}_${sequence}`,
        name: tool.name || 'tool',
        arguments: tool.arguments || '',
        progress: normalizeToolProgressEntries(tool.progress),
    };
    const baseNode = options.node && typeof options.node === 'object'
        ? {
            ...options.node,
            payload: { ...(options.node.payload || {}) },
        }
        : {
            kind: 'tool_run',
            node_id: makeExecutionNodeId('tool', sessionId, normalizedTool.call_id, sequence),
            dom_id: null,
            session_id: sessionId,
            timestamp: options.timestamp || null,
            sort_key: options.sortKey || null,
            parent_node_id: stepNode?.node_id || null,
            call_id: normalizedTool.call_id,
            label: normalizedTool.name,
            payload: {},
        };
    if (!Object.prototype.hasOwnProperty.call(baseNode, 'dom_id')) {
        baseNode.dom_id = null;
    }
    baseNode.kind = 'tool_run';
    baseNode.session_id = baseNode.session_id || sessionId;
    baseNode.timestamp = Object.prototype.hasOwnProperty.call(options, 'timestamp') ? options.timestamp : (baseNode.timestamp || null);
    baseNode.sort_key = Object.prototype.hasOwnProperty.call(options, 'sortKey') ? options.sortKey : (baseNode.sort_key || null);
    baseNode.parent_node_id = baseNode.parent_node_id || stepNode?.node_id || null;
    baseNode.call_id = normalizedTool.call_id;
    baseNode.label = normalizedTool.name;
    baseNode.payload.tool = normalizedTool;
    if (Object.prototype.hasOwnProperty.call(options, 'sourceMessage')) {
        baseNode.payload.sourceMessage = options.sourceMessage;
    }
    if (Object.prototype.hasOwnProperty.call(options, 'toolRow')) {
        baseNode.payload.toolRow = options.toolRow;
    }
    return baseNode;
}

function buildAssistantTraceDiagnosticNode(state, details = {}) {
    const trace = state.trace || {};
    const sessionId = details.sessionId || trace.sessionId || state.traceNode?.session_id || 'live';
    const sequence = Number.isInteger(details.sequence) ? details.sequence : (trace.orphanSequence || 0);
    if (!Number.isInteger(details.sequence)) {
        trace.orphanSequence = sequence + 1;
    }
    const tool = {
        call_id: details.tool?.call_id || '',
        name: details.tool?.name || 'tool',
        arguments: details.tool?.arguments || '',
        progress: normalizeToolProgressEntries(details.tool?.progress),
    };
    if (Object.prototype.hasOwnProperty.call(details.tool || {}, 'output')) {
        tool.output = details.tool.output;
    }
    const baseNode = details.node && typeof details.node === 'object'
        ? {
            ...details.node,
            payload: { ...(details.node.payload || {}) },
        }
        : {
            kind: 'diagnostic_artifact',
            node_id: makeExecutionNodeId('orphan', sessionId, tool.call_id || `tool_${sequence}`, sequence),
            dom_id: null,
            session_id: sessionId,
            timestamp: details.timestamp || null,
            sort_key: details.sortKey || null,
            parent_node_id: null,
            call_id: tool.call_id || null,
            label: details.label || `Unmatched ${tool.name} output`,
            payload: {},
        };
    baseNode.kind = 'diagnostic_artifact';
    baseNode.session_id = baseNode.session_id || sessionId;
    baseNode.timestamp = Object.prototype.hasOwnProperty.call(details, 'timestamp') ? details.timestamp : (baseNode.timestamp || null);
    baseNode.sort_key = Object.prototype.hasOwnProperty.call(details, 'sortKey') ? details.sortKey : (baseNode.sort_key || null);
    baseNode.call_id = tool.call_id || baseNode.call_id || null;
    baseNode.label = details.label || baseNode.label || `Unmatched ${tool.name} output`;
    baseNode.payload.message = Object.prototype.hasOwnProperty.call(details, 'message') ? details.message : (baseNode.payload.message || null);
    baseNode.payload.tool = tool;
    baseNode.payload.orphan = true;
    baseNode.payload.reason = details.reason || baseNode.payload.reason || 'unmatched_tool_output';
    return baseNode;
}

function findAssistantToolNode(state, callId) {
    const trace = state?.trace;
    if (!callId || !trace?.toolNodes) return null;
    const indexed = trace.toolIndexByCallId && Object.prototype.hasOwnProperty.call(trace.toolIndexByCallId, callId)
        ? trace.toolNodes[trace.toolIndexByCallId[callId]]
        : null;
    if (indexed) return indexed;
    const index = trace.toolNodes.findIndex(node => node?.payload?.tool?.call_id === callId);
    if (index >= 0) {
        trace.toolIndexByCallId[callId] = index;
        return trace.toolNodes[index];
    }
    return null;
}

function findAssistantDiagnosticNode(state, matcher) {
    const nodes = Array.isArray(state?.trace?.orphanNodes) ? state.trace.orphanNodes : [];
    for (let i = nodes.length - 1; i >= 0; i--) {
        if (matcher(nodes[i])) return nodes[i];
    }
    return null;
}

function syncAssistantTraceStepNode(state) {
    const stepNode = state?.trace?.stepNode;
    if (!stepNode?.payload) return;
    stepNode.payload.contentNode = state.trace.contentNode || null;
    stepNode.payload.toolNodes = state.trace.toolNodes || [];
    stepNode.payload.orphanNodes = state.trace.orphanNodes || [];
    stepNode.payload.items = state.trace.items || [];
    stepNode.payload.toolIndexByCallId = state.trace.toolIndexByCallId || {};
}

function buildAssistantEventsFromTraceState(state) {
    const items = Array.isArray(state?.trace?.items) ? state.trace.items : [];
    if (items.length) {
        return groupParallelToolEvents(items.map((node) => {
            if (node?.kind === 'assistant_content') {
                const text = node?.payload?.text || '';
                return text ? { type: 'content', text, node } : null;
            }
            if (node?.kind === 'tool_run') {
                const tool = node?.payload?.tool || {};
                return {
                    type: hasCapturedToolOutput(tool) ? 'tool_output' : 'tool_call',
                    tool,
                    node,
                };
            }
            if (node?.kind === 'parallel_group') {
                return { type: 'parallel_group', node };
            }
            if (node?.kind === 'diagnostic_artifact') {
                return { type: 'diagnostic', node };
            }
            return null;
        }).filter(Boolean));
    }
    const events = [];
    const contentNode = state?.trace?.contentNode || null;
    const text = state?.content || contentNode?.payload?.text || '';
    const toolNodes = Array.isArray(state?.trace?.toolNodes) ? state.trace.toolNodes : [];
    const orphanNodes = Array.isArray(state?.trace?.orphanNodes) ? state.trace.orphanNodes : [];
    const contentEvent = text ? { type: 'content', text, node: contentNode } : null;
    const contentAfterTools = state?.trace?.contentOrder === 'after_tools' && toolNodes.length > 0;
    if (contentEvent && !contentAfterTools) {
        events.push(contentEvent);
    }
    if (toolNodes.length > 1) {
        events.push({
            type: 'parallel_group',
            node: {
                kind: 'parallel_group',
                payload: {
                    label: summarizeParallelGroupLabel(toolNodes.map(node => node?.payload?.tool)),
                    toolNodes,
                },
            },
        });
    } else {
        toolNodes.forEach((node) => {
            const tool = node?.payload?.tool || {};
            events.push({
                type: hasCapturedToolOutput(tool) ? 'tool_output' : 'tool_call',
                tool,
                node,
            });
        });
    }
    if (contentEvent && contentAfterTools) {
        events.push(contentEvent);
    }
    orphanNodes.forEach((node) => {
        events.push({ type: 'diagnostic', node });
    });
    return events;
}

function syncAssistantTraceDerivedFields(state) {
    const trace = ensureAssistantTraceCollections(state);
    if (!trace.items.length) {
        populateAssistantTraceItemsFromLegacyState(state);
    }
    if (trace.items.length) {
        trace.toolNodes = trace.items.flatMap((node) => {
            if (node?.kind === 'tool_run') return [node];
            if (node?.kind === 'parallel_group' && Array.isArray(node?.payload?.toolNodes)) {
                return node.payload.toolNodes.filter(toolNode => toolNode?.kind === 'tool_run');
            }
            return [];
        });
        trace.orphanNodes = trace.items.filter(node => node?.kind === 'diagnostic_artifact' && node?.payload?.orphan);
        trace.contentNode = trace.items.find(node => node?.kind === 'assistant_content') || null;
    }
    rebuildAssistantTraceToolIndex(trace);
    if (state.trace.contentOrder !== 'after_tools') {
        state.trace.contentOrder = 'before_tools';
    }
    syncAssistantTraceStepNode(state);
    state.content = collectAssistantTraceContentText(trace, state.content || '');
    state.tools = trace.toolNodes.map(node => node.payload.tool);
    state.events = buildAssistantEventsFromTraceState(state);
    return state;
}

function appendAssistantTraceDiagnostic(state, details = {}) {
    const existingByCallId = details.tool?.call_id
        ? findAssistantDiagnosticNode(state, node => node?.payload?.tool?.call_id === details.tool.call_id)
        : null;
    if (existingByCallId) {
        existingByCallId.payload.tool = {
            ...(existingByCallId.payload.tool || {}),
            ...(details.tool || {}),
            progress: normalizeToolProgressEntries(
                Object.prototype.hasOwnProperty.call(details.tool || {}, 'progress')
                    ? details.tool.progress
                    : existingByCallId.payload.tool?.progress,
            ),
        };
        existingByCallId.label = details.label || existingByCallId.label;
        existingByCallId.payload.reason = details.reason || existingByCallId.payload.reason;
        if (Object.prototype.hasOwnProperty.call(details, 'message')) {
            existingByCallId.payload.message = details.message;
        }
        return syncAssistantTraceDerivedFields(state);
    }
    const node = buildAssistantTraceDiagnosticNode(state, details);
    state.trace.orphanNodes.push(node);
    state.trace.items.push(node);
    return syncAssistantTraceDerivedFields(state);
}

function reduceAssistantTraceEvent(state, event, options = {}) {
    if (!state || !event || typeof event !== 'object') return state;
    const trace = ensureAssistantTraceCollections(state);

    if (event.type === 'content') {
        const nextText = event.text || '';
        if (event.replace && !trace.toolNodes.length) {
            trace.contentOrder = 'before_tools';
        }
        if (event.replace) {
            trace.items = trace.items.filter(node => node?.kind !== 'assistant_content');
            trace.contentNode = null;
        }
        const lastItem = trace.items[trace.items.length - 1] || null;
        const reuseLastContentNode = !event.replace
            && lastItem?.kind === 'assistant_content'
            && (!event.node || event.node === lastItem || event.node?.node_id === lastItem.node_id);
        let contentNode = reuseLastContentNode ? lastItem : null;
        if (!contentNode && nextText) {
            contentNode = event.node?.kind === 'assistant_content'
                ? event.node
                : buildAssistantTraceContentSegmentNode(state, {
                    text: '',
                    timestamp: event.timestamp,
                    sortKey: event.sortKey,
                    sessionId: trace.sessionId,
                });
            trace.items.push(contentNode);
        }
        if (contentNode?.payload) {
            contentNode.payload.text = event.replace
                ? nextText
                : `${contentNode.payload.text || ''}${nextText}`;
        }
        trace.contentNode = trace.items.find(node => node?.kind === 'assistant_content') || contentNode || null;
        return syncAssistantTraceDerivedFields(state);
    }

    if (event.type === 'meta') {
        if (event.usage) state.usage = event.usage;
        if (event.last_prompt_tokens) state.last_prompt_tokens = event.last_prompt_tokens;
        if (Array.isArray(event.prompt_breakdown)) {
            state.prompt_breakdown = event.prompt_breakdown.map(item => item && typeof item === 'object' ? { ...item } : item);
        }
        return syncAssistantTraceDerivedFields(state);
    }

    if (event.type === 'diagnostic') {
        return appendAssistantTraceDiagnostic(state, {
            ...event,
            tool: event.tool || event.node?.payload?.tool || {},
            node: event.node || null,
        });
    }

    if (event.type === 'parallel_group') {
        const sourceNode = event.node && typeof event.node === 'object' ? event.node : {};
        const sourceTools = Array.isArray(sourceNode?.payload?.toolNodes)
            ? sourceNode.payload.toolNodes
            : (Array.isArray(event.toolNodes) ? event.toolNodes : []);
        const groupNode = {
            ...sourceNode,
            kind: 'parallel_group',
            payload: {
                ...(sourceNode.payload || {}),
                label: sourceNode?.payload?.label || event.label || summarizeParallelGroupLabel(
                    sourceTools.map(item => item?.payload?.tool || item?.tool || item),
                ),
                toolNodes: sourceTools.map((item, index) => {
                    if (item?.kind === 'tool_run' && item?.payload?.tool) return item;
                    const tool = item?.payload?.tool || item?.tool || item || {};
                    return buildAssistantTraceToolNode(state, tool, {
                        node: item?.kind === 'tool_run' ? item : null,
                        sequence: index,
                        sessionId: trace.sessionId,
                    });
                }),
            },
        };
        if (!trace.items.some(node => node === groupNode || (groupNode.node_id && node?.node_id === groupNode.node_id))) {
            trace.items.push(groupNode);
        }
        return syncAssistantTraceDerivedFields(state);
    }

    const callId = event.call_id
        || event.tool_call_id
        || event.arguments?.call_id
        || event.arguments?.tool_call_id
        || event.tool?.call_id
        || event.tool?.tool_call_id
        || '';
    const hasToolArguments = Object.prototype.hasOwnProperty.call(event, 'arguments')
        || Object.prototype.hasOwnProperty.call(event.tool || {}, 'arguments');
    const toolEvent = {
        call_id: callId,
        name: event.name || event.tool?.name || 'tool',
        progress: Object.prototype.hasOwnProperty.call(event, 'progress') ? event.progress : (event.tool?.progress || []),
    };
    if (hasToolArguments || event.type === 'tool_call') {
        toolEvent.arguments = Object.prototype.hasOwnProperty.call(event, 'arguments')
            ? event.arguments
            : (event.tool?.arguments || '');
    }
    ['status', 'error', 'timestamp', 'started_at', 'completed_at', 'duration_ms', 'metrics'].forEach((key) => {
        if (Object.prototype.hasOwnProperty.call(event, key)) toolEvent[key] = event[key];
        else if (Object.prototype.hasOwnProperty.call(event.tool || {}, key)) toolEvent[key] = event.tool[key];
    });
    if (Object.prototype.hasOwnProperty.call(event, 'output')) {
        toolEvent.output = event.output;
    } else if (Object.prototype.hasOwnProperty.call(event.tool || {}, 'output')) {
        toolEvent.output = event.tool.output;
    }

    if (event.type === 'tool_call') {
        const existingNode = findAssistantToolNode(state, toolEvent.call_id);
        const existingDiagnostic = !existingNode && toolEvent.call_id
            ? findAssistantDiagnosticNode(state, node => node?.payload?.tool?.call_id === toolEvent.call_id)
            : null;
        const promotableProgressDiagnostic = !existingNode && !existingDiagnostic
            ? findPromotableProgressDiagnosticNode(state, toolEvent)
            : null;
        const targetNode = existingNode
            || (existingDiagnostic
                ? promoteAssistantDiagnosticToToolNode(state, existingDiagnostic, toolEvent, {
                    node: event.node || null,
                    sortKey: event.sortKey,
                    timestamp: event.timestamp,
                    sourceMessage: event.sourceMessage,
                    toolRow: event.toolRow,
                    preserveOutput: !Object.prototype.hasOwnProperty.call(event, 'output'),
                })
                : promotableProgressDiagnostic
                    ? promoteAssistantDiagnosticToToolNode(state, promotableProgressDiagnostic, toolEvent, {
                        node: event.node || null,
                        sortKey: event.sortKey,
                        timestamp: event.timestamp,
                        sourceMessage: event.sourceMessage,
                        toolRow: event.toolRow,
                        preserveOutput: !Object.prototype.hasOwnProperty.call(event, 'output'),
                    })
                : buildAssistantTraceToolNode(state, toolEvent, {
                    node: event.node || null,
                    sortKey: event.sortKey,
                    timestamp: event.timestamp,
                    sourceMessage: event.sourceMessage,
                    toolRow: event.toolRow,
                    sessionId: trace.sessionId,
                    sequence: event.sequence,
                }));
        if (!existingNode) {
            if (!trace.toolNodes.includes(targetNode)) {
                trace.toolNodes.push(targetNode);
            }
            if (!trace.items.includes(targetNode)) {
                trace.items.push(targetNode);
            }
        }
        const mergedTool = {
            ...targetNode.payload.tool,
            ...toolEvent,
            progress: normalizeToolProgressEntries(toolEvent.progress || targetNode.payload.tool.progress),
        };
        if (!Object.prototype.hasOwnProperty.call(event, 'output') && hasCapturedToolOutput(targetNode.payload.tool)) {
            mergedTool.output = targetNode.payload.tool.output;
        }
        if (!Object.prototype.hasOwnProperty.call(event, 'progress') && Array.isArray(targetNode.payload.tool?.progress) && targetNode.payload.tool.progress.length) {
            mergedTool.progress = normalizeToolProgressEntries(targetNode.payload.tool.progress);
        }
        targetNode.payload.tool = mergedTool;
        if (Object.prototype.hasOwnProperty.call(event, 'toolRow')) {
            targetNode.payload.toolRow = event.toolRow;
        }
        return syncAssistantTraceDerivedFields(state);
    }

    if (event.type === 'tool_output') {
        const existingNode = findAssistantToolNode(state, toolEvent.call_id);
        if (existingNode) {
            existingNode.payload.tool = {
                ...existingNode.payload.tool,
                ...toolEvent,
                progress: normalizeToolProgressEntries(existingNode.payload.tool.progress),
            };
            if (Object.prototype.hasOwnProperty.call(event, 'toolRow')) {
                existingNode.payload.toolRow = event.toolRow;
            }
            return syncAssistantTraceDerivedFields(state);
        }
        if (options.unmatchedToDiagnostic !== false) {
            return appendAssistantTraceDiagnostic(state, {
                node: event.node || null,
                tool: toolEvent,
                message: event.toolRow || null,
                timestamp: event.timestamp || null,
                sortKey: event.sortKey || null,
                label: event.label || `Unmatched ${toolEvent.name} output`,
                reason: event.reason || 'unmatched_tool_output',
            });
        }
        return syncAssistantTraceDerivedFields(state);
    }

    if (event.type === 'tool_progress') {
        const existingNode = findAssistantToolNode(state, toolEvent.call_id);
        const progressEntry = {
            label: typeof event.progress === 'string'
                ? event.progress
                : summarizeValue(event.progress || event.arguments || '', 160),
            task_index: Number.isInteger(event?.arguments?.task_index) ? event.arguments.task_index : null,
            task_count: Number.isInteger(event?.arguments?.task_count) ? event.arguments.task_count : null,
        };
        if (existingNode) {
            const progress = Array.isArray(existingNode.payload.tool.progress) ? existingNode.payload.tool.progress : [];
            const last = progress[progress.length - 1];
            if (progressEntry.label && (!last || last.label !== progressEntry.label || last.task_index !== progressEntry.task_index)) {
                progress.push(progressEntry);
            }
            if (progress.length > 30) {
                existingNode.payload.tool.progress = progress.slice(-30);
            } else {
                existingNode.payload.tool.progress = progress;
            }
            return syncAssistantTraceDerivedFields(state);
        }
        const diagnosticByCallId = toolEvent.call_id
            ? findAssistantDiagnosticNode(state, node => node?.payload?.tool?.call_id === toolEvent.call_id)
            : null;
        if (diagnosticByCallId) {
            const progress = Array.isArray(diagnosticByCallId.payload.tool.progress) ? diagnosticByCallId.payload.tool.progress : [];
            const last = progress[progress.length - 1];
            if (progressEntry.label && (!last || last.label !== progressEntry.label || last.task_index !== progressEntry.task_index)) {
                progress.push(progressEntry);
            }
            diagnosticByCallId.payload.tool.progress = progress.length > 30 ? progress.slice(-30) : progress;
            return syncAssistantTraceDerivedFields(state);
        }
        const unmatchedTool = {
            ...toolEvent,
            progress: progressEntry.label ? [progressEntry] : [],
        };
        const normalizedUnmatchedArgs = normalizeAssistantTraceToolIdentityValue(unmatchedTool.arguments);
        const diagnosticNode = findAssistantDiagnosticNode(
            state,
            node => node?.payload?.reason === 'unmatched_tool_progress'
                && node?.payload?.tool?.name === unmatchedTool.name
                && !node?.payload?.tool?.output
                && !node?.payload?.tool?.call_id
                && (
                    normalizedUnmatchedArgs
                        ? normalizeAssistantTraceToolIdentityValue(node?.payload?.tool?.arguments) === normalizedUnmatchedArgs
                        : !normalizeAssistantTraceToolIdentityValue(node?.payload?.tool?.arguments)
                ),
        );
        if (diagnosticNode) {
            const progress = Array.isArray(diagnosticNode.payload.tool.progress) ? diagnosticNode.payload.tool.progress : [];
            const last = progress[progress.length - 1];
            if (progressEntry.label && (!last || last.label !== progressEntry.label || last.task_index !== progressEntry.task_index)) {
                progress.push(progressEntry);
            }
            if (progress.length > 30) {
                diagnosticNode.payload.tool.progress = progress.slice(-30);
            } else {
                diagnosticNode.payload.tool.progress = progress;
            }
            return syncAssistantTraceDerivedFields(state);
        }
        return appendAssistantTraceDiagnostic(state, {
            node: event.node || null,
            tool: unmatchedTool,
            message: progressEntry.label || null,
            timestamp: event.timestamp || null,
            sortKey: event.sortKey || null,
            label: event.label || `${unmatchedTool.name} progress`,
            reason: event.reason || 'unmatched_tool_progress',
        });
    }

    return syncAssistantTraceDerivedFields(state);
}

function groupParallelToolEvents(events) {
    if (!Array.isArray(events) || !events.length) return [];
    // Adjacency only proves ordering, not concurrency. Parallel groups must arrive
    // as explicit parallel_group events from the execution trace.
    return events.filter(Boolean);
}

function buildHistoricalExecutionTrace(data) {
    const sessionId = data?.id || data?.session_id || '';
    const nodes = [];
    const messages = [];
    const pendingAssistantByTool = new Map();
    const toolTargets = new Map();
    const rows = Array.isArray(data?.messages) ? data.messages : [];

    rows.forEach((message, messageIndex) => {
        const sortKey = [message?.timestamp || '', String(messageIndex).padStart(6, '0')].join(':');
        if (message.role === 'assistant') {
            const tools = normalizeToolCallEntries(message.tool_calls);
            const messageId = makeExecutionNodeId('message', sessionId, message.id ?? `assistant_${messageIndex}`, messageIndex);
            const stepNode = {
                kind: 'assistant_step',
                node_id: messageId,
                dom_id: `message-${message.id != null ? String(message.id) : `assistant-${messageIndex}`}`,
                session_id: sessionId,
                timestamp: message.timestamp || null,
                sort_key: sortKey,
                parent_node_id: null,
                call_id: null,
                label: 'assistant',
                payload: {
                    message,
                    toolNodes: [],
                },
            };
            const assistantState = createAssistantTraceState({
                traceNode: stepNode,
                sessionId,
            });
            reduceAssistantTraceEvent(assistantState, {
                type: 'content',
                text: message.content || '',
                replace: true,
                node: buildAssistantContentNode(sessionId, stepNode, message, `${sortKey}:content`, messageIndex),
                timestamp: message.timestamp || null,
                sortKey: `${sortKey}:content`,
            }, { unmatchedToDiagnostic: false });
            tools.forEach((tool, toolIndex) => {
                const callId = tool.call_id || tool.id || `${message?.id || 'assistant'}_${toolIndex}`;
                const toolNode = buildAssistantTraceToolNode(assistantState, {
                    ...tool,
                    call_id: callId,
                }, {
                    node: {
                        kind: 'tool_run',
                        node_id: makeExecutionNodeId('tool', sessionId, callId, toolIndex),
                        dom_id: `tool-${String(callId).replace(/[^A-Za-z0-9_-]/g, '_')}`,
                        session_id: sessionId,
                        timestamp: message?.timestamp || null,
                        sort_key: `${sortKey}:tool:${String(toolIndex).padStart(4, '0')}`,
                        parent_node_id: messageId,
                        call_id: callId,
                        label: tool.name || 'tool',
                        payload: {},
                    },
                    sortKey: `${sortKey}:tool:${String(toolIndex).padStart(4, '0')}`,
                    timestamp: message?.timestamp || null,
                    sourceMessage: message || null,
                    sequence: toolIndex,
                });
                reduceAssistantTraceEvent(assistantState, {
                    type: 'tool_call',
                    ...tool,
                    call_id: callId,
                    node: toolNode,
                    sortKey: `${sortKey}:tool:${String(toolIndex).padStart(4, '0')}`,
                    timestamp: message?.timestamp || null,
                    sourceMessage: message || null,
                    sequence: toolIndex,
                }, { unmatchedToDiagnostic: false });
                if (callId) {
                    pendingAssistantByTool.set(callId, assistantState);
                    if (toolNode.dom_id) {
                        toolTargets.set(callId, toolNode.dom_id);
                    }
                }
            });
            syncAssistantTraceDerivedFields(assistantState);
            nodes.push(stepNode);
            messages.push({
                ...message,
                ...assistantState,
                role: 'assistant',
                traceNode: stepNode,
                trace: assistantState.trace,
            });
            return;
        }

        if (message.role === 'tool') {
            const callId = message.tool_call_id || '';
            const pending = callId ? pendingAssistantByTool.get(callId) : null;
            if (pending) {
                reduceAssistantTraceEvent(pending, {
                    type: 'tool_output',
                    call_id: callId,
                    name: message.tool_name || '',
                    output: message.content || '',
                    toolRow: message,
                    timestamp: message.timestamp || null,
                    sortKey: `${sortKey}:output`,
                });
                pendingAssistantByTool.delete(callId);
            } else {
                const orphanTool = {
                    call_id: callId,
                    name: message.tool_name || 'tool',
                    arguments: '',
                    output: message.content || '',
                    progress: [],
                };
                const orphanNode = buildAssistantTraceDiagnosticNode(createAssistantTraceState({ sessionId }), {
                    node: {
                        kind: 'diagnostic_artifact',
                        node_id: makeExecutionNodeId('orphan', sessionId, callId || `tool_${messageIndex}`, messageIndex),
                        dom_id: `orphan-tool-${message.id != null ? String(message.id) : messageIndex}`,
                        session_id: sessionId,
                        timestamp: message.timestamp || null,
                        sort_key: `${sortKey}:orphan`,
                        parent_node_id: null,
                        call_id: callId || null,
                        label: `Unmatched ${orphanTool.name} output`,
                        payload: {},
                    },
                    tool: orphanTool,
                    message,
                    timestamp: message.timestamp || null,
                    sortKey: `${sortKey}:orphan`,
                    label: `Unmatched ${orphanTool.name} output`,
                    reason: 'unmatched_tool_output',
                    sequence: messageIndex,
                });
                nodes.push(orphanNode);
                if (callId) toolTargets.set(callId, orphanNode.dom_id);
            }
            return;
        }

        const messageNode = {
            kind: message.role === 'user' ? 'user_message' : 'diagnostic_artifact',
            node_id: makeExecutionNodeId('message', sessionId, message.id ?? `${message.role || 'message'}_${messageIndex}`, messageIndex),
            dom_id: `message-${message.id != null ? String(message.id) : `${message.role || 'message'}-${messageIndex}`}`,
            session_id: sessionId,
            timestamp: message.timestamp || null,
            sort_key: sortKey,
            parent_node_id: null,
            call_id: null,
            label: message.role || 'message',
            payload: { message },
        };
        nodes.push(messageNode);
        messages.push({ ...message, traceNode: messageNode });
    });

    const childNodes = (Array.isArray(data?.children) ? data.children : []).map((child, index) => ({
        kind: 'child_session',
        node_id: makeExecutionNodeId('child', sessionId, child.id || `child_${index}`, index),
        dom_id: `child-session-${String(child.id || index).replace(/[^A-Za-z0-9_-]/g, '_')}`,
        session_id: sessionId,
        timestamp: child.started_at || null,
        sort_key: `${child.started_at || 'zzzz'}:child:${String(index).padStart(4, '0')}`,
        parent_node_id: null,
        call_id: null,
        label: child.title || child.id || 'Child session',
        payload: { child },
    }));

    const artifactNodes = (Array.isArray(data?.related_artifacts) ? data.related_artifacts : []).map((artifact, index) => ({
        kind: 'diagnostic_artifact',
        node_id: makeExecutionNodeId('artifact', sessionId, artifact.slug || `artifact_${index}`, index),
        dom_id: `artifact-${sessionId.replace(/[^A-Za-z0-9_-]/g, '_')}-${String(artifact.slug || index).replace(/[^A-Za-z0-9_-]/g, '_')}`,
        session_id: sessionId,
        timestamp: artifact.timestamp || null,
        sort_key: `${artifact.timestamp || 'zzzz'}:artifact:${String(index).padStart(4, '0')}`,
        parent_node_id: null,
        call_id: null,
        label: artifact.reason || artifact.file_name || 'Diagnostic artifact',
        payload: { artifact },
    }));

    return {
        sessionId,
        messages,
        nodes: [...nodes, ...childNodes, ...artifactNodes]
            .sort((a, b) => String(a.sort_key || '').localeCompare(String(b.sort_key || ''))),
        targetDomIds: {
            tool: toolTargets,
            child: new Map(childNodes.map(node => [node.payload.child?.id, node.dom_id]).filter(([key]) => key)),
            artifact: new Map(artifactNodes.map(node => [node.payload.artifact?.slug, node.dom_id]).filter(([key]) => key)),
        },
    };
}

function buildConversationFromSessionData(data) {
    return buildHistoricalExecutionTrace(data).messages.filter(message => !isBackgroundCompletionPrompt(message)).map(message => {
        if (message.role === 'assistant') {
            return {
                ...message,
                role: 'assistant',
                content: message.content || '',
                tools: Array.isArray(message.tools) ? message.tools : [],
                events: Array.isArray(message.events) ? message.events : [],
                trace: message.trace || null,
                traceNode: message.traceNode || null,
            };
        }
        if (message.role === 'user') {
            return { role: 'user', content: message.content || '', traceNode: message.traceNode || null };
        }
        return message;
    });
}

function buildAssistantMessageFromTraceNode(traceNode) {
    return normalizeAssistantMessage({
        ...traceNode?.payload?.message,
        traceNode,
        trace: {
            sessionId: traceNode?.session_id || null,
            stepNode: traceNode,
            contentNode: traceNode?.payload?.contentNode || null,
            toolNodes: Array.isArray(traceNode?.payload?.toolNodes) ? traceNode.payload.toolNodes : [],
            orphanNodes: Array.isArray(traceNode?.payload?.orphanNodes) ? traceNode.payload.orphanNodes : [],
            items: Array.isArray(traceNode?.payload?.items) ? traceNode.payload.items : [],
            toolIndexByCallId: traceNode?.payload?.toolIndexByCallId || {},
            pendingDelegateChildren: {},
        },
    });
}

function buildSessionTraceContext(data, options = {}) {
    const trace = buildHistoricalExecutionTrace(data);
    trace.data = data;
    trace.domScope = options.domScope || '';
    const backgroundReviews = Array.isArray(data?.background_reviews) ? data.background_reviews : [];
    backgroundReviews.forEach((review) => {
        (review?.events || []).forEach((event, index) => {
            if (!event?.call_id) return;
            const domId = `child-tool-${String(event.call_id).replace(/[^A-Za-z0-9_-]/g, '_')}`;
            if (!trace.targetDomIds.tool.has(event.call_id)) {
                trace.targetDomIds.tool.set(event.call_id, domId);
            }
        });
    });
    return trace;
}

function scopedExecutionDomId(domId, traceContext = null) {
    const raw = String(domId || '').trim();
    if (!raw) return '';
    const scope = String(traceContext?.domScope || '').trim();
    return scope ? `${scope}-${raw}` : raw;
}

function executionTargetDomId(target, traceContext = currentSessionTraceContext) {
    const normalized = normalizeExecutionTarget(target);
    if (!normalized || !traceContext?.targetDomIds) return null;
    const bucket = traceContext.targetDomIds[normalized.kind];
    if (!(bucket instanceof Map)) return null;
    const direct = bucket.get(normalized.id) || null;
    return direct ? scopedExecutionDomId(direct, traceContext) : null;
}

function expandExecutionAncestors(element) {
    let current = element?.parentElement || null;
    while (current) {
        if (current.tagName === 'DETAILS') current.open = true;
        current = current.parentElement;
    }
}

function scrollToExecutionNode(target, traceContext = currentSessionTraceContext) {
    const domId = executionTargetDomId(target, traceContext);
    if (!domId) return false;
    const element = document.getElementById(domId);
    if (!element) return false;
    expandExecutionAncestors(element);
    element.classList.remove('execution-pulse');
    void element.offsetWidth;
    element.classList.add('execution-pulse');
    element.scrollIntoView({ behavior: 'smooth', block: 'center' });
    return true;
}

function renderExecutionTargetLink(sessionId, target, label) {
    const route = routeForExecutionTarget(sessionId, target);
    if (!route) return '';
    return `<a class="execution-target-link" href="#${escapeHtml(route)}">${escapeHtml(label)}</a>`;
}

function renderInlineChildStage(node, traceContext = currentSessionTraceContext) {
    const child = node?.payload?.child || {};
    const review = (traceContext?.data?.background_reviews || []).find(item => item?.session_id === child.id) || null;
    const summary = review?.summary || child.summary || '';
    const reviewEvents = Array.isArray(review?.events) ? review.events : [];
    return `
        <details class="inline-child-stage execution-node" id="${escapeHtml(scopedExecutionDomId(node.dom_id, traceContext))}" data-session-child="${escapeHtml(child.id || '')}">
            <summary>
                <div class="inline-stage-title">
                    <span>${escapeHtml(child.title || child.id || 'Child session')}</span>
                    <span class="meta-pill">inline stage</span>
                </div>
                <div class="inline-stage-meta">${escapeHtml(formatSessionDate(child.started_at) || 'Unknown start')} ${child.id ? `· ${escapeHtml(String(child.id).slice(0, 8))}` : ''}</div>
                ${summary ? `<div class="inline-stage-summary">${escapeHtml(summary)}</div>` : ''}
            </summary>
            <div class="inline-child-stage-body">
                <div class="inline-stage-links">
                    <button class="btn execution-child-session-link" type="button" data-session-route="${escapeHtml(`sessions/detail/${encodeURIComponent(child.id || '')}`)}">Open child session</button>
                    <button class="btn live-view-btn" data-child-session-id="${escapeHtml(child.id || '')}" data-anchor-selector="#${escapeHtml(scopedExecutionDomId(node.dom_id, traceContext))}" data-label="${escapeHtml(child.title || '')}">Live view</button>
                    ${renderExecutionTargetLink(traceContext?.sessionId, { kind: 'child', id: child.id }, 'Jump here')}
                </div>
                ${reviewEvents.length ? `<div class="activity-block">${reviewEvents.slice(0, 6).map((event, index) => {
                    const eventId = scopedExecutionDomId(event.call_id ? `child-tool-${String(event.call_id).replace(/[^A-Za-z0-9_-]/g, '_')}` : `child-tool-${String(child.id || 'child').replace(/[^A-Za-z0-9_-]/g, '_')}-${index}`, traceContext);
                    return `<div id="${escapeHtml(eventId)}" class="execution-node" style="margin-top:0.45rem;"><strong>${escapeHtml(event.name || 'tool')}</strong>${event.call_id ? ` <span class="meta-pill">call ${escapeHtml(String(event.call_id).slice(-8))}</span>` : ''}${renderActivityData(event.output)}</div>`;
                }).join('')}</div>` : '<div style="color:var(--text-dim);margin-top:0.65rem;">No inline review events were synthesized for this child session.</div>'}
            </div>
        </details>
    `;
}

function renderDiagnosticArtifactNode(node, traceContext = currentSessionTraceContext) {
    const artifact = node?.payload?.artifact || {};
    const meta = [artifact.reason, artifact.model, artifact.url].filter(Boolean).join(' · ');
    const errorMeta = [artifact.error_type, artifact.error_response_status ? `status ${artifact.error_response_status}` : ''].filter(Boolean).join(' · ');
    return `
        <details class="diagnostic-artifact execution-node" id="${escapeHtml(scopedExecutionDomId(node.dom_id, traceContext))}">
            <summary>
                <div class="inline-stage-title">
                    <span>${escapeHtml(artifact.file_name || artifact.slug || 'Diagnostic artifact')}</span>
                    <span class="meta-pill">artifact</span>
                </div>
                <div class="inline-stage-meta">${escapeHtml(formatSessionDate(artifact.timestamp) || 'Unknown time')}</div>
                ${meta ? `<div class="inline-stage-summary">${escapeHtml(meta)}</div>` : ''}
            </summary>
            <div class="diagnostic-artifact-body">
                ${artifact.error_message ? `<div class="activity-block"><strong>Error</strong><pre>${escapeHtml(artifact.error_message)}</pre></div>` : ''}
                ${errorMeta ? `<div class="activity-block"><strong>Failure Details</strong><pre>${escapeHtml(errorMeta)}</pre></div>` : ''}
                <div class="activity-block"><strong>Path</strong><pre>${escapeHtml(artifact.path || '')}</pre></div>
            </div>
        </details>
    `;
}

function renderOrphanDiagnosticNode(node, traceContext = currentSessionTraceContext) {
    if (node?.payload?.reason === 'unmatched_tool_progress') return '';
    const tool = node?.payload?.tool || {};
    return `
        <div class="orphan-tool-block execution-node" id="${escapeHtml(scopedExecutionDomId(node.dom_id, traceContext))}">
            <span class="orphan-tool-label">${escapeHtml(node?.label || 'Unmatched tool output')}</span>
            ${renderToolBlock(tool, 0, { node, traceContext })}
        </div>
    `;
}

function renderSessionTranscript(traceContext) {
    const rows = (traceContext?.nodes || []).map((node) => {
        if (node.kind === 'assistant_step') {
            return { message: { ...buildAssistantMessageFromTraceNode(node), renderTraceContext: traceContext }, node };
        }
        return { kind: 'boundary', node };
    });
    return renderTranscriptSegments(buildTranscriptRenderSegments(rows), {
        assistant: (body, segment) => {
            const source = segment.message || segment.updates?.[0]?.message || {};
            const normalized = segment.normalized || segment.updates?.[0]?.normalized || normalizeAssistantMessage(source);
            return `<div class="message assistant">${renderAssistantMessageShell({ ...source, traceNode: null }, normalized, body)}</div>`;
        },
        boundary: (row) => {
            const node = row?.node;
            if (node?.kind === 'user_message') return renderSessionMessage({ ...node.payload.message, traceNode: node });
            if (node?.kind === 'child_session') return renderInlineChildStage(node, traceContext);
            if (node?.kind === 'diagnostic_artifact' && node.payload?.artifact) return renderDiagnosticArtifactNode(node, traceContext);
            if (node?.kind === 'diagnostic_artifact' && node.payload?.orphan) return renderOrphanDiagnosticNode(node, traceContext);
            return '';
        },
    });
}

function renderFloatingSessionTranscript(traceContext) {
    const rows = (traceContext?.nodes || []).map((node) => {
        if (node.kind === 'assistant_step') {
            return { message: { ...buildAssistantMessageFromTraceNode(node), renderTraceContext: traceContext }, node };
        }
        return { kind: 'boundary', node };
    });
    return renderTranscriptSegments(buildTranscriptRenderSegments(rows), {
        assistant: (body, segment) => {
            const source = segment.message || segment.updates?.[0]?.message || {};
            const normalized = segment.normalized || segment.updates?.[0]?.normalized || normalizeAssistantMessage(source);
            return `<div class="fp-msg" style="border-left-color:#06b6d4"><div class="fp-msg-role" style="color:#06b6d4">assistant</div>${renderAssistantMessageShell(source, normalized, body)}</div>`;
        },
        boundary: (row) => {
            const node = row?.node;
            if (node?.kind === 'user_message') {
                const message = node.payload.message || {};
                return `<div class="fp-msg" style="border-left-color:#a855f7"><div class="fp-msg-role" style="color:#a855f7">user</div><div style="font-size:0.8rem;line-height:1.4">${escapeHtml(message.content || '').replace(/\n/g, '<br>')}</div></div>`;
            }
            if (node?.kind === 'child_session') return `<div class="fp-msg" style="border-left-color:#a855f7">${renderInlineChildStage(node, traceContext)}</div>`;
            if (node?.kind === 'diagnostic_artifact' && node.payload?.artifact) return `<div class="fp-msg" style="border-left-color:#f97316">${renderDiagnosticArtifactNode(node, traceContext)}</div>`;
            if (node?.kind === 'diagnostic_artifact' && node.payload?.orphan) return `<div class="fp-msg" style="border-left-color:#f97316">${renderOrphanDiagnosticNode(node, traceContext)}</div>`;
            return '';
        },
    });
}

async function hydrateChatFromSession(sessionId, options = {}) {
    if (!options.preserveActiveRun && activeChatRoomId !== 'main') {
        const switched = await switchChatRoom('main');
        if (!switched) return;
    }
    log('req', `GET /api/sessions/${sessionId} for chat hydration`);
    const data = await fetchJsonOrThrow(`/api/sessions/${sessionId}`);
    activeChatSessionId = sessionId;
    void refreshSessionContextInfo(sessionId);
    if (!options.preserveActiveRun) {
        chatRoomIntentEpochs.set(activeChatRoomId, (chatRoomIntentEpochs.get(activeChatRoomId) || 0) + 1);
    }
    conversation = buildConversationFromSessionData(data);
    saveConversation();
    if (!options.preserveActiveRun) {
        clearActiveRun();
    }
    renderConversation();
    const lastAssistant = [...conversation].reverse().find(msg => msg.role === 'assistant');
    updateContextDisplay(lastAssistant ? normalizeAssistantMessage(lastAssistant) : { usage: null, last_prompt_tokens: 0 });
    saveActiveChatSession();
    refreshTokenUsageSoon();
    updateActiveChatBanner();
    updateActiveRunBanner();
    showToast(`Loaded session ${sessionId.slice(0, 8)} into chat`);
    navigateTo('chat');
}

function normalizeAssistantMessage(message) {
    if (typeof message === 'string') {
        return syncAssistantTraceDerivedFields(reduceAssistantTraceEvent(createAssistantTraceState(), { type: 'content', text: message, replace: true }));
    }
    const state = createAssistantTraceState({
        usage: message?.usage || null,
        last_prompt_tokens: message?.last_prompt_tokens || 0,
        prompt_breakdown: Array.isArray(message?.prompt_breakdown) ? message.prompt_breakdown : [],
        traceNode: message?.traceNode || null,
        sessionId: message?.trace?.sessionId || message?.traceNode?.session_id || null,
        trace: message?.trace || null,
    });
    if (message?.trace?.contentNode || message?.trace?.toolNodes || message?.trace?.orphanNodes || message?.trace?.items) {
        state.content = message.content || collectAssistantTraceContentText(message.trace, message.trace?.contentNode?.payload?.text || '');
        state.trace.contentNode = message.trace?.contentNode || state.trace.contentNode;
        state.trace.toolNodes = Array.isArray(message.trace?.toolNodes) ? message.trace.toolNodes : state.trace.toolNodes;
        state.trace.orphanNodes = Array.isArray(message.trace?.orphanNodes) ? message.trace.orphanNodes : state.trace.orphanNodes;
        state.trace.items = Array.isArray(message.trace?.items) ? message.trace.items : state.trace.items;
        state.trace.toolIndexByCallId = message.trace?.toolIndexByCallId && typeof message.trace.toolIndexByCallId === 'object'
            ? { ...message.trace.toolIndexByCallId }
            : state.trace.toolIndexByCallId;
        syncAssistantTraceDerivedFields(state);
    } else if (message?.traceNode?.kind === 'assistant_step') {
        state.content = message.content || collectAssistantTraceContentText(message.traceNode?.payload, message.traceNode?.payload?.contentNode?.payload?.text || '');
        state.trace.stepNode = message.traceNode;
        state.trace.contentNode = message.traceNode?.payload?.contentNode || null;
        state.trace.toolNodes = Array.isArray(message.traceNode?.payload?.toolNodes) ? message.traceNode.payload.toolNodes : [];
        state.trace.orphanNodes = Array.isArray(message.traceNode?.payload?.orphanNodes) ? message.traceNode.payload.orphanNodes : [];
        state.trace.items = Array.isArray(message.traceNode?.payload?.items) ? message.traceNode.payload.items : [];
        state.trace.toolIndexByCallId = message.traceNode?.payload?.toolIndexByCallId && typeof message.traceNode.payload.toolIndexByCallId === 'object'
            ? { ...message.traceNode.payload.toolIndexByCallId }
            : state.trace.toolIndexByCallId;
        syncAssistantTraceDerivedFields(state);
    } else {
        reduceAssistantTraceEvent(state, { type: 'content', text: message?.content || '', replace: true });
        const replayEvents = Array.isArray(message?.events) ? message.events : [];
        if (replayEvents.length) {
            replayEvents.forEach((event) => {
                if (!event) return;
                reduceAssistantTraceEvent(state, event);
            });
        } else if (Array.isArray(message?.tools)) {
            message.tools.forEach((tool) => {
                const normalizedTool = {
                    ...tool,
                    call_id: tool?.call_id || tool?.id || '',
                };
                reduceAssistantTraceEvent(state, {
                    ...normalizedTool,
                    type: hasCapturedToolOutput(normalizedTool) ? 'tool_output' : 'tool_call',
                });
            });
        }
    }
    state.renderTraceContext = message?.renderTraceContext || null;
    return syncAssistantTraceDerivedFields(state);
}

function safePayloadStringify(value, fallback = '') {
    try {
        const seen = new WeakSet();
        const serialized = JSON.stringify(value, (key, item) => {
            if (typeof item === 'bigint') return `${item.toString()}n`;
            if (typeof item === 'function') return `[Function ${item.name || 'anonymous'}]`;
            if (item && typeof item === 'object') {
                if (seen.has(item)) return '[Circular]';
                seen.add(item);
            }
            return item;
        }, 2);
        return serialized === undefined ? fallback : serialized;
    } catch (error) {
        return fallback || `[Unserializable payload: ${error?.message || 'unknown error'}]`;
    }
}

function parseToolPayload(value) {
    if (value === null || value === undefined) {
        return { raw: '', parsed: null };
    }
    if (typeof value === 'string') {
        const raw = value.trim();
        if (!raw) return { raw: '', parsed: null };
        try {
            return { raw, parsed: JSON.parse(raw) };
        } catch {
            return { raw, parsed: null };
        }
    }
    if (typeof value === 'object') {
        return { raw: safePayloadStringify(value, String(value)), parsed: value };
    }
    return { raw: String(value), parsed: value };
}

function normalizeToolProgressEntries(progress) {
    if (!Array.isArray(progress)) return [];
    return progress.map(item => {
        if (item && typeof item === 'object') {
            const message = item.message || item.progress || '';
            return {
                label: typeof item.label === 'string'
                    ? item.label
                    : summarizeValue(
                        item.name === 'session_search' && item.mode
                            ? `Searching sessions (${item.mode})`
                            : message,
                        160,
                    ),
                task_index: Number.isInteger(item.task_index) ? item.task_index : null,
                task_count: Number.isInteger(item.task_count) ? item.task_count : null,
            };
        }
        return {
            label: typeof item === 'string' ? item : summarizeValue(item, 160),
            task_index: null,
            task_count: null,
        };
    }).filter(item => item.label);
}

function summarizeValue(value, limit = 120) {
    if (value === null || value === undefined) return '';
    const text = typeof value === 'string' ? value : JSON.stringify(value);
    if (!text) return '';
    return text.length > limit ? `${text.slice(0, limit - 3)}...` : text;
}

function summarizeToolSubject(value, limit = 72) {
    const text = summarizeValue(value, limit).replace(/\s+/g, ' ').trim();
    return text.replace(/^['"]|['"]$/g, '');
}

function toolVerbPhrase(toolName) {
    const map = {
        read_file: 'Reading file',
        write_file: 'Writing file',
        patch: 'Patching file',
        terminal: 'Running terminal command',
        execute_code: 'Executing code',
        web_search: 'Searching the web',
        web_extract: 'Extracting web page content',
        fetch_url: 'Fetching URL',
        skill_view: 'Opening skill instructions',
        skill_manage: 'Updating skill metadata',
        session_search: 'Searching session history',
        delegate_task: 'Delegating subtask',
        todo: 'Updating task list',
        mcp_becomussy_project_list: 'Listing projects',
        mcp_becomussy_thread_list: 'Listing project threads',
    };
    return map[toolName] || `Running ${toolName || 'tool'}`;
}

function toolFileTargets(args) {
    if (!args || typeof args !== 'object') return [];
    const direct = [args.path, args.file_path, args.target_file, ...(Array.isArray(args.paths) ? args.paths : [])]
        .filter(value => typeof value === 'string' && value.trim())
        .map(value => value.trim());
    const patchText = typeof args.patch === 'string' ? args.patch : '';
    const patched = Array.from(patchText.matchAll(/^\*\*\* (?:Add|Update|Delete) File: (.+)$/gm), match => match[1].trim());
    return Array.from(new Set([...direct, ...patched]));
}

function describeTodoChange(args) {
    const todos = Array.isArray(args?.todos) ? args.todos : null;
    if (!todos) return 'Reading task list';
    const verb = args?.merge ? 'Updating' : 'Replacing';
    if (todos.length === 1) {
        const item = todos[0] || {};
        const content = typeof item.content === 'string' ? item.content.trim() : '';
        const status = typeof item.status === 'string' ? item.status.replace(/_/g, ' ') : '';
        if (content) return `${verb} task "${content}"${status ? ` as ${status}` : ''}`;
    }
    const counts = todos.reduce((result, item) => {
        const status = typeof item?.status === 'string' ? item.status.replace(/_/g, ' ') : '';
        if (status) result[status] = (result[status] || 0) + 1;
        return result;
    }, {});
    const statusText = Object.entries(counts).map(([status, count]) => `${count} ${status}`).join(', ');
    return `${verb} ${todos.length} task${todos.length === 1 ? '' : 's'}${statusText ? `: ${statusText}` : ''}`;
}

function getLocalToolDescription(toolName, parsedArgs, targetDetail = '', descriptionPending = false) {
    if (toolName === 'terminal') return descriptionPending ? 'Analyzing terminal command...' : 'Running terminal command';
    if (toolName === 'execute_code') return descriptionPending ? 'Analyzing code execution...' : 'Executing code';
    if (toolName === 'todo') return describeTodoChange(parsedArgs);
    if (['read_file', 'write_file', 'patch'].includes(toolName)) {
        const targets = toolFileTargets(parsedArgs);
        const verbs = { read_file: 'Reading', write_file: 'Writing', patch: 'Updating' };
        return `${verbs[toolName]} ${targets.length ? targets.join(', ') : 'file'}`;
    }
    const verb = toolVerbPhrase(toolName);
    return targetDetail ? `${verb}: ${targetDetail}` : verb;
}

function summarizeToolArgs(toolName, args) {
    if (!args || typeof args !== 'object') return '';
    switch (toolName) {
        case 'read_file':
        case 'write_file':
        case 'patch':
            return summarizeToolSubject(args.path || args.file_path || args.target_file || args.paths?.[0]);
        case 'terminal':
            return summarizeToolSubject(args.command || args.cmd, 88);
        case 'execute_code':
            return summarizeToolSubject(args.language || args.filename || args.code, 88);
        case 'web_search':
        case 'session_search':
            return summarizeToolSubject(args.query || args.prompt || args.search || args.mode, 88);
        case 'web_extract':
        case 'fetch_url':
            return summarizeToolSubject(args.url || args.urls?.[0], 88);
        case 'skill_view':
            return summarizeToolSubject(args.skill || args.skill_id || args.name);
        case 'skill_manage':
            return summarizeToolSubject(args.name || args.skill_id || args.action, 88);
        case 'delegate_task':
            return summarizeToolSubject(
                args.goal
                || args.task_description
                || args.prompt
                || args.description
                || args.task
                || args.tasks?.[0]?.goal
                || args.tasks?.[0]?.task
                || args.tasks?.[0]?.description,
                88,
            );
        case 'todo':
            return summarizeToolSubject(args.content || args.items?.[0]?.content || args.action, 88);
        case 'mcp_becomussy_project_list':
            return summarizeToolSubject(args.status || args.filter || 'available projects');
        case 'mcp_becomussy_thread_list':
            return summarizeToolSubject(args.project_id || args.project || args.status || 'project threads');
        default:
            return summarizeToolSubject(
                args.path || args.query || args.url || args.command || args.name || args.id || args.action,
                88,
            );
    }
}

function summarizeToolResult(toolName, result) {
    if (result == null || result === '') return '';
    if (typeof result === 'string') {
        return summarizeToolSubject(result, 88);
    }
    if (typeof result === 'object') {
        if (typeof result.message === 'string' && result.message.trim()) return summarizeToolSubject(result.message, 88);
        if (typeof result.summary === 'string' && result.summary.trim()) return summarizeToolSubject(result.summary, 88);
        if (typeof result.error === 'string' && result.error.trim()) return summarizeToolSubject(result.error, 88);
        if (typeof result.path === 'string' && result.path.trim()) return summarizeToolSubject(result.path, 88);
        if (typeof result.count === 'number') return `${result.count} item${result.count === 1 ? '' : 's'}`;
        if (Array.isArray(result.results)) return `${result.results.length} result${result.results.length === 1 ? '' : 's'}`;
        if (typeof result.status === 'string' && result.status.trim()) return summarizeToolSubject(result.status, 88);
    }
    return summarizeToolSubject(result, 88);
}

function describeToolLog(toolName, phase, payload = null) {
    const verb = toolVerbPhrase(toolName);
    const subject = summarizeToolArgs(toolName, payload && typeof payload === 'object' ? payload : null);
    const prefix = subject ? `${verb}: ${subject}` : verb;
    if (phase === 'start') return `${prefix}...`;
    if (phase === 'progress') {
        const progressText = typeof payload === 'string'
            ? summarizeToolSubject(payload, 88)
            : summarizeToolSubject(payload?.progress || payload?.message || payload?.status || payload, 88);
        return progressText ? `${prefix} • ${progressText}` : `${prefix} in progress`;
    }
    if (phase === 'delegated') return `${prefix} • handed off to a subagent`;
    if (phase === 'output') {
        const summary = summarizeToolResult(toolName, payload);
        return summary ? `${prefix} • completed: ${summary}` : `${prefix} • completed`;
    }
    return prefix;
}

function unwrapDelegateTaskEnvelope(payload, depth = 0) {
    if (depth > 6 || payload === null || payload === undefined) return {};
    if (Array.isArray(payload)) return { results: payload };
    if (typeof payload === 'string') {
        const parsed = parseToolPayload(payload).parsed;
        return parsed === null ? {} : unwrapDelegateTaskEnvelope(parsed, depth + 1);
    }
    if (typeof payload !== 'object') return {};
    if (Array.isArray(payload.results)) return payload;
    for (const key of ['data', 'output', 'result', 'payload', 'response']) {
        if (!Object.prototype.hasOwnProperty.call(payload, key)) continue;
        const nested = unwrapDelegateTaskEnvelope(payload[key], depth + 1);
        if (Array.isArray(nested.results)) {
            return {
                ...payload,
                ...nested,
                total_duration_seconds: payload.total_duration_seconds ?? nested.total_duration_seconds,
            };
        }
    }
    return payload;
}

function firstPresentValue(source, keys, fallback = '') {
    if (!source || typeof source !== 'object') return fallback;
    for (const key of keys) {
        if (Object.prototype.hasOwnProperty.call(source, key) && source[key] !== null && source[key] !== undefined) {
            return source[key];
        }
    }
    return fallback;
}

function renderDelegateTaskOutput(parsedOutput, rawOutput) {
    const envelope = unwrapDelegateTaskEnvelope(parsedOutput);
    const results = Array.isArray(envelope.results)
        ? envelope.results.filter(result => result && typeof result === 'object')
        : [];
    const totalDuration = envelope.total_duration_seconds;
    const summaryHtml = results.length ? `
        <div class="delegate-task-results">${results.map((result, idx) => {
            const status = firstPresentValue(result, ['status'], 'unknown');
            const itemClass = status === 'completed' ? 'success' : 'error';
            const title = firstPresentValue(
                result,
                ['title', 'label'],
                result.task_index !== undefined ? `Task ${Number(result.task_index) + 1}` : `Task ${idx + 1}`,
            );
            const secondary = [
                status,
                result.duration_seconds !== null && result.duration_seconds !== undefined ? `${result.duration_seconds}s` : '',
                result.api_calls !== null && result.api_calls !== undefined ? `${result.api_calls} API calls` : '',
            ].filter(value => value !== '').join(' • ');
            const bodyValue = firstPresentValue(result, ['summary', 'final_summary', 'result', 'output', 'error'], '');
            const body = typeof bodyValue === 'object' ? safePayloadStringify(bodyValue, String(bodyValue)) : String(bodyValue);
            return `
                <div class="delegate-task-item ${itemClass}">
                    <div class="delegate-task-topline">
                        <div class="delegate-task-title">${escapeHtml(String(title))}</div>
                        ${secondary ? `<div class="delegate-task-meta">${escapeHtml(secondary)}</div>` : ''}
                    </div>
                    ${bodyValue !== '' ? `<div class="delegate-task-summary">${escapeHtml(body)}</div>` : ''}
                </div>
            `;
        }).join('')}</div>
    ` : '';
    return `
        <div class="tool-section">
            <label>Output</label>
            ${totalDuration !== null && totalDuration !== undefined ? `<div class="delegate-task-meta" style="margin-bottom:0.35rem;">Total duration: ${escapeHtml(String(totalDuration))}s</div>` : ''}
            ${summaryHtml || '<pre>No delegated task results were returned.</pre>'}
            <details class="delegate-task-raw">
                <summary>Raw output</summary>
                <pre class="tool-output-json">${highlightJSON(rawOutput || '')}</pre>
            </details>
        </div>
    `;
}

function renderSkillViewOutput(parsedOutput, rawOutput) {
    const tags = Array.isArray(parsedOutput?.tags) ? parsedOutput.tags : [];
    const related = Array.isArray(parsedOutput?.related_skills) ? parsedOutput.related_skills : [];
    return `
        <div class="tool-section">
            <label>Output</label>
            <div class="structured-output">
                <div class="structured-output-card">
                    <div class="structured-output-title">${escapeHtml(parsedOutput?.name || 'Skill')}</div>
                    ${parsedOutput?.description ? `<div>${escapeHtml(parsedOutput.description)}</div>` : ''}
                    <div class="structured-output-meta">${escapeHtml(parsedOutput?.path || '')}</div>
                    ${tags.length ? `<div class="structured-output-tags">${tags.map(tag => `<span class="structured-output-tag">${escapeHtml(tag)}</span>`).join('')}</div>` : ''}
                    ${related.length ? `<div class="structured-output-tags" style="margin-top:0.35rem;">${related.map(tag => `<span class="structured-output-tag">related: ${escapeHtml(tag)}</span>`).join('')}</div>` : ''}
                </div>
                ${parsedOutput?.content ? `<details class="delegate-task-raw"><summary>Skill Content</summary><pre>${escapeHtml(parsedOutput.content)}</pre></details>` : ''}
                <details class="delegate-task-raw"><summary>Raw output</summary><pre class="tool-output-json">${highlightJSON(rawOutput || '')}</pre></details>
            </div>
        </div>
    `;
}

function renderStructuredJsonOutput(parsedOutput, rawOutput) {
    const status = parsedOutput?.success;
    const summaryFields = [
        parsedOutput?.message,
        parsedOutput?.error,
        parsedOutput?.description,
        parsedOutput?.name,
    ].filter(Boolean);
    const metadata = [];
    if (parsedOutput?.path) metadata.push(parsedOutput.path);
    if (parsedOutput?.count !== undefined) metadata.push(`${parsedOutput.count} items`);
    if (parsedOutput?.readiness_status) metadata.push(parsedOutput.readiness_status);
    const remainingEntries = Object.entries(parsedOutput || {}).filter(([key]) => ![
        'success', 'message', 'error', 'description', 'name', 'path', 'content', 'results', 'count', 'tags', 'related_skills', 'readiness_status'
    ].includes(key));
    return `
        <div class="tool-section">
            <label>Output</label>
            <div class="structured-output">
                <div class="structured-output-card">
                    <div class="structured-output-title">${escapeHtml(status === false ? 'Tool returned an error' : 'Tool completed successfully')}</div>
                    ${summaryFields.length ? `<div>${escapeHtml(summaryFields[0])}</div>` : ''}
                    ${metadata.length ? `<div class="structured-output-meta">${escapeHtml(metadata.join(' • '))}</div>` : ''}
                    ${remainingEntries.length ? `<div class="tool-request-summary">${remainingEntries.slice(0, 6).map(([key, value]) => `
                        <div class="tool-request-item">
                            <div class="tool-request-key">${escapeHtml(key)}</div>
                            <div class="tool-request-value">${escapeHtml(summarizeValue(value) || '(empty)')}</div>
                        </div>
                    `).join('')}</div>` : ''}
                </div>
                <details class="delegate-task-raw"><summary>Raw output</summary><pre class="tool-output-json">${highlightJSON(rawOutput || '')}</pre></details>
            </div>
        </div>
    `;
}

function renderSessionSearchOutput(parsedOutput, rawOutput) {
    const mode = parsedOutput?.mode || '';
    const results = Array.isArray(parsedOutput?.results) ? parsedOutput.results : [];
    const count = parsedOutput?.count;
    const summary = parsedOutput?.message || parsedOutput?.summary || '';
    return `
        <div class="tool-section">
            <label>Output</label>
            <div class="structured-output">
                <div class="structured-output-card">
                    <div class="structured-output-title">Session Search</div>
                    ${summary ? `<div>${escapeHtml(summary)}</div>` : ''}
                    <div class="structured-output-meta">${escapeHtml([
                        mode ? `mode: ${mode}` : '',
                        count !== undefined ? `${count} items` : '',
                    ].filter(Boolean).join(' • '))}</div>
                </div>
                ${results.length ? `<div class="delegate-task-results">${results.map((result, idx) => {
                    const title = result?.title || result?.session_id || `Session ${idx + 1}`;
                    const meta = [
                        result?.timestamp ? formatTimestamp(result.timestamp) : '',
                        result?.session_id ? String(result.session_id).slice(0, 8) : '',
                    ].filter(Boolean).join(' • ');
                    const body = result?.summary || result?.preview || result?.content || '';
                    return `
                        <div class="delegate-task-item success">
                            <div class="delegate-task-topline">
                                <div class="delegate-task-title">${escapeHtml(title)}</div>
                                ${meta ? `<div class="delegate-task-meta">${escapeHtml(meta)}</div>` : ''}
                            </div>
                            ${body ? `<div class="delegate-task-summary">${escapeHtml(body)}</div>` : ''}
                        </div>
                    `;
                }).join('')}</div>` : ''}
                <details class="delegate-task-raw"><summary>Raw output</summary><pre class="tool-output-json">${highlightJSON(rawOutput || '')}</pre></details>
            </div>
        </div>
    `;
}

function renderToolOutput(toolName, parsedOutput, rawOutput, outputCaptured = rawOutput !== '') {
    if (!rawOutput) {
        return `
            <div class="tool-section tool-call-result">
                <label>Output</label>
                <pre>${outputCaptured ? 'Tool completed with empty output.' : 'Tool is still running. Final output will appear here when the call completes.'}</pre>
            </div>
        `;
    }
    if (toolName === 'delegate_task' && parsedOutput && typeof parsedOutput === 'object') {
        return renderDelegateTaskOutput(parsedOutput, rawOutput);
    }
    if (toolName === 'skill_view' && parsedOutput && typeof parsedOutput === 'object') {
        return renderSkillViewOutput(parsedOutput, rawOutput);
    }
    if (toolName === 'session_search' && parsedOutput && typeof parsedOutput === 'object') {
        return renderSessionSearchOutput(parsedOutput, rawOutput);
    }
    if (parsedOutput && typeof parsedOutput === 'object') {
        return renderStructuredJsonOutput(parsedOutput, rawOutput);
    }
    return `<div class="tool-section tool-call-result"><label>Output</label>${formatToolOutputText(rawOutput)}</div>`;
}

function normalizeTaskIndex(value) {
    if (Number.isInteger(value)) return value;
    if (typeof value === 'string' && value.trim() !== '' && Number.isInteger(Number(value))) return Number(value);
    return null;
}

function getEventMetadata(parsed) {
    const args = (parsed && typeof parsed.arguments === 'object' && parsed.arguments !== null) ? parsed.arguments : {};
    const rawArgs = (parsed && typeof parsed.args === 'object' && parsed.args !== null) ? parsed.args : {};
    return { ...args, ...rawArgs, ...(parsed || {}) };
}

function renderDelegateChildStreams(tool) {
    if (!tool) return '';
    const childEntries = liveChildSessionMap.get(tool.call_id || '') || [];
    const childEvents = (tool.child_events && typeof tool.child_events === 'object') ? tool.child_events : {};
    const keys = Object.keys(childEvents);
    if (!keys.length && !childEntries.length) return '';
    const allEvents = keys.flatMap(key => Array.isArray(childEvents[key]) ? childEvents[key] : []);
    const activeCount = allEvents.filter(event => event.type === 'tool_call' && !hasCapturedToolOutput(event.tool)).length;
    const completedCount = allEvents.filter(event => event.type === 'tool_output').length;
    const liveSummary = `<div class="subagent-activity-summary">
        <span class="subagent-badge">${allEvents.length} event${allEvents.length === 1 ? '' : 's'}</span>
        ${activeCount > 0 ? `<span class="subagent-badge active">${activeCount} running</span>` : ''}
        ${completedCount > 0 ? `<span class="subagent-badge complete">${completedCount} done</span>` : ''}
    </div>`;
    const representedKeys = new Set();
    const monitorRows = childEntries.map((entry, idx) => {
        const taskIndex = normalizeTaskIndex(entry.taskIndex);
        const key = Number.isInteger(taskIndex) ? String(taskIndex) : 'default';
        representedKeys.add(key);
        const events = Array.isArray(childEvents[key]) ? childEvents[key] : [];
        const latest = events[events.length - 1] || {};
        const statusClass = events.length ? (activeCount > 0 ? 'running' : 'success') : 'pending';
        return `<div class="subagent-monitor-row">
            <span class="tool-call-status-dot ${statusClass}"></span>
            <div class="subagent-monitor-main">
                <div class="subagent-monitor-title">${escapeHtml(Number.isInteger(taskIndex) ? `Task ${taskIndex + 1}` : `Subagent ${idx + 1}`)}</div>
                <div class="subagent-monitor-meta">${escapeHtml((entry.childSessionId || '').slice(0, 12) || 'pending session')} · ${escapeHtml(latest.name || latest.tool?.name || (events.length ? 'activity' : 'waiting'))} · ${events.length} event${events.length === 1 ? '' : 's'}</div>
            </div>
            <div class="subagent-monitor-actions">
                <button class="btn live-view-btn" type="button" data-child-session-id="${escapeHtml(entry.childSessionId)}" data-delegate-call-id="${escapeHtml(tool.call_id || '')}" data-label="${escapeHtml(entry.label || '')}">Open window</button>
                <button class="btn emergency-stop-btn subagent-stop-btn" type="button" data-child-session-id="${escapeHtml(entry.childSessionId)}">Stop</button>
            </div>
        </div>`;
    });
    keys.filter(key => !representedKeys.has(key)).forEach(key => {
        const events = Array.isArray(childEvents[key]) ? childEvents[key] : [];
        const latest = events[events.length - 1] || {};
        monitorRows.push(`<div class="subagent-monitor-row">
            <span class="tool-call-status-dot ${events.length ? 'running' : 'pending'}"></span>
            <div class="subagent-monitor-main"><div class="subagent-monitor-title">${escapeHtml(key === 'default' ? 'Subagent activity' : `Task ${Number(key) + 1}`)}</div><div class="subagent-monitor-meta">${escapeHtml(latest.name || latest.tool?.name || 'activity')} · ${events.length} event${events.length === 1 ? '' : 's'}</div></div>
        </div>`);
    });
    return `<div class="tool-section"><label>Subagent Activity</label>${liveSummary}<div class="subagent-monitor-list">${monitorRows.join('')}</div></div>`;
}

// Global mapping for child sessions discovered via live stream
const liveChildSessionMap = new Map();
const drawerEventSources = new Map();
const childDrawerEventCache = new Map();
const childDrawerPersistedEventKeys = new Map();
const childDrawerSnapshotFingerprints = new Map();
const childDrawerPausedSet = new Set();
const childDrawerPausedQueue = new Map();
// Preserve the latest connection/terminal state independently of chat markup.
const childDrawerStatusMap = new Map();
const childDrawerDedupState = new Map();
const DRAWER_DEDUP_MAX_KEYS = 500;
const DRAWER_SIGNATURE_WINDOW_MS = 1500;
// Window state and DOM live at body level, outside assistant messages that rerender.
const openDrawerSet = new Set();
const childDrawerRegistry = new Map();
const childWindowState = new Map();
const childFlightEventSources = new Map();
const restoredChildFlightSessions = new Set();
let profileBotSessions = new Map();
let profileBotFlightPollTimer = null;
let profileBotFlightPollInFlight = false;
let childWindowZIndex = 1200;
let childMobileWindowSequence = 0;
const MOBILE_WINDOW_MAX_SLOTS = 6;
const MOBILE_WINDOW_SLOT_STEP_PX = 42;
const ACTIVE_CHILD_DRAWER_STATUSES = new Set(['LIVE', 'RECONNECTING', 'OFFLINE', 'PAUSED', 'STOPPING']);
const parentCompletionReconcileTimers = new Map();
const reconciledParentCompletionMessages = new Set();
const PARENT_COMPLETION_RECONCILE_INTERVAL_MS = 2000;
const PARENT_COMPLETION_RECONCILE_TIMEOUT_MS = 10 * 60 * 1000;

function getInFlightSubagents() {
    return Array.from(childDrawerRegistry.values())
        .filter(entry => !entry.profileBot && ACTIVE_CHILD_DRAWER_STATUSES.has(childDrawerStatusMap.get(entry.childSessionId) || ''))
        .sort((a, b) => (normalizeTaskIndex(a.taskIndex) ?? Number.MAX_SAFE_INTEGER) - (normalizeTaskIndex(b.taskIndex) ?? Number.MAX_SAFE_INTEGER));
}

function rememberRunChildSession(runState, entry, status = 'LIVE') {
    if (!runState || !entry?.childSessionId) return;
    const children = Array.isArray(runState.childSessions) ? runState.childSessions : [];
    const existing = children.find(child => child.childSessionId === entry.childSessionId);
    if (existing) Object.assign(existing, entry, { status });
    else children.push({ ...entry, status });
    runState.childSessions = children;
}

function restoreActiveRunChildSessions() {
    Object.values(activeRuns).forEach(runState => {
        (Array.isArray(runState?.childSessions) ? runState.childSessions : []).forEach(entry => {
            if (!entry?.childSessionId || !ACTIVE_CHILD_DRAWER_STATUSES.has(entry.status || 'LIVE')) return;
            rememberChildDrawer(entry.childSessionId, entry);
            childDrawerStatusMap.set(entry.childSessionId, entry.status || 'LIVE');
            restoredChildFlightSessions.add(entry.childSessionId);
            watchSubagentFlightStatus(entry.childSessionId);
            const delegateEntries = liveChildSessionMap.get(entry.delegateCallId || '') || [];
            if (!delegateEntries.some(child => child.childSessionId === entry.childSessionId)) delegateEntries.push(entry);
            liveChildSessionMap.set(entry.delegateCallId || '', delegateEntries);
        });
    });
    renderChatRoomRail();
}

function renderSubagentFlightRailItem() {
    const children = getInFlightSubagents();
    if (!children.length) return '';
    const count = children.length;
    return `<button class="subagent-flight-toggle" type="button" aria-haspopup="dialog" aria-expanded="false" title="${count} delegated subagent${count === 1 ? '' : 's'} working" aria-label="Watch ${count} delegated subagent${count === 1 ? '' : 's'} working">
        <span class="subagent-flight-glyph" aria-hidden="true"><span class="subagent-flight-antenna"></span><span class="subagent-flight-eye left"></span><span class="subagent-flight-eye right"></span></span>
        <span class="subagent-flight-count" aria-hidden="true">${count}</span>
        <span class="chat-room-tab-copy"><strong>Subagents working</strong><small>${count} delegated task${count === 1 ? '' : 's'} in flight</small></span>
    </button>`;
}

function renderRoomChildSessionEntries(roomId) {
    const run = getActiveRun(roomId);
    const runChildren = Array.isArray(run?.childSessions) ? run.childSessions : [];
    const profile = String(roomId || '').startsWith('bot:') ? String(roomId).slice(4) : '';
    const profileChildren = (profileBotSessions.get(profile) || []).map(child => ({ ...child, profileBot: true, profile }));
    const children = [...runChildren, ...profileChildren].filter((child, index, all) => (
        child?.childSessionId && all.findIndex(item => item?.childSessionId === child.childSessionId) === index
    ));
    if (!children.length) return '';
    const rows = children.map(child => {
        if (!child?.childSessionId) return '';
        const status = child.status || 'LIVE';
        const label = child.label || 'delegate_task';
        const id = child.childSessionId;
        if (child.profileBot) {
            const identity = child.bot || botRegistry.find(bot => bot.name === profile) || { name: profile, display_name: profile };
            const botName = identity.display_name || identity.name || profile || 'Bot';
            return `<div class="chat-room-child profile-bot-room-child">
                <button class="chat-room-child-open live-view-btn" type="button" data-child-session-id="${escapeHtml(id)}" data-label="${escapeHtml(label)}" title="Watch ${escapeHtml(botName)}: ${escapeHtml(label)}" aria-label="Watch ${escapeHtml(botName)} live session ${escapeHtml(label)}">
                    <span class="profile-bot-child-avatar">${avatarHtml(identity, { className: 'bot-avatar-flight', decorative: true })}<span class="chat-room-child-dot is-${escapeHtml(String(status).toLowerCase())}"></span></span>
                    <span class="chat-room-child-copy"><strong>${escapeHtml(label)}</strong><small>${escapeHtml(botName)} &middot; ${escapeHtml(status)}</small></span>
                </button>
            </div>`;
        }
        return `<div class="chat-room-child">
            <button class="chat-room-child-open live-view-btn" type="button" data-child-session-id="${escapeHtml(id)}" data-delegate-call-id="${escapeHtml(child.delegateCallId || '')}" data-label="${escapeHtml(label)}" title="Open live session ${escapeHtml(label)}" aria-label="Open live session ${escapeHtml(label)}">
                <span class="chat-room-child-dot is-${escapeHtml(String(status).toLowerCase())}"></span>
                <span class="chat-room-child-copy"><strong>${escapeHtml(label)}</strong><small>${escapeHtml((id || '').slice(0, 12))} · ${escapeHtml(status)}</small></span>
            </button>
            <button class="chat-room-child-stop subagent-stop-btn" type="button" data-child-session-id="${escapeHtml(id)}" title="Stop ${escapeHtml(label)}" aria-label="Stop ${escapeHtml(label)}">&times;</button>
        </div>`;
    }).join('');
    return `<div class="chat-room-children${profileChildren.length ? ' has-profile-bot' : ''}" role="list" aria-label="Live sessions">${rows}</div>`;
}

function ensureSubagentFlightPopover() {
    let popover = document.getElementById('subagent-flight-popover');
    if (popover) return popover;
    popover = document.createElement('section');
    popover.id = 'subagent-flight-popover';
    popover.className = 'subagent-flight-popover';
    popover.setAttribute('role', 'dialog');
    popover.setAttribute('aria-label', 'In-flight delegated subagents');
    popover.hidden = true;
    document.body.appendChild(popover);
    return popover;
}

function closeSubagentFlightPopover() {
    const popover = document.getElementById('subagent-flight-popover');
    if (popover) popover.hidden = true;
    document.querySelectorAll('.subagent-flight-toggle').forEach(button => button.setAttribute('aria-expanded', 'false'));
}

function renderSubagentFlightPopover(anchorEl = document.querySelector('.subagent-flight-toggle')) {
    const children = getInFlightSubagents();
    const popover = ensureSubagentFlightPopover();
    if (!children.length) {
        closeSubagentFlightPopover();
        return;
    }
    const focused = document.activeElement?.closest?.('.live-view-btn, .subagent-stop-btn');
    const focusedChildId = focused?.dataset?.childSessionId || '';
    const focusedAction = focused?.classList.contains('subagent-stop-btn') ? 'stop' : (focused ? 'watch' : '');
    const closeWasFocused = document.activeElement?.classList?.contains('subagent-flight-close');
    popover.innerHTML = `<header><div><span class="subagent-flight-kicker">DELEGATED WORK</span><h3>${children.length} subagent${children.length === 1 ? '' : 's'} in flight</h3></div><button type="button" class="subagent-flight-close" aria-label="Close subagent monitor">&times;</button></header>
        <div class="subagent-flight-list">${children.map((entry, index) => {
            const taskIndex = normalizeTaskIndex(entry.taskIndex);
            const title = entry.label || (Number.isInteger(taskIndex) ? `Task ${taskIndex + 1}` : `Subagent ${index + 1}`);
            const status = childDrawerStatusMap.get(entry.childSessionId) || 'LIVE';
            return `<article class="subagent-flight-row">
                <span class="subagent-flight-row-pulse" aria-hidden="true"></span>
                <div><strong>${escapeHtml(title)}</strong><small>${escapeHtml(entry.childSessionId.slice(0, 12))} &middot; ${escapeHtml(status.toLowerCase())}</small></div>
                <button class="btn live-view-btn" type="button" data-child-session-id="${escapeHtml(entry.childSessionId)}" data-delegate-call-id="${escapeHtml(entry.delegateCallId || '')}" data-label="${escapeHtml(title)}">Watch live</button>
                ${entry.profileBot ? '' : `<button class="btn emergency-stop-btn subagent-stop-btn" type="button" data-child-session-id="${escapeHtml(entry.childSessionId)}">Emergency stop</button>`}
            </article>`;
        }).join('')}</div>`;
    if (anchorEl) {
        const rect = anchorEl.getBoundingClientRect();
        const width = Math.min(480, Math.max(320, window.innerWidth - 24));
        popover.style.width = `${width}px`;
        popover.style.left = `${Math.max(12, Math.min(rect.right + 10, window.innerWidth - width - 12))}px`;
        popover.style.top = `${Math.min(Math.max(12, rect.top), Math.max(12, window.innerHeight - 420))}px`;
    }
    if (focusedChildId) {
        const selector = focusedAction === 'stop' ? '.subagent-stop-btn' : '.live-view-btn';
        const restoredFocus = popover.querySelector(`${selector}[data-child-session-id="${CSS.escape(focusedChildId)}"]`);
        (restoredFocus || popover.querySelector('.live-view-btn, .subagent-flight-close'))?.focus();
    } else if (closeWasFocused) {
        popover.querySelector('.subagent-flight-close')?.focus();
    }
}

function toggleSubagentFlightPopover(anchorEl) {
    const popover = ensureSubagentFlightPopover();
    if (!popover.hidden) {
        closeSubagentFlightPopover();
        return;
    }
    renderSubagentFlightPopover(anchorEl);
    if (!getInFlightSubagents().length) return;
    popover.hidden = false;
    anchorEl?.setAttribute('aria-expanded', 'true');
    popover.querySelector('.live-view-btn, .subagent-flight-close')?.focus();
}

function syncSubagentFlightUi() {
    renderChatRoomRail();
    const popover = document.getElementById('subagent-flight-popover');
    if (popover && !popover.hidden) {
        renderSubagentFlightPopover();
        document.querySelector('.subagent-flight-toggle')?.setAttribute('aria-expanded', 'true');
    }
}

function rememberChildDrawer(childSessionId, data = {}) {
    if (!childSessionId) return;
    const existing = childDrawerRegistry.get(childSessionId) || {};
    childDrawerRegistry.set(childSessionId, { ...existing, childSessionId, label: data.label ?? existing.label ?? '', delegateCallId: data.delegateCallId ?? existing.delegateCallId ?? '', taskIndex: data.taskIndex ?? existing.taskIndex ?? null, parentSessionId: data.parentSessionId ?? existing.parentSessionId ?? '', profile: data.profile ?? existing.profile ?? '', profileBot: data.profileBot ?? existing.profileBot ?? false, bot: data.bot ?? existing.bot ?? null });
}

function isBackgroundCompletionPrompt(message) {
    if (message?.role !== 'user' || typeof message.content !== 'string') return false;
    const content = message.content.trimStart();
    return content.startsWith('[ASYNC DELEGATION COMPLETE')
        || content.startsWith('[ASYNC DELEGATION BATCH COMPLETE')
        || content.startsWith('[IMPORTANT:');
}

function completionGoalNeedle(label) {
    const needle = String(label || '')
        .replace(/\s+/g, ' ')
        .trim()
        .slice(0, 80)
        .toLowerCase();
    return ['delegate_task', 'subagent', 'background subagent'].includes(needle) ? '' : needle;
}

function findBackgroundCompletionResponse(data, label = '') {
    const rows = Array.isArray(data?.messages) ? data.messages : [];
    const needle = completionGoalNeedle(label);
    for (let index = rows.length - 1; index >= 0; index -= 1) {
        const message = rows[index];
        if (!isBackgroundCompletionPrompt(message)) continue;
        const content = String(message.content || '').replace(/\s+/g, ' ').toLowerCase();
        if (needle && !content.includes(needle)) continue;
        let completionResponse = null;
        for (let responseIndex = index + 1; responseIndex < rows.length; responseIndex += 1) {
            const response = rows[responseIndex];
            if (response?.role === 'user') break;
            if (response?.role === 'assistant' && String(response.content || '').trim()) completionResponse = response;
        }
        return completionResponse;
    }
    return null;
}

function stopParentCompletionReconcile(childSessionId) {
    const state = parentCompletionReconcileTimers.get(childSessionId);
    if (state?.timer) clearTimeout(state.timer);
    parentCompletionReconcileTimers.delete(childSessionId);
}

function scheduleParentCompletionReconcile(childSessionId) {
    const entry = childDrawerRegistry.get(childSessionId) || {};
    const parentSessionId = String(entry.parentSessionId || '').trim();
    if (!childSessionId || !parentSessionId || entry.profileBot) return;
    stopParentCompletionReconcile(childSessionId);
    const state = { startedAt: Date.now(), timer: null, inFlight: false };
    parentCompletionReconcileTimers.set(childSessionId, state);

    const schedule = () => {
        if (!parentCompletionReconcileTimers.has(childSessionId)) return;
        if (Date.now() - state.startedAt >= PARENT_COMPLETION_RECONCILE_TIMEOUT_MS) {
            stopParentCompletionReconcile(childSessionId);
            return;
        }
        state.timer = setTimeout(poll, PARENT_COMPLETION_RECONCILE_INTERVAL_MS);
    };
    const poll = async () => {
        if (state.inFlight || !parentCompletionReconcileTimers.has(childSessionId)) return;
        if (activeChatRoomId !== 'main' || activeChatSessionId !== parentSessionId || getActiveRun('main') || streamResumeRooms.has('main') || chatResetInFlight) {
            schedule();
            return;
        }
        state.inFlight = true;
        try {
            const data = await fetchJsonOrThrow(`/api/sessions/${encodeURIComponent(parentSessionId)}`);
            const completionResponse = findBackgroundCompletionResponse(data, entry.label);
            if (!completionResponse) {
                schedule();
                return;
            }
            const completionKey = `${parentSessionId}:${completionResponse.id ?? completionResponse.timestamp ?? completionResponse.content}`;
            if (reconciledParentCompletionMessages.has(completionKey)) {
                stopParentCompletionReconcile(childSessionId);
                return;
            }
            reconciledParentCompletionMessages.add(completionKey);
            conversation = buildConversationFromSessionData(data);
            saveConversation();
            renderConversation();
            const lastAssistant = [...conversation].reverse().find(message => message.role === 'assistant');
            updateContextDisplay(lastAssistant ? normalizeAssistantMessage(lastAssistant) : { usage: null, last_prompt_tokens: 0 });
            refreshTokenUsageSoon();
            void refreshSessionContextInfo(parentSessionId);
            showToast(`${entry.label || 'Background subagent'} completed; Hermes posted its summary.`);
            stopParentCompletionReconcile(childSessionId);
        } catch (error) {
            log('warn', `Could not reconcile parent session ${parentSessionId}: ${error.message || error}`);
            schedule();
        } finally {
            state.inFlight = false;
        }
    };
    void poll();
}

async function refreshProfileBotFlights() {
    if (profileBotFlightPollInFlight) return;
    profileBotFlightPollInFlight = true;
    try {
        const response = await fetch('/api/bots/in-flight', { headers: { Accept: 'application/json' } });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
        const next = new Map();
        (Array.isArray(data.sessions) ? data.sessions : []).forEach(session => {
            const profile = String(session.profile || '').trim();
            const childSessionId = String(session.session_id || '').trim();
            if (!profile || !childSessionId) return;
            const entry = {
                childSessionId,
                label: session.title || `${session.bot?.display_name || profile} session`,
                delegateCallId: '',
                taskIndex: null,
                parentSessionId: '',
                profile,
                profileBot: true,
                bot: session.bot || null,
                status: 'LIVE',
            };
            const sessions = next.get(profile) || [];
            sessions.push(entry);
            next.set(profile, sessions);
            rememberChildDrawer(childSessionId, entry);
            updateDrawerBadge(childSessionId, 'LIVE');
        });
        const liveIds = new Set(Array.from(next.values()).flat().map(entry => entry.childSessionId));
        Array.from(profileBotSessions.values()).flat().forEach(entry => {
            if (liveIds.has(entry.childSessionId)) return;
            const status = childDrawerStatusMap.get(entry.childSessionId);
            if (ACTIVE_CHILD_DRAWER_STATUSES.has(status || '')) updateDrawerBadge(entry.childSessionId, 'DONE');
        });
        profileBotSessions = next;
        syncSubagentFlightUi();
    } catch (error) {
        log('warn', `Could not refresh in-flight bot sessions: ${error.message || error}`);
    } finally {
        profileBotFlightPollInFlight = false;
    }
}

function startProfileBotFlightPolling() {
    if (profileBotFlightPollTimer) clearInterval(profileBotFlightPollTimer);
    void refreshProfileBotFlights();
    profileBotFlightPollTimer = setInterval(() => void refreshProfileBotFlights(), 2000);
}

function ensureSubagentWindowLayer() {
    let layer = document.getElementById('subagent-window-layer');
    if (layer) return layer;
    layer = document.createElement('div');
    layer.id = 'subagent-window-layer';
    layer.setAttribute('aria-live', 'polite');
    document.body.appendChild(layer);
    if (typeof window !== 'undefined' && !window.__subagentWindowResizeBound) {
        window.__subagentWindowResizeBound = true;
        window.addEventListener('resize', () => {
            document.querySelectorAll('.subagent-window').forEach(windowEl => clampSubagentWindowToViewport(windowEl));
        });
    }
    return layer;
}

function renderChildSessionDrawerShell(childSessionId, label = '') {
    if (!childSessionId) return '';
    const status = childDrawerStatusMap.get(childSessionId) || 'LIVE';
    const isLive = status === 'LIVE';
    const isDisconnected = status === 'RECONNECTING' || status === 'OFFLINE';
    const entry = childDrawerRegistry.get(childSessionId) || {};
    const profileBot = Boolean(entry.profileBot);
    const identity = entry.bot || botRegistry.find(bot => bot.name === entry.profile) || null;
    const botName = profileBot ? (identity?.display_name || identity?.name || entry.profile || 'Bot') : '';
    const drawerTitle = profileBot ? botName : (label || 'Subagent');
    const dotColor = status === 'ERROR' ? 'var(--error)' : (isDisconnected ? 'var(--warning, #d6a84b)' : 'var(--success)');
    return `<section class="child-session-drawer subagent-window" data-child-session-id="${escapeHtml(childSessionId)}" role="dialog" aria-label="${escapeHtml(drawerTitle)} live session">
        <div class="drawer-header" data-subagent-drag-handle><div class="drawer-header-info"><span class="drawer-header-title">${escapeHtml(drawerTitle)}</span><span class="drawer-header-id">${escapeHtml(childSessionId.slice(0, 16))}</span>${profileBot && label ? `<span class="drawer-header-label">${escapeHtml(label)}</span>` : ''}</div>
        <div class="drawer-header-actions"><span class="live-badge ${isLive ? 'active' : ''}" data-badge="${escapeHtml(childSessionId)}"><span class="live-dot"${isLive ? '' : ` style="animation:none;background:${dotColor};"`}></span>${escapeHtml(status)}</span>${profileBot ? '' : `<button class="btn subagent-pause-btn" type="button" data-child-session-id="${escapeHtml(childSessionId)}" data-control-mode="soft">Soft pause</button><button class="btn subagent-pause-btn" type="button" data-child-session-id="${escapeHtml(childSessionId)}" data-control-mode="hard">Hard pause</button><button class="btn subagent-steer-btn" type="button" data-child-session-id="${escapeHtml(childSessionId)}" data-control-mode="soft">Soft steer</button><button class="btn subagent-steer-btn" type="button" data-child-session-id="${escapeHtml(childSessionId)}" data-control-mode="hard">Hard steer</button><button class="btn emergency-stop-btn subagent-stop-btn" type="button" data-child-session-id="${escapeHtml(childSessionId)}">Stop</button>`}<button class="drawer-minimize-btn" type="button" data-minimize-child-session="${escapeHtml(childSessionId)}" aria-label="Minimize subagent window">−</button><button class="drawer-close-btn" type="button" data-close-child-session="${escapeHtml(childSessionId)}" aria-label="Close subagent window">×</button></div></div>
        <div class="drawer-transcript" data-drawer-transcript="${escapeHtml(childSessionId)}"></div>
        <div class="subagent-resize-handle" data-subagent-resize-handle role="button" tabindex="0" aria-label="Resize subagent window; use arrow keys"></div>
    </section>`;
}

function getSubagentWindowState(childSessionId) {
    let state = childWindowState.get(childSessionId);
    if (!state) {
        const offset = childWindowState.size % 6;
        const mobileIndex = childMobileWindowSequence % getMobileWindowSlotCount();
        childMobileWindowSequence += 1;
        state = { left: 32 + offset * 28, top: 72 + offset * 28, width: 560, height: 440, minimized: false, mobileIndex, zIndex: ++childWindowZIndex };
        childWindowState.set(childSessionId, state);
    }
    return state;
}

function getMobileWindowSlotCount(viewportHeight = null) {
    const height = viewportHeight ?? window.innerHeight ?? document.documentElement.clientHeight ?? 240;
    return Math.max(1, Math.min(MOBILE_WINDOW_MAX_SLOTS, Math.floor((Math.max(240, height) - 52) / MOBILE_WINDOW_SLOT_STEP_PX) + 1));
}

function refreshMobileWindowSlots() {
    const slotCount = getMobileWindowSlotCount();
    document.querySelectorAll('.subagent-window[data-child-session-id]').forEach((windowEl, index) => {
        const state = childWindowState.get(windowEl.dataset.childSessionId || '');
        if (!state) return;
        state.mobileIndex = index % slotCount;
        windowEl.style.setProperty('--mobile-window-index', String(state.mobileIndex));
    });
}

function clampSubagentWindowToViewport(windowEl, state = null) {
    if (!windowEl) return;
    state = state || getSubagentWindowState(windowEl.dataset.childSessionId || '');
    const viewportWidth = Math.max(320, window.innerWidth || document.documentElement.clientWidth || 320);
    const viewportHeight = Math.max(240, window.innerHeight || document.documentElement.clientHeight || 240);
    state.width = Math.min(Math.max(320, state.width), Math.max(320, viewportWidth - 16));
    state.height = Math.min(Math.max(220, state.height), Math.max(220, viewportHeight - 16));
    state.left = Math.min(Math.max(8, state.left), Math.max(8, viewportWidth - state.width - 8));
    state.top = Math.min(Math.max(8, state.top), Math.max(8, viewportHeight - (state.minimized ? 52 : state.height) - 8));
    state.mobileIndex %= getMobileWindowSlotCount(viewportHeight);
    windowEl.style.left = `${state.left}px`;
    windowEl.style.top = `${state.top}px`;
    windowEl.style.width = `${state.width}px`;
    windowEl.style.height = `${state.height}px`;
    windowEl.style.zIndex = String(state.zIndex);
    windowEl.style.setProperty('--mobile-window-index', String(state.mobileIndex));
}

function bringSubagentWindowToFront(windowEl) {
    if (!windowEl) return;
    const state = getSubagentWindowState(windowEl.dataset.childSessionId || '');
    state.zIndex = ++childWindowZIndex;
    windowEl.style.zIndex = String(state.zIndex);
    windowEl.focus?.({ preventScroll: true });
}

function setSubagentWindowMinimized(childSessionId, minimized = null) {
    const windowEl = document.querySelector(`.subagent-window[data-child-session-id="${CSS.escape(childSessionId)}"]`);
    if (!windowEl) return;
    const state = getSubagentWindowState(childSessionId);
    state.minimized = minimized === null ? !state.minimized : Boolean(minimized);
    windowEl.classList.toggle('subagent-window-minimized', state.minimized);
    const button = windowEl.querySelector('[data-minimize-child-session]');
    if (button) {
        button.textContent = state.minimized ? '□' : '−';
        button.setAttribute('aria-label', state.minimized ? 'Restore subagent window' : 'Minimize subagent window');
    }
    clampSubagentWindowToViewport(windowEl, state);
    bringSubagentWindowToFront(windowEl);
}

function initializeSubagentWindow(windowEl, childSessionId) {
    if (!windowEl || windowEl.dataset.windowBound) return;
    windowEl.dataset.windowBound = 'true';
    windowEl.tabIndex = -1;
    const state = getSubagentWindowState(childSessionId);
    windowEl.classList.toggle('subagent-window-minimized', state.minimized);
    clampSubagentWindowToViewport(windowEl, state);
    windowEl.addEventListener('pointerdown', () => bringSubagentWindowToFront(windowEl));
    const dragHandle = windowEl.querySelector('[data-subagent-drag-handle]');
    dragHandle?.addEventListener('pointerdown', (event) => {
        if (event.target.closest('button')) return;
        event.preventDefault();
        bringSubagentWindowToFront(windowEl);
        const startX = event.clientX;
        const startY = event.clientY;
        const startLeft = state.left;
        const startTop = state.top;
        dragHandle.setPointerCapture?.(event.pointerId);
        const move = (moveEvent) => {
            state.left = startLeft + moveEvent.clientX - startX;
            state.top = startTop + moveEvent.clientY - startY;
            clampSubagentWindowToViewport(windowEl, state);
        };
        const done = (upEvent) => {
            dragHandle.releasePointerCapture?.(upEvent.pointerId);
            dragHandle.removeEventListener('pointermove', move);
            dragHandle.removeEventListener('pointerup', done);
            dragHandle.removeEventListener('pointercancel', done);
        };
        dragHandle.addEventListener('pointermove', move);
        dragHandle.addEventListener('pointerup', done);
        dragHandle.addEventListener('pointercancel', done);
    });
    const resizeHandle = windowEl.querySelector('[data-subagent-resize-handle]');
    resizeHandle?.addEventListener('pointerdown', (event) => {
        event.preventDefault();
        event.stopPropagation();
        bringSubagentWindowToFront(windowEl);
        const startX = event.clientX;
        const startY = event.clientY;
        const startWidth = state.width;
        const startHeight = state.height;
        resizeHandle.setPointerCapture?.(event.pointerId);
        const move = (moveEvent) => {
            state.width = startWidth + moveEvent.clientX - startX;
            state.height = startHeight + moveEvent.clientY - startY;
            clampSubagentWindowToViewport(windowEl, state);
        };
        const done = (upEvent) => {
            resizeHandle.releasePointerCapture?.(upEvent.pointerId);
            resizeHandle.removeEventListener('pointermove', move);
            resizeHandle.removeEventListener('pointerup', done);
            resizeHandle.removeEventListener('pointercancel', done);
        };
        resizeHandle.addEventListener('pointermove', move);
        resizeHandle.addEventListener('pointerup', done);
        resizeHandle.addEventListener('pointercancel', done);
    });
    resizeHandle?.addEventListener('keydown', (event) => {
        const amount = event.shiftKey ? 40 : 10;
        if (event.key === 'ArrowRight') state.width += amount;
        else if (event.key === 'ArrowLeft') state.width -= amount;
        else if (event.key === 'ArrowDown') state.height += amount;
        else if (event.key === 'ArrowUp') state.height -= amount;
        else return;
        event.preventDefault();
        clampSubagentWindowToViewport(windowEl, state);
    });
    bringSubagentWindowToFront(windowEl);
}

function getDrawerTranscript(childSessionId) {
    if (!childSessionId) return null;
    return document.querySelector(`[data-drawer-transcript="${CSS.escape(childSessionId)}"]`);
}

function recordDrawerEvent(childSessionId, parsed) {
    if (!childSessionId || !parsed) return;
    const cache = childDrawerEventCache.get(childSessionId) || [];
    cache.push(parsed);
    if (cache.length > 300) cache.splice(0, cache.length - 300);
    childDrawerEventCache.set(childSessionId, cache);
}

function stableDrawerEventSignature(value, seen = new WeakSet()) {
    if (value === null || typeof value !== 'object') return JSON.stringify(value);
    if (seen.has(value)) return '"[circular]"';
    seen.add(value);
    if (Array.isArray(value)) return `[${value.map(item => stableDrawerEventSignature(item, seen)).join(',')}]`;
    return `{${Object.keys(value).sort().map(key => `${JSON.stringify(key)}:${stableDrawerEventSignature(value[key], seen)}`).join(',')}}`;
}

function drawerSessionSnapshotFingerprint(data) {
    const serialized = stableDrawerEventSignature({
        messages: data?.messages || [],
        children: data?.children || [],
        related_artifacts: data?.related_artifacts || [],
        background_reviews: data?.background_reviews || [],
        ended_at: data?.ended_at ?? null,
        end_reason: data?.end_reason || '',
    });
    let hash = 2166136261;
    for (let index = 0; index < serialized.length; index++) {
        hash ^= serialized.charCodeAt(index);
        hash = Math.imul(hash, 16777619);
    }
    return `${serialized.length}:${hash >>> 0}`;
}

function getDrawerEventDedupKey(parsed) {
    const metadata = getEventMetadata(parsed);
    const explicitId = parsed.event_id ?? parsed.eventId ?? parsed.id ?? metadata.event_id ?? metadata.eventId;
    if (explicitId !== undefined && explicitId !== null && explicitId !== '') return `id:${String(explicitId)}`;
    const sequence = parsed.sequence ?? parsed.seq ?? parsed.sequence_index ?? metadata.sequence ?? metadata.seq ?? metadata.sequence_index;
    if (sequence !== undefined && sequence !== null && sequence !== '') return `seq:${String(sequence)}`;
    return `sig:${stableDrawerEventSignature(parsed)}`;
}

function shouldAcceptDrawerEvent(childSessionId, parsed, now = Date.now()) {
    if (!childSessionId || !parsed) return false;
    let state = childDrawerDedupState.get(childSessionId);
    if (!state) {
        state = new Map();
        childDrawerDedupState.set(childSessionId, state);
    }
    const key = getDrawerEventDedupKey(parsed);
    const previous = state.get(key);
    const isFallback = key.startsWith('sig:');
    if (previous !== undefined && (!isFallback || now - previous <= DRAWER_SIGNATURE_WINDOW_MS)) return false;
    state.delete(key);
    state.set(key, now);
    while (state.size > DRAWER_DEDUP_MAX_KEYS) state.delete(state.keys().next().value);
    return true;
}

function renderDrawerEventRow(transcriptEl, parsed) {
    if (!transcriptEl || !parsed) return;
    if (transcriptEl.textContent.trim() === 'No activity recorded yet.' || transcriptEl.textContent.trim() === 'Loading session...') transcriptEl.innerHTML = '';
    const row = document.createElement('div');
    row.className = 'drawer-tool-row';
    const meta = getEventMetadata(parsed);
    if (parsed.type === 'tool_call' || parsed.type === 'tool_output') {
        const fullOutput = typeof parsed.output === 'string'
            ? parsed.output
            : safePayloadStringify(parsed.output, String(parsed.output ?? ''));
        row.innerHTML = `<strong>${escapeHtml(parsed.name || 'tool')}</strong> <span class="meta-pill">${escapeHtml(parsed.type)}</span>${fullOutput ? `<details class="drawer-event-details"><summary>${escapeHtml(summarizeValue(fullOutput, 160))}</summary><pre style="margin-top:0.25rem;font-size:0.7rem;white-space:pre-wrap;overflow-wrap:anywhere;">${escapeHtml(fullOutput)}</pre></details>` : ''}`;
    } else if (parsed.type === 'tool_progress') {
        row.innerHTML = `<span class="meta-pill">progress</span> ${escapeHtml(parsed.progress || parsed.label || meta.message || '')}`;
    } else if (parsed.type === 'steer') {
        row.innerHTML = `<span class="meta-pill">${escapeHtml(parsed.mode === 'hard' ? 'hard steer queued' : 'soft steer queued')}</span> ${escapeHtml(parsed.message || '')}`;
    } else {
        row.innerHTML = `<span class="meta-pill">${escapeHtml(parsed.type || 'event')}</span> ${escapeHtml(JSON.stringify(parsed))}`;
    }
    transcriptEl.appendChild(row);
    transcriptEl.scrollTop = transcriptEl.scrollHeight;
}

function normalizeDrawerTraceEvent(parsed) {
    if (!parsed || typeof parsed !== 'object') return null;
    if (parsed.type === 'content') {
        return {
            ...parsed,
            text: Object.prototype.hasOwnProperty.call(parsed, 'text') ? parsed.text : (parsed.content || ''),
        };
    }
    if (parsed.type === 'tool_call' && parsed.function && typeof parsed.function === 'object') {
        const normalized = normalizeToolCallEntries([parsed])[0] || {};
        return { ...parsed, ...normalized, type: 'tool_call' };
    }
    return parsed;
}

function buildDrawerLiveTraceState(childSessionId, events = []) {
    const state = createAssistantTraceState({ sessionId: childSessionId });
    (Array.isArray(events) ? events : []).forEach((rawEvent) => {
        const event = normalizeDrawerTraceEvent(rawEvent);
        if (!event || !['content', 'tool_call', 'tool_output', 'tool_progress', 'meta'].includes(event.type)) return;
        reduceAssistantTraceEvent(state, event);
    });
    state.renderTraceContext = {
        domScope: `subagent-live-${String(childSessionId || '').replace(/[^A-Za-z0-9_-]/g, '_')}`,
    };
    return syncAssistantTraceDerivedFields(state);
}

function renderDrawerLiveTrace(childSessionId, transcriptEl, events = []) {
    if (!transcriptEl) return false;
    const traceEvents = events.filter(event => ['content', 'tool_call', 'tool_output', 'tool_progress', 'meta'].includes(event?.type));
    const auxiliaryEvents = events.filter(event => !traceEvents.includes(event));
    const state = buildDrawerLiveTraceState(childSessionId, traceEvents);
    const renderScope = `subagent-live-${String(childSessionId || '').replace(/[^A-Za-z0-9_-]/g, '_')}`;
    const body = renderAssistantEvents(state, renderScope);
    transcriptEl.innerHTML = body
        ? `<div class="message assistant drawer-live-trace">${renderAssistantMessageShell({ renderScope }, state, body)}</div>`
        : '';
    auxiliaryEvents.forEach(event => renderDrawerEventRow(transcriptEl, event));
    syncToolCallUi(transcriptEl);
    return Boolean(body || auxiliaryEvents.length);
}

function ensureDrawerLiveTail(transcriptEl) {
    if (!transcriptEl) return null;
    let tail = transcriptEl.querySelector('[data-drawer-live-tail]');
    if (tail) return tail;
    tail = document.createElement('div');
    tail.dataset.drawerLiveTail = 'true';
    tail.className = 'drawer-live-tail';
    transcriptEl.appendChild(tail);
    return tail;
}

function getDrawerCallKey(value) {
    if (!value || typeof value !== 'object') return '';
    const metadata = getEventMetadata(value);
    const callId = value.call_id ?? value.tool_call_id ?? value.toolCallId ?? value.id
        ?? metadata.call_id ?? metadata.tool_call_id ?? metadata.toolCallId ?? metadata.id;
    return callId == null || callId === '' ? '' : String(callId);
}

function collectPersistedDrawerEventKeys(data) {
    const keys = new Set();
    (data?.messages || []).forEach((message) => {
        const direct = message?.tool_call_id;
        if (direct != null && direct !== '') keys.add(String(direct));
        const calls = Array.isArray(message?.tool_calls) ? message.tool_calls : [];
        calls.forEach((call) => {
            const key = getDrawerCallKey(call);
            if (key) keys.add(key);
        });
    });
    return keys;
}

function renderDrawerSessionSnapshot(childSessionId, transcriptEl, data) {
    if (!transcriptEl || !data || !Array.isArray(data.messages)) return false;
    const fingerprint = drawerSessionSnapshotFingerprint(data);
    if (childDrawerSnapshotFingerprints.get(childSessionId) === fingerprint && transcriptEl.dataset.drawerHydrated === 'true') {
        return false;
    }
    const hadSnapshot = transcriptEl.dataset.drawerHydrated === 'true';
    const stickToBottom = !hadSnapshot || shouldStickToBottom(transcriptEl);
    const previousScrollTop = transcriptEl.scrollTop;
    const openToolState = captureOpenToolState(transcriptEl);
    const traceContext = buildSessionTraceContext(data, {
        domScope: `subagent-${String(childSessionId || '').replace(/[^A-Za-z0-9_-]/g, '_')}`,
    });
    traceContext.sessionId = childSessionId;
    const persistedKeys = collectPersistedDrawerEventKeys(data);
    childDrawerPersistedEventKeys.set(childSessionId, persistedKeys);
    transcriptEl.innerHTML = `<div class="drawer-session-history" data-drawer-session-history>${renderSessionTranscript(traceContext)}</div><div class="drawer-live-tail" data-drawer-live-tail></div>`;
    transcriptEl.dataset.drawerHydrated = 'true';
    delete transcriptEl.dataset.drawerLoadError;
    childDrawerSnapshotFingerprints.set(childSessionId, fingerprint);
    renderCachedDrawerEvents(childSessionId, ensureDrawerLiveTail(transcriptEl));
    restoreOpenToolState(transcriptEl, openToolState);
    transcriptEl.scrollTop = stickToBottom ? transcriptEl.scrollHeight : previousScrollTop;
    return true;
}

function childSessionSnapshotPath(childSessionId) {
    const entry = childDrawerRegistry.get(childSessionId) || {};
    if (entry.profileBot && entry.profile) {
        return `/api/bots/${encodeURIComponent(entry.profile)}/sessions/${encodeURIComponent(childSessionId)}`;
    }
    return `/api/sessions/${encodeURIComponent(childSessionId)}`;
}

async function rehydrateChildSessionDrawer(childSessionId, transcriptEl) {
    if (!childSessionId || !transcriptEl) return false;
    try {
        const response = await fetch(childSessionSnapshotPath(childSessionId));
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
        renderDrawerSessionSnapshot(childSessionId, transcriptEl, data);
        return data;
    } catch (error) {
        const errorText = error.message || String(error);
        if (transcriptEl.dataset.drawerLoadError === errorText) return false;
        transcriptEl.dataset.drawerLoadError = errorText;
        transcriptEl.innerHTML = `<div class="drawer-load-error">Could not restore session history: ${escapeHtml(errorText)}</div><div class="drawer-live-tail" data-drawer-live-tail></div>`;
        renderCachedDrawerEvents(childSessionId, ensureDrawerLiveTail(transcriptEl));
        return false;
    }
}

function appendDrawerEventRow(childSessionId, transcriptEl, parsed) {
    if (!childSessionId || !parsed || !shouldAcceptDrawerEvent(childSessionId, parsed)) return false;
    recordDrawerEvent(childSessionId, parsed);
    const target = transcriptEl?.matches?.('[data-drawer-live-tail]')
        ? transcriptEl
        : ensureDrawerLiveTail(transcriptEl);
    renderCachedDrawerEvents(childSessionId, target);
    return true;
}

function renderCachedDrawerEvents(childSessionId, transcriptEl) {
    const events = childDrawerEventCache.get(childSessionId) || [];
    if (!events.length || !transcriptEl) return false;
    const persistedKeys = childDrawerPersistedEventKeys.get(childSessionId) || new Set();
    const unpersisted = events.filter((event) => {
        const callKey = getDrawerCallKey(event);
        return !callKey || !persistedKeys.has(callKey);
    });
    return renderDrawerLiveTrace(childSessionId, transcriptEl, unpersisted);
}

function appendLiveDrawerEventIfOpen(parsed) {
    const metadata = getEventMetadata(parsed);
    const childSessionId = metadata.child_session_id || metadata.session_id || metadata.subagent_id || '';
    const transcript = getDrawerTranscript(childSessionId);
    if (!transcript) return false;
    appendDrawerEventRow(childSessionId, ensureDrawerLiveTail(transcript), parsed);
    return true;
}

async function togglePauseSubagentStream(childSessionId, mode = 'soft') {
    if (!childSessionId) return;
    mode = mode === 'hard' ? 'hard' : 'soft';
    const paused = childDrawerPausedSet.has(childSessionId);
    const action = paused ? 'resume' : 'pause';
    try {
        const res = await fetch(`/api/sessions/${encodeURIComponent(childSessionId)}/interrupt`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action, mode }) });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.status || `HTTP ${res.status}`);
        if (paused) childDrawerPausedSet.delete(childSessionId); else childDrawerPausedSet.add(childSessionId);
        document.querySelectorAll(`.subagent-pause-btn[data-child-session-id="${CSS.escape(childSessionId)}"]`).forEach(button => { button.textContent = paused ? (button.dataset.controlMode === 'hard' ? 'Hard pause' : 'Soft pause') : 'Resume'; });
        showToast(`${paused ? 'Resume' : mode + ' pause'} requested`);
    } catch (err) { showToast(`Could not ${action} subagent: ${err.message}`, true); }
}

async function requestSteerSubagent(childSessionId, mode = 'soft') {
    if (!childSessionId) return;
    mode = mode === 'hard' ? 'hard' : 'soft';
    const message = prompt(mode === 'hard' ? 'Hard steer: abort current work and deliver this guidance immediately:' : 'Soft steer: queue guidance for the next safe opportunity:');
    if (!message || !message.trim()) return;
    try {
        const res = await fetch(`/api/sessions/${encodeURIComponent(childSessionId)}/steer`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message: message.trim(), mode }) });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.status || `HTTP ${res.status}`);
        appendDrawerEventRow(childSessionId, getDrawerTranscript(childSessionId), { type: 'steer', mode, message: message.trim() });
        showToast(data.status === 'queued' ? `${mode} steer queued` : (data.status || 'Steer request sent'));
    } catch (err) { showToast(`Could not queue steer guidance: ${err.message}`, true); }
}

async function requestStopSubagent(childSessionId) {
    if (!childSessionId) return;
    if (!confirm(`Stop live subagent ${childSessionId.slice(0, 8)}?`)) return;
    try {
        const res = await fetch(`/api/sessions/${encodeURIComponent(childSessionId)}/interrupt`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action: 'stop', mode: 'hard' }) });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.status || `HTTP ${res.status}`);
        const currentStatus = childDrawerStatusMap.get(childSessionId);
        if (!currentStatus || ACTIVE_CHILD_DRAWER_STATUSES.has(currentStatus)) {
            watchSubagentFlightStatus(childSessionId);
            updateDrawerBadge(childSessionId, 'STOPPING');
        }
        showToast(data.status || 'Stop requested');
    } catch (err) { showToast(`Could not stop subagent: ${err.message}`, true); }
}

async function openChildSessionDrawer(childSessionId, anchorEl, label) {
    if (!childSessionId) return;
    const existing = document.querySelector(`.subagent-window[data-child-session-id="${CSS.escape(childSessionId)}"]`);
    if (existing) {
        setSubagentWindowMinimized(childSessionId, false);
        bringSubagentWindowToFront(existing);
        return;
    }
    openDrawerSet.add(childSessionId);
    rememberChildDrawer(childSessionId, { label: label || '', delegateCallId: anchorEl?.dataset?.delegateCallId || '' });
    const layer = ensureSubagentWindowLayer();
    layer.insertAdjacentHTML('beforeend', renderChildSessionDrawerShell(childSessionId, label || ''));
    const windowEl = layer.querySelector(`.subagent-window[data-child-session-id="${CSS.escape(childSessionId)}"]`);
    initializeSubagentWindow(windowEl, childSessionId);
    const transcript = getDrawerTranscript(childSessionId);
    if (transcript) transcript.innerHTML = '<div style="color:var(--text-dim);font-size:0.8rem;">Loading complete session history...</div><div class="drawer-live-tail" data-drawer-live-tail></div>';
    // Subscribe before reading state.db so events cannot fall into the gap
    // between the persisted snapshot and the live stream.
    openDrawerEventSource(childSessionId, ensureDrawerLiveTail(transcript));
    await rehydrateChildSessionDrawer(childSessionId, transcript);
    if (!document.contains(transcript)) return;
}

function closeChildSessionDrawer(childSessionId) {
    const source = drawerEventSources.get(childSessionId);
    if (source) { source.close(); drawerEventSources.delete(childSessionId); }
    document.querySelectorAll(`.subagent-window[data-child-session-id="${CSS.escape(childSessionId)}"]`).forEach(windowEl => windowEl.remove());
    openDrawerSet.delete(childSessionId);
    childWindowState.delete(childSessionId);
    childDrawerSnapshotFingerprints.delete(childSessionId);
    refreshMobileWindowSlots();
}

function watchSubagentFlightStatus(childSessionId) {
    if (!childSessionId || childFlightEventSources.has(childSessionId)) return;
    if (childDrawerRegistry.get(childSessionId)?.profileBot) return;
    const currentStatus = childDrawerStatusMap.get(childSessionId);
    if (currentStatus && !ACTIVE_CHILD_DRAWER_STATUSES.has(currentStatus)) return;
    const source = new EventSource(`/api/sessions/${encodeURIComponent(childSessionId)}/stream`);
    childFlightEventSources.set(childSessionId, source);
    source.onmessage = event => {
        if (event.data === '[DONE]') {
            updateDrawerBadge(childSessionId, 'DONE');
            return;
        }
        try {
            const parsed = JSON.parse(event.data || '{}');
            if (parsed.type !== 'run_state') return;
            if (parsed.status === 'complete') updateDrawerBadge(childSessionId, 'DONE');
            else if (parsed.status === 'error') updateDrawerBadge(childSessionId, 'ERROR');
            else if (parsed.status === 'paused') updateDrawerBadge(childSessionId, 'PAUSED');
            else if (parsed.status === 'running' || parsed.status === 'resumed') updateDrawerBadge(childSessionId, 'LIVE');
        } catch (error) { /* status watcher ignores non-JSON keepalive data */ }
    };
    source.onopen = () => {
        restoredChildFlightSessions.delete(childSessionId);
        const status = childDrawerStatusMap.get(childSessionId);
        if (status !== 'PAUSED' && status !== 'STOPPING') updateDrawerBadge(childSessionId, 'LIVE');
    };
    source.onerror = () => {
        const status = childDrawerStatusMap.get(childSessionId);
        if (!ACTIVE_CHILD_DRAWER_STATUSES.has(status || '')) return;
        if (restoredChildFlightSessions.has(childSessionId) && source.readyState === EventSource.CLOSED) {
            restoredChildFlightSessions.delete(childSessionId);
            updateDrawerBadge(childSessionId, 'DONE');
            return;
        }
        updateDrawerBadge(childSessionId, source.readyState === EventSource.CLOSED ? 'OFFLINE' : 'RECONNECTING');
    };
}

function updateDrawerBadge(childSessionId, status) {
    const previousStatus = childSessionId ? childDrawerStatusMap.get(childSessionId) : null;
    if (previousStatus === 'STOPPING' && ACTIVE_CHILD_DRAWER_STATUSES.has(status) && status !== 'STOPPING') status = 'STOPPING';
    if (childSessionId && status) childDrawerStatusMap.set(childSessionId, status);
    document.querySelectorAll(`.live-badge[data-badge="${CSS.escape(childSessionId)}"]`).forEach(badge => {
        const isLive = status === 'LIVE';
        const isDisconnected = status === 'RECONNECTING' || status === 'OFFLINE';
        badge.classList.toggle('active', isLive);
        const color = status === 'ERROR' ? 'var(--error)' : (isDisconnected ? 'var(--warning, #d6a84b)' : 'var(--success)');
        badge.innerHTML = `<span class="live-dot" style="${isLive ? '' : `animation:none;background:${color};`}"></span>${escapeHtml(status)}`;
    });
    if (childSessionId && status && previousStatus !== status) {
        const entry = childDrawerRegistry.get(childSessionId) || {};
        const label = entry.label || `Subagent ${childSessionId.slice(0, 8)}`;
        if (status === 'ERROR') {
            sendDashboardNotification('errors', 'Hermes subagent failed', label, {
                key: `subagent:${childSessionId}:error`,
                tag: `hermes-subagent-${childSessionId}`,
                panel: 'chat',
            });
        } else if (status === 'DONE') {
            sendDashboardNotification('subagents', 'Hermes subagent finished', label, {
                key: `subagent:${childSessionId}:done`,
                tag: `hermes-subagent-${childSessionId}`,
                panel: 'chat',
            });
        }
        if (status === 'DONE' || status === 'ERROR') scheduleParentCompletionReconcile(childSessionId);
        let runChanged = false;
        Object.values(activeRuns).forEach(runState => {
            const child = (Array.isArray(runState?.childSessions) ? runState.childSessions : []).find(entry => entry.childSessionId === childSessionId);
            if (child && child.status !== status) {
                child.status = status;
                runChanged = true;
            }
        });
        if (runChanged) saveActiveRuns();
        if (!ACTIVE_CHILD_DRAWER_STATUSES.has(status)) {
            const source = childFlightEventSources.get(childSessionId);
            source?.close();
            childFlightEventSources.delete(childSessionId);
            restoredChildFlightSessions.delete(childSessionId);
        }
        syncSubagentFlightUi();
    }
}

function openDrawerEventSource(childSessionId, transcriptEl) {
    if (!childSessionId || drawerEventSources.has(childSessionId)) return;
    if (childDrawerRegistry.get(childSessionId)?.profileBot) {
        let closed = false;
        let timer = null;
        const controller = {
            close() {
                if (closed) return;
                closed = true;
                if (timer) clearInterval(timer);
                drawerEventSources.delete(childSessionId);
            },
        };
        const poll = async () => {
            if (closed) return;
            const data = await rehydrateChildSessionDrawer(childSessionId, getDrawerTranscript(childSessionId));
            if (!data || data.ended_at == null) return;
            updateDrawerBadge(childSessionId, data.end_reason === 'error' ? 'ERROR' : 'DONE');
            controller.close();
        };
        drawerEventSources.set(childSessionId, controller);
        timer = setInterval(() => void poll(), 2000);
        void poll();
        return;
    }
    const es = new EventSource(`/api/sessions/${encodeURIComponent(childSessionId)}/stream`);
    drawerEventSources.set(childSessionId, es);
    if (transcriptEl && !renderCachedDrawerEvents(childSessionId, transcriptEl) && !transcriptEl.children.length) transcriptEl.innerHTML = '<div style="color:var(--text-dim);font-size:0.8rem;">No new live activity.</div>';
    es.onmessage = async (event) => {
        if (!event.data) return;
        updateDrawerBadge(childSessionId, 'LIVE');
        if (event.data === '[DONE]') {
            await rehydrateChildSessionDrawer(childSessionId, getDrawerTranscript(childSessionId));
            updateDrawerBadge(childSessionId, 'DONE');
            es.close();
            drawerEventSources.delete(childSessionId);
            return;
        }
        try {
            const parsed = JSON.parse(event.data);
            // Surface the SSE occurrence identity to cache/dedup consumers.
            // EventSource maintains this ID across its native reconnects.
            if (event.lastEventId && parsed.event_id == null) parsed.event_id = event.lastEventId;
            if (parsed.type === 'run_state' && (parsed.status === 'complete' || parsed.status === 'error')) {
                await rehydrateChildSessionDrawer(childSessionId, getDrawerTranscript(childSessionId));
                updateDrawerBadge(childSessionId, parsed.status === 'error' ? 'ERROR' : 'DONE');
                es.close();
                drawerEventSources.delete(childSessionId);
                return;
            }
            appendDrawerEventRow(childSessionId, ensureDrawerLiveTail(getDrawerTranscript(childSessionId)), parsed);
        } catch (e) { /* ignore parse errors */ }
    };
    es.onopen = () => updateDrawerBadge(childSessionId, 'LIVE');
    // Do not close here: EventSource owns retry timing and will reconnect natively.
    es.onerror = () => updateDrawerBadge(childSessionId, es.readyState === EventSource.CLOSED ? 'OFFLINE' : 'RECONNECTING');
}

function renderDelegateLiveActionStrip(childEntries, tool, rawToolKey) {
    if (!Array.isArray(childEntries) || !childEntries.length) return '';
    const delegateCallId = tool?.call_id || rawToolKey || '';
    const liveButtons = childEntries.map((entry, childIdx) => {
        const taskIndex = normalizeTaskIndex(entry?.taskIndex);
        const label = Number.isInteger(taskIndex) ? `Task ${taskIndex + 1}` : `Subagent ${childIdx + 1}`;
        return `<button type="button" class="tool-call-action-badge live-view-btn" data-child-session-id="${escapeHtml(entry.childSessionId)}" data-delegate-call-id="${escapeHtml(delegateCallId)}" data-tool-key="${escapeHtml(rawToolKey)}" data-label="${escapeHtml(entry.label || label)}">${escapeHtml(label)}</button>`;
    }).join('');
    const countLabel = `${childEntries.length} live subagent${childEntries.length === 1 ? '' : 's'}`;
    return `<span class="delegate-live-actions" aria-label="${escapeHtml(countLabel)}"><span class="delegate-live-count">${escapeHtml(countLabel)}</span>${liveButtons}</span>`;
}

function findLatestDelegateToolCallId(state) {
    const tools = state?.tools || [];
    for (let i = tools.length - 1; i >= 0; i -= 1) {
        if (tools[i]?.name === 'delegate_task' && tools[i]?.call_id) return tools[i].call_id;
    }
    return '';
}

function ensureAssistantTracePendingDelegateChildren(state) {
    if (!state?.trace || typeof state.trace !== 'object') {
        state.trace = { toolNodes: [], orphanNodes: [], pendingDelegateChildren: {}, toolSequence: 0, orphanSequence: 0 };
    }
    if (!state.trace.pendingDelegateChildren || typeof state.trace.pendingDelegateChildren !== 'object') {
        state.trace.pendingDelegateChildren = {};
    }
    return state.trace.pendingDelegateChildren;
}

const toolCallUiState = new Map();
const executionHistoryUiState = new Map();
const toolCallData = new Map();
const toolIntentRequests = new Map();
const toolIntentRunOwners = new Map();
const chatRoomIntentEpochs = new Map();
const assistantRenderScopes = new WeakMap();
let assistantRenderScopeSequence = 0;

function getAssistantRenderScope(message, normalized = null) {
    const explicitScope = message?.renderScope || normalized?.renderTraceContext?.domScope;
    const nodeScope = message?.traceNode?.node_id || normalized?.trace?.stepNode?.node_id;
    if (explicitScope || nodeScope) return `assistant:${explicitScope || 'default'}:${nodeScope || 'message'}`;
    if (message && typeof message === 'object') {
        if (!assistantRenderScopes.has(message)) {
            assistantRenderScopeSequence += 1;
            assistantRenderScopes.set(message, `assistant:runtime:${assistantRenderScopeSequence}`);
        }
        return assistantRenderScopes.get(message);
    }
    assistantRenderScopeSequence += 1;
    return `assistant:runtime:${assistantRenderScopeSequence}`;
}

function captureOpenToolState(container) {
    if (!container) return new Map();
    const state = new Map();
    container.querySelectorAll('[data-tool-id]').forEach((node) => {
        const id = node.getAttribute('data-tool-id');
        if (!id) return;
        const existing = toolCallUiState.get(id);
        if (!existing) return;
        state.set(id, {
            expanded: existing.expanded === true,
            activePanel: existing.activePanel || null,
            renderedPanels: new Set(existing.renderedPanels || []),
        });
    });
    return state;
}

function restoreOpenToolState(container, openKey) {
    if (!(openKey instanceof Map)) return;
    openKey.forEach((value, key) => {
        toolCallUiState.set(key, {
            expanded: value?.expanded === true,
            activePanel: value?.activePanel || null,
            renderedPanels: new Set(value?.renderedPanels || []),
        });
    });
    syncToolCallUi(container);
}

function formatTimestamp(ts) {
    if (!ts) return '';
    const date = new Date(Number(ts) * 1000 || ts);
    if (Number.isNaN(date.getTime())) return String(ts);
    return date.toLocaleString();
}

function renderActivityData(value) {
    if (value === null || value === undefined || value === '') return '';
    const text = typeof value === 'string' ? value : JSON.stringify(value, null, 2);
    return `<pre>${escapeHtml(text)}</pre>`;
}

function renderBackgroundReviews(items) {
    const target = document.getElementById('session-background-reviews');
    if (!Array.isArray(items) || !items.length) {
        target.innerHTML = '<div style="color:var(--text-dim);">No background review activity yet.</div>';
        return;
    }
    target.innerHTML = items.map(item => `
        <div class="activity-item">
            <div class="activity-title">${normalizeActivityTarget(item) ? renderExecutionTargetLink(currentSessionTraceContext?.sessionId, normalizeActivityTarget(item), `Review ${(item.session_id || '').slice(0, 8)}`) : `Review ${escapeHtml((item.session_id || '').slice(0, 8))}`}</div>
            <div class="activity-meta">${escapeHtml(formatTimestamp(item.timestamp) || 'Unknown time')}</div>
            ${item.summary ? `<div>${escapeHtml(item.summary)}</div>` : ''}
            ${Array.isArray(item.events) && item.events.length ? `<div class="activity-block">${item.events.map(event => `
                <div style="margin-bottom:0.4rem;"><strong>${escapeHtml(event.name || 'tool')}</strong>${event.call_id ? ` ${renderExecutionTargetLink(currentSessionTraceContext?.sessionId, { kind: 'tool', id: event.call_id }, 'open call')}` : ''}${renderActivityData(event.output)}</div>
            `).join('')}</div>` : ''}
        </div>
    `).join('');
}

function renderRequestResultActivity(targetId, items, emptyMessage, titleBuilder) {
    const target = document.getElementById(targetId);
    if (!Array.isArray(items) || !items.length) {
        target.innerHTML = `<div style="color:var(--text-dim);">${escapeHtml(emptyMessage)}</div>`;
        return;
    }
    target.innerHTML = items.map(item => `
        <div class="activity-item">
            <div class="activity-title">${normalizeActivityTarget(item) ? renderExecutionTargetLink(currentSessionTraceContext?.sessionId, normalizeActivityTarget(item), titleBuilder(item)) : escapeHtml(titleBuilder(item))}</div>
            <div class="activity-meta">${escapeHtml(formatTimestamp(item.timestamp) || 'Unknown time')}</div>
            ${normalizeActivityTarget(item) ? `<div class="transcript-anchor-list"><span class="meta-pill">linked to transcript</span></div>` : ''}
            <div class="activity-block"><strong>Request</strong>${renderActivityData(item.request)}</div>
            <div class="activity-block"><strong>Result</strong>${renderActivityData(item.result)}</div>
        </div>
    `).join('');
}

function renderSessionSearchEvents(items) {
    const target = document.getElementById('session-search-events');
    if (!target) return;
    if (!Array.isArray(items) || !items.length) {
        target.innerHTML = '<div style="color:var(--text-dim);">No session recall activity yet.</div>';
        return;
    }
    target.innerHTML = items.map((item) => {
        const req = item?.request || {};
        const result = item?.result || {};
        const sessionId = result.session_id || result.id || item.session_id || req.session_id || '';
        const shortSessionId = sessionId ? String(sessionId).slice(0, 8) : 'unknown';
        const score = result.score ?? result.relevance ?? result.similarity ?? item.score;
        const dateLabel = formatTimestamp(result.timestamp || item.timestamp) || 'Unknown time';
        const snippetSource = result.snippet || result.preview || result.content || result.text || req.query || '';
        const snippet = summarizeValue(typeof snippetSource === 'string' ? snippetSource : JSON.stringify(snippetSource), 120).replace(/\s+/g, ' ').trim();
        const fullBody = typeof result.content === 'string'
            ? result.content
            : JSON.stringify(result, null, 2);
        return `
            <details class="session-search-result">
                <summary>
                    <span class="tool-call-chip">session ${escapeHtml(shortSessionId)}</span>
                    ${score !== null && score !== undefined && score !== '' ? `<span class="tool-call-chip">score ${escapeHtml(String(score))}</span>` : ''}
                    <span class="meta-pill">${escapeHtml(dateLabel)}</span>
                    <span style="min-width:0;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--text-dim);">${escapeHtml(snippet || '(no preview)')}</span>
                </summary>
                <div class="session-search-result-body">${escapeHtml(fullBody)}</div>
            </details>
        `;
    }).join('');
}

function renderMetaPill(label, value) {
    if (value === null || value === undefined || value === '') return '';
    return `<span class="meta-pill">${escapeHtml(label)}: ${escapeHtml(String(value))}</span>`;
}

function renderPromptBreakdownRows(items) {
    if (!Array.isArray(items) || !items.length) return '';
    const ranked = [...items]
        .filter(item => item && item.estimated_tokens)
        .sort((a, b) => (b.estimated_tokens || 0) - (a.estimated_tokens || 0));
    if (!ranked.length) return '';
    return `<div class="context-breakdown-list">${ranked.map(item => {
        const sourceText = item.source ? String(item.source) : '';
        const countText = item.count ? `${String(item.count)} tools` : '';
        const raw = item.content || JSON.stringify(item, null, 2);
        return `
            <details class="context-breakdown-item">
                <summary>
                    <div class="summary-left">
                        <span class="item-arrow">▶</span>
                        <span>${escapeHtml(item.name)}</span>
                        ${sourceText ? `<span class="meta-pill">${escapeHtml(sourceText)}</span>` : ''}
                    </div>
                    <div class="summary-right">
                        ${countText ? `<span>${escapeHtml(countText)}</span>` : ''}
                        <span>${escapeHtml(String(item.estimated_tokens))} tok</span>
                    </div>
                </summary>
                <div class="context-breakdown-item-body">
                    <pre><code>${escapeHtml(raw)}</code></pre>
                </div>
            </details>
        `;
    }).join('')}</div>`;
}

function getToolHeaderDetail(toolName, parsedArgs, rawArgs) {
    if (!parsedArgs || typeof parsedArgs !== 'object') return '';
    switch(toolName) {
        case 'read_file':
        case 'write_file':
            return parsedArgs.path || parsedArgs.file_path || '';
        case 'patch':
            return parsedArgs.path || parsedArgs.file_path || '';
        case 'terminal':
            const cmd = parsedArgs.command || parsedArgs.cmd || '';
            return cmd.length > 60 ? cmd.slice(0, 57) + '...' : cmd;
        case 'session_search':
            return parsedArgs.query || parsedArgs.search || '';
        case 'delegate_task':
            const goal = parsedArgs.goal || parsedArgs.task || '';
            return goal.length > 80 ? goal.slice(0, 77) + '...' : goal;
        case 'web_search':
            return parsedArgs.query || '';
        case 'web_fetch':
            return parsedArgs.url || '';
        case 'skill_view':
            return parsedArgs.skill_id || parsedArgs.name || '';
        default:
            // Show first string argument value
            const firstVal = Object.values(parsedArgs).find(v => typeof v === 'string' && v.length > 0 && v.length < 80);
            return firstVal || '';
    }
}

function getDelegationProgressSummary(progress) {
    if (!progress.length) return '';
    // Count distinct task indices
    const taskIndices = new Set(progress.filter(p => p && typeof p === 'object' && Number.isInteger(p.task_index)).map(p => p.task_index));
    const taskCount = progress.find(p => p && typeof p === 'object' && Number.isInteger(p.task_count))?.task_count;
    if (taskIndices.size > 0 && taskCount) {
        return `${taskIndices.size}/${taskCount} tasks`;
    }
    return `${progress.length} updates`;
}

function highlightToolCode(containerEl) {
    if (!window.hljs || !containerEl || typeof containerEl.querySelectorAll !== 'function') return;
    containerEl.querySelectorAll('.tool-output-json, .tool-output-text, .tool-raw-json').forEach((el) => {
        if (el.dataset.hljsDone === 'true') return;
        try {
            window.hljs.highlightElement(el);
            el.dataset.hljsDone = 'true';
        } catch (e) { /* leave unhighlighted */ }
    });
}

function formatToolOutputText(rawOutput) {
    if (!rawOutput) return '<pre>No output</pre>';

    // Try to parse and pretty-print JSON
    try {
        const parsed = JSON.parse(rawOutput);
        const pretty = JSON.stringify(parsed, null, 2);
        if (pretty.length > 3000) {
            const truncated = pretty.slice(0, 3000);
            const id = 'tout_' + Math.random().toString(36).slice(2, 8);
            return `<pre class="tool-output-json">${highlightJSON(truncated)}</pre>
                <button class="tool-output-expand" onclick="document.getElementById('${id}').style.display='block';this.style.display='none';">Show full output (${(pretty.length/1024).toFixed(1)}KB)</button>
                <pre id="${id}" class="tool-output-json" style="display:none;">${highlightJSON(pretty)}</pre>`;
        }
        return `<pre class="tool-output-json">${highlightJSON(pretty)}</pre>`;
    } catch(e) {
        // Not JSON — render as wrapped text with truncation
        if (rawOutput.length > 3000) {
            const truncated = rawOutput.slice(0, 3000);
            const id = 'tout_' + Math.random().toString(36).slice(2, 8);
            return `<pre class="tool-output-text">${escapeHtml(truncated)}</pre>
                <button class="tool-output-expand" onclick="document.getElementById('${id}').style.display='block';this.style.display='none';">Show full output (${(rawOutput.length/1024).toFixed(1)}KB)</button>
                <pre id="${id}" class="tool-output-text" style="display:none;">${escapeHtml(rawOutput)}</pre>`;
        }
        return `<pre class="tool-output-text">${escapeHtml(rawOutput)}</pre>`;
    }
}

function getToolCallId(tool, idx = 0, options = {}) {
    const scope = String(
        options?.renderScope
        || options?.node?.parent_node_id
        || options?.node?.node_id
        || options?.traceContext?.domScope
        || options?.traceContext?.sessionId
        || 'unscoped',
    );
    return `${scope}:tool:${tool?.call_id ?? `${tool?.name || 'tool'}_${idx}`}`;
}

function getToolActionLabel(toolName, parsedArgs, parsedOutput) {
    const candidates = [
        parsedArgs?.action,
        parsedArgs?.method,
        parsedArgs?.operation,
        parsedArgs?.mode,
        parsedArgs?.verb,
        parsedOutput?.action,
    ].filter((value) => typeof value === 'string' && value.trim());
    if (candidates.length) return candidates[0].trim();
    if (toolName === 'todo') return Array.isArray(parsedArgs?.todos) ? 'update' : 'read';
    const defaults = {
        skill_manage: 'patch',
        memory_write: 'replace',
        patch: 'patch',
        write_file: 'write',
        read_file: 'read',
        session_search: 'search',
        web_search: 'search',
        web_fetch: 'fetch',
        fetch_url: 'fetch',
        delegate_task: 'delegate',
        terminal: 'run',
        execute_code: 'run',
    };
    return defaults[toolName] || 'run';
}

function setToolIntentDescription(state, callId, description) {
    const normalized = String(description || '').replace(/\s+/g, ' ').trim();
    if (!normalized) return false;
    const node = findAssistantToolNode(state, callId);
    if (!node?.payload?.tool) return false;
    node.payload.tool.intent_description = normalized;
    syncAssistantTraceDerivedFields(state);
    return true;
}

function setToolIntentDescriptionPending(state, callId, pending) {
    const node = findAssistantToolNode(state, callId);
    if (!node?.payload?.tool) return false;
    node.payload.tool.intent_description_pending = pending === true;
    syncAssistantTraceDerivedFields(state);
    return true;
}

function requestToolIntentDescription(tool, options = {}) {
    if (!['terminal', 'execute_code'].includes(tool?.name) || !tool?.call_id || tool.intent_description) return null;
    const requestKey = `${options.runId || 'run'}:${tool.call_id}`;
    const existing = toolIntentRequests.get(requestKey);
    if (existing) {
        tool.intent_description_pending = true;
        existing.tools.add(tool);
        existing.listeners.push(options);
        return existing.promise;
    }
    const parsedArgs = parseToolPayload(tool.arguments);
    const fetchImpl = options.fetchImpl || fetch;
    tool.intent_description_pending = true;
    const entry = {
        promise: null,
        tools: new Set([tool]),
        listeners: [options],
    };
    const notify = (callback, ...args) => {
        entry.listeners.forEach((listener) => {
            if (typeof listener.isCurrent === 'function' && !listener.isCurrent()) return;
            try {
                if (typeof listener[callback] === 'function') listener[callback](...args);
            } catch (error) {
                log('warn', `Tool intent ${callback} callback failed: ${error.message || error}`);
            }
        });
    };
    let responsePromise;
    try {
        responsePromise = fetchImpl('/api/tool-intent', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                tool: tool.name,
                arguments: parsedArgs.parsed ?? parsedArgs.raw,
            }),
        });
    } catch (error) {
        responsePromise = Promise.reject(error);
    }
    const request = Promise.resolve(responsePromise)
        .then(response => response.ok && response.status !== 204 ? response.text() : '')
        .then(description => {
            const normalized = String(description || '').replace(/\s+/g, ' ').trim();
            if (normalized) notify('onReady', normalized);
            return normalized;
        })
        .catch(() => '')
        .finally(() => {
            entry.tools.forEach(item => { item.intent_description_pending = false; });
            if (toolIntentRequests.get(requestKey) === entry) toolIntentRequests.delete(requestKey);
            notify('onSettled');
        });
    entry.promise = request;
    toolIntentRequests.set(requestKey, entry);
    return request;
}

function hasCapturedToolOutput(tool) {
    return Boolean(tool)
        && Object.prototype.hasOwnProperty.call(tool, 'output')
        && tool.output !== null
        && tool.output !== undefined;
}

function getToolStatusClass(tool) {
    const parsedOutput = parseToolPayload(tool?.output);
    const parsed = parsedOutput.parsed;
    if (parsed && typeof parsed === 'object' && (parsed.error || parsed.success === false || parsed.status === 'error')) return 'error';
    if (tool?.error) return 'error';
    if (hasCapturedToolOutput(tool)) return 'complete';
    const progress = Array.isArray(tool?.progress) ? tool.progress : [];
    return progress.length ? 'running' : 'pending';
}

function getToolStatusText(statusClass) {
    if (statusClass === 'complete') return 'done';
    if (statusClass === 'error') return 'error';
    if (statusClass === 'running') return 'running';
    return 'queued';
}

function getToolDurationLabel(tool) {
    if (!tool?.call_id) return '';
    if (toolCallCompletionTimes.has(tool.call_id)) return toolCallCompletionTimes.get(tool.call_id);
    return getToolElapsed(tool.call_id);
}

function getToolTargetSummary(toolName, parsedArgs, rawArgs) {
    return summarizeToolArgs(toolName, parsedArgs)
        || getToolHeaderDetail(toolName, parsedArgs, rawArgs)
        || '';
}

function getToolTargetDetail(toolName, parsedArgs, rawArgs) {
    if (parsedArgs && typeof parsedArgs === 'object') {
        switch (toolName) {
            case 'read_file':
            case 'write_file':
            case 'patch':
                return parsedArgs.path || parsedArgs.file_path || parsedArgs.target_file || parsedArgs.paths?.[0] || '';
            case 'terminal':
                return parsedArgs.command || parsedArgs.cmd || '';
            case 'execute_code':
                return parsedArgs.code || parsedArgs.filename || parsedArgs.language || '';
            case 'session_search':
            case 'web_search':
                return parsedArgs.query || parsedArgs.prompt || parsedArgs.search || parsedArgs.mode || '';
            case 'web_fetch':
            case 'fetch_url':
                return parsedArgs.url || parsedArgs.urls?.[0] || '';
            case 'skill_view':
            case 'skill_manage':
                return parsedArgs.skill || parsedArgs.skill_id || parsedArgs.name || '';
            case 'delegate_task':
                return parsedArgs.task_description || parsedArgs.prompt || parsedArgs.description || parsedArgs.goal || parsedArgs.task || '';
            default:
                return Object.values(parsedArgs).find((value) => typeof value === 'string' && value.trim()) || '';
        }
    }
    return rawArgs || '';
}

function getToolVisibleDetail(toolName, parsedArgs, rawArgs, targetDetail = '') {
    const args = parsedArgs && typeof parsedArgs === 'object' ? parsedArgs : {};
    if (toolName === 'terminal') {
        return { label: 'command', value: args.command || args.cmd || targetDetail || rawArgs || '' };
    }
    if (toolName === 'execute_code') {
        return { label: 'code', value: args.code || targetDetail || rawArgs || '' };
    }
    if (toolName === 'process') {
        const operation = [args.action || args.operation || '', args.session_id || args.process_id || '']
            .filter(Boolean)
            .join(' ');
        return { label: 'operation', value: args.command || operation || targetDetail || rawArgs || '' };
    }
    return { label: 'target', value: targetDetail || '' };
}

function getToolTimestampLabel(tool, options = {}) {
    return formatTimestamp(options?.node?.timestamp || tool?.timestamp || '') || '';
}

function getToolCollapsedSummary(tool, parsedArgs, parsedOutput) {
    const statusClass = getToolStatusClass(tool);
    const progress = Array.isArray(tool?.progress) ? tool.progress : [];
    const toolName = tool?.name || 'tool';
    const resultSummary = summarizeToolResult(toolName, parsedOutput);
    const latestProgress = progress[progress.length - 1];
    const progressSummary = typeof latestProgress === 'object' ? latestProgress?.label : latestProgress;
    if (statusClass === 'error') return resultSummary || 'tool failed';
    if (statusClass === 'complete') return resultSummary || 'completed';
    if (toolName === 'delegate_task' && progress.length) return getDelegationProgressSummary(progress) || 'delegating';
    return summarizeToolSubject(progressSummary || '', 120) || 'in progress';
}

function renderToolMetricsPanel(tool, parsedArgs, parsedOutput, options = {}) {
    const node = options?.node || null;
    const metrics = [];
    const outputMetrics = parsedOutput && typeof parsedOutput === 'object' ? parsedOutput : {};
    const promptTokens = outputMetrics.prompt_tokens ?? outputMetrics.input_tokens ?? node?.payload?.usage?.prompt_tokens;
    const completionTokens = outputMetrics.completion_tokens ?? outputMetrics.output_tokens ?? node?.payload?.usage?.completion_tokens;
    const totalTokens = outputMetrics.total_tokens ?? ((Number(promptTokens) || Number(completionTokens)) ? (Number(promptTokens || 0) + Number(completionTokens || 0)) : null);
    const modelName = outputMetrics.model || parsedArgs?.model || node?.payload?.model || '';
    const skillName = outputMetrics.skill || parsedArgs?.skill || parsedArgs?.skill_id || parsedArgs?.name || '';
    const skillErrors = Array.isArray(outputMetrics.skill_errors) ? outputMetrics.skill_errors : [];
    const contextUsage = outputMetrics.context_window_usage ?? outputMetrics.context_usage ?? outputMetrics.context_window;
    if (promptTokens !== null && promptTokens !== undefined && promptTokens !== '') metrics.push(['prompt tokens', String(promptTokens)]);
    if (completionTokens !== null && completionTokens !== undefined && completionTokens !== '') metrics.push(['completion tokens', String(completionTokens)]);
    if (totalTokens !== null && totalTokens !== undefined && totalTokens !== '') metrics.push(['total tokens', String(totalTokens)]);
    if (modelName) metrics.push(['model', String(modelName)]);
    if (skillName) metrics.push(['skill', String(skillName)]);
    if (contextUsage !== null && contextUsage !== undefined && contextUsage !== '') metrics.push(['context usage', typeof contextUsage === 'object' ? JSON.stringify(contextUsage, null, 2) : String(contextUsage)]);
    if (skillErrors.length) metrics.push(['skill errors', JSON.stringify(skillErrors, null, 2)]);
    if (!metrics.length) {
        return `
            <div class="tool-call-panel-header">Metrics</div>
            <div class="tool-call-panel-body"><pre>No metrics available for this call yet.</pre></div>
        `;
    }
    return `
        <div class="tool-call-panel-header">Metrics</div>
        <div class="tool-call-panel-body"><pre>${escapeHtml(metrics.map(([label, value]) => `${label}: ${value}`).join('\n'))}</pre></div>
    `;
}

function getToolPanelCopyText(id, panel) {
    const entry = toolCallData.get(id);
    if (!entry) return '';
    const { tool, parsedArgs, parsedOutput, options } = entry;
    if (panel === 'input') return parsedArgs.raw || '';
    if (panel === 'output') return parsedOutput.raw || '';
    if (panel === 'raw') {
        return safePayloadStringify({
            tool,
            node: options?.node || null,
            parsedArgs: parsedArgs.parsed,
            parsedOutput: parsedOutput.parsed,
        }, '');
    }
    return '';
}

function copyToolPanelContent(id, panel, btn) {
    const text = getToolPanelCopyText(id, panel);
    const flash = () => {
        if (!btn) return;
        btn.textContent = 'copied';
        setTimeout(() => { btn.textContent = 'copy'; }, 1200);
    };
    const fallback = () => {
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        try {
            document.execCommand('copy');
            flash();
        } catch (e) {
            showToast('Copy failed', true);
        }
        ta.remove();
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(flash).catch(fallback);
    } else {
        fallback();
    }
}

function renderToolPanelContent(id, panel) {
    const entry = toolCallData.get(id);
    if (!entry) return '';
    const { tool, parsedArgs, parsedOutput, options } = entry;
    const copyBtn = (panelName) => `<button type="button" class="tool-copy-btn" data-tool-copy-key="${escapeHtml(id)}" data-tool-copy-panel="${panelName}">copy</button>`;
    if (panel === 'input') {
        const content = parsedArgs.raw ? highlightJSON(parsedArgs.raw) : escapeHtml('No input captured');
        return `
            <div class="tool-call-panel-header">Input ${copyBtn('input')}</div>
            <div class="tool-call-panel-body"><pre class="tool-output-json">${content}</pre></div>
        `;
    }
    if (panel === 'output') {
        const errorText = parsedOutput.parsed?.error || parsedOutput.parsed?.message || tool?.error || '';
        return `
            <div class="tool-call-panel-header">Output ${copyBtn('output')}</div>
            <div class="tool-call-panel-body">
                ${getToolStatusClass(tool) === 'error' && errorText ? `<div class="tool-call-error-banner">${escapeHtml(String(errorText))}</div>` : ''}
                ${renderToolOutput(tool.name || 'tool', parsedOutput.parsed, parsedOutput.raw || '', hasCapturedToolOutput(tool))}
                ${renderDelegateChildStreams(tool)}
            </div>
        `;
    }
    if (panel === 'metrics') {
        return renderToolMetricsPanel(tool, parsedArgs.parsed, parsedOutput.parsed, options);
    }
    if (panel === 'raw') {
        const rawPayload = {
            tool,
            node: options?.node || null,
            parsedArgs: parsedArgs.parsed,
            parsedOutput: parsedOutput.parsed,
        };
        return `
            <div class="tool-call-panel-header">Raw Event ${copyBtn('raw')}</div>
            <div class="tool-call-panel-body"><pre class="tool-output-json tool-raw-json">${highlightJSON(safePayloadStringify(rawPayload, '[Unserializable raw event]'))}</pre></div>
        `;
    }
    return '';
}

function ensureToolCallUiState(id) {
    if (!toolCallUiState.has(id)) {
        toolCallUiState.set(id, { expanded: false, activePanel: null, renderedPanels: new Set() });
    }
    return toolCallUiState.get(id);
}

function renderToolCallPanels(id, tool) {
    const state = ensureToolCallUiState(id);
    const panelButtons = [
        ['input', 'Input'],
        ['output', 'Output'],
        ['metrics', 'Metrics'],
        ['raw', 'Raw'],
    ].map(([panelKey, label]) => `
        <button type="button" class="tool-call-panel-btn${state.activePanel === panelKey ? ' active' : ''}" data-tool-panel-key="${escapeHtml(id)}" data-tool-panel-name="${panelKey}">${label}</button>
    `).join('');
    const renderedPanels = Array.from(state.renderedPanels || []);
    const errorText = parseToolPayload(tool?.output).parsed?.error || tool?.error || '';
    return `
        <div class="tool-call-expand">
            <div class="tool-call-expand-inner">
                <div class="tool-call-summary-line">
                    <span class="tool-call-summary-label">tool</span>
                    <span class="tool-call-summary-value">${escapeHtml(tool?.name || 'tool')}</span>
                    <span class="tool-call-summary-label">timestamp</span>
                    <span class="tool-call-summary-value">${escapeHtml(toolCallData.get(id)?.timestamp || '-')}</span>
                    <span class="tool-call-summary-label">status</span>
                    <span class="tool-call-status-badge ${getToolStatusClass(tool)}">${escapeHtml(getToolStatusText(getToolStatusClass(tool)))}</span>
                    <span class="tool-call-summary-label">duration</span>
                    <span class="tool-call-summary-value">${escapeHtml(getToolDurationLabel(tool) || '-')}</span>
                    ${tool?.call_id ? `<span class="tool-call-summary-label">call</span><span class="tool-call-summary-value">${escapeHtml(tool.call_id)}</span>` : ''}
                </div>
                <div class="tool-call-summary-line">
                    <span class="tool-call-summary-label">action</span>
                    <span class="tool-call-summary-value">${escapeHtml(toolCallData.get(id)?.action || 'run')}</span>
                    <span class="tool-call-summary-label">target</span>
                    <span class="tool-call-summary-value">${escapeHtml(toolCallData.get(id)?.targetDetail || toolCallData.get(id)?.target || 'n/a')}</span>
                </div>
                ${errorText && getToolStatusClass(tool) === 'error' ? `<div class="tool-call-error-banner">${escapeHtml(String(errorText))}</div>` : ''}
                <div class="tool-call-panel-bar">${panelButtons}</div>
                <div class="tool-call-panel-host" data-tool-panel-host="${escapeHtml(id)}">
                    ${renderedPanels.map((panelKey) => `
                        <div class="tool-call-panel${state.activePanel === panelKey ? ' active' : ''}" data-tool-panel="${escapeHtml(id)}:${panelKey}">
                            ${renderToolPanelContent(id, panelKey)}
                        </div>
                    `).join('')}
                </div>
            </div>
        </div>
    `;
}

function renderToolBlock(tool, idx, options = {}) {
    const toolName = tool.name || `tool_${idx + 1}`;
    const rawToolKey = getToolCallId(tool, idx, options);
    const domIdValue = options?.node?.dom_id ? scopedExecutionDomId(options.node.dom_id, options?.traceContext || null) : '';
    const domId = domIdValue ? ` id="${escapeHtml(domIdValue)}"` : '';
    const executionClass = options?.node?.dom_id ? ' execution-node' : '';
    const parsedArgs = parseToolPayload(tool.arguments);
    const parsedOutput = parseToolPayload(tool.output);
    const statusClass = getToolStatusClass(tool);
    const state = ensureToolCallUiState(rawToolKey);
    const actionLabel = getToolActionLabel(toolName, parsedArgs.parsed, parsedOutput.parsed);
    const targetSummary = getToolTargetSummary(toolName, parsedArgs.parsed, parsedArgs.raw);
    const targetDetail = getToolTargetDetail(toolName, parsedArgs.parsed, parsedArgs.raw) || targetSummary;
    const headerDescription = tool.intent_description || getLocalToolDescription(
        toolName,
        parsedArgs.parsed,
        targetDetail,
        tool.intent_description_pending === true,
    );
    const visibleDetail = getToolVisibleDetail(toolName, parsedArgs.parsed, parsedArgs.raw, targetDetail);
    const collapsedSummary = getToolCollapsedSummary(tool, parsedArgs.parsed, parsedOutput.parsed);
    const durationLabel = getToolDurationLabel(tool);
    const timestampLabel = getToolTimestampLabel(tool, options);
    toolCallData.set(rawToolKey, {
        tool,
        idx,
        options,
        parsedArgs,
        parsedOutput,
        action: actionLabel,
        target: targetSummary,
        targetDetail,
        timestamp: timestampLabel,
    });
    if (statusClass === 'error') {
        state.expanded = true;
        state.activePanel = state.activePanel || 'output';
        state.renderedPanels.add('output');
    }
    const childEntries = toolName === 'delegate_task' ? (liveChildSessionMap.get(tool.call_id || '') || []) : [];
    const drawerBtn = renderDelegateLiveActionStrip(childEntries, tool, rawToolKey);
    return `
        <div class="tool-call-block${state.expanded ? ' active' : ''}${executionClass}" data-tool-id="${escapeHtml(rawToolKey)}"${domId}>
            <button type="button" class="tool-call-pill" data-tool-toggle="${escapeHtml(rawToolKey)}">
                <span class="tool-call-status-dot ${statusClass}"></span>
                <span class="tool-call-name">${escapeHtml(toolName)}</span>
                <span class="tool-call-action-badge">${escapeHtml(actionLabel)}</span>
                <span class="tool-call-summary-text" title="${escapeHtml(headerDescription)}">${escapeHtml(headerDescription || collapsedSummary || '-')}</span>
                <span class="tool-call-meta">
                    <span class="tool-call-timer" data-call-id="${escapeHtml(tool.call_id || '')}">${escapeHtml(durationLabel || '')}</span>
                    <span class="tool-call-chevron">▶</span>
                </span>
            </button>
            ${visibleDetail.value ? `<div class="tool-call-visible-detail"><span>${escapeHtml(visibleDetail.label)}</span><pre>${escapeHtml(visibleDetail.value)}</pre></div>` : ''}
            ${drawerBtn}
            ${renderToolCallPanels(rawToolKey, tool)}
        </div>
    `;
}

function setExecutionHistoryExpanded(segmentKey, expanded) {
    if (!segmentKey) return;
    executionHistoryUiState.set(segmentKey, expanded === true);
}

function getExecutionHistorySegmentKey(entries = [], fallback = 'execution') {
    const firstKey = entries[0]?.key || entries[0]?.tool?.call_id || 'first-update';
    return `${fallback}:${firstKey}`;
}

function renderToolCallList(entries = [], options = {}) {
    if (!Array.isArray(entries) || !entries.length) return '';
    const validEntries = entries.filter(entry => entry && typeof entry === 'object');
    if (!validEntries.length) return '';
    const segmentKey = options.segmentKey || getExecutionHistorySegmentKey(validEntries, options.renderScope || 'execution');
    const visibleStart = Math.max(0, validEntries.length - 3);
    const olderEntries = validEntries.slice(0, visibleStart);
    const latestEntries = validEntries.slice(visibleStart);
    const isExpanded = executionHistoryUiState.get(segmentKey) === true;
    const olderHtml = olderEntries.length ? `
        <details class="execution-history-older"${isExpanded ? ' open' : ''} data-execution-segment-key="${escapeHtml(segmentKey)}">
            <summary>Show ${olderEntries.length} earlier call${olderEntries.length === 1 ? '' : 's'}</summary>
            <div class="tool-call-list">${olderEntries.map(entry => entry.html || '').join('')}</div>
        </details>
    ` : '';
    return `
        <section class="execution-history-bubble" aria-label="Execution history" data-execution-history-key="${escapeHtml(segmentKey)}">
            <div class="execution-history-header">
                <span>Execution</span>
                <span>${validEntries.length} call${validEntries.length === 1 ? '' : 's'}</span>
            </div>
            ${olderHtml}
            <div class="tool-call-list execution-history-latest">${latestEntries.map(entry => entry.html || '').join('')}</div>
        </section>
    `;
}

function makeToolCardEntry(tool, idx, options = {}) {
    const key = getToolCallId(tool, idx, options);
    return {
        key,
        tool,
        idx,
        html: renderToolBlock(tool, idx, options),
    };
}

function getParallelToolBatchStatusClass(tools = []) {
    const statuses = tools.map((tool) => getToolStatusClass(tool));
    if (statuses.includes('error')) return 'error';
    if (statuses.length && statuses.every((status) => status === 'complete')) return 'complete';
    if (statuses.includes('running')) return 'running';
    return 'pending';
}

function renderParallelToolBatch(toolNodes = [], traceContext = null, label = '', renderScope = 'parallel') {
    const batchId = `${renderScope}:parallel:${toolNodes.map((node, idx) => getToolCallId(node?.payload?.tool || {}, idx, { node, traceContext, renderScope })).join('|')}`;
    const state = ensureToolCallUiState(batchId);
    const tools = toolNodes.map((node) => node?.payload?.tool || {}).filter(Boolean);
    const names = Array.from(new Set(tools.map((tool) => tool?.name || 'tool'))).slice(0, 3).join(', ');
    const totalDuration = tools.map((tool) => getToolDurationLabel(tool)).filter(Boolean).pop() || '';
    const batchStatusClass = getParallelToolBatchStatusClass(tools);
    return `
        <div class="tool-call-parallel-block${state.expanded ? ' active' : ''}" data-tool-id="${escapeHtml(batchId)}">
            <button type="button" class="tool-call-parallel-pill" data-tool-toggle="${escapeHtml(batchId)}">
                <span class="tool-call-status-dot ${escapeHtml(batchStatusClass)}"></span>
                <span class="tool-call-chip">parallel ${toolNodes.length}</span>
                <span class="tool-call-summary-text">${escapeHtml(label || `parallel · ${toolNodes.length} calls · ${names}`)}</span>
                <span class="tool-call-meta">
                    <span class="tool-call-timer">${escapeHtml(totalDuration)}</span>
                    <span class="tool-call-chevron">▶</span>
                </span>
            </button>
            <div class="tool-call-parallel-expand">
                <div class="tool-call-parallel-inner">
                    <div class="tool-call-nested-list">${toolNodes.map((node, toolIdx) => renderToolBlock(node.payload.tool, toolIdx, { node, traceContext, renderScope })).join('')}</div>
                </div>
            </div>
        </div>
    `;
}

function makeParallelToolCardEntry(event, idx, traceContext = null, renderScope = 'parallel') {
    const toolNodes = Array.isArray(event?.node?.payload?.toolNodes) ? event.node.payload.toolNodes : [];
    const label = event?.node?.payload?.label || summarizeParallelGroupLabel(toolNodes.map(node => node?.payload?.tool));
    const memberKeys = toolNodes.map((node, toolIdx) => getToolCallId(
        node?.payload?.tool || {}, toolIdx, { node, traceContext, renderScope },
    ));
    return {
        key: `${renderScope}:parallel-update:${memberKeys.join('|') || idx}`,
        event,
        html: renderParallelToolBatch(toolNodes, traceContext, `${label} · ${toolNodes.length} calls`, renderScope),
    };
}

function isTranscriptToolUpdate(event) {
    return event?.type === 'tool_call' || event?.type === 'tool_output'
        || event?.type === 'tool_collection' || event?.type === 'parallel_group';
}

function getTranscriptToolUpdateIdentity(event, fallbackIndex = 0) {
    if (event?.node?.node_id) return event.node.node_id;
    const tool = event?.tool || event;
    if (tool?.call_id || tool?.id) return tool.call_id || tool.id;
    if (event?.type === 'tool_collection') {
        const first = event.tools?.[0];
        return first?.key || first?.tool?.call_id || first?.call_id || `collection-${fallbackIndex}`;
    }
    if (event?.type === 'parallel_group') {
        const firstNode = event.node?.payload?.toolNodes?.[0];
        return firstNode?.node_id || firstNode?.payload?.tool?.call_id || `parallel-${fallbackIndex}`;
    }
    return `update-${fallbackIndex}`;
}

function isMeaningfulTranscriptMeta(value) {
    if (value === null || value === undefined || value === '') return false;
    if (Array.isArray(value)) return value.length > 0;
    if (typeof value === 'number') return Number.isFinite(value) && value !== 0;
    return true;
}

function mergeTranscriptUsageMetadata(updates = []) {
    const uniqueMessages = new Set();
    const normalizedRows = [];
    (updates || []).forEach((update) => {
        const source = update?.message;
        if (source && uniqueMessages.has(source)) return;
        if (source) uniqueMessages.add(source);
        normalizedRows.push(update?.normalized || normalizeAssistantMessage(source || {}));
    });

    const usage = {};
    const tokenTotals = {};
    let lastPromptTokens = 0;
    let promptBreakdown = [];
    normalizedRows.forEach((normalized) => {
        Object.entries(normalized?.usage || {}).forEach(([key, value]) => {
            if (typeof value === 'number' && Number.isFinite(value) && /tokens?$/i.test(key)) {
                tokenTotals[key] = (tokenTotals[key] || 0) + value;
            } else if (isMeaningfulTranscriptMeta(value)) {
                usage[key] = value;
            }
        });
        if (isMeaningfulTranscriptMeta(normalized?.last_prompt_tokens)) {
            lastPromptTokens = normalized.last_prompt_tokens;
        }
        if (isMeaningfulTranscriptMeta(normalized?.prompt_breakdown)) {
            promptBreakdown = normalized.prompt_breakdown;
        }
    });

    return {
        ...(normalizedRows[normalizedRows.length - 1] || {}),
        usage: Object.keys(usage).length || Object.keys(tokenTotals).length ? { ...usage, ...tokenTotals } : null,
        last_prompt_tokens: lastPromptTokens,
        prompt_breakdown: promptBreakdown,
    };
}

function buildTranscriptRenderSegments(rows = []) {
    const segments = [];
    let pendingUpdates = [];
    let pendingSegmentKey = '';
    let transcriptPosition = 0;
    const flushUpdates = () => {
        if (!pendingUpdates.length) return;
        segments.push({
            type: 'execution',
            updates: pendingUpdates,
            segmentKey: pendingSegmentKey,
            message: pendingUpdates[pendingUpdates.length - 1]?.message || {},
            normalized: mergeTranscriptUsageMetadata(pendingUpdates),
        });
        pendingUpdates = [];
        pendingSegmentKey = '';
    };

    (Array.isArray(rows) ? rows : []).forEach((row) => {
        const message = row?.message || row;
        if (row?.kind === 'boundary' || message?.role !== 'assistant') {
            flushUpdates();
            segments.push({ type: 'boundary', row, message });
            transcriptPosition += 1;
            return;
        }
        const normalized = mergeLegacyMarkersIntoEvents(normalizeAssistantMessage(message));
        const renderScope = getAssistantRenderScope(message, normalized);
        const events = normalized.events.length
            ? normalized.events
            : [{ type: 'content', text: normalized.content || '' }];
        events.forEach((event) => {
            if (isTranscriptToolUpdate(event)) {
                if (!pendingUpdates.length) {
                    const firstIdentity = getTranscriptToolUpdateIdentity(event, transcriptPosition);
                    pendingSegmentKey = `${renderScope}:execution:${transcriptPosition}:${firstIdentity}`;
                }
                pendingUpdates.push({ event, message, normalized, renderScope, traceContext: normalized.renderTraceContext || null });
                transcriptPosition += 1;
                return;
            }
            if (event?.type === 'content' && !String(event.text || '').trim()) return;
            flushUpdates();
            segments.push({ type: 'assistant', event, message, normalized, renderScope });
            transcriptPosition += 1;
        });
    });
    flushUpdates();
    return segments;
}

function renderTranscriptExecutionEntries(segment) {
    const entries = [];
    (segment?.updates || []).forEach((update, updateIdx) => {
        const { event, renderScope, traceContext } = update;
        if (event?.type === 'tool_collection') {
            (event.tools || []).forEach((item, itemIdx) => {
                if (item?.html) entries.push(item);
                else entries.push(makeToolCardEntry(item?.tool || item, itemIdx, { traceContext, renderScope }));
            });
        } else if (event?.type === 'parallel_group') {
            entries.push(makeParallelToolCardEntry(event, updateIdx, traceContext, renderScope));
        } else if (event?.type === 'tool_call' || event?.type === 'tool_output') {
            entries.push(makeToolCardEntry(event.tool || event, updateIdx, {
                node: event.node || null, traceContext, renderScope,
            }));
        }
    });
    return entries;
}

function renderTranscriptSegments(segments = [], renderers = {}) {
    return (segments || []).map((segment) => {
        if (segment.type === 'boundary') return renderers.boundary ? renderers.boundary(segment.row, segment) : '';
        if (segment.type === 'assistant') {
            const body = segment.event?.type === 'content'
                ? `<div>${formatMessageContent(segment.event.text || '')}</div>`
                : groupSequentialToolCards([segment.event], segment.normalized?.renderTraceContext || null, segment.renderScope).join('');
            return renderers.assistant ? renderers.assistant(body, segment) : body;
        }
        if (segment.type === 'execution') {
            const entries = renderTranscriptExecutionEntries(segment);
            const scope = segment.updates?.[0]?.renderScope || 'transcript';
            const key = segment.segmentKey || getExecutionHistorySegmentKey(entries, scope);
            const body = renderToolCallList(entries, { segmentKey: key, renderScope: scope });
            return renderers.assistant ? renderers.assistant(body, segment) : body;
        }
        return '';
    }).join('');
}

function syncToolCallUi(root = document) {
    if (!root) return;
    root.querySelectorAll('[data-tool-id]').forEach((node) => {
        const id = node.getAttribute('data-tool-id');
        if (!id) return;
        const state = ensureToolCallUiState(id);
        node.classList.toggle('active', state.expanded === true);
        node.querySelectorAll('[data-tool-panel]').forEach((panelNode) => {
            const panelId = panelNode.getAttribute('data-tool-panel');
            const panelName = panelId?.split(':').pop();
            panelNode.classList.toggle('active', state.activePanel === panelName);
        });
        node.querySelectorAll('[data-tool-panel-key]').forEach((button) => {
            const panelName = button.getAttribute('data-tool-panel-name');
            button.classList.toggle('active', state.activePanel === panelName);
        });
    });
}

function groupSequentialToolCards(events = [], traceContext = null, renderScope = 'assistant') {
    if (!Array.isArray(events) || !events.length) return [];
    const rendered = [];
    let pendingTools = [];
    const flushPendingTools = () => {
        if (!pendingTools.length) return;
        rendered.push(renderToolCallList(pendingTools));
        pendingTools = [];
    };

    events.forEach((event, idx) => {
        // Providers commonly emit newline-only content between tool updates.
        // It is not a visible boundary, so keep the execution run together.
        if (event?.type === 'content' && !String(event.text || '').trim()) return;
        if (event.type === 'tool_collection') {
            flushPendingTools();
            rendered.push(renderToolCallList(event.tools || []));
            return;
        }
        if (event.type === 'tool_call' || event.type === 'tool_output') {
            pendingTools.push(makeToolCardEntry(event.tool || event, idx, { node: event.node || null, traceContext, renderScope }));
            return;
        }
        if (event.type === 'parallel_group') {
            pendingTools.push(makeParallelToolCardEntry(event, idx, traceContext, renderScope));
            return;
        }
        flushPendingTools();
        if (event.type === 'diagnostic' && event.node?.payload?.orphan) {
            rendered.push(renderOrphanDiagnosticNode(event.node, traceContext));
            return;
        }
        if (event.type === 'content') {
            rendered.push(event.text ? `<div>${formatMessageContent(event.text)}</div>` : '');
        }
    });

    flushPendingTools();
    return rendered;
}

function mergeLegacyMarkersIntoEvents(normalized) {
    const extracted = extractLegacyToolMarkers(normalized.content || '');
    if (!normalized.events.length) {
        const events = [];
        if (extracted.content) events.push({ type: 'content', text: extracted.content });
        if (extracted.tools.length) {
            events.push({
                type: 'tool_collection',
                tools: extracted.tools.map((tool, idx) => makeToolCardEntry(tool, idx)),
            });
        }
        return { ...normalized, events };
    }
    return normalized;
}

/* <!-- TOOL CALL UI v2 --> */
function toggleToolCall(id) {
    if (!id) return;
    const state = ensureToolCallUiState(id);
    state.expanded = !state.expanded;
    if (state.expanded && !state.activePanel && toolCallData.has(id)) {
        const entry = toolCallData.get(id);
        const statusClass = getToolStatusClass(entry.tool);
        if (statusClass === 'error') {
            state.activePanel = 'output';
            state.renderedPanels.add('output');
        } else if (statusClass === 'complete' && hasCapturedToolOutput(entry.tool)) {
            state.activePanel = 'output';
            state.renderedPanels.add('output');
        }
    }
    syncToolCallUi(document);
    if (state.expanded) {
        const node = document.querySelector(`[data-tool-id="${CSS.escape(id)}"]`);
        if (node) highlightToolCode(node);
    }
}

function toggleToolPanel(id, panel) {
    if (!id || !panel) return;
    const state = ensureToolCallUiState(id);
    state.expanded = true;
    state.renderedPanels.add(panel);
    state.activePanel = state.activePanel === panel ? null : panel;
    const host = document.querySelector(`[data-tool-panel-host="${CSS.escape(id)}"]`);
    if (!host) {
        syncToolCallUi(document);
        return;
    }
    const panelSelector = `[data-tool-panel="${CSS.escape(`${id}:${panel}`)}"]`;
    let panelNode = host.querySelector(panelSelector);
    if (!panelNode) {
        panelNode = document.createElement('div');
        panelNode.className = 'tool-call-panel';
        panelNode.setAttribute('data-tool-panel', `${id}:${panel}`);
        panelNode.innerHTML = renderToolPanelContent(id, panel);
        host.appendChild(panelNode);
        highlightToolCode(panelNode);
    }
    syncToolCallUi(document);
}

function renderAssistantEvents(normalized, renderScope = 'assistant') {
    const events = normalized.events.length
        ? normalized.events
        : [{ type: 'content', text: normalized.content || '' }];
    return groupSequentialToolCards(events, normalized.renderTraceContext || null, renderScope).join('');
}

function extractLegacyToolMarkers(content) {
    if (!content) return { content, tools: [] };
    const tools = [];
    const markerRegex = /^`([^\n`]+)`$/gm;
    const cleaned = content.replace(markerRegex, (full, inner) => {
        const text = (inner || '').trim();
        const match = text.match(/^[^A-Za-z0-9_\/-]*\s*([A-Za-z0-9_./-]+)(?:\s+(.*))?$/);
        if (!match) return full;
        const name = match[1];
        const rest = (match[2] || '').trim();
        tools.push({
            call_id: `legacy_${tools.length + 1}_${name}`,
            name,
            arguments: rest,
            output: '',
        });
        return '';
    });
    return {
        content: cleaned.replace(/\n{3,}/g, '\n\n').trim(),
        tools,
    };
}

function renderAssistantMessageShell(message, normalized, bodyHtml) {
    const usage = normalized.usage || {};
    const wrapperIdValue = message?.traceNode?.dom_id ? scopedExecutionDomId(message.traceNode.dom_id, normalized.renderTraceContext || null) : '';
    const wrapperId = wrapperIdValue ? ` id="${escapeHtml(wrapperIdValue)}"` : '';
    const wrapperClass = message?.traceNode?.dom_id ? ' assistant-step-block execution-node' : '';
    const metaHtml = [
        renderMetaPill('Prompt', usage.prompt_tokens),
        renderMetaPill('Completion', usage.completion_tokens),
        renderMetaPill('Total', usage.total_tokens),
        renderMetaPill('Context window', normalized.last_prompt_tokens),
    ].filter(Boolean).join('');
    const registry = typeof botRegistry !== 'undefined' && Array.isArray(botRegistry) ? botRegistry : [];
    const bot = message?.bot ? registry.find(item => item.name === message.bot) : null;
    const identity = bot || (message?.bot ? { name: message.bot, display_name: message.display_name || message.bot, color: message.color } : null);
    const assistantLabel = identity?.display_name || 'Hermes';
    const assistantAvatar = identity && typeof avatarHtml === 'function'
        ? avatarHtml(identity, { className: 'bot-avatar-message', decorative: true })
        : '';
    return `
        <div class="${wrapperClass.trim()}"${wrapperId}>
            <div class="message-header">
                <div class="message-title">${assistantAvatar}<span>${escapeHtml(assistantLabel)}</span></div>
            </div>
            <div class="assistant-tools">${bodyHtml}</div>
            ${metaHtml ? `<div class="message-meta">${metaHtml}</div>` : ''}
        </div>
    `;
}

function renderAssistantMessage(message) {
    const normalized = mergeLegacyMarkersIntoEvents(normalizeAssistantMessage(message));
    const renderScope = getAssistantRenderScope(message, normalized);
    return renderAssistantMessageShell(message, normalized, renderAssistantEvents(normalized, renderScope));
}

function normalizeToolCallEntries(toolCalls) {
    if (!Array.isArray(toolCalls)) return [];
    return toolCalls.reduce((normalized, tool, idx) => {
        if (!tool || typeof tool !== 'object' || Array.isArray(tool)) return normalized;
        const functionPayload = tool.function && typeof tool.function === 'object' ? tool.function : null;
        const hasOwn = (source, key) => Object.prototype.hasOwnProperty.call(source || {}, key);
        const argumentsValue = functionPayload && hasOwn(functionPayload, 'arguments')
            ? functionPayload.arguments
            : (hasOwn(tool, 'arguments') ? tool.arguments : '');
        const outputValue = hasOwn(tool, 'output')
            ? tool.output
            : (hasOwn(tool, 'content') ? tool.content : '');
        const { function: _functionPayload, type: _wireType, ...metadata } = tool;
        const normalizedTool = {
            ...metadata,
            call_id: tool.call_id ?? tool.id ?? `tool_${idx + 1}`,
            name: functionPayload?.name ?? tool.name ?? tool.tool_name ?? `tool_${idx + 1}`,
            arguments: argumentsValue,
            progress: normalizeToolProgressEntries(tool.progress),
        };
        if (hasOwn(tool, 'output') || hasOwn(tool, 'content')) {
            normalizedTool.output = outputValue;
        }
        normalized.push(normalizedTool);
        return normalized;
    }, []);
}

function renderLogDetails(details) {
    if (details === null || details === undefined) return '';
    if (typeof details !== 'object' || Array.isArray(details)) {
        return `<div class="detail-section"><div class="detail-label">Details</div><pre>${escapeHtml(String(details))}</pre></div>`;
    }
    const sections = [];
    const labels = { args: 'Arguments', result: 'Result', error: 'Error' };
    for (const key of Object.keys(labels)) {
        if (!Object.prototype.hasOwnProperty.call(details, key)) continue;
        const value = details[key];
        const text = typeof value === 'object' && value !== null
            ? safePayloadStringify(value, String(value))
            : String(value ?? '');
        const errorClass = key === 'error' ? ' detail-label-error' : '';
        sections.push(`<div class="detail-section"><div class="detail-label${errorClass}">${labels[key]}</div><pre>${escapeHtml(text)}</pre></div>`);
    }
    const usefulFields = Object.fromEntries(
        Object.entries(details).filter(([key]) => !Object.prototype.hasOwnProperty.call(labels, key)),
    );
    if (Object.keys(usefulFields).length) {
        sections.push(`<div class="detail-section"><div class="detail-label">Fields</div><pre>${escapeHtml(safePayloadStringify(usefulFields, String(usefulFields)))}</pre></div>`);
    }
    sections.push(`<div class="detail-section detail-section-raw"><div class="detail-label">Raw payload</div><pre>${escapeHtml(safePayloadStringify(details, String(details)))}</pre></div>`);
    return sections.join('');
}

function getDelegateChildBucket(delegateTool, taskIndex = null) {
    if (!delegateTool) return null;
    if (!delegateTool.child_events || typeof delegateTool.child_events !== 'object') {
        delegateTool.child_events = {};
    }
    const key = Number.isInteger(taskIndex) ? String(taskIndex) : 'default';
    if (!Array.isArray(delegateTool.child_events[key])) {
        delegateTool.child_events[key] = [];
    }
    return delegateTool.child_events[key];
}

function appendDelegateChildEvent(state, parsed) {
    const delegateCallId = parsed?.arguments?.delegate_call_id || parsed?.arguments?.call_id || '';
    if (!delegateCallId) return false;
    const delegateNode = findAssistantToolNode(state, delegateCallId);
    const delegateTool = delegateNode?.payload?.tool || null;
    if (!delegateTool) {
        const pending = ensureAssistantTracePendingDelegateChildren(state);
        if (!Array.isArray(pending[delegateCallId])) pending[delegateCallId] = [];
        pending[delegateCallId].push(parsed);
        if (pending[delegateCallId].length > 100) pending[delegateCallId] = pending[delegateCallId].slice(-100);
        return true;
    }

    const taskIndex = Number.isInteger(parsed?.arguments?.task_index) ? parsed.arguments.task_index : null;
    const bucket = getDelegateChildBucket(delegateTool, taskIndex);
    if (!bucket) return false;

    function findByCallId() {
        for (let i = bucket.length - 1; i >= 0; i--) {
            const event = bucket[i];
            if ((event.type === 'tool_call' || event.type === 'tool_output') && event.tool?.call_id === parsed.call_id) {
                return event;
            }
        }
        return null;
    }

    if (parsed.type === 'tool_call') {
        bucket.push({
            type: 'tool_call',
            tool: {
                call_id: parsed.call_id || `child_${bucket.length + 1}`,
                name: parsed.name || 'tool',
                arguments: parsed.arguments?.child_args || parsed.arguments || '',
                output: '',
                progress: [],
            },
        });
        return true;
    }

    if (parsed.type === 'tool_output') {
        const target = findByCallId();
        if (target) {
            target.type = 'tool_output';
            target.tool.output = parsed.output || '';
        } else {
            bucket.push({
                type: 'tool_output',
                tool: {
                    call_id: parsed.call_id || `child_${bucket.length + 1}`,
                    name: parsed.name || 'tool',
                    arguments: parsed.arguments?.child_args || parsed.arguments || '',
                    output: parsed.output || '',
                    progress: [],
                },
            });
        }
        return true;
    }

    if (parsed.type === 'tool_progress') {
        let target = findByCallId();
        if (!target) {
            const syntheticCallId = `${delegateCallId}:task:${taskIndex ?? 'default'}`;
            target = {
                type: 'tool_call',
                tool: {
                    call_id: syntheticCallId,
                    name: parsed?.arguments?.latest_tool || 'subagent',
                    arguments: parsed?.arguments?.latest_args || '',
                    output: '',
                    progress: [],
                },
            };
            bucket.push(target);
        }
        if (!target) {
            for (let i = bucket.length - 1; i >= 0; i--) {
                const event = bucket[i];
                if (event.type === 'tool_call' || event.type === 'tool_output') {
                    target = event;
                    break;
                }
            }
        }
        if (!target) return true;
        if (!Array.isArray(target.tool.progress)) target.tool.progress = [];
        const label = typeof parsed.progress === 'string'
            ? parsed.progress
            : summarizeValue(parsed.progress || parsed.arguments || '', 160);
        if (label) {
            target.tool.progress.push({
                label,
                task_index: taskIndex,
                task_count: Number.isInteger(parsed?.arguments?.task_count) ? parsed.arguments.task_count : null,
            });
            if (target.tool.progress.length > 30) target.tool.progress = target.tool.progress.slice(-30);
        }
        return true;
    }

    return false;
}

function flushPendingDelegateChildEvents(state, delegateTool) {
    if (!delegateTool?.call_id) return;
    const pending = ensureAssistantTracePendingDelegateChildren(state);
    const queued = pending[delegateTool.call_id];
    if (!Array.isArray(queued) || !queued.length) return;
    delete pending[delegateTool.call_id];
    queued.forEach(event => appendDelegateChildEvent(state, event));
}

function appendContentEvent(state, text) {
    reduceAssistantTraceEvent(state, { type: 'content', text });
}

function upsertToolEvent(state, toolEvent) {
    const eventType = Object.prototype.hasOwnProperty.call(toolEvent, 'output')
        ? 'tool_output'
        : 'tool_call';
    reduceAssistantTraceEvent(state, {
        ...toolEvent,
        type: eventType,
    });
    const tool = findAssistantToolNode(state, toolEvent.call_id)?.payload?.tool
        || findAssistantDiagnosticNode(state, node => node?.payload?.tool?.call_id === toolEvent.call_id)?.payload?.tool
        || null;
    if (tool?.name === 'delegate_task') flushPendingDelegateChildEvents(state, tool);
    return tool || {
        call_id: toolEvent.call_id || '',
        name: toolEvent.name || 'tool',
        arguments: toolEvent.arguments || '',
        output: toolEvent.output || '',
        progress: normalizeToolProgressEntries(toolEvent.progress),
    };
}

function appendToolProgress(state, toolEvent) {
    reduceAssistantTraceEvent(state, {
        ...toolEvent,
        type: 'tool_progress',
    });
    return findAssistantToolNode(state, toolEvent.call_id)?.payload?.tool
        || findAssistantDiagnosticNode(state, node => node?.payload?.tool?.call_id === toolEvent.call_id)?.payload?.tool
        || {
            call_id: toolEvent.call_id || '',
            name: toolEvent.name || 'tool',
            arguments: toolEvent.arguments || '',
            output: '',
            progress: normalizeToolProgressEntries(toolEvent.progress),
        };
}

function shouldStickToBottom(container, threshold = 80) {
    return container.scrollHeight - container.scrollTop - container.clientHeight <= threshold;
}

function scrollChatToBottom(force = false, stick = null) {
    const shouldScroll = force || stick === true || (stick === null && shouldStickToBottom(chat));
    if (shouldScroll) {
        chat.scrollTop = chat.scrollHeight;
    }
}

function renderUserMessageContent(content) {
    if (!Array.isArray(content)) {
        return formatMessageContent(content || '');
    }
    const textHtml = content
        .filter(part => part && part.type === 'text' && typeof part.text === 'string' && part.text.trim())
        .map(part => formatMessageContent(part.text))
        .join('');
    const imageHtml = content
        .filter(part => part && part.type === 'image_url' && part.image_url && typeof part.image_url.url === 'string')
        .map(part => part.image_url.url)
        .filter(url => /^data:image\//i.test(url) || /^https?:\/\//i.test(url))
        .map(url => `<button type="button" class="chat-message-image-wrap" onclick="showImageModal('${escapeHtml(url)}')" aria-label="Open pasted image"><img class="chat-message-image" src="${escapeHtml(url)}" alt="Pasted image"></button>`)
        .join('');
    const images = imageHtml ? `<div class="chat-message-images">${imageHtml}</div>` : '';
    return (textHtml || '') + images || '<span style="color:var(--text-dim);">[empty message]</span>';
}

function addMessage(role, message, save = true) {
    const div = document.createElement('div');
    div.className = `message ${role}`;
    if (role === 'assistant') {
        div.innerHTML = renderAssistantMessage(message);
        bindToolCardInteractions(div);
        bindAvatarFallbacks(div);
    } else {
        const content = typeof message === 'string' ? message : message.content;
        div.innerHTML = renderUserMessageContent(content);
    }
    chat.appendChild(div);
    if (role === 'assistant') highlightToolCode(div);
    scrollChatToBottom(true);
    return div;
}

function bindToolCardInteractions(root = document) {
    if (!root || root.dataset.toolCardBound === 'true') return;
    root.dataset.toolCardBound = 'true';
    syncToolCallUi(root);
}

// Debug logging with expandable tool calls
function log(type, message, isError = false, details = null, imageData = null) {
    const now = new Date();
    const time = now.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });

    const entry = document.createElement('div');

    const hasDetails = (details !== null && details !== undefined) || Boolean(imageData);
    entry.className = 'log-entry' + (hasDetails ? ' log-expandable' : '');

    let detailsHtml = '';
    if (hasDetails) {
        detailsHtml = `<div class="log-details">`;
        if (details !== null && details !== undefined) {
            detailsHtml += renderLogDetails(details);
        }
        if (imageData) {
            detailsHtml += `<img src="${imageData}" alt="Screenshot">`;
        }
        detailsHtml += '</div>';
    }

    const expandArrow = hasDetails ? '<span class="expand-arrow">▶</span>' : '';

    entry.innerHTML = `
        <div class="log-entry-header" ${hasDetails ? 'onclick="toggleLogEntry(this.parentElement)"' : ''}>
            ${expandArrow}
            <span class="log-time">${time}</span>
            <span class="log-type ${type}">${type}</span>
            <span class="log-content ${isError ? 'error' : ''}">${escapeHtml(message)}</span>
        </div>
        ${detailsHtml}
    `;

    debugLog.appendChild(entry);
    debugLog.scrollTop = debugLog.scrollHeight;

    // Keep only last 200 entries
    while (debugLog.children.length > 200) {
        debugLog.removeChild(debugLog.firstChild);
    }
}

function toggleLogEntry(entry) {
    entry.classList.toggle('expanded');
}

function clearLog() {
    debugLog.innerHTML = '';
    log('inf', 'Log cleared');
}

function applyDebugVisibility() {
    const panel = document.getElementById('debug-panel');
    const reopen = document.getElementById('debug-reopen');
    if (panel) panel.classList.toggle('collapsed', !debugVisible);
    if (reopen) reopen.classList.toggle('visible', !debugVisible);
}

function toggleDebug() {
    debugVisible = !debugVisible;
    applyDebugVisibility();
}

// Image modal
function showImageModal(src) {
    document.getElementById('image-modal-img').src = src;
    document.getElementById('image-modal').classList.add('active');
}

function closeImageModal() {
    document.getElementById('image-modal').classList.remove('active');
}

function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        showToast('Copied!');
    }).catch(() => {
        showToast('Copy failed', true);
    });
}

let botRoomRegistry = [];
let botEditorName = null;
let createAvatarPreviewUrl = null;
let editAvatarPreviewUrl = null;

function setChatRoomRailExpanded(expanded, persist = true) {
    const isExpanded = Boolean(expanded);
    chatRoomRail?.classList.toggle('expanded', isExpanded);
    if (chatRoomRailToggle) {
        chatRoomRailToggle.setAttribute('aria-expanded', String(isExpanded));
        const action = isExpanded ? 'Collapse' : 'Expand';
        chatRoomRailToggle.setAttribute('aria-label', `${action} chat room rail`);
        chatRoomRailToggle.title = `${action} chat room rail`;
    }
    if (!persist) return;
    try {
        if (isExpanded) localStorage.setItem(CHAT_ROOM_RAIL_EXPANDED_KEY, 'true');
        else localStorage.removeItem(CHAT_ROOM_RAIL_EXPANDED_KEY);
    } catch (error) {
        log('warn', `Failed to save room rail preference: ${error.message}`);
    }
}

function initializeChatRoomRail() {
    let expanded = false;
    try {
        expanded = localStorage.getItem(CHAT_ROOM_RAIL_EXPANDED_KEY) === 'true';
    } catch (error) {
        log('warn', `Failed to restore room rail preference: ${error.message}`);
    }
    setChatRoomRailExpanded(expanded, false);
    chatRoomRailToggle?.addEventListener('click', () => {
        setChatRoomRailExpanded(chatRoomRailToggle.getAttribute('aria-expanded') !== 'true');
    });
}

function renderBotRoster() {
    const roster = document.getElementById('bots-roster');
    if (!roster) return;
    if (!botRegistry.length) {
        roster.innerHTML = '<div class="bots-empty"><strong>No profiles yet.</strong><span>Create a focused Hermes identity for a role you want to keep isolated.</span></div>';
        return;
    }
    roster.innerHTML = botRegistry.map((bot, index) => {
        const color = safeBotColor(bot.color);
        const providerModel = [bot.provider, bot.model].filter(Boolean).join(' / ') || 'Model follows profile config';
        return `<article class="bot-roster-row ${bot.hidden ? 'is-hidden' : ''}" style="--bot-color:${color}">
            <div class="bot-roster-index">${String(index + 1).padStart(2, '0')}</div>
            <div class="bot-identity">
                ${avatarHtml(bot)}
                <div><h3>${escapeHtml(bot.display_name || bot.name)}</h3><code>@${escapeHtml(bot.name || '')}</code></div>
            </div>
            <div class="bot-role"><strong>${escapeHtml(bot.title || 'Hermes profile')}</strong><p>${escapeHtml(bot.description || 'No role description yet.')}</p></div>
            <div class="bot-runtime"><span>${escapeHtml(providerModel)}</span><small>${Number(bot.skill_count) || 0} skills${bot.is_default ? ' / default' : ''}${bot.hidden ? ' / hidden' : ''}</small></div>
            <div class="bot-roster-actions">
                <button class="btn primary" type="button" data-bot-open="${escapeHtml(bot.name || '')}" ${bot.hidden ? 'disabled' : ''}>Open Chat</button>
                <button class="btn" type="button" data-bot-settings="${escapeHtml(bot.name || '')}" aria-label="Edit settings for ${escapeHtml(bot.display_name || bot.name || 'bot')}">Settings</button>
                <button class="btn" type="button" data-bot-visibility="${escapeHtml(bot.name || '')}" data-bot-hidden="${bot.hidden ? 'true' : 'false'}">${bot.hidden ? 'Unhide' : 'Hide'}</button>
            </div>
        </article>`;
    }).join('');
    roster.querySelectorAll('[data-bot-open]').forEach(button => {
        button.addEventListener('click', () => openBotChat(button.dataset.botOpen));
    });
    roster.querySelectorAll('[data-bot-settings]').forEach(button => {
        button.addEventListener('click', () => openBotEditor(button.dataset.botSettings));
    });
    roster.querySelectorAll('[data-bot-visibility]').forEach(button => {
        button.addEventListener('click', () => setBotHidden(button.dataset.botVisibility, button.dataset.botHidden !== 'true'));
    });
    bindAvatarFallbacks(roster);
}

function renderChatRoomRail() {
    if (!chatRoomList) return;
    const roomAvatar = (roomId, identity) => `<span class="chat-room-avatar-wrap${getActiveRun(roomId) ? ' running' : ''}">${avatarHtml(identity, { className: 'bot-avatar-rail', decorative: true })}</span>`;
    const mainIdentity = defaultBotIdentity();
    const sharedIdentity = identityForRoom('shared');
    const roomTab = (roomId, content) => `<button class="chat-room-tab" type="button" data-room-id="${escapeHtml(roomId)}" title="${escapeHtml(botTooltip(identityForRoom(roomId)))}">${roomAvatar(roomId, identityForRoom(roomId))}<span class="chat-room-tab-copy">${content}</span></button>`;
    const mainContent = `<strong>Main</strong><small>Default ${escapeHtml(mainIdentity.display_name || 'Hermes')} profile</small>`;
    const sharedContent = `<strong>All Bots Room</strong><small>Shared profile roundtable</small>`;
    const fixedRooms = `
        <div class="chat-room-group" data-room-group="main">${roomTab('main', mainContent)}${renderRoomChildSessionEntries('main')}</div>
        <div class="chat-room-group" data-room-group="shared">${roomTab('shared', sharedContent)}${renderRoomChildSessionEntries('shared')}</div>
        ${renderSubagentFlightRailItem()}`;
    const botRooms = botRegistry.filter(bot => !bot.hidden).map(bot => {
        const roomId = `bot:${bot.name || ''}`;
        const content = `<strong>${escapeHtml(bot.display_name || bot.name)}</strong><small>@${escapeHtml(bot.name || '')}</small>`;
        return `<div class="chat-room-group" data-room-group="${escapeHtml(roomId)}">${roomTab(roomId, content)}${renderRoomChildSessionEntries(roomId)}</div>`;
    }).join('');
    chatRoomList.innerHTML = fixedRooms + botRooms;
    chatRoomList.querySelectorAll('[data-room-id]').forEach(button => {
        button.classList.toggle('active', button.dataset.roomId === activeChatRoomId);
        if (button.dataset.roomId === activeChatRoomId) button.setAttribute('aria-current', 'page');
        else button.removeAttribute('aria-current');
        button.addEventListener('click', () => switchChatRoom(button.dataset.roomId));
    });
    bindAvatarFallbacks(chatRoomList);
}

function updateChatRoomChrome() {
    const bot = botForRoom();
    const room = botRoomRegistry.find(item => (item.room_id || item.id) === activeChatRoomId);
    let title = 'Hermes';
    let subtitle = 'Your default dashboard conversation and session.';
    let eyebrow = 'MAIN PROFILE';
    let profile = 'default';
    let placeholder = 'Message Hermes...';
    if (activeChatRoomId === 'shared') {
        title = room?.title || 'All Bots Room';
        subtitle = 'One prompt, multiple profile perspectives.';
        eyebrow = 'SHARED ROUNDTABLE';
        profile = 'all profiles';
        placeholder = 'Ask the roster...';
    } else if (bot) {
        title = room?.title || bot.display_name || bot.name;
        subtitle = bot.description || 'Isolated Hermes profile conversation.';
        eyebrow = 'BOT DIRECT MESSAGE';
        profile = `@${bot.name}`;
        placeholder = `Message ${bot.display_name || bot.name}...`;
    }
    if (chatRoomTitle) chatRoomTitle.textContent = title;
    if (chatRoomSubtitle) chatRoomSubtitle.textContent = subtitle;
    if (chatRoomEyebrow) chatRoomEyebrow.textContent = eyebrow;
    if (chatRoomProfile) chatRoomProfile.textContent = profile;
    if (chatRoomAvatar) {
        chatRoomAvatar.outerHTML = avatarHtml(identityForRoom(), { className: 'bot-avatar-heading', decorative: true }).replace('<span class="bot-avatar bot-avatar-heading"', '<span id="chat-room-avatar" class="bot-avatar bot-avatar-heading"');
        chatRoomAvatar = document.getElementById('chat-room-avatar');
        bindAvatarFallbacks(chatRoomAvatar);
    }
    if (userInput) userInput.placeholder = placeholder;
    if (chatImageBtn) chatImageBtn.disabled = activeChatRoomId === 'shared';
    renderChatRoomRail();
}

async function loadBots() {
    try {
        const [botsData, roomsData] = await Promise.all([
            fetchJsonOrThrow('/api/bots'),
            fetchJsonOrThrow('/api/bot-rooms'),
        ]);
        botRegistry = Array.isArray(botsData?.bots) ? botsData.bots : [];
        botRoomRegistry = Array.isArray(roomsData?.rooms) ? roomsData.rooms : [];
        renderBotRoster();
        updateChatRoomChrome();
    } catch (error) {
        const roster = document.getElementById('bots-roster');
        if (roster) roster.innerHTML = `<div class="bots-empty error">Could not load profiles: ${escapeHtml(error.message || error)}</div>`;
        showToast(`Failed to load bots: ${error.message || error}`, true);
    }
}

function toggleCreateBotForm(force) {
    const form = document.getElementById('bot-create-form');
    if (!form) return;
    form.classList.toggle('visible', typeof force === 'boolean' ? force : !form.classList.contains('visible'));
    if (form.classList.contains('visible')) document.getElementById('bot-name')?.focus();
}

function validateAvatarFile(file) {
    if (!file) return null;
    if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type)) {
        throw new Error('Avatar must be a PNG, JPEG, or WebP image');
    }
    if (file.size > 2 * 1024 * 1024) throw new Error('Avatar must be 2 MiB or smaller');
    return file;
}

function revokeAvatarPreview(kind) {
    const url = kind === 'create' ? createAvatarPreviewUrl : editAvatarPreviewUrl;
    if (url) URL.revokeObjectURL(url);
    if (kind === 'create') createAvatarPreviewUrl = null;
    else editAvatarPreviewUrl = null;
}

function renderAvatarPreview(element, identity, file = null, kind = 'edit') {
    if (!element) return;
    revokeAvatarPreview(kind);
    element.outerHTML = avatarHtml(identity, { className: 'bot-avatar-preview', decorative: true }).replace(
        '<span class="bot-avatar bot-avatar-preview"',
        `<span id="${escapeHtml(element.id)}" class="bot-avatar bot-avatar-preview"`,
    );
    const replacement = document.getElementById(element.id);
    if (file && replacement) {
        const url = URL.createObjectURL(file);
        if (kind === 'create') createAvatarPreviewUrl = url;
        else editAvatarPreviewUrl = url;
        const image = document.createElement('img');
        image.src = url;
        image.alt = '';
        replacement.appendChild(image);
    }
    bindAvatarFallbacks(replacement);
}

async function uploadBotAvatar(name, file) {
    validateAvatarFile(file);
    const response = await fetch(`/api/bots/${encodeURIComponent(name)}/avatar`, {
        method: 'PUT',
        headers: { 'Content-Type': file.type },
        body: file,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data?.ok === false) throw new Error(data.error || `Avatar upload failed (HTTP ${response.status})`);
    return data;
}

async function openBotEditor(name) {
    const form = document.getElementById('bot-edit-form');
    const status = document.getElementById('bot-edit-status');
    if (!form || !name) return;
    closeBotEditor();
    form.classList.add('visible');
    form.setAttribute('aria-busy', 'true');
    botEditorName = name;
    if (status) status.textContent = `Loading @${name} settings...`;
    try {
        const data = await fetchJsonOrThrow(`/api/bots/${encodeURIComponent(name)}`);
        const bot = data?.bot || data;
        form.elements.name.value = bot.name || name;
        form.elements.display_name.value = bot.display_name || '';
        form.elements.description.value = bot.description || '';
        form.elements.soul.value = bot.soul || '';
        form.elements.color.value = safeBotColor(bot.color);
        form.elements.hidden.checked = Boolean(bot.hidden);
        renderAvatarPreview(document.getElementById('bot-edit-avatar-preview'), bot, null, 'edit');
        const remove = document.getElementById('bot-avatar-remove');
        if (remove) remove.disabled = !bot.avatar_url;
        if (status) status.textContent = `Editing @${name}`;
        form.elements.display_name.focus();
    } catch (error) {
        if (status) status.textContent = `Could not load settings: ${error.message || error}`;
        showToast(`Failed to load @${name}: ${error.message || error}`, true);
    } finally {
        form.setAttribute('aria-busy', 'false');
    }
}

function closeBotEditor() {
    const form = document.getElementById('bot-edit-form');
    revokeAvatarPreview('edit');
    form?.classList.remove('visible');
    form?.reset();
    botEditorName = null;
}

async function saveBotEditor(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const submit = document.getElementById('bot-edit-submit');
    const status = document.getElementById('bot-edit-status');
    const name = botEditorName || form.elements.name.value;
    let file = null;
    const body = {
        display_name: form.elements.display_name.value.trim(),
        description: form.elements.description.value.trim(),
        soul: form.elements.soul.value.trim(),
        color: form.elements.color.value,
        hidden: form.elements.hidden.checked,
    };
    if (submit) submit.disabled = true;
    form.setAttribute('aria-busy', 'true');
    if (status) status.textContent = `Saving @${name}...`;
    try {
        file = validateAvatarFile(form.elements.avatar.files?.[0] || null);
        await fetchJsonOrThrow(`/api/bots/${encodeURIComponent(name)}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        if (file) await uploadBotAvatar(name, file);
        if (body.hidden && activeChatRoomId === `bot:${name}`) await switchChatRoom('main');
        await loadBots();
        closeBotEditor();
        showToast(`Saved @${name}`);
    } catch (error) {
        if (status) status.textContent = `Save failed: ${error.message || error}`;
        showToast(`Failed to save @${name}: ${error.message || error}`, true);
    } finally {
        if (submit) submit.disabled = false;
        form.setAttribute('aria-busy', 'false');
    }
}

async function removeBotAvatar() {
    if (!botEditorName) return;
    const button = document.getElementById('bot-avatar-remove');
    const status = document.getElementById('bot-edit-status');
    if (button) button.disabled = true;
    if (status) status.textContent = `Removing @${botEditorName} avatar...`;
    try {
        await fetchJsonOrThrow(`/api/bots/${encodeURIComponent(botEditorName)}/avatar`, { method: 'DELETE' });
        const bot = botRegistry.find(item => item.name === botEditorName) || { name: botEditorName };
        renderAvatarPreview(document.getElementById('bot-edit-avatar-preview'), { ...bot, avatar_url: '' }, null, 'edit');
        await loadBots();
        if (status) status.textContent = 'Avatar removed. Other unsaved field changes are still in the form.';
        showToast(`Removed @${botEditorName} avatar`);
    } catch (error) {
        if (button) button.disabled = false;
        if (status) status.textContent = `Avatar removal failed: ${error.message || error}`;
    }
}

async function createBot(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const submit = document.getElementById('bot-create-submit');
    const body = {
        name: form.elements.name.value.trim(),
        display_name: form.elements.display_name.value.trim(),
        description: form.elements.description.value.trim(),
        soul: form.elements.soul.value.trim(),
        color: form.elements.color.value,
    };
    let avatar = null;
    const status = document.getElementById('bot-create-status');
    if (submit) submit.disabled = true;
    if (status) status.textContent = `Creating @${body.name}...`;
    try {
        avatar = validateAvatarFile(form.elements.avatar.files?.[0] || null);
        const data = await fetchJsonOrThrow('/api/bots', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        if (data?.ok === false) throw new Error(data.error || 'Profile creation failed');
        if (avatar) await uploadBotAvatar(body.name, avatar);
        revokeAvatarPreview('create');
        form.reset();
        form.elements.color.value = '#60a5fa';
        renderAvatarPreview(document.getElementById('bot-create-avatar-preview'), { display_name: '?', color: '#60a5fa' }, null, 'create');
        toggleCreateBotForm(false);
        await loadBots();
        showToast(`Created @${body.name}`);
    } catch (error) {
        if (status) status.textContent = `Creation failed: ${error.message || error}`;
        showToast(`Failed to create bot: ${error.message || error}`, true);
    } finally {
        if (submit) submit.disabled = false;
    }
}

async function setBotHidden(name, hidden) {
    try {
        const options = hidden
            ? { method: 'DELETE' }
            : { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ hidden: false }) };
        const data = await fetchJsonOrThrow(`/api/bots/${encodeURIComponent(name)}`, options);
        if (data?.ok === false) throw new Error(data.error || 'Profile update failed');
        if (hidden && activeChatRoomId === `bot:${name}`) await switchChatRoom('main');
        await loadBots();
        showToast(`${hidden ? 'Hidden' : 'Restored'} @${name}`);
    } catch (error) {
        showToast(`Failed to update @${name}: ${error.message || error}`, true);
    }
}

async function saveCurrentChatRoom() {
    if (activeChatRoomId === 'main') {
        await saveDashboardState('conversation', conversation, { immediate: true });
        saveActiveChatSession();
    } else {
        await saveBotRoom(activeChatRoomId, conversation, activeChatSessionId);
    }
}

async function loadChatRoom(roomId) {
    const previousIntentEpoch = chatRoomIntentEpochs.get(roomId) || 0;
    const invalidateLateIntents = !getActiveRun(roomId);
    if (invalidateLateIntents) chatRoomIntentEpochs.set(roomId, previousIntentEpoch + 1);
    try {
        if (roomId === 'main') {
            conversation = [];
            await loadConversation();
            loadActiveChatSession();
            return;
        }
        const data = await fetchJsonOrThrow(`/api/bot-rooms/${encodeURIComponent(roomId)}`);
        const room = data?.room || data;
        conversation = Array.isArray(room?.conversation) ? room.conversation : [];
        activeChatSessionId = room?.session_id || null;
    } catch (error) {
        if (invalidateLateIntents) chatRoomIntentEpochs.set(roomId, previousIntentEpoch);
        throw error;
    }
}

async function switchChatRoom(roomId, options = {}) {
    if (!roomId || roomId === activeChatRoomId || chatRoomSwitchInFlight) return roomId === activeChatRoomId;
    if (!options.allowActiveRun && sharedRoomRequestInFlight) {
        showToast('Wait for the shared room response before switching rooms', true);
        return false;
    }
    const previous = { roomId: activeChatRoomId, conversation, sessionId: activeChatSessionId };
    chatRoomSwitchInFlight = true;
    if (chatRoomList) chatRoomList.classList.add('is-switching');
    try {
        await saveCurrentChatRoom();
        await loadChatRoom(roomId);
        activeChatRoomId = roomId;
        saveActiveChatRoom();
        clearPendingImageAttachments();
        renderConversation();
        updateChatRoomChrome();
        const lastAssistant = [...conversation].reverse().find(msg => msg.role === 'assistant');
        updateContextDisplay(activeChatRoomId === 'shared' || !lastAssistant ? { usage: null, last_prompt_tokens: 0 } : normalizeAssistantMessage(lastAssistant));
        void refreshSessionContextInfo(activeChatSessionId);
        updateActiveChatBanner();
        updateActiveRunBanner();
        const roomRun = getActiveRun();
        if (roomRun?.sessionId) showInterruptButton(roomRun.sessionId);
        else hideInterruptButton(false);
        syncChatInputState();
        userInput?.focus();
        return true;
    } catch (error) {
        activeChatRoomId = previous.roomId;
        conversation = previous.conversation;
        activeChatSessionId = previous.sessionId;
        renderConversation();
        updateChatRoomChrome();
        showToast(`Failed to open room: ${error.message || error}`, true);
        return false;
    } finally {
        chatRoomSwitchInFlight = false;
        if (chatRoomList) chatRoomList.classList.remove('is-switching');
    }
}

async function openBotChat(name) {
    navigateTo('chat');
    await switchChatRoom(`bot:${name}`);
}

// Navigation & hash routing
function navigateTo(hash) {
    const requestedPanel = String(hash || '').split('/')[0];
    if (requestedPanel && !isDashboardTabVisible(requestedPanel)) {
        hash = 'chat';
    }
    log('inf', 'Navigate to: #' + hash);
    const mobileMenu = document.getElementById('mobile-menu');
    if (mobileMenu) mobileMenu.classList.remove('open');
    location.hash = hash;
    if (location.hash.slice(1) === hash) {
        handleHashChange();
    }
}

function switchToPanel(panel) {
    if (panel !== 'scrolls' && typeof stopScrollsResearchAutoRefresh === 'function') {
        stopScrollsResearchAutoRefresh();
    }
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
    const tab = document.querySelector(`.tab[data-panel="${panel}"]`);
    if (tab) tab.classList.add('active');
    const panelEl = document.getElementById(panel + '-panel');
    if (panelEl) panelEl.classList.add('active');

    // Update mobile menu active state
    document.querySelectorAll('.mobile-tab').forEach(t => {
        t.classList.toggle('active', t.dataset.panel === panel);
    });

    // Lazy loading / refresh on revisit for dynamic panels
    if (!tabLoaded[panel]) {
        tabLoaded[panel] = true;
        log('inf', 'Lazy-loading panel: ' + panel);
        switch(panel) {
            case 'bots': loadBots(); break;
            case 'kanban': loadKanban(); break;
            case 'message-board': loadMessageBoardPosts(); break;
            case 'dashboard-chat': loadDashboardChat(); break;
            case 'parallel-arena': loadParallelArena(); break;
            case 'config': loadSettings(); break;
            case 'secrets': loadSecrets(); break;
            case 'sessions': loadSessions(); loadSessionSources(); break;
            case 'agent-observability': loadAgentObservability(); break;
            case 'memory': loadMemory(); break;
            case 'skills': loadSkills(); break;
            case 'capabilities': loadCapabilities(); break;
            case 'files': loadFileManager(); break;
            case 'games': loadGames(); break;
            case 'roguelike': initRoguelike(); break;
            case 'dnd': loadDndCampaigns(); break;
            case 'self-improvement': loadSelfImprovement(); break;
            case 'autonomous-development': loadAutonomousDevelopment(); break;
            case 'nexussy': loadNexussy(); break;
            case 'scrolls': loadScrollsResearch(); break;
            case 'cron': loadCronJobs(); break;
            case 'schedule': loadSchedulePanel(); break;
            case 'graph': loadGraph(); break;
        }
    } else if (panel === 'sessions') {
        loadSessions();
    } else if (panel === 'agent-observability') {
        loadAgentObservability();
    } else if (panel === 'bots') {
        loadBots();
    } else if (panel === 'kanban') {
        loadKanban();
    } else if (panel === 'message-board') {
        loadMessageBoardPosts();
    } else if (panel === 'dashboard-chat') {
        loadDashboardChat();
    } else if (panel === 'parallel-arena') {
        loadParallelArena();
    } else if (panel === 'games') {
        loadGames();
    } else if (panel === 'roguelike') {
        initRoguelike();
    } else if (panel === 'dnd') {
        loadDndCampaigns();
    } else if (panel === 'self-improvement') {
        loadSelfImprovement();
    } else if (panel === 'autonomous-development') {
        loadAutonomousDevelopment();
    } else if (panel === 'nexussy') {
        loadNexussy();
    } else if (panel === 'scrolls') {
        loadScrollsResearch();
    } else if (panel === 'graph') {
        loadGraph();
    } else if (panel === 'capabilities') {
        loadCapabilities(true);
    } else if (panel === 'files') {
        loadFileDirectory();
    }

    // Close mobile menu if open
    const mobileMenu = document.getElementById('mobile-menu');
    if (mobileMenu) mobileMenu.classList.remove('open');

    // Close session detail if navigating away or to sessions list
    const sessionDetail = document.getElementById('session-detail');
    if (sessionDetail && sessionDetail.classList.contains('active')) {
        if (panel !== 'sessions' || !location.hash.includes('detail')) {
            sessionDetail.classList.remove('active');
            currentSessionFiles = [];
        }
    }

    // Update breadcrumbs
    updateBreadcrumbs(panel);
}

function handleHashChange() {
    const hash = location.hash.slice(1) || 'chat';
    const parts = hash.split('/');
    const panel = parts[0];

    const validPanels = ['chat','bots','kanban','message-board','dashboard-chat','parallel-arena','config','secrets','sessions','agent-observability','memory','skills','capabilities','files','games','roguelike','diagnostics','dnd','self-improvement','autonomous-development','nexussy','scrolls','cron','schedule','graph'];
    if (!validPanels.includes(panel) || !isDashboardTabVisible(panel)) {
        switchToPanel('chat');
        return;
    }

    switchToPanel(panel);

    // Handle sub-routes like sessions/detail/{id}
    if (panel === 'sessions' && parts[1] === 'detail' && parts[2]) {
        pendingSessionExecutionTarget = parts[3] && parts[4]
            ? { kind: decodeURIComponent(parts[3]), id: decodeURIComponent(parts[4]) }
            : null;
        viewSession(parts[2]);
    }
}

function updateBreadcrumbs(panel, detail) {
    const bc = document.getElementById('breadcrumbs');
    if (!bc) return;

    const names = { chat:'Chat', bots:'Bots', kanban:'Kanban', 'message-board':'Message Board', 'dashboard-chat':'Dashboard Chat', 'parallel-arena':'Parallel Arena', config:'Config', secrets:'Secrets', sessions:'Sessions', 'agent-observability':'Agent Ops', memory:'Memory', skills:'Skills', capabilities:'Capabilities', files:'Files', games:'Games', roguelike:'Roguelike', diagnostics:'Diagnostics', dnd:'Campaigns', 'self-improvement':'Self-Improvement', 'autonomous-development':'Autonomous Development', nexussy:'Nexussy', scrolls:'Vesuvius AutoResearch', cron:'Cron', schedule:'Schedule', graph:'Graph' };

    if (detail) {
        bc.className = 'breadcrumbs visible';
        bc.innerHTML = '<a onclick="navigateTo(\'' + panel + '\')">' + (names[panel] || panel) + '</a><span class="separator">&#9656;</span><span>' + detail + '</span>';
    } else {
        bc.className = 'breadcrumbs';
        bc.innerHTML = '';
    }
}

function toggleMobileMenu() {
    const menu = document.getElementById('mobile-menu');
    menu.classList.toggle('open');
}

async function fetchJsonOrThrow(url, options = {}) {
    const response = await fetch(url, options);
    let data = null;
    try {
        data = await response.json();
    } catch (error) {
        data = null;
    }
    if (!response.ok) {
        const message = data && typeof data.error === 'string'
            ? data.error
            : `HTTP ${response.status}: ${response.statusText}`;
        throw new Error(message);
    }
    return data;
}

let kanbanControlPending = false;

function renderKanbanStatus(status) {
    const state = document.getElementById('kanban-control-state');
    const open = document.getElementById('kanban-open-board');
    const enable = document.getElementById('kanban-enable-btn');
    const disable = document.getElementById('kanban-disable-btn');
    const refresh = document.getElementById('kanban-refresh-btn');
    const message = document.getElementById('kanban-control-message');
    const policy = document.getElementById('kanban-policy-details');
    const automation = document.getElementById('kanban-automation-details');
    if (!state) return;

    const installed = Boolean(status?.installed);
    const enabled = Boolean(status?.enabled);
    const dispatchEnabled = Boolean(status?.dispatch_enabled);
    const serviceActive = Boolean(status?.service_active);
    const label = !installed ? 'Kanban unavailable' : (enabled ? 'Kanban enabled' : (serviceActive ? 'Dispatch paused' : 'Kanban disabled'));
    state.classList.toggle('is-enabled', enabled);
    state.classList.toggle('is-disabled', !enabled);
    const title = state.querySelector('strong');
    if (title) title.textContent = label;

    if (open) {
        open.href = status?.board_url || 'http://127.0.0.1:8083/kanban';
        open.setAttribute('aria-disabled', String(!serviceActive));
        open.tabIndex = serviceActive ? 0 : -1;
    }
    if (enable) enable.disabled = kanbanControlPending || enabled || !installed;
    if (disable) disable.disabled = kanbanControlPending || (!dispatchEnabled && !serviceActive);
    if (refresh) refresh.disabled = kanbanControlPending;

    if (policy) policy.innerHTML = `
        <div><dt>Orchestrator</dt><dd>${escapeHtml(status?.orchestrator_profile || 'not configured')}</dd></div>
        <div><dt>Default worker</dt><dd>${escapeHtml(status?.default_assignee || 'not configured')}</dd></div>
        <div><dt>Concurrency</dt><dd>${escapeHtml(String(status?.max_in_progress ?? 'auto'))} global / ${escapeHtml(String(status?.max_in_progress_per_profile ?? 'auto'))} per profile</dd></div>`;
    if (automation) automation.innerHTML = `
        <div><dt>Auto-decompose</dt><dd>${status?.auto_decompose ? 'enabled' : 'manual'}</dd></div>
        <div><dt>Auto-review</dt><dd>${status?.review_dispatch ? 'enabled' : 'human'}</dd></div>
        <div><dt>Native service</dt><dd>${serviceActive ? 'active' : (status?.service_enabled ? 'stopped' : 'disabled')}</dd></div>`;
    if (message && !kanbanControlPending) {
        message.textContent = enabled
            ? 'New cards can dispatch on the next gateway tick. Open Board launches the native Hermes Kanban interface.'
            : 'No new Kanban workers will be dispatched. Existing workers, if any, are allowed to finish.';
    }
}

async function loadKanban() {
    const message = document.getElementById('kanban-control-message');
    try {
        const status = await fetchJsonOrThrow('/api/kanban');
        renderKanbanStatus(status);
    } catch (error) {
        if (message) message.textContent = `Could not read Kanban status: ${error.message}`;
        showToast(`Kanban status failed: ${error.message}`, true);
    }
}

async function controlKanban(action) {
    if (kanbanControlPending || !['enable', 'disable'].includes(action)) return;
    if (action === 'disable' && !confirm('Disable Kanban dispatch and stop the native board? Existing workers will finish naturally.')) return;
    kanbanControlPending = true;
    const message = document.getElementById('kanban-control-message');
    if (message) message.textContent = action === 'enable' ? 'Starting Kanban...' : 'Pausing Kanban safely...';
    document.querySelectorAll('#kanban-panel button').forEach(button => { button.disabled = true; });
    try {
        const status = await fetchJsonOrThrow('/api/kanban/control', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                action,
                intent: 'kanban_deployment_control',
                passphrase: currentApprovalPassphrase(),
            }),
        });
        showToast(action === 'enable' ? 'Kanban enabled' : 'Kanban disabled');
        renderKanbanStatus(status);
    } catch (error) {
        if (message) message.textContent = `Could not ${action} Kanban: ${error.message}`;
        showToast(`Could not ${action} Kanban: ${error.message}`, true);
    } finally {
        kanbanControlPending = false;
        await loadKanban();
    }
}

let parallelArenaActiveRunId = null;

function parallelArenaStatusClass(status) {
    if (status === 'completed') return 'success';
    if (status === 'running') return 'info';
    if (status === 'cancelled') return 'warning';
    if (status === 'failed') return 'error';
    return '';
}


function renderParallelArenaArtifactButtons(runId, lane = {}) {
    const artifacts = Array.isArray(lane.artifact_manifest) ? lane.artifact_manifest : [];
    if (!runId || !lane.lane_id || !artifacts.length) {
        return '<p class="message-meta">No browsable artifacts yet.</p>';
    }
    return `<div class="parallel-arena-artifact-buttons">${artifacts.map((artifact) => `
        <button type="button" class="small secondary" onclick="openParallelArenaArtifact('${escapeHtml(runId)}','${escapeHtml(lane.lane_id)}','${escapeHtml(artifact.name)}')">
            ${escapeHtml(artifact.label || artifact.file_name || artifact.name)} · ${escapeHtml(artifact.kind || 'text')} · ${escapeHtml(String(artifact.size_bytes || 0))}b
        </button>
    `).join('')}</div>`;
}

async function openParallelArenaArtifact(runId, laneId, artifactName) {
    try {
        const data = await fetchJsonOrThrow(`/api/parallel-arena/runs/${encodeURIComponent(runId)}/artifacts/${encodeURIComponent(laneId)}/${encodeURIComponent(artifactName)}`);
        const artifact = data.artifact || {};
        const content = artifact.kind === 'json' && data.json
            ? JSON.stringify(data.json, null, 2)
            : (data.content || '');
        const popup = window.open('', '_blank', 'noopener,noreferrer,width=980,height=720');
        if (!popup) {
            showToast('Popup blocked; artifact loaded but could not open viewer.', true);
            return;
        }
        popup.document.write(`<!doctype html><title>${escapeHtml(artifact.label || artifactName)}</title><style>body{font-family:system-ui;margin:24px;background:#111827;color:#e5e7eb}pre{white-space:pre-wrap;background:#020617;padding:16px;border-radius:12px;overflow:auto}.meta{color:#9ca3af}</style><h1>${escapeHtml(artifact.label || artifactName)}</h1><p class="meta">${escapeHtml(data.run_id)} · ${escapeHtml(data.lane_id)} · ${escapeHtml(artifact.file_name || '')}${data.truncated ? ' · truncated' : ''}</p><pre>${escapeHtml(content)}</pre>`);
        popup.document.close();
    } catch (error) {
        showToast(`Could not open arena artifact: ${error.message || error}`, true);
    }
}

function renderParallelArenaImpactPlan(run = {}) {
    const impact = run.impact_plan || null;
    if (!impact || !Array.isArray(impact.artifacts) || !impact.artifacts.length) return '';
    const artifacts = impact.artifacts.map((artifact) => `
        <button type="button" class="small secondary" onclick="openParallelArenaImpactPlanArtifact('${escapeHtml(run.run_id)}','${escapeHtml(artifact.name)}')">
            ${escapeHtml(artifact.label || artifact.file_name || artifact.name)} · ${escapeHtml(artifact.kind || 'text')} · ${escapeHtml(String(artifact.size_bytes || 0))}b
        </button>
    `).join('');
    const fileCount = Array.isArray(impact.candidate_files) ? impact.candidate_files.length : 0;
    const testCount = Array.isArray(impact.candidate_tests) ? impact.candidate_tests.length : 0;
    const commands = Array.isArray(impact.verification_commands) ? impact.verification_commands : [];
    return `
        <div class="card parallel-arena-impact-plan">
            <h3>Semantic Patch Impact Plan</h3>
            <p><strong>${escapeHtml(String(fileCount))}</strong> likely files · <strong>${escapeHtml(String(testCount))}</strong> candidate tests · ${escapeHtml((impact.terms || []).slice(0, 8).join(', ') || 'local semantic scan')}</p>
            <p class="message-meta">${escapeHtml(impact.next_action || 'Aim lanes at concrete source surfaces before editing.')}</p>
            ${commands.length ? `<details><summary>Suggested verification commands</summary><pre>${escapeHtml(commands.join('\n'))}</pre></details>` : ''}
            <div class="parallel-arena-artifact-buttons">${artifacts}</div>
        </div>
    `;
}

async function openParallelArenaImpactPlanArtifact(runId, artifactName) {
    try {
        const data = await fetchJsonOrThrow(`/api/parallel-arena/runs/${encodeURIComponent(runId)}/impact-plan/${encodeURIComponent(artifactName)}`);
        const artifact = data.artifact || {};
        const content = artifact.kind === 'json' && data.json ? JSON.stringify(data.json, null, 2) : (data.content || '');
        const popup = window.open('', '_blank', 'noopener,noreferrer,width=980,height=720');
        if (!popup) {
            showToast('Popup blocked; Impact Plan artifact could not open.', true);
            return;
        }
        popup.document.write(`<!doctype html><title>${escapeHtml(artifact.label || artifactName)}</title><style>body{font-family:system-ui;margin:24px;background:#111827;color:#e5e7eb}pre{white-space:pre-wrap;background:#020617;padding:16px;border-radius:12px;overflow:auto}.meta{color:#9ca3af}</style><h1>${escapeHtml(artifact.label || artifactName)}</h1><p class="meta">${escapeHtml(data.run_id)} · ${escapeHtml(artifact.file_name || '')}${data.truncated ? ' · truncated' : ''}</p><pre>${escapeHtml(content)}</pre>`);
        popup.document.close();
    } catch (error) {
        showToast(`Could not open Impact Plan artifact: ${error.message || error}`, true);
    }
}


function renderParallelArenaProviderAdvisor(advisor = null) {
    if (!advisor) return '';
    const candidates = Array.isArray(advisor.candidates) ? advisor.candidates.slice(0, 4) : [];
    const pills = candidates.map((item) => `
        <span class="meta-pill ${item.provider === advisor.recommended_provider ? 'success' : ''}">${escapeHtml(item.label || item.provider)} ${escapeHtml(String(item.score ?? '—'))}</span>
    `).join('');
    return `
        <div class="card parallel-arena-provider-advisor-card">
            <h3>Provider Choice Autopilot</h3>
            <p><strong>${escapeHtml(advisor.recommended_provider || 'local_worker')}</strong> · ${escapeHtml(advisor.recommended_execution_mode || 'local_worker')} · ${escapeHtml(advisor.adapter_status || 'ready')}</p>
            ${advisor.recommended_execution_mode === 'hermes_cli' ? '<p class="message-meta">Hermes CLI adapter is a real model-backed subprocess lane and stays blocked until both spend gates are enabled.</p>' : ''}
            <div class="parallel-arena-title-row">${pills}</div>
            <p class="message-meta">${escapeHtml(advisor.next_action || 'Use the advisor before spending provider tokens.')}</p>
            <details><summary>Launch policy</summary><pre>${escapeHtml(JSON.stringify(advisor.launch_policy || {}, null, 2))}</pre></details>
        </div>
    `;
}

function collectParallelArenaLaunchInput() {
    const task = document.getElementById('parallel-arena-task')?.value?.trim() || '';
    const maxLanes = Number(document.getElementById('parallel-arena-lane-count')?.value || 3);
    const executionMode = document.getElementById('parallel-arena-execution-mode')?.value || 'local_worker';
    return { task, max_lanes: maxLanes, execution_mode: executionMode };
}

function displayParallelArenaProviderAdvisor(advisor = null) {
    const target = document.getElementById('parallel-arena-provider-advisor');
    if (!target) return;
    if (!advisor) {
        target.textContent = 'Provider Autopilot will recommend local vs provider-backed lanes before launch.';
        return;
    }
    const top = Array.isArray(advisor.candidates) && advisor.candidates.length ? advisor.candidates[0] : {};
    target.innerHTML = `
        <strong>Autopilot:</strong> ${escapeHtml(advisor.recommended_provider || 'local_worker')}
        · ${escapeHtml(advisor.adapter_status || 'ready')}
        · top score ${escapeHtml(String(top.score ?? '—'))}
        <br>${escapeHtml(advisor.next_action || '')}
    `;
}

async function refreshParallelArenaProviderAdvisor() {
    const input = collectParallelArenaLaunchInput();
    if (!input.task) {
        displayParallelArenaProviderAdvisor(null);
        showToast('Enter a task before asking Provider Autopilot.', true);
        return null;
    }
    try {
        const data = await fetchJsonOrThrow('/api/parallel-arena/provider-advisor', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(input),
        });
        displayParallelArenaProviderAdvisor(data.advisor);
        return data.advisor || null;
    } catch (error) {
        showToast(`Provider Autopilot failed: ${error.message || error}`, true);
        return null;
    }
}


function renderParallelArenaSkillForge(run = {}) {
    const forge = run.skill_forge || null;
    if (forge && Array.isArray(forge.artifacts) && forge.artifacts.length) {
        const artifacts = forge.artifacts.map((artifact) => `
            <button type="button" class="small secondary" onclick="openParallelArenaSkillForgeArtifact('${escapeHtml(run.run_id)}','${escapeHtml(artifact.name)}')">
                ${escapeHtml(artifact.label || artifact.file_name || artifact.name)} · ${escapeHtml(artifact.kind || 'text')} · ${escapeHtml(String(artifact.size_bytes || 0))}b
            </button>
        `).join('');
        return `
            <div class="card parallel-arena-skill-forge">
                <h3>Skill Forge Draft</h3>
                <p><strong>${escapeHtml(forge.skill_name || 'draft')}</strong> forged from ${escapeHtml(forge.source_lane_id || 'winner lane')}.</p>
                <p class="message-meta">${escapeHtml(forge.install_hint || 'Review artifacts before promoting this draft skill.')}</p>
                <div class="parallel-arena-artifact-buttons">${artifacts}</div>
            </div>
        `;
    }
    if (run.status === 'completed' && run.synthesis && run.synthesis.winner_lane_id) {
        return `
            <div class="card parallel-arena-skill-forge">
                <h3>Skill Forge</h3>
                <p>Convert the winning lane into a reviewable Hermes skill draft with SKILL.md, promotion manifest, and a test plan.</p>
                <button class="btn primary" type="button" onclick="forgeParallelArenaWinnerSkill('${escapeHtml(run.run_id)}')">Forge Winner Skill Draft</button>
            </div>
        `;
    }
    return '';
}

async function forgeParallelArenaWinnerSkill(runId) {
    if (!runId) return;
    try {
        const data = await fetchJsonOrThrow(`/api/parallel-arena/runs/${encodeURIComponent(runId)}/skill-forge`, { method: 'POST' });
        invalidateCache('/api/parallel-arena');
        renderParallelArena({ current: data.run, runs: data.runs || [data.run] });
        showToast(`Forged skill draft: ${data.promotion?.skill_name || 'draft'}`);
    } catch (error) {
        showToast(`Skill Forge failed: ${error.message || error}`, true);
    }
}

async function openParallelArenaSkillForgeArtifact(runId, artifactName) {
    try {
        const data = await fetchJsonOrThrow(`/api/parallel-arena/runs/${encodeURIComponent(runId)}/skill-forge/${encodeURIComponent(artifactName)}`);
        const artifact = data.artifact || {};
        const content = artifact.kind === 'json' && data.json ? JSON.stringify(data.json, null, 2) : (data.content || '');
        const popup = window.open('', '_blank', 'noopener,noreferrer,width=980,height=720');
        if (!popup) {
            showToast('Popup blocked; Skill Forge artifact could not open.', true);
            return;
        }
        popup.document.write(`<!doctype html><title>${escapeHtml(artifact.label || artifactName)}</title><style>body{font-family:system-ui;margin:24px;background:#111827;color:#e5e7eb}pre{white-space:pre-wrap;background:#020617;padding:16px;border-radius:12px;overflow:auto}.meta{color:#9ca3af}</style><h1>${escapeHtml(artifact.label || artifactName)}</h1><p class="meta">${escapeHtml(data.run_id)} · ${escapeHtml(artifact.file_name || '')}${data.truncated ? ' · truncated' : ''}</p><pre>${escapeHtml(content)}</pre>`);
        popup.document.close();
    } catch (error) {
        showToast(`Could not open Skill Forge artifact: ${error.message || error}`, true);
    }
}

function renderParallelArenaMissionPlan(run = {}) {
    const mission = run.mission_plan || null;
    if (mission && Array.isArray(mission.artifacts) && mission.artifacts.length) {
        const artifacts = mission.artifacts.map((artifact) => `
            <button type="button" class="small secondary" onclick="openParallelArenaMissionPlanArtifact('${escapeHtml(run.run_id)}','${escapeHtml(artifact.name)}')">
                ${escapeHtml(artifact.label || artifact.file_name || artifact.name)} · ${escapeHtml(artifact.kind || 'text')} · ${escapeHtml(String(artifact.size_bytes || 0))}b
            </button>
        `).join('');
        const nodeCount = Array.isArray(mission.nodes) ? mission.nodes.length : 0;
        const edgeCount = Array.isArray(mission.edges) ? mission.edges.length : 0;
        return `
            <div class="card parallel-arena-mission-plan">
                <h3>Mission Control DAG</h3>
                <p><strong>${escapeHtml(mission.mission_title || 'Mission plan')}</strong></p>
                <p class="message-meta">${escapeHtml(String(nodeCount))} nodes · ${escapeHtml(String(edgeCount))} edges · winner ${escapeHtml(mission.source_lane_id || 'lane')}</p>
                <p>${escapeHtml(mission.next_action || 'Review DAG artifacts before replaying the workflow.')}</p>
                <div class="parallel-arena-artifact-buttons">${artifacts}</div>
            </div>
        `;
    }
    if (run.status === 'completed' && run.synthesis && run.synthesis.winner_lane_id) {
        return `
            <div class="card parallel-arena-mission-plan">
                <h3>Mission Control</h3>
                <p>Compile the winning lane into a replayable campaign DAG with node prompts, dependencies, success metrics, and a mission brief.</p>
                <button class="btn primary" type="button" onclick="buildParallelArenaMissionPlan('${escapeHtml(run.run_id)}')">Build Mission DAG</button>
            </div>
        `;
    }
    return '';
}

async function buildParallelArenaMissionPlan(runId) {
    if (!runId) return;
    try {
        const data = await fetchJsonOrThrow(`/api/parallel-arena/runs/${encodeURIComponent(runId)}/mission-plan`, { method: 'POST' });
        invalidateCache('/api/parallel-arena');
        renderParallelArena({ current: data.run, runs: data.runs || [data.run] });
        showToast(`Built mission DAG: ${data.mission_plan?.mission_title || 'draft'}`);
    } catch (error) {
        showToast(`Mission DAG build failed: ${error.message || error}`, true);
    }
}

async function openParallelArenaMissionPlanArtifact(runId, artifactName) {
    try {
        const data = await fetchJsonOrThrow(`/api/parallel-arena/runs/${encodeURIComponent(runId)}/mission-plan/${encodeURIComponent(artifactName)}`);
        const artifact = data.artifact || {};
        const content = artifact.kind === 'json' && data.json ? JSON.stringify(data.json, null, 2) : (data.content || '');
        const popup = window.open('', '_blank', 'noopener,noreferrer,width=980,height=720');
        if (!popup) {
            showToast('Popup blocked; Mission DAG artifact could not open.', true);
            return;
        }
        popup.document.write(`<!doctype html><title>${escapeHtml(artifact.label || artifactName)}</title><style>body{font-family:system-ui;margin:24px;background:#111827;color:#e5e7eb}pre{white-space:pre-wrap;background:#020617;padding:16px;border-radius:12px;overflow:auto}.meta{color:#9ca3af}</style><h1>${escapeHtml(artifact.label || artifactName)}</h1><p class="meta">${escapeHtml(data.run_id)} · ${escapeHtml(artifact.file_name || '')}${data.truncated ? ' · truncated' : ''}</p><pre>${escapeHtml(content)}</pre>`);
        popup.document.close();
    } catch (error) {
        showToast(`Could not open Mission DAG artifact: ${error.message || error}`, true);
    }
}


function renderParallelArenaWorkflowReplay(run = {}) {
    const replay = run.workflow_replay || null;
    if (replay && Array.isArray(replay.artifacts) && replay.artifacts.length) {
        const artifacts = replay.artifacts.map((artifact) => `
            <button type="button" class="small secondary" onclick="openParallelArenaWorkflowReplayArtifact('${escapeHtml(run.run_id)}','${escapeHtml(artifact.name)}')">
                ${escapeHtml(artifact.label || artifact.file_name || artifact.name)} · ${escapeHtml(artifact.kind || 'text')} · ${escapeHtml(String(artifact.size_bytes || 0))}b
            </button>
        `).join('');
        const nodeCount = Array.isArray(replay.nodes) ? replay.nodes.length : 0;
        return `
            <div class="card parallel-arena-workflow-replay">
                <h3>Workflow Replay Bundle</h3>
                <p><strong>${escapeHtml(replay.schema_version || 'parallel_arena.workflow_replay.v1')}</strong> · ${escapeHtml(String(nodeCount))} executable nodes</p>
                <p class="message-meta">Read-only driver persisted under ${escapeHtml(replay.artifact_dir || 'the arena run directory')}.</p>
                <div class="parallel-arena-artifact-buttons">${artifacts}</div>
            </div>
        `;
    }
    if (run.status === 'completed' && run.synthesis && run.synthesis.winner_lane_id) {
        return `
            <div class="card parallel-arena-workflow-replay">
                <h3>Workflow Replay Studio</h3>
                <p>Export the winner + Mission DAG into a replayable workflow bundle with JSON nodes, an executable read-only replay driver, and operator commands.</p>
                <button class="btn primary" type="button" onclick="exportParallelArenaWorkflowReplay('${escapeHtml(run.run_id)}')">Export Replay Bundle</button>
            </div>
        `;
    }
    return '';
}

async function exportParallelArenaWorkflowReplay(runId) {
    if (!runId) return;
    try {
        const data = await fetchJsonOrThrow(`/api/parallel-arena/runs/${encodeURIComponent(runId)}/workflow-replay`, { method: 'POST' });
        invalidateCache('/api/parallel-arena');
        renderParallelArena({ current: data.run, runs: data.runs || [data.run] });
        showToast(`Exported replay bundle with ${data.workflow_replay?.nodes?.length || 0} nodes`);
    } catch (error) {
        showToast(`Workflow replay export failed: ${error.message || error}`, true);
    }
}

async function openParallelArenaWorkflowReplayArtifact(runId, artifactName) {
    try {
        const data = await fetchJsonOrThrow(`/api/parallel-arena/runs/${encodeURIComponent(runId)}/workflow-replay/${encodeURIComponent(artifactName)}`);
        const artifact = data.artifact || {};
        const content = artifact.kind === 'json' && data.json ? JSON.stringify(data.json, null, 2) : (data.content || '');
        const popup = window.open('', '_blank', 'noopener,noreferrer,width=980,height=720');
        if (!popup) {
            showToast('Popup blocked; Workflow Replay artifact could not open.', true);
            return;
        }
        popup.document.write(`<!doctype html><title>${escapeHtml(artifact.label || artifactName)}</title><style>body{font-family:system-ui;margin:24px;background:#111827;color:#e5e7eb}pre{white-space:pre-wrap;background:#020617;padding:16px;border-radius:12px;overflow:auto}.meta{color:#9ca3af}</style><h1>${escapeHtml(artifact.label || artifactName)}</h1><p class="meta">${escapeHtml(data.run_id)} · ${escapeHtml(artifact.file_name || '')}${data.truncated ? ' · truncated' : ''}</p><pre>${escapeHtml(content)}</pre>`);
        popup.document.close();
    } catch (error) {
        showToast(`Could not open Workflow Replay artifact: ${error.message || error}`, true);
    }
}


function renderParallelArenaCanaryHarness(run = {}) {
    const canary = run.canary_harness || null;
    if (canary && Array.isArray(canary.artifacts) && canary.artifacts.length) {
        const artifacts = canary.artifacts.map((artifact) => `
            <button type="button" class="small secondary" onclick="openParallelArenaCanaryHarnessArtifact('${escapeHtml(run.run_id)}','${escapeHtml(artifact.name)}')">
                ${escapeHtml(artifact.label || artifact.file_name || artifact.name)} · ${escapeHtml(artifact.kind || 'text')} · ${escapeHtml(String(artifact.size_bytes || 0))}b
            </button>
        `).join('');
        const requiredPasses = canary.promotion_gate && Array.isArray(canary.promotion_gate.required_passes) ? canary.promotion_gate.required_passes.join(', ') : 'schema-present, node-chain-ready, privacy-safe';
        return `
            <div class="card parallel-arena-canary-harness">
                <h3>Training Canary Harness</h3>
                <p><strong>${escapeHtml(canary.schema_version || 'parallel_arena.canary_harness.v1')}</strong> · ${escapeHtml(String(canary.node_count || 0))} replay nodes covered</p>
                <p class="message-meta">Promotion gate: ${escapeHtml(requiredPasses)} · ${escapeHtml(canary.promotion_gate?.pass_command || 'python3 canary_driver.py --json')}</p>
                <div class="parallel-arena-artifact-buttons">${artifacts}</div>
            </div>
        `;
    }
    if (run.workflow_replay && run.status === 'completed') {
        return `
            <div class="card parallel-arena-canary-harness">
                <h3>Training Episode Canary Harness</h3>
                <p>Compile the replay bundle into privacy-safe canaries that gate training/prompt/tool promotion episodes before they become reusable capability data.</p>
                <button class="btn primary" type="button" onclick="buildParallelArenaCanaryHarness('${escapeHtml(run.run_id)}')">Build Canary Harness</button>
            </div>
        `;
    }
    return '';
}

async function buildParallelArenaCanaryHarness(runId) {
    if (!runId) return;
    try {
        const data = await fetchJsonOrThrow(`/api/parallel-arena/runs/${encodeURIComponent(runId)}/canary-harness`, { method: 'POST' });
        invalidateCache('/api/parallel-arena');
        renderParallelArena({ current: data.run, runs: data.runs || [data.run] });
        showToast(`Built canary harness with ${data.canary_harness?.checks?.length || 0} checks`);
    } catch (error) {
        showToast(`Canary harness build failed: ${error.message || error}`, true);
    }
}

async function openParallelArenaCanaryHarnessArtifact(runId, artifactName) {
    try {
        const data = await fetchJsonOrThrow(`/api/parallel-arena/runs/${encodeURIComponent(runId)}/canary-harness/${encodeURIComponent(artifactName)}`);
        const artifact = data.artifact || {};
        const content = artifact.kind === 'json' && data.json ? JSON.stringify(data.json, null, 2) : (data.content || '');
        const popup = window.open('', '_blank', 'noopener,noreferrer,width=980,height=720');
        if (!popup) {
            showToast('Popup blocked; Canary harness artifact could not open.', true);
            return;
        }
        popup.document.write(`<!doctype html><title>${escapeHtml(artifact.label || artifactName)}</title><style>body{font-family:system-ui;margin:24px;background:#111827;color:#e5e7eb}pre{white-space:pre-wrap;background:#020617;padding:16px;border-radius:12px;overflow:auto}.meta{color:#9ca3af}</style><h1>${escapeHtml(artifact.label || artifactName)}</h1><p class="meta">${escapeHtml(data.run_id)} · ${escapeHtml(artifact.file_name || '')}${data.truncated ? ' · truncated' : ''}</p><pre>${escapeHtml(content)}</pre>`);
        popup.document.close();
    } catch (error) {
        showToast(`Could not open Canary harness artifact: ${error.message || error}`, true);
    }
}


function renderParallelArenaDemoReel(run = {}) {
    const demo = run.demo_reel || null;
    if (demo && Array.isArray(demo.artifacts) && demo.artifacts.length) {
        const artifacts = demo.artifacts.map((artifact) => `
            <button type="button" class="small secondary" onclick="openParallelArenaDemoReelArtifact('${escapeHtml(run.run_id)}','${escapeHtml(artifact.name)}')">
                ${escapeHtml(artifact.label || artifact.file_name || artifact.name)} · ${escapeHtml(artifact.kind || 'text')} · ${escapeHtml(String(artifact.size_bytes || 0))}b
            </button>
        `).join('');
        const cards = Array.isArray(demo.cards) ? demo.cards.map((card) => `
            <span class="meta-pill success">${escapeHtml(card.label || 'metric')}: ${escapeHtml(String(card.value ?? '—'))}</span>
        `).join('') : '';
        return `
            <div class="card parallel-arena-demo-reel">
                <h3>Demo Reel</h3>
                <p><strong>${escapeHtml(demo.headline || 'Arena run packaged into a shareable capability demo.')}</strong></p>
                <div class="parallel-arena-title-row">${cards}</div>
                <p class="message-meta">${escapeHtml(demo.next_action || 'Open the demo reel artifact and decide whether to promote.')}</p>
                <div class="parallel-arena-artifact-buttons">${artifacts}</div>
            </div>
        `;
    }
    if (run.canary_harness && run.status === 'completed') {
        return `
            <div class="card parallel-arena-demo-reel">
                <h3>Demo Reel</h3>
                <p>Turn this canary-gated arena chain into a punchy, shareable brag sheet with scoreboard, artifact trail, privacy posture, and next action.</p>
                <button class="btn primary" type="button" onclick="buildParallelArenaDemoReel('${escapeHtml(run.run_id)}')">Build Demo Reel</button>
            </div>
        `;
    }
    return '';
}

async function buildParallelArenaDemoReel(runId) {
    if (!runId) return;
    try {
        const data = await fetchJsonOrThrow(`/api/parallel-arena/runs/${encodeURIComponent(runId)}/demo-reel`, { method: 'POST' });
        invalidateCache('/api/parallel-arena');
        renderParallelArena({ current: data.run, runs: data.runs || [data.run] });
        showToast('Built Parallel Arena demo reel');
    } catch (error) {
        showToast(`Demo reel build failed: ${error.message || error}`, true);
    }
}

async function openParallelArenaDemoReelArtifact(runId, artifactName) {
    try {
        const data = await fetchJsonOrThrow(`/api/parallel-arena/runs/${encodeURIComponent(runId)}/demo-reel/${encodeURIComponent(artifactName)}`);
        const artifact = data.artifact || {};
        const content = artifact.kind === 'json' && data.json ? JSON.stringify(data.json, null, 2) : (data.content || '');
        const popup = window.open('', '_blank', 'noopener,noreferrer,width=980,height=720');
        if (!popup) {
            showToast('Popup blocked; Demo Reel artifact could not open.', true);
            return;
        }
        popup.document.write(`<!doctype html><title>${escapeHtml(artifact.label || artifactName)}</title><style>body{font-family:system-ui;margin:24px;background:#111827;color:#e5e7eb}pre{white-space:pre-wrap;background:#020617;padding:16px;border-radius:12px;overflow:auto}.meta{color:#9ca3af}</style><h1>${escapeHtml(artifact.label || artifactName)}</h1><p class="meta">${escapeHtml(data.run_id)} · ${escapeHtml(artifact.file_name || '')}${data.truncated ? ' · truncated' : ''}</p><pre>${escapeHtml(content)}</pre>`);
        popup.document.close();
    } catch (error) {
        showToast(`Could not open Demo Reel artifact: ${error.message || error}`, true);
    }
}


function renderParallelArena(data = {}) {
    const current = data.current || null;
    const summaryEl = document.getElementById('parallel-arena-summary');
    const lanesEl = document.getElementById('parallel-arena-lanes');
    const synthesisEl = document.getElementById('parallel-arena-synthesis');
    const historyEl = document.getElementById('parallel-arena-history');
    const cancelBtn = document.getElementById('parallel-arena-cancel-btn');
    parallelArenaActiveRunId = current && current.run_id ? current.run_id : null;
    if (cancelBtn) cancelBtn.disabled = !current || !['queued', 'running'].includes(current.status);
    if (summaryEl) {
        if (!current) {
            summaryEl.textContent = 'No arena launched yet.';
        } else {
            summaryEl.innerHTML = `
                <div class="parallel-arena-title-row"><strong>${escapeHtml(current.title || 'Untitled arena')}</strong><span class="meta-pill ${parallelArenaStatusClass(current.status)}">${escapeHtml(current.status)}</span></div>
                <p>${escapeHtml(current.task || '')}</p>
                <div class="message-meta">Run ${escapeHtml(current.run_id)} · ${escapeHtml(current.execution_mode || 'simulated')} · ${escapeHtml(String(current.completed_lanes || 0))}/${escapeHtml(String(current.lane_count || 0))} lanes complete · ${escapeHtml(String(current.duration_ms || 0))}ms</div>
                ${current.run_dir || current.artifact_dir ? `<div class="message-meta">Artifacts: ${escapeHtml(current.run_dir || current.artifact_dir)}</div>` : ''}
            `;
        }
    }
    if (lanesEl) {
        const lanes = current && Array.isArray(current.lanes) ? current.lanes : [];
        lanesEl.innerHTML = lanes.length ? lanes.map((lane) => `
            <div class="parallel-arena-lane card">
                <div class="parallel-arena-lane-head"><strong>${escapeHtml(lane.name || lane.strategy || lane.lane_id)}</strong><span class="meta-pill ${parallelArenaStatusClass(lane.status)}">${escapeHtml(lane.status)}</span></div>
                <div class="parallel-arena-score">${escapeHtml(lane.execution_mode || 'simulated')} · Score ${escapeHtml(String(lane.score ?? '—'))} · ${escapeHtml(String(lane.duration_ms || 0))}ms</div>
                <p>${escapeHtml(lane.summary || 'Waiting for lane artifact…')}</p>
                ${renderParallelArenaArtifactButtons(current.run_id, lane)}
                <details><summary>Raw artifact manifest</summary><pre>${escapeHtml(JSON.stringify(lane.artifacts || {}, null, 2))}</pre></details>
            </div>
        `).join('') : '<p class="message-meta">Lanes will appear after launch.</p>';
    }
    if (synthesisEl) {
        const synthesis = current && current.synthesis ? current.synthesis : null;
        synthesisEl.innerHTML = synthesis ? `
            <div class="card parallel-arena-winner"><h3>Synthesis</h3><p><strong>Winner:</strong> ${escapeHtml(synthesis.winner_lane_id || 'pending')}</p><p>${escapeHtml(synthesis.rationale || '')}</p></div>
            ${renderParallelArenaProviderAdvisor(current.provider_advisor)}
            ${renderParallelArenaImpactPlan(current)}
            ${renderParallelArenaMissionPlan(current)}
            ${renderParallelArenaWorkflowReplay(current)}
            ${renderParallelArenaCanaryHarness(current)}
            ${renderParallelArenaDemoReel(current)}
            ${renderParallelArenaSkillForge(current)}
        ` : '';
    }
    if (historyEl) {
        const runs = Array.isArray(data.runs) ? data.runs : [];
        historyEl.innerHTML = runs.length ? runs.map((run) => `
            <button class="parallel-arena-history-row" type="button" onclick="loadParallelArenaRun('${escapeHtml(run.run_id)}')">
                <span>${escapeHtml(run.title || run.run_id)}</span><span>${escapeHtml(run.status)} · ${escapeHtml(String(run.lane_count || 0))} lanes</span>
            </button>
        `).join('') : '<p class="message-meta">No arena runs yet.</p>';
    }
}

async function loadParallelArena(force = false) {
    try {
        const data = force ? await fetchJsonOrThrow('/api/parallel-arena') : await cachedFetch('/api/parallel-arena', 3000);
        renderParallelArena(data);
        if (data.current && ['queued', 'running'].includes(data.current.status)) {
            setTimeout(() => loadParallelArena(true), 1800);
        }
    } catch (error) {
        const summaryEl = document.getElementById('parallel-arena-summary');
        if (summaryEl) summaryEl.textContent = `Parallel Arena failed to load: ${error.message || error}`;
    }
}

async function loadParallelArenaRun(runId) {
    try {
        const data = await fetchJsonOrThrow(`/api/parallel-arena/runs/${encodeURIComponent(runId)}`);
        renderParallelArena({ current: data.run, runs: data.runs || [data.run] });
    } catch (error) {
        showToast(`Could not load arena: ${error.message || error}`, true);
    }
}

async function startParallelArenaRun() {
    const launchInput = collectParallelArenaLaunchInput();
    const task = launchInput.task;
    const strategiesRaw = document.getElementById('parallel-arena-strategies')?.value || '';
    const maxLanes = launchInput.max_lanes;
    const executionMode = launchInput.execution_mode;
    const startBtn = document.getElementById('parallel-arena-start-btn');
    if (!task) {
        showToast('Parallel Arena needs a task.', true);
        return;
    }
    if (startBtn) startBtn.disabled = true;
    try {
        const strategies = strategiesRaw.split('\n').map(s => s.trim()).filter(Boolean).slice(0, Math.max(1, Math.min(8, maxLanes || 3)));
        const data = await fetchJsonOrThrow('/api/parallel-arena/runs', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ task, strategies, max_lanes: maxLanes, execution_mode: executionMode }),
        });
        invalidateCache('/api/parallel-arena');
        renderParallelArena({ current: data.run, runs: data.runs || [data.run] });
        showToast(`Parallel Arena started with ${data.run.lane_count} lanes`);
        setTimeout(() => loadParallelArena(true), 900);
    } catch (error) {
        showToast(`Could not start arena: ${error.message || error}`, true);
    } finally {
        if (startBtn) startBtn.disabled = false;
    }
}

async function cancelParallelArenaRun() {
    if (!parallelArenaActiveRunId) return;
    try {
        const data = await fetchJsonOrThrow(`/api/parallel-arena/runs/${encodeURIComponent(parallelArenaActiveRunId)}/cancel`, { method: 'POST' });
        invalidateCache('/api/parallel-arena');
        renderParallelArena({ current: data.run, runs: data.runs || [data.run] });
        showToast('Parallel Arena cancellation requested');
    } catch (error) {
        showToast(`Could not cancel arena: ${error.message || error}`, true);
    }
}

let dashboardChatSocket = null;
let dashboardChatJoined = false;
let dashboardChatActiveTarget = '#hermesdashboard';

function appendDashboardChatLog(text, className = '') {
    const logEl = document.getElementById('dashboard-chat-log');
    if (!logEl) return;
    const row = document.createElement('div');
    row.className = className ? `dashboard-chat-log-row ${className}` : 'dashboard-chat-log-row';
    row.textContent = text;
    logEl.appendChild(row);
    logEl.scrollTop = logEl.scrollHeight;
}

function renderDashboardChatStatus(data = {}) {
    const statusEl = document.getElementById('dashboard-chat-status');
    if (statusEl) {
        const hosts = (data.hosts || []).join(', ') || 'not configured';
        statusEl.innerHTML = `
            <div><strong>Status:</strong> ${data.enabled ? 'enabled' : 'disabled'} · ${data.connected ? 'connected' : 'disconnected'}</div>
            <div><strong>Channel:</strong> ${escapeHtml(data.channel || '#hermesdashboard')}</div>
            <div><strong>Hosts:</strong> ${escapeHtml(hosts)} · <strong>Port:</strong> ${escapeHtml(String(data.port || ''))} · <strong>TLS:</strong> ${data.tls ? 'yes' : 'no'}</div>
            <div><strong>Privacy identity:</strong> ${escapeHtml(data.default_nick_prefix || 'HermesDash')}* / ${escapeHtml(data.ident || 'hermesdash')} / ${escapeHtml(data.realname || 'Hermes Dashboard')}</div>
            <div><strong>Channel key:</strong> ${data.channel_key_configured ? 'configured' : 'not configured'} · <strong>Policy:</strong> ${escapeHtml(data.jail || '')}</div>
        `;
    }
    const connectBtn = document.getElementById('dashboard-chat-connect-btn');
    if (connectBtn) connectBtn.disabled = !data.enabled || !(data.hosts || []).length;
}

function hydrateDashboardChatSettings(status = {}) {
    const cfg = settingsData?.config?.dashboard_chat || {};
    const setValue = (id, value) => {
        const el = document.getElementById(id);
        if (el) el.value = value;
    };
    setValue('dashboard-chat-enabled', String(Boolean(cfg.enabled)));
    setValue('dashboard-chat-hosts', Array.isArray(cfg.hosts) ? cfg.hosts.join(',') : ((status.hosts || []).join(',') || ''));
    setValue('dashboard-chat-port', String(cfg.port || status.port || 6697));
    setValue('dashboard-chat-tls', String(cfg.tls ?? status.tls ?? true));
    setValue('dashboard-chat-nick-prefix', cfg.default_nick_prefix || status.default_nick_prefix || 'HermesDash');
    setValue('dashboard-chat-ident', cfg.ident || status.ident || 'hermesdash');
    setValue('dashboard-chat-realname', cfg.realname || status.realname || 'Hermes Dashboard');
}

async function loadDashboardChat(force = false) {
    if (force) invalidateCache('/api/dashboard-chat/status');
    const status = force ? await fetchJsonOrThrow('/api/dashboard-chat/status') : await cachedFetch('/api/dashboard-chat/status', 10000);
    renderDashboardChatStatus(status);
    if (!settingsData) {
        settingsData = await cachedFetch('/api/settings', 15000);
    }
    hydrateDashboardChatSettings(status);
    appendDashboardChatLog(status.enabled ? 'Dashboard Chat is enabled. Connect when ready.' : 'Dashboard Chat is disabled. Enable it in settings to connect.', status.enabled ? 'info' : 'warn');
    return status;
}

async function saveDashboardChatSettings() {
    const key = getElementValue('dashboard-chat-channel-key', '').trim();
    const updates = {
        'dashboard_chat.enabled': getBooleanSelectValue('dashboard-chat-enabled', false),
        'dashboard_chat.hosts': getElementValue('dashboard-chat-hosts', '').split(',').map(item => item.trim()).filter(Boolean),
        'dashboard_chat.port': getNumberValue('dashboard-chat-port', 6697),
        'dashboard_chat.tls': getBooleanSelectValue('dashboard-chat-tls', true),
        'dashboard_chat.default_nick_prefix': getElementValue('dashboard-chat-nick-prefix', 'HermesDash').trim(),
        'dashboard_chat.ident': getElementValue('dashboard-chat-ident', 'hermesdash').trim(),
        'dashboard_chat.realname': getElementValue('dashboard-chat-realname', 'Hermes Dashboard').trim(),
    };
    if (key) updates['dashboard_chat.channel_key'] = key;
    await postConfigUpdates(updates, 'Dashboard Chat / IRC settings saved');
    const keyEl = document.getElementById('dashboard-chat-channel-key');
    if (keyEl) keyEl.value = '';
    await loadDashboardChat(true);
}

function selectDashboardChatTarget(target) {
    dashboardChatActiveTarget = target || '#hermesdashboard';
    const targetsEl = document.getElementById('dashboard-chat-targets');
    if (!targetsEl) return;
    targetsEl.querySelectorAll('.dashboard-chat-tab').forEach(item => {
        const active = item.dataset.target === dashboardChatActiveTarget;
        item.classList.toggle('active', active);
        if (active) item.classList.remove('blink');
    });
}

function ensureDashboardChatPmTab(name, options = {}) {
    const target = name === 'self' ? 'self' : String(name || '').trim();
    if (!target) return null;
    const targetsEl = document.getElementById('dashboard-chat-targets');
    if (!targetsEl) return null;
    let tab = targetsEl.querySelector(`[data-target="${CSS.escape(target)}"]`);
    if (!tab) {
        tab = document.createElement('button');
        tab.type = 'button';
        tab.className = 'dashboard-chat-tab blink';
        tab.dataset.target = target;
        tab.textContent = target === 'self' ? 'PM yourself' : `PM ${target}`;
        tab.onclick = () => openDashboardChatPmTab(target);
        targetsEl.appendChild(tab);
    } else if (options.blink && dashboardChatActiveTarget !== target) {
        tab.classList.add('blink');
    }
    return tab;
}

function openDashboardChatPmTab(name) {
    const tab = ensureDashboardChatPmTab(name);
    if (!tab) return;
    selectDashboardChatTarget(tab.dataset.target);
}

function noteDashboardChatPmActivity(name) {
    ensureDashboardChatPmTab(name, { blink: true });
}

function connectDashboardChat() {
    if (dashboardChatSocket && dashboardChatSocket.readyState === WebSocket.OPEN) return;
    dashboardChatSocket = new WebSocket((location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/api/dashboard-chat/ws');
    appendDashboardChatLog('Opening Dashboard Chat websocket and requesting IRC bridge connection.', 'info');
    dashboardChatSocket.onmessage = (event) => {
        let data = {};
        try { data = JSON.parse(event.data); } catch (error) { data = { type: 'raw', text: event.data }; }
        if (data.status === 'joined') dashboardChatJoined = true;
        if (data.type === 'message' || data.type === 'notice') appendDashboardChatLog(`${data.private ? 'PM ' : ''}${data.from || '?'}: ${data.text || ''}`);
        else appendDashboardChatLog(data.text || data.status || data.type || 'event', data.type === 'error' ? 'error' : 'info');
        if (data.from && data.from !== 'self') noteDashboardChatPmActivity(data.from);
    };
    dashboardChatSocket.onclose = () => appendDashboardChatLog('Dashboard Chat disconnected.', 'warn');
    dashboardChatSocket.onerror = () => appendDashboardChatLog('Dashboard Chat websocket error.', 'error');
}

function disconnectDashboardChat() {
    if (dashboardChatSocket) dashboardChatSocket.close();
    dashboardChatSocket = null;
    dashboardChatJoined = false;
}

function sendDashboardChatMessage() {
    const input = document.getElementById('dashboard-chat-message');
    const text = (input?.value || '').trim();
    if (!text || !dashboardChatSocket || dashboardChatSocket.readyState !== WebSocket.OPEN) return;
    const target = dashboardChatActiveTarget || '#hermesdashboard';
    if (target === '#hermesdashboard') {
        if (!dashboardChatJoined) {
            appendDashboardChatLog('Wait for the server-confirmed #hermesdashboard join before sending.', 'warn');
            return;
        }
        dashboardChatSocket.send(JSON.stringify({ type: 'say', text }));
    } else if (target === 'self') {
        dashboardChatSocket.send(JSON.stringify({ type: 'selfpm', text }));
    } else {
        dashboardChatSocket.send(JSON.stringify({ type: 'pm', target, text }));
    }
    if (input) input.value = '';
}

let messageBoardSelectedPostId = null;

function formatMessageBoardDate(value) {
    if (!value) return '';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleString();
}

function renderMessageBoardList(posts = []) {
    const list = document.getElementById('message-board-list');
    if (!list) return;
    if (!posts.length) {
        list.innerHTML = '<div style="color:var(--text-dim);">No posts yet. Start the first iteration thread.</div>';
        return;
    }
    list.innerHTML = posts.map(post => `
        <div class="message-board-post-card ${post.id === messageBoardSelectedPostId ? 'active' : ''}" onclick="loadMessageBoardPost('${encodeURIComponent(post.id)}')">
            <h4>${escapeHtml(post.title || 'Untitled')}</h4>
            <div class="message-board-meta">
                <span>${escapeHtml(post.status || 'open')}</span>
                <span>${escapeHtml(String(post.reply_count || 0))} replies</span>
                <span>${escapeHtml(formatMessageBoardDate(post.updated_at))}</span>
            </div>
            ${post.last_reply_preview ? `<p style="color:var(--text-dim);font-size:0.82rem;margin-top:0.45rem;">${escapeHtml(post.last_reply_preview)}</p>` : ''}
        </div>
    `).join('');
}

function renderMessageBoardThread(post) {
    const thread = document.getElementById('message-board-thread');
    if (!thread) return;
    if (!post) {
        thread.innerHTML = '<h3>Message Board</h3><p style="color:var(--text-dim);">Select a thread or create a new one. Replies stay scoped to that thread.</p>';
        return;
    }
    const messages = Array.isArray(post.messages) ? post.messages : [];
    thread.innerHTML = `
        <div style="display:flex;justify-content:space-between;gap:1rem;align-items:flex-start;flex-wrap:wrap;">
            <div>
                <h3>${escapeHtml(post.title || 'Untitled')}</h3>
                <div class="message-board-meta">
                    <span>${escapeHtml(post.author || 'mojo')}</span>
                    <span>${escapeHtml(post.status || 'open')}</span>
                    <span>${escapeHtml(formatMessageBoardDate(post.updated_at || post.created_at))}</span>
                </div>
            </div>
            <button class="btn" onclick="loadMessageBoardPosts()">Refresh</button>
        </div>
        ${messages.map(message => `
            <div class="message-board-message ${escapeHtml(message.role || '')}">
                <div class="message-board-meta" style="margin-bottom:0.45rem;">
                    <strong>${escapeHtml(message.author || message.role || 'unknown')}</strong>
                    <span>${escapeHtml(message.role || '')}</span>
                    <span>${escapeHtml(formatMessageBoardDate(message.created_at))}</span>
                </div>
                <div>${escapeHtml(message.content || '')}</div>
            </div>
        `).join('')}
        <form class="message-board-form" id="message-board-reply-form" onsubmit="submitMessageBoardReply(event)">
            <textarea id="message-board-reply-body" placeholder="Reply in this thread..." required></textarea>
            <div style="display:flex;gap:0.5rem;justify-content:flex-end;flex-wrap:wrap;">
                <button class="btn" id="message-board-reply-only" type="button" onclick="submitMessageBoardReply(event, false)">Post only</button>
                <button class="btn primary" id="message-board-reply-submit" type="submit">Post + ask Hermes</button>
            </div>
        </form>
    `;
}

async function loadMessageBoardPosts() {
    const data = await fetchJsonOrThrow('/api/message-board');
    const posts = data.posts || [];
    renderMessageBoardList(posts);
    if (!messageBoardSelectedPostId && posts.length) {
        await loadMessageBoardPost(encodeURIComponent(posts[0].id));
    }
    return posts;
}

async function loadMessageBoardPost(encodedPostId) {
    const postId = decodeURIComponent(encodedPostId || '');
    if (!postId) return;
    messageBoardSelectedPostId = postId;
    const post = await fetchJsonOrThrow(`/api/message-board/${encodeURIComponent(postId)}`);
    renderMessageBoardThread(post);
    await loadMessageBoardPosts();
}

async function submitMessageBoardPost(event) {
    event.preventDefault();
    const titleEl = document.getElementById('message-board-title');
    const bodyEl = document.getElementById('message-board-body');
    const submitEl = document.getElementById('message-board-submit');
    const title = titleEl?.value?.trim() || '';
    const body = bodyEl?.value?.trim() || '';
    if (!title || !body) {
        showToast('Title and body are required', 'error');
        return;
    }
    if (submitEl) {
        submitEl.disabled = true;
        submitEl.textContent = 'Posting...';
    }
    try {
        const post = await fetchJsonOrThrow('/api/message-board', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title, body, author: 'mojo' }),
        });
        messageBoardSelectedPostId = post.id;
        if (titleEl) titleEl.value = '';
        if (bodyEl) bodyEl.value = '';
        renderMessageBoardThread(post);
        await loadMessageBoardPosts();
        showToast('Posted to Hermes message board');
    } catch (error) {
        showToast(`Message board post failed: ${error.message}`, 'error');
    } finally {
        if (submitEl) {
            submitEl.disabled = false;
            submitEl.textContent = 'Start thread + ask Hermes';
        }
    }
}

async function submitMessageBoardReply(event, askAgent = true) {
    if (event && typeof event.preventDefault === 'function') event.preventDefault();
    if (!messageBoardSelectedPostId) {
        showToast('Select a thread first', 'error');
        return;
    }
    const bodyEl = document.getElementById('message-board-reply-body');
    const submitEl = document.getElementById('message-board-reply-submit');
    const onlyEl = document.getElementById('message-board-reply-only');
    const content = bodyEl?.value?.trim() || '';
    if (!content) {
        showToast('Reply content is required', 'error');
        return;
    }
    if (submitEl) {
        submitEl.disabled = true;
        submitEl.textContent = askAgent ? 'Asking Hermes...' : 'Posting...';
    }
    if (onlyEl) onlyEl.disabled = true;
    try {
        const post = await fetchJsonOrThrow(`/api/message-board/${encodeURIComponent(messageBoardSelectedPostId)}/messages`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content, author: 'mojo', ask_agent: askAgent }),
        });
        if (bodyEl) bodyEl.value = '';
        renderMessageBoardThread(post);
        await loadMessageBoardPosts();
        showToast(askAgent ? 'Posted and Hermes replied' : 'Reply posted');
    } catch (error) {
        showToast(`Message board reply failed: ${error.message}`, 'error');
    } finally {
        if (submitEl) {
            submitEl.disabled = false;
            submitEl.textContent = 'Post + ask Hermes';
        }
        if (onlyEl) onlyEl.disabled = false;
    }
}

function parseJsonField(id, fallback) {
    const value = document.getElementById(id)?.value?.trim();
    if (!value) return fallback;
    try {
        return JSON.parse(value);
    } catch (error) {
        throw new Error(`${id} contains invalid JSON: ${error.message}`);
    }
}

function getElementValue(id, fallback = '') {
    const element = document.getElementById(id);
    return element ? element.value : fallback;
}

function getBooleanSelectValue(id, fallback = false) {
    const value = getElementValue(id, String(fallback));
    return value === 'true';
}

function getNumberValue(id, fallback = 0) {
    const raw = getElementValue(id, String(fallback)).trim();
    if (!raw) return fallback;
    const parsed = Number(raw);
    if (!Number.isFinite(parsed)) {
        throw new Error(`${id} must be a valid number`);
    }
    return parsed;
}

async function postConfigUpdates(updates, successMessage) {
    await fetchJsonOrThrow('/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updates),
    });
    invalidateCache('/api/config');
    invalidateCache('/api/settings');
    await loadSettings(true);
    await loadStatus();
    showToast(successMessage);
}

function renderSecretTags(keys = []) {
    if (!settingsData || !Array.isArray(keys) || !keys.length) return '';
    const secretMap = new Map((settingsData.secrets || []).map(item => [item.key, item]));
    const tags = keys.map((key) => {
        const meta = secretMap.get(key);
        const configured = !!meta?.configured;
        const label = meta?.name || key;
        return `<span class="config-tag ${configured ? 'ok' : 'warn'}">${escapeHtml(label)} ${configured ? 'configured' : 'missing'}</span>`;
    });
    return tags.length ? `<div class="config-tags">${tags.join('')}</div>` : '';
}

function renderConfigOverview() {
    const el = document.getElementById('config-overview');
    if (!el || !settingsData) return;
    const overview = settingsData.overview || {};
    const byCategory = overview.secrets_by_category || {};
    const secretSummary = Object.entries(byCategory)
        .map(([key, value]) => `${key}: ${value.configured}/${value.total}`)
        .join(' · ');
    el.innerHTML = `
        <div class="overview-stat"><span class="label">Profile Home</span><span class="value">${escapeHtml(overview.profile_home || '--')}</span></div>
        <div class="overview-stat"><span class="label">Config Version</span><span class="value">${escapeHtml(String(overview.config_version ?? '--'))}</span></div>
        <div class="overview-stat"><span class="label">Changed Values</span><span class="value">${escapeHtml(String(overview.changed_count ?? 0))}</span></div>
        <div class="overview-stat"><span class="label">Configured Secrets</span><span class="value">${escapeHtml(String(overview.configured_secrets_count ?? 0))}</span></div>
        <div class="overview-stat"><span class="label">Missing Secrets</span><span class="value">${escapeHtml(String(overview.missing_secrets_count ?? 0))}</span></div>
        <div class="overview-stat"><span class="label">Secret Coverage</span><span class="value">${escapeHtml(secretSummary || 'No secret metadata')}</span></div>
    `;
}

function renderToolsetCheckboxes(platformKey, selected, extras = []) {
    const toolsets = settingsData?.toolsets || [];
    return `<div class="checkbox-list">${toolsets.map((toolset) => `
        <label class="check-item">
            <input type="checkbox" data-platform-toolset="${escapeHtml(platformKey)}" value="${escapeHtml(toolset.key)}" ${selected.includes(toolset.key) ? 'checked' : ''}>
            <div>
                <strong>${toolset.label}</strong>
                <small>${escapeHtml(toolset.description || toolset.key)}</small>
            </div>
        </label>
    `).join('')}</div>${extras.length ? `<div class="config-help" style="margin-top:0.7rem;">Preserved custom entries: ${extras.map(escapeHtml).join(', ')}</div>` : ''}`;
}

function renderConfigSections() {
    const el = document.getElementById('config-sections');
    if (!el || !settingsData) return;
    const cfg = settingsData.config || {};
    const model = settingsData.model || {};
    const personality = settingsData.personality || {};
    const memory = cfg.memory || {};
    const display = cfg.display || {};
    const browser = cfg.browser || {};
    const tts = cfg.tts || {};
    const stt = cfg.stt || {};
    const voice = cfg.voice || {};
    const skills = cfg.skills || {};
    const smart = cfg.smart_model_routing || {};
    const sessionReset = cfg.session_reset || {};
    const platforms = (settingsData.platforms || []).filter(p => ['cli','api_server','telegram','discord','slack','whatsapp','signal','homeassistant'].includes(p.key));
    const personalityOptions = (personality.built_in || []).map(p => `<option value="${escapeHtml(p)}" ${p === personality.current ? 'selected' : ''}>${escapeHtml(p)}</option>`).join('') + ((personality.custom || []).length ? `<optgroup label="Custom">${(personality.custom || []).map(p => `<option value="${escapeHtml(p)}" ${p === personality.current ? 'selected' : ''}>${escapeHtml(p)}</option>`).join('')}</optgroup>` : '');

    el.innerHTML = `
        <section class="config-section">
            <div class="config-section-header">
                <div>
                    <h3>Model & Routing</h3>
                    <p>Primary model/provider, base URL override, smart routing, fallbacks, and advanced auxiliary/delegation model slots.</p>
                    ${renderSecretTags(['OPENROUTER_API_KEY','GLM_API_KEY','ZAI_API_KEY','OPENAI_API_KEY','KIMI_API_KEY','ANTHROPIC_API_KEY'])}
                </div>
            </div>
            <div class="config-fields">
                <div class="config-field"><label>Provider</label><select id="provider-select">${(models.providers || []).map(provider => `<option value="${escapeHtml(provider.id)}" ${provider.id === (model.provider || 'auto') ? 'selected' : ''}>${escapeHtml(provider.name)}</option>`).join('')}</select></div>
                <div class="config-field"><label>Model</label><select id="model-select"></select></div>
                <div class="config-field full"><label>Base URL Override</label><input type="text" id="model-base-url" value="${escapeHtml(model.base_url || '')}" placeholder="https://api.z.ai/api/paas/v4"></div>
                <div class="config-field full"><label>Fallback Providers JSON</label><textarea id="fallback-providers-json" spellcheck="false">${escapeHtml(JSON.stringify(cfg.fallback_providers || [], null, 2))}</textarea></div>
                <div class="config-field full"><label>Provider Routing JSON</label><textarea id="provider-routing-json" spellcheck="false">${escapeHtml(JSON.stringify(cfg.provider_routing || {}, null, 2))}</textarea></div>
                <div class="config-field"><label>Smart Routing</label><select id="smart-routing-enabled"><option value="true" ${smart.enabled ? 'selected' : ''}>Enabled</option><option value="false" ${!smart.enabled ? 'selected' : ''}>Disabled</option></select></div>
                <div class="config-field"><label>Max Simple Chars</label><input type="number" id="smart-routing-max-chars" min="1" value="${escapeHtml(String(smart.max_simple_chars ?? 160))}"></div>
                <div class="config-field"><label>Max Simple Words</label><input type="number" id="smart-routing-max-words" min="1" value="${escapeHtml(String(smart.max_simple_words ?? 28))}"></div>
                <div class="config-field full"><label>Cheap Model JSON</label><textarea id="smart-routing-cheap-model-json" spellcheck="false">${escapeHtml(JSON.stringify(smart.cheap_model || {}, null, 2))}</textarea></div>
                <div class="config-field full"><label>Auxiliary Models JSON</label><textarea id="auxiliary-json" spellcheck="false">${escapeHtml(JSON.stringify(cfg.auxiliary || {}, null, 2))}</textarea></div>
                <div class="config-field full"><label>Delegation JSON</label><textarea id="delegation-json" spellcheck="false">${escapeHtml(JSON.stringify(cfg.delegation || {}, null, 2))}</textarea></div>
            </div>
            <div class="section-actions"><button class="btn primary" onclick="saveModelRoutingSettings()">Save Model & Routing</button></div>
        </section>

        <section class="config-section">
            <div class="config-section-header"><div><h3>Agent & Personality</h3><p>Current personality, iteration budget, reasoning effort, and runtime custom personality definitions.</p></div></div>
            <div class="config-fields">
                <div class="config-field"><label>Personality</label><select id="personality-select">${personalityOptions}</select></div>
                <div class="config-field"><label>Max Turns</label><input type="number" id="max-turns" value="${escapeHtml(String((cfg.agent || {}).max_turns ?? 60))}" min="1" max="500"></div>
                <div class="config-field"><label>Reasoning Effort</label><select id="reasoning-effort">${(settingsData.reasoning_efforts || []).map(value => `<option value="${escapeHtml(value)}" ${(cfg.agent || {}).reasoning_effort === value ? 'selected' : ''}>${escapeHtml(value || 'default')}</option>`).join('')}</select></div>
                <div class="config-field"><label>Tool Use Enforcement</label><input type="text" id="tool-use-enforcement" value="${escapeHtml(String((cfg.agent || {}).tool_use_enforcement ?? 'auto'))}" placeholder="auto"></div>
                <div class="config-field"><label>Verbose</label><select id="agent-verbose"><option value="true" ${(cfg.agent || {}).verbose ? 'selected' : ''}>Enabled</option><option value="false" ${!(cfg.agent || {}).verbose ? 'selected' : ''}>Disabled</option></select></div>
                <div class="config-field full"><label>Custom Personalities JSON</label><textarea id="custom-personalities-json" spellcheck="false">${escapeHtml(JSON.stringify(personality.custom_definitions || {}, null, 2))}</textarea><div class="config-help">Stored under <code>agent.personalities</code>.</div></div>
            </div>
            <div class="section-actions"><button class="btn primary" onclick="saveAgentPersonalitySettings()">Save Agent Settings</button></div>
        </section>

        <section class="config-section">
            <div class="config-section-header"><div><h3>Memory & Session</h3><p>Memory limits, flush/nudge behavior, session reset policy, privacy, and profile-scoped session behavior.</p></div></div>
            <div class="config-fields">
                <div class="config-field"><label>Memory</label><select id="memory-enabled"><option value="true" ${memory.memory_enabled ? 'selected' : ''}>Enabled</option><option value="false" ${!memory.memory_enabled ? 'selected' : ''}>Disabled</option></select></div>
                <div class="config-field"><label>User Profile Memory</label><select id="user-profile-enabled"><option value="true" ${memory.user_profile_enabled ? 'selected' : ''}>Enabled</option><option value="false" ${!memory.user_profile_enabled ? 'selected' : ''}>Disabled</option></select></div>
                <div class="config-field"><label>Memory Char Limit</label><input type="number" id="memory-char-limit" min="0" value="${escapeHtml(String(memory.memory_char_limit ?? 22000))}"></div>
                <div class="config-field"><label>User Char Limit</label><input type="number" id="user-char-limit" min="0" value="${escapeHtml(String(memory.user_char_limit ?? 13750))}"></div>
                <div class="config-field"><label>Memory Nudge Interval</label><input type="number" id="memory-nudge-interval" min="0" value="${escapeHtml(String(memory.nudge_interval ?? 10))}"></div>
                <div class="config-field"><label>Flush Min Turns</label><input type="number" id="memory-flush-min-turns" min="0" value="${escapeHtml(String(memory.flush_min_turns ?? 6))}"></div>
                <div class="config-field"><label>Session Reset Mode</label><select id="session-reset-mode">${['both','idle','daily','none'].map(mode => `<option value="${mode}" ${mode === (sessionReset.mode || 'both') ? 'selected' : ''}>${mode}</option>`).join('')}</select></div>
                <div class="config-field"><label>Idle Minutes</label><input type="number" id="session-reset-idle" min="0" value="${escapeHtml(String(sessionReset.idle_minutes ?? 1440))}"></div>
                <div class="config-field"><label>Daily Reset Hour</label><input type="number" id="session-reset-hour" min="0" max="23" value="${escapeHtml(String(sessionReset.at_hour ?? 4))}"></div>
                <div class="config-field"><label>Group Sessions Per User</label><select id="group-sessions-per-user"><option value="true" ${(cfg.group_sessions_per_user ?? true) ? 'selected' : ''}>Enabled</option><option value="false" ${!(cfg.group_sessions_per_user ?? true) ? 'selected' : ''}>Disabled</option></select></div>
                <div class="config-field"><label>Redact PII</label><select id="privacy-redact-pii"><option value="true" ${(cfg.privacy || {}).redact_pii ? 'selected' : ''}>Enabled</option><option value="false" ${!(cfg.privacy || {}).redact_pii ? 'selected' : ''}>Disabled</option></select></div>
                <div class="config-field"><label>Timezone</label><input type="text" id="timezone" value="${escapeHtml(cfg.timezone || '')}" placeholder="America/New_York"></div>
                <div class="config-field full"><label>Prefill Messages File</label><input type="text" id="prefill-messages-file" value="${escapeHtml(cfg.prefill_messages_file || '')}" placeholder="/path/to/messages.json"></div>
            </div>
            <div class="section-actions"><button class="btn primary" onclick="saveMemorySessionSettings()">Save Memory & Session</button></div>
        </section>

        <section class="config-section">
            <div class="config-section-header"><div><h3>Tools & Skills</h3><p>Toolsets by platform plus skill behavior. Existing custom entries like MCP server names are preserved when saving.</p></div></div>
            <div class="config-fields">
                <div class="config-field"><label>Skill Creation Nudge Interval</label><input type="number" id="skills-creation-nudge" min="0" value="${escapeHtml(String(skills.creation_nudge_interval ?? 15))}"></div>
                <div class="config-field full"><label>Disabled Skills JSON</label><textarea id="skills-disabled-json" spellcheck="false">${escapeHtml(JSON.stringify(skills.disabled || [], null, 2))}</textarea></div>
                <div class="config-field full"><label>External Skill Dirs JSON</label><textarea id="skills-external-dirs-json" spellcheck="false">${escapeHtml(JSON.stringify(skills.external_dirs || [], null, 2))}</textarea></div>
            </div>
            <div class="advanced-editor" open>
                <summary>Platform Toolsets</summary>
                <div class="advanced-editor-body">
                    ${platforms.map(platform => `<div><div class="subsection-title">${platform.label}</div>${renderToolsetCheckboxes(platform.key, (settingsData.resolved_platform_toolsets || {})[platform.key] || [], (settingsData.platform_toolset_extras || {})[platform.key] || [])}</div>`).join('')}
                </div>
            </div>
            <div class="section-actions"><button class="btn primary" onclick="saveToolsSkillsSettings()">Save Tools & Skills</button></div>
        </section>

        <section class="config-section">
            <div class="config-section-header"><div><h3>Browser / Web / Voice</h3><p>Browser behavior, web backend, STT/TTS providers, and voice interaction defaults.</p>${renderSecretTags(['FIRECRAWL_API_KEY','EXA_API_KEY','PARALLEL_API_KEY','TAVILY_API_KEY','BROWSERBASE_API_KEY','BROWSER_USE_API_KEY','CAMOFOX_URL','ELEVENLABS_API_KEY','VOICE_TOOLS_OPENAI_KEY','OPENAI_API_KEY','GROQ_API_KEY'])}</div></div>
            <div class="config-fields">
                <div class="config-field"><label>Web Backend</label><select id="web-backend">${(settingsData.web_backends || []).map(value => `<option value="${value}" ${value === ((cfg.web || {}).backend || 'firecrawl') ? 'selected' : ''}>${value}</option>`).join('')}</select></div>
                <div class="config-field"><label>Browser Inactivity Timeout</label><input type="number" id="browser-inactivity-timeout" min="1" value="${escapeHtml(String(browser.inactivity_timeout ?? 120))}"></div>
                <div class="config-field"><label>Browser Command Timeout</label><input type="number" id="browser-command-timeout" min="1" value="${escapeHtml(String(browser.command_timeout ?? 30))}"></div>
                <div class="config-field"><label>Record Browser Sessions</label><select id="browser-record-sessions"><option value="true" ${browser.record_sessions ? 'selected' : ''}>Enabled</option><option value="false" ${!browser.record_sessions ? 'selected' : ''}>Disabled</option></select></div>
                <div class="config-field"><label>Allow Private URLs</label><select id="browser-allow-private-urls"><option value="true" ${browser.allow_private_urls ? 'selected' : ''}>Enabled</option><option value="false" ${!browser.allow_private_urls ? 'selected' : ''}>Disabled</option></select></div>
                <div class="config-field"><label>Camofox Managed Persistence</label><select id="browser-camofox-persistence"><option value="true" ${(browser.camofox || {}).managed_persistence ? 'selected' : ''}>Enabled</option><option value="false" ${!(browser.camofox || {}).managed_persistence ? 'selected' : ''}>Disabled</option></select></div>
                <div class="config-field"><label>TTS Provider</label><select id="tts-provider">${(settingsData.tts_providers || []).map(value => `<option value="${value}" ${value === (tts.provider || 'edge') ? 'selected' : ''}>${value}</option>`).join('')}</select></div>
                <div class="config-field"><label>STT Enabled</label><select id="stt-enabled"><option value="true" ${stt.enabled ? 'selected' : ''}>Enabled</option><option value="false" ${!stt.enabled ? 'selected' : ''}>Disabled</option></select></div>
                <div class="config-field"><label>STT Provider</label><select id="stt-provider">${(settingsData.stt_providers || []).map(value => `<option value="${value}" ${value === (stt.provider || 'local') ? 'selected' : ''}>${value}</option>`).join('')}</select></div>
                <div class="config-field"><label>Record Key</label><input type="text" id="voice-record-key" value="${escapeHtml(String(voice.record_key || 'ctrl+b'))}"></div>
                <div class="config-field"><label>Max Recording Seconds</label><input type="number" id="voice-max-recording" min="1" value="${escapeHtml(String(voice.max_recording_seconds ?? 120))}"></div>
                <div class="config-field"><label>Auto TTS</label><select id="voice-auto-tts"><option value="true" ${voice.auto_tts ? 'selected' : ''}>Enabled</option><option value="false" ${!voice.auto_tts ? 'selected' : ''}>Disabled</option></select></div>
                <div class="config-field"><label>Silence Threshold</label><input type="number" id="voice-silence-threshold" min="0" value="${escapeHtml(String(voice.silence_threshold ?? 200))}"></div>
                <div class="config-field"><label>Silence Duration</label><input type="number" step="0.1" id="voice-silence-duration" min="0" value="${escapeHtml(String(voice.silence_duration ?? 3))}"></div>
                <div class="config-field full"><label>TTS Config JSON</label><textarea id="tts-json" spellcheck="false">${escapeHtml(JSON.stringify(tts, null, 2))}</textarea></div>
                <div class="config-field full"><label>STT Config JSON</label><textarea id="stt-json" spellcheck="false">${escapeHtml(JSON.stringify(stt, null, 2))}</textarea></div>
            </div>
            <div class="section-actions"><button class="btn primary" onclick="saveBrowserVoiceSettings()">Save Browser / Voice</button></div>
        </section>

        <section class="config-section">
            <div class="config-section-header"><div><h3>Display & UX</h3><p>Display, reasoning, streaming, tool progress, and pacing settings that shape Hermes’ interactive behavior.</p></div></div>
            <div class="config-fields">
                <div class="config-field"><label>Compact UI</label><select id="display-compact"><option value="true" ${display.compact ? 'selected' : ''}>Enabled</option><option value="false" ${!display.compact ? 'selected' : ''}>Disabled</option></select></div>
                <div class="config-field"><label>Skin</label><select id="display-skin">${(settingsData.skins || []).map(item => `<option value="${escapeHtml(item.name)}" ${item.name === (display.skin || 'default') ? 'selected' : ''}>${escapeHtml(item.name)}${item.source === 'user' ? ' (user)' : ''}</option>`).join('')}</select></div>
                <div class="config-field"><label>Resume Display</label><select id="display-resume-display">${(settingsData.resume_display_modes || []).map(value => `<option value="${value}" ${value === (display.resume_display || 'full') ? 'selected' : ''}>${value}</option>`).join('')}</select></div>
                <div class="config-field"><label>Busy Input Mode</label><select id="display-busy-input-mode">${(settingsData.busy_input_modes || []).map(value => `<option value="${value}" ${value === (display.busy_input_mode || 'interrupt') ? 'selected' : ''}>${value}</option>`).join('')}</select></div>
                <div class="config-field"><label>Tool Progress</label><select id="display-tool-progress">${(settingsData.tool_progress_modes || []).map(value => `<option value="${value}" ${value === (display.tool_progress || 'all') ? 'selected' : ''}>${value}</option>`).join('')}</select></div>
                <div class="config-field"><label>Tool Preview Length</label><input type="number" id="display-tool-preview-length" min="0" value="${escapeHtml(String(display.tool_preview_length ?? 0))}"></div>
                <div class="config-field"><label>Show Reasoning</label><select id="display-show-reasoning"><option value="true" ${display.show_reasoning ? 'selected' : ''}>Enabled</option><option value="false" ${!display.show_reasoning ? 'selected' : ''}>Disabled</option></select></div>
                <div class="config-field"><label>Streaming</label><select id="display-streaming"><option value="true" ${display.streaming ? 'selected' : ''}>Enabled</option><option value="false" ${!display.streaming ? 'selected' : ''}>Disabled</option></select></div>
                <div class="config-field"><label>Inline Diffs</label><select id="display-inline-diffs"><option value="true" ${display.inline_diffs ? 'selected' : ''}>Enabled</option><option value="false" ${!display.inline_diffs ? 'selected' : ''}>Disabled</option></select></div>
                <div class="config-field"><label>Show Cost</label><select id="display-show-cost"><option value="true" ${display.show_cost ? 'selected' : ''}>Enabled</option><option value="false" ${!display.show_cost ? 'selected' : ''}>Disabled</option></select></div>
                <div class="config-field"><label>Background Notifications</label><select id="display-background-notifications">${(settingsData.background_notification_modes || []).map(value => `<option value="${value}" ${value === (display.background_process_notifications || 'all') ? 'selected' : ''}>${value}</option>`).join('')}</select></div>
                <div class="config-field"><label>Bell On Complete</label><select id="display-bell-on-complete"><option value="true" ${display.bell_on_complete ? 'selected' : ''}>Enabled</option><option value="false" ${!display.bell_on_complete ? 'selected' : ''}>Disabled</option></select></div>
                <div class="config-field"><label>Enable /verbose Command</label><select id="display-tool-progress-command"><option value="true" ${display.tool_progress_command ? 'selected' : ''}>Enabled</option><option value="false" ${!display.tool_progress_command ? 'selected' : ''}>Disabled</option></select></div>
                <div class="config-field"><label>Human Delay Mode</label><select id="human-delay-mode">${['off','natural','custom'].map(value => `<option value="${value}" ${value === ((cfg.human_delay || {}).mode || 'off') ? 'selected' : ''}>${value}</option>`).join('')}</select></div>
                <div class="config-field"><label>Human Delay Min (ms)</label><input type="number" id="human-delay-min" min="0" value="${escapeHtml(String((cfg.human_delay || {}).min_ms ?? 800))}"></div>
                <div class="config-field"><label>Human Delay Max (ms)</label><input type="number" id="human-delay-max" min="0" value="${escapeHtml(String((cfg.human_delay || {}).max_ms ?? 2500))}"></div>
            </div>
            <div class="section-actions"><button class="btn primary" onclick="saveDisplayUXSettings()">Save Display & UX</button></div>
        </section>

        <section class="config-section">
            <div class="config-section-header"><div><h3>Advanced Admin</h3><p>Raw JSON editors for the structurally complex groups that would otherwise be hidden from the dashboard.</p></div></div>
            <div class="config-fields">
                <div class="config-field full"><label>Terminal / Approvals JSON</label><textarea id="terminal-approvals-json" spellcheck="false">${escapeHtml(JSON.stringify({ terminal: cfg.terminal || {}, approvals: cfg.approvals || {}, command_allowlist: cfg.command_allowlist || [] }, null, 2))}</textarea></div>
                <div class="config-field full"><label>Security JSON</label><textarea id="security-json" spellcheck="false">${escapeHtml(JSON.stringify(cfg.security || {}, null, 2))}</textarea></div>
                <div class="config-field full"><label>Platform Behavior JSON</label><textarea id="platform-behavior-json" spellcheck="false">${escapeHtml(JSON.stringify({ discord: cfg.discord || {}, whatsapp: cfg.whatsapp || {}, streaming: cfg.streaming || {}, session_reset: cfg.session_reset || {}, group_sessions_per_user: cfg.group_sessions_per_user ?? true }, null, 2))}</textarea></div>
                <div class="config-field full"><label>MCP Servers JSON</label><textarea id="mcp-servers-json" spellcheck="false">${escapeHtml(JSON.stringify(cfg.mcp_servers || {}, null, 2))}</textarea></div>
                <div class="config-field full"><label>Cron / Quick Commands JSON</label><textarea id="cron-quick-json" spellcheck="false">${escapeHtml(JSON.stringify({ cron: cfg.cron || {}, quick_commands: cfg.quick_commands || {} }, null, 2))}</textarea></div>
            </div>
            <div class="section-actions"><button class="btn primary" onclick="saveAdvancedSettings()">Save Advanced JSON</button></div>
        </section>
    `;

    updateModelSelect(model.default || null);
}

async function loadSettings(force = false) {
    log('req', 'GET /api/settings');
    settingsData = force ? await fetchJsonOrThrow('/api/settings') : await cachedFetch('/api/settings', 15000);
    log('res', 'Loaded expanded config settings');
    renderConfigOverview();
    renderConfigSections();
}

function syncModelControls(statusData) {
    const providerSelect = document.getElementById('provider-select');
    const modelSelect = document.getElementById('model-select');
    if (!providerSelect || !modelSelect || !models?.providers) return;

    const activeProvider = statusData.provider || providerSelect.value;
    if (activeProvider && providerSelect.value !== activeProvider) {
        providerSelect.value = activeProvider;
    }

    updateModelSelect(statusData.model);
}

// Tab click handlers -> use hash navigation
document.querySelectorAll('.tab').forEach(tab => {
    tab.addEventListener('click', () => {
        navigateTo(tab.dataset.panel);
    });
});

// Listen for hash changes (browser back/forward) and close settings on outside click/Escape
document.addEventListener('click', (event) => {
    const executionSummary = event.target.closest?.('details[data-execution-segment-key] > summary');
    if (executionSummary) {
        const details = executionSummary.parentElement;
        setExecutionHistoryExpanded(details.getAttribute('data-execution-segment-key'), !details.open);
    }
    const toolToggle = event.target.closest?.('[data-tool-toggle]');
    if (toolToggle) {
        toggleToolCall(toolToggle.getAttribute('data-tool-toggle'));
        return;
    }
    const panelToggle = event.target.closest?.('[data-tool-panel-key]');
    if (panelToggle) {
        toggleToolPanel(
            panelToggle.getAttribute('data-tool-panel-key'),
            panelToggle.getAttribute('data-tool-panel-name'),
        );
        return;
    }
    const toolCopy = event.target.closest?.('[data-tool-copy-key]');
    if (toolCopy) {
        event.stopPropagation();
        copyToolPanelContent(toolCopy.getAttribute('data-tool-copy-key'), toolCopy.getAttribute('data-tool-copy-panel'), toolCopy);
        return;
    }
    const childRoute = event.target.closest?.('[data-session-route]');
    if (childRoute) {
        event.preventDefault();
        event.stopPropagation();
        navigateTo(childRoute.getAttribute('data-session-route'));
        return;
    }
    const minimizeChild = event.target.closest?.('[data-minimize-child-session]');
    if (minimizeChild) {
        event.preventDefault();
        event.stopPropagation();
        setSubagentWindowMinimized(minimizeChild.getAttribute('data-minimize-child-session'));
        return;
    }
    const closeChild = event.target.closest?.('[data-close-child-session]');
    if (closeChild) {
        closeChildSessionDrawer(closeChild.getAttribute('data-close-child-session'));
        return;
    }
    const wrapper = document.querySelector('.dashboard-settings-wrapper');
    if (wrapper && !wrapper.contains(event.target)) closeDashboardSettings();
});
document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') closeDashboardSettings();
});
window.addEventListener('hashchange', handleHashChange);

// Toast notifications
function showToast(message, error = false) {
    const toast = document.getElementById('toast');
    toast.textContent = message;
    toast.className = 'toast show' + (error ? ' error' : '');
    setTimeout(() => toast.classList.remove('show'), 3000);
}

// Load initial data
async function loadStatus() {
    log('req', 'GET /api/status');
    const resp = await fetch('/api/status');
    const data = await resp.json();
    log('res', `Status: model=${data.model}, personality=${data.personality}`);

    document.getElementById('current-model').textContent = data.model;
    document.getElementById('current-personality').textContent = `Personality: ${data.personality}`;
    const maxTurns = document.getElementById('max-turns');
    if (maxTurns) maxTurns.value = data.max_turns;
    const memoryEnabled = document.getElementById('memory-enabled');
    if (memoryEnabled) memoryEnabled.value = data.memory_enabled.toString();
    syncModelControls(data);
}

async function loadModels() {
    log('req', 'GET /api/models');
    const resp = await fetch('/api/models');
    models = await resp.json();
    log('res', `Loaded ${models.providers.length} providers`);
    updateModelSelect();
    await loadStatus();
}

function updateModelSelect(selectedModel = null) {
    const providerSelect = document.getElementById('provider-select');
    const modelSelect = document.getElementById('model-select');
    if (!providerSelect || !modelSelect || !models?.providers) return;
    const provider = providerSelect.value;
    const providerData = models.providers.find(p => p.id === provider);
    modelSelect.innerHTML = (providerData?.models || []).map(m =>
        `<option value="${m}">${m}</option>`
    ).join('');
    if (selectedModel && (providerData?.models || []).includes(selectedModel)) {
        modelSelect.value = selectedModel;
    } else if ((providerData?.models || []).length) {
        modelSelect.value = providerData.models[0];
    }
}

document.addEventListener('change', (event) => {
    if (event.target && event.target.id === 'provider-select') {
        updateModelSelect();
    }
});

function collectPlatformToolsets() {
    if (!settingsData) return {};
    const existing = { ...(settingsData.raw_config?.platform_toolsets || {}) };
    const extras = settingsData.platform_toolset_extras || {};
    const collected = {};
    Object.entries(existing).forEach(([platform, values]) => {
        if (Array.isArray(values)) {
            collected[platform] = [...values];
        }
    });
    document.querySelectorAll('[data-platform-toolset]').forEach((checkbox) => {
        const platform = checkbox.dataset.platformToolset;
        if (!platform) return;
        if (!Object.prototype.hasOwnProperty.call(collected, platform)) {
            collected[platform] = [];
        }
        if (checkbox.checked) collected[platform].push(checkbox.value);
    });
    Object.entries(extras).forEach(([platform, values]) => {
        if (!collected[platform]) collected[platform] = [];
        collected[platform].push(...values);
    });
    Object.keys(collected).forEach((platform) => {
        collected[platform] = Array.from(new Set(collected[platform])).sort();
    });
    return collected;
}

async function saveModelRoutingSettings() {
    const updates = {
        'model.provider': getElementValue('provider-select', 'auto'),
        'model.default': getElementValue('model-select', ''),
        'model.base_url': getElementValue('model-base-url', '').trim(),
        'fallback_providers': parseJsonField('fallback-providers-json', []),
        'provider_routing': parseJsonField('provider-routing-json', {}),
        'smart_model_routing.enabled': getBooleanSelectValue('smart-routing-enabled', false),
        'smart_model_routing.max_simple_chars': getNumberValue('smart-routing-max-chars', 160),
        'smart_model_routing.max_simple_words': getNumberValue('smart-routing-max-words', 28),
        'smart_model_routing.cheap_model': parseJsonField('smart-routing-cheap-model-json', {}),
        'auxiliary': parseJsonField('auxiliary-json', {}),
        'delegation': parseJsonField('delegation-json', {}),
    };
    await postConfigUpdates(updates, 'Model and routing saved');
}

async function saveAgentPersonalitySettings() {
    const updates = {
        'display.personality': getElementValue('personality-select', 'helpful'),
        'agent.max_turns': getNumberValue('max-turns', 60),
        'agent.reasoning_effort': getElementValue('reasoning-effort', ''),
        'agent.tool_use_enforcement': getElementValue('tool-use-enforcement', 'auto').trim(),
        'agent.verbose': getBooleanSelectValue('agent-verbose', false),
        'agent.personalities': parseJsonField('custom-personalities-json', {}),
    };
    await postConfigUpdates(updates, 'Agent settings saved');
}

async function saveMemorySessionSettings() {
    const updates = {
        'memory.memory_enabled': getBooleanSelectValue('memory-enabled', true),
        'memory.user_profile_enabled': getBooleanSelectValue('user-profile-enabled', true),
        'memory.memory_char_limit': getNumberValue('memory-char-limit', 22000),
        'memory.user_char_limit': getNumberValue('user-char-limit', 13750),
        'memory.nudge_interval': getNumberValue('memory-nudge-interval', 10),
        'memory.flush_min_turns': getNumberValue('memory-flush-min-turns', 6),
        'session_reset.mode': getElementValue('session-reset-mode', 'both'),
        'session_reset.idle_minutes': getNumberValue('session-reset-idle', 1440),
        'session_reset.at_hour': getNumberValue('session-reset-hour', 4),
        'group_sessions_per_user': getBooleanSelectValue('group-sessions-per-user', true),
        'privacy.redact_pii': getBooleanSelectValue('privacy-redact-pii', false),
        'timezone': getElementValue('timezone', '').trim(),
        'prefill_messages_file': getElementValue('prefill-messages-file', '').trim(),
    };
    await postConfigUpdates(updates, 'Memory and session settings saved');
}

async function saveToolsSkillsSettings() {
    const updates = {
        'skills.creation_nudge_interval': getNumberValue('skills-creation-nudge', 15),
        'skills.disabled': parseJsonField('skills-disabled-json', []),
        'skills.external_dirs': parseJsonField('skills-external-dirs-json', []),
        'platform_toolsets': collectPlatformToolsets(),
    };
    await postConfigUpdates(updates, 'Tools and skills settings saved');
}

async function saveBrowserVoiceSettings() {
    const tts = parseJsonField('tts-json', {});
    const stt = parseJsonField('stt-json', {});
    tts.provider = getElementValue('tts-provider', tts.provider || 'edge');
    stt.enabled = getBooleanSelectValue('stt-enabled', Boolean(stt.enabled));
    stt.provider = getElementValue('stt-provider', stt.provider || 'local');

    const updates = {
        'web.backend': getElementValue('web-backend', 'firecrawl'),
        'browser.inactivity_timeout': getNumberValue('browser-inactivity-timeout', 120),
        'browser.command_timeout': getNumberValue('browser-command-timeout', 30),
        'browser.record_sessions': getBooleanSelectValue('browser-record-sessions', false),
        'browser.allow_private_urls': getBooleanSelectValue('browser-allow-private-urls', false),
        'browser.camofox.managed_persistence': getBooleanSelectValue('browser-camofox-persistence', false),
        'tts': tts,
        'stt': stt,
        'voice.record_key': getElementValue('voice-record-key', 'ctrl+b').trim(),
        'voice.max_recording_seconds': getNumberValue('voice-max-recording', 120),
        'voice.auto_tts': getBooleanSelectValue('voice-auto-tts', false),
        'voice.silence_threshold': getNumberValue('voice-silence-threshold', 200),
        'voice.silence_duration': getNumberValue('voice-silence-duration', 3),
    };
    await postConfigUpdates(updates, 'Browser, web, and voice settings saved');
}

async function saveDisplayUXSettings() {
    const updates = {
        'display.compact': getBooleanSelectValue('display-compact', false),
        'display.skin': getElementValue('display-skin', 'default'),
        'display.resume_display': getElementValue('display-resume-display', 'full'),
        'display.busy_input_mode': getElementValue('display-busy-input-mode', 'interrupt'),
        'display.tool_progress': getElementValue('display-tool-progress', 'all'),
        'display.tool_preview_length': getNumberValue('display-tool-preview-length', 0),
        'display.show_reasoning': getBooleanSelectValue('display-show-reasoning', false),
        'display.streaming': getBooleanSelectValue('display-streaming', true),
        'display.inline_diffs': getBooleanSelectValue('display-inline-diffs', false),
        'display.show_cost': getBooleanSelectValue('display-show-cost', false),
        'display.background_process_notifications': getElementValue('display-background-notifications', 'all'),
        'display.bell_on_complete': getBooleanSelectValue('display-bell-on-complete', false),
        'display.tool_progress_command': getBooleanSelectValue('display-tool-progress-command', false),
        'human_delay.mode': getElementValue('human-delay-mode', 'off'),
        'human_delay.min_ms': getNumberValue('human-delay-min', 800),
        'human_delay.max_ms': getNumberValue('human-delay-max', 2500),
    };
    await postConfigUpdates(updates, 'Display and UX settings saved');
}

async function saveAdvancedSettings() {
    const terminalApprovals = parseJsonField('terminal-approvals-json', {});
    const platformBehavior = parseJsonField('platform-behavior-json', {});
    const cronQuick = parseJsonField('cron-quick-json', {});
    const updates = {
        'terminal': terminalApprovals.terminal || {},
        'approvals': terminalApprovals.approvals || {},
        'command_allowlist': terminalApprovals.command_allowlist || [],
        'security': parseJsonField('security-json', {}),
        'discord': platformBehavior.discord || {},
        'whatsapp': platformBehavior.whatsapp || {},
        'streaming': platformBehavior.streaming || {},
        'session_reset': platformBehavior.session_reset || {},
        'group_sessions_per_user': Object.prototype.hasOwnProperty.call(platformBehavior, 'group_sessions_per_user') ? platformBehavior.group_sessions_per_user : true,
        'mcp_servers': parseJsonField('mcp-servers-json', {}),
        'cron': cronQuick.cron || {},
        'quick_commands': cronQuick.quick_commands || {},
    };
    await postConfigUpdates(updates, 'Advanced settings saved');
}

async function loadSessions() {
    const search = document.getElementById('session-search').value;
    const sort = document.getElementById('session-sort').value;
    const source = document.getElementById('session-source').value;
    const offset = sessionsPage * sessionsPerPage;

    let url = `/api/sessions?limit=${sessionsPerPage}&offset=${offset}&sort=${sort}`;
    if (search) url += '&search=' + encodeURIComponent(search);
    if (source) url += '&source=' + encodeURIComponent(source);

    log('req', `GET ${url}`);
    const data = search ? await fetch(url).then(r => r.json()) : await cachedFetch(url, 10000);
    log('res', `Found ${data.sessions.length} sessions (total: ${data.total})`);

    // Update stats
    const stats = document.getElementById('sessions-stats');
    if (stats) stats.textContent = `${data.total} session${data.total !== 1 ? 's' : ''}`;

    const list = document.getElementById('sessions-list');

    if (!data.sessions.length) {
        list.innerHTML = '<div style="text-align:center;color:var(--text-dim);padding:2rem;">No sessions found</div>';
        document.getElementById('sessions-pagination').innerHTML = '';
        return;
    }

    list.innerHTML = renderSessionListItems(data.sessions);

    // Render pagination
    const totalPages = Math.ceil(data.total / sessionsPerPage);
    const pag = document.getElementById('sessions-pagination');
    if (totalPages > 1) {
        pag.innerHTML = `
            <button onclick="sessionsPage--;loadSessions()" ${sessionsPage === 0 ? 'disabled' : ''}>Prev</button>
            <span>Page ${sessionsPage + 1} of ${totalPages}</span>
            <button onclick="sessionsPage++;loadSessions()" ${sessionsPage >= totalPages - 1 ? 'disabled' : ''}>Next</button>
        `;
    } else {
        pag.innerHTML = '';
    }
}

async function exportSession(id) {
    try {
        const resp = await fetch(`/api/sessions/${id}`);
        const data = await resp.json();
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `session-${id.slice(0,8)}.json`;
        a.click();
        URL.revokeObjectURL(url);
        showToast('Session exported');
    } catch (e) {
        showToast('Export failed: ' + e.message, true);
        log('err', 'Session export failed: ' + e.message, true);
    }
}

async function loadSessionSources() {
    try {
        const data = await cachedFetch('/api/sessions/sources', 60000);
        const select = document.getElementById('session-source');
        if (select && data.sources && data.sources.length) {
            select.innerHTML = '<option value="">All Sources</option>' +
                data.sources.map(s => `<option value="${escapeHtml(s)}">${escapeHtml(s)}</option>`).join('');
        }
    } catch(e) { log('warn', 'Failed to load session sources: ' + e.message); }
}

document.getElementById('session-search').addEventListener('input', debounce(() => { sessionsPage = 0; loadSessions(); }, 300));

async function viewSession(id) {
    const requestId = ++activeSessionDetailRequestId;
    activeSessionDetailId = id;
    log('req', `GET /api/sessions/${id}`);
    const resp = await fetch(`/api/sessions/${id}`);
    const data = await resp.json();
    if (requestId !== activeSessionDetailRequestId || activeSessionDetailId !== id) {
        log('inf', `Ignoring stale session detail response for ${id}`);
        return;
    }
    log('res', `Loaded ${data.messages.length} messages`);

    // Update hash if not already matching (avoid re-triggering hashchange)
    const expectedHash = 'sessions/detail/' + id;
    const currentHash = location.hash.slice(1);
    if (!(currentHash === expectedHash || currentHash.startsWith(expectedHash + '/'))) {
        location.hash = expectedHash;
        return;
    }

    // Update breadcrumbs
    updateBreadcrumbs('sessions', data.title || ('Session ' + id.slice(0, 8)));

    const detail = document.getElementById('session-detail');
    const messages = document.getElementById('session-detail-messages');
    document.getElementById('session-detail-title').textContent = data.title || `Session ${id.slice(0, 8)}`;
    const detailActions = document.querySelector('#session-detail .session-detail-actions');
    if (detailActions) {
        detailActions.innerHTML = `
            <button class="btn" onclick="attachChatToSession('${id}')">Use in Chat</button>
            <button class="btn" id="session-regenerate-summary-btn" onclick="regenerateSessionSummary()">Regenerate Title + Summary</button>
            <button class="btn" onclick="closeSessionDetail()">Close</button>
        `;
    }

    currentSessionTraceContext = buildSessionTraceContext(data);
    const summaryHtml = data.summary ? `<div class="summary-block"><span class="label">Session Summary</span>${escapeHtml(data.summary)}</div>` : '';
    const warningHtml = renderSessionTranscriptWarning(data);
    const overviewHtml = renderSessionOverview(data);
    messages.innerHTML = overviewHtml + summaryHtml + warningHtml + renderSessionTranscript(currentSessionTraceContext);

    renderBackgroundReviews(data.background_reviews || []);
    renderRequestResultActivity(
        'session-skill-events',
        data.skill_events || [],
        'No skill creation or update activity yet.',
        item => {
            const req = item.request || {};
            const action = req.action || 'skill_manage';
            const name = req.name || 'skill';
            return `${action} ${name}`;
        }
    );
    renderSessionSearchEvents(data.session_search_events || []);

    await loadSessionFiles(id);

    detail.classList.add('active');
    if (pendingSessionExecutionTarget) {
        requestAnimationFrame(() => {
            scrollToExecutionNode(pendingSessionExecutionTarget, currentSessionTraceContext);
        });
    }

    await loadSessionTokens(id);
    await loadSessionContextGauge(id);
}

async function loadSessionFiles(id) {
    const requestId = activeSessionDetailRequestId;
    log('req', `GET /api/sessions/${id}/files`);
    const resp = await fetch(`/api/sessions/${id}/files`);
    const data = await resp.json();
    if (requestId !== activeSessionDetailRequestId || activeSessionDetailId !== id) {
        log('inf', `Ignoring stale session files response for ${id}`);
        return;
    }
    currentSessionFiles = data.files || [];
    log('res', `Loaded ${currentSessionFiles.length} touched files`);
    renderSessionFiles();
}

function persistActiveAssistantState(assistantState, roomId = activeChatRoomId, runState = getActiveRun(roomId)) {
    if (!assistantState || !runState || getActiveRun(roomId)?.runId !== runState.runId) return;
    runState.assistantState = {
        role: 'assistant',
        bot: assistantState.bot || runState.profile || 'default',
        content: assistantState.content || '',
        tools: Array.isArray(assistantState.tools) ? assistantState.tools : [],
        events: Array.isArray(assistantState.events) ? assistantState.events : [],
        usage: assistantState.usage || null,
        last_prompt_tokens: assistantState.last_prompt_tokens || 0,
        prompt_breakdown: Array.isArray(assistantState.prompt_breakdown) ? assistantState.prompt_breakdown : [],
        trace: assistantState.trace || null,
    };
    saveActiveRuns();
    if (roomId === activeChatRoomId) updateActiveRunBanner();
    renderChatRoomRail();
}

async function finalizeActiveRun(assistantState, roomId, roomConversation, runState) {
    if (!assistantState) {
        clearActiveRun(roomId, runState.runId);
        return;
    }
    persistActiveAssistantState(assistantState, roomId, runState);
    if (!roomConversation.length || roomConversation[roomConversation.length - 1] !== assistantState) {
        const finalMessage = {
            role: 'assistant',
            bot: assistantState.bot || runState.profile || 'default',
            content: assistantState.content,
            tools: assistantState.tools,
            events: assistantState.events,
            usage: assistantState.usage,
            last_prompt_tokens: assistantState.last_prompt_tokens || (assistantState.usage && assistantState.usage.prompt_tokens) || 0,
            prompt_breakdown: assistantState.prompt_breakdown,
            trace: assistantState.trace || null,
        };
        roomConversation.push(finalMessage);
        if (roomId === 'main') {
            await saveDashboardState('conversation', roomConversation, { immediate: true });
        } else {
            await saveBotRoom(roomId, roomConversation, runState.sessionId);
        }
        if (roomId === activeChatRoomId && conversation !== roomConversation) {
            conversation.push(finalMessage);
        }
    }
    if (runState.notificationStatus !== 'error') {
        const identity = identityForRoom(roomId);
        sendDashboardNotification('runs', 'Hermes finished', `${identity.display_name || identity.name || 'Hermes'} completed its response.`, {
            key: `run:${runState.runId}:complete`,
            tag: `hermes-run-${runState.runId}`,
            panel: 'chat',
        });
    }
    clearActiveRun(roomId, runState.runId);
    if (roomId === activeChatRoomId) {
        renderConversation();
        updateContextDisplay(assistantState);
        void refreshSessionContextInfo(activeChatSessionId);
    }
}

function buildChatRequestMessages(messages) {
    return (messages || [])
        .map((msg) => {
            if (!msg || typeof msg !== 'object') return null;
            const role = msg.role;
            const content = typeof msg.content === 'string' ? msg.content : '';
            if (!['system', 'user', 'assistant', 'tool'].includes(role)) return null;
            if (role === 'assistant' && content.startsWith('Error: Hermes gateway')) return null;
            if (!content && role !== 'assistant') return null;
            return { role, content };
        })
        .filter(Boolean);
}

// === TRACK D: Interrupt ===
const liveRunInterruptState = { sessionId: null, roomId: null, queued: false };

function showInterruptButton(sessionId) {
    if (!sessionId) return;
    if (liveRunInterruptState.sessionId !== sessionId || liveRunInterruptState.roomId !== activeChatRoomId) {
        liveRunInterruptState.queued = false;
    }
    liveRunInterruptState.sessionId = sessionId;
    liveRunInterruptState.roomId = activeChatRoomId;
    if (chatRunStopBtn) {
        chatRunStopBtn.hidden = false;
        chatRunStopBtn.disabled = liveRunInterruptState.queued;
        chatRunStopBtn.textContent = liveRunInterruptState.queued ? 'Stopping...' : 'Stop main agent';
        chatRunStopBtn.classList.toggle('queued', liveRunInterruptState.queued);
    }
}

function hideInterruptButton(disableStop = true) {
    liveRunInterruptState.sessionId = null;
    liveRunInterruptState.roomId = null;
    liveRunInterruptState.queued = false;
    if (chatRunStopBtn && disableStop) {
        chatRunStopBtn.disabled = true;
    }
    const message = document.getElementById('interrupt-status-msg');
    if (message) message.hidden = true;
}

function requestInterrupt(sessionId, runId = null) {
    if (!sessionId && !runId) return;
    if (!window.confirm('Emergency stop the running main agent?')) return;
    const requestRoomId = activeChatRoomId;
    const targetRun = Object.values(activeRuns).find(run => run.runId === runId);
    const useRunStop = Boolean(runId && targetRun?.profile && targetRun.profile !== 'default');
    const path = sessionId && !useRunStop
        ? '/api/sessions/' + encodeURIComponent(sessionId) + '/interrupt'
        : '/api/runs/' + encodeURIComponent(runId) + '/stop';
    fetch(path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'stop', run_id: runId || '' }),
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
        if (data.status === 'interrupt_queued' || data.status === 'stop_queued') {
            if (activeChatRoomId !== requestRoomId) {
                showToast('Emergency stop queued');
                return;
            }
            liveRunInterruptState.queued = true;
            liveRunInterruptState.roomId = requestRoomId;
            const btn = chatRunStopBtn;
            if (btn) {
                btn.classList.add('queued');
                btn.textContent = 'Stopping...';
                btn.disabled = true;
            }
            if (chatRunStopBtn) {
                chatRunStopBtn.disabled = true;
            }
            const msg = document.getElementById('interrupt-status-msg');
            if (msg) {
                msg.textContent = 'Emergency stop queued.';
                msg.hidden = false;
            }
            showToast('Emergency stop queued');
        } else if (data.status === 'not_running') {
            showToast('Session is not running', true);
            if (activeChatRoomId === requestRoomId) hideInterruptButton();
        }
    })
    .catch(function(err) {
        log('err', 'Failed to queue emergency stop: ' + err.message);
        showToast('Failed to queue emergency stop', true);
    });
}
// === END TRACK D ===

async function streamChatRun({ runId, messagesPayload, resume = false, eventOffset = 0, sessionId = null, assistantSeed = null, roomId = 'main', profile = 'default' }) {
    const runState = getActiveRun(roomId);
    if (!runState || runState.runId !== runId) throw new Error('Active run state is unavailable');
    const roomConversation = messagesPayload;
    connectedChatRunRooms.add(roomId);
    if (roomId === activeChatRoomId) updateActiveRunBanner();
    let response;
    try {
        response = await fetch('/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                run_id: runId,
                resume,
                event_offset: eventOffset,
                session_id: sessionId,
                room_id: roomId,
                profile,
                messages: buildChatRequestMessages(messagesPayload),
            })
        });
    } catch (error) {
        connectedChatRunRooms.delete(roomId);
        if (roomId === activeChatRoomId) updateActiveRunBanner();
        throw error;
    }

    if (!response.ok) {
        connectedChatRunRooms.delete(roomId);
        if (roomId === activeChatRoomId) updateActiveRunBanner();
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    const reader = response.body.getReader();
    // TRACK D: show/hide interrupt button
    if (roomId === activeChatRoomId) showInterruptButton(sessionId);
    // TRACK D: end
    const decoder = new TextDecoder();
    const assistantState = assistantSeed
        ? normalizeAssistantMessage(assistantSeed)
        : createAssistantTraceState({ sessionId });
    assistantState.bot = assistantSeed?.bot || profile || 'default';
    const intentOwner = {};
    const intentEpoch = chatRoomIntentEpochs.get(roomId) || 0;
    toolIntentRunOwners.set(runId, intentOwner);
    let assistantDiv = null;
    let chunkCount = 0;
    let streamBuffer = '';
    let sawDone = false;

    // Render batching system for streaming performance
    let renderDirty = false;
    let persistDirty = false;
    let lastPersistTime = 0;
    let intentStreamOpen = true;

    function persistToolIntentUpdate() {
        if ((chatRoomIntentEpochs.get(roomId) || 0) !== intentEpoch) return;
        const currentRun = getActiveRun(roomId);
        const finalMessageExists = roomConversation.some(message => (
            message?.role === 'assistant'
            && (message.trace === assistantState.trace || message.tools === assistantState.tools)
        ));
        if (currentRun?.runId === runId && !finalMessageExists) {
            persistActiveAssistantState(assistantState, roomId, currentRun);
            if (intentStreamOpen) renderDirty = true;
            else if (roomId === activeChatRoomId) renderConversation();
            return;
        }
        if (roomId === 'main') {
            void saveDashboardState('conversation', roomConversation, { immediate: true });
        } else {
            void saveBotRoom(roomId, roomConversation, runState.sessionId);
        }
        if (roomId === activeChatRoomId) renderConversation();
    }

    function queueToolIntentDescription(tool) {
        return requestToolIntentDescription(tool, {
            runId,
            isCurrent: () => toolIntentRunOwners.get(runId) === intentOwner,
            onReady(description) {
                if (!setToolIntentDescription(assistantState, tool.call_id, description)) return;
                persistToolIntentUpdate();
            },
            onSettled() {
                if (!setToolIntentDescriptionPending(assistantState, tool.call_id, false)) return;
                persistToolIntentUpdate();
            },
        });
    }

    assistantState.tools.forEach(tool => void queueToolIntentDescription(tool));
    if (roomId === activeChatRoomId && (assistantState.content || assistantState.tools.length || assistantState.events.length)) {
        assistantDiv = renderActiveRunProjection() || addMessage('assistant', assistantState, false);
        assistantDiv.dataset.chatRunId = runId;
        bindToolCardInteractions(assistantDiv);
    }

    function scheduleRender() {
        if (!renderDirty) return;
        renderDirty = false;
        const now = Date.now();
        if (now - lastPersistTime > 1000) {
            lastPersistTime = now;
            persistActiveAssistantState(assistantState, roomId, runState);
            persistDirty = false;
        } else {
            persistDirty = true;
        }
        if (roomId !== activeChatRoomId) {
            return;
        }
        const stickToBottom = shouldStickToBottom(chat);
        if (assistantDiv && !assistantDiv.isConnected) assistantDiv = null;
        if (!assistantDiv) {
            assistantDiv = renderActiveRunProjection() || addMessage('assistant', assistantState, false);
            assistantDiv.dataset.chatRunId = runId;
            bindToolCardInteractions(assistantDiv);
        } else {
            const openToolState = captureOpenToolState(assistantDiv);
            assistantDiv.innerHTML = renderAssistantMessage(assistantState);
            bindAvatarFallbacks(assistantDiv);
            restoreOpenToolState(assistantDiv, openToolState);
        }
        scrollChatToBottom(false, stickToBottom);

    }

    // Render loop at ~30fps
    const renderLoop = setInterval(scheduleRender, 32);
    log('inf', 'SSE stream connected, render loop started (~30fps)');

    try {
    outer: while (true) {
        const { done, value } = await reader.read();
        streamBuffer += decoder.decode(value || new Uint8Array(), { stream: !done });

        const events = streamBuffer.split(/\r?\n\r?\n/);
        if (!done) {
            streamBuffer = events.pop() || '';
        } else {
            streamBuffer = '';
        }

        for (const rawEvent of events) {
            const line = rawEvent
                .split(/\r?\n/)
                .find(part => part.startsWith('data: '));
            if (!line) continue;
            const data = line.slice(6);
            if (data === '[DONE]') {
                sawDone = true;
                break outer;
            }

            try {
                const parsed = JSON.parse(data);
                if (parsed.type === 'run_state') {
                    const stateMetadata = getEventMetadata(parsed);
                    const childStateId = stateMetadata.child_session_id || stateMetadata.subagent_id
                        || (stateMetadata.delegate_call_id ? stateMetadata.session_id : '');
                    if (childStateId) {
                        const childStatus = parsed.status === 'error' ? 'ERROR'
                            : (parsed.status === 'complete' ? 'DONE' : (parsed.status === 'paused' ? 'PAUSED' : 'LIVE'));
                        rememberChildDrawer(childStateId, {
                            label: stateMetadata.label || '',
                            taskIndex: stateMetadata.task_index ?? null,
                            parentSessionId: stateMetadata.parent_session_id || runState.sessionId || '',
                            delegateCallId: stateMetadata.delegate_call_id || '',
                        });
                        rememberRunChildSession(runState, childDrawerRegistry.get(childStateId), childStatus);
                        appendLiveDrawerEventIfOpen(parsed);
                        updateDrawerBadge(childStateId, childStatus);
                        if (ACTIVE_CHILD_DRAWER_STATUSES.has(childStatus)) watchSubagentFlightStatus(childStateId);
                        saveActiveRuns();
                        continue;
                    }
                    if (parsed.approval_session_id && runState.approvalSessionId !== parsed.approval_session_id) {
                        runState.approvalSessionId = parsed.approval_session_id;
                        saveActiveRuns();
                        void refreshApprovals(false);
                        log('inf', 'Run state: approval_session_id=' + parsed.approval_session_id);
                    }
                    if (parsed.session_id && runState.sessionId !== parsed.session_id) {
                        runState.sessionId = parsed.session_id;
                        if (roomId === activeChatRoomId) {
                            activeChatSessionId = parsed.session_id;
                            void refreshSessionContextInfo(parsed.session_id);
                            updateActiveChatBanner();
                            showInterruptButton(parsed.session_id);
                        }
                        if (roomId === 'main') {
                            saveMainChatSession(parsed.session_id);
                        } else {
                            void saveBotRoom(roomId, roomConversation, parsed.session_id);
                        }
                        saveActiveRuns();
                        log('inf', 'Run state: session_id=' + parsed.session_id);
                    }
                    // TRACK D: show/hide interrupt button
                    if (roomId === activeChatRoomId && (parsed.status === 'complete' || parsed.status === 'error')) {
                        hideInterruptButton();
                    }
                    if (parsed.status === 'error') {
                        runState.notificationStatus = 'error';
                        const identity = identityForRoom(roomId);
                        sendDashboardNotification('errors', 'Hermes run needs attention', `${identity.display_name || identity.name || 'Hermes'} reported an error.`, {
                            key: `run:${runId}:error`,
                            tag: `hermes-run-${runId}`,
                            panel: 'chat',
                        });
                    }
                    // TRACK D: end
                    continue;
                }
                runState.eventOffset = (runState.eventOffset || 0) + 1;
                if (parsed.type === 'content' && parsed.content) {
                    appendContentEvent(assistantState, parsed.content);
                    chunkCount++;
                    renderDirty = true;

                    const imagesInContent = parseImagesFromContent(parsed.content);
                    imagesInContent.forEach((img) => {
                        log('img', `Image (${img.type}, ${Math.round(img.data.length / 1024)}KB)`, false, null, img.full);
                    });
                } else if (parsed.type === 'child_session_started' || (parsed.type === 'tool_progress' && parsed.name === 'child_session_started')) {
                    const args = getEventMetadata(parsed);
                    const delegateCallId = parsed.delegate_call_id || parsed.call_id || args.delegate_call_id || findLatestDelegateToolCallId(assistantState) || '';
                    const childSessionId = parsed.child_session_id || args.child_session_id || parsed.session_id || args.session_id || parsed.subagent_id || args.subagent_id || '';
                    if (childSessionId) {
                        const entry = liveChildSessionMap.get(delegateCallId) || [];
                        const childEntry = { childSessionId, label: parsed.label || args.label || 'delegate_task', taskIndex: parsed.task_index ?? args.task_index ?? null, parentSessionId: parsed.parent_session_id || args.parent_session_id || runState.sessionId || '', delegateCallId };
                        if (!entry.some(item => item.childSessionId === childSessionId)) {
                            entry.push(childEntry);
                        }
                        liveChildSessionMap.set(delegateCallId, entry);
                        rememberChildDrawer(childSessionId, childEntry);
                        rememberRunChildSession(runState, childEntry, 'LIVE');
                        updateDrawerBadge(childSessionId, 'LIVE');
                        watchSubagentFlightStatus(childSessionId);
                        appendLiveDrawerEventIfOpen(parsed);
                        renderDirty = true;
                        renderChatRoomRail();
                        log('tool', `[child_session_started] ${childSessionId.slice(0, 8)}...`, false, { result: parsed });
                        saveActiveRuns();
                    }
                    continue;
                } else if (parsed.type === 'tool_call') {
                    const isSubagent = parsed.arguments?.subagent || parsed.arguments?.delegate_call_id;
                    appendLiveDrawerEventIfOpen(parsed);
                    if (isSubagent && appendDelegateChildEvent(assistantState, parsed)) {
                        startToolTimer(parsed.call_id || parsed.name, true);
                        renderDirty = true;
                        log('tool', `[subagent] ${parsed.name || 'tool'} started`, false, { args: parsed.arguments?.child_args || parsed.arguments });
                        saveActiveRuns();
                        continue;
                    }
                    const tool = upsertToolEvent(assistantState, parsed);
                    startToolTimer(tool.call_id);
                    startToolTimerUpdates();
                    renderDirty = true;
                    void queueToolIntentDescription(tool);
                    if (tool.name === 'delegate_task') {
                        log('tool', describeToolLog(tool.name, 'delegated', tool.arguments), false, { args: tool.arguments });
                    } else {
                        log('tool', describeToolLog(tool.name, 'start', tool.arguments), false, { args: tool.arguments });
                    }
                } else if (parsed.type === 'tool_output') {
                    const isSubagentOutput = parsed.arguments?.subagent || parsed.arguments?.delegate_call_id;
                    appendLiveDrawerEventIfOpen(parsed);
                    if (isSubagentOutput && appendDelegateChildEvent(assistantState, parsed)) {
                        stopToolTimer(parsed.call_id || parsed.name, true);
                        renderDirty = true;
                        log('tool', `[subagent] ${parsed.name || 'tool'} completed`, false, { result: parsed.output });
                        saveActiveRuns();
                        continue;
                    }
                    const tool = upsertToolEvent(assistantState, parsed);
                    stopToolTimer(parsed.call_id || parsed.name);
                    renderDirty = true;
                    log('tool', describeToolLog(tool.name, 'output', tool.output), false, { result: tool.output });
                } else if (parsed.type === 'tool_progress') {
                    appendLiveDrawerEventIfOpen(parsed);
                    if ((parsed.arguments?.delegate_call_id || parsed.arguments?.call_id) && appendDelegateChildEvent(assistantState, parsed)) {
                        renderDirty = true;
                        log('tool', `[subagent] ${parsed.name || 'progress'}: ${summarizeValue(parsed.progress || parsed.arguments || '', 100)}`, false, { result: parsed.progress || parsed.arguments || '' });
                        saveActiveRuns();
                        continue;
                    }
                    const tool = appendToolProgress(assistantState, parsed);
                    renderDirty = true;
                    log('tool', describeToolLog(tool.name, 'progress', parsed.progress || parsed.arguments || ''), false, { result: parsed.progress || parsed.arguments || '' });
                } else if (parsed.type === 'meta') {
                    reduceAssistantTraceEvent(assistantState, parsed);
                    renderDirty = true;
                    if (roomId === activeChatRoomId) updateContextDisplay(assistantState);
                    log('inf', 'Meta: ' + (parsed.usage ? parsed.usage.total_tokens + ' tokens' : 'prompt update'), false, { result: parsed });
                }
                saveActiveRuns();
            } catch (e) {
                if (data && data !== '[DONE]') log('warn', 'Failed to parse SSE event: ' + e.message, false, { error: data });
            }
        }

        if (done) {
            log('res', `Stream complete (${chunkCount} chunks, ${assistantState.content.length} chars)`);
            break;
        }
    }

        if (sawDone) {
            log('res', `Stream complete (${chunkCount} chunks, ${assistantState.content.length} chars)`);
            await finalizeActiveRun(assistantState, roomId, roomConversation, runState);
        } else {
            log('warn', `Stream ended before completion; run ${runId} remains available to follow`);
            persistActiveAssistantState(assistantState, roomId, runState);
            if (roomId === activeChatRoomId) updateActiveRunBanner();
        }
    } finally {
        intentStreamOpen = false;
        connectedChatRunRooms.delete(roomId);
        if (roomId === activeChatRoomId) updateActiveRunBanner();
        clearInterval(renderLoop);
        log('inf', 'Render loop stopped');
        if (renderDirty) scheduleRender();
        if (assistantDiv) highlightToolCode(assistantDiv);
        if (persistDirty) persistActiveAssistantState(assistantState, roomId, runState);
        const hasPendingIntentRequest = Array.from(toolIntentRequests.keys())
            .some(key => key.startsWith(`${runId}:`));
        if (!hasPendingIntentRequest && toolIntentRunOwners.get(runId) === intentOwner) {
            toolIntentRunOwners.delete(runId);
        }
        const hasOtherRun = Object.values(activeRuns).some(run => run.runId !== runId);
        if (!hasOtherRun) {
            toolCallTimers.clear();
            stopToolTimerUpdates();
        }
        if (roomId === activeChatRoomId) hideInterruptButton(false);
    }
}

function renderSessionFiles(activePath = null) {
    const list = document.getElementById('session-files-list');
    if (!currentSessionFiles.length) {
        list.innerHTML = '<div style="color:var(--text-dim);">No file tool activity was recorded for this session.</div>';
        document.getElementById('file-preview-title').textContent = 'File Preview';
        document.getElementById('file-preview-body').innerHTML = '<div style="color:var(--text-dim);margin-top:0.5rem;">Choose a file to preview its contents.</div>';
        return;
    }
    list.innerHTML = currentSessionFiles.map(file => `
        <div class="file-item ${activePath === file.path ? 'active' : ''}" onclick="previewSessionFile(${JSON.stringify(file.path)}, ${file.previewable ? 'true' : 'false'})">
            <div class="file-item-meta">
                <span class="meta-pill">${escapeHtml(file.action || 'file')}</span>
                <span class="meta-pill">${escapeHtml(file.tool || 'tool')}</span>
                ${file.previewable ? '<span class="meta-pill">previewable</span>' : '<span class="meta-pill">metadata only</span>'}
            </div>
            <div class="file-item-path">${escapeHtml(file.path || file.raw_path || '')}</div>
        </div>
    `).join('');
}

function toSessionDateMs(value) {
    if (value == null || value === '') return null;
    const numeric = Number(value);
    if (Number.isFinite(numeric)) {
        return numeric < 1e12 ? numeric * 1000 : numeric;
    }
    const parsed = Date.parse(String(value));
    return Number.isFinite(parsed) ? parsed : null;
}

function formatSessionDate(value) {
    const ms = toSessionDateMs(value);
    if (ms == null) return value ? String(value) : '--';
    const date = new Date(ms);
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleString();
}

function formatDuration(startedAt, endedAt) {
    if (!startedAt || !endedAt) return '--';
    const start = toSessionDateMs(startedAt);
    const end = toSessionDateMs(endedAt);
    if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) return '--';
    const totalSeconds = Math.round((end - start) / 1000);
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;
    if (hours) return `${hours}h ${minutes}m ${seconds}s`;
    if (minutes) return `${minutes}m ${seconds}s`;
    return `${seconds}s`;
}

function renderSessionOverview(data) {
    const items = [
        ['Session ID', data.id || '--'],
        ['Source', data.source || '--'],
        ['Model', data.model || '--'],
        ['Started', formatSessionDate(data.started_at)],
        ['Ended', formatSessionDate(data.ended_at)],
        ['Duration', formatDuration(data.started_at, data.ended_at)],
        ['Messages', data.message_count ?? '--'],
        ['Tool Calls', data.tool_call_count ?? '--'],
        ['Input Tokens', data.input_tokens ?? '--'],
        ['Output Tokens', data.output_tokens ?? '--'],
        ['Reasoning Tokens', data.reasoning_tokens ?? '--'],
        ['Estimated Cost', data.estimated_cost_usd != null ? `$${Number(data.estimated_cost_usd).toFixed(4)}` : '--'],
        ['Actual Cost', data.actual_cost_usd != null ? `$${Number(data.actual_cost_usd).toFixed(4)}` : '--'],
        ['End Reason', data.end_reason || '--'],
        ['Parent Session', data.parent_session_id || '--'],
        ['Child Sessions', data.child_count ?? 0],
    ];
    const children = Array.isArray(data.children) && data.children.length
        ? `<div class="config-help" style="margin-top:0.75rem;">Child sessions: ${data.children.map(child => renderExecutionTargetLink(data.id, { kind: 'child', id: child.id }, child.title || child.id)).join(' | ')}</div>`
        : '';
    const debugJson = {
        model_config: data.model_config,
        billing_provider: data.billing_provider,
        billing_base_url: data.billing_base_url,
        billing_mode: data.billing_mode,
        cost_status: data.cost_status,
        cost_source: data.cost_source,
        cache_read_tokens: data.cache_read_tokens,
        cache_write_tokens: data.cache_write_tokens,
    };
    return `
        <div class="session-overview">
            <div style="display:flex;justify-content:space-between;gap:1rem;align-items:flex-start;flex-wrap:wrap;">
                <div>
                    <div class="label" style="font-size:0.72rem;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.05em;">Session Overview</div>
                    <div style="font-size:0.86rem;color:var(--text-dim);margin-top:0.25rem;">Stored session metadata, lineage, and token/cost totals.</div>
                </div>
            </div>
            <div class="session-overview-grid">
                ${items.map(([label, value]) => `<div class="session-overview-item"><span class="label">${escapeHtml(String(label))}</span><span class="value">${escapeHtml(String(value ?? '--'))}</span></div>`).join('')}
            </div>
            ${children}
            <div class="session-debug-block">
                <details>
                    <summary>Session Debug JSON</summary>
                    <pre>${escapeHtml(JSON.stringify(debugJson, null, 2))}</pre>
                </details>
                ${data.system_prompt ? `<details><summary>System Prompt</summary><pre>${escapeHtml(data.system_prompt)}</pre></details>` : ''}
            </div>
        </div>
    `;
}

function renderSessionTranscriptWarning(data) {
    const messageCount = Array.isArray(data?.messages) ? data.messages.length : 0;
    const artifacts = Array.isArray(data?.related_artifacts) ? data.related_artifacts : [];
    const requestDump = artifacts.find((artifact) => artifact?.kind === 'request_dump');
    if (messageCount > 1 || !requestDump) return '';
    const reason = [requestDump.error_type, requestDump.error_response_status ? `status ${requestDump.error_response_status}` : '', requestDump.model].filter(Boolean).join(' · ');
    return `
        <div class="session-warning">
            <strong>Partial session transcript.</strong>
            Only ${messageCount} persisted message${messageCount === 1 ? '' : 's'} are available for this session. Hermes also recorded a request dump for a failed upstream call${reason ? ` (${escapeHtml(reason)})` : ''}, so the detailed transcript you expect may never have been written to session storage.
        </div>
    `;
}

function renderSessionMessage(message) {
    const meta = [];
    if (message.timestamp) meta.push(formatSessionDate(message.timestamp));
    if (message.finish_reason) meta.push(`finish=${message.finish_reason}`);
    if (message.token_count != null) meta.push(`tokens=${message.token_count}`);
    if (message.id != null) meta.push(`id=${message.id}`);
    const metaHtml = meta.length ? `<div class="session-message-meta">${meta.map(escapeHtml).join(' · ')}</div>` : '';
    const traceContext = message?.renderTraceContext || null;
    const traceDomId = message?.traceNode?.dom_id ? scopedExecutionDomId(message.traceNode.dom_id, traceContext) : '';
    const traceId = traceDomId ? ` id="${escapeHtml(traceDomId)}"` : '';
    const traceClass = message?.traceNode?.dom_id ? ' execution-node' : '';

    if (message.role === 'assistant') {
        const debugSections = [];
        if (message.reasoning) {
            debugSections.push(`<details><summary>Reasoning</summary><pre>${escapeHtml(message.reasoning)}</pre></details>`);
        }
        if (message.reasoning_details) {
            debugSections.push(`<details><summary>Reasoning Details</summary><pre>${escapeHtml(JSON.stringify(message.reasoning_details, null, 2))}</pre></details>`);
        }
        if (message.codex_reasoning_items) {
            debugSections.push(`<details><summary>Codex Reasoning Items</summary><pre>${escapeHtml(JSON.stringify(message.codex_reasoning_items, null, 2))}</pre></details>`);
        }
        const debugHtml = debugSections.length ? `<div class="session-debug-block">${debugSections.join('')}</div>` : '';
        return `<div class="message assistant${traceClass}"${traceId}>${metaHtml}${renderAssistantMessage({ ...message, content: message.content || '', tools: message.tools || [], events: message.events || [], renderTraceContext: traceContext })}${debugHtml}</div>`;
    }

    return `<div class="message ${message.role}${traceClass}"${traceId}>${metaHtml}${formatSessionTranscriptContent(message.content || '')}</div>`;
}

async function previewSessionFile(path, previewable = true) {
    renderSessionFiles(path);
    document.getElementById('file-preview-title').textContent = path;
    const body = document.getElementById('file-preview-body');
    await renderUniversalFileViewer(path, body, { compact: true, legacyPreviewable: previewable });
}

function closeSessionDetail() {
    document.getElementById('session-detail').classList.remove('active');
    currentSessionFiles = [];
    navigateTo('sessions');
}

async function regenerateSessionSummary() {
    const hash = location.hash.slice(1);
    const parts = hash.split('/');
    const sessionId = parts[0] === 'sessions' && parts[1] === 'detail' ? parts[2] : '';
    if (!sessionId) {
        showToast('No session selected', true);
        return;
    }

    const button = document.getElementById('session-regenerate-summary-btn');
    const previousText = button ? button.textContent : '';
    if (button) {
        button.disabled = true;
        button.textContent = 'Regenerating...';
    }

    try {
        const data = await fetchJsonOrThrow(`/api/sessions/${encodeURIComponent(sessionId)}/summary`, {
            method: 'POST'
        });
        showToast('Session title and summary regenerated');
        invalidateCache('/api/sessions');
        invalidateCache('/api/graph');
        if (location.hash.slice(1) === `sessions/detail/${sessionId}`) {
            await viewSession(sessionId);
        }
        const graphPanel = document.getElementById('graph-panel');
        if (graphPanel && graphPanel.classList.contains('active') && graphLoaded) {
            loadGraph();
        }
    } catch (e) {
        showToast('Summary regeneration failed: ' + e.message, true);
        log('err', 'Summary regeneration failed: ' + e.message, true);
    } finally {
        if (button) {
            button.disabled = false;
            button.textContent = previousText || 'Regenerate Title + Summary';
        }
    }
}

async function deleteSession(id) {
    if (!confirm('Delete this session?')) return;
    try {
        log('req', `DELETE /api/sessions/${id}`);
        await fetchJsonOrThrow(`/api/sessions/${id}`, { method: 'DELETE' });
        log('res', 'Session deleted');
        showToast('Session deleted');
        invalidateCache('/api/sessions');
        loadSessions();
    } catch (e) {
        showToast('Delete failed: ' + e.message, true);
        log('err', 'Session delete failed: ' + e.message, true);
    }
}

async function loadMemory() {
    log('req', 'GET /api/memory');
    const data = await cachedFetch('/api/memory', 60000);
    log('res', 'Memory loaded');
    document.getElementById('memory-text').value = data.memory;
    document.getElementById('user-profile-text').value = data.user_profile;
    updateMemoryCharCount();
}

let allSkills = [];
let allSkillsDisabled = [];

async function loadSkills() {
    log('req', 'GET /api/skills');
    const data = await cachedFetch('/api/skills', 60000);
    log('res', `Loaded ${data.skills.length} skills`);

    allSkills = data.skills;
    allSkillsDisabled = data.disabled;

    // Populate category filter
    const categories = [...new Set(allSkills.map(s => s.id.split('/')[0] || s.id))].sort();
    const catSelect = document.getElementById('skill-category');
    if (catSelect) {
        const current = catSelect.value;
        catSelect.innerHTML = '<option value="">All Categories</option>' +
            categories.map(c => `<option value="${escapeHtml(c)}" ${c === current ? 'selected' : ''}>${escapeHtml(c.replace(/-/g, ' ').replace(/\b\w/g, l => l.toUpperCase()))}</option>`).join('');
    }

    filterSkills();
}

function filterSkills() {
    const search = (document.getElementById('skill-search')?.value || '').toLowerCase();
    const category = document.getElementById('skill-category')?.value || '';

    let filtered = allSkills;
    if (search) {
        filtered = filtered.filter(s =>
            (s.name || s.id).toLowerCase().includes(search) ||
            (s.description || '').toLowerCase().includes(search) ||
            s.id.toLowerCase().includes(search)
        );
    }
    if (category) {
        filtered = filtered.filter(s => s.id === category || s.id.startsWith(category + '/'));
    }

    const stats = document.getElementById('skills-stats');
    if (stats) stats.textContent = `${filtered.length} of ${allSkills.length} skills`;

    const list = document.getElementById('skills-list');

    if (!filtered.length) {
        list.innerHTML = '<div style="text-align:center;color:var(--text-dim);padding:2rem;">No skills match</div>';
        return;
    }

    list.innerHTML = filtered.map(s => {
        const disabled = allSkillsDisabled.includes(s.id);
        return `
            <div class="skill-card ${disabled ? 'disabled' : ''}">
                <div class="skill-info" onclick="viewSkillContent('${escapeHtml(s.id)}')" style="cursor:pointer;">
                    <h4>${escapeHtml(s.name || s.id)}</h4>
                    <p>${escapeHtml(s.description || 'No description')}</p>
                    <span style="font-size:0.7rem;color:var(--text-dim);">${escapeHtml(s.id)}</span>
                </div>
                <div class="toggle ${disabled ? '' : 'active'}" onclick="toggleSkill('${s.id}', ${disabled})"></div>
            </div>
        `;
    }).join('');
}

async function viewSkillContent(skillId) {
    try {
        const resp = await fetch('/api/skills/' + encodeURIComponent(skillId) + '/content');
        const data = await resp.json();

        const modal = document.getElementById('skill-modal');
        document.getElementById('skill-modal-title').textContent = skillId;
        document.getElementById('skill-modal-content').textContent = data.content || 'No content available';

        if (data.files && data.files.length) {
            document.getElementById('skill-modal-files').innerHTML =
                '<strong>Files:</strong> ' + data.files.map(f => escapeHtml(f)).join(', ');
        } else {
            document.getElementById('skill-modal-files').innerHTML = '';
        }

        modal.style.display = 'flex';
    } catch (e) {
        showToast('Failed to load skill content', true);
        log('err', 'Failed to load skill content: ' + e.message, true);
    }
}

function closeSkillModal() {
    document.getElementById('skill-modal').style.display = 'none';
}

async function viewGameSkillContent(gameId) {
    try {
        const data = await fetchJsonOrThrow('/api/games/' + encodeURIComponent(gameId) + '/content');
        const modal = document.getElementById('skill-modal');
        document.getElementById('skill-modal-title').textContent = data.id || gameId;
        document.getElementById('skill-modal-content').textContent = data.content || 'No content available';
        document.getElementById('skill-modal-files').innerHTML = data.files && data.files.length
            ? '<strong>Files:</strong> ' + data.files.map(f => escapeHtml(f)).join(', ')
            : '';
        modal.style.display = 'flex';
    } catch (e) {
        showToast('Failed to load game skill content', true);
        log('err', 'Failed to load game skill content: ' + e.message, true);
    }
}

async function toggleSkill(skillId, enable) {
    try {
        log('req', `POST /api/skills/toggle {skill_id: ${skillId}, enabled: ${enable}}`);
        await fetchJsonOrThrow('/api/skills/toggle', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ skill_id: skillId, enabled: enable })
        });
        log('res', `Skill ${skillId} ${enable ? 'enabled' : 'disabled'}`);
        showToast(enable ? 'Skill enabled' : 'Skill disabled');
        invalidateCache('/api/skills');
        loadSkills();
    } catch (e) {
        showToast(`Skill update failed: ${e.message}`, true);
        log('err', `Skill update failed: ${e.message}`, true);
    }
}

let capabilityRows = [];
let selectedCapabilityId = '';

function capabilityKindLabel(kind) {
    return ({ skill: 'Skill', toolset: 'Toolset', mcp_server: 'MCP server', plugin: 'Plugin' })[kind] || kind;
}

function capabilityKindColor(kind) {
    return ({ skill: '#eab308', toolset: '#06b6d4', mcp_server: '#a855f7', plugin: '#f97316' })[kind] || '#6b7280';
}

async function loadCapabilities(force = false) {
    const grid = document.getElementById('capability-grid');
    if (!grid) return;
    grid.innerHTML = '<div class="empty-state">Inspecting local capability manifests...</div>';
    try {
        if (force) invalidateCache('/api/capabilities');
        const data = await fetchJsonOrThrow('/api/capabilities');
        capabilityRows = Array.isArray(data.rows) ? data.rows : [];
        const counts = data.summary?.by_kind || {};
        const summary = document.getElementById('capability-summary');
        if (summary) {
            summary.innerHTML = ['skill', 'toolset', 'mcp_server', 'plugin'].map(kind => `
                <div class="capability-summary-card"><strong>${Number(counts[kind] || 0)}</strong><span>${escapeHtml(capabilityKindLabel(kind))}${Number(counts[kind] || 0) === 1 ? '' : 's'}</span></div>
            `).join('');
        }
        renderCapabilities();
    } catch (error) {
        grid.innerHTML = `<div class="empty-state">Capability inventory unavailable: ${escapeHtml(error.message || String(error))}</div>`;
    }
}

function renderCapabilities() {
    const grid = document.getElementById('capability-grid');
    if (!grid) return;
    const query = (document.getElementById('capability-search')?.value || '').trim().toLowerCase();
    const kind = document.getElementById('capability-kind')?.value || '';
    const state = document.getElementById('capability-state')?.value || '';
    const filtered = capabilityRows.filter(row => {
        if (kind && row.kind !== kind) return false;
        if (state === 'enabled' && row.states?.enabled !== true) return false;
        if (state === 'disabled' && row.states?.enabled !== false) return false;
        if (state === 'available' && row.states?.available !== true) return false;
        if (state === 'optional' && row.source?.kind !== 'optional_catalog') return false;
        if (!query) return true;
        const haystack = [row.name, row.description, row.kind, ...(row.capability_names || [])].join(' ').toLowerCase();
        return haystack.includes(query);
    });
    const stats = document.getElementById('capability-stats');
    if (stats) stats.textContent = `${filtered.length} of ${capabilityRows.length}`;
    if (!filtered.length) {
        grid.innerHTML = '<div class="empty-state">No capabilities match these filters.</div>';
        return;
    }
    grid.innerHTML = filtered.map((row, index) => {
        const installed = row.states?.installed;
        const enabled = row.states?.enabled;
        const status = installed === false ? 'optional' : enabled === true ? 'enabled' : enabled === false ? 'disabled' : 'detected';
        const configured = row.states?.configured === true ? '<span class="capability-badge good">configured</span>' : '';
        return `<button class="capability-card${row.id === selectedCapabilityId ? ' active' : ''}" type="button" data-capability-index="${capabilityRows.indexOf(row)}" style="--capability-color:${capabilityKindColor(row.kind)}">
            <div class="capability-card-head"><h3>${escapeHtml(row.name)}</h3><span class="capability-badge">${escapeHtml(capabilityKindLabel(row.kind))}</span></div>
            <p>${escapeHtml(row.description || 'No description supplied by this capability.')}</p>
            <div class="capability-badges"><span class="capability-badge ${status === 'enabled' ? 'good' : status === 'disabled' ? 'warn' : ''}">${status}</span>${configured}<span class="capability-badge">${(row.capability_names || []).length} exposed</span></div>
        </button>`;
    }).join('');
    grid.querySelectorAll('[data-capability-index]').forEach(button => {
        button.addEventListener('click', () => selectCapability(Number(button.dataset.capabilityIndex)));
    });
}

function selectCapability(index) {
    const row = capabilityRows[index];
    const detail = document.getElementById('capability-detail');
    if (!row || !detail) return;
    selectedCapabilityId = row.id;
    renderCapabilities();
    const capabilities = row.capability_names || [];
    const security = row.security && Object.keys(row.security).length ? row.security : null;
    const sourceKind = row.source?.kind === 'optional_catalog' ? 'Optional skill catalog' : (row.source?.kind || 'local');
    const skillId = row.details?.skill_id || row.name;
    const canManageSkill = row.kind === 'skill' && row.states?.installed === true && row.source?.kind !== 'optional_catalog';
    detail.innerHTML = `
        <span class="panel-kicker">${escapeHtml(capabilityKindLabel(row.kind))}</span>
        <h3>${escapeHtml(row.name)}</h3>
        <p>${escapeHtml(row.description || 'No description supplied.')}</p>
        <div class="capability-badges">
            ${Object.entries(row.states || {}).map(([name, value]) => `<span class="capability-badge ${value === true ? 'good' : value === false ? 'warn' : ''}">${escapeHtml(name)}: ${value === null ? 'unknown' : value ? 'yes' : 'no'}</span>`).join('')}
        </div>
        ${canManageSkill ? `<div class="capability-detail-section"><button class="btn primary" type="button" data-capability-skill-toggle>${row.states.enabled ? 'Disable skill' : 'Enable skill'}</button> <button class="btn" type="button" data-capability-skill-view>Read SKILL.md</button></div>` : ''}
        <div class="capability-detail-section"><h4>Exposed capabilities</h4><div class="capability-chip-list">${capabilities.length ? capabilities.map(name => `<span class="capability-badge">${escapeHtml(name)}</span>`).join('') : '<span class="file-viewer-meta">None declared</span>'}</div></div>
        <div class="capability-detail-section"><h4>Security and consent</h4>${security ? `<pre>${escapeHtml(JSON.stringify(security, null, 2))}</pre>` : '<p class="file-viewer-meta">No trust or permission metadata was declared.</p>'}</div>
        <div class="capability-detail-section"><h4>Source</h4><p class="file-viewer-meta">${escapeHtml(sourceKind)}${row.details?.version ? ` · version ${escapeHtml(row.details.version)}` : ''}${row.details?.transport ? ` · ${escapeHtml(row.details.transport)}` : ''}</p></div>
    `;
    detail.querySelector('[data-capability-skill-toggle]')?.addEventListener('click', async () => {
        await toggleSkill(skillId, !row.states.enabled);
        await loadCapabilities(true);
    });
    detail.querySelector('[data-capability-skill-view]')?.addEventListener('click', () => viewSkillContent(skillId));
}

let fileProjects = [];
let fileEntries = [];
let currentFileProject = '';
let currentFilePath = '';
let selectedFilePath = '';

function formatFileSize(value) {
    const bytes = Number(value);
    if (!Number.isFinite(bytes)) return '--';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(bytes < 10240 ? 1 : 0)} KB`;
    if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

function fileRefUrl(endpoint, ref, extra = {}) {
    const params = new URLSearchParams(extra);
    if (typeof ref === 'string') params.set('path', ref);
    else {
        params.set('project', ref.project_id || ref.project || '');
        params.set('path', ref.path || '');
    }
    return `${endpoint}?${params.toString()}`;
}

async function loadFileManager() {
    try {
        const data = await fetchJsonOrThrow('/api/files/projects');
        fileProjects = Array.isArray(data.projects) ? data.projects : [];
        const select = document.getElementById('file-project');
        if (!select) return;
        select.innerHTML = fileProjects.map(project => `<option value="${escapeHtml(project.id)}">${escapeHtml(project.label)}</option>`).join('');
        if (!currentFileProject || !fileProjects.some(project => project.id === currentFileProject)) {
            currentFileProject = fileProjects[0]?.id || '';
            currentFilePath = '';
        }
        select.value = currentFileProject;
        await loadFileDirectory();
    } catch (error) {
        const list = document.getElementById('file-list');
        if (list) list.innerHTML = `<div class="empty-state">File manager unavailable: ${escapeHtml(error.message || String(error))}</div>`;
    }
}

function selectFileProject(projectId) {
    currentFileProject = projectId;
    currentFilePath = '';
    selectedFilePath = '';
    void loadFileDirectory();
}

async function loadFileDirectory(path = currentFilePath) {
    if (!currentFileProject) return loadFileManager();
    const list = document.getElementById('file-list');
    if (list) list.innerHTML = '<div class="empty-state">Loading directory...</div>';
    try {
        const hidden = document.getElementById('files-show-hidden')?.checked ? 'true' : 'false';
        const data = await fetchJsonOrThrow(fileRefUrl('/api/files/list', { project_id: currentFileProject, path }, { hidden, limit: '500' }));
        currentFilePath = data.path || '';
        fileEntries = Array.isArray(data.entries) ? data.entries : [];
        selectedFilePath = '';
        renderFileBreadcrumbs();
        renderFileEntries();
        const up = document.getElementById('file-up-button');
        if (up) up.disabled = !currentFilePath;
    } catch (error) {
        if (list) list.innerHTML = `<div class="empty-state">Could not open directory: ${escapeHtml(error.message || String(error))}</div>`;
    }
}

function renderFileBreadcrumbs() {
    const host = document.getElementById('file-breadcrumbs');
    if (!host) return;
    const project = fileProjects.find(item => item.id === currentFileProject);
    const parts = currentFilePath ? currentFilePath.split('/') : [];
    const crumbs = [{ label: project?.label || currentFileProject, path: '' }];
    parts.forEach((part, index) => crumbs.push({ label: part, path: parts.slice(0, index + 1).join('/') }));
    host.innerHTML = crumbs.map((crumb, index) => `${index ? '<span>/</span>' : ''}<button type="button" data-file-crumb="${index}">${escapeHtml(crumb.label)}</button>`).join('');
    host.querySelectorAll('[data-file-crumb]').forEach(button => {
        button.addEventListener('click', () => loadFileDirectory(crumbs[Number(button.dataset.fileCrumb)].path));
    });
}

function openParentFileDirectory() {
    const parts = currentFilePath.split('/').filter(Boolean);
    parts.pop();
    void loadFileDirectory(parts.join('/'));
}

function renderFileEntries() {
    const list = document.getElementById('file-list');
    if (!list) return;
    const query = (document.getElementById('file-search')?.value || '').trim().toLowerCase();
    const entries = fileEntries.filter(entry => !query || entry.name.toLowerCase().includes(query));
    if (!entries.length) {
        list.innerHTML = '<div class="empty-state">This directory is empty or no files match.</div>';
        return;
    }
    list.innerHTML = entries.map((entry, index) => {
        const icon = entry.type === 'directory' ? '&#9656;' : entry.type === 'symlink' ? '&#8644;' : '&#9633;';
        const modified = entry.mtime ? new Date(entry.mtime * 1000).toLocaleString() : '--';
        return `<button class="file-entry${entry.path === selectedFilePath ? ' active' : ''}" type="button" role="option" data-file-entry="${fileEntries.indexOf(entry)}" aria-selected="${entry.path === selectedFilePath}">
            <span class="file-entry-name"><span class="file-entry-icon">${icon}</span>${escapeHtml(entry.name)}${entry.escaped ? ' (blocked)' : ''}</span>
            <span class="file-entry-meta">${entry.type === 'directory' ? 'folder' : formatFileSize(entry.size)}</span>
            <span class="file-entry-meta">${escapeHtml(modified)}</span>
        </button>`;
    }).join('');
    list.querySelectorAll('[data-file-entry]').forEach(button => {
        button.addEventListener('click', () => openFileEntry(fileEntries[Number(button.dataset.fileEntry)]));
    });
}

function openFileEntry(entry) {
    if (!entry || entry.escaped) return;
    if (entry.type === 'directory') {
        void loadFileDirectory(entry.path);
        return;
    }
    selectedFilePath = entry.path;
    renderFileEntries();
    void renderUniversalFileViewer({ project_id: currentFileProject, path: entry.path }, document.getElementById('file-viewer'));
}

async function renderUniversalFileViewer(ref, host, options = {}) {
    if (!host) return;
    host.innerHTML = '<div class="empty-state">Inspecting file...</div>';
    try {
        const meta = await fetchJsonOrThrow(fileRefUrl('/api/files/meta', ref));
        const normalizedRef = { project_id: meta.project_id, path: meta.path };
        const rawUrl = fileRefUrl('/api/files/raw', normalizedRef);
        const downloadUrl = fileRefUrl('/api/files/download', normalizedRef);
        host.innerHTML = `<div class="file-viewer-header">
            <div><span class="panel-kicker">${escapeHtml(meta.kind || 'file')}</span><h3>${escapeHtml(meta.name || meta.path)}</h3><div class="file-viewer-meta">${escapeHtml(meta.mime || 'unknown type')} · ${formatFileSize(meta.size)} · ${escapeHtml(meta.path || '')}</div></div>
            <div class="file-viewer-actions"><a class="btn" href="${escapeHtml(rawUrl)}" target="_blank" rel="noopener">Open raw</a><a class="btn primary" href="${escapeHtml(downloadUrl)}">Download</a></div>
        </div><div class="file-viewer-content"></div>`;
        const content = host.querySelector('.file-viewer-content');
        if (meta.kind === 'image') {
            content.innerHTML = `<img src="${escapeHtml(rawUrl)}" alt="${escapeHtml(meta.name)}">`;
        } else if (meta.kind === 'pdf') {
            content.innerHTML = `<iframe src="${escapeHtml(rawUrl)}" title="${escapeHtml(meta.name)} PDF preview"></iframe>`;
        } else if (meta.kind === 'audio') {
            content.innerHTML = `<audio controls preload="metadata" src="${escapeHtml(rawUrl)}"></audio>`;
        } else if (meta.kind === 'video') {
            content.innerHTML = `<video controls preload="metadata" src="${escapeHtml(rawUrl)}"></video>`;
        } else {
            const limit = ['text', 'code', 'json', 'markdown'].includes(meta.kind) ? 262144 : 65536;
            const preview = await fetchJsonOrThrow(fileRefUrl('/api/files/preview', normalizedRef, { limit: String(limit) }));
            if (meta.kind === 'archive') {
                const entries = Array.isArray(preview.entries) ? preview.entries : [];
                content.innerHTML = `${preview.format === 'unsupported' ? '<div class="file-warning">Archive listing is unavailable for this format. The file can still be downloaded.</div>' : ''}<ul class="file-archive-list">${entries.map(entry => `<li><span>${entry.unsafe_path ? '&#9888; ' : ''}${escapeHtml(entry.name)}</span><span>${formatFileSize(entry.size)}</span></li>`).join('')}</ul>${preview.truncated ? `<div class="file-warning">Showing ${entries.length} of ${preview.total} entries.</div>` : ''}`;
            } else if (preview.content !== undefined) {
                const pre = document.createElement('pre');
                pre.textContent = preview.content;
                content.replaceChildren(pre);
                if (preview.truncated) content.insertAdjacentHTML('beforeend', `<div class="file-warning">Preview is limited to ${formatFileSize(preview.bytes)}. Download the file for complete contents.</div>`);
            } else {
                content.innerHTML = `<div class="file-warning">This format has no safe inline renderer. A bounded binary view is shown below.</div><div class="file-binary-grid"><pre>${escapeHtml(preview.hex || '')}</pre><pre>${escapeHtml(preview.ascii || '')}</pre></div>${preview.truncated ? '<div class="file-viewer-meta">Binary preview truncated.</div>' : ''}`;
            }
        }
        if (options.metaHost) options.metaHost.innerHTML = `<span>Size: <span class="val">${formatFileSize(meta.size)}</span></span><span>Type: <span class="val">${escapeHtml(meta.kind)}</span></span>`;
    } catch (error) {
        host.innerHTML = `<div class="empty-state">Could not display this file: ${escapeHtml(error.message || String(error))}</div>`;
        if (options.metaHost) options.metaHost.textContent = 'Preview unavailable';
    }
}

const HermesRogue = (() => {
    const WIDTH = 21;
    const HEIGHT = 15;
    const STORE = 'hermesRogue.';
    const TILE_LABELS = { '#': 'Wall', '.': 'Floor', '>': 'Exit Kernel', '✦': 'Memory Shard', '⚿': 'Cache Key', '+': 'Health Patch', '◇': 'Focus Crystal', 'T': 'Tool Shrine', 'L': 'Lock Gate' };
    let state = null;
    let initialized = false;

    function stringSeed(input) {
        const value = String(input || Date.now()).trim();
        if (/^\d+$/.test(value)) return Number(value) >>> 0;
        let h = 2166136261;
        for (let i = 0; i < value.length; i++) {
            h ^= value.charCodeAt(i);
            h = Math.imul(h, 16777619);
        }
        return h >>> 0;
    }

    function mulberry32(seed) {
        return function() {
            let t = seed += 0x6D2B79F5;
            t = Math.imul(t ^ t >>> 15, t | 1);
            t ^= t + Math.imul(t ^ t >>> 7, t | 61);
            return ((t ^ t >>> 14) >>> 0) / 4294967296;
        };
    }

    function getMetric(name) {
        return Number(localStorage.getItem(STORE + name) || 0);
    }

    function setMetric(name, value) {
        localStorage.setItem(STORE + name, String(value));
    }

    function idx(x, y) { return y * WIDTH + x; }
    function inBounds(x, y) { return x >= 0 && y >= 0 && x < WIDTH && y < HEIGHT; }
    function tileAt(x, y) { return state.floor.tiles[idx(x, y)]; }
    function setTile(x, y, tile) { state.floor.tiles[idx(x, y)] = tile; }
    function randInt(rng, min, max) { return Math.floor(rng() * (max - min + 1)) + min; }
    function manhattan(a, b) { return Math.abs(a.x - b.x) + Math.abs(a.y - b.y); }
    function passable(tile) { return tile !== '#' && tile !== 'L'; }

    function log(message) {
        if (!state) return;
        state.log.unshift(message);
        state.log = state.log.slice(0, 8);
    }

    function reachableFrom(start, tiles) {
        const seen = new Set([idx(start.x, start.y)]);
        const queue = [start];
        while (queue.length) {
            const p = queue.shift();
            for (const [dx, dy] of [[1,0],[-1,0],[0,1],[0,-1]]) {
                const nx = p.x + dx, ny = p.y + dy, key = idx(nx, ny);
                if (!inBounds(nx, ny) || seen.has(key) || tiles[key] === '#') continue;
                seen.add(key);
                queue.push({ x: nx, y: ny });
            }
        }
        return seen;
    }

    function randomFloorCell(rng, occupied = new Set()) {
        const floors = [];
        for (let y = 1; y < HEIGHT - 1; y++) {
            for (let x = 1; x < WIDTH - 1; x++) {
                const key = idx(x, y);
                if (tileAt(x, y) === '.' && !occupied.has(key)) floors.push({ x, y });
            }
        }
        return floors[Math.floor(rng() * floors.length)] || { x: 10, y: 7 };
    }

    function place(tile, count, rng, occupied, avoidStart = false) {
        for (let i = 0; i < count; i++) {
            let p = null;
            for (let tries = 0; tries < 60; tries++) {
                const candidate = randomFloorCell(rng, occupied);
                if (!avoidStart || manhattan(candidate, { x: 10, y: 7 }) > 3) { p = candidate; break; }
            }
            if (!p) continue;
            setTile(p.x, p.y, tile);
            occupied.add(idx(p.x, p.y));
        }
    }

    function generateFloor(depth) {
        const rng = state.rng;
        for (let attempt = 0; attempt < 20; attempt++) {
            const tiles = Array(WIDTH * HEIGHT).fill('#');
            let x = Math.floor(WIDTH / 2), y = Math.floor(HEIGHT / 2);
            tiles[idx(x, y)] = '.';
            const steps = randInt(rng, 240, 330);
            for (let i = 0; i < steps; i++) {
                const dir = [[1,0],[-1,0],[0,1],[0,-1]][randInt(rng, 0, 3)];
                x = Math.max(1, Math.min(WIDTH - 2, x + dir[0]));
                y = Math.max(1, Math.min(HEIGHT - 2, y + dir[1]));
                tiles[idx(x, y)] = '.';
                if (rng() < 0.2) {
                    tiles[idx(Math.max(1, Math.min(WIDTH - 2, x + randInt(rng, -1, 1))), Math.max(1, Math.min(HEIGHT - 2, y + randInt(rng, -1, 1))))] = '.';
                }
            }
            const seen = reachableFrom({ x: 10, y: 7 }, tiles);
            if (seen.size < 85) continue;
            state.player.x = 10; state.player.y = 7;
            state.floor = { tiles, enemies: [] };
            let farthest = { x: 10, y: 7, d: 0 };
            for (const key of seen) {
                const px = key % WIDTH, py = Math.floor(key / WIDTH), d = manhattan({ x: 10, y: 7 }, { x: px, y: py });
                if (d > farthest.d) farthest = { x: px, y: py, d };
            }
            const occupied = new Set([idx(10, 7), idx(farthest.x, farthest.y)]);
            setTile(farthest.x, farthest.y, '>');
            const spec = depth === 1 ? { shards: 3, hp: 1, focus: 1, keys: 0, shrines: 0, gates: 0, bugs: 2, wraiths: 0 }
                : depth === 2 ? { shards: 4, hp: 1, focus: 0, keys: 1, shrines: 1, gates: 1, bugs: 3, wraiths: 1 }
                : { shards: 5, hp: 1, focus: 0, keys: 1, shrines: 1, gates: 2, bugs: 4, wraiths: 2 };
            place('✦', spec.shards, rng, occupied);
            place('+', spec.hp, rng, occupied);
            place('◇', spec.focus, rng, occupied);
            place('⚿', spec.keys, rng, occupied);
            place('T', spec.shrines, rng, occupied);
            place('L', spec.gates, rng, occupied);
            for (let i = 0; i < spec.bugs; i++) {
                const p = randomFloorCell(rng, occupied); occupied.add(idx(p.x, p.y));
                state.floor.enemies.push({ x: p.x, y: p.y, hp: 2, kind: 'entropy', symbol: 'e', damage: 1 });
            }
            for (let i = 0; i < spec.wraiths; i++) {
                const p = randomFloorCell(rng, occupied); occupied.add(idx(p.x, p.y));
                state.floor.enemies.push({ x: p.x, y: p.y, hp: 3, kind: 'drift', symbol: 'd', damage: 2, slow: 0 });
            }
            return;
        }
        const tiles = Array(WIDTH * HEIGHT).fill('#');
        for (let yy = 1; yy < HEIGHT - 1; yy++) for (let xx = 1; xx < WIDTH - 1; xx++) tiles[idx(xx, yy)] = '.';
        state.player.x = 10; state.player.y = 7;
        state.floor = { tiles, enemies: [{ x: 5, y: 5, hp: 2, kind: 'entropy', symbol: 'e', damage: 1 }] };
        setTile(18, 12, '>'); setTile(7, 6, '✦'); setTile(12, 8, '+');
    }

    function newRun(seed) {
        const seedInt = stringSeed(seed || Date.now());
        state = {
            seed: seedInt,
            rng: mulberry32(seedInt),
            player: { x: 10, y: 7 },
            hp: 10, maxHp: 10, focus: 3, keys: 0, shards: 0, depth: 1, turns: 0,
            status: 'running', log: [], finalSummary: ''
        };
        generateFloor(1);
        log('Run initialized. Hermes enters the Labyrinth.');
        setMetric('lastSeed', seedInt);
        render();
        focusMap();
    }

    function enemyAt(x, y) {
        return state.floor.enemies.find(enemy => enemy.x === x && enemy.y === y);
    }

    function classFor(tile, enemy, playerHere) {
        if (playerHere) return 'rogue-player';
        if (enemy) return 'rogue-enemy';
        if (tile === '#') return 'rogue-wall';
        if (tile === '>') return 'rogue-exit';
        if (tile === 'T') return 'rogue-shrine';
        if (tile === 'L') return 'rogue-gate';
        if (tile !== '.') return 'rogue-item';
        return 'rogue-floor';
    }

    function labelFor(tile, enemy, playerHere, x, y) {
        if (playerHere) return `Hermes at ${x},${y}`;
        if (enemy) return `${enemy.kind === 'drift' ? 'Drift Wraith' : 'Entropy Bug'} at ${x},${y}`;
        return `${TILE_LABELS[tile] || 'Floor'} at ${x},${y}`;
    }

    function render() {
        const map = document.getElementById('rogue-map');
        if (!map || !state) return;
        const cells = [];
        for (let y = 0; y < HEIGHT; y++) {
            for (let x = 0; x < WIDTH; x++) {
                const enemy = enemyAt(x, y);
                const playerHere = state.player.x === x && state.player.y === y;
                const tile = tileAt(x, y);
                const symbol = playerHere ? '@' : enemy ? enemy.symbol : tile === '.' ? '' : tile;
                cells.push(`<div class="rogue-cell ${classFor(tile, enemy, playerHere)}" role="gridcell" data-x="${x}" data-y="${y}" data-tile="${playerHere ? 'player' : enemy ? enemy.kind : tile}" aria-label="${labelFor(tile, enemy, playerHere, x, y)}">${symbol}</div>`);
            }
        }
        map.innerHTML = cells.join('');
        const values = {
            'rogue-depth': state.depth,
            'rogue-hp': `${state.hp}/${state.maxHp}`,
            'rogue-focus': state.focus,
            'rogue-keys': state.keys,
            'rogue-shards': state.shards,
            'rogue-turns': state.turns,
            'rogue-best': getMetric('bestDepth'),
            'rogue-record': `${getMetric('wins')}/${getMetric('losses')}`
        };
        Object.entries(values).forEach(([id, value]) => { const el = document.getElementById(id); if (el) el.textContent = value; });
        const tile = tileAt(state.player.x, state.player.y);
        const tileEl = document.getElementById('rogue-tile');
        if (tileEl) tileEl.textContent = `Tile: ${TILE_LABELS[tile] || 'Floor'} (${state.player.x},${state.player.y})`;
        const inv = document.getElementById('rogue-inventory');
        if (inv) inv.textContent = `Inventory: ${state.keys} cache key(s), ${state.focus} focus, seed ${state.seed}.`;
        const logEl = document.getElementById('rogue-log');
        if (logEl) logEl.textContent = state.log.join('\n');
        const live = document.getElementById('rogue-live-status');
        if (live) live.textContent = state.log[0] || 'Ready.';
    }

    function focusMap() {
        const map = document.getElementById('rogue-map');
        if (map) map.focus({ preventScroll: true });
    }

    function resolveTile(tile, nx, ny) {
        if (tile === '✦') { state.shards += 1; setTile(nx, ny, '.'); log('Recovered a memory shard.'); }
        else if (tile === '⚿') { state.keys += 1; setTile(nx, ny, '.'); log('Found a cache key.'); }
        else if (tile === '+') { state.hp = Math.min(state.maxHp, state.hp + 4); setTile(nx, ny, '.'); log('Applied a health patch.'); }
        else if (tile === '◇') { state.focus += 2; setTile(nx, ny, '.'); log('Focus restored.'); }
        else if (tile === '>') {
            if (state.depth >= 3) {
                if (state.shards >= 6) winRun();
                else log('The Exit Kernel rejects the run: collect 6 memory shards.');
            } else {
                state.depth += 1;
                setMetric('bestDepth', Math.max(getMetric('bestDepth'), state.depth));
                generateFloor(state.depth);
                log(`Descended to depth ${state.depth}.`);
            }
        }
    }

    function spendTurn() {
        state.turns += 1;
        enemyTurn();
        checkWinLoss();
        render();
    }

    function tryMove(dx, dy) {
        if (!state || state.status !== 'running') return;
        const nx = state.player.x + dx, ny = state.player.y + dy;
        if (!inBounds(nx, ny)) return;
        const targetEnemy = enemyAt(nx, ny);
        if (targetEnemy) {
            targetEnemy.hp -= 1;
            if (targetEnemy.hp <= 0) {
                state.floor.enemies = state.floor.enemies.filter(enemy => enemy !== targetEnemy);
                log(targetEnemy.kind === 'drift' ? 'Drift wraith anchored.' : 'Entropy bug patched.');
            } else {
                log('Hermes patches hostile entropy.');
            }
            spendTurn(); return;
        }
        const tile = tileAt(nx, ny);
        if (tile === '#') { log('Wall: not a productive path.'); render(); return; }
        if (tile === 'L') {
            if (state.keys > 0) { state.keys -= 1; setTile(nx, ny, '.'); log('Cache key consumed. Gate opened.'); }
            else { log('The lock gate needs a cache key.'); render(); return; }
        }
        if (tile === 'T') {
            if (state.focus > 0) {
                state.focus -= 1;
                if (state.floor.enemies.length) { state.floor.enemies.shift(); log('Tool Shrine terminates a hostile process.'); }
                else { state.hp = Math.min(state.maxHp, state.hp + 2); log('Tool Shrine stabilizes coherence.'); }
            } else log('No focus available to invoke the shrine.');
            spendTurn(); return;
        }
        state.player.x = nx; state.player.y = ny;
        resolveTile(tile, nx, ny);
        if (state.status === 'running') spendTurn(); else render();
    }

    function waitTurn() {
        if (!state || state.status !== 'running') return;
        log('Hermes waits and listens for drift.');
        spendTurn();
    }

    function enemyTurn() {
        for (const enemy of [...state.floor.enemies]) {
            if (manhattan(enemy, state.player) === 1) { state.hp -= enemy.damage; log(`${enemy.kind === 'drift' ? 'Drift wraith' : 'Entropy bug'} hits for ${enemy.damage}.`); continue; }
            if (enemy.kind === 'drift') { enemy.slow = (enemy.slow || 0) + 1; if (enemy.slow % 2) continue; }
            const chase = manhattan(enemy, state.player) <= 6;
            const options = [[1,0],[-1,0],[0,1],[0,-1]].map(([dx, dy]) => ({ x: enemy.x + dx, y: enemy.y + dy }));
            const valid = options.filter(p => inBounds(p.x, p.y) && passable(tileAt(p.x, p.y)) && !enemyAt(p.x, p.y) && !(p.x === state.player.x && p.y === state.player.y));
            if (!valid.length) continue;
            valid.sort((a, b) => chase ? manhattan(a, state.player) - manhattan(b, state.player) : state.rng() - 0.5);
            enemy.x = valid[0].x; enemy.y = valid[0].y;
            if (manhattan(enemy, state.player) === 1) { state.hp -= enemy.damage; log(`${enemy.kind === 'drift' ? 'Drift wraith' : 'Entropy bug'} corrupts ${enemy.damage} HP.`); }
        }
    }

    function checkWinLoss() {
        if (state.status !== 'running') return;
        if (state.hp <= 0) {
            state.hp = 0;
            state.status = 'lost';
            setMetric('losses', getMetric('losses') + 1);
            state.finalSummary = `Hermes Labyrinth loss — turns: ${state.turns}, shards: ${state.shards}, depth: ${state.depth}, seed: ${state.seed}`;
            log('Run lost: coherence collapsed.');
        }
    }

    function winRun() {
        state.status = 'won';
        setMetric('wins', getMetric('wins') + 1);
        setMetric('bestDepth', Math.max(getMetric('bestDepth'), state.depth));
        state.finalSummary = `Hermes Labyrinth win — turns: ${state.turns}, shards: ${state.shards}, hp: ${state.hp}, seed: ${state.seed}`;
        log('Run complete: Hermes stabilized the Labyrinth.');
    }

    function handleKeydown(event) {
        if (!state) return;
        const tag = event.target && event.target.tagName ? event.target.tagName.toLowerCase() : '';
        if (['input', 'textarea', 'select'].includes(tag) || event.target?.isContentEditable) return;
        const active = document.getElementById('roguelike-panel')?.classList.contains('active');
        if (!active) return;
        const key = event.key.toLowerCase();
        const moves = { arrowup: [0,-1], w: [0,-1], k: [0,-1], arrowdown: [0,1], s: [0,1], j: [0,1], arrowleft: [-1,0], a: [-1,0], h: [-1,0], arrowright: [1,0], d: [1,0], l: [1,0] };
        if (moves[key]) { event.preventDefault(); tryMove(moves[key][0], moves[key][1]); }
        else if (key === ' ' || key === '.') { event.preventDefault(); waitTurn(); }
        else if (key === 'r') { event.preventDefault(); newRun(); }
        else if (key === '?') { event.preventDefault(); toggleHelp(); }
    }

    function toggleHelp() {
        document.getElementById('rogue-help')?.classList.toggle('visible');
    }

    function copySummary() {
        if (!state) return;
        const summary = state.finalSummary || `Hermes Labyrinth run — turns: ${state.turns}, shards: ${state.shards}, hp: ${state.hp}, depth: ${state.depth}, seed: ${state.seed}`;
        if (navigator.clipboard?.writeText) navigator.clipboard.writeText(summary).then(() => showToast('Roguelike summary copied'));
        else window.prompt('Copy summary', summary);
    }

    function init() {
        if (initialized) { render(); focusMap(); return; }
        initialized = true;
        document.getElementById('rogue-new-run')?.addEventListener('click', () => newRun());
        document.getElementById('rogue-seeded-run')?.addEventListener('click', () => {
            const seed = window.prompt('Seed for Hermes Labyrinth?', localStorage.getItem(STORE + 'lastSeed') || 'hermes');
            if (seed !== null) newRun(seed);
        });
        document.getElementById('rogue-help-toggle')?.addEventListener('click', toggleHelp);
        document.getElementById('rogue-copy-summary')?.addEventListener('click', copySummary);
        document.querySelectorAll('[data-rogue-move]').forEach(button => button.addEventListener('click', () => {
            const [dx, dy] = button.dataset.rogueMove.split(',').map(Number);
            tryMove(dx, dy); focusMap();
        }));
        document.querySelectorAll('[data-rogue-wait]').forEach(button => button.addEventListener('click', () => { waitTurn(); focusMap(); }));
        document.addEventListener('keydown', handleKeydown);
        newRun(localStorage.getItem(STORE + 'lastSeed') || Date.now());
    }

    return { init, newRun, generateFloor, enemyTurn, checkWinLoss, handleKeydown, move: tryMove, wait: waitTurn, getState: () => state };
})();
window.HermesRogue = HermesRogue;

function initRoguelike() { HermesRogue.init(); }

let allGames = [];

async function loadGames() {
    const list = document.getElementById('games-list');
    const stats = document.getElementById('games-stats');
    try {
        log('req', 'GET /api/games');
        const data = await fetchJsonOrThrow('/api/games');
        allGames = data.games || [];
        if (stats) stats.textContent = `${allGames.length} game ${allGames.length === 1 ? 'launcher' : 'launchers'}`;
        renderGames(allGames);
        log('res', `Loaded ${allGames.length} games`);
    } catch (e) {
        if (stats) stats.textContent = '';
        if (list) list.innerHTML = '<div style="text-align:center;color:var(--danger);padding:2rem;">Failed to load games</div>';
        showToast(`Games load failed: ${e.message}`, true);
        log('err', `Games load failed: ${e.message}`, true);
    }
}

function openGameWatch(url) {
    const frame = document.getElementById('games-watch-frame');
    if (!frame || !url) return;
    if (location.hash !== '#games') {
        history.replaceState(null, '', '#games');
    }
    frame.src = url;
    frame.style.display = 'block';
    frame.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

async function restartPokemonAgent() {
    const btn = document.getElementById('pokemon-restart-btn');
    const previousText = btn ? btn.textContent : '';
    if (!confirm('Restart the local Pokémon agent and autoplayer? This briefly interrupts the live game dashboard.')) return;
    try {
        if (btn) {
            btn.disabled = true;
            btn.textContent = 'Restarting…';
        }
        log('req', 'POST /api/pokemon/restart');
        const data = await fetchJsonOrThrow('/api/pokemon/restart', { method: 'POST' });
        const serverPid = data.started && data.started.server_pid ? ` server pid ${data.started.server_pid}` : '';
        showToast(`Pokémon restart requested${serverPid}`);
        log('res', `Pokémon restart requested: ${JSON.stringify(data.started || {})}`);
        setTimeout(() => {
            const frame = document.getElementById('games-watch-frame');
            if (frame && frame.style.display !== 'none' && frame.src && frame.src.includes('/pokemon/')) {
                frame.src = frame.src;
            }
            loadGames();
        }, 2500);
    } catch (e) {
        showToast(`Pokémon restart failed: ${e.message}`, true);
        log('err', `Pokémon restart failed: ${e.message}`, true);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.textContent = previousText || 'Restart Pokémon Agent';
        }
    }
}

function renderGames(games) {
    const list = document.getElementById('games-list');
    if (!list) return;
    if (!games.length) {
        list.innerHTML = '<div style="text-align:center;color:var(--text-dim);padding:2rem;">No gaming skills installed yet.</div>';
        return;
    }
    list.innerHTML = games.map(game => {
        const tags = (game.tags || []).map(tag => `<span class="tag">${escapeHtml(tag)}</span>`).join(' ');
        const uploadLabel = game.upload_label || 'Upload / Choose ROM';
        const uploadButton = game.upload_url
            ? `<button class="btn primary" onclick="openGameWatch('${escapeHtml(game.upload_url)}')">${escapeHtml(uploadLabel)}</button>`
            : '';
        const uploadTabLink = game.upload_url
            ? `<a class="btn" href="${escapeHtml(game.upload_url)}" target="_blank" rel="noopener noreferrer">Open Upload New Tab</a>`
            : '';
        const watchLabel = game.launch_label || `Open ${game.name || 'Dashboard'}`;
        const watchButton = game.watch_url
            ? `<button class="btn" onclick="openGameWatch('${escapeHtml(game.watch_url)}')">${escapeHtml(watchLabel)}</button>`
            : '';
        const watchTabLink = game.watch_url
            ? `<a class="btn" href="${escapeHtml(game.watch_url)}" target="_blank" rel="noopener noreferrer">Open Watch New Tab</a>`
            : '';
        const controlLabel = game.control_label || 'Open Controls';
        const controlButton = game.control_url
            ? `<button class="btn" onclick="openGameWatch('${escapeHtml(game.control_url)}')">${escapeHtml(controlLabel)}</button>`
            : '';
        const controlTabLink = game.control_url
            ? `<a class="btn" href="${escapeHtml(game.control_url)}" target="_blank" rel="noopener noreferrer">Open Control New Tab</a>`
            : '';
        return `
            <div class="skill-card">
                <div class="skill-info" onclick="viewGameSkillContent('${escapeHtml(game.id)}')" style="cursor:pointer;">
                    <h4>${escapeHtml(game.name || game.id)}</h4>
                    <p>${escapeHtml(game.description || 'No description')}</p>
                    <div style="display:flex;gap:0.35rem;flex-wrap:wrap;margin-top:0.5rem;">${tags}</div>
                    <span style="font-size:0.7rem;color:var(--text-dim);display:block;margin-top:0.5rem;">${escapeHtml(game.category || 'Tool')} · ${escapeHtml(game.id)}</span>
                </div>
                <div style="display:flex;gap:0.5rem;flex-wrap:wrap;align-items:center;justify-content:flex-end;">
                    ${uploadButton}
                    ${uploadTabLink}
                    ${watchButton}
                    ${watchTabLink}
                    ${controlButton}
                    ${controlTabLink}
                    <button class="btn" onclick="viewGameSkillContent('${escapeHtml(game.id)}')">Open Skill</button>
                </div>
            </div>
        `;
    }).join('');
}

let dndCampaigns = [];
let selectedDndCampaignId = null;
let selectedDndCampaign = null;
let selectedDndEvents = [];
let selectedDndEventFilter = '';
let selectedDndEventOrder = 'asc';
let dndAutoTurnJobId = null;
let dndAutoTurnJobCampaignId = null;
let dndAutoTurnPollTimer = null;
let dndTurnProgress = [];

function openDndPopout() {
    const suffix = selectedDndCampaignId ? `?campaign=${encodeURIComponent(selectedDndCampaignId)}&popout=1#dnd` : '?popout=1#dnd';
    window.open('/dnd/popout' + suffix, 'hermes-dnd-dashboard', 'popup,width=1500,height=940,noopener,noreferrer');
}

function applyDndPopoutMode() {
    const params = new URLSearchParams(window.location.search || '');
    const path = window.location.pathname || '';
    const isPopout = params.get('popout') === '1' || path.startsWith('/dnd/popout');
    if (!isPopout) return;
    document.body.classList.add('dnd-popout-mode');
    if (location.hash !== '#dnd') history.replaceState(null, '', window.location.pathname + window.location.search + '#dnd');
    const campaignId = params.get('campaign');
    setTimeout(async () => {
        await loadDndCampaigns();
        if (campaignId) await selectDndCampaign(encodeURIComponent(campaignId));
    }, 50);
}

function dndAttr(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
}

function dndEncodedId(value) {
    return encodeURIComponent(String(value ?? '')).replace(/'/g, '%27');
}

function dndArrayFromResponse(data, key) {
    if (Array.isArray(data)) return data;
    if (Array.isArray(data?.[key])) return data[key];
    if (Array.isArray(data?.items)) return data.items;
    return [];
}

function dndCampaignFromResponse(data) {
    return data?.campaign || data?.item || data || null;
}

function dndCampaignId(campaign) {
    return campaign?.id || campaign?.campaign_id || campaign?.uuid || '';
}

function dndCampaignEvents(campaign, explicitEvents = []) {
    if (Array.isArray(explicitEvents) && explicitEvents.length) return explicitEvents;
    if (Array.isArray(campaign?.events)) return campaign.events;
    if (Array.isArray(campaign?.action_log)) return campaign.action_log;
    if (Array.isArray(campaign?.log)) return campaign.log;
    return [];
}

function dndSceneSummary(campaign) {
    const scene = campaign?.current_scene || campaign?.scene || campaign?.scene_summary;
    if (!scene) return 'No scene established yet.';
    if (typeof scene === 'string') return scene;
    return [
        scene.summary || '',
        scene.location ? `Location: ${scene.location}` : '',
        scene.mood ? `Mood: ${scene.mood}` : '',
        Array.isArray(scene.visible_threats) && scene.visible_threats.length ? `Visible threats: ${scene.visible_threats.join(', ')}` : '',
        Array.isArray(scene.open_questions) && scene.open_questions.length ? `Open questions: ${scene.open_questions.join('; ')}` : '',
    ].filter(Boolean).join('\n') || 'No scene established yet.';
}

function dndEventType(event) {
    return event?.event_type || event?.type || event?.kind || 'event';
}

function dndEventClass(event) {
    const type = dndEventType(event);
    if (type === 'dm_narration') return 'dnd-event-narration';
    if (type === 'player_action') return 'dnd-event-action';
    if (type === 'dice_roll') return 'dnd-event-dice';
    if (type === 'scene_update') return 'dnd-event-scene';
    if (type === 'subagent_status') return 'dnd-event-subagent';
    return 'dnd-event-generic';
}

function dndEventBody(event) {
    return (event && event.body) || event?.narration || event?.action || event?.content || event?.message || event?.summary || JSON.stringify(event || {});
}

function dndDicePayload(event) {
    return event?.payload || event?.roll || event?.details || {};
}

async function loadDndCampaigns() {
    const list = document.getElementById('dnd-campaign-list');
    const stats = document.getElementById('dnd-stats');
    try {
        if (list) list.innerHTML = '<div style="color:var(--text-dim);">Loading campaigns...</div>';
        log('req', 'GET /api/dnd/campaigns');
        const data = await fetchJsonOrThrow('/api/dnd/campaigns');
        dndCampaigns = dndArrayFromResponse(data, 'campaigns');
        if (stats) stats.textContent = `${dndCampaigns.length} campaign${dndCampaigns.length === 1 ? '' : 's'}`;
        renderDndCampaignList();
        if (!selectedDndCampaignId && dndCampaigns.length) {
            await selectDndCampaign(encodeURIComponent(dndCampaignId(dndCampaigns[0])));
        } else if (selectedDndCampaignId && dndCampaigns.some(c => dndCampaignId(c) === selectedDndCampaignId)) {
            renderDndCampaignList();
        }
        log('res', `Loaded ${dndCampaigns.length} D&D campaigns`);
        return dndCampaigns;
    } catch (e) {
        if (stats) stats.textContent = '';
        if (list) list.innerHTML = `<div style="color:var(--error);padding:1rem;">Failed to load campaigns: ${escapeHtml(e.message)}</div>`;
        showToast(`Campaigns load failed: ${e.message}`, true);
        log('err', `Campaigns load failed: ${e.message}`, true);
        return [];
    }
}

function renderDndCampaignList() {
    const list = document.getElementById('dnd-campaign-list');
    if (!list) return;
    if (!dndCampaigns.length) {
        list.innerHTML = '<div style="color:var(--text-dim);padding:1rem 0;">No campaigns yet. Create one above.</div>';
        return;
    }
    list.innerHTML = dndCampaigns.map(campaign => {
        const id = dndCampaignId(campaign);
        const turn = campaign.turn_number ?? campaign.turn_index ?? campaign.turn ?? campaign.current_turn ?? 0;
        const playerCount = (campaign.players || campaign.roster || []).length || campaign.player_count || 0;
        return `
            <div class="message-board-post-card ${id === selectedDndCampaignId ? 'active' : ''}" onclick="selectDndCampaign('${dndEncodedId(id)}')">
                <h4>${escapeHtml(campaign.name || campaign.title || id || 'Untitled Campaign')}</h4>
                <div class="message-board-meta">
                    <span>turn ${escapeHtml(String(turn))}</span>
                    <span>${escapeHtml(String(playerCount))} players</span>
                    <span>${escapeHtml(campaign.status || campaign.phase || 'active')}</span>
                </div>
                ${campaign.current_scene || campaign.scene ? `<p style="color:var(--text-dim);font-size:0.82rem;margin-top:0.45rem;">${escapeHtml(dndSceneSummary(campaign))}</p>` : ''}
            </div>
        `;
    }).join('');
}

async function createDndCampaign(event) {
    if (event && typeof event.preventDefault === 'function') event.preventDefault();
    const nameEl = document.getElementById('dnd-campaign-name');
    const premiseEl = document.getElementById('dnd-campaign-premise');
    const submitEl = document.getElementById('dnd-create-submit');
    const toneEl = document.getElementById('dnd-campaign-tone');
    const systemEl = document.getElementById('dnd-campaign-system');
    const name = nameEl?.value?.trim() || '';
    const premise = premiseEl?.value?.trim() || '';
    const tone = toneEl?.value?.trim() || '';
    const system = systemEl?.value || 'dnd5e';
    if (!name) {
        showToast('Campaign name is required', true);
        return;
    }
    if (submitEl) {
        submitEl.disabled = true;
        submitEl.textContent = 'Creating...';
    }
    try {
        const payload = { name, premise, description: premise, tone, system, world_metadata: { tone, rules_profile_id: system } };
        log('req', 'POST /api/dnd/campaigns');
        const data = await fetchJsonOrThrow('/api/dnd/campaigns', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const campaign = dndCampaignFromResponse(data);
        selectedDndCampaignId = dndCampaignId(campaign);
        if (nameEl) nameEl.value = '';
        if (premiseEl) premiseEl.value = '';
        if (toneEl) toneEl.value = '';
        showToast('Campaign created');
        await loadDndCampaigns();
        if (selectedDndCampaignId) await selectDndCampaign(encodeURIComponent(selectedDndCampaignId));
    } catch (e) {
        showToast(`Campaign create failed: ${e.message}`, true);
        log('err', `Campaign create failed: ${e.message}`, true);
    } finally {
        if (submitEl) {
            submitEl.disabled = false;
            submitEl.textContent = 'Create Campaign';
        }
    }
}

async function selectDndCampaign(encodedCampaignId) {
    const campaignId = decodeURIComponent(encodedCampaignId || '');
    if (!campaignId) return;
    selectedDndCampaignId = campaignId;
    renderDndCampaignList();
    const detail = document.getElementById('dnd-campaign-detail');
    if (detail) detail.innerHTML = '<h4>Selected Campaign</h4><p style="color:var(--text-dim);">Loading campaign...</p>';
    try {
        log('req', `GET /api/dnd/campaigns/${campaignId}`);
        const data = await fetchJsonOrThrow(`/api/dnd/campaigns/${encodeURIComponent(campaignId)}`);
        selectedDndCampaign = {
            ...dndCampaignFromResponse(data),
            players: dndArrayFromResponse(data, 'players'),
            characters: dndArrayFromResponse(data, 'characters'),
        };
        selectedDndEvents = dndCampaignEvents(selectedDndCampaign, dndArrayFromResponse(data, 'events'));
        try {
            const eventData = await fetchJsonOrThrow(`/api/dnd/campaigns/${encodeURIComponent(campaignId)}/events`);
            selectedDndEvents = dndArrayFromResponse(eventData, 'events');
        } catch (eventError) {
            log('warn', `Campaign events fetch skipped/failed: ${eventError.message}`);
        }
        try {
            const worldData = await fetchJsonOrThrow(`/api/dnd/campaigns/${encodeURIComponent(campaignId)}/world/entities`);
            selectedDndCampaign.world_entities = dndArrayFromResponse(worldData, 'entities');
        } catch (worldError) {
            selectedDndCampaign.world_entities = selectedDndCampaign.world_entities || [];
            log('warn', `Campaign world entities fetch skipped/failed: ${worldError.message}`);
        }
        renderDndCampaign(selectedDndCampaign);
        log('res', `Loaded D&D campaign ${campaignId}`);
    } catch (e) {
        if (detail) detail.innerHTML = `<h4>Selected Campaign</h4><p style="color:var(--error);">Failed to load campaign: ${escapeHtml(e.message)}</p>`;
        showToast(`Campaign load failed: ${e.message}`, true);
        log('err', `Campaign load failed: ${e.message}`, true);
    }
}

function renderDndTurnProgress(job = null) {
    const container = document.getElementById('dnd-turn-progress-list');
    const summary = document.getElementById('dnd-turn-progress-summary');
    const pollStatus = document.getElementById('dnd-turn-poll-status');
    if (!container || !summary) return;
    const events = Array.isArray(job?.events) ? job.events : dndTurnProgress;
    dndTurnProgress = events;
    const phase = job?.progress?.phase || (dndAutoTurnJobId ? 'queued' : 'idle');
    const percent = job?.progress?.percent ?? (dndAutoTurnJobId ? 0 : 0);
    const terminalStatus = job?.status === 'completed' ? 'Turn complete' : (job?.status === 'failed' ? 'Turn failed' : '');
    summary.textContent = terminalStatus
        ? `${terminalStatus} — ${phase} (${percent}%)`
        : (dndAutoTurnJobId
            ? `Polling live turn... ${phase} (${percent}%)`
            : 'No live auto turn is currently running.');
    if (pollStatus) pollStatus.textContent = dndAutoTurnJobId ? `job ${dndAutoTurnJobId}` : 'idle';
    const subagentEvents = events.filter(event => event.type === 'subagent_status');
    const latestByPlayer = {};
    subagentEvents.forEach(event => {
        const key = event.player_id || event.player_name || event.index;
        latestByPlayer[key] = event;
    });
    const rows = Object.values(latestByPlayer);
    if (!rows.length) {
        container.innerHTML = dndAutoTurnJobId
            ? '<p style="color:var(--text-dim);">Thinking — waiting for subagent progress events...</p>'
            : '<p style="color:var(--text-dim);">Start a live auto turn to see Thinking → JSON received → Committed progress.</p>';
        return;
    }
    const labelFor = (status) => ({
        thinking: 'Thinking',
        json_received: 'JSON received',
        validated: 'Validated',
        committed: 'Committed',
        fallback_used: 'Fallback used',
    }[status] || status || 'Running');
    container.innerHTML = rows.map(event => `
        <div class="dnd-subagent-progress-row" data-player-id="${dndAttr(event.player_id || '')}" style="padding:0.55rem;border:1px solid var(--border-subtle);border-radius:9px;margin:0.4rem 0;background:rgba(255,255,255,0.03);">
            <div style="display:flex;justify-content:space-between;gap:0.5rem;align-items:center;">
                <strong class="dnd-subagent-progress-name">${escapeHtml(event.player_name || event.player_id || 'Subagent')}</strong>
                <span class="tag dnd-progress-stage" data-stage="${dndAttr(event.status || '')}">${escapeHtml(labelFor(event.status))}</span>
            </div>
            ${event.error ? `<div class="dnd-subagent-progress-error" style="color:var(--error);font-size:0.8rem;margin-top:0.35rem;">${escapeHtml(event.error)}</div>` : ''}
        </div>
    `).join('');
}

function updateDndAutoTurnButton(running) {
    const button = document.getElementById('dnd-auto-turn-btn');
    if (!button) return;
    button.disabled = Boolean(running);
    button.textContent = running ? 'Polling live turn...' : 'Run Live Auto Turn';
}

function stopDndAutoTurnPolling() {
    if (dndAutoTurnPollTimer) {
        clearTimeout(dndAutoTurnPollTimer);
        dndAutoTurnPollTimer = null;
    }
}

async function pollDndAutoTurnJob(campaignId = dndAutoTurnJobCampaignId, jobId = dndAutoTurnJobId) {
    if (!campaignId || !jobId) return;
    try {
        const data = await fetchJsonOrThrow(`/api/dnd/campaigns/${encodeURIComponent(campaignId)}/turns/auto/jobs/${encodeURIComponent(jobId)}`);
        const job = data.job || data;
        renderDndTurnProgress(job);
        if (job.status === 'completed') {
            stopDndAutoTurnPolling();
            renderDndTurnProgress(job);
            dndAutoTurnJobId = null;
            dndAutoTurnJobCampaignId = null;
            updateDndAutoTurnButton(false);
            showToast('Live auto turn complete');
            if (selectedDndCampaignId === campaignId) {
                await selectDndCampaign(encodeURIComponent(campaignId));
            }
            await loadDndCampaigns();
            return;
        }
        if (job.status === 'failed') {
            stopDndAutoTurnPolling();
            renderDndTurnProgress(job);
            dndAutoTurnJobId = null;
            dndAutoTurnJobCampaignId = null;
            updateDndAutoTurnButton(false);
            showToast(`Auto turn failed: ${job.error || 'unknown error'}`, true);
            return;
        }
        dndAutoTurnPollTimer = setTimeout(() => pollDndAutoTurnJob(campaignId, jobId), 900);
    } catch (e) {
        stopDndAutoTurnPolling();
        dndAutoTurnJobId = null;
        dndAutoTurnJobCampaignId = null;
        updateDndAutoTurnButton(false);
        showToast(`Auto turn polling failed: ${e.message}`, true);
        log('err', `D&D auto turn polling failed: ${e.message}`, true);
    }
}

function startDndAutoTurnPolling(campaignId, jobId, initialJob = null) {
    stopDndAutoTurnPolling();
    dndAutoTurnJobCampaignId = campaignId;
    dndAutoTurnJobId = jobId;
    dndTurnProgress = Array.isArray(initialJob?.events) ? initialJob.events : [];
    updateDndAutoTurnButton(true);
    renderDndTurnProgress(initialJob || { status: 'queued', progress: { phase: 'queued', percent: 0 }, events: dndTurnProgress });
    dndAutoTurnPollTimer = setTimeout(() => pollDndAutoTurnJob(campaignId, jobId), 250);
}

function renderDndCampaign(campaign) {
    const detail = document.getElementById('dnd-campaign-detail');
    if (!detail) return;
    if (!campaign) {
        detail.innerHTML = '<h4>Selected Campaign</h4><p style="color:var(--text-dim);">Select a campaign or create a new one.</p>';
        return;
    }
    const id = dndCampaignId(campaign);
    const players = campaign.players || campaign.roster || [];
    const characters = campaign.characters || [];
    const worldEntities = campaign.world_entities || campaign.entities || [];
    const worldState = campaign.world_state || {};
    const rawEvents = dndCampaignEvents(campaign, selectedDndEvents);
    const orderedEvents = selectedDndEventOrder === 'desc' ? [...rawEvents] : [...rawEvents].reverse();
    const events = selectedDndEventFilter ? orderedEvents.filter(event => dndEventType(event) === selectedDndEventFilter) : orderedEvents;
    const diceEvents = orderedEvents.filter(event => dndEventType(event) === 'dice_roll');
    const scene = dndSceneSummary(campaign);
    const turn = campaign.turn_number ?? campaign.turn_index ?? campaign.turn ?? campaign.current_turn ?? 0;
    const roster = players.length ? players.map(player => {
        const controller = player.controller_type || player.controller || (player.subagent_id ? 'subagent' : 'human');
        const badgeColor = controller === 'subagent' ? 'var(--purple)' : 'var(--info)';
        const status = player.status || player.last_action_source || (controller === 'subagent' ? 'idle/fallback-ready' : 'human');
        const prompt = player.agent_prompt || player.role || player.class_name || player.notes || player.description || '';
        const humanActionInput = controller === 'human' ? `
                <textarea class="dnd-human-action" data-player-id="${dndAttr(player.id || '')}" placeholder="Optional action for this human player before auto turn" style="margin-top:0.5rem;min-height:64px;"></textarea>
            ` : '';
        const subagentPrompt = controller === 'subagent' ? `
                <div class="dnd-subagent-status" style="color:var(--text-dim);font-size:0.8rem;margin-top:0.35rem;">Status: ${escapeHtml(status)}</div>
                <details class="dnd-subagent-prompt" style="margin-top:0.35rem;color:var(--text-dim);font-size:0.8rem;"><summary>Prompt</summary><div>${escapeHtml(prompt || 'No persona prompt yet.')}</div></details>
            ` : '';
        return `
            <div style="padding:0.65rem;border:1px solid var(--border-subtle);border-radius:10px;margin:0.45rem 0;background:rgba(255,255,255,0.03);">
                <div style="display:flex;justify-content:space-between;gap:0.5rem;align-items:center;">
                    <strong>${escapeHtml(player.name || player.character_name || player.id || 'Unnamed player')}</strong>
                    <span class="tag" style="border-color:${badgeColor};color:${badgeColor};">${escapeHtml(controller)}</span>
                </div>
                <div style="color:var(--text-dim);font-size:0.82rem;margin-top:0.25rem;">${escapeHtml(prompt)}</div>
                ${humanActionInput}
                ${subagentPrompt}
            </div>
        `;
    }).join('') : '<p style="color:var(--text-dim);">No players yet. Add a human or subagent controller below.</p>';
    const pendingRows = players.length ? players.map(player => {
        const controller = player.controller_type || player.controller || 'human';
        return `<li>${escapeHtml(player.name || 'Player')}: ${controller === 'human' ? 'waiting for optional human action' : 'subagent will choose an action'}</li>`;
    }).join('') : '<li>Add players to start a turn.</li>';
    const characterPlayerOptions = ['<option value="">No linked player</option>'].concat(players.map(player => `<option value="${dndAttr(player.id || '')}">${escapeHtml(player.name || player.id || 'Player')}</option>`)).join('');
    const characterRows = characters.length ? characters.map(character => {
        const sheet = character.character_sheet || {};
        const bits = [sheet.ancestry || sheet.race || sheet.species || '', sheet.class_name || sheet.class || '', sheet.level ? `level ${sheet.level}` : ''].filter(Boolean).join(' · ');
        return `<div class="dnd-character-sheet" data-character-id="${dndAttr(character.id || '')}"><div style="display:flex;justify-content:space-between;gap:0.5rem;"><strong>${escapeHtml(character.name || 'Unnamed character')}</strong><span class="tag">${escapeHtml(character.kind || sheet.kind || 'pc')}</span></div><div style="color:var(--text-dim);font-size:0.82rem;margin-top:0.25rem;">${escapeHtml(bits || 'No class/species set')}</div><details style="margin-top:0.35rem;color:var(--text-dim);font-size:0.8rem;"><summary>Character sheet</summary><pre style="white-space:pre-wrap;">${escapeHtml(JSON.stringify(sheet, null, 2))}</pre></details></div>`;
    }).join('') : '<p style="color:var(--text-dim);">No characters yet. Use manual create or AI forge below.</p>';
    const worldRows = worldEntities.length ? worldEntities.map(entity => `<div class="dnd-world-entity" data-entity-id="${dndAttr(entity.id || '')}"><div style="display:flex;justify-content:space-between;gap:0.5rem;"><strong>${escapeHtml(entity.name || 'World entity')}</strong><span class="tag">${escapeHtml(entity.entity_type || entity.type || 'lore')}</span></div><div style="color:var(--text-dim);font-size:0.82rem;margin-top:0.25rem;">${escapeHtml(entity.summary || entity.description || '')}</div></div>`).join('') : '<p style="color:var(--text-dim);">No structured world entities yet. Generate a world seed or add lore below.</p>';
    const diceActorOptions = ['<option value="">No actor</option>'].concat(players.map(player => `<option value="${dndAttr(player.name || player.id || '')}">${escapeHtml(player.name || player.id || 'Player')}</option>`)).concat(characters.map(character => `<option value="${dndAttr(character.name || character.id || '')}">${escapeHtml(character.name || character.id || 'Character')}</option>`)).join('');
    const mechanicsRows = diceEvents.length ? diceEvents.map(event => {
        const payload = dndDicePayload(event);
        return `
            <div class="message-board-message dnd-event-dice" style="margin:0.45rem 0;">
                <div class="message-board-meta"><strong>${escapeHtml(payload.label || 'Dice')}</strong>${event.actor ? `<span>${escapeHtml(event.actor)}</span>` : ''}</div>
                <div><strong>${escapeHtml(String(payload.total ?? ''))}</strong> · ${escapeHtml(payload.expression || '')} · ${escapeHtml(JSON.stringify(payload.rolls || []))}</div>
            </div>
        `;
    }).join('') : '<p style="color:var(--text-dim);">No dice or mechanics yet.</p>';
    const logRows = events.length ? events.map(event => {
        const label = dndEventType(event);
        const actor = event.actor || event.player_name || event.source || '';
        const body = dndEventBody(event);
        const stamp = event.created_at || event.timestamp || event.time || '';
        const payload = event.payload || {};
        const actionSource = payload.action_source || payload.resolution_source || '';
        const status = payload.status || '';
        const detailBits = [
            actionSource ? `source: ${actionSource}` : '',
            status ? `status: ${status}` : '',
            payload.error ? `error: ${payload.error}` : '',
        ].filter(Boolean);
        const structuredAction = payload.action && Object.keys(payload.action).length ? `
                <details style="margin-top:0.4rem;color:var(--text-dim);font-size:0.82rem;"><summary>Structured action</summary><pre style="white-space:pre-wrap;">${escapeHtml(JSON.stringify(payload.action, null, 2))}</pre></details>
            ` : '';
        return `
            <div class="message-board-message ${dndEventClass(event)}" style="margin:0.6rem 0;">
                <div class="message-board-meta" style="margin-bottom:0.35rem;">
                    <strong>${escapeHtml(label)}</strong>
                    ${actor ? `<span>${escapeHtml(actor)}</span>` : ''}
                    ${stamp ? `<span>${escapeHtml(stamp)}</span>` : ''}
                </div>
                <div>${escapeHtml(body)}</div>
                ${detailBits.length ? `<div style="color:var(--text-dim);font-size:0.78rem;margin-top:0.35rem;">${escapeHtml(detailBits.join(' · '))}</div>` : ''}
                ${structuredAction}
            </div>
        `;
    }).join('') : '<p style="color:var(--text-dim);">No matching action or narration events yet.</p>';
    detail.innerHTML = `
        <div style="display:flex;justify-content:space-between;gap:1rem;align-items:flex-start;flex-wrap:wrap;">
            <div>
                <h3>${escapeHtml(campaign.name || campaign.title || id || 'Untitled Campaign')}</h3>
                <div class="message-board-meta">
                    <span>turn ${escapeHtml(String(turn))}</span>
                    <span>${escapeHtml(players.length)} players</span>
                    <span>${escapeHtml(campaign.status || campaign.phase || 'active')}</span>
                </div>
            </div>
            <div style="display:flex;gap:0.5rem;flex-wrap:wrap;">
                <button class="btn primary" id="dnd-auto-turn-btn" onclick="runDndAutoTurn()">Run Live Auto Turn</button>
                <span class="tag" title="Subagent controllers call Hermes live, emit player_action/subagent_status events, and show fallback_used when JSON or gateway calls fail.">Live autonomous subagents</span>
                <button class="btn" onclick="selectDndCampaign('${dndEncodedId(id)}')">Refresh</button>
            </div>
        </div>
        <div id="dnd-scene-card" style="margin-top:1rem;padding:0.85rem;border:1px solid var(--border-subtle);border-radius:12px;background:rgba(255,255,255,0.03);">
            <h4>Current Scene</h4>
            <p style="color:var(--text-dim);margin-top:0.4rem;white-space:pre-wrap;">${escapeHtml(scene)}</p>
        </div>
        <div class="dnd-dashboard-grid" id="dnd-dashboard-shell" style="margin-top:1rem;">
            <div id="dnd-left-rail">
                <h4>Player Roster</h4>
                <div style="margin-top:0.45rem;">${roster}</div>
                <form class="message-board-form" style="margin-top:0.75rem;" onsubmit="addDndPlayer(event)">
                    <input id="dnd-player-name" type="text" placeholder="Player / character name" required>
                    <select id="dnd-player-controller" required>
                        <option value="human">human</option>
                        <option value="subagent">subagent</option>
                    </select>
                    <input id="dnd-player-notes" type="text" placeholder="Subagent prompt / personality / goals, or human character notes">
                    <button class="btn" id="dnd-add-player-submit" type="submit">Add Player</button>
                </form>
                <div id="dnd-pending-turn" style="margin-top:1rem;padding:0.75rem;border:1px solid var(--border-subtle);border-radius:10px;">
                    <h4>Pending Turn</h4>
                    <ul style="color:var(--text-dim);margin-left:1.1rem;">${pendingRows}</ul>
                </div>
                <div id="dnd-turn-progress" style="margin-top:1rem;padding:0.75rem;border:1px solid var(--border-subtle);border-radius:10px;background:rgba(255,255,255,0.025);">
                    <div style="display:flex;justify-content:space-between;gap:0.5rem;align-items:center;">
                        <h4>Live turn progress</h4>
                        <span class="tag" id="dnd-turn-poll-status">idle</span>
                    </div>
                    <p id="dnd-turn-progress-summary" style="color:var(--text-dim);font-size:0.84rem;margin-top:0.35rem;">No live auto turn is currently running.</p>
                    <div id="dnd-turn-progress-list" style="margin-top:0.45rem;"><p style="color:var(--text-dim);">Start a live auto turn to see Thinking → JSON received → Committed progress.</p></div>
                </div>
            </div>
            <div id="dnd-main-stage">
                <div class="dnd-cockpit-card" id="dnd-character-card">
                    <h4>Character Builder</h4>
                    <div id="dnd-character-list">${characterRows}</div>
                    <form class="message-board-form" id="dnd-character-create-form" style="margin-top:0.75rem;" onsubmit="createDndCharacter(event)">
                        <input id="dnd-character-name" type="text" placeholder="Character name" required>
                        <select id="dnd-character-player-id">${characterPlayerOptions}</select>
                        <input id="dnd-character-ancestry" type="text" placeholder="Species / ancestry">
                        <input id="dnd-character-class" type="text" placeholder="Class / subclass">
                        <input id="dnd-character-background" type="text" placeholder="Background">
                        <input id="dnd-character-level" type="number" min="1" max="20" value="1" placeholder="Level">
                        <button class="btn" id="dnd-character-create-submit" type="submit">Create Character</button>
                    </form>
                    <form class="message-board-form" id="dnd-character-ai-form" style="margin-top:0.75rem;" onsubmit="generateDndCharacter(event)">
                        <textarea id="dnd-character-ai-brief" placeholder="AI character brief: haunted tiefling warlock, optimistic dwarf medic, etc." style="min-height:70px;"></textarea>
                        <button class="btn primary" id="dnd-character-generate-btn" type="submit">AI Generate Character</button>
                    </form>
                </div>
                <div class="dnd-cockpit-card" id="dnd-world-builder-card">
                    <h4>World Builder</h4>
                    <div class="message-board-meta"><span>Schema: dnd.world_generation.v1</span><span>${escapeHtml(worldState?.source || 'manual/world forge')}</span></div>
                    <textarea id="dnd-world-summary" placeholder="Scene summary / world premise" style="margin-top:0.5rem;min-height:70px;">${escapeHtml((campaign.current_scene && campaign.current_scene.summary) || campaign.description || '')}</textarea>
                    <input id="dnd-world-location" type="text" placeholder="Current location" value="${dndAttr((campaign.current_scene && campaign.current_scene.location) || '')}">
                    <input id="dnd-world-mood" type="text" placeholder="Mood / tone" value="${dndAttr((campaign.current_scene && campaign.current_scene.mood) || '')}">
                    <textarea id="dnd-world-open-questions" placeholder="Open questions, one per line" style="min-height:58px;">${escapeHtml(((campaign.current_scene && campaign.current_scene.open_questions) || []).join('\n'))}</textarea>
                    <div style="display:flex;gap:0.5rem;flex-wrap:wrap;margin:0.5rem 0;"><button class="btn" onclick="saveDndWorldScene()">Save Scene</button><button class="btn primary" id="dnd-world-generate-btn" onclick="generateDndWorld()">AI Generate World</button></div>
                    <h4 style="margin-top:0.75rem;">World Entities</h4>
                    <div id="dnd-world-entities">${worldRows}</div>
                    <form class="message-board-form" id="dnd-world-entity-form" style="margin-top:0.75rem;" onsubmit="createDndWorldEntity(event)">
                        <select id="dnd-world-entity-type"><option value="location">location</option><option value="npc">npc</option><option value="faction">faction</option><option value="quest">quest</option><option value="encounter">encounter</option><option value="lore">lore</option></select>
                        <input id="dnd-world-entity-name" type="text" placeholder="Name" required>
                        <input id="dnd-world-entity-summary" type="text" placeholder="Summary / hook">
                        <button class="btn" type="submit">Add World Entity</button>
                    </form>
                </div>
                <h4>Mechanics & Dice</h4>
                <form id="dnd-dice-form" class="message-board-form" onsubmit="rollDndDice(event)">
                    <input id="dnd-dice-expression" type="text" placeholder="1d20+5" required>
                    <input id="dnd-dice-label" type="text" placeholder="Stealth check / attack / damage">
                    <select id="dnd-dice-actor">${diceActorOptions}</select>
                    <button class="btn" type="submit">Roll</button>
                </form>
                <div id="dnd-mechanics-log" style="margin-top:0.6rem;max-height:220px;overflow:auto;">${mechanicsRows}</div>
                <form id="dnd-manual-event-form" class="message-board-form" style="margin-top:1rem;" onsubmit="submitDndEvent(event)">
                    <select id="dnd-event-type"><option value="dm_narration">DM narration</option><option value="scene_update">Scene update</option><option value="rules_note">Rules note</option></select>
                    <textarea id="dnd-event-body" placeholder="Add DM narration, rules note, or scene update" style="min-height:70px;"></textarea>
                    <button class="btn" type="submit">Add Event</button>
                </form>
            </div>
            <div id="dnd-right-rail">
                <div class="dnd-cockpit-card" id="dnd-dm-tools-card">
                    <h4>DM Tools</h4>
                    <p style="color:var(--text-dim);font-size:0.84rem;">rpg-dm-bot inspired cockpit: batched turns, server dice, editable world memory, and visible mechanics.</p>
                    <button class="btn" onclick="document.getElementById('dnd-event-type').value='dm_narration';document.getElementById('dnd-event-body').focus();">Inject DM Event</button>
                    <button class="btn" onclick="document.getElementById('dnd-event-type').value='rules_note';document.getElementById('dnd-event-body').focus();">Add Rules Note</button>
                </div>
                <h4>Action / Narration Log</h4>
                <div style="display:flex;gap:0.5rem;margin-top:0.4rem;flex-wrap:wrap;">
                    <select id="dnd-event-filter" onchange="selectedDndEventFilter=this.value; renderDndCampaign(selectedDndCampaign);">
                        <option value="" ${selectedDndEventFilter === '' ? 'selected' : ''}>All events</option>
                        <option value="dm_narration" ${selectedDndEventFilter === 'dm_narration' ? 'selected' : ''}>Narration</option>
                        <option value="player_action" ${selectedDndEventFilter === 'player_action' ? 'selected' : ''}>Player actions</option>
                        <option value="subagent_status" ${selectedDndEventFilter === 'subagent_status' ? 'selected' : ''}>Subagent status</option>
                        <option value="dice_roll" ${selectedDndEventFilter === 'dice_roll' ? 'selected' : ''}>Dice</option>
                        <option value="scene_update" ${selectedDndEventFilter === 'scene_update' ? 'selected' : ''}>Scene</option>
                        <option value="rules_note" ${selectedDndEventFilter === 'rules_note' ? 'selected' : ''}>Rules</option>
                    </select>
                    <select id="dnd-event-order" onchange="selectedDndEventOrder=this.value; renderDndCampaign(selectedDndCampaign);">
                        <option value="asc" ${selectedDndEventOrder === 'asc' ? 'selected' : ''}>Oldest first</option>
                        <option value="desc" ${selectedDndEventOrder === 'desc' ? 'selected' : ''}>Newest first</option>
                    </select>
                </div>
                <div style="margin-top:0.45rem;max-height:520px;overflow:auto;">${logRows}</div>
            </div>
        </div>
    `;
    updateDndAutoTurnButton(Boolean(dndAutoTurnJobId));
    renderDndTurnProgress();
}


async function createDndCharacter(event) {
    if (event && typeof event.preventDefault === 'function') event.preventDefault();
    if (!selectedDndCampaignId) { showToast('Select a campaign first', true); return; }
    const name = document.getElementById('dnd-character-name')?.value?.trim() || '';
    const player_id = document.getElementById('dnd-character-player-id')?.value || null;
    const sheet = {
        ancestry: document.getElementById('dnd-character-ancestry')?.value?.trim() || '',
        class_name: document.getElementById('dnd-character-class')?.value?.trim() || '',
        background: document.getElementById('dnd-character-background')?.value?.trim() || '',
        level: Number(document.getElementById('dnd-character-level')?.value || 1),
        kind: 'pc',
    };
    if (!name) { showToast('Character name is required', true); return; }
    try {
        await fetchJsonOrThrow(`/api/dnd/campaigns/${encodeURIComponent(selectedDndCampaignId)}/characters`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name, player_id, character_sheet: sheet })
        });
        showToast('Character created');
        await selectDndCampaign(encodeURIComponent(selectedDndCampaignId));
    } catch (e) { showToast(`Character create failed: ${e.message}`, true); log('err', `D&D character create failed: ${e.message}`, true); }
}

async function generateDndCharacter(event) {
    if (event && typeof event.preventDefault === 'function') event.preventDefault();
    if (!selectedDndCampaignId) { showToast('Select a campaign first', true); return; }
    const brief = document.getElementById('dnd-character-ai-brief')?.value?.trim() || '';
    const player_id = document.getElementById('dnd-character-player-id')?.value || null;
    const btn = document.getElementById('dnd-character-generate-btn');
    if (btn) { btn.disabled = true; btn.textContent = 'Generating...'; }
    try {
        await fetchJsonOrThrow(`/api/dnd/campaigns/${encodeURIComponent(selectedDndCampaignId)}/characters/generate`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ prompt: brief, player_id, constraints: { level: 1, rules_profile_id: 'dnd5e' } })
        });
        showToast('AI character generated');
        await selectDndCampaign(encodeURIComponent(selectedDndCampaignId));
    } catch (e) { showToast(`AI character failed: ${e.message}`, true); log('err', `D&D AI character failed: ${e.message}`, true); }
    finally { if (btn) { btn.disabled = false; btn.textContent = 'AI Generate Character'; } }
}

async function saveDndWorldScene() {
    if (!selectedDndCampaignId) { showToast('Select a campaign first', true); return; }
    const current_scene = {
        summary: document.getElementById('dnd-world-summary')?.value?.trim() || '',
        location: document.getElementById('dnd-world-location')?.value?.trim() || '',
        mood: document.getElementById('dnd-world-mood')?.value?.trim() || '',
        visible_threats: [],
        open_questions: (document.getElementById('dnd-world-open-questions')?.value || '').split('\n').map(s => s.trim()).filter(Boolean),
    };
    try {
        await fetchJsonOrThrow(`/api/dnd/campaigns/${encodeURIComponent(selectedDndCampaignId)}/scene`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ current_scene })
        });
        showToast('World scene saved');
        await selectDndCampaign(encodeURIComponent(selectedDndCampaignId));
    } catch (e) { showToast(`Scene save failed: ${e.message}`, true); log('err', `D&D scene save failed: ${e.message}`, true); }
}

async function generateDndWorld() {
    if (!selectedDndCampaignId) { showToast('Select a campaign first', true); return; }
    const btn = document.getElementById('dnd-world-generate-btn');
    const brief = document.getElementById('dnd-world-summary')?.value?.trim() || selectedDndCampaign?.description || '';
    if (btn) { btn.disabled = true; btn.textContent = 'Forging world...'; }
    try {
        await fetchJsonOrThrow(`/api/dnd/campaigns/${encodeURIComponent(selectedDndCampaignId)}/world/generate`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ brief, parameters: { tone: document.getElementById('dnd-world-mood')?.value?.trim() || '', rules_profile_id: 'dnd5e', content_pack_id: 'fantasy_core' } })
        });
        showToast('AI world generated');
        await selectDndCampaign(encodeURIComponent(selectedDndCampaignId));
    } catch (e) { showToast(`World generation failed: ${e.message}`, true); log('err', `D&D world generation failed: ${e.message}`, true); }
    finally { if (btn) { btn.disabled = false; btn.textContent = 'AI Generate World'; } }
}

async function createDndWorldEntity(event) {
    if (event && typeof event.preventDefault === 'function') event.preventDefault();
    if (!selectedDndCampaignId) { showToast('Select a campaign first', true); return; }
    const entity_type = document.getElementById('dnd-world-entity-type')?.value || 'lore';
    const name = document.getElementById('dnd-world-entity-name')?.value?.trim() || '';
    const summary = document.getElementById('dnd-world-entity-summary')?.value?.trim() || '';
    if (!name) { showToast('World entity name is required', true); return; }
    try {
        await fetchJsonOrThrow(`/api/dnd/campaigns/${encodeURIComponent(selectedDndCampaignId)}/world/entities`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ entity_type, name, summary })
        });
        showToast('World entity added');
        await selectDndCampaign(encodeURIComponent(selectedDndCampaignId));
    } catch (e) { showToast(`World entity failed: ${e.message}`, true); log('err', `D&D world entity failed: ${e.message}`, true); }
}

async function addDndPlayer(event) {
    if (event && typeof event.preventDefault === 'function') event.preventDefault();
    if (!selectedDndCampaignId) {
        showToast('Select a campaign first', true);
        return;
    }
    const nameEl = document.getElementById('dnd-player-name');
    const controllerEl = document.getElementById('dnd-player-controller');
    const notesEl = document.getElementById('dnd-player-notes');
    const submitEl = document.getElementById('dnd-add-player-submit');
    const name = nameEl?.value?.trim() || '';
    const controller_type = controllerEl?.value || 'human';
    const notes = notesEl?.value?.trim() || '';
    if (!name) {
        showToast('Player name is required', true);
        return;
    }
    if (submitEl) {
        submitEl.disabled = true;
        submitEl.textContent = 'Adding...';
    }
    try {
        log('req', `POST /api/dnd/campaigns/${selectedDndCampaignId}/players`);
        await fetchJsonOrThrow(`/api/dnd/campaigns/${encodeURIComponent(selectedDndCampaignId)}/players`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, controller_type, notes, role: notes, agent_prompt: controller_type === 'subagent' ? notes : undefined }),
        });
        if (nameEl) nameEl.value = '';
        if (notesEl) notesEl.value = '';
        showToast('Player added');
        await selectDndCampaign(encodeURIComponent(selectedDndCampaignId));
    } catch (e) {
        showToast(`Add player failed: ${e.message}`, true);
        log('err', `Add D&D player failed: ${e.message}`, true);
    } finally {
        if (submitEl) {
            submitEl.disabled = false;
            submitEl.textContent = 'Add Player';
        }
    }
}

async function runDndAutoTurn() {
    if (!selectedDndCampaignId) {
        showToast('Select a campaign first', true);
        return;
    }
    if (dndAutoTurnJobId) {
        showToast('A live auto turn is already running', true);
        return;
    }
    updateDndAutoTurnButton(true);
    try {
        const human_actions = {};
        document.querySelectorAll('.dnd-human-action').forEach(input => {
            const playerId = input.dataset.playerId;
            const action = input.value.trim();
            if (playerId && action) human_actions[playerId] = action;
        });
        log('req', `POST /api/dnd/campaigns/${selectedDndCampaignId}/turns/auto/jobs`);
        const data = await fetchJsonOrThrow(`/api/dnd/campaigns/${encodeURIComponent(selectedDndCampaignId)}/turns/auto/jobs`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ human_actions }),
        });
        const job = data.job || data;
        startDndAutoTurnPolling(selectedDndCampaignId, job.id, job);
        showToast('Live auto turn started');
    } catch (e) {
        updateDndAutoTurnButton(false);
        showToast(`Auto turn failed: ${e.message}`, true);
        log('err', `D&D auto turn failed: ${e.message}`, true);
    }
}

async function rollDndDice(event) {
    if (event && typeof event.preventDefault === 'function') event.preventDefault();
    if (!selectedDndCampaignId) {
        showToast('Select a campaign first', true);
        return;
    }
    const expression = document.getElementById('dnd-dice-expression')?.value?.trim() || '';
    const label = document.getElementById('dnd-dice-label')?.value?.trim() || '';
    const actor = document.getElementById('dnd-dice-actor')?.value || '';
    if (!expression) {
        showToast('Dice expression is required', true);
        return;
    }
    try {
        log('req', `POST /api/dnd/campaigns/${selectedDndCampaignId}/dice`);
        await fetchJsonOrThrow(`/api/dnd/campaigns/${encodeURIComponent(selectedDndCampaignId)}/dice`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ expression, label, actor }),
        });
        showToast('Dice rolled');
        await selectDndCampaign(encodeURIComponent(selectedDndCampaignId));
    } catch (e) {
        showToast(`Dice roll failed: ${e.message}`, true);
        log('err', `D&D dice roll failed: ${e.message}`, true);
    }
}

async function submitDndEvent(event) {
    if (event && typeof event.preventDefault === 'function') event.preventDefault();
    if (!selectedDndCampaignId) {
        showToast('Select a campaign first', true);
        return;
    }
    const type = document.getElementById('dnd-event-type')?.value || 'dm_narration';
    const bodyEl = document.getElementById('dnd-event-body');
    const body = bodyEl?.value?.trim() || '';
    if (!body) {
        showToast('Event body is required', true);
        return;
    }
    try {
        log('req', `POST /api/dnd/campaigns/${selectedDndCampaignId}/events`);
        await fetchJsonOrThrow(`/api/dnd/campaigns/${encodeURIComponent(selectedDndCampaignId)}/events`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ event_type: type, body, actor: 'DM' }),
        });
        if (bodyEl) bodyEl.value = '';
        showToast('Event added');
        await selectDndCampaign(encodeURIComponent(selectedDndCampaignId));
    } catch (e) {
        showToast(`Event add failed: ${e.message}`, true);
        log('err', `D&D event add failed: ${e.message}`, true);
    }
}

async function loadAgentObservability() {
    const stats = document.getElementById('agent-observability-stats');
    const windowHours = document.getElementById('agent-observability-window')?.value || '24';
    try {
        log('req', `GET /api/agent-observability?window_hours=${windowHours}`);
        const data = await fetchJsonOrThrow(`/api/agent-observability?window_hours=${encodeURIComponent(windowHours)}&trace_limit=8`);
        renderAgentObservability(data);
        const summary = data.summary || {};
        if (stats) {
            const failurePct = Math.round((summary.tool_failure_rate || 0) * 100);
            stats.textContent = `${summary.sessions || 0} sessions · ${summary.tool_calls || 0} tool events · ${failurePct}% tool failure rate · ${summary.running_sessions || 0} running`;
        }
        log('res', 'Loaded agent ops radar');
    } catch (e) {
        if (stats) stats.textContent = '';
        const alerts = document.getElementById('agent-observability-alerts');
        if (alerts) alerts.innerHTML = `<h4>Signals</h4><p style="color:var(--error);">Failed to load agent ops telemetry: ${escapeHtml(e.message)}</p>`;
        showToast(`Agent ops load failed: ${e.message}`, true);
        log('err', `Agent ops load failed: ${e.message}`, true);
    }
}

function renderAgentObservability(data) {
    const summary = data?.summary || {};
    const metricCards = [
        ['Sessions', summary.sessions || 0],
        ['Completed', summary.completed_sessions || 0],
        ['Running', summary.running_sessions || 0],
        ['Errors', summary.error_sessions || 0],
        ['Messages', summary.messages || 0],
        ['Tool failures', summary.tool_failures || 0],
        ['Missing summaries', summary.missing_summaries || 0],
        ['Stale runs', summary.stale_running_sessions || 0],
    ].map(([label, value]) => `<span class="meta-pill"><strong>${escapeHtml(value)}</strong> ${escapeHtml(label)}</span>`).join(' ');

    const alerts = document.getElementById('agent-observability-alerts');
    if (alerts) {
        const rows = (data.alerts || []).map(alert => `
            <div style="padding:0.65rem;border:1px solid var(--border-subtle);border-radius:10px;margin:0.5rem 0;background:rgba(255,255,255,0.03);">
                <div style="font-weight:700;">${escapeHtml(alert.title || 'Signal')} <span class="tag">${escapeHtml(alert.severity || 'info')}</span></div>
                <div style="color:var(--text-dim);font-size:0.84rem;margin-top:0.25rem;">${escapeHtml(alert.detail || '')}</div>
            </div>
        `).join('') || '<p style="color:var(--text-dim);">No signals.</p>';
        const recommendations = (data.recommendations || []).map(item => `<li>${escapeHtml(item)}</li>`).join('');
        alerts.innerHTML = `<h4>Signals</h4><div class="message-meta" style="margin:0.5rem 0;">${metricCards}</div>${rows}<h4 style="margin-top:1rem;">Operator Moves</h4><ul style="color:var(--text-dim);font-size:0.84rem;line-height:1.45;">${recommendations}</ul>`;
    }

    const research = document.getElementById('agent-observability-research');
    if (research) {
        const basis = (data.research_basis || []).map(item => `<li>${escapeHtml(item)}</li>`).join('');
        research.innerHTML = `<h4>Research Basis</h4><p style="color:var(--text-dim);font-size:0.84rem;">Inspired by current agent-observability guidance: combine aggregate monitoring with trace-level debugging.</p><ul style="color:var(--text-dim);font-size:0.84rem;line-height:1.45;">${basis}</ul>`;
    }

    const tools = document.getElementById('agent-observability-tools');
    if (tools) {
        const topTools = data.top_tools || [];
        tools.innerHTML = `<h4>Top Tools</h4>` + (topTools.length ? `
            <table class="sessions-table"><thead><tr><th>Tool</th><th>Events</th></tr></thead><tbody>
                ${topTools.map(tool => `<tr><td>${escapeHtml(tool.name || 'tool')}</td><td>${escapeHtml(tool.count ?? 0)}</td></tr>`).join('')}
            </tbody></table>
        ` : '<p style="color:var(--text-dim);">No tool activity in this window.</p>');
    }

    const mix = document.getElementById('agent-observability-mix');
    if (mix) {
        const renderMix = (title, rows) => `<h4 style="margin-top:0.75rem;">${title}</h4><div class="message-meta">${(rows || []).map(row => `<span class="meta-pill">${escapeHtml(row.name || 'unknown')}: ${escapeHtml(row.count ?? 0)}</span>`).join(' ') || '<span class="meta-pill">none</span>'}</div>`;
        mix.innerHTML = `<h4>Source / Model Mix</h4>${renderMix('Sources', data.source_mix)}${renderMix('Models', data.model_mix)}`;
    }

    const traces = document.getElementById('agent-observability-traces');
    if (traces) {
        const traceRows = data.recent_traces || [];
        traces.innerHTML = `<h4>Recent Trace Exemplars</h4>` + (traceRows.length ? `
            <table class="sessions-table"><thead><tr><th>Session</th><th>Status</th><th>Source</th><th>Model</th><th>Messages</th><th>Tool Events</th></tr></thead><tbody>
                ${traceRows.map(trace => `<tr>
                    <td><a href="#sessions/${escapeHtml(trace.id || '')}">${escapeHtml(trace.title || trace.id || 'Session')}</a><div style="color:var(--text-dim);font-size:0.76rem;">${escapeHtml(trace.started_at || '')}</div></td>
                    <td><span class="tag">${escapeHtml(trace.status || 'unknown')}</span></td>
                    <td>${escapeHtml(trace.source || 'unknown')}</td>
                    <td>${escapeHtml(trace.model || 'unknown')}</td>
                    <td>${escapeHtml(trace.messages ?? 0)}</td>
                    <td>${escapeHtml(trace.tool_events ?? 0)}</td>
                </tr>`).join('')}
            </tbody></table>
        ` : '<p style="color:var(--text-dim);">No traces in this window.</p>');
    }
}

async function loadSelfImprovement() {
    const stats = document.getElementById('self-improvement-stats');
    try {
        log('req', 'GET /api/self-improvement');
        const data = await fetchJsonOrThrow('/api/self-improvement');
        renderSelfImprovement(data);
        const runs = data?.ledger?.count || 0;
        const queued = data?.supervisor?.queued_candidate_count || 0;
        const hub = data?.policy?.hub_ok ? 'hub ok' : 'needs attention';
        const controlPlane = data?.control_plane_packet || {};
        const promptP95 = controlPlane?.telemetry?.prompt_budgets?.total_input_tokens?.p95;
        const buildMs = controlPlane?.benchmarks?.health_packet_build_ms;
        const privacy = controlPlane?.privacy?.mode === 'aggregate_only' ? 'privacy ok' : 'privacy unknown';
        const telemetryText = promptP95 !== null && promptP95 !== undefined
            ? ` · prompt p95 ${promptP95}`
            : '';
        const buildText = buildMs !== null && buildMs !== undefined ? ` · health ${Number(buildMs).toFixed(1)}ms` : '';
        if (stats) stats.textContent = `${runs} recent runs · ${queued} queued candidates · ${hub}${telemetryText}${buildText} · ${privacy}`;
        log('res', 'Loaded self-improvement cockpit');
    } catch (e) {
        if (stats) stats.textContent = '';
        const runs = document.getElementById('self-improvement-runs');
        if (runs) runs.innerHTML = `<p style="color:var(--error);">Failed to load self-improvement state: ${escapeHtml(e.message)}</p>`;
        showToast(`Self-improvement load failed: ${e.message}`, true);
        log('err', `Self-improvement load failed: ${e.message}`, true);
    }
}

function renderSelfImprovement(data) {
    const supervisor = data?.supervisor || {};
    const supervisorEl = document.getElementById('self-improvement-supervisor');
    const job = supervisor.cron_job || {};
    const locked = !!supervisor?.lock?.locked;
    if (supervisorEl) {
        supervisorEl.innerHTML = `
            <h4>Supervisor</h4>
            <div class="message-meta" style="margin:0.5rem 0;">
                <span class="meta-pill">${supervisor.active ? 'Active' : 'Paused/Missing'}</span>
                <span class="meta-pill">State: ${escapeHtml(supervisor.state || 'unknown')}</span>
                <span class="meta-pill">Lock: ${locked ? 'locked' : 'free'}</span>
                <span class="meta-pill">Score: ${supervisor.recent_outcome_score ?? '—'}</span>
            </div>
            <p style="color:var(--text-dim);font-size:0.84rem;margin-top:0.5rem;">Job: ${escapeHtml(job.name || 'self-improvement-loop not found')} · next: ${escapeHtml(job.next_run_at || '—')} · last: ${escapeHtml(job.last_run_at || 'never')}</p>
        `;
    }
    renderSelfImprovementControlPlane(data?.control_plane_packet || {});
    renderSelfImprovementCronMesh(data?.cron_mesh || {});
    renderSelfImprovementDrift(data?.drift || {}, data?.policy || {});
    renderBecomussyOutboxHealth(data?.becomussy_outbox || {});
    renderSelfImprovementEventCoverage(data?.candidate_event_coverage || {});
    renderBecomussyResumePacket(data?.becomussy_resume_packet || {});
    renderSelfImprovementRuns(data?.ledger?.runs || []);
    renderSelfImprovementQueue(data?.queue || {});
}

function renderSelfImprovementControlPlane(packet) {
    const el = document.getElementById('self-improvement-control-plane');
    if (!el) return;
    const telemetry = packet?.telemetry || {};
    const prompt = telemetry?.prompt_budgets || {};
    const input = prompt?.total_input_tokens || {};
    const output = prompt?.available_output_budget || {};
    const api = telemetry?.api_calls || {};
    const latency = api?.total_latency_ms || {};
    const benchmarks = packet?.benchmarks || {};
    const privacy = packet?.privacy || {};
    const metrics = packet?.metrics || {};
    const gates = packet?.gates || {};
    const gateSummary = Object.keys(gates).length
        ? Object.entries(gates).map(([name, status]) => `${name}:${status}`).join(' · ')
        : 'no gates yet';
    const privacyOk = privacy.mode === 'aggregate_only'
        && privacy.raw_prompts === false
        && privacy.raw_messages === false
        && privacy.raw_tool_payloads === false
        && privacy.local_file_contents === false;
    el.innerHTML = `
        <h4>Control Plane</h4>
        <div class="message-meta" style="margin:0.5rem 0;">
            <span class="meta-pill">${packet.ok ? 'ready' : 'attention'}</span>
            <span class="meta-pill">privacy: ${privacyOk ? 'aggregate-only' : 'unknown'}</span>
            <span class="meta-pill">health: ${benchmarks.health_packet_build_ms !== undefined ? `${Number(benchmarks.health_packet_build_ms).toFixed(1)}ms` : '—'}</span>
            <span class="meta-pill">target: ${escapeHtml(String(benchmarks.health_latency_target_ms ?? '—'))}ms</span>
        </div>
        <p style="color:var(--text-dim);font-size:0.84rem;margin:0.45rem 0;">Prompt input p50/p95/p99: ${escapeHtml(String(input.p50 ?? '—'))} / ${escapeHtml(String(input.p95 ?? '—'))} / ${escapeHtml(String(input.p99 ?? '—'))} · samples ${escapeHtml(String(prompt.sample_count ?? 0))}</p>
        <p style="color:var(--text-dim);font-size:0.84rem;margin:0.45rem 0;">Output budget p50/p95/p99: ${escapeHtml(String(output.p50 ?? '—'))} / ${escapeHtml(String(output.p95 ?? '—'))} / ${escapeHtml(String(output.p99 ?? '—'))}</p>
        <p style="color:var(--text-dim);font-size:0.84rem;margin:0.45rem 0;">API latency p95: ${escapeHtml(String(latency.p95 ?? '—'))}ms · failures ${escapeHtml(String(api.failure_count ?? 0))} · outbox pending ${escapeHtml(String(metrics.outbox_pending_count ?? 0))}</p>
        <p style="color:var(--text-dim);font-size:0.82rem;margin:0.45rem 0;">Gates: ${escapeHtml(gateSummary)}</p>
    `;
}

function renderSelfImprovementCronMesh(mesh) {
    const el = document.getElementById('self-improvement-cron-mesh');
    if (!el) return;
    const selfJobs = mesh.self_improvement_jobs || [];
    const legacyJobs = mesh.legacy_jobs || [];
    const primary = selfJobs.find(job => job.id === mesh.primary_job_id) || selfJobs[0] || {};
    const blockers = mesh.blockers || [];
    const legacySummary = legacyJobs.length
        ? legacyJobs.map(job => `${job.enabled ? 'ACTIVE' : 'paused'} ${job.name}`).join(' · ')
        : 'No legacy jobs found';
    const skillGap = (primary.missing_required_skills || []).join(', ') || 'none';
    el.innerHTML = `
        <h4>Cron Wiring</h4>
        <div class="message-meta" style="margin:0.5rem 0;">
            <span class="meta-pill">${mesh.ok ? 'wired' : 'attention'}</span>
            <span class="meta-pill">jobs: ${escapeHtml(String(mesh.job_count ?? 0))}</span>
            <span class="meta-pill">active legacy: ${escapeHtml(String(mesh.active_legacy_count ?? 0))}</span>
        </div>
        <p style="color:var(--text-dim);font-size:0.84rem;margin:0.45rem 0;">Primary: ${escapeHtml(primary.name || 'missing')} · ${escapeHtml(primary.script || 'inline prompt')} · next ${escapeHtml(primary.next_run_at || '—')}</p>
        <p style="color:var(--text-dim);font-size:0.84rem;margin:0.45rem 0;">Required skill gaps: ${escapeHtml(skillGap)}</p>
        <p style="color:var(--text-dim);font-size:0.84rem;margin:0.45rem 0;">Legacy: ${escapeHtml(legacySummary)}</p>
        ${blockers.length ? `<p style="color:var(--warning);font-size:0.84rem;">${escapeHtml(blockers.join(' · '))}</p>` : ''}
    `;
}

function renderSelfImprovementDrift(drift, policy) {
    const el = document.getElementById('self-improvement-drift');
    if (!el) return;
    const severities = drift.severity_counts || {};
    const severityText = Object.keys(severities).length
        ? Object.entries(severities).map(([k, v]) => `${k}:${v}`).join(' · ')
        : 'none';
    const findings = drift.findings || [];
    el.innerHTML = `
        <h4>Drift / Guardrails</h4>
        <div class="message-meta" style="margin:0.5rem 0;">
            <span class="meta-pill">${policy.hub_ok ? 'hub ok' : 'needs attention'}</span>
            <span class="meta-pill">drift: ${drift.ok === null || drift.ok === undefined ? 'unknown' : (drift.ok ? 'ok' : 'findings')}</span>
            <span class="meta-pill">findings: ${escapeHtml(String(drift.finding_count ?? '—'))}</span>
        </div>
        <p style="color:var(--text-dim);font-size:0.84rem;margin:0.45rem 0;">Scope: ${escapeHtml(drift.scope || 'no drift artifact yet')} · severity: ${escapeHtml(severityText)}</p>
        <p style="color:var(--text-dim);font-size:0.84rem;margin:0.45rem 0;">Source: ${escapeHtml(drift.source || 'waiting for first run')}</p>
        ${findings.length ? `<ul style="color:var(--warning);font-size:0.82rem;margin:0.4rem 0 0 1rem;">${findings.map(f => `<li>${escapeHtml(f.message || f.summary || JSON.stringify(f).slice(0, 120))}</li>`).join('')}</ul>` : ''}
    `;
}

function renderBecomussyOutboxHealth(outbox) {
    const el = document.getElementById('self-improvement-outbox');
    if (!el) return;
    const errors = outbox.recent_errors || [];
    const invalidRecords = outbox.invalid_records || [];
    const oldest = outbox.oldest_pending || {};
    const status = outbox.invalid_count ? 'preflight attention' : (outbox.replay_needed ? 'replay needed' : (outbox.exists ? 'clear' : 'no outbox'));
    el.innerHTML = `
        <h4>Becomussy Outbox</h4>
        <div class="message-meta" style="margin:0.5rem 0;">
            <span class="meta-pill">${escapeHtml(status)}</span>
            <span class="meta-pill">pending: ${escapeHtml(String(outbox.pending_count ?? 0))}</span>
            <span class="meta-pill">valid pending: ${escapeHtml(String(outbox.valid_pending_count ?? 0))}</span>
            <span class="meta-pill">invalid: ${escapeHtml(String(outbox.invalid_count ?? 0))}</span>
            <span class="meta-pill">done: ${escapeHtml(String(outbox.done_count ?? 0))}</span>
            <span class="meta-pill">malformed: ${escapeHtml(String(outbox.malformed_count ?? 0))}</span>
        </div>
        <p style="color:var(--text-dim);font-size:0.84rem;margin:0.45rem 0;">Oldest pending: ${escapeHtml(oldest.id || 'none')} ${outbox.oldest_pending_age_hours !== null && outbox.oldest_pending_age_hours !== undefined ? `· ${escapeHtml(String(outbox.oldest_pending_age_hours))}h old` : ''}</p>
        ${invalidRecords.length ? `<p style="color:var(--warning);font-size:0.82rem;margin:0.35rem 0;">Preflight invalid_records:</p><ul style="color:var(--warning);font-size:0.82rem;margin:0.2rem 0 0 1rem;">${invalidRecords.map(rec => `<li>${escapeHtml(rec.path || 'unknown path')}: ${escapeHtml((rec.issues || []).join('; '))}</li>`).join('')}</ul>` : ''}
        ${errors.length ? `<ul style="color:var(--warning);font-size:0.82rem;margin:0.4rem 0 0 1rem;">${errors.map(err => `<li>${escapeHtml(err.path || 'unknown path')}: ${escapeHtml(err.last_error || '')}</li>`).join('')}</ul>` : '<p style="color:var(--text-dim);font-size:0.82rem;margin:0.35rem 0;">No recent outbox errors.</p>'}
    `;
}

function renderSelfImprovementEventCoverage(coverage) {
    const el = document.getElementById('self-improvement-event-coverage');
    if (!el) return;
    const missing = coverage.missing_event_coverage || {};
    const severity = coverage.missing_event_coverage_severity || {};
    const statusCounts = missing.status_counts || {};
    const statusSummary = Object.keys(statusCounts).length
        ? Object.entries(statusCounts).map(([k, v]) => `${k}:${v}`).join(' · ')
        : 'none';
    const missingPreview = (missing.candidates || [])
        .slice(0, 4)
        .map(candidate => candidate.id || candidate.candidate_id || candidate.title || '')
        .filter(Boolean);
    const repairHint = coverage.repair_hint || coverage.event_coverage_repair_hint || {};
    const applyReadiness = repairHint.apply_readiness || {};
    const anomalyDetails = (repairHint.anomaly_details || []).slice(0, 4);
    const nextRepairCommands = (repairHint.next_commands || []).slice(0, 4);
    const applySafe = applyReadiness.apply_safe;
    const blocking = applyReadiness.blocking;
    const repairCommandFallbacks = [
        repairHint.dry_run_command ? {kind: 'dry_run', command: repairHint.dry_run_command, reason: 'review synthetic event backfill preview'} : null,
        repairHint.apply_command ? {kind: 'apply', command: repairHint.apply_command, reason: 'apply only after preview/token review'} : null,
        repairHint.verify_after_apply_command ? {kind: 'verify', command: repairHint.verify_after_apply_command, reason: 'verify coverage after any apply'} : null,
    ].filter(Boolean);
    const commandRows = nextRepairCommands.length ? nextRepairCommands : repairCommandFallbacks;
    const status = coverage.coverage_ok === false ? 'coverage gaps' : (coverage.coverage_ok === true ? 'covered' : 'unknown');
    el.innerHTML = `
        <h4>Queue Event Coverage</h4>
        <div class="message-meta" style="margin:0.5rem 0;">
            <span class="meta-pill">${escapeHtml(status)}</span>
            <span class="meta-pill">level: ${escapeHtml(severity.level || 'unknown')}</span>
            <span class="meta-pill">events: ${escapeHtml(String(coverage.event_count ?? '—'))}</span>
            <span class="meta-pill">missing: ${escapeHtml(String(missing.count ?? severity.missing_count ?? '—'))}</span>
            ${repairHint.anomaly_count !== undefined && repairHint.anomaly_count !== null ? `<span class="meta-pill">anomalies: ${escapeHtml(String(repairHint.anomaly_count))}</span>` : ''}
        </div>
        <p style="color:var(--text-dim);font-size:0.84rem;margin:0.45rem 0;">Missing by status: ${escapeHtml(statusSummary)}</p>
        <p style="color:var(--text-dim);font-size:0.84rem;margin:0.45rem 0;">Source: ${escapeHtml(coverage.source || coverage.event_ledger_path || 'waiting for replay summary')}</p>
        ${repairHint.mutation === false ? `
        <div class="activity-item" style="margin:0.55rem 0;">
            <strong>Repair Readiness</strong>
            <div class="message-meta" style="margin-top:0.35rem;">
                <span class="meta-pill">apply_safe: ${escapeHtml(String(applySafe ?? 'unknown'))}</span>
                <span class="meta-pill">blocking: ${escapeHtml(String(blocking ?? false))}</span>
                <span class="meta-pill">missing: ${escapeHtml(String(repairHint.missing_count ?? '—'))}</span>
                <span class="meta-pill">anomalies: ${escapeHtml(String(repairHint.anomaly_count ?? '—'))}</span>
            </div>
            <p style="color:var(--text-dim);font-size:0.82rem;margin:0.35rem 0 0;">${escapeHtml(applyReadiness.reason || repairHint.reason || 'Review read-only repair hints before mutating the event ledger.')}</p>
        </div>` : ''}
        ${anomalyDetails.length ? `
        <div class="activity-item" style="margin:0.55rem 0;">
            <strong>Anomaly Samples</strong>
            <ul style="color:var(--warning);font-size:0.82rem;margin:0.35rem 0 0 1rem;">
                ${anomalyDetails.map(item => `<li>${escapeHtml(item.anomaly_type || 'anomaly')}: ${escapeHtml(item.candidate_id || item.title || 'unknown candidate')} ${item.line_number ? `· line ${escapeHtml(String(item.line_number))}` : ''}</li>`).join('')}
            </ul>
        </div>` : ''}
        ${commandRows.length ? `
        <div class="activity-item" style="margin:0.55rem 0;">
            <strong>Next repair commands</strong>
            <ul style="color:var(--text-dim);font-size:0.78rem;margin:0.35rem 0 0 1rem;">
                ${commandRows.map(row => `<li><code>${escapeHtml(row.command || '')}</code>${row.reason ? ` — ${escapeHtml(row.reason)}` : ''}</li>`).join('')}
            </ul>
        </div>` : ''}
        ${missingPreview.length ? `<ul style="color:var(--warning);font-size:0.82rem;margin:0.4rem 0 0 1rem;">${missingPreview.map(id => `<li>${escapeHtml(id)}</li>`).join('')}</ul>` : '<p style="color:var(--text-dim);font-size:0.82rem;margin:0.35rem 0;">No missing candidate coverage preview.</p>'}
    `;
}

function renderBecomussyResumePacket(packet) {
    const el = document.getElementById('self-improvement-resume-packet');
    if (!el) return;
    const featureResume = packet.feature_resume || {};
    const queue = featureResume.queue || {};
    const ledger = featureResume.ledger || {};
    const actions = packet.next_actions || [];
    const generated = packet.generated_at || 'not generated';
    const status = packet.exists === false ? 'missing' : (packet.ok === false ? 'attention' : 'ready');
    el.innerHTML = `
        <h4>Becomussy Resume Packet</h4>
        <div class="message-meta" style="margin:0.5rem 0;">
            <span class="meta-pill">${escapeHtml(status)}</span>
            <span class="meta-pill">resumable: ${escapeHtml(String(queue.resumable_count ?? 0))}</span>
            <span class="meta-pill">recoverable runs: ${escapeHtml(String(ledger.recoverable_run_count ?? 0))}</span>
        </div>
        <p style="color:var(--text-dim);font-size:0.84rem;margin:0.45rem 0;">Generated: ${escapeHtml(generated)}</p>
        <p style="color:var(--text-dim);font-size:0.84rem;margin:0.45rem 0;">Source: ${escapeHtml(packet.source || packet?.sources?.self_improvement_home || 'waiting for packet')}</p>
        ${actions.length ? `<ul style="color:var(--warning);font-size:0.82rem;margin:0.4rem 0 0 1rem;">${actions.slice(0, 4).map(action => `<li>${escapeHtml(action)}</li>`).join('')}</ul>` : '<p style="color:var(--text-dim);font-size:0.82rem;margin:0.35rem 0;">No resume actions recorded.</p>'}
    `;
}

function renderSelfImprovementRuns(runs) {
    const el = document.getElementById('self-improvement-runs');
    if (!el) return;
    if (!runs.length) {
        el.innerHTML = '<p style="color:var(--text-dim);">No self-improvement runs recorded yet.</p>';
        return;
    }
    el.innerHTML = runs.map(run => {
        const stepSummary = run.step_journal_summary || {};
        const recoverable = Number(run.recoverable_step_count || stepSummary.recoverable_step_count || 0);
        const latestStepStatus = run.latest_step_status || stepSummary.latest_step_status || '—';
        const latestStep = stepSummary.latest_step || {};
        const recoverableSteps = Array.isArray(stepSummary.recoverable_steps) ? stepSummary.recoverable_steps : [];
        const recoveryHints = recoverableSteps
            .map(step => step.recovery_hint || step.step_name || '')
            .filter(Boolean)
            .slice(0, 2);
        return `
        <div class="activity-item" style="margin:0.75rem 0;">
            <div style="display:flex;justify-content:space-between;gap:0.75rem;flex-wrap:wrap;">
                <strong>${escapeHtml(run.run_id || 'unknown run')}</strong>
                <span class="meta-pill">${escapeHtml(run.outcome || 'unknown')} · ${escapeHtml(String(run.outcome_score ?? '—'))}</span>
            </div>
            <p style="color:var(--text-dim);font-size:0.84rem;margin:0.45rem 0;">${escapeHtml(run.summary || run.candidate || 'No summary')}</p>
            <div class="message-meta">
                <span>${escapeHtml(run.selected_layer || 'no layer')}</span>
                <span>${escapeHtml((run.verification_commands || []).join(', ') || 'no verification')}</span>
                <span>${escapeHtml((run.artifacts || []).join(', ') || 'no artifacts')}</span>
                <span class="meta-pill">steps: ${escapeHtml(String(stepSummary.count ?? 0))} · latest ${escapeHtml(String(latestStepStatus))}</span>
                <span class="meta-pill">recoverable steps: ${escapeHtml(String(recoverable))}</span>
            </div>
            ${(recoverable || latestStep.step_name) ? `<p style="color:${recoverable ? 'var(--warning)' : 'var(--text-dim)'};font-size:0.82rem;margin:0.4rem 0 0;">Latest step: ${escapeHtml(latestStep.step_name || 'unknown')} ${recoveryHints.length ? `· recovery: ${escapeHtml(recoveryHints.join(' · '))}` : ''}</p>` : ''}
        </div>
    `;
    }).join('');
}

function renderSelfImprovementQueue(queue) {
    const el = document.getElementById('self-improvement-queue');
    if (!el) return;
    const candidates = Array.isArray(queue) ? queue : (queue?.candidates || []);
    const statusCounts = queue?.status_counts || {};
    const gate = queue?.backlog_gate || {};
    const statusSummary = Object.keys(statusCounts).length
        ? Object.entries(statusCounts).map(([k, v]) => `${k}:${v}`).join(' · ')
        : 'none';
    const gateSummary = gate.action
        ? `${gate.action} · queued ${gate.queued_count ?? '—'} · selected ${gate.selected_count ?? '—'} · needed ${gate.needed_additions ?? gate.max_additions_this_tick ?? '—'}`
        : 'backlog gate unavailable';
    if (!candidates.length) {
        el.innerHTML = `
            <div class="message-meta" style="margin:0.5rem 0;">
                <span class="meta-pill">statuses: ${escapeHtml(statusSummary)}</span>
                <span class="meta-pill">${escapeHtml(gateSummary)}</span>
            </div>
            <p style="color:var(--text-dim);">No candidates yet. Add an evidence-backed candidate or let cron pause cleanly.</p>
        `;
        return;
    }
    el.innerHTML = `
        <div class="message-meta" style="margin:0.5rem 0;">
            <span class="meta-pill">statuses: ${escapeHtml(statusSummary)}</span>
            <span class="meta-pill">${escapeHtml(gateSummary)}</span>
            <span class="meta-pill">sources: ${escapeHtml(JSON.stringify(queue?.source_counts || {}))}</span>
        </div>
        ${(gate.reason || gate.queue_path) ? `<p style="color:var(--text-dim);font-size:0.82rem;margin:0.35rem 0;">${escapeHtml(gate.reason || '')} ${gate.queue_path ? `· ${gate.queue_path}` : ''}</p>` : ''}
        ${candidates.map(candidate => `
            <div class="activity-item" style="margin:0.75rem 0;">
                <div style="display:flex;justify-content:space-between;gap:0.75rem;align-items:flex-start;">
                    <strong>${escapeHtml(candidate.title || candidate.id || 'untitled')}</strong>
                    <span class="meta-pill">${escapeHtml(candidate.status || 'unknown')} · ${escapeHtml(String(candidate.score ?? '—'))}</span>
                </div>
                <p style="color:var(--text-dim);font-size:0.84rem;margin:0.45rem 0;">${escapeHtml(candidate.explanation || '')}</p>
                <div class="message-meta"><span>${escapeHtml(candidate.allowed_layer || 'no layer')}</span><span>${escapeHtml(candidate.risk || 'risk?')}</span></div>
            </div>
        `).join('')}
    `;
}

async function submitSelfImprovementCandidate(event) {
    event.preventDefault();
    const payload = {
        title: document.getElementById('si-candidate-title')?.value?.trim() || '',
        allowed_layer: document.getElementById('si-candidate-layer')?.value || 'dashboard_control_surface',
        evidence_source: document.getElementById('si-candidate-evidence')?.value?.trim() || '',
        expected_measurable_benefit: document.getElementById('si-candidate-benefit')?.value?.trim() || '',
        risk: 'low',
        evidence_strength: 4,
        expected_impact: 4,
        implementation_size: 2,
        verification_clarity: 4,
    };
    try {
        await fetchJsonOrThrow('/api/self-improvement/candidates', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        ['si-candidate-title','si-candidate-evidence','si-candidate-benefit'].forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
        showToast('Candidate added');
        await loadSelfImprovement();
    } catch (e) {
        showToast(`Candidate rejected: ${e.message}`, true);
    }
}

async function selectSelfImprovementCandidate() {
    const result = await fetchJsonOrThrow('/api/self-improvement/candidates/select', { method: 'POST' });
    showToast(result.decision === 'build' ? 'Candidate selected for build' : 'No candidate selected: loop should pause');
    await loadSelfImprovement();
}

async function selfImprovementControl(action, confirmAction = false) {
    if (confirmAction && !confirm(`Confirm ${action}?`)) return;
    try {
        const result = await fetchJsonOrThrow('/api/self-improvement/control', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action, confirm: confirmAction, actor: 'dashboard' }),
        });
        showToast(result.note || `Self-improvement ${action} complete`);
        await loadSelfImprovement();
    } catch (e) {
        showToast(`Control failed: ${e.message}`, true);
    }
}

async function loadAutonomousDevelopment() {
    const stats = document.getElementById('autonomous-development-stats');
    try {
        log('req', 'GET /api/autonomous-development');
        const data = await fetchJsonOrThrow('/api/autonomous-development');
        renderAutonomousDevelopment(data);
        if (stats) stats.textContent = `${data.count || 0} pipelines · ${data.active_count || 0} active · registry ${data.registry_path || '—'}`;
        log('res', 'Loaded autonomous development pipelines');
    } catch (e) {
        if (stats) stats.textContent = '';
        const list = document.getElementById('autonomous-development-pipelines');
        if (list) list.innerHTML = `<p style="color:var(--error);">Failed to load autonomous development pipelines: ${escapeHtml(e.message)}</p>`;
        showToast(`Autonomous development load failed: ${e.message}`, true);
    }
}

function renderAutonomousDevelopment(data) {
    const el = document.getElementById('autonomous-development-pipelines');
    if (!el) return;
    const pipelines = data?.pipelines || [];
    if (!pipelines.length) {
        el.innerHTML = '<p style="color:var(--text-dim);">No pipelines registered yet.</p>';
        return;
    }
    el.innerHTML = pipelines.map(pipeline => {
        const jobs = pipeline.jobs_summary?.jobs || [];
        const specs = pipeline.specifications || {};
        const missing = (pipeline.missing_jobs || []).join(', ');
        return `
            <div class="activity-item" style="margin:0.85rem 0;padding:0.85rem;border:1px solid var(--border-subtle);border-radius:10px;">
                <div style="display:flex;justify-content:space-between;gap:0.75rem;flex-wrap:wrap;align-items:flex-start;">
                    <div style="min-width:0;">
                        <strong>${escapeHtml(pipeline.name || pipeline.id)}</strong>
                        <p style="color:var(--text-dim);font-size:0.84rem;margin:0.35rem 0;">${escapeHtml(pipeline.description || '')}</p>
                    </div>
                    <span class="meta-pill">${pipeline.active ? 'active' : 'paused'} · ${escapeHtml(pipeline.activation_mode || 'manual')}</span>
                </div>
                <div class="message-meta" style="margin:0.5rem 0;">
                    <span>${escapeHtml(pipeline.kind || 'custom')}</span>
                    <span>jobs ${escapeHtml(String(pipeline.jobs_summary?.active || 0))}/${escapeHtml(String(pipeline.jobs_summary?.total || 0))}</span>
                    <span>${escapeHtml(pipeline.schedule || 'no schedule')}</span>
                </div>
                ${missing ? `<p style="color:var(--warning);font-size:0.82rem;">Missing jobs: ${escapeHtml(missing)}</p>` : ''}
                <details style="margin-top:0.55rem;">
                    <summary style="cursor:pointer;color:var(--primary);">Specifications & linked jobs</summary>
                    <div style="display:grid;gap:0.55rem;margin-top:0.55rem;font-size:0.83rem;color:var(--text-dim);">
                        <div><strong style="color:var(--text);">Research:</strong> ${escapeHtml(specs.research || '—')}</div>
                        <div><strong style="color:var(--text);">Tournament:</strong> ${escapeHtml(specs.tournament || '—')}</div>
                        <div><strong style="color:var(--text);">Build/Curation:</strong> ${escapeHtml(specs.build || '—')}</div>
                        <div><strong style="color:var(--text);">Safety:</strong> ${escapeHtml(specs.safety || '—')}</div>
                        <div><strong style="color:var(--text);">Jobs:</strong> ${escapeHtml(jobs.map(job => `${job.enabled ? 'ACTIVE' : 'paused'} ${job.name}`).join(' · ') || 'none linked')}</div>
                        <div><strong style="color:var(--text);">Dirs:</strong> ${escapeHtml((pipeline.directories || []).join(' · ') || '—')}</div>
                    </div>
                </details>
                <div class="cron-actions-row" style="margin-top:0.75rem;">
                    <button onclick="controlAutonomousDevelopmentPipeline('${escapeHtml(pipeline.id)}', 'enable')">Enable Linked Jobs</button>
                    <button onclick="controlAutonomousDevelopmentPipeline('${escapeHtml(pipeline.id)}', 'disable')">Disable Linked Jobs</button>
                    <button onclick="editAutonomousDevelopmentPipeline('${escapeHtml(pipeline.id)}')">Edit Specs</button>
                </div>
            </div>
        `;
    }).join('');
}

async function submitAutonomousDevelopmentPipeline(event) {
    event.preventDefault();
    const payload = {
        name: document.getElementById('ad-name')?.value?.trim() || '',
        description: document.getElementById('ad-description')?.value?.trim() || '',
        job_names: (document.getElementById('ad-jobs')?.value || '').split(',').map(x => x.trim()).filter(Boolean),
        schedule: document.getElementById('ad-schedule')?.value?.trim() || '',
        research_specification: document.getElementById('ad-research-spec')?.value?.trim() || '',
        tournament_specification: document.getElementById('ad-tournament-spec')?.value?.trim() || '',
        build_specification: document.getElementById('ad-build-spec')?.value?.trim() || '',
        safety_policy: document.getElementById('ad-safety-policy')?.value?.trim() || '',
    };
    try {
        await fetchJsonOrThrow('/api/autonomous-development/pipelines', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        document.getElementById('autonomous-development-form')?.reset();
        showToast('Pipeline created');
        await loadAutonomousDevelopment();
    } catch (e) {
        showToast(`Pipeline create failed: ${e.message}`, true);
    }
}

async function controlAutonomousDevelopmentPipeline(pipelineId, action) {
    if (action === 'enable' && !confirm(`Enable all linked jobs for ${pipelineId}?`)) return;
    try {
        const result = await fetchJsonOrThrow(`/api/autonomous-development/pipelines/${encodeURIComponent(pipelineId)}/control`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action, actor: 'dashboard' }),
        });
        showToast(`${action} touched ${result.touched_jobs?.length || 0} jobs`);
        invalidateCache('/api/cron');
        await loadAutonomousDevelopment();
    } catch (e) {
        showToast(`Pipeline ${action} failed: ${e.message}`, true);
    }
}

async function editAutonomousDevelopmentPipeline(pipelineId) {
    const data = await fetchJsonOrThrow('/api/autonomous-development');
    const pipeline = (data.pipelines || []).find(p => p.id === pipelineId);
    if (!pipeline) return showToast('Pipeline not found', true);
    const specs = pipeline.specifications || {};
    const research = prompt('Research specification', specs.research || '');
    if (research === null) return;
    const tournament = prompt('Tournament specification', specs.tournament || '');
    if (tournament === null) return;
    const build = prompt('Build / curation specification', specs.build || '');
    if (build === null) return;
    const safety = prompt('Safety policy', specs.safety || '');
    if (safety === null) return;
    await fetchJsonOrThrow(`/api/autonomous-development/pipelines/${encodeURIComponent(pipelineId)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            specifications: { research, tournament, build, safety },
        }),
    });
    showToast('Pipeline specifications updated');
    await loadAutonomousDevelopment();
}

let nexussyLastData = null;
let nexussyActiveRunId = null;
let nexussyActiveSessionId = null;

function nexussyActiveIds(data = nexussyLastData) {
    const active = data?.active_session || {};
    const run = data?.latest_status?.run || {};
    return {
        runId: run.run_id || active.last_run_id || nexussyActiveRunId || null,
        sessionId: run.session_id || active.session_id || nexussyActiveSessionId || null,
    };
}

async function loadNexussy() {
    const stats = document.getElementById('nexussy-stats');
    try {
        log('req', 'GET /api/nexussy');
        const data = await fetchJsonOrThrow('/api/nexussy');
        nexussyLastData = data;
        const ids = nexussyActiveIds(data);
        nexussyActiveRunId = ids.runId;
        nexussyActiveSessionId = ids.sessionId;
        renderNexussy(data);
        log('res', 'Loaded Nexussy control plane');
    } catch (e) {
        if (stats) stats.textContent = '';
        ['nexussy-health','nexussy-progress','nexussy-artifacts','nexussy-workers','nexussy-events'].forEach(id => {
            const el = document.getElementById(id);
            if (el) el.innerHTML = `<h4>${escapeHtml(id.replace('nexussy-','').replace('-', ' '))}</h4><p style="color:var(--error);">${escapeHtml(e.message)}</p>`;
        });
        showToast(`Nexussy load failed: ${e.message}`, true);
    }
}

function renderNexussy(data) {
    const health = data?.health || {};
    const guard = data?.model_guard || {};
    const sessions = data?.sessions || [];
    const status = data?.latest_status || {};
    const run = status.run || {};
    const artifacts = data?.artifacts?.artifacts || [];
    const workers = data?.workers || [];
    const stats = document.getElementById('nexussy-stats');
    if (stats) {
        stats.textContent = `${health.ok ? 'healthy' : 'offline'} · ${sessions.length} recent sessions · active ${run.status || data?.active_session?.status || 'none'} · model guard ${guard.ok ? 'ok' : 'needs override'}`;
    }
    renderNexussyHealth(health, guard, data?.nexussy_api);
    renderNexussyProgress(status, sessions);
    renderNexussyArtifacts(artifacts, run.session_id || data?.active_session?.session_id);
    renderNexussyWorkers(workers);
    renderNexussySafety(data, artifacts);
    renderNexussyInterview(data);
    if (run.run_id) loadNexussyEvents(run.run_id);
    else {
        const events = document.getElementById('nexussy-events');
        if (events) events.innerHTML = '<h4>Recent Events</h4><p style="color:var(--text-dim);">No active run yet.</p>';
    }
}

function renderNexussyHealth(health, guard, api) {
    const el = document.getElementById('nexussy-health');
    if (!el) return;
    const missing = guard?.missing || [];
    el.innerHTML = `
        <h4>Health & Model Guard</h4>
        <div class="message-meta" style="margin:0.5rem 0;">
            <span class="meta-pill">${health?.ok ? 'sidecar healthy' : 'sidecar offline'}</span>
            <span class="meta-pill">providers: ${escapeHtml((health?.providers_configured || []).join(', ') || 'none')}</span>
            <span class="meta-pill">pi: ${health?.pi_available ? 'available' : 'not available'}</span>
        </div>
        <p style="color:var(--text-dim);font-size:0.83rem;">${escapeHtml(api || '')}</p>
        ${missing.length ? `<p style="color:var(--warning);font-size:0.84rem;">${escapeHtml(guard.message || 'Model override recommended.')} Dashboard launch defaults to ${escapeHtml(guard.recommended_model || '')} for all stages.</p>` : '<p style="color:var(--success);font-size:0.84rem;">Configured stage model providers are available.</p>'}
        ${missing.length ? `<details><summary style="cursor:pointer;color:var(--primary);">Unavailable stage models</summary><div class="message-meta" style="margin-top:0.5rem;">${missing.map(m => `<span>${escapeHtml(m.stage)} → ${escapeHtml(m.model)}</span>`).join('')}</div></details>` : ''}
    `;
}

function renderNexussyProgress(status, sessions) {
    const el = document.getElementById('nexussy-progress');
    if (!el) return;
    const run = status?.run || {};
    const stages = status?.stages || [];
    const blockers = status?.blockers || [];
    if (!run.run_id) {
        el.innerHTML = `<h4>Pipeline Progress</h4><p style="color:var(--text-dim);">No active run. Recent sessions: ${escapeHtml(String((sessions || []).length))}</p>`;
        return;
    }
    el.innerHTML = `
        <h4>Pipeline Progress</h4>
        <div class="message-meta" style="margin:0.5rem 0;">
            <span class="meta-pill">${escapeHtml(run.status || 'unknown')}</span>
            <span class="meta-pill">stage: ${escapeHtml(run.current_stage || '—')}</span>
            <span class="meta-pill">run ${escapeHtml(String(run.run_id).slice(0, 12))}</span>
            <span class="meta-pill">session ${escapeHtml(String(run.session_id || '').slice(0, 12))}</span>
        </div>
        ${blockers.length ? `<p style="color:var(--warning);font-size:0.84rem;">Blockers: ${escapeHtml(blockers.map(b => b.message || b.reason || JSON.stringify(b)).join(' · '))}</p>` : ''}
        <div style="display:grid;gap:0.45rem;margin-top:0.75rem;">${stages.map(stage => `
            <div class="activity-item" style="padding:0.55rem;">
                <div style="display:flex;justify-content:space-between;gap:0.5rem;"><strong>${escapeHtml(stage.stage || 'stage')}</strong><span class="meta-pill">${escapeHtml(stage.status || 'pending')}</span></div>
                ${stage.error ? `<p style="color:var(--error);font-size:0.82rem;margin:0.25rem 0 0;">${escapeHtml(stage.error)}</p>` : ''}
            </div>
        `).join('')}</div>
    `;
}

function renderNexussyArtifacts(artifacts, sessionId) {
    const el = document.getElementById('nexussy-artifacts');
    if (!el) return;
    if (!artifacts.length) {
        el.innerHTML = '<h4>Artifacts</h4><p style="color:var(--text-dim);">No artifacts yet. Interview/design output will appear here.</p>';
        return;
    }
    el.innerHTML = `<h4>Artifacts</h4>${artifacts.map(a => `
        <div class="activity-item" style="margin:0.55rem 0;">
            <div style="display:flex;justify-content:space-between;gap:0.5rem;align-items:flex-start;"><strong>${escapeHtml(a.kind || 'artifact')}</strong><span class="meta-pill">${escapeHtml(String(a.bytes || 0))} bytes</span></div>
            <p style="color:var(--text-dim);font-size:0.8rem;margin:0.35rem 0;">${escapeHtml(a.path || '')}</p>
            <button class="btn" onclick="loadNexussyArtifact('${escapeHtml(a.kind || '')}', '${escapeHtml(sessionId || '')}')">Open</button>
        </div>
    `).join('')}<pre id="nexussy-artifact-preview" style="white-space:pre-wrap;max-height:220px;overflow:auto;background:var(--input-bg);padding:0.75rem;border-radius:8px;color:var(--text-dim);"></pre>`;
}

async function loadNexussyArtifact(kind, sessionId) {
    if (!kind || !sessionId) return showToast('No artifact session available yet', true);
    try {
        const data = await fetchJsonOrThrow(`/api/nexussy/artifacts/${encodeURIComponent(kind)}?session_id=${encodeURIComponent(sessionId)}`);
        const preview = document.getElementById('nexussy-artifact-preview');
        if (preview) preview.textContent = data.content_text || JSON.stringify(data, null, 2);
    } catch (e) {
        showToast(`Artifact load failed: ${e.message}`, true);
    }
}

function renderNexussyWorkers(workers) {
    const el = document.getElementById('nexussy-workers');
    if (!el) return;
    if (!workers.length) {
        el.innerHTML = '<h4>Workers</h4><p style="color:var(--text-dim);">No workers spawned yet. Develop-stage workers will appear here.</p>';
        return;
    }
    el.innerHTML = `<h4>Workers</h4>${workers.map(w => `
        <div class="activity-item" style="margin:0.55rem 0;">
            <div style="display:flex;justify-content:space-between;gap:0.5rem;"><strong>${escapeHtml(w.worker_id || 'worker')}</strong><span class="meta-pill">${escapeHtml(w.status || 'unknown')}</span></div>
            <p style="color:var(--text-dim);font-size:0.82rem;margin:0.35rem 0;">${escapeHtml(w.role || '')} · ${escapeHtml(w.task_title || w.task_id || 'no task')}</p>
        </div>
    `).join('')}`;
}

function renderNexussySafety(data, artifacts) {
    const el = document.getElementById('nexussy-safety');
    if (!el) return;
    const changed = (artifacts || []).find(a => a.kind === 'changed_files');
    const merge = (artifacts || []).find(a => a.kind === 'merge_report' || a.kind === 'conflict_report');
    el.innerHTML = `
        <h4>Safety / Merge Gate</h4>
        <div class="message-meta" style="margin:0.5rem 0;"><span class="meta-pill">preview-first</span><span class="meta-pill">explicit merge only</span><span class="meta-pill">${changed ? 'changed files ready' : 'no changed_files yet'}</span></div>
        <p style="color:var(--text-dim);font-size:0.84rem;">${merge ? 'Merge/conflict report is available in artifacts. Review before applying generated work.' : 'Nexussy artifacts will surface review/develop/merge reports here before any handoff.'}</p>
    `;
}

function renderNexussyInterview(data) {
    const el = document.getElementById('nexussy-interview');
    if (!el) return;
    const ids = nexussyActiveIds(data);
    const status = data?.latest_status || {};
    const paused = status?.paused || status?.run?.status === 'paused';
    if (!ids.sessionId) {
        el.innerHTML = '<h4>Interview</h4><p style="color:var(--text-dim);">Launch a pipeline to let Nexussy interview you inside Hermes.</p>';
        return;
    }
    el.innerHTML = `
        <h4>Interview</h4>
        <p style="color:var(--text-dim);font-size:0.84rem;">Session ${escapeHtml(String(ids.sessionId).slice(0, 16))}${paused ? ' is paused for input.' : ' interview artifact can be opened from Artifacts.'}</p>
        <textarea id="nexussy-interview-json" placeholder='Paste answer JSON, e.g. {"q1":"..."}' style="width:100%;min-height:92px;"></textarea>
        <button class="btn primary" onclick="submitNexussyInterviewAnswer()">Submit Answers</button>
        <button class="btn" onclick="loadNexussyArtifact('interview', '${escapeHtml(ids.sessionId)}')">Open Interview Artifact</button>
    `;
}

async function loadNexussyEvents(runId) {
    const el = document.getElementById('nexussy-events');
    if (!el || !runId) return;
    try {
        const data = await fetchJsonOrThrow(`/api/nexussy/runs/${encodeURIComponent(runId)}/events?limit=80`);
        const events = data.events || [];
        el.innerHTML = `<h4>Recent Events</h4>${events.slice(-25).reverse().map(ev => `
            <div class="activity-item" style="margin:0.45rem 0;"><div style="display:flex;justify-content:space-between;gap:0.5rem;"><strong>${escapeHtml(ev.type || 'event')}</strong><span class="meta-pill">#${escapeHtml(String(ev.sequence || ''))}</span></div><p style="color:var(--text-dim);font-size:0.8rem;margin:0.25rem 0 0;">${escapeHtml(JSON.stringify(ev.payload || {}).slice(0, 220))}</p></div>
        `).join('') || '<p style="color:var(--text-dim);">No events yet.</p>'}`;
    } catch (e) {
        el.innerHTML = `<h4>Recent Events</h4><p style="color:var(--error);">${escapeHtml(e.message)}</p>`;
    }
}

async function startNexussySidecar() {
    try {
        const result = await fetchJsonOrThrow('/api/nexussy/sidecar/start', { method: 'POST' });
        showToast(result.already_running ? 'Nexussy already running' : `Nexussy starting pid ${result.pid || 'unknown'}`);
        setTimeout(loadNexussy, 1200);
    } catch (e) {
        showToast(`Nexussy start failed: ${e.message}`, true);
    }
}

async function launchNexussy(event) {
    if (event) event.preventDefault();
    const payload = {
        project_name: document.getElementById('nexussy-project-name')?.value?.trim() || '',
        project_slug: document.getElementById('nexussy-project-slug')?.value?.trim() || undefined,
        description: document.getElementById('nexussy-description')?.value?.trim() || '',
        existing_repo_path: document.getElementById('nexussy-repo-path')?.value?.trim() || undefined,
        start_stage: document.getElementById('nexussy-start-stage')?.value || 'interview',
        stop_after_stage: document.getElementById('nexussy-stop-stage')?.value || 'develop',
        auto_approve_interview: Boolean(document.getElementById('nexussy-auto-approve')?.checked),
        auto_model_override: Boolean(document.getElementById('nexussy-auto-model-override')?.checked),
        stage_model: document.getElementById('nexussy-stage-model')?.value?.trim() || 'openrouter/openai/gpt-4o-mini',
        metadata: { source: 'hermes_dashboard', ussyverse: true },
    };
    try {
        const result = await fetchJsonOrThrow('/api/nexussy/pipelines', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        nexussyActiveRunId = result.run_id || nexussyActiveRunId;
        nexussyActiveSessionId = result.session_id || nexussyActiveSessionId;
        showToast(`Nexussy pipeline launched: ${result.run_id || result.status || 'started'}`);
        await loadNexussy();
    } catch (e) {
        showToast(`Nexussy launch failed: ${e.message}`, true);
        await loadNexussy();
    }
}

async function nexussyControl(action, confirmAction = false) {
    const ids = nexussyActiveIds();
    if (!ids.runId) return showToast('No active Nexussy run selected', true);
    if (confirmAction && !confirm(`Confirm Nexussy ${action} for run ${ids.runId}?`)) return;
    try {
        await fetchJsonOrThrow(`/api/nexussy/runs/${encodeURIComponent(ids.runId)}/control`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action, reason: `${action} from Hermes Dashboard` }),
        });
        showToast(`Nexussy ${action} sent`);
        await loadNexussy();
    } catch (e) {
        showToast(`Nexussy ${action} failed: ${e.message}`, true);
    }
}

async function sendNexussySteering() {
    const ids = nexussyActiveIds();
    const status = document.getElementById('nexussy-steering-status');
    if (!ids.runId) return showToast('No active Nexussy run selected', true);
    const priority = document.getElementById('nexussy-steer-priority')?.value || 'normal';
    if (priority === 'urgent' && !confirm('Urgent steering can unblock paused waits. Send urgent steer?')) return;
    const payload = {
        target: document.getElementById('nexussy-steer-target')?.value || 'orchestrator',
        worker_id: document.getElementById('nexussy-steer-worker')?.value?.trim() || undefined,
        priority,
        message: document.getElementById('nexussy-steer-message')?.value?.trim() || '',
    };
    try {
        const result = await fetchJsonOrThrow(`/api/nexussy/runs/${encodeURIComponent(ids.runId)}/steer`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        if (status) status.textContent = `Steering queued: ${JSON.stringify(result).slice(0, 160)}`;
        showToast('Nexussy steering sent');
        await loadNexussy();
    } catch (e) {
        if (status) status.textContent = e.message;
        showToast(`Steering failed: ${e.message}`, true);
    }
}

async function sendNexussyInject() {
    const ids = nexussyActiveIds();
    if (!ids.runId) return showToast('No active Nexussy run selected', true);
    const message = document.getElementById('nexussy-steer-message')?.value?.trim() || '';
    try {
        await fetchJsonOrThrow(`/api/nexussy/runs/${encodeURIComponent(ids.runId)}/inject`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message }),
        });
        showToast('Nexussy context injected');
        await loadNexussy();
    } catch (e) {
        showToast(`Inject failed: ${e.message}`, true);
    }
}

async function submitNexussyInterviewAnswer() {
    const ids = nexussyActiveIds();
    if (!ids.sessionId) return showToast('No active Nexussy session selected', true);
    const raw = document.getElementById('nexussy-interview-json')?.value || '{}';
    let answers;
    try { answers = JSON.parse(raw); } catch (e) { return showToast('Interview answers must be JSON', true); }
    try {
        await fetchJsonOrThrow(`/api/nexussy/sessions/${encodeURIComponent(ids.sessionId)}/interview-answer`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ answers }),
        });
        showToast('Interview answers submitted');
        await loadNexussy();
    } catch (e) {
        showToast(`Interview submit failed: ${e.message}`, true);
    }
}

// ── Cron Jobs ──
let allCronJobs = [];

async function loadCronJobs() {
    log('req', 'GET /api/cron');
    try {
        const data = await cachedFetch('/api/cron', 30000);
        allCronJobs = data.jobs || [];
        log('res', `Loaded ${allCronJobs.length} cron jobs`);
        filterCronJobs();
    } catch (e) {
        log('err', 'Failed to load cron jobs: ' + e.message, true);
        document.getElementById('cron-list').innerHTML =
            '<div style="text-align:center;color:var(--text-dim);padding:2rem;">Failed to load jobs</div>';
    }
}

function filterCronJobs() {
    const search = (document.getElementById('cron-search')?.value || '').toLowerCase();
    const filter = document.getElementById('cron-filter')?.value || '';

    let filtered = allCronJobs;
    if (search) {
        filtered = filtered.filter(j =>
            (j.name || '').toLowerCase().includes(search) ||
            (j.prompt || '').toLowerCase().includes(search) ||
            (j.id || '').toLowerCase().includes(search)
        );
    }
    if (filter === 'enabled') {
        filtered = filtered.filter(j => j.enabled !== false);
    } else if (filter === 'paused') {
        filtered = filtered.filter(j => j.enabled === false || j.state === 'paused');
    }

    const stats = document.getElementById('cron-stats');
    if (stats) stats.textContent = `${filtered.length} of ${allCronJobs.length} jobs`;

    const list = document.getElementById('cron-list');
    if (!filtered.length) {
        list.innerHTML = '<div style="text-align:center;color:var(--text-dim);padding:2rem;">No jobs match</div>';
        return;
    }

    list.innerHTML = filtered.map(j => {
        const isPaused = j.enabled === false || j.state === 'paused';
        const statusClass = isPaused ? 'paused' : 'scheduled';
        const statusText = isPaused ? 'Paused' : 'Scheduled';
        const schedule = j.schedule_display || (j.schedule ? j.schedule.display : '');
        const completed = j.repeat?.completed ?? 0;
        const nextRun = j.next_run_at ? formatRelativeTime(new Date(j.next_run_at)) : '—';
        const lastRun = j.last_run_at ? formatRelativeTime(new Date(j.last_run_at)) : 'never';
        const promptPreview = (j.prompt || '').substring(0, 120);

        return `
            <div class="cron-card ${isPaused ? 'paused' : ''}">
                <div class="cron-card-header">
                    <h4>${escapeHtml(j.name || j.id)}</h4>
                    <span class="cron-status ${statusClass}">${statusText}</span>
                </div>
                <div class="cron-meta">
                    <span>⏱ ${escapeHtml(schedule || '—')}</span>
                    <span>✓ ${completed} runs</span>
                    <span>→ ${escapeHtml(nextRun)}</span>
                    <span>← ${escapeHtml(lastRun)}</span>
                </div>
                <div class="cron-prompt-preview">${escapeHtml(promptPreview)}${(j.prompt || '').length > 120 ? '…' : ''}</div>
                <div class="cron-actions-row">
                    ${isPaused
                        ? `<button class="primary" onclick="resumeCronJob('${escapeHtml(j.id)}')">Resume</button>`
                        : `<button onclick="pauseCronJob('${escapeHtml(j.id)}')">Pause</button>`}
                    <button onclick="runCronJob('${escapeHtml(j.id)}')">Run Now</button>
                    <button onclick="editCronJob('${escapeHtml(j.id)}')">Edit</button>
                    <button class="danger" onclick="deleteCronJob('${escapeHtml(j.id)}')">Delete</button>
                </div>
            </div>
        `;
    }).join('');
}

async function pauseCronJob(jobId) {
    try {
        log('req', `POST /api/cron/${jobId}/pause`);
        await fetchJsonOrThrow(`/api/cron/${encodeURIComponent(jobId)}/pause`, { method: 'POST' });
        log('res', `Job ${jobId} paused`);
        showToast('Job paused');
        invalidateCache('/api/cron');
        loadCronJobs();
    } catch (e) {
        showToast(`Pause failed: ${e.message}`, true);
        log('err', `Pause failed: ${e.message}`, true);
    }
}

async function resumeCronJob(jobId) {
    try {
        log('req', `POST /api/cron/${jobId}/resume`);
        await fetchJsonOrThrow(`/api/cron/${encodeURIComponent(jobId)}/resume`, { method: 'POST' });
        log('res', `Job ${jobId} resumed`);
        showToast('Job resumed');
        invalidateCache('/api/cron');
        loadCronJobs();
    } catch (e) {
        showToast(`Resume failed: ${e.message}`, true);
        log('err', `Resume failed: ${e.message}`, true);
    }
}

async function runCronJob(jobId) {
    try {
        log('req', `POST /api/cron/${jobId}/run`);
        await fetchJsonOrThrow(`/api/cron/${encodeURIComponent(jobId)}/run`, { method: 'POST' });
        log('res', `Job ${jobId} triggered`);
        showToast('Job triggered');
        invalidateCache('/api/cron');
        loadCronJobs();
    } catch (e) {
        showToast(`Run failed: ${e.message}`, true);
        log('err', `Run failed: ${e.message}`, true);
    }
}

async function deleteCronJob(jobId) {
    if (!confirm(`Delete job "${jobId}"? This cannot be undone.`)) return;
    try {
        log('req', `DELETE /api/cron/${jobId}`);
        await fetchJsonOrThrow(`/api/cron/${encodeURIComponent(jobId)}`, { method: 'DELETE' });
        log('res', `Job ${jobId} deleted`);
        showToast('Job deleted');
        invalidateCache('/api/cron');
        loadCronJobs();
    } catch (e) {
        showToast(`Delete failed: ${e.message}`, true);
        log('err', `Delete failed: ${e.message}`, true);
    }
}

function openCronModal(jobId) {
    const modal = document.getElementById('cron-modal');
    const title = document.getElementById('cron-modal-title');
    if (jobId) {
        const job = allCronJobs.find(j => j.id === jobId);
        if (!job) return;
        title.textContent = 'Edit Cron Job';
        document.getElementById('cron-job-id').value = job.id;
        document.getElementById('cron-name').value = job.name || '';
        document.getElementById('cron-schedule').value = job.schedule_display || '';
        document.getElementById('cron-prompt').value = job.prompt || '';
        document.getElementById('cron-deliver').value = job.deliver || 'local';
        document.getElementById('cron-skills').value = (job.skills || []).join(', ');
        document.getElementById('cron-repeat').value = job.repeat?.times || '';
    } else {
        title.textContent = 'New Cron Job';
        document.getElementById('cron-job-id').value = '';
        document.getElementById('cron-name').value = '';
        document.getElementById('cron-schedule').value = '';
        document.getElementById('cron-prompt').value = '';
        document.getElementById('cron-deliver').value = 'local';
        document.getElementById('cron-skills').value = '';
        document.getElementById('cron-repeat').value = '';
    }
    modal.style.display = 'flex';
}

function closeCronModal() {
    document.getElementById('cron-modal').style.display = 'none';
}

function editCronJob(jobId) {
    openCronModal(jobId);
}

async function saveCronJob() {
    const jobId = document.getElementById('cron-job-id').value;
    const name = document.getElementById('cron-name').value.trim();
    const schedule = document.getElementById('cron-schedule').value.trim();
    const prompt = document.getElementById('cron-prompt').value;
    const deliver = document.getElementById('cron-deliver').value;
    const skillsRaw = document.getElementById('cron-skills').value;
    const skills = skillsRaw ? skillsRaw.split(',').map(s => s.trim()).filter(Boolean) : undefined;
    const repeatVal = document.getElementById('cron-repeat').value;
    const repeat = repeatVal ? parseInt(repeatVal, 10) : undefined;

    if (!name) {
        showToast('Name is required', true);
        return;
    }
    if (!schedule) {
        showToast('Schedule is required', true);
        return;
    }

    try {
        if (jobId) {
            log('req', `PATCH /api/cron/${jobId}`);
            const payload = { name, schedule, prompt, deliver };
            if (skills) payload.skills = skills;
            if (repeat !== undefined) payload.repeat = repeat;
            await fetchJsonOrThrow(`/api/cron/${encodeURIComponent(jobId)}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            log('res', `Job ${jobId} updated`);
            showToast('Job updated');
        } else {
            log('req', 'POST /api/cron');
            const payload = { name, schedule, prompt, deliver };
            if (skills) payload.skills = skills;
            if (repeat !== undefined) payload.repeat = repeat;
            await fetchJsonOrThrow('/api/cron', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            log('res', 'Job created');
            showToast('Job created');
        }
        closeCronModal();
        invalidateCache('/api/cron');
        loadCronJobs();
    } catch (e) {
        showToast(`Save failed: ${e.message}`, true);
        log('err', `Save failed: ${e.message}`, true);
    }
}

function formatRelativeTime(date) {
    const now = new Date();
    const diffMs = date - now;
    const diffSec = Math.round(diffMs / 1000);
    const absSec = Math.abs(diffSec);
    if (absSec < 60) return diffSec < 0 ? 'just now' : 'in moments';
    const absMin = Math.round(absSec / 60);
    if (absMin < 60) return diffSec < 0 ? `${absMin}m ago` : `in ${absMin}m`;
    const absHr = Math.round(absMin / 60);
    if (absHr < 24) return diffSec < 0 ? `${absHr}h ago` : `in ${absHr}h`;
    const absDay = Math.round(absHr / 24);
    return diffSec < 0 ? `${absDay}d ago` : `in ${absDay}d`;
}

// Save functions
async function saveMemory(silent = false) {
    log('req', 'POST /api/memory');
    await fetchJsonOrThrow('/api/memory', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            memory: document.getElementById('memory-text').value,
            user_profile: document.getElementById('user-profile-text').value
        })
    });
    log('res', 'Memory saved');
    invalidateCache('/api/memory');
    if (!silent) showToast('Memory saved');
}

function updateMemoryCharCount() {
    const memChars = document.getElementById('memory-text').value.length;
    const userChars = document.getElementById('user-profile-text').value.length;
    document.getElementById('memory-chars').textContent = memChars.toLocaleString() + ' chars';
    document.getElementById('user-chars').textContent = userChars.toLocaleString() + ' chars';
}

// Auto-save with debounce
const autoSaveMemory = debounce(async () => {
    const status = document.getElementById('memory-autosave-status');
    status.textContent = 'Auto-saving...';
    try {
        await saveMemory(true);
        status.textContent = 'Auto-saved';
        setTimeout(() => { status.textContent = ''; }, 2000);
    } catch(e) {
        status.textContent = 'Auto-save failed';
        log('warn', 'Memory auto-save failed: ' + e.message);
    }
}, 5000);

// Hook auto-save to textarea input events
document.getElementById('memory-text')?.addEventListener('input', autoSaveMemory);
document.getElementById('user-profile-text')?.addEventListener('input', autoSaveMemory);

function toggleMemoryPreview() {
    const preview = document.getElementById('memory-preview');
    if (preview.style.display === 'none') {
        const memText = document.getElementById('memory-text').value;
        const userText = document.getElementById('user-profile-text').value;
        // Simple markdown to HTML (basic rendering)
        preview.innerHTML = '<h4 style="color:var(--primary);margin-bottom:0.5rem;">Agent Memory</h4>' +
            formatMessageContent(memText) +
            '<hr style="border-color:var(--border-subtle);margin:1rem 0;">' +
            '<h4 style="color:var(--primary);margin-bottom:0.5rem;">User Profile</h4>' +
            formatMessageContent(userText);
        preview.style.display = 'block';
    } else {
        preview.style.display = 'none';
    }
}

// Secrets functions
let currentEditKey = null;

async function loadSecrets() {
    log('req', 'GET /api/secrets');
    const data = await cachedFetch('/api/secrets', 30000);
    log('res', `Loaded ${data.secrets.length} secrets`);

    const categories = {
        provider: [],
        messaging: [],
        tool: [],
        setting: [],
        other: []
    };

    data.secrets.forEach(s => {
        if (categories[s.category]) {
            categories[s.category].push(s);
        } else {
            categories.other.push(s);
        }
    });

    const categoryNames = {
        provider: 'API Providers',
        messaging: 'Messaging & Gateway',
        tool: 'Tools & Services',
        setting: 'Runtime Settings',
        other: 'Other Secrets'
    };

    let html = '';

    for (const [cat, secrets] of Object.entries(categories)) {
        if (!secrets.length) continue;

        html += `<div class="secret-category">${categoryNames[cat] || cat}</div>`;

        secrets.forEach(s => {
            html += `
                <div class="secret-item ${s.configured ? '' : 'not-configured'}">
                    <div class="secret-info">
                        <h4>${s.name}</h4>
                        <p>${s.key}${s.masked_value ? `: ${s.masked_value}` : ''}</p>
                        ${s.description ? `<div class="secret-description">${escapeHtml(s.description)}</div>` : ''}
                        ${s.url ? `<a href="${s.url}" target="_blank" class="secret-link">Get API key →</a>` : ''}
                    </div>
                    <div class="secret-actions">
                        <span class="secret-status ${s.configured ? 'configured' : 'not-configured'}">
                            ${s.configured ? 'configured' : 'not set'}
                        </span>
                        <button class="btn" onclick="editSecret('${s.key}')">${s.configured ? 'Edit' : 'Add'}</button>
                        ${s.configured ? `<button class="btn" style="color: var(--error); border-color: rgba(248,113,113,0.3);" onclick="deleteSecret('${s.key}')">Delete</button>` : ''}
                    </div>
                </div>
            `;
        });
    }

    document.getElementById('secrets-list').innerHTML = html;
}

document.getElementById('new-secret-key').addEventListener('change', function() {
    const customInput = document.getElementById('custom-secret-key');
    if (this.value === 'custom') {
        customInput.style.display = 'block';
        customInput.focus();
    } else {
        customInput.style.display = 'none';
    }
});

async function addSecret() {
    const select = document.getElementById('new-secret-key');
    const customInput = document.getElementById('custom-secret-key');
    const valueInput = document.getElementById('new-secret-value');

    let key = select.value;
    if (key === 'custom') {
        key = customInput.value.trim().toUpperCase().replace(/[^A-Z0-9_]/g, '_');
        if (!key) {
            showToast('Please enter a key name', true);
            return;
        }
    }

    const value = valueInput.value.trim();
    if (!key || !value) {
        showToast('Please fill in all fields', true);
        return;
    }

    try {
        log('req', `POST /api/secrets {key: ${key}}`);
        await fetchJsonOrThrow('/api/secrets', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ key, value })
        });
        log('res', 'Secret saved');

        select.value = '';
        customInput.value = '';
        customInput.style.display = 'none';
        valueInput.value = '';

        showToast('Secret saved');
        invalidateCache('/api/secrets');
        loadSecrets();
        loadStatus();
    } catch (e) {
        showToast('Secret save failed: ' + e.message, true);
        log('err', 'Secret save failed: ' + e.message, true);
    }
}

function editSecret(key) {
    currentEditKey = key;
    document.getElementById('edit-secret-value').value = '';
    document.getElementById('edit-modal').classList.add('active');
    document.getElementById('edit-secret-value').focus();
}

async function saveEditSecret() {
    const value = document.getElementById('edit-secret-value').value.trim();
    if (!value) {
        showToast('Please enter a value', true);
        return;
    }

    try {
        log('req', `POST /api/secrets {key: ${currentEditKey}}`);
        await fetchJsonOrThrow('/api/secrets', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ key: currentEditKey, value })
        });
        log('res', 'Secret updated');

        closeEditModal();
        showToast('Secret updated');
        invalidateCache('/api/secrets');
        loadSecrets();
        loadStatus();
    } catch (e) {
        showToast('Secret update failed: ' + e.message, true);
        log('err', 'Secret update failed: ' + e.message, true);
    }
}

function closeEditModal() {
    document.getElementById('edit-modal').classList.remove('active');
    currentEditKey = null;
}

async function deleteSecret(key) {
    if (!confirm(`Delete ${key}? This cannot be undone.`)) return;

    try {
        log('req', `DELETE /api/secrets/${key}`);
        await fetchJsonOrThrow(`/api/secrets/${encodeURIComponent(key)}`, { method: 'DELETE' });
        log('res', 'Secret deleted');
        showToast('Secret deleted');
        invalidateCache('/api/secrets');
        loadSecrets();
        loadStatus();
    } catch (e) {
        showToast('Secret delete failed: ' + e.message, true);
        log('err', 'Secret delete failed: ' + e.message, true);
    }
}

// Chat functions
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function markdownTableCells(line) {
    let trimmed = String(line || '').trim();
    if (!trimmed.includes('|')) return [];
    if (trimmed.startsWith('|')) trimmed = trimmed.slice(1);
    if (trimmed.endsWith('|')) trimmed = trimmed.slice(0, -1);
    return trimmed.split('|').map(cell => cell.trim());
}

function isMarkdownTableSeparator(line) {
    const cells = markdownTableCells(line);
    return cells.length >= 2 && cells.every(cell => /^:?-{3,}:?$/.test(cell.replace(/\s+/g, '')));
}

function markdownTableAlignments(separatorLine) {
    return markdownTableCells(separatorLine).map(cell => {
        const compact = cell.replace(/\s+/g, '');
        if (compact.startsWith(':') && compact.endsWith(':')) return 'center';
        if (compact.endsWith(':')) return 'right';
        return 'left';
    });
}

function renderMarkdownInline(rawText) {
    const imageRegex = /(data:image\/(png|jpeg|jpg|gif|webp);base64,[A-Za-z0-9+/=]+)/g;
    const codeTokens = [];
    let text = String(rawText ?? '').replace(/`([^`]+)`/g, (_, code) => {
        const token = `\u0000CODE${codeTokens.length}\u0000`;
        codeTokens.push(`<code>${escapeHtml(code)}</code>`);
        return token;
    });

    let html = escapeHtml(text);
    html = html.replace(imageRegex, (match) => {
        return `<div class="image-container"><img src="${match}" class="message-image" onclick="showImageModal('${match}')" alt="Screenshot"><span class="image-label">Click to enlarge</span></div>`;
    });
    html = html.replace(/\[([^\]\n]+)\]\((https?:\/\/[^\s)]+)\)/g, (_, label, url) => {
        const safeUrl = escapeHtml(url);
        return `<a href="${safeUrl}" target="_blank" rel="noopener noreferrer">${label}</a>`;
    });
    html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/__([^_]+)__/g, '<strong>$1</strong>');
    html = html.replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>');
    html = html.replace(/(^|[^_])_([^_\n]+)_/g, '$1<em>$2</em>');
    codeTokens.forEach((replacement, index) => {
        html = html.replaceAll(`\u0000CODE${index}\u0000`, replacement);
    });
    return html;
}

function renderMarkdownTable(lines, startIndex) {
    const header = markdownTableCells(lines[startIndex]);
    const separator = lines[startIndex + 1];
    const aligns = markdownTableAlignments(separator);
    let index = startIndex + 2;
    const rows = [];
    while (index < lines.length && lines[index].includes('|') && lines[index].trim()) {
        if (isMarkdownTableSeparator(lines[index])) break;
        rows.push(markdownTableCells(lines[index]));
        index++;
    }
    const headerHtml = header.map((cell, idx) => {
        const cls = aligns[idx] && aligns[idx] !== 'left' ? ` class="align-${aligns[idx]}"` : '';
        return `<th${cls}>${renderMarkdownInline(cell)}</th>`;
    }).join('');
    const rowsHtml = rows.map(row => `<tr>${header.map((_, idx) => {
        const cls = aligns[idx] && aligns[idx] !== 'left' ? ` class="align-${aligns[idx]}"` : '';
        return `<td${cls}>${renderMarkdownInline(row[idx] || '')}</td>`;
    }).join('')}</tr>`).join('');
    return {
        html: `<div class="markdown-table-wrap"><table><thead><tr>${headerHtml}</tr></thead><tbody>${rowsHtml}</tbody></table></div>`,
        nextIndex: index,
    };
}

function renderMarkdownBlocks(markdownText) {
    const lines = String(markdownText ?? '').replace(/\r\n/g, '\n').split('\n');
    const blocks = [];
    let i = 0;

    const paragraphLines = [];
    const flushParagraph = () => {
        if (!paragraphLines.length) return;
        blocks.push(`<p>${paragraphLines.map(renderMarkdownInline).join('<br>')}</p>`);
        paragraphLines.length = 0;
    };

    while (i < lines.length) {
        const line = lines[i];
        const trimmed = line.trim();

        if (!trimmed) {
            flushParagraph();
            i++;
            continue;
        }

        if (/^\s*[-*_]{3,}\s*$/.test(trimmed)) {
            flushParagraph();
            blocks.push('<hr>');
            i++;
            continue;
        }

        const heading = trimmed.match(/^(#{1,6})\s+(.+)$/);
        if (heading) {
            flushParagraph();
            const level = heading[1].length;
            blocks.push(`<h${level}>${renderMarkdownInline(heading[2])}</h${level}>`);
            i++;
            continue;
        }

        if (i + 1 < lines.length && line.includes('|') && isMarkdownTableSeparator(lines[i + 1])) {
            flushParagraph();
            const rendered = renderMarkdownTable(lines, i);
            blocks.push(rendered.html);
            i = rendered.nextIndex;
            continue;
        }

        if (/^>\s?/.test(trimmed)) {
            flushParagraph();
            const quoteLines = [];
            while (i < lines.length && /^>\s?/.test(lines[i].trim())) {
                quoteLines.push(lines[i].trim().replace(/^>\s?/, ''));
                i++;
            }
            blocks.push(`<blockquote>${quoteLines.map(renderMarkdownInline).join('<br>')}</blockquote>`);
            continue;
        }

        if (/^[-*+]\s+/.test(trimmed)) {
            flushParagraph();
            const items = [];
            while (i < lines.length && /^[-*+]\s+/.test(lines[i].trim())) {
                items.push(lines[i].trim().replace(/^[-*+]\s+/, ''));
                i++;
            }
            blocks.push(`<ul>${items.map(item => `<li>${renderMarkdownInline(item)}</li>`).join('')}</ul>`);
            continue;
        }

        if (/^\d+[.)]\s+/.test(trimmed)) {
            flushParagraph();
            const items = [];
            while (i < lines.length && /^\d+[.)]\s+/.test(lines[i].trim())) {
                items.push(lines[i].trim().replace(/^\d+[.)]\s+/, ''));
                i++;
            }
            blocks.push(`<ol>${items.map(item => `<li>${renderMarkdownInline(item)}</li>`).join('')}</ol>`);
            continue;
        }

        paragraphLines.push(line);
        i++;
    }
    flushParagraph();
    return blocks.join('');
}

function formatMessageContent(text) {
    const raw = typeof text === 'string' ? text : String(text ?? '');
    const fenceRegex = /```([^\n`]*)\n([\s\S]*?)```/g;
    const parts = [];
    let cursor = 0;
    let match;
    while ((match = fenceRegex.exec(raw)) !== null) {
        if (match.index > cursor) {
            parts.push(renderMarkdownBlocks(raw.slice(cursor, match.index)));
        }
        const language = String(match[1] || '').trim().replace(/[^A-Za-z0-9_-]/g, '');
        const languageClass = language ? ` class="language-${escapeHtml(language)}"` : '';
        parts.push(`<pre><code${languageClass}>${escapeHtml(match[2] || '')}</code></pre>`);
        cursor = fenceRegex.lastIndex;
    }
    if (cursor < raw.length) {
        parts.push(renderMarkdownBlocks(raw.slice(cursor)));
    }
    return `<div class="markdown-body">${parts.join('')}</div>`;
}

function formatSessionTranscriptContent(text) {
    const raw = typeof text === 'string' ? text : '';
    if (raw.length < 5000 && raw.split('\n').length < 120) {
        return formatMessageContent(raw);
    }
    const preview = summarizeValue(raw.replace(/\s+/g, ' ').trim(), 420);
    return `
        <div class="long-message-shell">
            <div>${formatMessageContent(preview)}</div>
            <details>
                <summary>Show full message</summary>
                <div style="margin-top:0.5rem;">${formatMessageContent(raw)}</div>
            </details>
        </div>
    `;
}

// Parse base64 images from content
function parseImagesFromContent(content) {
    const imageRegex = /data:image\/(png|jpeg|jpg|gif|webp);base64,([A-Za-z0-9+/=]+)/g;
    const images = [];
    let match;

    while ((match = imageRegex.exec(content)) !== null) {
        images.push({
            full: match[0],
            type: match[1],
            data: match[2]
        });
    }

    return images;
}

function updateContextDisplay(assistantMessage) {
    const usage = assistantMessage.usage || {};
    const lastPromptTokens = assistantMessage.last_prompt_tokens || usage.prompt_tokens || 0;
    const cachedInfo = sessionContextCache.info;
    if (!contextPanel || !contextSummary || activeChatRoomId === 'shared' || !cachedInfo?.max) {
        if (contextPanel) contextPanel.hidden = true;
        if (contextSummary) contextSummary.innerHTML = '';
        return;
    }
    const used = lastPromptTokens || cachedInfo.used;
    const percent = lastPromptTokens ? (lastPromptTokens / cachedInfo.max) * 100 : cachedInfo.percent;
    const info = { used, max: cachedInfo.max, percent, stale: cachedInfo.stale };
    contextPanel.hidden = false;
    contextSummary.innerHTML = renderContextGaugeHtml(percent, contextGaugeTooltip(info), 'chat');
}

function isSafeImageDataUrl(url) {
    return typeof url === 'string' && /^data:image\/(png|jpe?g|gif|webp|bmp);base64,/i.test(url);
}

function renderPendingImageAttachments() {
    if (!chatAttachmentPreviewBar) return;
    chatAttachmentPreviewBar.innerHTML = pendingImageAttachments.map(att => `
        <div class="chat-attachment-preview">
            <img src="${escapeHtml(att.dataUrl)}" alt="Pasted image preview">
            <button type="button" class="chat-attachment-remove" onclick="removePendingImageAttachment('${att.id}')" aria-label="Remove pasted image">×</button>
        </div>
    `).join('');
    chatAttachmentPreviewBar.classList.toggle('has-attachments', pendingImageAttachments.length > 0);
}

function removePendingImageAttachment(id) {
    pendingImageAttachments = pendingImageAttachments.filter(att => att.id !== id);
    renderPendingImageAttachments();
}

function clearPendingImageAttachments() {
    pendingImageAttachmentGeneration += 1;
    pendingImageAttachments = [];
    renderPendingImageAttachments();
}

function readImageFile(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result || ''));
        reader.onerror = () => reject(reader.error || new Error('Failed to read image'));
        reader.readAsDataURL(file);
    });
}

async function attachImageFiles(files, sourceLabel = 'selected') {
    const imageFiles = Array.from(files || []).filter(file => /^image\//i.test(file.type || ''));
    if (!imageFiles.length) return;
    const generation = pendingImageAttachmentGeneration;
    try {
        const dataUrls = await Promise.all(imageFiles.map(readImageFile));
        if (generation !== pendingImageAttachmentGeneration) return;
        const validUrls = dataUrls.filter(isSafeImageDataUrl);
        if (!validUrls.length) {
            showToast(`${sourceLabel} image format is not supported`, true);
            return;
        }
        pendingImageAttachments.push(...validUrls.map(dataUrl => ({
            id: `img_${Date.now()}_${pendingImageAttachmentSeq++}`,
            dataUrl,
        })));
        renderPendingImageAttachments();
        log('inf', `Attached ${validUrls.length} ${sourceLabel} image${validUrls.length === 1 ? '' : 's'}`);
    } catch (error) {
        showToast(`Failed to attach ${sourceLabel} image: ` + error.message, true);
        log('err', `Failed to attach ${sourceLabel} image: ` + error.message, true);
    }
}

async function handleUserInputPaste(event) {
    const items = Array.from(event.clipboardData?.items || []);
    const imageFiles = items
        .filter(item => item.kind === 'file' && /^image\//i.test(item.type || ''))
        .map(item => item.getAsFile())
        .filter(Boolean);
    if (!imageFiles.length) return;
    event.preventDefault();
    await attachImageFiles(imageFiles, 'pasted');
}

async function handleChatImageInputChange(event) {
    await attachImageFiles(event.target?.files || [], 'selected');
    if (event.target) event.target.value = '';
}

function syncChatInputState() {
    if (!sendBtn) return;
    sendBtn.disabled = Boolean(getActiveRun() || streamResumeRooms.has(activeChatRoomId) || sharedRoomRequestInFlight || chatResetInFlight);
}

async function consumeSharedRoomNdjson(response, onEvent) {
    if (!response.body?.getReader) throw Object.assign(new Error('Streaming response is unavailable'), { streamUnavailable: true });
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    const consumeLine = (line) => {
        const text = line.trim();
        if (!text) return;
        let event;
        try {
            event = JSON.parse(text);
        } catch (_error) {
            throw new Error('Shared room returned invalid streaming data');
        }
        onEvent(event);
    };
    while (true) {
        const { done, value } = await reader.read();
        buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        lines.forEach(consumeLine);
        if (done) break;
    }
    if (buffer.trim()) consumeLine(buffer);
}

async function sendSharedRoomMessageFallback(message) {
    const data = await fetchJsonOrThrow('/api/bot-rooms/shared/messages', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message }),
    });
    if (data?.ok === false) throw new Error(data.error || 'Shared room request failed');
    return data;
}

async function sendSharedRoomMessage(message) {
    if (sharedRoomRequestInFlight) return;
    sharedRoomRequestInFlight = true;
    userInput.value = '';
    userInput.style.height = 'auto';
    syncChatInputState();
    conversation.push({ role: 'user', content: message });
    renderSharedConversation();
    const indicator = document.createElement('div');
    indicator.className = 'message assistant shared-working-indicator';
    indicator.innerHTML = '<span></span><span></span><span></span><strong>Profiles are conferring</strong>';
    chat.appendChild(indicator);
    scrollChatToBottom(true);
    try {
        let completeEvent = null;
        try {
            const response = await fetch('/api/bot-rooms/shared/messages/stream', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Accept': 'application/x-ndjson' },
                body: JSON.stringify({ message }),
            });
            if ([404, 405, 501].includes(response.status)) {
                throw Object.assign(new Error('Shared room streaming endpoint is unavailable'), { streamUnavailable: true });
            }
            if (!response.ok) {
                const error = await response.json().catch(() => ({}));
                throw new Error(error.error || `Shared room stream failed (HTTP ${response.status})`);
            }
            await consumeSharedRoomNdjson(response, (event) => {
                if (event?.type === 'message' && event.message) {
                    const streamedMessage = { ...event.message, role: 'assistant', bot: event.message.bot || event.message.profile };
                    conversation.push(streamedMessage);
                    indicator.insertAdjacentHTML('beforebegin', sharedMessageHtml(streamedMessage));
                    bindAvatarFallbacks(chat);
                    scrollChatToBottom(true);
                } else if (event?.type === 'complete') {
                    completeEvent = event;
                } else if (event?.type === 'error') {
                    throw new Error(event.error || event.message || 'Shared room stream failed');
                }
            });
            if (!completeEvent) throw new Error('Shared room stream ended before completion');
        } catch (error) {
            if (!error.streamUnavailable) throw error;
            completeEvent = await sendSharedRoomMessageFallback(message);
        }
        const room = completeEvent?.room;
        if (Array.isArray(room?.conversation)) conversation = room.conversation;
        activeChatSessionId = room?.session_id || null;
        indicator.remove();
        renderSharedConversation();
        if (Array.isArray(completeEvent?.errors) && completeEvent.errors.length) {
            const details = completeEvent.errors
                .map(item => `@${item.bot || 'bot'}: ${item.error || 'response failed'}`)
                .join(' | ');
            showToast(details, true);
        }
    } catch (error) {
        indicator.remove();
        showToast(`Shared room failed: ${error.message || error}`, true);
    } finally {
        sharedRoomRequestInFlight = false;
        syncChatInputState();
        userInput.focus();
    }
}

async function sendMessage() {
    const message = userInput.value.trim();
    const imageAttachments = pendingImageAttachments.slice();
    if (!message && !imageAttachments.length) return;
    if (!imageAttachments.length && /^\/(?:new|mew)$/i.test(message)) {
        if (await resetCurrentChatRoom({ freshSession: true })) {
            userInput.value = '';
            userInput.style.height = 'auto';
        }
        return;
    }
    if (getActiveRun() || streamResumeRooms.has(activeChatRoomId) || sharedRoomRequestInFlight || chatResetInFlight) return;
    if (activeChatRoomId === 'shared') {
        if (imageAttachments.length) {
            showToast('The shared room accepts text prompts only', true);
            return;
        }
        await sendSharedRoomMessage(message);
        return;
    }
    const userContent = imageAttachments.length
        ? [
            ...(message ? [{ type: 'text', text: message }] : []),
            ...imageAttachments.map(att => ({ type: 'image_url', image_url: { url: att.dataUrl } })),
        ]
        : message;

    userInput.value = '';
    userInput.style.height = 'auto';
    clearPendingImageAttachments();
    const roomId = activeChatRoomId;
    const roomConversation = conversation;

    addMessage('user', { content: userContent });
    conversation.push({ role: 'user', content: userContent });
    saveConversation();

    log('req', `POST /chat (streaming)`);
    const logMessage = message || `[${imageAttachments.length} pasted image${imageAttachments.length === 1 ? '' : 's'}]`;
    log('inf', `User: ${logMessage.substring(0, 100)}${logMessage.length > 100 ? '...' : ''}`);
    const runState = {
        runId: `run_${Date.now()}_${Math.random().toString(16).slice(2)}`,
        eventOffset: 0,
        startedAt: Date.now(),
        sessionId: activeChatSessionId,
        approvalSessionId: null,
        roomId,
        profile: profileForRoom(roomId),
        assistantState: null,
    };
    activeRuns[roomId] = runState;
    saveActiveRuns();
    updateActiveRunBanner();
    renderChatRoomRail();
    syncChatInputState();

    try {
        await streamChatRun({
            runId: runState.runId,
            messagesPayload: roomConversation,
            resume: false,
            eventOffset: 0,
            sessionId: runState.sessionId,
            roomId,
            profile: runState.profile,
        });

    } catch (error) {
        log('err', `Error: ${error.message}`, true);
        sendDashboardNotification('errors', 'Hermes run needs attention', error.message || 'The chat run failed.', {
            key: `run:${runState.runId}:transport-error`,
            tag: `hermes-run-${runState.runId}`,
            panel: 'chat',
        });
        const errorMessage = { role: 'assistant', bot: runState.profile || 'default', content: `Error: ${error.message}` };
        roomConversation.push(errorMessage);
        if (roomId === 'main') {
            await saveDashboardState('conversation', roomConversation, { immediate: true });
        } else {
            await saveBotRoom(roomId, roomConversation, runState.sessionId);
        }
        if (roomId === activeChatRoomId) {
            if (conversation !== roomConversation) conversation.push(errorMessage);
            renderConversation();
        }
        clearActiveRun(roomId, runState.runId);
    }

    syncChatInputState();
    if (roomId === activeChatRoomId) userInput.focus();
}

async function resetCurrentChatRoom(options = {}) {
    const roomId = activeChatRoomId;
    if (chatResetInFlight) return false;
    if (options.freshSession && roomId === 'shared') {
        showToast('Start a direct bot chat to create a fresh bot session', true);
        return false;
    }
    if (getActiveRun(roomId) || streamResumeRooms.has(roomId) || sharedRoomRequestInFlight) {
        showToast('Stop or finish the active run before starting a new session', true);
        return false;
    }

    chatResetInFlight = true;
    syncChatInputState();
    const previousIntentEpoch = chatRoomIntentEpochs.get(roomId) || 0;
    let resetPersisted = false;
    chatRoomIntentEpochs.set(roomId, previousIntentEpoch + 1);
    try {
        const persisted = roomId === 'main'
            ? await saveDashboardState('conversation', null, { immediate: true })
            : await saveBotRoom(roomId, [], null);
        if (!persisted) {
            chatRoomIntentEpochs.set(roomId, previousIntentEpoch);
            showToast('Could not persist the new session reset', true);
            return false;
        }
        resetPersisted = true;

        conversation = [];
        clearPendingImageAttachments();
        activeChatSessionId = null;
        chat.innerHTML = '';
        userInput.value = '';
        userInput.style.height = 'auto';
        if (roomId === 'main') {
            removeLegacyLocalStorageValue(STORAGE_KEY);
            saveMainChatSession(null);
        }
        refreshTokenUsageSoon();
        await refreshSessionContextInfo(null);
        updateContextDisplay({ usage: null, last_prompt_tokens: 0 });
        updateActiveChatBanner();
        updateActiveRunBanner();
        userInput?.focus();
        showToast(roomId === 'shared' ? 'Shared room cleared; bot sessions retained' : 'New session ready');
        log('inf', `Chat room ${roomId} reset for a new session`);
        return true;
    } catch (error) {
        if (!resetPersisted) chatRoomIntentEpochs.set(roomId, previousIntentEpoch);
        throw error;
    } finally {
        chatResetInFlight = false;
        syncChatInputState();
    }
}

async function clearChat() {
    return resetCurrentChatRoom();
}

function debounce(fn, ms) {
    let timeout;
    return (...args) => {
        clearTimeout(timeout);
        timeout = setTimeout(() => fn(...args), ms);
    };
}

// Event listeners
sendBtn.addEventListener('click', sendMessage);
if (chatImageBtn && chatImageInput) {
    chatImageBtn.addEventListener('click', () => chatImageInput.click());
    chatImageInput.addEventListener('change', handleChatImageInputChange);
}
userInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});
userInput.addEventListener('paste', handleUserInputPaste);
userInput.addEventListener('input', () => {
    userInput.style.height = 'auto';
    userInput.style.height = Math.min(userInput.scrollHeight, 150) + 'px';
});

let diagnosticsContextCache = null;

async function loadDiagnosticsContext() {
    const output = document.getElementById('diagnostics-context');
    const target = document.getElementById('diagnostics-target')?.value || 'pokemon';
    if (output) output.textContent = 'Gathering live context...';
    try {
        const response = await fetch('/api/diagnostics/context?target=' + encodeURIComponent(target));
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || data.detail || 'HTTP ' + response.status);
        diagnosticsContextCache = data;
        if (output) output.textContent = JSON.stringify(data, null, 2);
        return data;
    } catch (error) {
        if (output) output.textContent = 'Failed to gather context: ' + error.message;
        throw error;
    }
}

function fillDiagnosticsPrompt(kind) {
    const input = document.getElementById('diagnostics-input');
    if (!input) return;
    const prompts = {
        stuck: 'The Pokemon autoplayer appears stuck or not making progress. Diagnose the likely blocker from the live context, cite the exact status/readiness fields that matter, and give the safest next action. Do not edit files or restart services unless I explicitly approve a specific plan.',
        dashboard: 'Something in the dashboard, WebRTC/watch page, WebSocket proxy, or ROM onboarding may be broken. Diagnose it from the live context and propose a minimal verification checklist before any fix.',
        fix: 'Propose a safe fix plan for the current issue. Include files likely touched, commands to verify, risk level, and the approval you need before making changes. Do not perform the fix yet.'
    };
    input.value = prompts[kind] || prompts.stuck;
    input.focus();
}

async function sendDiagnosticsMessage() {
    const input = document.getElementById('diagnostics-input');
    const output = document.getElementById('diagnostics-output');
    const button = document.getElementById('diagnostics-send');
    const question = (input?.value || '').trim();
    if (!question) return;
    if (button) button.disabled = true;
    if (output) output.textContent = 'Gathering context and starting Diagnostics Agent...\n\n';
    try {
        const context = diagnosticsContextCache || await loadDiagnosticsContext();
        const system = 'You are the Hermes Dashboard Diagnostics Agent. You may diagnose live dashboard and Pokemon-agent problems from provided context. Default to observe/propose mode. Do not claim you changed files, ran commands, restarted services, or approved a fix unless the user explicitly asks and the tool system actually does it. If a fix is needed, return a concise plan with risk, files, commands, and approval request. Prefer using subagents/delegation for nontrivial investigation when available.';
        const messages = [
            { role: 'system', content: system },
            { role: 'user', content: question + '\n\nLive diagnostics context:\n```json\n' + JSON.stringify(context, null, 2).slice(0, 26000) + '\n```' }
        ];
        const response = await fetch('/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                run_id: 'diag_' + Date.now() + '_' + Math.random().toString(16).slice(2),
                messages: messages,
            }),
        });
        if (!response.ok || !response.body) throw new Error('HTTP ' + response.status);
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let content = '';
        while (true) {
            const chunk = await reader.read();
            buffer += decoder.decode(chunk.value || new Uint8Array(), { stream: !chunk.done });
            const events = buffer.split(/\r?\n\r?\n/);
            if (!chunk.done) buffer = events.pop() || '';
            else buffer = '';
            for (const rawEvent of events) {
                const line = rawEvent.split(/\r?\n/).find(part => part.startsWith('data: '));
                if (!line) continue;
                const data = line.slice(6);
                if (data === '[DONE]') break;
                try {
                    const parsed = JSON.parse(data);
                    if (parsed.type === 'content' && parsed.content) {
                        content += parsed.content;
                        if (output) output.textContent = content;
                    } else if (parsed.type === 'tool_progress') {
                        const label = parsed.name || parsed.tool || 'tool';
                        if (output) output.textContent = content + '\n\n[tool] ' + label;
                    }
                } catch (_) {}
            }
            if (chunk.done) break;
        }
        if (output && !content) output.textContent = 'Diagnostics Agent completed without text output.';
    } catch (error) {
        if (output) output.textContent += 'Error: ' + error.message;
    } finally {
        if (button) button.disabled = false;
    }
}

window.loadDiagnosticsContext = loadDiagnosticsContext;
window.fillDiagnosticsPrompt = fillDiagnosticsPrompt;
window.sendDiagnosticsMessage = sendDiagnosticsMessage;

// GRAPH_RUNTIME_START

// ── Global State (owned by this block) ──
let graphSim = null;
let graphData = null;
let graphLoaded = false;
const floatingPanels = new Map();
let floatingZCounter = 200;
const GRAPH_SETTINGS_STORAGE_KEY = 'hermes-dashboard-graph-settings-v1';
const GRAPH_EDGE_TYPES = ['accessed', 'used_tool', 'used_model', 'delegated', 'relates_to', 'used_skill'];
const GRAPH_FONT_FAMILIES = {
  system: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
  sans: 'Inter, "Segoe UI", Roboto, sans-serif',
  mono: '"JetBrains Mono", "Fira Code", monospace',
  serif: 'Iowan Old Style, Georgia, serif',
};
const DEFAULT_GRAPH_SETTINGS = {
  labelDensity: 'auto',
  labelFontSize: 9,
  fontFamily: 'system',
  labelMaxLength: 25,
  nodeScale: 1,
  spacing: 1,
  showEdges: true,
  edgeOpacity: 0.3,
  edgeStyle: 'mixed',
  edgeTypes: {
    accessed: true,
    used_tool: true,
    used_model: true,
    delegated: true,
    relates_to: true,
    used_skill: true,
  },
  motionMode: 'system',
  sidebarWidth: 340,
  floatingPanelWidth: 500,
};
let graphSettings = loadGraphSettings();

function clampGraphSetting(value, min, max, fallback) {
  const num = Number(value);
  if (!Number.isFinite(num)) return fallback;
  return Math.min(max, Math.max(min, num));
}

function normalizeGraphSettings(raw) {
  const edgeTypes = { ...DEFAULT_GRAPH_SETTINGS.edgeTypes };
  const incomingEdgeTypes = raw && typeof raw.edgeTypes === 'object' ? raw.edgeTypes : {};
  GRAPH_EDGE_TYPES.forEach(type => {
    if (type in incomingEdgeTypes) edgeTypes[type] = !!incomingEdgeTypes[type];
  });
  return {
    labelDensity: ['auto', 'sparse', 'normal', 'dense'].includes(raw?.labelDensity) ? raw.labelDensity : DEFAULT_GRAPH_SETTINGS.labelDensity,
    labelFontSize: clampGraphSetting(raw?.labelFontSize, 7, 18, DEFAULT_GRAPH_SETTINGS.labelFontSize),
    fontFamily: Object.prototype.hasOwnProperty.call(GRAPH_FONT_FAMILIES, raw?.fontFamily) ? raw.fontFamily : DEFAULT_GRAPH_SETTINGS.fontFamily,
    labelMaxLength: clampGraphSetting(raw?.labelMaxLength, 12, 64, DEFAULT_GRAPH_SETTINGS.labelMaxLength),
    nodeScale: clampGraphSetting(raw?.nodeScale, 0.7, 1.8, DEFAULT_GRAPH_SETTINGS.nodeScale),
    spacing: clampGraphSetting(raw?.spacing, 0.7, 1.8, DEFAULT_GRAPH_SETTINGS.spacing),
    showEdges: raw?.showEdges !== undefined ? !!raw.showEdges : DEFAULT_GRAPH_SETTINGS.showEdges,
    edgeOpacity: clampGraphSetting(raw?.edgeOpacity, 0.05, 1, DEFAULT_GRAPH_SETTINGS.edgeOpacity),
    edgeStyle: ['mixed', 'solid', 'dashed'].includes(raw?.edgeStyle) ? raw.edgeStyle : DEFAULT_GRAPH_SETTINGS.edgeStyle,
    edgeTypes,
    motionMode: ['system', 'reduced', 'full'].includes(raw?.motionMode) ? raw.motionMode : DEFAULT_GRAPH_SETTINGS.motionMode,
    sidebarWidth: clampGraphSetting(raw?.sidebarWidth, 280, 520, DEFAULT_GRAPH_SETTINGS.sidebarWidth),
    floatingPanelWidth: clampGraphSetting(raw?.floatingPanelWidth, 360, 760, DEFAULT_GRAPH_SETTINGS.floatingPanelWidth),
  };
}

function loadGraphSettings() {
  try {
    const raw = JSON.parse(localStorage.getItem(GRAPH_SETTINGS_STORAGE_KEY) || '{}');
    return normalizeGraphSettings(raw);
  } catch {
    return normalizeGraphSettings({});
  }
}

function saveGraphSettings() {
  localStorage.setItem(GRAPH_SETTINGS_STORAGE_KEY, JSON.stringify(graphSettings));
}

function resolvedGraphMotionMode() {
  if (graphSettings.motionMode === 'full') return 'full';
  if (graphSettings.motionMode === 'reduced') return 'reduced';
  return window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'reduced' : 'full';
}

function graphFontFamily() {
  return GRAPH_FONT_FAMILIES[graphSettings.fontFamily] || GRAPH_FONT_FAMILIES.system;
}

function getFloatingPanelWidth(minimum = 320) {
  return Math.max(minimum, Math.round(graphSettings.floatingPanelWidth || DEFAULT_GRAPH_SETTINGS.floatingPanelWidth));
}

function setFloatingPanelWidth(panel, minimum = 320) {
  panel.dataset.minWidth = String(minimum);
  panel.style.width = `${getFloatingPanelWidth(minimum)}px`;
}

function refreshFloatingPanelWidths() {
  document.querySelectorAll('#graph-container .floating-panel').forEach(panel => {
    setFloatingPanelWidth(panel, Number(panel.dataset.minWidth || 320));
  });
}

function applyGraphPanelCssVars() {
  const graphPanel = document.getElementById('graph-panel');
  if (!graphPanel) return;
  const sidebarWidth = Math.round(graphSettings.sidebarWidth);
  const floatingWidth = Math.round(graphSettings.floatingPanelWidth);
  graphPanel.style.setProperty('--graph-sidebar-width', `${sidebarWidth}px`);
  graphPanel.style.setProperty('--graph-sidebar-offset', `${sidebarWidth + 20}px`);
  graphPanel.style.setProperty('--graph-floating-panel-width', `${floatingWidth}px`);
  refreshFloatingPanelWidths();
}

function updateGraphSettingsValueLabels() {
  document.querySelectorAll('[data-setting-value="labelFontSize"]').forEach(el => { el.textContent = `${Math.round(graphSettings.labelFontSize)}px`; });
  document.querySelectorAll('[data-setting-value="labelMaxLength"]').forEach(el => { el.textContent = `${Math.round(graphSettings.labelMaxLength)} chars`; });
  document.querySelectorAll('[data-setting-value="nodeScale"]').forEach(el => { el.textContent = `${graphSettings.nodeScale.toFixed(2)}x`; });
  document.querySelectorAll('[data-setting-value="spacing"]').forEach(el => { el.textContent = `${graphSettings.spacing.toFixed(2)}x`; });
  document.querySelectorAll('[data-setting-value="edgeOpacity"]').forEach(el => { el.textContent = `${Math.round(graphSettings.edgeOpacity * 100)}%`; });
  document.querySelectorAll('[data-setting-value="sidebarWidth"]').forEach(el => { el.textContent = `${Math.round(graphSettings.sidebarWidth)}px`; });
  document.querySelectorAll('[data-setting-value="floatingPanelWidth"]').forEach(el => { el.textContent = `${Math.round(graphSettings.floatingPanelWidth)}px`; });
}

function syncGraphSettingsControls() {
  const values = {
    'graph-setting-label-density': graphSettings.labelDensity,
    'graph-setting-label-font-size': String(graphSettings.labelFontSize),
    'graph-setting-font-family': graphSettings.fontFamily,
    'graph-setting-label-max-length': String(graphSettings.labelMaxLength),
    'graph-setting-node-scale': String(graphSettings.nodeScale),
    'graph-setting-spacing': String(graphSettings.spacing),
    'graph-setting-edge-opacity': String(graphSettings.edgeOpacity),
    'graph-setting-edge-style': graphSettings.edgeStyle,
    'graph-setting-motion-mode': graphSettings.motionMode,
    'graph-setting-sidebar-width': String(graphSettings.sidebarWidth),
    'graph-setting-floating-panel-width': String(graphSettings.floatingPanelWidth),
  };
  Object.entries(values).forEach(([id, value]) => {
    const el = document.getElementById(id);
    if (el) el.value = value;
  });
  const showEdges = document.getElementById('graph-setting-show-edges');
  if (showEdges) showEdges.checked = !!graphSettings.showEdges;
  GRAPH_EDGE_TYPES.forEach(type => {
    const el = document.getElementById(`graph-setting-edge-${type}`);
    if (el) el.checked = graphSettings.edgeTypes[type] !== false;
  });
  updateGraphSettingsValueLabels();
}

function applyGraphSettingsToUi() {
  applyGraphPanelCssVars();
  syncGraphSettingsControls();
  const toggle = document.getElementById('graph-settings-toggle');
  const drawer = document.getElementById('graph-settings-drawer');
  if (toggle && drawer) toggle.classList.toggle('active', drawer.classList.contains('open'));
}

function toggleGraphSettingsDrawer(forceOpen) {
  const drawer = document.getElementById('graph-settings-drawer');
  if (!drawer) return;
  const nextOpen = typeof forceOpen === 'boolean' ? forceOpen : !drawer.classList.contains('open');
  drawer.classList.toggle('open', nextOpen);
  applyGraphSettingsToUi();
}

function persistGraphSettings(changedKey, options = {}) {
  saveGraphSettings();
  applyGraphSettingsToUi();
  if (!graphLoaded) return;
  if (options.reload || typeof window._graphOnSettingsChanged !== 'function') {
    loadGraph();
    return;
  }
  window._graphOnSettingsChanged(changedKey);
}

function initGraphSettingsControls() {
  const toggle = document.getElementById('graph-settings-toggle');
  const close = document.getElementById('graph-settings-close');
  const reset = document.getElementById('graph-settings-reset');
  const drawer = document.getElementById('graph-settings-drawer');
  if (toggle && !toggle.dataset.bound) {
    toggle.dataset.bound = 'true';
    toggle.addEventListener('click', () => toggleGraphSettingsDrawer());
  }
  if (close && !close.dataset.bound) {
    close.dataset.bound = 'true';
    close.addEventListener('click', () => toggleGraphSettingsDrawer(false));
  }
  if (reset && !reset.dataset.bound) {
    reset.dataset.bound = 'true';
    reset.addEventListener('click', () => {
      graphSettings = normalizeGraphSettings({});
      persistGraphSettings('reset', { reload: true });
    });
  }
  if (drawer && !drawer.dataset.bound) {
    drawer.dataset.bound = 'true';
    drawer.addEventListener('click', (e) => e.stopPropagation());
  }
  if (!document.body.dataset.graphSettingsOutsideBound) {
    document.body.dataset.graphSettingsOutsideBound = 'true';
    document.addEventListener('click', (e) => {
      const panel = document.getElementById('graph-panel');
      const currentDrawer = document.getElementById('graph-settings-drawer');
      const currentToggle = document.getElementById('graph-settings-toggle');
      if (!panel || !currentDrawer || !currentDrawer.classList.contains('open')) return;
      if (currentDrawer.contains(e.target) || currentToggle?.contains(e.target)) return;
      if (!panel.contains(e.target)) return;
      toggleGraphSettingsDrawer(false);
    });
  }

  // Delegated event listener for Live view buttons (avoids inline onclick escaping issues)
  if (!document.body.dataset.liveViewDelegated) {
    document.body.dataset.liveViewDelegated = 'true';
    document.addEventListener('click', (e) => {
      const flightToggle = e.target.closest('.subagent-flight-toggle');
      if (flightToggle) { e.preventDefault(); e.stopPropagation(); toggleSubagentFlightPopover(flightToggle); return; }
      const flightClose = e.target.closest('.subagent-flight-close');
      if (flightClose) { e.preventDefault(); e.stopPropagation(); closeSubagentFlightPopover(); return; }
      const stopBtn = e.target.closest('.subagent-stop-btn');
      if (stopBtn) { e.preventDefault(); e.stopPropagation(); requestStopSubagent(stopBtn.dataset.childSessionId || ''); return; }
      const pauseBtn = e.target.closest('.subagent-pause-btn');
      if (pauseBtn) { e.preventDefault(); e.stopPropagation(); togglePauseSubagentStream(pauseBtn.dataset.childSessionId || '', pauseBtn.dataset.controlMode || 'soft'); return; }
      const steerBtn = e.target.closest('.subagent-steer-btn');
      if (steerBtn) { e.preventDefault(); e.stopPropagation(); requestSteerSubagent(steerBtn.dataset.childSessionId || '', steerBtn.dataset.controlMode || 'soft'); return; }
      const btn = e.target.closest('.live-view-btn');
      if (!btn) {
        const flightPopover = document.getElementById('subagent-flight-popover');
        if (flightPopover && !flightPopover.hidden && !flightPopover.contains(e.target)) closeSubagentFlightPopover();
        return;
      }
      e.preventDefault();
      e.stopPropagation();
      const childSessionId = btn.dataset.childSessionId;
      const label = btn.dataset.label || '';
      let anchorEl = btn;
      if (btn.dataset.anchorSelector) anchorEl = document.querySelector(btn.dataset.anchorSelector) || btn;
      else if (btn.dataset.toolKey) anchorEl = document.querySelector(`[data-tool-id="${CSS.escape(btn.dataset.toolKey)}"]`) || btn;
      else if (btn.dataset.useParent) anchorEl = btn.closest('details') || btn;
      closeSubagentFlightPopover();
      openChildSessionDrawer(childSessionId, anchorEl, label);
    });
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && !document.getElementById('subagent-flight-popover')?.hidden) {
        e.preventDefault();
        closeSubagentFlightPopover();
        document.querySelector('.subagent-flight-toggle')?.focus();
        return;
      }
      const btn = e.target.closest?.('.live-view-btn[role="button"]');
      if (!btn || (e.key !== 'Enter' && e.key !== ' ')) return;
      e.preventDefault();
      btn.click();
    });
  }

  const layoutKeys = new Set(['nodeScale', 'spacing', 'motionMode']);
  const bindValueControl = (id, key, parser = (value) => value) => {
    const el = document.getElementById(id);
    if (!el || el.dataset.bound) return;
    el.dataset.bound = 'true';
    const eventName = el.tagName === 'SELECT' ? 'change' : 'input';
    el.addEventListener(eventName, () => {
      graphSettings = normalizeGraphSettings({ ...graphSettings, [key]: parser(el.value) });
      persistGraphSettings(key, { reload: layoutKeys.has(key) });
    });
  };

  bindValueControl('graph-setting-label-density', 'labelDensity');
  bindValueControl('graph-setting-label-font-size', 'labelFontSize', Number);
  bindValueControl('graph-setting-font-family', 'fontFamily');
  bindValueControl('graph-setting-label-max-length', 'labelMaxLength', Number);
  bindValueControl('graph-setting-node-scale', 'nodeScale', Number);
  bindValueControl('graph-setting-spacing', 'spacing', Number);
  bindValueControl('graph-setting-edge-opacity', 'edgeOpacity', Number);
  bindValueControl('graph-setting-edge-style', 'edgeStyle');
  bindValueControl('graph-setting-motion-mode', 'motionMode');
  bindValueControl('graph-setting-sidebar-width', 'sidebarWidth', Number);
  bindValueControl('graph-setting-floating-panel-width', 'floatingPanelWidth', Number);

  const showEdges = document.getElementById('graph-setting-show-edges');
  if (showEdges && !showEdges.dataset.bound) {
    showEdges.dataset.bound = 'true';
    showEdges.addEventListener('change', () => {
      graphSettings = normalizeGraphSettings({ ...graphSettings, showEdges: showEdges.checked });
      persistGraphSettings('showEdges', { reload: false });
    });
  }

  GRAPH_EDGE_TYPES.forEach(type => {
    const el = document.getElementById(`graph-setting-edge-${type}`);
    if (!el || el.dataset.bound) return;
    el.dataset.bound = 'true';
    el.addEventListener('change', () => {
      graphSettings = normalizeGraphSettings({
        ...graphSettings,
        edgeTypes: { ...graphSettings.edgeTypes, [type]: el.checked },
      });
      persistGraphSettings(`edgeType:${type}`, { reload: false });
    });
  });

  applyGraphSettingsToUi();
}

// ── Node type helpers ──
function nodeTypeIcon(type) {
  switch (type) {
    case 'session': return '&#128172;';
    case 'file':    return '&#128196;';
    case 'tool':    return '&#128295;';
    case 'model':   return '&#129302;';
    case 'skill':   return '&#11088;';
    default:        return '&#128993;';
  }
}

function nodeTypeColor(type) {
  switch (type) {
    case 'session': return '#a855f7';
    case 'file':    return '#22c55e';
    case 'tool':    return '#f97316';
    case 'model':   return '#06b6d4';
    case 'skill':   return '#ffd700';
    default:        return '#6b7280';
  }
}

// ── Draggable helper ──
function makeDraggable(el, handle) {
  let startX, startY, startLeft, startTop;
  handle.addEventListener('mousedown', (e) => {
    if (e.target.closest('.fp-close')) return;
    e.preventDefault();
    startX = e.clientX;
    startY = e.clientY;
    const rect = el.getBoundingClientRect();
    const parentRect = el.parentElement.getBoundingClientRect();
    startLeft = rect.left - parentRect.left;
    startTop = rect.top - parentRect.top;
    el.style.zIndex = ++floatingZCounter;

    function onMove(ev) {
      el.style.left = (startLeft + ev.clientX - startX) + 'px';
      el.style.top = (startTop + ev.clientY - startY) + 'px';
    }
    function onUp() {
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
    }
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
  });
}

// ── Floating file panel ──
function openFloatingPanel(path) {
  if (floatingPanels.has(path)) {
    const panel = floatingPanels.get(path);
    panel.style.zIndex = ++floatingZCounter;
    return;
  }

  const container = document.getElementById('graph-container');
  const panel = document.createElement('div');
  panel.className = 'floating-panel';
  setFloatingPanelWidth(panel, 420);

  const offset = floatingPanels.size * 30;
  panel.style.left = (200 + offset) + 'px';
  panel.style.top = (80 + offset) + 'px';
  panel.style.zIndex = ++floatingZCounter;

  const name = path.split('/').pop();

  panel.innerHTML = `
    <div class="floating-panel-header">
      <span class="fp-icon">📄</span>
      <span class="fp-title">${escapeHtml(name)}</span>
      <button class="fp-copy-btn" onclick="copyToClipboard(${JSON.stringify(path)})" title="Copy file path">&#x29C9;</button>
      <span class="fp-badge" style="background:rgba(34,197,94,0.15);color:#22c55e">file</span>
      <button class="fp-close" title="Close">&times;</button>
    </div>
    <div class="floating-panel-body">Loading...</div>
    <div class="floating-panel-meta"></div>
  `;

  panel.querySelector('.fp-close').addEventListener('click', () => {
    panel.remove();
    floatingPanels.delete(path);
  });

  makeDraggable(panel, panel.querySelector('.floating-panel-header'));
  panel.addEventListener('mousedown', () => { panel.style.zIndex = ++floatingZCounter; });

  container.appendChild(panel);
  floatingPanels.set(path, panel);

  loadFloatingPanelContent(path, panel);
}

async function loadFloatingPanelContent(path, panel) {
  const body = panel.querySelector('.floating-panel-body');
  const meta = panel.querySelector('.floating-panel-meta');
  await renderUniversalFileViewer(path, body, { metaHost: meta, compact: true });
}

// ── Floating session panel ──
function openFloatingSessionPanel(sessionId) {
  const panelKey = 'session:' + sessionId;
  if (floatingPanels.has(panelKey)) {
    const panel = floatingPanels.get(panelKey);
    panel.style.zIndex = ++floatingZCounter;
    return;
  }

  const container = document.getElementById('graph-container');
  const panel = document.createElement('div');
  panel.className = 'floating-panel';
  setFloatingPanelWidth(panel, 550);
  panel.style.maxHeight = '80vh';

  const offset = floatingPanels.size * 30;
  panel.style.left = (180 + offset) + 'px';
  panel.style.top = (60 + offset) + 'px';
  panel.style.zIndex = ++floatingZCounter;

  panel.innerHTML = `
    <div class="floating-panel-header">
      <span class="fp-icon">💬</span>
      <span class="fp-title">${escapeHtml(sessionId)}</span>
      <button class="fp-copy-btn" onclick="copyToClipboard('${sessionId.replace(/'/g, "\\'")}')" title="Copy session ID">&#x29C9;</button>
      <span class="fp-badge" style="background:rgba(168,85,247,0.15);color:#a855f7">session</span>
      <button class="fp-close" title="Close">&times;</button>
    </div>
    <div class="floating-panel-body" style="padding:0.5rem">Loading...</div>
    <div class="floating-panel-meta"></div>
  `;

  panel.querySelector('.fp-close').addEventListener('click', () => {
    panel.remove();
    floatingPanels.delete(panelKey);
  });

  makeDraggable(panel, panel.querySelector('.floating-panel-header'));
  panel.addEventListener('mousedown', () => { panel.style.zIndex = ++floatingZCounter; });

  container.appendChild(panel);
  floatingPanels.set(panelKey, panel);

  loadFloatingSessionContent(sessionId, panel);
}

function highlightJSON(str) {
  const escaped = escapeHtml(str);
  return escaped
    .replace(/"([^"]+)"(?=\s*:)/g, '<span class="j-key">"$1"</span>')
    .replace(/:\s*"([^"]*?)"/g, ': <span class="j-str">"$1"</span>')
    .replace(/:\s*(\d+\.?\d*)/g, ': <span class="j-num">$1</span>')
    .replace(/:\s*(true|false|null)/g, ': <span class="j-bool">$1</span>');
}

async function loadFloatingSessionContent(sessionId, panel) {
  const body = panel.querySelector('.floating-panel-body');
  const meta = panel.querySelector('.floating-panel-meta');

  try {
    const resp = await fetch('/api/sessions/' + encodeURIComponent(sessionId));
    if (!resp.ok) throw new Error('Failed');
    const data = await resp.json();
    const summaryHtml = data.summary ? `<div class="summary-block"><span class="label">Session Summary</span>${escapeHtml(data.summary)}</div>` : '';

    if (!data.messages || data.messages.length === 0) {
      body.innerHTML = summaryHtml || '<div style="color:var(--text-dim);padding:1rem">No messages in this session</div>';
      return;
    }
    const traceContext = buildSessionTraceContext(data, { domScope: `floating-${String(sessionId).replace(/[^A-Za-z0-9_-]/g, '_')}` });
    const html = renderFloatingSessionTranscript(traceContext);

    body.innerHTML = `${summaryHtml}<div style="max-height:60vh;overflow-y:auto">${html}</div>`;
    if (meta) meta.innerHTML = `<span>Messages: <span class="val">${data.messages.length}</span></span>${data.summary ? `<span>Summary: <span class="val">yes</span></span>` : ''}`;
  } catch {
    body.innerHTML = '<div style="color:var(--text-dim);padding:1rem">Could not load session messages</div>';
  }
}

// ── Floating tool panel ──
function openFloatingToolPanel(node) {
  const panelKey = 'tool:' + node.name;
  if (floatingPanels.has(panelKey)) {
    floatingPanels.get(panelKey).style.zIndex = ++floatingZCounter;
    return;
  }

  const container = document.getElementById('graph-container');
  const panel = document.createElement('div');
  panel.className = 'floating-panel';
  setFloatingPanelWidth(panel, 420);

  const offset = floatingPanels.size * 30;
  panel.style.left = (220 + offset) + 'px';
  panel.style.top = (90 + offset) + 'px';
  panel.style.zIndex = ++floatingZCounter;

  const color = '#f97316';
  panel.innerHTML = `
    <div class="floating-panel-header">
      <span class="fp-icon">\u{1F527}</span>
      <span class="fp-title">${escapeHtml(node.name || node.label || '')}</span>
      <button class="fp-copy-btn" onclick="copyToClipboard('${escapeHtml(node.name || '').replace(/'/g, "\\'")}')" title="Copy tool name">&#x29C9;</button>
      <span class="fp-badge" style="background:rgba(249,115,22,0.15);color:${color}">tool</span>
      <button class="fp-close" title="Close">&times;</button>
    </div>
    <div class="floating-panel-body" style="padding:1rem"></div>
    <div class="floating-panel-meta"></div>
  `;

  panel.querySelector('.fp-close').addEventListener('click', () => {
    panel.remove();
    floatingPanels.delete(panelKey);
  });
  makeDraggable(panel, panel.querySelector('.floating-panel-header'));
  panel.addEventListener('mousedown', () => { panel.style.zIndex = ++floatingZCounter; });

  container.appendChild(panel);
  floatingPanels.set(panelKey, panel);

  // Build tool detail content from graph data
  const body = panel.querySelector('.floating-panel-body');
  const meta = panel.querySelector('.floating-panel-meta');

  let html = '';
  html += `<div style="margin-bottom:0.75rem">`;
  html += `<div style="font-size:0.85rem;font-weight:600;margin-bottom:4px">${escapeHtml(node.name || '')}</div>`;
  if (node.usage_count != null) {
    html += `<div style="font-size:0.78rem;color:var(--text-dim)">Used <span style="color:${color};font-weight:600">${node.usage_count}</span> times across sessions</div>`;
  }
  html += `</div>`;

  // Find sessions that used this tool from graph edges
  if (graphData && graphData.edges && graphData.nodes) {
    const nodeMap = {};
    graphData.nodes.forEach(n => { nodeMap[n.id] = n; });

    const sessions = [];
    graphData.edges.forEach(e => {
      const sid = typeof e.source === 'object' ? e.source.id : e.source;
      const tid = typeof e.target === 'object' ? e.target.id : e.target;
      if (e.type === 'used_tool') {
        if (tid === node.id && nodeMap[sid] && nodeMap[sid].type === 'session') sessions.push(nodeMap[sid]);
        else if (sid === node.id && nodeMap[tid] && nodeMap[tid].type === 'session') sessions.push(nodeMap[tid]);
      }
    });

    if (sessions.length > 0) {
      html += `<div style="font-size:0.75rem;font-weight:600;color:var(--text-dim);margin-bottom:6px;text-transform:uppercase;letter-spacing:0.05em">Sessions using this tool (${sessions.length})</div>`;
      html += `<div style="max-height:300px;overflow-y:auto">`;
      sessions.slice(0, 50).forEach(s => {
        const label = s.label || s.session_id || s.id;
        const model = s.model ? ` · ${s.model}` : '';
        html += `<div class="sidebar-neighbor" onclick="onNeighborClick('${s.id.replace(/'/g, "\\'")}')">
          <span style="font-size:0.9rem;flex-shrink:0">\u{1F4AC}</span>
          <span style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:0.78rem">${escapeHtml(label)}</span>
          <span style="font-size:0.65rem;color:var(--text-dim)">${model}</span>
        </div>`;
      });
      if (sessions.length > 50) html += `<div style="font-size:0.7rem;color:var(--text-dim);padding:4px 8px">...and ${sessions.length - 50} more</div>`;
      html += `</div>`;
    }
  }

  body.innerHTML = html;
  if (meta) meta.innerHTML = `<span>Type: <span class="val">tool</span></span><span>Invocations: <span class="val">${node.usage_count || 0}</span></span>`;
}

// ── Floating model panel ──
function openFloatingModelPanel(node) {
  const panelKey = 'model:' + node.name;
  if (floatingPanels.has(panelKey)) {
    floatingPanels.get(panelKey).style.zIndex = ++floatingZCounter;
    return;
  }

  const container = document.getElementById('graph-container');
  const panel = document.createElement('div');
  panel.className = 'floating-panel';
  setFloatingPanelWidth(panel, 420);

  const offset = floatingPanels.size * 30;
  panel.style.left = (240 + offset) + 'px';
  panel.style.top = (70 + offset) + 'px';
  panel.style.zIndex = ++floatingZCounter;

  const color = '#06b6d4';
  panel.innerHTML = `
    <div class="floating-panel-header">
      <span class="fp-icon">\u{1F916}</span>
      <span class="fp-title">${escapeHtml(node.name || node.label || '')}</span>
      <span class="fp-badge" style="background:rgba(6,182,212,0.15);color:${color}">model</span>
      <button class="fp-close" title="Close">&times;</button>
    </div>
    <div class="floating-panel-body" style="padding:1rem"></div>
    <div class="floating-panel-meta"></div>
  `;

  panel.querySelector('.fp-close').addEventListener('click', () => {
    panel.remove();
    floatingPanels.delete(panelKey);
  });
  makeDraggable(panel, panel.querySelector('.floating-panel-header'));
  panel.addEventListener('mousedown', () => { panel.style.zIndex = ++floatingZCounter; });

  container.appendChild(panel);
  floatingPanels.set(panelKey, panel);

  const body = panel.querySelector('.floating-panel-body');
  const meta = panel.querySelector('.floating-panel-meta');

  let html = '';
  html += `<div style="margin-bottom:0.75rem">`;
  html += `<div style="font-size:0.85rem;font-weight:600;margin-bottom:4px">${escapeHtml(node.name || '')}</div>`;
  if (node.session_count != null) {
    html += `<div style="font-size:0.78rem;color:var(--text-dim)">Used in <span style="color:${color};font-weight:600">${node.session_count}</span> sessions</div>`;
  }
  html += `</div>`;

  if (graphData && graphData.edges && graphData.nodes) {
    const nodeMap = {};
    graphData.nodes.forEach(n => { nodeMap[n.id] = n; });

    const sessions = [];
    graphData.edges.forEach(e => {
      const sid = typeof e.source === 'object' ? e.source.id : e.source;
      const tid = typeof e.target === 'object' ? e.target.id : e.target;
      if (e.type === 'used_model') {
        if (tid === node.id && nodeMap[sid] && nodeMap[sid].type === 'session') sessions.push(nodeMap[sid]);
        else if (sid === node.id && nodeMap[tid] && nodeMap[tid].type === 'session') sessions.push(nodeMap[tid]);
      }
    });

    // Compute aggregated stats
    let totalInput = 0, totalOutput = 0, totalCost = 0;
    sessions.forEach(s => {
      if (s.input_tokens) totalInput += s.input_tokens;
      if (s.output_tokens) totalOutput += s.output_tokens;
      if (s.estimated_cost_usd) totalCost += s.estimated_cost_usd;
    });

    if (totalInput > 0 || totalOutput > 0) {
      html += `<div style="display:flex;gap:1rem;margin-bottom:0.75rem;flex-wrap:wrap">`;
      html += `<div style="font-size:0.72rem"><span style="color:var(--text-dim)">Input tokens</span><br><span style="font-weight:600;color:${color}">${totalInput.toLocaleString()}</span></div>`;
      html += `<div style="font-size:0.72rem"><span style="color:var(--text-dim)">Output tokens</span><br><span style="font-weight:600;color:${color}">${totalOutput.toLocaleString()}</span></div>`;
      if (totalCost > 0) html += `<div style="font-size:0.72rem"><span style="color:var(--text-dim)">Est. cost</span><br><span style="font-weight:600;color:${color}">$${totalCost.toFixed(4)}</span></div>`;
      html += `</div>`;
    }

    if (sessions.length > 0) {
      html += `<div style="font-size:0.75rem;font-weight:600;color:var(--text-dim);margin-bottom:6px;text-transform:uppercase;letter-spacing:0.05em">Sessions (${sessions.length})</div>`;
      html += `<div style="max-height:300px;overflow-y:auto">`;
      sessions.slice(0, 50).forEach(s => {
        const label = s.label || s.session_id || s.id;
        const time = s.started_at ? new Date(s.started_at * 1000).toLocaleDateString() : '';
        html += `<div class="sidebar-neighbor" onclick="onNeighborClick('${s.id.replace(/'/g, "\\'")}')">
          <span style="font-size:0.9rem;flex-shrink:0">\u{1F4AC}</span>
          <span style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:0.78rem">${escapeHtml(label)}</span>
          <span style="font-size:0.65rem;color:var(--text-dim)">${time}</span>
        </div>`;
      });
      if (sessions.length > 50) html += `<div style="font-size:0.7rem;color:var(--text-dim);padding:4px 8px">...and ${sessions.length - 50} more</div>`;
      html += `</div>`;
    }
  }

  body.innerHTML = html;
  if (meta) meta.innerHTML = `<span>Type: <span class="val">model</span></span><span>Sessions: <span class="val">${node.session_count || 0}</span></span>`;
}

// ── Floating skill panel ──
function openFloatingSkillPanel(node) {
  const panelKey = 'skill:' + (node.name || node.id);
  if (floatingPanels.has(panelKey)) {
    floatingPanels.get(panelKey).style.zIndex = ++floatingZCounter;
    return;
  }

  const container = document.getElementById('graph-container');
  const panel = document.createElement('div');
  panel.className = 'floating-panel';
  setFloatingPanelWidth(panel, 440);

  const offset = floatingPanels.size * 30;
  panel.style.left = (200 + offset) + 'px';
  panel.style.top = (80 + offset) + 'px';
  panel.style.zIndex = ++floatingZCounter;

  const color = '#ffd700';
  panel.innerHTML = `
    <div class="floating-panel-header">
      <span class="fp-icon">\u{2B50}</span>
      <span class="fp-title">${escapeHtml(node.name || node.label || '')}</span>
      <span class="fp-badge" style="background:rgba(255,215,0,0.15);color:${color}">skill</span>
      <button class="fp-close" title="Close">&times;</button>
    </div>
    <div class="floating-panel-body" style="padding:1rem"></div>
    <div class="floating-panel-meta"></div>
  `;

  panel.querySelector('.fp-close').addEventListener('click', () => {
    panel.remove();
    floatingPanels.delete(panelKey);
  });
  makeDraggable(panel, panel.querySelector('.floating-panel-header'));
  panel.addEventListener('mousedown', () => { panel.style.zIndex = ++floatingZCounter; });

  container.appendChild(panel);
  floatingPanels.set(panelKey, panel);

  const body = panel.querySelector('.floating-panel-body');
  const meta = panel.querySelector('.floating-panel-meta');

  let html = '';
  html += `<div style="margin-bottom:0.75rem">`;
  html += `<div style="font-size:0.85rem;font-weight:600;margin-bottom:4px">${escapeHtml(node.name || '')}</div>`;
  if (node.description) {
    html += `<div style="font-size:0.78rem;color:var(--text-dim);line-height:1.5;margin-bottom:6px">${escapeHtml(node.description)}</div>`;
  }
  if (node.category) {
    html += `<div style="font-size:0.72rem"><span style="color:var(--text-dim)">Category:</span> <span style="color:${color};font-weight:600">${escapeHtml(node.category)}</span></div>`;
  }
  html += `<div style="font-size:0.72rem"><span style="color:var(--text-dim)">Enabled:</span> <span style="font-weight:600;color:${node.enabled ? '#22c55e' : '#f87171'}">${node.enabled ? 'Yes' : 'No'}</span></div>`;
  html += `</div>`;

  // Find related skills and sessions
  if (graphData && graphData.edges && graphData.nodes) {
    const nodeMap = {};
    graphData.nodes.forEach(n => { nodeMap[n.id] = n; });

    const relatedSkills = [];
    const sessions = [];
    graphData.edges.forEach(e => {
      const sid = typeof e.source === 'object' ? e.source.id : e.source;
      const tid = typeof e.target === 'object' ? e.target.id : e.target;

      if (e.type === 'relates_to') {
        if (sid === node.id && nodeMap[tid] && nodeMap[tid].type === 'skill') relatedSkills.push(nodeMap[tid]);
        else if (tid === node.id && nodeMap[sid] && nodeMap[sid].type === 'skill') relatedSkills.push(nodeMap[sid]);
      }
      // Skills might be connected to sessions via loaded_skill edges or similar
      if (sid === node.id && nodeMap[tid] && nodeMap[tid].type === 'session') sessions.push(nodeMap[tid]);
      else if (tid === node.id && nodeMap[sid] && nodeMap[sid].type === 'session') sessions.push(nodeMap[sid]);
    });

    if (relatedSkills.length > 0) {
      html += `<div style="font-size:0.75rem;font-weight:600;color:var(--text-dim);margin-bottom:6px;text-transform:uppercase;letter-spacing:0.05em">Related Skills (${relatedSkills.length})</div>`;
      relatedSkills.forEach(s => {
        html += `<div class="sidebar-neighbor" onclick="onNeighborClick('${s.id.replace(/'/g, "\\'")}')">
          <span style="font-size:0.9rem;flex-shrink:0">\u{2B50}</span>
          <span style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:0.78rem">${escapeHtml(s.name || s.label || s.id)}</span>
          <span style="font-size:0.65rem;color:var(--text-dim)">${s.category || ''}</span>
        </div>`;
      });
    }

    if (sessions.length > 0) {
      html += `<div style="font-size:0.75rem;font-weight:600;color:var(--text-dim);margin:10px 0 6px;text-transform:uppercase;letter-spacing:0.05em">Sessions (${sessions.length})</div>`;
      html += `<div style="max-height:250px;overflow-y:auto">`;
      sessions.slice(0, 30).forEach(s => {
        const label = s.label || s.session_id || s.id;
        html += `<div class="sidebar-neighbor" onclick="onNeighborClick('${s.id.replace(/'/g, "\\'")}')">
          <span style="font-size:0.9rem;flex-shrink:0">\u{1F4AC}</span>
          <span style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:0.78rem">${escapeHtml(label)}</span>
        </div>`;
      });
      if (sessions.length > 30) html += `<div style="font-size:0.7rem;color:var(--text-dim);padding:4px 8px">...and ${sessions.length - 30} more</div>`;
      html += `</div>`;
    }
  }

  body.innerHTML = html;
  const metaParts = [`<span>Type: <span class="val">skill</span></span>`];
  if (node.category) metaParts.push(`<span>Category: <span class="val">${escapeHtml(node.category)}</span></span>`);
  metaParts.push(`<span>Status: <span class="val">${node.enabled ? 'Enabled' : 'Disabled'}</span></span>`);
  if (meta) meta.innerHTML = metaParts.join('');
}

// ── Remove all floating panels ──
function removeAllFloatingPanels() {
  floatingPanels.forEach((panel) => panel.remove());
  floatingPanels.clear();
}

// ── Legend builder ──
function buildGraphLegend() {
  const legend = document.getElementById('graph-legend');
  if (!legend) return;

  const types = [
    { type: 'session', color: '#a855f7', label: 'Session' },
    { type: 'file',    color: '#22c55e', label: 'File' },
    { type: 'tool',    color: '#f97316', label: 'Tool' },
    { type: 'model',   color: '#06b6d4', label: 'Model' },
    { type: 'skill',   color: '#ffd700', label: 'Skill' },
  ];

  legend.innerHTML = types.map(t =>
    `<span class="legend-item">
      <span class="legend-dot" style="background:${t.color}"></span>
      ${t.label}
    </span>`
  ).join('');
}

// GRAPH_SIDEBAR_START

// ── Sidebar metadata builder ──
function formatGraphTimestamp(ts) {
  if (ts == null) return 'N/A';
  return new Date(ts * 1000).toLocaleString();
}

function formatCost(val) {
  if (val == null) return 'N/A';
  return '$' + Number(val).toFixed(4);
}

function detailRow(key, val) {
  if (val == null || val === '') return '';
  return `<div class="detail-row"><span class="key">${escapeHtml(String(key))}</span><span class="val">${val}</span></div>`;
}

function buildSidebarMetadata(node) {
  const label = node.label || node.name || node.id;
  const type = node.type || 'unknown';
  const color = nodeTypeColor(type);

  let html = `
    <div class="detail-row" style="align-items:center;gap:8px">
      <span style="font-size:1.3rem">${nodeTypeIcon(type)}</span>
      <span class="val" style="font-weight:700;font-size:0.95rem">${escapeHtml(label)}</span>
      <span style="background:${color}15;color:${color};padding:2px 8px;border-radius:6px;font-size:0.7rem;font-weight:600">${type}</span>
    </div>
  `;

  switch (type) {
    case 'session':
      html += detailRow('ID', `<span style="font-family:monospace;font-size:0.7rem">${escapeHtml(node.session_id || node.id)}</span><button class="fp-copy-btn" onclick="copyToClipboard('${(node.session_id || node.id).replace(/'/g, "\\'")}')" title="Copy session ID">&#x29C9;</button>`);
      if (node.source) html += detailRow('Source', escapeHtml(node.source));
      if (node.model) html += detailRow('Model', escapeHtml(node.model));
      if (node.summary) html += detailRow('Summary', escapeHtml(node.summary));
      html += detailRow('Started', formatGraphTimestamp(node.started_at));
      html += detailRow('Ended', node.ended_at ? formatGraphTimestamp(node.ended_at) : 'In progress');
      if (node.message_count != null) html += detailRow('Messages', node.message_count);
      if (node.tool_call_count != null) html += detailRow('Tool Calls', node.tool_call_count);
      if (node.input_tokens != null) html += detailRow('Input Tokens', Number(node.input_tokens).toLocaleString());
      if (node.output_tokens != null) html += detailRow('Output Tokens', Number(node.output_tokens).toLocaleString());
      if (node.estimated_cost_usd != null) html += detailRow('Est. Cost', formatCost(node.estimated_cost_usd));
      break;
    case 'file':
      html += detailRow('Path', `<span style="font-family:monospace;font-size:0.7rem;word-break:break-all">${escapeHtml(node.path || '')}</span><button class="fp-copy-btn" onclick="copyToClipboard('${(node.path || '').replace(/\\/g, '\\\\').replace(/'/g, "\\'")}')" title="Copy file path">&#x29C9;</button>`);
      if (node.basename) html += detailRow('Basename', escapeHtml(node.basename));
      if (node.category) html += detailRow('Category', escapeHtml(node.category));
      break;
    case 'tool':
      html += detailRow('Name', escapeHtml(node.name || ''));
      if (node.usage_count != null) html += detailRow('Usage Count', node.usage_count);
      break;
    case 'model':
      html += detailRow('Name', escapeHtml(node.name || ''));
      if (node.session_count != null) html += detailRow('Sessions', node.session_count);
      break;
    case 'skill':
      html += detailRow('Name', escapeHtml(node.name || ''));
      if (node.description) html += detailRow('Description', escapeHtml(node.description));
      if (node.category) html += detailRow('Category', escapeHtml(node.category));
      html += detailRow('Enabled', node.enabled ? 'Yes' : 'No');
      break;
  }

  // Connection summary
  const connMap = {};
  let connTotal = 0;
  if (graphData && graphData.edges) {
    graphData.edges.forEach(e => {
      const sid = typeof e.source === 'object' ? e.source.id : e.source;
      const tid = typeof e.target === 'object' ? e.target.id : e.target;
      if (sid === node.id || tid === node.id) {
        connTotal++;
        const t = e.type || 'unknown';
        connMap[t] = (connMap[t] || 0) + 1;
      }
    });
  }
  html += detailRow('Connections', connTotal);

  const detailsEl = document.getElementById('sidebar-details');
  if (detailsEl) detailsEl.innerHTML = html;

  const contentEl = document.getElementById('sidebar-content');
  if (contentEl) contentEl.innerHTML = buildNeighborsList(node);
}

function buildNeighborsList(node) {
  if (!graphData || !graphData.edges || !graphData.nodes) {
    return '<div style="color:var(--text-dim);font-size:0.8rem">No graph data</div>';
  }

  const nodeMap = {};
  graphData.nodes.forEach(n => { nodeMap[n.id] = n; });

  const neighbors = [];
  const seen = new Set();

  graphData.edges.forEach(e => {
    const sid = typeof e.source === 'object' ? e.source.id : e.source;
    const tid = typeof e.target === 'object' ? e.target.id : e.target;
    let neighborId = null;
    let relation = e.type || 'related';

    if (sid === node.id) neighborId = tid;
    else if (tid === node.id) neighborId = sid;

    if (neighborId && !seen.has(neighborId)) {
      seen.add(neighborId);
      const nb = nodeMap[neighborId];
      if (nb) neighbors.push({ node: nb, relation });
    }
  });

  if (neighbors.length === 0) {
    return '<div style="color:var(--text-dim);font-size:0.8rem">No connected nodes</div>';
  }

  let html = `<h4 style="margin:0 0 0.5rem 0;font-size:0.8rem;color:var(--text-dim)">Connected Nodes (${neighbors.length})</h4>`;

  neighbors.forEach(nb => {
    const n = nb.node;
    const color = nodeTypeColor(n.type);
    const displayLabel = n.label || n.name || n.id;

    html += `
      <div class="sidebar-neighbor" onclick="onNeighborClick('${n.id.replace(/'/g, "\\'")}')">
        <span style="font-size:1rem;flex-shrink:0">${nodeTypeIcon(n.type)}</span>
        <span style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:0.8rem">${escapeHtml(displayLabel)}</span>
        <span style="background:${color}15;color:${color};padding:1px 6px;border-radius:4px;font-size:0.65rem;font-weight:600">${n.type}</span>
        <span style="font-size:0.65rem;color:var(--text-dim)">${nb.relation}</span>
      </div>
    `;
  });

  return html;
}

function onNeighborClick(nodeId) {
  if (!graphData || !graphData.nodes) return;
  const node = graphData.nodes.find(n => n.id === nodeId);
  if (!node) return;

  // Open the appropriate floating panel for this node type
  if (node.type === 'file' && node.path) {
    openFloatingPanel(node.path);
  } else if (node.type === 'session') {
    openFloatingSessionPanel(node.session_id || node.id.replace('session:', ''));
  } else if (node.type === 'tool') {
    openFloatingToolPanel(node);
  } else if (node.type === 'model') {
    openFloatingModelPanel(node);
  } else if (node.type === 'skill') {
    openFloatingSkillPanel(node);
  }

  // Pan the canvas to center on the node
  if (typeof window._graphPanToNode === 'function') {
    window._graphPanToNode(nodeId);
  }
}

// GRAPH_SIDEBAR_END

// AbortController for graph canvas event listeners (prevents accumulation on reload)
let graphCanvasAbort = null;

// ── Core: loadGraph(includeFiles) ──
async function loadGraph() {
  const depth = 'full';
  const hours = document.getElementById('graph-time-scope')?.value || '24';
  const url = '/api/graph?depth=' + depth + '&hours=' + hours;

  try {
    const resp = await fetch(url);
    if (!resp.ok) throw new Error('API error ' + resp.status);
    graphData = await resp.json();
  } catch (err) {
    log('warn', 'Graph API failed: ' + err.message);
    showToast('Graph API unavailable');
    graphData = { nodes: [], edges: [], node_count: 0, edge_count: 0 };
    const badge = document.getElementById('graph-badge');
    if (badge) badge.textContent = 'Graph unavailable';
    const sidebar = document.getElementById('graph-sidebar');
    if (sidebar) sidebar.classList.remove('open');
    removeAllFloatingPanels();
    graphLoaded = false;
    return;
  }

  const container = document.getElementById('graph-container');
  const canvas = document.getElementById('graph-canvas');
  const ctx = canvas.getContext('2d');
  const width = container.clientWidth;
  const height = container.clientHeight;

  // Abort old canvas event listeners to prevent accumulation
  if (graphCanvasAbort) graphCanvasAbort.abort();
  graphCanvasAbort = new AbortController();
  const canvasSignal = graphCanvasAbort.signal;

  // Set canvas resolution (handle HiDPI)
  const dpr = window.devicePixelRatio || 1;
  canvas.width = width * dpr;
  canvas.height = height * dpr;
  canvas.style.width = width + 'px';
  canvas.style.height = height + 'px';

  // Clean up
  removeAllFloatingPanels();

  const nodes = graphData.nodes || [];
  const edges = graphData.edges || [];

  // Compute degree for each node
  const degreeMap = new Map();
  nodes.forEach(n => degreeMap.set(n.id, 0));
  edges.forEach(e => {
    const sid = typeof e.source === 'object' ? e.source.id : e.source;
    const tid = typeof e.target === 'object' ? e.target.id : e.target;
    degreeMap.set(sid, (degreeMap.get(sid) || 0) + 1);
    degreeMap.set(tid, (degreeMap.get(tid) || 0) + 1);
  });
  nodes.forEach(n => { n.degree = degreeMap.get(n.id) || 0; });

  const maxDegree = Math.max(1, ...nodes.map(n => n.degree));
  const radiusScale = d3.scaleSqrt().domain([0, maxDegree]).range([4, 22]);

  // Build adjacency index for O(degree) lookups
  const adjacency = new Map();
  nodes.forEach(n => adjacency.set(n.id, { edges: [], neighbors: new Set() }));
  edges.forEach(e => {
    const sid = typeof e.source === 'object' ? e.source.id : e.source;
    const tid = typeof e.target === 'object' ? e.target.id : e.target;
    const sEntry = adjacency.get(sid);
    const tEntry = adjacency.get(tid);
    if (sEntry) { sEntry.edges.push(e); sEntry.neighbors.add(tid); }
    if (tEntry) { tEntry.edges.push(e); tEntry.neighbors.add(sid); }
  });

  if (nodes.length === 0) {
    const badge = document.getElementById('graph-badge');
    if (badge) badge.textContent = '0 nodes';
    ctx.save();
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, width, height);
    ctx.restore();
    graphLoaded = true;
    return;
  }

  // ── Badge ──
  const badge = document.getElementById('graph-badge');
  if (badge) badge.textContent = `${nodes.length} nodes \u00b7 ${edges.length} edges`;

  // ── Legend ──
  buildGraphLegend();

  // ── Active filter state ──
  const activeTypes = new Set(
    Array.from(document.querySelectorAll('.type-toggle.active')).map(btn => btn.dataset.type)
  );
  if (!activeTypes.size) {
    ['session', 'file', 'tool', 'model', 'skill'].forEach(type => activeTypes.add(type));
  }
  let minDegree = Number(document.getElementById('graph-degree-slider')?.value || 0);
  const visibleNodeIds = new Set(nodes.map(n => n.id));

  // Update type counts in toggle buttons
  ['session', 'file', 'tool', 'model', 'skill'].forEach(t => {
    const countEl = document.querySelector(`.toggle-count[data-count="${t}"]`);
    if (countEl) countEl.textContent = nodes.filter(n => n.type === t).length;
  });

  // ── Type configs ──
  const typeConfig = {
    session: { color: '#a855f7', shape: 'hexagon', r: 14 },
    file:    { color: '#22c55e', shape: 'circle',  r: 6 },
    tool:    { color: '#f97316', shape: 'diamond',  r: 8 },
    model:   { color: '#06b6d4', shape: 'square',   r: 12 },
    skill:   { color: '#ffd700', shape: 'circle',   r: 10 },
  };

  const edgeConfig = {
    accessed:   { stroke: '#22c55e', dash: [6,3], width: 1.5 },
    used_tool:  { stroke: '#f97316', dash: [3,3], width: 1.2 },
    used_model: { stroke: '#06b6d4', dash: [],    width: 1.5 },
    delegated:  { stroke: '#a855f7', dash: [],    width: 2 },
    relates_to: { stroke: '#ffd700', dash: [4,4], width: 1 },
    used_skill: { stroke: '#ffd700', dash: [2,4], width: 1.4 },
  };
  const defaultEdge = { stroke: '#4b5563', dash: [], width: 1 };
  function edgeCfg(d) {
    const base = edgeConfig[d.type] || defaultEdge;
    if (graphSettings.edgeStyle === 'solid') return { ...base, dash: [] };
    if (graphSettings.edgeStyle === 'dashed') return { ...base, dash: [4, 3] };
    return base;
  }

  function applyNodeSizing() {
    nodes.forEach(n => {
      const cfg = typeConfig[n.type] || typeConfig.file;
      const baseRadius = Math.max(cfg.r * 0.7, radiusScale(n.degree));
      n._r = baseRadius * graphSettings.nodeScale;
      n._visible = true;
      n._searchMatch = true;
      n._alpha = 1;
    });
  }

  // Compute radii for all nodes
  applyNodeSizing();
  edges.forEach(e => { e._filtered = false; });

  // ── Interaction state ──
  let hoveredNode = null;
  let selectedNode = null;
  let dragNode = null;
  let showLabels = document.getElementById('graph-toggle-labels')?.checked !== false;
  let currentZoomK = 1;
  const reducedMotion = resolvedGraphMotionMode() === 'reduced';

  function isEdgeVisible(edge) {
    if (!graphSettings.showEdges) return false;
    return graphSettings.edgeTypes[edge.type] !== false;
  }

  function shouldDrawLabel(node) {
    if (!showLabels || !node._visible) return false;
    if (node === hoveredNode || node === selectedNode) return true;
    const density = graphSettings.labelDensity;
    if (density === 'dense') return currentZoomK >= 0.45;
    if (density === 'normal') return currentZoomK >= 0.65 && (node.type === 'session' || node.type === 'model' || node.type === 'skill' || node.degree >= 4);
    if (density === 'sparse') return currentZoomK >= 1 && (node.type === 'session' || node.type === 'model' || node.degree >= 6);
    if (currentZoomK >= 1.2) return true;
    return currentZoomK >= 0.8 && (node.type === 'session' || node.type === 'model' || (node.type === 'skill' && node.degree >= 2));
  }

  function trimGraphLabel(label) {
    const value = String(label || '');
    const maxLength = Math.max(4, Math.round(graphSettings.labelMaxLength));
    return value.length > maxLength ? value.slice(0, maxLength - 1).trimEnd() + '\u2026' : value;
  }

  // ── Quadtree ──
  let quadtree = d3.quadtree()
    .x(d => d.x)
    .y(d => d.y);

  function rebuildQuadtree() {
    quadtree = d3.quadtree()
      .x(d => d.x)
      .y(d => d.y)
      .addAll(nodes.filter(n => n._visible));
  }

  // ── Canvas shape drawers ──
  function drawHexagon(ctx, x, y, r) {
    const a = Math.PI / 3;
    ctx.beginPath();
    for (let i = 0; i < 6; i++) {
      const px = x + r * Math.cos(a * i - Math.PI / 6);
      const py = y + r * Math.sin(a * i - Math.PI / 6);
      if (i === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    }
    ctx.closePath();
  }

  function drawDiamond(ctx, x, y, r) {
    ctx.beginPath();
    ctx.moveTo(x, y - r);
    ctx.lineTo(x + r, y);
    ctx.lineTo(x, y + r);
    ctx.lineTo(x - r, y);
    ctx.closePath();
  }

  function drawSquare(ctx, x, y, r) {
    ctx.beginPath();
    ctx.rect(x - r, y - r, r * 2, r * 2);
  }

  function drawArrow(ctx, sx, sy, tx, ty, r) {
    const angle = Math.atan2(ty - sy, tx - sx);
    const tipX = tx - Math.cos(angle) * (r + 2);
    const tipY = ty - Math.sin(angle) * (r + 2);
    const arrowLen = 6 / transform.k;
    const arrowW = 3 / transform.k;
    ctx.beginPath();
    ctx.moveTo(tipX, tipY);
    ctx.lineTo(tipX - arrowLen * Math.cos(angle - Math.PI / 7), tipY - arrowLen * Math.sin(angle - Math.PI / 7));
    ctx.lineTo(tipX - arrowLen * Math.cos(angle + Math.PI / 7), tipY - arrowLen * Math.sin(angle + Math.PI / 7));
    ctx.closePath();
    ctx.fill();
  }

  // ── Render function ──
  let needsRender = false;

  function render() {
    ctx.save();
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.scale(dpr, dpr);
    ctx.translate(transform.x, transform.y);
    ctx.scale(transform.k, transform.k);

    const focusNode = selectedNode || hoveredNode;

    // Build connected node set — only include visible neighbors
    const connectedIds = new Set();
    if (focusNode) {
      connectedIds.add(focusNode.id);
      const adj = adjacency.get(focusNode.id);
      if (adj) adj.neighbors.forEach(nid => {
        if (visibleNodeIds.has(nid)) connectedIds.add(nid);
      });
    }

    // Draw edges
    const edgesToDraw = focusNode && focusNode._visible
      ? (adjacency.get(focusNode.id)?.edges || [])
      : edges;
    edgesToDraw.forEach(e => {
      if (e._filtered) return;
      const s = typeof e.source === 'object' ? e.source : null;
      const t = typeof e.target === 'object' ? e.target : null;
      if (!s || !t) return;
      if (s.x == null || t.x == null) return;
      if (!s._visible || !t._visible) return;

      const cfg = edgeCfg(e);
      ctx.save();
      ctx.strokeStyle = cfg.stroke;
      ctx.lineWidth = cfg.width / transform.k;
      let edgeAlpha = graphSettings.edgeOpacity;
      if (focusNode) {
        const isConnected = s.id === focusNode.id || t.id === focusNode.id;
        edgeAlpha = selectedNode
          ? (isConnected ? Math.max(graphSettings.edgeOpacity, 0.9) : graphSettings.edgeOpacity * 0.25)
          : (isConnected ? Math.max(graphSettings.edgeOpacity, 0.75) : graphSettings.edgeOpacity * 0.4);
      }
      if ((!s._searchMatch || !t._searchMatch) && !focusNode) edgeAlpha = Math.min(edgeAlpha, 0.06);
      ctx.globalAlpha = edgeAlpha;
      if (cfg.dash.length > 0) ctx.setLineDash(cfg.dash.map(v => v / transform.k));
      else ctx.setLineDash([]);

      ctx.beginPath();
      ctx.moveTo(s.x, s.y);
      ctx.lineTo(t.x, t.y);
      ctx.stroke();

      ctx.setLineDash([]);
      ctx.fillStyle = cfg.stroke;
      ctx.globalAlpha = Math.min(1, edgeAlpha + 0.1);
      drawArrow(ctx, s.x, s.y, t.x, t.y, t._r || 6);

      ctx.restore();
    });

    // Draw nodes

    nodes.forEach(n => {
      if (!n._visible) return;
      if (n.x == null || n.y == null) return;

      const cfg = typeConfig[n.type] || typeConfig.file;
      const r = n._r;

      // Compute alpha based on focus/search state
      let alpha = n._alpha;
      if (focusNode) {
        if (selectedNode) {
          // Click-selection: stronger dimming
          alpha = connectedIds.has(n.id) ? 1 : 0.15;
        } else {
          // Hover only: subtle dimming
          alpha = connectedIds.has(n.id) ? 1 : 0.4;
        }
      }
      if (!n._searchMatch) alpha = 0.1;

      ctx.globalAlpha = alpha;

      // Fill
      ctx.fillStyle = cfg.color + '30';
      ctx.strokeStyle = cfg.color;
      ctx.lineWidth = 1.5 / transform.k;

      if (cfg.shape === 'circle') {
        ctx.beginPath();
        ctx.arc(n.x, n.y, r, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();
      } else if (cfg.shape === 'hexagon') {
        drawHexagon(ctx, n.x, n.y, r);
        ctx.fill();
        ctx.stroke();
      } else if (cfg.shape === 'diamond') {
        drawDiamond(ctx, n.x, n.y, r);
        ctx.fill();
        ctx.stroke();
      } else if (cfg.shape === 'square') {
        drawSquare(ctx, n.x, n.y, r);
        ctx.fill();
        ctx.stroke();
      }

      // Highlight ring for hovered/selected
      if (n === hoveredNode || n === selectedNode) {
        ctx.globalAlpha = 0.6;
        ctx.strokeStyle = '#fff';
        ctx.lineWidth = 2 / transform.k;
        if (cfg.shape === 'circle') {
          ctx.beginPath();
          ctx.arc(n.x, n.y, r + 2, 0, Math.PI * 2);
          ctx.stroke();
        } else if (cfg.shape === 'hexagon') {
          drawHexagon(ctx, n.x, n.y, r + 2);
          ctx.stroke();
        } else if (cfg.shape === 'diamond') {
          drawDiamond(ctx, n.x, n.y, r + 2);
          ctx.stroke();
        } else if (cfg.shape === 'square') {
          drawSquare(ctx, n.x, n.y, r + 2);
          ctx.stroke();
        }
      }
    });

    // Draw labels
    if (showLabels) {
      ctx.textAlign = 'center';
      ctx.textBaseline = 'top';
      nodes.forEach(n => {
        if (!shouldDrawLabel(n)) return;
        if (n.x == null || n.y == null) return;

        let alpha = 0.7;
        if (focusNode) {
          if (selectedNode) {
            alpha = connectedIds.has(n.id) ? 1 : 0.12;
          } else {
            alpha = connectedIds.has(n.id) ? 1 : 0.35;
          }
        }
        if (!n._searchMatch) alpha = 0.08;

        ctx.globalAlpha = alpha;
        const baseFontSize = n.type === 'session' || n.type === 'model'
          ? graphSettings.labelFontSize + 1
          : graphSettings.labelFontSize;
        ctx.font = `${baseFontSize / transform.k}px ${graphFontFamily()}`;
        ctx.fillStyle = '#a0a0b0';

        const name = n.label || n.name || n.id || '';
        const label = trimGraphLabel(name);
        ctx.fillText(label, n.x, n.y + (n._r || 8) + 4);
      });
    }

    ctx.restore();
    needsRender = false;
  }

  // Apply visibility filter (client-side, no API call, no re-layout)
  function applyVisibilityFilter() {
    visibleNodeIds.clear();
    nodes.forEach(n => {
      const typeVisible = activeTypes.has(n.type);
      const degreeVisible = n.degree >= minDegree;
      n._visible = typeVisible && degreeVisible;
      if (n._visible) visibleNodeIds.add(n.id);
    });

    edges.forEach(e => {
      const sid = typeof e.source === 'object' ? e.source.id : e.source;
      const tid = typeof e.target === 'object' ? e.target.id : e.target;
      e._filtered = !(visibleNodeIds.has(sid) && visibleNodeIds.has(tid) && isEdgeVisible(e));
    });

    // Clear selection if node is now hidden
    if (hoveredNode && !hoveredNode._visible) hoveredNode = null;
    if (selectedNode && !selectedNode._visible) {
      selectedNode = null;
      const sidebar = document.getElementById('graph-sidebar');
      if (sidebar) sidebar.classList.remove('open');
    }

    // Update badge
    const visibleCount = visibleNodeIds.size;
    const visibleEdges = edges.filter(e => !e._filtered).length;
    const badgeEl = document.getElementById('graph-badge');
    if (badgeEl) badgeEl.textContent = `${visibleCount}/${nodes.length} nodes \u00b7 ${visibleEdges}/${edges.length} edges`;

    rebuildQuadtree();
    scheduleRender();
  }

  // Expose filter entry points
  window._graphApplyFilter = function(newActiveTypes) {
    activeTypes.clear();
    newActiveTypes.forEach(t => activeTypes.add(t));
    applyVisibilityFilter();
  };
  window._graphApplyDegree = function(newMinDegree) {
    minDegree = newMinDegree;
    applyVisibilityFilter();
  };

  function scheduleRender() {
    if (!needsRender) {
      needsRender = true;
      requestAnimationFrame(render);
    }
  }

  // ── Force simulation ──
  const isLarge = nodes.length > 300;
  if (graphSim) graphSim.stop();
  const spacingMultiplier = graphSettings.spacing;

  // Pre-initialize node positions around center to avoid phantom clusters
  // D3's default phyllotaxis places nodes around (0,0) which is off-screen
  nodes.forEach(n => {
    if (n.x == null) n.x = width / 2 + (Math.random() - 0.5) * 200;
    if (n.y == null) n.y = height / 2 + (Math.random() - 0.5) * 200;
  });

  graphSim = d3.forceSimulation(nodes)
    .force('link', d3.forceLink(edges).id(d => d.id)
      .distance(d => {
        if (d.type === 'accessed')   return (isLarge ? 40 : 60) * spacingMultiplier;
        if (d.type === 'used_tool')  return (isLarge ? 30 : 50) * spacingMultiplier;
        if (d.type === 'used_model') return (isLarge ? 50 : 80) * spacingMultiplier;
        if (d.type === 'delegated')  return (isLarge ? 60 : 90) * spacingMultiplier;
        return (isLarge ? 35 : 55) * spacingMultiplier;
      })
      .strength(d => {
        if (d.type === 'accessed')   return isLarge ? 0.2  : 0.4;
        if (d.type === 'used_tool')  return isLarge ? 0.15 : 0.3;
        if (d.type === 'delegated')  return isLarge ? 0.25 : 0.5;
        return isLarge ? 0.1 : 0.25;
      })
    )
    .force('charge', d3.forceManyBody()
      .strength(d => {
        if (d.type === 'session') return (isLarge ? -80  : -200) * spacingMultiplier;
        if (d.type === 'model')   return (isLarge ? -60  : -150) * spacingMultiplier;
        if (d.type === 'skill')   return (isLarge ? -50  : -120) * spacingMultiplier;
        return (isLarge ? -30 : -80) * spacingMultiplier;
      })
      .distanceMax((isLarge ? 200 : 500) * spacingMultiplier)
      .theta(1.2)
    )
    .force('center', d3.forceCenter(width / 2, height / 2).strength(0.08))
    .force('collision', d3.forceCollide()
      .radius(d => ((d._r || 6) + (isLarge ? 2 : 3)) * Math.max(0.9, spacingMultiplier))
    )
    .force('x', d3.forceX(width / 2).strength(reducedMotion ? 0.1 : 0.06))
    .force('y', d3.forceY(height / 2).strength(reducedMotion ? 0.1 : 0.06))
    .alphaDecay(reducedMotion ? 0.1 : 0.04)
    .velocityDecay(reducedMotion ? 0.65 : 0.5);

  // ── Zoom / pan ──
  let transform = d3.zoomIdentity;
  const zoomBehavior = d3.zoom()
    .scaleExtent([0.15, 5])
    .filter((e) => {
      // Allow wheel events (for zoom) always
      if (e.type === 'wheel') return true;
      // For mousedown/touchstart, prevent zoom when clicking on a node
      if (e.type === 'mousedown' || e.type === 'touchstart') {
        const rect = canvas.getBoundingClientRect();
        const sx = e.clientX - rect.left;
        const sy = e.clientY - rect.top;
        if (findNodeAt(sx, sy)) return false;
      }
      // Default: allow (D3 default filter checks for primary button etc.)
      return !e.ctrlKey && !e.button;
    })
    .on('zoom', (e) => {
      transform = e.transform;
      currentZoomK = transform.k;
      scheduleRender();
    });
  d3.select(canvas).call(zoomBehavior);

  // Expose pan-to-node for cross-referencing from floating panels
  window._graphPanToNode = function(nodeId) {
    const node = nodes.find(n => n.id === nodeId);
    if (!node || node.x == null) return;
    const w = canvas.clientWidth, h = canvas.clientHeight;
    const scale = 1.5;
    const tx = w / 2 - node.x * scale;
    const ty = h / 2 - node.y * scale;
    const newTransform = d3.zoomIdentity.translate(tx, ty).scale(scale);
    d3.select(canvas).transition().duration(400).call(zoomBehavior.transform, newTransform);
    selectedNode = node;
    scheduleRender();
  };

  // Expose fit-to-viewport for keyboard shortcut
  window._graphFitToViewport = function() {
    const visibleNodes = nodes.filter(n => n._visible && n.x != null);
    if (visibleNodes.length === 0) return;
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    visibleNodes.forEach(n => {
      if (n.x < minX) minX = n.x;
      if (n.x > maxX) maxX = n.x;
      if (n.y < minY) minY = n.y;
      if (n.y > maxY) maxY = n.y;
    });
    const w = canvas.clientWidth, h = canvas.clientHeight;
    const padding = 40;
    const dx = maxX - minX || 1;
    const dy = maxY - minY || 1;
    const scale = Math.min((w - padding * 2) / dx, (h - padding * 2) / dy, 3);
    const cx = (minX + maxX) / 2, cy = (minY + maxY) / 2;
    const tx = w / 2 - cx * scale;
    const ty = h / 2 - cy * scale;
    const newTransform = d3.zoomIdentity.translate(tx, ty).scale(scale);
    d3.select(canvas).transition().duration(600).call(zoomBehavior.transform, newTransform);
  };

  // Expose open-panel-for-selected-node for keyboard shortcut
  window._graphOpenSelectedPanel = function() {
    if (!selectedNode) return;
    const found = selectedNode;
    if (found.type === 'file' && found.path) {
      openFloatingPanel(found.path);
    } else if (found.type === 'session') {
      openFloatingSessionPanel(found.session_id || found.id.replace('session:', ''));
    } else if (found.type === 'tool') {
      openFloatingToolPanel(found);
    } else if (found.type === 'model') {
      openFloatingModelPanel(found);
    } else if (found.type === 'skill') {
      openFloatingSkillPanel(found);
    }
  };

  // Reset zoom button
  const resetBtn = document.getElementById('graph-reset');
  if (resetBtn) {
    const newBtn = resetBtn.cloneNode(true);
    resetBtn.parentNode.replaceChild(newBtn, resetBtn);
    newBtn.addEventListener('click', () => {
      d3.select(canvas).transition().duration(600)
        .call(zoomBehavior.transform, d3.zoomIdentity);
    });
  }

  // ── Labels checkbox ──
  const labelsCheckbox = document.getElementById('graph-toggle-labels');
  if (labelsCheckbox) {
    const newCb = labelsCheckbox.cloneNode(true);
    labelsCheckbox.parentNode.replaceChild(newCb, labelsCheckbox);
    showLabels = newCb.checked;
    newCb.addEventListener('change', (e) => {
      showLabels = e.target.checked;
      scheduleRender();
    });
  }

  // ── Hit-testing helpers ──
  function screenToWorld(sx, sy) {
    return [(sx - transform.x) / transform.k, (sy - transform.y) / transform.k];
  }

  function findNodeAt(sx, sy) {
    const [wx, wy] = screenToWorld(sx, sy);
    const searchRadius = 25 / transform.k;
    const found = quadtree.find(wx, wy, searchRadius);
    if (found && found._visible) {
      const dx = found.x - wx;
      const dy = found.y - wy;
      const dist = Math.sqrt(dx * dx + dy * dy);
      if (dist <= (found._r || 8) + 4) return found;
    }
    return null;
  }

  // ── Tooltip ──
  const tooltip = document.getElementById('graph-tooltip');

  function showTooltip(d, clientX, clientY) {
    if (!tooltip) return;
    tooltip.style.display = 'block';
    const ttName = tooltip.querySelector('.tt-name');
    const ttType = tooltip.querySelector('.tt-type');
    if (ttName) ttName.textContent = d.label || d.name || d.id;

    let details = d.type;
    if (d.source) details += ' · ' + d.source;
    if (d.model) details += ' \u00b7 ' + d.model;
    if (d.usage_count) details += ' \u00b7 ' + d.usage_count + ' uses';
    if (d.session_count) details += ' \u00b7 ' + d.session_count + ' sessions';
    if (d.path) details += '\n' + (d.path.length > 50 ? '\u2026' + d.path.slice(-47) : d.path);
    if (d.description) details += '\n' + d.description;
    if (d.summary) details += '\n' + d.summary;
    if (ttType) ttType.textContent = details;

    const rect = container.getBoundingClientRect();
    tooltip.style.left = (clientX - rect.left + 12) + 'px';
    tooltip.style.top = (clientY - rect.top - 10) + 'px';
  }

  function hideTooltip() {
    if (tooltip) tooltip.style.display = 'none';
  }

  // ── Mouse interaction ──
  let lastClickTime = 0;
  let wasDragging = false;

  canvas.addEventListener('mousemove', (e) => {
    if (dragNode) {
      const [wx, wy] = screenToWorld(e.offsetX, e.offsetY);
      dragNode.fx = wx;
      dragNode.fy = wy;
      // Only reheat simulation once when drag actually starts, not every pixel
      if (graphSim.alpha() < 0.05) {
        graphSim.alphaTarget(0.08).restart();
      }
      scheduleRender();
      return;
    }

    const found = findNodeAt(e.offsetX, e.offsetY);
    if (found !== hoveredNode) {
      hoveredNode = found;
      canvas.style.cursor = found ? 'pointer' : 'grab';
      if (found) {
        showTooltip(found, e.clientX, e.clientY);
      } else {
        hideTooltip();
      }
      scheduleRender();
    } else if (found) {
      // Update tooltip position
      showTooltip(found, e.clientX, e.clientY);
    }
  }, { signal: canvasSignal });

  canvas.addEventListener('mousedown', (e) => {
    const found = findNodeAt(e.offsetX, e.offsetY);
    if (found) {
      dragNode = found;
      dragNode._dragPointerStartX = e.clientX;
      dragNode._dragPointerStartY = e.clientY;
      dragNode.fx = dragNode.x;
      dragNode.fy = dragNode.y;
      // Don't reheat simulation on mousedown — wait for actual drag movement
      canvas.style.cursor = 'grabbing';
    }
  }, { signal: canvasSignal });

  canvas.addEventListener('mouseup', (e) => {
    if (dragNode) {
      const startX = Number.isFinite(dragNode._dragPointerStartX) ? dragNode._dragPointerStartX : e.clientX;
      const startY = Number.isFinite(dragNode._dragPointerStartY) ? dragNode._dragPointerStartY : e.clientY;
      const movedDist = Math.abs(e.clientX - startX) + Math.abs(e.clientY - startY);
      wasDragging = movedDist > 5;
      dragNode.fx = null;
      dragNode.fy = null;
      // Immediately cool simulation to prevent jostling after release
      graphSim.alphaTarget(0).alpha(Math.min(graphSim.alpha(), 0.01));
      dragNode = null;
      canvas.style.cursor = 'grab';
    }
  }, { signal: canvasSignal });

  canvas.addEventListener('click', (e) => {
    // Skip click if we just finished dragging a node
    if (wasDragging) {
      wasDragging = false;
      return;
    }
    const now = Date.now();
    const found = findNodeAt(e.offsetX, e.offsetY);
    const sidebar = document.getElementById('graph-sidebar');

    if (found) {
      // Check for double-click (within 350ms)
      if (now - lastClickTime < 350 && selectedNode === found) {
        // Double-click
        if (found.type === 'file' && found.path) {
          openFloatingPanel(found.path);
        } else if (found.type === 'session') {
          openFloatingSessionPanel(found.session_id || found.id.replace('session:', ''));
        } else if (found.type === 'tool') {
          openFloatingToolPanel(found);
        } else if (found.type === 'model') {
          openFloatingModelPanel(found);
        } else if (found.type === 'skill') {
          openFloatingSkillPanel(found);
        }
      } else {
        // Single click: select node, open sidebar
        selectedNode = found;
        if (sidebar) {
          sidebar.classList.add('open');
          const sidebarTitle = document.getElementById('sidebar-title');
          if (sidebarTitle) sidebarTitle.textContent = found.label || found.name || found.id;
          if (typeof buildSidebarMetadata === 'function') buildSidebarMetadata(found);
        }
        scheduleRender();
      }
      lastClickTime = now;
    } else {
      // Background click: deselect
      selectedNode = null;
      if (sidebar) sidebar.classList.remove('open');
      scheduleRender();
      lastClickTime = 0;
    }
  }, { signal: canvasSignal });

  // Sidebar close button
  const sidebarClose = document.getElementById('sidebar-close');
  if (sidebarClose) {
    const newClose = sidebarClose.cloneNode(true);
    sidebarClose.parentNode.replaceChild(newClose, sidebarClose);
    newClose.addEventListener('click', () => {
      selectedNode = null;
      const sidebar = document.getElementById('graph-sidebar');
      if (sidebar) sidebar.classList.remove('open');
      scheduleRender();
    });
  }

  // ── Search ──
  const searchInput = document.getElementById('graph-search');
  if (searchInput) {
    const newSearch = searchInput.cloneNode(true);
    searchInput.parentNode.replaceChild(newSearch, searchInput);
    newSearch.addEventListener('input', debounce(() => {
      const q = newSearch.value.toLowerCase().trim();
      if (!q) {
        nodes.forEach(n => { n._searchMatch = true; });
      } else {
        nodes.forEach(n => {
          const name = (n.label || n.name || n.id || '').toLowerCase();
          n._searchMatch = name.includes(q);
        });
      }
      scheduleRender();
    }, 150));
  }

  // ── Tick handler ──
  graphSim.on('tick', () => {
    rebuildQuadtree();
    scheduleRender();
    if (reducedMotion && graphSim.alpha() < 0.03) {
      graphSim.stop();
    }
  });

  window._graphOnSettingsChanged = function(changedKey) {
    if (changedKey === 'sidebarWidth' || changedKey === 'floatingPanelWidth') {
      applyGraphPanelCssVars();
      scheduleRender();
      return;
    }
    if (
      changedKey === 'labelDensity' ||
      changedKey === 'labelFontSize' ||
      changedKey === 'fontFamily' ||
      changedKey === 'labelMaxLength' ||
      changedKey === 'showEdges' ||
      changedKey === 'edgeOpacity' ||
      changedKey === 'edgeStyle' ||
      String(changedKey || '').startsWith('edgeType:')
    ) {
      applyVisibilityFilter();
      scheduleRender();
      return;
    }
    loadGraph();
  };

  applyVisibilityFilter();
  graphLoaded = true;
}

// GRAPH_INTEGRATION_START

// ── Type toggle buttons ──
document.querySelectorAll('.type-toggle').forEach(btn => {
  btn.addEventListener('click', () => {
    const type = btn.dataset.type;
    btn.classList.toggle('active');
    // Call into loadGraph's filter if graph is loaded
    if (typeof window._graphApplyFilter === 'function') {
      const activeTypes = new Set();
      document.querySelectorAll('.type-toggle.active').forEach(b => activeTypes.add(b.dataset.type));
      window._graphApplyFilter(activeTypes);
    }
  });
});

// ── Degree slider ──
const degreeSlider = document.getElementById('graph-degree-slider');
if (degreeSlider) {
  degreeSlider.addEventListener('input', debounce(() => {
    const val = parseInt(degreeSlider.value);
    const valEl = document.getElementById('degree-val');
    if (valEl) valEl.textContent = val;
    if (typeof window._graphApplyDegree === 'function') {
      window._graphApplyDegree(val);
    }
  }, 100));
}

// ── Preset buttons ──
document.querySelectorAll('.preset-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.preset-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    const preset = btn.dataset.preset;
    const presets = {
      'all': ['session', 'file', 'tool', 'model', 'skill'],
      'sessions-models': ['session', 'model'],
      'tool-usage': ['session', 'tool'],
      'skills-map': ['session', 'skill', 'model'],
    };
    const types = presets[preset] || presets['all'];
    // Update toggle buttons to match preset
    document.querySelectorAll('.type-toggle').forEach(tb => {
      if (types.includes(tb.dataset.type)) {
        tb.classList.add('active');
      } else {
        tb.classList.remove('active');
      }
    });
    if (typeof window._graphApplyFilter === 'function') {
      window._graphApplyFilter(new Set(types));
    }
  });
});

// ── Keyboard shortcuts ──
document.addEventListener('keydown', (e) => {
  const graphPanel = document.getElementById('graph-panel');
  if (!graphPanel || !graphPanel.classList.contains('active')) return;
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT' || e.target.tagName === 'TEXTAREA') return;

  const keyMap = { '1': 'session', '2': 'file', '3': 'tool', '4': 'model', '5': 'skill' };
  if (keyMap[e.key]) {
    e.preventDefault();
    const btn = document.querySelector(`.type-toggle[data-type="${keyMap[e.key]}"]`);
    if (btn) btn.click();
  }
  if (e.key === '/') {
    e.preventDefault();
    document.getElementById('graph-search')?.focus();
  }
  if (e.key === 'Escape') {
    e.preventDefault();
    // Close topmost floating panel, or deselect node if none open
    const container = document.getElementById('graph-container');
    if (container) {
      const panels = Array.from(container.querySelectorAll('.floating-panel'));
      if (panels.length > 0) {
        let topPanel = panels[0];
        let topZ = parseInt(topPanel.style.zIndex || '0');
        panels.forEach(p => {
          const z = parseInt(p.style.zIndex || '0');
          if (z > topZ) { topZ = z; topPanel = p; }
        });
        topPanel.remove();
        // Also remove from floatingPanels map
        if (typeof floatingPanels !== 'undefined') {
          for (const [key, val] of floatingPanels) {
            if (val === topPanel) { floatingPanels.delete(key); break; }
          }
        }
      } else {
        // Deselect node
        selectedNode = null;
        const sidebar = document.getElementById('graph-sidebar');
        if (sidebar) sidebar.classList.remove('open');
        scheduleRender();
      }
    }
  }
  if (e.key === 'f') {
    e.preventDefault();
    if (typeof window._graphFitToViewport === 'function') {
      window._graphFitToViewport();
    }
  }
  if (e.key === 'Enter') {
    e.preventDefault();
    if (typeof window._graphOpenSelectedPanel === 'function') {
      window._graphOpenSelectedPanel();
    }
  }
});

// ── Time scope dropdown ──
document.getElementById('graph-time-scope')?.addEventListener('change', () => {
  loadGraph();
});

// ── Resize handler ──
window.addEventListener('resize', debounce(() => {
  const graphPanel = document.getElementById('graph-panel');
  if (graphPanel && graphPanel.classList.contains('active') && graphLoaded) {
    loadGraph();
  }
}, 300));

// GRAPH_INTEGRATION_END

initGraphSettingsControls();
applyGraphSettingsToUi();
initializeChatRoomRail();

document.getElementById('bot-avatar-file')?.addEventListener('change', (event) => {
    const input = event.currentTarget;
    try {
        const file = validateAvatarFile(input.files?.[0] || null);
        renderAvatarPreview(document.getElementById('bot-create-avatar-preview'), {
            display_name: document.getElementById('bot-display-name')?.value || document.getElementById('bot-name')?.value,
            color: document.getElementById('bot-color')?.value,
        }, file, 'create');
        document.getElementById('bot-create-status').textContent = file ? `${file.name} ready to upload` : '';
    } catch (error) {
        input.value = '';
        renderAvatarPreview(document.getElementById('bot-create-avatar-preview'), {
            display_name: document.getElementById('bot-display-name')?.value || document.getElementById('bot-name')?.value || '?',
            color: document.getElementById('bot-color')?.value,
        }, null, 'create');
        document.getElementById('bot-create-status').textContent = error.message;
    }
});

document.getElementById('bot-edit-avatar-file')?.addEventListener('change', (event) => {
    const input = event.currentTarget;
    try {
        const file = validateAvatarFile(input.files?.[0] || null);
        const current = botRegistry.find(bot => bot.name === botEditorName) || {};
        renderAvatarPreview(document.getElementById('bot-edit-avatar-preview'), {
            ...current,
            display_name: document.getElementById('bot-edit-display-name')?.value || current.display_name,
            color: document.getElementById('bot-edit-color')?.value || current.color,
        }, file, 'edit');
        document.getElementById('bot-edit-status').textContent = file ? `${file.name} ready to upload` : '';
    } catch (error) {
        input.value = '';
        const current = botRegistry.find(bot => bot.name === botEditorName) || { name: botEditorName };
        renderAvatarPreview(document.getElementById('bot-edit-avatar-preview'), current, null, 'edit');
        document.getElementById('bot-edit-status').textContent = error.message;
    }
});

window.addEventListener('beforeunload', () => {
    revokeAvatarPreview('create');
    revokeAvatarPreview('edit');
});

// Initialize (lazy: only load essentials for chat)
log('inf', 'Dashboard initialized');
applyDebugVisibility();
renderDashboardNotificationSettings();
startTokenUsagePolling();
startApprovalPolling();
startProfileBotFlightPolling();
loadStatus();
loadModels();

async function initializeDashboardChatState() {
    const hadActiveRun = await loadActiveRuns();
    restoreActiveRunChildSessions();
    await loadBots();
    let storedRoomId = 'main';
    try {
        storedRoomId = localStorage.getItem(ACTIVE_CHAT_ROOM_KEY) || 'main';
    } catch (error) {
        log('warn', 'Failed to restore active chat room: ' + error.message);
    }
    const desiredRoomId = recoveredLegacyRunRoomId || storedRoomId;

    if (desiredRoomId === 'main') {
        loadActiveChatSession();
        await loadConversation();
    } else {
        try {
            await loadChatRoom(desiredRoomId);
            activeChatRoomId = desiredRoomId;
        } catch (error) {
            activeChatRoomId = 'main';
            loadActiveChatSession();
            await loadConversation();
            showToast(`Could not restore ${desiredRoomId}; opened Main instead`, true);
        }
    }

    if (conversation.length > 0) {
        renderConversation();
        const lastAssistant = [...conversation].reverse().find(msg => msg.role === 'assistant');
        if (lastAssistant && activeChatRoomId !== 'shared') {
            updateContextDisplay(normalizeAssistantMessage(lastAssistant));
        }
    } else {
        updateContextDisplay({ usage: null, last_prompt_tokens: 0 });
    }

    if (hadActiveRun) {
        log('inf', `Recovered ${Object.keys(activeRuns).length} in-flight chat run(s); waiting for manual resume or reattach`);
        updateActiveRunBanner();
    }

    updateActiveChatBanner();
    updateActiveRunBanner();
    updateChatRoomChrome();
    const roomRun = getActiveRun();
    if (roomRun?.sessionId) showInterruptButton(roomRun.sessionId);
    else hideInterruptButton(false);
    syncChatInputState();
}

void initializeDashboardChatState();

// Independent, lazily loaded browser terminal windows with shared auth and assets.
(function initializeBrowserTerminal() {
    const STORAGE_KEY = 'hermes_terminal_windows_v2';
    const LEGACY_STORAGE_KEY = 'hermes_terminal_window_v1';
    const SESSION_STORAGE_KEY = 'hermes_terminal_sessions_v1';
    const XTERM_VERSION = '5.3.0';
    const FIT_VERSION = '0.8.0';
    const MIN_WIDTH = 300;
    const MIN_HEIGHT = 210;
    const MIN_WORKSPACE_WIDTH = 320;
    const MARGIN = 8;
    const PERSIST_REFRESH_MS = 30000;

    function terminalTheme(theme = document.documentElement.dataset.theme || 'dark') {
        return theme === 'light'
            ? { background: '#f7f7f4', foreground: '#202124', cursor: '#8a6508', selectionBackground: '#d8c47a66', black: '#202124', brightBlack: '#6b7280' }
            : { background: '#0f111a', foreground: '#d8dee9', cursor: '#ffd700', selectionBackground: '#ffd70044', black: '#0f111a', brightBlack: '#687080' };
    }

    class BrowserTerminalManager {
        constructor() {
            this.hostEl = document.getElementById('terminal-window-host');
            this.templateEl = document.getElementById('terminal-window-template');
            this.launcherEl = document.getElementById('terminal-launcher');
            this.launcherCountEl = document.getElementById('terminal-launcher-count');
            this.launcherStatusEl = document.getElementById('terminal-launcher-status');
            this.dockEl = document.getElementById('terminal-dock');
            this.workspaceEl = document.getElementById('dashboard-workspace');
            this.columnEl = document.getElementById('terminal-column');
            this.columnStackEl = document.getElementById('terminal-column-stack');
            this.columnResizerEl = document.getElementById('terminal-column-resizer');
            this.disabledMessageEl = document.getElementById('terminal-disabled-message');
            this.authEl = document.getElementById('terminal-auth');
            this.authInputEl = document.getElementById('terminal-access-token');
            this.authSubmitEl = document.getElementById('terminal-auth-submit');
            this.authErrorEl = document.getElementById('terminal-auth-error');
            this.controllers = new Map();
            this.usedSlots = new Set();
            this.maxSessions = 4;
            this.detachTtlSeconds = 60;
            this.enabled = false;
            this.authRequired = false;
            this.assetsPromise = null;
            this.authPromise = null;
            this.authResolve = null;
            this.statusPromise = null;
            this.restoreAttempted = false;
            this.serial = 0;
            this.zIndex = 20000;
            this.geometrySlots = this.readGeometrySlots();
            this.columnWidth = this.readColumnWidth();
            this.dockSerial = this.geometrySlots.reduce((maximum, geometry) => Math.max(maximum, Number(geometry?.dockOrder) || 0), 0);
            this.columnResizeState = null;
            this.handleViewportResize = this.handleViewportResize.bind(this);
        }

        initialize() {
            if (!this.hostEl || !this.templateEl || !this.launcherEl) return false;
            this.authSubmitEl?.addEventListener('click', () => void this.authorize());
            this.authInputEl?.addEventListener('keydown', event => {
                event.stopPropagation();
                if (event.key === 'Enter') void this.authorize();
            });
            this.authEl?.addEventListener('keydown', event => event.stopPropagation());
            this.authEl?.addEventListener('keyup', event => event.stopPropagation());
            this.dockEl?.addEventListener('click', event => {
                const item = event.target.closest?.('[data-terminal-key]');
                if (item) this.activateDock(item.dataset.terminalKey);
            });
            this.columnResizerEl?.addEventListener('pointerdown', event => this.startColumnResize(event));
            this.columnResizerEl?.addEventListener('keydown', event => this.handleColumnResizeKey(event));
            window.addEventListener('pointermove', event => this.resizeColumn(event));
            window.addEventListener('pointerup', event => this.endColumnResize(event));
            window.addEventListener('pointercancel', event => this.endColumnResize(event));
            window.addEventListener('resize', this.handleViewportResize);
            window.addEventListener('pagehide', () => this.refreshPersistedSessions());
            window.setInterval?.(() => this.refreshPersistedSessions(), PERSIST_REFRESH_MS);
            this.updateLauncher();
            this.renderDock();
            this.applyColumnWidth(this.columnWidth);
            this.syncTerminalColumn();
            void this.loadStatus();
            return true;
        }

        clampGeometry(value = {}) {
            const maxWidth = Math.max(1, window.innerWidth - (MARGIN * 2));
            const maxHeight = Math.max(1, window.innerHeight - (MARGIN * 2));
            const width = Math.min(maxWidth, Math.max(Math.min(MIN_WIDTH, maxWidth), Number(value.width) || Math.min(680, maxWidth)));
            const height = Math.min(maxHeight, Math.max(Math.min(MIN_HEIGHT, maxHeight), Number(value.height) || Math.min(400, maxHeight)));
            return {
                x: Math.min(window.innerWidth - width - MARGIN, Math.max(MARGIN, Number.isFinite(Number(value.x)) ? Number(value.x) : window.innerWidth - width - 20)),
                y: Math.min(window.innerHeight - height - MARGIN, Math.max(MARGIN, Number.isFinite(Number(value.y)) ? Number(value.y) : window.innerHeight - height - 20)),
                width,
                height,
                minimized: Boolean(value.minimized),
                docked: Boolean(value.docked),
                dockOrder: Number.isFinite(Number(value.dockOrder)) && Number(value.dockOrder) > 0 ? Number(value.dockOrder) : null,
            };
        }

        readGeometrySlots() {
            let slots = [];
            try {
                const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
                if (Array.isArray(stored.slots)) slots = stored.slots;
                if (!slots.length) {
                    const legacyRaw = localStorage.getItem(LEGACY_STORAGE_KEY);
                    if (legacyRaw) {
                        const legacy = JSON.parse(legacyRaw);
                        if (legacy && typeof legacy === 'object') slots = [legacy];
                        localStorage.setItem(STORAGE_KEY, JSON.stringify({ slots }));
                        localStorage.removeItem(LEGACY_STORAGE_KEY);
                    }
                }
            } catch (error) {
                console.warn('Failed to read terminal geometry:', error);
            }
            return slots.slice(0, 32).map(value => value && typeof value === 'object' ? this.clampGeometry(value) : null);
        }

        readColumnWidth() {
            try {
                const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
                return this.normalizeColumnWidth(stored.columnWidth);
            } catch (error) {
                return 480;
            }
        }

        persistLayout() {
            try {
                localStorage.setItem(STORAGE_KEY, JSON.stringify({
                    slots: this.geometrySlots,
                    columnWidth: this.columnWidth,
                }));
            } catch (error) {
                console.warn('Failed to persist terminal layout:', error);
            }
        }

        persistGeometry(slot, geometry) {
            if (slot < 0 || slot >= this.maxSessions) return;
            this.geometrySlots[slot] = this.clampGeometry(geometry);
            this.geometrySlots = this.geometrySlots.slice(0, this.maxSessions);
            this.persistLayout();
        }

        clampColumnWidth(value) {
            const maximum = Math.max(320, window.innerWidth - MIN_WORKSPACE_WIDTH);
            return Math.min(maximum, this.normalizeColumnWidth(value));
        }

        normalizeColumnWidth(value) {
            return Math.max(320, Number(value) || 480);
        }

        applyColumnWidth(value, persist = false) {
            this.columnWidth = this.normalizeColumnWidth(value);
            const renderedWidth = this.clampColumnWidth(this.columnWidth);
            if (this.columnEl) {
                this.columnEl.style.width = `${renderedWidth}px`;
                this.columnEl.style.flexBasis = `${renderedWidth}px`;
            }
            if (this.columnResizerEl) {
                this.columnResizerEl.setAttribute('aria-valuenow', String(renderedWidth));
                this.columnResizerEl.setAttribute('aria-valuemax', String(Math.max(320, window.innerWidth - MIN_WORKSPACE_WIDTH)));
            }
            if (persist) this.persistLayout();
        }

        startColumnResize(event) {
            if (event.button !== 0) return;
            this.columnResizeState = { pointerId: event.pointerId, startX: event.clientX, width: this.clampColumnWidth(this.columnWidth) };
            this.columnEl?.classList.add('is-resizing');
            this.columnResizerEl?.setPointerCapture?.(event.pointerId);
            event.preventDefault?.();
        }

        resizeColumn(event) {
            if (!this.columnResizeState || this.columnResizeState.pointerId !== event.pointerId) return;
            this.applyColumnWidth(this.columnResizeState.width + this.columnResizeState.startX - event.clientX);
            this.controllers.forEach(controller => { if (controller.docked) controller.fit(); });
        }

        endColumnResize(event) {
            if (!this.columnResizeState || this.columnResizeState.pointerId !== event.pointerId) return;
            this.columnResizeState = null;
            this.columnEl?.classList.remove('is-resizing');
            if (this.columnResizerEl?.hasPointerCapture?.(event.pointerId)) this.columnResizerEl.releasePointerCapture(event.pointerId);
            this.persistLayout();
        }

        handleColumnResizeKey(event) {
            let width = this.columnWidth;
            if (event.key === 'ArrowLeft') width += 20;
            else if (event.key === 'ArrowRight') width -= 20;
            else if (event.key === 'Home') width = 320;
            else if (event.key === 'End') width = window.innerWidth - MIN_WORKSPACE_WIDTH;
            else return;
            event.preventDefault();
            this.applyColumnWidth(width, true);
            this.controllers.forEach(controller => { if (controller.docked) controller.fit(); });
        }

        syncTerminalColumn() {
            const docked = [...this.controllers.values()].filter(controller => controller.docked);
            if (this.columnEl) this.columnEl.hidden = docked.length === 0;
            this.workspaceEl?.classList.toggle('has-terminal-column', docked.length > 0);
            if (docked.length) {
                this.applyColumnWidth(this.columnWidth);
                requestAnimationFrame(() => docked.forEach(controller => controller.fit()));
            }
        }

        claimGeometrySlot(preferredSlot = null) {
            let slot = Number.isInteger(preferredSlot) && preferredSlot >= 0 && preferredSlot < this.maxSessions && !this.usedSlots.has(preferredSlot)
                ? preferredSlot
                : 0;
            while (this.usedSlots.has(slot) && slot < this.maxSessions) slot += 1;
            this.usedSlots.add(slot);
            const offset = 28 * slot;
            const saved = this.geometrySlots[slot];
            return {
                slot,
                geometry: this.clampGeometry(saved || {
                    width: 680,
                    height: 400,
                    x: window.innerWidth - 700 - offset,
                    y: window.innerHeight - 420 - offset,
                }),
            };
        }

        releaseGeometrySlot(slot) {
            this.usedSlots.delete(slot);
        }

        readSessionRecords() {
            try {
                const stored = JSON.parse(localStorage.getItem(SESSION_STORAGE_KEY) || '{}');
                if (!Array.isArray(stored.sessions)) return [];
                const cutoff = Date.now() - (this.detachTtlSeconds * 1000) - (PERSIST_REFRESH_MS * 2);
                const seen = new Set();
                return stored.sessions.filter(record => {
                    if (!record || typeof record !== 'object') return false;
                    if (typeof record.terminalId !== 'string' || !record.terminalId || record.terminalId.length > 256) return false;
                    if (typeof record.resumeToken !== 'string' || !record.resumeToken || record.resumeToken.length > 512) return false;
                    if (!Number.isInteger(record.slot) || record.slot < 0 || record.slot >= 32) return false;
                    if (!Number.isInteger(record.number) || record.number < 1 || record.number > 9999) return false;
                    if (!Number.isFinite(record.updatedAt) || record.updatedAt < cutoff || seen.has(record.terminalId)) return false;
                    seen.add(record.terminalId);
                    return true;
                }).slice(0, Math.min(32, this.maxSessions));
            } catch (error) {
                console.warn('Failed to read saved terminal sessions:', error);
                return [];
            }
        }

        writeSessionRecords(records) {
            try {
                localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify({ sessions: records.slice(0, Math.min(32, this.maxSessions)) }));
            } catch (error) {
                console.warn('Failed to persist terminal sessions:', error);
            }
        }

        persistSession(controller) {
            if (!controller.terminalId || !controller.resumeToken || controller.disposed || controller.waitingElsewhere) return;
            const records = this.readSessionRecords().filter(record => record.terminalId !== controller.terminalId);
            records.unshift({
                terminalId: controller.terminalId,
                resumeToken: controller.resumeToken,
                slot: controller.slot,
                number: controller.number,
                updatedAt: Date.now(),
            });
            this.writeSessionRecords(records);
        }

        forgetSession(terminalId) {
            if (!terminalId) return;
            this.writeSessionRecords(this.readSessionRecords().filter(record => record.terminalId !== terminalId));
        }

        refreshPersistedSessions() {
            this.controllers.forEach(controller => this.persistSession(controller));
        }

        restoreSessions() {
            if (this.restoreAttempted || !this.enabled) return;
            this.restoreAttempted = true;
            const records = this.readSessionRecords().sort((left, right) => {
                const leftOrder = this.geometrySlots[left.slot]?.docked ? this.geometrySlots[left.slot].dockOrder || Number.MAX_SAFE_INTEGER : Number.MAX_SAFE_INTEGER;
                const rightOrder = this.geometrySlots[right.slot]?.docked ? this.geometrySlots[right.slot].dockOrder || Number.MAX_SAFE_INTEGER : Number.MAX_SAFE_INTEGER;
                return leftOrder - rightOrder;
            });
            this.writeSessionRecords(records);
            records.forEach(record => this.open(record));
        }

        topmostVisibleController() {
            return [...this.controllers.values()]
                .filter(controller => !controller.docked && !controller.windowEl.classList.contains('is-minimized'))
                .sort((left, right) => right.zIndex - left.zIndex)[0] || null;
        }

        renderDock() {
            if (!this.dockEl) return;
            const active = this.topmostVisibleController();
            this.dockEl.hidden = this.controllers.size === 0;
            this.dockEl.innerHTML = [...this.controllers.values()].map(controller => {
                const minimized = controller.windowEl.classList.contains('is-minimized');
                const docked = controller.docked;
                const activeClass = active === controller ? ' is-active' : '';
                const minimizedClass = minimized ? ' is-minimized' : '';
                const dockedClass = docked ? ' is-docked' : '';
                const state = ['connected', 'connecting', 'error'].includes(controller.connectionState) ? controller.connectionState : '';
                const action = docked ? 'focus docked terminal' : minimized ? 'restore' : active === controller ? 'minimize' : 'bring forward';
                const statusLabel = docked ? 'Docked right' : minimized ? 'Minimized' : state === 'connected' ? 'Connected' : state === 'connecting' ? 'Connecting' : state === 'error' ? 'Needs attention' : 'Disconnected';
                return `<button class="terminal-dock-item${activeClass}${minimizedClass}${dockedClass}${state ? ` is-${state}` : ''}" type="button" data-terminal-key="${controller.key}" title="Terminal ${controller.number}: ${action}" aria-label="Terminal ${controller.number}, ${state || 'disconnected'}, ${action}"><span class="terminal-dock-glyph" aria-hidden="true">&gt;_${controller.number}<span class="terminal-dock-status"></span></span><span class="terminal-dock-copy"><strong>Terminal ${controller.number}</strong><small>${statusLabel}</small></span></button>`;
            }).join('');
        }

        activateDock(key) {
            const controller = this.controllers.get(key);
            if (!controller) return;
            if (controller.docked) {
                if (controller.waitingElsewhere) {
                    controller.waitingElsewhere = false;
                    controller.connect();
                }
                this.syncTerminalColumn();
                controller.windowEl.scrollIntoView?.({ block: 'nearest' });
                controller.fit();
                controller.terminal?.focus();
                return;
            }
            if (controller.waitingElsewhere) {
                controller.waitingElsewhere = false;
                controller.connect();
                if (controller.windowEl.classList.contains('is-minimized')) controller.toggleMinimize();
                controller.raise();
                return;
            }
            if (controller.windowEl.classList.contains('is-minimized')) {
                controller.toggleMinimize();
                controller.raise();
                return;
            }
            if (this.topmostVisibleController() === controller) {
                controller.toggleMinimize();
                return;
            }
            controller.raise();
            controller.terminal?.focus();
        }

        updateLauncher(announcement = '') {
            const count = this.controllers.size;
            this.launcherEl?.classList.toggle('active', count > 0);
            if (this.launcherCountEl) this.launcherCountEl.textContent = String(count);
            if (this.launcherEl) {
                const suffix = this.enabled ? `${count} open, maximum ${this.maxSessions}` : 'unavailable';
                this.launcherEl.setAttribute('aria-label', `New terminal, ${suffix}`);
                this.launcherEl.title = count >= this.maxSessions ? `Terminal limit reached (${this.maxSessions})` : `New terminal (${count}/${this.maxSessions} open)`;
            }
            if (announcement && this.launcherStatusEl) this.launcherStatusEl.textContent = announcement;
        }

        announceLimit() {
            const topmost = this.topmostVisibleController() || this.controllers.values().next().value;
            topmost?.raise();
            topmost?.setStatus(`Limit reached (${this.maxSessions} terminals)`, 'error');
            const message = `Terminal limit reached. ${this.controllers.size} of ${this.maxSessions} terminals are open.`;
            this.updateLauncher(message);
            this.launcherEl.classList.remove('at-limit');
            requestAnimationFrame(() => this.launcherEl.classList.add('at-limit'));
            window.setTimeout(() => this.launcherEl?.classList.remove('at-limit'), 900);
        }

        open(savedSession = null) {
            if (!this.enabled) return null;
            if (this.controllers.size >= this.maxSessions) {
                this.announceLimit();
                return null;
            }
            let number = Number.isInteger(savedSession?.number) ? savedSession.number : this.serial + 1;
            while (this.controllers.has(`terminal-${number}`)) number += 1;
            this.serial = Math.max(this.serial, number);
            const { slot, geometry } = this.claimGeometrySlot(savedSession?.slot);
            const controller = new TerminalWindowController(this, number, slot, geometry, savedSession);
            this.controllers.set(controller.key, controller);
            this.hostEl.appendChild(controller.windowEl);
            if (geometry.docked) controller.setDocked(true, false);
            else controller.raise();
            this.updateLauncher(`Terminal ${number} opened. ${this.controllers.size} open.`);
            this.renderDock();
            void controller.start();
            return controller;
        }

        remove(controller) {
            if (!this.controllers.delete(controller.key)) return;
            this.releaseGeometrySlot(controller.slot);
            this.updateLauncher(`Terminal ${controller.number} closed. ${this.controllers.size} open.`);
            this.renderDock();
            this.syncTerminalColumn();
        }

        raise(controller) {
            if (controller.docked) {
                this.renderDock();
                return;
            }
            controller.zIndex = ++this.zIndex;
            controller.windowEl.style.zIndex = String(controller.zIndex);
            this.renderDock();
        }

        handleViewportResize() {
            this.applyColumnWidth(this.columnWidth);
            this.controllers.forEach(controller => controller.handleViewportResize());
        }

        applyTheme(theme) {
            this.controllers.forEach(controller => controller.applyTheme(theme));
        }

        loadScript(id, src) {
            const existing = document.getElementById(id);
            if (existing) {
                if (existing.dataset.loaded === 'true') return Promise.resolve();
                return new Promise((resolve, reject) => {
                    existing.addEventListener('load', resolve, { once: true });
                    existing.addEventListener('error', reject, { once: true });
                });
            }
            return new Promise((resolve, reject) => {
                const script = document.createElement('script');
                script.id = id;
                script.src = src;
                script.onload = () => { script.dataset.loaded = 'true'; resolve(); };
                script.onerror = () => {
                    script.remove();
                    reject(new Error(`Could not load ${src}`));
                };
                document.head.appendChild(script);
            });
        }

        loadAssets() {
            if (window.Terminal && window.FitAddon?.FitAddon) return Promise.resolve();
            if (this.assetsPromise) return this.assetsPromise;
            if (!document.getElementById('xterm-css')) {
                const link = document.createElement('link');
                link.id = 'xterm-css';
                link.rel = 'stylesheet';
                link.href = `/static/vendor/xterm/xterm.css?v=${XTERM_VERSION}`;
                document.head.appendChild(link);
            }
            this.assetsPromise = this.loadScript('xterm-js', `/static/vendor/xterm/xterm.js?v=${XTERM_VERSION}`)
                .then(() => this.loadScript('xterm-fit-js', `/static/vendor/xterm/xterm-addon-fit.js?v=${FIT_VERSION}`))
                .catch(error => { this.assetsPromise = null; throw error; });
            return this.assetsPromise;
        }

        requestAuthorization(controller) {
            if (!this.authRequired) return Promise.resolve();
            controller?.setStatus('Authorization required', 'connecting');
            if (this.authPromise) return this.authPromise;
            this.authErrorEl.textContent = '';
            this.authEl.hidden = false;
            this.authPromise = new Promise(resolve => { this.authResolve = resolve; });
            requestAnimationFrame(() => this.authInputEl?.focus());
            return this.authPromise;
        }

        async authorize() {
            const token = this.authInputEl.value;
            if (!token) {
                this.authErrorEl.textContent = 'Access token required.';
                this.authInputEl.focus();
                return;
            }
            this.authSubmitEl.disabled = true;
            this.authErrorEl.textContent = '';
            try {
                const response = await fetch('/api/terminal/auth', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ token }),
                });
                const data = await response.json().catch(() => ({}));
                if (!response.ok || data.ok === false) throw new Error(data.error || data.message || 'Terminal authorization failed');
                this.authRequired = false;
                this.authEl.hidden = true;
                const resolve = this.authResolve;
                this.authPromise = null;
                this.authResolve = null;
                resolve?.();
            } catch (error) {
                this.authErrorEl.textContent = error.message || 'Authorization failed';
                this.authInputEl.focus();
            } finally {
                this.authInputEl.value = '';
                this.authSubmitEl.disabled = false;
            }
        }

        async handleAuthRequired(controller) {
            controller.setStatus('Checking authorization...', 'connecting');
            await this.loadStatus(true);
            if (controller.disposed || !this.enabled) return;
            if (!this.authRequired) {
                controller.setStatus('Terminal access denied', 'error');
                return;
            }
            await this.requestAuthorization(controller);
            if (!controller.disposed) controller.connect();
        }

        loadStatus(silent = false) {
            if (this.statusPromise) return this.statusPromise;
            this.statusPromise = (async () => {
                try {
                    const response = await fetch('/api/terminal/status', { headers: { Accept: 'application/json' } });
                    const data = await response.json().catch(() => ({}));
                    if (!response.ok) throw new Error(data.error || data.message || `Terminal status unavailable (${response.status})`);
                    this.enabled = data.enabled !== false && data.available !== false && data.access_allowed !== false;
                    this.authRequired = Boolean(data.remote_auth_required ?? data.auth_required ?? data.requires_auth);
                    this.maxSessions = Math.max(1, Math.min(32, Number(data.max_sessions) || 4));
                    this.detachTtlSeconds = Math.max(1, Math.min(86400, Number(data.detach_ttl_seconds) || 60));
                    this.geometrySlots = this.geometrySlots.slice(0, this.maxSessions);
                    this.launcherEl.hidden = !this.enabled;
                    this.disabledMessageEl.hidden = this.enabled || !data.running_in_docker;
                    if (!this.enabled) {
                        this.disabledMessageEl.textContent = data.access_reason || data.explanation || data.reason || data.message || 'Terminal unavailable';
                    }
                    this.updateLauncher();
                    this.restoreSessions();
                    return data;
                } catch (error) {
                    this.enabled = false;
                    this.launcherEl.hidden = true;
                    this.disabledMessageEl.hidden = false;
                    this.disabledMessageEl.textContent = silent ? 'Terminal authorization unavailable' : 'Terminal unavailable';
                    this.updateLauncher();
                    return null;
                } finally {
                    this.statusPromise = null;
                }
            })();
            return this.statusPromise;
        }
    }

    class TerminalWindowController {
        constructor(manager, number, slot, geometry, savedSession = null) {
            this.manager = manager;
            this.number = number;
            this.key = `terminal-${number}`;
            this.slot = slot;
            this.geometry = geometry;
            this.windowEl = manager.templateEl.content.firstElementChild.cloneNode(true);
            this.headerEl = this.role('header');
            this.bodyEl = this.role('body');
            this.screenEl = this.role('screen');
            this.titleEl = this.role('title');
            this.statusEl = this.role('status');
            this.dockButtonEl = this.role('dock');
            this.minimizeEl = this.role('minimize');
            this.maximizeEl = this.role('maximize');
            this.closeEl = this.role('close');
            this.terminal = null;
            this.fitAddon = null;
            this.socket = null;
            this.terminalId = savedSession?.terminalId || null;
            this.resumeToken = savedSession?.resumeToken || null;
            this.reconnectTimer = null;
            this.reconnectAttempt = 0;
            this.retryFreshAfterMissing = false;
            this.restoring = Boolean(this.terminalId && this.resumeToken);
            this.waitingElsewhere = false;
            this.suppressReconnect = false;
            this.docked = false;
            this.maximized = false;
            this.restoreGeometry = null;
            this.lastResize = '';
            this.dragState = null;
            this.disposed = false;
            this.zIndex = 0;
            this.connectionState = 'connecting';
            this.configureAccessibility();
            this.applyGeometry(geometry);
            this.bindEvents();
            this.resizeObserver = new ResizeObserver(() => {
                if (!this.docked && !this.maximized && !this.disposed) this.persistGeometry();
                this.fit();
            });
            this.resizeObserver.observe(this.windowEl);
        }

        role(name) {
            return this.windowEl.querySelector(`[data-terminal-role="${name}"]`);
        }

        configureAccessibility() {
            const windowId = `terminal-window-${this.number}`;
            const titleId = `${windowId}-title`;
            const statusId = `${windowId}-status`;
            const screenId = `${windowId}-screen`;
            this.windowEl.id = windowId;
            this.titleEl.id = titleId;
            this.statusEl.id = statusId;
            this.screenEl.id = screenId;
            this.titleEl.textContent = `Terminal ${this.number}`;
            this.windowEl.setAttribute('aria-labelledby', titleId);
            this.windowEl.setAttribute('aria-describedby', statusId);
            this.screenEl.setAttribute('aria-label', `Interactive terminal ${this.number}`);
            this.updateDockButton();
            this.minimizeEl.setAttribute('aria-label', `Minimize terminal ${this.number}`);
            this.maximizeEl.setAttribute('aria-label', `Maximize terminal ${this.number}`);
            this.closeEl.setAttribute('aria-label', `Terminate terminal ${this.number}`);
        }

        bindEvents() {
            this.windowEl.addEventListener('pointerdown', () => this.raise());
            for (const eventName of ['keydown', 'keyup', 'keypress']) {
                this.windowEl.addEventListener(eventName, event => event.stopPropagation());
            }
            this.dockButtonEl.addEventListener('click', () => this.toggleDocked());
            this.minimizeEl.addEventListener('click', () => this.toggleMinimize());
            this.maximizeEl.addEventListener('click', () => this.toggleMaximize());
            this.closeEl.addEventListener('click', () => this.close());
            this.headerEl.addEventListener('pointerdown', event => this.startDrag(event));
            this.headerEl.addEventListener('pointermove', event => this.drag(event));
            this.headerEl.addEventListener('pointerup', event => this.endDrag(event));
            this.headerEl.addEventListener('pointercancel', event => this.endDrag(event));
        }

        setStatus(message, state = '') {
            this.statusEl.textContent = message;
            this.statusEl.className = `terminal-connection-status ${state}`.trim();
            this.connectionState = state;
            this.manager.renderDock();
        }

        async start() {
            try {
                if (this.manager.authRequired) await this.manager.requestAuthorization(this);
                if (this.disposed) return;
                this.setStatus('Loading terminal...', 'connecting');
                await this.manager.loadAssets();
                if (this.disposed) return;
                this.terminal = new window.Terminal({
                    allowProposedApi: false,
                    convertEol: false,
                    cursorBlink: true,
                    fontFamily: "'SFMono-Regular', Consolas, 'Liberation Mono', monospace",
                    fontSize: 13,
                    scrollback: 5000,
                    theme: terminalTheme(),
                });
                this.fitAddon = new window.FitAddon.FitAddon();
                this.terminal.loadAddon(this.fitAddon);
                this.terminal.open(this.screenEl);
                this.terminal.attachCustomKeyEventHandler(event => this.handleClipboardKey(event));
                this.terminal.onData(data => this.sendControl({ type: 'input', data }));
                this.connect();
                requestAnimationFrame(() => { this.fit(); this.terminal?.focus(); });
            } catch (error) {
                if (!this.disposed) this.setStatus(error.message || 'Terminal failed to load', 'error');
            }
        }

        applyTheme(theme) {
            if (this.terminal) this.terminal.options.theme = terminalTheme(theme);
        }

        handleClipboardKey(event) {
            if (event.type !== 'keydown' || !(event.ctrlKey || event.metaKey)) return true;
            const key = String(event.key || '').toLowerCase();
            if (key === 'c' && (event.shiftKey || event.metaKey || this.terminal?.hasSelection?.())) {
                const selection = this.terminal?.getSelection?.() || '';
                if (!selection || !navigator.clipboard?.writeText) return true;
                void navigator.clipboard.writeText(selection).catch(() => showToast('Could not copy terminal selection'));
                return false;
            }
            if (key === 'v') {
                if (!navigator.clipboard?.readText) return true;
                void navigator.clipboard.readText()
                    .then(text => { if (text && !this.disposed) this.terminal?.paste(text); })
                    .catch(() => showToast('Could not read clipboard'));
                return false;
            }
            return true;
        }

        websocketUrl() {
            const url = new URL('/api/terminal/ws', window.location.href);
            url.protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            if (this.terminalId) url.searchParams.set('terminal_id', this.terminalId);
            if (this.resumeToken) url.searchParams.set('resume_token', this.resumeToken);
            return url.toString();
        }

        connect() {
            if (this.disposed || (this.socket && (this.socket.readyState === WebSocket.OPEN || this.socket.readyState === WebSocket.CONNECTING))) return;
            this.suppressReconnect = false;
            this.setStatus(this.terminalId && this.resumeToken ? 'Resuming...' : 'Connecting...', 'connecting');
            try {
                const candidate = new WebSocket(this.websocketUrl());
                this.socket = candidate;
                candidate.binaryType = 'arraybuffer';
                candidate.addEventListener('open', () => {
                    if (this.socket !== candidate || this.disposed) return;
                    this.reconnectAttempt = 0;
                    this.setStatus('Connected', 'connected');
                    this.lastResize = '';
                    this.fit();
                });
                candidate.addEventListener('message', event => {
                    if (this.socket === candidate && !this.disposed) this.writeServerMessage(event.data);
                });
                candidate.addEventListener('error', () => {
                    if (this.socket === candidate && !this.disposed) this.setStatus('Connection error', 'error');
                });
                candidate.addEventListener('close', event => this.handleSocketClose(candidate, event));
            } catch (error) {
                this.setStatus(error.message || 'Connection failed', 'error');
                this.scheduleReconnect();
            }
        }

        handleSocketClose(candidate, event) {
            if (this.socket !== candidate || this.disposed) return;
            this.socket = null;
            if (this.suppressReconnect) return;
            if (event.code === 4429) {
                this.setStatus(event.reason || `Server limit reached (${this.manager.maxSessions})`, 'error');
                this.manager.updateLauncher('The server terminal session limit was reached.');
                return;
            }
            if (event.code === 4404) {
                this.expireSavedSession(event.reason || 'Terminal expired or dashboard restarted');
                return;
            }
            if (event.code === 4403) {
                if (/resume token/i.test(event.reason || '')) {
                    this.expireSavedSession(event.reason || 'Saved terminal recovery capability is invalid');
                    return;
                }
                this.setStatus(event.reason || 'Authorization required', 'error');
                void this.manager.handleAuthRequired(this);
                return;
            }
            if (event.code === 4409) {
                this.waitingElsewhere = true;
                this.setStatus('Open in another dashboard window; click dock to retry', 'error');
                return;
            }
            this.scheduleReconnect();
        }

        expireSavedSession(errorMessage) {
            this.manager.forgetSession(this.terminalId);
            this.terminalId = null;
            this.resumeToken = null;
            this.restoring = false;
            this.suppressReconnect = true;
            this.setStatus(errorMessage, 'error');
        }

        scheduleReconnect() {
            if (this.disposed || this.suppressReconnect || this.reconnectTimer) return;
            const delay = Math.min(10000, 500 * (2 ** this.reconnectAttempt));
            this.reconnectAttempt += 1;
            this.setStatus(`Reconnecting in ${Math.ceil(delay / 1000)}s`, 'connecting');
            this.reconnectTimer = window.setTimeout(() => {
                this.reconnectTimer = null;
                this.connect();
            }, delay);
        }

        rememberServerCredentials(data) {
            this.terminalId = data.terminal_id || data.terminalId || data.id || this.terminalId;
            this.resumeToken = data.resume_token || data.resumeToken || data.token || this.resumeToken;
        }

        writeServerMessage(data) {
            if (!this.terminal) return;
            if (data instanceof ArrayBuffer) {
                this.terminal.write(new Uint8Array(data));
                return;
            }
            if (typeof Blob !== 'undefined' && data instanceof Blob) {
                const owner = this.terminal;
                data.arrayBuffer().then(buffer => {
                    if (!this.disposed && this.terminal === owner) owner.write(new Uint8Array(buffer));
                });
                return;
            }
            let message;
            try {
                message = JSON.parse(data);
            } catch (error) {
                this.terminal.write(String(data));
                return;
            }
            this.rememberServerCredentials(message);
            if (message.type === 'ready' || message.type === 'connected' || message.type === 'session') {
                this.reconnectAttempt = 0;
                this.retryFreshAfterMissing = false;
                this.restoring = false;
                this.waitingElsewhere = false;
                this.manager.persistSession(this);
                this.setStatus('Connected', 'connected');
            } else if (message.type === 'output' && typeof message.data === 'string') {
                this.terminal.write(message.encoding === 'base64' ? Uint8Array.from(atob(message.data), char => char.charCodeAt(0)) : message.data);
            } else if (message.type === 'error') {
                this.setStatus(message.message || message.error || 'Terminal error', 'error');
            } else if (message.type === 'exit' || message.type === 'closed') {
                this.suppressReconnect = true;
                this.manager.forgetSession(this.terminalId);
                this.setStatus(`Exited${message.code === undefined ? '' : ` (${message.code})`}`, 'error');
            }
        }

        sendControl(payload) {
            if (this.socket?.readyState !== WebSocket.OPEN) return false;
            this.socket.send(JSON.stringify(payload));
            return true;
        }

        fit() {
            if (!this.terminal || !this.fitAddon || this.disposed || this.windowEl.classList.contains('is-minimized')) return;
            try {
                this.fitAddon.fit();
                const dimensions = `${this.terminal.cols}x${this.terminal.rows}`;
                if (dimensions !== this.lastResize && this.terminal.cols > 0 && this.terminal.rows > 0) {
                    if (this.sendControl({ type: 'resize', cols: this.terminal.cols, rows: this.terminal.rows })) {
                        this.lastResize = dimensions;
                    }
                }
            } catch (error) {
                console.warn('Terminal fit failed:', error);
            }
        }

        currentGeometry() {
            const rect = this.windowEl.getBoundingClientRect();
            return this.manager.clampGeometry({
                x: rect.left,
                y: rect.top,
                width: rect.width,
                height: this.windowEl.classList.contains('is-minimized') ? (this.restoreGeometry?.height || this.geometry.height) : rect.height,
                minimized: this.windowEl.classList.contains('is-minimized'),
                docked: false,
            });
        }

        persistGeometry() {
            if (this.maximized || this.disposed) return;
            this.geometry = this.docked
                ? this.manager.clampGeometry({ ...this.geometry, minimized: false, docked: true })
                : this.currentGeometry();
            this.manager.persistGeometry(this.slot, this.geometry);
        }

        applyGeometry(value) {
            this.geometry = this.manager.clampGeometry(value);
            if (this.geometry.minimized) this.restoreGeometry = { ...this.geometry, minimized: false };
            this.windowEl.style.left = `${this.geometry.x}px`;
            this.windowEl.style.top = `${this.geometry.y}px`;
            this.windowEl.style.width = `${this.geometry.width}px`;
            this.windowEl.style.height = `${this.geometry.height}px`;
            this.setMinimized(this.geometry.minimized, false);
        }

        updateDockButton() {
            if (!this.dockButtonEl) return;
            const label = this.docked ? `Pop terminal ${this.number} out` : `Dock terminal ${this.number} to the right`;
            this.dockButtonEl.title = this.docked ? 'Pop terminal out' : 'Dock terminal to the right';
            this.dockButtonEl.setAttribute('aria-label', label);
            this.dockButtonEl.setAttribute('aria-pressed', String(this.docked));
        }

        setDocked(docked, persist = true) {
            if (this.docked === docked) return;
            if (docked) {
                if (this.maximized) this.toggleMaximize();
                if (this.windowEl.classList.contains('is-minimized')) this.setMinimized(false);
                if (persist) this.persistGeometry();
                this.docked = true;
                this.geometry = this.manager.clampGeometry({
                    ...this.geometry,
                    minimized: false,
                    docked: true,
                    dockOrder: this.geometry.dockOrder || ++this.manager.dockSerial,
                });
                this.windowEl.classList.add('is-docked');
                this.manager.columnStackEl?.appendChild(this.windowEl);
                this.updateDockButton();
                if (persist) this.manager.persistGeometry(this.slot, this.geometry);
                this.manager.syncTerminalColumn();
                this.manager.renderDock();
                requestAnimationFrame(() => { this.fit(); this.terminal?.focus(); });
                return;
            }

            this.docked = false;
            this.geometry = this.manager.clampGeometry({ ...this.geometry, minimized: false, docked: false, dockOrder: null });
            this.windowEl.classList.remove('is-docked');
            this.manager.hostEl.appendChild(this.windowEl);
            this.updateDockButton();
            this.applyGeometry(this.geometry);
            if (persist) this.manager.persistGeometry(this.slot, this.geometry);
            this.manager.syncTerminalColumn();
            this.raise();
            requestAnimationFrame(() => { this.fit(); this.terminal?.focus(); });
        }

        toggleDocked() {
            this.setDocked(!this.docked);
        }

        setMinimized(minimized, persist = true) {
            this.windowEl.classList.toggle('is-minimized', minimized);
            this.bodyEl.hidden = minimized;
            this.bodyEl.inert = minimized;
            this.bodyEl.setAttribute('aria-hidden', String(minimized));
            this.minimizeEl.setAttribute('aria-label', `${minimized ? 'Restore' : 'Minimize'} terminal ${this.number}`);
            this.minimizeEl.title = minimized ? 'Restore terminal' : 'Minimize terminal';
            this.minimizeEl.innerHTML = minimized ? '&#9633;' : '&#8722;';
            if (persist && minimized && this.restoreGeometry) {
                this.geometry = this.manager.clampGeometry({ ...this.restoreGeometry, minimized: true });
                this.manager.persistGeometry(this.slot, this.geometry);
            } else if (persist) {
                this.persistGeometry();
            }
            this.manager.renderDock();
        }

        toggleMinimize() {
            if (this.docked) return;
            if (this.maximized) this.toggleMaximize();
            const minimized = !this.windowEl.classList.contains('is-minimized');
            if (minimized) this.restoreGeometry = this.currentGeometry();
            this.setMinimized(minimized);
            if (!minimized) requestAnimationFrame(() => { this.fit(); this.terminal?.focus(); });
        }

        toggleMaximize() {
            if (this.docked) return;
            if (!this.maximized) {
                if (this.windowEl.classList.contains('is-minimized')) this.setMinimized(false);
                this.restoreGeometry = this.currentGeometry();
                this.maximized = true;
                this.windowEl.classList.add('is-maximized');
                this.maximizeEl.setAttribute('aria-label', `Restore terminal ${this.number}`);
                this.maximizeEl.title = 'Restore terminal window';
            } else {
                this.maximized = false;
                this.windowEl.classList.remove('is-maximized');
                this.applyGeometry(this.restoreGeometry || this.geometry);
                this.maximizeEl.setAttribute('aria-label', `Maximize terminal ${this.number}`);
                this.maximizeEl.title = 'Maximize terminal';
            }
            requestAnimationFrame(() => { this.fit(); this.terminal?.focus(); });
        }

        handleViewportResize() {
            if (this.docked) {
                this.fit();
                return;
            }
            if (!this.maximized) {
                this.applyGeometry(this.windowEl.classList.contains('is-minimized') ? this.geometry : this.currentGeometry());
            }
            this.fit();
        }

        startDrag(event) {
            if (event.button !== 0 || event.target.closest('button') || this.maximized || this.docked) return;
            const rect = this.windowEl.getBoundingClientRect();
            this.dragState = { pointerId: event.pointerId, startX: event.clientX, startY: event.clientY, x: rect.left, y: rect.top };
            this.headerEl.setPointerCapture(event.pointerId);
            this.raise();
            event.preventDefault();
        }

        drag(event) {
            if (!this.dragState || this.dragState.pointerId !== event.pointerId) return;
            const rect = this.windowEl.getBoundingClientRect();
            const next = this.manager.clampGeometry({
                x: this.dragState.x + event.clientX - this.dragState.startX,
                y: this.dragState.y + event.clientY - this.dragState.startY,
                width: rect.width,
                height: rect.height,
                minimized: this.windowEl.classList.contains('is-minimized'),
            });
            this.windowEl.style.left = `${next.x}px`;
            this.windowEl.style.top = `${next.y}px`;
        }

        endDrag(event) {
            if (!this.dragState || this.dragState.pointerId !== event.pointerId) return;
            this.dragState = null;
            if (this.headerEl.hasPointerCapture?.(event.pointerId)) this.headerEl.releasePointerCapture(event.pointerId);
            this.persistGeometry();
        }

        raise() {
            this.manager.raise(this);
        }

        close() {
            if (this.disposed) return;
            this.persistGeometry();
            this.manager.forgetSession(this.terminalId);
            this.disposed = true;
            this.suppressReconnect = true;
            window.clearTimeout(this.reconnectTimer);
            this.reconnectTimer = null;
            this.resizeObserver?.disconnect();
            const closingSocket = this.socket;
            this.socket = null;
            if (closingSocket?.readyState === WebSocket.OPEN) {
                closingSocket.send(JSON.stringify({ type: 'close' }));
                closingSocket.close(1000, 'Terminal closed by user');
            } else if (closingSocket?.readyState === WebSocket.CONNECTING) {
                closingSocket.addEventListener('open', () => {
                    closingSocket.send(JSON.stringify({ type: 'close' }));
                    closingSocket.close(1000, 'Terminal closed by user');
                }, { once: true });
                window.setTimeout(() => {
                    if (closingSocket.readyState === WebSocket.CONNECTING) closingSocket.close();
                }, 3000);
            } else {
                closingSocket?.close(1000, 'Terminal closed by user');
            }
            this.terminal?.dispose();
            this.terminal = null;
            this.fitAddon = null;
            this.terminalId = null;
            this.resumeToken = null;
            this.windowEl.remove();
            this.manager.remove(this);
        }
    }

    window.BrowserTerminalManager = BrowserTerminalManager;
    window.TerminalWindowController = TerminalWindowController;
    const manager = new BrowserTerminalManager();
    if (!manager.initialize()) return;
    window.openTerminalWindow = () => manager.open();
    window.hermesTerminalManager = manager;
    window.hermesTerminalController = manager;
})();

userInput.focus();

// Initialize hash routing
applyDndPopoutMode();
applyDashboardTabSettings();
handleHashChange();

// === TRACK E: CommandPalette ===
const CMD_PALETTE_COMMANDS = [
    { id: 'new-chat',       label: 'New Chat',              icon: '\u270F',  action: () => navigateTo('chat') },
    { id: 'view-sessions',  label: 'View All Sessions',     icon: '\u1F4CB', action: () => navigateTo('sessions') },
    { id: 'view-schedule',  label: 'View Cron Schedule',    icon: '\u1F5D3', action: () => navigateTo('cron') },
    { id: 'settings',       label: 'Open Settings',         icon: '\u2699',  action: () => navigateTo('config') },
];

let cmdPaletteActiveIndex = -1;
let cmdPaletteItems = [];

function openCmdPalette() {
    const overlay = document.getElementById('cmd-palette-overlay');
    const input = document.getElementById('cmd-palette-input');
    if (!overlay || !input) return;
    overlay.classList.remove('hidden');
    input.value = '';
    input.focus();
    filterCmdPalette('');
}

function closeCmdPalette() {
    const overlay = document.getElementById('cmd-palette-overlay');
    const input = document.getElementById('cmd-palette-input');
    if (!overlay) return;
    overlay.classList.add('hidden');
    if (input) input.value = '';
    cmdPaletteActiveIndex = -1;
    cmdPaletteItems = [];
}

function getRecentSessions() {
    // Read from apiCache to reuse cached session list data without adding new fetches
    for (const [url, entry] of Object.entries(apiCache)) {
        if (url.startsWith('/api/sessions?') && entry.data && Array.isArray(entry.data.sessions)) {
            return entry.data.sessions.slice(0, 5);
        }
    }
    return [];
}

function filterCmdPalette(query) {
    const q = (query || '').toLowerCase().trim();
    const commands = CMD_PALETTE_COMMANDS.filter(c => c.label.toLowerCase().includes(q));
    const recentSessions = getRecentSessions().filter(s => {
        const label = (s.title || s.id || '').toLowerCase();
        return label.includes(q);
    }).map(s => ({
        id: 'session-' + s.id,
        label: s.title || s.id,
        icon: '\u1F5C2',
        action: () => viewSession(s.id)
    }));
    cmdPaletteItems = [];
    if (commands.length) {
        cmdPaletteItems.push({ type: 'separator', label: 'Actions' });
        cmdPaletteItems.push(...commands);
    }
    if (recentSessions.length) {
        cmdPaletteItems.push({ type: 'separator', label: 'Recent Sessions' });
        cmdPaletteItems.push(...recentSessions);
    }
    cmdPaletteActiveIndex = cmdPaletteItems.length > 0 && cmdPaletteItems[0].type !== 'separator' ? 0 : (cmdPaletteItems.length > 1 ? 1 : -1);
    renderCmdResults(cmdPaletteItems);
}

function renderCmdResults(items) {
    const list = document.getElementById('cmd-palette-results');
    const input = document.getElementById('cmd-palette-input');
    if (!list) return;
    if (!items.length) {
        list.innerHTML = '<li class="cmd-result-empty">No results found</li>';
        if (input) input.removeAttribute('aria-activedescendant');
        return;
    }
    list.innerHTML = items.map((item, idx) => {
        if (item.type === 'separator') {
            return `<li class="cmd-result-separator" role="presentation">${escapeHtml(item.label)}</li>`;
        }
        const activeClass = idx === cmdPaletteActiveIndex ? 'active' : '';
        const itemId = 'cmd-result-' + idx;
        return `<li id="${itemId}" class="cmd-result-item ${activeClass}" role="option" aria-selected="${idx === cmdPaletteActiveIndex ? 'true' : 'false'}" onclick="executeCmdItem(cmdPaletteItems[${idx}])">
            <span class="icon">${item.icon || ''}</span>
            <span class="label">${escapeHtml(item.label)}</span>
            <span class="shortcut">${idx === cmdPaletteActiveIndex ? '\u23CE' : ''}</span>
        </li>`;
    }).join('');
    const activeItem = items[cmdPaletteActiveIndex];
    if (input && activeItem && activeItem.type !== 'separator') {
        input.setAttribute('aria-activedescendant', 'cmd-result-' + cmdPaletteActiveIndex);
    } else if (input) {
        input.removeAttribute('aria-activedescendant');
    }
}

function navigateCmdResults(direction) {
    if (!cmdPaletteItems.length) return;
    let next = cmdPaletteActiveIndex + direction;
    const max = cmdPaletteItems.length - 1;
    // Skip separators
    while (next >= 0 && next <= max && cmdPaletteItems[next].type === 'separator') {
        next += direction;
    }
    if (next < 0) {
        // Wrap to bottom, skip separators
        next = max;
        while (next >= 0 && cmdPaletteItems[next].type === 'separator') next--;
    } else if (next > max) {
        // Wrap to top, skip separators
        next = 0;
        while (next <= max && cmdPaletteItems[next].type === 'separator') next++;
    }
    if (next >= 0 && next <= max && cmdPaletteItems[next].type !== 'separator') {
        cmdPaletteActiveIndex = next;
        renderCmdResults(cmdPaletteItems);
        const el = document.getElementById('cmd-result-' + next);
        if (el) el.scrollIntoView({ block: 'nearest' });
    }
}

function executeCmdItem(item) {
    if (!item || item.type === 'separator') return;
    closeCmdPalette();
    if (typeof item.action === 'function') {
        item.action();
    }
}

// Event listeners
document.addEventListener('keydown', (e) => {
    const overlay = document.getElementById('cmd-palette-overlay');
    const isOpen = overlay && !overlay.classList.contains('hidden');

    // Cmd+K / Ctrl+K
    if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        if (isOpen) closeCmdPalette();
        else openCmdPalette();
        return;
    }

    if (!isOpen) return;

    // Escape
    if (e.key === 'Escape') {
        e.preventDefault();
        closeCmdPalette();
        return;
    }

    // Arrow navigation
    if (e.key === 'ArrowDown') {
        e.preventDefault();
        navigateCmdResults(1);
        return;
    }
    if (e.key === 'ArrowUp') {
        e.preventDefault();
        navigateCmdResults(-1);
        return;
    }

    // Enter
    if (e.key === 'Enter') {
        e.preventDefault();
        const item = cmdPaletteItems[cmdPaletteActiveIndex];
        if (item && item.type !== 'separator') {
            executeCmdItem(item);
        }
        return;
    }

    // Tab focus trap
    if (e.key === 'Tab') {
        e.preventDefault();
        return;
    }
});

// Overlay background click
document.getElementById('cmd-palette-overlay').addEventListener('click', (e) => {
    if (e.target === e.currentTarget) {
        closeCmdPalette();
    }
});

// Input filtering
document.getElementById('cmd-palette-input').addEventListener('input', (e) => {
    filterCmdPalette(e.target.value);
});
// === END TRACK E ===

// === TRACK A: TokenCost ===
async function loadSessionTokens(sessionId) {
    const badgeId = 'token-badge-' + sessionId;
    const panelId = 'token-panel-' + sessionId;

    document.querySelectorAll('.token-badge, .token-panel').forEach(el => el.remove());

    try {
        const resp = await fetch(`/api/sessions/${sessionId}/tokens`);
        const data = await resp.json();

        const badge = document.createElement('span');
        badge.className = 'token-badge';
        badge.id = badgeId;

        const titleEl = document.getElementById('session-detail-title');
        const header = document.querySelector('#session-detail .session-detail-header');

        if (data.total_tokens == null) {
            badge.textContent = 'No token data';
        } else {
            const cost = data.estimated_cost_usd != null
                ? `~$${Number(data.estimated_cost_usd).toFixed(3)}`
                : '';
            badge.textContent = `${Number(data.total_tokens).toLocaleString()} tokens${cost ? ' \u00b7 ' + cost : ''}`;
        }

        if (header && titleEl) {
            header.insertBefore(badge, titleEl.nextSibling);
        }

        const panel = document.createElement('div');
        panel.className = 'token-panel';
        panel.id = panelId;

        if (!data.steps || data.steps.length === 0) {
            panel.innerHTML = `<div class="token-panel-empty">No per-step token data available.</div>`;
        } else {
            const rows = data.steps.map(step => {
                const input = step.input_tokens != null ? Number(step.input_tokens).toLocaleString() : '\u2014';
                const output = step.output_tokens != null ? Number(step.output_tokens).toLocaleString() : '\u2014';
                const total = step.total_tokens != null ? Number(step.total_tokens).toLocaleString() : '\u2014';
                return `<tr class="token-breakdown-row">
                    <td>${step.step_index}</td>
                    <td>${escapeHtml(step.role)}</td>
                    <td>${escapeHtml(step.model || '\u2014')}</td>
                    <td>${input}</td>
                    <td>${output}</td>
                    <td class="token-total-cell">${total}</td>
                </tr>`;
            }).join('');

            panel.innerHTML = `
                <div class="token-panel-header"><h4>Token Breakdown</h4></div>
                <table class="token-breakdown-table">
                    <thead>
                        <tr>
                            <th>Step</th>
                            <th>Role</th>
                            <th>Model</th>
                            <th>Input</th>
                            <th>Output</th>
                            <th>Total</th>
                        </tr>
                    </thead>
                    <tbody>${rows}</tbody>
                </table>
            `;
        }

        const messagesContainer = document.getElementById('session-detail-messages');
        if (messagesContainer) {
            const overview = messagesContainer.querySelector('.session-overview');
            if (overview) {
                overview.after(panel);
            } else {
                messagesContainer.prepend(panel);
            }
        }
    } catch (err) {
        console.error('Failed to load session tokens:', err);
    }
}

function drawerContextGaugeTooltip(info, breakdown) {
    const lines = [contextGaugeTooltip(info)];
    if (breakdown && typeof breakdown === 'object') {
        Object.entries(breakdown)
            .filter(([, value]) => Number(value) > 0)
            .sort((a, b) => Number(b[1]) - Number(a[1]))
            .slice(0, 5)
            .forEach(([key, value]) => {
                const label = key.replace(/_tokens$/, '').replace(/_/g, ' ');
                lines.push(`${label}: ${formatTokenCount(Number(value))}`);
            });
    }
    return lines.join('\n');
}

function renderDrawerContextGauge(host, info, breakdown) {
    const tooltip = drawerContextGaugeTooltip(info, breakdown);
    host.innerHTML = `${renderContextGaugeHtml(info.percent, tooltip)}<span class="context-gauge-drawer-label" title="${escapeHtml(tooltip)}">${escapeHtml(contextGaugeTooltip(info))}</span>`;
    host.style.display = '';
}

async function loadSessionContextGauge(sessionId) {
    const host = document.getElementById('session-context-gauge');
    if (!host) return;
    host.innerHTML = '';
    host.style.display = 'none';
    if (!sessionId) return;

    const showFallback = (used) => {
        const n = Number(used);
        if (!Number.isFinite(n) || n < 0) return;
        host.textContent = `context: ${formatTokenCount(n)} tokens`;
        host.style.display = '';
    };

    if (sessionContextCache.sessionId === sessionId && sessionContextCache.info) {
        const cached = sessionContextCache.info;
        if (cached.stale) {
            showFallback(cached.used);
        } else {
            renderDrawerContextGauge(host, cached, null);
        }
        return;
    }

    try {
        const resp = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}/context`, {
            headers: { 'Accept': 'application/json' },
        });
        if (!resp.ok) return;
        const data = await resp.json();
        if (activeSessionDetailId !== sessionId) return;
        const info = normalizeContextInfo(data);
        sessionContextCache = { sessionId, info };
        if (!info || info.stale) {
            showFallback(data && data.context_used);
            return;
        }
        renderDrawerContextGauge(host, info, data && data.breakdown);
    } catch (err) {
        console.warn('Failed to load session context gauge:', err);
    }
}
// === END TRACK A ===

// === TRACK C: CronSchedule ===
let scheduleCountdownInterval = null;

function relativeTime(isoString) {
    if (!isoString) return '—';
    const date = new Date(isoString);
    if (Number.isNaN(date.getTime())) return isoString;
    const now = new Date();
    const diffMs = date - now;
    const diffSec = Math.round(diffMs / 1000);
    const absSec = Math.abs(diffSec);
    if (absSec < 60) return diffSec < 0 ? 'just now' : 'in moments';
    const absMin = Math.round(absSec / 60);
    if (absMin < 60) return diffSec < 0 ? `${absMin}m ago` : `in ${absMin}m`;
    const absHr = Math.round(absMin / 60);
    if (absHr < 24) return diffSec < 0 ? `${absHr}h ago` : `in ${absHr}h`;
    const absDay = Math.round(absHr / 24);
    if (absDay < 30) return diffSec < 0 ? `${absDay}d ago` : `in ${absDay}d`;
    const absMo = Math.round(absDay / 30);
    return diffSec < 0 ? `${absMo}mo ago` : `in ${absMo}mo`;
}

function renderScheduleCard(schedule) {
    const lastRun = schedule.last_run;
    const recentRuns = schedule.recent_runs || [];
    const dotsHtml = recentRuns.slice(0, 5).map(run => {
        const statusClass = run.status === 'complete' ? 'complete' : (run.status === 'error' ? 'error' : (run.status === 'running' ? 'running' : 'unknown'));
        return `<span class="run-history-dot ${statusClass}" title="${escapeHtml(run.status)} — ${escapeHtml(run.started_at || '')}" onclick="event.stopPropagation();viewSession('${escapeHtml(run.session_id)}')"></span>`;
    }).join('');

    const lastRunStatus = lastRun ? (lastRun.status || 'unknown') : 'unknown';
    const statusClass = lastRunStatus === 'complete' ? 'complete' : (lastRunStatus === 'error' ? 'error' : (lastRunStatus === 'running' ? 'running' : 'unknown'));
    const durationText = lastRun && lastRun.duration_seconds ? `${lastRun.duration_seconds}s` : '';

    const nextRunHtml = schedule.next_run
        ? `<span class="next-run-countdown" data-next-run="${escapeHtml(schedule.next_run)}">${relativeTime(schedule.next_run)}</span>`
        : '';

    return `
        <div class="schedule-card">
            <div class="schedule-card-header">
                <h4>${escapeHtml(schedule.name)}</h4>
                <span class="status-badge ${statusClass}">${escapeHtml(lastRunStatus)}</span>
            </div>
            <div class="schedule-card-meta">
                ${schedule.cron_expr ? `<span class="cron-expr-badge">${escapeHtml(schedule.cron_expr)}</span>` : ''}
                ${nextRunHtml}
                ${durationText ? `<span>${escapeHtml(durationText)}</span>` : ''}
            </div>
            <div class="run-history-dots">
                <span class="run-history-label">Recent runs:</span>
                ${dotsHtml || '<span style="color:var(--text-dim);font-size:0.75rem;">None</span>'}
            </div>
            ${lastRun ? `<div style="font-size:0.78rem;color:var(--text-dim);margin-top:0.2rem;">Last run: ${escapeHtml(formatSessionDate(lastRun.started_at) || '—')}</div>` : ''}
        </div>
    `;
}


var scrollsConsoleTimer = null;
var scrollsResearchTimer = null;
var scrollsResearchLoading = false;
var scrollsLastRunId = null;

function scrollsFmtNumber(value, digits = 4) {
    const n = Number(value);
    return Number.isFinite(n) ? n.toFixed(digits) : '—';
}

function scrollsGet(obj, path) {
    let cur = obj;
    for (const part of path) {
        if (!cur || typeof cur !== 'object') return undefined;
        cur = cur[part];
    }
    return cur;
}

function scrollsFmtTime(value) {
    if (!value) return '—';
    const d = typeof value === 'number' ? new Date(value * 1000) : new Date(value);
    return Number.isNaN(d.getTime()) ? String(value) : d.toLocaleString();
}

function scrollsFmtBytes(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return '—';
    if (n < 1024) return `${n} B`;
    if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
    return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

function scrollsFmtDuration(seconds) {
    const n = Number(seconds);
    if (!Number.isFinite(n)) return '—';
    if (n < 60) return `${Math.round(n)}s`;
    if (n < 3600) return `${Math.round(n / 60)}m`;
    return `${(n / 3600).toFixed(1)}h`;
}

function renderScrollsLoopPills(loop) {
    const state = loop || {};
    const active = !!state.active;
    return `
        <span class="meta-pill" style="color:${active ? 'var(--success)' : 'var(--text-dim)'};">loop ${escapeHtml(state.status || 'idle')}</span>
        <span class="meta-pill">remaining ${scrollsFmtDuration(state.remaining_seconds)}</span>
        <span class="meta-pill">iterations ${escapeHtml(String(state.iterations ?? 0))}</span>
        ${state.current_pid ? `<span class="meta-pill">pid ${escapeHtml(String(state.current_pid))}</span>` : ''}
    `;
}

function scrollsCompactJson(value) {
    if (value === undefined) return '—';
    if (value === null) return 'null';
    if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') return String(value);
    try { return JSON.stringify(value); } catch (_) { return String(value); }
}

function scrollsMetricDirection(run) {
    const metric = String(scrollsGet(run?.config || {}, ['evaluation', 'main_metric']) || 'val_loss').toLowerCase();
    return metric.includes('loss') ? 1 : -1;
}

function scrollsMetricName(run) {
    return String(scrollsGet(run?.config || {}, ['evaluation', 'main_metric']) || 'val_loss');
}

function scrollsMetricDelta(current, previous, run = null) {
    const cur = Number(current);
    const prev = Number(previous);
    if (!Number.isFinite(cur) || !Number.isFinite(prev)) return { text: '—', tone: 'neutral' };
    const delta = cur - prev;
    if (Math.abs(delta) < 1e-12) return { text: '±0.0000', tone: 'neutral' };
    const direction = scrollsMetricDirection(run);
    return { text: `${delta > 0 ? '+' : ''}${scrollsFmtNumber(delta)}`, tone: direction * delta < 0 ? 'good' : 'bad' };
}

function scrollsProgressTone(status) {
    if (status === 'improving' || status === 'done' || status === 'ok') return 'var(--success)';
    if (status === 'regressing' || status === 'blocked') return 'var(--error)';
    if (status === 'warning' || status === 'noisy' || status === 'active') return 'var(--warning)';
    return 'var(--text-dim)';
}

function scrollsPct(value) {
    const n = Number(value);
    return Number.isFinite(n) ? `${Math.round(n * 100)}%` : '—';
}

function renderScrollsProgressTracker(tracker) {
    const summary = tracker?.summary || {};
    const score = tracker?.scorecard || {};
    const sanity = tracker?.sanity || {};
    const signals = tracker?.signals || {};
    const percent = Math.max(0, Math.min(100, Number(summary.percent || 0)));
    const target = Number(summary.progress_target || 0.02);
    const foundationReadiness = Number(summary.foundation_readiness);
    const relativeGain = score.relative_gain_vs_baseline == null ? '—' : `${Number(score.relative_gain_vs_baseline) >= 0 ? '+' : ''}${scrollsPct(score.relative_gain_vs_baseline)}`;
    const apGain = score.average_precision_gain == null ? '—' : `${Number(score.average_precision_gain) >= 0 ? '+' : ''}${scrollsFmtNumber(score.average_precision_gain)}`;
    const modelMix = Object.entries(score.model_family_mix || {}).map(([family, count]) => `${family} ${count}`).join(' · ') || 'unknown mix';
    const milestones = (tracker?.milestones || []).map(item => `
        <div class="activity-item" style="padding:0.55rem 0.65rem;border-left:3px solid ${scrollsProgressTone(item.state)};">
            <div style="display:flex;justify-content:space-between;gap:0.6rem;align-items:center;">
                <strong style="font-size:0.82rem;">${escapeHtml(item.label || '')}</strong>
                <span class="meta-pill" style="color:${scrollsProgressTone(item.state)};">${escapeHtml(item.state || 'unknown')}</span>
            </div>
            <div style="color:var(--text-dim);font-size:0.75rem;margin-top:0.25rem;">${escapeHtml(item.detail || '')}</div>
        </div>
    `).join('') || '<p style="color:var(--text-dim);">No progress milestones available.</p>';
    const sanityText = (sanity.warnings || []).length ? sanity.warnings.join(' · ') : 'precision/recall nonzero';
    return `
        <div class="card scrolls-card-tight" style="margin-bottom:0.75rem;border-color:var(--primary-border);">
            <div style="display:flex;justify-content:space-between;gap:1rem;align-items:flex-start;flex-wrap:wrap;">
                <div style="min-width:240px;flex:1;">
                    <div style="color:var(--text-dim);font-size:0.72rem;text-transform:uppercase;letter-spacing:0.08em;">Research Progress Tracker</div>
                    <h3 style="margin:0.25rem 0;color:${scrollsProgressTone(summary.status)};">${escapeHtml(summary.label || 'Unknown progress')}</h3>
                    <p style="color:var(--text-dim);font-size:0.84rem;line-height:1.35;max-width:820px;">${escapeHtml(summary.current_step || '')}</p>
                    <p style="color:var(--text);font-size:0.86rem;line-height:1.35;margin-top:0.35rem;"><strong>Next:</strong> ${escapeHtml(summary.next_action || '')}</p>
                </div>
                <div style="min-width:220px;">
                    <div style="font-size:1.65rem;font-weight:800;color:var(--primary);">${escapeHtml(String(Math.round(percent)))}%</div>
                    <div style="height:9px;border-radius:999px;background:rgba(255,255,255,0.08);overflow:hidden;margin-top:0.35rem;"><div style="width:${percent}%;height:100%;background:linear-gradient(90deg,var(--primary),var(--success));"></div></div>
                    <div style="color:var(--text-dim);font-size:0.74rem;margin-top:0.3rem;">of first +${scrollsFmtNumber(target)} F1 improvement target</div>
                    <div style="color:var(--text-dim);font-size:0.72rem;margin-top:0.2rem;">setup confidence ${Number.isFinite(foundationReadiness) ? `${Math.round(foundationReadiness)}%` : '—'}</div>
                </div>
            </div>
            <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:0.55rem;margin-top:0.75rem;">
                <div class="stat-card"><div class="stat-value">${scrollsFmtNumber(score.best)}</div><div class="stat-label">Best held-out F1</div></div>
                <div class="stat-card"><div class="stat-value" title="${escapeHtml(score.best_model_name || '')}">${escapeHtml(score.best_model_name || '—')}</div><div class="stat-label">Best model</div></div>
                <div class="stat-card"><div class="stat-value">${scrollsFmtNumber(score.best_pytorch_f1)}</div><div class="stat-label">Best PyTorch F1</div></div>
                <div class="stat-card"><div class="stat-value">${scrollsFmtNumber(score.best_pytorch_ap)}</div><div class="stat-label">Best PyTorch AP</div></div>
                <div class="stat-card"><div class="stat-value" style="color:${Number(score.gain_vs_baseline) > 0 ? 'var(--success)' : 'var(--text)'};">${score.gain_vs_baseline == null ? '—' : `${Number(score.gain_vs_baseline) >= 0 ? '+' : ''}${scrollsFmtNumber(score.gain_vs_baseline)}`}</div><div class="stat-label">Gain vs baseline</div></div>
                <div class="stat-card"><div class="stat-value" style="color:${Number(score.average_precision_gain) > 0 ? 'var(--success)' : 'var(--text)'};">${apGain}</div><div class="stat-label">AP/ranking gain</div></div>
                <div class="stat-card"><div class="stat-value" style="color:${scrollsProgressTone(score.trend)};">${escapeHtml(score.trend || 'unknown')}</div><div class="stat-label">Recent direction</div></div>
            </div>
            <div style="display:grid;grid-template-columns:minmax(0,1.05fr) minmax(290px,0.95fr);gap:0.75rem;margin-top:0.75rem;align-items:start;">
                <div>
                    <h5>Evidence Checklist</h5>
                    <div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0.45rem;margin-top:0.45rem;">${milestones}</div>
                </div>
                <div>
                    <h5>What This Means</h5>
                    <div class="activity-item" style="margin-top:0.45rem;padding:0.7rem;">
                        <p style="color:var(--text-dim);font-size:0.82rem;line-height:1.4;">The big percent is not setup completion. It is actual score lift: best held-out val_f1 minus the first comparable baseline, measured against an initial +${scrollsFmtNumber(target)} F1 target. Right now, the important question is whether that lift keeps increasing or has plateaued.</p>
                        <div class="message-meta" style="margin-top:0.55rem;">
                            <span class="meta-pill">runs ${escapeHtml(String(score.comparable_run_count ?? 0))}</span>
                            <span class="meta-pill">models ${escapeHtml(modelMix)}</span>
                            <span class="meta-pill">idea success ${scrollsPct(score.hypothesis_yield)}</span>
                            <span class="meta-pill">best AP ${scrollsFmtNumber(score.best_average_precision)}</span>
                            <span class="meta-pill">${escapeHtml(signals.validation_mode || 'unknown')}</span>
                            <span class="meta-pill">${escapeHtml(signals.train || '?')} → ${escapeHtml(signals.val || '?')}</span>
                        </div>
                        <p style="color:${scrollsProgressTone(sanity.status)};font-size:0.8rem;margin-top:0.5rem;">Prediction sanity: ${escapeHtml(sanityText)} · precision ${scrollsFmtNumber(sanity.precision)} · recall ${scrollsFmtNumber(sanity.recall)}</p>
                    </div>
                </div>
            </div>
        </div>
    `;
}

function scrollsRunLabel(run) {
    if (!run) return '—';
    const setup = run.validation_setup || {};
    const train = setup.train_segment_id || scrollsGet(run.config || {}, ['dataset', 'train_scroll_id']) || '?';
    const val = setup.val_segment_id || scrollsGet(run.config || {}, ['dataset', 'val_scroll_id']) || '?';
    return `${train}→${val}`;
}

function scrollsRunValidationMode(run) {
    return run?.validation_setup?.mode || scrollsGet(run?.config || {}, ['dataset', 'validation_mode']) || 'unknown';
}

function scrollsRecommendation(data, latest, previous, best) {
    if (data.lock_active) {
        return { title: 'AutoResearch is running', body: 'Wait for the current run to finish, then inspect the new metrics and artifacts before changing configs.', action: 'Refresh status', run: latest?.run_id || '—' };
    }
    if (!latest) {
        return { title: 'Start a baseline run', body: 'No experiment ledger entries are available yet. Run AutoResearch or a baseline config to create the first comparable artifact set.', action: 'Run AutoResearch', run: 'none' };
    }
    const latestHypothesis = (data.experiments?.hypotheses || [])[0];
    const delta = scrollsMetricDelta(latest.main_metric, previous?.main_metric, latest);
    if (latestHypothesis?.status === 'improved') {
        return { title: 'Exploit the latest improvement', body: `Latest run improved by ${delta.text}. Inspect its artifacts, then run a small follow-up around the changed paths: ${(latestHypothesis.changed_paths || []).slice(0, 3).join(', ') || 'config changes'}.`, action: 'Inspect artifacts', run: latest.run_id };
    }
    if (latestHypothesis?.status === 'regressed') {
        return { title: 'Backtrack the last change', body: `Latest run regressed by ${delta.text}. Compare latest vs best and prefer configs closer to ${best?.run_id || 'the best run'} before launching another sweep.`, action: 'Compare latest vs best', run: latest.run_id };
    }
    return { title: 'Tighten the next hypothesis', body: 'Review the latest config diff and artifact metrics, then run one interpretable change instead of a broad sweep.', action: 'Review evidence', run: latest.run_id };
}

function scrollsArtifactRow(artifact) {
    const encodedPath = encodeURIComponent(artifact.path || '');
    return `
        <button class="activity-item" style="width:100%;text-align:left;display:flex;justify-content:space-between;gap:0.75rem;align-items:center;cursor:pointer;" onclick="loadScrollsArtifact('${encodedPath}')">
            <span style="min-width:0;"><span style="display:block;font-family:monospace;font-size:0.78rem;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${escapeHtml(artifact.name || '')}</span><span style="display:block;font-size:0.72rem;color:var(--text-dim);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${escapeHtml(artifact.path || '')}</span></span>
            <span class="meta-pill">${escapeHtml(artifact.kind || 'file')} · ${scrollsFmtBytes(artifact.size_bytes)}</span>
        </button>
    `;
}

function renderScrollsFeatureInventory(inventory) {
    const features = Array.isArray(inventory?.features) ? inventory.features : [];
    const warnings = Array.isArray(inventory?.warnings) ? inventory.warnings : [];
    const champions = Array.isArray(inventory?.champion_configs) ? inventory.champion_configs : [];
    const featureCards = features.map((item) => `
        <div class="activity-item" style="padding:0.65rem 0.75rem;">
            <div style="display:flex;justify-content:space-between;gap:0.65rem;align-items:flex-start;flex-wrap:wrap;">
                <strong>${escapeHtml(item.title || '')}</strong>
                <span class="meta-pill">${item.available ? 'available' : 'check files'}</span>
            </div>
            <p style="color:var(--text-dim);font-size:0.78rem;line-height:1.35;margin-top:0.25rem;">${escapeHtml(item.detail || '')}</p>
            <pre style="white-space:pre-wrap;color:var(--text-dim);font-size:0.72rem;margin-top:0.45rem;overflow:auto;">${escapeHtml(item.command || '')}</pre>
        </div>
    `).join('') || '<p style="color:var(--text-dim);">No Vesuvius AutoResearch feature inventory returned.</p>';
    const championPills = champions.map((cfg) => `<span class="meta-pill" title="${escapeHtml(cfg.path || '')}">${escapeHtml(cfg.name || '')}${cfg.available ? '' : ' missing'}</span>`).join('') || '<span style="color:var(--text-dim);font-size:0.78rem;">No champion configs listed.</span>';
    const warningRows = warnings.map((warning) => `<p style="color:var(--warning);font-size:0.78rem;line-height:1.35;margin-top:0.35rem;">${escapeHtml(warning)}</p>`).join('');
    return `
        <div id="scrolls-autoresearch-features" class="card scrolls-card-tight" style="margin-top:0.75rem;">
            <div style="display:flex;justify-content:space-between;gap:0.75rem;align-items:flex-start;flex-wrap:wrap;">
                <div>
                    <h4>Vesuvius AutoResearch Feature Inventory</h4>
                    <p style="color:var(--text-dim);font-size:0.82rem;line-height:1.35;margin-top:0.35rem;">Safe recommended commands are shown for terminal review from the project root; the dashboard does not execute these commands.</p>
                </div>
                <div class="message-meta" style="max-width:520px;justify-content:flex-end;">${championPills}</div>
            </div>
            ${warningRows}
            <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:0.55rem;margin-top:0.75rem;">${featureCards}</div>
        </div>
    `;
}

async function scrollsFetchJson(url, options = {}) {
    const resp = await fetch(url, options);
    let data = null;
    try { data = await resp.json(); } catch (_) { data = {}; }
    if (!resp.ok) throw new Error(data.error || data.detail || resp.statusText || 'request failed');
    return data;
}

function renderScrollsProcessPills(processes) {
    const rows = Array.isArray(processes) ? processes : [];
    if (!rows.length) return '<span class="meta-pill">no live process</span>';
    return rows.map(proc => `<span class="meta-pill" title="${escapeHtml(proc.command || '')}">pid ${escapeHtml(proc.pid || '?')} · ${scrollsFmtDuration(proc.age_seconds)}</span>`).join('');
}

function updateScrollsConsole(data) {
    const consoleEl = document.getElementById('scrolls-live-console');
    const statusEl = document.getElementById('scrolls-console-status');
    const cronEl = document.getElementById('scrolls-console-cron');
    const loopEl = document.getElementById('scrolls-improvement-loop');
    const timedLoopEl = document.getElementById('scrolls-timed-loop-status');
    const lines = data?.logs?.lines || [];
    if (consoleEl) {
        consoleEl.textContent = lines.join('\n') || 'No AutoResearch log lines yet. Start a supervised run or wait for cron fallback.';
        consoleEl.scrollTop = consoleEl.scrollHeight;
    }
    if (statusEl) {
        statusEl.innerHTML = `
            <span class="meta-pill">${data?.lock_active ? 'running' : 'idle'}</span>
            ${renderScrollsProcessPills(data?.processes)}
            ${renderScrollsLoopPills(data?.timed_loop)}
            <span class="meta-pill">updated ${escapeHtml(scrollsFmtTime(data?.generated_at))}</span>
        `;
    }
    if (timedLoopEl) timedLoopEl.innerHTML = renderScrollsLoopPills(data?.timed_loop);
    if (cronEl) {
        cronEl.innerHTML = `
            <span class="meta-pill">fallback cron ${data?.cron?.installed ? 'installed' : 'missing'}</span>
            <span class="meta-pill">log ${escapeHtml(scrollsFmtBytes(data?.logs?.stat?.size_bytes))}</span>
        `;
    }
    if (loopEl) {
        const loop = data?.improvement_loop || {};
        const job = loop.primary_job || {};
        const blockers = loop.blockers || [];
        loopEl.innerHTML = `
            <h4>Daily Hermes Improvement Loop</h4>
            <div class="message-meta" style="margin:0.5rem 0;">
                <span class="meta-pill">${loop.ok ? 'wired' : 'attention'}</span>
                <span class="meta-pill">jobs ${escapeHtml(String(loop.job_count ?? '—'))}</span>
                <span class="meta-pill">legacy active ${escapeHtml(String(loop.active_legacy_count ?? '—'))}</span>
            </div>
            <p style="color:var(--text-dim);font-size:0.82rem;line-height:1.35;margin-top:0.4rem;">Once a day, Hermes should review Vesuvius AutoResearch results, Becomussy continuity notes, cron outputs, and dashboard friction to propose small efficiency improvements. Manual supervised runs stay primary; cron is the fallback.</p>
            <p style="color:var(--text-dim);font-size:0.8rem;margin-top:0.45rem;">Primary: ${escapeHtml(job.name || 'self-improvement-loop not found')} · next ${escapeHtml(job.next_run_at || '—')}</p>
            ${blockers.length ? `<p style="color:var(--warning);font-size:0.8rem;margin-top:0.4rem;">${escapeHtml(blockers.join(' · '))}</p>` : ''}
        `;
    }
    const topBtn = document.getElementById('scrolls-autoresearch-btn');
    if (topBtn) topBtn.disabled = !!data?.lock_active;
}

async function refreshScrollsConsole() {
    try {
        const data = await scrollsFetchJson('/api/scrolls/console');
        updateScrollsConsole(data);
    } catch (err) {
        const statusEl = document.getElementById('scrolls-console-status');
        if (statusEl) statusEl.innerHTML = `<span style="color:var(--error);">Console refresh failed: ${escapeHtml(String(err))}</span>`;
    }
}

function toggleScrollsConsoleAutoRefresh() {
    const enabled = !!document.getElementById('scrolls-console-autorefresh')?.checked;
    if (scrollsConsoleTimer) {
        clearInterval(scrollsConsoleTimer);
        scrollsConsoleTimer = null;
    }
    if (enabled) {
        refreshScrollsConsole();
        scrollsConsoleTimer = setInterval(refreshScrollsConsole, 5000);
    }
}

function startScrollsResearchAutoRefresh() {
    if (scrollsResearchTimer) clearInterval(scrollsResearchTimer);
    scrollsResearchTimer = setInterval(() => {
        const panel = document.getElementById('scrolls-panel');
        if (panel && panel.classList.contains('active')) loadScrollsResearch({ silent: true });
    }, 10000);
}

function stopScrollsResearchAutoRefresh() {
    if (scrollsResearchTimer) {
        clearInterval(scrollsResearchTimer);
        scrollsResearchTimer = null;
    }
}

async function loadScrollsResearch(options = {}) {
    const container = document.getElementById('scrolls-container');
    if (!container) return;
    if (scrollsResearchLoading) return;
    scrollsResearchLoading = true;
    const silent = !!options.silent;
    const previousScrollTop = container.scrollTop;
    if (!silent) container.innerHTML = '<div style="text-align:center;color:var(--text-dim);padding:2rem;">Loading Vesuvius AutoResearch...</div>';
    try {
        const data = await scrollsFetchJson('/api/scrolls/research');
        const best = data.experiments?.best || null;
        const recent = data.experiments?.recent || [];
        const configs = data.configs || [];
        const scrolls = Array.isArray(data.data_summary?.scrolls) ? data.data_summary.scrolls : [];
        const prepared = data.prepared_datasets || [];
        const latest = data.experiments?.latest || recent[0] || null;
        const latestRunId = latest?.run_id || null;
        if (silent && latestRunId && scrollsLastRunId && latestRunId !== scrollsLastRunId) {
            showToast(`New Vesuvius AutoResearch result logged: ${latestRunId}`);
        }
        scrollsLastRunId = latestRunId;
        const previous = recent[1] || null;
        const logLines = data.logs?.lines || [];
        const metricLabel = scrollsMetricName(best || latest);
        const metricValue = best ? scrollsFmtNumber(best.main_metric) : '—';
        const cronText = data.cron?.installed ? 'Installed' : 'Missing';
        const lockText = data.lock_active ? 'Running' : 'Idle';
        const latestArtifacts = latest?.artifacts || [];
        const bestArtifacts = data.experiments?.best?.artifacts || [];
        const latestDelta = scrollsMetricDelta(latest?.main_metric, previous?.main_metric, latest);
        const bestGap = scrollsMetricDelta(latest?.main_metric, best?.main_metric, latest);
        const recommendation = scrollsRecommendation(data, latest, previous, best);
        const progressHtml = renderScrollsProgressTracker(data.progress_tracker || {});
        const latestHypothesis = (data.experiments?.hypotheses || [])[0] || null;
        const weakestPair = (data.experiments?.validation_matrix || []).slice().sort((a, b) => Number(b.best_main_metric ?? -Infinity) - Number(a.best_main_metric ?? -Infinity))[0] || null;
        const validationMode = scrollsRunValidationMode(latest);
        const validationWarning = latest?.validation_setup?.warning || data.data_summary?.validation_setup?.warning || (validationMode === 'cross-segment' || validationMode === 'cross-scroll' ? '' : 'Active validation is not cross-segment/cross-scroll.');
        const consoleLines = data.logs?.lines || [];
        const consoleStat = data.logs?.stat || {};
        const featureInventoryHtml = renderScrollsFeatureInventory(data.autoresearch_inventory || {});
        const processPills = renderScrollsProcessPills(data.processes);
        const loop = data.improvement_loop || {};
        const loopJob = loop.primary_job || {};
        const loopBlockers = loop.blockers || [];
        const timedLoop = data.timed_loop || {};
        const diffRows = (data.experiments?.config_diffs?.latest_vs_previous || []).map((diff) => `
            <tr>
                <td style="padding:0.4rem 0.45rem;font-family:monospace;color:var(--primary);">${escapeHtml(diff.path || '')}</td>
                <td style="padding:0.4rem 0.45rem;font-family:monospace;color:var(--text-dim);max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${escapeHtml(scrollsCompactJson(diff.before))}">${escapeHtml(scrollsCompactJson(diff.before))}</td>
                <td style="padding:0.4rem 0.45rem;font-family:monospace;max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${escapeHtml(scrollsCompactJson(diff.after))}">${escapeHtml(scrollsCompactJson(diff.after))}</td>
            </tr>
        `).join('') || '<tr><td colspan="3" style="padding:0.75rem;color:var(--text-dim);">No latest-vs-previous config changes.</td></tr>';
        const hypothesisCards = (data.experiments?.hypotheses || []).slice(0, 6).map((item) => `
            <div class="activity-item">
                <div style="display:flex;gap:0.35rem;flex-wrap:wrap;align-items:center;margin-bottom:0.35rem;">
                    <span class="meta-pill" style="font-family:monospace;">${escapeHtml(item.run_id || '')}</span>
                    <span class="meta-pill">${escapeHtml(item.status || 'inconclusive')}</span>
                    <span class="meta-pill">metric ${scrollsFmtNumber(item.metric)}</span>
                    <span class="meta-pill">Δ prev ${item.metric_delta_vs_previous == null ? '—' : scrollsFmtNumber(item.metric_delta_vs_previous)}</span>
                </div>
                <p style="color:var(--text-dim);font-size:0.84rem;">${escapeHtml(item.reason || 'No hypothesis text recorded.')}</p>
                <div style="display:flex;gap:0.25rem;flex-wrap:wrap;margin-top:0.45rem;">${(item.changed_paths || []).slice(0,8).map(p => `<span class="meta-pill" style="font-family:monospace;font-size:0.7rem;">${escapeHtml(p)}</span>`).join('') || '<span style="color:var(--text-dim);font-size:0.75rem;">No config changes recorded.</span>'}</div>
            </div>
        `).join('') || '<p style="color:var(--text-dim);">No AutoResearch hypotheses found.</p>';
        const artifactRows = latestArtifacts.map(scrollsArtifactRow).join('') || '<p style="color:var(--text-dim);">No artifacts listed for latest run.</p>';
        const bestArtifactRows = bestArtifacts.map(scrollsArtifactRow).join('') || '<p style="color:var(--text-dim);">No artifacts listed for best run.</p>';
        const trendBars = (data.experiments?.metric_trends || []).map((point) => {
            const value = Number(point.main_metric ?? point.val_loss);
            return { point, value };
        }).filter(x => Number.isFinite(x.value));
        const trendMin = trendBars.length ? Math.min(...trendBars.map(x => x.value)) : 0;
        const trendMax = trendBars.length ? Math.max(...trendBars.map(x => x.value)) : 1;
        const trendHtml = trendBars.length ? trendBars.map(({point, value}) => {
            const norm = trendMax === trendMin ? 0.5 : (value - trendMin) / (trendMax - trendMin);
            const higherIsBetter = !metricLabel.toLowerCase().includes('loss');
            const height = 12 + (higherIsBetter ? norm : (1 - norm)) * 84;
            return `<div title="${escapeHtml(point.run_id)}: ${escapeHtml(metricLabel)} ${scrollsFmtNumber(value)} F1 ${scrollsFmtNumber(point.val_f1)}" style="flex:1;min-width:7px;height:${height}%;background:var(--primary);opacity:0.75;border-radius:4px 4px 0 0;"></div>`;
        }).join('') : '<p style="color:var(--text-dim);">No metric trend data.</p>';
        const matrixRows = (data.experiments?.validation_matrix || []).map((cell) => `
            <tr><td style="padding:0.4rem 0.45rem;font-family:monospace;">${escapeHtml(cell.train_segment_id || cell.train_scroll_id || '?')} → ${escapeHtml(cell.val_segment_id || cell.val_scroll_id || '?')}</td><td style="padding:0.4rem 0.45rem;">${escapeHtml(cell.validation_mode || 'unknown')}</td><td style="padding:0.4rem 0.45rem;text-align:right;">${scrollsFmtNumber(cell.best_main_metric)}</td><td style="padding:0.4rem 0.45rem;text-align:right;">${scrollsFmtNumber(cell.best_val_f1)}</td><td style="padding:0.4rem 0.45rem;text-align:right;">${escapeHtml(String(cell.run_count ?? '—'))}</td><td style="padding:0.4rem 0.45rem;font-family:monospace;color:var(--text-dim);">${escapeHtml(cell.best_run_id || '')}</td></tr>
        `).join('') || '<tr><td colspan="6" style="padding:0.75rem;color:var(--text-dim);">No train/validation scroll pairs recorded.</td></tr>';
        const configRows = configs.slice(0, 12).map((cfg) => `
            <div class="activity-item" style="display:flex;justify-content:space-between;gap:0.65rem;align-items:center;padding:0.55rem 0.65rem;">
                <div style="min-width:0;">
                    <div style="font-family:monospace;font-size:0.82rem;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${escapeHtml(cfg.name)}</div>
                    <div style="font-size:0.75rem;color:var(--text-dim);margin-top:0.25rem;">
                        lr ${scrollsFmtNumber(scrollsGet(cfg.summary, ['training','learning_rate']), 5)} · depth ${escapeHtml(String(scrollsGet(cfg.summary, ['model','depth']) ?? '—'))} · validation ${escapeHtml(String(scrollsGet(cfg.summary, ['dataset','validation_mode']) ?? 'unknown'))}
                    </div>
                </div>
                <button class="btn" onclick="runScrollsConfig('${escapeHtml(cfg.name)}')">Run</button>
            </div>
        `).join('') || '<p style="color:var(--text-dim);">No configs found.</p>';
        const preparedRows = prepared.slice(0, 8).map((item) => {
            const meta = item.metadata || {};
            return `
                <div class="activity-item" style="padding:0.5rem 0.6rem;">
                    <div style="display:flex;justify-content:space-between;gap:0.5rem;align-items:center;">
                        <strong style="font-size:0.78rem;">${escapeHtml(meta.split || 'dataset')}</strong>
                        <span class="meta-pill">pos ${scrollsFmtNumber(meta.positive_rate ?? meta.label_positive_rate, 3)}</span>
                    </div>
                    <div style="font-size:0.72rem;color:var(--text-dim);font-family:monospace;margin-top:0.25rem;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${escapeHtml(meta.segment_id || '?')} · ${escapeHtml(meta.source || 'unknown')} · ${escapeHtml(String(meta.samples ?? '—'))} samples</div>
                </div>
            `;
        }).join('') || '<p style="color:var(--text-dim);font-size:0.82rem;">No prepared dataset metadata found.</p>';
        const latestTrain = scrollsGet(latest?.config || {}, ['resolved_data', 'train', 'metadata']) || {};
        const latestVal = scrollsGet(latest?.config || {}, ['resolved_data', 'val', 'metadata']) || {};
        const runRows = recent.map((run) => `
            <tr>
                <td style="padding:0.45rem 0.5rem;font-family:monospace;font-size:0.75rem;">${escapeHtml(run.run_id)}</td>
                <td style="padding:0.45rem 0.5rem;text-align:right;">${scrollsFmtNumber(run.metrics?.val_loss ?? run.main_metric)}</td>
                <td style="padding:0.45rem 0.5rem;text-align:right;">${scrollsFmtNumber(run.metrics?.val_f1)}</td>
                <td style="padding:0.45rem 0.5rem;text-align:right;">${scrollsFmtNumber(scrollsGet(run.config, ['training','learning_rate']), 5)}</td>
                <td style="padding:0.45rem 0.5rem;text-align:right;">${escapeHtml(String(scrollsGet(run.config, ['model','depth']) ?? '—'))}</td>
                <td style="padding:0.45rem 0.5rem;text-align:right;">${escapeHtml(scrollsRunLabel(run))}</td>
                <td style="padding:0.45rem 0.5rem;text-align:right;color:var(--text-dim);">${escapeHtml(scrollsFmtTime(run.timestamp))}</td>
            </tr>
        `).join('') || '<tr><td colspan="7" style="padding:1rem;color:var(--text-dim);">No experiments logged yet.</td></tr>';
        container.innerHTML = `
            ${progressHtml}
            <div class="scrolls-hero">
                <div>
                    <div class="card scrolls-card-tight" style="overflow:auto;">
                        <h4>Latest Config Diff</h4>
                        <p style="color:var(--text-dim);font-size:0.72rem;margin-top:0.2rem;">Latest ${escapeHtml(latest?.run_id || '—')} vs previous ${escapeHtml(previous?.run_id || '—')}.</p>
                        <div style="max-height:235px;overflow:auto;margin-top:0.35rem;"><table style="width:100%;border-collapse:collapse;font-size:0.74rem;"><thead><tr style="color:var(--text-dim);border-bottom:1px solid var(--border-subtle);"><th style="text-align:left;padding:0.28rem 0.32rem;">Path</th><th style="text-align:left;padding:0.28rem 0.32rem;">Before</th><th style="text-align:left;padding:0.28rem 0.32rem;">After</th></tr></thead><tbody>${diffRows}</tbody></table></div>
                    </div>
                    <div style="display:flex;gap:0.35rem;flex-wrap:wrap;margin-top:0.55rem;align-items:center;">
                        <span class="meta-pill">auto-refresh 10s</span>
                        ${['runs','matrix','artifacts','hypotheses','logs'].map(id => `<a class="meta-pill" href="#scrolls-${id}" style="text-decoration:none;">${id[0].toUpperCase()}${id.slice(1)}</a>`).join('')}
                    </div>
                </div>
                <div class="scrolls-hero-side">
                    <div class="card scrolls-card-tight" style="border-color:var(--primary-border);background:linear-gradient(135deg,var(--primary-dim),rgba(255,255,255,0.02));">
                        <div style="display:flex;justify-content:space-between;gap:0.75rem;align-items:flex-start;">
                            <div style="min-width:0;">
                                <div style="color:var(--text-dim);font-size:0.72rem;text-transform:uppercase;letter-spacing:0.08em;">Next decision</div>
                                <strong style="display:block;margin-top:0.15rem;">${escapeHtml(recommendation.title)}</strong>
                                <p style="color:var(--text-dim);font-size:0.78rem;line-height:1.3;margin-top:0.25rem;">${escapeHtml(recommendation.body)}</p>
                            </div>
                            <button class="btn" onclick="triggerScrollsAutoresearch()">Run</button>
                        </div>
                    </div>
                    <div class="card scrolls-card-tight">
                        <div style="display:flex;justify-content:space-between;gap:0.5rem;align-items:center;"><h4>Validation Health</h4><span class="meta-pill">cron ${escapeHtml(cronText)}</span></div>
                        <div class="scrolls-health-row">
                            <span class="meta-pill" title="${escapeHtml(latestTrain.segment_id || '')}">train ${escapeHtml(latestTrain.segment_id || latest?.validation_setup?.train_segment_id || '?')}</span>
                            <span class="meta-pill" title="${escapeHtml(latestVal.segment_id || '')}">val ${escapeHtml(latestVal.segment_id || latest?.validation_setup?.val_segment_id || '?')}</span>
                            <span class="meta-pill">train pos ${scrollsFmtNumber(latest?.metrics?.train_positive_rate, 3)}</span>
                            <span class="meta-pill">val pos ${scrollsFmtNumber(latest?.metrics?.val_positive_rate, 3)}</span>
                        </div>
                    </div>
                </div>
            </div>
            ${!data.exists ? `<div class="card" style="border-color:var(--error);color:var(--error);margin-top:1rem;">Project root not found: ${escapeHtml(data.project_root || '')}</div>` : ''}
            ${validationWarning ? `<div class="card" style="border-color:var(--warning);color:var(--warning);margin-top:1rem;"><strong>Validation mode: ${escapeHtml(validationMode)}</strong><br>${escapeHtml(validationWarning)}</div>` : ''}
            ${featureInventoryHtml}
            <div class="scrolls-control-grid">
                <div class="card scrolls-card-tight">
                    <div style="display:flex;justify-content:space-between;gap:0.75rem;align-items:flex-start;flex-wrap:wrap;">
                        <div>
                            <h4>Live Research Console</h4>
                            <p style="color:var(--text-dim);font-size:0.82rem;margin-top:0.25rem;">Supervise active runs from the log tail. Auto-refresh polls every 5s and disables manual launch while a lock is held.</p>
                        </div>
                        <div style="display:flex;gap:0.45rem;flex-wrap:wrap;align-items:center;">
                            <button class="btn" onclick="refreshScrollsConsole()">Refresh Console</button>
                            <button class="btn primary" onclick="triggerScrollsAutoresearch()">Run Supervised Step</button>
                            <label class="meta-pill" style="cursor:pointer;"><input id="scrolls-console-autorefresh" type="checkbox" checked onchange="toggleScrollsConsoleAutoRefresh()" style="vertical-align:middle;margin-right:0.25rem;">live</label>
                        </div>
                    </div>
                    <div id="scrolls-console-status" class="message-meta" style="margin:0.55rem 0;"><span class="meta-pill">${data.lock_active ? 'running' : 'idle'}</span>${processPills}<span class="meta-pill">updated now</span></div>
                    <pre id="scrolls-live-console" class="scrolls-console">${escapeHtml(consoleLines.join('\n') || 'No AutoResearch log lines yet. Start a supervised run or wait for cron fallback.')}</pre>
                </div>
                <div style="display:grid;gap:0.75rem;">
                    <div class="card scrolls-card-tight">
                        <h4>Continued Research Controls</h4>
                        <p style="color:var(--text-dim);font-size:0.82rem;line-height:1.35;margin-top:0.35rem;">Run one interpretable AutoResearch step, inspect metrics/artifacts, then decide whether to exploit, backtrack, or prepare a new focused segment pair. PyTorch runs are CPU-only here; keep worker counts conservative and cron as the fallback, not the main driver.</p>
                        <div style="display:flex;gap:0.45rem;flex-wrap:wrap;margin-top:0.65rem;">
                            <button class="btn primary" onclick="triggerScrollsAutoresearch()">Run next step</button>
                            <button class="btn" onclick="runScrollsConfig('baseline.yaml')">Run baseline</button>
                            <a class="btn" href="#cron" onclick="navigateTo('cron')" style="text-decoration:none;">Cron jobs</a>
                            <a class="btn" href="#self-improvement" onclick="navigateTo('self-improvement')" style="text-decoration:none;">Hermes loop</a>
                        </div>
                        <div style="border-top:1px solid var(--border-subtle);margin-top:0.75rem;padding-top:0.75rem;">
                            <h5>Timed Autonomous Loop</h5>
                            <p style="color:var(--text-dim);font-size:0.78rem;line-height:1.35;margin-top:0.25rem;">Runs repeated AutoResearch iterations until the selected time budget expires. Live console and results update while it runs.</p>
                            <div style="display:flex;gap:0.45rem;flex-wrap:wrap;margin-top:0.55rem;align-items:center;">
                                <select id="scrolls-loop-minutes" style="background:var(--input-bg);color:var(--text);border:1px solid var(--border-subtle);border-radius:8px;padding:0.45rem;">
                                    <option value="5">5 min</option>
                                    <option value="15" selected>15 min</option>
                                    <option value="30">30 min</option>
                                    <option value="60">60 min</option>
                                    <option value="120">120 min</option>
                                </select>
                                <button class="btn primary" id="scrolls-loop-start-btn" onclick="startScrollsTimedLoop()">Start timed loop</button>
                                <button class="btn" id="scrolls-loop-stop-btn" onclick="stopScrollsTimedLoop()">Stop after current run</button>
                            </div>
                            <div id="scrolls-timed-loop-status" class="message-meta" style="margin-top:0.55rem;">${renderScrollsLoopPills(timedLoop)}</div>
                        </div>
                        <div id="scrolls-console-cron" class="message-meta" style="margin-top:0.65rem;"><span class="meta-pill">fallback cron ${cronText.toLowerCase()}</span><span class="meta-pill">log ${escapeHtml(scrollsFmtBytes(consoleStat.size_bytes))}</span></div>
                    </div>
                    <div id="scrolls-improvement-loop" class="card scrolls-card-tight">
                        <h4>Daily Hermes Improvement Loop</h4>
                        <div class="message-meta" style="margin:0.5rem 0;">
                            <span class="meta-pill">${loop.ok ? 'wired' : 'attention'}</span>
                            <span class="meta-pill">jobs ${escapeHtml(String(loop.job_count ?? '—'))}</span>
                            <span class="meta-pill">legacy active ${escapeHtml(String(loop.active_legacy_count ?? '—'))}</span>
                        </div>
                        <p style="color:var(--text-dim);font-size:0.82rem;line-height:1.35;margin-top:0.4rem;">Once a day, Hermes should review Vesuvius AutoResearch results, Becomussy continuity notes, cron outputs, and dashboard friction to propose small efficiency improvements.</p>
                        <p style="color:var(--text-dim);font-size:0.8rem;margin-top:0.45rem;">Primary: ${escapeHtml(loopJob.name || 'self-improvement-loop not found')} · next ${escapeHtml(loopJob.next_run_at || '—')}</p>
                        ${loopBlockers.length ? `<p style="color:var(--warning);font-size:0.8rem;margin-top:0.4rem;">${escapeHtml(loopBlockers.join(' · '))}</p>` : ''}
                    </div>
                </div>
            </div>
            <div id="scrolls-runs" class="scrolls-grid" style="margin-top:0.75rem;">
                <div class="card scrolls-card-tight">
                    <h4>Experiment Leaderboard</h4>
                    <div class="scrolls-table-wrap">
                        <table style="width:100%;border-collapse:collapse;font-size:0.82rem;margin-top:0.35rem;">
                            <thead><tr style="color:var(--text-dim);border-bottom:1px solid var(--border-subtle);"><th style="text-align:left;padding:0.38rem 0.45rem;">Run</th><th style="text-align:right;padding:0.38rem 0.45rem;">${escapeHtml(metricLabel)}</th><th style="text-align:right;padding:0.38rem 0.45rem;">F1</th><th style="text-align:right;padding:0.38rem 0.45rem;">LR</th><th style="text-align:right;padding:0.38rem 0.45rem;">Depth</th><th style="text-align:right;padding:0.38rem 0.45rem;">Train→Val</th><th style="text-align:right;padding:0.38rem 0.45rem;">Time</th></tr></thead>
                            <tbody>${runRows}</tbody>
                        </table>
                    </div>
                    <div style="display:grid;grid-template-columns:minmax(0,0.7fr) minmax(280px,1.3fr);gap:0.7rem;margin-top:0.7rem;align-items:start;">
                        <div>
                            <h5>Metric Trend</h5>
                            <div style="height:86px;display:flex;align-items:flex-end;gap:3px;border:1px solid var(--border-subtle);background:rgba(0,0,0,0.18);padding:0.55rem;margin-top:0.35rem;">${trendHtml}</div>
                            <p style="color:var(--text-dim);font-size:0.72rem;margin-top:0.35rem;">Taller means better ${escapeHtml(metricLabel)}.</p>
                        </div>
                        <div id="scrolls-matrix" style="overflow:auto;">
                            <h5>Validation Matrix</h5>
                            <table style="width:100%;border-collapse:collapse;font-size:0.76rem;margin-top:0.35rem;"><thead><tr style="color:var(--text-dim);border-bottom:1px solid var(--border-subtle);"><th style="text-align:left;padding:0.3rem 0.35rem;">Train → Val</th><th style="text-align:left;padding:0.3rem 0.35rem;">Mode</th><th style="text-align:right;padding:0.3rem 0.35rem;">F1</th><th style="text-align:right;padding:0.3rem 0.35rem;">Runs</th></tr></thead><tbody>${(data.experiments?.validation_matrix || []).map((cell) => `<tr><td style="padding:0.3rem 0.35rem;font-family:monospace;">${escapeHtml(cell.train_segment_id || cell.train_scroll_id || '?')} → ${escapeHtml(cell.val_segment_id || cell.val_scroll_id || '?')}</td><td style="padding:0.3rem 0.35rem;">${escapeHtml(cell.validation_mode || 'unknown')}</td><td style="padding:0.3rem 0.35rem;text-align:right;">${scrollsFmtNumber(cell.best_val_f1)}</td><td style="padding:0.3rem 0.35rem;text-align:right;">${escapeHtml(String(cell.run_count ?? '—'))}</td></tr>`).join('') || '<tr><td colspan="4" style="padding:0.5rem;color:var(--text-dim);">No validation matrix yet.</td></tr>'}</tbody></table>
                        </div>
                    </div>
                    <div style="display:grid;grid-template-columns:minmax(0,1fr);gap:0.7rem;margin-top:0.7rem;align-items:start;">
                        <div>
                            <h5>Hypothesis Tracker</h5>
                            <div style="display:grid;gap:0.35rem;margin-top:0.4rem;max-height:250px;overflow:auto;">${hypothesisCards}</div>
                        </div>
                    </div>
                </div>
                <div style="display:grid;gap:0.75rem;">
                    <div class="card scrolls-card-tight"><h4>Configs</h4><div class="scrolls-micro-list">${configRows}</div></div>
                    <div class="card scrolls-card-tight"><h4>Prepared Data</h4><div class="scrolls-micro-list">${preparedRows}</div></div>
                    <div class="card scrolls-card-tight"><h4>Operations</h4><p style="color:var(--text-dim);font-size:0.8rem;line-height:1.35;margin-top:0.35rem;">Project: ${escapeHtml(data.project_root || '')}</p><pre style="white-space:pre-wrap;color:var(--text-dim);font-size:0.72rem;margin-top:0.45rem;max-height:90px;overflow:auto;">${escapeHtml(data.cron?.line || 'No Vesuvius cron line found')}</pre></div>
                </div>
            </div>
            <div id="scrolls-artifacts" class="card scrolls-card-tight" style="margin-top:0.75rem;">
                <h4>Artifact Library</h4>
                <p style="color:var(--text-dim);font-size:0.82rem;margin-top:0.35rem;">Click JSON, YAML, text, CSV, or log artifacts to preview them safely from the run directory.</p>
                <div style="display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:1rem;margin-top:0.75rem;align-items:start;">
                    <div><h5 style="margin-bottom:0.5rem;">Latest artifacts</h5><div style="display:grid;gap:0.45rem;">${artifactRows}</div></div>
                    <div><h5 style="margin-bottom:0.5rem;">Best-run artifacts</h5><div style="display:grid;gap:0.45rem;">${bestArtifactRows}</div></div>
                </div>
                <div id="scrolls-artifact-preview" class="activity-item" style="margin-top:1rem;min-height:4rem;color:var(--text-dim);">Select an artifact to preview metrics, configs, or logs here.</div>
            </div>
            <details id="scrolls-logs" class="card scrolls-card-tight" style="margin-top:0.75rem;"><summary style="cursor:pointer;"><strong>AutoResearch Log Tail</strong></summary><pre style="white-space:pre-wrap;max-height:260px;overflow:auto;font-size:0.78rem;color:var(--text-dim);margin-top:0.5rem;">${escapeHtml(logLines.join('\n') || 'No log lines yet.')}</pre></details>
        `;
        const btn = document.getElementById('scrolls-autoresearch-btn');
        if (btn) btn.disabled = !!data.lock_active;
        toggleScrollsConsoleAutoRefresh();
        if (silent) container.scrollTop = previousScrollTop;
        startScrollsResearchAutoRefresh();
    } catch (err) {
        if (!silent) container.innerHTML = `<div class="card" style="border-color:var(--error);color:var(--error);">Failed to load Vesuvius AutoResearch: ${escapeHtml(String(err))}</div>`;
        else showToast(`Vesuvius AutoResearch refresh failed: ${err}`, true);
    } finally {
        scrollsResearchLoading = false;
    }
}

async function triggerScrollsAutoresearch() {
    const btn = document.getElementById('scrolls-autoresearch-btn');
    if (btn) btn.disabled = true;
    try {
        const res = await scrollsFetchJson('/api/scrolls/autoresearch/trigger', { method: 'POST' });
        showToast(`AutoResearch started (pid ${res.pid})`);
        setTimeout(loadScrollsResearch, 1200);
    } catch (err) {
        showToast(`Could not start AutoResearch: ${err}`, true);
    } finally {
        if (btn) btn.disabled = false;
    }
}

async function startScrollsTimedLoop() {
    const minutes = Number(document.getElementById('scrolls-loop-minutes')?.value || 15);
    const btn = document.getElementById('scrolls-loop-start-btn');
    if (btn) btn.disabled = true;
    try {
        const res = await scrollsFetchJson('/api/scrolls/autoresearch/loop/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ minutes }),
        });
        showToast(`Timed AutoResearch loop started for ${minutes} min`);
        const timedLoopEl = document.getElementById('scrolls-timed-loop-status');
        if (timedLoopEl) timedLoopEl.innerHTML = renderScrollsLoopPills(res.timed_loop);
        startScrollsResearchAutoRefresh();
        setTimeout(() => loadScrollsResearch({ silent: true }), 800);
    } catch (err) {
        showToast(`Could not start timed loop: ${err}`, true);
    } finally {
        if (btn) btn.disabled = false;
    }
}

async function stopScrollsTimedLoop() {
    const btn = document.getElementById('scrolls-loop-stop-btn');
    if (btn) btn.disabled = true;
    try {
        const res = await scrollsFetchJson('/api/scrolls/autoresearch/loop/stop', { method: 'POST' });
        showToast('Timed loop will stop after the current run');
        const timedLoopEl = document.getElementById('scrolls-timed-loop-status');
        if (timedLoopEl) timedLoopEl.innerHTML = renderScrollsLoopPills(res.timed_loop);
        setTimeout(() => loadScrollsResearch({ silent: true }), 800);
    } catch (err) {
        showToast(`Could not stop timed loop: ${err}`, true);
    } finally {
        if (btn) btn.disabled = false;
    }
}

async function loadScrollsArtifact(encodedPath) {
    const preview = document.getElementById('scrolls-artifact-preview');
    if (!preview) return;
    preview.innerHTML = '<span style="color:var(--text-dim);">Loading artifact...</span>';
    try {
        const data = await scrollsFetchJson(`/api/scrolls/artifact?path=${encodedPath}`);
        const body = typeof data.preview === 'string'
            ? data.preview
            : data.preview !== null && data.preview !== undefined
                ? JSON.stringify(data.preview, null, 2)
                : (data.preview_error || 'No preview available.');
        preview.innerHTML = `
            <div style="display:flex;justify-content:space-between;gap:0.75rem;flex-wrap:wrap;margin-bottom:0.6rem;">
                <div><strong>${escapeHtml(data.name || 'artifact')}</strong><div style="font-size:0.75rem;color:var(--text-dim);font-family:monospace;">${escapeHtml(data.path || '')}</div></div>
                <span class="meta-pill">${escapeHtml(data.kind || 'file')} · ${scrollsFmtBytes(data.size_bytes)}${data.truncated ? ' · truncated' : ''}</span>
            </div>
            <pre style="white-space:pre-wrap;max-height:420px;overflow:auto;font-size:0.78rem;color:var(--text);background:rgba(0,0,0,0.22);border:1px solid var(--border-subtle);border-radius:8px;padding:0.75rem;">${escapeHtml(body)}</pre>
        `;
    } catch (err) {
        preview.innerHTML = `<span style="color:var(--error);">Could not load artifact: ${escapeHtml(String(err))}</span>`;
    }
}

async function runScrollsConfig(name) {
    try {
        const res = await scrollsFetchJson('/api/scrolls/experiments/run', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ config: name }),
        });
        showToast(`Experiment started (pid ${res.pid})`);
        setTimeout(loadScrollsResearch, 1200);
    } catch (err) {
        showToast(`Could not start experiment: ${err}`, true);
    }
}

async function loadSchedulePanel() {
    const container = document.getElementById('schedule-container');
    if (!container) return;
    container.innerHTML = '<div style="text-align:center;color:var(--text-dim);padding:2rem;">Loading schedules...</div>';
    try {
        const data = await fetch('/api/cron/schedule').then(r => r.json());
        const schedules = data.schedules || [];
        if (!schedules.length) {
            container.innerHTML = '<div class="schedule-empty-state">No cron schedules found. Cron sessions will appear here once they are recorded.</div>';
            return;
        }
        container.innerHTML = schedules.map(renderScheduleCard).join('');
        startCountdownUpdater();
    } catch (e) {
        container.innerHTML = `<div class="schedule-empty-state">Failed to load schedules: ${escapeHtml(e.message)}</div>`;
    }
}

function startCountdownUpdater() {
    if (scheduleCountdownInterval) {
        clearInterval(scheduleCountdownInterval);
    }
    scheduleCountdownInterval = setInterval(() => {
        document.querySelectorAll('.next-run-countdown[data-next-run]').forEach(el => {
            const iso = el.getAttribute('data-next-run');
            if (iso) {
                el.textContent = relativeTime(iso);
            }
        });
    }, 60000);
}
// === END TRACK C ===

// === TRACK B: SessionSearch ===
function renderSessionListItems(items) {
    if (!items || !items.length) return '';
    return items.map(s => {
        const id = s.id || s.session_id;
        const title = s.title || 'Untitled';
        const source = s.source || '';
        const summary = s.summary || s.preview || 'No preview';
        const date = formatSessionDate(s.started_at || s.created_at);
        const matchContext = s.match_context || '';
        return `
            <div class="session-item" onclick="viewSession('${id}')">
                <div class="session-info">
                    <h4>${escapeHtml(title)}${source ? ' <span style="font-size:0.75rem;color:var(--text-dim);font-weight:normal;">(' + escapeHtml(source) + ')</span>' : ''}</h4>
                    <p>${escapeHtml(summary)} · ${escapeHtml(date)}</p>
                    ${matchContext ? `<p class="search-result-context">${escapeHtml(matchContext)}</p>` : ''}
                </div>
                <div class="session-actions">
                    <button class="btn" onclick="event.stopPropagation();attachChatToSession('${id}')">Use in Chat</button>
                    <button class="export-btn" onclick="event.stopPropagation();exportSession('${id}')" title="Export JSON">Export</button>
                    <button class="btn" onclick="event.stopPropagation();deleteSession('${id}')">Delete</button>
                </div>
            </div>
        `;
    }).join('');
}

const sessionSearchState = {
    q: '',
    status: 'all',
    dateFrom: null,
    dateTo: null,
    offset: 0,
    limit: 20,
    debounceTimer: null
};

function renderSearchPagination(total, offset, limit) {
    const totalPages = Math.ceil(total / limit);
    const currentPage = Math.floor(offset / limit);
    if (totalPages <= 1) return '';
    return `
        <button onclick="changeSearchPage(${offset - limit})" ${offset === 0 ? 'disabled' : ''}>Prev</button>
        <span>Page ${currentPage + 1} of ${totalPages}</span>
        <button onclick="changeSearchPage(${offset + limit})" ${currentPage >= totalPages - 1 ? 'disabled' : ''}>Next</button>
    `;
}

function changeSearchPage(newOffset) {
    sessionSearchState.offset = Math.max(0, newOffset);
    runSessionSearch();
}

async function runSessionSearch() {
    const qInput = document.getElementById('session-search-input');
    const statusInput = document.getElementById('session-search-status');
    const dateFromInput = document.getElementById('session-search-date-from');
    const dateToInput = document.getElementById('session-search-date-to');

    sessionSearchState.q = (qInput?.value || '').trim();
    sessionSearchState.status = (statusInput?.value || 'all').trim();
    sessionSearchState.dateFrom = (dateFromInput?.value || '').trim() || null;
    sessionSearchState.dateTo = (dateToInput?.value || '').trim() || null;

    const params = new URLSearchParams();
    if (sessionSearchState.q) params.set('q', sessionSearchState.q);
    if (sessionSearchState.status && sessionSearchState.status !== 'all') params.set('status', sessionSearchState.status);
    if (sessionSearchState.dateFrom) params.set('date_from', sessionSearchState.dateFrom);
    if (sessionSearchState.dateTo) params.set('date_to', sessionSearchState.dateTo);
    params.set('limit', String(sessionSearchState.limit));
    params.set('offset', String(sessionSearchState.offset));

    const url = '/api/sessions/search?' + params.toString();
    log('req', `GET ${url}`);

    try {
        const data = await fetch(url).then(r => r.json());
        log('res', `Search found ${data.results.length} sessions (total: ${data.total})`);

        const list = document.getElementById('sessions-list');
        const pag = document.getElementById('sessions-pagination');
        const stats = document.getElementById('sessions-stats');

        if (stats) stats.textContent = `${data.total} session${data.total !== 1 ? 's' : ''}`;

        if (!data.results.length) {
            list.innerHTML = '<div class="search-empty-state">No sessions match your search</div>';
            pag.innerHTML = '';
            return;
        }

        list.innerHTML = renderSessionListItems(data.results);
        pag.innerHTML = renderSearchPagination(data.total, data.offset, data.limit);
    } catch (e) {
        log('err', 'Session search failed: ' + e.message);
        const list = document.getElementById('sessions-list');
        list.innerHTML = '<div class="search-empty-state">Search failed. Please try again.</div>';
    }
}

function debounceSessionSearch() {
    if (sessionSearchState.debounceTimer) clearTimeout(sessionSearchState.debounceTimer);
    sessionSearchState.debounceTimer = setTimeout(() => {
        sessionSearchState.offset = 0;
        runSessionSearch();
    }, 300);
}

function clearSessionSearch() {
    const qInput = document.getElementById('session-search-input');
    const statusInput = document.getElementById('session-search-status');
    const dateFromInput = document.getElementById('session-search-date-from');
    const dateToInput = document.getElementById('session-search-date-to');
    if (qInput) qInput.value = '';
    if (statusInput) statusInput.value = 'all';
    if (dateFromInput) dateFromInput.value = '';
    if (dateToInput) dateToInput.value = '';
    sessionSearchState.q = '';
    sessionSearchState.status = 'all';
    sessionSearchState.dateFrom = null;
    sessionSearchState.dateTo = null;
    sessionSearchState.offset = 0;
    sessionsPage = 0;
    loadSessions();
}
// === END TRACK B ===
