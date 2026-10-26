/**
 * @file Profile edit page (templates/profile_edit.html): keep the accent color
 * hex field in sync with the color picker.
 *
 * A color input marked data-sync-target="<input id>" copies its value into
 * that input on every input event (the hex field stays the submitted value).
 * Loaded at the end of <body>, so the inputs already exist.
 */
(function initColorSync() {
  /**
   * Copy a color picker's value into the input named by its data-sync-target.
   *
   * @param {HTMLInputElement} picker - The color input that changed.
   * @returns {void}
   */
  function syncTarget(picker) {
    document.getElementById(picker.dataset.syncTarget).value = picker.value;
  }

  document.querySelectorAll('input[data-sync-target]').forEach((picker) => {
    picker.addEventListener('input', () => syncTarget(picker));
  });
})();
