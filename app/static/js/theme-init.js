/**
 * @file Apply the saved (or the OS) colour theme before the first paint.
 *
 * Loaded from <head> in base.html WITHOUT defer or async, so it runs before
 * the page is drawn (no light/dark flash). It used to be an inline script;
 * as a file it can run under the site's Content-Security-Policy, which allows
 * no inline scripts. Sets data-theme and data-bs-theme on <html>.
 */
(function initTheme() {
  try {
    var theme = localStorage.getItem('theme');
    if (theme !== 'light' && theme !== 'dark') {
      // 기본은 밝은 에디토리얼. OS가 다크를 선호할 때만 다크.
      theme = (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) ? 'dark' : 'light';
    }
    document.documentElement.setAttribute('data-theme', theme);
    document.documentElement.setAttribute('data-bs-theme', theme);
  } catch (e) { /* storage unavailable: keep the default theme */ }
})();
