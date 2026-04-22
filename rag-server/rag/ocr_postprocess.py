"""
ocr_postprocess.py
OCR 도메인 교정기 (Korean/English 혼합)
- 1차: exact alias 치환
- 2차: 구(phrase) 단위 fuzzy 치환
- 3차: 토큰(token) 단위 fuzzy 치환
- 오탐 방지 가드레일 + 변경 이력(audit) 반환
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional
import re

from rapidfuzz import fuzz, process


# ---------------------------------------------------------
# 설정
# ---------------------------------------------------------

@dataclass(frozen=True)
class CorrectorConfig:
    min_token_len: int = 4
    min_phrase_len: int = 6
    token_cutoff: int = 90
    phrase_cutoff: int = 92
    max_len_delta: int = 4
    keep_case_for_english: bool = True


# ---------------------------------------------------------
# 유틸
# ---------------------------------------------------------

_KO_EN_TOKEN_RE = re.compile(r"[가-힣A-Za-z0-9]+")

def _tokens_with_spans(text: str) -> List[Tuple[str, int, int]]:
    return [(m.group(0), m.start(), m.end()) for m in _KO_EN_TOKEN_RE.finditer(text)]

def _is_korean_text(s: str) -> bool:
    return any("가" <= ch <= "힣" for ch in s)

def _len_guard(src: str, tgt: str, max_delta: int) -> bool:
    return abs(len(src) - len(tgt)) <= max_delta

def _char_guard(src: str, tgt: str) -> bool:
    # 과교정 방지: 첫 글자/마지막 글자 중 하나라도 맞으면 통과
    if not src or not tgt:
        return False
    return (src[0] == tgt[0]) or (src[-1] == tgt[-1])


# ---------------------------------------------------------
# 교정기
# ---------------------------------------------------------

class OCRDomainCorrector:
    """
    canonical_terms: 표준 용어 목록 (학과명/과목명)
    alias_map: 자주 깨지는 고정 오타 -> 표준 용어 (exact 치환)
    """
    def __init__(
        self,
        canonical_terms: List[str],
        alias_map: Optional[Dict[str, str]] = None,
        config: Optional[CorrectorConfig] = None,
    ):
        self.cfg = config or CorrectorConfig()
        self.canonical_terms = sorted(set(canonical_terms), key=len, reverse=True)
        self.alias_map = alias_map or {}

        # phrase 후보(공백 포함) / token 후보(공백 없는 단어)
        self.phrase_choices = [t for t in self.canonical_terms if " " in t or len(t) >= self.cfg.min_phrase_len]
        self.token_choices = [t for t in self.canonical_terms if " " not in t and len(t) >= self.cfg.min_token_len]

    def correct(self, text: str) -> Tuple[str, List[dict]]:
        if not text:
            return "", []

        original = text
        audits: List[dict] = []

        # 1) exact alias 치환
        for wrong, right in self.alias_map.items():
            if wrong in text:
                text = text.replace(wrong, right)
                audits.append({"type": "exact", "from": wrong, "to": right, "score": 100})

        # 2) phrase 단위 fuzzy 치환 (문장 스캔)
        text, phrase_audits = self._phrase_fuzzy_pass(text)
        audits.extend(phrase_audits)

        # 3) token 단위 fuzzy 치환
        text, token_audits = self._token_fuzzy_pass(text)
        audits.extend(token_audits)

        # 중복 audit 정리
        dedup = []
        seen = set()
        for a in audits:
            key = (a["type"], a["from"], a["to"], a["score"])
            if key not in seen:
                seen.add(key)
                dedup.append(a)

        return text, dedup

    def _phrase_fuzzy_pass(self, text: str) -> Tuple[str, List[dict]]:
        audits: List[dict] = []
        if not self.phrase_choices:
            return text, audits

        # 공백 기준 2~6-gram phrase 생성 후 치환
        words = text.split()
        if len(words) < 2:
            return text, audits

        # 긴 phrase부터 치환하여 충돌 최소화
        for n in range(6, 1, -1):
            if len(words) < n:
                continue
            i = 0
            while i + n <= len(words):
                src_phrase = " ".join(words[i:i+n]).strip()
                if len(src_phrase) < self.cfg.min_phrase_len:
                    i += 1
                    continue

                m = process.extractOne(
                    src_phrase,
                    self.phrase_choices,
                    scorer=fuzz.WRatio,
                    score_cutoff=self.cfg.phrase_cutoff,
                )
                if not m:
                    i += 1
                    continue

                tgt, score, _ = m

                # 가드레일
                if not _len_guard(src_phrase, tgt, self.cfg.max_len_delta):
                    i += 1
                    continue
                if not _char_guard(src_phrase.replace(" ", ""), tgt.replace(" ", "")):
                    i += 1
                    continue
                
                if src_phrase != tgt:  # 같으면 스킵
                    words[i:i+n] = [tgt]
                    audits.append({"type": "phrase_fuzzy", "from": src_phrase, "to": tgt, "score": round(score, 2)})
                    i += 1

        return " ".join(words), audits

    def _token_fuzzy_pass(self, text: str) -> Tuple[str, List[dict]]:
        audits: List[dict] = []
        if not self.token_choices:
            return text, audits

        parts = []
        last = 0
        for tok, s, e in _tokens_with_spans(text):
            parts.append(text[last:s])

            replaced = tok
            if len(tok) >= self.cfg.min_token_len:
                m = process.extractOne(
                    tok,
                    self.token_choices,
                    scorer=fuzz.ratio,
                    score_cutoff=self.cfg.token_cutoff,
                )
                if m:
                    tgt, score, _ = m

                    # 가드레일
                    if _len_guard(tok, tgt, self.cfg.max_len_delta) and _char_guard(tok, tgt):
                        # 한글 토큰은 한글 후보로, 영문 토큰은 영문 후보로 제한
                        if _is_korean_text(tok) == _is_korean_text(tgt):
                            if tok != tgt:  # 같으면 스킵
                                replaced = tgt
                                audits.append({"type": "token_fuzzy", "from": tok, "to": tgt, "score": round(score, 2)})

            parts.append(replaced)
            last = e

        parts.append(text[last:])
        return "".join(parts), audits


# ---------------------------------------------------------
# 학과명 + 이수구분 + 과목명
# ---------------------------------------------------------
CANONICAL_TERMS = [
    # 의과대학
    "의예과", "의학과", "간호학과",

    # 자연과학대학
    "화학과", "식품영양학과", "환경보건학과", "생명과학과",
    "스포츠과학과", "사회체육학과", "스포츠의학과",

    # 인문사회과학대학
    "유아교육과", "특수교육과", "청소년교육상담학과",
    "법학과", "행정학과", "경찰행정학과", "사회복지학과",

    # 글로벌경영대학
    "경영학과", "국제통상학과", "관광경영학과",
    "경제금융학과", "IT금융경영학과", "글로벌문화산업학과", "회계학과",

    # 공과대학
    "컴퓨터공학과", "정보통신공학과", "전자공학과", "전기공학과",
    "전자정보공학과", "나노화학공학과", "에너지환경공학과",
    "디스플레이신소재공학과", "기계공학과",

    # SW융합대학
    "컴퓨터소프트웨어공학과", "정보보호학과", "메타버스게임학과",

    # 의료과학대학
    "보건행정경영학과", "의료생명공학과", "의료IT공학과",
    "임상병리학과", "작업치료학과", "의약공학과", "의공학과",

    # 미디어/기타
    "한국문화콘텐츠학과", "영미학과", "중국학과",
    "미디어커뮤니케이션학과", "건축학과", "디지털애니메이션학과",
    "AI빅데이터학과", "사물인터넷학과", "스마트자동차학과",
    "에너지공학과", "공연영상학과",

    # 기타 학부/전공
    "글로벌자유전공학과",
    "자동차산업공학과", "융합기계학과", "신뢰성품질공학과",
    "산업경영공학과", "메카트로닉스공학과", "화학공학과",
    "세무회계학과", "스마트팩토리공학과", "스마트모빌리티공학과",
    "융합바이오화학공학과"
]
CANONICAL_TERMS += [
    "학부기초", "학과기초", "전공", "전공필수", "전공선택",
    "교양", "교양필수", "교양선택",
    "일반선택", "자유선택"
]
# ---------------------------------------------------------
# 과목명 (계속 추가 필요)
# ---------------------------------------------------------
CANONICAL_TERMS += [
    "공중보건학개론", "보건통계학", "해부생리학",
    "병리학", "미생물학", "생화학",
    "데이터베이스", "자료구조", "운영체제",
    "컴퓨터네트워크", "인공지능", "머신러닝",
    "딥러닝", "알고리즘", "확률과통계",
    "선형대수", "미적분학"
]

ALIAS_MAP = {
    "보건행정경영학괴": "보건행정경영학과",
    "간호학괴": "간호학과",
    "컴퓨터공학괴": "컴퓨터공학과",
    "데이터베이스스": "데이터베이스",
}

corrector = OCRDomainCorrector(
    canonical_terms=CANONICAL_TERMS,
    alias_map=ALIAS_MAP,
    config=CorrectorConfig(
        token_cutoff=90,
        phrase_cutoff=92,
        min_token_len=4,
        min_phrase_len=6,
        max_len_delta=4,
    ),
)

# 적용:
# corrected_text, audits = corrector.correct(page_text)