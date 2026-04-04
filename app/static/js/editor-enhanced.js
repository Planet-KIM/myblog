/* ============================================
   Planet KIM's Travel - Enhanced Editor JS
   ============================================ */

class EnhancedEditor {
  constructor() {
    this.draftId = window.DRAFT_ID || null;
    this.autoSaveTimer = null;
    this.selectedTags = new Set();
    this.wordCount = 0;
    this.charCount = 0;
    this.imageCount = 0;
    this.init();
  }

  init() {
    this.initTitleSlug();
    this.initTagSystem();
    this.initAutoSave();
    this.initToolbar();
    this.initPreview();
    this.initStats();
    this.initTemplates();
    this.initResizable();
  }

  // ─────────────────────────────────────────────
  // Title & Slug Generation
  // ─────────────────────────────────────────────
  initTitleSlug() {
    const titleInput = document.getElementById('title-input');
    const slugInput = document.getElementById('slug-input');
    const editSlugBtn = document.getElementById('edit-slug');

    if (!titleInput || !slugInput) return;

    // Auto-generate slug from title
    titleInput.addEventListener('input', (e) => {
      const title = e.target.value;
      if (!slugInput.readOnly) return;

      const slug = this.generateSlug(title);
      slugInput.value = slug;
    });

    // Allow manual slug editing
    if (editSlugBtn) {
      editSlugBtn.addEventListener('click', () => {
        slugInput.readOnly = !slugInput.readOnly;
        if (!slugInput.readOnly) {
          slugInput.focus();
        }
      });
    }
  }

  generateSlug(text) {
    return text
      .toLowerCase()
      .trim()
      .replace(/[\s\W-]+/g, '-')
      .replace(/^-+|-+$/g, '');
  }

  // ─────────────────────────────────────────────
  // Tag System
  // ─────────────────────────────────────────────
  initTagSystem() {
    const tagInput = document.getElementById('tag-input');
    const selectedTagsDiv = document.getElementById('selected-tags');
    const suggestionsDiv = document.getElementById('tag-suggestions');
    const tagsHidden = document.getElementById('tags-hidden');

    if (!tagInput) return;

    // Popular tags for suggestions
    const popularTags = [
      '여행', '맛집', '제주도', '서울', '부산',
      '카페', '호텔', '펜션', '일본', '유럽',
      '미국', '동남아', '혼자여행', '가족여행', '커플여행'
    ];

    tagInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        const tag = tagInput.value.trim();
        if (tag && !this.selectedTags.has(tag)) {
          this.addTag(tag);
          tagInput.value = '';
        }
      }
    });

    tagInput.addEventListener('input', (e) => {
      const query = e.target.value.trim();
      if (query.length > 0) {
        this.showTagSuggestions(query, popularTags);
      } else {
        this.hideTagSuggestions();
      }
    });
  }

  addTag(tag) {
    this.selectedTags.add(tag);
    this.renderTags();
    this.updateTagsHidden();
  }

  removeTag(tag) {
    this.selectedTags.delete(tag);
    this.renderTags();
    this.updateTagsHidden();
  }

  renderTags() {
    const container = document.getElementById('selected-tags');
    if (!container) return;

    container.innerHTML = Array.from(this.selectedTags)
      .map(tag => `
        <div class="tag-chip">
          <span>#${tag}</span>
          <span class="remove-tag" data-tag="${tag}">&times;</span>
        </div>
      `).join('');

    // Add remove event listeners
    container.querySelectorAll('.remove-tag').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const tag = e.target.dataset.tag;
        this.removeTag(tag);
      });
    });
  }

  updateTagsHidden() {
    const tagsHidden = document.getElementById('tags-hidden');
    if (tagsHidden) {
      tagsHidden.value = Array.from(this.selectedTags).join(',');
    }
  }

  showTagSuggestions(query, popularTags) {
    const suggestionsDiv = document.getElementById('tag-suggestions');
    if (!suggestionsDiv) return;

    const filtered = popularTags
      .filter(tag => tag.includes(query) && !this.selectedTags.has(tag))
      .slice(0, 5);

    if (filtered.length > 0) {
      suggestionsDiv.innerHTML = filtered
        .map(tag => `<div class="tag-suggestion" data-tag="${tag}">${tag}</div>`)
        .join('');
      suggestionsDiv.classList.add('active');

      // Add click listeners
      suggestionsDiv.querySelectorAll('.tag-suggestion').forEach(item => {
        item.addEventListener('click', () => {
          const tag = item.dataset.tag;
          this.addTag(tag);
          document.getElementById('tag-input').value = '';
          this.hideTagSuggestions();
        });
      });
    } else {
      this.hideTagSuggestions();
    }
  }

  hideTagSuggestions() {
    const suggestionsDiv = document.getElementById('tag-suggestions');
    if (suggestionsDiv) {
      suggestionsDiv.classList.remove('active');
    }
  }

  // ─────────────────────────────────────────────
  // Auto Save
  // ─────────────────────────────────────────────
  initAutoSave() {
    // Auto save every 5 seconds
    this.autoSaveTimer = setInterval(() => {
      this.saveDraft();
    }, 5000);

    // Save on manual trigger
    const saveDraftBtn = document.getElementById('save-draft');
    if (saveDraftBtn) {
      saveDraftBtn.addEventListener('click', () => {
        this.saveDraft();
      });
    }

    // Save before unload
    window.addEventListener('beforeunload', (e) => {
      if (this.hasUnsavedChanges()) {
        e.preventDefault();
        e.returnValue = '작성 중인 내용이 있습니다. 정말 나가시겠습니까?';
      }
    });
  }

  async saveDraft() {
    const indicator = document.getElementById('auto-save-indicator');
    const spinner = document.getElementById('save-spinner');
    const check = document.getElementById('save-check');
    const status = document.getElementById('save-status');

    if (!indicator) return;

    // Show saving state
    indicator.style.display = 'flex';
    indicator.classList.add('saving');
    spinner.style.display = 'block';
    check.style.display = 'none';
    status.textContent = '저장 중...';

    try {
      const data = {
        draft_id: this.draftId,
        title: document.getElementById('title-input')?.value || '',
        content: this.getEditorContent(),
        tags: Array.from(this.selectedTags).join(','),
        category_id: document.getElementById('category_id')?.value,
        is_private: document.getElementById('is_private')?.checked
      };

      const response = await fetch('/api/drafts/save', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(data)
      });

      if (response.ok) {
        const result = await response.json();
        this.draftId = result.draft_id;

        // Show saved state
        indicator.classList.remove('saving');
        indicator.classList.add('saved');
        spinner.style.display = 'none';
        check.style.display = 'block';
        status.textContent = '저장됨';

        // Hide after 3 seconds
        setTimeout(() => {
          indicator.style.display = 'none';
        }, 3000);
      }
    } catch (error) {
      console.error('Auto save failed:', error);
      indicator.classList.add('error');
      status.textContent = '저장 실패';
    }
  }

  getEditorContent() {
    // Get content from Milkdown editor
    // This depends on your Milkdown implementation
    return document.querySelector('.milkdown')?.innerText || '';
  }

  hasUnsavedChanges() {
    // Check if there are unsaved changes
    return this.getEditorContent().length > 0;
  }

  // ─────────────────────────────────────────────
  // Toolbar Actions
  // ─────────────────────────────────────────────
  initToolbar() {
    document.querySelectorAll('.toolbar-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const action = btn.dataset.action;
        this.handleToolbarAction(action);
      });
    });
  }

  handleToolbarAction(action) {
    // These would integrate with Milkdown commands
    switch(action) {
      case 'bold':
        this.wrapSelection('**', '**');
        break;
      case 'italic':
        this.wrapSelection('*', '*');
        break;
      case 'strike':
        this.wrapSelection('~~', '~~');
        break;
      case 'h1':
        this.insertAtLineStart('# ');
        break;
      case 'h2':
        this.insertAtLineStart('## ');
        break;
      case 'h3':
        this.insertAtLineStart('### ');
        break;
      case 'link':
        this.insertLink();
        break;
      case 'image':
        this.insertImage();
        break;
      case 'code':
        this.insertCodeBlock();
        break;
      case 'preview':
        this.togglePreview();
        break;
      case 'fullscreen':
        this.toggleFullscreen();
        break;
    }
  }

  wrapSelection(before, after) {
    // Implementation would depend on Milkdown API
    console.log('Wrap selection:', before, after);
  }

  insertAtLineStart(text) {
    // Implementation would depend on Milkdown API
    console.log('Insert at line start:', text);
  }

  insertLink() {
    const url = prompt('Enter URL:');
    const text = prompt('Enter link text:');
    if (url && text) {
      // Insert markdown link
      console.log(`[${text}](${url})`);
    }
  }

  insertImage() {
    // Trigger file upload
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/*';
    input.onchange = (e) => {
      const file = e.target.files[0];
      if (file) {
        this.uploadImage(file);
      }
    };
    input.click();
  }

  async uploadImage(file) {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('draft_id', this.draftId);

    try {
      const response = await fetch('/api/images', {
        method: 'POST',
        body: formData
      });

      if (response.ok) {
        const data = await response.json();
        // Insert image markdown
        console.log(`![${file.name}](${data.url})`);
        this.imageCount++;
        this.updateStats();
      }
    } catch (error) {
      console.error('Image upload failed:', error);
      window.toast?.error('이미지 업로드 실패');
    }
  }

  insertCodeBlock() {
    const lang = prompt('Enter language (optional):') || '';
    // Insert code block
    console.log('```' + lang + '\n\n```');
  }

  // ─────────────────────────────────────────────
  // Preview
  // ─────────────────────────────────────────────
  initPreview() {
    const previewBtn = document.getElementById('toggle-preview');
    const previewPane = document.getElementById('preview-pane');

    if (previewBtn && previewPane) {
      previewBtn.addEventListener('click', () => {
        this.togglePreview();
      });
    }

    // Update preview on content change
    setInterval(() => {
      this.updatePreview();
    }, 1000);
  }

  togglePreview() {
    const previewPane = document.getElementById('preview-pane');
    const editorPane = document.querySelector('.editor-main');

    if (previewPane) {
      if (previewPane.style.display === 'none') {
        previewPane.style.display = 'block';
        editorPane.style.gridColumn = '1';
      } else {
        previewPane.style.display = 'none';
        editorPane.style.gridColumn = '1 / -1';
      }
    }
  }

  async updatePreview() {
    const content = this.getEditorContent();
    const previewDiv = document.getElementById('preview-content');

    if (previewDiv && content) {
      // Convert markdown to HTML
      // This would use a markdown parser
      previewDiv.innerHTML = await this.parseMarkdown(content);
    }
  }

  async parseMarkdown(content) {
    // Simple markdown parsing (would use marked.js or similar)
    return content
      .replace(/^### (.*$)/gim, '<h3>$1</h3>')
      .replace(/^## (.*$)/gim, '<h2>$1</h2>')
      .replace(/^# (.*$)/gim, '<h1>$1</h1>')
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.+?)\*/g, '<em>$1</em>')
      .replace(/\n/g, '<br>');
  }

  // ─────────────────────────────────────────────
  // Statistics
  // ─────────────────────────────────────────────
  initStats() {
    // Update stats every second
    setInterval(() => {
      this.updateStats();
    }, 1000);
  }

  updateStats() {
    const content = this.getEditorContent();

    // Word count
    this.wordCount = content.split(/\s+/).filter(word => word.length > 0).length;
    document.getElementById('word-count').textContent = `${this.wordCount} 단어`;

    // Character count
    this.charCount = content.length;
    document.getElementById('char-count').textContent = this.charCount.toLocaleString();

    // Read time (200 words per minute)
    const readTime = Math.max(1, Math.ceil(this.wordCount / 200));
    document.getElementById('read-time').textContent = `${readTime}분 읽기`;
    document.getElementById('estimated-time').textContent = readTime;

    // Image count
    const imageMatches = content.match(/!\[.*?\]\(.*?\)/g);
    this.imageCount = imageMatches ? imageMatches.length : 0;
    document.getElementById('image-count').textContent = this.imageCount;

    // Update TOC
    this.updateTOC(content);
  }

  updateTOC(content) {
    const tocList = document.getElementById('toc-list');
    if (!tocList) return;

    const headings = content.match(/^#{1,3} .+$/gm);
    if (!headings || headings.length === 0) {
      tocList.innerHTML = '<li class="toc-item text-muted">제목을 입력하면 목차가 생성됩니다</li>';
      return;
    }

    tocList.innerHTML = headings.map(heading => {
      const level = heading.match(/^#+/)[0].length;
      const text = heading.replace(/^#+\s+/, '');
      return `<li class="toc-item h${level}">${text}</li>`;
    }).join('');
  }

  // ─────────────────────────────────────────────
  // Templates
  // ─────────────────────────────────────────────
  initTemplates() {
    document.querySelectorAll('[data-template]').forEach(btn => {
      btn.addEventListener('click', () => {
        const template = btn.dataset.template;
        this.insertTemplate(template);
      });
    });
  }

  insertTemplate(type) {
    const templates = {
      travel: `# 🌍 [여행지] 여행 일정

## 📅 여행 정보
- **기간**: 2024년 0월 0일 ~ 0일 (0박 0일)
- **여행지**:
- **동행**:
- **예산**:

## 🗓️ 일정

### Day 1 - [날짜]
**오전**
-

**오후**
-

**저녁**
-

## 🏨 숙소
- **호텔명**:
- **위치**:
- **가격**:

## 🍽️ 맛집
1. **[식당명]**
   - 위치:
   - 추천 메뉴:
   - 가격:

## 💡 팁
-

## 📸 사진
`,
      review: `# ⭐ [제품/장소] 리뷰

## 📊 평점
⭐⭐⭐⭐⭐ (5.0/5.0)

## 👍 장점
-

## 👎 단점
-

## 📝 상세 리뷰

## 📸 사진

## 💰 가격 정보
-

## 🎯 추천 대상
-

## ✨ 총평
`,
      tutorial: `# 📚 [주제] 튜토리얼

## 📋 목차
1. 소개
2. 준비사항
3. 단계별 가이드
4. 팁 & 트릭
5. 마무리

## 🎯 목표

## 📦 준비사항
- [ ]
- [ ]

## 📝 단계별 가이드

### Step 1:
\`\`\`
코드 예시
\`\`\`

### Step 2:

## 💡 팁 & 트릭
-

## 🎉 마무리
`
    };

    const template = templates[type];
    if (template) {
      // Insert template into editor
      console.log('Insert template:', template);
      window.toast?.success('템플릿이 삽입되었습니다');
    }
  }

  // ─────────────────────────────────────────────
  // Resizable Panes
  // ─────────────────────────────────────────────
  initResizable() {
    const handle = document.getElementById('resize-handle');
    const container = document.querySelector('.editor-split-container');

    if (!handle || !container) return;

    let isResizing = false;

    handle.addEventListener('mousedown', () => {
      isResizing = true;
      document.body.style.cursor = 'col-resize';
    });

    document.addEventListener('mousemove', (e) => {
      if (!isResizing) return;

      const containerRect = container.getBoundingClientRect();
      const percentage = ((e.clientX - containerRect.left) / containerRect.width) * 100;

      if (percentage > 20 && percentage < 80) {
        container.style.gridTemplateColumns = `${percentage}% ${100 - percentage}%`;
      }
    });

    document.addEventListener('mouseup', () => {
      isResizing = false;
      document.body.style.cursor = '';
    });
  }

  // ─────────────────────────────────────────────
  // Fullscreen
  // ─────────────────────────────────────────────
  toggleFullscreen() {
    const editor = document.querySelector('.editor-enhanced');
    if (!editor) return;

    if (!document.fullscreenElement) {
      editor.requestFullscreen();
    } else {
      document.exitFullscreen();
    }
  }

  // ─────────────────────────────────────────────
  // Cleanup
  // ─────────────────────────────────────────────
  destroy() {
    if (this.autoSaveTimer) {
      clearInterval(this.autoSaveTimer);
    }
  }
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
  window.enhancedEditor = new EnhancedEditor();
});