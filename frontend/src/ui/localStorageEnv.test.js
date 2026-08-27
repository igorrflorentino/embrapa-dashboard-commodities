// localStorageEnv.test.js — the test environment must give every test a WORKING
// localStorage, whatever Node major the developer happens to be on.
//
// Node 26 defines its own `localStorage` global behind `--localstorage-file`. Without
// that flag it resolves to `undefined`, and since Vitest's jsdom environment merges
// `window` into `globalThis` it SHADOWS jsdom's working Storage — turning every
// `getItem` into "Cannot read properties of undefined" and producing 36 failures in
// AppShell.cov.test.jsx that look like our bug and are not. CI runs the /.nvmrc major
// (24), where none of this happens, so the breakage only ever hits a local machine.
//
// vitest.setup.js repairs it. This pins the invariant so the repair cannot rot away
// unnoticed: if someone removes it, this fails on a modern Node instead of 36 tests
// failing somewhere unrelated with a misleading message.

import { afterEach, describe, expect, it } from 'vitest';

describe('test environment — localStorage', () => {
  afterEach(() => { localStorage.removeItem('__probe__'); });

  it('exists and round-trips a value', () => {
    expect(localStorage).toBeTruthy();
    localStorage.setItem('__probe__', 'valor');
    expect(localStorage.getItem('__probe__')).toBe('valor');
  });

  it('returns null for an absent key rather than undefined', () => {
    // The app branches on `=== null`; `undefined` would silently take the wrong path.
    expect(localStorage.getItem('__nunca_gravado__')).toBeNull();
  });

  it('removes and clears', () => {
    localStorage.setItem('__probe__', 'x');
    localStorage.removeItem('__probe__');
    expect(localStorage.getItem('__probe__')).toBeNull();
  });

  it('is reachable through window as well as the bare global', () => {
    // The UI reads it both ways; on a merged jsdom global they must be one object.
    window.localStorage.setItem('__probe__', 'via-window');
    expect(localStorage.getItem('__probe__')).toBe('via-window');
  });
});
