/**
 * @file Magazine post page (board_detail_magazine.html): the page-flip viewer
 * built from the post's content blocks (with a linear reading mode for small
 * screens and print), the name prompt of the "save as layout template" form,
 * and hiding a duplicated title in HTML-bodied posts. The action bar, scroll
 * progress and recent-posts history are shared with the Markdown page in
 * board_detail.js.
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

    const slides = pages.map((page, i) => {
      const slide = document.createElement('div');
      slide.className = 'page-slide';
      slide.innerHTML = buildSlideHTML(page);
      track.appendChild(slide);
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
      d.addEventListener('click', () => goTo(i));
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
      if (!root.classList.contains('reader-on')) scaleSlides();
    });
    const modeBar = document.createElement('div');
    modeBar.className = 'mag-mode-bar';
    modeBar.appendChild(modeToggle);
    root.insertBefore(modeBar, root.firstChild);
    if (window.innerWidth < 640) root.classList.add('reader-on');  // 모바일 기본 읽기 모드
    syncToggleLabel();

    // ── State & transition ────────────────────────────────
    let current = 0, animating = false;
    const HALF = 210; // ms for each half of the flip

    /**
     * Show only the slide at idx, without animation, and sync the dots,
     * counter and prev/next buttons.
     *
     * @param {number} idx - Slide index.
     * @returns {void}
     */
    function showImmediate(idx) {
      slides.forEach((s, i) => {
        s.hidden = i !== idx;
        s.className = 'page-slide';
      });
      dots.forEach((d, i) => d.classList.toggle('active', i === idx));
      counter.textContent = `${idx + 1} / ${pages.length}`;
      prevBtn.disabled = idx <= 0;
      nextBtn.disabled = idx >= pages.length - 1;
    }

    /**
     * Flip to another slide: the current one turns away from the spine, then
     * the next one turns in (HALF ms each). Ignored while a flip is running or
     * when next is out of range.
     *
     * @param {number} next - Target slide index.
     * @param {number} [dir] - 1 for forward, -1 for backward; derived from next when omitted.
     * @returns {void}
     */
    function goTo(next, dir) {
      if (animating || next === current) return;
      if (next < 0 || next >= pages.length) return;
      if (dir === undefined) dir = next > current ? 1 : -1;
      animating = true;

      const outSlide = slides[current];
      const inSlide  = slides[next];

      // Show both for transition
      slides.forEach(s => { s.hidden = true; });
      outSlide.hidden = false;
      inSlide.hidden  = false;

      // Outgoing: flip away from spine
      outSlide.className = 'page-slide ' + (dir > 0 ? 'flip-out-left' : 'flip-out-right');

      setTimeout(() => {
        outSlide.hidden = true;
        // Incoming: flip in from spine
        inSlide.className = 'page-slide ' + (dir > 0 ? 'flip-in-right' : 'flip-in-left');

        setTimeout(() => {
          inSlide.className = 'page-slide';
          current = next;
          showImmediate(current);
          animating = false;
        }, HALF);
      }, HALF);

      // Update UI immediately
      dots.forEach((d, i) => d.classList.toggle('active', i === next));
      counter.textContent = `${next + 1} / ${pages.length}`;
      prevBtn.disabled = next <= 0;
      nextBtn.disabled = next >= pages.length - 1;
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
     * Scale every page's original canvas uniformly to the viewer width
     * (never above 1), center canvases narrower than the screen and size each
     * .mag-fit to the scaled height. Hidden slides use the viewer width too.
     *
     * @returns {void}
     */
    function scaleSlides() {
      const w = viewer.clientWidth || viewer.offsetWidth || root.clientWidth;
      if (!w) return;
      slides.forEach(slide => {
        const fit = slide.querySelector('.mag-fit');
        if (!fit) return;
        const cw = +fit.dataset.cw || 1200, ch = +fit.dataset.ch || 800;
        const scale = Math.min(1, w / cw);
        const canvas = fit.querySelector('.magazine-layout');
        if (canvas) {
          canvas.style.transform = 'scale(' + scale + ')'; // conventions: allow (scale measured from the viewer width)
          // conventions: allow (centering offset measured from the viewer width)
          canvas.style.left = Math.max(0, (w - cw * scale) / 2) + 'px';   // 화면보다 좁은 캔버스는 가운데 정렬
        }
        fit.style.height = (ch * scale) + 'px'; // conventions: allow (scaled canvas height)
      });
    }
    scaleSlides();
    let _rz;
    window.addEventListener('resize', () => { clearTimeout(_rz); _rz = setTimeout(scaleSlides, 120); });

    showImmediate(0);
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
