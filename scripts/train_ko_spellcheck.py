"""
한국어 맞춤법 교정 모델 Fine-tuning 스크립트
============================================
대상 모델: paust/pko-t5-large  (Apache 2.0, 재학습/배포 가능)
태스크:    seq2seq 교정  — "맞춤법 교정: {오류문}" → "{교정문}"

== 빠른 시작 ==
  # 1) 의존성 설치
  pip install transformers datasets accelerate sentencepiece

  # 2) 데이터 준비 (CSV, 탭 구분 텍스트, JSONL 모두 지원)
  #    필수 컬럼: noisy (오류 문장), clean (정답 문장)
  #    예시: data/ko_correction_train.csv

  # 3) 학습 실행
  python scripts/train_ko_spellcheck.py \\
      --data_path  data/ko_correction_train.csv \\
      --output_dir models/ko-pko-t5-finetuned \\
      --epochs 3 \\
      --batch_size 8

  # 4) 서버에 적용 (.env 또는 환경변수)
  SPELLCHECK_KO_QUALITY_MODEL=models/ko-pko-t5-finetuned

== 데이터 형식 ==
  CSV  : noisy,clean 헤더 필수
  JSONL: {"noisy": "오류 문장", "clean": "정답 문장"} 한 줄씩
  TSV  : noisy\tclean (헤더 없어도 됨)

== 권장 데이터셋 ==
  - AI Hub '한국어 문법 오류 수정 데이터' (aihub.or.kr, 무료 신청)
  - 국립국어원 모두의말뭉치 맞춤법 교정 말뭉치
  - 직접 수집: (오타 삽입된 문장, 원문) 쌍

== 학습 후 성능 평가 ==
  python scripts/train_ko_spellcheck.py --eval_only \\
      --model_path models/ko-pko-t5-finetuned \\
      --data_path  data/ko_correction_val.csv
"""

import argparse
import os
import csv
import json
from pathlib import Path
from typing import Dict, List


# ── 인자 파싱 ─────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description="한국어 맞춤법 교정 T5 Fine-tuning")
    p.add_argument("--base_model",  default="paust/pko-t5-large",
                   help="HuggingFace 모델 ID 또는 로컬 경로 (기본: paust/pko-t5-large)")
    p.add_argument("--data_path",   required=True,
                   help="학습 데이터 파일 (.csv / .jsonl / .tsv)")
    p.add_argument("--output_dir",  default="models/ko-pko-t5-finetuned",
                   help="학습된 모델 저장 경로")
    p.add_argument("--val_path",    default=None,
                   help="검증 데이터 파일 (없으면 train의 10%% 사용)")
    p.add_argument("--epochs",      type=int,   default=3)
    p.add_argument("--batch_size",  type=int,   default=8,
                   help="GPU 메모리에 맞게 조정. M-series 32GB: 8~16 권장")
    p.add_argument("--lr",          type=float, default=3e-4)
    p.add_argument("--max_input",   type=int,   default=256,
                   help="입력 최대 토큰 수 (prefix 포함)")
    p.add_argument("--max_target",  type=int,   default=256,
                   help="출력 최대 토큰 수")
    p.add_argument("--prefix",      default="맞춤법 교정: ",
                   help="T5 입력 prefix (서버 설정과 반드시 일치시킬 것)")
    p.add_argument("--eval_only",   action="store_true",
                   help="학습 없이 평가만 실행")
    p.add_argument("--model_path",  default=None,
                   help="--eval_only 시 평가할 모델 경로")
    p.add_argument("--warmup_ratio", type=float, default=0.1)
    p.add_argument("--weight_decay", type=float, default=0.01)
    p.add_argument("--save_steps",   type=int,   default=500)
    p.add_argument("--logging_steps",type=int,   default=100)
    return p.parse_args()


# ── 데이터 로더 ───────────────────────────────────────────

def load_pairs(path: str) -> List[Dict]:
    """
    (noisy, clean) 쌍을 로드합니다.
    지원 형식: .csv / .tsv / .jsonl / .json
    """
    path = Path(path)
    pairs = []

    def _extract(obj):
        noisy = obj.get("noisy") or obj.get("input") or obj.get("wrong") or obj.get("original")
        clean = obj.get("clean") or obj.get("output") or obj.get("correct") or obj.get("corrected")
        return noisy, clean

    if path.suffix == ".jsonl":
        with open(path, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                obj = json.loads(line.strip())
                noisy, clean = _extract(obj)
                if noisy and clean:
                    pairs.append({"noisy": noisy, "clean": clean})

    elif path.suffix == ".json":
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            for k in ("data", "records", "items"):
                if k in data:
                    data = data[k]
                    break
        for obj in data:
            noisy, clean = _extract(obj)
            if noisy and clean:
                pairs.append({"noisy": noisy, "clean": clean})

    elif path.suffix in (".csv", ".tsv"):
        delim = "\t" if path.suffix == ".tsv" else ","
        with open(path, encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f, delimiter=delim)
            # 헤더가 없는 TSV 처리
            if reader.fieldnames and "noisy" not in reader.fieldnames:
                f.seek(0)
                reader = csv.reader(f, delimiter=delim)
                for row in reader:
                    if len(row) >= 2:
                        pairs.append({"noisy": row[0], "clean": row[1]})
            else:
                for row in reader:
                    pairs.append({"noisy": row["noisy"], "clean": row["clean"]})
    else:
        raise ValueError(f"지원하지 않는 파일 형식: {path.suffix}")

    print(f"[Data] {len(pairs)}개 쌍 로드 완료: {path}")
    return pairs


# ── 데이터셋 클래스 ───────────────────────────────────────

class CorrectionDataset:
    def __init__(self, pairs: List[Dict], tokenizer, prefix: str,
                 max_input: int, max_target: int):
        self.pairs = pairs
        self.tokenizer = tokenizer
        self.prefix = prefix
        self.max_input = max_input
        self.max_target = max_target

    def __len__(self):
        return len(self.pairs)

    def __getitem__(self, idx):
        noisy = self.pairs[idx]["noisy"]
        clean = self.pairs[idx]["clean"]

        input_text = f"{self.prefix}{noisy}"
        model_inputs = self.tokenizer(
            input_text,
            max_length=self.max_input,
            padding="max_length",
            truncation=True,
            return_tensors="pt",
        )
        labels = self.tokenizer(
            clean,
            max_length=self.max_target,
            padding="max_length",
            truncation=True,
            return_tensors="pt",
        )
        label_ids = labels["input_ids"].squeeze()
        # T5: padding 토큰을 -100으로 마스킹 (loss 계산 제외)
        label_ids[label_ids == self.tokenizer.pad_token_id] = -100

        return {
            "input_ids":      model_inputs["input_ids"].squeeze(),
            "attention_mask": model_inputs["attention_mask"].squeeze(),
            "labels":         label_ids,
        }


# ── 평가 함수 ─────────────────────────────────────────────

def evaluate(model, tokenizer, pairs: List[Dict], prefix: str,
             max_input: int, max_target: int, device, n_samples: int = 200):
    """
    정확일치(EM)와 간단한 문자 수준 유사도로 평가.
    """
    import torch
    model.eval()
    exact_match = 0
    sample = pairs[:n_samples]

    for pair in sample:
        input_text = f"{prefix}{pair['noisy']}"
        inputs = tokenizer(
            input_text, return_tensors="pt",
            max_length=max_input, truncation=True
        ).to(device)

        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=max_target,
                num_beams=4,
                early_stopping=True,
            )
        pred = tokenizer.decode(outputs[0], skip_special_tokens=True).strip()
        if pred == pair["clean"].strip():
            exact_match += 1

    em_score = exact_match / len(sample) * 100
    print(f"\n[Eval] Exact Match: {exact_match}/{len(sample)} = {em_score:.1f}%")

    # 샘플 출력
    print("\n[Eval] 예시 (첫 5개):")
    for i, pair in enumerate(sample[:5]):
        input_text = f"{prefix}{pair['noisy']}"
        inputs = tokenizer(input_text, return_tensors="pt", truncation=True).to(device)
        with torch.no_grad():
            out = model.generate(**inputs, max_new_tokens=max_target, num_beams=4)
        pred = tokenizer.decode(out[0], skip_special_tokens=True).strip()
        match = "✓" if pred == pair["clean"].strip() else "✗"
        print(f"  {match} 입력:  {pair['noisy']}")
        print(f"     정답:  {pair['clean']}")
        print(f"     예측:  {pred}\n")

    return em_score


# ── 메인 학습 루프 ────────────────────────────────────────

def main():
    args = parse_args()

    import torch
    from transformers import (
        AutoTokenizer,
        T5ForConditionalGeneration,
        Seq2SeqTrainer,
        Seq2SeqTrainingArguments,
        DataCollatorForSeq2Seq,
    )

    # ── 디바이스 설정 ────────────────────────────────────
    if torch.cuda.is_available():
        device = torch.device("cuda")
        print(f"[Device] CUDA: {torch.cuda.get_device_name(0)}")
    elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        device = torch.device("mps")
        print("[Device] Apple Silicon MPS")
    else:
        device = torch.device("cpu")
        print("[Device] CPU")

    # ── 평가 전용 모드 ───────────────────────────────────
    if args.eval_only:
        model_path = args.model_path or args.output_dir
        print(f"[EvalOnly] 모델 로드: {model_path}")
        tokenizer = AutoTokenizer.from_pretrained(model_path)
        model = T5ForConditionalGeneration.from_pretrained(model_path).to(device)
        pairs = load_pairs(args.data_path)
        evaluate(model, tokenizer, pairs, args.prefix,
                 args.max_input, args.max_target, device)
        return

    # ── 모델 & 토크나이저 로드 ───────────────────────────
    print(f"[Model] 로드 중: {args.base_model}")
    tokenizer = AutoTokenizer.from_pretrained(args.base_model)
    model = T5ForConditionalGeneration.from_pretrained(args.base_model)
    print(f"[Model] 파라미터 수: {sum(p.numel() for p in model.parameters()):,}")

    # ── 데이터 로드 & 분할 ───────────────────────────────
    all_pairs = load_pairs(args.data_path)

    if args.val_path:
        val_pairs = load_pairs(args.val_path)
        train_pairs = all_pairs
    else:
        split = max(1, int(len(all_pairs) * 0.1))
        val_pairs   = all_pairs[:split]
        train_pairs = all_pairs[split:]
        print(f"[Data] Train: {len(train_pairs)} / Val: {len(val_pairs)}")

    train_dataset = CorrectionDataset(
        train_pairs, tokenizer, args.prefix, args.max_input, args.max_target
    )
    val_dataset = CorrectionDataset(
        val_pairs, tokenizer, args.prefix, args.max_input, args.max_target
    )

    # ── 학습 설정 ────────────────────────────────────────
    os.makedirs(args.output_dir, exist_ok=True)

    training_args = Seq2SeqTrainingArguments(
        output_dir=args.output_dir,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        learning_rate=args.lr,
        warmup_ratio=args.warmup_ratio,
        weight_decay=args.weight_decay,
        predict_with_generate=True,
        generation_max_length=args.max_target,
        eval_strategy="steps",
        eval_steps=args.save_steps,
        save_strategy="steps",
        save_steps=args.save_steps,
        save_total_limit=3,
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        logging_steps=args.logging_steps,
        logging_dir=os.path.join(args.output_dir, "logs"),
        fp16=torch.cuda.is_available(),          # CUDA만 fp16
        # MPS/CPU는 fp16 미지원 → 자동으로 fp32 사용
        dataloader_num_workers=0,                # macOS fork 안전
        report_to="none",                        # wandb 등 비활성화
    )

    data_collator = DataCollatorForSeq2Seq(
        tokenizer, model=model, padding=True, label_pad_token_id=-100
    )

    trainer = Seq2SeqTrainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
        tokenizer=tokenizer,
        data_collator=data_collator,
    )

    # ── 학습 시작 ────────────────────────────────────────
    print(f"\n[Train] 학습 시작")
    print(f"  모델:    {args.base_model}")
    print(f"  데이터:  Train {len(train_pairs)}개 / Val {len(val_pairs)}개")
    print(f"  Epochs:  {args.epochs}")
    print(f"  Batch:   {args.batch_size}")
    print(f"  LR:      {args.lr}")
    print(f"  Prefix:  '{args.prefix}'")
    print(f"  저장:    {args.output_dir}\n")

    trainer.train()

    # ── 최종 저장 ────────────────────────────────────────
    trainer.save_model(args.output_dir)
    tokenizer.save_pretrained(args.output_dir)
    print(f"\n[Done] 모델 저장 완료: {args.output_dir}")

    # ── 최종 평가 ────────────────────────────────────────
    evaluate(model, tokenizer, val_pairs, args.prefix,
             args.max_input, args.max_target, device)

    # ── 서버 적용 안내 ───────────────────────────────────
    print("\n[Next] 서버에 적용하려면 .env 또는 환경변수를 설정하세요:")
    print(f"  SPELLCHECK_KO_QUALITY_MODEL={args.output_dir}")
    print("\n  또는 Celery 워커 실행 전:")
    print(f"  export SPELLCHECK_KO_QUALITY_MODEL={args.output_dir}")


if __name__ == "__main__":
    main()
