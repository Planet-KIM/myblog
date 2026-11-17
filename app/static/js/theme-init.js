/**
 * @file Apply the saved (or the OS) colour theme and the saved text size of
 * post bodies before the first paint.
 *
 * Loaded from <head> in base.html WITHOUT defer or async, so it runs before
 * the page is drawn (no light/dark flash, no jump in text size). It used to
 * be an inline script; as a file it can run under the site's
 * Content-Security-Policy, which allows no inline scripts. Sets data-theme
 * and data-bs-theme on <html>, and data-reading-size ("sm" or "lg", chosen
 * with the buttons of _reading_size.html; see reading_size.css).
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

(function initReadingSize() {
  try {
    var size = localStorage.getItem('readingSize');
    if (size === 'sm' || size === 'lg') document.documentElement.setAttribute('data-reading-size', size);
  } catch (e) { /* storage unavailable: keep the default size */ }
})();
