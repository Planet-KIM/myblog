/**
 * @file frontend/board_edit_tiptap.js — Multi-page free-position (magazine)
 * editor for editing an existing post (templates/board_edit_tiptap.html).
 *
 * Same editor as board_new_tiptap.js, but it loads the saved layout from
 * #initial-blocks (or the HTML fallback from #initial-content), uploads images
 * under the post id (data-post-id on #block-canvas) and keys its autosave by
 * post. Its selection spell-check dialog uses the older compact design.
 *
 * Built by Vite into static/editor/board_edit_tiptap.js. Styles: static/css/
 * tiptap-editor.css. Keep in sync with board_new_tiptap.js.
 */
import { Editor, Extension } from '@tiptap/core';
import StarterKit from '@tiptap/starter-kit';
import Placeholder from '@tiptap/extension-placeholder';
import TextAlign from '@tiptap/extension-text-align';
import Underline from '@tiptap/extension-underline';
import { TextStyle } from '@tiptap/extension-text-style';
import Color from '@tiptap/extension-color';
import Highlight from '@tiptap/extension-highlight';
import Image from '@tiptap/extension-image';

// ── Upload ────────────────────────────────────────────────
/**
 * Upload an image file and return its public URL.
 *
 * The server files it under the post being edited (data-post-id on
 * #block-canvas).
 *
 * @param {File} file - Image picked, dropped or pasted by the user.
 * @returns {Promise<string>} URL of the stored image.
 * @throws {Error} When the upload request fails.
 */
async function uploadImage(file) {
  const fd = new FormData();
  fd.append('file', file);
  const postId = document.getElementById('block-canvas')?.dataset?.postId;
  if (postId) fd.append('post_id', postId);
  const r = await fetch('/api/upload', { method: 'POST', body: fd });
  if (!r.ok) throw new Error('upload failed');
  return (await r.json()).url;
}

// ── State ─────────────────────────────────────────────────
let idCounter = 0;
const pages = [{ id: 'p1', blocks: [], cw: null, ch: null }];
let currentPageIdx = 0;
let blocks = pages[0].blocks;
let selectedId = null;
let dragInfo = null;
let resizeInfo = null;
let panInfo = null;
const _scSplitActive = new Set(); // block ids with spell-preview panel open

/**
 * Return a new unique id ("b1", "b2", …) for a block or page.
 *
 * The same counter also feeds "bring to front" z-indexes, so ids and z-order
 * values never repeat.
 *
 * @returns {string} Fresh id.
 */
function uid() { return 'b' + (++idCounter); }

// ── 매거진 타이포그래피: textStyle 마크에 크기/서체/자간/대소문자 속성 추가 ──
// (TipTap 기본은 font-size 등을 버리므로, 저장·출력·에디터에서 모두 유지되도록 확장)
const MagTypography = Extension.create({
  name: 'magTypography',
  /**
   * Default options: the extension decorates textStyle marks.
   *
   * @returns {{types: string[]}} Mark types that get the typography attributes.
   */
  addOptions() { return { types: ['textStyle'] }; },
  /**
   * Register the typography attributes on the configured mark types.
   *
   * @returns {Array<Object>} TipTap global attribute definitions for fontSize,
   *   fontFamily, letterSpacing and textTransform.
   */
  addGlobalAttributes() {
    /**
     * Build a mark attribute that round-trips one inline CSS property.
     *
     * @param {string} prop - camelCase CSS property name (e.g. "fontSize").
     * @returns {Object} TipTap attribute spec: parsed from `style[prop]`, rendered as
     *   a `style="kebab-case: value"` declaration (nothing when unset).
     */
    const attr = (prop) => ({
      default: null,
      parseHTML: (el) => el.style && el.style[prop] ? el.style[prop] : null,
      renderHTML: (a) => {
        const v = a[prop];
        if (!v) return {};
        const css = prop.replace(/[A-Z]/g, (m) => '-' + m.toLowerCase());
        return { style: `${css}: ${v}` };
      },
    });
    return [{
      types: this.options.types,
      attributes: {
        fontSize: attr('fontSize'),
        fontFamily: attr('fontFamily'),
        letterSpacing: attr('letterSpacing'),
        textTransform: attr('textTransform'),
      },
    }];
  },
  /**
   * Commands that set the font size / family through the textStyle mark.
   *
   * @returns {Object} `setFontSize(size)` and `setFontFamily(family)` command factories.
   */
  addCommands() {
    return {
      setFontSize: (size) => ({ chain }) => chain().setMark('textStyle', { fontSize: size }).run(),
      setFontFamily: (f) => ({ chain }) => chain().setMark('textStyle', { fontFamily: f }).run(),
    };
  },
});

// 서체 스택(세리프/산세리프)
const FONT_SERIF = "'Fraunces','Noto Serif KR',serif";
const FONT_SANS = "'Pretendard','Inter',system-ui,sans-serif";

/**
 * Default font size of a block type, in px.
 *
 * @param {string} type - Block type.
 * @returns {number} 34 for headings, 18 for everything else.
 */
function _defaultFs(type) { return type === 'heading' ? 34 : 18; }
/**
 * Grow or shrink all text of a block by `delta` px.
 *
 * The size is clamped to 10–120px and applied to the whole content.
 *
 * @param {Object} block - Text or heading block with a live editor.
 * @param {number} delta - Pixels to add (negative to shrink).
 * @returns {void}
 */
function bumpFont(block, delta) {
  if (!block.editor) return;
  block._fs = Math.max(10, Math.min(120, (block._fs || _defaultFs(block.type)) + delta));
  block.editor.chain().focus().selectAll().setFontSize(block._fs + 'px').run();
}

// ── 여행 타임라인: 'DAY n / 라벨:시간' 텍스트 → HTML ──────────
/**
 * Escape &, <, > and " for timeline HTML.
 *
 * @param {?string} s - Raw text (null/undefined become "").
 * @returns {string} HTML-safe text.
 */
function tlEscape(s) { return (s || '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c])); }
/**
 * Parse travel-timeline source text into days and events.
 *
 * Lines starting with "#", "DAY", "N일차" or "N일째" open a new day; "label:HH:MM"
 * (ASCII or full-width colon) adds a timed event; any other line adds an event
 * without a time. Days with neither a title nor events are dropped.
 *
 * @param {?string} text - Timeline source, one entry per line.
 * @returns {Array<{title: string, events: Array<{label: string, time: string}>}>} Parsed days.
 */
function parseTimeline(text) {
  const days = []; let cur = null;
  /**
   * Open an untitled day when an event comes before any day header.
   *
   * @returns {void}
   */
  const ensure = () => { if (!cur) { cur = { title: '', events: [] }; days.push(cur); } };
  (text || '').split(/\r?\n/).forEach(raw => {
    const line = raw.trim(); if (!line) return;
    const m = line.match(/^(.*?)[:：]\s*(\d{1,2}:\d{2})\s*$/);
    if (m) { ensure(); cur.events.push({ label: m[1].trim(), time: m[2].trim() }); }
    else if (line.startsWith('#')) { cur = { title: line.replace(/^#+/, '').trim(), events: [] }; days.push(cur); }
    else if (/^day\b/i.test(line) || /^\d+\s*일\s*차/.test(line) || /^\d+\s*일째/.test(line)) { cur = { title: line, events: [] }; days.push(cur); }
    else { ensure(); cur.events.push({ label: line, time: '' }); }
  });
  return days.filter(d => d.events.length || d.title.trim());
}
/**
 * Render timeline source text as .mag-timeline HTML.
 *
 * @param {?string} text - Timeline source (see parseTimeline).
 * @param {string} [dir] - "h" for the horizontal layout, anything else for vertical.
 * @returns {string} Timeline HTML, or a hint paragraph when there is nothing to show.
 */
function renderTimelineHTML(text, dir) {
  const days = parseTimeline(text);
  const cls = 'mag-timeline' + (dir === 'h' ? ' mtl-h' : '');
  if (!days.length) return `<div class="${cls}"><p class="mtl-empty">일정 입력 (예: # 첫째 날 / 왕궁:09:00)</p></div>`;
  let h = `<div class="${cls}">`;
  for (const d of days) {
    h += '<div class="mtl-day">';
    if ((d.title || '').trim()) h += `<div class="mtl-day-title">${tlEscape(d.title)}</div>`;
    h += '<div class="mtl-events">';
    for (const e of d.events) {
      h += `<div class="mtl-item"><span class="mtl-time">${tlEscape(e.time)}</span><span class="mtl-mark"><span class="mtl-dot"></span></span><span class="mtl-label">${tlEscape(e.label)}</span></div>`;
    }
    h += '</div></div>';
  }
  return h + '</div>';
}

// ── 여행 지도: 장소 텍스트 → 서버 렌더 지도 이미지 ──────────
/**
 * Render a place list as a server-drawn map image.
 *
 * @param {?string} text - Places, one per line ("name@lat,lng" or a name to look up).
 * @returns {string} An <img> pointing at /api/mapimg, or an empty-state hint.
 */
function renderMapHTML(text) {
  if (!(text || '').trim()) return '<div class="mag-map-empty">지도: 장소를 입력하세요 (예: 왕궁@13.75,100.49 또는 장소명)</div>';
  return `<img class="mag-map" src="/api/mapimg?m=${encodeURIComponent(text)}" alt="여행 지도" loading="lazy">`;
}

/**
 * Create the TipTap editor used inside text, heading and code blocks.
 *
 * @param {HTMLElement} el - Element to mount the editor in.
 * @param {string} [content] - Initial HTML (defaults to an empty paragraph).
 * @returns {Editor} The new editor instance.
 */
function createEditor(el, content) {
  return new Editor({
    element: el,
    extensions: [
      StarterKit,
      Placeholder.configure({ placeholder: 'Type here...' }),
      TextAlign.configure({ types: ['heading', 'paragraph'] }),
      Underline, TextStyle, Color,
      MagTypography,
      Highlight.configure({ multicolor: true }),
      Image.configure({ inline: false }),
    ],
    content: content || '<p></p>',
  });
}

/**
 * Current width of the block canvas.
 *
 * @returns {number} Width in px (at least 1, so it is safe to divide by).
 */
function canvasW() { return document.getElementById('block-canvas').offsetWidth || 1; }

/**
 * Grow the canvas so the lowest block has 100px of room below it (min 600px).
 *
 * @returns {void}
 */
function updateCanvasHeight() {
  const canvas = document.getElementById('block-canvas');
  const max = blocks.reduce((m, b) => Math.max(m, b.y + b.h + 100), 600);
  canvas.style.minHeight = max + 'px'; // conventions: allow (height measured from the blocks at runtime)
}

// ── Page management ───────────────────────────────────────
/**
 * Save the current page's editor HTML and canvas size into `pages`.
 *
 * @returns {void}
 */
function syncCurrentPage() {
  blocks.forEach(b => { if (b.editor) b.content = b.editor.getHTML(); });
  const cW = canvasW();
  const cH = Math.max(blocks.reduce((m, b) => Math.max(m, b.y + b.h), 0) + 40, 400);
  pages[currentPageIdx].cw = cW;
  pages[currentPageIdx].ch = cH;
}

/**
 * Remove the current page's blocks from the canvas and destroy their editors.
 *
 * The block data stays in `pages`; only the DOM and editors go away.
 *
 * @returns {void}
 */
function clearCanvas() {
  blocks.forEach(b => { if (b.editor) { b.editor.destroy(); b.editor = null; } });
  document.querySelectorAll('#block-canvas .fb').forEach(el => el.remove());
  document.getElementById('block-canvas').style.minHeight = '600px'; // conventions: allow (resets the runtime min-height kept by updateCanvasHeight)
  selectedId = null;
}

/**
 * Show another page: save the current one, then render the target page.
 *
 * @param {number} idx - Index into `pages`.
 * @returns {void}
 */
function switchPage(idx) {
  if (idx === currentPageIdx) return;
  syncCurrentPage();
  clearCanvas();
  currentPageIdx = idx;
  blocks = pages[idx].blocks;
  blocks.forEach(b => renderBlock(b));
  updateCanvasHeight();
  updatePageTabs();
}

/**
 * Append a new page with an empty heading and text block and switch to it.
 *
 * @returns {void}
 */
function addPage() {
  syncCurrentPage();
  clearCanvas();
  const newPage = { id: uid(), blocks: [], cw: null, ch: null };
  pages.push(newPage);
  currentPageIdx = pages.length - 1;
  blocks = pages[currentPageIdx].blocks;
  addBlock('heading', { content: '<h1></h1>', h: 80 });
  addBlock('text', { h: 200 });
  updatePageTabs();
}

/**
 * Delete a page (the last remaining page is kept) and show its neighbour.
 *
 * @param {number} idx - Index into `pages`.
 * @returns {void}
 */
function deletePage(idx) {
  if (pages.length === 1) return;
  clearCanvas();
  pages.splice(idx, 1);
  currentPageIdx = Math.min(idx, pages.length - 1);
  blocks = pages[currentPageIdx].blocks;
  blocks.forEach(b => renderBlock(b));
  updateCanvasHeight();
  updatePageTabs();
}

/**
 * Rebuild the page tab bar: one tab per page (with × when there are
 * several pages) plus the "+ Page" button.
 *
 * @returns {void}
 */
function updatePageTabs() {
  const tabBar = document.getElementById('page-tab-bar');
  if (!tabBar) return;
  tabBar.innerHTML = '';
  pages.forEach((page, i) => {
    const tab = document.createElement('button');
    tab.type = 'button';
    tab.className = 'page-tab' + (i === currentPageIdx ? ' active' : '');
    tab.textContent = `P${i + 1}`;
    tab.title = `Page ${i + 1}`;
    tab.addEventListener('click', () => switchPage(i));
    if (pages.length > 1) {
      const del = document.createElement('span');
      del.className = 'page-tab-del'; del.innerHTML = '×'; del.title = 'Delete page';
      del.addEventListener('click', e => { e.stopPropagation(); deletePage(i); });
      tab.appendChild(del);
    }
    tabBar.appendChild(tab);
  });
  const addBtn = document.createElement('button');
  addBtn.type = 'button'; addBtn.className = 'page-tab-add';
  addBtn.textContent = '+ Page'; addBtn.title = 'Add page';
  addBtn.addEventListener('click', addPage);
  tabBar.appendChild(addBtn);
}

// ── Add / Remove blocks ───────────────────────────────────
/**
 * Create a block on the current page, render it and select it.
 *
 * @param {string} type - text | heading | image | code | timeline | map | spacer.
 * @param {Object} [opts] - Initial values (position/size, content, src, image
 *   offsets and filter, timeline/map text, drop cap, border settings, id).
 * @returns {Object} The new block record.
 */
function addBlock(type, opts = {}) {
  const cW = canvasW();
  const block = {
    id: opts.id || uid(), type,
    x: opts.x ?? 40,
    y: opts.y ?? nextY(),
    w: opts.w ?? Math.max(200, cW - 80),
    h: opts.h ?? (type === 'image' ? 300 : type === 'spacer' ? 60 : 160),
    content: opts.content || '',
    src: opts.src || '',
    imgOffsetX: opts.imgOffsetX ?? 50,
    imgOffsetY: opts.imgOffsetY ?? 50,
    imgFilter: opts.imgFilter ?? 'none',
    tlText: opts.tlText ?? '',
    tlDir: opts.tlDir ?? 'v',
    mapText: opts.mapText ?? '',
    dropCap: opts.dropCap ?? false,
    showBorder: opts.showBorder ?? false,
    borderColor: opts.borderColor ?? '#000000',
    borderWidth: opts.borderWidth ?? 1,
    borderRadius: opts.borderRadius ?? 0,
    editor: null,
  };
  blocks.push(block);
  renderBlock(block);
  selectBlock(block.id);
  updateCanvasHeight();
  return block;
}

/**
 * Y position for a new block: 20px below the lowest block (20 on an empty page).
 *
 * @returns {number} Top offset in px.
 */
function nextY() {
  if (!blocks.length) return 20;
  return blocks.reduce((m, b) => Math.max(m, b.y + b.h), 0) + 20;
}

/**
 * Delete a block from the current page, its element and its editor.
 *
 * @param {string} id - Block id.
 * @returns {void}
 */
function removeBlock(id) {
  const idx = blocks.findIndex(b => b.id === id);
  if (idx === -1) return;
  const b = blocks[idx];
  if (b.editor) b.editor.destroy();
  _scSplitActive.delete(id);
  document.querySelector(`[data-bid="${id}"]`)?.remove();
  blocks.splice(idx, 1);
  if (selectedId === id) selectedId = null;
  updateCanvasHeight();
}

/**
 * Resize an image block to the image's aspect ratio once the image has loaded.
 *
 * @param {Object} block - Image block (its width is kept).
 * @param {HTMLImageElement} imgEl - The block's <img>.
 * @returns {void}
 */
function fitBlockToImage(block, imgEl) {
  /**
   * Apply the natural aspect ratio to the block height.
   *
   * @returns {void}
   */
  const doFit = () => {
    if (!imgEl.naturalWidth || !imgEl.naturalHeight) return;
    block.h = Math.round(block.w * imgEl.naturalHeight / imgEl.naturalWidth);
    const el = document.querySelector(`[data-bid="${block.id}"]`);
    if (el) el.style.height = block.h + 'px'; // conventions: allow (height from the image's aspect ratio)
    updateCanvasHeight();
  };
  if (imgEl.complete && imgEl.naturalWidth) doFit();
  else imgEl.addEventListener('load', doFit, { once: true });
}

// ── Render block ──────────────────────────────────────────
/**
 * Create the DOM for one block and append it to the canvas.
 *
 * Builds the drag header (type label, z-order, border controls and the
 * type-specific buttons), the body for the block type (TipTap editor, image or
 * drop zone, spacer, timeline or map with its source textarea) and the resize
 * handles, then applies the saved border and image filter.
 *
 * @param {Object} block - Block record from `pages`.
 * @returns {void}
 */
function renderBlock(block) {
  const canvas = document.getElementById('block-canvas');
  const el = document.createElement('div');
  el.className = 'fb'; el.dataset.bid = block.id;
  applyPos(el, block);

  const hdr = document.createElement('div');
  hdr.className = 'fb-hdr';
  const label = document.createElement('span'); label.className = 'fb-label'; label.textContent = block.type;
  hdr.appendChild(label);
  const flex = document.createElement('div'); flex.className = 'fb-hdr-spacer'; hdr.appendChild(flex);
  hdr.appendChild(mkBtn('<i class="bi bi-front"></i>', 'Bring front', () => bringFront(block.id)));
  hdr.appendChild(mkBtn('<i class="bi bi-back"></i>', 'Send back', () => sendBack(block.id)));

  // 먼저 선언 (borderBtn 콜백에서 참조하기 위해)
  const colorSwatch = document.createElement('label');
  colorSwatch.className = 'fb-border-swatch';
  colorSwatch.title = 'Border color';
  colorSwatch.hidden = !block.showBorder;
  colorSwatch.style.background = block.borderColor; // conventions: allow (border colour picked by the user)

  const colorInput = document.createElement('input');
  colorInput.type = 'color';
  colorInput.value = block.borderColor;
  colorInput.className = 'fb-color-input';
  colorInput.addEventListener('input', () => {
    block.borderColor = colorInput.value;
    colorSwatch.style.background = block.borderColor; // conventions: allow (border colour picked by the user)
    applyBorder(el, block);
  });
  colorSwatch.appendChild(colorInput);

  const widthSel = document.createElement('select');
  widthSel.className = 'fb-border-width';
  widthSel.title = 'Border width';
  widthSel.hidden = !block.showBorder;
  [['1px', 1], ['2px', 2], ['3px', 3], ['4px', 4]].forEach(([lbl, val]) => {
    const opt = document.createElement('option');
    opt.value = val; opt.textContent = lbl;
    if (block.borderWidth === val) opt.selected = true;
    widthSel.appendChild(opt);
  });
  widthSel.addEventListener('change', () => {
    block.borderWidth = Number(widthSel.value);
    applyBorder(el, block);
  });

  const radiusSel = document.createElement('select');
  radiusSel.className = 'fb-border-width';
  radiusSel.title = 'Border radius';
  radiusSel.hidden = !block.showBorder;
  [['0', 0], ['4', 4], ['8', 8], ['12', 12], ['16', 16], ['24', 24], ['pill', 9999]].forEach(([lbl, val]) => {
    const opt = document.createElement('option');
    opt.value = val; opt.textContent = lbl === 'pill' ? '● pill' : `${lbl}r`;
    if (block.borderRadius === val) opt.selected = true;
    radiusSel.appendChild(opt);
  });
  radiusSel.addEventListener('change', () => {
    block.borderRadius = Number(radiusSel.value);
    applyBorder(el, block);
  });

  const borderBtn = mkBtn('<i class="bi bi-border-style"></i>', 'Toggle border', () => {
    block.showBorder = !block.showBorder;
    borderBtn.classList.toggle('fb-btn-active', block.showBorder);
    colorSwatch.hidden = !block.showBorder;
    widthSel.hidden = !block.showBorder;
    radiusSel.hidden = !block.showBorder;
    applyBorder(el, block);
  });
  if (block.showBorder) borderBtn.classList.add('fb-btn-active');

  hdr.appendChild(borderBtn);
  hdr.appendChild(colorSwatch);
  hdr.appendChild(widthSel);
  hdr.appendChild(radiusSel);

  if (block.type === 'text' || block.type === 'heading') {
    const serifBtn = mkBtn('<span style="font-family:Georgia,serif;font-weight:700;">Aa</span>', '세리프 / 산세리프', () => {
      block._serif = !block._serif;
      serifBtn.classList.toggle('fb-btn-active', block._serif);
      block.editor?.chain().focus().selectAll().setFontFamily(block._serif ? FONT_SERIF : FONT_SANS).run();
    });
    hdr.appendChild(serifBtn);
    hdr.appendChild(mkBtn('<b style="font-size:0.72rem;">A−</b>', '글자 작게', () => bumpFont(block, -2)));
    hdr.appendChild(mkBtn('<b style="font-size:0.95rem;">A+</b>', '글자 크게', () => bumpFont(block, 2)));
    const tcLabel = document.createElement('label');
    tcLabel.className = 'fb-btn fb-tc-btn'; tcLabel.title = '글자 색';
    tcLabel.innerHTML = '<i class="bi bi-palette-fill"></i>';
    const tcIn = document.createElement('input');
    tcIn.type = 'color'; tcIn.value = '#b4542f';
    tcIn.className = 'fb-tc-input';
    tcIn.addEventListener('mousedown', e => e.stopPropagation());
    tcIn.addEventListener('input', () => block.editor && block.editor.chain().focus().selectAll().setColor(tcIn.value).run());
    tcLabel.appendChild(tcIn);
    hdr.appendChild(tcLabel);
    if (block.type === 'text') {
      const dcBtn = mkBtn('<b style="font-family:Georgia,serif;">D</b>', '드롭캡 (첫 글자 장식)', () => {
        block.dropCap = !block.dropCap;
        dcBtn.classList.toggle('fb-btn-active', block.dropCap);
        const ed = el.querySelector('.fb-editor'); if (ed) ed.classList.toggle('mag-dropcap', block.dropCap);
      });
      if (block.dropCap) dcBtn.classList.add('fb-btn-active');
      hdr.appendChild(dcBtn);
    }
  }

  if (block.type === 'image') {
    const FILTERS = ['none', 'duotone', 'bw'];
    const FLABEL = { none: '원본', duotone: '듀오톤', bw: '흑백' };
    const filterBtn = mkBtn('<i class="bi bi-circle-half"></i>', '사진 필터: ' + FLABEL[block.imgFilter || 'none'], () => {
      const i = FILTERS.indexOf(block.imgFilter || 'none');
      block.imgFilter = FILTERS[(i + 1) % FILTERS.length];
      filterBtn.classList.toggle('fb-btn-active', block.imgFilter !== 'none');
      filterBtn.title = '사진 필터: ' + FLABEL[block.imgFilter];
      applyImgFilter(el, block);
    });
    if ((block.imgFilter || 'none') !== 'none') filterBtn.classList.add('fb-btn-active');
    hdr.appendChild(filterBtn);
  }

  if (block.type === 'timeline' || block.type === 'map') {
    const editBtn = mkBtn('<i class="bi bi-pencil"></i>', block.type === 'map' ? '장소 편집' : '일정 텍스트 편집', () => {
      const ta = el.querySelector('.fb-tl-src'), rd = el.querySelector('.fb-tl-render');
      if (!ta || !rd) return;
      const editing = ta.hidden;
      ta.hidden = !editing;
      rd.hidden = editing;
      editBtn.classList.toggle('fb-btn-active', editing);
      if (editing) ta.focus();
    });
    hdr.appendChild(editBtn);
  }

  if (block.type === 'timeline') {
    const dirBtn = mkBtn('<i class="bi bi-distribute-horizontal"></i>', '세로 / 가로 전환', () => {
      block.tlDir = block.tlDir === 'h' ? 'v' : 'h';
      block.content = renderTimelineHTML(block.tlText || '', block.tlDir);
      const rd = el.querySelector('.fb-tl-render'); if (rd) rd.innerHTML = block.content;
      dirBtn.classList.toggle('fb-btn-active', block.tlDir === 'h');
    });
    if (block.tlDir === 'h') dirBtn.classList.add('fb-btn-active');
    hdr.appendChild(dirBtn);
  }

  if (block.type === 'text') {
    const scBtn = mkBtn(
      '<span style="font-size:0.7rem;font-weight:700;letter-spacing:-0.5px;">맞춤법</span>',
      '블록 맞춤법 미리보기',
      () => _scBlockPreviewToggle(block.id),
    );
    scBtn.classList.add('fb-sc-preview-btn');
    scBtn.classList.add('fb-btn-wide');
    hdr.appendChild(scBtn);
  }

  const del = mkBtn('<i class="bi bi-x-lg"></i>', 'Delete', () => removeBlock(block.id));
  del.classList.add('fb-del'); hdr.appendChild(del);
  hdr.addEventListener('mousedown', e => { if (!e.target.closest('button, select, label, input')) startDrag(e, block); });
  el.appendChild(hdr);

  const body = document.createElement('div');
  body.className = 'fb-body';

  if (block.type === 'text' || block.type === 'heading' || block.type === 'code') {
    const edEl = document.createElement('div'); edEl.className = 'fb-editor';
    if (block.dropCap) edEl.classList.add('mag-dropcap');
    body.appendChild(edEl); el.appendChild(body); canvas.appendChild(el);
    block.editor = createEditor(edEl, block.content || (block.type === 'heading' ? '<h1></h1>' : '<p></p>'));
  } else if (block.type === 'image') {
    body.classList.add('fb-body-image');
    if (block.src) {
      const img = document.createElement('img');
      img.src = block.src; img.className = 'fb-img'; img.draggable = false;
      img.style.objectPosition = `${block.imgOffsetX}% ${block.imgOffsetY}%`; // conventions: allow (photo focal point panned by the user)
      fitBlockToImage(block, img);
      body.appendChild(img);
      body.addEventListener('mousedown', e => { e.stopPropagation(); selectBlock(block.id); startPan(e, block); });
      const hint = document.createElement('div');
      hint.className = 'fb-pan-hint'; hint.textContent = '✥ drag to pan';
      body.appendChild(hint);
    } else { body.appendChild(buildDropZone(block)); }
    el.appendChild(body); canvas.appendChild(el);
  } else if (block.type === 'spacer') {
    body.className = 'fb-body fb-spacer-body';
    body.innerHTML = '<span>— spacer —</span>';
    el.appendChild(body); canvas.appendChild(el);
  } else if (block.type === 'timeline') {
    body.classList.add('fb-body-timeline');
    const render = document.createElement('div');
    render.className = 'fb-tl-render';
    if (!block.content) block.content = renderTimelineHTML(block.tlText || '', block.tlDir || 'v');
    render.innerHTML = block.content;
    const ta = document.createElement('textarea');
    ta.className = 'fb-tl-src fb-tl-src-block';
    ta.value = block.tlText || '';
    ta.spellcheck = false;
    ta.placeholder = '# 첫째 날\n왕궁:09:00\n점심:12:30';
    ta.hidden = true;
    ta.addEventListener('mousedown', e => e.stopPropagation());
    ta.addEventListener('input', () => {
      block.tlText = ta.value;
      block.content = renderTimelineHTML(block.tlText, block.tlDir || 'v');
      render.innerHTML = block.content;
    });
    body.appendChild(render);
    body.appendChild(ta);
    el.appendChild(body); canvas.appendChild(el);
  } else if (block.type === 'map') {
    body.classList.add('fb-body-map');
    const render = document.createElement('div');
    render.className = 'fb-tl-render fb-map-render';
    if (!block.content) block.content = renderMapHTML(block.mapText || '');
    render.innerHTML = block.content;
    const ta = document.createElement('textarea');
    ta.className = 'fb-tl-src fb-tl-src-block';
    ta.value = block.mapText || '';
    ta.spellcheck = false;
    ta.placeholder = '왕궁@13.75,100.49\n왓 포@13.746,100.493\n(장소명만 적으면 자동 검색)';
    ta.hidden = true;
    ta.addEventListener('mousedown', e => e.stopPropagation());
    ta.addEventListener('change', () => {
      block.mapText = ta.value;
      block.content = renderMapHTML(block.mapText);
      render.innerHTML = block.content;
    });
    body.appendChild(render);
    body.appendChild(ta);
    el.appendChild(body); canvas.appendChild(el);
  }

  // body가 DOM에 붙은 이후 테두리·필터 적용
  applyBorder(el, block);
  applyImgFilter(el, block);

  ['se', 'e', 's'].forEach(edge => {
    const rh = document.createElement('div');
    rh.className = `fb-rh fb-rh-${edge}`;
    rh.addEventListener('mousedown', e => { e.stopPropagation(); selectBlock(block.id); startResize(e, block, edge); });
    el.appendChild(rh);
  });
  el.addEventListener('mousedown', () => selectBlock(block.id));
}

/**
 * Build the "click or drag image here" area of an empty image block.
 *
 * @param {Object} block - Image block that receives the uploaded src.
 * @returns {HTMLDivElement} The drop zone element.
 */
function buildDropZone(block) {
  const drop = document.createElement('div');
  drop.className = 'fb-drop';
  drop.innerHTML = '<i class="bi bi-image" style="font-size:2.5rem;color:#d1d5db;"></i><p>Click or drag image here</p>';
  drop.addEventListener('click', () => pickImage(block));
  drop.addEventListener('dragover', e => { e.preventDefault(); drop.classList.add('over'); });
  drop.addEventListener('dragleave', () => drop.classList.remove('over'));
  drop.addEventListener('drop', async e => {
    e.preventDefault(); drop.classList.remove('over');
    const file = e.dataTransfer?.files?.[0];
    if (file?.type.startsWith('image/')) { block.src = await uploadImage(file); refreshBlock(block); }
  });
  return drop;
}

/**
 * Re-render a block from its data (after its image changed) and select it.
 *
 * @param {Object} block - Block record.
 * @returns {void}
 */
function refreshBlock(block) {
  if (block.editor) block.content = block.editor.getHTML();
  const old = document.querySelector(`[data-bid="${block.id}"]`);
  if (old) { if (block.editor) { block.editor.destroy(); block.editor = null; } old.remove(); }
  renderBlock(block); selectBlock(block.id);
}

/**
 * Position and size a block element from its record.
 *
 * @param {HTMLElement} el - The .fb element.
 * @param {{x: number, y: number, w: number, h: number}} b - Block geometry in px.
 * @returns {void}
 */
function applyPos(el, b) {
  el.style.left = b.x + 'px'; el.style.top = b.y + 'px'; // conventions: allow (block geometry from the layout data)
  el.style.width = b.w + 'px'; el.style.height = b.h + 'px'; // conventions: allow (block geometry from the layout data)
}

/**
 * Show or clear the user-chosen border on a block body.
 *
 * @param {HTMLElement} el - The .fb element.
 * @param {Object} block - Block with showBorder, borderWidth, borderColor, borderRadius.
 * @returns {void}
 */
function applyBorder(el, block) {
  const body = el.querySelector('.fb-body');
  if (!body) return;
  if (block.showBorder) {
    body.style.border = `${block.borderWidth ?? 1}px solid ${block.borderColor ?? '#000000'}`; // conventions: allow (border chosen by the user)
    const r = block.borderRadius ?? 0;
    body.style.borderRadius = r >= 9999 ? '9999px' : `${r}px`; // conventions: allow (radius chosen by the user)
  } else {
    body.style.border = ''; // conventions: allow (clears the user-chosen border)
    body.style.borderRadius = ''; // conventions: allow (clears the user-chosen radius)
  }
}

/**
 * Apply the block's photo filter class (duotone / black-and-white) to its image.
 *
 * @param {HTMLElement} el - The .fb element.
 * @param {Object} block - Image block with imgFilter.
 * @returns {void}
 */
function applyImgFilter(el, block) {
  const img = el.querySelector('.fb-img');
  if (!img) return;
  img.classList.remove('mag-filter-bw', 'mag-filter-duotone');
  const f = block.imgFilter || 'none';
  if (f !== 'none') img.classList.add('mag-filter-' + f);
}

/**
 * Mark one block as selected (and unmark the others).
 *
 * @param {string} id - Block id.
 * @returns {void}
 */
function selectBlock(id) {
  selectedId = id;
  document.querySelectorAll('.fb').forEach(e => e.classList.remove('selected'));
  document.querySelector(`[data-bid="${id}"]`)?.classList.add('selected');
}

/**
 * Raise a block above the others with a fresh, higher z-index.
 *
 * @param {string} id - Block id.
 * @returns {void}
 */
function bringFront(id) { const el = document.querySelector(`[data-bid="${id}"]`); if (el) el.style.zIndex = String(++idCounter); } // conventions: allow (stacking order chosen by the user)
/**
 * Send a block behind the others (z-index 1).
 *
 * @param {string} id - Block id.
 * @returns {void}
 */
function sendBack(id)   { const el = document.querySelector(`[data-bid="${id}"]`); if (el) el.style.zIndex = '1'; } // conventions: allow (stacking order chosen by the user)

/**
 * Create a small block-header button.
 *
 * @param {string} html - Button content (icon markup).
 * @param {string} title - Tooltip.
 * @param {Function} fn - Click handler; the click does not reach the block.
 * @returns {HTMLButtonElement} The button.
 */
function mkBtn(html, title, fn) {
  const b = document.createElement('button');
  b.type = 'button'; b.innerHTML = html; b.title = title; b.className = 'fb-btn';
  b.addEventListener('click', e => { e.stopPropagation(); fn(); });
  return b;
}

/**
 * Open a file picker and upload the chosen image into an image block.
 *
 * @param {Object} block - Image block that receives the src.
 * @returns {void}
 */
function pickImage(block) {
  const inp = document.createElement('input');
  inp.type = 'file'; inp.accept = 'image/*';
  inp.addEventListener('change', async e => {
    const file = e.target.files?.[0]; if (!file) return;
    try { block.src = await uploadImage(file); refreshBlock(block); } catch { alert('Upload failed.'); }
  });
  inp.click();
}

// ── Drag ──────────────────────────────────────────────────
/**
 * Start moving a block with the mouse (from its header).
 *
 * @param {MouseEvent} e - The mousedown event.
 * @param {Object} block - Block being moved.
 * @returns {void}
 */
function startDrag(e, block) {
  e.preventDefault();
  const el = document.querySelector(`[data-bid="${block.id}"]`); if (!el) return;
  const rect = el.getBoundingClientRect();
  dragInfo = { id: block.id, offsetX: e.clientX - rect.left, offsetY: e.clientY - rect.top };
  el.classList.add('dragging');
  document.addEventListener('mousemove', onDrag);
  document.addEventListener('mouseup', endDrag);
}
// ── Snap & alignment guides (Alt 키로 일시 해제) ────────────
const SNAP_PX = 7;
/**
 * Snap a moving box to the canvas edges/centre and to other blocks.
 *
 * Each axis snaps independently to the nearest target within `snap` px, using
 * the box's start, centre and end against the targets' start, centre and end.
 *
 * @param {{x: number, y: number, w: number, h: number}} moving - Proposed box.
 * @param {Array<Object>} others - Other blocks on the page.
 * @param {number} cw - Canvas width.
 * @param {number} snap - Snap distance in px.
 * @param {number[]} [extraX] - Extra vertical targets (column grid lines).
 * @returns {{x: number, y: number, vLines: number[], hLines: number[]}} Snapped
 *   position and the guide lines that it now touches.
 */
function computeSnap(moving, others, cw, snap, extraX = []) {
  const mX = [moving.x, moving.x + moving.w / 2, moving.x + moving.w];
  const mY = [moving.y, moving.y + moving.h / 2, moving.y + moving.h];
  const tX = [0, cw / 2, cw, ...extraX];
  const tY = [0];
  others.forEach(o => { tX.push(o.x, o.x + o.w / 2, o.x + o.w); tY.push(o.y, o.y + o.h / 2, o.y + o.h); });
  let bestDx = null, bestDy = null;
  mX.forEach(me => tX.forEach(t => { const d = t - me; if (Math.abs(d) <= snap && (bestDx === null || Math.abs(d) < Math.abs(bestDx))) bestDx = d; }));
  mY.forEach(me => tY.forEach(t => { const d = t - me; if (Math.abs(d) <= snap && (bestDy === null || Math.abs(d) < Math.abs(bestDy))) bestDy = d; }));
  const x = moving.x + (bestDx || 0);
  const y = moving.y + (bestDy || 0);
  const sX = [x, x + moving.w / 2, x + moving.w];
  const sY = [y, y + moving.h / 2, y + moving.h];
  const vLines = [...new Set(tX.filter(t => sX.some(e => Math.abs(e - t) < 0.5)))];
  const hLines = [...new Set(tY.filter(t => sY.some(e => Math.abs(e - t) < 0.5)))];
  return { x, y, vLines, hLines };
}
/**
 * Snap the right and bottom edges of a block being resized.
 *
 * @param {Object} block - Block being resized (x/y stay fixed).
 * @param {number} w - Proposed width.
 * @param {number} h - Proposed height.
 * @param {Array<Object>} others - Other blocks on the page.
 * @param {number} cw - Canvas width.
 * @param {number} snap - Snap distance in px.
 * @param {number[]} [extraX] - Extra vertical targets (column grid lines).
 * @returns {{w: number, h: number, vLines: number[], hLines: number[]}} Snapped
 *   size (min 80x40) and the guide lines it touches.
 */
function computeResizeSnap(block, w, h, others, cw, snap, extraX = []) {
  const tX = [cw / 2, cw, ...extraX], tY = [];
  others.forEach(o => { tX.push(o.x, o.x + o.w / 2, o.x + o.w); tY.push(o.y, o.y + o.h / 2, o.y + o.h); });
  const right = block.x + w, bottom = block.y + h;
  let bestDw = null, bestDh = null;
  tX.forEach(t => { const d = t - right; if (Math.abs(d) <= snap && (bestDw === null || Math.abs(d) < Math.abs(bestDw))) bestDw = d; });
  tY.forEach(t => { const d = t - bottom; if (Math.abs(d) <= snap && (bestDh === null || Math.abs(d) < Math.abs(bestDh))) bestDh = d; });
  const nw = Math.max(80, w + (bestDw || 0));
  const nh = Math.max(40, h + (bestDh || 0));
  const vLines = [...new Set(tX.filter(t => Math.abs((block.x + nw) - t) < 0.5))];
  const hLines = [...new Set(tY.filter(t => Math.abs((block.y + nh) - t) < 0.5))];
  return { w: nw, h: nh, vLines, hLines };
}
/**
 * Return the snap-guide overlay, creating it on first use.
 *
 * @returns {HTMLDivElement} The #snap-guides layer on the canvas.
 */
function _guideLayer() {
  const canvas = document.getElementById('block-canvas');
  let layer = document.getElementById('snap-guides');
  if (!layer) {
    layer = document.createElement('div');
    layer.id = 'snap-guides';
    layer.className = 'fb-snap-layer';
    canvas.appendChild(layer);
  }
  return layer;
}
/**
 * Draw the snap guide lines, replacing the previous ones.
 *
 * @param {number[]} vLines - X positions of vertical guides.
 * @param {number[]} hLines - Y positions of horizontal guides.
 * @returns {void}
 */
function showSnapGuides(vLines, hLines) {
  const canvas = document.getElementById('block-canvas');
  const layer = _guideLayer();
  const H = Math.max(canvas.scrollHeight, canvas.clientHeight);
  layer.innerHTML = '';
  // conventions: allow (guide position and length computed from the canvas at runtime)
  vLines.forEach(x => { const l = document.createElement('div'); l.style.cssText = `position:absolute;top:0;left:${x}px;width:1px;height:${H}px;background:#2a82c4;`; layer.appendChild(l); });
  // conventions: allow (guide position and length computed from the canvas at runtime)
  hLines.forEach(y => { const l = document.createElement('div'); l.style.cssText = `position:absolute;left:0;top:${y}px;height:1px;width:100%;background:#2a82c4;`; layer.appendChild(l); });
}
/**
 * Remove all snap guide lines.
 *
 * @returns {void}
 */
function clearSnapGuides() { document.getElementById('snap-guides')?.replaceChildren(); }

// ── 칼럼 그리드 (12칼럼, 스냅 가이드 역할) ──────────────────
let gridOn = false;
const GRID_COLS = 12, GRID_MARGIN = 40, GRID_GUTTER = 16;
let _gridXs = [];
/**
 * Left and right edges of the columns of a column grid.
 *
 * @param {number} cw - Canvas width.
 * @param {number} margin - Outer margin on each side.
 * @param {number} cols - Number of columns.
 * @param {number} gutter - Gap between columns.
 * @returns {number[]} Rounded x positions (two per column), or [] when nothing fits.
 */
function columnLines(cw, margin, cols, gutter) {
  const usable = cw - margin * 2;
  if (usable <= 0 || cols < 1) return [];
  const colW = (usable - (cols - 1) * gutter) / cols;
  const xs = [];
  for (let i = 0; i < cols; i++) {
    const left = margin + i * (colW + gutter);
    xs.push(Math.round(left), Math.round(left + colW));
  }
  return xs;
}
/**
 * Draw (or remove) the 12-column guide grid and cache its snap lines.
 *
 * @returns {void}
 */
function renderGrid() {
  const canvas = document.getElementById('block-canvas');
  let layer = document.getElementById('col-grid');
  if (!gridOn) { layer?.remove(); _gridXs = []; return; }
  if (!layer) {
    layer = document.createElement('div');
    layer.id = 'col-grid';
    layer.className = 'fb-grid-layer';
    canvas.insertBefore(layer, canvas.firstChild);
  }
  const cw = canvasW();
  const H = Math.max(canvas.scrollHeight, canvas.clientHeight);
  _gridXs = columnLines(cw, GRID_MARGIN, GRID_COLS, GRID_GUTTER);
  const colW = (cw - GRID_MARGIN * 2 - (GRID_COLS - 1) * GRID_GUTTER) / GRID_COLS;
  layer.innerHTML = '';
  for (let i = 0; i < GRID_COLS; i++) {
    const left = GRID_MARGIN + i * (colW + GRID_GUTTER);
    const band = document.createElement('div');
    // conventions: allow (column position and size computed from the canvas width)
    band.style.cssText = `position:absolute;top:0;left:${left}px;width:${colW}px;height:${H}px;background:rgba(42,130,196,0.05);border-left:1px solid rgba(42,130,196,0.14);border-right:1px solid rgba(42,130,196,0.14);`;
    layer.appendChild(band);
  }
}
/**
 * Turn the column grid on or off and update the toolbar button.
 *
 * @returns {void}
 */
function toggleGrid() {
  gridOn = !gridOn;
  renderGrid();
  document.getElementById('fb-grid-btn')?.classList.toggle('fb-btn-active', gridOn);
}

/**
 * Move the dragged block with the mouse, snapping unless Alt is held.
 *
 * @param {MouseEvent} e - mousemove event.
 * @returns {void}
 */
function onDrag(e) {
  if (!dragInfo) return;
  const block = blocks.find(b => b.id === dragInfo.id); if (!block) return;
  const canvas = document.getElementById('block-canvas');
  const cRect = canvas.getBoundingClientRect();
  let nx = Math.max(0, e.clientX - cRect.left - dragInfo.offsetX);
  let ny = Math.max(0, e.clientY - cRect.top - dragInfo.offsetY + canvas.scrollTop);
  if (!e.altKey) {
    const others = blocks.filter(b => b.id !== block.id);
    const s = computeSnap({ x: nx, y: ny, w: block.w, h: block.h }, others, canvasW(), SNAP_PX, gridOn ? _gridXs : []);
    nx = s.x; ny = s.y;
    showSnapGuides(s.vLines, s.hLines);
  } else { clearSnapGuides(); }
  block.x = nx; block.y = ny;
  const el = document.querySelector(`[data-bid="${block.id}"]`);
  if (el) { el.style.left = block.x + 'px'; el.style.top = block.y + 'px'; } // conventions: allow (drag position)
  updateCanvasHeight();
}
/**
 * Finish a block drag and remove the guides and listeners.
 *
 * @returns {void}
 */
function endDrag() {
  clearSnapGuides();
  document.querySelector(`[data-bid="${dragInfo?.id}"]`)?.classList.remove('dragging');
  dragInfo = null;
  document.removeEventListener('mousemove', onDrag);
  document.removeEventListener('mouseup', endDrag);
}

// ── Resize ────────────────────────────────────────────────
/**
 * Start resizing a block from one of its handles.
 *
 * @param {MouseEvent} e - The mousedown event.
 * @param {Object} block - Block being resized.
 * @param {string} edge - Handle: "e" (width), "s" (height) or "se" (both).
 * @returns {void}
 */
function startResize(e, block, edge) {
  e.preventDefault(); e.stopPropagation();
  resizeInfo = { id: block.id, edge, startX: e.clientX, startY: e.clientY, startW: block.w, startH: block.h };
  document.addEventListener('mousemove', onResize);
  document.addEventListener('mouseup', endResize);
}
/**
 * Resize the block with the mouse, snapping unless Alt is held.
 *
 * @param {MouseEvent} e - mousemove event.
 * @returns {void}
 */
function onResize(e) {
  if (!resizeInfo) return;
  const block = blocks.find(b => b.id === resizeInfo.id); if (!block) return;
  const dx = e.clientX - resizeInfo.startX, dy = e.clientY - resizeInfo.startY;
  let w = block.w, h = block.h;
  if (resizeInfo.edge === 'e' || resizeInfo.edge === 'se') w = Math.max(80, resizeInfo.startW + dx);
  if (resizeInfo.edge === 's' || resizeInfo.edge === 'se') h = Math.max(40, resizeInfo.startH + dy);
  if (!e.altKey) {
    const others = blocks.filter(b => b.id !== block.id);
    const s = computeResizeSnap(block, w, h, others, canvasW(), SNAP_PX, gridOn ? _gridXs : []);
    w = s.w; h = s.h;
    showSnapGuides(s.vLines, s.hLines);
  } else { clearSnapGuides(); }
  block.w = w; block.h = h;
  const el = document.querySelector(`[data-bid="${block.id}"]`);
  if (el) { el.style.width = block.w + 'px'; el.style.height = block.h + 'px'; } // conventions: allow (resize geometry)
  updateCanvasHeight();
}
/**
 * Finish a resize and remove the guides and listeners.
 *
 * @returns {void}
 */
function endResize() {
  clearSnapGuides();
  resizeInfo = null;
  document.removeEventListener('mousemove', onResize);
  document.removeEventListener('mouseup', endResize);
}

// ── Image Pan ─────────────────────────────────────────────
/**
 * Start panning the photo inside an image block.
 *
 * @param {MouseEvent} e - The mousedown event.
 * @param {Object} block - Image block.
 * @returns {void}
 */
function startPan(e, block) {
  e.preventDefault();
  document.querySelector(`[data-bid="${block.id}"] .fb-body-image`)?.classList.add('panning');
  panInfo = { id: block.id, startX: e.clientX, startY: e.clientY, startOX: block.imgOffsetX ?? 50, startOY: block.imgOffsetY ?? 50 };
  document.addEventListener('mousemove', onPan);
  document.addEventListener('mouseup', endPan);
}
/**
 * Move the photo's focal point (object-position, 0–100%) with the mouse.
 *
 * @param {MouseEvent} e - mousemove event.
 * @returns {void}
 */
function onPan(e) {
  if (!panInfo) return;
  const block = blocks.find(b => b.id === panInfo.id); if (!block) return;
  block.imgOffsetX = Math.max(0, Math.min(100, panInfo.startOX - (e.clientX - panInfo.startX) / block.w * 100));
  block.imgOffsetY = Math.max(0, Math.min(100, panInfo.startOY - (e.clientY - panInfo.startY) / block.h * 100));
  const img = document.querySelector(`[data-bid="${block.id}"] .fb-img`);
  if (img) img.style.objectPosition = `${block.imgOffsetX}% ${block.imgOffsetY}%`; // conventions: allow (photo focal point while panning)
}
/**
 * Finish panning and remove the listeners.
 *
 * @returns {void}
 */
function endPan() {
  document.querySelector(`[data-bid="${panInfo?.id}"] .fb-body-image`)?.classList.remove('panning');
  panInfo = null;
  document.removeEventListener('mousemove', onPan);
  document.removeEventListener('mouseup', endPan);
}

// ── Inline preview ────────────────────────────────────────
let previewActive = false;

/**
 * Build the HTML of one page for the inline preview.
 *
 * Same percent-based absolute layout as the published HTML. A page that was
 * never synced falls back to a 1200px x 600px page.
 *
 * @param {{cw: ?number, ch: ?number, blocks: Array<Object>}} page - Page snapshot.
 * @returns {string} HTML for one preview page.
 */
function buildPreviewSlide(page) {
  const cw = page.cw || 1200;
  const ch = page.ch || 600;
  const ratio = (ch / cw * 100).toFixed(3);
  let html = `<div style="position:relative;width:100%;padding-bottom:${ratio}%;overflow:hidden;">`;
  html += `<div style="position:absolute;top:0;left:0;width:100%;height:100%;">`;
  (page.blocks || []).forEach(b => {
    const L = (b.x / cw * 100).toFixed(3);
    const T = (b.y / ch * 100).toFixed(3);
    const W = (b.w / cw * 100).toFixed(3);
    const H = (b.h / ch * 100).toFixed(3);
    const br = b.showBorder ? (b.borderRadius >= 9999 ? '9999px' : `${b.borderRadius ?? 0}px`) : '';
    const border = b.showBorder ? `border:${b.borderWidth ?? 1}px solid ${b.borderColor ?? '#000000'};border-radius:${br};` : '';
    const s = `position:absolute;left:${L}%;top:${T}%;width:${W}%;height:${H}%;overflow:hidden;box-sizing:border-box;${border}`;
    if (b.type === 'image' && b.src) {
      const ox = (b.imgOffsetX ?? 50).toFixed(1), oy = (b.imgOffsetY ?? 50).toFixed(1);
      const fc = b.imgFilter && b.imgFilter !== 'none' ? ` class="mag-filter-${b.imgFilter}"` : '';
      html += `<div style="${s}"><img${fc} src="${b.src}" style="width:100%;height:100%;object-fit:cover;object-position:${ox}% ${oy}%;display:block;"></div>`;
    } else if (b.type === 'spacer') {
      html += `<div style="${s}"></div>`;
    } else {
      html += `<div${b.dropCap ? ' class="mag-dropcap"' : ''} style="${s}">${b.content || ''}</div>`;
    }
  });
  html += '</div></div>';
  return html;
}

/**
 * Replace the canvas with a read-only preview of every page.
 *
 * Clicking anywhere in the preview returns to editing.
 *
 * @returns {void}
 */
function enterPreview() {
  syncCurrentPage();
  const pagesSnap = pages.map(p => ({
    id: p.id, cw: p.cw || canvasW(), ch: p.ch || 600,
    blocks: p.blocks.map(b => ({ ...b, content: b.editor ? b.editor.getHTML() : b.content })),
  }));

  const canvas = document.getElementById('block-canvas');
  const tabBar = document.getElementById('page-tab-bar');
  canvas.hidden = true;
  if (tabBar) tabBar.hidden = true;

  const wrap = canvas.parentElement;
  const pv = document.createElement('div');
  pv.id = 'inline-preview';
  pv.className = 'inline-preview';
  pv.title = 'Click to return to editing';

  pagesSnap.forEach(page => {
    const pg = document.createElement('div');
    pg.className = 'inline-preview-page';
    pg.innerHTML = buildPreviewSlide(page);
    pv.appendChild(pg);
  });

  const hint = document.createElement('div');
  hint.className = 'inline-preview-hint';
  hint.textContent = 'Click anywhere to return to editing';
  pv.appendChild(hint);

  pv.addEventListener('click', exitPreview);
  wrap.appendChild(pv);

  const btn = document.querySelector('.tiptap-btn-preview');
  if (btn) { btn.textContent = '← Edit'; btn.classList.add('fb-btn-active'); }

  previewActive = true;
}

/**
 * Remove the preview and show the canvas and page tabs again.
 *
 * @returns {void}
 */
function exitPreview() {
  const canvas = document.getElementById('block-canvas');
  const tabBar = document.getElementById('page-tab-bar');
  const pv = document.getElementById('inline-preview');
  canvas.hidden = false;
  if (tabBar) tabBar.hidden = false;
  if (pv) pv.remove();

  const btn = document.querySelector('.tiptap-btn-preview');
  if (btn) { btn.textContent = 'Preview'; btn.classList.remove('fb-btn-active'); }

  previewActive = false;
}

/**
 * Switch between editing and the inline preview.
 *
 * @returns {void}
 */
function togglePreview() {
  previewActive ? exitPreview() : enterPreview();
}

// ── Collect (v3 multi-page) ───────────────────────────────
/**
 * Serialize every page for the publish form.
 *
 * Syncs the current page first, then builds the v3 layout JSON
 * ({v: 3, pages: [{id, cw, ch, blocks}]}) and the reading HTML: one
 * .magazine-page per page whose blocks are absolutely positioned in percent of
 * the page size, so the published layout scales with the reader's width.
 *
 * @returns {{blocksJson: string, html: string}} Layout JSON and reading HTML.
 */
function collectData() {
  syncCurrentPage();

  const pagesData = pages.map(page => {
    const cW = page.cw || canvasW();
    const cH = page.ch || 600;
    return {
      id: page.id, cw: cW, ch: cH,
      blocks: page.blocks.map(b => ({
        id: b.id, type: b.type,
        x: Math.round(b.x), y: Math.round(b.y),
        w: Math.round(b.w), h: Math.round(b.h),
        content: b.content || '', src: b.src || '',
        imgOffsetX: b.imgOffsetX ?? 50, imgOffsetY: b.imgOffsetY ?? 50,
        imgFilter: b.imgFilter || 'none',
        tlText: b.tlText || '',
        tlDir: b.tlDir || 'v',
        mapText: b.mapText || '',
        dropCap: b.dropCap || false,
        showBorder: b.showBorder ?? false,
        borderColor: b.borderColor ?? '#000000',
        borderWidth: b.borderWidth ?? 1,
        borderRadius: b.borderRadius ?? 0,
      })),
    };
  });

  const data = { v: 3, pages: pagesData };

  let html = '<div class="magazine-pages" data-page-count="' + pagesData.length + '">';
  pagesData.forEach((page, pi) => {
    const { cw: cW, ch: cH, blocks: pBlocks } = page;
    const ratio = (cH / cW * 100).toFixed(3);
    html += `<div class="magazine-page" data-page="${pi}">`;
    html += `<div class="magazine-layout" style="position:relative;width:100%;padding-bottom:${ratio}%;overflow:hidden;">`;
    html += `<div style="position:absolute;top:0;left:0;width:100%;height:100%;">`;
    pBlocks.forEach(b => {
      const L = (b.x / cW * 100).toFixed(3);
      const T = (b.y / cH * 100).toFixed(3);
      const W = (b.w / cW * 100).toFixed(3);
      const H = (b.h / cH * 100).toFixed(3);
      const br = b.showBorder ? (b.borderRadius >= 9999 ? '9999px' : `${b.borderRadius ?? 0}px`) : '';
      const border = b.showBorder ? `border:${b.borderWidth ?? 1}px solid ${b.borderColor ?? '#000000'};border-radius:${br};` : '';
      const s = `position:absolute;left:${L}%;top:${T}%;width:${W}%;height:${H}%;overflow:hidden;box-sizing:border-box;${border}`;
      if (b.type === 'image' && b.src) {
        const ox = (b.imgOffsetX ?? 50).toFixed(1), oy = (b.imgOffsetY ?? 50).toFixed(1);
        const fc = b.imgFilter && b.imgFilter !== 'none' ? ` class="mag-filter-${b.imgFilter}"` : '';
        html += `<div style="${s}"><img${fc} src="${b.src}" style="width:100%;height:100%;object-fit:cover;object-position:${ox}% ${oy}%;display:block;"></div>`;
      } else if (b.type === 'spacer') {
        html += `<div style="${s}"></div>`;
      } else {
        html += `<div${b.dropCap ? ' class="mag-dropcap"' : ''} style="${s}">${b.content}</div>`;
      }
    });
    html += '</div></div></div>';
  });
  html += '</div>';

  return { blocksJson: JSON.stringify(data), html };
}

// ── Spell Check ───────────────────────────────────────────
let _scState = { editor: null, from: 0, to: 0 };
let _scEnVariant = 'vennify'; // 글로벌 팝업 모델 선택 상태

/**
 * Escape &, < and > for spell-check messages.
 *
 * @param {string} text - Raw text.
 * @returns {string} HTML-safe text.
 */
function _scEscapeHtml(text) {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

/**
 * Word-level diff of one line or sentence (LCS over words and spaces).
 *
 * Very long inputs (over 400 tokens) are shown as one inserted span instead.
 *
 * @param {string} orig - Original text.
 * @param {string} corr - Corrected text.
 * @returns {{html: string, changes: number}} Diff HTML (deleted and inserted spans)
 *   and the number of changed runs.
 */
function _scWordDiff(orig, corr) {
  // 단일 줄(문자열) 내 word-level LCS diff → { html, changes }
  /**
   * Escape &, < and > for the diff output.
   *
   * @param {string} s - Raw text.
   * @returns {string} HTML-safe text.
   */
  const esc = s => s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  /**
   * Split text into word and whitespace tokens.
   *
   * @param {string} s - Text.
   * @returns {string[]} Tokens (empty for empty text).
   */
  const tok = s => s.match(/\S+|\s+/g) || [];
  const a = tok(orig), b = tok(corr);
  if (a.length > 400 || b.length > 400) {
    return { html: `<span style="background:#dcfce7;color:#166534;border-radius:2px;padding:0 1px;">${esc(corr)}</span>`, changes: 1 };
  }
  const m = a.length, n = b.length;
  const dp = Array.from({ length: m + 1 }, () => new Int16Array(n + 1));
  for (let i = 1; i <= m; i++)
    for (let j = 1; j <= n; j++)
      dp[i][j] = a[i-1] === b[j-1] ? dp[i-1][j-1] + 1 : Math.max(dp[i-1][j], dp[i][j-1]);
  const ops = []; let i = m, j = n;
  while (i > 0 || j > 0) {
    if (i > 0 && j > 0 && a[i-1] === b[j-1]) { ops.push([0, a[i-1]]); i--; j--; }
    else if (j > 0 && (i === 0 || dp[i][j-1] >= dp[i-1][j])) { ops.push([1, b[j-1]]); j--; }
    else { ops.push([-1, a[i-1]]); i--; }
  }
  ops.reverse();
  let html = '', changes = 0, k = 0;
  while (k < ops.length) {
    if (ops[k][0] === 0) { html += esc(ops[k][1]); k++; continue; }
    let dels = [], ins = [];
    while (k < ops.length && ops[k][0] !== 0) {
      (ops[k][0] === -1 ? dels : ins).push(ops[k][1]); k++;
    }
    changes++;
    if (dels.length) html += `<span style="background:#fee2e2;color:#b91c1c;text-decoration:line-through;border-radius:2px;padding:0 1px;">${esc(dels.join(''))}</span>`;
    if (ins.length)  html += `<span style="background:#dcfce7;color:#166534;border-radius:2px;padding:0 1px;">${esc(ins.join(''))}</span>`;
  }
  return { html, changes };
}

/**
 * Diff two texts line by line, then sentence by sentence, then word by word.
 *
 * Lines only in the correction are shown as inserted, lines only in the original
 * as deleted.
 *
 * @param {string} orig - Original text.
 * @param {string} corr - Corrected text.
 * @returns {{html: string, changes: number}} Diff HTML with <br> between lines and
 *   the total number of changes.
 */
function _scDiffHtml(orig, corr) {
  // 항상 줄(\n) 단위로 처리 — _scWordDiff(orig, corr) 전체 텍스트 호출 절대 없음
  // 줄 수가 달라도 zip으로 처리 (추가된 줄 → 초록, 삭제된 줄 → 빨강)
  /**
   * Escape &, < and > for the diff output.
   *
   * @param {string} s - Raw text.
   * @returns {string} HTML-safe text.
   */
  const esc = s => s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  const DEL = 'background:#fee2e2;color:#b91c1c;text-decoration:line-through;border-radius:2px;padding:0 1px;';
  const INS = 'background:#dcfce7;color:#166534;border-radius:2px;padding:0 1px;';

  const origLines = orig.split('\n');
  const corrLines = corr.split('\n');
  const maxLen = Math.max(origLines.length, corrLines.length);

  let totalChanges = 0;
  const parts = [];

  for (let li = 0; li < maxLen; li++) {
    if (li > 0) parts.push('<br>');

    const hasO = li < origLines.length;
    const hasC = li < corrLines.length;
    const oLine = hasO ? origLines[li] : '';
    const cLine = hasC ? corrLines[li] : '';

    if (!hasO) {
      // 교정본에만 있는 줄 (추가)
      totalChanges++;
      parts.push(`<span style="${INS}">${esc(cLine)}</span>`);
    } else if (!hasC) {
      // 원본에만 있는 줄 (삭제)
      totalChanges++;
      parts.push(`<span style="${DEL}">${esc(oLine)}</span>`);
    } else if (oLine === cLine) {
      // 변경 없음
      parts.push(esc(oLine));
    } else {
      // 변경 있음: 줄 내부에서 마침표(. ! ? 。) 기준으로 문장 분리 후 word diff
      // 마침표 뒤 공백이 있을 때만 분리 (소수점 3.14 등 제외)
      const oSents = oLine.split(/(?<=[.!?。])\s+/).filter(Boolean);
      const cSents = cLine.split(/(?<=[.!?。])\s+/).filter(Boolean);

      if (oSents.length === cSents.length && oSents.length > 1) {
        // 문장 단위로 쪼개서 각 문장 내에서만 word diff
        const sentParts = [];
        for (let si = 0; si < oSents.length; si++) {
          if (si > 0) sentParts.push(' ');
          if (oSents[si] === cSents[si]) {
            sentParts.push(esc(oSents[si]));
          } else {
            const r = _scWordDiff(oSents[si], cSents[si]);
            totalChanges += r.changes;
            sentParts.push(r.html);
          }
        }
        parts.push(sentParts.join(''));
      } else {
        // 단일 문장 줄: 줄 전체 word diff
        const r = _scWordDiff(oLine, cLine);
        totalChanges += r.changes;
        parts.push(r.html);
      }
    }
  }

  return { html: parts.join(''), changes: totalChanges };
}

/**
 * Legend shown under a diff: change count plus deleted / added samples.
 *
 * @param {number} changes - Number of changes.
 * @returns {string} Legend HTML.
 */
function _scDiffLegend(changes) {
  return `<div style="margin-top:10px;padding-top:8px;border-top:1px solid #e2e8f0;display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
    <span style="font-size:0.69rem;color:#94a3b8;flex:1;font-weight:500;">${changes}개 수정됨</span>
    <span style="background:#fee2e2;color:#b91c1c;border-radius:3px;padding:1px 7px;font-size:0.68rem;font-weight:500;text-decoration:line-through;">삭제</span>
    <span style="background:#dcfce7;color:#166534;border-radius:3px;padding:1px 7px;font-size:0.68rem;font-weight:500;">추가</span>
  </div>`;
}

// 애니메이션 CSS 즉시 주입
;(function() {
  if (document.getElementById('sc-spin-style')) return;
  const s = document.createElement('style'); s.id = 'sc-spin-style';
  s.textContent = '@keyframes spin{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}@keyframes scShimmer{from{background-position:200% 0}to{background-position:-200% 0}}';
  (document.head || document.documentElement).appendChild(s);
})();

/**
 * Put a spell-check run button into its busy state (spinner, disabled).
 *
 * @param {HTMLButtonElement} btn - Run button.
 * @returns {void}
 */
function _scBtnLoad(btn) {
  btn.disabled = true;
  btn.innerHTML = '<span style="display:inline-block;width:15px;height:15px;border:2.5px solid rgba(255,255,255,0.35);border-top-color:#fff;border-radius:50%;animation:spin 0.65s linear infinite;vertical-align:middle;margin-right:8px;"></span>검사 중...';
  btn.classList.add('sc-btn-busy');
}
/**
 * Re-enable a spell-check run button and label it "다시 검사".
 *
 * @param {HTMLButtonElement} btn - Run button.
 * @returns {void}
 */
function _scBtnReady(btn) {
  btn.disabled = false;
  btn.textContent = '다시 검사';
  btn.classList.remove('sc-btn-busy');
}

// 결과 영역 상태 클래스 (tiptap-editor.css)
const SC_RESULT_STATES = ['initial', 'loading', 'same', 'diff', 'error'];
const SC_PANEL_TONES = ['muted', 'error'];

/**
 * Switch an element to one of several mutually exclusive state classes.
 *
 * @param {HTMLElement} el - Element whose look depends on the state.
 * @param {string} prefix - Class prefix, e.g. "sc-modal-result-".
 * @param {string[]} states - Every state name that uses the prefix.
 * @param {?string} state - State to turn on; null turns them all off.
 * @returns {void}
 */
function _scSetState(el, prefix, states, state) {
  states.forEach(s => el.classList.toggle(prefix + s, s === state));
}

const _scSpinnerBtn = '';

/**
 * Placeholder shown while the spell checker runs (four shimmering bars).
 *
 * @returns {string} Skeleton HTML.
 */
function _scLoadingHtml() {
  /**
   * One shimmering skeleton bar.
   *
   * @param {number} w - Width in percent.
   * @param {number} d - Animation delay in seconds.
   * @returns {string} Bar HTML.
   */
  const bar = (w, d) => `<div style="height:13px;background:linear-gradient(90deg,#e2e8f0 25%,#f8fafc 50%,#e2e8f0 75%);background-size:200% 100%;animation:scShimmer 1.4s ease-in-out infinite;animation-delay:${d}s;border-radius:4px;width:${w}%;"></div>`;
  return `<div style="display:flex;flex-direction:column;gap:10px;padding:2px 0;">${bar(88,0)}${bar(73,0.15)}${bar(81,0.3)}${bar(65,0.45)}</div>`;
}

/**
 * Find the text selection to spell-check.
 *
 * Looks for the block whose editor has a non-empty selection (the selection
 * survives the editor losing focus to the toolbar button).
 *
 * @returns {?{editor: Editor, text: string, from: number, to: number}} The
 *   selection, with paragraphs joined by "\n", or null when nothing is selected.
 */
function _scGetTarget() {
  // isFocused 대신 selection 상태로 탐지 (버튼 클릭 시 포커스 잃어도 selection은 유지됨)
  const blockWithSel = blocks.find(b => {
    if (!b.editor) return false;
    const { from, to } = b.editor.state.selection;
    return from !== to;
  });
  if (!blockWithSel?.editor) return null;
  const editor = blockWithSel.editor;
  const { from, to } = editor.state.selection;
  // '\n' 으로 단락 경계를 보존 — ' ' 이면 모든 줄이 한 문장으로 합쳐짐
  const text = editor.state.doc.textBetween(from, to, '\n');
  return { editor, text, from, to };
}

/**
 * Close the spell-check dialog and its overlay.
 *
 * @returns {void}
 */
function _scRemovePopup() {
  document.getElementById('sc-overlay')?.remove();
  document.getElementById('sc-popup')?.remove();
}

/**
 * Replace the checked selection with the corrected text (one paragraph per line).
 *
 * @param {string} correctedText - Text returned by the spell checker.
 * @returns {void}
 */
function _scApply(correctedText) {
  const { editor, from, to } = _scState;
  if (!editor) return;
  // \n 이 포함된 경우 줄별로 paragraph 노드로 분리해서 삽입
  const lines = correctedText.split('\n');
  const content = lines.map(line => ({
    type: 'paragraph',
    content: line ? [{ type: 'text', text: line }] : [],
  }));
  editor.chain().focus().deleteRange({ from, to }).insertContentAt(from, content).run();
  _scRemovePopup();
}

/**
 * Open the selection spell-check dialog (overlay + compact card).
 *
 * With `error` the dialog only shows the message and a close button. Otherwise it
 * shows the model buttons, the selected text, a result area and the
 * close / run / apply buttons; running posts the text to /api/spellcheck and
 * shows a word-level diff that "적용하기" writes back over the selection.
 * Escape and the overlay dismiss it.
 *
 * @param {Object} opts - Dialog options.
 * @param {boolean} [opts.selectModel] - Show the model chooser (always true when no error).
 * @param {string} [opts.original] - Selected text to check.
 * @param {string} [opts.error] - Message to show instead of the checker.
 * @returns {void}
 */
function _scShowPopup({ selectModel, original, error }) {
  _scRemovePopup();

  const overlay = document.createElement('div');
  overlay.id = 'sc-overlay';
  overlay.className = 'sc-dlg-overlay';
  overlay.addEventListener('click', _scRemovePopup);

  const popup = document.createElement('div');
  popup.id = 'sc-popup';
  popup.className = 'sc-dlg';
  popup.addEventListener('click', e => e.stopPropagation());

  if (error) {
    popup.innerHTML = `<div style="font-weight:600;margin-bottom:12px;">맞춤법 검사</div>
      <div style="color:#ef4444;font-size:0.9rem;margin-bottom:16px;">${_scEscapeHtml(error)}</div>`;
    const btn = document.createElement('button');
    btn.type = 'button'; btn.textContent = '닫기';
    btn.className = 'sc-dlg-cancel sc-dlg-close';
    btn.addEventListener('click', _scRemovePopup);
    popup.appendChild(btn);
  } else {
    popup.innerHTML = `<div style="font-weight:600;margin-bottom:14px;">맞춤법 검사</div>`;

    const modelRow = document.createElement('div');
    modelRow.className = 'sc-dlg-models';
    const modelLabel = document.createElement('span');
    modelLabel.className = 'sc-dlg-models-label';
    modelLabel.textContent = '모델:';
    modelRow.appendChild(modelLabel);

    const variantBtns = {};
    ['vennify', 'coedit'].forEach(v => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.textContent = v === 'vennify' ? '빠름' : '고품질';
      btn.title = v === 'vennify' ? 'vennify/t5-base-grammar-correction' : 'grammarly/coedit-large';
      btn.className = 'sc-dlg-model' + (v === _scEnVariant ? ' sc-dlg-model-active' : '');
      btn.addEventListener('click', e => {
        e.stopPropagation();
        _scEnVariant = v;
        Object.entries(variantBtns).forEach(([key, b]) => { b.classList.toggle('sc-dlg-model-active', key === v); });
      });
      variantBtns[v] = btn;
      modelRow.appendChild(btn);
    });
    popup.appendChild(modelRow);

    const previewBox = document.createElement('div');
    previewBox.className = 'sc-dlg-text';
    previewBox.textContent = original;
    popup.appendChild(previewBox);

    const resultArea = document.createElement('div');
    resultArea.className = 'sc-dlg-result-area';
    resultArea.hidden = true;
    resultArea.innerHTML = `
      <div style="font-size:0.75rem;color:#9ca3af;margin-bottom:4px;">교정 결과</div>
      <div class="sc-result-box sc-dlg-result sc-dlg-result-initial"></div>`;
    popup.appendChild(resultArea);

    const actions = document.createElement('div');
    actions.className = 'sc-dlg-actions';

    const cancelBtn = document.createElement('button');
    cancelBtn.type = 'button'; cancelBtn.textContent = '닫기';
    cancelBtn.className = 'sc-dlg-cancel';
    cancelBtn.addEventListener('click', _scRemovePopup);

    const runBtn = document.createElement('button');
    runBtn.type = 'button'; runBtn.textContent = '검사 시작';
    runBtn.className = 'sc-dlg-run';

    const applyBtn = document.createElement('button');
    applyBtn.type = 'button'; applyBtn.textContent = '적용하기';
    applyBtn.className = 'sc-dlg-apply';
    applyBtn.hidden = true;

    actions.appendChild(cancelBtn);
    actions.appendChild(runBtn);
    actions.appendChild(applyBtn);
    popup.appendChild(actions);

    runBtn.addEventListener('click', async e => {
      e.stopPropagation();
      _scBtnLoad(runBtn);
      applyBtn.hidden = true;
      // 로딩 shimmer 즉시 표시
      const resultBox = resultArea.querySelector('.sc-result-box');
      resultArea.hidden = false;
      _scSetState(resultBox, 'sc-dlg-result-', SC_RESULT_STATES, 'loading');
      resultBox.innerHTML = _scLoadingHtml();
      const _scCtrl = new AbortController();
      const _scTimer = setTimeout(() => _scCtrl.abort(), 150000);
      try {
        const res = await fetch('/api/spellcheck', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text: original, en_variant: _scEnVariant, ko_variant: 'et5' }),
          signal: _scCtrl.signal,
        });
        if (!res.ok) { const err = await res.json().catch(() => ({})); throw new Error(err.detail || `서버 오류 (${res.status})`); }
        const data = await res.json();
        const corrected = data.corrected;
        const isSame = original === corrected;
        resultArea.hidden = false;
        if (isSame) {
          _scSetState(resultBox, 'sc-dlg-result-', SC_RESULT_STATES, 'same');
          resultBox.innerHTML = '<i class="bi bi-check-circle-fill" style="color:#10b981;margin-right:6px;"></i>오류가 발견되지 않았습니다.';
        } else {
          _scSetState(resultBox, 'sc-dlg-result-', SC_RESULT_STATES, 'diff');
          const diff = _scDiffHtml(original, corrected);
          resultBox.innerHTML = diff.html + _scDiffLegend(diff.changes);
          applyBtn.hidden = false;
          applyBtn.onclick = () => { _scApply(corrected); };
        }
      } catch (err) {
        resultArea.hidden = false;
        _scSetState(resultBox, 'sc-dlg-result-', SC_RESULT_STATES, 'error');
        const msg = err.name === 'AbortError' ? '요청 시간 초과 (2분 30초). 모델 로딩 중이면 잠시 후 다시 시도해주세요.' : (err.message || '오류가 발생했습니다.');
        resultBox.innerHTML = `<i class="bi bi-exclamation-circle-fill" style="margin-right:6px;"></i>${msg}`;
      } finally {
        clearTimeout(_scTimer);
        _scBtnReady(runBtn);
      }
    });
  }

  document.body.appendChild(overlay);
  document.body.appendChild(popup);

  if (!document.getElementById('sc-spin-style')) {
    const s = document.createElement('style');
    s.id = 'sc-spin-style';
    s.textContent = '@keyframes spin{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}@keyframes scShimmer{from{background-position:200% 0}to{background-position:-200% 0}}';
    document.head.appendChild(s);
  }

  /**
   * Close the dialog on Escape and stop listening.
   *
   * @param {KeyboardEvent} e - keydown event.
   * @returns {void}
   */
  const onEsc = e => { if (e.key === 'Escape') { _scRemovePopup(); document.removeEventListener('keydown', onEsc); } };
  document.addEventListener('keydown', onEsc);
}

/**
 * Spell-check the selected text (toolbar button or Ctrl+Shift+S).
 *
 * Shows the model chooser for the selection, or an error dialog when no text is
 * selected.
 *
 * @returns {void}
 */
function triggerSpellCheck() {
  const target = _scGetTarget();
  if (!target) {
    _scShowPopup({ error: '텍스트 블록에서 검사할 텍스트를 드래그로 선택한 후 실행하세요.' });
    return;
  }
  _scState = { editor: target.editor, from: target.from, to: target.to };
  _scShowPopup({ selectModel: true, original: target.text });
}

// ── Block-level spell preview (split panel) ───────────────
/**
 * Open the spell-check side panel of a text block.
 *
 * Splits the block body into the editor (left) and a panel (right) with a model
 * choice, a run button and the result; a diff result offers "적용하기", which
 * replaces the whole block text and closes the panel.
 *
 * @param {string} blockId - Text block id.
 * @returns {void}
 */
function _scBlockPreviewOpen(blockId) {
  const block = blocks.find(b => b.id === blockId);
  if (!block || !block.editor) return;
  const el = document.querySelector(`[data-bid="${blockId}"]`);
  if (!el) return;

  _scSplitActive.add(blockId);
  el.querySelector('.fb-sc-preview-btn')?.classList.add('fb-btn-active');

  // Split body into two panes
  const body = el.querySelector('.fb-body');
  body.classList.add('fb-body-split');
  const edEl = body.querySelector('.fb-editor');
  edEl.classList.add('fb-editor-split');

  // ── 패널 ─────────────────────────────────────────────────
  const panel = document.createElement('div');
  panel.className = 'fb-spell-preview sc-panel';

  // 헤더
  const panelHdr = document.createElement('div');
  panelHdr.className = 'sc-panel-hdr';
  panelHdr.innerHTML = `<i class="bi bi-spell-check" style="color:#6366f1;font-size:0.9rem;"></i>
    <span style="font-size:0.78rem;font-weight:700;color:#334155;letter-spacing:-0.2px;flex:1;">맞춤법 미리보기</span>`;
  const closeBtn = document.createElement('button');
  closeBtn.type = 'button'; closeBtn.innerHTML = '<i class="bi bi-x"></i>';
  closeBtn.className = 'sc-panel-x';
  closeBtn.addEventListener('click', e => { e.stopPropagation(); _scBlockPreviewClose(blockId); });
  panelHdr.appendChild(closeBtn);
  panel.appendChild(panelHdr);

  // 모델 선택
  let selectedVariant = 'vennify';
  const modelSection = document.createElement('div');
  modelSection.className = 'sc-panel-model';
  const modelTopLabel = document.createElement('div');
  modelTopLabel.className = 'sc-panel-label';
  modelTopLabel.textContent = '모델 선택';
  modelSection.appendChild(modelTopLabel);

  const modelGrid = document.createElement('div');
  modelGrid.className = 'sc-panel-models';
  const variantBtns = {};
  [{ v: 'vennify', label: '빠름', sub: 'KO: et5 · EN: T5-base' }, { v: 'coedit', label: '고품질', sub: 'KO: et5 · EN: CoEdIT' }].forEach(({ v, label, sub }) => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'sc-panel-variant' + (v === 'vennify' ? ' sc-panel-variant-active' : '');
    btn.innerHTML = `<div style="font-size:0.8rem;font-weight:600;margin-bottom:1px;">${label}</div><div style="font-size:0.67rem;opacity:0.7;">${sub}</div>`;
    btn.addEventListener('click', e => {
      e.stopPropagation(); selectedVariant = v;
      Object.entries(variantBtns).forEach(([key, b]) => { b.classList.toggle('sc-panel-variant-active', key === v); });
    });
    variantBtns[v] = btn; modelGrid.appendChild(btn);
  });
  modelSection.appendChild(modelGrid);

  // 검사 시작 버튼
  const runBtn = document.createElement('button');
  runBtn.type = 'button'; runBtn.textContent = '검사 시작';
  runBtn.className = 'sc-panel-run';
  modelSection.appendChild(runBtn);
  panel.appendChild(modelSection);

  // 결과 영역
  const content = document.createElement('div');
  content.className = 'fb-spell-preview-text sc-panel-result sc-panel-result-muted';
  content.textContent = '모델을 선택하고 검사 시작을 눌러주세요.';
  panel.appendChild(content);

  body.appendChild(panel);

  // 검사 실행
  runBtn.addEventListener('click', async e => {
    e.stopPropagation();
    const fullText = block.editor.state.doc.textBetween(0, block.editor.state.doc.content.size, '\n');
    if (!fullText.trim()) { _scSetState(content, 'sc-panel-result-', SC_PANEL_TONES, 'muted'); content.textContent = '내용이 없습니다.'; return; }

    _scBtnLoad(runBtn);
    panel.querySelector('.fb-spell-apply-btn')?.remove();
    _scSetState(content, 'sc-panel-result-', SC_PANEL_TONES, null);
    content.innerHTML = _scLoadingHtml();

    const _scCtrl2 = new AbortController();
    const _scTimer2 = setTimeout(() => _scCtrl2.abort(), 150000);
    try {
      const res = await fetch('/api/spellcheck', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: fullText, en_variant: selectedVariant, ko_variant: 'et5' }),
        signal: _scCtrl2.signal,
      });
      if (!res.ok) { const err = await res.json().catch(() => ({})); throw new Error(err.detail || `서버 오류 (${res.status})`); }
      const data = await res.json();
      const corrected = data.corrected;
      const isSame = fullText === corrected;
      if (isSame) {
        _scSetState(content, 'sc-panel-result-', SC_PANEL_TONES, 'muted');
        content.innerHTML = '<i class="bi bi-check-circle-fill" style="color:#10b981;margin-right:6px;"></i>오류가 발견되지 않았습니다.';
      } else {
        _scSetState(content, 'sc-panel-result-', SC_PANEL_TONES, null);
        const diff = _scDiffHtml(fullText, corrected);
        content.innerHTML = diff.html + _scDiffLegend(diff.changes);
        const applyBtn = document.createElement('button');
        applyBtn.type = 'button'; applyBtn.textContent = '적용하기';
        applyBtn.className = 'fb-spell-apply-btn sc-panel-apply';
        applyBtn.addEventListener('click', () => {
          const lines = corrected.split('\n');
          const nodes = lines.map(line => ({ type: 'paragraph', content: line ? [{ type: 'text', text: line }] : [] }));
          block.editor.commands.setContent(nodes);
          _scBlockPreviewClose(blockId);
        });
        panel.appendChild(applyBtn);
      }
    } catch (err) {
      _scSetState(content, 'sc-panel-result-', SC_PANEL_TONES, 'error');
      const msg = err.name === 'AbortError' ? '요청 시간 초과 (2분 30초). 모델 로딩 중이면 잠시 후 다시 시도해주세요.' : (err.message || '오류가 발생했습니다.');
      content.innerHTML = `<i class="bi bi-exclamation-circle-fill" style="margin-right:6px;"></i>${msg}`;
    } finally {
      clearTimeout(_scTimer2);
      _scBtnReady(runBtn);
    }
  });
}

/**
 * Close a block's spell-check panel and restore the full-width editor.
 *
 * @param {string} blockId - Text block id.
 * @returns {void}
 */
function _scBlockPreviewClose(blockId) {
  _scSplitActive.delete(blockId);
  const el = document.querySelector(`[data-bid="${blockId}"]`);
  if (!el) return;
  el.querySelector('.fb-sc-preview-btn')?.classList.remove('fb-btn-active');
  el.querySelector('.fb-spell-preview')?.remove();
  const body = el.querySelector('.fb-body');
  if (body) { body.classList.remove('fb-body-split'); }
  const edEl = el.querySelector('.fb-editor');
  if (edEl) { edEl.classList.remove('fb-editor-split'); }
}

/**
 * Open or close a block's spell-check panel.
 *
 * @param {string} blockId - Text block id.
 * @returns {void}
 */
function _scBlockPreviewToggle(blockId) {
  _scSplitActive.has(blockId) ? _scBlockPreviewClose(blockId) : _scBlockPreviewOpen(blockId);
}

// ── Toolbar ───────────────────────────────────────────────
/**
 * Add the editor buttons to #tiptap-toolbar: undo/redo, column grid, one
 * button per block type or preset (kicker, lead, pull quote, divider, caption,
 * timeline, map, spacer) and spell check.
 *
 * @returns {void}
 */
function buildToolbar() {
  const tb = document.getElementById('tiptap-toolbar');
  if (!tb) return;
  [
    { id: 'fb-undo-btn', icon: '<i class="bi bi-arrow-counterclockwise"></i>', tip: '실행취소 (Ctrl+Z)', fn: () => undoAction() },
    { id: 'fb-redo-btn', icon: '<i class="bi bi-arrow-clockwise"></i>', tip: '다시실행 (Ctrl+Shift+Z)', fn: () => redoAction() },
    { id: 'fb-grid-btn', icon: '<i class="bi bi-layout-three-columns"></i>', tip: '칼럼 그리드 (12단 정렬 가이드)', fn: () => toggleGrid() },
    { icon: '<i class="bi bi-fonts"></i>', tip: 'Text block', fn: () => addBlock('text') },
    { icon: '<i class="bi bi-type-h1"></i>', tip: 'Heading block', fn: () => addBlock('heading') },
    { icon: '<i class="bi bi-image"></i>', tip: 'Image block', fn: () => addBlock('image') },
    { icon: '<i class="bi bi-code-slash"></i>', tip: 'Code block', fn: () => addBlock('code') },
    { icon: '<span style="font-size:0.66rem;font-weight:700;letter-spacing:1px;">Aa</span>', tip: '키커 (Kicker)', fn: () => addBlock('text', { content: '<p><span style="font-size:15px;letter-spacing:3px;text-transform:uppercase;color:#b4542f">FEATURE</span></p>', h: 40 }) },
    { icon: '<i class="bi bi-type-h2"></i>', tip: '리드 (Lead)', fn: () => addBlock('text', { content: '<p><span style="font-size:24px;color:#4c4239">리드 문장 — 기사의 핵심을 한두 문장으로.</span></p>', h: 100 }) },
    { icon: '<i class="bi bi-quote"></i>', tip: '인용구 (Pull quote)', fn: () => addBlock('text', { content: '<p><em><span style="font-size:30px;color:#b4542f">“인상적인 한 문장을 인용구로.”</span></em></p>', h: 130 }) },
    { icon: '<i class="bi bi-dash-lg"></i>', tip: '구분선 (Divider)', fn: () => addBlock('text', { content: '<hr>', h: 30 }) },
    { icon: '<i class="bi bi-card-text"></i>', tip: '캡션 (Caption)', fn: () => addBlock('text', { content: '<p><span style="font-size:14px;color:#8a7c6d">사진 캡션을 입력하세요</span></p>', h: 40 }) },
    { icon: '<i class="bi bi-signpost-2"></i>', tip: '타임라인 (여행 일정)', fn: () => { const s = '# 첫째 날\n왕궁:09:00\n점심:12:30\n카페:15:00\n호텔 복귀:22:00'; addBlock('timeline', { tlText: s, content: renderTimelineHTML(s), w: 460, h: 340 }); } },
    { icon: '<i class="bi bi-geo-alt"></i>', tip: '지도 (여행 장소)', fn: () => { const s = '왕궁@13.7500,100.4914\n왓 포@13.7465,100.4927\n왓 아룬@13.7437,100.4889'; addBlock('map', { mapText: s, content: renderMapHTML(s), w: 520, h: 380 }); } },
    { icon: '<i class="bi bi-arrows-expand"></i>', tip: 'Spacer', fn: () => addBlock('spacer', { h: 60 }) },
    { icon: '<span style="font-size:0.72rem;font-weight:700;letter-spacing:-0.5px;">맞춤법</span>', tip: '맞춤법 검사 (Ctrl+Shift+S)', fn: () => triggerSpellCheck(), wide: true },
  ].forEach(({ icon, tip, fn, wide, id }) => {
    const btn = document.createElement('button');
    btn.type = 'button'; btn.className = 'tiptap-toolbar-btn';
    if (id) btn.id = id;
    if (wide) btn.classList.add('tiptap-toolbar-btn-wide');
    btn.innerHTML = icon; btn.title = tip;
    btn.addEventListener('click', fn);
    tb.appendChild(btn);
  });
}

// ── Load blocks from saved data ───────────────────────────
/**
 * Load a saved layout into the editor.
 *
 * Accepts the v3 multi-page format, the v2 single-page format and the legacy
 * block array. Horizontal positions and widths are scaled from the saved canvas
 * width to the current one.
 *
 * @param {*} raw - Parsed content_blocks JSON.
 * @returns {boolean} True when blocks were loaded.
 */
function loadSavedData(raw) {
  const currentCW = canvasW();

  if (raw && raw.v === 3 && Array.isArray(raw.pages) && raw.pages.length) {
    // v3 multi-page format
    // Replace initial page with saved pages
    pages.splice(0, pages.length);
    raw.pages.forEach((savedPage, pi) => {
      const scale = savedPage.cw ? currentCW / savedPage.cw : 1;
      const page = { id: savedPage.id || uid(), blocks: [], cw: savedPage.cw, ch: savedPage.ch };
      pages.push(page);
      if (pi === 0) blocks = page.blocks; // point blocks ref to first page
      savedPage.blocks.forEach(b => {
        page.blocks.push({
          id: b.id || uid(), type: b.type,
          x: Math.round((b.x || 0) * scale), y: b.y || 0,
          w: Math.round((b.w || 200) * scale), h: b.h || 160,
          content: b.content || '', src: b.src || '',
          imgOffsetX: b.imgOffsetX ?? 50, imgOffsetY: b.imgOffsetY ?? 50,
          imgFilter: b.imgFilter || 'none', tlText: b.tlText || '', tlDir: b.tlDir || 'v', mapText: b.mapText || '', dropCap: b.dropCap || false,
          showBorder: b.showBorder ?? false,
          borderColor: b.borderColor ?? '#000000',
          borderWidth: b.borderWidth ?? 1,
          borderRadius: b.borderRadius ?? 0,
          editor: null,
        });
      });
    });
    currentPageIdx = 0;
    blocks = pages[0].blocks;
    blocks.forEach(b => renderBlock(b));
    updateCanvasHeight();
    updatePageTabs();
    return true;

  } else if (raw && raw.v === 2 && Array.isArray(raw.blocks)) {
    // v2 single-page format
    const scale = raw.cw ? currentCW / raw.cw : 1;
    raw.blocks.forEach(b => {
      addBlock(b.type, {
        id: b.id, x: Math.round((b.x || 0) * scale), y: b.y || 0,
        w: Math.round((b.w || 200) * scale), h: b.h || 160,
        content: b.content || '', src: b.src || '',
        imgOffsetX: b.imgOffsetX ?? 50, imgOffsetY: b.imgOffsetY ?? 50,
        showBorder: b.showBorder ?? false,
        borderColor: b.borderColor ?? '#000000',
        borderWidth: b.borderWidth ?? 1,
        borderRadius: b.borderRadius ?? 0,
      });
    });
    updatePageTabs();
    return true;

  } else if (Array.isArray(raw) && raw.length) {
    // legacy array format
    raw.forEach(b => {
      addBlock(b.type, {
        id: b.id, x: b.x || 0, y: b.y || 0,
        w: b.w || 200, h: b.h || 160,
        content: b.content || '', src: b.src || '',
      });
    });
    updatePageTabs();
    return true;
  }
  return false;
}

// ── Undo / Redo (레이아웃 히스토리) + 자동저장 ───────────────
const _history = { past: [], future: [], last: null, max: 60 };
let _historyReady = false;
let _commitTimer = null, _asTimer = null, _suppressUntil = 0;

/**
 * Serialize all pages (and the current page index) for undo history and autosave.
 *
 * @returns {string} JSON snapshot.
 */
function snapshotState() {
  syncCurrentPage();
  return JSON.stringify({
    v: 3, page: currentPageIdx,
    pages: pages.map(p => ({
      id: p.id, cw: p.cw, ch: p.ch,
      blocks: p.blocks.map(b => ({
        id: b.id, type: b.type,
        x: Math.round(b.x), y: Math.round(b.y), w: Math.round(b.w), h: Math.round(b.h),
        content: (b.editor ? b.editor.getHTML() : b.content) || '', src: b.src || '',
        imgOffsetX: b.imgOffsetX ?? 50, imgOffsetY: b.imgOffsetY ?? 50,
        imgFilter: b.imgFilter || 'none',
        tlText: b.tlText || '',
        tlDir: b.tlDir || 'v',
        mapText: b.mapText || '',
        dropCap: b.dropCap || false,
        showBorder: b.showBorder ?? false, borderColor: b.borderColor ?? '#000000',
        borderWidth: b.borderWidth ?? 1, borderRadius: b.borderRadius ?? 0,
      })),
    })),
  });
}
/**
 * Replace all pages with a snapshot and re-render the current page.
 *
 * Invalid JSON is ignored.
 *
 * @param {string} json - Snapshot from snapshotState().
 * @returns {void}
 */
function _applySnapshot(json) {
  let data; try { data = JSON.parse(json); } catch { return; }
  clearCanvas();
  pages.splice(0, pages.length);
  (data.pages || []).forEach(sp => {
    pages.push({ id: sp.id || uid(), cw: sp.cw, ch: sp.ch, blocks: (sp.blocks || []).map(b => ({ ...b, editor: null })) });
  });
  if (!pages.length) pages.push({ id: uid(), blocks: [], cw: null, ch: null });
  currentPageIdx = Math.min(data.page || 0, pages.length - 1);
  blocks = pages[currentPageIdx].blocks;
  blocks.forEach(b => renderBlock(b));
  updateCanvasHeight();
  updatePageTabs();
}
/**
 * Record the current state as a new undo step when it changed.
 *
 * Skipped before history is ready and right after an undo/redo. Clears the redo
 * stack and schedules an autosave.
 *
 * @returns {void}
 */
function commitHistory() {
  if (!_historyReady || Date.now() < _suppressUntil) return;
  const snap = snapshotState();
  if (snap === _history.last) return;
  if (_history.last !== null) { _history.past.push(_history.last); if (_history.past.length > _history.max) _history.past.shift(); }
  _history.last = snap;
  _history.future = [];
  scheduleAutosave();
  updateUndoButtons();
}
/**
 * Debounce commitHistory() (250ms) after a mouse action.
 *
 * @returns {void}
 */
function scheduleCommit() { if (!_historyReady) return; clearTimeout(_commitTimer); _commitTimer = setTimeout(commitHistory, 250); }
/**
 * Step the layout back one history entry.
 *
 * @returns {void}
 */
function undoAction() {
  if (!_history.past.length) return;
  _suppressUntil = Date.now() + 500;
  _history.future.push(_history.last);
  _history.last = _history.past.pop();
  _applySnapshot(_history.last);
  scheduleAutosave();
  updateUndoButtons();
}
/**
 * Re-apply the history entry that was last undone.
 *
 * @returns {void}
 */
function redoAction() {
  if (!_history.future.length) return;
  _suppressUntil = Date.now() + 500;
  _history.past.push(_history.last);
  _history.last = _history.future.pop();
  _applySnapshot(_history.last);
  scheduleAutosave();
  updateUndoButtons();
}
/**
 * Enable or dim the undo/redo buttons for the current history.
 *
 * @returns {void}
 */
function updateUndoButtons() {
  const u = document.getElementById('fb-undo-btn'), r = document.getElementById('fb-redo-btn');
  if (u) { u.disabled = !_history.past.length; u.classList.toggle('tiptap-toolbar-btn-dim', !_history.past.length); }
  if (r) { r.disabled = !_history.future.length; r.classList.toggle('tiptap-toolbar-btn-dim', !_history.future.length); }
}
/**
 * localStorage key for this editor's autosave.
 *
 * @returns {string} "magazine:autosave:post-<id>", "…:draft-<id>" or "…:new".
 */
function _draftKey() {
  const pid = document.getElementById('block-canvas')?.dataset?.postId;
  const did = (typeof window !== 'undefined' && window.DRAFT_ID) ? window.DRAFT_ID : null;
  return 'magazine:autosave:' + (pid ? ('post-' + pid) : (did ? ('draft-' + did) : 'new'));
}
/**
 * Save the latest snapshot to localStorage after 1s (debounced).
 *
 * @returns {void}
 */
function scheduleAutosave() {
  clearTimeout(_asTimer);
  _asTimer = setTimeout(() => { try { localStorage.setItem(_draftKey(), JSON.stringify({ t: Date.now(), s: _history.last })); } catch {} }, 1000);
}
/**
 * Delete this editor's autosaved snapshot.
 *
 * @returns {void}
 */
function clearAutosave() { try { localStorage.removeItem(_draftKey()); } catch {} }
/**
 * Offer to restore an autosaved layout that differs from the loaded one.
 *
 * Shows a bar above the canvas with "복원" (apply the saved snapshot) and
 * "버리기" (delete it).
 *
 * @param {string} currentSnap - Snapshot of the freshly loaded state.
 * @returns {void}
 */
function maybeOfferRestore(currentSnap) {
  let saved; try { saved = JSON.parse(localStorage.getItem(_draftKey()) || 'null'); } catch { saved = null; }
  if (!saved || !saved.s || saved.s === currentSnap) return;
  const canvas = document.getElementById('block-canvas');
  const bar = document.createElement('div');
  bar.className = 'fb-restore-bar';
  const ago = new Date(saved.t || Date.now()).toLocaleString();
  bar.innerHTML = `<i class="bi bi-clock-history"></i><span style="flex:1">저장하지 않은 편집 내용이 있습니다 <span style="opacity:.7">(${ago})</span>. 이어서 편집할까요?</span>`;
  const yes = document.createElement('button'); yes.type = 'button'; yes.textContent = '복원'; yes.className = 'fb-restore-yes';
  const no = document.createElement('button'); no.type = 'button'; no.textContent = '버리기'; no.className = 'fb-restore-no';
  yes.onclick = () => { _applySnapshot(saved.s); _history.last = saved.s; _history.past = []; _history.future = []; updateUndoButtons(); bar.remove(); };
  no.onclick = () => { clearAutosave(); bar.remove(); };
  bar.appendChild(yes); bar.appendChild(no);
  canvas.parentElement.insertBefore(bar, canvas);
}
/**
 * Start undo history from the loaded state and check for an autosave.
 *
 * @returns {void}
 */
function initHistory() {
  _history.past = []; _history.future = [];
  _history.last = snapshotState();
  _historyReady = true;
  updateUndoButtons();
  maybeOfferRestore(_history.last);
}
/**
 * Tell whether keyboard focus is inside a TipTap editor.
 *
 * @returns {boolean} True when typing goes to a text editor (its own undo applies).
 */
function _inTextEditor() {
  const a = document.activeElement;
  return !!(a && (a.classList?.contains('ProseMirror') || a.closest?.('.ProseMirror')));
}

// ── Main ──────────────────────────────────────────────────
/**
 * Entry point: build the toolbar and page tabs, load the saved layout (or the
 * HTML fallback, or an empty heading and text block), then wire history,
 * keyboard shortcuts (undo/redo, Delete, Ctrl+Shift+S), image paste, the preview
 * button and the update form.
 *
 * @returns {void}
 */
function main() {
  const canvas = document.getElementById('block-canvas');
  if (!canvas) return;
  buildToolbar();
  updatePageTabs();

  let loaded = false;
  const blocksScript = document.getElementById('initial-blocks');
  if (blocksScript?.textContent?.trim()) {
    try { loaded = loadSavedData(JSON.parse(blocksScript.textContent)); } catch (e) { console.error(e); }
  }
  if (!loaded) {
    const contentScript = document.getElementById('initial-content');
    if (contentScript?.textContent?.trim()) {
      try {
        const html = JSON.parse(contentScript.textContent);
        if (html) { addBlock('text', { content: html, h: 400 }); loaded = true; }
      } catch {}
    }
  }
  if (!loaded) {
    addBlock('heading', { content: '<h1></h1>', h: 80 });
    addBlock('text', { h: 200 });
  }

  initHistory();
  document.addEventListener('mouseup', scheduleCommit);

  document.addEventListener('keydown', e => {
    const mod = e.ctrlKey || e.metaKey;
    // 실행취소/다시실행 — 텍스트 편집 중엔 TipTap 자체 히스토리에 양보
    if (mod && !e.shiftKey && e.key.toLowerCase() === 'z' && !_inTextEditor()) { e.preventDefault(); undoAction(); return; }
    if (mod && ((e.shiftKey && e.key.toLowerCase() === 'z') || e.key.toLowerCase() === 'y') && !_inTextEditor()) { e.preventDefault(); redoAction(); return; }
    if (e.key === 'Delete' && selectedId) {
      const b = blocks.find(b => b.id === selectedId);
      if (b && !b.editor?.isFocused) removeBlock(selectedId);
    }
    if (e.ctrlKey && e.shiftKey && e.key.toLowerCase() === 's') {
      e.preventDefault();
      triggerSpellCheck();
    }
  });
  document.addEventListener('paste', async e => {
    const file = e.clipboardData?.files?.[0];
    if (!file?.type.startsWith('image/')) return;
    e.preventDefault();
    try { addBlock('image', { src: await uploadImage(file) }); } catch {}
  });

  // Preview button in bottom bar
  const previewBtn = document.querySelector('.tiptap-bottom-bar .tiptap-btn-preview');
  if (previewBtn) previewBtn.addEventListener('click', togglePreview);

  const form = document.getElementById('post-form');
  if (!form) return;
  form.addEventListener('submit', e => {
    e.preventDefault();
    const { blocksJson, html } = collectData();
    document.getElementById('content').value = html;
    document.getElementById('content_html').value = html;
    document.getElementById('content_blocks').value = blocksJson;
    clearAutosave();
    form.submit();
  });
}

main();
