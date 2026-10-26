/**
 * @file Magazine post page (board_detail_magazine.html): the page-flip viewer
 * built from the post's content blocks (with a linear reading mode for small
 * screens and print, and view options for two-page spreads and full width that
 * are remembered in this browser; showing bilingual text in both languages
 * switches to the reading mode), the name prompt of the "save as layout
 * template" form, and hiding a duplicated title in HTML-bodied posts. The
 * action bar, scroll progress and recent-posts history are shared with the
 * Markdown page in board_detail.js.
 *
 * Load it WITHOUT defer right after board_detail.js: the viewer is built while
 * the page is parsed, before _reading_enhancements.html adds code-block
 * headers to it. Block geometry and borders go to board_detail_magazine.css as
 * --mag-* custom properties; only measured values (scale, offset, height) are
 * written as inline styles.
 */
(function initBoardDetailMagazine() {
  /**
   * Build the page-flip viewer (slides, nav bar, dots, reading-mode toggle and
   * reader) into #magazine-viewer-root from the #content-blocks-data JSON.
   * Does nothing when the root, the data or any page is missing.
   *
   * @returns {void}
   */
  function initPageViewer() {
    const root = document.getElementById('magazine-viewer-root');
    if (!root) return;
    const raw = document.getElementById('content-blocks-data');
    if (!raw) return;

    let data;
    try { data = JSON.parse(raw.textContent); } catch { return; }

    let pages = [];
    if (data.v === 3 && Array.isArray(data.pages) && data.pages.length) {
      pages = data.pages;
    } else if ((data.v === 2 || data.cw) && Array.isArray(data.blocks)) {
      pages = [data];
    } else { return; }

    if (!pages.length) return;

    /**
     * Build one slide's inner HTML: the page's original canvas (cw×ch px) with
     * its blocks absolutely positioned in percent, later scaled to the viewer
     * width by scaleSlides() so text shrinks uniformly (no clipping on mobile).
     *
     * @param {Object} page - Page data: cw, ch and blocks.
     * @returns {string} HTML for the slide.
     */
    function buildSlideHTML(page) {
      const cw = page.cw || 1200, ch = page.ch || 800;
      let html = `<div class="mag-fit" data-cw="${cw}" data-ch="${ch}">`;
      html += `<div class="magazine-layout" style="--mag-cw:${cw}px;--mag-ch:${ch}px;">`;
      (page.blocks || []).forEach(b => {
        const L = (b.x / cw * 100).toFixed(3);
        const T = (b.y / ch * 100).toFixed(3);
        const W = (b.w / cw * 100).toFixed(3);
        const H = (b.h / ch * 100).toFixed(3);
        const br = b.showBorder ? (b.borderRadius >= 9999 ? '9999px' : `${b.borderRadius ?? 0}px`) : '';
        const border = b.showBorder ? `--mag-bw:${b.borderWidth ?? 1}px;--mag-bc:${b.borderColor ?? '#000000'};--mag-br:${br};` : '';
        const cls = 'mag-block' + (b.showBorder ? ' mag-block-bordered' : '');
        const s = `--mag-x:${L}%;--mag-y:${T}%;--mag-w:${W}%;--mag-h:${H}%;${border}`;
        if (b.type === 'image' && b.src) {
          const ox = (b.imgOffsetX ?? 50).toFixed(1), oy = (b.imgOffsetY ?? 50).toFixed(1);
          const fc = b.imgFilter && b.imgFilter !== 'none' ? ` mag-filter-${b.imgFilter}` : '';
          html += `<div class="${cls}" style="${s}"><img class="mag-block-img${fc}" src="${b.src}" style="--mag-ox:${ox}%;--mag-oy:${oy}%;"></div>`;
        } else if (b.type === 'spacer') {
          html += `<div class="${cls}" style="${s}"></div>`;
        } else {
          html += `<div class="${cls}${b.dropCap ? ' mag-dropcap' : ''}" style="${s}">${b.content || ''}</div>`;
        }
      });
      html += '</div></div>';
      return html;
    }

    /**
     * Build the reader (linear reading mode): every page's blocks stacked
     * full width, top-to-bottom then left-to-right, with a font size estimated
     * from each block's width (clamped to a readable range).
     *
     * @returns {string} HTML for the reader.
     */
    function buildReaderHTML() {
      let html = '';
      pages.forEach((page, pi) => {
        const cw = page.cw || 1200;
        if (pi > 0) html += '<div class="reader-page-sep" aria-hidden="true"></div>';
        const blocks = (page.blocks || []).slice().sort((a, b) => (a.y - b.y) || (a.x - b.x));
        blocks.forEach(b => {
          if (b.type === 'image' && b.src) {
            const fc = b.imgFilter && b.imgFilter !== 'none' ? ` mag-filter-${b.imgFilter}` : '';
            html += `<figure class="reader-block"><img class="reader-img${fc}" src="${b.src}" loading="lazy"></figure>`;
          } else if (b.type === 'spacer') {
            html += '<div class="reader-spacer"></div>';
          } else if (b.content) {
            const rel = Math.max(0.85, Math.min(1.9, (b.w || cw) / cw * 2.2));
            html += `<div class="reader-block reader-text${b.dropCap ? ' mag-dropcap' : ''}" style="--reader-fs:${rel.toFixed(2)}rem;">${b.content}</div>`;
          }
        });
      });
      return `<div class="mag-reader-inner">${html}</div>`;
    }

    // ── Build DOM ──────────────────────────────────────────
    const viewer = document.createElement('div');
    viewer.className = 'page-viewer';

    const track = document.createElement('div');
    track.className = 'page-track';

    // One slide per page; slides are grouped into views (one page, or a
    // two-page spread) by buildViews().
    const slides = pages.map(page => {
      const slide = document.createElement('div');
      slide.className = 'page-slide';
      slide.innerHTML = buildSlideHTML(page);
      return slide;
    });

    viewer.appendChild(track);
    root.appendChild(viewer);

    // Nav bar
    const navBar  = document.createElement('div'); navBar.className = 'page-nav-bar';
    const prevBtn = document.createElement('button'); prevBtn.className = 'page-nav-btn'; prevBtn.innerHTML = '&#8249;';
    const counter = document.createElement('div');   counter.className = 'page-counter';
    const nextBtn = document.createElement('button'); nextBtn.className = 'page-nav-btn'; nextBtn.innerHTML = '&#8250;';
    navBar.appendChild(prevBtn); navBar.appendChild(counter); navBar.appendChild(nextBtn);
    root.appendChild(navBar);

    // Dots
    const dotsBar = document.createElement('div'); dotsBar.className = 'page-dots';
    const dots = pages.map((_, i) => {
      const d = document.createElement('button');
      d.className = 'page-dot' + (i === 0 ? ' active' : '');
      d.addEventListener('click', () => goTo(viewOfPage(i)));
      dotsBar.appendChild(d);
      return d;
    });
    root.appendChild(dotsBar);

    // ── 읽기 모드 (모바일 가독성) ───────────────────────────
    const reader = document.createElement('div');
    reader.className = 'mag-reader';
    reader.innerHTML = buildReaderHTML();
    root.appendChild(reader);

    const modeToggle = document.createElement('button');
    modeToggle.type = 'button';
    modeToggle.className = 'mag-mode-toggle';

    /**
     * Label the mode toggle with the mode it switches to.
     *
     * @returns {void}
     */
    function syncToggleLabel() {
      modeToggle.innerHTML = root.classList.contains('reader-on')
        ? '<i class="bi bi-easel2"></i> 매거진 모드'
        : '<i class="bi bi-text-paragraph"></i> 읽기 모드';
    }
    modeToggle.addEventListener('click', () => {
      root.classList.toggle('reader-on');
      syncToggleLabel();
      // 매거진 페이지(고정 크기 블록)엔 두 언어가 다 들어가지 않으므로 마지막 한 언어로
      if (!root.classList.contains('reader-on') && document.documentElement.dataset.contentLang === 'both') {
        document.dispatchEvent(new CustomEvent('bilingual:set', { detail: { lang: lastSingleLang } }));
      }
      applyLayout();
    });

    // ── 이중 언어 글: '함께'는 읽기 모드에서 (static/js/bilingual.js 이벤트) ──
    let lastSingleLang = 'ko';
    document.addEventListener('bilingual:change', e => {
      const lang = e.detail.lang;
      if (lang !== 'both') { lastSingleLang = lang; return; }
      if (root.classList.contains('reader-on')) return;
      root.classList.add('reader-on');
      syncToggleLabel();
      applyLayout();
    });

    // ── 보기 옵션: 두 페이지(펼침면) · 전체 폭 ───────────────
    let spreadPref = readPref(PREF_SPREAD) === '1';
    let fullPref = readPref(PREF_FULL) === '1';
    const spreadToggle = makeOptionToggle('bi-book', '두 페이지', () => {
      spreadPref = !spreadPref;
      savePref(PREF_SPREAD, spreadPref);
      applyLayout();
    });
    const fullToggle = makeOptionToggle('bi-arrows-angle-expand', '전체 폭', () => {
      fullPref = !fullPref;
      savePref(PREF_FULL, fullPref);
      applyLayout();
    });

    const modeBar = document.createElement('div');
    modeBar.className = 'mag-mode-bar';
    modeBar.append(modeToggle, spreadToggle, fullToggle);
    root.insertBefore(modeBar, root.firstChild);
    if (window.innerWidth < 640) root.classList.add('reader-on');  // 모바일 기본 읽기 모드
    syncToggleLabel();

    // ── State & transition ────────────────────────────────
    let views = [];    // page indices shown together: [[0], [1], …] or [[0, 1], [2, 3], …]
    let viewEls = [];  // one .page-view per entry of views
    let current = 0, animating = false;  // current is an index into views
    const HALF = 210; // ms for each half of the flip

    /**
     * Whether pages are shown as two-page spreads right now: the viewer asked
     * for it, there is more than one page and the screen is wide enough.
     *
     * @returns {boolean} True for spreads.
     */
    function spreadActive() {
      return spreadPref && pages.length > 1 && (root.clientWidth || window.innerWidth) >= SPREAD_MIN_WIDTH;
    }

    /**
     * Index of the view that shows a page.
     *
     * @param {number} page - Page index.
     * @returns {number} View index (0 when not found).
     */
    function viewOfPage(page) {
      return Math.max(0, views.findIndex(v => v.includes(page)));
    }

    /**
     * Regroup the slides into views (single pages or spreads of 1–2, 3–4, …)
     * and keep the given page on screen.
     *
     * @param {boolean} spread - Build two-page spreads.
     * @param {number} keepPage - Page index that should stay visible.
     * @returns {void}
     */
    function buildViews(spread, keepPage) {
      views = [];
      for (let i = 0; i < pages.length; i += spread ? 2 : 1) {
        views.push(spread && i + 1 < pages.length ? [i, i + 1] : [i]);
      }
      viewEls = views.map(v => {
        const el = document.createElement('div');
        el.className = 'page-view' + (v.length > 1 ? ' has-pair' : '');
        v.forEach(i => el.appendChild(slides[i]));
        return el;
      });
      track.replaceChildren(...viewEls);
      root.classList.toggle('spread-on', spread);
      current = viewOfPage(keepPage);
    }

    /**
     * Put one flip animation class on a view (or none), removing the others.
     *
     * @param {HTMLElement} el - A .page-view.
     * @param {?string} cls - Flip class to add, or null.
     * @returns {void}
     */
    function setFlip(el, cls) {
      el.classList.remove(...FLIP_CLASSES);
      if (cls) el.classList.add(cls);
    }

    /**
     * Sync the dots, page counter and prev/next buttons with a view.
     *
     * @param {number} idx - View index.
     * @returns {void}
     */
    function syncNav(idx) {
      const shown = views[idx];
      dots.forEach((d, i) => d.classList.toggle('active', shown.includes(i)));
      const first = shown[0] + 1, last = shown[shown.length - 1] + 1;
      counter.textContent = `${first === last ? first : `${first}–${last}`} / ${pages.length}`;
      prevBtn.disabled = idx <= 0;
      nextBtn.disabled = idx >= views.length - 1;
    }

    /**
     * Show only the view at idx, without animation, and sync the navigation.
     *
     * @param {number} idx - View index.
     * @returns {void}
     */
    function showImmediate(idx) {
      viewEls.forEach((el, i) => {
        el.hidden = i !== idx;
        setFlip(el, null);
      });
      syncNav(idx);
    }

    /**
     * Flip to another view: the current one turns away from the spine, then
     * the next one turns in (HALF ms each). Ignored while a flip is running or
     * when next is out of range.
     *
     * @param {number} next - Target view index.
     * @param {number} [dir] - 1 for forward, -1 for backward; derived from next when omitted.
     * @returns {void}
     */
    function goTo(next, dir) {
      if (animating || next === current) return;
      if (next < 0 || next >= views.length) return;
      if (dir === undefined) dir = next > current ? 1 : -1;
      animating = true;

      const outView = viewEls[current];
      const inView  = viewEls[next];

      // Show both for transition
      viewEls.forEach(el => { el.hidden = true; });
      outView.hidden = false;
      inView.hidden  = false;

      // Outgoing: flip away from spine
      setFlip(outView, dir > 0 ? 'flip-out-left' : 'flip-out-right');

      setTimeout(() => {
        outView.hidden = true;
        // Incoming: flip in from spine
        setFlip(inView, dir > 0 ? 'flip-in-right' : 'flip-in-left');

        setTimeout(() => {
          current = next;
          showImmediate(current);
          animating = false;
        }, HALF);
      }, HALF);

      // Update UI immediately
      syncNav(next);
    }

    /**
     * Show the view options that apply: spreads only in magazine mode, with
     * two or more pages, on a wide enough screen. Pressed state follows the
     * viewer's choices.
     *
     * @returns {void}
     */
    function syncOptionToggles() {
      spreadToggle.hidden = root.classList.contains('reader-on') || pages.length < 2
        || (root.clientWidth || window.innerWidth) < SPREAD_MIN_WIDTH;
      spreadToggle.setAttribute('aria-pressed', String(spreadPref));
      fullToggle.setAttribute('aria-pressed', String(fullPref));
    }

    /**
     * Apply the view options: regroup into spreads or single pages when that
     * changed (keeping the current page), set full width, and rescale.
     * Waits for a running flip to finish first.
     *
     * @returns {void}
     */
    function applyLayout() {
      if (animating) { setTimeout(applyLayout, HALF * 2 + 20); return; }
      const spread = spreadActive();
      if (!viewEls.length || spread !== root.classList.contains('spread-on')) {
        buildViews(spread, viewEls.length ? views[current][0] : 0);
        showImmediate(current);
      }
      root.classList.toggle('full-on', fullPref);
      syncOptionToggles();
      scaleSlides();
    }

    prevBtn.addEventListener('click', () => goTo(current - 1, -1));
    nextBtn.addEventListener('click', () => goTo(current + 1,  1));

    document.addEventListener('keydown', e => {
      if (e.key === 'ArrowRight' || e.key === 'ArrowDown') goTo(current + 1,  1);
      if (e.key === 'ArrowLeft'  || e.key === 'ArrowUp')   goTo(current - 1, -1);
    });

    let tx = 0;
    viewer.addEventListener('touchstart', e => { tx = e.touches[0].clientX; }, { passive: true });
    viewer.addEventListener('touchend', e => {
      const dx = e.changedTouches[0].clientX - tx;
      if (Math.abs(dx) > 50) goTo(current + (dx < 0 ? 1 : -1), dx < 0 ? 1 : -1);
    });

    /**
     * Scale every page's original canvas uniformly to the width of its slot
     * (the viewer, or half of it for spreads), center canvases narrower than
     * the slot and size each .mag-fit to the scaled height. Pages are never
     * enlarged unless full width is on. Hidden slides use the same slot width.
     *
     * @returns {void}
     */
    function scaleSlides() {
      const w = viewer.clientWidth || viewer.offsetWidth || root.clientWidth;
      if (!w) return;
      const probe = root.classList.contains('spread-on') && viewEls[current]?.querySelector('.page-slide');
      const slotW = (probe && probe.clientWidth) || w;
      slides.forEach(slide => {
        const fit = slide.querySelector('.mag-fit');
        if (!fit) return;
        const cw = +fit.dataset.cw || 1200, ch = +fit.dataset.ch || 800;
        const scale = fullPref ? slotW / cw : Math.min(1, slotW / cw);
        const canvas = fit.querySelector('.magazine-layout');
        if (canvas) {
          canvas.style.transform = 'scale(' + scale + ')'; // conventions: allow (scale measured from the viewer width)
          // conventions: allow (centering offset measured from the viewer width)
          canvas.style.left = Math.max(0, (slotW - cw * scale) / 2) + 'px';   // 칸보다 좁은 캔버스는 가운데 정렬
        }
        fit.style.height = (ch * scale) + 'px'; // conventions: allow (scaled canvas height)
      });
    }
    applyLayout();
    let _rz;
    window.addEventListener('resize', () => { clearTimeout(_rz); _rz = setTimeout(applyLayout, 120); });
  }

  // 보기 옵션 (펼침면·전체 폭): 이 브라우저에만 기억하는 개인 설정
  const PREF_SPREAD = 'magViewer.spread';
  const PREF_FULL = 'magViewer.full';
  const SPREAD_MIN_WIDTH = 900;  // px; narrower screens always show one page
  const FLIP_CLASSES = ['flip-out-left', 'flip-in-right', 'flip-out-right', 'flip-in-left'];

  /**
   * Read a saved viewer preference.
   *
   * @param {string} key - localStorage key.
   * @returns {?string} The stored value, or null when unset or storage is unavailable.
   */
  function readPref(key) {
    try { return localStorage.getItem(key); } catch { return null; }
  }

  /**
   * Save a viewer preference as "1" or "0" (best effort).
   *
   * @param {string} key - localStorage key.
   * @param {boolean} on - The setting.
   * @returns {void}
   */
  function savePref(key, on) {
    try { localStorage.setItem(key, on ? '1' : '0'); } catch { /* storage unavailable: the choice lasts for this page only */ }
  }

  /**
   * Build a pressed/unpressed option button for the mode bar.
   *
   * @param {string} icon - Bootstrap Icons class (e.g. "bi-book").
   * @param {string} label - Visible label.
   * @param {function(): void} onClick - Called after a click.
   * @returns {HTMLButtonElement} The button (aria-pressed is set by the caller).
   */
  function makeOptionToggle(icon, label, onClick) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'mag-mode-toggle mag-option-toggle';
    btn.innerHTML = `<i class="bi ${icon}" aria-hidden="true"></i> ${label}`;
    btn.addEventListener('click', onClick);
    return btn;
  }

  /**
   * Ask for the layout name before "save as layout template" submits,
   * prefilled with the hidden name field; cancelling the prompt cancels the
   * submit. The prompt text comes from the form's data-name-prompt.
   *
   * @returns {void}
   */
  function bindLayoutTemplateForm() {
    const form = document.querySelector('[data-layout-template-form]');
    if (!form) return;
    form.addEventListener('submit', (event) => {
      const n = prompt(form.dataset.namePrompt, form.querySelector('[name=name]').value);
      if (n === null) { event.preventDefault(); return; }
      form.querySelector('[name=name]').value = n;
    });
  }

  /**
   * Hide the body's first element when it is an <h1> (it repeats the page
   * title) in posts rendered as HTML instead of content blocks.
   *
   * @returns {void}
   */
  function hideDuplicateTitle() {
    const content = document.querySelector('.magazine-content .markdown-content');
    if (content) {
      const firstEl = content.firstElementChild;
      if (firstEl && firstEl.tagName === 'H1') {
        firstEl.hidden = true;
      }
    }
  }

  initPageViewer();
  bindLayoutTemplateForm();
  document.addEventListener('DOMContentLoaded', hideDuplicateTitle);
})();
