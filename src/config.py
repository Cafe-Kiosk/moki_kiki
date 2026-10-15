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
    if os.getenv("VERCEL"):
        return default
    try:                                   # 배포 환경에서만 있다
        import streamlit as st
        return str(st.secrets.get(name, default))
    except Exception:
        return default


def current_api_key() -> str:
    """브라우저 세션 입력을 우선하고, 환경변수·Secrets 순서로 키를 찾는다."""
    if os.getenv("VERCEL"):
        return os.getenv("OPENAI_API_KEY", "")
    try:
        import streamlit as st
        session_key = str(st.session_state.get("_openai_api_key", "")).strip()
        if session_key:
            return session_key
    except Exception:
        pass
    return _secret("OPENAI_API_KEY")


def ensure_api_key() -> bool:
    """브라우저 세션·환경변수·Secrets 중 API 키가 있는지 확인한다."""
    return bool(current_api_key())


def app_password() -> str:
    """비어 있으면 잠그지 않는다 (로컬 개발)."""
    return _secret("MOKI_PASSWORD")


def secret_status() -> dict:
    """화면에 표시할 진단 정보. 키 값 자체는 노출하지 않는다."""
    try:
        import streamlit as st
        session_key = str(st.session_state.get("_openai_api_key", "")).strip()
    except Exception:
        session_key = ""
    k = session_key or os.getenv("OPENAI_API_KEY") or _secret("OPENAI_API_KEY")
    pw = _secret("MOKI_PASSWORD")
    if session_key:
        src = "현재 세션"
    elif os.getenv("OPENAI_API_KEY"):
        src = "환경변수(.env)"
    else:
        src = "Secrets" if k else "없음"
    return {"key_found": bool(k), "key_head": (k[:7] + "...") if k else "",
            "key_source": src, "password_set": bool(pw)}

# ── 모델 (팀 합의: gpt-4.1-mini) ──────────────────────────────
ROUTER_MODEL = os.getenv("MOKI_ROUTER_MODEL", "gpt-4.1-mini")
ANSWER_MODEL = os.getenv("MOKI_ANSWER_MODEL", "gpt-4.1-mini")
EMBED_MODEL  = os.getenv("MOKI_EMBED_MODEL",  "text-embedding-3-small")

# ── 비용 제어 ────────────────────────────────────────────────
# 화면 작업 중에는 MOKI_MOCK=1 로 두면 API를 한 번도 호출하지 않는다.
MOCK = os.getenv("MOKI_MOCK", "0") == "1"


def is_mock() -> bool:
    """화면에서 선택한 실행 모드를 우선하고 기본값은 MOKI_MOCK를 따른다."""
    if os.getenv("VERCEL"):
        return MOCK
    try:
        import streamlit as st
        return bool(st.session_state.get("_use_mock", MOCK))
    except Exception:
        return MOCK

ANSWER_MAX_TOKENS = int(os.getenv("MOKI_ANSWER_MAX_TOKENS", "500"))
ROUTER_MAX_TOKENS = int(os.getenv("MOKI_ROUTER_MAX_TOKENS", "1200"))
HISTORY_TURNS     = int(os.getenv("MOKI_HISTORY_TURNS", "4"))   # 최근 N턴만 프롬프트에 넣음
OPENAI_TIMEOUT_SECONDS = float(os.getenv("MOKI_OPENAI_TIMEOUT_SECONDS", "15"))
OPENAI_MAX_RETRIES = int(os.getenv("MOKI_OPENAI_MAX_RETRIES", "1"))

# ── 검색 ─────────────────────────────────────────────────────
TOP_K = int(os.getenv("MOKI_TOP_K", "4"))
# FAISS 는 L2 거리를 돌려준다. 값이 작을수록 가깝다.
# 이 값보다 먼 문서는 근거로 쓰지 않는다 (개발팀 과제: 유사도 기준값 설정).
DISTANCE_THRESHOLD = float(os.getenv("MOKI_DISTANCE_THRESHOLD", "1.15"))

# ── 경로 ─────────────────────────────────────────────────────
DATA_XLSX   = ROOT / "data" / "moki_data.xlsx"
RAG_JSONL   = ROOT / "data" / "rag_documents.jsonl"
INDEX_DIR   = ROOT / "index" / "faiss"
CACHE_DIR   = (pathlib.Path("/tmp") / "moki_cache"
               if os.getenv("VERCEL") else ROOT / ".cache")
ANSWER_CACHE = CACHE_DIR / "answers.json"
QUERY_EMBED_CACHE = CACHE_DIR / "query_embeddings.json"

# ── 매장 설정 (매장정책 P02) ─────────────────────────────────
TABLES = list(range(1, 13))        # 좌석 1~12
MIN_QTY, MAX_QTY = 1, 10           # P11
