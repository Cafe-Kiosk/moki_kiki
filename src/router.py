"""질의 재작성과 의도/실행계획 생성.

프롬프트팀 산출물의 두 단계 계약을 그대로 사용한다.
  1. rewrite: 검색 질의와 미해결 지시어 생성
  2. classify: 검색 문서를 참고해 구조화된 actions 생성

실제 상태 변경 권한은 이 모듈에 없다. 계획은 kiosk.py의 검증 코드가 실행한다.
"""
from __future__ import annotations

import json
from typing import Any

from jsonschema import ValidationError, validate
from langchain_openai import ChatOpenAI

from .config import (ROUTER_MODEL, ROUTER_MAX_TOKENS, HISTORY_TURNS,
                     OPENAI_TIMEOUT_SECONDS, OPENAI_MAX_RETRIES,
                     current_api_key, is_mock)
from .prompts import load as load_prompt, load_schema

REWRITE_PROMPT = load_prompt("rewrite")
INTENT_PROMPT = load_prompt("intent")
REWRITE_SCHEMA = load_schema("rewrite")
INTENT_SCHEMA = load_schema("intent")


def _llm():
    return ChatOpenAI(
        model=ROUTER_MODEL,
        temperature=0,
        max_tokens=ROUTER_MAX_TOKENS,
        api_key=current_api_key(),
        timeout=OPENAI_TIMEOUT_SECONDS,
        max_retries=OPENAI_MAX_RETRIES,
    )


def _language(text: str) -> str:
    if any("\u3040" <= c <= "\u30ff" for c in text):
        return "ja"
    if any("\u4e00" <= c <= "\u9fff" for c in text):
        return "zh"
    letters = [c for c in text if c.isalpha()]
    return "en" if letters and all(ord(c) < 128 for c in letters) else "ko"


def _history_summary(history: list[dict] | None) -> str:
    if not history:
        return "(없음)"
    lines = []
    for message in history[-HISTORY_TURNS * 2:]:
        who = "user" if message.get("role") == "user" else "assistant"
        lines.append(f"{who}: {str(message.get('content', ''))[:180]}")
    return "\n".join(lines)


def _history_messages(history: list[dict] | None) -> list[dict[str, str]]:
    """재작성·의도 분류에도 최근 대화의 역할과 충분한 문맥을 보존한다."""
    return [
        {
            "role": "user" if message.get("role") == "user" else "assistant",
            "content": str(message.get("content", ""))[:1200],
        }
        for message in (history or [])[-HISTORY_TURNS * 2:]
        if str(message.get("content", "")).strip()
    ]


def _parse_json(content: Any) -> dict:
    if isinstance(content, dict):
        return content
    text = str(content).strip()
    text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(text)


def _invoke(prompt: str, payload: dict, schema: dict) -> dict:
    schema_text = json.dumps(schema, ensure_ascii=False)
    payload_text = json.dumps(payload, ensure_ascii=False, default=str)
    response = _llm().invoke([
        {"role": "system", "content": prompt},
        {
            "role": "user",
            "content": (
                "다음 입력을 처리하고 JSON만 출력하세요.\n"
                f"입력:\n{payload_text}\n\n"
                f"반드시 따를 JSON Schema:\n{schema_text}"
            ),
        },
    ])
    parsed = _parse_json(response.content)
    validate(instance=parsed, schema=schema)
    return parsed


def _mock_rewrite(user_input: str) -> dict:
    return {
        "schema_version": "1.0",
        "language": _language(user_input),
        "rewritten_utterance": user_input,
        "queries": [{"query": user_input, "document_types": [], "menu_ids": []}],
        "resolved": True,
        "unresolved_references": [],
    }


def _empty_options() -> dict:
    return {key: None for key in (
        "bean", "extra_shots", "milk", "sweetness", "ice", "warming"
    )}


def _mock_plan(user_input: str, rewrite_result: dict) -> dict:
    lower = user_input.lower()
    if any(word in lower for word in ("확정", "결제", "checkout", "confirm")):
        intent = "order_confirm"
    elif any(word in lower for word in ("담아", "추가", "빼", "장바구니", "cart")):
        intent = "cart_view"
    elif any(word in lower for word in ("추천", "recommend")):
        intent = "recommend"
    else:
        intent = "menu_info"
    return {
        "schema_version": "1.0",
        "language": rewrite_result["language"],
        "actions": [{
            "action_id": "mock-1",
            "intent": intent,
            "hti_ids": [],
            "targets": [],
            "constraints": [],
            "quantity_mode": "none",
            "requires_tool": intent in {"order_confirm", "cart_view"},
            "mutates_state": intent == "order_confirm",
            "blocked_reason": None,
        }],
        "needs_retrieval": intent not in {"order_confirm", "cart_view"},
        "needs_clarification": False,
        "clarification_question": None,
        "safety_flags": [],
        "preserve_state": True,
    }


def rewrite(user_input: str, history: list[dict] | None = None,
            session_state: dict | None = None) -> dict:
    if is_mock():
        return _mock_rewrite(user_input)
    payload = {
        "user_message": user_input,
        "conversation_summary": _history_summary(history),
        "conversation_history": _history_messages(history),
        "session_state": session_state or {},
    }
    try:
        return _invoke(REWRITE_PROMPT, payload, REWRITE_SCHEMA)
    except (json.JSONDecodeError, ValidationError, TypeError, ValueError):
        return _mock_rewrite(user_input)


def classify(user_input: str, rewrite_result: dict, retrieved_documents: str,
             history: list[dict] | None = None,
             session_state: dict | None = None,
             catalog_aliases: list[tuple[str, str]] | None = None) -> dict:
    if is_mock():
        return _mock_plan(user_input, rewrite_result)
    payload = {
        "user_message": user_input,
        "rewrite_result": rewrite_result,
        "conversation_summary": _history_summary(history),
        "conversation_history": _history_messages(history),
        "session_state": session_state or {},
        "catalog_aliases": catalog_aliases or [],
        "retrieved_documents": retrieved_documents,
    }
    try:
        return _invoke(INTENT_PROMPT, payload, INTENT_SCHEMA)
    except (json.JSONDecodeError, ValidationError, TypeError, ValueError):
        return _mock_plan(user_input, rewrite_result)


def adapt_plan(user_input: str, rewrite_result: dict, plan: dict) -> dict:
    """새 actions 계약을 기존 키오스크 실행 코드가 읽는 형태로 변환한다."""
    actions = plan.get("actions") or []
    intents = [action.get("intent") for action in actions]

    if "order_confirm" in intents:
        legacy_intent = "결제"
    elif any(i in {"cart_add", "cart_update", "cart_remove", "cart_view", "cart_clear"}
             for i in intents):
        legacy_intent = "장바구니"
    elif "recommend" in intents:
        legacy_intent = "추천"
    elif "option_check" in intents:
        legacy_intent = "옵션"
    elif any(i in {"out_of_scope", "unsafe_request", "injection_attempt"} for i in intents):
        legacy_intent = "범위밖"
    elif any(i in {"start_order", "help", "accessibility", "language_set"} for i in intents):
        legacy_intent = "잡담"
    else:
        legacy_intent = "메뉴질문"

    order_items = []
    if not plan.get("needs_clarification"):
        for action in actions:
            if action.get("intent") != "cart_add" or action.get("blocked_reason"):
                continue
            for target in action.get("targets") or []:
                options = {**_empty_options(), **(target.get("options") or {})}
                order_items.append({
                    "menu_id": target.get("menu_id"),
                    "menu_name": target.get("menu_id") or "",
                    "variant_id": target.get("variant_id"),
                    "temp": None,
                    "size": None,
                    "qty": target.get("quantity"),
                    **options,
                })

    return {
        "intent": legacy_intent,
        "rewritten_query": rewrite_result.get("rewritten_utterance", user_input),
        "language": plan.get("language", rewrite_result.get("language", "ko")),
        "order_items": order_items,
        "rewrite_result": rewrite_result,
        "plan": plan,
    }


def route(user_input: str, history: list[dict] | None = None,
          retrieved_documents: str = "", session_state: dict | None = None,
          catalog_aliases: list[tuple[str, str]] | None = None) -> dict:
    """호환용 진입점. kiosk는 검색을 사이에 넣기 위해 두 함수를 따로 호출한다."""
    rewritten = rewrite(user_input, history, session_state)
    plan = classify(user_input, rewritten, retrieved_documents, history,
                    session_state, catalog_aliases)
    return adapt_plan(user_input, rewritten, plan)
