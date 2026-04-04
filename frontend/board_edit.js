// frontend/board_edit.js
import '@milkdown/crepe/theme/common/style.css';
import '@milkdown/crepe/theme/frame.css';

import { Crepe } from '@milkdown/crepe';
import { insert, getHTML } from '@milkdown/utils';
import { editorViewCtx } from '@milkdown/core';
import { DOMParser as ProseDOMParser } from 'prosemirror-model';
import { textColorPlugin } from './plugins/textColor.js';

// ── 이미지 업로드 ──────────────────────────────────────────
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

function createColorToolbar(editor) {
  const toolbar = document.createElement('div');
  toolbar.id = 'text-color-toolbar';
  toolbar.style.cssText = `
    position: fixed; display: none; align-items: center; gap: 4px;
    background: white; border: 1px solid #e5e7eb; border-radius: 8px;
    padding: 6px 8px; box-shadow: 0 4px 16px rgba(0,0,0,0.12);
    z-index: 9999; pointer-events: all;
  `;

  PRESET_COLORS.forEach((color) => {
    const swatch = document.createElement('button');
    swatch.type = 'button';
    swatch.title = color;
    swatch.style.cssText = `
      width: 18px; height: 18px; border-radius: 50%;
      border: 2px solid transparent; background: ${color};
      cursor: pointer; transition: transform 0.1s, border-color 0.1s; flex-shrink: 0;
    `;
    swatch.addEventListener('mouseenter', () => {
      swatch.style.transform = 'scale(1.25)';
      swatch.style.borderColor = '#9ca3af';
    });
    swatch.addEventListener('mouseleave', () => {
      swatch.style.transform = 'scale(1)';
      swatch.style.borderColor = 'transparent';
    });
    swatch.addEventListener('mousedown', (e) => {
      e.preventDefault();
      applyColor(editor, color);
    });
    toolbar.appendChild(swatch);
  });

  const sep = document.createElement('div');
  sep.style.cssText = 'width:1px; height:18px; background:#e5e7eb; margin: 0 2px;';
  toolbar.appendChild(sep);

  const customInput = document.createElement('input');
  customInput.type = 'color';
  customInput.title = '사용자 지정 색상';
  customInput.style.cssText = `
    width: 22px; height: 22px; border: 2px solid #e5e7eb;
    border-radius: 4px; padding: 0; cursor: pointer; background: none;
  `;
  customInput.addEventListener('input', (e) => applyColor(editor, e.target.value));
  toolbar.appendChild(customInput);

  const removeBtn = document.createElement('button');
  removeBtn.type = 'button';
  removeBtn.title = '색상 제거';
  removeBtn.innerHTML = '✕';
  removeBtn.style.cssText = `
    width: 22px; height: 22px; border: 1px solid #e5e7eb; border-radius: 4px;
    background: white; color: #6b7280; font-size: 11px; cursor: pointer;
    display: flex; align-items: center; justify-content: center; line-height: 1;
  `;
  removeBtn.addEventListener('mousedown', (e) => {
    e.preventDefault();
    removeColor(editor);
  });
  toolbar.appendChild(removeBtn);

  document.body.appendChild(toolbar);
  return toolbar;
}

function positionToolbar(toolbar) {
  const sel = window.getSelection();
  if (!sel || sel.isCollapsed || sel.rangeCount === 0) {
    toolbar.style.display = 'none';
    return;
  }
  const range = sel.getRangeAt(0);
  const rect = range.getBoundingClientRect();
  if (!rect.width && !rect.height) { toolbar.style.display = 'none'; return; }

  toolbar.style.display = 'flex';
  const tbRect = toolbar.getBoundingClientRect();
  let top = rect.top + window.scrollY - tbRect.height - 8;
  let left = rect.left + window.scrollX + rect.width / 2 - tbRect.width / 2;
  top = Math.max(8, top);
  left = Math.max(8, Math.min(left, window.innerWidth - tbRect.width - 8));
  toolbar.style.top = `${top}px`;
  toolbar.style.left = `${left}px`;
}

// ── 메인 ──────────────────────────────────────────────────
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
      colorToolbar.style.display = 'none';
    }
  });

  document.addEventListener('mousedown', (e) => {
    if (!colorToolbar.contains(e.target)) colorToolbar.style.display = 'none';
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
