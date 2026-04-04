"""
한국어/영어 맞춤법 교정 모델 Fine-tuning 스크립트

== 전체 흐름 ==

  1단계: 학습 데이터 생성
    python scripts/generate_training_data.py synthetic --input_file data/clean_text.txt
    python scripts/generate_training_data.py aihub    --input_file data/aihub_raw.json
    → data/spellcheck_train.jsonl 생성

  2단계: 학습 실행 (현재 모델에서 이어서 fine-tuning)
    python scripts/train_spellcheck.py train \\
      --train_file data/spellcheck_train.jsonl \\
      --val_file   data/spellcheck_val.jsonl \\
      --output_dir models/my-ko-spellcheck \\
      --epochs 5

  3단계: 서비스에 적용
    SPELLCHECK_KO_MODEL=models/my-ko-spellcheck/best uvicorn app.main:app

== 기본 베이스 모델 ==
  한국어: j5ng/et5-typos-corrector  (이미 교정용으로 fine-tuned → 여기서 추가 학습)
  → 처음부터 학습하는 것보다 훨씬 적은 데이터/시간으로 개선 가능

== 데이터 출처 ==
  - AI Hub (aihub.or.kr) → "한국어 맞춤법 교정 데이터" (무료, 회원가입 필요)
  - 국립국어원 NIKL (corpus.korean.go.kr) → 문어/구어 말뭉치
  - 블로그 글 직접 활용 → scripts/generate_training_data.py synthetic

== 모델 아키텍처 열람/수정 ==
   from transformers import T5ForConditionalGeneration
   model = T5ForConditionalGeneration.from_pretrained("j5ng/et5-typos-corrector")

   # 전체 구조 확인
   print(model)

   # 인코더 6번째 블록 어텐션 Q 가중치
   print(model.encoder.block[5].layer[0].SelfAttention.q.weight.shape)

   # 커스텀 레이어 추가 예시
   import torch.nn as nn
   class CustomByT5(T5ForConditionalGeneration):
       def __init__(self, config):
           super().__init__(config)
           self.correction_head = nn.Linear(config.d_model, config.d_model)

       def forward(self, **kwargs):
           outputs = super().forward(**kwargs)
           return outputs
"""

import argparse
import json
import os
from pathlib import Path

import torch
from torch.utils.data import Dataset, DataLoader
from transformers import (
    AutoTokenizer,
    T5ForConditionalGeneration,
    get_linear_schedule_with_warmup,
)


# ── 하이퍼파라미터 ────────────────────────────────────────
DEFAULT_MODEL = os.environ.get("SPELLCHECK_KO_MODEL", "j5ng/et5-typos-corrector")
MAX_INPUT_LEN = 256
MAX_TARGET_LEN = 256
BATCH_SIZE = 8
LEARNING_RATE = 5e-4


# ── 데이터셋 ──────────────────────────────────────────────
class SpellCheckDataset(Dataset):
    """
    JSONL 형식 맞춤법 교정 데이터셋
    각 줄: {"input": "오류 텍스트", "output": "교정된 텍스트"}
    """

    KO_PREFIX = "맞춤법 교정: "
    EN_PREFIX = "correct spelling: "

    def __init__(self, file_path: str, tokenizer, max_input_len: int, max_target_len: int):
        self.tokenizer = tokenizer
        self.max_input_len = max_input_len
        self.max_target_len = max_target_len
        self.samples = []

        with open(file_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                item = json.loads(line)
                self.samples.append((item["input"], item["output"]))

        print(f"[Dataset] {len(self.samples)}개 샘플 로드: {file_path}")

    @staticmethod
    def _is_korean(text: str) -> bool:
        import re
        return bool(re.search(r"[\uAC00-\uD7A3]", text))

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        src, tgt = self.samples[idx]
        prefix = self.KO_PREFIX if self._is_korean(src) else self.EN_PREFIX
        input_text = prefix + src

        input_enc = self.tokenizer(
            input_text,
            max_length=self.max_input_len,
            padding="max_length",
            truncation=True,
            return_tensors="pt",
        )
        target_enc = self.tokenizer(
            tgt,
            max_length=self.max_target_len,
            padding="max_length",
            truncation=True,
            return_tensors="pt",
        )

        labels = target_enc["input_ids"].squeeze()
        # 패딩 토큰은 손실 계산에서 제외
        labels[labels == self.tokenizer.pad_token_id] = -100

        return {
            "input_ids": input_enc["input_ids"].squeeze(),
            "attention_mask": input_enc["attention_mask"].squeeze(),
            "labels": labels,
        }


# ── 학습 루프 ─────────────────────────────────────────────
def train(args):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[Train] 디바이스: {device}")
    print(f"[Train] 베이스 모델: {args.base_model}")

    # 모델 & 토크나이저 로드
    tokenizer = AutoTokenizer.from_pretrained(args.base_model)
    model = T5ForConditionalGeneration.from_pretrained(args.base_model)
    model = model.to(device)

    # 모델 구조 출력 (선택)
    if args.print_model:
        print("\n=== 모델 아키텍처 ===")
        print(model)
        total_params = sum(p.numel() for p in model.parameters())
        trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
        print(f"전체 파라미터: {total_params:,}")
        print(f"학습 가능 파라미터: {trainable_params:,}\n")

    # 특정 레이어만 학습 (선택: --freeze_encoder)
    if args.freeze_encoder:
        for param in model.encoder.parameters():
            param.requires_grad = False
        print("[Train] 인코더 동결 - 디코더만 학습")

    # 데이터셋
    train_dataset = SpellCheckDataset(
        args.train_file, tokenizer, MAX_INPUT_LEN, MAX_TARGET_LEN
    )
    train_loader = DataLoader(
        train_dataset, batch_size=args.batch_size, shuffle=True, num_workers=0
    )

    val_loader = None
    if args.val_file and Path(args.val_file).exists():
        val_dataset = SpellCheckDataset(
            args.val_file, tokenizer, MAX_INPUT_LEN, MAX_TARGET_LEN
        )
        val_loader = DataLoader(val_dataset, batch_size=args.batch_size, shuffle=False)

    # 옵티마이저 & 스케줄러
    optimizer = torch.optim.AdamW(
        [p for p in model.parameters() if p.requires_grad],
        lr=args.learning_rate
    )
    total_steps = len(train_loader) * args.epochs
    scheduler = get_linear_schedule_with_warmup(
        optimizer,
        num_warmup_steps=total_steps // 10,
        num_training_steps=total_steps,
    )

    # 체크포인트 디렉토리 생성
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    best_val_loss = float("inf")

    for epoch in range(1, args.epochs + 1):
        # ── 학습 ──
        model.train()
        total_loss = 0.0
        for step, batch in enumerate(train_loader, 1):
            input_ids = batch["input_ids"].to(device)
            attention_mask = batch["attention_mask"].to(device)
            labels = batch["labels"].to(device)

            outputs = model(
                input_ids=input_ids,
                attention_mask=attention_mask,
                labels=labels,
            )
            loss = outputs.loss
            loss.backward()

            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()
            optimizer.zero_grad()

            total_loss += loss.item()
            if step % 50 == 0:
                avg = total_loss / step
                print(f"  Epoch {epoch} | Step {step}/{len(train_loader)} | Loss: {avg:.4f}")

        avg_train_loss = total_loss / len(train_loader)
        print(f"[Epoch {epoch}] 학습 Loss: {avg_train_loss:.4f}")

        # ── 검증 ──
        if val_loader:
            model.eval()
            val_loss = 0.0
            with torch.no_grad():
                for batch in val_loader:
                    outputs = model(
                        input_ids=batch["input_ids"].to(device),
                        attention_mask=batch["attention_mask"].to(device),
                        labels=batch["labels"].to(device),
                    )
                    val_loss += outputs.loss.item()
            avg_val_loss = val_loss / len(val_loader)
            print(f"[Epoch {epoch}] 검증 Loss: {avg_val_loss:.4f}")

            if avg_val_loss < best_val_loss:
                best_val_loss = avg_val_loss
                best_path = output_dir / "best"
                model.save_pretrained(best_path)
                tokenizer.save_pretrained(best_path)
                print(f"  → Best 모델 저장: {best_path}")

        # 에포크별 체크포인트 저장
        ckpt_path = output_dir / f"epoch-{epoch}"
        model.save_pretrained(ckpt_path)
        tokenizer.save_pretrained(ckpt_path)
        print(f"[Epoch {epoch}] 체크포인트 저장: {ckpt_path}")

    # 최종 모델 저장
    final_path = output_dir / "final"
    model.save_pretrained(final_path)
    tokenizer.save_pretrained(final_path)
    print(f"\n[완료] 최종 모델 저장: {final_path}")
    print(f"적용 방법: SPELLCHECK_MODEL={final_path} uvicorn app.main:app")


# ── 샘플 데이터 생성 ──────────────────────────────────────
def create_sample_data(output_path: str):
    """학습 데이터 형식 확인용 샘플 데이터 생성"""
    samples = [
        {"input": "안녕하세오", "output": "안녕하세요"},
        {"input": "반갑습니다. 잘 부탁드립니다.", "output": "반갑습니다. 잘 부탁드립니다."},
        {"input": "오늘 날씨가 참 좋네요", "output": "오늘 날씨가 참 좋네요"},
        {"input": "이 글을 쓰는것이 어렵네요", "output": "이 글을 쓰는 것이 어렵네요"},
        {"input": "I recieve the email", "output": "I receive the email"},
        {"input": "She dont know the answer", "output": "She doesn't know the answer"},
        {"input": "The weather is beatiful today", "output": "The weather is beautiful today"},
    ]
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for s in samples:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")
    print(f"샘플 데이터 생성: {output_path}")


# ── CLI ───────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ByT5 맞춤법 교정 Fine-tuning")
    subparsers = parser.add_subparsers(dest="command")

    # train 커맨드
    train_parser = subparsers.add_parser("train", help="모델 학습")
    train_parser.add_argument("--train_file", required=True, help="학습 데이터 JSONL 경로")
    train_parser.add_argument("--val_file", default=None, help="검증 데이터 JSONL 경로 (선택)")
    train_parser.add_argument("--output_dir", default="models/spellcheck-byt5", help="모델 저장 경로")
    train_parser.add_argument("--base_model", default=DEFAULT_MODEL, help="베이스 모델 경로/ID")
    train_parser.add_argument("--epochs", type=int, default=3, help="학습 에포크 수")
    train_parser.add_argument("--batch_size", type=int, default=BATCH_SIZE)
    train_parser.add_argument("--learning_rate", type=float, default=LEARNING_RATE)
    train_parser.add_argument("--freeze_encoder", action="store_true", help="인코더 동결 (디코더만 학습)")
    train_parser.add_argument("--print_model", action="store_true", help="모델 아키텍처 출력")

    # sample 커맨드
    sample_parser = subparsers.add_parser("sample", help="샘플 데이터 생성")
    sample_parser.add_argument("--output", default="data/spellcheck_sample.jsonl")

    args = parser.parse_args()

    if args.command == "train":
        train(args)
    elif args.command == "sample":
        create_sample_data(args.output)
    else:
        parser.print_help()
