/**
 * @file tiptap_word_count.js — Live character count (spaces excluded) in the
 * magazine editor toolbar (#wordCount). Only the text of the blocks' editors
 * (.fb-editor inside #block-canvas) is counted.
 *
 * Used by templates/board_new_tiptap.html and board_edit_tiptap.html, loaded
 * (no defer) after the canvas markup and before the editor bundle.
 */
// 글자 수 (공백 제외) — 블록 본문만 센다
(function () {
  const out = document.getElementById('wordCount');
  const canvas = document.getElementById('block-canvas');
  if (!out || !canvas) return;
  /**
   * Recount the characters of every block editor and show the total.
   *
   * @returns {void}
   */
  function update() {
    let n = 0;
    canvas.querySelectorAll('.fb-editor').forEach(el => { n += el.innerText.replace(/\s/g, '').length; });
    out.textContent = `${n.toLocaleString()}자`;
  }
  canvas.addEventListener('input', update);
  canvas.addEventListener('keyup', update);
  setTimeout(update, 800);
})();
