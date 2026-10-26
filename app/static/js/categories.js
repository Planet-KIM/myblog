/**
 * @file Board Categories — Tree Logic (templates/board_categories.html).
 *
 * On DOMContentLoaded: reads the categories from the hidden .cat-data-item
 * elements, then builds the stat pills and charts (Chart.js), the tree search
 * (Fuse.js with an includes() fallback), the parent picker (Tom Select), the
 * drag-and-drop tree (SortableJS), inline rename, the delete modal and the
 * right-click menu.
 * Libraries: Chart.js, Fuse.js, Tom Select, SortableJS (loaded before this file).
 * Per-category colors come from theme tokens read once at load (COLORS).
 */

document.addEventListener('DOMContentLoaded', function () {

  // ── Color palette — theme.css 브랜드 토큰에서 파생 (테마 일관성) ──
  const rootCss = getComputedStyle(document.documentElement);
  /**
   * Read a theme token from :root.
   *
   * @param {string} name - Custom property name, e.g. '--primary'.
   * @param {string} fallback - Value used when the token is empty.
   * @returns {string} The token value, or the fallback.
   */
  const tok = (name, fallback) => rootCss.getPropertyValue(name).trim() || fallback;
  const COLORS = [
    tok('--primary', '#b4542f'), tok('--accent', '#2a82c4'), tok('--secondary', '#3f8f5c'),
    tok('--warning', '#c4820e'), tok('--cat-tech', '#7a5bbf'), tok('--cat-life', '#c0567f'),
    tok('--primary-dark', '#8f3f20'), tok('--accent-dark', '#1d6098'), tok('--secondary-dark', '#2f7047'),
  ];
  /**
   * Pick a category's palette color (stable per id).
   *
   * @param {number} id - Category id.
   * @returns {string} A color from COLORS.
   */
  const getColor = (id) => COLORS[id % COLORS.length];
  // '#rrggbb' + 알파 2자리 (토큰이 hex가 아니면 그대로)
  /**
   * Append a two-digit hex alpha to a '#rrggbb' color.
   *
   * @param {string} c - Color; returned unchanged unless it is '#rrggbb'.
   * @param {string} aa - Alpha as two hex digits, e.g. 'cc'.
   * @returns {string} '#rrggbbaa', or c as given.
   */
  const withAlpha = (c, aa) => (/^#[0-9a-f]{6}$/i.test(c) ? c + aa : c);

  // ── 1) Parse hidden data ─────────────────────────
  const nodesById = {};
  document.querySelectorAll('.cat-data-item').forEach((el) => {
    const id = parseInt(el.dataset.id, 10);
    nodesById[id] = {
      id,
      parentId:  el.dataset.parentId ? parseInt(el.dataset.parentId, 10) : null,
      name:      el.dataset.name,
      created:   el.dataset.created,
      postCount: parseInt(el.dataset.postCount || '0', 10),
      children:  [],
    };
  });

  // ── 2) Build parent → child tree ─────────────────
  Object.values(nodesById).forEach((node) => {
    if (node.parentId && nodesById[node.parentId]) {
      nodesById[node.parentId].children.push(node);
    }
  });

  const roots = Object.values(nodesById).filter(
    (n) => !n.parentId || !nodesById[n.parentId]
  );

  // ── DOM refs ──────────────────────────────────────
  const treeContent  = document.getElementById('tree-content');
  const parentSelect = document.getElementById('parent_id');
  const ctxMenu      = document.getElementById('cat-ctx-menu');
  const deleteModal  = document.getElementById('deleteCategoryModal')
    ? new bootstrap.Modal(document.getElementById('deleteCategoryModal'))
    : null;

  let tomSelect    = null;
  let pendingDelete = null;
  let ctxNode       = null;

  // ── 3) Chart.js — horizontal bar chart ───────────
  /**
   * Fill the stat pills and draw the overview chart (root categories with
   * their subtree post counts), or an empty-state note when there are no posts.
   *
   * @returns {void}
   */
  (function initChart() {
    if (!window.Chart) return;

    // Recursively sum post counts for a node + all descendants
    /**
     * Sum the posts of a category and all of its descendants.
     *
     * @param {Object} node - Tree node ({postCount, children}).
     * @returns {number} Total post count of the subtree.
     */
    function aggCount(node) {
      return node.postCount + node.children.reduce((s, c) => s + aggCount(c), 0);
    }

    // Total posts across every category (for stat pill + tooltip %)
    const totalPosts = Object.values(nodesById).reduce((s, n) => s + n.postCount, 0);

    // Chart shows only ROOT categories with aggregated counts (avoids double-counting)
    const rootItems = roots
      .sort((a, b) => a.id - b.id)
      .map((n) => ({ label: n.name, count: aggCount(n), color: getColor(n.id) }));

    // Update stat pills
    const elPosts  = document.getElementById('stat-total-posts');
    const elTopCat = document.getElementById('stat-top-cat');
    if (elPosts) elPosts.textContent = totalPosts;
    if (elTopCat) {
      const top = rootItems.length ? rootItems.reduce((a, b) => a.count >= b.count ? a : b) : null;
      elTopCat.textContent = (top && top.count > 0) ? `${top.label} (${top.count})` : '—';
    }

    const container = document.getElementById('stats-chart-container');
    if (!container) return;

    if (totalPosts === 0) {
      container.innerHTML =
        '<p class="cat-chart-empty">' +
        '글을 작성하면 카테고리별 분포가 여기에 표시됩니다.</p>';
      return;
    }

    // Dynamic height based on root category count
    const chartH = Math.min(280, Math.max(80, rootItems.length * 42));
    container.style.height = chartH + 'px'; // conventions: allow (chart height computed at runtime from the category count)

    const clrBorder = tok('--border', '#e8dfd2');
    const clrMuted  = tok('--text-muted', '#7d6f60');
    const clrMain   = tok('--text-main', '#4c4239');

    new Chart(document.getElementById('stats-chart').getContext('2d'), {
      type: 'bar',
      data: {
        labels:   rootItems.map((i) => i.label),
        datasets: [{
          data:            rootItems.map((i) => i.count),
          backgroundColor: rootItems.map((i) => withAlpha(i.color, 'cc')),
          borderColor:     rootItems.map((i) => i.color),
          borderWidth: 1,
          borderRadius: 4,
          borderSkipped: false,
        }],
      },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (c) =>
                ` 글 ${c.raw}개 ` +
                `(${totalPosts ? Math.round((c.raw / totalPosts) * 100) : 0}%)`,
            },
          },
        },
        scales: {
          x: {
            grid:   { color: clrBorder },
            ticks:  { color: clrMuted, precision: 0 },
            border: { color: clrBorder },
          },
          y: {
            grid:   { display: false },
            ticks:  { color: clrMain },
            border: { color: clrBorder },
          },
        },
      },
    });
  })();

  // ── 4) Search — Fuse.js fuzzy + simple-includes fallback ──
  /**
   * Filter the tree as the user types: matches stay visible together with
   * their ancestors (expanded) and all their descendants.
   *
   * @returns {void}
   */
  (function initSearch() {
    const input = document.getElementById('categorySearch');
    if (!input) return;

    // Recursively collect all descendant IDs
    /**
     * Add the ids of every descendant of a category to a set.
     *
     * @param {number} nodeId - Category whose subtree is collected.
     * @param {Set<number>} acc - Set that receives the ids (mutated).
     * @returns {void}
     */
    function collectDescendants(nodeId, acc) {
      const node = nodesById[nodeId];
      if (!node) return;
      node.children.forEach((child) => {
        acc.add(child.id);
        collectDescendants(child.id, acc);
      });
    }

    // Fuse.js를 쓸 수 있으면 퍼지 검색, 아니면 includes 폴백
    /**
     * Find the categories whose name matches a query.
     *
     * @param {string} query - Non-empty search text.
     * @returns {Set<number>} Ids of the matching categories.
     */
    function getMatchIds(query) {
      if (typeof Fuse !== 'undefined') { // eslint-disable-line no-undef
        try {
          const fuse = new Fuse(Object.values(nodesById), { // eslint-disable-line no-undef
            keys: ['name'],
            threshold: 0.3,
            ignoreLocation: true,
          });
          return new Set(fuse.search(query).map((r) => r.item.id));
        } catch (_) { /* fall through */ }
      }
      // 폴백: 대소문자 무시 포함 검색
      const q = query.toLowerCase();
      return new Set(
        Object.values(nodesById)
          .filter((n) => n.name.toLowerCase().includes(q))
          .map((n) => n.id)
      );
    }

    input.addEventListener('input', function () {
      const query = this.value.trim();
      const allLi = document.querySelectorAll('.cat-tree-node');

      if (!query) {
        allLi.forEach((el) => (el.hidden = false));
        return;
      }

      const matchIds   = getMatchIds(query);
      const visibleIds = new Set(matchIds);

      matchIds.forEach((id) => {
        // 조상 — 루트까지 경로 유지
        let node = nodesById[id];
        while (node && node.parentId && nodesById[node.parentId]) {
          visibleIds.add(node.parentId);
          node = nodesById[node.parentId];
        }
        // 자손 — 하위 폴더 전체 표시
        collectDescendants(id, visibleIds);
      });

      allLi.forEach((el) => {
        const nodeId = parseInt(el.dataset.id, 10);
        if (visibleIds.has(nodeId)) {
          el.hidden = false;
          const ul = document.getElementById(`children-${nodeId}`);
          if (ul) ul.classList.remove('collapsed');
        } else {
          el.hidden = true;
        }
      });
    });
  })();

  // ── 5) Tom Select — enhanced parent dropdown ─────
  /**
   * Upgrade the parent <select> to Tom Select, with each category's color dot.
   * The dot color is passed as --cat-dot-color (see .ts-color-dot).
   *
   * @returns {void}
   */
  (function initTomSelect() {
    if (!window.TomSelect || !parentSelect) return;

    tomSelect = new TomSelect('#parent_id', {
      create: false,
      render: {
        option: function (data, escape) {
          const nId  = parseInt(data.value);
          const dot  = nId ? `<span class="ts-color-dot" style="--cat-dot-color:${getColor(nId)}"></span>` : '';
          return `<div class="d-flex align-items-center gap-2">${dot}<span>${escape(data.text)}</span></div>`;
        },
        item: function (data, escape) {
          const nId  = parseInt(data.value);
          const dot  = nId ? `<span class="ts-color-dot" style="--cat-dot-color:${getColor(nId)}"></span>` : '';
          return `<div class="d-flex align-items-center gap-2">${dot}<span>${escape(data.text)}</span></div>`;
        },
      },
    });
  })();

  // ── 6) Chart.js — Breakdown (개별 카테고리 직접 포스트 수) ──
  let breakdownChartInited = false;

  /**
   * Draw the breakdown chart (every category in tree order with its direct
   * post count) the first time its tab is shown; later calls do nothing.
   *
   * @returns {void}
   */
  function initBreakdownChart() {
    if (breakdownChartInited || !window.Chart) return;
    breakdownChartInited = true;

    const container = document.getElementById('breakdown-chart-container');
    if (!container) return;

    // 트리 순서로 모든 카테고리 나열 (루트 → 자식)
    const items = [];
    /**
     * Append a node and, depth-first, its children to items.
     *
     * @param {Object} node - Tree node.
     * @param {number} depth - 0 for roots; children are prefixed with '↳ '.
     * @returns {void}
     */
    function walk(node, depth) {
      items.push({
        label: (depth > 0 ? '↳ ' : '') + node.name,
        count: node.postCount,
        color: getColor(node.id),
        depth,
      });
      node.children.sort((a, b) => a.id - b.id).forEach((c) => walk(c, depth + 1));
    }
    roots.sort((a, b) => a.id - b.id).forEach((r) => walk(r, 0));

    if (items.every((i) => i.count === 0)) {
      container.innerHTML =
        '<p class="cat-chart-empty">' +
        '아직 어떤 카테고리에도 글이 없습니다.</p>';
      return;
    }

    const chartH = Math.min(320, Math.max(80, items.length * 40));
    container.style.height = chartH + 'px'; // conventions: allow (chart height computed at runtime from the category count)

    const clrBorder = tok('--border', '#e8dfd2');
    const clrMuted  = tok('--text-muted', '#7d6f60');
    const clrMain   = tok('--text-main', '#4c4239');

    new Chart(document.getElementById('breakdown-chart').getContext('2d'), {
      type: 'bar',
      data: {
        labels:   items.map((i) => i.label),
        datasets: [{
          data:            items.map((i) => i.count),
          backgroundColor: items.map((i) => withAlpha(i.color, i.depth > 0 ? '88' : 'cc')),
          borderColor:     items.map((i) => i.color),
          borderWidth: 1,
          borderRadius: 4,
          borderSkipped: false,
        }],
      },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (c) =>
                ` 직접 속한 글 ${c.raw}개`,
            },
          },
        },
        scales: {
          x: {
            grid:   { color: clrBorder },
            ticks:  { color: clrMuted, precision: 0 },
            border: { color: clrBorder },
          },
          y: {
            grid:  { display: false },
            ticks: {
              color: (ctx) => items[ctx.index]?.depth > 0 ? clrMuted : clrMain,
            },
            border: { color: clrBorder },
          },
        },
      },
    });
  }

  // Breakdown 탭이 처음 열릴 때만 차트 초기화 (hidden canvas 렌더 방지)
  const breakdownTabBtn = document.getElementById('chart-tab-breakdown');
  if (breakdownTabBtn) {
    breakdownTabBtn.addEventListener('shown.bs.tab', initBreakdownChart);
  }

  // ── 7) SortableJS — per-<ul> drag & drop ─────────
  /**
   * Make a tree level draggable. Dropping a category into another level asks
   * for confirmation, then moves it (or reloads to undo the drop);
   * reordering within the same level is visual only.
   *
   * @param {HTMLUListElement} ul - The root list or a children list.
   * @returns {void}
   */
  function initSortable(ul) {
    if (!window.Sortable) return;
    Sortable.create(ul, {
      group:          { name: 'cat-tree', pull: true, put: true },
      animation:      150,
      handle:         '.bi-grip-vertical',
      ghostClass:     'cat-sortable-ghost',
      dragClass:      'cat-sortable-drag',
      fallbackOnBody: true,
      swapThreshold:  0.35,
      onEnd: function (evt) {
        if (evt.from === evt.to) return; // same-level reorder → visual only

        const movedId     = parseInt(evt.item.dataset.id, 10);
        const toId        = evt.to.id;
        const newParentId = toId === 'cat-root-ul'
          ? null
          : parseInt(toId.replace('children-', ''), 10);

        const movedName  = nodesById[movedId]?.name    || String(movedId);
        const targetName = newParentId
          ? (nodesById[newParentId]?.name || String(newParentId))
          : '최상위';

        if (confirm(`"${movedName}"을(를) "${targetName}"(으)로 옮길까요?`)) {
          moveCategory(movedId, newParentId);
        } else {
          window.location.reload();
        }
      },
    });
  }

  // ── 8) API helpers ───────────────────────────────
  /**
   * Move a category under a new parent on the server, then reload the page.
   * Shows the loading overlay meanwhile and a toast with the result.
   *
   * @param {number} id - Category to move.
   * @param {number|null} newParentId - New parent id, or null for top level.
   * @returns {Promise<void>} Resolves once the request is handled.
   */
  async function moveCategory(id, newParentId) {
    window.loading.show('카테고리를 옮기는 중…');
    try {
      const res = await fetch('/board/categories/move', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'same-origin',
        body: JSON.stringify({ category_id: id, new_parent_id: newParentId ?? null }),
      });
      if (res.ok) {
        window.toast.success('카테고리를 옮겼습니다');
        setTimeout(() => window.location.reload(), 700);
      } else {
        window.loading.hide();
        window.toast.error('이동 실패: ' + ((await res.json()).detail || '알 수 없는 오류'));
      }
    } catch { window.loading.hide(); window.toast.error('네트워크 오류가 발생했습니다.'); }
  }

  /**
   * Delete a category on the server, then reload the page.
   * Shows the loading overlay meanwhile and a toast with the result.
   *
   * @param {number} id - Category to delete.
   * @param {string|null} reassignTo - Category id that receives its posts, if any.
   * @returns {Promise<void>} Resolves once the request is handled.
   */
  async function deleteCategory(id, reassignTo) {
    window.loading.show('카테고리를 삭제하는 중…');
    const body = new FormData();
    if (reassignTo) body.append('reassign_to', reassignTo);
    try {
      const res = await fetch(`/board/categories/${id}/delete`, { method: 'POST', credentials: 'same-origin', body });
      if (res.ok) {
        window.toast.success('카테고리를 삭제했습니다');
        setTimeout(() => window.location.reload(), 700);
      } else {
        window.loading.hide();
        window.toast.error('삭제 실패: ' + ((await res.json()).detail || '알 수 없는 오류'));
      }
    } catch { window.loading.hide(); window.toast.error('네트워크 오류가 발생했습니다.'); }
  }

  /**
   * Rename a category on the server and update its label and node.
   * Restores the old label and shows an error toast on failure.
   *
   * @param {number} id - Category to rename.
   * @param {string} newName - Requested name.
   * @param {HTMLSpanElement} nameSpan - The tree label showing the name.
   * @returns {Promise<void>} Resolves once the request is handled.
   */
  async function renameCategory(id, newName, nameSpan) {
    const oldName = nameSpan.textContent;
    try {
      const res = await fetch(`/board/categories/${id}/rename`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'same-origin',
        body: JSON.stringify({ name: newName }),
      });
      if (res.ok) {
        const data = await res.json();
        nameSpan.textContent = data.name;
        nodesById[id].name   = data.name;
        window.toast.success(`"${data.name}"(으)로 이름을 바꿨습니다`);
      } else {
        nameSpan.textContent = oldName;
        window.toast.error('이름 변경 실패: ' + ((await res.json()).detail || '알 수 없는 오류'));
      }
    } catch { nameSpan.textContent = oldName; window.toast.error('네트워크 오류가 발생했습니다.'); }
  }

  // ── 8) Context menu ──────────────────────────────
  /**
   * Pick a category as the parent in the create form.
   *
   * @param {Object} node - Tree node to select.
   * @returns {void}
   */
  function selectAsParent(node) {
    if (tomSelect) tomSelect.setValue(String(node.id));
    else if (parentSelect) parentSelect.value = String(node.id);
  }

  if (ctxMenu) {
    // Hide on outside click
    document.addEventListener('click', () => ctxMenu.classList.remove('visible'));
    document.addEventListener('contextmenu', (e) => {
      if (!e.target.closest('.cat-item-container')) ctxMenu.classList.remove('visible');
    });

    ctxMenu.addEventListener('click', (e) => {
      const action = e.target.closest('[data-action]')?.dataset.action;
      if (!action || !ctxNode) return;

      ctxMenu.classList.remove('visible');

      if (action === 'rename') {
        document.querySelector(`.cat-tree-node[data-id="${ctxNode.id}"] .cat-action-btn.rename`)?.click();
      } else if (action === 'delete') {
        document.querySelector(`.cat-tree-node[data-id="${ctxNode.id}"] .cat-action-btn.delete`)?.click();
      } else if (action === 'new-child') {
        selectAsParent(ctxNode);
        const nameInput = document.getElementById('name');
        nameInput?.focus();
        nameInput?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    });
  }

  // ── 9) Delete modal confirm ───────────────────────
  if (deleteModal) {
    document.getElementById('confirmDeleteBtn')?.addEventListener('click', () => {
      if (!pendingDelete) return;
      const reassignTo = document.getElementById('deleteReassignSelect').value || null;
      deleteModal.hide();
      deleteCategory(pendingDelete.id, reassignTo);
      pendingDelete = null;
    });
  }

  // ── 10) Render a single tree node ────────────────
  /**
   * Build the <li> for a category and, recursively, its children: grip,
   * collapse toggle, color dot, name, post count, date, rename/delete buttons,
   * right-click menu and a sortable children list.
   *
   * @param {Object} node - Tree node ({id, name, created, postCount, children}).
   * @returns {HTMLLIElement} The rendered node.
   */
  function renderNode(node) {
    const li = document.createElement('li');
    li.className  = 'cat-tree-node';
    li.dataset.id = node.id;

    const hasChildren = node.children.length > 0;
    const color       = getColor(node.id);

    // Container
    const container     = document.createElement('div');
    container.className  = 'cat-item-container';
    container.dataset.id = node.id;

    // Right-click → context menu
    if (ctxMenu) {
      container.addEventListener('contextmenu', (e) => {
        e.preventDefault();
        e.stopPropagation();
        ctxNode = node;
        const x = Math.min(e.clientX, window.innerWidth  - 185);
        const y = Math.min(e.clientY, window.innerHeight - 130);
        // conventions: allow (menu position follows the pointer, known only at runtime)
        ctxMenu.style.left = x + 'px';
        ctxMenu.style.top  = y + 'px'; // conventions: allow (menu position follows the pointer)
        ctxMenu.classList.add('visible');
      });
    }

    // Grip handle (SortableJS handle target)
    const grip = document.createElement('i');
    grip.className = 'bi bi-grip-vertical cat-grip';
    grip.setAttribute('aria-hidden', 'true');
    container.appendChild(grip);

    // Toggle
    const toggle = document.createElement('button');
    toggle.type      = 'button';
    toggle.className = 'tree-toggle' + (hasChildren ? '' : ' disabled');
    toggle.innerHTML = hasChildren ? '<i class="bi bi-chevron-down"></i>' : '<i class="bi bi-dash"></i>';
    toggle.setAttribute('aria-label', hasChildren ? `${node.name} 접기/펼치기` : '하위 카테고리 없음');
    if (hasChildren) toggle.setAttribute('aria-expanded', 'true');
    container.appendChild(toggle);

    // Label: color dot + icon + name + badge + meta
    const label = document.createElement('div');
    label.className = 'cat-label';

    const dot = document.createElement('span');
    dot.className       = 'cat-color-dot';
    dot.style.setProperty('--cat-dot-color', color);
    label.appendChild(dot);

    const icon = document.createElement('i');
    icon.className = `bi cat-icon ${hasChildren ? 'bi-folder2' : 'bi-folder'}`;
    label.appendChild(icon);

    const nameSpan = document.createElement('span');
    nameSpan.className   = 'cat-name ms-1';
    nameSpan.textContent = node.name;
    label.appendChild(nameSpan);

    if (node.postCount > 0) {
      const badge = document.createElement('span');
      badge.className   = 'cat-count';
      badge.textContent = node.postCount;
      badge.title       = `글 ${node.postCount}개`;
      label.appendChild(badge);
    }

    const meta = document.createElement('span');
    meta.className   = 'cat-meta d-none d-sm-inline';
    meta.textContent = node.created;
    label.appendChild(meta);

    // Click on label → select as parent in form
    label.addEventListener('click', () => {
      selectAsParent(node);
      document.querySelectorAll('.cat-item-container.active').forEach((el) => el.classList.remove('active'));
      container.classList.add('active');
    });

    container.appendChild(label);

    // Action buttons
    const actions = document.createElement('div');
    actions.className = 'cat-actions';

    // Rename btn
    const renameBtn = document.createElement('button');
    renameBtn.type      = 'button';
    renameBtn.className = 'cat-action-btn rename';
    renameBtn.title     = '이름 바꾸기';
    renameBtn.setAttribute('aria-label', `${node.name} 이름 바꾸기`);
    renameBtn.innerHTML = '<i class="bi bi-pencil"></i>';
    renameBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      const input = document.createElement('input');
      input.type      = 'text';
      input.className = 'cat-rename-input';
      input.value     = nameSpan.textContent;
      nameSpan.replaceWith(input);
      input.focus();
      input.select();

      /**
       * Put the label back and save the new name if it changed.
       *
       * @returns {Promise<void>} Resolves once the rename (if any) is handled.
       */
      const commit = async () => {
        const newName = input.value.trim();
        input.replaceWith(nameSpan);
        if (newName && newName !== node.name) await renameCategory(node.id, newName, nameSpan);
      };
      input.addEventListener('keydown', (ev) => {
        if (ev.key === 'Enter')  { ev.preventDefault(); commit(); }
        if (ev.key === 'Escape') { input.replaceWith(nameSpan); }
      });
      input.addEventListener('blur', commit);
    });

    // Delete btn
    const deleteBtn = document.createElement('button');
    deleteBtn.type      = 'button';
    deleteBtn.className = 'cat-action-btn delete';
    deleteBtn.title     = '삭제';
    deleteBtn.setAttribute('aria-label', `${node.name} 삭제`);
    deleteBtn.innerHTML = '<i class="bi bi-trash"></i>';
    deleteBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      if (!deleteModal) return;

      document.getElementById('deleteCatName').textContent = node.name;
      const reassignSec    = document.getElementById('deleteReassignSection');
      const childWarn      = document.getElementById('deleteChildrenWarning');
      const reassignSelect = document.getElementById('deleteReassignSelect');

      if (node.postCount > 0) {
        document.getElementById('deletePostCount').textContent = node.postCount;
        reassignSelect.innerHTML = '';
        Object.values(nodesById).forEach((n) => {
          if (n.id === node.id) return;
          const opt = document.createElement('option');
          opt.value = n.id; opt.textContent = n.name;
          reassignSelect.appendChild(opt);
        });
        reassignSec.classList.remove('d-none');
      } else {
        reassignSec.classList.add('d-none');
      }
      childWarn.classList.toggle('d-none', node.children.length === 0);
      pendingDelete = { id: node.id };
      deleteModal.show();
    });

    actions.appendChild(renameBtn);
    actions.appendChild(deleteBtn);
    container.appendChild(actions);
    li.appendChild(container);

    // Recursive children
    if (hasChildren) {
      const ul = document.createElement('ul');
      ul.id        = `children-${node.id}`;
      ul.className = 'cat-tree-children';
      node.children.sort((a, b) => a.id - b.id).forEach((child) => ul.appendChild(renderNode(child)));
      li.appendChild(ul);

      initSortable(ul); // ← SortableJS on each children <ul>

      toggle.setAttribute('aria-controls', `children-${node.id}`);
      toggle.addEventListener('click', (e) => {
        e.stopPropagation();
        const collapsed = ul.classList.toggle('collapsed');
        toggle.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
        toggle.innerHTML = collapsed
          ? '<i class="bi bi-chevron-right"></i>'
          : '<i class="bi bi-chevron-down"></i>';
      });
    }

    return li;
  }

  // ── 11) Render tree ──────────────────────────────
  if (roots.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'cat-empty';
    empty.innerHTML = '<i class="bi bi-folder2-open"></i>' +
      '<p>아직 카테고리가 없습니다.<br>왼쪽 폼에서 첫 카테고리를 만들어 보세요.</p>';
    treeContent.appendChild(empty);
    return;
  }

  const rootUl = document.createElement('ul');
  rootUl.id        = 'cat-root-ul';
  rootUl.className = 'category-tree-root';
  roots.sort((a, b) => a.id - b.id).forEach((r) => rootUl.appendChild(renderNode(r)));
  treeContent.appendChild(rootUl);

  initSortable(rootUl); // ← SortableJS on root <ul>
});
