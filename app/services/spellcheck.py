"""
맞춤법 교정 서비스 (한국어 + 영어)

언어별로 이미 fine-tuned된 모델을 사용합니다:
  - 한국어: j5ng/et5-typos-corrector          (T5 기반, 한국어 오타 교정 전용)
  - 영어:   vennify/t5-base-grammar-correction (T5 기반, 영어 철자 + 문법 교정)

== 이전 영어 모델 (학습용으로 보존) ==
  oliverguhr/spelling-correction-english-base  (BERT2BERT, 철자 교정 전용)
  교체 이유: 문법 오류(시제, 주어-동사 일치 등)를 교정하지 못함
  환경변수로 되돌리기: SPELLCHECK_EN_MODEL=oliverguhr/spelling-correction-english-base

== 서버 시작 시 사전 로드 ==
  app/main.py의 lifespan에서 load_all()을 호출하여 서버 시작 시 모델을 미리 로드합니다.
  최초 요청 지연 (20~30초) 없이 즉시 응답 가능합니다.

== Celery 워커에서도 동일하게 사용 ==
  app/tasks/spellcheck_task.py의 worker_process_init 시그널에서
  load_all()을 호출하여 워커 시작 시 미리 로드합니다.

== 모델 아키텍처 열람/수정 ==
    from transformers import T5ForConditionalGeneration
    model = T5ForConditionalGeneration.from_pretrained("j5ng/et5-typos-corrector")
    print(model)                                          # 전체 레이어 구조
    model.encoder.block[0].layer[0].SelfAttention.q.weight  # 특정 레이어 접근

== 환경변수로 custom 모델 교체 ==
    SPELLCHECK_KO_MODEL=models/blog-spellcheck/best
    SPELLCHECK_EN_MODEL=models/my-en-model
"""

import os
import re
import threading

KO_MODEL = os.environ.get("SPELLCHECK_KO_MODEL", "j5ng/et5-typos-corrector")
EN_MODEL = os.environ.get("SPELLCHECK_EN_MODEL", "vennify/t5-base-grammar-correction")

# 이전 영어 모델 — 삭제하지 않고 보존 (학습/비교 용도)
# EN_MODEL_LEGACY = "oliverguhr/spelling-correction-english-base"
# 직접 뜯어보려면:
#   from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
#   tok = AutoTokenizer.from_pretrained(EN_MODEL_LEGACY)
#   mdl = AutoModelForSeq2SeqLM.from_pretrained(EN_MODEL_LEGACY)
#   print(mdl)  # EncoderDecoderModel(BERT2BERT) 구조 확인


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
    한국어 맞춤법 교정기 — j5ng/et5-typos-corrector
    T5ForConditionalGeneration 기반 seq2seq 모델
    """

    def __init__(self):
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
                print(f"[KoSpellChecker] 로딩 중: {KO_MODEL}")
                self._tokenizer = AutoTokenizer.from_pretrained(KO_MODEL)
                self._model = T5ForConditionalGeneration.from_pretrained(KO_MODEL)
                self._device = _get_device()
                self._model = self._model.to(self._device)
                self._model.eval()
                self._loaded = True
                print("[KoSpellChecker] 로딩 완료")
            except ImportError:
                raise RuntimeError("pip install transformers torch sentencepiece 를 실행하세요.")

    def _correct_chunk(self, text: str) -> str:
        """단일 청크 교정 — max_tokens 이하의 텍스트만 받음"""
        import torch
        inputs = self._tokenizer(
            text, return_tensors="pt", max_length=512, truncation=True
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
        """
        긴 텍스트를 청크로 분할해 교정 후 원래 구조로 복원.
        단락(\\n)과 문장 경계를 보존하며 분할하므로 결과가 잘리지 않음.
        """
        self._load()
        chunks = _split_into_chunks(text, self._tokenizer, max_tokens=400)
        corrected_parts = [self._correct_chunk(chunk) + delim for chunk, delim in chunks]
        return ''.join(corrected_parts)

    @property
    def model_path(self) -> str:
        return KO_MODEL


class _EnSpellChecker:
    """
    영어 문법+맞춤법 교정기 — vennify/t5-base-grammar-correction
    T5ForConditionalGeneration 기반 seq2seq 모델

    한국어 모델(j5ng/et5-typos-corrector)과 동일한 T5 아키텍처라서
    scripts/train_spellcheck.py 로 fine-tuning 가능합니다.

    교정 범위:
      - 철자 오류:   recieve → receive
      - 시제 오류:   She go → She went / buyed → bought
      - 주어-동사:   I am agree → I agree
      - 관사:        a apple → an apple

    뜯어보기:
      from transformers import T5ForConditionalGeneration
      m = T5ForConditionalGeneration.from_pretrained("vennify/t5-base-grammar-correction")
      print(m)                                    # 전체 레이어 구조
      print(sum(p.numel() for p in m.parameters()))  # 파라미터 수 (~242M)

    이전 모델(oliverguhr, BERT2BERT) 비교 학습:
      from transformers import AutoModelForSeq2SeqLM
      old = AutoModelForSeq2SeqLM.from_pretrained("oliverguhr/spelling-correction-english-base")
      print(old)  # EncoderDecoderModel 구조 — T5와 구조 차이 확인 가능
    """

    def __init__(self):
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
                import torch
                print(f"[EnSpellChecker] 로딩 중: {EN_MODEL}")
                self._tokenizer = AutoTokenizer.from_pretrained(EN_MODEL)
                self._model = T5ForConditionalGeneration.from_pretrained(EN_MODEL)
                # vennify/t5-base-grammar-correction 은 T5 기반이라 MPS 지원
                self._device = _get_device()
                self._model = self._model.to(self._device)
                self._model.eval()
                self._loaded = True
                print("[EnSpellChecker] 로딩 완료")
            except ImportError:
                raise RuntimeError("pip install transformers torch 를 실행하세요.")

    def _correct_chunk(self, text: str) -> str:
        """단일 청크 교정 — max_tokens 이하의 텍스트만 받음"""
        import torch
        # vennify 모델은 "grammar: " 프리픽스를 붙여야 교정 모드로 동작
        prefixed = f"grammar: {text}"
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
        """
        긴 텍스트를 청크로 분할해 교정 후 원래 구조로 복원.
        단락(\\n)과 문장 경계를 보존하며 분할하므로 결과가 잘리지 않음.
        프리픽스 'grammar: '는 청크별로 독립 적용됨.
        """
        self._load()
        chunks = _split_into_chunks(text, self._tokenizer, max_tokens=390)
        # 영어 모델은 "grammar: " 프리픽스(약 10토큰)가 추가되므로 390으로 더 보수적으로
        corrected_parts = [self._correct_chunk(chunk) + delim for chunk, delim in chunks]
        return ''.join(corrected_parts)

    @property
    def model_path(self) -> str:
        return EN_MODEL


# 싱글톤 인스턴스 (웹 프로세스 & Celery 워커 모두 공유)
_ko = _KoSpellChecker()
_en = _EnSpellChecker()


def load_all() -> None:
    """
    두 모델 모두 미리 로드.
    - 웹 서버: app/main.py lifespan startup 에서 호출
    - Celery 워커: app/tasks/spellcheck_task.py worker_process_init 에서 호출
    첫 요청 지연을 없애기 위한 함수.
    """
    print("[SpellCheck] 모델 사전 로딩 시작...")
    _ko._load()
    _en._load()
    print("[SpellCheck] 모델 사전 로딩 완료 ✓")


def correct(text: str) -> str:
    """언어 감지 후 적절한 모델로 교정"""
    lang = detect_lang(text)
    if lang == "ko":
        return _ko.correct(text)
    return _en.correct(text)


def model_info(text: str) -> str:
    """사용된 모델 경로 반환"""
    return KO_MODEL if detect_lang(text) == "ko" else EN_MODEL
