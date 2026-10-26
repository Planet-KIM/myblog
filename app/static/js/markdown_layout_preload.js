/**
 * @file markdown_layout_preload.js — Re-apply the saved body width
 * (localStorage "contentLayout", default "center") to .writing-editor-wrapper
 * on DOMContentLoaded, so the Markdown editor does not flash at the wrong width
 * (FOUC 방지: layout 미리 적용).
 *
 * Used by templates/board_edit.html, loaded in <head> without defer.
 */
(function() {
  const layout = localStorage.getItem('contentLayout') || 'center';
  document.addEventListener('DOMContentLoaded', function() {
    const w = document.querySelector('.writing-editor-wrapper');
    if (w) w.dataset.layout = layout;
  });
})();
