// plugins/tiptapColumns.js
// Custom TipTap nodes for multi-column layouts
import { Node, mergeAttributes } from '@tiptap/core';

export const Column = Node.create({
  name: 'column',
  content: 'block+',
  isolating: true,

  parseHTML() {
    return [{ tag: 'div[data-type="column"]' }];
  },

  renderHTML({ HTMLAttributes }) {
    return ['div', mergeAttributes(HTMLAttributes, {
      'data-type': 'column',
      style: 'flex: 1; min-width: 0; padding: 0.5rem;',
    }), 0];
  },
});

export const MultiColumn = Node.create({
  name: 'multiColumn',
  group: 'block',
  content: 'column{2,4}',
  defining: true,

  parseHTML() {
    return [{ tag: 'div[data-type="multi-column"]' }];
  },

  renderHTML({ HTMLAttributes }) {
    return ['div', mergeAttributes(HTMLAttributes, {
      'data-type': 'multi-column',
      style: 'display: flex; gap: 1rem; margin: 1rem 0; border: 1px dashed #e5e7eb; border-radius: 8px; padding: 0.5rem;',
    }), 0];
  },
});
