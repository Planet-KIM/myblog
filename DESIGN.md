# Planet KIM 디자인 시스템

방향: **에디토리얼 미니멀 + 따뜻한 매거진.** 장식을 더하기보다 타이포그래피와 여백으로 위계를 만든다.

- 토큰: [`app/static/css/theme.css`](app/static/css/theme.css)
- 공통 컴포넌트: [`app/static/css/components.css`](app/static/css/components.css)
- 반응형/인쇄: [`app/static/css/mobile.css`](app/static/css/mobile.css)

새 화면을 만들거나 고칠 때 **하드코딩 값을 쓰지 말고 토큰을 쓴다.** 필요한 값이 없으면 토큰을 먼저 추가한다.

## 토큰

| 분류 | 토큰 | 용도 |
|---|---|---|
| 브랜드 | `--primary` 테라코타 `#b4542f` | 주요 버튼, 활성 상태, 키커 |
| | `--accent` 스카이 `#2a82c4` | 정보성 포인트 (드물게) |
| | `--secondary` 세이지 `#3f8f5c` | 성공·보조 |
| 틴트 | `--primary-soft`, `--accent-soft` | 선택/활성 배경 |
| 표면 | `--bg-body` 종이, `--surface` 카드, `--surface-light`, `--surface-dark` | |
| 글자 | `--text-primary` 제목, `--text-main` 본문, `--text-muted` 메타 (AA 대비) | |
| 테두리 | `--border`, `--border-light`, `--border-dark` | |
| 글꼴 | `--font-display` 제목 세리프 (Fraunces + Noto Serif KR) | h1–h5, 카드 제목 |
| | `--font-sans` Pretendard | 본문, UI, 메타 |
| | `--font-mono` Fira Code | **코드에만** |
| 글자 크기 | `--fs-xs` 12 · `--fs-sm` 14 · `--fs-base` 16 · `--fs-md` 18 · `--fs-lg` 22 · `--fs-xl` 28 · `--fs-2xl` 36 · `--fs-3xl` 36–52 | |
| 간격 | `--space-xs` 4 · `sm` 8 · `md` 16 · `lg` 24 · `xl` 32 · `2xl` 48 · `3xl` 72 | |
| 모서리 | `--radius-sm` 4 (배지) · `--radius-md` 8 (버튼·입력) · `--radius-lg` 12 (카드) · `--radius-full` (아바타·칩) | |
| 그림자 | `--shadow-sm/md/lg` | 메뉴·모달처럼 **떠 있는 요소에만** |

다크 모드는 `[data-theme="dark"]`에서 같은 이름의 토큰 값만 바뀐다. 컴포넌트에 다크 전용 색을 따로 쓰지 않는다.

## 공통 컴포넌트

| 클래스 | 용도 |
|---|---|
| `.page-header` + `.eyebrow` + `h1` + `.lead-text` | 모든 목록·허브 페이지 상단 |
| `.meta-row` | 작성자 · 날짜 · 조회수 (가운뎃점 구분, 이모지 없음) |
| `.avatar` (`-sm`/`-lg`/`-xl`) | 이미지 또는 이니셜 |
| `.chip` (`.active`) | 태그·필터 |
| `.badge-tint` (`-sea`/`-forest`/`-sunset`/`-rose`/`-violet`/`-amber`) | 카테고리·상태 라벨 |
| `.btn-travel` / `.btn-ghost` | 주요 / 보조 버튼 (Bootstrap `.btn-primary`, `.btn-outline-secondary`도 같은 톤) |
| `.travel-card` | 글 카드 (이름은 레거시, 주제 중립) |
| `.page-card`, `.section-title`, `.empty-state`, `.segmented-control` | |

## 문구 규칙

- **영어:** 상단 메뉴(Home, Archive, Explore, About)와 `.eyebrow` 라벨(ARCHIVE, DASHBOARD 등)처럼 길을 안내하는 짧은 라벨만.
- **한국어:** 그 밖의 제목, 본문, 버튼, 필터, 빈 화면 문구, 메타 전부.
- **메타 형식:** `2026.05.31 · 조회 9 · 1분`. 날짜는 점으로 구분하고, 이모지는 쓰지 않는다.
- **카테고리 표기:** 카드와 글 상세 모두 `.eyebrow` 텍스트 (배지로 쓰지 않는다).

## 하지 않는 것

AI가 만든 템플릿처럼 보이게 하는 주요 원인들이다.

- 그라데이션 배경·버튼, **그라데이션 텍스트**. 예외: 사진 위 글자를 읽히게 하는 어두운 오버레이, 말줄임 페이드.
- 호버 시 떠오르기(`translateY`), 확대(`scale`), 글로우. 호버는 색·테두리만 바꾼다.
- 장식 애니메이션 (float, pulse, shine, 회전 배경, 스크롤 등장 효과).
- UI에 쓰는 이모지 (📅 👁 👍 ✍️). 아이콘이 필요하면 bootstrap-icons의 outline 아이콘을 쓴다.
- 날짜·제목·라벨에 쓰는 모노스페이스 폰트.
- 카드에 그림자 쌓기. 카드는 1px 테두리로 구분한다.
- 버튼에 pill(완전 둥근) 모서리. pill은 칩과 아바타만 쓴다.
- Tailwind 기본색(`#38bdf8`, `#0f172a` 같은 slate/sky 계열) 하드코딩.

## 예외: 사용자 콘텐츠

매거진 에디터에서 사용자가 고른 글자색·하이라이트·드롭캡·레이아웃 색과 코드 신택스 하이라이트는 디자인 장식이 아니라 **콘텐츠**다. 토큰으로 바꾸지 않는다.
