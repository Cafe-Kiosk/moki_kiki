"""서버리스 환경용 무상태 로컬 검색 저장소.

Vercel에서는 첫 요청마다 FAISS 인덱스를 다시 쓰지 않도록 JSONL 문서를 메모리에
올리고 단어·한글 글자 조각의 겹침으로 후보를 고른다. 별칭·정책·맛 규칙 검색은
기존 retrieve.py가 먼저 적용하므로 이 저장소는 의미 후보를 보충하는 역할만 한다.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

from .documents import build_documents


_KO_STOPWORDS = {
    "것", "것을", "그거", "그걸", "나", "나는", "말해", "말해줘", "마시고", "먹고",
    "뭐", "뭔가", "무엇", "어떤", "알려", "알려줘", "있", "있나", "있나요", "제일",
    "좀", "좋은", "주세요", "해", "해줘", "하나", "싶", "싶어", "싶어요",
}
_EN_STOPWORDS = {
    "a", "an", "any", "are", "can", "could", "do", "for", "give", "have", "i",
    "is", "it", "me", "much", "of", "please", "recommend", "show", "something",
    "some", "that", "the", "there", "to", "want", "what", "with", "without", "you",
}
_KO_SUFFIXES = (
    "인가요", "있나요", "이에요", "예요", "에서", "으로", "처럼", "하면서",
    "하고", "가요", "나요", "은", "는", "이", "가", "을", "를", "의", "에", "도", "만",
)
_CANONICAL = {
    "카카오": "chocolate", "코코아": "chocolate", "초코": "chocolate",
    "초코라떼": "chocolate", "초콜릿": "chocolate", "chocolate": "chocolate",
    "부드럽": "smooth", "부드러": "smooth", "smooth": "smooth",
    "bitter": "bitter", "bitterness": "bitter",
}


def _english_stem(word: str) -> str:
    """작은 어휘 검색을 위한 보수적 어간 정규화."""
    if word.endswith("iness") and len(word) > 7:
        return word[:-5] + "y"
    if word.endswith("ness") and len(word) > 6:
        return word[:-4]
    if word.endswith("ies") and len(word) > 5:
        return word[:-3] + "y"
    if word.endswith("ing") and len(word) > 6:
        return word[:-3]
    if word.endswith("ed") and len(word) > 5:
        return word[:-2]
    if word.endswith("s") and len(word) > 4:
        return word[:-1]
    return word


def _korean_stem(word: str) -> str:
    for suffix in _KO_SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 1:
            return word[:-len(suffix)]
    return word


def _canonical(word: str) -> str:
    if word in _CANONICAL:
        return _CANONICAL[word]
    # 한국어는 어미가 달라도 같은 맛 표현으로 묶이도록 접두를 살펴본다.
    if word.startswith("부드러") or word.startswith("부드럽"):
        return "smooth"
    return word


def _features(text: str) -> dict[str, float]:
    """단어는 크게, 한국어 단어 내 2-gram은 작게 반영한다.

    문장 전체의 한글을 이어 붙이지 않아 단어 경계에서 생기던 가짜 2-gram을
    막고, 질문 표현보다 메뉴 핵심어가 점수를 주도하게 한다.
    """
    features: dict[str, float] = {}
    for raw in re.findall(r"[a-z0-9]+|[가-힣]+", str(text).lower()):
        is_korean = bool(re.fullmatch(r"[가-힣]+", raw))
        word = _korean_stem(raw) if is_korean else _english_stem(raw)
        stopwords = _KO_STOPWORDS if is_korean else _EN_STOPWORDS
        if not word or word in stopwords or raw in stopwords:
            continue

        canonical = _canonical(word)
        features[f"w:{canonical}"] = max(features.get(f"w:{canonical}", 0.0), 2.0)
        if is_korean and len(word) >= 2:
            for index in range(len(word) - 1):
                gram = word[index:index + 2]
                features[f"g:{gram}"] = max(features.get(f"g:{gram}", 0.0), 0.55)
    return features


@dataclass
class _DocStore:
    _dict: dict[str, object]


class LexicalStore:
    """hybrid_search가 요구하는 FAISS의 최소 인터페이스를 제공한다."""

    def __init__(self):
        documents = build_documents()
        self.docstore = _DocStore({str(index): doc for index, doc in enumerate(documents)})
        self._entries = [
            (
                document,
                _features(document.page_content),
                # JSONL 메뉴 문서의 앞 8줄은 이름·설명·재료·식감·별칭이다.
                # 뒤의 공통 옵션 안내가 다른 메뉴의 핵심어로 잘못 점수화되는
                # 것을 막기 위해 고유 설명 영역을 따로 보존한다.
                _features("\n".join(document.page_content.splitlines()[:8])),
            )
            for document in documents
        ]
        document_frequency = Counter()
        for _, _, primary_features in self._entries:
            document_frequency.update(primary_features.keys())
        count = max(1, len(self._entries))
        self._idf = {
            feature: math.log((count + 1) / (frequency + 1)) + 1.0
            for feature, frequency in document_frequency.items()
        }

    def similarity_search_with_score(self, query: str, k: int = 4):
        return self._search(query, k=k, language=None)

    def similarity_search_with_score_for_language(
            self, query: str, language: str, k: int = 4):
        """언어가 다른 문서가 top-k 자리를 차지하기 전에 후보를 제한한다."""
        return self._search(query, k=k, language=language)

    def _search(self, query: str, k: int, language: str | None):
        query_features = _features(query)
        denominator = sum(
            weight * self._idf.get(feature, 1.0)
            for feature, weight in query_features.items()
        )
        ranked = []
        for document, document_features, primary_features in self._entries:
            if language and document.metadata.get("lang") != language:
                continue
            overlap = sum(
                weight * self._idf.get(feature, 1.0)
                * (1.0 if feature in primary_features else 0.2)
                for feature, weight in query_features.items()
                if feature in document_features
            )
            coverage = overlap / denominator if denominator else 0.0
            # 기존 검색기는 0~2 L2 거리처럼 작을수록 관련성이 높다고 해석한다.
            # 핵심어 하나만 공통인 장문이 기준값을 넘지 않도록 중간 점수를
            # 보수적으로 펼친다. 메뉴명·재료처럼 여러 근거가 맞는 문서는 유지된다.
            distance = 2.0 * (1.0 - (coverage * coverage))
            ranked.append((document, distance))
        ranked.sort(key=lambda item: item[1])
        return ranked[:k]
