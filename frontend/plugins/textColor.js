/**
 * textColor.js
 * ============
 * Milkdown v7 용 텍스트 색상 플러그인.
 *
 * 저장 형식: 마크다운 내 HTML 패스스루
 *   <span data-text-color="#ff0000" style="color:#ff0000">텍스트</span>
 */

import { $mark, $command } from '@milkdown/utils';

// ── Mark 정의 ──────────────────────────────────────────────
export const textColorMark = $mark('text_color', () => ({
  attrs: {
    color: { default: null },
  },

  // HTML → ProseMirror: span[data-text-color] 파싱
  parseDOM: [
    {
      tag: 'span[data-text-color]',
      getAttrs: (dom) => ({
        color: dom.getAttribute('data-text-color'),
      }),
    },
    {
      style: 'color',
      getAttrs: (value) => {
        if (value && value.trim()) return { color: value.trim() };
        return false;
      },
    },
  ],

  // ProseMirror → HTML: span 태그로 직렬화
  toDOM: (mark) => [
    'span',
    {
      'data-text-color': mark.attrs.color,
      style: `color:${mark.attrs.color}`,
    },
    0,
  ],

  // Milkdown remark → ProseMirror: html 노드에서 data-text-color 파싱
  parseMarkdown: {
    match: (node) =>
      node.type === 'html' &&
      typeof node.value === 'string' &&
      node.value.includes('data-text-color'),
    runner: (state, node, markType) => {
      const colorMatch = node.value.match(/data-text-color="([^"]+)"/);
      const textMatch = node.value.match(/>([^<]*)</);
      if (!colorMatch) return;
      const color = colorMatch[1];
      const text = textMatch ? textMatch[1] : '';
      state.openMark(markType, { color });
      state.addText(text);
      state.closeMark(markType);
    },
  },

  // ProseMirror → remark: text_color mark → html 인라인 노드
  toMarkdown: {
    match: (mark) => mark.type.name === 'text_color',
    runner: (state, mark, node) => {
      const color = mark.attrs.color;
      const text = node.text || '';
      // 인라인 HTML로 직렬화 — remark-stringify가 value를 그대로 출력
      state.addNode('html', undefined, `<span data-text-color="${color}" style="color:${color}">${text}</span>`);
      return true; // 기본 텍스트 노드 렌더링 방지
    },
  },
}));

// ── 색상 적용 커맨드 ──────────────────────────────────────
export const setTextColor = $command('SetTextColor', () => (color) => {
  return (state, dispatch) => {
    const { selection, schema, tr } = state;
    const markType = schema.marks['text_color'];
    if (!markType || selection.empty) return false;

    const { from, to } = selection;
    if (dispatch) {
      dispatch(
        tr
          .removeMark(from, to, markType)
          .addMark(from, to, markType.create({ color }))
      );
    }
    return true;
  };
});

// ── 색상 제거 커맨드 ──────────────────────────────────────
export const removeTextColor = $command('RemoveTextColor', () => () => {
  return (state, dispatch) => {
    const { selection, schema, tr } = state;
    const markType = schema.marks['text_color'];
    if (!markType || selection.empty) return false;

    const { from, to } = selection;
    if (dispatch) {
      dispatch(tr.removeMark(from, to, markType));
    }
    return true;
  };
});

// ── 플러그인 배열 (editor.use() 에 전달) ──────────────────
export const textColorPlugin = [textColorMark, setTextColor, removeTextColor];
