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
