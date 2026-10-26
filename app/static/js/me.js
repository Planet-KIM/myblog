/**
 * @file Personal dashboard (templates/me.html) behavior.
 *
 * - Bookmarks tab: the filter form (#bookmark-filter-form) refreshes
 *   #me-bookmark-panel in place (debounced search, category/sort changes,
 *   pager links, unbookmark buttons) by fetching /me and swapping the panel's
 *   HTML; the URL is kept in sync with history.replaceState.
 * - APIs tab: .js-copy-api buttons copy the sample named by data-copy-target.
 * - Issues tab: clicking a .js-issue-card outside its links opens data-url.
 *
 * Loaded without defer right after the dashboard markup, so every element it
 * looks up already exists.
 */
(function initMeDashboard() {
  /**
   * POST to an API endpoint and return its JSON body.
   * Alerts the user and resolves to null when the request fails.
   *
   * @param {string} url - Endpoint to call.
   * @returns {Promise<Object|null>} Parsed response, or null on failure.
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
   * Wire the bookmark filter form and panel for in-place (AJAX) updates.
   * Does nothing outside the bookmarks tab.
   *
   * @returns {void}
   */
  (function setupBookmarkRealtimeFilter() {
    const form = document.getElementById('bookmark-filter-form');
    const panel = document.getElementById('me-bookmark-panel');
    if (!form || !panel) return;

    const qInput = form.querySelector('input[name="q"]');
    const categorySelect = form.querySelector('select[name="category_id"]');
    const sortSelect = form.querySelector('select[name="sort"]');
    let debounceTimer = null;
    let requestSeq = 0;

    /**
     * Set the form's hidden "page" input, creating it on first use.
     *
     * @param {number|string} value - Page number to submit.
     * @returns {void}
     */
    function ensurePageInput(value) {
      let pageInput = form.querySelector('input[name="page"]');
      if (!pageInput) {
        pageInput = document.createElement('input');
        pageInput.type = 'hidden';
        pageInput.name = 'page';
        form.appendChild(pageInput);
      }
      pageInput.value = String(value);
    }

    /**
     * Build the /me URL for the current filter values.
     *
     * @returns {string} Path and query, with tab, page and category_id always present.
     */
    function buildQueryUrl() {
      const params = new URLSearchParams(new FormData(form));
      if (!params.get('tab')) params.set('tab', 'bookmarks');
      if (!params.get('page')) params.set('page', '1');
      if (!params.has('category_id')) params.set('category_id', '');
      return `/me?${params.toString()}`;
    }

    /**
     * Fetch a bookmarks page and swap its panel HTML into the current one.
     * Only the latest request is applied; errors are logged, not shown.
     *
     * @param {string} url - Same-origin /me URL to load.
     * @returns {Promise<void>} Resolves when the panel is updated (or the request dropped).
     */
    async function refreshBookmarkPanel(url) {
      const currentReq = ++requestSeq;
      panel.classList.add('is-loading');
      try {
        const response = await fetch(url, {
          credentials: 'same-origin',
          headers: { 'X-Requested-With': 'XMLHttpRequest' },
        });
        if (!response.ok) throw new Error('북마크 목록을 불러오지 못했습니다.');
        const html = await response.text();
        if (currentReq !== requestSeq) return;

        const doc = new DOMParser().parseFromString(html, 'text/html');
        const nextPanel = doc.getElementById('me-bookmark-panel');
        if (!nextPanel) throw new Error('북마크 패널 파싱 실패');

        panel.innerHTML = nextPanel.innerHTML;
        history.replaceState({}, '', url);
      } catch (error) {
        console.error(error);
      } finally {
        if (currentReq === requestSeq) {
          panel.classList.remove('is-loading');
        }
      }
    }

    /**
     * Reload the panel for the current filters.
     *
     * @param {boolean} resetPage - Go back to page 1 first.
     * @returns {void}
     */
    function triggerFilter(resetPage) {
      if (resetPage) ensurePageInput(1);
      const url = buildQueryUrl();
      refreshBookmarkPanel(url);
    }

    /**
     * Handle clicks inside the (re-rendered) panel: pager links load their
     * page in place, unbookmark buttons remove the bookmark and refresh.
     *
     * @param {MouseEvent} event - Click delegated to the panel.
     * @returns {Promise<void>} Resolves once the click is handled.
     */
    async function handlePanelClick(event) {
      const pageLink = event.target.closest('.pager-links a');
      if (pageLink) {
        event.preventDefault();
        const href = pageLink.getAttribute('href');
        if (!href) return;
        const url = new URL(href, window.location.origin);
        ensurePageInput(url.searchParams.get('page') || 1);
        refreshBookmarkPanel(`${url.pathname}${url.search}`);
        return;
      }

      const unbookmarkBtn = event.target.closest('.js-unbookmark-btn');
      if (!unbookmarkBtn) return;

      event.preventDefault();
      const postId = unbookmarkBtn.getAttribute('data-post-id');
      if (!postId) return;
      const result = await postAction(`/api/posts/${postId}/bookmark`);
      if (!result) return;

      if (result.active === false) {
        const url = buildQueryUrl();
        refreshBookmarkPanel(url);
      }
    }

    form.addEventListener('submit', (event) => {
      event.preventDefault();
      triggerFilter(true);
    });

    if (qInput) {
      qInput.addEventListener('input', () => {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => triggerFilter(true), 260);
      });
    }
    if (categorySelect) {
      categorySelect.addEventListener('change', () => triggerFilter(true));
    }
    if (sortSelect) {
      sortSelect.addEventListener('change', () => triggerFilter(true));
    }

    panel.addEventListener('click', handlePanelClick);
  })();

  /**
   * Copy the sample text named by a button's data-copy-target to the
   * clipboard, then show "복사됨" on the button for 1.2 s.
   *
   * @param {HTMLButtonElement} btn - The .js-copy-api button that was clicked.
   * @returns {Promise<void>} Resolves once copied (or the failure alerted).
   */
  async function copyApiSample(btn) {
    const targetId = btn.getAttribute('data-copy-target');
    if (!targetId) return;
    const source = document.getElementById(targetId);
    if (!source) return;
    const text = source.textContent || '';
    try {
      await navigator.clipboard.writeText(text.trim());
      btn.textContent = '복사됨';
      setTimeout(() => { btn.textContent = targetId.includes('curl') ? 'cURL 복사' : 'fetch 복사'; }, 1200);
    } catch {
      alert('클립보드 복사에 실패했습니다.');
    }
  }

  document.querySelectorAll('.js-copy-api').forEach((btn) => {
    btn.addEventListener('click', () => copyApiSample(btn));
  });

  document.querySelectorAll('.js-issue-card').forEach((card) => {
    card.addEventListener('click', (event) => {
      if (event.target.closest('a') || event.target.closest('button')) return;
      const url = card.getAttribute('data-url');
      if (!url) return;
      window.open(url, '_blank', 'noopener,noreferrer');
    });
  });
})();
