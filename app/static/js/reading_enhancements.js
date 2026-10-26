/**
 * @file Reading helpers on post pages (_reading_enhancements.html), as
 * progressive enhancement: the body still shows if this fails.
 *   - Table of contents built from the h2/h3 headings of .article-content
 *     (Markdown posts only, when there are at least 3), inserted before it.
 *   - Code-block header (language label + copy button) around every <pre> in
 *     .article-content and .magazine-content.
 * Sets window.__skipCodeCopy so app.js doesn't add its generic copy button too.
 *
 * Load it WITHOUT defer where the partial is included: it works on the
 * content parsed so far (the article, or the magazine viewer built just
 * before it). TOC styles: reading_enhancements.css; code-block styles:
 * writer-journey.css (.code-block).
 */
(function initReadingEnhancements() {
  window.__skipCodeCopy = true;   // app.js 의 범용 복사 버튼과 중복 방지

  var article = document.querySelector('.article-content');

  // ── 목차 (h2/h3) — 제목이 3개 이상일 때만 ──
  if (article) {
    var heads = article.querySelectorAll('h2, h3');
    if (heads.length >= 3) {
      var used = {};
      var toc = document.createElement('nav');
      toc.className = 'post-toc';
      toc.setAttribute('aria-label', '목차');
      var items = '';
      heads.forEach(function (h, i) {
        var text = (h.textContent || '').trim();
        if (!text) return;
        var slug = text.toLowerCase().replace(/[^\w가-힣]+/g, '-').replace(/^-+|-+$/g, '') || ('section-' + i);
        if (used[slug]) slug = slug + '-' + i;
        used[slug] = true;
        if (!h.id) h.id = slug;
        var lvl = h.tagName === 'H3' ? ' class="lvl-3"' : '';
        var a = document.createElement('a');
        a.textContent = text;          // 텍스트로 넣어 XSS 없이 안전
        items += '<li' + lvl + '><a href="#' + h.id + '">' + a.innerHTML + '</a></li>';
      });
      if (items) {
        toc.innerHTML = '<div class="post-toc-title">목차</div><ul>' + items + '</ul>';
        article.parentNode.insertBefore(toc, article);
      }
    }
  }

  // ── 코드블록: 언어 라벨 + 복사 버튼 헤더 ──
  /**
   * Language label for a code block: data-language on the <pre>, else the
   * language-* class of its <code>; "code" when unknown or plaintext.
   *
   * @param {HTMLPreElement} pre - The code block.
   * @returns {string} Label text.
   */
  function langOf(pre) {
    var lang = pre.getAttribute('data-language') || '';
    var code = pre.querySelector('code');
    if (!lang && code) {
      var m = (code.className || '').match(/language-([\w+#-]+)/);
      if (m) lang = m[1];
    }
    return lang && lang !== 'plaintext' ? lang : 'code';
  }

  document.querySelectorAll('.article-content pre, .magazine-content pre').forEach(function (pre) {
    if (pre.parentElement && pre.parentElement.classList.contains('code-block')) return;
    var block = document.createElement('div');
    block.className = 'code-block';
    var head = document.createElement('div');
    head.className = 'code-block-head';
    var label = document.createElement('span');
    label.textContent = langOf(pre);
    head.appendChild(label);

    if (navigator.clipboard) {
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'code-copy-btn';
      btn.setAttribute('aria-label', '코드 복사');
      btn.innerHTML = '<i class="bi bi-clipboard" aria-hidden="true"></i><span>복사</span>';
      btn.addEventListener('click', function () {
        navigator.clipboard.writeText(pre.innerText).then(function () {
          btn.classList.add('copied');
          btn.innerHTML = '<i class="bi bi-check2" aria-hidden="true"></i><span>복사됨</span>';
          setTimeout(() => {
            btn.classList.remove('copied');
            btn.innerHTML = '<i class="bi bi-clipboard" aria-hidden="true"></i><span>복사</span>';
          }, 1500);
        }).catch(function () {});
      });
      head.appendChild(btn);
    }

    pre.parentNode.insertBefore(block, pre);
    block.appendChild(head);
    block.appendChild(pre);
  });
})();
