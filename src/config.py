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


# Streamlit Cloud 시크릿에 키가 있으면 환경변수로 옮겨 둔다
if not os.getenv("OPENAI_API_KEY"):
    _k = _secret("OPENAI_API_KEY")
    if _k:
        os.environ["OPENAI_API_KEY"] = _k

APP_PASSWORD = _secret("MOKI_PASSWORD")    # 비어 있으면 잠그지 않는다

# ── 모델 (팀 합의: gpt-4.1-mini) ──────────────────────────────
ROUTER_MODEL = os.getenv("MOKI_ROUTER_MODEL", "gpt-4.1-mini")
ANSWER_MODEL = os.getenv("MOKI_ANSWER_MODEL", "gpt-4.1-mini")
EMBED_MODEL  = os.getenv("MOKI_EMBED_MODEL",  "text-embedding-3-small")

# ── 비용 제어 ────────────────────────────────────────────────
# 화면 작업 중에는 MOKI_MOCK=1 로 두면 API를 한 번도 호출하지 않는다.
MOCK = os.getenv("MOKI_MOCK", "0") == "1"

ANSWER_MAX_TOKENS = int(os.getenv("MOKI_ANSWER_MAX_TOKENS", "500"))
ROUTER_MAX_TOKENS = int(os.getenv("MOKI_ROUTER_MAX_TOKENS", "400"))
HISTORY_TURNS     = int(os.getenv("MOKI_HISTORY_TURNS", "4"))   # 최근 N턴만 프롬프트에 넣음

# ── 검색 ─────────────────────────────────────────────────────
TOP_K = int(os.getenv("MOKI_TOP_K", "4"))
# FAISS 는 L2 거리를 돌려준다. 값이 작을수록 가깝다.
# 이 값보다 먼 문서는 근거로 쓰지 않는다 (개발팀 과제: 유사도 기준값 설정).
DISTANCE_THRESHOLD = float(os.getenv("MOKI_DISTANCE_THRESHOLD", "1.15"))

# ── 경로 ─────────────────────────────────────────────────────
DATA_XLSX   = ROOT / "data" / "moki_data.xlsx"
INDEX_DIR   = ROOT / "index" / "faiss"
CACHE_DIR   = ROOT / ".cache"
ANSWER_CACHE = CACHE_DIR / "answers.json"
QUERY_EMBED_CACHE = CACHE_DIR / "query_embeddings.json"

# ── 매장 설정 (매장정책 P02) ─────────────────────────────────
TABLES = list(range(1, 13))        # 좌석 1~12
MIN_QTY, MAX_QTY = 1, 10           # P11
