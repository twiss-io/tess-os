// Tess OS Mission Control — one-field prompt modal.
//
// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Twiss
//
// Uses the native <dialog> element (see index.html #prompt-modal) rather
// than a hand-rolled overlay: free focus trap, free Escape-to-cancel, free
// top-layer stacking — all browsers in scope (current Chrome/Safari/
// Firefox) support HTMLDialogElement.showModal().

export function openPrompt({ title, label, placeholder = '', confirmLabel = 'Launch' } = {}) {
  const dialog = document.getElementById('prompt-modal');
  const form = document.getElementById('prompt-modal-form');
  const titleEl = document.getElementById('prompt-modal-title');
  const labelEl = document.getElementById('prompt-modal-label');
  const input = document.getElementById('prompt-modal-input');
  const cancelBtn = document.getElementById('prompt-modal-cancel');
  const confirmBtn = document.getElementById('prompt-modal-confirm');

  titleEl.textContent = title || 'Mission input';
  labelEl.textContent = label || 'Details';
  labelEl.setAttribute('for', 'prompt-modal-input');
  input.value = '';
  input.placeholder = placeholder;
  confirmBtn.textContent = confirmLabel;

  return new Promise((resolve) => {
    function cleanup() {
      form.removeEventListener('submit', onSubmit);
      cancelBtn.removeEventListener('click', onCancel);
      dialog.removeEventListener('close', onClose);
      dialog.removeEventListener('click', onBackdropClick);
    }
    function closeDialog() {
      if (typeof dialog.close === 'function') dialog.close();
      else dialog.removeAttribute('open');
    }
    function onSubmit(event) {
      event.preventDefault();
      const value = input.value.trim();
      if (!value) return;
      cleanup();
      closeDialog();
      resolve(value);
    }
    function onCancel() {
      cleanup();
      closeDialog();
      resolve(null);
    }
    function onClose() {
      cleanup();
      resolve(null);
    }
    function onBackdropClick(event) {
      if (event.target === dialog) onCancel();
    }

    form.addEventListener('submit', onSubmit);
    cancelBtn.addEventListener('click', onCancel);
    dialog.addEventListener('close', onClose, { once: true });
    dialog.addEventListener('click', onBackdropClick);
    // Feature-detected, not environment-detected: every target browser
    // (current Chrome/Safari/Firefox) implements showModal(); this guard
    // only exists so the component degrades instead of throwing in an
    // embedding that lacks it (e.g. jsdom, used by this package's own tests).
    if (typeof dialog.showModal === 'function') dialog.showModal();
    else dialog.setAttribute('open', '');
    input.focus();
  });
}
