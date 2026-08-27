// vitest.setup.js — jsdom has no bootstrap-globals.js, so replicate the globals the UI
// modules rely on. The CLASSIC JSX runtime (pinned in vite.config.js for dev, build AND
// Vitest — audit DEV-1) compiles JSX to `React.createElement(...)` against the global
// `window.React`, and the ui/ modules read React as a bare global; both need it set here.
import React from 'react';
import * as ReactDOMClient from 'react-dom/client';

if (typeof globalThis.global === 'undefined') globalThis.global = globalThis;
if (typeof globalThis.process === 'undefined') globalThis.process = { env: {} };
window.React = React;
window.ReactDOM = ReactDOMClient;

// ── localStorage: repair the one Node ≥26 breaks ─────────────────────────────
//
// Node 26 ships its own `localStorage` global, gated behind `--localstorage-file`.
// Without that flag the global is still DEFINED — as a getter returning `undefined`
// — and because Vitest's jsdom environment merges `window` into `globalThis`, that
// getter SHADOWS the working Storage jsdom installed. Every `localStorage.getItem`
// then dies with "Cannot read properties of undefined", which surfaced as 36 failures
// in AppShell.cov.test.jsx that look exactly like a bug in our code and are not.
//
// CI runs the Node major in /.nvmrc (24), where none of this exists — so the symptom
// only ever hits a developer whose local Node is newer, and it costs them an hour
// before they think to check `node -v`. The descriptor is `configurable: true`, so we
// can simply put a working Storage back.
//
// Deliberately scoped: this runs ONLY when localStorage is missing or unusable. On
// Node 24 jsdom's own implementation is untouched.
function installMemoryStorage() {
  const store = new Map();
  const storage = {
    getItem: (k) => (store.has(String(k)) ? store.get(String(k)) : null),
    setItem: (k, v) => { store.set(String(k), String(v)); },
    removeItem: (k) => { store.delete(String(k)); },
    clear: () => { store.clear(); },
    key: (i) => [...store.keys()][i] ?? null,
    get length() { return store.size; },
  };
  Object.defineProperty(globalThis, 'localStorage', {
    value: storage, writable: true, configurable: true,
  });
  if (globalThis.window && globalThis.window !== globalThis) {
    Object.defineProperty(globalThis.window, 'localStorage', {
      value: storage, writable: true, configurable: true,
    });
  }
}

function localStorageWorks() {
  try {
    const ls = globalThis.localStorage;
    if (!ls) return false;
    const probe = '__vitest_probe__';
    ls.setItem(probe, '1');
    const ok = ls.getItem(probe) === '1';
    ls.removeItem(probe);
    return ok;
  } catch {
    return false;
  }
}

if (!localStorageWorks()) installMemoryStorage();
