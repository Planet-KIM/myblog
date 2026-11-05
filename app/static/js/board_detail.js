/**
 * @file Behavior shared by both post detail pages (board_detail_writer.html and
 * board_detail_magazine.html): the action bar (like, bookmark, copy link,
 * print, share on X), the scroll-to-top button with its reading-progress
 * ring, the "recent posts" history in localStorage and code highlighting.
 *
 * Post data comes from <script type="application/json" id="board-detail-data">:
 *   { postId: number, shareTitle: string, recentTitle: string, recentDate: string, isPrivate: boolean }
 * Buttons opt in with data-detail-action="like|bookmark|copy-link|print|share-x|scroll-top".
 *
 * The post body sits in the same document and may carry any id or data-*
 * attribute, so the data is looked up as a <script> element (a body cannot
 * contain one) and its postId must be a positive integer, and only controls
 * outside the post body are used.
 *
 * Load it WITHOUT defer, after the action bar and the scroll-to-top button and
 * before the page's own script, so its DOMContentLoaded work runs first (the
 * order the old inline script had).
 */
(function initBoardDetail() {
  /** The page's data block; a <script> element, which post bodies cannot contain. */
  const DATA_SELECTOR = 'script#board-detail-data[type="application/json"]';

  /** Containers of the author's content; nothing inside them is a page control. */
  const USER_CONTENT = '.article-content, .magazine-content';

  /**
   * Read and check the page's post data.
   *
   * @returns {?{postId: number, shareTitle: string, recentTitle: string, recentDate: string}}
   *   The data, or null when the block is missing or postId is not a positive integer.
   */
  function readPostData() {
    const block = document.querySelector(DATA_SELECTOR);
    if (!block) return null;
    let data;
    try {
      data = JSON.parse(block.textContent);
    } catch (e) {
      return null;
    }
    return data && Number.isSafeInteger(data.postId) && data.postId > 0 ? data : null;
  }

  /**
   * The page's own elements matching a selector, leaving out any inside the
   * post body.
   *
   * @param {string} selector - CSS selector.
   * @returns {Element[]} Matching elements outside USER_CONTENT.
   */
  function pageControls(selector) {
    return Array.from(document.querySelectorAll(selector)).filter((el) => !el.closest(USER_CONTENT));
  }

  const POST = readPostData();
  if (!POST) return;

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
   * Toggle the like on this post and update the button's count and icon.
   *
   * @param {HTMLElement} button - The like button that was clicked.
   * @returns {Promise<void>}
   */
  async function toggleDetailLike(button) {
    const result = await postAction(`/api/posts/${POST.postId}/like`);
    if (!result) return;
    const likeCount = button.querySelector('#detail-like-count');
    const icon = button.querySelector('i');
    if (likeCount) likeCount.textContent = String(result.likes ?? 0);
    if (icon) icon.className = result.active ? 'bi bi-hand-thumbs-up-fill' : 'bi bi-hand-thumbs-up';
  }

  /**
   * Toggle the bookmark on this post and update the button's icon.
   *
   * @param {HTMLElement} button - The bookmark button that was clicked.
   * @returns {Promise<void>}
   */
  async function toggleDetailBookmark(button) {
    const result = await postAction(`/api/posts/${POST.postId}/bookmark`);
    if (!result) return;
    const icon = button.querySelector('i');
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
   * Private posts are not recorded: the list outlives the session and the
   * next person on this browser would see their titles. Storage errors are
   * ignored.
   *
   * @returns {void}
   */
  function saveRecentPost() {
    if (POST.isPrivate) return;
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
    const scrollBtn = pageControls('#scroll-to-top')[0];
    const ring = scrollBtn && scrollBtn.querySelector('#scrollProgressRing');
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
   * What each data-detail-action button does when clicked; each gets the
   * clicked button.
   *
   * @type {Object<string, function(HTMLElement): void>}
   */
  const ACTIONS = {
    like: toggleDetailLike,
    bookmark: toggleDetailBookmark,
    'copy-link': copyLink,
    print: () => window.print(),
    'share-x': shareTwitter,
    'scroll-top': scrollToTop
  };

  pageControls('[data-detail-action]').forEach((button) => {
    const action = ACTIONS[button.dataset.detailAction];
    if (action) button.addEventListener('click', () => { action(button); });
  });

  document.addEventListener('DOMContentLoaded', () => {
    saveRecentPost();
    initScrollProgress();
    highlightCode();
  });
})();
