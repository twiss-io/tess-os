// Tess OS Mission Control — tiny DOM helper.
//
// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Twiss
//
// Every renderer builds DOM via el()/textContent instead of innerHTML +
// string interpolation — mission prompts, command names, and roster data
// are all untrusted-ish text that must never be parsed as markup. There is
// deliberately no innerHTML escape hatch here.

export function el(tag, props = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value == null) continue;
    if (key === 'className') node.className = value;
    else if (key === 'dataset') Object.assign(node.dataset, value);
    else if (key.startsWith('on') && typeof value === 'function') {
      node.addEventListener(key.slice(2).toLowerCase(), value);
    } else if (typeof value === 'boolean') {
      if (value) node.setAttribute(key, '');
    } else {
      node.setAttribute(key, value);
    }
  }
  for (const child of Array.isArray(children) ? children : [children]) {
    if (child == null) continue;
    node.appendChild(typeof child === 'string' ? document.createTextNode(child) : child);
  }
  return node;
}

export function clear(node) {
  node.replaceChildren();
}

// Assigns an incrementing animation-delay across `elements` (in reading
// order) so a first paint reads as a staggered cascade instead of every
// element firing at once. Keyed by `container` (a WeakSet, not a shared
// counter) so a container that rebuilds its children on every update — the
// metrics band re-renders on every mission launch/finish — replays its
// entrance once, not on every rebuild. Delay is capped at `max` steps so a
// long list settles together rather than trailing into a multi-second reveal.
const staggeredContainers = new WeakSet();

export function staggerEntrance(container, elements, { step = 90, max = 12 } = {}) {
  if (staggeredContainers.has(container)) return;
  staggeredContainers.add(container);
  elements.forEach((element, index) => {
    element.style.animationDelay = `${Math.min(index, max) * step}ms`;
  });
}
