"""
맞춤법 교정 학습 데이터 생성 스크립트

== 사용법 ==

1. 합성 오류 데이터 생성 (깨끗한 텍스트 → 오류 삽입 → 학습 쌍 생성)
   python scripts/generate_training_data.py synthetic \\
     --input_file  data/clean_korean_text.txt \\
     --output_file data/spellcheck_train.jsonl \\
     --samples     5000

2. AI Hub 데이터 변환
   python scripts/generate_training_data.py aihub \\
     --input_file  data/aihub_raw.json \\
     --output_file data/spellcheck_train.jsonl

3. 학습/검증 분리
   python scripts/generate_training_data.py split \\
     --input_file  data/spellcheck_train.jsonl \\
     --val_ratio   0.1

== 합성 오류 생성 원리 ==
  실제 한국인이 자주 하는 오류 패턴을 코드로 구현:
  - 모음 혼동: 하상→항상, 잇다→있다, 됬→됐
  - 자음 혼동: 빡처→빡쳐, 안→않
  - 된소리/거센소리: 깨끗히→깨끗이
  - 띄어쓰기: 있는데→있는 데
  - 동음이의어: 이/히 접미사 혼동

== 사용 가능한 깨끗한 텍스트 소스 ==
  - 블로그 기존 게시글 (DB에서 추출)
  - 뉴스 기사
  - 국립국어원 NIKL 말뭉치 (corpus.korean.go.kr)
  - AI Hub 원문 텍스트
"""

import argparse
import json
import random
import re
import sys
from pathlib import Path


# ── 한국어 오류 패턴 정의 ─────────────────────────────────

# 자주 혼동하는 단어 쌍 (정답 → [오류 후보들])
WORD_CONFUSIONS = {
    "항상": ["하상", "항쌍"],
    "있다": ["잇다", "잇따"],
    "있어": ["이써", "잇어"],
    "있는": ["잇는"],
    "있었": ["잇었", "이썼"],
    "없다": ["업다", "엄다"],
    "없어": ["업어", "엄어"],
    "됐다": ["됬다", "됐따"],
    "됐어": ["됬어"],
    "안 되": ["안돼", "않 되"],
    "되어": ["돼", "되"],
    "돼서": ["되서"],
    "않아": ["안아"],
    "않고": ["안고"],
    "않는": ["안는"],
    "맞히다": ["맞추다"],
    "부치다": ["붙이다"],
    "반드시": ["반듯이", "반드씨"],
    "로서": ["로써"],
    "로써": ["로서"],
    "던": ["든"],
    "든": ["던"],
    "왠지": ["웬지"],
    "웬만하면": ["왠만하면"],
    "어떡해": ["어떻해", "어떡게"],
    "어떻게": ["어떡해"],
    "깨끗이": ["깨끗히"],
    "가득이": ["가득히"],
    "일찍이": ["일찍히"],
    "너무": ["너무나"],
    "굉장히": ["굉장이"],
    "열심히": ["열심이"],
    "솔직히": ["솔직이"],
    "특히": ["특이"],
    "같이": ["가치"],
    "붙여": ["부쳐"],
    "데": ["대"],  # 의존명사
    "대": ["데"],
    "지": ["치"],
    "때문에": ["때문에"],
    "에": ["에서"],
    "를": ["을"],
    "이": ["가"],
    "가": ["이"],
}

# 모음 오류 (자소 단위)
VOWEL_ERRORS = {
    "ㅐ": "ㅔ",
    "ㅔ": "ㅐ",
    "ㅒ": "ㅖ",
    "ㅖ": "ㅒ",
    "ㅚ": "ㅙ",
    "ㅙ": "ㅚ",
}

# 받침 오류 패턴 (글자 → [오류 글자들])
JONGSEONG_ERRORS = {
    "있": ["잇", "읻"],
    "없": ["업", "엄"],
    "닭": ["닥"],
    "삶": ["삼"],
    "읽": ["익"],
    "밟": ["밥"],
    "넋": ["넉"],
    "닻": ["닷"],
}

# 띄어쓰기 오류 패턴
SPACING_ERRORS = [
    ("있는데", "있는 데"),
    ("없는데", "없는 데"),
    ("할수록", "할 수록"),
    ("뿐만아니라", "뿐만 아니라"),
    ("것같다", "것 같다"),
    ("것이다", "것이다"),
    ("수있다", "수 있다"),
    ("수없다", "수 없다"),
    ("때문이다", "때문이다"),
    ("하다보면", "하다 보면"),
    ("해보면", "해 보면"),
    ("해보니", "해 보니"),
    ("알아보다", "알아 보다"),
    ("찾아보다", "찾아 보다"),
]


def add_word_confusion(text: str, rate: float = 0.15) -> str:
    """단어 수준 혼동 오류 삽입"""
    for correct, errors in WORD_CONFUSIONS.items():
        if correct in text and random.random() < rate:
            text = text.replace(correct, random.choice(errors), 1)
    return text


def add_spacing_error(text: str, rate: float = 0.1) -> str:
    """띄어쓰기 오류 삽입"""
    for spaced, nospace in SPACING_ERRORS:
        # 오류 방향을 랜덤하게 (붙이기 또는 띄우기)
        if random.random() < rate:
            if spaced in text:
                text = text.replace(spaced, nospace, 1)
            elif nospace in text:
                text = text.replace(nospace, spaced, 1)
    return text


def add_jongseong_error(text: str, rate: float = 0.05) -> str:
    """받침 오류 삽입"""
    for correct, errors in JONGSEONG_ERRORS.items():
        if correct in text and random.random() < rate:
            text = text.replace(correct, random.choice(errors), 1)
    return text


def corrupt_text(clean_text: str) -> str:
    """깨끗한 텍스트에 복합 오류 삽입"""
    corrupted = clean_text
    corrupted = add_word_confusion(corrupted, rate=0.2)
    corrupted = add_spacing_error(corrupted, rate=0.1)
    corrupted = add_jongseong_error(corrupted, rate=0.05)
    return corrupted


def is_valid_pair(original: str, corrupted: str) -> bool:
    """유효한 학습 쌍인지 확인"""
    if original == corrupted:
        return False  # 오류가 삽입되지 않은 경우 제외
    if len(original.strip()) < 5:
        return False  # 너무 짧은 텍스트 제외
    if len(original) > 200:
        return False  # 너무 긴 텍스트 제외
    return True


# ── 합성 데이터 생성 ──────────────────────────────────────

def generate_synthetic(input_file: str, output_file: str, n_samples: int, seed: int = 42):
    """
    깨끗한 텍스트 파일에서 합성 오류 데이터 생성

    input_file: 한 줄에 하나의 문장/문단 (UTF-8)
    output_file: JSONL 형식 {"input": "오류", "output": "정답"}
    """
    random.seed(seed)

    lines = Path(input_file).read_text(encoding="utf-8").splitlines()
    lines = [l.strip() for l in lines if l.strip()]
    print(f"[synthetic] 원본 문장 {len(lines)}개 로드")

    pairs = []
    attempts = 0
    max_attempts = n_samples * 10

    while len(pairs) < n_samples and attempts < max_attempts:
        line = random.choice(lines)
        corrupted = corrupt_text(line)
        if is_valid_pair(line, corrupted):
            pairs.append({"input": corrupted, "output": line})
        attempts += 1

    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        for pair in pairs:
            f.write(json.dumps(pair, ensure_ascii=False) + "\n")

    print(f"[synthetic] {len(pairs)}개 학습 쌍 생성 → {output_file}")
    print(f"  예시:")
    for p in pairs[:3]:
        print(f"  오류: {p['input']}")
        print(f"  정답: {p['output']}")
        print()


# ── AI Hub 데이터 변환 ────────────────────────────────────

def convert_aihub(input_file: str, output_file: str):
    """
    AI Hub "한국어 맞춤법 교정 데이터" JSON → JSONL 변환

    AI Hub 데이터 구조 (일반적인 형식):
    [
      {"original": "오류가 잇는 문장", "corrected": "오류가 있는 문장"},
      ...
    ]
    또는
    {
      "data": [
        {"annotation": {"wrong": "...", "correct": "..."}}
      ]
    }

    다운로드: https://aihub.or.kr → "맞춤법 교정" 검색
    """
    raw = json.loads(Path(input_file).read_text(encoding="utf-8"))

    pairs = []

    # 형식 1: 리스트 [{original, corrected}, ...]
    if isinstance(raw, list):
        for item in raw:
            src = item.get("original") or item.get("wrong") or item.get("input") or item.get("오류문장")
            tgt = item.get("corrected") or item.get("correct") or item.get("output") or item.get("교정문장")
            if src and tgt and src != tgt:
                pairs.append({"input": src.strip(), "output": tgt.strip()})

    # 형식 2: {"data": [...]}
    elif isinstance(raw, dict) and "data" in raw:
        for item in raw["data"]:
            ann = item.get("annotation", item)
            src = ann.get("wrong") or ann.get("original") or ann.get("오류문장")
            tgt = ann.get("correct") or ann.get("corrected") or ann.get("교정문장")
            if src and tgt and src != tgt:
                pairs.append({"input": src.strip(), "output": tgt.strip()})

    if not pairs:
        print("[aihub] 경고: 데이터를 파싱하지 못했습니다. JSON 구조를 확인하세요.")
        print(f"  최상위 키: {list(raw.keys()) if isinstance(raw, dict) else type(raw)}")
        sys.exit(1)

    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        for pair in pairs:
            f.write(json.dumps(pair, ensure_ascii=False) + "\n")

    print(f"[aihub] {len(pairs)}개 변환 완료 → {output_file}")


# ── DB에서 블로그 글 추출 ─────────────────────────────────

def extract_from_db(output_file: str, db_url: str = "sqlite:///app.db"):
    """
    블로그 DB에서 기존 게시글 텍스트 추출 (clean text로 사용)
    → generate_synthetic의 input_file로 활용 가능
    """
    try:
        from sqlalchemy import create_engine, text
        from bs4 import BeautifulSoup
    except ImportError:
        print("pip install sqlalchemy beautifulsoup4 를 실행하세요.")
        sys.exit(1)

    engine = create_engine(db_url)
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT content_html FROM board_posts WHERE content_html IS NOT NULL")).fetchall()

    texts = []
    for (html,) in rows:
        if not html:
            continue
        soup = BeautifulSoup(html, "html.parser")
        plain = soup.get_text(separator="\n")
        for line in plain.splitlines():
            line = line.strip()
            if len(line) >= 10:
                texts.append(line)

    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    Path(output_file).write_text("\n".join(texts), encoding="utf-8")
    print(f"[db] {len(texts)}개 문장 추출 → {output_file}")


# ── 학습/검증 분리 ────────────────────────────────────────

def split_data(input_file: str, val_ratio: float = 0.1, seed: int = 42):
    """JSONL 파일을 train/val로 분리"""
    random.seed(seed)
    lines = Path(input_file).read_text(encoding="utf-8").splitlines()
    lines = [l for l in lines if l.strip()]
    random.shuffle(lines)

    n_val = max(1, int(len(lines) * val_ratio))
    val_lines = lines[:n_val]
    train_lines = lines[n_val:]

    base = Path(input_file).stem
    parent = Path(input_file).parent

    train_path = parent / f"{base}_train.jsonl"
    val_path = parent / f"{base}_val.jsonl"

    train_path.write_text("\n".join(train_lines), encoding="utf-8")
    val_path.write_text("\n".join(val_lines), encoding="utf-8")

    print(f"[split] 학습: {len(train_lines)}개 → {train_path}")
    print(f"[split] 검증: {len(val_lines)}개 → {val_path}")


# ── CLI ───────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="맞춤법 교정 학습 데이터 생성")
    sub = parser.add_subparsers(dest="command")

    # synthetic
    p = sub.add_parser("synthetic", help="합성 오류 데이터 생성")
    p.add_argument("--input_file",  required=True, help="깨끗한 한국어 텍스트 파일 (한 줄 = 한 문장)")
    p.add_argument("--output_file", default="data/spellcheck_synthetic.jsonl")
    p.add_argument("--samples",     type=int, default=5000, help="생성할 학습 쌍 수")
    p.add_argument("--seed",        type=int, default=42)

    # aihub
    p = sub.add_parser("aihub", help="AI Hub JSON 데이터 변환")
    p.add_argument("--input_file",  required=True, help="AI Hub에서 다운로드한 JSON 파일")
    p.add_argument("--output_file", default="data/spellcheck_aihub.jsonl")

    # db
    p = sub.add_parser("db", help="블로그 DB에서 clean text 추출")
    p.add_argument("--output_file", default="data/clean_from_db.txt")
    p.add_argument("--db_url",      default="sqlite:///app.db")

    # split
    p = sub.add_parser("split", help="JSONL 파일 train/val 분리")
    p.add_argument("--input_file",  required=True)
    p.add_argument("--val_ratio",   type=float, default=0.1)
    p.add_argument("--seed",        type=int, default=42)

    args = parser.parse_args()

    if args.command == "synthetic":
        generate_synthetic(args.input_file, args.output_file, args.samples, args.seed)
    elif args.command == "aihub":
        convert_aihub(args.input_file, args.output_file)
    elif args.command == "db":
        extract_from_db(args.output_file, args.db_url)
    elif args.command == "split":
        split_data(args.input_file, args.val_ratio, args.seed)
    else:
        parser.print_help()
