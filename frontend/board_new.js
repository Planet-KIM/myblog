/**
 * @file frontend/board_new.js — Markdown (Milkdown/Crepe) editor for a new post
 * (templates/board_new_clean.html).
 *
 * Adds image upload (picker, paste, drop) under the current draft, a floating
 * text-colour toolbar for selections, and fills the publish form with the
 * editor HTML. Built by Vite into static/editor/board_new.js; the toolbar's
 * looks live in static/css/writing-enhanced.css.
 */
import '@milkdown/crepe/theme/common/style.css';
import '@milkdown/crepe/theme/frame.css';

import { Crepe } from '@milkdown/crepe';
import { insert, getHTML } from '@milkdown/utils';
import { editorViewCtx } from '@milkdown/core';
import { textColorPlugin } from './plugins/textColor.js';

// ── 이미지 업로드 ──────────────────────────────────────────
/**
 * Upload an image file and return its public URL.
 *
 * The server files it under the current draft (window.DRAFT_ID) so it can be
 * moved into the post's folder when the post is published.
 *
 * @param {File} file - Image picked, dropped or pasted by the user.
 * @returns {Promise<string>} URL of the stored image.
 * @throws {Error} When the upload fails or the response has no URL.
 */
async function uploadImage(file) {
  const formData = new FormData();
  formData.append('file', file);

  const draftId = window.DRAFT_ID || null;
  if (draftId) {
    formData.append('draft_id', draftId);
  }

  const resp = await fetch('/api/upload', { method: 'POST', body: formData });
  if (!resp.ok) throw new Error('upload failed');
  const data = await resp.json();
  if (!data.url) throw new Error('no url in response');
  return data.url;
}

// ── 이미지 height 마크다운 주입 ────────────────────────────
/**
 * Copy image heights from the editor HTML into the Markdown as `{height="N"}`.
 *
 * Images already followed by an attribute block are left alone.
 *
 * @param {string} markdown - Markdown source.
 * @param {string} html - Rendered editor HTML (.milkdown-image-block img).
 * @returns {string} Markdown with height attributes added.
 */
function injectImageSizesIntoMarkdown(markdown, html) {
  const parser = new DOMParser();
  const doc = parser.parseFromString(html, 'text/html');
  const images = doc.querySelectorAll('.milkdown-image-block img');
  let updated = markdown;

  images.forEach((img) => {
    const src = img.getAttribute('src');
    if (!src) return;
    let h = img.style.height || img.getAttribute('data-height');
    if (!h) return;
    let numeric = parseFloat(h);
    if (Number.isNaN(numeric) || numeric <= 0) return;
    const escSrc = src.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const pattern = new RegExp(`(\\!\\[[^\\]]*\\]\\(${escSrc}\\))(?!\\{)`, 'g');
    updated = updated.replace(pattern, `$1{height="${numeric}"}`);
  });

  return updated;
}

// ── 플로팅 색상 툴바 ───────────────────────────────────────
const PRESET_COLORS = [
  '#ef4444', // red
  '#f97316', // orange
  '#eab308', // yellow
  '#22c55e', // green
  '#3b82f6', // blue
  '#8b5cf6', // purple
  '#ec4899', // pink
  '#06b6d4', // cyan
  '#000000', // black
  '#6b7280', // gray
];

// 에디터 뷰에서 직접 ProseMirror 트랜잭션으로 색상 적용
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
    const { from, to } = state.selection;
    view.dispatch(state.tr.removeMark(from, to, markType));
  });
}

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

  // 프리셋 색상 스와치
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
      e.preventDefault(); // 에디터 선택 유지
      applyColor(editor, color);
    });
    toolbar.appendChild(swatch);
  });

  // 구분선
  const sep = document.createElement('div');
  sep.className = 'md-color-sep';
  toolbar.appendChild(sep);

  // 커스텀 색상 인풋
  const customInput = document.createElement('input');
  customInput.type = 'color';
  customInput.title = '사용자 지정 색상';
  customInput.className = 'md-color-custom';
  customInput.addEventListener('input', (e) => {
    applyColor(editor, e.target.value);
  });
  toolbar.appendChild(customInput);

  // 색상 제거 버튼
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
  if (!rect.width && !rect.height) {
    toolbar.classList.remove('md-color-toolbar-open');
    return;
  }

  toolbar.classList.add('md-color-toolbar-open');

  // 선택 영역 위에 표시 (화면 밖으로 나가지 않도록 clamp)
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
 * Entry point: create the Crepe (Milkdown) editor with image upload and the
 * text-colour plugin, then wire the colour toolbar, image paste/drop and the
 * publish form (the editor HTML goes into #content and #content_html).
 *
 * @returns {Promise<void>} Resolves once the editor is ready and wired.
 */
async function main() {
  const root = document.getElementById('editor-root');
  if (!root) return;

  const crepe = new Crepe({
    root,
    // 새 글은 빈 상태로 시작한다 (샘플 문구/코드 자동 삽입 제거).
    defaultValue: '',
    featureConfigs: {
      [Crepe.Feature.ImageBlock]: { onUpload: uploadImage },
    },
  });

  // 텍스트 색상 플러그인 등록 (create() 전에!)
  crepe.editor.use(textColorPlugin);

  await crepe.create();
  const editor = crepe.editor;

  // 플로팅 색상 툴바 생성
  const colorToolbar = createColorToolbar(editor);

  // 선택 변경 시 툴바 위치 업데이트
  document.addEventListener('selectionchange', () => {
    const sel = window.getSelection();
    const editorEl = root.querySelector('.ProseMirror');

    // 에디터 내부 선택인지 확인
    if (
      sel &&
      !sel.isCollapsed &&
      editorEl &&
      editorEl.contains(sel.anchorNode)
    ) {
      // 약간의 딜레이로 selection rect가 확정된 후 위치 계산
      requestAnimationFrame(() => positionToolbar(colorToolbar));
    } else {
      colorToolbar.classList.remove('md-color-toolbar-open');
    }
  });

  // 클릭이 툴바 밖이면 숨김
  document.addEventListener('mousedown', (e) => {
    if (!colorToolbar.contains(e.target)) {
      colorToolbar.classList.remove('md-color-toolbar-open');
    }
  });

  // 붙여넣기 이미지 업로드
  root.addEventListener('paste', async (event) => {
    const clipboard = event.clipboardData;
    if (!clipboard?.files?.length) return;
    const file = clipboard.files[0];
    if (!file.type.startsWith('image/')) return;
    event.preventDefault();
    try {
      const url = await uploadImage(file);
      editor.action(insert(`\n\n![image](${url})\n`));
    } catch (e) {
      console.error(e);
      alert('이미지 업로드에 실패했습니다.');
    }
  });

  // 드래그 & 드랍 이미지 업로드
  root.addEventListener('dragover', (e) => e.preventDefault());
  root.addEventListener('drop', async (event) => {
    event.preventDefault();
    const file = event.dataTransfer?.files?.[0];
    if (!file?.type.startsWith('image/')) return;
    try {
      const url = await uploadImage(file);
      editor.action(insert(`\n\n![image](${url})\n`));
    } catch (e) {
      console.error(e);
      alert('이미지 업로드에 실패했습니다.');
    }
  });

  // 폼 제출 시 content 저장
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
