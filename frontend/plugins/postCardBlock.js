/**
 * @file 글 카드 blocks for the magazine (TipTap) editors: pick a post in the
 * "글 연결" dialog (postPicker.js) and place its card as a block (type
 * "postcard", postId). The block shows the server-rendered card
 * (GET /board/<id>/card, templates/_post_card.html) and keeps it in
 * block.content, so the preview and the saved reading HTML include it; the post
 * page swaps in the current card when it is shown (app/services/post_links.py).
 * Looks: static/css/post-link.css (.fb-body-postcard).
 */
import { openPostPicker } from './postPicker.js';

// 새 카드 블록 크기 (페이지 좌표, px): 페이지에서는 제목 두 줄 + 미리보기 두 줄,
// 에디터(블록 머리줄만큼 낮다)에서는 미리보기 한 줄이 들어가는 높이
export const POST_CARD_SIZE = { w: 600, h: 180 };

/**
 * Fetch the card HTML of a post.
 *
 * @param {number|string} postId - The linked post.
 * @returns {Promise<string>} The card markup (the unavailable card when the writer cannot open it).
 * @throws {Error} When the request fails.
 */
export async function fetchPostCard(postId) {
  const resp = await fetch(`/board/${encodeURIComponent(postId)}/card`, { credentials: 'same-origin' });
  if (!resp.ok) throw new Error(`card request failed: ${resp.status}`);
  return resp.text();
}

/**
 * Ask for a post and add its card block.
 *
 * @param {function(string, Object): Object} addBlock - The editor's addBlock(type, opts).
 * @param {?(number|string)} [excludeId] - Post being edited, not offered.
 * @returns {Promise<?Object>} The new block, or null when the dialog was closed.
 */
export async function pickPostCard(addBlock, excludeId = null) {
  const post = await openPostPicker({ excludeId });
  if (!post) return null;
  let content = '';
  try { content = await fetchPostCard(post.id); } catch { /* 블록이 그려질 때 다시 불러온다 */ }
  return addBlock('postcard', { postId: post.id, content, ...POST_CARD_SIZE });
}

/**
 * Fill a card block's body: the saved card at once, then the current one.
 * Clicking the card does not follow its link while editing.
 *
 * @param {HTMLElement} body - The block's .fb-body.
 * @param {Object} block - The card block (postId, content).
 * @returns {void}
 */
export function renderPostCardBody(body, block) {
  body.classList.add('fb-body-postcard');
  body.innerHTML = block.content || '<div class="fb-postcard-loading">카드를 불러오는 중…</div>';
  body.addEventListener('click', e => e.preventDefault());
  if (!block.postId) return;
  fetchPostCard(block.postId)
    .then(html => { block.content = html; body.innerHTML = html; })
    .catch(() => {});
}
