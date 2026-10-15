"""검색 결과를 근거로 답변을 만든다. 같은 질문은 캐시에서 꺼내 쓴다."""
from __future__ import annotations
import json, hashlib
from langchain_openai import ChatOpenAI
from .config import (ANSWER_MODEL, ANSWER_MAX_TOKENS, CACHE_DIR,
                     ANSWER_CACHE, HISTORY_TURNS, current_api_key, is_mock)

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


def _cache_key(system: str, conversation: str) -> str:
    return hashlib.sha1((system + "||" + conversation).encode()).hexdigest()


def _conversation_messages(history: list[dict] | None) -> list[dict[str, str]]:
    """최근 대화를 모델의 실제 user/assistant 역할로 보존한다."""
    messages: list[dict[str, str]] = []
    for message in (history or [])[-HISTORY_TURNS * 2:]:
        role = "user" if message.get("role") == "user" else "assistant"
        content = str(message.get("content", "")).strip()
        if content:
            messages.append({"role": role, "content": content})
    return messages


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
                "tts": True,
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

    messages = [
        {"role": "system", "content": system},
        *_conversation_messages(history),
        {"role": "user", "content": user_input},
    ]

    if is_mock():
        return (
            "지금은 화면 체험 모드라 실제 AI 프롬프트로 답하고 있지 않아요. "
            "왼쪽 ‘API 연결’에 키를 적용하면 모키가 앞 대화를 기억하며 자연스럽게 이어갈게요.",
            True,
        )

    cache = _cache_load()
    conversation = json.dumps(messages[1:], ensure_ascii=False, separators=(",", ":"))
    key = _cache_key(system, conversation)
    if key in cache:
        return cache[key], True

    llm = ChatOpenAI(model=ANSWER_MODEL, temperature=0.3,
                     max_tokens=ANSWER_MAX_TOKENS, api_key=current_api_key())
    text = llm.invoke(messages).content.strip()
    cache[key] = text
    ANSWER_CACHE.write_text(json.dumps(cache, ensure_ascii=False))
    return text, False
