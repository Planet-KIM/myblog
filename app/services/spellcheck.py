"""
맞춤법 교정 서비스 (한국어 + 영어)

언어별로 이미 fine-tuned된 모델을 사용합니다:
  - 한국어: j5ng/et5-typos-corrector          (T5 기반, 한국어 오타 교정 전용)
  - 영어:   vennify/t5-base-grammar-correction (기본) 또는 grammarly/coedit-large (고품질)

== 영어 모델 선택 ==
  .env 또는 환경변수로 선택:

  SPELLCHECK_EN_VARIANT=vennify   # 기본값, ~250M, 빠름
  SPELLCHECK_EN_VARIANT=coedit    # grammarly/coedit-large, ~780M, 고품질

  또는 HuggingFace 경로 / 로컬 경로 직접 지정:
  SPELLCHECK_EN_MODEL=models/my-en-model

  우선순위: SPELLCHECK_EN_MODEL > SPELLCHECK_EN_VARIANT

  모델별 프리픽스:
    vennify  → "grammar: {text}"
    coedit   → "Fix grammatical errors in this sentence: {text}"

== 이전 영어 모델 (학습용으로 보존) ==
  oliverguhr/spelling-correction-english-base  (BERT2BERT, 철자 교정 전용)
  교체 이유: 문법 오류(시제, 주어-동사 일치 등)를 교정하지 못함

== 서버 시작 시 사전 로드 ==
  app/main.py의 lifespan에서 load_all()을 호출하여 서버 시작 시 모델을 미리 로드합니다.

== 환경변수로 custom 모델 교체 ==
    SPELLCHECK_KO_MODEL=models/blog-spellcheck/best
"""

import os
import re
import threading

# ── 한국어 모델 variant 매핑 ──────────────────────────────
# 두 모델 모두 서버 시작 시 로드, 요청마다 variant로 선택
_KO_VARIANTS: dict = {
    "et5": {
        "model": os.environ.get("SPELLCHECK_KO_FAST_MODEL", "j5ng/et5-typos-corrector"),
        "prefix": "",          # et5는 prefix 없이 원문 그대로 입력
        "max_tokens": 400,
    },
    "pko": {
        "model": os.environ.get("SPELLCHECK_KO_QUALITY_MODEL", "paust/pko-t5-large"),
        "prefix": "맞춤법 교정: ",   # fine-tuning 시 이 prefix로 학습
        "max_tokens": 380,
    },
}

# 하위 호환 (환경변수 SPELLCHECK_KO_MODEL 단독 지정 시 et5에 적용)
KO_MODEL = _KO_VARIANTS["et5"]["model"]

# ── 영어 모델 variant 매핑 ─────────────────────────────────
# 두 모델 모두 서버 시작 시 로드, 요청마다 variant로 선택
_EN_VARIANTS: dict = {
    "vennify": {
        "model": "vennify/t5-base-grammar-correction",
        "prefix": "grammar: ",
        "max_tokens": 390,  # prefix ~10토큰 감안
    },
    "coedit": {
        "model": "grammarly/coedit-large",
        "prefix": "Fix grammatical errors in this sentence: ",
        "max_tokens": 380,  # prefix ~15토큰 감안
    },
}


def _filter_ko_hallucinations(original: str, corrected: str) -> str:
    """
    한국어 교정 결과에서 hallucination(엉뚱한 단어 치환)을 제거.

    판단 기준: 같은 위치 음절의 초성(첫 자음)이 바뀌면 hallucination.
      갓다  → 갔다  : 가(ㄱ)→갔(ㄱ)  초성 동일 → 교정 허용
      그는  → 나는  : 그(ㄱ)→나(ㄴ)  초성 변경 → 원본 복원
      그녀는 → 그들은: 녀(ㄴ)→들(ㄷ) 초성 변경 → 원본 복원

    토큰 수가 달라지는 경우(띄어쓰기 교정 등)는 교정 결과 그대로 반환.
    """
    _BASE = 0xAC00

    def chosung(ch: str) -> int:
        code = ord(ch) - _BASE
        if code < 0 or code > 11171:
            return -1          # 한국어 음절 아님
        return code // (21 * 28)

    def is_hallucination(ow: str, cw: str) -> bool:
        if ow == cw:
            return False
        # 구두점 제거
        import string
        punct = string.punctuation + '.,!?;:()[]"\'"\'。'
        oc = ow.strip(punct)
        cc = cw.strip(punct)
        if not oc or not cc:
            return False
        # 길이 차이가 2 초과 → 단어 자체가 바뀐 것
        if abs(len(oc) - len(cc)) > 2:
            return True
        # 같은 위치 음절의 초성 비교
        for a, b in zip(oc, cc):
            ca, cb = chosung(a), chosung(b)
            if ca >= 0 and cb >= 0 and ca != cb:
                return True
        return False

    orig_tokens = re.findall(r'\S+|\s+', original)
    corr_tokens = re.findall(r'\S+|\s+', corrected)

    if len(orig_tokens) != len(corr_tokens):
        # 토큰 수 불일치(띄어쓰기 교정 등) → 교정 결과 그대로
        return corrected

    result = []
    for ot, ct in zip(orig_tokens, corr_tokens):
        if not ot.strip():          # 공백 토큰
            result.append(ct)
        elif is_hallucination(ot, ct):
            result.append(ot)       # hallucination → 원본 복원
        else:
            result.append(ct)       # 정상 교정 적용
    return ''.join(result)


def detect_lang(text: str) -> str:
    """텍스트 언어 자동 감지 (한국어/영어)"""
    korean_chars = len(re.findall(r'[\uAC00-\uD7A3\u1100-\u11FF\u3130-\u318F]', text))
    total_chars = len(text.replace(' ', ''))
    if total_chars == 0:
        return "en"
    return "ko" if korean_chars / total_chars > 0.3 else "en"


def _split_into_chunks(text: str, tokenizer, max_tokens: int = 400):
    """
    텍스트를 (청크, 뒤따르는_구분자) 쌍의 리스트로 분할.

    분할 우선순위:
      1. 단락 경계 (\n 하나 이상)  — 항상 청크 경계로 사용
      2. 문장 경계 (.  !  ?  。)   — 단락이 max_tokens 초과 시
      3. 글자 경계                  — 단일 문장이 max_tokens 초과 시 (극히 드묾)

    반환값:
      [(chunk_text, delimiter), ...]
      delimiter : 이 청크 뒤에 붙일 구분자 ('\\n', '\\n\\n', ' ', '')
      마지막 요소의 delimiter 는 항상 ''

    예시:
      '안녕하세요.\\n\\n오늘 날씨가 좋네요. 산책하러 가자.'
      → [('안녕하세요.', '\\n\\n'), ('오늘 날씨가 좋네요. 산책하러 가자.', '')]
    """
    import re
    from typing import List, Tuple

    # ── 1단계: 단락 + 구분자 쌍으로 분리 ──────────────────
    # re.split에서 캡처 그룹(\n+)을 쓰면 구분자도 리스트에 포함됨
    parts = re.split(r'(\n+)', text)
    # parts = ['단락1', '\n\n', '단락2', '\n', '단락3', ...]

    paragraphs: List[Tuple[str, str]] = []
    i = 0
    while i < len(parts):
        para = parts[i]
        delim = parts[i + 1] if i + 1 < len(parts) else ''
        if not re.match(r'\n+', para):  # 구분자 자체는 스킵
            paragraphs.append((para, delim))
        i += 2 if i + 1 < len(parts) else 1

    # ── 2단계: 단락별로 문장 경계에서 세분화 ──────────────
    # 반환할 (청크, 구분자) 쌍
    result: List[Tuple[str, str]] = []

    for para_text, para_delim in paragraphs:
        if not para_text.strip():
            continue

        token_count = len(tokenizer.encode(para_text))

        if token_count <= max_tokens:
            # 단락 전체가 한 청크에 들어감
            result.append((para_text, para_delim))
            continue

        # 단락이 너무 길면 문장 단위로 분할
        # 한국어(。!?) + 영어(.!?) 문장 끝 패턴, 뒤에 공백 또는 줄끝
        sentence_ends = re.split(r'(?<=[.!?。])\s*', para_text)
        sentences = [s for s in sentence_ends if s.strip()]

        current_sents: List[str] = []
        current_tokens = 0

        for sent in sentences:
            t = len(tokenizer.encode(sent))

            if t > max_tokens:
                # 단일 문장 자체가 너무 긺 (극히 드묾) → 글자 수로 강제 분할
                if current_sents:
                    result.append((' '.join(current_sents), ' '))
                    current_sents = []
                    current_tokens = 0
                # 글자 단위 분할 (max_tokens * 3 ≈ 글자 수 상한)
                char_limit = max_tokens * 3
                for start in range(0, len(sent), char_limit):
                    piece = sent[start:start + char_limit]
                    is_last = (start + char_limit >= len(sent))
                    result.append((piece, '' if is_last else ' '))
                continue

            if current_tokens + t <= max_tokens:
                current_sents.append(sent)
                current_tokens += t
            else:
                # 현재 청크 저장 후 새 청크 시작
                if current_sents:
                    result.append((' '.join(current_sents), ' '))
                current_sents = [sent]
                current_tokens = t

        # 단락 내 마지막 청크 — 단락 구분자 사용
        if current_sents:
            result.append((' '.join(current_sents), para_delim))

    # 마지막 요소의 구분자 제거
    if result:
        result[-1] = (result[-1][0], '')

    return result


def _get_device():
    """
    사용 가능한 최적 디바이스 자동 선택
      CUDA (NVIDIA)  → cuda
      MPS  (Apple M시리즈) → mps   ← M4 MacBook 웹 서버에서 활성화됨
      CPU  → cpu

    SPELLCHECK_DEVICE 환경변수로 강제 지정 가능:
      SPELLCHECK_DEVICE=cpu   → Celery 워커처럼 fork된 프로세스에서 사용
      SPELLCHECK_DEVICE=mps   → 웹 서버에서 강제 MPS
      SPELLCHECK_DEVICE=cuda  → NVIDIA GPU 강제

    주의: MPS는 macOS fork된 자식 프로세스(Celery ForkPoolWorker)에서
          MTLCompilerService 접근이 차단되어 RuntimeError 발생.
          Celery 워커는 반드시 CPU를 사용해야 함.
    """
    import torch
    forced = os.environ.get("SPELLCHECK_DEVICE", "").strip().lower()
    if forced:
        print(f"[SpellCheck] 디바이스: {forced} (SPELLCHECK_DEVICE 환경변수)")
        return torch.device(forced)
    if torch.cuda.is_available():
        name = torch.cuda.get_device_name(0)
        print(f"[SpellCheck] 디바이스: cuda ({name})")
        return torch.device("cuda")
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        print("[SpellCheck] 디바이스: mps (Apple Silicon GPU)")
        return torch.device("mps")
    print("[SpellCheck] 디바이스: cpu")
    return torch.device("cpu")


class _KoSpellChecker:
    """
    한국어 맞춤법 교정기 — variant별 독립 인스턴스.

      et5 — j5ng/et5-typos-corrector, ~250M, 빠름 (현재 사용 중)
        prefix: "" (원문 그대로)

      pko — paust/pko-t5-large, ~780M, T5-large (Apache 2.0), 고품질
        prefix: "맞춤법 교정: {text}"
        fine-tuning 후 coedit 수준 기대 가능 (AI Hub 한국어 문법오류 데이터)

    교정 범위:
      - et5:  오타 교정 위주 (j5ng 모델 특성)
      - pko:  fine-tuning 전: 기본 생성만 / 후: 문법+맞춤법+띄어쓰기 가능
    """

    def __init__(self, variant: str):
        cfg = _KO_VARIANTS[variant]
        self._variant = variant
        self._model_id = cfg["model"]
        self._prefix = cfg["prefix"]
        self._max_tokens = cfg["max_tokens"]
        self._model = None
        self._tokenizer = None
        self._device = None
        self._lock = threading.Lock()
        self._loaded = False

    def _load(self):
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            try:
                from transformers import AutoTokenizer, T5ForConditionalGeneration
                print(f"[KoSpellChecker:{self._variant}] 로딩 중: {self._model_id}")
                self._tokenizer = AutoTokenizer.from_pretrained(self._model_id)
                self._model = T5ForConditionalGeneration.from_pretrained(self._model_id)
                self._device = _get_device()
                self._model = self._model.to(self._device)
                self._model.eval()
                self._loaded = True
                print(f"[KoSpellChecker:{self._variant}] 로딩 완료")
            except ImportError:
                raise RuntimeError("pip install transformers torch sentencepiece 를 실행하세요.")

    def _correct_chunk(self, text: str) -> str:
        """
        단일 청크 교정.

        생성 파라미터 설명:
          num_beams=3          : beam 5→3 으로 줄임. beam이 클수록 모델이
                                 "더 그럴듯한" 문장으로 치환하려는 경향 증가.
          no_repeat_ngram_size=3 : 3-gram 반복 방지 → 루프 출력 제거.
          repetition_penalty=1.3 : 이미 생성한 토큰 재사용 패널티 →
                                   단어 치환 hallucination 억제.
          length_penalty=1.0   : 짧은 출력에 불이익 없음 (교정이므로
                                  입력과 길이가 비슷해야 함).
        """
        import torch
        prefixed = f"{self._prefix}{text}" if self._prefix else text
        inputs = self._tokenizer(
            prefixed, return_tensors="pt", max_length=512, truncation=True
        )
        inputs = {k: v.to(self._device) for k, v in inputs.items()}
        with torch.no_grad():
            outputs = self._model.generate(
                **inputs,
                max_new_tokens=512,
                num_beams=3,
                no_repeat_ngram_size=3,
                repetition_penalty=1.3,
                length_penalty=1.0,
                early_stopping=True,
            )
        return self._tokenizer.decode(outputs[0], skip_special_tokens=True)

    def correct(self, text: str) -> str:
        """
        긴 텍스트를 청크로 분할해 교정 후 원래 구조로 복원.
        단락(\\n)과 문장 경계를 보존하며 분할하므로 결과가 잘리지 않음.
        교정 후 hallucination 필터 적용 (초성 바뀐 단어 복원).
        """
        self._load()
        chunks = _split_into_chunks(text, self._tokenizer, max_tokens=self._max_tokens)
        corrected_parts = []
        for chunk, delim in chunks:
            raw = self._correct_chunk(chunk)
            filtered = _filter_ko_hallucinations(chunk, raw)
            corrected_parts.append(filtered + delim)
        return ''.join(corrected_parts)

    @property
    def model_path(self) -> str:
        return self._model_id


class _EnSpellChecker:
    """
    영어 문법+맞춤법 교정기 — variant별 독립 인스턴스.

      vennify — vennify/t5-base-grammar-correction, ~250M, T5-base, 빠름
        prefix: "grammar: {text}"

      coedit  — grammarly/coedit-large, ~780M, T5-large (Apache 2.0), 고품질
        prefix: "Fix grammatical errors in this sentence: {text}"
        논문: CoEdIT (ACL 2023), fine-tuning/reproduce 가능

    교정 범위 (coedit이 더 넓음):
      - 철자/시제/주어-동사: 두 모델 모두 가능
      - 전치사:   married with → married to  (coedit만)
      - 형용사:   I am boring → I am bored   (coedit만)
    """

    def __init__(self, variant: str):
        cfg = _EN_VARIANTS[variant]
        self._variant = variant
        self._model_id = cfg["model"]
        self._prefix = cfg["prefix"]
        self._max_tokens = cfg["max_tokens"]
        self._model = None
        self._tokenizer = None
        self._device = None
        self._lock = threading.Lock()
        self._loaded = False

    def _load(self):
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            try:
                from transformers import AutoTokenizer, T5ForConditionalGeneration
                print(f"[EnSpellChecker:{self._variant}] 로딩 중: {self._model_id}")
                self._tokenizer = AutoTokenizer.from_pretrained(self._model_id)
                self._model = T5ForConditionalGeneration.from_pretrained(self._model_id)
                self._device = _get_device()
                self._model = self._model.to(self._device)
                self._model.eval()
                self._loaded = True
                print(f"[EnSpellChecker:{self._variant}] 로딩 완료")
            except ImportError:
                raise RuntimeError("pip install transformers torch 를 실행하세요.")

    def _correct_chunk(self, text: str) -> str:
        import torch
        prefixed = f"{self._prefix}{text}"
        inputs = self._tokenizer(
            prefixed, return_tensors="pt", max_length=512,
            truncation=True, padding=True
        )
        inputs = {k: v.to(self._device) for k, v in inputs.items()}
        with torch.no_grad():
            outputs = self._model.generate(
                **inputs,
                max_new_tokens=512,
                num_beams=5,
                early_stopping=True,
            )
        return self._tokenizer.decode(outputs[0], skip_special_tokens=True)

    def correct(self, text: str) -> str:
        self._load()
        chunks = _split_into_chunks(text, self._tokenizer, max_tokens=self._max_tokens)
        corrected_parts = [self._correct_chunk(chunk) + delim for chunk, delim in chunks]
        return ''.join(corrected_parts)

    @property
    def model_path(self) -> str:
        return self._model_id


# ── 싱글톤 인스턴스 ───────────────────────────────────────
# 웹 프로세스 & Celery 워커 모두 공유
_ko_et5 = _KoSpellChecker("et5")
_ko_pko  = _KoSpellChecker("pko")
_en_vennify = _EnSpellChecker("vennify")
_en_coedit  = _EnSpellChecker("coedit")

_KO_CHECKERS = {
    "et5": _ko_et5,
    "pko": _ko_pko,
}
_EN_CHECKERS = {
    "vennify": _en_vennify,
    "coedit":  _en_coedit,
}


def load_all() -> None:
    """
    빠른 모델만 사전 로드 (ko-et5 + en-vennify).

    고품질 모델(pko / coedit)은 첫 요청 시 lazy 로드됩니다.
    이유: pko-t5-large(780MB) + coedit(780MB) 미리 다운로드 시
         Celery 워커 시작이 수분 이상 블로킹되고 OOM 위험이 있음.
    첫 '고품질' 요청은 모델 로드 시간이 걸리지만 이후 요청은 빠릅니다.
    """
    print("[SpellCheck] 빠른 모델 사전 로딩 시작 (ko-et5 + en-vennify)...")
    _ko_et5._load()
    _en_vennify._load()
    print("[SpellCheck] 모델 로딩 완료 ✓  (pko / coedit 은 첫 요청 시 자동 로드)")


def correct(text: str, en_variant: str = "vennify", ko_variant: str = "et5") -> str:
    """
    언어 감지 후 적절한 모델로 교정.
      ko_variant: "et5" (빠름) | "pko" (고품질)
      en_variant: "vennify" (빠름) | "coedit" (고품질)
    """
    lang = detect_lang(text)
    if lang == "ko":
        checker = _KO_CHECKERS.get(ko_variant, _ko_et5)
        return checker.correct(text)
    checker = _EN_CHECKERS.get(en_variant, _en_vennify)
    return checker.correct(text)


def model_info(text: str, en_variant: str = "vennify", ko_variant: str = "et5") -> str:
    """사용된 모델 경로 반환"""
    if detect_lang(text) == "ko":
        return _KO_CHECKERS.get(ko_variant, _ko_et5).model_path
    return _EN_CHECKERS.get(en_variant, _en_vennify).model_path
