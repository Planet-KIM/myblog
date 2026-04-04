"""
맞춤법 교정 서비스 (한국어 + 영어)

언어별로 이미 fine-tuned된 모델을 사용합니다:
  - 한국어: j5ng/et5-typos-corrector  (T5 기반, 한국어 오타 교정 전용)
  - 영어:   oliverguhr/spelling-correction-english-base  (BERT 기반, 영어 교정 전용)

두 모델 모두 HuggingFace transformers를 통해 아키텍처 열람/수정 가능합니다:
    from transformers import T5ForConditionalGeneration
    model = T5ForConditionalGeneration.from_pretrained("j5ng/et5-typos-corrector")
    print(model)  # 전체 레이어 구조 확인
    model.encoder.block[0].layer[0].SelfAttention.q.weight  # 특정 레이어 접근

나중에 직접 fine-tuning한 모델로 교체하려면:
    SPELLCHECK_KO_MODEL=models/my-ko-model
    SPELLCHECK_EN_MODEL=models/my-en-model
"""

import os
import re
import threading

KO_MODEL = os.environ.get("SPELLCHECK_KO_MODEL", "j5ng/et5-typos-corrector")
EN_MODEL = os.environ.get("SPELLCHECK_EN_MODEL", "oliverguhr/spelling-correction-english-base")


def detect_lang(text: str) -> str:
    """텍스트 언어 자동 감지 (한국어/영어)"""
    korean_chars = len(re.findall(r'[\uAC00-\uD7A3\u1100-\u11FF\u3130-\u318F]', text))
    total_chars = len(text.replace(' ', ''))
    if total_chars == 0:
        return "en"
    return "ko" if korean_chars / total_chars > 0.3 else "en"


class _KoSpellChecker:
    """
    한국어 맞춤법 교정기 — j5ng/et5-typos-corrector
    T5ForConditionalGeneration 기반 seq2seq 모델
    """

    def __init__(self):
        self._model = None
        self._tokenizer = None
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
                print(f"[KoSpellChecker] 로딩 중: {KO_MODEL}")
                self._tokenizer = AutoTokenizer.from_pretrained(KO_MODEL)
                self._model = T5ForConditionalGeneration.from_pretrained(KO_MODEL)
                self._model.eval()
                if torch.cuda.is_available():
                    self._model = self._model.cuda()
                self._loaded = True
                print(f"[KoSpellChecker] 로딩 완료")
            except ImportError:
                raise RuntimeError("pip install transformers torch 를 실행하세요.")

    def correct(self, text: str) -> str:
        import torch
        self._load()
        inputs = self._tokenizer(
            text, return_tensors="pt", max_length=512, truncation=True
        )
        if next(self._model.parameters()).is_cuda:
            inputs = {k: v.cuda() for k, v in inputs.items()}
        with torch.no_grad():
            outputs = self._model.generate(
                **inputs,
                max_length=512,
                num_beams=5,
                early_stopping=True,
            )
        return self._tokenizer.decode(outputs[0], skip_special_tokens=True)

    @property
    def model_path(self) -> str:
        return KO_MODEL


class _EnSpellChecker:
    """
    영어 맞춤법 교정기 — oliverguhr/spelling-correction-english-base
    EncoderDecoderModel (BERT2BERT) 기반
    """

    def __init__(self):
        self._model = None
        self._tokenizer = None
        self._lock = threading.Lock()
        self._loaded = False

    def _load(self):
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            try:
                from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
                import torch
                print(f"[EnSpellChecker] 로딩 중: {EN_MODEL}")
                self._tokenizer = AutoTokenizer.from_pretrained(EN_MODEL)
                self._model = AutoModelForSeq2SeqLM.from_pretrained(EN_MODEL)
                self._model.eval()
                if torch.cuda.is_available():
                    self._model = self._model.cuda()
                self._loaded = True
                print(f"[EnSpellChecker] 로딩 완료")
            except ImportError:
                raise RuntimeError("pip install transformers torch 를 실행하세요.")

    def correct(self, text: str) -> str:
        import torch
        self._load()
        inputs = self._tokenizer(
            text, return_tensors="pt", max_length=512,
            truncation=True, padding=True
        )
        if next(self._model.parameters()).is_cuda:
            inputs = {k: v.cuda() for k, v in inputs.items()}
        with torch.no_grad():
            outputs = self._model.generate(
                **inputs,
                max_length=512,
                num_beams=4,
                early_stopping=True,
            )
        return self._tokenizer.decode(outputs[0], skip_special_tokens=True)

    @property
    def model_path(self) -> str:
        return EN_MODEL


# 싱글톤 인스턴스
_ko = _KoSpellChecker()
_en = _EnSpellChecker()


def correct(text: str) -> str:
    """언어 감지 후 적절한 모델로 교정"""
    lang = detect_lang(text)
    if lang == "ko":
        return _ko.correct(text)
    return _en.correct(text)


def model_info(text: str) -> str:
    """사용된 모델 경로 반환"""
    return KO_MODEL if detect_lang(text) == "ko" else EN_MODEL
