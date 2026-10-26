/**
 * @file tag_suggestions.js — Popular-tag chips under the tag input: clicking a
 * chip adds its tag to the comma-separated #tags input (once) and focuses it.
 *
 * Used by templates/_tag_suggestions.html, loaded (no defer) right after the
 * chips, which come after the #tags input.
 */
(function () {
  var input = document.getElementById('tags');
  if (!input) return;
  /**
   * Append a chip's tag to the input unless it is already listed.
   *
   * @param {HTMLElement} chip - The clicked .tag-suggest-chip (tag in data-tag).
   * @returns {void}
   */
  function addTag(chip) {
    var tag = chip.getAttribute('data-tag');
    var cur = input.value.split(',').map(function (s) { return s.trim(); }).filter(Boolean);
    if (cur.indexOf(tag) === -1) { cur.push(tag); }
    input.value = cur.join(', ');
    input.focus();
  }
  document.querySelectorAll('.tag-suggest-chip').forEach(function (chip) {
    chip.addEventListener('click', function () { addTag(chip); });
  });
})();
