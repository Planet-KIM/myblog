/**
 * @file Success flash for the category page (templates/board_categories.html).
 *
 * Reads the message from this script element's data-message attribute and,
 * on DOMContentLoaded, shows it with window.toast when that exists.
 *
 * The listener sits on window, so it runs after every DOMContentLoaded
 * listener on document, including the one in app.js that creates
 * window.toast. Load this without defer/async where the flash belongs in the
 * page; that keeps its place among the other window listeners.
 */
(function initCategoryFlash() {
  const message = document.currentScript.dataset.message;
  window.addEventListener('DOMContentLoaded', function () {
    if (window.toast) window.toast.success(message);
  });
})();
