"""팀 시스템 규칙에 실제 검색 근거·서버 상태를 구분해 전달한다."""
from __future__ import annotations
import hashlib, json
from collections import OrderedDict
from langchain_openai import ChatOpenAI
from .config import ANSWER_MODEL, ANSWER_MAX_TOKENS, MOCK, HISTORY_TURNS
from .prompts import load as load_prompt
from .cart import _tables

_CACHE = OrderedDict()

def answer(user_input, context, calc="", history=None, offtopic=False, state=None):
    system = load_prompt("system")
    system += "\n화면에는 읽어주기·글자크기 설정이 있지만 채팅 도구로 실행하지 못한다. 사용자가 직접 버튼을 누르도록 안내하고 실행했다고 말하지 않는다. 직원 호출·실제 결제는 미지원, 주류는 직원 확인 대기만 지원한다."
    system += "\n고객에게 메뉴 ID(M03 등)·내부 옵션 코드(normal 등)를 노출하지 말고 메뉴 이름과 쉬운 표현을 쓴다. 서버 견적이 있으면 기본값 대신 선택 옵션 적용 결과를 따른다.\n"
    system += "\n서버가 준 전체 판매 목록에 없는 상품을 담아줄 수 있다고 제안하지 않는다. 추천 질문에는 실제 후보와 근거를 바로 답하고 확인 중이라는 말로 끝내지 않는다.\n"
    if (state or {}).get("language") == "en": system += "\nRespond only in English. Translate menu explanations and all questions into English.\n"
    if offtopic: system += "\n카페와 무관한 요청은 짧게 응대하고 메뉴·주문으로 안내한다."
    payload = {"user_message": user_input, "retrieved_documents": context,
               "tool_results": calc or "이번 요청에서 실행한 쓰기 도구 없음. 주문 완료를 주장하지 않는다.",
               "session_state": state or {}, "capabilities": {"tts":False,"font_resize":False,"staff_call":False,"real_payment":False,"demo_order":True}, "available_menu_names": [{"name":m["메뉴명"],"english_name":m.get("영문명")} for m in _tables()[0].values()]}
    messages = [{"role": "system", "content": system}]
    messages += (history or [])[-HISTORY_TURNS*2:]
    messages.append({"role": "user", "content": json.dumps(payload, ensure_ascii=False)})
    if MOCK: return "[화면 시험용 가짜 응답] " + user_input, True
    key = hashlib.sha256((ANSWER_MODEL + json.dumps(messages, ensure_ascii=False)).encode()).hexdigest()
    if key in _CACHE:
        _CACHE.move_to_end(key); return _CACHE[key], True
    text = ChatOpenAI(model=ANSWER_MODEL, temperature=0, max_tokens=ANSWER_MAX_TOKENS,
                      timeout=45, max_retries=1).invoke(messages).content.strip()
    _CACHE[key] = text
    if len(_CACHE) > 128: _CACHE.popitem(last=False)
    return text, False
