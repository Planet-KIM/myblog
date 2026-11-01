/**
 * @file home.js — Main page (index) interaction layer
 * (검색 단축키, 좋아요/북마크/팔로우, 뉴스레터, 이어 읽기, 정렬 자동 적용,
 * 이미지 받침판 색, 커버 레일 넘기기, 맨 위 메뉴 선)
 */

document.addEventListener('DOMContentLoaded', function () {
  const searchInput = document.getElementById('home-search-input');

  /* ── Global search shortcut (Ctrl/Cmd + K, /) ───────────── */
  document.addEventListener('keydown', (event) => {
    const target = event.target;
    const inEditable =
      target instanceof HTMLElement &&
      (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable);
    if (!searchInput) return;

    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
      event.preventDefault();
      searchInput.focus();
      searchInput.select();
      return;
    }

    if (!inEditable && event.key === '/') {
      event.preventDefault();
      searchInput.focus();
    }
  });

  /* ── Engagement actions (like/bookmark/follow) ───────────── */
  /**
   * POST to an engagement API and return its JSON body.
   *
   * @param {string} url - Endpoint to call.
   * @param {Object} [body] - Optional payload, sent as JSON.
   * @returns {Promise<Object>} Parsed response.
   * @throws {Error} With a user-facing message when the response is not OK
   *   ("로그인이 필요합니다." for 401/403).
   */
  async function postAction(url, body) {
    const response = await fetch(url, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: body ? JSON.stringify(body) : null
    });
    if (!response.ok) {
      const message = (response.status === 401 || response.status === 403)
        ? '로그인이 필요합니다.'
        : '요청 처리에 실패했습니다.';
      throw new Error(message);
    }
    return response.json();
  }

  /**
   * Show a message with the global toast helper, or alert() before it exists.
   *
   * @param {string} message - Text to show.
   * @param {string} [type='info'] - Toast method: 'success', 'error', 'warning' or 'info'.
   * @returns {void}
   */
  function toast(message, type = 'info') {
    if (window.toast && typeof window.toast[type] === 'function') {
      window.toast[type](message);
      return;
    }
    alert(message);
  }

  document.querySelectorAll('.js-like-btn').forEach((btn) => {
    btn.addEventListener('click', async (event) => {
      event.preventDefault();
      event.stopPropagation();
      const postId = btn.getAttribute('data-post-id');
      if (!postId) return;
      try {
        const data = await postAction(`/api/posts/${postId}/like`);
        const icon = btn.querySelector('i');
        const count = btn.querySelector('span');
        if (icon) icon.className = data.active ? 'bi bi-hand-thumbs-up-fill' : 'bi bi-hand-thumbs-up';
        if (count) count.textContent = String(data.likes ?? 0);
      } catch (error) {
        toast(error.message, 'warning');
      }
    });
  });

  document.querySelectorAll('.js-bookmark-btn').forEach((btn) => {
    btn.addEventListener('click', async (event) => {
      event.preventDefault();
      event.stopPropagation();
      const postId = btn.getAttribute('data-post-id');
      if (!postId) return;
      try {
        const data = await postAction(`/api/posts/${postId}/bookmark`);
        const icon = btn.querySelector('i');
        if (icon) icon.className = data.active ? 'bi bi-bookmark-check-fill' : 'bi bi-bookmark';
      } catch (error) {
        toast(error.message, 'warning');
      }
    });
  });

  document.querySelectorAll('.js-follow-category-btn').forEach((btn) => {
    btn.addEventListener('click', async (event) => {
      event.preventDefault();
      event.stopPropagation();
      const categoryId = btn.getAttribute('data-category-id');
      if (!categoryId) return;
      try {
        const data = await postAction(`/api/follow/category/${categoryId}`);
        btn.classList.toggle('active', Boolean(data.active));
      } catch (error) {
        toast(error.message, 'warning');
      }
    });
  });

  document.querySelectorAll('.js-follow-author-btn').forEach((btn) => {
    btn.addEventListener('click', async (event) => {
      event.preventDefault();
      event.stopPropagation();
      const authorId = btn.getAttribute('data-author-id');
      if (!authorId) return;
      try {
        const data = await postAction(`/api/follow/author/${authorId}`);
        btn.classList.toggle('active', Boolean(data.active));
      } catch (error) {
        toast(error.message, 'warning');
      }
    });
  });

  /* ── Newsletter subscribe (double opt-in) ───────────────── */
  const newsletterForm = document.getElementById('newsletter-form');
  const newsletterInput = document.getElementById('newsletter-email');
  const newsletterFeedback = document.getElementById('newsletter-feedback');
  if (newsletterForm && newsletterInput && newsletterFeedback) {
    newsletterForm.addEventListener('submit', async (event) => {
      event.preventDefault();
      const email = newsletterInput.value.trim();
      if (!email) return;
      try {
        const result = await postAction('/api/newsletter/subscribe', { email, source: 'home' });
        newsletterFeedback.textContent = result.message || '';
        if (result.verify_url) {
          newsletterFeedback.appendChild(document.createTextNode(' '));
          const link = document.createElement('a');
          link.href = result.verify_url;
          link.target = '_blank';
          link.rel = 'noopener noreferrer';
          link.textContent = '확인 링크 열기';
          newsletterFeedback.appendChild(link);
        }
        newsletterInput.value = '';
      } catch (error) {
        newsletterFeedback.textContent = error.message;
      }
    });
  }

  /* ── Continue reading module (localStorage) ─────────────── */
  /* 읽은 글이 있을 때만 [data-continue-reading] 칸을 보인다 (빈 칸을 두지 않음) */
  const continueList = document.getElementById('continue-reading-list');
  const continueWidget = document.querySelector('[data-continue-reading]');
  if (continueList) {
    let items = [];
    try {
      items = JSON.parse(localStorage.getItem('recentPosts') || '[]');
    } catch (_error) {
      items = [];
    }

    if (Array.isArray(items) && items.length > 0) {
      if (continueWidget) continueWidget.hidden = false;
      continueList.innerHTML = '';
      items.slice(0, 5).forEach((item) => {
        const link = document.createElement('a');
        link.className = 'recent-post-item';
        link.href = item.url || '/';

        const title = document.createElement('span');
        title.className = 'rp-title';
        title.textContent = item.title || 'Untitled';

        const date = document.createElement('span');
        date.className = 'rp-date';
        date.textContent = item.date || '';

        link.appendChild(title);
        link.appendChild(date);
        continueList.appendChild(link);
      });
    }
  }
});

/**
 * Submit a select's form as soon as its value changes (replaces the inline
 * onchange="this.form.submit()" on the home sort select).
 *
 * Mark the control with data-autosubmit. Delegated on document, so it is
 * active from the moment this script runs and also covers controls added
 * later. Like the inline handler it calls form.submit(), which navigates
 * without firing a submit event.
 *
 * @returns {void}
 */
(function setupAutoSubmit() {
  /**
   * Submit the form of the changed [data-autosubmit] control, if any.
   *
   * @param {Event} event - Change event from anywhere in the document.
   * @returns {void}
   */
  function submitOnChange(event) {
    const control = event.target.closest && event.target.closest('[data-autosubmit]');
    if (control && control.form) {
      control.form.submit();
    }
  }

  document.addEventListener('change', submitOnChange);
})();

/**
 * Colour each [data-plate] frame like the edges of its image.
 *
 * Home images are shown whole (object-fit: contain), so a frame of a different
 * shape leaves bars around them. When the four corners of the image share one
 * colour (a cover graphic, a diagram on white), the frame takes that colour
 * and the bars disappear into the picture; photos with busy edges keep the
 * default plate. Cross-origin images taint the canvas and are skipped.
 *
 * @returns {void}
 */
(function setupPlateTint() {
  const SAMPLE = 8;           // the image is shrunk to SAMPLE x SAMPLE pixels
  const MAX_CORNER_SPREAD = 36; // corners further apart than this (per channel) = busy edge

  const canvas = document.createElement('canvas');
  canvas.width = SAMPLE;
  canvas.height = SAMPLE;
  const ctx = canvas.getContext('2d', { willReadFrequently: true });
  if (!ctx) return;

  /**
   * Average the corner pixels of a loaded image, if they agree.
   *
   * @param {HTMLImageElement} img - A loaded, same-origin image.
   * @returns {?number[]} [r, g, b] of the edge, or null for busy or transparent edges.
   */
  function edgeColour(img) {
    ctx.clearRect(0, 0, SAMPLE, SAMPLE);
    ctx.drawImage(img, 0, 0, SAMPLE, SAMPLE);
    const last = SAMPLE - 1;
    const corners = [[0, 0], [last, 0], [0, last], [last, last]]
      .map(([x, y]) => ctx.getImageData(x, y, 1, 1).data);
    if (corners.some((px) => px[3] < 250)) return null;
    const rgb = [0, 1, 2].map((c) => corners.map((px) => px[c]));
    if (rgb.some((values) => Math.max(...values) - Math.min(...values) > MAX_CORNER_SPREAD)) return null;
    return rgb.map((values) => Math.round(values.reduce((a, b) => a + b, 0) / values.length));
  }

  /**
   * Set --plate-bg on the image's [data-plate] frame from its edge colour.
   *
   * @param {HTMLImageElement} img - An image inside a [data-plate] frame.
   * @returns {void}
   */
  function tint(img) {
    const plate = img.closest('[data-plate]');
    if (!plate || !img.naturalWidth) return;
    try {
      const colour = edgeColour(img);
      if (colour) plate.style.setProperty('--plate-bg', `rgb(${colour.join(', ')})`); // conventions: allow (CSS variable)
    } catch (_error) {
      // cross-origin image: the canvas is tainted, keep the default plate
    }
  }

  document.querySelectorAll('[data-plate] img').forEach((img) => {
    if (img.complete) tint(img);
    else img.addEventListener('load', () => tint(img), { once: true });
  });
})();

/**
 * Cover stories rail: slides on a sideways-scrolling track ([data-cover-track]).
 *
 * Native scrolling already handles touch swipes, trackpad swipes and arrow keys
 * (the track is focusable) and CSS scroll-snap stops on a slide. This adds the
 * ‹ › buttons, the bars ([data-cover-to]), dragging with a mouse, and keeps the
 * active bar and the disabled ends in step with the scroll position.
 *
 * It also moves on by itself every --cover-interval (home.css), back to the first
 * slide after the last. The pause button ([data-cover-autoplay]) stops that; it
 * also rests while the mouse is over the rail, keyboard focus is inside it, a
 * finger or a mouse drag is on it, the tab is hidden or the rail is scrolled out
 * of view, and starts paused when the OS asks for reduced motion. Any change of
 * slide starts the countdown over. The rail carries data-autoplay (auto-advance
 * on) and data-playing (counting now) so the active bar can show the countdown.
 *
 * @returns {void}
 */
(function setupCoverRail() {
  const rail = document.querySelector('[data-cover-rail]');
  const track = rail && rail.querySelector('[data-cover-track]');
  if (!track) return;

  const slides = [...track.querySelectorAll('[data-cover-slide]')];
  const bars = [...rail.querySelectorAll('[data-cover-to]')];
  const prev = rail.querySelector('[data-cover-prev]');
  const next = rail.querySelector('[data-cover-next]');
  if (slides.length < 2) return;

  const DRAG_START_PX = 6;     // a press that moves less than this is a click
  const FLICK_PX = 60;         // a drag longer than this moves one slide
  const VISIBLE_RATIO = 0.35;  // auto-advance only while at least this much of the rail is on screen
  const DEFAULT_INTERVAL_MS = 15000;
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const behavior = reducedMotion ? 'auto' : 'smooth';
  const toggle = rail.querySelector('[data-cover-autoplay]');

  let lastIndex = 0;           // slide shown at the last sync (also re-aligned after a resize)

  /**
   * Index of the slide the track is showing, from its scroll position.
   *
   * @returns {number} 0-based slide index.
   */
  function currentIndex() {
    const maxScroll = track.scrollWidth - track.clientWidth;
    if (track.scrollLeft >= maxScroll - 2) return slides.length - 1;
    let best = 0;
    slides.forEach((slide, i) => {
      if (Math.abs(slide.offsetLeft - track.scrollLeft) < Math.abs(slides[best].offsetLeft - track.scrollLeft)) best = i;
    });
    return best;
  }

  /**
   * Scroll the track so slide ``index`` is in view.
   *
   * @param {number} index - Slide to show; clamped to the slides that exist.
   * @param {ScrollBehavior} [how] - 'smooth' or 'auto'.
   * @returns {void}
   */
  function goTo(index, how = behavior) {
    const target = slides[Math.max(0, Math.min(slides.length - 1, index))];
    track.scrollTo({ left: target.offsetLeft, behavior: how });
  }

  /**
   * Mark the visible slide (.is-current), light its bar, disable ‹ › at the ends,
   * and start the auto-advance countdown over when the slide has changed.
   *
   * @returns {void}
   */
  function syncControls() {
    const index = currentIndex();
    if (index !== lastIndex) {
      lastIndex = index;
      restartCountdown();
    }
    slides.forEach((slide, i) => slide.classList.toggle('is-current', i === index));
    bars.forEach((bar, i) => {
      bar.classList.toggle('active', i === index);
      if (i === index) bar.setAttribute('aria-current', 'true');
      else bar.removeAttribute('aria-current');
    });
    if (prev) prev.disabled = index === 0;
    if (next) next.disabled = index === slides.length - 1;
  }

  let frame = 0;
  track.addEventListener('scroll', () => {
    cancelAnimationFrame(frame);
    frame = requestAnimationFrame(syncControls);
  }, { passive: true });

  if (prev) prev.addEventListener('click', () => goTo(currentIndex() - 1));
  if (next) next.addEventListener('click', () => goTo(currentIndex() + 1));
  bars.forEach((bar) => bar.addEventListener('click', () => goTo(Number(bar.dataset.coverTo))));

  /* 마우스 끌기: 손을 떼면 끈 방향으로 한 장, 짧게 끌었으면 제자리로. 끈 뒤의 클릭은 막는다 */
  let drag = null;
  let swallowClick = false;

  /**
   * Follow the mouse while dragging the track.
   *
   * @param {PointerEvent} event - pointermove on window.
   * @returns {void}
   */
  function onDragMove(event) {
    const dx = event.clientX - drag.startX;
    if (!drag.moved && Math.abs(dx) < DRAG_START_PX) return;
    if (!drag.moved) {
      drag.moved = true;
      track.classList.add('is-dragging');
    }
    track.scrollLeft = drag.startScroll - dx;
  }

  /**
   * Finish a drag: settle on a slide and stop listening.
   *
   * @param {PointerEvent} event - pointerup or pointercancel on window.
   * @returns {void}
   */
  function onDragEnd(event) {
    window.removeEventListener('pointermove', onDragMove);
    window.removeEventListener('pointerup', onDragEnd);
    window.removeEventListener('pointercancel', onDragEnd);
    if (drag.moved) {
      const dx = event.clientX - drag.startX;
      const step = dx <= -FLICK_PX ? 1 : dx >= FLICK_PX ? -1 : 0;
      track.classList.remove('is-dragging');
      goTo(drag.startIndex + step);
      swallowClick = true;
    }
    drag = null;
    release('drag');
  }

  track.addEventListener('pointerdown', (event) => {
    if (event.pointerType !== 'mouse' || event.button !== 0) return;
    event.preventDefault(); // 글자 선택·이미지 끌기 대신 레일을 끈다
    hold('drag');
    drag = { startX: event.clientX, startScroll: track.scrollLeft, startIndex: currentIndex(), moved: false };
    window.addEventListener('pointermove', onDragMove);
    window.addEventListener('pointerup', onDragEnd);
    window.addEventListener('pointercancel', onDragEnd);
  });

  track.addEventListener('click', (event) => {
    if (!swallowClick) return;
    swallowClick = false;
    event.preventDefault();
    event.stopPropagation();
  }, true);

  /* 창 크기가 바뀌면 보던 슬라이드에 다시 맞춘다 */
  new ResizeObserver(() => goTo(lastIndex, 'auto')).observe(track);

  /* ── 자동 넘김 ──────────────────────────────────────────────
     쉬는 이유(holds)가 하나라도 있으면 세지 않는다:
     'user'(멈춤 버튼·동작 줄이기) 'hover' 'focus'(키보드) 'touch' 'drag' 'hidden'(탭) 'offscreen' */
  const interval = parseInterval(getComputedStyle(rail).getPropertyValue('--cover-interval'));
  const holds = new Set(reducedMotion ? ['user'] : []);
  let remaining = interval;
  let startedAt = 0;
  let timer = 0;

  /**
   * Read a CSS time ("15s" or "15000ms") as milliseconds.
   *
   * @param {string} value - The custom property's value.
   * @returns {number} Milliseconds; DEFAULT_INTERVAL_MS when it is missing or invalid.
   */
  function parseInterval(value) {
    const text = value.trim();
    const amount = parseFloat(text);
    if (!(amount > 0)) return DEFAULT_INTERVAL_MS;
    return text.endsWith('ms') ? amount : amount * 1000;
  }

  /**
   * Reflect the state on the rail (data-autoplay / data-playing, read by CSS)
   * and on the pause button's icon and name.
   *
   * @returns {void}
   */
  function render() {
    const userPaused = holds.has('user');
    rail.toggleAttribute('data-autoplay', !userPaused);
    rail.toggleAttribute('data-playing', holds.size === 0);
    if (toggle) {
      toggle.setAttribute('aria-label', userPaused ? '자동 넘김 켜기' : '자동 넘김 멈추기');
      toggle.querySelector('i').className = userPaused ? 'bi bi-play' : 'bi bi-pause';
    }
  }

  /**
   * Count down the remaining time, unless something holds the rail.
   *
   * @returns {void}
   */
  function startTimer() {
    clearTimeout(timer);
    timer = 0;
    if (holds.size) return;
    startedAt = performance.now();
    timer = setTimeout(advance, Math.max(0, remaining));
  }

  /**
   * Stop counting and keep the time that is left.
   *
   * @returns {void}
   */
  function stopTimer() {
    if (!timer) return;
    clearTimeout(timer);
    timer = 0;
    remaining -= performance.now() - startedAt;
  }

  /**
   * Start the full interval over (the active bar's fill restarts with it in CSS).
   *
   * @returns {void}
   */
  function restartCountdown() {
    remaining = interval;
    startTimer();
  }

  /**
   * Show the next slide, or the first one after the last.
   *
   * @returns {void}
   */
  function advance() {
    timer = 0;
    const index = currentIndex();
    goTo(index >= slides.length - 1 ? 0 : index + 1);
    restartCountdown(); // 슬라이드가 바뀌면 다시 시작되지만, 혹시 안 바뀌어도 멈추지 않게
  }

  /**
   * Add a reason to rest.
   *
   * @param {string} reason - One of the hold names listed above.
   * @returns {void}
   */
  function hold(reason) {
    if (holds.has(reason)) return;
    holds.add(reason);
    stopTimer();
    render();
  }

  /**
   * Remove a reason to rest; counting resumes when none is left.
   *
   * @param {string} reason - One of the hold names listed above.
   * @returns {void}
   */
  function release(reason) {
    if (!holds.delete(reason)) return;
    render();
    startTimer();
  }

  if (toggle) {
    toggle.addEventListener('click', () => {
      if (!holds.has('user')) {
        hold('user');
        return;
      }
      remaining = interval; // 다시 켜면 막대가 처음부터 차오르므로 시간도 처음부터
      release('user');
    });
  }

  rail.addEventListener('pointerenter', (event) => { if (event.pointerType === 'mouse') hold('hover'); });
  rail.addEventListener('pointerleave', (event) => { if (event.pointerType === 'mouse') release('hover'); });
  rail.addEventListener('focusin', (event) => { if (event.target.matches(':focus-visible')) hold('focus'); });
  rail.addEventListener('focusout', (event) => { if (!rail.contains(event.relatedTarget)) release('focus'); });
  track.addEventListener('touchstart', () => hold('touch'), { passive: true });
  track.addEventListener('touchend', () => release('touch'), { passive: true });
  track.addEventListener('touchcancel', () => release('touch'), { passive: true });
  document.addEventListener('visibilitychange', () => (document.hidden ? hold('hidden') : release('hidden')));
  new IntersectionObserver(([entry]) => {
    if (entry.intersectionRatio >= VISIBLE_RATIO) release('offscreen');
    else hold('offscreen');
  }, { threshold: [0, VISIBLE_RATIO, 1] }).observe(rail);
  if (document.hidden) holds.add('hidden');

  render();
  syncControls();
  startTimer();
})();

/**
 * Hide the navbar's bottom line while the page is at the very top, so the
 * full-width cover band meets the menu without a rule; the line returns as soon
 * as the page scrolls (the sticky menu then needs it). Only on a home with a cover.
 *
 * @returns {void}
 */
(function setupNavAtTop() {
  const nav = document.querySelector('.site-nav');
  if (!nav || !document.querySelector('[data-cover-rail]')) return;

  /**
   * Mark the navbar with data-at-top when the page is scrolled to the top.
   *
   * @returns {void}
   */
  function update() {
    nav.toggleAttribute('data-at-top', window.scrollY < 1);
  }

  window.addEventListener('scroll', update, { passive: true });
  update();
})();
