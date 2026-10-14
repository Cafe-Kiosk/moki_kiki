"""FAISS 인덱스 — 디스크에 저장해두고 재사용한다.

비용: 문서 61개 임베딩은 index/ 폴더에 한 번만 만들고 그 뒤로는 불러만 쓴다.
앱을 켤 때마다 다시 임베딩하면 그만큼 공용 키 크레딧이 나간다.
사용자 질문 임베딩도 캐시해서 같은 질문은 두 번 호출하지 않는다.
"""
from __future__ import annotations
import json, hashlib
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings
from langchain_core.embeddings import Embeddings

from .config import (EMBED_MODEL, INDEX_DIR, CACHE_DIR, QUERY_EMBED_CACHE,
                     MOCK, TOP_K, DISTANCE_THRESHOLD)
from .documents import build_documents


class _MockEmbeddings(Embeddings):
    """MOKI_MOCK=1 일 때 쓰는 가짜 임베딩. API를 부르지 않는다."""
    DIM = 256

    def _vec(self, text: str) -> list[float]:
        h = hashlib.sha256(text.encode()).digest()
        return [((h[i % len(h)] + i) % 97) / 97.0 for i in range(self.DIM)]

    def embed_documents(self, texts): return [self._vec(t) for t in texts]
    def embed_query(self, text):      return self._vec(text)


class CachedEmbeddings(Embeddings):
    """질문 임베딩을 디스크에 캐시한다. 같은 질문은 API를 다시 부르지 않는다."""

    def __init__(self, inner: Embeddings):
        self.inner = inner
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self._cache = {}
        if QUERY_EMBED_CACHE.exists():
            try:
                self._cache = json.loads(QUERY_EMBED_CACHE.read_text())
            except json.JSONDecodeError:
                self._cache = {}
        self.api_calls = 0

    def embed_documents(self, texts):
        self.api_calls += len(texts)
        return self.inner.embed_documents(texts)

    def embed_query(self, text):
        key = hashlib.sha1(text.strip().encode()).hexdigest()
        if key in self._cache:
            return self._cache[key]
        self.api_calls += 1
        vec = self.inner.embed_query(text)
        self._cache[key] = vec
        QUERY_EMBED_CACHE.write_text(json.dumps(self._cache))
        return vec


def get_embeddings() -> Embeddings:
    inner = _MockEmbeddings() if MOCK else OpenAIEmbeddings(model=EMBED_MODEL)
    return CachedEmbeddings(inner)


def build_index(verbose: bool = True) -> FAISS:
    """문서를 임베딩해 인덱스를 만들고 디스크에 저장한다. API를 쓰는 유일한 지점."""
    docs = build_documents()
    emb = get_embeddings()
    store = FAISS.from_documents(docs, emb)
    INDEX_DIR.parent.mkdir(parents=True, exist_ok=True)
    store.save_local(str(INDEX_DIR))
    if verbose:
        print(f"인덱스 생성: 문서 {len(docs)}개 → {INDEX_DIR}")
        print(f"임베딩 API 호출 {getattr(emb, 'api_calls', '?')}회")
    return store


def load_index() -> FAISS:
    """저장된 인덱스를 불러온다. 없으면 만든다."""
    emb = get_embeddings()
    if (INDEX_DIR / "index.faiss").exists():
        return FAISS.load_local(str(INDEX_DIR), emb,
                                allow_dangerous_deserialization=True)
    return build_index(verbose=False)


def search(store: FAISS, query: str, k: int = TOP_K,
           threshold: float = DISTANCE_THRESHOLD):
    """거리 기준값을 넘는(= 너무 먼) 문서는 버린다.

    개발팀 과제인 '유사도 점수 기준값 설정'이 이 부분이다.
    기준값을 넘으면 근거가 없다고 보고 모델이 지어내지 않도록 빈 목록을 준다.
    """
    hits = store.similarity_search_with_score(query, k=k)
    kept = [(d, s) for d, s in hits if s <= threshold]
    return kept, hits


if __name__ == "__main__":
    import sys
    store = build_index() if "--build" in sys.argv else load_index()
    for q in ["산미 적고 고소한 커피", "카페인 없는 거", "하이볼", "Is yakgwa gluten-free?"]:
        kept, raw = search(store, q)
        print(f"\n'{q}'")
        for d, s in raw:
            mark = "✓" if s <= DISTANCE_THRESHOLD else "✗"
            print(f"   {mark} {s:.3f}  {d.metadata['name']}")
