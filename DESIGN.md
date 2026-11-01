# Planet KIM 디자인 시스템

방향: **에디토리얼 미니멀 + 따뜻한 매거진.** 장식을 더하기보다 타이포그래피와 여백으로 위계를 만든다.

- 토큰: [`app/static/css/theme.css`](app/static/css/theme.css)
- 공통 컴포넌트: [`app/static/css/components.css`](app/static/css/components.css)
- 반응형/인쇄: [`app/static/css/mobile.css`](app/static/css/mobile.css)

새 화면을 만들거나 고칠 때 **하드코딩 값을 쓰지 말고 토큰을 쓴다.** 필요한 값이 없으면 토큰을 먼저 추가한다.

정적 파일은 nginx가 7일 동안 캐시하므로, 템플릿에서 CSS·JS를 불러올 때 `?v={{ asset_ver('css/파일.css') }}`를 붙인다 (`app/services/static_assets.py`, 모든 템플릿 환경에 등록됨).

## 토큰

| 분류 | 토큰 | 용도 |
|---|---|---|
| 브랜드 | `--primary` 테라코타 `#b4542f` | 주요 버튼, 활성 상태, 키커 |
| | `--accent` 스카이 `#2a82c4` | 정보성 포인트 (드물게) |
| | `--secondary` 세이지 `#3f8f5c` | 성공·보조 |
| 틴트 | `--primary-soft`, `--accent-soft` | 선택/활성 배경 |
| 표면 | `--bg-body` 종이, `--surface` 카드, `--surface-light`, `--surface-dark` | |
| | `--surface-panel` | 종이 위에 놓인 큰 패널 (홈 커버). 라이트는 한 톤 어둡게, 다크는 한 톤 밝게 |
| | `--surface-tint` | 화면 폭 전체를 덮는 옅은 테라코타 띠 (홈 매거진) |
| 글자 | `--text-primary` 제목, `--text-main` 본문, `--text-muted` 메타 (AA 대비) | |
| 테두리 | `--border`, `--border-light`, `--border-dark` | |
| 글꼴 | `--font-display` 제목 세리프 (Fraunces + Noto Serif KR) | h1–h5, 카드 제목 |
| | `--font-sans` Pretendard | 본문, UI, 메타 |
| | `--font-mono` Fira Code | **코드에만** |
| 글자 크기 | `--fs-xs` 12 · `--fs-sm` 14 · `--fs-base` 16 · `--fs-md` 18 · `--fs-lg` 22 · `--fs-xl` 28 · `--fs-2xl` 36 · `--fs-3xl` 36–52 | |
| 간격 | `--space-xs` 4 · `sm` 8 · `md` 16 · `lg` 24 · `xl` 32 · `2xl` 48 · `3xl` 72 | |
| 모서리 | `--radius-sm` 4 (배지) · `--radius-md` 8 (버튼·입력) · `--radius-lg` 12 (카드) · `--radius-full` (아바타·칩) | |
| 그림자 | `--shadow-sm/md/lg` | 메뉴·모달처럼 **떠 있는 요소** |
| | `--shadow-card` | 테두리 위에 아주 옅게 얹는 **강조 카드** (Bootstrap `.shadow-sm`) |

다크 모드는 `[data-theme="dark"]`에서 같은 이름의 토큰 값만 바뀐다. 컴포넌트에 다크 전용 색을 따로 쓰지 않는다.

## Bootstrap

Bootstrap 5.3 CSS·JS는 모든 페이지에 들어 있다. 컴포넌트(carousel, card, `.nav-underline`, `.btn-group`, `.ratio`, `.stretched-link` 등)와 유틸리티를 그대로 쓰고, [Bootstrap 예제](https://getbootstrap.kr/docs/5.3/examples/)의 레이아웃(Blog, Heroes, Album, Features)을 참고해도 된다.

- `theme.css`가 `--bs-*` 변수를 토큰에 연결한다. 그래서 `.btn-primary`, `.bg-body-tertiary`, `.shadow-sm` 같은 클래스도 브랜드 색과 그림자로 나온다.
- 그림자는 `.shadow-sm`(강조 카드)과 `.shadow`(큰 이미지)까지 쓴다. `.shadow-lg`는 떠 있는 요소에만 쓴다.
- Bootstrap의 파랑, system-ui 글꼴, pill 버튼(`.rounded-pill`)은 쓰지 않는다.

## 홈 (`index.html`)

위에서부터 커버 스토리(캐러셀), 요즘 많이 읽는 글, 매거진 선반, 글 목록과 사이드바가 이어진다. 로그인하지 않은 방문자에게는 "할 수 있는 것" 구역도 보인다. 고르는 규칙은 `app/services/home_sections.py`에 있다.

- 커버는 [Product 예제](https://getbootstrap.kr/docs/5.3/examples/product/)처럼 여백 없이 화면 폭 전체를 채우는 띠다.
  - 맨 위에 있을 때는 메뉴 아래 선도 지워 띠와 이어진다.
  - 띠 안에서 커버 글이 옆으로 넘어가는 레일에 놓인다(왼쪽 이미지, 오른쪽 글).
  - 다음 커버의 이미지 끝이 오른쪽에 살짝 보인다.
  - 넘기는 방법은 스와이프·트랙패드·마우스 끌기·‹ › 버튼·막대·키보드 화살표다(`home.js` `setupCoverRail`).
  - 15초(`--cover-interval`)마다 자동으로 넘어가고, 마지막 다음에는 처음으로 돌아간다.
  - 지금 막대가 차오르며 남은 시간을 보인다.
  - 멈춤/재생 버튼이 있다.
  - 다음 경우에는 잠시 쉰다: 마우스를 올렸을 때, 키보드 포커스가 안에 있을 때, 손가락이나 마우스로 끌 때, 탭이 가려졌을 때, 화면 밖으로 스크롤됐을 때.
  - 손으로 넘기면 15초를 처음부터 다시 센다.
  - OS의 "동작 줄이기"가 켜져 있으면 멈춘 상태로 시작한다.
- 화면 폭 전체 띠는 `.bleed` 클래스와 `--bleed-bg` 색으로 만든다. `.container` 안에서도 배경만 화면 끝까지 칠해진다.
- 한 글은 한 구역에만 나온다. 아래 목록은 위 구역에 나온 글을 뺀다.
- 제목이 없는 글은 본문 첫머리를 제목 자리에 본문 글꼴로 쓴다. 제목도 본문도 없는 글은 홈에 싣지 않는다.
- 이미지는 자르지 않는다(`.plate`).
  - `home.js`가 이미지 가장자리 색으로 남는 여백을 칠한다.
  - 다크 모드에서는 `--media-edge`가 어두운 이미지의 테두리를 살짝 밝힌다.

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

## 모션

- **페이지 전환:** View Transitions API를 쓴다 (`components.css` 맨 아래). 헤더는 고정되고 본문은 0.18초 교차 페이드한다. 클릭한 카드의 제목은 글 상세 제목(`.article-title`)으로 이어진다. 지원하지 않는 브라우저에서는 평소처럼 이동한다.
- **새 글 카드를 만들 때:** 카드 요소에 `data-vt-card`, 제목 요소에 `data-vt-title`을 붙인다. 제목 요소는 블록 요소여야 한다. 이름은 클릭 순간 `app.js`가 붙이므로 `view-transition-name`을 직접 쓰지 않는다. 한 페이지에 같은 이름이 둘이면 전환이 취소된다.
- **허용하는 모션:** 호버 시 색 전환, 기능적 피드백(토스트, 스피너)까지만. OS의 "동작 줄이기"가 켜져 있으면 전환도 끈다.
- **예외:** 홈 커버는 15초마다 자동으로 넘어간다(사용자 요청). 멈춤 버튼과 쉬는 조건을 반드시 함께 둔다(아래 "홈" 참고).

## 하지 않는 것

AI가 만든 템플릿처럼 보이게 하는 주요 원인들이다.

- 그라데이션 배경·버튼, **그라데이션 텍스트**. 예외: 사진 위 글자를 읽히게 하는 어두운 오버레이, 말줄임 페이드.
- 호버 시 떠오르기(`translateY`), 확대(`scale`), 글로우. 호버는 색·테두리만 바꾼다.
- 장식 애니메이션 (float, pulse, shine, 회전 배경, 스크롤 등장 효과).
- UI에 쓰는 이모지 (📅 👁 👍 ✍️). 아이콘이 필요하면 bootstrap-icons의 outline 아이콘을 쓴다.
- 날짜·제목·라벨에 쓰는 모노스페이스 폰트.
- 카드에 진한 그림자 쌓기. 카드는 1px 테두리로 구분하고, 강조할 카드에만 `.shadow-sm`을 옅게 얹는다.
- 버튼에 pill(완전 둥근) 모서리. pill은 칩과 아바타만 쓴다.
- Tailwind 기본색(`#38bdf8`, `#0f172a` 같은 slate/sky 계열) 하드코딩.

## 예외: 사용자 콘텐츠

매거진 에디터에서 사용자가 고른 글자색·하이라이트·드롭캡·레이아웃 색과 코드 신택스 하이라이트는 디자인 장식이 아니라 **콘텐츠**다. 토큰으로 바꾸지 않는다.
