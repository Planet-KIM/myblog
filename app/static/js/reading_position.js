/**
 * @file "Continue where you left off" on post pages (_reading_position.html).
 *
 * While a post is read, how far the reader got is kept in this browser's
 * localStorage (nothing goes to the server). When the post is opened again a
 * small prompt offers to go back there; it never scrolls on its own. The
 * record is dropped when the post is read to the end or the prompt is closed.
 *
 * Markup hooks:
 *   [data-reading-resume][data-post-id]  the prompt (hidden until needed)
 *   [data-reading-resume-text]           where the "62%까지…" sentence goes
 *   [data-reading-resume-go]             "이어 읽기" button
 *   [data-reading-resume-close]          close button
 *   [data-reading-article]               the element that holds the post body
 *
 * Magazine posts shown as flipping pages do not scroll, so the page number is
 * kept too. The viewer (board_detail_magazine.js) reports it with a
 * `magazine:page` event ({ page, pages }) and turns to a page on
 * `magazine:goto` ({ page }); in its scrolling reading mode the page is the
 * number of `.reader-page-sep` separators above the top of the screen.
 */
(function initReadingPosition() {
  /** localStorage key: { [postId]: { r: ratio, p: page, m: 'scroll'|'pages', t: savedAt } }. */
  const STORAGE_KEY = 'readingPositions';
  /** Most posts remembered; the oldest records are dropped first. */
  const MAX_RECORDS = 50;
  /** Records older than this are forgotten. */
  const MAX_AGE_MS = 60 * 24 * 60 * 60 * 1000;
  /** Least time between two saves while scrolling. */
  const SAVE_INTERVAL_MS = 1000;
  /** A scroll position counts once the reader is this far into the body… */
  const MIN_RATIO = 0.08;
  /** …and at least this many screens down. */
  const MIN_SCREENS = 0.75;
  /** Past this share of the body the post counts as read. */
  const DONE_RATIO = 0.95;
  /** The prompt goes away once the reader has scrolled this many screens on their own. */
  const IGNORE_SCREENS = 1.5;

  /** Containers of the author's content; nothing inside them is a page control. */
  const USER_CONTENT = '.article-content, .magazine-content';
  /** The magazine viewer's root, and the class it carries in scrolling reading mode. */
  const VIEWER_ID = 'magazine-viewer-root';
  const READER_CLASS = 'reader-on';
  const PAGE_SEPARATOR = '.reader-page-sep';
  /** The sticky navigation bar at the top of every page. */
  const SITE_NAV = '.site-nav';

  const prompt = Array.from(document.querySelectorAll('[data-reading-resume]'))
    .find((el) => !el.closest(USER_CONTENT));
  const article = document.querySelector('[data-reading-article]');
  const postId = prompt ? Number(prompt.dataset.postId) : NaN;
  if (!prompt || !article || !Number.isSafeInteger(postId) || postId <= 0) return;

  const viewer = document.getElementById(VIEWER_ID);
  /** Page the flip viewer shows, as last reported by `magazine:page`. */
  let viewerPage = 0;

  /**
   * Read every stored record, dropping the expired ones.
   *
   * @returns {Object<string, {r: number, p: number, m: string, t: number}>} Records by post id.
   */
  function readAll() {
    let all;
    try {
      all = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
    } catch (e) {
      return {};
    }
    if (!all || typeof all !== 'object' || Array.isArray(all)) return {};
    const now = Date.now();
    Object.keys(all).forEach((id) => {
      const rec = all[id];
      if (!rec || typeof rec.t !== 'number' || now - rec.t > MAX_AGE_MS) delete all[id];
    });
    return all;
  }

  /**
   * Store this post's record, or remove it, keeping at most MAX_RECORDS posts.
   *
   * @param {?{r: number, p: number, m: string, t: number}} record - The record, or null to forget the post.
   * @returns {void}
   */
  function write(record) {
    const all = readAll();
    if (record) all[postId] = record; else delete all[postId];
    const ids = Object.keys(all).sort((a, b) => all[b].t - all[a].t);
    ids.slice(MAX_RECORDS).forEach((id) => { delete all[id]; });
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(all));
    } catch (e) { /* storage unavailable: nothing is remembered */ }
  }

  /**
   * Whether the magazine viewer is showing flipping pages (not scrolling).
   *
   * @returns {boolean} True in page-flip mode.
   */
  function isPaged() {
    return Boolean(viewer) && !viewer.classList.contains(READER_CLASS);
  }

  /**
   * Top of the post body in document coordinates, and its height.
   *
   * @returns {{top: number, height: number}} The body's box.
   */
  function articleBox() {
    const rect = article.getBoundingClientRect();
    return { top: rect.top + window.scrollY, height: rect.height };
  }

  /**
   * Where the reader is now.
   *
   * @returns {{r: number, p: number, m: string, t: number}} Share of the body
   *   above the top of the screen (0–1), the magazine page (0 without one),
   *   the mode it was measured in and the time.
   */
  function measure() {
    const box = articleBox();
    const ratio = box.height > 0 ? Math.min(1, Math.max(0, (window.scrollY - box.top) / box.height)) : 0;
    let page = 0;
    if (isPaged()) {
      page = viewerPage;
    } else if (viewer) {
      page = Array.from(viewer.querySelectorAll(PAGE_SEPARATOR))
        .filter((sep) => sep.getBoundingClientRect().top <= 0).length;
    }
    return { r: ratio, p: page, m: isPaged() ? 'pages' : 'scroll', t: Date.now() };
  }

  /**
   * Whether a position is far enough in to be worth coming back to.
   *
   * @param {{r: number, p: number, m: string}} pos - A measured or stored position.
   * @returns {boolean} True when it is past the opening of the post.
   */
  function isWorthKeeping(pos) {
    if (pos.m === 'pages') return pos.p >= 1;
    return pos.r >= MIN_RATIO && pos.r * articleBox().height >= window.innerHeight * MIN_SCREENS;
  }

  /**
   * Whether a position is the end of the post.
   *
   * @param {{r: number, m: string}} pos - A measured position.
   * @returns {boolean} True when the scrolled body is all but read.
   */
  function isDone(pos) {
    return pos.m === 'scroll' && pos.r >= DONE_RATIO;
  }

  /**
   * Save the current position: forget the post at its end, keep the record
   * when far enough in, and leave an older record alone near the top (so
   * opening a post does not erase where the reader was).
   *
   * @returns {void}
   */
  function save() {
    const pos = measure();
    if (isDone(pos)) write(null);
    else if (isWorthKeeping(pos)) write(pos);
  }

  /**
   * Height of the site's sticky navigation bar, which covers the top of the
   * screen.
   *
   * @returns {number} Pixels to leave free above a scroll target (0 without a bar).
   */
  function navHeight() {
    const nav = document.querySelector(SITE_NAV);
    return nav ? nav.offsetHeight : 0;
  }

  /**
   * Go to a stored position: turn the flip viewer to its page, or scroll to
   * the page's start (record from page mode) or to the same share of the
   * body. The start of the body or of a page is placed below the navigation
   * bar; a share of the body is restored exactly as it was measured.
   *
   * @param {{r: number, p: number, m: string}} rec - The stored record.
   * @returns {void}
   */
  function restore(rec) {
    const behavior = window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth';
    const box = articleBox();
    if (isPaged()) {
      document.dispatchEvent(new CustomEvent('magazine:goto', { detail: { page: rec.p } }));
      window.scrollTo({ top: Math.max(0, box.top - navHeight()), behavior });
      return;
    }
    const separator = rec.m === 'pages' && viewer ? viewer.querySelectorAll(PAGE_SEPARATOR)[rec.p - 1] : null;
    const top = separator
      ? separator.getBoundingClientRect().top + window.scrollY - navHeight()
      : box.top + rec.r * box.height;
    window.scrollTo({ top, behavior });
  }

  /**
   * The prompt's sentence for a record.
   *
   * @param {{r: number, p: number, m: string}} rec - The stored record.
   * @returns {string} "지난번에 3쪽까지 읽었습니다" or "지난번에 62%까지 읽었습니다".
   */
  function describe(rec) {
    const where = rec.m === 'pages' ? `${rec.p + 1}쪽` : `${Math.round(rec.r * 100)}%`;
    return `지난번에 ${where}까지 읽었습니다`;
  }

  /**
   * Show the prompt for a stored record and wire its buttons. It hides when
   * the reader resumes, closes it (which also forgets the record) or scrolls
   * IGNORE_SCREENS on their own.
   *
   * @param {{r: number, p: number, m: string}} rec - The stored record.
   * @returns {void}
   */
  function offer(rec) {
    const text = prompt.querySelector('[data-reading-resume-text]');
    const go = prompt.querySelector('[data-reading-resume-go]');
    const close = prompt.querySelector('[data-reading-resume-close]');
    if (!text || !go || !close) return;
    const startY = window.scrollY;

    /** Hide the prompt and stop watching the scroll. */
    function hide() {
      prompt.hidden = true;
      window.removeEventListener('scroll', hideWhenIgnored);
    }

    /** Hide the prompt once the reader has clearly chosen to read on their own. */
    function hideWhenIgnored() {
      if (Math.abs(window.scrollY - startY) > window.innerHeight * IGNORE_SCREENS) hide();
    }

    text.textContent = describe(rec);
    go.addEventListener('click', () => { hide(); restore(rec); });
    close.addEventListener('click', () => { hide(); write(null); });
    window.addEventListener('scroll', hideWhenIgnored, { passive: true });
    prompt.hidden = false;
  }

  document.addEventListener('magazine:page', (event) => {
    const page = event.detail && Number(event.detail.page);
    if (!Number.isInteger(page) || page < 0) return;
    const turned = page !== viewerPage;
    viewerPage = page;
    if (turned && isPaged()) save();
  });

  let lastSave = 0;
  window.addEventListener('scroll', () => {
    const now = Date.now();
    if (now - lastSave < SAVE_INTERVAL_MS) return;
    lastSave = now;
    save();
  }, { passive: true });

  let moved = false;
  window.addEventListener('scroll', () => { moved = true; }, { passive: true, once: true });
  document.addEventListener('magazine:page', () => { moved = true; });
  window.addEventListener('pagehide', () => { if (moved) save(); });
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden' && moved) save();
  });

  const stored = readAll()[postId];
  if (stored && typeof stored.r === 'number' && Number.isInteger(stored.p) && isWorthKeeping(stored)) {
    offer(stored);
  }
})();
