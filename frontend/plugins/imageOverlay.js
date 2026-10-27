/**
 * @file plugins/imageOverlay.js — Text written on a photo ("덧글씨") in the
 * magazine editors' image blocks (board_new_tiptap.js, board_edit_tiptap.js).
 *
 * An image block may carry three fields, saved with the layout:
 *   overlay      HTML of the text on the photo ('' = none)
 *   overlayPos   'bottom' | 'center' | 'top'
 *   overlayTone  'band-dark' (light text on a dark band) | 'band-light'
 *                (dark text on a light band) | 'plain' (no band)
 * Being part of the image block, the text always stays on its photo: in the
 * magazine pages, in the reading mode and on small screens. The look comes
 * from static/css/mag-overlay.css, shared with the post page
 * (static/js/board_detail_magazine.js), so the editor shows what readers see.
 */

export const OVERLAY_POSITIONS = ['bottom', 'center', 'top'];
export const OVERLAY_TONES = ['band-dark', 'band-light', 'plain'];
const POSITION_LABELS = { bottom: '아래', center: '가운데', top: '위' };
const TONE_LABELS = { 'band-dark': '어두운 띠', 'band-light': '밝은 띠', plain: '띠 없음' };

/**
 * The block's overlay position, falling back to 'bottom' for missing or unknown values.
 *
 * @param {Object} block - Image block.
 * @returns {string} One of OVERLAY_POSITIONS.
 */
export function overlayPosition(block) {
  return OVERLAY_POSITIONS.includes(block.overlayPos) ? block.overlayPos : 'bottom';
}

/**
 * The block's overlay tone, falling back to 'band-dark' for missing or unknown values.
 *
 * @param {Object} block - Image block.
 * @returns {string} One of OVERLAY_TONES.
 */
export function overlayTone(block) {
  return OVERLAY_TONES.includes(block.overlayTone) ? block.overlayTone : 'band-dark';
}

/**
 * Class list of the overlay element (see mag-overlay.css).
 *
 * @param {Object} block - Image block.
 * @returns {string} "mag-overlay mag-overlay--<position> mag-overlay--<tone>".
 */
export function overlayClass(block) {
  return `mag-overlay mag-overlay--${overlayPosition(block)} mag-overlay--${overlayTone(block)}`;
}

/**
 * Overlay markup for the reading HTML and the inline preview.
 *
 * @param {Object} block - Block (non-image blocks and empty overlays give '').
 * @returns {string} The overlay <div>, or ''.
 */
export function overlayMarkup(block) {
  return block.type === 'image' && block.overlay ? `<div class="${overlayClass(block)}">${block.overlay}</div>` : '';
}

/**
 * Copy the live overlay editor's text into block.overlay ('' when it is empty).
 *
 * @param {Object} block - Any block (blocks without an overlay editor are left alone).
 * @returns {void}
 */
export function syncOverlay(block) {
  if (block.overlayEditor) block.overlay = block.overlayEditor.isEmpty ? '' : block.overlayEditor.getHTML();
}

/**
 * Destroy the block's overlay editor, if any.
 *
 * @param {Object} block - Any block.
 * @returns {void}
 */
export function destroyOverlay(block) {
  if (block.overlayEditor) { block.overlayEditor.destroy(); block.overlayEditor = null; }
}

/**
 * Next value in a cycle.
 *
 * @param {string[]} list - Values in order.
 * @param {string} current - Current value.
 * @returns {string} The value after it (wrapping around).
 */
function nextOf(list, current) {
  return list[(list.indexOf(current) + 1) % list.length];
}

/**
 * Add the overlay buttons to an image block's header and show its overlay.
 *
 * Buttons: 글씨 (add / remove the text), 위치 (bottom → center → top) and
 * 띠 (dark band → light band → no band). The text is edited in place with a
 * TipTap editor on the photo; pressing inside it never starts a photo pan.
 *
 * @param {Object} opts - What the editor provides.
 * @param {HTMLElement} opts.hdr - The block header (buttons go before its delete button).
 * @param {HTMLElement} opts.body - The image body (.fb-body-image) the overlay sits in.
 * @param {Object} opts.block - The image block record.
 * @param {function(string, string, function(): void): HTMLButtonElement} opts.mkBtn - Header button factory.
 * @param {function(HTMLElement, string): Object} opts.createEditor - TipTap editor factory.
 * @returns {void}
 */
export function initImageOverlay({ hdr, body, block, mkBtn, createEditor }) {
  let el = null;
  const del = hdr.querySelector('.fb-del');

  /**
   * Refresh the overlay's classes and the buttons' state and tooltips.
   *
   * @returns {void}
   */
  const refresh = () => {
    const on = !!el;
    textBtn.classList.toggle('fb-btn-active', on);
    posBtn.hidden = toneBtn.hidden = !on;
    posBtn.title = `글씨 위치: ${POSITION_LABELS[overlayPosition(block)]}`;
    toneBtn.title = `글씨 배경: ${TONE_LABELS[overlayTone(block)]}`;
    if (el) el.className = `fb-overlay ${overlayClass(block)}`;
  };
  /**
   * Put the overlay and its editor on the photo.
   *
   * @returns {void}
   */
  const show = () => {
    el = document.createElement('div');
    el.addEventListener('mousedown', e => e.stopPropagation());   // typing, not panning
    body.appendChild(el);
    block.overlayEditor = createEditor(el, block.overlay || '<p></p>');
  };
  /**
   * Remove the overlay text from the photo and the block.
   *
   * @returns {void}
   */
  const hide = () => {
    destroyOverlay(block);
    el.remove(); el = null;
    block.overlay = '';
  };

  const textBtn = mkBtn('<i class="bi bi-fonts"></i>', '사진 위 글씨 넣기 / 빼기', () => {
    if (el) hide(); else { show(); block.overlayEditor.commands.focus(); }
    refresh();
  });
  const posBtn = mkBtn('<i class="bi bi-arrows-vertical"></i>', '', () => {
    block.overlayPos = nextOf(OVERLAY_POSITIONS, overlayPosition(block)); refresh();
  });
  const toneBtn = mkBtn('<i class="bi bi-square-half"></i>', '', () => {
    block.overlayTone = nextOf(OVERLAY_TONES, overlayTone(block)); refresh();
  });
  [textBtn, posBtn, toneBtn].forEach(b => hdr.insertBefore(b, del));
  if (block.overlay) show();
  refresh();
}
