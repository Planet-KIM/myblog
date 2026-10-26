/**
 * @file plugins/pageCanvas.js — Page sizing for the magazine editors' block
 * canvas (board_new_tiptap.js, board_edit_tiptap.js). The width rule that reads
 * --page-w lives in static/css/tiptap-editor.css (#block-canvas).
 */

// Space kept under the lowest block, and the smallest page height (px).
const PAGE_BOTTOM_MARGIN = 40;
const MIN_PAGE_HEIGHT = 400;

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
