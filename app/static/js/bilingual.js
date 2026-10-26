/**
 * @file Bilingual post text on post pages (board_detail_writer.html,
 * board_detail_magazine.html).
 *
 * Authors write {{한국어||English}} in a post body. This script turns every
 * pair inside the [data-bilingual-root] containers into
 *   <span class="bi-pair"><span class="bi-ko" lang="ko">…</span><span class="bi-en" lang="en">…</span></span>
 * (formatting inside either side is kept; code is left alone), then fills the
 * [data-bilingual-switch] box with 한국어 / English / 함께 buttons and, while
 * 함께 is on, 나란히 / 아래에 / 펼쳐보기 buttons for how whole paragraphs show both
 * languages (펼쳐보기 adds an EN toggle after each paragraph's Korean). The
 * choices are set as data-content-lang and data-both-style on <html>
 * (static/css/bilingual.css shows the matching layout), remembered in this
 * browser, and the language is announced as a "bilingual:change" event; a
 * "bilingual:set" event with {lang} changes it.
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
  // How 함께 lays out whole paragraphs: side by side, English below, or folded behind an EN toggle.
  const STYLES = [['side', '나란히'], ['stack', '아래에'], ['fold', '펼쳐보기']];
  const PREF_KEY = 'bilingual.lang';
  const STYLE_KEY = 'bilingual.bothStyle';

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
   * Put an EN toggle after the Korean side of every whole-paragraph pair, for
   * the 펼쳐보기 layout (the CSS shows it only there).
   *
   * @param {Element} root - A [data-bilingual-root] container.
   * @returns {void}
   */
  function addFoldToggles(root) {
    root.querySelectorAll('.bi-pair.is-whole').forEach(pair => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'bi-fold';
      btn.textContent = 'EN';
      btn.setAttribute('aria-expanded', 'false');
      btn.setAttribute('aria-label', '이 문단 영어 보기');
      pair.querySelector(':scope > .bi-ko').after(btn);
    });
  }

  /**
   * Read a saved choice.
   *
   * @param {string} key - localStorage key.
   * @param {Array<Array<string>>} options - Allowed [value, label] pairs.
   * @returns {string} The saved value, or the first option when unset, unknown or storage is unavailable.
   */
  function readPref(key, options) {
    let v = null;
    try { v = localStorage.getItem(key); } catch { /* storage unavailable */ }
    return options.some(([o]) => o === v) ? v : options[0][0];
  }

  /**
   * Remember a choice (best effort).
   *
   * @param {string} key - localStorage key.
   * @param {string} value - The choice.
   * @returns {void}
   */
  function savePref(key, value) {
    try { localStorage.setItem(key, value); } catch { /* storage unavailable: lasts for this page only */ }
  }

  /**
   * Add a segmented button group to the switch box.
   *
   * @param {Element} box - The [data-bilingual-switch] element.
   * @param {Array<Array<string>>} items - [value, label] per button.
   * @param {string} label - Accessible name of the group.
   * @param {function(string): void} onPick - Called with the picked value.
   * @returns {{group: HTMLElement, buttons: HTMLButtonElement[]}} The group and its buttons (data-value holds each value).
   */
  function buildGroup(box, items, label, onPick) {
    const group = document.createElement('div');
    group.className = 'bi-seg';
    group.setAttribute('role', 'group');
    group.setAttribute('aria-label', label);
    const buttons = items.map(([value, text]) => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.dataset.value = value;
      btn.textContent = text;
      btn.addEventListener('click', () => onPick(value));
      group.appendChild(btn);
      return btn;
    });
    box.appendChild(group);
    return { group, buttons };
  }

  /**
   * Mark the button of the current value as pressed.
   *
   * @param {HTMLButtonElement[]} buttons - A group's buttons.
   * @param {string} value - Current value.
   * @returns {void}
   */
  function press(buttons, value) {
    buttons.forEach(b => b.setAttribute('aria-pressed', String(b.dataset.value === value)));
  }

  let total = 0;
  const roots = document.querySelectorAll('[data-bilingual-root]');
  roots.forEach(root => { total += splitPairs(root); });
  if (!total && !document.querySelector('.bi-pair')) return;   // not a bilingual post
  roots.forEach(addFoldToggles);

  const box = document.querySelector('[data-bilingual-switch]');
  /**
   * Show a language: set it on <html>, press its button, save it and announce it.
   * The layout buttons appear only for 함께.
   *
   * @param {string} lang - "ko", "en" or "both".
   * @returns {void}
   */
  function setLanguage(lang) {
    document.documentElement.dataset.contentLang = lang;
    press(langs.buttons, lang);
    if (styles.group) styles.group.hidden = lang !== 'both';
    savePref(PREF_KEY, lang);
    document.dispatchEvent(new CustomEvent('bilingual:change', { detail: { lang } }));
  }
  /**
   * Choose how 함께 lays out whole paragraphs, press its button and save it.
   *
   * @param {string} style - "side", "stack" or "fold".
   * @returns {void}
   */
  function setBothStyle(style) {
    document.documentElement.dataset.bothStyle = style;
    press(styles.buttons, style);
    savePref(STYLE_KEY, style);
  }
  const langs = box ? buildGroup(box, LANGS, '본문 언어', setLanguage) : { buttons: [] };
  const styles = box ? buildGroup(box, STYLES, '함께 보기 방식', setBothStyle) : { buttons: [] };
  if (box) box.hidden = false;

  // 펼쳐보기: EN 표시를 누르면 그 문단의 영어만 펼치고 접는다
  document.addEventListener('click', e => {
    const btn = e.target.closest('.bi-fold');
    if (!btn) return;
    const open = btn.closest('.bi-pair').classList.toggle('is-open');
    btn.setAttribute('aria-expanded', String(open));
  });
  document.addEventListener('bilingual:set', e => setLanguage(e.detail.lang));
  setBothStyle(readPref(STYLE_KEY, STYLES));
  setLanguage(readPref(PREF_KEY, LANGS));
})();
