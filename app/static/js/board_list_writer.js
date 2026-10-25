/**
 * @file Archive page (/board/) behavior: in-place filtering/search (AJAX) and
 * whole-card links on the story list. Loaded by templates/board_list_writer.html.
 */

/**
 * Re-render the results region in place when the search, a filter link or a
 * pagination link changes, keeping the URL and hidden form fields in sync.
 * Does nothing when the page has no search form or results region.
 *
 * @returns {void}
 */
(function setupBoardListRealtimeFilter() {
  const form = document.getElementById("board-search-form");
  const resultsRegion = document.getElementById("board-results-region");
  const searchInput = document.getElementById("searchInput");

  if (!form || !resultsRegion) {
    return;
  }

  let debounceTimer = null;
  let controller = null;
  let requestSeq = 0;

  /**
   * Set a hidden input on the search form, creating it if missing.
   *
   * @param {string} name - Input name (scope, sort, category_id, page).
   * @param {string} value - Value to set.
   * @returns {void}
   */
  function ensureHiddenInput(name, value) {
    let input = form.querySelector(`input[name="${name}"]`);
    if (!input) {
      input = document.createElement("input");
      input.type = "hidden";
      input.name = name;
      form.appendChild(input);
    }
    input.value = value;
  }

  /**
   * Copy the filter parameters of a list URL into the form and search box.
   *
   * @param {string} url - Absolute or root-relative /board/ URL.
   * @returns {void}
   */
  function syncHiddenInputsFromUrl(url) {
    const parsed = new URL(url, window.location.origin);
    ensureHiddenInput("scope", parsed.searchParams.get("scope") || "all");
    ensureHiddenInput("sort", parsed.searchParams.get("sort") || "recent");
    ensureHiddenInput("category_id", parsed.searchParams.get("category_id") || "");
    ensureHiddenInput("page", parsed.searchParams.get("page") || "1");
    if (searchInput) {
      searchInput.value = parsed.searchParams.get("q") || "";
    }
  }

  /**
   * Build the /board/ URL for the form's current values, with defaults
   * for any missing filter.
   *
   * @returns {string} Root-relative URL such as "/board/?scope=all&sort=recent…".
   */
  function buildQueryUrl() {
    const params = new URLSearchParams(new FormData(form));
    if (!params.get("scope")) params.set("scope", "all");
    if (!params.get("sort")) params.set("sort", "recent");
    if (!params.has("category_id")) params.set("category_id", "");
    if (!params.get("page")) params.set("page", "1");
    return `/board/?${params.toString()}`;
  }

  /**
   * Fetch a list URL and swap its results region into the page.
   *
   * Aborts the previous request and ignores out-of-order responses. Falls back
   * to a full navigation on redirects or when the response has no results
   * region; other errors are logged and leave the current results in place.
   *
   * @param {string} url - Root-relative /board/ URL to load.
   * @returns {Promise<void>}
   */
  async function refreshBoardResults(url) {
    const currentReq = ++requestSeq;
    if (controller) {
      controller.abort();
    }
    controller = new AbortController();
    resultsRegion.classList.add("is-loading");

    try {
      const response = await fetch(url, {
        credentials: "same-origin",
        headers: { "X-Requested-With": "XMLHttpRequest" },
        signal: controller.signal,
      });

      if (response.redirected) {
        window.location.href = response.url;
        return;
      }
      if (!response.ok) {
        throw new Error("failed to fetch board list");
      }

      const html = await response.text();
      if (currentReq !== requestSeq) return;

      const doc = new DOMParser().parseFromString(html, "text/html");
      const nextRegion = doc.getElementById("board-results-region");
      if (!nextRegion) {
        window.location.href = url;
        return;
      }

      resultsRegion.innerHTML = nextRegion.innerHTML;
      history.replaceState({}, "", url);
      syncHiddenInputsFromUrl(url);
    } catch (error) {
      if (error && error.name === "AbortError") {
        return;
      }
      console.error(error);
    } finally {
      if (currentReq === requestSeq) {
        resultsRegion.classList.remove("is-loading");
      }
    }
  }

  /**
   * Reload the results for the form's current values.
   *
   * @param {boolean} resetPage - Go back to page 1 first (new search/filter).
   * @returns {void}
   */
  function triggerFilter(resetPage) {
    if (resetPage) {
      ensureHiddenInput("page", "1");
    }
    refreshBoardResults(buildQueryUrl());
  }

  /** Search form submit: filter in place instead of reloading the page. */
  form.addEventListener("submit", function onSubmit(event) {
    event.preventDefault();
    triggerFilter(true);
  });

  if (searchInput) {
    /** Live search: filter 280 ms after the last keystroke. */
    searchInput.addEventListener("input", function onInput() {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(function runSearch() {
        triggerFilter(true);
      }, 280);
    });
  }

  /**
   * Filter and pagination links (a.js-board-filter-link) load in place.
   * Filter links reset to page 1; the current search text is kept.
   */
  resultsRegion.addEventListener("click", function onRegionClick(event) {
    const link = event.target.closest("a.js-board-filter-link");
    if (!link) {
      return;
    }

    const href = link.getAttribute("href");
    if (!href) {
      return;
    }

    event.preventDefault();
    const url = new URL(href, window.location.origin);
    const isPagerLink = link.classList.contains("page-link");

    if (!isPagerLink) {
      url.searchParams.set("page", "1");
    }
    if (searchInput) {
      const currentQuery = searchInput.value || "";
      if (currentQuery) {
        url.searchParams.set("q", currentQuery);
      } else {
        url.searchParams.delete("q");
      }
    }

    refreshBoardResults(`${url.pathname}${url.search}`);
  });
})();

/**
 * Make each whole story card a link to its post (replaces the inline onclick).
 *
 * Delegated on document so cards that the AJAX filter re-renders keep
 * working. Like the old inline handler, it runs for every click inside a card,
 * including clicks on the links within it.
 *
 * @returns {void}
 */
(function setupStoryCardLinks() {
  /**
   * Navigate to the post of the story card that was clicked, if any.
   *
   * @param {MouseEvent} event - Click anywhere in the document.
   * @returns {void}
   */
  function openStoryCard(event) {
    const card = event.target.closest("[data-card-href]");
    if (card) {
      window.location.href = card.dataset.cardHref;
    }
  }

  document.addEventListener("click", openStoryCard);
})();
