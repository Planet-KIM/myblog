/**
 * @file plugins/spellcheckAccess.js — Which spell check the signed-in user may
 * use in the magazine editors (board_new_tiptap.js, board_edit_tiptap.js).
 *
 * The server writes the level on #block-canvas as data-spellcheck-level
 * (0 none, 1 the fast models, 2 the large models too; see
 * app/services/spellcheck_access.py) and enforces it on POST /api/spellcheck.
 * The editors use these helpers only to hide what the level does not allow.
 */

/** English model variants that need level 2 (the Korean editor UI only uses et5). */
const LARGE_EN_VARIANTS = new Set(['coedit']);

/**
 * The user's spell-check level, read from the page.
 *
 * @returns {number} 0, 1 or 2; 0 when the attribute is missing or invalid.
 */
export function spellcheckLevel() {
  const level = Number(document.getElementById('block-canvas')?.dataset.spellcheckLevel);
  return Number.isInteger(level) && level >= 0 && level <= 2 ? level : 0;
}

/**
 * Whether the user may use spell check at all.
 *
 * @returns {boolean} True from level 1.
 */
export function canSpellcheck() {
  return spellcheckLevel() >= 1;
}

/**
 * Whether the user may pick an English model variant.
 *
 * @param {string} variant - 'vennify' or 'coedit'.
 * @returns {boolean} False for a large model below level 2.
 */
export function canUseEnVariant(variant) {
  return !LARGE_EN_VARIANTS.has(variant) || spellcheckLevel() >= 2;
}
