/**
 * @file Reading helpers on post pages (_reading_enhancements.html), as
 * progressive enhancement: the body still shows if this fails.
 *   - Table of contents built from the h2/h3 headings of .article-content
 *     (Markdown posts only, when there are at least 3), inserted before it.
 *     Bilingual headings (already split by bilingual.js) keep both languages,
 *     so the language switch changes the table of contents too.
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

  // The page's own <article>: post markup cannot add one (sanitize.py drops
  // the tag), so a block in a post body that copies the class is not taken
  // for the article.
  var article = document.querySelector('article.article-content');

  /**
   * Text of a heading without the elements matching a selector (used to read
   * one language of a bilingual heading: drop .bi-en for Korean, .bi-ko for
   * English, and the .bi-fold toggle either way).
   *
   * @param {Element} h - The heading.
   * @param {string} drop - Selector of the elements to leave out.
   * @returns {string} Trimmed text.
   */
  function textWithout(h, drop) {
    var copy = h.cloneNode(true);
    copy.querySelectorAll(drop).forEach(function (el) { el.remove(); });
    return (copy.textContent || '').trim();
  }

  /**
   * Make an element with a class and, optionally, text.
   *
   * @param {string} tag - Tag name.
   * @param {string} className - Class attribute ('' for none).
   * @param {string} [text] - Text content.
   * @returns {HTMLElement} The element.
   */
  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  /**
   * The label of a TOC link: the heading text, or both languages of a
   * bilingual heading (so the language switch applies to it too).
   *
   * @param {Element} h - The heading.
   * @param {string} text - Its Korean (or only) text.
   * @param {boolean} bilingual - Whether the heading holds a .bi-pair.
   * @returns {Node} A text node or a .bi-pair span.
   */
  function tocLabel(h, text, bilingual) {
    if (!bilingual) return document.createTextNode(text);
    var pair = el('span', 'bi-pair');
    var ko = el('span', 'bi-ko', text);
    var en = el('span', 'bi-en', textWithout(h, '.bi-ko, .bi-fold'));
    ko.lang = 'ko';
    en.lang = 'en';
    pair.append(ko, en);
    return pair;
  }

  /**
   * Build the table of contents for the h2/h3 headings, giving each heading
   * without an id one made from its text. Built with DOM APIs only: heading
   * ids and text come from the post body and are set as attribute values and
   * text, never parsed as HTML.
   *
   * @param {NodeList} heads - The article's h2/h3 headings.
   * @returns {?HTMLElement} The nav.post-toc, or null when no heading has text.
   */
  function buildToc(heads) {
    var used = {};
    var list = document.createElement('ul');
    heads.forEach(function (h, i) {
      // 이중 언어 제목(bilingual.js 가 만든 .bi-pair)은 한국어로 앵커를 만들고 두 언어를 함께 담는다
      var bilingual = !!h.querySelector('.bi-pair');
      var text = bilingual ? textWithout(h, '.bi-en, .bi-fold') : (h.textContent || '').trim();
      if (!text) return;
      var slug = text.toLowerCase().replace(/[^\w가-힣]+/g, '-').replace(/^-+|-+$/g, '') || ('section-' + i);
      if (used[slug]) slug = slug + '-' + i;
      used[slug] = true;
      if (!h.id) h.id = slug;
      var link = el('a', '');
      link.setAttribute('href', '#' + h.id);
      link.appendChild(tocLabel(h, text, bilingual));
      var item = el('li', h.tagName === 'H3' ? 'lvl-3' : '');
      item.appendChild(link);
      list.appendChild(item);
    });
    if (!list.children.length) return null;
    var toc = el('nav', 'post-toc');
    toc.setAttribute('aria-label', '목차');
    toc.append(el('div', 'post-toc-title', '목차'), list);
    return toc;
  }

  // ── 목차 (h2/h3) — 제목이 3개 이상일 때만 ──
  if (article) {
    var heads = article.querySelectorAll('h2, h3');
    var toc = heads.length >= 3 ? buildToc(heads) : null;
    if (toc) article.parentNode.insertBefore(toc, article);
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
