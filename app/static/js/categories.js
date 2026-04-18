/* ============================================
   Board Categories — Tree Logic
   Libraries: Chart.js, Fuse.js, Tom Select, SortableJS
   ============================================ */

document.addEventListener('DOMContentLoaded', function () {

  // ── Color palette (MIT / Apache 2.0 safe colors) ──
  const COLORS = [
    '#6366f1', '#10b981', '#f59e0b', '#ef4444',
    '#8b5cf6', '#06b6d4', '#f97316', '#ec4899',
    '#14b8a6', '#84cc16',
  ];
  const getColor = (id) => COLORS[id % COLORS.length];

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
  (function initChart() {
    if (!window.Chart) return;

    // Recursively sum post counts for a node + all descendants
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
        '<p class="text-center text-muted small py-3 mb-0" style="border-top:1px solid var(--border)">' +
        'Post some articles to see the distribution chart.</p>';
      return;
    }

    // Dynamic height based on root category count
    const chartH = Math.min(280, Math.max(80, rootItems.length * 42));
    container.style.height = chartH + 'px';

    const css       = getComputedStyle(document.documentElement);
    const clrBorder = css.getPropertyValue('--border').trim()     || '#334155';
    const clrMuted  = css.getPropertyValue('--text-muted').trim() || '#94a3b8';
    const clrMain   = css.getPropertyValue('--text-main').trim()  || '#e2e8f0';

    new Chart(document.getElementById('stats-chart').getContext('2d'), {
      type: 'bar',
      data: {
        labels:   rootItems.map((i) => i.label),
        datasets: [{
          data:            rootItems.map((i) => i.count),
          backgroundColor: rootItems.map((i) => i.color + 'bb'),
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
                ` ${c.raw} post${c.raw !== 1 ? 's' : ''} ` +
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
  (function initSearch() {
    const input = document.getElementById('categorySearch');
    if (!input) return;

    // Recursively collect all descendant IDs
    function collectDescendants(nodeId, acc) {
      const node = nodesById[nodeId];
      if (!node) return;
      node.children.forEach((child) => {
        acc.add(child.id);
        collectDescendants(child.id, acc);
      });
    }

    // Fuse.js를 쓸 수 있으면 퍼지 검색, 아니면 includes 폴백
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
        allLi.forEach((el) => (el.style.display = ''));
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
          el.style.display = '';
          const ul = document.getElementById(`children-${nodeId}`);
          if (ul) ul.classList.remove('collapsed');
        } else {
          el.style.display = 'none';
        }
      });
    });
  })();

  // ── 5) Tom Select — enhanced parent dropdown ─────
  (function initTomSelect() {
    if (!window.TomSelect || !parentSelect) return;

    tomSelect = new TomSelect('#parent_id', {
      create: false,
      render: {
        option: function (data, escape) {
          const nId  = parseInt(data.value);
          const dot  = nId ? `<span class="ts-color-dot" style="background:${getColor(nId)}"></span>` : '';
          return `<div class="d-flex align-items-center gap-2">${dot}<span>${escape(data.text)}</span></div>`;
        },
        item: function (data, escape) {
          const nId  = parseInt(data.value);
          const dot  = nId ? `<span class="ts-color-dot" style="background:${getColor(nId)}"></span>` : '';
          return `<div class="d-flex align-items-center gap-2">${dot}<span>${escape(data.text)}</span></div>`;
        },
      },
    });
  })();

  // ── 6) Chart.js — Breakdown (개별 카테고리 직접 포스트 수) ──
  let breakdownChartInited = false;

  function initBreakdownChart() {
    if (breakdownChartInited || !window.Chart) return;
    breakdownChartInited = true;

    const container = document.getElementById('breakdown-chart-container');
    if (!container) return;

    // 트리 순서로 모든 카테고리 나열 (루트 → 자식)
    const items = [];
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
        '<p class="text-center text-muted small py-3 mb-0">' +
        'No posts in any category yet.</p>';
      return;
    }

    const chartH = Math.min(320, Math.max(80, items.length * 40));
    container.style.height = chartH + 'px';

    const css       = getComputedStyle(document.documentElement);
    const clrBorder = css.getPropertyValue('--border').trim()     || '#334155';
    const clrMuted  = css.getPropertyValue('--text-muted').trim() || '#94a3b8';
    const clrMain   = css.getPropertyValue('--text-main').trim()  || '#e2e8f0';

    new Chart(document.getElementById('breakdown-chart').getContext('2d'), {
      type: 'bar',
      data: {
        labels:   items.map((i) => i.label),
        datasets: [{
          data:            items.map((i) => i.count),
          backgroundColor: items.map((i) => i.color + (i.depth > 0 ? '88' : 'bb')),
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
                ` ${c.raw} post${c.raw !== 1 ? 's' : ''} (direct)`,
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
          : 'top level';

        if (confirm(`Move "${movedName}" to "${targetName}"?`)) {
          moveCategory(movedId, newParentId);
        } else {
          window.location.reload();
        }
      },
    });
  }

  // ── 8) API helpers ───────────────────────────────
  async function moveCategory(id, newParentId) {
    window.loading.show('Moving category…');
    try {
      const res = await fetch('/board/categories/move', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'same-origin',
        body: JSON.stringify({ category_id: id, new_parent_id: newParentId ?? null }),
      });
      if (res.ok) {
        window.toast.success('Category moved');
        setTimeout(() => window.location.reload(), 700);
      } else {
        window.loading.hide();
        window.toast.error('Move failed: ' + ((await res.json()).detail || 'Unknown error'));
      }
    } catch { window.loading.hide(); window.toast.error('Network error.'); }
  }

  async function deleteCategory(id, reassignTo) {
    window.loading.show('Deleting category…');
    const body = new FormData();
    if (reassignTo) body.append('reassign_to', reassignTo);
    try {
      const res = await fetch(`/board/categories/${id}/delete`, { method: 'POST', credentials: 'same-origin', body });
      if (res.ok) {
        window.toast.success('Category deleted');
        setTimeout(() => window.location.reload(), 700);
      } else {
        window.loading.hide();
        window.toast.error('Delete failed: ' + ((await res.json()).detail || 'Unknown error'));
      }
    } catch { window.loading.hide(); window.toast.error('Network error.'); }
  }

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
        window.toast.success(`Renamed to "${data.name}"`);
      } else {
        nameSpan.textContent = oldName;
        window.toast.error('Rename failed: ' + ((await res.json()).detail || 'Unknown error'));
      }
    } catch { nameSpan.textContent = oldName; window.toast.error('Network error.'); }
  }

  // ── 8) Context menu ──────────────────────────────
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
        ctxMenu.style.left = x + 'px';
        ctxMenu.style.top  = y + 'px';
        ctxMenu.classList.add('visible');
      });
    }

    // Grip handle (SortableJS handle target)
    const grip = document.createElement('i');
    grip.className = 'bi bi-grip-vertical text-secondary me-1';
    grip.style.cssText = 'cursor:grab;flex-shrink:0;';
    container.appendChild(grip);

    // Toggle
    const toggle = document.createElement('button');
    toggle.type      = 'button';
    toggle.className = 'tree-toggle' + (hasChildren ? '' : ' disabled');
    toggle.innerHTML = hasChildren ? '<i class="bi bi-chevron-down"></i>' : '<i class="bi bi-dash"></i>';
    toggle.setAttribute('aria-label', hasChildren ? `Collapse ${node.name}` : 'No children');
    if (hasChildren) toggle.setAttribute('aria-expanded', 'true');
    container.appendChild(toggle);

    // Label: color dot + icon + name + badge + meta
    const label = document.createElement('div');
    label.className = 'cat-label';

    const dot = document.createElement('span');
    dot.className       = 'cat-color-dot';
    dot.style.background = color;
    label.appendChild(dot);

    const icon = document.createElement('i');
    icon.className = `bi cat-icon ${hasChildren ? 'bi-folder2 text-warning' : 'bi-file-earmark-text'}`;
    label.appendChild(icon);

    const nameSpan = document.createElement('span');
    nameSpan.className   = 'cat-name ms-1';
    nameSpan.textContent = node.name;
    label.appendChild(nameSpan);

    if (node.postCount > 0) {
      const badge = document.createElement('span');
      badge.className     = 'badge rounded-pill ms-1';
      badge.style.cssText = `background:${color};font-size:0.68rem;`;
      badge.textContent   = node.postCount;
      label.appendChild(badge);
    }

    const meta = document.createElement('span');
    meta.className   = 'cat-meta d-none d-sm-inline';
    meta.textContent = `ID: ${node.id} · ${node.created}`;
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
    renameBtn.title     = 'Rename';
    renameBtn.setAttribute('aria-label', `Rename ${node.name}`);
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
    deleteBtn.title     = 'Delete';
    deleteBtn.setAttribute('aria-label', `Delete ${node.name}`);
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
    empty.innerHTML = '<i class="bi bi-folder-x fs-2 d-block mb-2"></i>' +
      'No categories yet.<br>Create your first one using the form on the left.';
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
