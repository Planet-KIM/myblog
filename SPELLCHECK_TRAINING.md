# 맞춤법 교정 모델 학습 가이드

블로그 글에 최적화된 한국어 맞춤법 교정 모델을 직접 fine-tuning하는 방법입니다.

---

## 전체 구조

```
현재 사용 중인 모델
  한국어: j5ng/et5-typos-corrector   (HuggingFace, T5 기반)
  영어:   oliverguhr/spelling-correction-english-base

fine-tuning 후 교체
  한국어: models/blog-spellcheck/best  (직접 학습한 모델)
```

---

## 1단계: 패키지 설치

```bash
pip install transformers torch sentencepiece datasets beautifulsoup4
```

Python 3.8 환경에서 torch 설치가 느리면 CPU 전용 버전 사용:
```bash
pip install torch --index-url https://download.pytorch.org/whl/cpu
```

---

## 2단계: 학습 실행 (원클릭)

프로젝트 루트에서 실행:

```bash
python scripts/pipeline_train.py
```

내부 동작 순서:
```
[1/5] 블로그 DB에서 텍스트 추출     ← app.db의 기존 게시글 활용
[2/5] 한국어 위키백과 다운로드      ← HuggingFace 자동 다운로드 (첫 실행 시 수 분)
[3/5] 합성 오류 8,000개 생성        ← 항상→하상, 됐다→됬다, 있다→잇다 등
[4/5] train / val 분리              ← 7,200 / 800
[5/5] Fine-tuning (5 epoch)         ← j5ng/et5-typos-corrector 기반으로 추가 학습
```

학습 완료 후 출력:
```
models/
  blog-spellcheck/
    best/          ← 검증 손실이 가장 낮은 체크포인트 (서비스 적용용)
    epoch-1/
    epoch-2/
    ...
```

---

## 3단계: 학습된 모델 서비스에 적용

```bash
SPELLCHECK_KO_MODEL=models/blog-spellcheck/best uvicorn app.main:app --reload
```

`.env` 파일에 영구 등록:
```
SPELLCHECK_KO_MODEL=models/blog-spellcheck/best
```

---

## 옵션 조정

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--samples` | 8000 | 생성할 학습 쌍 수. 많을수록 정확도 ↑, 시간 ↑ |
| `--epochs` | 5 | 반복 학습 횟수. 너무 크면 과적합 |
| `--batch_size` | 8 | 메모리 부족 시 4로 낮추기 |
| `--wiki_lines` | 20000 | 위키 데이터 양 |
| `--skip_download` | - | 데이터가 이미 있을 때 재사용 |

**빠른 테스트 (10분 이내)**:
```bash
python scripts/pipeline_train.py --samples 1000 --epochs 2 --wiki_lines 5000
```

**정확도 높이기**:
```bash
python scripts/pipeline_train.py --samples 20000 --epochs 10
```

**두 번째 실행부터 (위키 재다운로드 건너뜀)**:
```bash
python scripts/pipeline_train.py --skip_download
```

---

## 데이터 직접 준비하기 (고급)

### AI Hub 데이터 사용
1. [aihub.or.kr](https://aihub.or.kr) 접속 → "맞춤법" 검색 → 무료 신청
2. 다운로드한 JSON 파일 변환:
```bash
python scripts/generate_training_data.py aihub \
  --input_file  data/aihub_raw.json \
  --output_file data/spellcheck_aihub.jsonl
```

### 나만의 텍스트로 합성 데이터 생성
```bash
# 1. 깨끗한 텍스트 파일 준비 (한 줄 = 한 문장)
# 2. 합성 오류 생성
python scripts/generate_training_data.py synthetic \
  --input_file  data/my_clean_text.txt \
  --output_file data/my_train.jsonl \
  --samples     5000

# 3. train/val 분리
python scripts/generate_training_data.py split \
  --input_file data/my_train.jsonl
```

---

## 모델 아키텍처 직접 수정하기

```python
from transformers import T5ForConditionalGeneration

# 현재 모델 로드
model = T5ForConditionalGeneration.from_pretrained("j5ng/et5-typos-corrector")

# 전체 구조 확인
print(model)

# 파라미터 수 확인
total = sum(p.numel() for p in model.parameters())
print(f"총 파라미터: {total:,}개")

# 특정 레이어 가중치 확인
print(model.encoder.block[0].layer[0].SelfAttention.q.weight.shape)

# 인코더 동결 (디코더만 학습하고 싶을 때)
for param in model.encoder.parameters():
    param.requires_grad = False
```

학습 시 `--freeze_encoder` 옵션으로 동일하게 적용:
```bash
python scripts/train_spellcheck.py train \
  --train_file data/spellcheck_train.jsonl \
  --freeze_encoder
```

---

## 문제 해결

**메모리 부족 (OOM)**
```bash
python scripts/pipeline_train.py --batch_size 4
```

**위키 다운로드 실패**
```bash
# 위키 없이 블로그 데이터만으로 학습
python scripts/pipeline_train.py --wiki_lines 0 --skip_download
```

**학습이 너무 느림 (CPU)**
- `--samples 2000 --epochs 3` 으로 줄이거나
- GPU가 있는 환경에서 실행 권장

**Python 3.8 TypeError: 'type' object is not subscriptable**
- `pipeline_train.py`의 타입 힌트 문제 → 이미 수정됨
- 최신 파일인지 확인: `head -5 scripts/pipeline_train.py`
