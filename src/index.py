"""FAISS 인덱스 — 디스크에 저장해두고 재사용한다.

비용: 문서 61개 임베딩은 index/ 폴더에 한 번만 만들고 그 뒤로는 불러만 쓴다.
앱을 켤 때마다 다시 임베딩하면 그만큼 공용 키 크레딧이 나간다.
사용자 질문 임베딩도 캐시해서 같은 질문은 두 번 호출하지 않는다.
"""
from __future__ import annotations
import json, hashlib
from .config import DATA_XLSX
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
        key = hashlib.sha1((EMBED_MODEL + "||" + text.strip()).encode()).hexdigest()
        if key in self._cache:
            return self._cache[key]
        self.api_calls += 1
        vec = self.inner.embed_query(text)
        self._cache[key] = vec
        QUERY_EMBED_CACHE.write_text(json.dumps(self._cache))
        return vec


def get_embeddings() -> Embeddings:
    if MOCK: return _MockEmbeddings()
    return CachedEmbeddings(OpenAIEmbeddings(model=EMBED_MODEL))


def build_index(verbose: bool = True) -> FAISS:
    """문서를 임베딩해 인덱스를 만들고 디스크에 저장한다. API를 쓰는 유일한 지점."""
    docs = build_documents()
    emb = get_embeddings()
    store = FAISS.from_documents(docs, emb)
    INDEX_DIR.parent.mkdir(parents=True, exist_ok=True)
    if MOCK:
        return store
    store.save_local(str(INDEX_DIR))
    write_manifest(docs)
    if verbose:
        print(f"인덱스 생성: 문서 {len(docs)}개 → {INDEX_DIR}")
        print(f"임베딩 API 호출 {getattr(emb, 'api_calls', '?')}회")
    return store


def document_digest(docs):
    payload = [{"page_content": d.page_content, "metadata": d.metadata} for d in docs]
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

def write_manifest(docs):
    manifest = {"model": EMBED_MODEL, "documents": len(docs), "data_sha256": hashlib.sha256(DATA_XLSX.read_bytes()).hexdigest(),
                "document_digest": document_digest(docs),
                "files": {n: hashlib.sha256((INDEX_DIR / n).read_bytes()).hexdigest() for n in ("index.faiss", "index.pkl")}}
    (INDEX_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2))

def load_index():
    """저장 인덱스와 현재 데이터/문서의 일치를 검사한다. 자동 유료 재생성은 하지 않는다."""
    if MOCK:
        return FAISS.from_documents(build_documents(), _MockEmbeddings())
    path = INDEX_DIR / "manifest.json"
    if not path.exists(): raise ValueError("인덱스 검증 기록이 없습니다. python scripts/build_index.py를 실행해 주세요.")
    manifest = json.loads(path.read_text())
    if manifest["model"] != EMBED_MODEL or manifest["data_sha256"] != hashlib.sha256(DATA_XLSX.read_bytes()).hexdigest() or manifest["document_digest"] != document_digest(build_documents()):
        raise ValueError("데이터/문서/모델이 저장 인덱스와 다릅니다. 인덱스를 갱신해 주세요.")
    if set(manifest["files"]) != {"index.faiss", "index.pkl"}:
        raise ValueError("인덱스 파일 검증 목록이 올바르지 않습니다.")
    for name, digest in manifest["files"].items():
        if name not in ("index.faiss", "index.pkl") or hashlib.sha256((INDEX_DIR / name).read_bytes()).hexdigest() != digest:
            raise ValueError("저장 인덱스의 무결성 검사가 실패했습니다.")
    return FAISS.load_local(str(INDEX_DIR), get_embeddings(), allow_dangerous_deserialization=True)


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
