/**
 * @file markdown_editor_page.js — Page chrome of the Markdown (Milkdown)
 * editor: body-width switcher, light/dark toggle, focus mode, live character
 * count and, where the colour pickers exist (new post), the editor's text and
 * background colours (remembered in localStorage).
 *
 * Used by templates/board_new_clean.html and board_edit.html, loaded without
 * defer after the page markup and before the editor bundle. Option on the
 * <script> tag:
 *   data-count-existing  also count the post body once the editor has loaded
 *                        it (edit page).
 * Styles: static/css/writing-enhanced.css.
 */
(function () {
  const countExisting = 'countExisting' in document.currentScript.dataset;

  // ── Layout switcher ─────────────────────────────────
  const LAYOUT_KEY = 'contentLayout';
  /**
   * The element whose data-layout sets the editor body width.
   *
   * @returns {?HTMLElement} .writing-editor-wrapper, if present.
   */
  const wrapper = () => document.querySelector('.writing-editor-wrapper');

  /**
   * Set the editor body width and mark the matching layout button active.
   *
   * @param {string} layout - "left" | "center" | "full" | "right".
   * @returns {void}
   */
  function applyLayout(layout) {
    const el = wrapper();
    if (!el) return;
    el.dataset.layout = layout;
    document.querySelectorAll('.layout-btn').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.layout === layout);
    });
    localStorage.setItem(LAYOUT_KEY, layout);
  }

  /**
   * Wire the layout buttons and restore the saved width (default: center).
   *
   * @returns {void}
   */
  function initLayoutSwitcher() {
    document.querySelectorAll('.layout-btn').forEach(btn => {
      btn.addEventListener('click', () => applyLayout(btn.dataset.layout));
    });

    // 저장된 레이아웃 복원 (기본값: center)
    applyLayout(localStorage.getItem(LAYOUT_KEY) || 'center');
  }

  // ── Theme ───────────────────────────────────────────
  const html = document.documentElement;
  const sunIcon = document.getElementById('sunIcon');
  const moonIcon = document.getElementById('moonIcon');

  /**
   * Show the icon for the current theme (sun when light, moon when dark).
   *
   * @param {string} theme - "light" or "dark".
   * @returns {void}
   */
  function updateThemeIcon(theme) {
    const dark = theme === 'dark';
    sunIcon.classList.toggle('theme-icon-shown', !dark);
    sunIcon.classList.toggle('theme-icon-hidden', dark);
    moonIcon.classList.toggle('theme-icon-shown', dark);
    moonIcon.classList.toggle('theme-icon-hidden', !dark);
  }

  /**
   * Apply the saved theme (default: light) and wire the toggle button, which
   * flips the theme and remembers it.
   *
   * @returns {void}
   */
  function initThemeToggle() {
    const savedTheme = localStorage.getItem('theme') || 'light';
    html.setAttribute('data-theme', savedTheme);
    updateThemeIcon(savedTheme);

    document.getElementById('themeToggle').addEventListener('click', () => {
      const currentTheme = html.getAttribute('data-theme');
      const newTheme = currentTheme === 'light' ? 'dark' : 'light';
      html.setAttribute('data-theme', newTheme);
      localStorage.setItem('theme', newTheme);
      updateThemeIcon(newTheme);
    });
  }

  // ── Focus mode ──────────────────────────────────────
  const focusExitBtn = document.getElementById('focusExitBtn');
  let focusMode = false;

  /**
   * Enter focus mode: fade the chrome out and show the exit button.
   *
   * @returns {void}
   */
  function enterFocus() {
    focusMode = true;
    document.body.classList.add('focus-active');
    focusExitBtn.classList.add('is-visible');
  }

  /**
   * Leave focus mode and hide the exit button.
   *
   * @returns {void}
   */
  function exitFocus() {
    focusMode = false;
    document.body.classList.remove('focus-active');
    focusExitBtn.classList.remove('is-visible');
  }

  /**
   * Wire the focus-mode toggle, the exit button and Escape.
   *
   * @returns {void}
   */
  function initFocusMode() {
    document.getElementById('focusToggle').addEventListener('click', () => focusMode ? exitFocus() : enterFocus());
    focusExitBtn.addEventListener('click', exitFocus);

    // ESC로 Focus 모드 종료
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && focusMode) exitFocus();
    });
  }

  // ── 글자 수 (공백 제외) ─────────────────────────────
  /**
   * Show the character count of `text`, not counting whitespace.
   *
   * @param {string} text - Editor text.
   * @returns {void}
   */
  function updateWordCount(text) {
    const chars = text.replace(/\s/g, '').length;
    document.getElementById('wordCount').textContent = `${chars.toLocaleString()}자`;
  }

  /**
   * Recount whenever the user types in the editor.
   *
   * @returns {void}
   */
  function initWordCount() {
    document.addEventListener('input', (e) => {
      const pm = e.target.closest && e.target.closest('.ProseMirror');
      if (pm) updateWordCount(pm.innerText);
    });
  }

  /**
   * Count the existing post body once the editor has rendered it
   * (polls every 300ms, gives up after 10s).
   *
   * @returns {void}
   */
  function countLoadedBody() {
    // 기존 본문이 로드되면 한 번 계산
    const wcTimer = setInterval(() => {
      const pm = document.querySelector('#editor-root .ProseMirror');
      if (pm) { updateWordCount(pm.innerText); clearInterval(wcTimer); }
    }, 300);
    setTimeout(() => clearInterval(wcTimer), 10000);
  }

  // ── Editor colours ──────────────────────────────────
  /**
   * Return the editor's ProseMirror element, if it exists yet.
   *
   * @returns {?HTMLElement} The editable element.
   */
  function getEditor() {
    return document.querySelector('.milkdown .ProseMirror');
  }

  /**
   * Set the editor text colour (after 100ms, so a just-created editor exists)
   * and remember it.
   *
   * @param {string} color - CSS colour picked by the user.
   * @returns {void}
   */
  function applyTextColor(color) {
    setTimeout(() => {
      const editor = getEditor();
      if (editor) {
        editor.style.setProperty('color', color, 'important'); // conventions: allow (colour picked by the user)
        localStorage.setItem('editorTextColor', color);
      }
    }, 100);
  }

  /**
   * Set the editor and page background colour (after 100ms) and remember it.
   *
   * @param {string} color - CSS colour picked by the user.
   * @returns {void}
   */
  function applyBgColor(color) {
    setTimeout(() => {
      const editor = getEditor();
      const editorWrapper = document.querySelector('.writing-editor .milkdown .editor');
      const writingWrapper = document.querySelector('.writing-editor-wrapper');

      if (editor) {
        // conventions: allow (background colour picked by the user)
        editor.style.setProperty('background', color, 'important');
        if (editorWrapper) editorWrapper.style.setProperty('background', color, 'important');
        if (writingWrapper) writingWrapper.style.setProperty('background', color, 'important');
        localStorage.setItem('editorBgColor', color);
      }
    }, 100);
  }

  /**
   * Wire the text/background colour pickers and the reset button, restore the
   * saved colours, and keep re-applying them while the editor re-renders.
   *
   * @returns {void}
   */
  function initColorControls() {
    const textColorPicker = document.getElementById('textColorPicker');
    const bgColorPicker = document.getElementById('bgColorPicker');
    const resetColorsBtn = document.getElementById('resetColors');

    // Color picker events
    textColorPicker.addEventListener('input', (e) => {
      applyTextColor(e.target.value);
    });

    bgColorPicker.addEventListener('input', (e) => {
      applyBgColor(e.target.value);
    });

    // Reset colors — 현재 테마 토큰 값으로
    resetColorsBtn.addEventListener('click', () => {
      const tokens = getComputedStyle(html);
      const defaultText = tokens.getPropertyValue('--text-primary').trim();
      const defaultBg = tokens.getPropertyValue('--surface').trim();

      textColorPicker.value = defaultText;
      bgColorPicker.value = defaultBg;

      applyTextColor(defaultText);
      applyBgColor(defaultBg);
    });

    // Load saved colors
    const savedTextColor = localStorage.getItem('editorTextColor');
    const savedBgColor = localStorage.getItem('editorBgColor');

    // 저장된 색이 없으면 스와치를 현재 테마 색으로 표시
    {
      const tokens = getComputedStyle(html);
      if (!savedTextColor) textColorPicker.value = tokens.getPropertyValue('--text-primary').trim();
      if (!savedBgColor) bgColorPicker.value = tokens.getPropertyValue('--surface').trim();
    }

    if (savedTextColor) {
      textColorPicker.value = savedTextColor;
      applyTextColor(savedTextColor);
    }

    if (savedBgColor) {
      bgColorPicker.value = savedBgColor;
      applyBgColor(savedBgColor);
    }

    // Apply colors when editor loads
    setTimeout(() => {
      if (savedTextColor) applyTextColor(savedTextColor);
      if (savedBgColor) applyBgColor(savedBgColor);
    }, 500);

    // Reapply on editor changes
    setInterval(() => {
      const editor = getEditor();
      if (editor && savedTextColor && !editor.style.color.includes(savedTextColor)) {
        applyTextColor(savedTextColor);
      }
      if (editor && savedBgColor && !editor.style.background.includes(savedBgColor)) {
        applyBgColor(savedBgColor);
      }
    }, 1000);
  }

  initLayoutSwitcher();
  initThemeToggle();
  initFocusMode();
  initWordCount();
  if (countExisting) countLoadedBody();
  if (document.getElementById('textColorPicker')) initColorControls();
})();
