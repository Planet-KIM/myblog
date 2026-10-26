/**
 * @file Behavior shared by both post detail pages (board_detail_writer.html and
 * board_detail_magazine.html): the action bar (like, bookmark, copy link,
 * print, share on X), the scroll-to-top button with its reading-progress
 * ring, the "recent posts" history in localStorage and code highlighting.
 *
 * Post data comes from <script type="application/json" id="board-detail-data">:
 *   { postId: number, shareTitle: string, recentTitle: string, recentDate: string }
 * Buttons opt in with data-detail-action="like|bookmark|copy-link|print|share-x|scroll-top".
 *
 * Load it WITHOUT defer, after the action bar and the scroll-to-top button and
 * before the page's own script, so its DOMContentLoaded work runs first (the
 * order the old inline script had).
 */
(function initBoardDetail() {
  /** @type {{postId: number, shareTitle: string, recentTitle: string, recentDate: string}} */
  const POST = JSON.parse(document.getElementById('board-detail-data').textContent);

  /** Radius of the progress ring's circles (r="16" in the markup). */
  const RING_RADIUS = 16;

  /** How many entries the recent-posts history keeps. */
  const RECENT_LIMIT = 15;

  /**
   * Copy the page URL to the clipboard and confirm with a toast.
   *
   * @returns {void}
   */
  function copyLink() {
    navigator.clipboard.writeText(window.location.href).then(() => {
      if (window.toast) window.toast.success('링크를 복사했어요');
    });
  }

  /**
   * Open the X (Twitter) share dialog for this post in a new window.
   *
   * @returns {void}
   */
  function shareTwitter() {
    const text = POST.shareTitle;
    window.open(`https://twitter.com/intent/tweet?text=${encodeURIComponent(text)}&url=${encodeURIComponent(window.location.href)}`);
  }

  /**
   * POST to an engagement endpoint and return its JSON.
   * Alerts the user (login required / generic failure) when the request fails.
   *
   * @param {string} url - Endpoint, e.g. /api/posts/1/like.
   * @returns {Promise<?Object>} The parsed response, or null on failure.
   */
  async function postAction(url) {
    const response = await fetch(url, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' }
    });
    if (!response.ok) {
      if (response.status === 401 || response.status === 403) {
        alert('로그인이 필요합니다.');
        return null;
      }
      alert('요청 처리에 실패했습니다.');
      return null;
    }
    return response.json();
  }

  /**
   * Toggle the like on this post and update the count and icon.
   *
   * @returns {Promise<void>}
   */
  async function toggleDetailLike() {
    const result = await postAction(`/api/posts/${POST.postId}/like`);
    if (!result) return;
    const likeCount = document.getElementById('detail-like-count');
    const icon = document.querySelector('#detail-like-btn i');
    if (likeCount) likeCount.textContent = String(result.likes ?? 0);
    if (icon) icon.className = result.active ? 'bi bi-hand-thumbs-up-fill' : 'bi bi-hand-thumbs-up';
  }

  /**
   * Toggle the bookmark on this post and update the icon.
   *
   * @returns {Promise<void>}
   */
  async function toggleDetailBookmark() {
    const result = await postAction(`/api/posts/${POST.postId}/bookmark`);
    if (!result) return;
    const icon = document.querySelector('#detail-bookmark-btn i');
    if (icon) icon.className = result.active ? 'bi bi-bookmark-check-fill' : 'bi bi-bookmark';
  }

  /**
   * Smooth-scroll back to the top of the page.
   *
   * @returns {void}
   */
  function scrollToTop() {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  /**
   * Put this post at the front of the "recent posts" list in localStorage
   * (deduplicated by id, newest first, at most RECENT_LIMIT entries).
   * Storage errors are ignored.
   *
   * @returns {void}
   */
  function saveRecentPost() {
    const entry = {
      id: POST.postId,
      title: POST.recentTitle,
      url: '/board/' + POST.postId,
      date: POST.recentDate
    };
    let list = [];
    try {
      list = JSON.parse(localStorage.getItem('recentPosts') || '[]');
    } catch (e) {
      list = [];
    }
    list = list.filter(item => item.id !== entry.id);
    list.unshift(entry);
    try { localStorage.setItem('recentPosts', JSON.stringify(list.slice(0, RECENT_LIMIT))); } catch (e) {}
  }

  /**
   * Drive the scroll-to-top button: fill the progress ring with the scroll
   * position and show the button once the page is scrolled past 300px.
   *
   * @returns {void}
   */
  function initScrollProgress() {
    const scrollBtn = document.getElementById('scroll-to-top');
    const ring = document.getElementById('scrollProgressRing');
    if (!scrollBtn || !ring) return;

    const circumference = 2 * Math.PI * RING_RADIUS;
    // conventions: allow (ring dash length computed from the circle radius; the offset below tracks it)
    ring.style.strokeDasharray = `${circumference} ${circumference}`;
    ring.style.strokeDashoffset = circumference; // conventions: allow (runtime scroll progress)

    window.addEventListener('scroll', () => {
      const winScroll = document.body.scrollTop || document.documentElement.scrollTop;
      const height = document.documentElement.scrollHeight - document.documentElement.clientHeight;
      const scrolled = height > 0 ? (winScroll / height) * 100 : 0;
      ring.style.strokeDashoffset = circumference - (scrolled / 100 * circumference); // conventions: allow (runtime scroll progress)
      scrollBtn.classList.toggle('show', winScroll > 300);
    }, { passive: true });
  }

  /**
   * Syntax-highlight every code block with highlight.js when it is loaded.
   *
   * @returns {void}
   */
  function highlightCode() {
    if (window.hljs) {
      document.querySelectorAll('pre code').forEach((block) => hljs.highlightElement(block));
    }
  }

  /**
   * What each data-detail-action button does when clicked.
   *
   * @type {Object<string, function(): void>}
   */
  const ACTIONS = {
    like: toggleDetailLike,
    bookmark: toggleDetailBookmark,
    'copy-link': copyLink,
    print: () => window.print(),
    'share-x': shareTwitter,
    'scroll-top': scrollToTop
  };

  document.querySelectorAll('[data-detail-action]').forEach((button) => {
    const action = ACTIONS[button.dataset.detailAction];
    if (action) button.addEventListener('click', () => { action(); });
  });

  document.addEventListener('DOMContentLoaded', () => {
    saveRecentPost();
    initScrollProgress();
    highlightCode();
  });
})();
