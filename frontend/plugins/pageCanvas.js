/**
 * @file plugins/pageCanvas.js — Page sizing and zoom for the magazine editors'
 * block canvas (board_new_tiptap.js, board_edit_tiptap.js). The rules that read
 * --page-w, --page-zoom and --canvas-h live in static/css/tiptap-editor.css
 * (#block-canvas, #block-canvas.is-zoomed); the zoom toggle is the
 * [data-page-zoom-toggle] button in the editor templates' bottom bar.
 */

// Space kept under the lowest block, and the smallest page height (px).
const PAGE_BOTTOM_MARGIN = 40;
const MIN_PAGE_HEIGHT = 400;
// localStorage key for the viewer's choice between fitting wide pages and 100%.
const ZOOM_PREF_KEY = 'magEditor.pageZoom';

/**
 * Height to save for a page.
 *
 * A page opened from saved data keeps its saved height while its blocks fit
 * inside it: starter layouts and imported pages have a fixed page size
 * (1000×1400) that can be taller than their content, or exactly filled by a
 * full-bleed photo. Only when a block reaches past the bottom edge does the
 * page grow, to the lowest block + 40px, which is also the height of a page
 * created in this session. Moving the blocks back up returns the page to its
 * saved height.
 *
 * @param {Array<{y: number, h: number}>} blocks - Blocks on the page.
 * @param {?number} [openedHeight] - Saved height when the page was loaded (omit for new pages).
 * @returns {number} Page height in px.
 */
export function pageHeight(blocks, openedHeight) {
  const bottom = blocks.reduce((m, b) => Math.max(m, b.y + b.h), 0);
  if (openedHeight && bottom <= openedHeight) return openedHeight;
  return Math.max(bottom + PAGE_BOTTOM_MARGIN, MIN_PAGE_HEIGHT);
}

/**
 * Size the block canvas to a page's saved width.
 *
 * Block positions are stored in px of the page they were laid out on (page.cw),
 * so showing the page at that width keeps every block where it was saved, on
 * any screen. A page that has not been saved yet (no cw) fills the editor column.
 *
 * @param {HTMLElement} canvas - The #block-canvas element.
 * @param {{cw: ?number}} page - Page about to be shown.
 * @returns {void}
 */
export function applyPageWidth(canvas, page) {
  if (page.cw) canvas.style.setProperty('--page-w', `${page.cw}px`); // conventions: allow (page width from saved layout data)
  else canvas.style.removeProperty('--page-w'); // conventions: allow (back to the column width)
}

/**
 * Current on-screen scale of the canvas: 1 unless a wide page is zoomed out.
 *
 * Mouse positions are in screen px while block geometry is in page px, so the
 * drag, resize and pan handlers divide mouse distances by this.
 *
 * @param {HTMLElement} canvas - The #block-canvas element.
 * @returns {number} Screen px per page px.
 */
export function canvasScale(canvas) {
  return canvas.getBoundingClientRect().width / (canvas.offsetWidth || 1) || 1;
}

/**
 * Read the viewer's saved zoom choice.
 *
 * @returns {?string} "fit", "actual", or null when unset or storage is unavailable.
 */
function readZoomPref() {
  try { return localStorage.getItem(ZOOM_PREF_KEY); } catch { return null; }
}

/**
 * Remember the viewer's zoom choice (best effort).
 *
 * @param {string} value - "fit" or "actual".
 * @returns {void}
 */
function saveZoomPref(value) {
  try { localStorage.setItem(ZOOM_PREF_KEY, value); } catch { /* storage unavailable: the choice lasts for this page only */ }
}

/**
 * Draw pages that are wider than the editor column zoomed out to fit it.
 *
 * The page keeps its saved width (applyPageWidth) and is only drawn smaller
 * (#block-canvas.is-zoomed), so block geometry never changes. The zoom follows
 * page switches, window resizes and canvas growth. The toggle switches between
 * fitting and 100% (scroll sideways), shows the current zoom, is hidden while
 * the page fits, and the choice is remembered in this browser.
 *
 * @param {HTMLElement} canvas - The #block-canvas element.
 * @param {HTMLElement} column - Element whose width the page has to fit.
 * @param {?HTMLButtonElement} toggle - The [data-page-zoom-toggle] button (its
 *   [data-page-zoom-label] child shows the zoom), or null.
 * @returns {void}
 */
export function initPageZoom(canvas, column, toggle) {
  let fit = readZoomPref() !== 'actual';
  const label = toggle?.querySelector('[data-page-zoom-label]');

  /**
   * Recompute the zoom from the page and column widths and refresh the toggle.
   *
   * @returns {void}
   */
  const update = () => {
    const pageW = canvas.offsetWidth, colW = column.clientWidth;
    const tooWide = pageW > colW + 1;
    const zoom = fit && tooWide ? colW / pageW : 1;
    canvas.style.setProperty('--page-zoom', String(zoom)); // conventions: allow (zoom computed from the column width)
    canvas.style.setProperty('--canvas-h', `${canvas.offsetHeight}px`); // conventions: allow (layout height the zoom has to shrink)
    canvas.classList.toggle('is-zoomed', zoom < 1);
    if (!toggle) return;
    toggle.hidden = !tooWide;
    toggle.setAttribute('aria-pressed', String(fit));
    toggle.title = fit ? '실제 크기(100%)로 보기' : '화면 폭에 맞추기';
    if (label) label.textContent = `${Math.round(zoom * 100)}%`;
  };

  const observer = new ResizeObserver(update);
  observer.observe(canvas);
  observer.observe(column);
  toggle?.addEventListener('click', () => {
    fit = !fit;
    saveZoomPref(fit ? 'fit' : 'actual');
    update();
  });
  update();
}
