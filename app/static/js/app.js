/**
 * @file Site-wide behavior loaded on every page (base.html): toasts, the nav
 * theme toggle, the loading overlay, smooth in-page scrolling, lazy images,
 * code-block copy buttons, form validation, the nav active state and page
 * transitions. Exposes window.toast, window.theme, window.loading and
 * window.AppUtils for page scripts.
 */

// ─────────────────────────────────────────────
// Toast Notification System
// ─────────────────────────────────────────────
/**
 * Small toast notifications stacked in a fixed .toast-container.
 * Available as window.toast after DOMContentLoaded.
 */
class ToastManager {
  /**
   * Create the manager and attach (or reuse) the toast container.
   */
  constructor() {
    this.container = null;
    this.init();
  }

  /**
   * Reuse an existing .toast-container or append a new one to <body>.
   *
   * @returns {void}
   */
  init() {
    // Create toast container if it doesn't exist
    if (!document.querySelector('.toast-container')) {
      this.container = document.createElement('div');
      this.container.className = 'toast-container';
      document.body.appendChild(this.container);
    } else {
      this.container = document.querySelector('.toast-container');
    }
  }

  /**
   * Show a toast.
   *
   * @param {string} message - Message markup. Inserted as HTML, so escape any
   *   user-provided text before passing it.
   * @param {'success'|'error'|'warning'|'info'} [type='info'] - Visual style and icon.
   * @param {number} [duration=5000] - Auto-dismiss delay in ms; 0 keeps it until closed.
   * @returns {HTMLDivElement} The toast element.
   */
  show(message, type = 'info', duration = 5000) {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type} fade-in`;

    const icons = {
      success: 'bi-check-circle-fill',
      error: 'bi-exclamation-circle-fill',
      warning: 'bi-exclamation-triangle-fill',
      info: 'bi-info-circle-fill'
    };

    toast.innerHTML = `
      <i class="bi ${icons[type]} toast-icon"></i>
      <div class="toast-content">
        <div class="toast-message">${message}</div>
      </div>
      <button class="toast-close">&times;</button>
      <div class="toast-progress"></div>
    `;

    this.container.appendChild(toast);

    // Close button functionality
    const closeBtn = toast.querySelector('.toast-close');
    closeBtn.addEventListener('click', () => this.remove(toast));

    // Auto remove after duration
    if (duration > 0) {
      setTimeout(() => this.remove(toast), duration);
    }

    return toast;
  }

  /**
   * Play the hide animation, then remove the toast from the DOM.
   *
   * @param {HTMLElement} toast - A toast created by show().
   * @returns {void}
   */
  remove(toast) {
    toast.classList.add('toast-hiding');
    setTimeout(() => {
      if (toast.parentElement) {
        toast.parentElement.removeChild(toast);
      }
    }, 300);
  }

  /**
   * Show a success toast. See show().
   *
   * @param {string} message - Message markup.
   * @param {number} [duration] - Auto-dismiss delay in ms.
   * @returns {HTMLDivElement} The toast element.
   */
  success(message, duration) {
    return this.show(message, 'success', duration);
  }

  /**
   * Show an error toast. See show().
   *
   * @param {string} message - Message markup.
   * @param {number} [duration] - Auto-dismiss delay in ms.
   * @returns {HTMLDivElement} The toast element.
   */
  error(message, duration) {
    return this.show(message, 'error', duration);
  }

  /**
   * Show a warning toast. See show().
   *
   * @param {string} message - Message markup.
   * @param {number} [duration] - Auto-dismiss delay in ms.
   * @returns {HTMLDivElement} The toast element.
   */
  warning(message, duration) {
    return this.show(message, 'warning', duration);
  }

  /**
   * Show an info toast. See show().
   *
   * @param {string} message - Message markup.
   * @param {number} [duration] - Auto-dismiss delay in ms.
   * @returns {HTMLDivElement} The toast element.
   */
  info(message, duration) {
    return this.show(message, 'info', duration);
  }
}

// ─────────────────────────────────────────────
// Theme Manager
// ─────────────────────────────────────────────
/**
 * Light/dark theme switch: adds the toggle button to the nav and keeps
 * <html data-theme>, <body data-bs-theme>, the theme-color meta tag and
 * localStorage in sync. Available as window.theme.
 */
class ThemeManager {
  /**
   * Start from the theme the <head> script already applied (saved or OS).
   */
  constructor() {
    // <head>의 FOUC 방지 스크립트가 이미 정한 테마(저장값 또는 OS 설정)를 그대로 따른다.
    this.theme =
      document.documentElement.getAttribute('data-theme') ||
      localStorage.getItem('theme') ||
      'dark';
    this.init();
  }

  /**
   * Apply the current theme and add the toggle button.
   *
   * @returns {void}
   */
  init() {
    // Apply saved theme
    this.applyTheme(this.theme);

    // Create theme toggle button
    this.createToggleButton();
  }

  /**
   * Insert the sun/moon toggle as the first item of the right-hand nav list.
   * Does nothing on pages without that list (e.g. full-screen editors).
   *
   * @returns {void}
   */
  createToggleButton() {
    const nav = document.querySelector('.navbar-nav.ms-auto');
    if (!nav) return;

    const toggleLi = document.createElement('li');
    toggleLi.className = 'nav-item';

    const toggleBtn = document.createElement('button');
    toggleBtn.className = 'nav-link nav-icon theme-toggle';
    toggleBtn.innerHTML = this.theme === 'dark'
      ? '<i class="bi bi-sun"></i>'
      : '<i class="bi bi-moon"></i>';
    toggleBtn.title = 'Toggle theme';
    toggleBtn.setAttribute('aria-label', 'Toggle theme');

    toggleBtn.addEventListener('click', () => this.toggle());

    toggleLi.appendChild(toggleBtn);
    nav.insertBefore(toggleLi, nav.firstChild);
  }

  /**
   * Apply a theme to the document and the browser UI color.
   *
   * @param {'light'|'dark'} theme - Theme to apply.
   * @returns {void}
   */
  applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    document.body.setAttribute('data-bs-theme', theme);

    // Update meta theme-color
    let metaTheme = document.querySelector('meta[name="theme-color"]');
    if (!metaTheme) {
      metaTheme = document.createElement('meta');
      metaTheme.name = 'theme-color';
      document.head.appendChild(metaTheme);
    }
    metaTheme.content = theme === 'dark' ? '#1a1511' : '#f8f4ee';
  }

  /**
   * Switch between light and dark, remember the choice and update the icon.
   *
   * @returns {void}
   */
  toggle() {
    this.theme = this.theme === 'dark' ? 'light' : 'dark';
    this.applyTheme(this.theme);
    localStorage.setItem('theme', this.theme);

    // Update toggle button icon
    const toggleBtn = document.querySelector('.theme-toggle');
    if (toggleBtn) {
      toggleBtn.innerHTML = this.theme === 'dark'
        ? '<i class="bi bi-sun"></i>'
        : '<i class="bi bi-moon"></i>';
    }
  }
}

// ─────────────────────────────────────────────
// Loading Overlay
// ─────────────────────────────────────────────
/**
 * Full-screen loading overlay with a spinner and a text line.
 * Available as window.loading.
 */
class LoadingOverlay {
  /**
   * Create the overlay element (or reuse an existing one).
   */
  constructor() {
    this.overlay = null;
    this.init();
  }

  /**
   * Reuse an existing .loading-overlay or append a new one to <body>.
   *
   * @returns {void}
   */
  init() {
    if (!document.querySelector('.loading-overlay')) {
      this.overlay = document.createElement('div');
      this.overlay.className = 'loading-overlay';
      this.overlay.innerHTML = `
        <div class="loading-content">
          <div class="loading-spinner"></div>
          <div class="loading-text">Loading...</div>
        </div>
      `;
      document.body.appendChild(this.overlay);
    } else {
      this.overlay = document.querySelector('.loading-overlay');
    }
  }

  /**
   * Show the overlay.
   *
   * @param {string} [text='Loading...'] - Text under the spinner.
   * @returns {void}
   */
  show(text = 'Loading...') {
    const loadingText = this.overlay.querySelector('.loading-text');
    if (loadingText) {
      loadingText.textContent = text;
    }
    this.overlay.classList.add('active');
  }

  /**
   * Hide the overlay.
   *
   * @returns {void}
   */
  hide() {
    this.overlay.classList.remove('active');
  }
}

// ─────────────────────────────────────────────
// Smooth Scroll
// ─────────────────────────────────────────────
/**
 * Smooth-scroll in-page "#…" links to their target. Links whose hash is not a
 * valid selector fall back to getElementById; links with no target keep the
 * browser's default behavior.
 *
 * @returns {void}
 */
function initSmoothScroll() {
  document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function(e) {
      const href = this.getAttribute('href');
      // "#"만 있거나 CSS 선택자로 부적합한 값(#숫자로 시작 등)은 건너뜀
      if (!href || href === '#') return;
      let target = null;
      try {
        target = document.querySelector(href);
      } catch (_err) {
        const el = document.getElementById(href.slice(1));
        target = el || null;
      }
      if (target) {
        e.preventDefault();
        target.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    });
  });
}

// ─────────────────────────────────────────────
// Lazy Loading Images
// ─────────────────────────────────────────────
/**
 * Load img[data-src] when it scrolls into view (or immediately without
 * IntersectionObserver), then drop the data-src attribute.
 *
 * @returns {void}
 */
function initLazyLoading() {
  const images = document.querySelectorAll('img[data-src]');

  if ('IntersectionObserver' in window) {
    const imageObserver = new IntersectionObserver((entries, observer) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          const img = entry.target;
          img.src = img.dataset.src;
          img.removeAttribute('data-src');
          imageObserver.unobserve(img);
        }
      });
    });

    images.forEach(img => imageObserver.observe(img));
  } else {
    // Fallback for older browsers
    images.forEach(img => {
      img.src = img.dataset.src;
      img.removeAttribute('data-src');
    });
  }
}

// ─────────────────────────────────────────────
// Animate on Scroll
// ─────────────────────────────────────────────
/**
 * Add .animated to .animate-on-scroll elements once 10% of them is visible.
 *
 * @returns {void}
 */
function initScrollAnimations() {
  const animatedElements = document.querySelectorAll('.animate-on-scroll');

  if ('IntersectionObserver' in window) {
    const animationObserver = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add('animated');
        }
      });
    }, {
      threshold: 0.1
    });

    animatedElements.forEach(el => animationObserver.observe(el));
  }
}

// ─────────────────────────────────────────────
// Copy Code Blocks
// ─────────────────────────────────────────────
/**
 * Wrap every <pre> in .code-wrapper and add a copy button that copies its
 * text and confirms with a toast. Pages that render their own code blocks
 * opt out by setting window.__skipCodeCopy before DOMContentLoaded.
 *
 * @returns {void}
 */
function initCodeCopy() {
  if (window.__skipCodeCopy) return;
  document.querySelectorAll('pre').forEach(pre => {
    const wrapper = document.createElement('div');
    wrapper.className = 'code-wrapper';
    pre.parentNode.insertBefore(wrapper, pre);
    wrapper.appendChild(pre);

    const copyBtn = document.createElement('button');
    copyBtn.className = 'code-copy-btn';
    copyBtn.innerHTML = '<i class="bi bi-clipboard"></i>';
    copyBtn.title = 'Copy code';
    wrapper.appendChild(copyBtn);

    copyBtn.addEventListener('click', async () => {
      const code = pre.textContent;
      try {
        await navigator.clipboard.writeText(code);
        copyBtn.innerHTML = '<i class="bi bi-clipboard-check"></i>';
        window.toast.success('Code copied to clipboard');
        setTimeout(() => {
          copyBtn.innerHTML = '<i class="bi bi-clipboard"></i>';
        }, 2000);
      } catch (err) {
        window.toast.error('Failed to copy code');
      }
    });
  });
}

// ─────────────────────────────────────────────
// Form Validation
// ─────────────────────────────────────────────
/**
 * Bootstrap-style validation for forms with .needs-validation: block submit
 * while invalid and add .was-validated to show the feedback styles.
 *
 * @returns {void}
 */
function initFormValidation() {
  const forms = document.querySelectorAll('.needs-validation');

  forms.forEach(form => {
    form.addEventListener('submit', event => {
      if (!form.checkValidity()) {
        event.preventDefault();
        event.stopPropagation();
      }
      form.classList.add('was-validated');
    });
  });
}

// ─────────────────────────────────────────────
// Initialize Everything
// ─────────────────────────────────────────────
/**
 * Boot the site once the DOM is ready: create the global helpers, run the
 * feature initializers and mark the nav link for the current page as active.
 */
document.addEventListener('DOMContentLoaded', () => {
  // Initialize global utilities
  window.toast = new ToastManager();
  window.theme = new ThemeManager();
  window.loading = new LoadingOverlay();

  // Initialize features
  initSmoothScroll();
  initLazyLoading();
  initScrollAnimations();
  initCodeCopy();
  initFormValidation();

  // Add page transition effects
  document.body.classList.add('fade-in');

  // Handle navigation active state
  const currentPath = window.location.pathname;
  document.querySelectorAll('.navbar-nav a.nav-link').forEach(link => {
    const href = link.getAttribute('href');
    if (!href) return;
    if (href === '/') {
      if (currentPath === '/') link.classList.add('active');
    } else if (currentPath.startsWith(href)) {
      link.classList.add('active');
    }
  });
});

// ─────────────────────────────────────────────
// Export for use in other scripts
// ─────────────────────────────────────────────
window.AppUtils = {
  toast: window.toast,
  theme: window.theme,
  loading: window.loading
};

/**
 * Page transitions: give the clicked post card's title the 'post-title'
 * view-transition name so it morphs into the post page's .article-title.
 *
 * The name comes from CSS classes (components.css), not inline styles. Only one
 * element per page may carry a given name, or the browser cancels the
 * transition, so the previous mark is cleared on every click.
 *
 * @returns {void}
 */
(function initPageTransitions() {
  /** Class that gives a card title the 'post-title' transition name. */
  const SOURCE_CLASS = 'is-transition-source';
  /** Class that removes the transition name from the current article title. */
  const MUTED_CLASS = 'is-transition-muted';

  /**
   * Mark the title of the clicked post card as the transition source.
   *
   * Modified clicks (new tab/window) are ignored. Clicks on buttons or forms
   * inside a card only clear the previous mark. On a post page the current
   * .article-title is muted first, so a related-post click doesn't produce
   * two elements with the same name.
   *
   * @param {MouseEvent} event - Click anywhere in the document.
   * @returns {void}
   */
  function markTransitionSource(event) {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;

    document.querySelectorAll('[data-vt-title]').forEach((el) => el.classList.remove(SOURCE_CLASS));

    const card = event.target.closest('[data-vt-card]');
    if (!card || event.target.closest('button, form')) return;

    const title = card.querySelector('[data-vt-title]');
    if (!title) return;
    document.querySelectorAll('.article-title').forEach((el) => el.classList.add(MUTED_CLASS));
    title.classList.add(SOURCE_CLASS);
  }

  document.addEventListener('click', markTransitionSource);
})();
