/**
 * @file Markdown post page (board_detail_writer.html): applies the reading
 * layout chosen on the writing page and hides a duplicated title. The action
 * bar, scroll progress, recent-posts history and code highlighting are shared
 * with the magazine page in board_detail.js.
 *
 * Load it WITHOUT defer right after board_detail.js, so this page's
 * DOMContentLoaded work runs after the shared work (the old inline order).
 */
(function initBoardDetailWriter() {
  /**
   * Set data-layout on .reading-container from the contentLayout saved by the
   * writing page (center when unset or storage is unavailable); the variants
   * are styled in board_detail_writer.css.
   *
   * @returns {void}
   */
  function applyReadingLayout() {
    let layout = 'center';
    try { layout = localStorage.getItem('contentLayout') || 'center'; } catch (e) {}
    const container = document.querySelector('.reading-container');
    if (container) container.dataset.layout = layout;
  }

  /**
   * Hide the article's first element when it is an <h1> (it repeats the page
   * title).
   *
   * @returns {void}
   */
  function hideDuplicateTitle() {
    const articleContent = document.querySelector('.article-content');
    if (articleContent) {
      const firstEl = articleContent.firstElementChild;
      if (firstEl && firstEl.tagName === 'H1') {
        firstEl.hidden = true;
      }
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    applyReadingLayout();
    hideDuplicateTitle();
  });
})();
