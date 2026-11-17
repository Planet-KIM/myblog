/**
 * @file Text-size buttons of the post body (_reading_size.html).
 *
 * A click on [data-reading-size-set="sm|md|lg"] inside
 * [data-reading-size-control] sets data-reading-size on <html> ("md" removes
 * it), which reading_size.css turns into the body's zoom, and stores the
 * choice in localStorage "readingSize" for theme-init.js to apply before the
 * first paint of later pages. A resize event follows so scripts that measure
 * the body (the magazine reader's photo overlays) measure again.
 */
(function initReadingSize() {
  /** localStorage key shared with theme-init.js. */
  const STORAGE_KEY = 'readingSize';
  /** Sizes other than the default ("md"), as stored and set on <html>. */
  const SIZES = ['sm', 'lg'];
  /** Containers of the author's content; nothing inside them is a page control. */
  const USER_CONTENT = '.article-content, .magazine-content';

  const control = Array.from(document.querySelectorAll('[data-reading-size-control]'))
    .find((el) => !el.closest(USER_CONTENT));
  if (!control) return;
  const buttons = Array.from(control.querySelectorAll('[data-reading-size-set]'));

  /**
   * The size in effect, read from <html>.
   *
   * @returns {string} "sm", "md" or "lg".
   */
  function currentSize() {
    const size = document.documentElement.dataset.readingSize;
    return SIZES.includes(size) ? size : 'md';
  }

  /**
   * Mark the button of the size in effect as pressed.
   *
   * @returns {void}
   */
  function syncButtons() {
    const size = currentSize();
    buttons.forEach((button) => {
      button.setAttribute('aria-pressed', String(button.dataset.readingSizeSet === size));
    });
  }

  /**
   * Apply a size, remember it and let measuring scripts know.
   *
   * @param {string} size - "sm", "md" or "lg"; anything else counts as "md".
   * @returns {void}
   */
  function setSize(size) {
    if (SIZES.includes(size)) document.documentElement.dataset.readingSize = size;
    else delete document.documentElement.dataset.readingSize;
    try {
      if (SIZES.includes(size)) localStorage.setItem(STORAGE_KEY, size);
      else localStorage.removeItem(STORAGE_KEY);
    } catch (e) { /* storage unavailable: the choice lasts for this page only */ }
    syncButtons();
    window.dispatchEvent(new Event('resize'));
  }

  /**
   * Apply the stored size when theme-init.js has not (an older cached copy
   * of it knows nothing about text sizes).
   *
   * @returns {void}
   */
  function applyStoredSize() {
    if (document.documentElement.dataset.readingSize) return;
    let stored = null;
    try { stored = localStorage.getItem(STORAGE_KEY); } catch (e) { /* storage unavailable */ }
    if (SIZES.includes(stored)) setSize(stored);
  }

  buttons.forEach((button) => {
    button.addEventListener('click', () => setSize(button.dataset.readingSizeSet));
  });
  applyStoredSize();
  syncButtons();
})();
