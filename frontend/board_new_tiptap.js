// frontend/board_new_tiptap.js — Multi-page free-position editor (new post)
import { Editor } from '@tiptap/core';
import StarterKit from '@tiptap/starter-kit';
import Placeholder from '@tiptap/extension-placeholder';
import TextAlign from '@tiptap/extension-text-align';
import Underline from '@tiptap/extension-underline';
import { TextStyle } from '@tiptap/extension-text-style';
import Color from '@tiptap/extension-color';
import Highlight from '@tiptap/extension-highlight';
import Image from '@tiptap/extension-image';

// ── Upload ────────────────────────────────────────────────
async function uploadImage(file) {
  const fd = new FormData();
  fd.append('file', file);
  if (window.DRAFT_ID) fd.append('draft_id', window.DRAFT_ID);
  const r = await fetch('/api/upload', { method: 'POST', body: fd });
  if (!r.ok) throw new Error('upload failed');
  return (await r.json()).url;
}

// ── State ─────────────────────────────────────────────────
let idCounter = 0;
const pages = [{ id: 'p1', blocks: [], cw: null, ch: null }];
let currentPageIdx = 0;
let blocks = pages[0].blocks; // always points to current page's blocks
let selectedId = null;
let dragInfo = null;
let resizeInfo = null;
let panInfo = null;
const _scSplitActive = new Set(); // block ids with spell-preview panel open

function uid() { return 'b' + (++idCounter); }

// ── TipTap editor factory ─────────────────────────────────
function createEditor(el, content) {
  return new Editor({
    element: el,
    extensions: [
      StarterKit,
      Placeholder.configure({ placeholder: 'Type here...' }),
      TextAlign.configure({ types: ['heading', 'paragraph'] }),
      Underline, TextStyle, Color,
      Highlight.configure({ multicolor: true }),
      Image.configure({ inline: false }),
    ],
    content: content || '<p></p>',
  });
}

// ── Canvas helpers ────────────────────────────────────────
function canvasW() { return document.getElementById('block-canvas').offsetWidth || 1; }

function updateCanvasHeight() {
  const canvas = document.getElementById('block-canvas');
  const max = blocks.reduce((m, b) => Math.max(m, b.y + b.h + 100), 600);
  canvas.style.minHeight = max + 'px';
}

// ── Page management ───────────────────────────────────────
function syncCurrentPage() {
  blocks.forEach(b => { if (b.editor) b.content = b.editor.getHTML(); });
  const cW = canvasW();
  const cH = Math.max(blocks.reduce((m, b) => Math.max(m, b.y + b.h), 0) + 40, 400);
  pages[currentPageIdx].cw = cW;
  pages[currentPageIdx].ch = cH;
}

function clearCanvas() {
  blocks.forEach(b => { if (b.editor) { b.editor.destroy(); b.editor = null; } });
  document.querySelectorAll('#block-canvas .fb').forEach(el => el.remove());
  document.getElementById('block-canvas').style.minHeight = '600px';
  selectedId = null;
}

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

function deletePage(idx) {
  if (pages.length === 1) return; // keep at least 1 page
  clearCanvas();
  pages.splice(idx, 1);
  currentPageIdx = Math.min(idx, pages.length - 1);
  blocks = pages[currentPageIdx].blocks;
  blocks.forEach(b => renderBlock(b));
  updateCanvasHeight();
  updatePageTabs();
}

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

    // Delete button (only if >1 page)
    if (pages.length > 1) {
      const del = document.createElement('span');
      del.className = 'page-tab-del';
      del.innerHTML = '×';
      del.title = 'Delete page';
      del.addEventListener('click', (e) => { e.stopPropagation(); deletePage(i); });
      tab.appendChild(del);
    }
    tabBar.appendChild(tab);
  });

  const addBtn = document.createElement('button');
  addBtn.type = 'button';
  addBtn.className = 'page-tab-add';
  addBtn.textContent = '+ Page';
  addBtn.title = 'Add page';
  addBtn.addEventListener('click', addPage);
  tabBar.appendChild(addBtn);
}

// ── Add / Remove blocks ───────────────────────────────────
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

function nextY() {
  if (!blocks.length) return 20;
  return blocks.reduce((m, b) => Math.max(m, b.y + b.h), 0) + 20;
}

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

// ── Image auto-fit ────────────────────────────────────────
function fitBlockToImage(block, imgEl) {
  const doFit = () => {
    if (!imgEl.naturalWidth || !imgEl.naturalHeight) return;
    block.h = Math.round(block.w * imgEl.naturalHeight / imgEl.naturalWidth);
    const el = document.querySelector(`[data-bid="${block.id}"]`);
    if (el) el.style.height = block.h + 'px';
    updateCanvasHeight();
  };
  if (imgEl.complete && imgEl.naturalWidth) doFit();
  else imgEl.addEventListener('load', doFit, { once: true });
}

// ── Render block ──────────────────────────────────────────
function renderBlock(block) {
  const canvas = document.getElementById('block-canvas');
  const el = document.createElement('div');
  el.className = 'fb';
  el.dataset.bid = block.id;
  applyPos(el, block);

  // Header
  const hdr = document.createElement('div');
  hdr.className = 'fb-hdr';
  const label = document.createElement('span');
  label.className = 'fb-label';
  label.textContent = block.type;
  hdr.appendChild(label);
  const flex = document.createElement('div'); flex.style.flex = '1';
  hdr.appendChild(flex);
  hdr.appendChild(mkBtn('<i class="bi bi-front"></i>', 'Bring front', () => bringFront(block.id)));
  hdr.appendChild(mkBtn('<i class="bi bi-back"></i>', 'Send back', () => sendBack(block.id)));

  // Border color swatch + hidden color input (선언 먼저, borderBtn에서 참조)
  const colorSwatch = document.createElement('label');
  colorSwatch.className = 'fb-border-swatch';
  colorSwatch.title = 'Border color';
  colorSwatch.style.display = block.showBorder ? 'flex' : 'none';
  colorSwatch.style.background = block.borderColor;

  const colorInput = document.createElement('input');
  colorInput.type = 'color';
  colorInput.value = block.borderColor;
  colorInput.className = 'fb-color-input';
  colorInput.addEventListener('input', () => {
    block.borderColor = colorInput.value;
    colorSwatch.style.background = block.borderColor;
    applyBorder(el, block);
  });
  colorSwatch.appendChild(colorInput);

  // Border width selector
  const widthSel = document.createElement('select');
  widthSel.className = 'fb-border-width';
  widthSel.title = 'Border width';
  widthSel.style.display = block.showBorder ? 'block' : 'none';
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

  // Border radius selector
  const radiusSel = document.createElement('select');
  radiusSel.className = 'fb-border-width';
  radiusSel.title = 'Border radius';
  radiusSel.style.display = block.showBorder ? 'block' : 'none';
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

  // Border toggle button (swatch/widthSel/radiusSel가 미리 선언된 이후에 정의)
  const borderBtn = mkBtn('<i class="bi bi-border-style"></i>', 'Toggle border', () => {
    block.showBorder = !block.showBorder;
    borderBtn.classList.toggle('fb-btn-active', block.showBorder);
    colorSwatch.style.display = block.showBorder ? 'flex' : 'none';
    widthSel.style.display = block.showBorder ? 'block' : 'none';
    radiusSel.style.display = block.showBorder ? 'block' : 'none';
    applyBorder(el, block);
  });
  if (block.showBorder) borderBtn.classList.add('fb-btn-active');

  hdr.appendChild(borderBtn);
  hdr.appendChild(colorSwatch);
  hdr.appendChild(widthSel);
  hdr.appendChild(radiusSel);

  if (block.type === 'text') {
    const scBtn = mkBtn(
      '<span style="font-size:0.7rem;font-weight:700;letter-spacing:-0.5px;">맞춤법</span>',
      '블록 맞춤법 미리보기',
      () => _scBlockPreviewToggle(block.id),
    );
    scBtn.classList.add('fb-sc-preview-btn');
    scBtn.style.cssText = 'width:auto;padding:0 6px;';
    hdr.appendChild(scBtn);
  }

  const del = mkBtn('<i class="bi bi-x-lg"></i>', 'Delete', () => removeBlock(block.id));
  del.classList.add('fb-del');
  hdr.appendChild(del);
  hdr.addEventListener('mousedown', e => { if (!e.target.closest('button, select, label, input')) startDrag(e, block); });
  el.appendChild(hdr);

  const body = document.createElement('div');
  body.className = 'fb-body';

  if (block.type === 'text' || block.type === 'heading' || block.type === 'code') {
    const edEl = document.createElement('div');
    edEl.className = 'fb-editor';
    body.appendChild(edEl);
    el.appendChild(body);
    canvas.appendChild(el);
    block.editor = createEditor(edEl, block.content || (block.type === 'heading' ? '<h1></h1>' : '<p></p>'));
  } else if (block.type === 'image') {
    body.classList.add('fb-body-image');
    if (block.src) {
      const img = document.createElement('img');
      img.src = block.src; img.className = 'fb-img'; img.draggable = false;
      img.style.objectPosition = `${block.imgOffsetX}% ${block.imgOffsetY}%`;
      fitBlockToImage(block, img);
      body.appendChild(img);
      body.addEventListener('mousedown', e => { e.stopPropagation(); selectBlock(block.id); startPan(e, block); });
      const hint = document.createElement('div');
      hint.className = 'fb-pan-hint'; hint.textContent = '✥ drag to pan';
      body.appendChild(hint);
    } else {
      body.appendChild(buildDropZone(block));
    }
    el.appendChild(body);
    canvas.appendChild(el);
  } else if (block.type === 'spacer') {
    body.className = 'fb-body fb-spacer-body';
    body.innerHTML = '<span>— spacer —</span>';
    el.appendChild(body);
    canvas.appendChild(el);
  }

  // body가 DOM에 붙은 이후 테두리 적용
  applyBorder(el, block);

  ['se', 'e', 's'].forEach(edge => {
    const rh = document.createElement('div');
    rh.className = `fb-rh fb-rh-${edge}`;
    rh.addEventListener('mousedown', e => { e.stopPropagation(); selectBlock(block.id); startResize(e, block, edge); });
    el.appendChild(rh);
  });
  el.addEventListener('mousedown', () => selectBlock(block.id));
}

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

function refreshBlock(block) {
  if (block.editor) block.content = block.editor.getHTML();
  const old = document.querySelector(`[data-bid="${block.id}"]`);
  if (old) { if (block.editor) { block.editor.destroy(); block.editor = null; } old.remove(); }
  renderBlock(block);
  selectBlock(block.id);
}

function applyPos(el, b) {
  el.style.left = b.x + 'px'; el.style.top = b.y + 'px';
  el.style.width = b.w + 'px'; el.style.height = b.h + 'px';
}

function applyBorder(el, block) {
  const body = el.querySelector('.fb-body');
  if (!body) return;
  if (block.showBorder) {
    body.style.border = `${block.borderWidth ?? 1}px solid ${block.borderColor ?? '#000000'}`;
    const r = block.borderRadius ?? 0;
    body.style.borderRadius = r >= 9999 ? '9999px' : `${r}px`;
  } else {
    body.style.border = '';
    body.style.borderRadius = '';
  }
}

function selectBlock(id) {
  selectedId = id;
  document.querySelectorAll('.fb').forEach(e => e.classList.remove('selected'));
  document.querySelector(`[data-bid="${id}"]`)?.classList.add('selected');
}

function bringFront(id) { const el = document.querySelector(`[data-bid="${id}"]`); if (el) el.style.zIndex = String(++idCounter); }
function sendBack(id)   { const el = document.querySelector(`[data-bid="${id}"]`); if (el) el.style.zIndex = '1'; }

function mkBtn(html, title, fn) {
  const b = document.createElement('button');
  b.type = 'button'; b.innerHTML = html; b.title = title; b.className = 'fb-btn';
  b.addEventListener('click', e => { e.stopPropagation(); fn(); });
  return b;
}

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
function startDrag(e, block) {
  e.preventDefault();
  const el = document.querySelector(`[data-bid="${block.id}"]`);
  if (!el) return;
  const rect = el.getBoundingClientRect();
  dragInfo = { id: block.id, offsetX: e.clientX - rect.left, offsetY: e.clientY - rect.top };
  el.classList.add('dragging');
  document.addEventListener('mousemove', onDrag);
  document.addEventListener('mouseup', endDrag);
}
function onDrag(e) {
  if (!dragInfo) return;
  const block = blocks.find(b => b.id === dragInfo.id); if (!block) return;
  const canvas = document.getElementById('block-canvas');
  const cRect = canvas.getBoundingClientRect();
  block.x = Math.max(0, e.clientX - cRect.left - dragInfo.offsetX);
  block.y = Math.max(0, e.clientY - cRect.top - dragInfo.offsetY + canvas.scrollTop);
  const el = document.querySelector(`[data-bid="${block.id}"]`);
  if (el) { el.style.left = block.x + 'px'; el.style.top = block.y + 'px'; }
  updateCanvasHeight();
}
function endDrag() {
  document.querySelector(`[data-bid="${dragInfo?.id}"]`)?.classList.remove('dragging');
  dragInfo = null;
  document.removeEventListener('mousemove', onDrag);
  document.removeEventListener('mouseup', endDrag);
}

// ── Resize ────────────────────────────────────────────────
function startResize(e, block, edge) {
  e.preventDefault(); e.stopPropagation();
  resizeInfo = { id: block.id, edge, startX: e.clientX, startY: e.clientY, startW: block.w, startH: block.h };
  document.addEventListener('mousemove', onResize);
  document.addEventListener('mouseup', endResize);
}
function onResize(e) {
  if (!resizeInfo) return;
  const block = blocks.find(b => b.id === resizeInfo.id); if (!block) return;
  const dx = e.clientX - resizeInfo.startX, dy = e.clientY - resizeInfo.startY;
  if (resizeInfo.edge === 'e' || resizeInfo.edge === 'se') block.w = Math.max(80, resizeInfo.startW + dx);
  if (resizeInfo.edge === 's' || resizeInfo.edge === 'se') block.h = Math.max(40, resizeInfo.startH + dy);
  const el = document.querySelector(`[data-bid="${block.id}"]`);
  if (el) { el.style.width = block.w + 'px'; el.style.height = block.h + 'px'; }
  updateCanvasHeight();
}
function endResize() {
  resizeInfo = null;
  document.removeEventListener('mousemove', onResize);
  document.removeEventListener('mouseup', endResize);
}

// ── Image Pan ─────────────────────────────────────────────
function startPan(e, block) {
  e.preventDefault();
  document.querySelector(`[data-bid="${block.id}"] .fb-body-image`)?.classList.add('panning');
  panInfo = { id: block.id, startX: e.clientX, startY: e.clientY, startOX: block.imgOffsetX ?? 50, startOY: block.imgOffsetY ?? 50 };
  document.addEventListener('mousemove', onPan);
  document.addEventListener('mouseup', endPan);
}
function onPan(e) {
  if (!panInfo) return;
  const block = blocks.find(b => b.id === panInfo.id); if (!block) return;
  block.imgOffsetX = Math.max(0, Math.min(100, panInfo.startOX - (e.clientX - panInfo.startX) / block.w * 100));
  block.imgOffsetY = Math.max(0, Math.min(100, panInfo.startOY - (e.clientY - panInfo.startY) / block.h * 100));
  const img = document.querySelector(`[data-bid="${block.id}"] .fb-img`);
  if (img) img.style.objectPosition = `${block.imgOffsetX}% ${block.imgOffsetY}%`;
}
function endPan() {
  document.querySelector(`[data-bid="${panInfo?.id}"] .fb-body-image`)?.classList.remove('panning');
  panInfo = null;
  document.removeEventListener('mousemove', onPan);
  document.removeEventListener('mouseup', endPan);
}

// ── Collect (v3 multi-page format) ────────────────────────
function collectData() {
  syncCurrentPage(); // save current page

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
        showBorder: b.showBorder ?? false,
        borderColor: b.borderColor ?? '#000000',
        borderWidth: b.borderWidth ?? 1,
        borderRadius: b.borderRadius ?? 0,
      })),
    };
  });

  const data = { v: 3, pages: pagesData };

  // Generate reading HTML (one .magazine-page per page)
  let html = '<div class="magazine-pages" data-page-count="' + pages.length + '">';
  pagesData.forEach((page, pi) => {
    const { cW, cH, blocks: pBlocks } = page;
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
        html += `<div style="${s}"><img src="${b.src}" style="width:100%;height:100%;object-fit:cover;object-position:${ox}% ${oy}%;display:block;"></div>`;
      } else if (b.type === 'spacer') {
        html += `<div style="${s}"></div>`;
      } else {
        html += `<div style="${s}">${b.content}</div>`;
      }
    });
    html += '</div></div></div>';
  });
  html += '</div>';

  return { blocksJson: JSON.stringify(data), html };
}

// ── Inline preview ────────────────────────────────────────
let previewActive = false;

function buildPreviewSlide(page) {
  const cw = page.cw || canvasW() || 1200;
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
      html += `<div style="${s}"><img src="${b.src}" style="width:100%;height:100%;object-fit:cover;object-position:${ox}% ${oy}%;display:block;"></div>`;
    } else if (b.type === 'spacer') {
      html += `<div style="${s}"></div>`;
    } else {
      html += `<div style="${s}">${b.content || ''}</div>`;
    }
  });
  html += '</div></div>';
  return html;
}

function enterPreview() {
  syncCurrentPage();
  const pagesSnap = pages.map(p => ({
    id: p.id, cw: p.cw || canvasW(), ch: p.ch || 600,
    blocks: p.blocks.map(b => ({ ...b, content: b.editor ? b.editor.getHTML() : b.content })),
  }));

  const canvas = document.getElementById('block-canvas');
  const tabBar = document.getElementById('page-tab-bar');
  canvas.style.display = 'none';
  if (tabBar) tabBar.style.display = 'none';

  const wrap = canvas.parentElement;
  const pv = document.createElement('div');
  pv.id = 'inline-preview';
  pv.className = 'inline-preview';
  pv.title = 'Click to return to editing';

  // Render each page
  pagesSnap.forEach(page => {
    const pg = document.createElement('div');
    pg.className = 'inline-preview-page';
    pg.innerHTML = buildPreviewSlide(page);
    pv.appendChild(pg);
  });

  // "Click to edit" hint
  const hint = document.createElement('div');
  hint.className = 'inline-preview-hint';
  hint.textContent = 'Click anywhere to return to editing';
  pv.appendChild(hint);

  pv.addEventListener('click', exitPreview);
  wrap.appendChild(pv);

  // Update button
  const btn = document.querySelector('.tiptap-btn-preview');
  if (btn) { btn.textContent = '← Edit'; btn.classList.add('fb-btn-active'); }

  previewActive = true;
}

function exitPreview() {
  const canvas = document.getElementById('block-canvas');
  const tabBar = document.getElementById('page-tab-bar');
  const pv = document.getElementById('inline-preview');
  canvas.style.display = '';
  if (tabBar) tabBar.style.display = '';
  if (pv) pv.remove();

  const btn = document.querySelector('.tiptap-btn-preview');
  if (btn) { btn.textContent = 'Preview'; btn.classList.remove('fb-btn-active'); }

  previewActive = false;
}

function togglePreview() {
  previewActive ? exitPreview() : enterPreview();
}

// ── Spell Check ───────────────────────────────────────────
let _scState = { editor: null, from: 0, to: 0 };
let _scEnVariant = 'vennify'; // 글로벌 팝업 모델 선택 상태

function _scEscapeHtml(text) {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function _scWordDiff(orig, corr) {
  // 단일 줄(문자열) 내 word-level LCS diff → { html, changes }
  const esc = s => s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
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

function _scDiffHtml(orig, corr) {
  // 항상 줄(\n) 단위로 처리 — _scWordDiff(orig, corr) 전체 텍스트 호출 절대 없음
  // 줄 수가 달라도 zip으로 처리 (추가된 줄 → 초록, 삭제된 줄 → 빨강)
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

function _scDiffLegend(changes) {
  return `<div style="margin-top:10px;padding-top:8px;border-top:1px solid #e2e8f0;display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
    <span style="font-size:0.69rem;color:#94a3b8;flex:1;font-weight:500;">${changes}개 수정됨</span>
    <span style="background:#fee2e2;color:#b91c1c;border-radius:3px;padding:1px 7px;font-size:0.68rem;font-weight:500;text-decoration:line-through;">삭제</span>
    <span style="background:#dcfce7;color:#166534;border-radius:3px;padding:1px 7px;font-size:0.68rem;font-weight:500;">추가</span>
  </div>`;
}

// 애니메이션 CSS 즉시 주입 (spin + shimmer)
;(function() {
  if (document.getElementById('sc-spin-style')) return;
  const s = document.createElement('style'); s.id = 'sc-spin-style';
  s.textContent = '@keyframes spin{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}@keyframes scShimmer{from{background-position:200% 0}to{background-position:-200% 0}}';
  (document.head || document.documentElement).appendChild(s);
})();

// 버튼 로딩 상태 헬퍼
function _scBtnLoad(btn) {
  btn.disabled = true;
  btn.innerHTML = '<span style="display:inline-block;width:15px;height:15px;border:2.5px solid rgba(255,255,255,0.35);border-top-color:#fff;border-radius:50%;animation:spin 0.65s linear infinite;vertical-align:middle;margin-right:8px;"></span>검사 중...';
  btn.style.opacity = '0.7';
  btn.style.cursor = 'not-allowed';
}
function _scBtnReady(btn) {
  btn.disabled = false;
  btn.textContent = '다시 검사';
  btn.style.opacity = '';
  btn.style.cursor = '';
}

// 버튼 링 스피너 HTML (하위호환)
const _scSpinnerBtn = '';

function _scLoadingHtml() {
  const bar = (w, d) => `<div style="height:13px;background:linear-gradient(90deg,#e2e8f0 25%,#f8fafc 50%,#e2e8f0 75%);background-size:200% 100%;animation:scShimmer 1.4s ease-in-out infinite;animation-delay:${d}s;border-radius:4px;width:${w}%;"></div>`;
  return `<div style="display:flex;flex-direction:column;gap:10px;padding:2px 0;">${bar(88,0)}${bar(73,0.15)}${bar(81,0.3)}${bar(65,0.45)}</div>`;
}

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

function _scRemovePopup() {
  document.getElementById('sc-overlay')?.remove();
  document.getElementById('sc-popup')?.remove();
}

function _scApply(correctedText) {
  const { editor, from, to } = _scState;
  if (!editor) return;
  // \n 이 포함된 경우 줄별로 paragraph 노드로 분리해서 삽입
  // insertContentAt에 plain string을 넘기면 \n이 무시되므로 노드 스펙 배열 사용
  const lines = correctedText.split('\n');
  const content = lines.map(line => ({
    type: 'paragraph',
    content: line ? [{ type: 'text', text: line }] : [],
  }));
  editor.chain().focus().deleteRange({ from, to }).insertContentAt(from, content).run();
  _scRemovePopup();
}

function _scShowPopup({ selectModel, original, error }) {
  _scRemovePopup();

  const overlay = document.createElement('div');
  overlay.id = 'sc-overlay';
  overlay.style.cssText = 'position:fixed;inset:0;background:rgba(15,23,42,0.45);backdrop-filter:blur(2px);z-index:9998;';
  overlay.addEventListener('click', _scRemovePopup);

  const popup = document.createElement('div');
  popup.id = 'sc-popup';
  popup.style.cssText = [
    'position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);',
    'background:#ffffff;border-radius:16px;',
    'box-shadow:0 20px 60px rgba(0,0,0,0.15),0 4px 16px rgba(0,0,0,0.08);',
    'z-index:9999;width:min(560px,92vw);font-family:inherit;overflow:hidden;',
  ].join('');
  popup.addEventListener('click', e => e.stopPropagation());

  if (error) {
    popup.innerHTML = `
      <div style="padding:20px 24px 0;display:flex;align-items:center;justify-content:space-between;">
        <span style="font-size:1rem;font-weight:700;color:#0f172a;letter-spacing:-0.3px;">맞춤법 검사</span>
        <button id="sc-hdr-close" type="button" style="background:none;border:none;cursor:pointer;color:#94a3b8;font-size:1.1rem;padding:4px;border-radius:6px;line-height:1;"><i class="bi bi-x-lg"></i></button>
      </div>
      <div style="padding:16px 24px;">
        <div style="display:flex;align-items:flex-start;gap:10px;background:#fef2f2;border:1px solid #fecaca;border-radius:10px;padding:12px 14px;">
          <i class="bi bi-exclamation-circle-fill" style="color:#ef4444;font-size:1rem;margin-top:1px;flex-shrink:0;"></i>
          <span style="font-size:0.875rem;color:#991b1b;line-height:1.5;">${_scEscapeHtml(error)}</span>
        </div>
      </div>
      <div style="padding:0 24px 20px;display:flex;justify-content:flex-end;">
        <button id="sc-err-close" type="button" style="padding:8px 20px;border:1.5px solid #e2e8f0;border-radius:8px;cursor:pointer;background:#fff;font-size:0.875rem;color:#475569;font-weight:500;transition:background 0.15s;">닫기</button>
      </div>`;
    popup.querySelector('#sc-hdr-close').addEventListener('click', _scRemovePopup);
    popup.querySelector('#sc-err-close').addEventListener('click', _scRemovePopup);
  } else {
    // ── 헤더 ──────────────────────────────────────────────────
    const hdr = document.createElement('div');
    hdr.style.cssText = 'padding:20px 24px 0;display:flex;align-items:center;justify-content:space-between;margin-bottom:18px;';
    hdr.innerHTML = `<span style="font-size:1rem;font-weight:700;color:#0f172a;letter-spacing:-0.3px;display:flex;align-items:center;gap:7px;"><i class="bi bi-spell-check" style="color:#6366f1;font-size:1.05rem;"></i>맞춤법 검사</span>`;
    const xBtn = document.createElement('button');
    xBtn.type = 'button';
    xBtn.innerHTML = '<i class="bi bi-x-lg"></i>';
    xBtn.style.cssText = 'background:none;border:none;cursor:pointer;color:#94a3b8;font-size:1rem;padding:4px;border-radius:6px;line-height:1;';
    xBtn.addEventListener('click', _scRemovePopup);
    hdr.appendChild(xBtn);
    popup.appendChild(hdr);

    // ── 모델 선택 ─────────────────────────────────────────────
    const modelSection = document.createElement('div');
    modelSection.style.cssText = 'padding:0 24px;margin-bottom:16px;';
    const modelLabel = document.createElement('div');
    modelLabel.style.cssText = 'font-size:0.72rem;font-weight:600;color:#94a3b8;text-transform:uppercase;letter-spacing:0.6px;margin-bottom:8px;';
    modelLabel.textContent = '모델 선택';
    modelSection.appendChild(modelLabel);

    const modelToggle = document.createElement('div');
    modelToggle.style.cssText = 'display:grid;grid-template-columns:1fr 1fr;gap:8px;';
    const activeStyle = [
      'padding:10px 12px;border-radius:10px;cursor:pointer;border:2px solid #6366f1;',
      'background:linear-gradient(135deg,#6366f1,#8b5cf6);color:#fff;text-align:left;transition:all 0.15s;',
    ].join('');
    const inactiveStyle = [
      'padding:10px 12px;border-radius:10px;cursor:pointer;border:1.5px solid #e2e8f0;',
      'background:#fff;color:#475569;text-align:left;transition:all 0.15s;',
    ].join('');
    const variantBtns = {};
    [
      { v: 'vennify', label: '빠름', sub: 'KO: et5 · EN: T5-base' },
      { v: 'coedit',  label: '고품질', sub: 'KO: et5 · EN: CoEdIT' },
    ].forEach(({ v, label, sub }) => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.style.cssText = v === _scEnVariant ? activeStyle : inactiveStyle;
      btn.innerHTML = `
        <div style="font-size:0.875rem;font-weight:600;margin-bottom:2px;">${label}</div>
        <div style="font-size:0.72rem;opacity:0.7;">${sub}</div>`;
      btn.addEventListener('click', e => {
        e.stopPropagation();
        _scEnVariant = v;
        Object.entries(variantBtns).forEach(([key, b]) => { b.style.cssText = key === v ? activeStyle : inactiveStyle; });
      });
      variantBtns[v] = btn;
      modelToggle.appendChild(btn);
    });
    modelSection.appendChild(modelToggle);
    popup.appendChild(modelSection);

    // ── 원본 텍스트 ──────────────────────────────────────────
    const textSection = document.createElement('div');
    textSection.style.cssText = 'padding:0 24px;margin-bottom:16px;';
    const textLabel = document.createElement('div');
    textLabel.style.cssText = 'font-size:0.72rem;font-weight:600;color:#94a3b8;text-transform:uppercase;letter-spacing:0.6px;margin-bottom:6px;';
    textLabel.textContent = '선택한 텍스트';
    const textBox = document.createElement('div');
    textBox.style.cssText = 'background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;padding:12px 14px;font-size:0.875rem;color:#334155;max-height:110px;overflow:auto;white-space:pre-wrap;word-break:break-all;line-height:1.6;';
    textBox.textContent = original;
    textSection.appendChild(textLabel);
    textSection.appendChild(textBox);
    popup.appendChild(textSection);

    // ── 결과 영역 ─────────────────────────────────────────────
    const resultSection = document.createElement('div');
    resultSection.style.cssText = 'display:none;padding:0 24px;margin-bottom:16px;';
    const resultLabel = document.createElement('div');
    resultLabel.style.cssText = 'font-size:0.72rem;font-weight:600;color:#94a3b8;text-transform:uppercase;letter-spacing:0.6px;margin-bottom:6px;';
    resultLabel.textContent = '교정 결과';
    const resultBox = document.createElement('div');
    resultBox.className = 'sc-result-box';
    resultBox.style.cssText = 'border-radius:10px;padding:12px 14px;font-size:0.875rem;max-height:110px;overflow:auto;white-space:pre-wrap;word-break:break-all;line-height:1.6;';
    resultSection.appendChild(resultLabel);
    resultSection.appendChild(resultBox);
    popup.appendChild(resultSection);

    // ── 액션 바 ───────────────────────────────────────────────
    const footer = document.createElement('div');
    footer.style.cssText = 'padding:14px 24px 20px;display:flex;gap:8px;justify-content:flex-end;border-top:1px solid #f1f5f9;margin-top:4px;';

    const cancelBtn = document.createElement('button');
    cancelBtn.type = 'button'; cancelBtn.textContent = '닫기';
    cancelBtn.style.cssText = 'padding:8px 18px;border:1.5px solid #e2e8f0;border-radius:8px;cursor:pointer;background:#fff;font-size:0.875rem;color:#475569;font-weight:500;';
    cancelBtn.addEventListener('click', _scRemovePopup);

    const runBtn = document.createElement('button');
    runBtn.type = 'button'; runBtn.textContent = '검사 시작';
    runBtn.style.cssText = 'padding:8px 20px;border:none;border-radius:8px;cursor:pointer;background:linear-gradient(135deg,#6366f1,#8b5cf6);color:#fff;font-size:0.875rem;font-weight:600;letter-spacing:-0.2px;';

    const applyBtn = document.createElement('button');
    applyBtn.type = 'button'; applyBtn.textContent = '적용하기';
    applyBtn.style.cssText = 'display:none;padding:8px 20px;border:none;border-radius:8px;cursor:pointer;background:linear-gradient(135deg,#10b981,#059669);color:#fff;font-size:0.875rem;font-weight:600;';

    footer.appendChild(cancelBtn);
    footer.appendChild(runBtn);
    footer.appendChild(applyBtn);
    popup.appendChild(footer);

    // ── 검사 실행 로직 ────────────────────────────────────────
    runBtn.addEventListener('click', async e => {
      e.stopPropagation();
      _scBtnLoad(runBtn);
      applyBtn.style.display = 'none';
      // 로딩 shimmer 즉시 표시
      resultSection.style.display = 'block';
      resultBox.style.cssText = 'border-radius:10px;padding:12px 14px;font-size:0.875rem;max-height:110px;overflow:auto;line-height:1.6;background:#f8fafc;border:1px solid #e2e8f0;';
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
        const corrected = (await res.json()).corrected;
        const isSame = original === corrected;

        resultSection.style.display = 'block';
        if (isSame) {
          resultBox.style.cssText = 'border-radius:10px;padding:12px 14px;font-size:0.875rem;max-height:110px;overflow:auto;white-space:pre-wrap;word-break:break-all;line-height:1.6;background:#f8fafc;border:1px solid #e2e8f0;color:#94a3b8;';
          resultBox.innerHTML = '<i class="bi bi-check-circle-fill" style="color:#10b981;margin-right:6px;"></i>오류가 발견되지 않았습니다.';
        } else {
          resultBox.style.cssText = 'border-radius:10px;padding:12px 14px;font-size:0.875rem;max-height:150px;overflow:auto;white-space:pre-wrap;word-break:break-all;line-height:1.6;background:#f8fafc;border:1px solid #e2e8f0;';
          const diff = _scDiffHtml(original, corrected);
          resultBox.innerHTML = diff.html + _scDiffLegend(diff.changes);
          applyBtn.style.display = '';
          applyBtn.onclick = () => { _scApply(corrected); };
        }
      } catch (err) {
        resultSection.style.display = 'block';
        resultBox.style.cssText = 'border-radius:10px;padding:12px 14px;font-size:0.875rem;max-height:150px;overflow:auto;white-space:pre-wrap;word-break:break-all;line-height:1.6;background:#fef2f2;border:1px solid #fecaca;color:#991b1b;';
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

  // spin 애니메이션 (없으면 추가)
  if (!document.getElementById('sc-spin-style')) {
    const s = document.createElement('style');
    s.id = 'sc-spin-style';
    s.textContent = '@keyframes spin{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}@keyframes scShimmer{from{background-position:200% 0}to{background-position:-200% 0}}';
    document.head.appendChild(s);
  }

  const onEsc = e => { if (e.key === 'Escape') { _scRemovePopup(); document.removeEventListener('keydown', onEsc); } };
  document.addEventListener('keydown', onEsc);
}

function triggerSpellCheck() {
  const target = _scGetTarget();
  if (!target) {
    _scShowPopup({ error: '텍스트 블록에서 검사할 텍스트를 드래그로 선택한 후 실행하세요.' });
    return;
  }
  _scState = { editor: target.editor, from: target.from, to: target.to };
  // 모델 선택 화면 먼저 표시 — 검사는 사용자가 버튼 클릭 시 실행
  _scShowPopup({ selectModel: true, original: target.text });
}

// ── Block-level spell preview (split panel) ───────────────
function _scBlockPreviewOpen(blockId) {
  const block = blocks.find(b => b.id === blockId);
  if (!block || !block.editor) return;
  const el = document.querySelector(`[data-bid="${blockId}"]`);
  if (!el) return;

  _scSplitActive.add(blockId);
  el.querySelector('.fb-sc-preview-btn')?.classList.add('fb-btn-active');

  // Split body into two panes
  const body = el.querySelector('.fb-body');
  body.style.cssText += 'display:flex;flex-direction:row;';
  const edEl = body.querySelector('.fb-editor');
  edEl.style.cssText += 'width:50%;height:100%;overflow:auto;border-right:1px solid #e5e7eb;box-sizing:border-box;';

  // ── 패널 ─────────────────────────────────────────────────
  const panel = document.createElement('div');
  panel.className = 'fb-spell-preview';
  panel.style.cssText = [
    'width:50%;height:100%;box-sizing:border-box;display:flex;flex-direction:column;',
    'background:#f8fafc;border-left:1px solid #e2e8f0;',
  ].join('');

  // 헤더
  const panelHdr = document.createElement('div');
  panelHdr.style.cssText = [
    'display:flex;align-items:center;gap:6px;padding:10px 14px;flex-shrink:0;',
    'background:#fff;border-bottom:1px solid #e2e8f0;',
  ].join('');
  panelHdr.innerHTML = `<i class="bi bi-spell-check" style="color:#6366f1;font-size:0.9rem;"></i>
    <span style="font-size:0.78rem;font-weight:700;color:#334155;letter-spacing:-0.2px;flex:1;">맞춤법 미리보기</span>`;
  const closeBtn = document.createElement('button');
  closeBtn.type = 'button'; closeBtn.innerHTML = '<i class="bi bi-x"></i>';
  closeBtn.style.cssText = 'background:none;border:none;cursor:pointer;font-size:0.95rem;color:#94a3b8;padding:2px 4px;line-height:1;border-radius:4px;';
  closeBtn.addEventListener('click', e => { e.stopPropagation(); _scBlockPreviewClose(blockId); });
  panelHdr.appendChild(closeBtn);
  panel.appendChild(panelHdr);

  // 모델 선택
  let selectedVariant = 'vennify';
  const modelSection = document.createElement('div');
  modelSection.style.cssText = 'padding:12px 14px 10px;flex-shrink:0;border-bottom:1px solid #e2e8f0;background:#fff;';
  const modelTopLabel = document.createElement('div');
  modelTopLabel.style.cssText = 'font-size:0.68rem;font-weight:600;color:#94a3b8;text-transform:uppercase;letter-spacing:0.6px;margin-bottom:8px;';
  modelTopLabel.textContent = '모델 선택';
  modelSection.appendChild(modelTopLabel);

  const modelGrid = document.createElement('div');
  modelGrid.style.cssText = 'display:grid;grid-template-columns:1fr 1fr;gap:6px;';
  const activeStyle = 'padding:7px 10px;border-radius:8px;cursor:pointer;border:2px solid #6366f1;background:linear-gradient(135deg,#6366f1,#8b5cf6);color:#fff;text-align:left;';
  const inactiveStyle = 'padding:7px 10px;border-radius:8px;cursor:pointer;border:1.5px solid #e2e8f0;background:#fff;color:#475569;text-align:left;';
  const variantBtns = {};
  [{ v: 'vennify', label: '빠름', sub: 'KO: et5 · EN: T5-base' }, { v: 'coedit', label: '고품질', sub: 'KO: et5 · EN: CoEdIT' }].forEach(({ v, label, sub }) => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.style.cssText = v === 'vennify' ? activeStyle : inactiveStyle;
    btn.innerHTML = `<div style="font-size:0.8rem;font-weight:600;margin-bottom:1px;">${label}</div><div style="font-size:0.67rem;opacity:0.7;">${sub}</div>`;
    btn.addEventListener('click', e => {
      e.stopPropagation(); selectedVariant = v;
      Object.entries(variantBtns).forEach(([key, b]) => { b.style.cssText = key === v ? activeStyle : inactiveStyle; });
    });
    variantBtns[v] = btn; modelGrid.appendChild(btn);
  });
  modelSection.appendChild(modelGrid);

  // 검사 시작 버튼
  const runBtn = document.createElement('button');
  runBtn.type = 'button'; runBtn.textContent = '검사 시작';
  runBtn.style.cssText = 'margin-top:10px;width:100%;padding:8px;border:none;border-radius:8px;cursor:pointer;background:linear-gradient(135deg,#6366f1,#8b5cf6);color:#fff;font-size:0.82rem;font-weight:600;letter-spacing:-0.2px;';
  modelSection.appendChild(runBtn);
  panel.appendChild(modelSection);

  // 결과 영역
  const content = document.createElement('div');
  content.className = 'fb-spell-preview-text';
  content.style.cssText = 'flex:1;padding:14px;font-size:0.875rem;line-height:1.7;color:#94a3b8;white-space:pre-wrap;word-break:break-all;overflow:auto;';
  content.textContent = '모델을 선택하고 검사 시작을 눌러주세요.';
  panel.appendChild(content);

  body.appendChild(panel);

  // 검사 실행
  runBtn.addEventListener('click', async e => {
    e.stopPropagation();
    const fullText = block.editor.state.doc.textBetween(0, block.editor.state.doc.content.size, '\n');
    if (!fullText.trim()) { content.style.color = '#94a3b8'; content.textContent = '내용이 없습니다.'; return; }

    _scBtnLoad(runBtn);
    panel.querySelector('.fb-spell-apply-btn')?.remove();
    content.style.color = '';
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
        content.style.color = '#94a3b8';
        content.innerHTML = '<i class="bi bi-check-circle-fill" style="color:#10b981;margin-right:6px;"></i>오류가 발견되지 않았습니다.';
      } else {
        content.style.color = '';
        const diff = _scDiffHtml(fullText, corrected);
        content.innerHTML = diff.html + _scDiffLegend(diff.changes);
        const applyBtn = document.createElement('button');
        applyBtn.type = 'button'; applyBtn.textContent = '적용하기';
        applyBtn.className = 'fb-spell-apply-btn';
        applyBtn.style.cssText = 'margin:10px 14px 14px;padding:8px 18px;border:none;border-radius:8px;cursor:pointer;background:linear-gradient(135deg,#10b981,#059669);color:#fff;font-size:0.82rem;font-weight:600;align-self:flex-end;flex-shrink:0;display:block;width:calc(100% - 28px);';
        applyBtn.addEventListener('click', () => {
          const lines = corrected.split('\n');
          const nodes = lines.map(line => ({ type: 'paragraph', content: line ? [{ type: 'text', text: line }] : [] }));
          block.editor.commands.setContent(nodes);
          _scBlockPreviewClose(blockId);
        });
        panel.appendChild(applyBtn);
      }
    } catch (err) {
      content.style.color = '#991b1b';
      const msg = err.name === 'AbortError' ? '요청 시간 초과 (2분 30초). 모델 로딩 중이면 잠시 후 다시 시도해주세요.' : (err.message || '오류가 발생했습니다.');
      content.innerHTML = `<i class="bi bi-exclamation-circle-fill" style="margin-right:6px;"></i>${msg}`;
    } finally {
      clearTimeout(_scTimer2);
      _scBtnReady(runBtn);
    }
  });
}

function _scBlockPreviewClose(blockId) {
  _scSplitActive.delete(blockId);
  const el = document.querySelector(`[data-bid="${blockId}"]`);
  if (!el) return;
  el.querySelector('.fb-sc-preview-btn')?.classList.remove('fb-btn-active');
  el.querySelector('.fb-spell-preview')?.remove();
  const body = el.querySelector('.fb-body');
  if (body) { body.style.display = ''; body.style.flexDirection = ''; }
  const edEl = el.querySelector('.fb-editor');
  if (edEl) { edEl.style.width = ''; edEl.style.height = ''; edEl.style.overflow = ''; edEl.style.borderRight = ''; }
}

function _scBlockPreviewToggle(blockId) {
  _scSplitActive.has(blockId) ? _scBlockPreviewClose(blockId) : _scBlockPreviewOpen(blockId);
}

// ── Toolbar ───────────────────────────────────────────────
function buildToolbar() {
  const tb = document.getElementById('tiptap-toolbar');
  if (!tb) return;
  [
    { icon: '<i class="bi bi-fonts"></i>', tip: 'Text block', fn: () => addBlock('text') },
    { icon: '<i class="bi bi-type-h1"></i>', tip: 'Heading block', fn: () => addBlock('heading') },
    { icon: '<i class="bi bi-image"></i>', tip: 'Image block', fn: () => addBlock('image') },
    { icon: '<i class="bi bi-code-slash"></i>', tip: 'Code block', fn: () => addBlock('code') },
    { icon: '<i class="bi bi-arrows-expand"></i>', tip: 'Spacer', fn: () => addBlock('spacer', { h: 60 }) },
    { icon: '<span style="font-size:0.72rem;font-weight:700;letter-spacing:-0.5px;">맞춤법</span>', tip: '맞춤법 검사 (Ctrl+Shift+S)', fn: () => triggerSpellCheck(), wide: true },
  ].forEach(({ icon, tip, fn, wide }) => {
    const btn = document.createElement('button');
    btn.type = 'button'; btn.className = 'tiptap-toolbar-btn';
    if (wide) btn.style.cssText = 'width:auto;padding:0 8px;';
    btn.innerHTML = icon; btn.title = tip;
    btn.addEventListener('click', fn);
    tb.appendChild(btn);
  });
}

// ── Main ──────────────────────────────────────────────────
function main() {
  const canvas = document.getElementById('block-canvas');
  if (!canvas) return;
  buildToolbar();
  updatePageTabs();
  addBlock('heading', { content: '<h1></h1>', h: 80 });
  addBlock('text', { h: 200 });

  document.addEventListener('keydown', e => {
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
    form.submit();
  });
}

main();
