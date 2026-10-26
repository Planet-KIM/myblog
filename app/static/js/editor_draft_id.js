/**
 * @file editor_draft_id.js — Expose the server-issued draft id as
 * window.DRAFT_ID; the new-post editor bundles send it with image uploads so
 * the files are filed under the draft until the post is published.
 *
 * Usage (no defer, before the editor bundle):
 *   <script src=".../js/editor_draft_id.js" data-draft-id="{{ draft_id }}"></script>
 * Used by templates/board_new_tiptap.html and board_new_clean.html.
 */
(function () {
  window.DRAFT_ID = document.currentScript.dataset.draftId;
})();
