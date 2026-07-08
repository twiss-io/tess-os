// tess-gui test helper — minimal jsdom global environment.
//
// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Twiss
//
// Installs a fresh JSDOM document's globals so the real client modules
// (which reference document/window/EventTarget/etc as free globals, exactly
// as they do in a browser) can be imported and exercised directly in Node —
// no reimplementation of their logic in the test.
import { JSDOM } from 'jsdom';

export function installDomEnv(html = '<!doctype html><html><body></body></html>', url = 'http://localhost/') {
  const dom = new JSDOM(html, { url, pretendToBeVisual: true });
  const { window } = dom;
  globalThis.window = window;
  globalThis.document = window.document;
  globalThis.EventTarget = window.EventTarget;
  globalThis.Event = window.Event;
  globalThis.MessageEvent = window.MessageEvent;
  globalThis.CustomEvent = window.CustomEvent;
  globalThis.KeyboardEvent = window.KeyboardEvent;
  globalThis.MouseEvent = window.MouseEvent;
  globalThis.HTMLElement = window.HTMLElement;
  globalThis.Node = window.Node;
  globalThis.history = window.history;
  globalThis.location = window.location;
  return dom;
}
