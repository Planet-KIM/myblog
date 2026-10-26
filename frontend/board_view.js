/**
 * @file frontend/board_view.js — Read-only Crepe (Milkdown) viewer for a
 * Markdown post: renders the Markdown in #initial-content into #viewer-root.
 * Built by Vite into static/editor/board_view.js.
 */
import '@milkdown/crepe/theme/common/style.css';
import '@milkdown/crepe/theme/frame.css';
import { Crepe } from '@milkdown/crepe';

/**
 * Entry point: render the post's Markdown read-only (no toolbars or editing;
 * layout and image sizes as saved).
 *
 * @returns {Promise<void>} Resolves once the viewer is ready.
 */
async function main() {
  const root = document.getElementById('viewer-root');
  if (!root) return;

  // 서버에서 넘겨준 markdown 원문 읽기
  const initialScript = document.getElementById('initial-content');
  let markdown = '';
  if (initialScript && initialScript.textContent) {
    try {
      markdown = JSON.parse(initialScript.textContent);
    } catch (e) {
      console.error('Failed to parse initial markdown JSON', e);
    }
  }

  const crepe = new Crepe({
    root,
    defaultValue: markdown,
  });

  await crepe.create();
  // 읽기 전용 모드로 전환 (툴바/편집 막고, 레이아웃/리사이즈는 그대로)
  crepe.setReadonly(true);
}

main();

