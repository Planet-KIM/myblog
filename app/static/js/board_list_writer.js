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

  function buildQueryUrl() {
    const params = new URLSearchParams(new FormData(form));
    if (!params.get("scope")) params.set("scope", "all");
    if (!params.get("sort")) params.set("sort", "recent");
    if (!params.has("category_id")) params.set("category_id", "");
    if (!params.get("page")) params.set("page", "1");
    return `/board/?${params.toString()}`;
  }

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

  function triggerFilter(resetPage) {
    if (resetPage) {
      ensureHiddenInput("page", "1");
    }
    refreshBoardResults(buildQueryUrl());
  }

  form.addEventListener("submit", function onSubmit(event) {
    event.preventDefault();
    triggerFilter(true);
  });

  if (searchInput) {
    searchInput.addEventListener("input", function onInput() {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(function runSearch() {
        triggerFilter(true);
      }, 280);
    });
  }

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
