'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

class FakeClassList {
    constructor() { this.values = new Set(); }
    add(...names) { names.forEach(name => this.values.add(name)); }
    remove(...names) { names.forEach(name => this.values.delete(name)); }
    contains(name) { return this.values.has(name); }
    toggle(name, force) {
        const enabled = force === undefined ? !this.contains(name) : Boolean(force);
        if (enabled) this.add(name); else this.remove(name);
        return enabled;
    }
}

class FakeElement {
    constructor(role = '') {
        this.role = role;
        this.id = '';
        this.hidden = false;
        this.inert = false;
        this.disabled = false;
        this.value = '';
        this.textContent = '';
        this.innerHTML = '';
        this.title = '';
        this.className = '';
        this.classList = new FakeClassList();
        this.style = {};
        this.dataset = {};
        this.attributes = new Map();
        this.listeners = new Map();
        this.children = [];
        this.parent = null;
        this.removed = false;
        this.focused = false;
    }
    addEventListener(name, callback) {
        if (!this.listeners.has(name)) this.listeners.set(name, []);
        this.listeners.get(name).push(callback);
    }
    dispatch(name, event = {}) {
        for (const callback of this.listeners.get(name) || []) callback(event);
    }
    setAttribute(name, value) { this.attributes.set(name, String(value)); }
    getAttribute(name) { return this.attributes.get(name); }
    appendChild(child) {
        if (child.parent) child.parent.children = child.parent.children.filter(existing => existing !== child);
        child.parent = this;
        child.removed = false;
        this.children.push(child);
        return child;
    }
    remove() {
        this.removed = true;
        if (this.parent) this.parent.children = this.parent.children.filter(child => child !== this);
    }
    focus() { this.focused = true; }
    scrollIntoView(options) { this.scrollOptions = options; }
    querySelector(selector) {
        const match = selector.match(/data-terminal-role="([^"]+)"/);
        return match ? this.roles?.[match[1]] || null : null;
    }
    cloneNode() { return createTerminalWindow(); }
    getBoundingClientRect() {
        return {
            left: Number.parseFloat(this.style.left) || 0,
            top: Number.parseFloat(this.style.top) || 0,
            width: Number.parseFloat(this.style.width) || 680,
            height: this.classList.contains('is-minimized') ? 42 : (Number.parseFloat(this.style.height) || 400),
        };
    }
    setPointerCapture() {}
    releasePointerCapture() {}
    hasPointerCapture() { return true; }
}

function createTerminalWindow() {
    const root = new FakeElement('window');
    root.classList.add('terminal-window');
    root.roles = {};
    for (const role of ['header', 'body', 'screen', 'title', 'status', 'dock', 'minimize', 'maximize', 'close']) {
        root.roles[role] = new FakeElement(role);
    }
    return root;
}

class FakeTerminal {
    static instances = [];
    constructor(options) {
        this.options = options;
        this.cols = 80;
        this.rows = 24;
        this.writes = [];
        this.selection = '';
        this.pastes = [];
        this.disposed = false;
        FakeTerminal.instances.push(this);
    }
    loadAddon(addon) { this.addon = addon; }
    open(element) { this.element = element; }
    onData(callback) { this.dataCallback = callback; }
    attachCustomKeyEventHandler(callback) { this.keyEventHandler = callback; }
    hasSelection() { return Boolean(this.selection); }
    getSelection() { return this.selection; }
    paste(text) { this.pastes.push(text); }
    write(data) { this.writes.push(data); }
    focus() { this.focused = true; }
    dispose() { this.disposed = true; }
}

class FakeFitAddon { fit() { this.fitCount = (this.fitCount || 0) + 1; } }
class FakeResizeObserver { constructor(callback) { this.callback = callback; } observe() {} disconnect() { this.disconnected = true; } }

class FakeWebSocket {
    static CONNECTING = 0;
    static OPEN = 1;
    static CLOSED = 3;
    static instances = [];
    constructor(url) {
        this.url = url;
        this.readyState = FakeWebSocket.CONNECTING;
        this.listeners = new Map();
        this.sent = [];
        FakeWebSocket.instances.push(this);
    }
    addEventListener(name, callback) {
        if (!this.listeners.has(name)) this.listeners.set(name, []);
        this.listeners.get(name).push(callback);
    }
    emit(name, event = {}) {
        if (name === 'open') this.readyState = FakeWebSocket.OPEN;
        if (name === 'close') this.readyState = FakeWebSocket.CLOSED;
        for (const callback of this.listeners.get(name) || []) callback(event);
    }
    send(data) { this.sent.push(data); }
    close(code, reason) { this.readyState = FakeWebSocket.CLOSED; this.closeArgs = [code, reason]; }
}

const storage = new Map([
    ['hermes_terminal_window_v1', JSON.stringify({ x: 11, y: 12, width: 500, height: 320, minimized: false })],
]);
const localStorage = {
    getItem: key => storage.has(key) ? storage.get(key) : null,
    setItem: (key, value) => storage.set(key, String(value)),
    removeItem: key => storage.delete(key),
};
const clipboardWrites = [];
const navigator = {
    clipboard: {
        writeText: async text => { clipboardWrites.push(text); },
        readText: async () => 'pasted text',
    },
};

const elements = new Map();
for (const id of [
    'terminal-window-host', 'terminal-launcher', 'terminal-launcher-count',
    'terminal-launcher-status', 'terminal-disabled-message', 'terminal-auth',
    'terminal-access-token', 'terminal-auth-submit', 'terminal-auth-error',
    'terminal-dock', 'dashboard-workspace', 'terminal-column',
    'terminal-column-stack', 'terminal-column-resizer',
]) elements.set(id, new FakeElement());
const template = new FakeElement();
template.content = { firstElementChild: createTerminalWindow() };
elements.set('terminal-window-template', template);

const document = {
    documentElement: { dataset: { theme: 'dark' } },
    getElementById: id => elements.get(id) || null,
    createElement: () => new FakeElement(),
    head: new FakeElement(),
};
const windowListeners = new Map();
const windowObject = {
    innerWidth: 1280,
    innerHeight: 800,
    location: { href: 'http://localhost/dashboard', protocol: 'http:' },
    Terminal: FakeTerminal,
    FitAddon: { FitAddon: FakeFitAddon },
    addEventListener(name, callback) {
        if (!windowListeners.has(name)) windowListeners.set(name, []);
        windowListeners.get(name).push(callback);
    },
    dispatch(name, event = {}) {
        for (const callback of windowListeners.get(name) || []) callback(event);
    },
    setTimeout: () => 1,
    setInterval: () => 1,
    clearTimeout() {},
};
windowObject.window = windowObject;

const context = {
    window: windowObject,
    document,
    localStorage,
    navigator,
    WebSocket: FakeWebSocket,
    ResizeObserver: FakeResizeObserver,
    URL,
    ArrayBuffer,
    Uint8Array,
    Blob,
    console,
    Promise,
    JSON,
    Number,
    Math,
    requestAnimationFrame: callback => { callback(); return 1; },
    atob: value => Buffer.from(value, 'base64').toString('binary'),
};

async function flush() {
    await new Promise(resolve => setImmediate(resolve));
    await new Promise(resolve => setImmediate(resolve));
}

async function main() {
    const source = fs.readFileSync(process.argv[2], 'utf8');
    const start = source.indexOf('// Independent, lazily loaded browser terminal windows');
    const endMarker = '\n})();';
    const end = source.indexOf(endMarker, start) + endMarker.length;
    assert.ok(start >= 0 && end > start, 'terminal block was not found');

    context.fetch = async url => {
        assert.equal(url, '/api/terminal/status');
        return { ok: true, json: async () => ({ enabled: true, requires_auth: false, max_sessions: 2, detach_ttl_seconds: 86400 }) };
    };
    vm.runInNewContext(source.slice(start, end), context, { filename: 'dashboard-terminal.js' });
    await flush();

    const manager = windowObject.hermesTerminalController;
    assert.ok(manager instanceof windowObject.BrowserTerminalManager);
    assert.equal(storage.has('hermes_terminal_window_v1'), false);
    const migrated = JSON.parse(storage.get('hermes_terminal_windows_v2'));
    assert.equal(migrated.slots.length, 1);
    assert.equal(migrated.slots[0].width, 500);

    const first = windowObject.openTerminalWindow();
    const second = windowObject.openTerminalWindow();
    await flush();
    assert.equal(manager.controllers.size, 2);
    assert.equal(FakeWebSocket.instances.length, 2);
    assert.notEqual(first.windowEl.id, second.windowEl.id);
    assert.notEqual(first.titleEl.id, second.titleEl.id);
    assert.notEqual(first.statusEl.id, second.statusEl.id);
    assert.equal(first.windowEl.getAttribute('aria-modal'), undefined);
    assert.equal(elements.get('terminal-launcher-count').textContent, '2');

    const firstSocket = FakeWebSocket.instances[0];
    const secondSocket = FakeWebSocket.instances[1];
    firstSocket.emit('open');
    secondSocket.emit('open');
    assert.equal(firstSocket.sent.some(value => JSON.parse(value).type === 'resize'), true);
    assert.equal(secondSocket.sent.some(value => JSON.parse(value).type === 'resize'), true);
    firstSocket.emit('message', { data: JSON.stringify({ type: 'ready', terminal_id: 'one', resume_token: 'token-one' }) });
    secondSocket.emit('message', { data: JSON.stringify({ type: 'ready', terminal_id: 'two', resume_token: 'token-two' }) });
    firstSocket.emit('message', { data: JSON.stringify({ type: 'output', data: 'first output' }) });
    secondSocket.emit('message', { data: JSON.stringify({ type: 'output', data: 'second output' }) });
    assert.deepEqual(first.terminal.writes, ['first output']);
    assert.deepEqual(second.terminal.writes, ['second output']);
    first.terminal.selection = 'copied text';
    assert.equal(first.terminal.keyEventHandler({ type: 'keydown', key: 'c', ctrlKey: true }), false);
    await flush();
    assert.deepEqual(clipboardWrites, ['copied text']);
    first.terminal.selection = '';
    assert.equal(first.terminal.keyEventHandler({ type: 'keydown', key: 'c', ctrlKey: true }), true);
    assert.equal(first.terminal.keyEventHandler({ type: 'keydown', key: 'v', ctrlKey: true }), false);
    await flush();
    assert.deepEqual(first.terminal.pastes, ['pasted text']);
    assert.equal(first.terminalId, 'one');
    assert.equal(second.terminalId, 'two');
    const savedSessions = JSON.parse(storage.get('hermes_terminal_sessions_v1')).sessions;
    assert.equal(savedSessions.length, 2);
    assert.deepEqual(new Set(savedSessions.map(record => record.terminalId)), new Set(['one', 'two']));
    assert.equal(JSON.stringify(savedSessions).includes('first output'), false);
    assert.equal(elements.get('terminal-dock').hidden, false);
    assert.match(elements.get('terminal-dock').innerHTML, /data-terminal-key="terminal-1"/);
    assert.match(elements.get('terminal-dock').innerHTML, /data-terminal-key="terminal-2"/);

    const terminalsBeforeDock = FakeTerminal.instances.length;
    const socketsBeforeDock = FakeWebSocket.instances.length;
    const firstFloatingGeometry = { ...first.geometry };
    first.toggleDocked();
    second.toggleDocked();
    assert.equal(first.docked, true);
    assert.equal(second.docked, true);
    assert.equal(first.windowEl.parent, elements.get('terminal-column-stack'));
    assert.equal(second.windowEl.parent, elements.get('terminal-column-stack'));
    assert.deepEqual(elements.get('terminal-column-stack').children.slice(-2), [first.windowEl, second.windowEl]);
    assert.equal(elements.get('terminal-column').hidden, false);
    assert.equal(elements.get('dashboard-workspace').classList.contains('has-terminal-column'), true);
    assert.equal(first.dockButtonEl.getAttribute('aria-pressed'), 'true');
    assert.equal(first.socket, firstSocket);
    assert.equal(FakeTerminal.instances.length, terminalsBeforeDock);
    assert.equal(FakeWebSocket.instances.length, socketsBeforeDock);
    first.windowEl.style.width = '333px';
    first.resizeObserver.callback();
    assert.equal(first.geometry.width, firstFloatingGeometry.width);
    assert.equal(JSON.parse(storage.get('hermes_terminal_windows_v2')).slots[first.slot].docked, true);
    assert.ok(first.geometry.dockOrder < second.geometry.dockOrder);

    first.toggleDocked();
    assert.equal(first.docked, false);
    assert.equal(first.windowEl.parent, elements.get('terminal-window-host'));
    assert.equal(first.windowEl.style.width, `${firstFloatingGeometry.width}px`);
    assert.equal(first.windowEl.style.height, `${firstFloatingGeometry.height}px`);
    assert.equal(first.socket, firstSocket);
    assert.equal(first.dockButtonEl.getAttribute('aria-pressed'), 'false');

    manager.applyColumnWidth(610, true);
    assert.equal(JSON.parse(storage.get('hermes_terminal_windows_v2')).columnWidth, 610);
    assert.equal(elements.get('terminal-column').style.width, '610px');
    windowObject.innerWidth = 700;
    manager.handleViewportResize();
    assert.equal(manager.columnWidth, 610);
    assert.equal(elements.get('terminal-column').style.width, '380px');
    assert.equal(JSON.parse(storage.get('hermes_terminal_windows_v2')).columnWidth, 610);
    windowObject.innerWidth = 1280;
    manager.handleViewportResize();
    assert.equal(elements.get('terminal-column').style.width, '610px');
    manager.applyColumnWidth(1000, true);
    assert.equal(elements.get('terminal-column').style.width, '960px');
    manager.activateDock(second.key);
    assert.equal(second.windowEl.scrollOptions.block, 'nearest');
    assert.equal(second.windowEl.classList.contains('is-minimized'), false);

    const socketsBeforeRestore = FakeWebSocket.instances.length;
    const restoredManager = new windowObject.BrowserTerminalManager();
    restoredManager.enabled = true;
    restoredManager.maxSessions = 2;
    restoredManager.detachTtlSeconds = 86400;
    restoredManager.restoreSessions();
    await flush();
    assert.equal(restoredManager.controllers.size, 2);
    const restoreSockets = FakeWebSocket.instances.slice(socketsBeforeRestore);
    assert.equal(restoreSockets.length, 2);
    assert.deepEqual(
        new Set(restoreSockets.map(socket => new URL(socket.url).searchParams.get('terminal_id'))),
        new Set(['one', 'two']),
    );
    const duplicateOne = [...restoredManager.controllers.values()].find(controller => controller.terminalId === 'one');
    const duplicateOneSocket = restoreSockets.find(socket => new URL(socket.url).searchParams.get('terminal_id') === 'one');
    duplicateOneSocket.emit('close', { code: 4409, reason: 'already attached' });
    assert.equal(duplicateOne.waitingElsewhere, true);

    const closeFramesBeforePageHide = firstSocket.sent.filter(value => JSON.parse(value).type === 'close').length;
    windowObject.dispatch('pagehide');
    assert.equal(firstSocket.sent.filter(value => JSON.parse(value).type === 'close').length, closeFramesBeforePageHide);

    manager.applyTheme('light');
    assert.equal(first.terminal.options.theme.background, '#f7f7f4');
    assert.equal(second.terminal.options.theme.background, '#f7f7f4');

    const priorZ = Math.max(first.zIndex, second.zIndex);
    assert.equal(windowObject.openTerminalWindow(), null);
    assert.equal(manager.controllers.size, 2);
    assert.ok(Math.max(first.zIndex, second.zIndex) > priorZ);
    assert.equal(elements.get('terminal-launcher').classList.contains('at-limit'), true);

    manager.activateDock(first.key);
    assert.equal(first.bodyEl.hidden, true);
    assert.equal(first.bodyEl.inert, true);
    assert.equal(first.windowEl.classList.contains('is-minimized'), true);
    assert.match(elements.get('terminal-dock').innerHTML, /is-minimized/);
    assert.equal(first.socket, firstSocket);
    manager.activateDock(first.key);
    assert.equal(first.windowEl.classList.contains('is-minimized'), false);

    const firstSlot = first.slot;
    first.close();
    assert.equal(first.disposed, true);
    assert.equal(first.terminal, null);
    assert.equal(firstSocket.sent.some(value => JSON.parse(value).type === 'close'), true);
    assert.equal(manager.controllers.size, 1);
    assert.equal(second.disposed, false);
    assert.equal(second.socket, secondSocket);
    assert.equal(JSON.parse(storage.get('hermes_terminal_sessions_v1')).sessions.some(record => record.terminalId === 'one'), false);
    restoredManager.refreshPersistedSessions();
    assert.equal(JSON.parse(storage.get('hermes_terminal_sessions_v1')).sessions.some(record => record.terminalId === 'one'), false);

    const third = windowObject.openTerminalWindow();
    await flush();
    assert.equal(third.slot, firstSlot);
    assert.notEqual(third.windowEl.id, second.windowEl.id);

    const thirdSocket = FakeWebSocket.instances.at(-1);
    thirdSocket.emit('open');
    thirdSocket.emit('message', { data: JSON.stringify({ type: 'ready', terminal_id: 'three', resume_token: 'token-three' }) });
    const writesBeforeStaleMessage = third.terminal.writes.length;
    const socketsBeforeExpiry = FakeWebSocket.instances.length;
    thirdSocket.emit('close', { code: 4404, reason: 'expired' });
    assert.equal(FakeWebSocket.instances.length, socketsBeforeExpiry);
    assert.equal(third.terminalId, null);
    assert.equal(third.statusEl.textContent, 'expired');
    assert.equal(JSON.parse(storage.get('hermes_terminal_sessions_v1')).sessions.some(record => record.terminalId === 'three'), false);
    thirdSocket.emit('message', { data: JSON.stringify({ type: 'output', data: 'stale output' }) });
    assert.equal(third.terminal.writes.length, writesBeforeStaleMessage);

    const socketsBeforeInvalidResume = FakeWebSocket.instances.length;
    secondSocket.emit('close', { code: 4403, reason: 'Invalid terminal resume token' });
    assert.equal(FakeWebSocket.instances.length, socketsBeforeInvalidResume);
    assert.equal(second.terminalId, null);
    assert.equal(JSON.parse(storage.get('hermes_terminal_sessions_v1')).sessions.some(record => record.terminalId === 'two'), false);

    second.connect();
    const secondFreshSocket = FakeWebSocket.instances.at(-1);
    secondFreshSocket.emit('open');
    assert.equal(secondFreshSocket.sent.some(value => JSON.parse(value).type === 'resize'), true);
    const socketsBeforeAccessDenied = FakeWebSocket.instances.length;
    secondFreshSocket.emit('close', { code: 4403, reason: 'Terminal request origin is not allowed.' });
    await flush();
    assert.equal(FakeWebSocket.instances.length, socketsBeforeAccessDenied);
    assert.equal(second.statusEl.textContent, 'Terminal access denied');

    third.connect();
    const limitedSocket = FakeWebSocket.instances.at(-1);
    const socketsBeforeLimit = FakeWebSocket.instances.length;
    limitedSocket.emit('close', { code: 4429, reason: 'session limit' });
    assert.equal(FakeWebSocket.instances.length, socketsBeforeLimit);
    assert.equal(third.statusEl.textContent, 'session limit');

    manager.authRequired = true;
    const authOne = manager.requestAuthorization(second);
    const authTwo = manager.requestAuthorization(third);
    assert.equal(authOne, authTwo);
    assert.equal(elements.get('terminal-auth').hidden, false);

    console.log('terminal frontend harness: ok');
}

main().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
