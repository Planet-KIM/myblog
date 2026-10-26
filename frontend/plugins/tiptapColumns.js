/**
 * @file plugins/tiptapColumns.js — Custom TipTap nodes for multi-column layouts:
 * a MultiColumn block holding 2–4 Column blocks, laid out side by side.
 * (Not imported by any editor entry at the moment.)
 */
import { Node, mergeAttributes } from '@tiptap/core';

export const Column = Node.create({
  name: 'column',
  content: 'block+',
  isolating: true,

  /**
   * Parse a column from `<div data-type="column">`.
   *
   * @returns {Array<{tag: string}>} ProseMirror parse rules.
   */
  parseHTML() {
    return [{ tag: 'div[data-type="column"]' }];
  },

  /**
   * Render a column as a flexible `<div data-type="column">`.
   *
   * @param {{HTMLAttributes: Object}} props - Attributes TipTap wants on the element.
   * @returns {Array} ProseMirror DOM spec (content goes in the div).
   */
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

  /**
   * Parse a column group from `<div data-type="multi-column">`.
   *
   * @returns {Array<{tag: string}>} ProseMirror parse rules.
   */
  parseHTML() {
    return [{ tag: 'div[data-type="multi-column"]' }];
  },

  /**
   * Render the column group as a flex row with a dashed outline.
   *
   * @param {{HTMLAttributes: Object}} props - Attributes TipTap wants on the element.
   * @returns {Array} ProseMirror DOM spec (columns go in the div).
   */
  renderHTML({ HTMLAttributes }) {
    return ['div', mergeAttributes(HTMLAttributes, {
      'data-type': 'multi-column',
      style: 'display: flex; gap: 1rem; margin: 1rem 0; border: 1px dashed #e5e7eb; border-radius: 8px; padding: 0.5rem;',
    }), 0];
  },
});
