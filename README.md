# FastAPI Blog & Board (Milkdown Crepe + Vite)

## 기능 요약

- /main : 개발자 CV + 최근 포스트
- /     : 블로그 메인 (BoardPost 기반, private 필터링)
- /board/ : 게시판 리스트 (Public + 내 Private)
- /board/new : Milkdown Crepe 기반 Markdown 에디터 (로그인 필요)
    - 제목은 마크다운의 첫 번째 non-empty 라인에서 자동 추출
- /board/{id} : 글 상세 (Markdown 렌더링 + 코드 하이라이트, private 권한 체크)
- /board/{id}/edit : 글 수정 (작성자 본인만 접근 가능)
- /auth/signup : 회원가입 (이메일 + 비밀번호 규칙)
- /auth/login : 로그인
- /auth/logout : 로그아웃
- /admin/ : Admin Dashboard (BoardPost = BlogPost 통합 관리)

## Signup 규칙

- 아이디는 이메일 형식
- 비밀번호는 8자 이상, 영문/숫자/특수문자를 각각 1개 이상 포함

---

## 1. Python 백엔드 실행

```bash
# 가상환경 생성 (선택)
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

pip install -r requirements.txt

uvicorn app.main:app --reload
```

서버가 올라가면:  
- http://127.0.0.1:8000/main
- http://127.0.0.1:8000/board/

---

## 2. 프론트엔드 (Milkdown Crepe) 번들 빌드

```bash
cd frontend
npm install
npm run build
```

빌드 결과:

- `app/static/editor/board_new.js`
- `app/static/editor/board_edit.js`

가 생성되고,  
`/board/new`, `/board/{id}/edit`에서 Milkdown 에디터가 동작합니다.

---

## 3. 개발 플로우

1. 한 번 `npm run build`로 에디터 번들을 만든다.
2. FastAPI 서버를 띄우고 (`uvicorn app.main:app --reload`)
3. 브라우저에서:
    - `/auth/signup` → 계정 만들기
    - `/auth/login` → 로그인
    - `/board/new` → Milkdown으로 글 작성
    - `/board/` & `/board/{id}` → 보기/수정
