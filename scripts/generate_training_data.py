"""
한국어 맞춤법 교정 학습 데이터 준비 스크립트
=============================================

== 권장 파이프라인 (등록 없이 즉시 시작) ==

  # 1단계: HuggingFace에서 실제 한국어 텍스트 다운로드 (등록 불필요)
  pip install datasets
  python scripts/generate_training_data.py download \\
    --output_file data/clean_ko_wiki.txt \\
    --source wikipedia --samples 50000

  # 2단계: 합성 오류 데이터 생성
  python scripts/generate_training_data.py synthetic \\
    --input_file  data/clean_ko_wiki.txt \\
    --output_file data/ko_correction_synthetic.jsonl \\
    --samples 20000

  # 3단계: (선택) AI Hub 실제 데이터와 병합
  python scripts/generate_training_data.py convert \\
    --input_file  data/raw/aihub.json \\
    --output_file data/ko_correction_aihub.jsonl
  cat data/ko_correction_aihub.jsonl data/ko_correction_synthetic.jsonl \\
    > data/ko_correction_merged.jsonl

  # 4단계: train/val 분리
  python scripts/generate_training_data.py split \\
    --input_file data/ko_correction_merged.jsonl   # 또는 synthetic.jsonl

  # 5단계: fine-tuning
  python scripts/train_ko_spellcheck.py \\
    --data_path  data/ko_correction_merged_train.jsonl \\
    --val_path   data/ko_correction_merged_val.jsonl \\
    --output_dir models/ko-et5-finetuned \\
    --base_model j5ng/et5-typos-corrector \\
    --epochs 3 --batch_size 8

  # 6단계: 서버 적용 (워커 재시작)
  SPELLCHECK_KO_FAST_MODEL=models/ko-et5-finetuned celery -A app.tasks worker ...

== 데이터 필드 규약 ==
  모든 JSONL: {"noisy": "오류 문장", "clean": "정답 문장"}
  CSV/TSV:   noisy,clean 헤더 (또는 헤더 없이 첫 열=noisy, 둘째 열=clean)

== 무료 데이터소스 ==
  1. AI Hub '한국어 맞춤법 교정 데이터' — aihub.or.kr (무료 회원가입 후 신청)
  2. 국립국어원 모두의말뭉치 — corpus.korean.go.kr (무료 회원가입 후 다운)
  3. NIKL 신문·구어 말뭉치 — 위와 동일 사이트
  4. 이 스크립트의 합성 데이터 — 즉시 사용 가능, 품질은 실제 데이터보다 낮음
"""

import argparse
import json
import random
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ── 한국어 오류 패턴 ──────────────────────────────────────

# 맞춤법 교정 학습에 가장 효과적인 오류: 형태소 혼동
WORD_CONFUSIONS = {
    # 모음 혼동
    "항상":   ["하상", "항쌍"],
    "있다":   ["잇다"],
    "있어":   ["이써", "잇어"],
    "있는":   ["잇는"],
    "있었":   ["잇었", "이썼"],
    "없다":   ["업다"],
    "없어":   ["업어"],
    "됐다":   ["됬다"],
    "됐어":   ["됬어"],
    "됩니다": ["됩니까", "됩니다"],
    # 조사 혼동
    "안 되":  ["안돼", "않 되"],
    "되어":   ["돼"],
    "돼서":   ["되서"],
    "않아":   ["안아"],
    "않고":   ["안고"],
    "않는":   ["안는"],
    "않았":   ["안았"],
    # 어미 혼동
    "왠지":   ["웬지"],
    "어떡해": ["어떻해"],
    "어떻게": ["어떡해"],
    # 접미사 혼동
    "깨끗이": ["깨끗히"],
    "열심히": ["열심이"],
    "솔직히": ["솔직이"],
    "특히":   ["특이"],
    "굉장히": ["굉장이"],
    "정확히": ["정확이"],
    # 조사 혼동 (짧은 것은 문맥에 의존하므로 주의)
    "로서":   ["로써"],
    "로써":   ["로서"],
    "던":     ["든"],
    "든":     ["던"],
    # 받침 오류
    "맞다":   ["맞따"],
    "좋다":   ["좋따"],
    "같다":   ["갗다"],
    "높다":   ["높따"],
}

# 받침 혼동 (글자 단위)
JONGSEONG_ERRORS = {
    "있": ["잇"],
    "없": ["업"],
    "읽": ["익"],
    "닭": ["닥"],
    "삶": ["삼"],
    "밟": ["밥"],
}

# 띄어쓰기 오류
SPACING_ERRORS = [
    ("있는데",    "있는 데"),
    ("없는데",    "없는 데"),
    ("할수록",    "할 수록"),
    ("뿐만아니라","뿐만 아니라"),
    ("것같다",    "것 같다"),
    ("수있다",    "수 있다"),
    ("수없다",    "수 없다"),
    ("하다보면",  "하다 보면"),
    ("해보면",    "해 보면"),
    ("해보니",    "해 보니"),
    ("찾아보다",  "찾아 보다"),
]


def _corrupt_text(clean: str) -> str:
    """깨끗한 문장에 오류 삽입"""
    t = clean
    for correct, errors in WORD_CONFUSIONS.items():
        if correct in t and random.random() < 0.2:
            t = t.replace(correct, random.choice(errors), 1)
    for correct, errors in JONGSEONG_ERRORS.items():
        if correct in t and random.random() < 0.08:
            t = t.replace(correct, random.choice(errors), 1)
    for spaced, nospace in SPACING_ERRORS:
        if random.random() < 0.08:
            if spaced in t:
                t = t.replace(spaced, nospace, 1)
            elif nospace in t:
                t = t.replace(nospace, spaced, 1)
    return t


# ── 데이터 변환 (AI Hub / 모두의말뭉치) ───────────────────

def _try_parse(obj: dict) -> Optional[Tuple[str, str]]:
    """다양한 JSON 구조에서 (noisy, clean) 추출 시도"""
    # 키 이름 후보 목록
    noisy_keys = ["noisy", "wrong", "original", "input",
                  "오류문장", "비표준문장", "원문", "문장1"]
    clean_keys = ["clean", "correct", "corrected", "output",
                  "교정문장", "표준문장", "교정문", "문장2"]

    src, tgt = None, None
    for k in noisy_keys:
        if k in obj:
            src = obj[k]
            break
    for k in clean_keys:
        if k in obj:
            tgt = obj[k]
            break

    # annotation 서브키 시도
    if not src or not tgt:
        ann = obj.get("annotation") or obj.get("label") or {}
        if isinstance(ann, dict):
            for k in noisy_keys:
                if k in ann:
                    src = ann[k]
                    break
            for k in clean_keys:
                if k in ann:
                    tgt = ann[k]
                    break

    if src and tgt:
        src, tgt = str(src).strip(), str(tgt).strip()
        if src and tgt and src != tgt and len(src) >= 3:
            return src, tgt
    return None


def _iter_raw(raw) -> List[Dict]:
    """JSON 루트가 리스트/딕셔너리 어느 쪽이든 레코드 목록으로"""
    if isinstance(raw, list):
        return raw
    # {"data": [...]} 또는 {"info": [...], "data": [...]}
    for k in ("data", "records", "items", "corpus", "list"):
        if k in raw and isinstance(raw[k], list):
            return raw[k]
    # 전체가 한 레코드
    return [raw]


def convert(input_file: str, output_file: str):
    """
    AI Hub / 모두의말뭉치 JSON(L) → 학습용 JSONL 변환.
    키 이름이 달라도 자동 감지.
    """
    p = Path(input_file)
    raw_text = p.read_text(encoding="utf-8")

    # .jsonl 처리
    if p.suffix == ".jsonl":
        records = [json.loads(l) for l in raw_text.splitlines() if l.strip()]
    else:
        raw = json.loads(raw_text)
        records = _iter_raw(raw)

    pairs = []
    failed = 0
    for rec in records:
        result = _try_parse(rec)
        if result:
            noisy, clean = result
            pairs.append({"noisy": noisy, "clean": clean})
        else:
            failed += 1

    if not pairs:
        print("[convert] 파싱 실패. JSON 구조를 확인하세요.")
        print(f"  샘플 키: {list(records[0].keys()) if records else '없음'}")
        sys.exit(1)

    if failed:
        print(f"[convert] 경고: {failed}개 레코드 파싱 실패 (필드명 불일치)")

    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        for pair in pairs:
            f.write(json.dumps(pair, ensure_ascii=False) + "\n")

    print(f"[convert] {len(pairs)}개 변환 완료 → {output_file}")
    print("  샘플 3개:")
    for pair in pairs[:3]:
        print(f"    noisy: {pair['noisy']}")
        print(f"    clean: {pair['clean']}")
        print()


# ── 합성 데이터 생성 ──────────────────────────────────────

def synthetic(input_file: str, output_file: str, n_samples: int, seed: int = 42):
    """
    깨끗한 텍스트 파일에서 합성 오류 데이터 생성.
    input_file: 한 줄에 하나의 문장 (UTF-8 텍스트)
    """
    random.seed(seed)
    lines = [l.strip() for l in Path(input_file).read_text(encoding="utf-8").splitlines()
             if l.strip() and len(l.strip()) >= 8 and len(l.strip()) <= 150]
    print(f"[synthetic] 원본 문장 {len(lines)}개 로드")

    if not lines:
        print("[synthetic] 오류: 유효한 문장이 없습니다.")
        sys.exit(1)

    pairs, attempts = [], 0
    while len(pairs) < n_samples and attempts < n_samples * 15:
        line = random.choice(lines)
        corrupted = _corrupt_text(line)
        if corrupted != line:
            pairs.append({"noisy": corrupted, "clean": line})
        attempts += 1

    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        for pair in pairs:
            f.write(json.dumps(pair, ensure_ascii=False) + "\n")

    print(f"[synthetic] {len(pairs)}개 학습 쌍 생성 → {output_file}")
    print("  샘플 3개:")
    for pair in pairs[:3]:
        print(f"    noisy: {pair['noisy']}")
        print(f"    clean: {pair['clean']}")
        print()

    if len(pairs) < n_samples * 0.5:
        print(f"[synthetic] 경고: 목표({n_samples})의 50% 미만 생성됨.")
        print("  → 원본 문장 수를 늘리거나 오류 삽입 rate를 높이세요.")


# ── HuggingFace 공개 데이터 다운로드 ─────────────────────

# 지원 소스 목록
_DOWNLOAD_SOURCES = {
    "wikipedia": {
        "desc": "한국어 위키백과 (Wikipedia) — 고품질 문어체, 6천만+ 문장",
        "hf_path": "wikimedia/wikipedia",
        "hf_name": "20231101.ko",
        "text_field": "text",
    },
    "news": {
        "desc": "CC-100 한국어 뉴스/웹 크롤링 텍스트 — 구어체 포함, 대용량",
        "hf_path": "cc100",
        "hf_name": "ko",
        "text_field": "text",
    },
    "namuwiki": {
        "desc": "나무위키 덤프 기반 한국어 텍스트 — 구어체/신조어 포함",
        "hf_path": "heegyu/namuwiki-extracted",
        "hf_name": None,
        "text_field": "text",
    },
}


def download(source: str, output_file: str, n_samples: int, min_len: int = 10, max_len: int = 150):
    """
    HuggingFace 공개 데이터셋에서 한국어 문장을 다운로드.
    등록/로그인 불필요. pip install datasets 만 있으면 됨.

    source    : wikipedia | news | namuwiki
    output_file: 한 줄에 하나의 문장 텍스트 파일 (synthetic의 --input_file로 사용)
    n_samples : 추출할 문장 수 (실제 다운로드되는 문서 수와 다름)
    """
    try:
        from datasets import load_dataset
    except ImportError:
        print("[download] 오류: datasets 라이브러리가 없습니다.")
        print("  pip install datasets")
        sys.exit(1)

    if source not in _DOWNLOAD_SOURCES:
        print(f"[download] 알 수 없는 소스: {source}")
        print(f"  사용 가능: {', '.join(_DOWNLOAD_SOURCES)}")
        sys.exit(1)

    cfg = _DOWNLOAD_SOURCES[source]
    print(f"[download] 소스: {cfg['desc']}")
    print(f"[download] 다운로드 중... (첫 실행 시 수분 소요, 이후 캐시됨)")

    try:
        ds = load_dataset(
            cfg["hf_path"],
            cfg["hf_name"],
            split="train",
            streaming=True,   # 전체 다운로드 없이 스트리밍 → 빠름
            trust_remote_code=True,
        )
    except Exception as e:
        print(f"[download] 로드 실패: {e}")
        print("  인터넷 연결을 확인하거나 다른 --source를 시도해보세요.")
        sys.exit(1)

    field = cfg["text_field"]
    sentences = []
    doc_count = 0

    print(f"[download] 문장 추출 중 (목표: {n_samples}개)...")
    for example in ds:
        text = example.get(field, "")
        if not text:
            continue
        doc_count += 1
        # 문서를 문장 단위로 분리
        for line in re.split(r'[.\n]', text):
            line = line.strip()
            # 한국어 비율 체크 (50% 이상 한글)
            ko_chars = len(re.findall(r'[\uAC00-\uD7A3]', line))
            total_chars = len(line.replace(' ', ''))
            if total_chars == 0:
                continue
            if ko_chars / total_chars < 0.5:
                continue
            if min_len <= len(line) <= max_len:
                sentences.append(line)
                if len(sentences) >= n_samples:
                    break
        if len(sentences) >= n_samples:
            break
        if doc_count % 1000 == 0:
            print(f"  문서 {doc_count}개 처리 → 문장 {len(sentences)}개 수집...")

    if not sentences:
        print("[download] 오류: 문장을 추출하지 못했습니다.")
        sys.exit(1)

    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    Path(output_file).write_text("\n".join(sentences), encoding="utf-8")

    print(f"[download] 완료: {len(sentences)}개 문장 → {output_file}")
    print(f"  (문서 {doc_count}개 처리)")
    print(f"\n  다음 단계:")
    print(f"  python scripts/generate_training_data.py synthetic \\")
    print(f"    --input_file {output_file} \\")
    print(f"    --output_file data/ko_correction_synthetic.jsonl \\")
    print(f"    --samples 20000")


# ── DB에서 블로그 글 추출 (게시글이 있을 때만 사용) ──────────

def extract_db(output_file: str, db_url: str = None):
    """
    블로그 DB에서 기존 게시글 텍스트 추출.
    결과 파일을 synthetic 명령의 --input_file로 사용.
    """
    if not db_url:
        # 프로젝트 기본 DB 경로 자동 탐색
        candidates = [
            Path("app.db"),
            Path("data/blog.db"),
            Path("instance/app.db"),
        ]
        env_db = None
        try:
            from app.config import settings
            env_db = settings.DATABASE_URL
        except Exception:
            pass
        if env_db:
            db_url = env_db
        else:
            for c in candidates:
                if c.exists():
                    db_url = f"sqlite:///{c}"
                    break
        if not db_url:
            print("[extract_db] DB URL을 찾지 못했습니다. --db_url을 직접 지정하세요.")
            sys.exit(1)

    try:
        from sqlalchemy import create_engine, text
        from bs4 import BeautifulSoup
    except ImportError:
        print("pip install sqlalchemy beautifulsoup4")
        sys.exit(1)

    engine = create_engine(db_url)
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT content_html FROM board_posts WHERE content_html IS NOT NULL")
        ).fetchall()

    texts = []
    for (html,) in rows:
        if not html:
            continue
        soup = BeautifulSoup(html, "html.parser")
        for line in soup.get_text(separator="\n").splitlines():
            line = line.strip()
            if 8 <= len(line) <= 150:
                texts.append(line)

    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    Path(output_file).write_text("\n".join(texts), encoding="utf-8")
    print(f"[extract_db] {len(texts)}개 문장 추출 → {output_file}")
    print(f"  다음 단계: python scripts/generate_training_data.py synthetic "
          f"--input_file {output_file} --output_file data/ko_correction_synthetic.jsonl")


# ── train/val 분리 ────────────────────────────────────────

def split(input_file: str, val_ratio: float = 0.1, seed: int = 42):
    """JSONL → _train.jsonl + _val.jsonl"""
    random.seed(seed)
    lines = [l for l in Path(input_file).read_text(encoding="utf-8").splitlines() if l.strip()]
    random.shuffle(lines)

    n_val = max(1, int(len(lines) * val_ratio))
    val_lines   = lines[:n_val]
    train_lines = lines[n_val:]

    base   = Path(input_file).stem.replace("_train", "").replace("_val", "")
    parent = Path(input_file).parent

    train_path = parent / f"{base}_train.jsonl"
    val_path   = parent / f"{base}_val.jsonl"

    train_path.write_text("\n".join(train_lines), encoding="utf-8")
    val_path.write_text("\n".join(val_lines), encoding="utf-8")

    print(f"[split] 학습: {len(train_lines)}개 → {train_path}")
    print(f"[split] 검증: {len(val_lines)}개 → {val_path}")
    print(f"\n  다음 단계:")
    print(f"  python scripts/train_ko_spellcheck.py \\")
    print(f"    --data_path {train_path} --val_path {val_path} \\")
    print(f"    --base_model j5ng/et5-typos-corrector \\")
    print(f"    --output_dir models/ko-et5-finetuned --epochs 3")


# ── 데이터소스 안내 ───────────────────────────────────────

def sources():
    print("""
== 한국어 맞춤법 교정 데이터소스 ==

[즉시 사용 가능 — 등록/로그인 불필요]

  pip install datasets
  python scripts/generate_training_data.py download \\
    --source wikipedia --output_file data/clean_ko_wiki.txt --samples 50000

  지원 소스:
    wikipedia  한국어 위키백과 (고품질 문어체, 권장)
    news       CC-100 한국어 웹 크롤링 (구어체 포함, 대용량)
    namuwiki   나무위키 (구어체/신조어 포함)

[AI Hub — 실제 (오류, 교정) 쌍, 최고 품질]

  URL : https://aihub.or.kr → "한국어 맞춤법 교정" 검색
  절차: 무료 회원가입 → 데이터 신청 → 승인(1~3일) → 다운로드
  변환:
    python scripts/generate_training_data.py convert \\
      --input_file data/raw/aihub.json \\
      --output_file data/ko_correction_aihub.jsonl

[국립국어원 모두의말뭉치 — clean text 소스]

  URL : https://corpus.korean.go.kr
  용도: download 대신 --input_file로 사용 가능 (텍스트 파일 직접 제공)

[권장 조합]

  # AI Hub 승인 전: Wikipedia 다운로드 → 합성 데이터로 먼저 학습
  python scripts/generate_training_data.py download --source wikipedia \\
    --output_file data/clean_ko_wiki.txt --samples 50000
  python scripts/generate_training_data.py synthetic \\
    --input_file data/clean_ko_wiki.txt \\
    --output_file data/ko_correction_synthetic.jsonl --samples 20000
  python scripts/generate_training_data.py split \\
    --input_file data/ko_correction_synthetic.jsonl

  # AI Hub 승인 후: 병합하여 재학습
  cat data/ko_correction_aihub.jsonl data/ko_correction_synthetic.jsonl \\
    > data/ko_correction_merged.jsonl
  python scripts/generate_training_data.py split \\
    --input_file data/ko_correction_merged.jsonl
""")


# ── CLI ───────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="한국어 맞춤법 교정 학습 데이터 준비",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("sources", help="무료 데이터소스 안내 출력")

    p = sub.add_parser("convert", help="AI Hub / 모두의말뭉치 JSON → JSONL 변환")
    p.add_argument("--input_file",  required=True, help="원본 JSON(L) 파일")
    p.add_argument("--output_file", default="data/ko_correction.jsonl")

    p = sub.add_parser("synthetic", help="깨끗한 텍스트로 합성 오류 데이터 생성")
    p.add_argument("--input_file",  required=True, help="깨끗한 텍스트 파일 (한 줄=한 문장)")
    p.add_argument("--output_file", default="data/ko_correction_synthetic.jsonl")
    p.add_argument("--samples",     type=int, default=5000)
    p.add_argument("--seed",        type=int, default=42)

    p = sub.add_parser("download",
        help="HuggingFace 공개 데이터셋 다운로드 (등록 불필요, pip install datasets 필요)")
    p.add_argument("--source",      default="wikipedia",
                   choices=list(_DOWNLOAD_SOURCES.keys()),
                   help="다운로드 소스: wikipedia(기본) | news | namuwiki")
    p.add_argument("--output_file", default="data/clean_ko.txt",
                   help="출력 텍스트 파일 (synthetic의 --input_file로 사용)")
    p.add_argument("--samples",     type=int, default=50000,
                   help="추출할 문장 수 (기본 50000)")
    p.add_argument("--min_len",     type=int, default=10)
    p.add_argument("--max_len",     type=int, default=150)

    p = sub.add_parser("extract_db",
        help="블로그 DB에서 깨끗한 텍스트 추출 (게시글이 있을 때만 유효)")
    p.add_argument("--output_file", default="data/clean_from_db.txt")
    p.add_argument("--db_url",      default=None, help="SQLAlchemy DB URL (기본: 자동 탐색)")

    p = sub.add_parser("split", help="JSONL → train/val 분리")
    p.add_argument("--input_file",  required=True)
    p.add_argument("--val_ratio",   type=float, default=0.1)
    p.add_argument("--seed",        type=int, default=42)

    args = parser.parse_args()

    if args.command == "sources":
        sources()
    elif args.command == "download":
        download(args.source, args.output_file, args.samples, args.min_len, args.max_len)
    elif args.command == "convert":
        convert(args.input_file, args.output_file)
    elif args.command == "synthetic":
        synthetic(args.input_file, args.output_file, args.samples, args.seed)
    elif args.command == "extract_db":
        extract_db(args.output_file, args.db_url)
    elif args.command == "split":
        split(args.input_file, args.val_ratio, args.seed)
    else:
        parser.print_help()
