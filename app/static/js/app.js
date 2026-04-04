/* ============================================
   Planet KIM's Travel - Main JavaScript
   ============================================ */

// ─────────────────────────────────────────────
// Toast Notification System
// ─────────────────────────────────────────────
class ToastManager {
  constructor() {
    this.container = null;
    this.init();
  }

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

  remove(toast) {
    toast.classList.add('toast-hiding');
    setTimeout(() => {
      if (toast.parentElement) {
        toast.parentElement.removeChild(toast);
      }
    }, 300);
  }

  success(message, duration) {
    return this.show(message, 'success', duration);
  }

  error(message, duration) {
    return this.show(message, 'error', duration);
  }

  warning(message, duration) {
    return this.show(message, 'warning', duration);
  }

  info(message, duration) {
    return this.show(message, 'info', duration);
  }
}

// ─────────────────────────────────────────────
// Theme Manager
// ─────────────────────────────────────────────
class ThemeManager {
  constructor() {
    this.theme = localStorage.getItem('theme') || 'dark';
    this.init();
  }

  init() {
    // Apply saved theme
    this.applyTheme(this.theme);

    // Create theme toggle button
    this.createToggleButton();
  }

  createToggleButton() {
    const nav = document.querySelector('.navbar-nav.ms-auto');
    if (!nav) return;

    const toggleLi = document.createElement('li');
    toggleLi.className = 'nav-item';

    const toggleBtn = document.createElement('button');
    toggleBtn.className = 'nav-link theme-toggle';
    toggleBtn.innerHTML = this.theme === 'dark'
      ? '<i class="bi bi-sun-fill"></i>'
      : '<i class="bi bi-moon-fill"></i>';
    toggleBtn.title = 'Toggle theme';
    toggleBtn.style.background = 'none';
    toggleBtn.style.border = 'none';
    toggleBtn.style.cursor = 'pointer';
    toggleBtn.setAttribute('aria-label', 'Toggle theme');

    toggleBtn.addEventListener('click', () => this.toggle());

    toggleLi.appendChild(toggleBtn);
    nav.insertBefore(toggleLi, nav.firstChild);
  }

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
    metaTheme.content = theme === 'dark' ? '#0f172a' : '#f8fafc';
  }

  toggle() {
    this.theme = this.theme === 'dark' ? 'light' : 'dark';
    this.applyTheme(this.theme);
    localStorage.setItem('theme', this.theme);

    // Update toggle button icon
    const toggleBtn = document.querySelector('.theme-toggle');
    if (toggleBtn) {
      toggleBtn.innerHTML = this.theme === 'dark'
        ? '<i class="bi bi-sun-fill"></i>'
        : '<i class="bi bi-moon-fill"></i>';
    }

    // Show toast notification
    window.toast.info(`Theme switched to ${this.theme} mode`);
  }
}

// ─────────────────────────────────────────────
// Loading Overlay
// ─────────────────────────────────────────────
class LoadingOverlay {
  constructor() {
    this.overlay = null;
    this.init();
  }

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

  show(text = 'Loading...') {
    const loadingText = this.overlay.querySelector('.loading-text');
    if (loadingText) {
      loadingText.textContent = text;
    }
    this.overlay.classList.add('active');
  }

  hide() {
    this.overlay.classList.remove('active');
  }
}

// ─────────────────────────────────────────────
// Smooth Scroll
// ─────────────────────────────────────────────
function initSmoothScroll() {
  document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function(e) {
      e.preventDefault();
      const target = document.querySelector(this.getAttribute('href'));
      if (target) {
        target.scrollIntoView({
          behavior: 'smooth',
          block: 'start'
        });
      }
    });
  });
}

// ─────────────────────────────────────────────
// Lazy Loading Images
// ─────────────────────────────────────────────
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