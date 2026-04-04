// frontend/board_new.js
import '@milkdown/crepe/theme/common/style.css';
import '@milkdown/crepe/theme/frame.css';

import { Crepe } from '@milkdown/crepe';
import { insert, getHTML } from '@milkdown/utils';
import { editorViewCtx } from '@milkdown/core';
import { textColorPlugin } from './plugins/textColor.js';

// ── 이미지 업로드 ──────────────────────────────────────────
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
    const { from, to } = state.selection;
    view.dispatch(state.tr.removeMark(from, to, markType));
  });
}

function createColorToolbar(editor) {
  const toolbar = document.createElement('div');
  toolbar.id = 'text-color-toolbar';
  toolbar.style.cssText = `
    position: fixed;
    display: none;
    align-items: center;
    gap: 4px;
    background: white;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    padding: 6px 8px;
    box-shadow: 0 4px 16px rgba(0,0,0,0.12);
    z-index: 9999;
    pointer-events: all;
  `;

  // 프리셋 색상 스와치
  PRESET_COLORS.forEach((color) => {
    const swatch = document.createElement('button');
    swatch.type = 'button';
    swatch.title = color;
    swatch.style.cssText = `
      width: 18px; height: 18px;
      border-radius: 50%;
      border: 2px solid transparent;
      background: ${color};
      cursor: pointer;
      transition: transform 0.1s, border-color 0.1s;
      flex-shrink: 0;
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
      e.preventDefault(); // 에디터 선택 유지
      applyColor(editor, color);
    });
    toolbar.appendChild(swatch);
  });

  // 구분선
  const sep = document.createElement('div');
  sep.style.cssText = 'width:1px; height:18px; background:#e5e7eb; margin: 0 2px;';
  toolbar.appendChild(sep);

  // 커스텀 색상 인풋
  const customInput = document.createElement('input');
  customInput.type = 'color';
  customInput.title = '사용자 지정 색상';
  customInput.style.cssText = `
    width: 22px; height: 22px;
    border: 2px solid #e5e7eb;
    border-radius: 4px;
    padding: 0;
    cursor: pointer;
    background: none;
  `;
  customInput.addEventListener('input', (e) => {
    applyColor(editor, e.target.value);
  });
  toolbar.appendChild(customInput);

  // 색상 제거 버튼
  const removeBtn = document.createElement('button');
  removeBtn.type = 'button';
  removeBtn.title = '색상 제거';
  removeBtn.innerHTML = '✕';
  removeBtn.style.cssText = `
    width: 22px; height: 22px;
    border: 1px solid #e5e7eb;
    border-radius: 4px;
    background: white;
    color: #6b7280;
    font-size: 11px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    line-height: 1;
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
  if (!rect.width && !rect.height) {
    toolbar.style.display = 'none';
    return;
  }

  toolbar.style.display = 'flex';

  // 선택 영역 위에 표시 (화면 밖으로 나가지 않도록 clamp)
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

  const crepe = new Crepe({
    root,
    defaultValue: '# 제목 예시\n\n여기에 내용을 작성하세요.\n\n```python\nprint("hello world")\n```',
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
      colorToolbar.style.display = 'none';
    }
  });

  // 클릭이 툴바 밖이면 숨김
  document.addEventListener('mousedown', (e) => {
    if (!colorToolbar.contains(e.target)) {
      colorToolbar.style.display = 'none';
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
