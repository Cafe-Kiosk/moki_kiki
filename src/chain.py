"""검색 결과를 근거로 답변을 만든다. 같은 질문은 캐시에서 꺼내 쓴다."""
from __future__ import annotations
import json, hashlib
from langchain_openai import ChatOpenAI
from .config import (ANSWER_MODEL, ANSWER_MAX_TOKENS, CACHE_DIR,
                     ANSWER_CACHE, HISTORY_TURNS, OPENAI_TIMEOUT_SECONDS,
                     OPENAI_MAX_RETRIES, current_api_key, current_language,
                     is_mock)

from .prompts import load as load_prompt
from .few_shot import render_examples

SYSTEM = load_prompt("system")
OFFTOPIC = load_prompt("offtopic")

DEFAULT_CAPABILITIES = {
    "tts": True,
    "text_input": True,
    "touch_input": True,
    "staff_call": False,
    "language_selector": True,
    "accessibility_controls": True,
    "easy_view": True,
    "menu_image_display": True,
    "menu_images_attached": False,
    "menu_image_menu_ids": [],
    "menu_option_selector": True,
    "option_selector": True,
    "live_cart_updates": True,
    "conversational_table_change": True,
    "staff_purchase_verification": True,
    "simulated_checkout": True,
    "real_payment": False,
    "customer_account_lookup": False,
}


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
    history_messages = _conversation_messages(history)
    effective_capabilities = {
        **DEFAULT_CAPABILITIES,
        **(capabilities or {}),
    }
    if offtopic:
        system = (
            OFFTOPIC
            + "\n\n화면에서 선택한 preferred_language로 답하세요. "
              "고객이 이번 발화에서 언어 변경을 명시한 경우에만 그 요청을 우선하세요."
            + "\n\n[서버가 검증해 제공한 현재 입력]\n"
            + json.dumps({
                "preferred_language": current_language(),
                "conversation_history": history_messages,
                "session_state": session_state or {},
                "capabilities": effective_capabilities,
            }, ensure_ascii=False, default=str)
        )
    else:
        server_input = {
            "user_message": user_input,
            "preferred_language": current_language(),
            "conversation_history": history_messages,
            "session_state": session_state or {},
            "retrieved_documents": context or "(없음)",
            "tool_results": calc or "(실행 결과 없음)",
            "capabilities": effective_capabilities,
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
        *history_messages,
        {"role": "user", "content": user_input},
    ]

    if is_mock():
        notices = {
            "ko": ("지금은 화면 체험 모드라 실제 AI 프롬프트로 답하고 있지 않아요. "
                   "OPENAI_API_KEY를 실행 환경에 연결하고 체험 모드를 끄면 "
                   "모키가 앞 대화를 기억하며 자연스럽게 이어갈게요."),
            "en": ("This is UI demo mode, so the live AI prompt is not running. "
                   "Connect OPENAI_API_KEY and turn off demo mode for a contextual conversation."),
            "zh": ("目前是界面演示模式，尚未运行真实 AI 提示词。连接 OPENAI_API_KEY "
                   "并关闭演示模式后，Moki 就能根据对话上下文自然回复。"),
            "ja": ("現在は画面デモモードのため、実際のAIプロンプトは動作していません。"
                   "OPENAI_API_KEYを接続してデモモードを解除すると、会話の流れに沿って応答します。"),
        }
        return notices[current_language()], True

    cache = _cache_load()
    conversation = json.dumps(messages[1:], ensure_ascii=False, separators=(",", ":"))
    key = _cache_key(system, conversation)
    if key in cache:
        return cache[key], True

    llm = ChatOpenAI(
        model=ANSWER_MODEL,
        temperature=0.3,
        max_tokens=ANSWER_MAX_TOKENS,
        api_key=current_api_key(),
        timeout=OPENAI_TIMEOUT_SECONDS,
        max_retries=OPENAI_MAX_RETRIES,
    )
    text = llm.invoke(messages).content.strip()
    cache[key] = text
    ANSWER_CACHE.write_text(json.dumps(cache, ensure_ascii=False))
    return text, False
