// frontend/board_new.js
// ★ CSS를 JS에서 import
import '@milkdown/crepe/theme/common/style.css';
import '@milkdown/crepe/theme/frame.css';

import { Crepe } from '@milkdown/crepe';
import { insert, getHTML } from '@milkdown/utils';

// 이미지 업로드 API
async function uploadImage(file) {
  const formData = new FormData();
  formData.append('file', file);

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

// 마크다운 문자열과 HTML 문자열을 받아서
// .milkdown-image-block img 의 height를 읽어
// 대응되는 마크다운 이미지에 {height="..."} 추가
function injectImageSizesIntoMarkdown(markdown, html) {
  const parser = new DOMParser();
  const doc = parser.parseFromString(html, 'text/html');
  const images = doc.querySelectorAll('.milkdown-image-block img');

  let updated = markdown;

  images.forEach((img) => {
    const src = img.getAttribute('src');
    if (!src) return;

    // style.height 또는 data-height 중 하나를 사용
    let h = img.style.height || img.getAttribute('data-height');
    if (!h) return;

    let numeric = parseFloat(h);
    if (Number.isNaN(numeric) || numeric <= 0) return;

    // src 를 정규식에서 쓸 수 있게 escape
    const escSrc = src.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

    // ![alt](src) 뒤에 아직 { 가 붙어있지 않은 경우만 치환
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

  const crepe = new Crepe({
    root,
    defaultValue: '# 제목 예시\n\n여기에 내용을 작성하세요.\n\n```python\nprint("hello world")\n```',
    featureConfigs: {
      [Crepe.Feature.ImageBlock]: {
        onUpload: uploadImage,
      },
    },
  });

  await crepe.create();
  const editor = crepe.editor;

  // 붙여넣기 시 이미지 업로드
  root.addEventListener('paste', async (event) => {
    const clipboard = event.clipboardData;
    if (!clipboard || !clipboard.files || clipboard.files.length === 0) return;

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

  // 드래그 & 드랍 업로드
  root.addEventListener('dragover', (event) => event.preventDefault());
  root.addEventListener('drop', async (event) => {
    event.preventDefault();
    const dt = event.dataTransfer;
    if (!dt || !dt.files || dt.files.length === 0) return;

    const file = dt.files[0];
    if (!file.type.startsWith('image/')) return;

    try {
      const url = await uploadImage(file);
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

    // 🔥 이미지 height 정보를 마크다운에 주입
    const markdownWithSizes = injectImageSizesIntoMarkdown(rawMarkdown, html);

    contentInput.value = markdownWithSizes;
    contentHtmlInput.value = html;
  });
}

main();

