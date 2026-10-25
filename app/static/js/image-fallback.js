/**
 * @file Declarative fallbacks for images that fail to load (replaces inline onerror="").
 *
 * Mark an <img> with data-img-fallback="<action>":
 *   hide           hide the image (img.hidden; Bootstrap makes [hidden] display:none)
 *   remove         remove the image from the DOM
 *   hide-parent    hide the image's parent element (e.g. a thumbnail frame)
 *   remove-parent  remove the image's parent element
 * Optionally add data-img-fallback-scope="<selector>" and data-img-fallback-class="<class>"
 * to put a class on the closest matching ancestor first (e.g. switch a card to
 * its no-image layout).
 *
 * Load this in <head> WITHOUT defer/async. An inline onerror handler is active
 * as soon as the parser creates the <img>, so this listener has to exist before
 * any image is parsed, or failures that happen early would be missed. Image
 * error events don't bubble, hence the capture-phase listener on document.
 */
(function initImageFallbacks() {
  'use strict';

  /**
   * What to do with a failed image, keyed by the data-img-fallback value.
   *
   * @type {Object<string, function(HTMLImageElement): void>}
   */
  const ACTIONS = {
    hide: (img) => { img.hidden = true; },
    remove: (img) => { img.remove(); },
    'hide-parent': (img) => { if (img.parentElement) img.parentElement.hidden = true; },
    'remove-parent': (img) => { if (img.parentElement) img.parentElement.remove(); },
  };

  /**
   * Add data-img-fallback-class to the closest ancestor matching
   * data-img-fallback-scope, when both are set.
   *
   * @param {HTMLImageElement} img - The image that failed.
   * @returns {void}
   */
  function flagScope(img) {
    const { imgFallbackScope: scope, imgFallbackClass: className } = img.dataset;
    if (!scope || !className) return;
    const target = img.closest(scope);
    if (target) target.classList.add(className);
  }

  /**
   * Apply the declared fallback when a marked image fails to load.
   *
   * @param {Event} event - An error event captured on document.
   * @returns {void}
   */
  function handleImageError(event) {
    const img = event.target;
    if (!(img instanceof HTMLImageElement)) return;
    const action = ACTIONS[img.dataset.imgFallback];
    if (!action) return;
    flagScope(img);
    action(img);
  }

  document.addEventListener('error', handleImageError, true);
})();
