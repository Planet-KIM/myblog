/**
 * @file plugins/tiptapMagazineHtml.js — TipTap extensions that keep magazine
 * page HTML intact in the magazine editors (board_new_tiptap.js,
 * board_edit_tiptap.js).
 *
 * Starter layouts (app/services/starter_templates.py) and imported pages style
 * whole paragraphs, headings, quotes and lists with style="…", draw rules and
 * boxes with styled <div>s, give headings weights such as 800, and may contain
 * tables and sub/superscripts. StarterKit drops all of that, so opening a page
 * in the editor and saving it lost the design. These extensions keep it:
 *   - BlockStyle: the style attribute of paragraphs, headings, quotes and lists
 *     (text-align stays with the TextAlign extension).
 *   - StyledDiv: a <div style="…"> holding blocks, or nothing (a rule).
 *   - WeightedBold: bold that keeps its own style, so a weight that comes from a
 *     heading's style (800) stays 800 instead of a <strong> that renders bolder.
 *   - StyledTable (+ row, cell, header cell): tables with their inline styles.
 *     Cells hold inline content (paragraphs inside a cell become lines); there
 *     is no table editing UI.
 *   - Subscript, Superscript: <sub> and <sup>.
 * Pasted HTML still loses its block styles (stripPastedBlockStyles).
 */
import { Extension, Mark, Node, mergeAttributes } from '@tiptap/core';
import Bold from '@tiptap/extension-bold';

// Node types whose style attribute BlockStyle keeps.
const STYLED_BLOCK_TYPES = ['paragraph', 'heading', 'blockquote', 'bulletList', 'orderedList', 'listItem'];
// Pasted elements whose styles are reduced to text alignment (block styles never survived a paste).
const PASTED_BLOCK_SELECTOR = 'p, h1, h2, h3, h4, h5, h6, blockquote, ul, ol, li';
// Pasted elements whose styles are dropped entirely.
const PASTED_UNSTYLED_SELECTOR = 'div[style], table, tr, td, th';
// font-weight values Bold treats as bold (same test as @tiptap/extension-bold).
const BOLD_WEIGHT = /^(bold(er)?|[5-9]\d{2,})$/;
// Block elements flattened into lines inside table cells (cells hold inline content).
const CELL_BLOCK_SELECTOR = 'p, div, h1, h2, h3, h4, h5, h6, blockquote, pre, ul, ol, li';

/**
 * Read an element's inline style without its text-align declarations.
 *
 * TextAlign already stores and renders text-align, so keeping it here too
 * would write it twice.
 *
 * @param {HTMLElement} el - Element being parsed.
 * @returns {?string} Remaining declarations joined with "; ", or null when none are left.
 */
function styleWithoutTextAlign(el) {
  const decls = (el.getAttribute('style') || '')
    .split(';')
    .map(d => d.trim())
    .filter(d => d && !/^text-align\s*:/i.test(d));
  return decls.length ? decls.join('; ') : null;
}

/**
 * Build a TipTap attribute spec that copies one HTML attribute in and out unchanged.
 *
 * @param {string} name - HTML attribute name (e.g. "style", "colspan").
 * @param {function(HTMLElement): ?string} [parse] - Custom reader; defaults to getAttribute(name).
 * @returns {Object} Attribute spec with default null.
 */
function htmlAttribute(name, parse = el => el.getAttribute(name)) {
  return {
    default: null,
    parseHTML: parse,
    renderHTML: attrs => (attrs[name] ? { [name]: attrs[name] } : {}),
  };
}

export const BlockStyle = Extension.create({
  name: 'blockStyle',

  /**
   * Add a `style` attribute to paragraphs, headings, quotes, lists and list items.
   *
   * @returns {Array<Object>} TipTap global attribute definitions.
   */
  addGlobalAttributes() {
    return [{
      types: STYLED_BLOCK_TYPES,
      attributes: { style: htmlAttribute('style', styleWithoutTextAlign) },
    }];
  },
});

export const StyledDiv = Node.create({
  name: 'styledDiv',
  group: 'block',
  content: 'block*',

  /**
   * The inline style of the div.
   *
   * @returns {Object} Attribute specs.
   */
  addAttributes() {
    return { style: htmlAttribute('style') };
  },

  /**
   * Parse only divs that carry a style; plain divs stay transparent wrappers.
   *
   * @returns {Array<{tag: string}>} ProseMirror parse rules.
   */
  parseHTML() {
    return [{ tag: 'div[style]' }];
  },

  /**
   * Render the div with its style around its blocks.
   *
   * @param {{HTMLAttributes: Object}} props - Attributes TipTap wants on the element.
   * @returns {Array} ProseMirror DOM spec.
   */
  renderHTML({ HTMLAttributes }) {
    return ['div', mergeAttributes(HTMLAttributes), 0];
  },
});

export const WeightedBold = Bold.extend({
  /**
   * The inline style of the bold element (for example its weight or colour).
   *
   * @returns {Object} Attribute specs.
   */
  addAttributes() {
    return { style: htmlAttribute('style') };
  },

  /**
   * Bold's own parse rules, except that bold coming from a font-weight style
   * keeps that exact weight.
   *
   * @returns {Array<Object>} ProseMirror parse rules.
   */
  parseHTML() {
    return [
      { tag: 'strong' },
      { tag: 'b', getAttrs: node => node.style.fontWeight !== 'normal' && null },
      { style: 'font-weight=400', clearMark: mark => mark.type.name === this.name },
      { style: 'font-weight', getAttrs: value => BOLD_WEIGHT.test(value) && { style: `font-weight: ${value}` } },
    ];
  },
});

export const StyledTable = Node.create({
  name: 'styledTable',
  group: 'block',
  content: 'styledTableRow+',
  isolating: true,

  /**
   * The inline style of the table.
   *
   * @returns {Object} Attribute specs.
   */
  addAttributes() {
    return { style: htmlAttribute('style') };
  },

  /**
   * Parse any <table>; <thead>/<tbody> are read through to their rows.
   *
   * @returns {Array<{tag: string}>} ProseMirror parse rules.
   */
  parseHTML() {
    return [{ tag: 'table' }];
  },

  /**
   * Render the table with its rows in a <tbody>.
   *
   * @param {{HTMLAttributes: Object}} props - Attributes TipTap wants on the element.
   * @returns {Array} ProseMirror DOM spec.
   */
  renderHTML({ HTMLAttributes }) {
    return ['table', mergeAttributes(HTMLAttributes), ['tbody', 0]];
  },
});

export const StyledTableRow = Node.create({
  name: 'styledTableRow',
  content: '(styledTableCell | styledTableHeader)*',

  /**
   * The inline style of the row.
   *
   * @returns {Object} Attribute specs.
   */
  addAttributes() {
    return { style: htmlAttribute('style') };
  },

  /**
   * Parse a table row.
   *
   * @returns {Array<{tag: string}>} ProseMirror parse rules.
   */
  parseHTML() {
    return [{ tag: 'tr' }];
  },

  /**
   * Render a table row.
   *
   * @param {{HTMLAttributes: Object}} props - Attributes TipTap wants on the element.
   * @returns {Array} ProseMirror DOM spec.
   */
  renderHTML({ HTMLAttributes }) {
    return ['tr', mergeAttributes(HTMLAttributes), 0];
  },
});

/**
 * Tell whether anything other than whitespace comes before a node among its siblings.
 *
 * @param {ChildNode} node - Node inside a table cell.
 * @returns {boolean} True when a preceding sibling has content.
 */
function hasContentBefore(node) {
  for (let prev = node.previousSibling; prev; prev = prev.previousSibling) {
    if (prev.nodeType !== 3 || prev.textContent.trim()) return true;
  }
  return false;
}

/**
 * Return a copy of a table cell whose block children are flattened into lines.
 *
 * Cells hold inline content, so a cell such as <td><p>a</p><p>b</p></td>
 * (common in pasted spreadsheets) is read as "a<br>b" instead of the
 * paragraphs breaking the table apart.
 *
 * @param {HTMLElement} cell - The <td> or <th> being parsed.
 * @returns {HTMLElement} A detached copy to read the cell content from.
 */
function inlineCellContent(cell) {
  const copy = cell.cloneNode(true);
  copy.querySelectorAll(CELL_BLOCK_SELECTOR).forEach(el => {
    if (hasContentBefore(el)) el.before(document.createElement('br'));
    el.replaceWith(...el.childNodes);
  });
  return copy;
}

/**
 * Create a table cell node for one tag, keeping its style and spans.
 *
 * @param {string} name - Node name.
 * @param {string} tag - "td" or "th".
 * @returns {Node} TipTap node holding inline content.
 */
function tableCellNode(name, tag) {
  return Node.create({
    name,
    content: 'inline*',
    isolating: true,

    /**
     * The cell's inline style and column/row spans.
     *
     * @returns {Object} Attribute specs.
     */
    addAttributes() {
      return { style: htmlAttribute('style'), colspan: htmlAttribute('colspan'), rowspan: htmlAttribute('rowspan') };
    },

    /**
     * Parse the cell tag, reading block children as lines.
     *
     * @returns {Array<Object>} ProseMirror parse rules.
     */
    parseHTML() {
      return [{ tag, contentElement: inlineCellContent }];
    },

    /**
     * Render the cell tag around its inline content.
     *
     * @param {{HTMLAttributes: Object}} props - Attributes TipTap wants on the element.
     * @returns {Array} ProseMirror DOM spec.
     */
    renderHTML({ HTMLAttributes }) {
      return [tag, mergeAttributes(HTMLAttributes), 0];
    },
  });
}

export const StyledTableCell = tableCellNode('styledTableCell', 'td');
export const StyledTableHeader = tableCellNode('styledTableHeader', 'th');

/**
 * Create a mark that wraps text in one tag with no attributes.
 *
 * @param {string} name - Mark name.
 * @param {string} tag - HTML tag ("sub" or "sup").
 * @param {string} excludes - Mark name that cannot be combined with this one.
 * @returns {Mark} TipTap mark.
 */
function tagMark(name, tag, excludes) {
  return Mark.create({
    name,
    excludes,

    /**
     * Parse the tag.
     *
     * @returns {Array<{tag: string}>} ProseMirror parse rules.
     */
    parseHTML() {
      return [{ tag }];
    },

    /**
     * Render the tag around the marked text.
     *
     * @returns {Array} ProseMirror DOM spec.
     */
    renderHTML() {
      return [tag, 0];
    },
  });
}

export const Subscript = tagMark('subscript', 'sub', 'superscript');
export const Superscript = tagMark('superscript', 'sup', 'subscript');

/**
 * Every extension in this module, ready to add after StarterKit.
 *
 * StarterKit must be configured with `bold: false`, since WeightedBold replaces its bold.
 */
export const magazineHtmlExtensions = [
  WeightedBold, BlockStyle, StyledDiv,
  StyledTable, StyledTableRow, StyledTableCell, StyledTableHeader,
  Subscript, Superscript,
];

/**
 * Drop styles from pasted HTML the way the editor did before these extensions.
 *
 * Paragraphs, headings, quotes and lists keep only their text alignment; divs
 * and table parts lose their styles. Pasted pages carry layout styles (margins,
 * line heights, fixed widths) that do not belong in a magazine block.
 *
 * @param {string} html - Pasted or dropped HTML.
 * @returns {string} The same HTML with those styles removed.
 */
export function stripPastedBlockStyles(html) {
  const tpl = document.createElement('template');
  tpl.innerHTML = html;
  tpl.content.querySelectorAll(PASTED_BLOCK_SELECTOR).forEach(el => {
    const align = el.style.textAlign;
    if (align) el.setAttribute('style', `text-align: ${align}`); // conventions: allow (rewrites pasted HTML, not page styling)
    else el.removeAttribute('style');
  });
  tpl.content.querySelectorAll(PASTED_UNSTYLED_SELECTOR).forEach(el => el.removeAttribute('style'));
  return tpl.innerHTML;
}
