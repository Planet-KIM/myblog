/**
 * @file frontend/board_edit.js — Markdown (Milkdown/Crepe) editor for editing a
 * post (templates/board_edit.html).
 *
 * Loads the saved HTML, adds image upload (picker, paste, drop) under the post,
 * a floating text-colour toolbar for selections, and fills the update form with
 * the editor HTML. Built by Vite into static/editor/board_edit.js; the
 * toolbar's looks live in static/css/writing-enhanced.css.
 */
import '@milkdown/crepe/theme/common/style.css';
import '@milkdown/crepe/theme/frame.css';

import { Crepe } from '@milkdown/crepe';
import { insert, getHTML } from '@milkdown/utils';
import { editorViewCtx } from '@milkdown/core';
import { DOMParser as ProseDOMParser } from 'prosemirror-model';
import { textColorPlugin } from './plugins/textColor.js';

// ── 이미지 업로드 ──────────────────────────────────────────
/**
 * Upload an image file and return its public URL.
 *
 * @param {File} file - Image picked, dropped or pasted by the user.
 * @param {?string} postId - Post being edited; the server files the image under it.
 * @returns {Promise<string>} URL of the stored image.
 * @throws {Error} When the upload fails or the response has no URL.
 */
async function uploadImage(file, postId) {
  const formData = new FormData();
  formData.append('file', file);
  if (postId) formData.append('post_id', postId);

  const resp = await fetch('/api/upload', { method: 'POST', body: formData });
  if (!resp.ok) throw new Error('upload failed');
  const data = await resp.json();
  if (!data.url) throw new Error('no url in response');
  return data.url;
}

// ── 색상 적용 / 제거 ───────────────────────────────────────
/**
 * Colour the selected text: replace any text_color mark on the selection
 * with one of `color`, in a single ProseMirror transaction.
 *
 * @param {Editor} editor - Milkdown editor.
 * @param {string} color - CSS colour.
 * @returns {void}
 */
function applyColor(editor, color) {
  editor.action((ctx) => {
    const view = ctx.get(editorViewCtx);
    const { state } = view;
    const markType = state.schema.marks['text_color'];
    if (!markType || state.selection.empty) return;
    const { from, to } = state.selection;
    const tr = state.tr
      .removeMark(from, to, markType)
      .addMark(from, to, markType.create({ color }));
    view.dispatch(tr);
  });
}

/**
 * Remove the text colour from the selected text.
 *
 * @param {Editor} editor - Milkdown editor.
 * @returns {void}
 */
function removeColor(editor) {
  editor.action((ctx) => {
    const view = ctx.get(editorViewCtx);
    const { state } = view;
    const markType = state.schema.marks['text_color'];
    if (!markType || state.selection.empty) return;
    view.dispatch(state.tr.removeMark(state.selection.from, state.selection.to, markType));
  });
}

// ── 플로팅 색상 툴바 ───────────────────────────────────────
const PRESET_COLORS = [
  '#ef4444', '#f97316', '#eab308', '#22c55e', '#3b82f6',
  '#8b5cf6', '#ec4899', '#06b6d4', '#000000', '#6b7280',
];

/**
 * Build the floating colour toolbar (preset swatches, custom colour, remove)
 * and append it to <body>, hidden.
 *
 * Swatches apply on mousedown so the editor keeps its selection.
 *
 * @param {Editor} editor - Milkdown editor the toolbar colours.
 * @returns {HTMLDivElement} The toolbar (#text-color-toolbar).
 */
function createColorToolbar(editor) {
  const toolbar = document.createElement('div');
  toolbar.id = 'text-color-toolbar';
  toolbar.className = 'md-color-toolbar';

  PRESET_COLORS.forEach((color) => {
    const swatch = document.createElement('button');
    swatch.type = 'button';
    swatch.title = color;
    swatch.className = 'md-color-swatch';
    swatch.style.setProperty('--swatch-color', color);
    swatch.addEventListener('mouseenter', () => {
      swatch.classList.add('md-color-swatch-hover');
    });
    swatch.addEventListener('mouseleave', () => {
      // 한 번 올렸다 뗀 스와치는 scale(1)·투명 테두리 상태로 남는다 (예전 인라인 스타일과 동일)
      swatch.classList.remove('md-color-swatch-hover');
      swatch.classList.add('md-color-swatch-rest');
    });
    swatch.addEventListener('mousedown', (e) => {
      e.preventDefault();
      applyColor(editor, color);
    });
    toolbar.appendChild(swatch);
  });

  const sep = document.createElement('div');
  sep.className = 'md-color-sep';
  toolbar.appendChild(sep);

  const customInput = document.createElement('input');
  customInput.type = 'color';
  customInput.title = '사용자 지정 색상';
  customInput.className = 'md-color-custom';
  customInput.addEventListener('input', (e) => applyColor(editor, e.target.value));
  toolbar.appendChild(customInput);

  const removeBtn = document.createElement('button');
  removeBtn.type = 'button';
  removeBtn.title = '색상 제거';
  removeBtn.innerHTML = '✕';
  removeBtn.className = 'md-color-remove';
  removeBtn.addEventListener('mousedown', (e) => {
    e.preventDefault();
    removeColor(editor);
  });
  toolbar.appendChild(removeBtn);

  document.body.appendChild(toolbar);
  return toolbar;
}

/**
 * Show the colour toolbar centred above the current selection, kept inside
 * the viewport, or hide it when there is no visible selection.
 *
 * @param {HTMLDivElement} toolbar - The colour toolbar.
 * @returns {void}
 */
function positionToolbar(toolbar) {
  const sel = window.getSelection();
  if (!sel || sel.isCollapsed || sel.rangeCount === 0) {
    toolbar.classList.remove('md-color-toolbar-open');
    return;
  }
  const range = sel.getRangeAt(0);
  const rect = range.getBoundingClientRect();
  if (!rect.width && !rect.height) { toolbar.classList.remove('md-color-toolbar-open'); return; }

  toolbar.classList.add('md-color-toolbar-open');
  const tbRect = toolbar.getBoundingClientRect();
  let top = rect.top + window.scrollY - tbRect.height - 8;
  let left = rect.left + window.scrollX + rect.width / 2 - tbRect.width / 2;
  top = Math.max(8, top);
  left = Math.max(8, Math.min(left, window.innerWidth - tbRect.width - 8));
  toolbar.style.top = `${top}px`; // conventions: allow (follows the text selection)
  toolbar.style.left = `${left}px`; // conventions: allow (follows the text selection)
}

// ── 메인 ──────────────────────────────────────────────────
/**
 * Entry point: create the Crepe (Milkdown) editor, load the post's saved HTML
 * (#initial-content) with colour marks intact, then wire the colour toolbar,
 * image paste/drop and the update form (the editor HTML goes into #content and
 * #content_html).
 *
 * @returns {Promise<void>} Resolves once the editor is ready and wired.
 */
async function main() {
  const root = document.getElementById('editor-root');
  if (!root) return;

  const postId = root.dataset.postId || null;

  // content_html (HTML) 을 초기값으로 사용
  const initialScript = document.getElementById('initial-content');
  let initialHtml = '';
  if (initialScript && initialScript.textContent) {
    try {
      initialHtml = JSON.parse(initialScript.textContent);
    } catch (e) {
      console.error('Failed to parse initial content JSON', e);
    }
  }

  const crepe = new Crepe({
    root,
    defaultValue: '',
    featureConfigs: {
      [Crepe.Feature.ImageBlock]: {
        onUpload: (file) => uploadImage(file, postId),
      },
    },
  });

  crepe.editor.use(textColorPlugin);
  await crepe.create();
  const editor = crepe.editor;

  // HTML 을 ProseMirror DOMParser 로 로드 (색상 marks 포함)
  if (initialHtml) {
    editor.action((ctx) => {
      const view = ctx.get(editorViewCtx);
      const div = document.createElement('div');
      div.innerHTML = initialHtml;
      const parser = ProseDOMParser.fromSchema(view.state.schema);
      const doc = parser.parse(div);
      const tr = view.state.tr.replaceWith(0, view.state.doc.content.size, doc.content);
      view.dispatch(tr);
    });
  }

  // 플로팅 색상 툴바
  const colorToolbar = createColorToolbar(editor);

  document.addEventListener('selectionchange', () => {
    const sel = window.getSelection();
    const editorEl = root.querySelector('.ProseMirror');
    if (sel && !sel.isCollapsed && editorEl && editorEl.contains(sel.anchorNode)) {
      requestAnimationFrame(() => positionToolbar(colorToolbar));
    } else {
      colorToolbar.classList.remove('md-color-toolbar-open');
    }
  });

  document.addEventListener('mousedown', (e) => {
    if (!colorToolbar.contains(e.target)) colorToolbar.classList.remove('md-color-toolbar-open');
  });

  // 붙여넣기 이미지
  root.addEventListener('paste', async (event) => {
    const clipboard = event.clipboardData;
    if (!clipboard?.files?.length) return;
    const file = clipboard.files[0];
    if (!file.type.startsWith('image/')) return;
    event.preventDefault();
    try {
      const url = await uploadImage(file, postId);
      editor.action(insert(`\n\n![image](${url})\n`));
    } catch (e) {
      console.error(e);
      alert('이미지 업로드에 실패했습니다.');
    }
  });

  // 드래그 & 드랍
  root.addEventListener('dragover', (e) => e.preventDefault());
  root.addEventListener('drop', async (event) => {
    event.preventDefault();
    const file = event.dataTransfer?.files?.[0];
    if (!file?.type.startsWith('image/')) return;
    try {
      const url = await uploadImage(file, postId);
      editor.action(insert(`\n\n![image](${url})\n`));
    } catch (e) {
      console.error(e);
      alert('이미지 업로드에 실패했습니다.');
    }
  });

  // 폼 제출 — getHTML() 만 사용 (getMarkdown 사용 안 함)
  const form = document.getElementById('post-form');
  if (!form) return;

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const contentInput = document.getElementById('content');
    const contentHtmlInput = document.getElementById('content_html');
    if (!contentInput || !contentHtmlInput) return;

    const html = editor.action(getHTML());
    contentInput.value = html;
    contentHtmlInput.value = html;

    form.submit();
  });
}

main();
