/**
 * @file Follow button on a user's blog home (templates/blog_home.html).
 *
 * The .js-blog-follow button (rendered for signed-in visitors who are not the
 * owner) toggles the follow through POST /api/follow/author/<id> and mirrors
 * the result in its label, .is-following class and aria-pressed.
 * Loaded at the end of <body>, so the button already exists.
 */
(function initBlogFollow() {
  var btn = document.querySelector('.js-blog-follow');
  if (!btn) return;

  /**
   * Toggle the follow on the server and show the new state on the button.
   * On failure, warn with a toast (or a plain alert if toasts are unavailable).
   *
   * @returns {Promise<void>} Resolves once the button is updated or the warning shown.
   */
  async function toggleFollow() {
    var id = btn.getAttribute('data-author-id');
    try {
      var res = await fetch('/api/follow/author/' + id, { method: 'POST', credentials: 'same-origin' });
      if (!res.ok) throw new Error('failed');
      var data = await res.json();
      btn.textContent = data.active ? '팔로잉' : '팔로우';
      btn.classList.toggle('is-following', !!data.active);
      btn.setAttribute('aria-pressed', data.active ? 'true' : 'false');
    } catch (e) {
      if (window.toast) { window.toast.warning('요청 처리에 실패했습니다.'); } else { alert('요청 실패'); }
    }
  }

  btn.addEventListener('click', toggleFollow);
})();
