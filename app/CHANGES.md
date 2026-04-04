# 변경 이력 (Change Log)

> 마지막 업데이트: 2026-03-27
> 기준 커밋: `a48322f` (fix: fix the category method and redesign the post)

---

## 1. 파일 업로드 시스템 전면 재설계

### `app/models.py`
- **추가**: `UploadedFile` 모델
  - 업로드된 모든 파일을 DB에서 추적
  - 필드: `user_id`, `post_id`, `draft_id`, `file_type`, `original_name`, `stored_name`, `file_path`, `url`, `size_bytes`, `mime_type`, `created_at`
  - `post_id`는 발행 전 NULL → 발행 후 연결, `draft_id`는 임시저장 ID

### `app/routers/upload/router.py` ← 전면 재작성
- **이전**: 이미지만 처리하는 단순 업로드
- **이후**: 모든 파일 타입을 처리하는 통합 업로드 시스템

**변경 내용:**
- `FILE_TYPES` dict: image / document / text / code / archive / video / audio 분류 테이블
  - 각 타입별 허용 확장자, 최대 용량, 저장 폴더 정의
- `_classify_file(suffix)`: 확장자로 파일 타입 자동 감지
- `_get_upload_dir(user_id, type_folder, post_id, draft_id)`: 저장 경로 결정
  - 신규 폴더 구조: `uploads/{user_id}/posts/{post_id}/{type}/`
  - 임시 저장: `uploads/{user_id}/drafts/{draft_id}/{type}/`
- `POST /api/upload`: 통합 업로드 엔드포인트 (모든 파일 타입)
- `POST /api/images`: 하위 호환 유지 (이미지만 허용, 내부적으로 /api/upload 호출)
- `GET /api/files/{post_id}`: 게시글 첨부파일 목록 조회
- `DELETE /api/files/{file_id}`: 파일 개별 삭제 (디스크 + DB)
- `relocate_draft_files()`: draft → post 폴더 이관 유틸 함수

### `app/routers/board/router.py`
- **추가**: `from app.routers.upload.router import relocate_draft_files` import
- **추가**: `POST /board/{post_id}/delete` 라우터
  - 첨부파일 DB 레코드 삭제
  - 디스크 uploads 폴더 전체 삭제 (`static/uploads/{user_id}/posts/{post_id}/`)
  - 게시글 DB 삭제 후 목록으로 리다이렉트
- **수정**: `board_update()` — `draft_id` Form 파라미터 추가, 수정 시 새 파일도 post 폴더로 이관
- **수정**: `board_create()` — `relocate_draft_files()` 추가 호출 (기존 `relocate_draft_images()`와 병행)

### `frontend/board_new.js`
- 업로드 엔드포인트: `/api/images` → `/api/upload`
- `window.DRAFT_ID`를 읽어서 FormData에 `draft_id` 추가
  - 이미지 업로드 시 draft 폴더에 저장 → 발행 시 post 폴더로 자동 이관

### `frontend/board_edit.js`
- 업로드 엔드포인트: `/api/images` → `/api/upload`
- `post_id`는 기존대로 `root.dataset.postId`에서 읽음 (수정 시 바로 post 폴더에 저장)

### `app/static/uploads/README.md` ← 신규 생성
- 업로드 폴더 구조 설명
- 파일 타입별 분류 테이블
- 파일 생명주기 (draft → post → delete)
- API 엔드포인트 목록
- DB 추적 방식 설명

### `migrate_uploads.py` ← 신규 생성 (프로젝트 루트)
- 기존 폴더 구조 (`uploads/{user_id}/{YYYY}/{MM}/{post_id}/`) →
  신규 구조 (`uploads/{user_id}/posts/{post_id}/images/`) 마이그레이션
- `--dry-run` 옵션으로 실제 이동 전 미리보기 가능
- DB의 content/content_html URL도 자동 치환

---

## 2. 글쓰기 에디터 UI 개선

### `app/templates/board_new_clean.html`

**레이아웃 스위처 추가**
- 툴바 우측에 4개 버튼: `‹` (left) / `■` (center) / `—` (full) / `›` (right)
- 선택한 레이아웃을 `localStorage('contentLayout')`에 저장
- 글 읽기 페이지에도 자동으로 동일 레이아웃 적용

**Focus 모드 개선**
- 이전: toolbar `opacity: 0` → Focus 버튼 클릭 불가, 빠져나올 방법 없음
- 이후:
  - 화면 우측 하단에 플로팅 `✕ Exit Focus` 버튼 추가
  - `ESC` 키로 Focus 모드 종료
  - navbar, 상단 toolbar, 하단 action bar 모두 숨김

**main 컨테이너 전체 너비 강제**
- `main.container { max-width: 100% !important; padding: 0 !important; margin: 0 !important; }`
- 이전에 Bootstrap container로 인해 에디터가 좌측 정렬되던 문제 해결

### `app/static/css/writing-enhanced.css`

**레이아웃 CSS 추가**
```
.writing-editor-wrapper[data-layout="center"] → max-width: 800px, margin: 0 auto
.writing-editor-wrapper[data-layout="left"]   → max-width: 800px, margin-right: auto
.writing-editor-wrapper[data-layout="right"]  → max-width: 800px, margin-left: auto
.writing-editor-wrapper[data-layout="full"]   → max-width: 100%
```

**레이아웃 스위처 버튼 스타일**
- `.layout-switcher`, `.layout-btn`, `.layout-btn.active` 스타일
- 라이트/다크 모드 대응

**Focus 모드 CSS**
- `.bottom-action-bar`: 하단 버튼 바를 클래스로 분리 (인라인 style 제거)
- `body.focus-active` 시: toolbar, bottom-bar, navbar 모두 `opacity: 0; pointer-events: none; transform`
- `#focusExitBtn`: 우측 하단 고정 반투명 버튼

---

## 3. 글 읽기 페이지 개선

### `app/templates/board_detail_writer.html`

**제목 중복 문제 해결**
- 원인: article-header에 `post.title` 표시 + content_html 안에 `<h1>제목</h1>` 함께 렌더링
- 해결: DOMContentLoaded에서 `.article-content` 첫 번째 자식이 `<h1>`이면 숨김

**레이아웃 동기화**
- `localStorage('contentLayout')` 읽어서 `.reading-container[data-layout]` 적용
- FOUC 방지: `<head>` 인라인 스크립트로 DOMContentLoaded 전에 미리 등록

**레이아웃 CSS 추가**
```
.reading-container[data-layout="center"] → max-width: 800px !important, margin: 0 auto
.reading-container[data-layout="left"]   → max-width: 800px !important, margin-right: auto
.reading-container[data-layout="right"]  → max-width: 800px !important, margin-left: auto
.reading-container[data-layout="full"]   → max-width: 100% !important
```

**main 컨테이너 전체 너비 강제**
- 글쓰기 페이지와 동일하게 `main.container { max-width: 100% !important }`
- 글쓰기/읽기 레이아웃 기준점 통일 → 동일한 위치에 콘텐츠 표시

---

## 4. 디자인 개선 (이전 세션)

### `app/templates/index.html`
- Hero 회전 애니메이션: 30s → 80s (덜 어지럽게)
- 카드 클릭 overlay (`card-link-overlay`) 추가
- 카드 미리보기: `content_html` → `post.preview` (제목 중복 방지)
- 이미지 없는 카드: `onerror="this.style.display='none'"` (깨진 이미지 숨김)

### `app/templates/base.html`
- `.badge-cat { align-self: flex-start }` — 배지 그라디언트가 세로로 늘어나는 버그 수정

### `app/templates/board_list.html`
- 카테고리 필터: `.cat-pill` 컴포넌트 (active 상태 그라디언트)
- 검색: 별도 버튼 제거, 인풋 안에 아이콘 (`search-input-wrap`)
- 모바일: 테이블 숨기고 카드 리스트 표시

### `app/static/js/app.js`
- 네비게이션 active 감지: `===` → `startsWith` (하위 경로도 활성화)
- `initCodeCopy()`: `window.__skipCodeCopy` 플래그 체크 (중복 버튼 방지)

### `app/static/css/components.css`
- `.cat-pill`: 카테고리 필터 버튼
- `.search-input-wrap / .search-input`: 아이콘 내장 검색창
- `.empty-state`: 빈 상태 컴포넌트 (float 애니메이션)
- `.card-link-overlay`: 카드 전체 클릭 가능 오버레이
- `.card-thumbnail-placeholder`: 이미지 없는 카드 placeholder

---

## 폴더 구조 (최종)

```
app/
├── models.py              ← UploadedFile 모델 추가
├── routers/
│   ├── board/router.py    ← delete 라우터 + draft 파일 이관
│   └── upload/router.py   ← 통합 업로드 시스템 (전면 재작성)
├── static/
│   ├── css/
│   │   ├── components.css       ← 공통 컴포넌트 스타일
│   │   └── writing-enhanced.css ← 에디터 레이아웃/Focus 모드
│   ├── js/app.js                ← 네비게이션 active, 코드 복사
│   └── uploads/README.md        ← 업로드 폴더 구조 문서
├── templates/
│   ├── base.html                ← 배지 정렬 수정
│   ├── board_detail_writer.html ← 제목 중복 제거, 레이아웃 동기화
│   ├── board_list.html          ← 카테고리 필터, 검색 개선
│   ├── board_new_clean.html     ← 레이아웃 스위처, Focus 모드
│   └── index.html               ← Hero, 카드 디자인 개선
└── CHANGES.md             ← 이 파일

frontend/
├── board_new.js           ← /api/upload + draft_id 전달
└── board_edit.js          ← /api/upload 엔드포인트 변경

migrate_uploads.py         ← 기존 파일 구조 마이그레이션 스크립트 (루트)
```
