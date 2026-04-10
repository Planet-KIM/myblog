/* ============================================
   Board Categories — Tree Logic
   ============================================ */

document.addEventListener('DOMContentLoaded', function () {
  const dataItems    = Array.from(document.querySelectorAll('.cat-data-item'));
  const treeContent  = document.getElementById('tree-content');
  const parentSelect = document.getElementById('parent_id');
  const rootDropzone = document.getElementById('root-dropzone');
  const deleteModal  = new bootstrap.Modal(document.getElementById('deleteCategoryModal'));
  let   pendingDelete = null;

  // ── 1) Parse node data ───────────────────────────
  const nodesById = {};
  dataItems.forEach((item) => {
    const id       = parseInt(item.dataset.id, 10);
    const parentId = item.dataset.parentId ? parseInt(item.dataset.parentId, 10) : null;
    nodesById[id] = {
      id,
      parentId,
      name:      item.dataset.name,
      created:   item.dataset.created,
      postCount: parseInt(item.dataset.postCount || '0', 10),
      children:  [],
    };
  });

  // ── 2) Build parent→child relationships ─────────
  Object.values(nodesById).forEach((node) => {
    if (node.parentId && nodesById[node.parentId]) {
      nodesById[node.parentId].children.push(node);
    }
  });

  const roots = Object.values(nodesById).filter(
    (node) => !node.parentId || !nodesById[node.parentId]
  );

  // ── API helpers ──────────────────────────────────
  async function moveCategory(categoryId, newParentId) {
    window.loading.show('Moving category…');
    try {
      const res = await fetch('/board/categories/move', {
        method:      'POST',
        headers:     { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({
          category_id:   parseInt(categoryId, 10),
          new_parent_id: newParentId ? parseInt(newParentId, 10) : null,
        }),
      });
      if (res.ok) {
        window.toast.success('Category moved successfully');
        setTimeout(() => window.location.reload(), 800);
      } else {
        window.loading.hide();
        const data = await res.json();
        window.toast.error('Move failed: ' + (data.detail || 'Unknown error'));
      }
    } catch {
      window.loading.hide();
      window.toast.error('Network error. Please try again.');
    }
  }

  async function deleteCategory(categoryId, reassignTo) {
    window.loading.show('Deleting category…');
    const body = new FormData();
    if (reassignTo) body.append('reassign_to', reassignTo);
    try {
      const res = await fetch(`/board/categories/${categoryId}/delete`, {
        method:      'POST',
        credentials: 'same-origin',
        body,
      });
      if (res.ok) {
        window.toast.success('Category deleted');
        setTimeout(() => window.location.reload(), 800);
      } else {
        window.loading.hide();
        const data = await res.json();
        window.toast.error('Delete failed: ' + (data.detail || 'Unknown error'));
      }
    } catch {
      window.loading.hide();
      window.toast.error('Network error. Please try again.');
    }
  }

  async function renameCategory(categoryId, newName, nameSpan) {
    const oldName = nameSpan.textContent;
    try {
      const res = await fetch(`/board/categories/${categoryId}/rename`, {
        method:      'POST',
        headers:     { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({ name: newName }),
      });
      if (res.ok) {
        const data = await res.json();
        nameSpan.textContent = data.name;
        nodesById[categoryId].name = data.name;
        window.toast.success(`Renamed to "${data.name}"`);
      } else {
        nameSpan.textContent = oldName;
        const data = await res.json();
        window.toast.error('Rename failed: ' + (data.detail || 'Unknown error'));
      }
    } catch {
      nameSpan.textContent = oldName;
      window.toast.error('Network error. Please try again.');
    }
  }

  // ── Root dropzone events ─────────────────────────
  rootDropzone.addEventListener('dragenter', (e) => { e.preventDefault(); rootDropzone.classList.add('drag-over'); });
  rootDropzone.addEventListener('dragover',  (e) => { e.preventDefault(); rootDropzone.classList.add('drag-over'); });
  rootDropzone.addEventListener('dragleave', ()  => { rootDropzone.classList.remove('drag-over'); });
  rootDropzone.addEventListener('drop', (e) => {
    e.preventDefault();
    rootDropzone.classList.remove('drag-over');
    const draggedId = e.dataTransfer.getData('text/plain');
    if (draggedId) moveCategory(draggedId, null);
  });

  // ── Delete modal confirm ─────────────────────────
  document.getElementById('confirmDeleteBtn').addEventListener('click', () => {
    if (!pendingDelete) return;
    const reassignTo = document.getElementById('deleteReassignSelect').value || null;
    deleteModal.hide();
    deleteCategory(pendingDelete.id, reassignTo);
    pendingDelete = null;
  });

  // ── Build a single tree node ─────────────────────
  function renderNode(node) {
    const li = document.createElement('li');
    li.className = 'cat-tree-node';
    li.dataset.id = node.id;

    const hasChildren = node.children.length > 0;

    const container = document.createElement('div');
    container.className  = 'cat-item-container';
    container.draggable  = true;
    container.dataset.id = node.id;

    // Drag handle
    const dragHandle = document.createElement('i');
    dragHandle.className = 'bi bi-grip-vertical text-secondary me-1';
    container.appendChild(dragHandle);

    // Drag & drop events
    container.addEventListener('dragstart', (e) => {
      e.dataTransfer.setData('text/plain', node.id);
      e.dataTransfer.effectAllowed = 'move';
      setTimeout(() => {
        container.classList.add('dragging');
        rootDropzone.classList.remove('d-none');
      }, 0);
      e.stopPropagation();
    });
    container.addEventListener('dragend', () => {
      container.classList.remove('dragging');
      rootDropzone.classList.add('d-none');
      document.querySelectorAll('.drag-over').forEach(el => el.classList.remove('drag-over'));
    });
    container.addEventListener('dragenter', (e) => { e.preventDefault(); container.classList.add('drag-over'); e.stopPropagation(); });
    container.addEventListener('dragover',  (e) => { e.preventDefault(); e.dataTransfer.dropEffect = 'move'; container.classList.add('drag-over'); e.stopPropagation(); });
    container.addEventListener('dragleave', (e) => { container.classList.remove('drag-over'); e.stopPropagation(); });
    container.addEventListener('drop', (e) => {
      e.preventDefault();
      container.classList.remove('drag-over');
      e.stopPropagation();
      const draggedId = e.dataTransfer.getData('text/plain');
      if (!draggedId || draggedId == node.id) return;
      if (confirm(`Move "${nodesById[draggedId]?.name || draggedId}" under "${node.name}"?`)) {
        moveCategory(draggedId, node.id);
      }
    });

    // Toggle arrow
    const toggleBtn = document.createElement('button');
    toggleBtn.type      = 'button';
    toggleBtn.className = 'tree-toggle' + (hasChildren ? '' : ' disabled');
    toggleBtn.innerHTML = hasChildren ? '<i class="bi bi-chevron-down"></i>' : '<i class="bi bi-dash"></i>';
    toggleBtn.setAttribute('aria-label', hasChildren ? `Collapse ${node.name}` : 'No children');
    if (hasChildren) toggleBtn.setAttribute('aria-expanded', 'true');

    // Icon + name + badge + meta
    const labelSpan = document.createElement('div');
    labelSpan.className = 'cat-label';

    const icon = document.createElement('i');
    icon.className = `bi cat-icon ${hasChildren ? 'bi-folder2 text-warning' : 'bi-file-earmark-text'}`;
    labelSpan.appendChild(icon);

    const nameSpan = document.createElement('span');
    nameSpan.className   = 'cat-name ms-1';
    nameSpan.textContent = node.name;
    labelSpan.appendChild(nameSpan);

    if (node.postCount > 0) {
      const badge = document.createElement('span');
      badge.className   = 'badge rounded-pill ms-1';
      badge.style.cssText = 'background:var(--primary);font-size:0.68rem;font-weight:500;';
      badge.textContent = node.postCount;
      labelSpan.appendChild(badge);
    }

    const metaSpan = document.createElement('span');
    metaSpan.className   = 'cat-meta d-none d-sm-inline';
    metaSpan.textContent = `ID: ${node.id} · ${node.created}`;
    labelSpan.appendChild(metaSpan);

    // Click → select as parent
    labelSpan.addEventListener('click', () => {
      if (!parentSelect) return;
      parentSelect.value = String(node.id);
      document.querySelectorAll('.cat-item-container.active').forEach(el => el.classList.remove('active'));
      container.classList.add('active');
    });

    // ── Action buttons ──────────────────────────────
    const actions = document.createElement('div');
    actions.className = 'cat-actions';

    // Rename
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
        if (newName && newName !== node.name) {
          await renameCategory(node.id, newName, nameSpan);
        }
      };
      input.addEventListener('keydown', (ev) => {
        if (ev.key === 'Enter')  { ev.preventDefault(); commit(); }
        if (ev.key === 'Escape') { input.replaceWith(nameSpan); }
      });
      input.addEventListener('blur', commit);
    });

    // Delete
    const deleteBtn = document.createElement('button');
    deleteBtn.type      = 'button';
    deleteBtn.className = 'cat-action-btn delete';
    deleteBtn.title     = 'Delete';
    deleteBtn.setAttribute('aria-label', `Delete ${node.name}`);
    deleteBtn.innerHTML = '<i class="bi bi-trash"></i>';
    deleteBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      document.getElementById('deleteCatName').textContent = node.name;

      const reassignSec    = document.getElementById('deleteReassignSection');
      const childWarn      = document.getElementById('deleteChildrenWarning');
      const reassignSelect = document.getElementById('deleteReassignSelect');
      const postCountSpan  = document.getElementById('deletePostCount');

      if (node.postCount > 0) {
        postCountSpan.textContent = node.postCount;
        reassignSelect.innerHTML  = '';
        Object.values(nodesById).forEach((n) => {
          if (n.id === node.id) return;
          const opt = document.createElement('option');
          opt.value       = n.id;
          opt.textContent = n.name;
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

    container.appendChild(toggleBtn);
    container.appendChild(labelSpan);
    container.appendChild(actions);
    li.appendChild(container);

    // Recursive children
    if (hasChildren) {
      const ul = document.createElement('ul');
      ul.id        = `children-${node.id}`;
      ul.className = 'cat-tree-children';
      node.children.sort((a, b) => a.id - b.id).forEach((child) => ul.appendChild(renderNode(child)));
      li.appendChild(ul);

      toggleBtn.setAttribute('aria-controls', `children-${node.id}`);
      toggleBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        const collapsed = ul.classList.toggle('collapsed');
        toggleBtn.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
        toggleBtn.innerHTML = collapsed
          ? '<i class="bi bi-chevron-right"></i>'
          : '<i class="bi bi-chevron-down"></i>';
      });
    }

    return li;
  }

  // ── Render ───────────────────────────────────────
  if (roots.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'cat-empty';
    empty.innerHTML = '<i class="bi bi-folder-x fs-2 d-block mb-2"></i>No categories yet.<br>Create your first one using the form on the left.';
    treeContent.appendChild(empty);
  } else {
    const rootUl = document.createElement('ul');
    rootUl.className = 'category-tree-root';
    roots.sort((a, b) => a.id - b.id).forEach((root) => rootUl.appendChild(renderNode(root)));
    treeContent.appendChild(rootUl);
  }
});
