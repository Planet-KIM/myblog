# 샘플 데이터 형식 확인
python scripts/train_spellcheck.py sample

# 학습 실행
python scripts/train_spellcheck.py train \
  --train_file data/spellcheck_train.jsonl \
  --output_dir models/spellcheck-byt5 \
  --print_model  # 아키텍처 직접 확인

# 학습된 모델 적용
SPELLCHECK_MODEL=models/spellcheck-byt5/final uvicorn app.main:app

