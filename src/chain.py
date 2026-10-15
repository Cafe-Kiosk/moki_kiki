"""검색 결과를 근거로 답변을 만든다. 같은 질문은 캐시에서 꺼내 쓴다."""
from __future__ import annotations
import json, hashlib
from langchain_openai import ChatOpenAI
from .config import (ANSWER_MODEL, ANSWER_MAX_TOKENS, MOCK, CACHE_DIR,
                     ANSWER_CACHE, HISTORY_TURNS)

from .prompts import load as load_prompt
from .few_shot import render_examples

SYSTEM = load_prompt("system")
OFFTOPIC = load_prompt("offtopic")


def _cache_load() -> dict:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if ANSWER_CACHE.exists():
        try:
            return json.loads(ANSWER_CACHE.read_text())
        except json.JSONDecodeError:
            pass
    return {}


def _cache_key(system: str, user: str) -> str:
    return hashlib.sha1((system + "||" + user).encode()).hexdigest()


def answer(user_input: str, context: str, calc: str = "",
           history: list[dict] | None = None, offtopic: bool = False,
           session_state: dict | None = None,
           capabilities: dict | None = None,
           plan: dict | None = None) -> tuple[str, bool]:
    """(답변, 캐시사용여부)를 돌려준다."""
    if offtopic:
        system = OFFTOPIC
    else:
        server_input = {
            "session_state": session_state or {},
            "retrieved_documents": context or "(없음)",
            "tool_results": calc or "(실행 결과 없음)",
            "capabilities": capabilities or {
                "tts": False,
                "text_input": True,
                "touch_input": True,
                "staff_call": False,
                "accessibility_controls": False,
            },
        }
        system = (
            SYSTEM
            + "\n\n[현재 요청에 맞춰 선별한 few-shot 예시]\n"
            + render_examples(user_input, plan, session_state)
            + "\n\n[서버가 검증해 제공한 현재 입력]\n"
            + json.dumps(server_input, ensure_ascii=False, default=str)
        )

    convo = ""
    if history:
        for m in history[-HISTORY_TURNS * 2:]:
            who = "손님" if m["role"] == "user" else "모키"
            convo += f"{who}: {m['content'][:150]}\n"
    user = (convo + "손님: " + user_input) if convo else user_input

    if MOCK:
        return f"[MOCK] {user_input} 에 대한 가짜 응답입니다. 검색 문서 {context.count('---') + 1}건.", True

    cache = _cache_load()
    key = _cache_key(system, user)
    if key in cache:
        return cache[key], True

    llm = ChatOpenAI(model=ANSWER_MODEL, temperature=0.3, max_tokens=ANSWER_MAX_TOKENS)
    text = llm.invoke([{"role": "system", "content": system},
                       {"role": "user", "content": user}]).content.strip()
    cache[key] = text
    ANSWER_CACHE.write_text(json.dumps(cache, ensure_ascii=False))
    return text, False
