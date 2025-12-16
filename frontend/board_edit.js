// frontend/board_edit.js
import '@milkdown/crepe/theme/common/style.css';
import '@milkdown/crepe/theme/frame.css';

import { Crepe } from '@milkdown/crepe';
import { insert, getHTML } from '@milkdown/utils';

// 🔥 postId 를 추가로 받도록 변경
async function uploadImage(file, postId) {
  const formData = new FormData();
  formData.append('file', file);
  if (postId) {
    formData.append('post_id', postId);
  }

  const resp = await fetch('/api/images', {
    method: 'POST',
    body: formData,
  });

  if (!resp.ok) {
    console.error('Image upload failed', await resp.text());
    throw new Error('upload failed');
  }

  const data = await resp.json();
  if (!data.url) throw new Error('no url in response');
  return data.url;
}

// board_new.js 와 동일한 유틸 함수
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
    const pattern = new RegExp(
      `(\\!\\[[^\\]]*\\]\\(${escSrc}\\))(?!\\{)`,
      'g'
    );

    updated = updated.replace(
      pattern,
      `$1{height="${numeric}"}`
    );
  });

  return updated;
}

async function main() {
  const root = document.getElementById('editor-root');
  if (!root) return;

  // 🔥 템플릿에서 data-post-id 로 넘어온 postId 사용
  const postId = root.dataset.postId || null;

  const initialScript = document.getElementById('initial-content');
  let initialMarkdown = '# 제목 예시';

  if (initialScript && initialScript.textContent) {
    try {
      initialMarkdown = JSON.parse(initialScript.textContent);
    } catch (e) {
      console.error('Failed to parse initial markdown JSON', e);
    }
  }

  const crepe = new Crepe({
    root,
    defaultValue: initialMarkdown,
    featureConfigs: {
      [Crepe.Feature.ImageBlock]: {
        // 🔥 이미지 블록의 onUpload 에도 postId 를 전달
        onUpload: (file) => uploadImage(file, postId),
      },
    },
  });

  await crepe.create();
  const editor = crepe.editor;

  // 붙여넣기에서 이미지 처리
  root.addEventListener('paste', async (event) => {
    const clipboard = event.clipboardData;
    if (!clipboard || !clipboard.files || clipboard.files.length === 0) return;

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

  // 드래그&드롭에서 이미지 처리
  root.addEventListener('dragover', (event) => event.preventDefault());
  root.addEventListener('drop', async (event) => {
    event.preventDefault();
    const dt = event.dataTransfer;
    if (!dt || !dt.files || dt.files.length === 0) return;

    const file = dt.files[0];
    if (!file.type.startsWith('image/')) return;

    try {
      const url = await uploadImage(file, postId);
      editor.action(insert(`\n\n![image](${url})\n`));
    } catch (e) {
      console.error(e);
      alert('이미지 업로드에 실패했습니다.');
    }
  });

  const form = document.getElementById('post-form');
  if (!form) return;

  form.addEventListener('submit', async () => {
    const contentInput = document.getElementById('content');
    const contentHtmlInput = document.getElementById('content_html');
    if (!contentInput || !contentHtmlInput) return;

    const rawMarkdown = await crepe.getMarkdown();
    const html = editor.action(getHTML());

    const markdownWithSizes = injectImageSizesIntoMarkdown(rawMarkdown, html);

    contentInput.value = markdownWithSizes;
    contentHtmlInput.value = html;
  });
}

main();

