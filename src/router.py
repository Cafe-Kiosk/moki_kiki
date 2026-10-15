"""질의 재작성 + 의도 분류 — LLM 호출 한 번으로 처리한다.

팀 설계는 '재작성 → 분류'를 따로 두지만, 둘 다 짧은 JSON 출력이라
한 번의 호출로 합쳤다. 턴당 LLM 호출이 3회에서 2회로 줄어든다.
공용 API 키를 쓰므로 호출 수를 줄이는 쪽을 택했다.
"""
from __future__ import annotations
import json
from langchain_openai import ChatOpenAI
from .config import ROUTER_MODEL, ROUTER_MAX_TOKENS, MOCK, HISTORY_TURNS

INTENTS = ["메뉴질문", "추천", "예산추천", "옵션", "장바구니", "결제", "잡담", "범위밖"]

from .prompts import load as load_prompt

PROMPT = load_prompt("router")


def _llm():
    # JSON 모드 — 모델이 코드펜스나 설명 문장을 붙여 파싱이 깨지는 일을 막는다
    return ChatOpenAI(model=ROUTER_MODEL, temperature=0, max_tokens=ROUTER_MAX_TOKENS,
                      model_kwargs={"response_format": {"type": "json_object"}})


def _mock(user_input: str) -> dict:
    return {"intent": "메뉴질문", "rewritten_query": user_input,
            "language": "en" if user_input.isascii() else "ko", "order_items": [],
            "budget": None, "people": None, "wants": []}


def route(user_input: str, history: list[dict] | None = None) -> dict:
    if MOCK:
        return _mock(user_input)

    hist = ""
    if history:
        for m in history[-HISTORY_TURNS * 2:]:
            who = "손님" if m["role"] == "user" else "모키"
            hist += f"{who}: {m['content'][:120]}\n"

    raw = _llm().invoke(PROMPT.format(history=hist or "(없음)",
                                      user_input=user_input)).content.strip()
    return parse(raw, user_input)


def parse(raw: str, user_input: str) -> dict:
    """라우터 출력 JSON 을 검사한다. 실패를 조용히 삼키지 않고 errors 에 남긴다.

    파싱이 안 되면 메뉴질문으로 검색은 하되 담기·변경은 하지 않는다 (kiosk 가 calc 에 적는다).
    """
    raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        out = json.loads(raw)
        if not isinstance(out, dict):
            raise ValueError(f"객체가 아님: {type(out).__name__}")
    except (json.JSONDecodeError, ValueError) as e:
        fallback = _mock(user_input)
        fallback["errors"] = [f"JSON 파싱 실패: {e} · 원문 {raw[:80]!r}"]
        return fallback

    errors = []
    if out.get("intent") not in INTENTS:
        errors.append(f"알 수 없는 intent {out.get('intent')!r} → 메뉴질문")
        out["intent"] = "메뉴질문"
    items = out.get("order_items") or []
    if not isinstance(items, list):
        errors.append(f"order_items 가 목록이 아님: {type(items).__name__}")
        items = []
    good = [it for it in items if isinstance(it, dict) and it.get("menu_name")]
    if len(good) != len(items):
        errors.append(f"order_items {len(items) - len(good)}개 형식 오류로 제외")
    out["order_items"] = good
    out["errors"] = errors

    out.setdefault("rewritten_query", user_input)
    out.setdefault("language", "ko")
    out.setdefault("order_items", [])
    out.setdefault("budget", None)
    out.setdefault("people", None)
    out.setdefault("wants", [])
    return out
