"""모키 키오스크 전역 설정.

비용 관련 설정이 한곳에 모여 있다. 조교님 공용 API 키를 쓰므로
호출 횟수와 토큰을 줄이는 값이 기본값이다.
"""
from __future__ import annotations
import os, pathlib
from dotenv import load_dotenv

ROOT = pathlib.Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _secret(name: str, default: str = "") -> str:
    """로컬은 .env, Streamlit Cloud 는 시크릿에서 읽는다."""
    v = os.getenv(name)
    if v:
        return v
    try:                                   # 배포 환경에서만 있다
        import streamlit as st
        return str(st.secrets.get(name, default))
    except Exception:
        return default


def ensure_api_key() -> bool:
    """시크릿·환경변수에서 키를 찾아 환경변수에 넣는다. 호출할 때마다 확인한다.

    import 시점에 한 번만 읽으면, 배포 후에 시크릿을 추가했을 때
    프로세스가 옛 값을 들고 있어 반영되지 않는다.
    """
    if os.getenv("OPENAI_API_KEY"):
        return True
    k = _secret("OPENAI_API_KEY")
    if k:
        os.environ["OPENAI_API_KEY"] = k
        return True
    return False


def app_password() -> str:
    """비어 있으면 잠그지 않는다 (로컬 개발)."""
    return _secret("MOKI_PASSWORD")


def secret_status() -> dict:
    """화면에 표시할 진단 정보. 키 값 자체는 노출하지 않는다."""
    k = os.getenv("OPENAI_API_KEY") or _secret("OPENAI_API_KEY")
    pw = _secret("MOKI_PASSWORD")
    src = "환경변수(.env)" if os.getenv("OPENAI_API_KEY") else ("시크릿" if k else "없음")
    return {"key_found": bool(k), "key_head": (k[:7] + "...") if k else "",
            "key_source": src, "password_set": bool(pw)}

# ── 모델 (팀 합의: gpt-4.1-mini) ──────────────────────────────
ROUTER_MODEL = os.getenv("MOKI_ROUTER_MODEL", "gpt-4.1-mini")
ANSWER_MODEL = os.getenv("MOKI_ANSWER_MODEL", "gpt-4.1-mini")
EMBED_MODEL  = os.getenv("MOKI_EMBED_MODEL",  "text-embedding-3-small")

# ── 비용 제어 ────────────────────────────────────────────────
# 화면 작업 중에는 MOKI_MOCK=1 로 두면 API를 한 번도 호출하지 않는다.
MOCK = os.getenv("MOKI_MOCK", "0") == "1"

ANSWER_MAX_TOKENS = int(os.getenv("MOKI_ANSWER_MAX_TOKENS", "500"))
ROUTER_MAX_TOKENS = int(os.getenv("MOKI_ROUTER_MAX_TOKENS", "1200"))
HISTORY_TURNS     = int(os.getenv("MOKI_HISTORY_TURNS", "4"))   # 최근 N턴만 프롬프트에 넣음

# ── 검색 ─────────────────────────────────────────────────────
TOP_K = int(os.getenv("MOKI_TOP_K", "4"))
# FAISS 는 L2 거리를 돌려준다. 값이 작을수록 가깝다.
# 이 값보다 먼 문서는 근거로 쓰지 않는다 (개발팀 과제: 유사도 기준값 설정).
DISTANCE_THRESHOLD = float(os.getenv("MOKI_DISTANCE_THRESHOLD", "1.15"))

# ── 경로 ─────────────────────────────────────────────────────
DATA_XLSX   = ROOT / "data" / "moki_data.xlsx"
RAG_JSONL   = ROOT / "data" / "rag_documents.jsonl"
INDEX_DIR   = ROOT / "index" / "faiss"
CACHE_DIR   = ROOT / ".cache"
ANSWER_CACHE = CACHE_DIR / "answers.json"
QUERY_EMBED_CACHE = CACHE_DIR / "query_embeddings.json"

# ── 매장 설정 (매장정책 P02) ─────────────────────────────────
TABLES = list(range(1, 13))        # 좌석 1~12
MIN_QTY, MAX_QTY = 1, 10           # P11
