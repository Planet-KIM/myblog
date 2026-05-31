/**
 * home.js — Main page (index) interaction layer
 *
 * Dependencies (loaded via CDN before this file):
 *   - AOS v2.3.4  (MIT License)  https://michalsnik.github.io/aos/
 *   - Typed.js v2.1.0 (MIT License)  https://mattboldt.com/demos/typed-js/
 */

document.addEventListener('DOMContentLoaded', function () {
  const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const searchInput = document.getElementById('home-search-input');
  const nav = document.querySelector('.site-nav');

  function syncHomeNavState() {
    if (!nav) return;
    nav.classList.toggle('is-scrolled', window.scrollY > 60);
  }

  syncHomeNavState();
  window.addEventListener('scroll', syncHomeNavState, { passive: true });

  /* ── AOS: Animate On Scroll (MIT License) ────────────────── */
  if (!prefersReducedMotion && typeof AOS !== 'undefined') {
    AOS.init({
      duration: 650,
      easing: 'ease-out-cubic',
      once: true,
      offset: 60
    });
  }

  /* ── Typed.js: Hero subtitle cycling (MIT License) ───────── */
  const typedEl = document.getElementById('typed-text');
  if (typedEl) {
    if (prefersReducedMotion) {
      typedEl.textContent = '모든 순간을 기록합니다';
    } else if (typeof Typed !== 'undefined') {
      new Typed('#typed-text', {
        strings: [
          '음식을 기록합니다',
          '풍경을 기록합니다',
          '사람을 기록합니다',
          '모든 순간을 기록합니다'
        ],
        typeSpeed: 60,
        backSpeed: 35,
        backDelay: 2200,
        loop: true,
        cursorChar: '|'
      });
    }
  }

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
  const continueList = document.getElementById('continue-reading-list');
  if (continueList) {
    let items = [];
    try {
      items = JSON.parse(localStorage.getItem('recentPosts') || '[]');
    } catch (_error) {
      items = [];
    }

    if (!Array.isArray(items) || items.length === 0) {
      continueList.innerHTML = '<p class="continue-empty">최근 읽은 글이 없습니다.</p>';
    } else {
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
