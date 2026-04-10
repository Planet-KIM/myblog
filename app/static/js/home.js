/**
 * home.js — Main page (index) initialization
 *
 * Dependencies (loaded via CDN before this file):
 *   - AOS v2.3.4  (MIT License)  https://michalsnik.github.io/aos/
 *   - Typed.js v2.1.0 (MIT License)  https://mattboldt.com/demos/typed-js/
 */

document.addEventListener('DOMContentLoaded', function () {

  /* ── AOS: Animate On Scroll (MIT License) ────────────────── */
  if (typeof AOS !== 'undefined') {
    AOS.init({
      duration: 650,
      easing: 'ease-out-cubic',
      once: true,
      offset: 60
    });
  }

  /* ── Typed.js: Hero subtitle cycling (MIT License) ───────── */
  const typedEl = document.getElementById('typed-text');
  if (typedEl && typeof Typed !== 'undefined') {
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

});
