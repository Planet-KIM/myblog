// frontend/board_edit_tiptap.js — Multi-page free-position editor (edit mode)
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

function uid() { return 'b' + (++idCounter); }

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
  if (pages.length === 1) return;
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
  document.querySelector(`[data-bid="${id}"]`)?.remove();
  blocks.splice(idx, 1);
  if (selectedId === id) selectedId = null;
  updateCanvasHeight();
}

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
  el.className = 'fb'; el.dataset.bid = block.id;
  applyPos(el, block);

  const hdr = document.createElement('div');
  hdr.className = 'fb-hdr';
  const label = document.createElement('span'); label.className = 'fb-label'; label.textContent = block.type;
  hdr.appendChild(label);
  const flex = document.createElement('div'); flex.style.flex = '1'; hdr.appendChild(flex);
  hdr.appendChild(mkBtn('<i class="bi bi-front"></i>', 'Bring front', () => bringFront(block.id)));
  hdr.appendChild(mkBtn('<i class="bi bi-back"></i>', 'Send back', () => sendBack(block.id)));

  // 먼저 선언 (borderBtn 콜백에서 참조하기 위해)
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

  const del = mkBtn('<i class="bi bi-x-lg"></i>', 'Delete', () => removeBlock(block.id));
  del.classList.add('fb-del'); hdr.appendChild(del);
  hdr.addEventListener('mousedown', e => { if (!e.target.closest('button, select, label, input')) startDrag(e, block); });
  el.appendChild(hdr);

  const body = document.createElement('div');
  body.className = 'fb-body';

  if (block.type === 'text' || block.type === 'heading' || block.type === 'code') {
    const edEl = document.createElement('div'); edEl.className = 'fb-editor';
    body.appendChild(edEl); el.appendChild(body); canvas.appendChild(el);
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
    } else { body.appendChild(buildDropZone(block)); }
    el.appendChild(body); canvas.appendChild(el);
  } else if (block.type === 'spacer') {
    body.className = 'fb-body fb-spacer-body';
    body.innerHTML = '<span>— spacer —</span>';
    el.appendChild(body); canvas.appendChild(el);
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
  renderBlock(block); selectBlock(block.id);
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
  const el = document.querySelector(`[data-bid="${block.id}"]`); if (!el) return;
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

// ── Inline preview ────────────────────────────────────────
let previewActive = false;

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

// ── Collect (v3 multi-page) ───────────────────────────────
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

// ── Spell Check ───────────────────────────────────────────
let _scState = { editor: null, from: 0, to: 0 };

function _scEscapeHtml(text) {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
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
  const text = editor.state.doc.textBetween(from, to, ' ');
  return { editor, text, from, to };
}

function _scRemovePopup() {
  document.getElementById('sc-overlay')?.remove();
  document.getElementById('sc-popup')?.remove();
}

function _scApply(correctedText) {
  const { editor, from, to } = _scState;
  if (!editor) return;
  editor.chain().focus().deleteRange({ from, to }).insertContentAt(from, correctedText).run();
  _scRemovePopup();
}

function _scShowPopup({ loading, original, corrected, error }) {
  _scRemovePopup();

  const overlay = document.createElement('div');
  overlay.id = 'sc-overlay';
  overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.35);z-index:9998;';
  overlay.addEventListener('click', _scRemovePopup);

  const popup = document.createElement('div');
  popup.id = 'sc-popup';
  popup.style.cssText = [
    'position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);',
    'background:#fff;border-radius:12px;padding:20px 22px;',
    'box-shadow:0 8px 32px rgba(0,0,0,0.18);z-index:9999;',
    'min-width:300px;max-width:500px;width:90%;font-family:inherit;',
  ].join('');
  popup.addEventListener('click', e => e.stopPropagation());

  if (loading) {
    popup.innerHTML = `
      <div style="font-weight:600;margin-bottom:14px;">맞춤법 검사</div>
      <div style="background:#f9fafb;border-radius:8px;padding:12px;font-size:0.88rem;color:#374151;margin-bottom:14px;word-break:break-all;">${_scEscapeHtml(original)}</div>
      <div style="text-align:center;color:#6b7280;font-size:0.9rem;padding:8px 0;">검사 중...</div>`;
  } else if (error) {
    popup.innerHTML = `
      <div style="font-weight:600;margin-bottom:14px;">맞춤법 검사</div>
      <div style="color:#ef4444;font-size:0.9rem;margin-bottom:16px;">${_scEscapeHtml(error)}</div>`;
    const closeBtn = document.createElement('div');
    closeBtn.style.cssText = 'text-align:right;';
    const btn = document.createElement('button');
    btn.type = 'button'; btn.textContent = '닫기';
    btn.style.cssText = 'padding:6px 18px;border:1px solid #d1d5db;border-radius:6px;cursor:pointer;background:#fff;font-size:0.88rem;';
    btn.addEventListener('click', _scRemovePopup);
    closeBtn.appendChild(btn);
    popup.appendChild(closeBtn);
  } else {
    const isSame = original === corrected;
    popup.innerHTML = `
      <div style="font-weight:600;margin-bottom:14px;">맞춤법 검사 결과</div>
      <div style="margin-bottom:10px;">
        <div style="font-size:0.75rem;color:#9ca3af;margin-bottom:4px;">원본</div>
        <div style="background:#f9fafb;border-radius:8px;padding:10px;font-size:0.88rem;color:#374151;word-break:break-all;">${_scEscapeHtml(original)}</div>
      </div>
      <div style="margin-bottom:18px;">
        <div style="font-size:0.75rem;color:#9ca3af;margin-bottom:4px;">교정</div>
        <div style="background:${isSame ? '#f9fafb' : '#f0fdf4'};border-radius:8px;padding:10px;font-size:0.88rem;color:${isSame ? '#9ca3af' : '#15803d'};word-break:break-all;">
          ${isSame ? '오류가 발견되지 않았습니다.' : _scEscapeHtml(corrected)}
        </div>
      </div>`;
    const actions = document.createElement('div');
    actions.style.cssText = 'display:flex;gap:8px;justify-content:flex-end;';
    const cancelBtn = document.createElement('button');
    cancelBtn.type = 'button'; cancelBtn.textContent = '취소';
    cancelBtn.style.cssText = 'padding:6px 18px;border:1px solid #d1d5db;border-radius:6px;cursor:pointer;background:#fff;font-size:0.88rem;';
    cancelBtn.addEventListener('click', _scRemovePopup);
    actions.appendChild(cancelBtn);
    if (!isSame) {
      const applyBtn = document.createElement('button');
      applyBtn.type = 'button'; applyBtn.textContent = '적용하기';
      applyBtn.style.cssText = 'padding:6px 18px;border:none;border-radius:6px;cursor:pointer;background:#3b82f6;color:#fff;font-size:0.88rem;';
      applyBtn.addEventListener('click', () => _scApply(corrected));
      actions.appendChild(applyBtn);
    }
    popup.appendChild(actions);
  }

  document.body.appendChild(overlay);
  document.body.appendChild(popup);

  const onEsc = e => { if (e.key === 'Escape') { _scRemovePopup(); document.removeEventListener('keydown', onEsc); } };
  document.addEventListener('keydown', onEsc);
}

async function triggerSpellCheck() {
  const target = _scGetTarget();
  if (!target) {
    _scShowPopup({ error: '텍스트 블록에서 검사할 텍스트를 드래그로 선택한 후 실행하세요.' });
    return;
  }
  _scState = { editor: target.editor, from: target.from, to: target.to };
  _scShowPopup({ loading: true, original: target.text });
  try {
    const res = await fetch('/api/spellcheck', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: target.text }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `서버 오류 (${res.status})`);
    }
    const data = await res.json();
    _scShowPopup({ original: target.text, corrected: data.corrected });
  } catch (e) {
    _scShowPopup({ error: e.message || '맞춤법 검사 중 오류가 발생했습니다.' });
  }
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

// ── Load blocks from saved data ───────────────────────────
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

// ── Main ──────────────────────────────────────────────────
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
