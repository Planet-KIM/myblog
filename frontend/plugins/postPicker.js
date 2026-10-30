/**
 * @file The "글 연결" dialog shared by the Markdown and magazine editors:
 * search the posts the writer may link to (GET /api/posts/link-targets: title or
 * body text, or a pasted post URL; empty lists the writer's latest posts) and
 * pick one with the mouse or the arrow keys + Enter. Looks: static/css/post-link.css
 * (.post-picker).
 */

const SEARCH_URL = '/api/posts/link-targets';
const SEARCH_DELAY_MS = 200;

/**
 * Create an element with a class and optional text.
 *
 * @param {string} tag - Tag name.
 * @param {string} className - Class attribute.
 * @param {string} [text] - Text content.
 * @returns {HTMLElement} The element.
 */
function el(tag, className, text) {
  const node = document.createElement(tag);
  node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

/**
 * Build the (closed) picker dialog.
 *
 * @returns {{dialog: HTMLDialogElement, input: HTMLInputElement, list: HTMLUListElement, close: HTMLButtonElement}}
 *   The dialog and the parts the picker drives.
 */
function buildDialog() {
  const dialog = el('dialog', 'post-picker');
  dialog.setAttribute('aria-label', '글 연결');
  const form = el('div', 'post-picker-form');
  const head = el('div', 'post-picker-head');
  head.appendChild(el('h2', 'post-picker-title', '글 연결'));
  const close = el('button', 'post-picker-close');
  close.type = 'button';
  close.setAttribute('aria-label', '닫기');
  close.innerHTML = '<i class="bi bi-x-lg"></i>';
  head.appendChild(close);
  const input = el('input', 'post-picker-search');
  input.type = 'search';
  input.placeholder = '제목이나 내용으로 찾기, 또는 글 주소 붙여넣기';
  input.setAttribute('aria-label', '연결할 글 찾기');
  const hint = el('p', 'post-picker-hint', '고른 글은 본문에 카드로 들어갑니다.');
  const list = el('ul', 'post-picker-list');
  list.setAttribute('role', 'listbox');
  form.append(head, input, hint, list);
  dialog.appendChild(form);
  return { dialog, input, list, close };
}

/**
 * Fetch the posts matching a search.
 *
 * @param {string} q - Search text.
 * @param {?(number|string)} excludeId - Post left out of the results.
 * @returns {Promise<Array<{id:number,title:string,author:string,date:string,private:boolean,mine:boolean}>>}
 *   Matching posts, newest first.
 */
async function searchPosts(q, excludeId) {
  const params = new URLSearchParams({ q });
  if (excludeId) params.set('exclude', String(excludeId));
  const resp = await fetch(`${SEARCH_URL}?${params}`, { credentials: 'same-origin' });
  if (!resp.ok) throw new Error(`search failed: ${resp.status}`);
  return resp.json();
}

/**
 * One result row: title on top, author · date (· 비공개) below.
 *
 * @param {{title:string,author:string,date:string,private:boolean}} post - A search result.
 * @returns {HTMLLIElement} The row with its button.
 */
function resultRow(post) {
  const li = document.createElement('li');
  const btn = el('button', 'post-picker-item');
  btn.type = 'button';
  btn.setAttribute('role', 'option');
  btn.appendChild(el('span', 'post-picker-item-title', post.title));
  const meta = [post.author, post.date, post.private ? '비공개' : ''].filter(Boolean).join(' · ');
  btn.appendChild(el('span', 'post-picker-item-meta', meta));
  li.appendChild(btn);
  return li;
}

/**
 * Open the post picker and wait for the writer's choice.
 *
 * Key presses inside the dialog do not reach the editor's own shortcuts
 * (Delete removing a block, Ctrl+Z, ...).
 *
 * @param {Object} [opts] - Options.
 * @param {?(number|string)} [opts.excludeId] - Post being edited, not offered.
 * @returns {Promise<?{id:number, title:string}>} The chosen post, or null when the dialog was closed.
 */
export function openPostPicker({ excludeId = null } = {}) {
  return new Promise(resolve => {
    const { dialog, input, list, close } = buildDialog();
    let results = [];
    let active = 0;
    let chosen = null;
    let timer = 0;
    let seq = 0;

    /** Close the dialog with ``post`` as the answer. */
    const choose = post => { chosen = post; dialog.close(); };

    /**
     * Mark the highlighted row (arrow keys) and keep it in view.
     *
     * @returns {void}
     */
    function highlight() {
      list.querySelectorAll('.post-picker-item').forEach((btn, i) => {
        btn.setAttribute('aria-selected', String(i === active));
        if (i === active) btn.scrollIntoView({ block: 'nearest' });
      });
    }

    /**
     * Show the current results, or a short message when there are none.
     *
     * @param {string} [message] - Text shown instead of results.
     * @returns {void}
     */
    function render(message) {
      list.replaceChildren();
      if (message || !results.length) {
        list.appendChild(el('li', 'post-picker-empty', message || (input.value.trim() ? '찾는 글이 없습니다.' : '아직 쓴 글이 없습니다.')));
        return;
      }
      results.forEach((post, i) => {
        const row = resultRow(post);
        row.firstChild.addEventListener('click', () => choose({ id: post.id, title: post.title }));
        row.firstChild.addEventListener('mouseenter', () => { active = i; highlight(); });
        list.appendChild(row);
      });
      highlight();
    }

    /**
     * Search with the current text; answers to older searches are dropped.
     *
     * @returns {Promise<void>} Resolves once the list is updated.
     */
    async function search() {
      const mine = ++seq;
      try {
        const found = await searchPosts(input.value.trim(), excludeId);
        if (mine !== seq) return;
        results = found;
        active = 0;
        render();
      } catch {
        if (mine === seq) render('글을 불러오지 못했습니다.');
      }
    }

    input.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(search, SEARCH_DELAY_MS); });
    input.addEventListener('keydown', e => {
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        if (!results.length) return;
        active = (active + (e.key === 'ArrowDown' ? 1 : -1) + results.length) % results.length;
        highlight();
      } else if (e.key === 'Enter') {
        e.preventDefault();
        if (results[active]) choose({ id: results[active].id, title: results[active].title });
      }
    });
    dialog.addEventListener('keydown', e => e.stopPropagation());
    dialog.addEventListener('click', e => { if (e.target === dialog) dialog.close(); });   // 바깥(배경) 클릭
    close.addEventListener('click', () => dialog.close());
    dialog.addEventListener('close', () => { clearTimeout(timer); dialog.remove(); resolve(chosen); });

    document.body.appendChild(dialog);
    dialog.showModal();
    input.focus();
    search();
  });
}
