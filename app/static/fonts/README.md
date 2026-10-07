# 번들 폰트

## Pretendard-Bold.ttf
- 글별 동적 OG 이미지(`app/services/og_image.py`)가 한글 제목을 렌더링하는 데 사용.
- 원본: Pretendard (https://github.com/orioncactus/pretendard) v1.3.9
- 라이선스: SIL Open Font License 1.1 — `Pretendard-OFL.txt` 참고(재배포 허용).
- 전체 Pretendard에서 **한글(가-힣)+라틴+문장부호 범위만 서브셋**하여 용량을 줄임
  (CJK 한자 등 제외). 서브셋은 `fonttools`로 생성.
