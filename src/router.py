"""질의 재작성 + 의도 분류 — LLM 호출 한 번으로 처리한다.

팀 설계는 '재작성 → 분류'를 따로 두지만, 둘 다 짧은 JSON 출력이라
한 번의 호출로 합쳤다. 턴당 LLM 호출이 3회에서 2회로 줄어든다.
공용 API 키를 쓰므로 호출 수를 줄이는 쪽을 택했다.
"""
from __future__ import annotations
import json
from langchain_openai import ChatOpenAI
from .config import ROUTER_MODEL, ROUTER_MAX_TOKENS, MOCK, HISTORY_TURNS

INTENTS = ["메뉴질문", "추천", "옵션", "장바구니", "결제", "잡담", "범위밖"]

from .prompts import load as load_prompt

PROMPT = load_prompt("router")


def _llm():
    return ChatOpenAI(model=ROUTER_MODEL, temperature=0,
                      max_tokens=ROUTER_MAX_TOKENS)


def _mock(user_input: str) -> dict:
    return {"intent": "메뉴질문", "rewritten_query": user_input,
            "language": "en" if user_input.isascii() else "ko", "order_items": []}


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
    raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        out = json.loads(raw)
    except json.JSONDecodeError:
        return _mock(user_input)

    out.setdefault("intent", "메뉴질문")
    out.setdefault("rewritten_query", user_input)
    out.setdefault("language", "ko")
    out.setdefault("order_items", [])
    if out["intent"] not in INTENTS:
        out["intent"] = "메뉴질문"
    return out
