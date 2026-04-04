"""
블로그 맞춤법 교정 모델 학습 파이프라인 (원클릭 실행)

== 실행 ==
  python scripts/pipeline_train.py

== 전체 흐름 ==
  1. 블로그 DB에서 깨끗한 글 추출
  2. 한국어 텍스트 다운로드 (HuggingFace, 자동) — 실패 시 내장 문장 사용
  3. 두 소스 합쳐서 합성 오류 데이터 생성
  4. 학습/검증 분리
  5. j5ng/et5-typos-corrector 에서 fine-tuning
  6. models/blog-spellcheck/best 에 저장

== 필요 패키지 ==
  pip install transformers torch datasets sqlalchemy beautifulsoup4
"""

import argparse
import json
import random
import re
import sys
import os
import time
from pathlib import Path
from typing import List, Dict, Tuple


# ── 설정 ─────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent.parent
DATA_DIR   = BASE_DIR / "data"
MODEL_DIR  = BASE_DIR / "models" / "blog-spellcheck"
DB_PATH    = BASE_DIR / "app.db"
BASE_MODEL = os.environ.get("SPELLCHECK_KO_MODEL", "j5ng/et5-typos-corrector")

# ── 오류 패턴 (자주 쓰이는 한국어 실수) ──────────────────

WORD_CONFUSIONS = {
    "항상": ["하상", "항쌍"],
    "있다": ["잇다"],
    "있어": ["이써", "잇어"],
    "있었": ["잇었", "이썼"],
    "있는": ["잇는"],
    "없다": ["업다"],
    "없어": ["업어"],
    "됐다": ["됬다"],
    "됐어": ["됬어"],
    "않아": ["안아"],
    "않고": ["안고"],
    "않는": ["안는"],
    "않았": ["안았"],
    "않을": ["안을"],
    "반드시": ["반듯이"],
    "왠지": ["웬지"],
    "어떡해": ["어떻해"],
    "어떻게": ["어떡게"],
    "깨끗이": ["깨끗히"],
    "솔직히": ["솔직이"],
    "열심히": ["열심이"],
    "굉장히": ["굉장이"],
    "특히": ["특이"],
    "같이": ["가치"],
    "되어": ["돼"],
    "돼서": ["되서"],
    "데": ["대"],
    "할게": ["할께"],
    "갈게": ["갈께"],
    "볼게": ["볼께"],
    "이에요": ["이예요"],
    "아니에요": ["아니예요"],
    "네요": ["내요"],
    "거예요": ["거에요"],
    "뭐예요": ["뭐에요"],
}

JONGSEONG_ERRORS = {
    "있": ["잇"],
    "없": ["업"],
    "읽": ["익"],
    "닭": ["닥"],
}

SPACING_ERRORS = [
    ("있는데",  "있는 데"),
    ("없는데",  "없는 데"),
    ("할수록",  "할 수록"),
    ("수있다",  "수 있다"),
    ("수없다",  "수 없다"),
    ("하다보면","하다 보면"),
    ("해보면",  "해 보면"),
    ("해보니",  "해 보니"),
    ("찾아보다","찾아 보다"),
    ("알아보다","알아 보다"),
]

# ── 글자 단위 모음 오류 (패턴 매칭 실패 시 fallback) ─────
# 중성(모음) 인덱스: ㅏ(0) ㅐ(1) ㅑ(2) ㅒ(3) ㅓ(4) ㅔ(5)
#                   ㅕ(6) ㅖ(7) ㅗ(8) ㅘ(9) ㅙ(10) ㅚ(11)
#                   ㅛ(12) ㅜ(13) ㅝ(14) ㅞ(15) ㅟ(16)
#                   ㅠ(17) ㅡ(18) ㅢ(19) ㅣ(20)
_VOWEL_CONFUSE = {
    1: 5,   # ㅐ → ㅔ  (에/애 혼동)
    5: 1,   # ㅔ → ㅐ
    3: 7,   # ㅒ → ㅖ
    7: 3,   # ㅖ → ㅒ
    8: 13,  # ㅗ → ㅜ
    13: 8,  # ㅜ → ㅗ
}


def _corrupt_char_level(text: str) -> str:
    """글자 단위 모음 오류 삽입 (단어 패턴 매칭 실패 시 fallback)"""
    chars = list(text)
    candidates = []
    for i, ch in enumerate(chars):
        code = ord(ch)
        if 0xAC00 <= code <= 0xD7A3:  # 한글 음절 범위
            offset = code - 0xAC00
            jung = (offset // 28) % 21
            if jung in _VOWEL_CONFUSE:
                candidates.append(i)

    if not candidates:
        return text

    idx = random.choice(candidates)
    code = ord(chars[idx])
    offset = code - 0xAC00
    jong = offset % 28
    jung = (offset // 28) % 21
    cho  = (offset // 28) // 21
    new_jung = _VOWEL_CONFUSE[jung]
    chars[idx] = chr(0xAC00 + (cho * 21 + new_jung) * 28 + jong)
    return "".join(chars)


def _corrupt(text: str) -> str:
    t = text
    for correct, wrongs in WORD_CONFUSIONS.items():
        if correct in t and random.random() < 0.2:
            t = t.replace(correct, random.choice(wrongs), 1)
    for correct, wrongs in JONGSEONG_ERRORS.items():
        if correct in t and random.random() < 0.05:
            t = t.replace(correct, random.choice(wrongs), 1)
    for sp, nsp in SPACING_ERRORS:
        if random.random() < 0.08:
            if sp in t:
                t = t.replace(sp, nsp, 1)
            elif nsp in t:
                t = t.replace(nsp, sp, 1)
    # 위에서 변경 없으면 글자 단위 모음 오류 적용 (항상 변경 가능)
    if t == text:
        t = _corrupt_char_level(text)
    return t


def _valid(clean: str, noisy: str) -> bool:
    return (
        clean != noisy
        and 8 <= len(clean.strip()) <= 150
        and re.search(r"[\uAC00-\uD7A3]", clean) is not None
    )


# ── 내장 한국어 문장 (외부 데이터 없을 때 사용) ──────────

_BUILTIN_KO = [
    "항상 성실하게 살아가는 것이 중요합니다.",
    "나는 항상 일찍 일어나려고 노력한다.",
    "그는 항상 다른 사람을 배려하는 사람이다.",
    "그 책은 도서관에 있다.",
    "오늘 해야 할 일이 있다.",
    "시간이 있으면 같이 산책하자.",
    "돈이 없어서 밥을 못 먹었다.",
    "그 문제에 대한 해답이 없다.",
    "아무런 이유가 없다고 생각했다.",
    "드디어 일이 됐다.",
    "그 문제는 이제 됐어.",
    "그 방법은 옳지 않다.",
    "먹지 않고 그냥 지나쳤다.",
    "일을 하지 않는 사람이 있다.",
    "포기하지 않아야 성공할 수 있다.",
    "실망하지 않고 다시 도전했다.",
    "방을 깨끗이 청소했다.",
    "열심히 공부한 덕분에 좋은 결과가 나왔다.",
    "그는 솔직히 말하는 사람이다.",
    "굉장히 어려운 문제였지만 풀어냈다.",
    "특히 이 부분이 중요합니다.",
    "같이 점심을 먹자.",
    "왠지 오늘은 일이 잘 될 것 같다.",
    "왠지 모르게 기분이 좋지 않다.",
    "어떻게 하면 더 잘 할 수 있을까?",
    "어떻게 설명해야 할지 모르겠다.",
    "제가 먼저 시작할게요.",
    "내일 다시 전화할게.",
    "나중에 확인하고 연락할게.",
    "이따가 같이 갈게.",
    "이것은 제 가방이에요.",
    "그분은 선생님이에요.",
    "여기는 회사가 아니에요.",
    "저는 학생이에요.",
    "이것이 정답일 거예요.",
    "아마 내일 도착할 거예요.",
    "정말 아름답네요.",
    "시간이 많이 걸리겠네요.",
    "공부하는 데 집중하는 것이 중요하다.",
    "새로운 것을 배우는 데 시간이 필요하다.",
    "문제를 해결하는 데 도움이 필요하다.",
    "드디어 합격이 돼서 기쁘다.",
    "일이 잘 돼서 다행이다.",
    "반드시 약속을 지켜야 한다.",
    "이 일은 반드시 완료해야 합니다.",
    "건강을 유지하려면 반드시 운동해야 한다.",
    "오늘 날씨가 정말 맑고 상쾌하다.",
    "이 책은 매우 흥미롭고 유익하다.",
    "지난 주말에 가족과 함께 여행을 다녀왔다.",
    "새로운 기술을 배우는 것은 즐거운 일이다.",
    "사람들과 함께하는 것이 행복의 비결이다.",
    "매일 조금씩 노력하면 큰 변화가 생긴다.",
    "좋은 습관을 만드는 것은 쉽지 않지만 중요하다.",
    "독서는 지식을 넓히는 좋은 방법이다.",
    "음악은 우리의 삶을 풍요롭게 만들어 준다.",
    "건강한 식습관을 유지하는 것이 중요하다.",
    "친구와 함께하는 시간은 소중하다.",
    "새벽에 일어나 공부하는 습관을 들였다.",
    "그 음식은 정말 맛있어서 또 먹고 싶다.",
    "이번 프로젝트는 팀원들과 협력해서 완성했다.",
    "어려운 상황에서도 포기하지 않는 것이 중요하다.",
    "배움에는 끝이 없다는 말이 맞는 것 같다.",
    "오늘 회의에서 중요한 결정이 내려졌다.",
    "그 가게는 항상 손님이 많아서 자리가 없었다.",
    "계획을 세우고 실행하는 것이 성공의 열쇠이다.",
    "경험이 쌓일수록 더 잘 할 수 있게 된다.",
    "새로운 환경에 적응하는 것은 시간이 걸린다.",
    "기술이 발전할수록 생활이 편리해진다.",
    "자신의 감정을 솔직히 표현하는 것이 중요하다.",
    "목표를 달성하기 위해 꾸준히 노력했다.",
    "다른 사람의 의견을 존중하는 것이 필요하다.",
    "일과 생활의 균형을 맞추는 것이 중요하다.",
    "좋은 결과를 위해서는 준비가 필요하다.",
    "문제가 발생했을 때 침착하게 대처해야 한다.",
    "그는 오랫동안 열심히 노력한 결과 성공했다.",
    "여행은 새로운 경험을 제공해 준다.",
    "창의적인 사고는 문제 해결에 도움이 된다.",
    "지속적인 학습이 성장의 밑거름이 된다.",
    "서로 돕는 문화가 더 좋은 사회를 만든다.",
    "변화를 두려워하지 않고 받아들여야 한다.",
    "어떤 일이든 최선을 다하면 후회가 없다.",
    "작은 변화가 큰 차이를 만들 수 있다.",
    "나는 매일 일기를 쓰는 습관을 기르고 있다.",
    "그 영화는 정말 감동적이어서 눈물이 났다.",
    "새로운 언어를 배우면 세계가 넓어진다.",
    "자신을 믿고 도전하는 것이 중요하다.",
    "협력과 소통이 팀의 성과를 높인다.",
    "건강은 모든 것의 기본이 됩니다.",
    "봄이 되면 꽃이 피어나는 것이 기대된다.",
    "이 문제는 생각보다 어렵지 않았다.",
    "그 프로그램은 사용하기 편리하게 설계되었다.",
    "독창적인 아이디어가 성공의 핵심이다.",
    "시간 관리를 잘 하는 것이 중요합니다.",
    "끊임없이 배우고 성장하는 자세가 필요합니다.",
    "그 경험은 나에게 많은 것을 가르쳐 주었다.",
    "여러 사람의 도움 덕분에 해낼 수 있었다.",
    "작은 성공들이 모여 큰 성취가 된다.",
    "새로운 도전은 늘 설레고 두렵기도 하다.",
    "이 방법이 가장 효율적인 것 같다.",
    "앞으로 더 잘 하기 위해 노력할 것이다.",
    "오늘 배운 내용을 잘 정리해 두었다.",
    "그 결정이 옳은 것인지 아직도 모르겠다.",
    "실수를 통해 배우는 것이 진정한 성장이다.",
    "다음에는 더 신중하게 판단해야겠다.",
    "혼자서는 할 수 없는 일도 함께라면 가능하다.",
    "감사하는 마음이 행복을 부른다.",
    "작은 것에도 감사할 줄 알아야 한다.",
    "꿈을 이루기 위해 매일 조금씩 나아가고 있다.",
    "어려움이 있어도 긍정적으로 생각하려 한다.",
    "인내심을 가지고 기다리면 좋은 결과가 온다.",
    "지금 이 순간에 집중하는 것이 중요하다.",
    "다른 사람에게 친절하게 대하면 나도 행복해진다.",
    "자연 속에서 휴식을 취하면 마음이 편안해진다.",
    "새로운 시작은 언제나 기대와 걱정을 동반한다.",
    "이것이 맞는 방향인지 확인해 봐야 한다.",
    "항상 감사하고 겸손한 자세를 유지하겠다.",
    "한국어 맞춤법은 배울수록 어렵다고 느껴진다.",
    "이 음식은 없다고 했는데 왜 있어요?",
    "그분은 항상 열심히 일하시는 분이에요.",
    "왠지 오늘은 결과가 좋을 것 같은 느낌이 든다.",
    "어떻게 해야 이 문제를 해결할 수 있을까요?",
    "깨끗이 정리된 책상을 보면 기분이 좋아진다.",
    "솔직히 말해서 그 계획은 무리라고 생각한다.",
    "반드시 성공하겠다는 의지가 중요하다.",
    "됐어, 이제 그만하고 쉬자.",
    "않아도 되는 걱정을 너무 많이 한다.",
    "같이 하면 더 즐겁고 빨리 끝낼 수 있다.",
    "특히 이번 경험이 많은 도움이 됐다.",
]


def _builtin_ko_sentences() -> List[str]:
    """내장 한국어 문장 반환"""
    return list(_BUILTIN_KO)


# ── 유틸리티 ──────────────────────────────────────────────

def _fmt_time(seconds: float) -> str:
    """초 → 'Xh Ym Zs' 형식"""
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    elif s < 3600:
        return f"{s // 60}m {s % 60:02d}s"
    else:
        return f"{s // 3600}h {(s % 3600) // 60:02d}m"


def _detect_device(preference: str) -> "torch.device":
    """cuda > mps(Apple Silicon) > cpu 순으로 자동 선택, preference로 강제 지정 가능"""
    import torch
    if preference != "auto":
        d = torch.device(preference)
        print(f"  디바이스: {d} (수동 지정)")
        return d

    if torch.cuda.is_available():
        d = torch.device("cuda")
        name = torch.cuda.get_device_name(0)
        print(f"  디바이스: cuda  ({name})")
    elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        d = torch.device("mps")
        print(f"  디바이스: mps   (Apple Silicon GPU)")
    else:
        d = torch.device("cpu")
        import platform
        cpu = platform.processor() or "CPU"
        print(f"  디바이스: cpu   ({cpu})")
    return d


# ── Step 1: 블로그 DB 추출 ────────────────────────────────

def step1_extract_blog(max_lines: int = 5000) -> List[str]:
    print("\n[1/5] 블로그 DB에서 텍스트 추출 중...")
    try:
        from sqlalchemy import create_engine, text
        from bs4 import BeautifulSoup
    except ImportError:
        print("  ⚠ pip install sqlalchemy beautifulsoup4 가 필요합니다. 블로그 데이터 건너뜀.")
        return []

    if not DB_PATH.exists():
        print(f"  ⚠ DB 파일 없음: {DB_PATH}. 블로그 데이터 건너뜀.")
        return []

    engine = create_engine(f"sqlite:///{DB_PATH}")
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT content_html FROM board_posts WHERE content_html IS NOT NULL LIMIT 500")
            ).fetchall()
    except Exception as e:
        print(f"  ⚠ DB 읽기 실패: {e}")
        return []

    lines = []
    for (html,) in rows:
        if not html:
            continue
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        for line in soup.get_text(separator="\n").splitlines():
            line = line.strip()
            if 8 <= len(line) <= 150 and re.search(r"[\uAC00-\uD7A3]", line):
                lines.append(line)

    lines = lines[:max_lines]
    print(f"  블로그 문장 {len(lines)}개 추출 완료")
    return lines


# ── Step 2: 외부 텍스트 다운로드 (실패 시 내장 문장) ─────

def step2_download_wiki(max_lines: int = 20000) -> List[str]:
    print("\n[2/5] 한국어 텍스트 다운로드 중 (HuggingFace)...")

    if max_lines == 0:
        print("  --wiki_lines 0 설정 — 내장 문장 사용")
        return _builtin_ko_sentences()

    try:
        from datasets import load_dataset
    except ImportError:
        print("  ⚠ pip install datasets 가 필요합니다. 내장 문장 사용.")
        return _builtin_ko_sentences()

    # 시도 순서: wikipedia → cc100 (streaming 모드로 전체 다운로드 불필요)
    sources = [
        ("wikipedia", "20220301.ko", "text"),
        ("cc100",     "ko",          "text"),
    ]

    for ds_name, ds_config, text_field in sources:
        try:
            print(f"  {ds_name} ({ds_config}) 시도 중...")
            ds = load_dataset(
                ds_name, ds_config,
                split="train",
                trust_remote_code=True,
                streaming=True,
            )
            lines = []
            for row in ds:
                for sent in row.get(text_field, "").split("\n"):
                    sent = sent.strip()
                    if 8 <= len(sent) <= 150 and re.search(r"[\uAC00-\uD7A3]", sent):
                        lines.append(sent)
                    if len(lines) >= max_lines:
                        break
                if len(lines) >= max_lines:
                    break
            if lines:
                print(f"  {len(lines)}개 문장 추출 완료 ({ds_name})")
                return lines
        except Exception as e:
            print(f"  ⚠ {ds_name} 실패: {e}")
            continue

    print("  ⚠ 외부 데이터 없음 — 내장 문장 코퍼스 사용")
    builtin = _builtin_ko_sentences()
    print(f"  내장 문장 {len(builtin)}개 로드")
    return builtin


# ── Step 3: 합성 오류 생성 ────────────────────────────────

def step3_generate_pairs(
    lines: List[str],
    n_samples: int,
    seed: int = 42,
) -> List[Dict]:
    # 문장 수 대비 샘플 수 자동 조정 (문장당 최대 50쌍)
    max_reasonable = len(lines) * 50
    if n_samples > max_reasonable:
        print(f"\n[3/5] 문장 {len(lines)}개로 {n_samples}개 요청 → {max_reasonable}개로 조정")
        n_samples = max_reasonable
    else:
        print(f"\n[3/5] 합성 오류 데이터 {n_samples}개 생성 중...")

    random.seed(seed)

    pairs = []
    attempts = 0
    while len(pairs) < n_samples and attempts < n_samples * 30:
        clean = random.choice(lines)
        noisy = _corrupt(clean)
        if _valid(clean, noisy):
            pairs.append({"input": noisy, "output": clean})
        attempts += 1

    print(f"  {len(pairs)}개 쌍 생성 완료")

    if pairs:
        print("  예시 3개:")
        for p in random.sample(pairs, min(3, len(pairs))):
            print(f"    오류: {p['input']}")
            print(f"    정답: {p['output']}")
            print()

    return pairs


# ── Step 4: 저장 + 분리 ───────────────────────────────────

def step4_save_and_split(
    pairs: List[Dict],
    val_ratio: float = 0.1,
    seed: int = 42,
) -> Tuple[Path, Path]:
    print("\n[4/5] 데이터 저장 및 train/val 분리 중...")
    random.seed(seed)
    random.shuffle(pairs)

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    n_val = max(5, int(len(pairs) * val_ratio))
    val_pairs   = pairs[:n_val]
    train_pairs = pairs[n_val:]

    train_path = DATA_DIR / "spellcheck_train.jsonl"
    val_path   = DATA_DIR / "spellcheck_val.jsonl"

    for path, data in [(train_path, train_pairs), (val_path, val_pairs)]:
        with open(path, "w", encoding="utf-8") as f:
            for p in data:
                f.write(json.dumps(p, ensure_ascii=False) + "\n")

    print(f"  학습: {len(train_pairs)}개 → {train_path}")
    print(f"  검증: {len(val_pairs)}개 → {val_path}")
    return train_path, val_path


# ── Step 5: Fine-tuning ───────────────────────────────────

def step5_train(
    train_path: Path,
    val_path: Path,
    epochs: int,
    batch_size: int,
    learning_rate: float,
    device_name: str = "auto",
):
    print(f"\n[5/5] Fine-tuning 시작: {BASE_MODEL}")
    print(f"  출력 경로: {MODEL_DIR}")

    try:
        import torch
        from torch.utils.data import Dataset, DataLoader
        from transformers import AutoTokenizer, T5ForConditionalGeneration, get_linear_schedule_with_warmup
    except ImportError:
        print("pip install transformers torch 를 먼저 실행하세요.")
        sys.exit(1)

    device = _detect_device(device_name)

    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
    model = T5ForConditionalGeneration.from_pretrained(BASE_MODEL).to(device)

    total_params = sum(p.numel() for p in model.parameters())
    print(f"  파라미터: {total_params:,}개")

    class SC_Dataset(Dataset):
        def __init__(self, path):
            self.samples = [json.loads(l) for l in Path(path).read_text("utf-8").splitlines() if l.strip()]

        def __len__(self): return len(self.samples)

        def __getitem__(self, idx):
            s = self.samples[idx]
            enc = tokenizer(s["input"],  max_length=128, padding="max_length", truncation=True, return_tensors="pt")
            dec = tokenizer(s["output"], max_length=128, padding="max_length", truncation=True, return_tensors="pt")
            labels = dec["input_ids"].squeeze()
            labels[labels == tokenizer.pad_token_id] = -100
            return {
                "input_ids":      enc["input_ids"].squeeze(),
                "attention_mask": enc["attention_mask"].squeeze(),
                "labels":         labels,
            }

    train_loader = DataLoader(SC_Dataset(train_path), batch_size=batch_size, shuffle=True,  num_workers=0)
    val_loader   = DataLoader(SC_Dataset(val_path),   batch_size=batch_size, shuffle=False, num_workers=0)

    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate)
    total_steps = len(train_loader) * epochs
    scheduler = get_linear_schedule_with_warmup(
        optimizer,
        num_warmup_steps=total_steps // 10,
        num_training_steps=total_steps,
    )

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    best_val_loss = float("inf")
    total_steps_done = 0
    total_step_count = len(train_loader) * epochs
    train_start = time.time()

    # exact match 계산용 val 샘플 미리 로드 (epoch마다 재사용)
    val_items = [json.loads(l) for l in Path(val_path).read_text("utf-8").splitlines() if l.strip()]
    em_sample_size = min(100, len(val_items))

    for epoch in range(1, epochs + 1):
        model.train()
        total_loss = 0.0
        total_tok_acc = 0.0          # 토큰 단위 정확도 누적
        epoch_start = time.time()
        recent_times: List[float] = []

        for step, batch in enumerate(train_loader, 1):
            step_start = time.time()
            lbl = batch["labels"].to(device)

            out = model(
                input_ids=      batch["input_ids"].to(device),
                attention_mask= batch["attention_mask"].to(device),
                labels=         lbl,
            )

            # 토큰 정확도: logits argmax vs labels (-100 패딩 제외)
            with torch.no_grad():
                preds = out.logits.argmax(-1)
                mask  = lbl != -100
                tok_acc = ((preds == lbl) & mask).sum().item() / mask.sum().clamp(min=1).item()
            total_tok_acc += tok_acc

            out.loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step(); scheduler.step(); optimizer.zero_grad()

            step_sec = time.time() - step_start
            recent_times.append(step_sec)
            if len(recent_times) > 20:
                recent_times.pop(0)

            total_loss += out.loss.item()
            total_steps_done += 1

            if step % 100 == 0:
                avg_loss     = total_loss / step
                avg_acc      = total_tok_acc / step
                avg_step_sec = sum(recent_times) / len(recent_times)
                samples_sec  = batch_size / avg_step_sec
                steps_left   = total_step_count - total_steps_done
                eta_total    = _fmt_time(steps_left * avg_step_sec)
                eta_epoch    = _fmt_time((len(train_loader) - step) * avg_step_sec)
                elapsed      = _fmt_time(time.time() - train_start)
                print(
                    f"  Epoch {epoch}/{epochs} | step {step}/{len(train_loader)}"
                    f" | loss {avg_loss:.4f} | tok_acc {avg_acc:.1%}"
                    f" | {avg_step_sec:.2f}s/step | {samples_sec:.1f} samp/s"
                    f" | epoch잔여 {eta_epoch} | 전체잔여 {eta_total} | 경과 {elapsed}"
                )

        avg_train     = total_loss / len(train_loader)
        avg_train_acc = total_tok_acc / len(train_loader)

        # ── 검증 loss ─────────────────────────────────────
        model.eval()
        val_loss = 0.0
        with torch.no_grad():
            for batch in val_loader:
                out = model(
                    input_ids=      batch["input_ids"].to(device),
                    attention_mask= batch["attention_mask"].to(device),
                    labels=         batch["labels"].to(device),
                )
                val_loss += out.loss.item()
        avg_val = val_loss / len(val_loader)

        # ── Exact Match: 실제 생성 결과 vs 정답 비교 ──────
        em_samples = random.sample(val_items, em_sample_size)
        em_correct = 0
        with torch.no_grad():
            for s in em_samples:
                inp_ids = tokenizer(
                    s["input"], return_tensors="pt",
                    max_length=128, truncation=True,
                ).input_ids.to(device)
                gen_ids = model.generate(inp_ids, max_new_tokens=128)
                pred = tokenizer.decode(gen_ids[0], skip_special_tokens=True).strip()
                if pred == s["output"].strip():
                    em_correct += 1
        val_em = em_correct / em_sample_size

        epoch_sec = time.time() - epoch_start
        print(
            f"\n  ✓ Epoch {epoch}/{epochs} 완료"
            f" | train loss {avg_train:.4f} | train tok_acc {avg_train_acc:.1%}"
            f" | val loss {avg_val:.4f} | val exact_match {val_em:.1%}"
            f" | 소요 {_fmt_time(epoch_sec)}"
        )

        if avg_val < best_val_loss:
            best_val_loss = avg_val
            best_path = MODEL_DIR / "best"
            model.save_pretrained(best_path)
            tokenizer.save_pretrained(best_path)
            print(f"  → Best 모델 저장: {best_path}")

        ckpt = MODEL_DIR / f"epoch-{epoch}"
        model.save_pretrained(ckpt)
        tokenizer.save_pretrained(ckpt)

    print(f"\n학습 완료!")
    print(f"적용 방법:")
    print(f"  SPELLCHECK_KO_MODEL={MODEL_DIR}/best uvicorn app.main:app --reload")


# ── 메인 ─────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="블로그 맞춤법 교정 모델 학습 파이프라인")
    parser.add_argument("--samples",       type=int,   default=8000,  help="생성할 학습 샘플 수 (기본 8000)")
    parser.add_argument("--wiki_lines",    type=int,   default=20000, help="외부 텍스트 최대 문장 수 (0=내장만 사용)")
    parser.add_argument("--blog_lines",    type=int,   default=5000,  help="블로그 DB 최대 문장 수 (기본 5000)")
    parser.add_argument("--epochs",        type=int,   default=5,     help="학습 에포크 (기본 5)")
    parser.add_argument("--batch_size",    type=int,   default=8,     help="배치 크기 (기본 8)")
    parser.add_argument("--learning_rate", type=float, default=3e-4,  help="학습률 (기본 3e-4)")
    parser.add_argument("--skip_download", action="store_true",       help="외부 다운로드 건너뜀 (이미 있을 때)")
    parser.add_argument("--device",        type=str,   default="auto",
                        help="학습 디바이스: auto (기본) | cpu | mps (Apple GPU) | cuda (NVIDIA)")
    args = parser.parse_args()

    print("=" * 55)
    print("  블로그 맞춤법 교정 Fine-tuning 파이프라인")
    print("=" * 55)
    print(f"  베이스 모델: {BASE_MODEL}")
    print(f"  학습 샘플:   {args.samples}개")
    print(f"  에포크:      {args.epochs}")
    print(f"  디바이스:    {args.device}")
    print(f"  출력:        {MODEL_DIR}")
    print("=" * 55)

    train_path = DATA_DIR / "spellcheck_train.jsonl"
    val_path   = DATA_DIR / "spellcheck_val.jsonl"

    if train_path.exists() and val_path.exists() and args.skip_download:
        print("\n기존 데이터 재사용 (--skip_download)")
    else:
        blog_lines = step1_extract_blog(args.blog_lines)
        wiki_lines = step2_download_wiki(args.wiki_lines) if not args.skip_download else []

        all_lines = blog_lines + wiki_lines
        if not all_lines:
            print("\n오류: 사용 가능한 텍스트가 없습니다.")
            sys.exit(1)

        print(f"\n  총 {len(all_lines)}개 문장 사용 (블로그 {len(blog_lines)} + 외부/내장 {len(wiki_lines)})")

        pairs = step3_generate_pairs(all_lines, args.samples)
        if not pairs:
            print("\n오류: 학습 데이터 생성 실패 — 문장에 한글이 없거나 너무 짧습니다.")
            sys.exit(1)

        train_path, val_path = step4_save_and_split(pairs)

    step5_train(train_path, val_path, args.epochs, args.batch_size, args.learning_rate, args.device)


if __name__ == "__main__":
    main()
