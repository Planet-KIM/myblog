/**
 * @file 글 카드 lines for the Markdown (Milkdown) editors. A paragraph that holds
 * nothing but one link to a post on this site becomes a card on the post page
 * (app/services/post_links.py); while writing it is marked .md-post-card-line
 * (static/css/post-link.css) so the writer can tell it apart from a plain link.
 * Also inserts such a line for a post picked in the "글 연결" dialog, from the
 * toolbar button marked data-post-link.
 */
import { $prose } from '@milkdown/utils';
import { editorViewCtx } from '@milkdown/core';
import { Plugin, PluginKey, TextSelection } from '@milkdown/prose/state';
import { Decoration, DecorationSet } from '@milkdown/prose/view';
import { openPostPicker } from './postPicker.js';

const POST_PATH = /^\/board\/(\d+)\/?$/;

/**
 * Tell which post a link points to (same rule as the server: /board/<id> on
 * this site, any port; a query or fragment is ignored).
 *
 * @param {string} href - Link target.
 * @returns {?number} The post id, or null for any other link.
 */
export function postIdFromHref(href) {
  try {
    const url = new URL(href, window.location.origin);
    if (!['http:', 'https:'].includes(url.protocol) || url.hostname !== window.location.hostname) return null;
    const match = POST_PATH.exec(url.pathname);
    return match ? Number(match[1]) : null;
  } catch {
    return null;
  }
}

/**
 * Tell whether a paragraph is a card line: apart from blank text and a line
 * break, it holds only text that links to one and the same post.
 *
 * @param {import('prosemirror-model').Node} node - A paragraph node.
 * @returns {boolean} True for a card line.
 */
function isCardLine(node) {
  let href = null;
  let ok = true;
  node.forEach(child => {
    if (!ok) return;
    if (child.type.name === 'hardbreak' || (child.isText && !child.text.trim())) return;
    const link = child.isText && child.marks.find(m => m.type.name === 'link');
    if (!link || (href !== null && link.attrs.href !== href)) { ok = false; return; }
    href = link.attrs.href;
  });
  return ok && href !== null && postIdFromHref(href) !== null;
}

/**
 * Decorations marking every card line in a document.
 *
 * @param {import('prosemirror-model').Node} doc - The editor document.
 * @returns {DecorationSet} One node decoration per card line.
 */
function cardLineDecorations(doc) {
  const decorations = [];
  doc.descendants((node, pos) => {
    if (node.type.name !== 'paragraph') return true;
    if (isCardLine(node)) decorations.push(Decoration.node(pos, pos + node.nodeSize, { class: 'md-post-card-line' }));
    return false;
  });
  return DecorationSet.create(doc, decorations);
}

/** Milkdown plugin: keeps the card-line marks up to date as the writer types. */
export const postCardLinePlugin = $prose(() => new Plugin({
  key: new PluginKey('post-card-line'),
  state: {
    init: (_, { doc }) => cardLineDecorations(doc),
    apply: (tr, old) => (tr.docChanged ? cardLineDecorations(tr.doc) : old),
  },
  props: {
    decorations(state) { return this.getState(state); },
  },
}));

/**
 * Insert a card line for a post as its own paragraph (in place of an empty
 * line at the cursor, else after the cursor's line), followed by an empty
 * paragraph that takes the cursor, so further typing never extends the link.
 *
 * @param {import('@milkdown/core').Editor} editor - The Milkdown editor.
 * @param {{id:number, title:string}} post - The post picked in the dialog.
 * @returns {void}
 */
export function insertPostCardLine(editor, post) {
  editor.action(ctx => {
    const view = ctx.get(editorViewCtx);
    const { state } = view;
    const { schema, selection } = state;
    const link = schema.marks.link.create({ href: `/board/${post.id}` });
    const line = schema.nodes.paragraph.create(null, schema.text(post.title, [link]));
    const next = schema.nodes.paragraph.create();
    const $from = selection.$from;
    let tr;
    let start;
    if ($from.depth === 0) {                                  // 이미지 등 블록 전체가 선택된 경우
      start = selection.to;
      tr = state.tr.insert(start, [line, next]);
    } else if ($from.parent.isTextblock && !$from.parent.content.size) {
      start = $from.before();
      tr = state.tr.replaceWith(start, $from.after(), [line, next]);
    } else {
      start = $from.after();
      tr = state.tr.insert(start, [line, next]);
    }
    tr.setSelection(TextSelection.create(tr.doc, start + line.nodeSize + 1)).scrollIntoView();
    view.dispatch(tr);
    view.focus();
  });
}

/**
 * Wire the toolbar's 글 연결 button ([data-post-link]): pick a post, insert its card line.
 *
 * @param {import('@milkdown/core').Editor} editor - The Milkdown editor.
 * @param {?(number|string)} [excludeId] - Post being edited, not offered.
 * @returns {void}
 */
export function initPostLinkButton(editor, excludeId = null) {
  document.querySelector('[data-post-link]')?.addEventListener('click', async () => {
    const post = await openPostPicker({ excludeId });
    if (post) insertPostCardLine(editor, post);
  });
}
