/**
 * @file Bilingual post text on post pages (board_detail_writer.html,
 * board_detail_magazine.html).
 *
 * Authors write {{한국어||English}} in a post body. This script turns every
 * pair inside the [data-bilingual-root] containers into
 *   <span class="bi-pair"><span class="bi-ko" lang="ko">…</span><span class="bi-en" lang="en">…</span></span>
 * (formatting inside either side is kept; code is left alone), then fills the
 * [data-bilingual-switch] box with 한국어 / English / 함께 buttons. The choice is
 * set as data-content-lang on <html> (static/css/bilingual.css shows the
 * matching side), remembered in this browser, and announced as a
 * "bilingual:change" event; a "bilingual:set" event with {lang} changes it.
 * The server reduces pairs to Korean everywhere else (app/services/bilingual.py).
 *
 * Load it WITHOUT defer after the post body (and after the magazine viewer has
 * been built) but before _reading_enhancements.html, whose table of contents
 * reads the processed headings.
 */
(function initBilingual() {
  const PAIR = /\{\{([\s\S]*?)\|\|([\s\S]*?)\}\}/;
  const SKIP = 'code, pre, kbd, samp, script, style, textarea';
  // A pair never spans two of these: it lives inside one paragraph, heading, item or cell.
  const BLOCK = 'p, li, h1, h2, h3, h4, h5, h6, td, th, dt, dd, figcaption, blockquote, div, section, article';
  const LANGS = [['ko', '한국어'], ['en', 'English'], ['both', '함께']];
  const PREF_KEY = 'bilingual.lang';

  /**
   * Text nodes under an element, in document order, outside code.
   *
   * @param {Element} el - Element to search.
   * @returns {Text[]} The text nodes.
   */
  function textNodes(el) {
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, {
      acceptNode: n => (n.parentElement && n.parentElement.closest(SKIP) ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT),
    });
    const out = [];
    for (let n = walker.nextNode(); n; n = walker.nextNode()) out.push(n);
    return out;
  }

  /**
   * Blocks under root that contain an opening "{{", in document order.
   *
   * @param {Element} root - A [data-bilingual-root] container.
   * @returns {Element[]} Nearest block of each such text (root itself when there is none).
   */
  function blocksWithPairs(root) {
    const blocks = [];
    textNodes(root).forEach(n => {
      if (!n.data.includes('{{')) return;
      const b = n.parentElement.closest(BLOCK);
      const block = b && root.contains(b) ? b : root;
      if (!blocks.includes(block)) blocks.push(block);
    });
    return blocks;
  }

  /**
   * Trim whitespace at the start and end of a fragment's text.
   *
   * @param {DocumentFragment} frag - One side of a pair.
   * @returns {DocumentFragment} The same fragment.
   */
  function trimFragment(frag) {
    const texts = textNodes(frag);
    if (texts.length) {
      texts[0].data = texts[0].data.replace(/^\s+/, '');
      const last = texts[texts.length - 1];
      last.data = last.data.replace(/\s+$/, '');
    }
    return frag;
  }

  /**
   * Move a range boundary out of the elements it sits at the very edge of.
   *
   * A side that is wholly bold starts at offset 0 inside <strong>; moving the
   * boundary before the <strong> makes the cut take the element along, so the
   * formatting stays with that side. Never leaves `stop`.
   *
   * @param {Node} node - Boundary node.
   * @param {number} offset - Boundary offset.
   * @param {Element} stop - Block the boundary must stay inside.
   * @param {boolean} atEnd - True for an end boundary (move after), false for a start (move before).
   * @returns {Array} [node, offset] of the widened boundary.
   */
  function widen(node, offset, stop, atEnd) {
    while (node !== stop && node.parentNode) {
      const len = node.nodeType === Node.TEXT_NODE ? node.length : node.childNodes.length;
      if (atEnd ? offset !== len : offset !== 0) break;
      const parent = node.parentNode;
      const idx = Array.prototype.indexOf.call(parent.childNodes, node);
      offset = atEnd ? idx + 1 : idx;
      node = parent;
    }
    return [node, offset];
  }

  /**
   * Make a language span holding one side of a pair.
   *
   * @param {string} lang - "ko" or "en".
   * @param {DocumentFragment} content - That side's nodes.
   * @returns {HTMLSpanElement} span.bi-<lang> with a lang attribute.
   */
  function sideSpan(lang, content) {
    const span = document.createElement('span');
    span.className = `bi-${lang}`;
    span.lang = lang;
    span.appendChild(trimFragment(content));
    return span;
  }

  /**
   * Replace the first {{ko||en}} pair inside a block with a .bi-pair span.
   *
   * The pair may run across several text nodes (bold or links inside a side);
   * DOM ranges cut it out and keep that formatting.
   *
   * @param {Element} block - Paragraph, heading, item or cell to search.
   * @returns {?HTMLSpanElement} The new .bi-pair, or null when none is left.
   */
  function wrapFirstPair(block) {
    const nodes = textNodes(block);
    const starts = [];
    let text = '';
    nodes.forEach(n => { starts.push(text.length); text += n.data; });
    const m = PAIR.exec(text);
    if (!m) return null;

    /**
     * DOM position of a character offset in the joined text.
     *
     * @param {number} pos - Offset in the joined text.
     * @param {boolean} isEnd - Prefer the end of the previous node at node borders.
     * @returns {Array} [node, offset] for Range.setStart/setEnd.
     */
    const point = (pos, isEnd) => {
      for (let i = 0; i < nodes.length; i++) {
        const s = starts[i], e = s + nodes[i].length;
        if (isEnd ? pos > s && pos <= e : pos >= s && pos < e) return [nodes[i], pos - s];
      }
      const last = nodes[nodes.length - 1];
      return [last, last.length];
    };
    /**
     * Live range over [from, to) of the joined text.
     *
     * @param {number} from - Start offset.
     * @param {number} to - End offset.
     * @param {boolean} [widened] - Take along elements the range exactly covers (for a side's content).
     * @returns {Range} The range.
     */
    const span = (from, to, widened) => {
      const r = document.createRange();
      const s = point(from, false), e = point(to, true);
      r.setStart(...(widened ? widen(s[0], s[1], block, false) : s));
      r.setEnd(...(widened ? widen(e[0], e[1], block, true) : e));
      return r;
    };

    const open = m.index, end = m.index + m[0].length;
    const sep = open + 2 + m[1].length;
    const whole = span(open, end);
    const koRange = span(open + 2, sep, true);
    const enRange = span(sep + 2, end - 2, true);

    const en = enRange.extractContents();
    const ko = koRange.extractContents();
    whole.deleteContents();   // what is left: the {{ || }} delimiters

    const pair = document.createElement('span');
    pair.className = 'bi-pair';
    pair.append(sideSpan('ko', ko), sideSpan('en', en));
    whole.insertNode(pair);
    if (block.textContent.trim() === pair.textContent.trim()) pair.classList.add('is-whole');
    return pair;
  }

  /**
   * Turn every pair under a root into .bi-pair spans.
   *
   * @param {Element} root - A [data-bilingual-root] container.
   * @returns {number} Number of pairs found.
   */
  function splitPairs(root) {
    let count = 0;
    blocksWithPairs(root).forEach(block => {
      while (wrapFirstPair(block)) count++;
    });
    return count;
  }

  /**
   * Read the saved language.
   *
   * @returns {string} "ko", "en" or "both" ("ko" when unset or storage is unavailable).
   */
  function savedLanguage() {
    let v = null;
    try { v = localStorage.getItem(PREF_KEY); } catch { /* storage unavailable */ }
    return LANGS.some(([l]) => l === v) ? v : 'ko';
  }

  /**
   * Remember the language (best effort).
   *
   * @param {string} lang - "ko", "en" or "both".
   * @returns {void}
   */
  function saveLanguage(lang) {
    try { localStorage.setItem(PREF_KEY, lang); } catch { /* storage unavailable: lasts for this page only */ }
  }

  /**
   * Fill the switch box with one button per language.
   *
   * @param {Element} box - The [data-bilingual-switch] element.
   * @param {function(string): void} onPick - Called with the picked language.
   * @returns {HTMLButtonElement[]} The buttons (data-lang holds each language).
   */
  function buildSwitch(box, onPick) {
    box.setAttribute('role', 'group');
    box.setAttribute('aria-label', '본문 언어');
    return LANGS.map(([lang, label]) => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.dataset.lang = lang;
      btn.textContent = label;
      btn.addEventListener('click', () => onPick(lang));
      box.appendChild(btn);
      return btn;
    });
  }

  let total = 0;
  document.querySelectorAll('[data-bilingual-root]').forEach(root => { total += splitPairs(root); });
  if (!total && !document.querySelector('.bi-pair')) return;   // not a bilingual post

  const box = document.querySelector('[data-bilingual-switch]');
  /**
   * Show a language: set it on <html>, press its button, save it and announce it.
   *
   * @param {string} lang - "ko", "en" or "both".
   * @returns {void}
   */
  function setLanguage(lang) {
    document.documentElement.dataset.contentLang = lang;
    buttons.forEach(b => b.setAttribute('aria-pressed', String(b.dataset.lang === lang)));
    saveLanguage(lang);
    document.dispatchEvent(new CustomEvent('bilingual:change', { detail: { lang } }));
  }
  const buttons = box ? buildSwitch(box, setLanguage) : [];
  if (box) box.hidden = false;
  document.addEventListener('bilingual:set', e => setLanguage(e.detail.lang));
  setLanguage(savedLanguage());
})();
