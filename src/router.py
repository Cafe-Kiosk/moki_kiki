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

PROMPT = """너는 커피바 '모키'의 주문 라우터다. 손님 말을 분석해 JSON만 출력한다.

intent 는 다음 중 하나다.
- 메뉴질문 : 메뉴·가격·성분·영양·원두에 대한 질문
- 추천     : 취향이나 상황을 말하며 골라 달라는 요청
- 옵션     : 샷·우유·원두·얼음·단맛·데우기 등 옵션 가능 여부나 추가금
- 장바구니 : 담기·수량 변경·빼기·장바구니 확인
- 결제     : 주문 확정, 결제, 주문번호
- 잡담     : 인사나 가벼운 말
- 범위밖   : 카페 주문과 관련 없는 요청

rewritten_query 는 검색에 쓸 문장이다.
- 줄임말과 지시어를 풀어 쓴다. "아아" → "아이스 아메리카노", "그거" → 직전에 말한 메뉴
- 취향 표현은 맛 조건으로 바꾼다. "임산부가 마실 거" → "카페인이 없거나 적은 음료"
- 여러 가지를 한꺼번에 물으면 핵심 두세 가지를 한 문장으로 모은다.

language 는 손님이 쓴 언어다. "ko" 또는 "en".

order_items 는 intent 가 장바구니일 때만 채운다. 아니면 빈 배열이다.
각 항목: {{"menu_name": "메뉴 이름", "temp": "HOT"|"ICED"|null, "size": "S"|"L"|"ONE"|null,
          "qty": 정수, "bean": "B01"|"B02"|"B03"|null, "extra_shots": 정수,
          "milk": "dairy"|"lowfat"|"oat"|"soy"|null, "sweetness": "normal"|"less"|null,
          "ice": "normal"|"less"|null, "warming": "room"|"warm"|null}}
손님이 말하지 않은 값은 null 로 둔다. 임의로 채우지 않는다.

출력 형식:
{{"intent":"...","rewritten_query":"...","language":"ko","order_items":[]}}

최근 대화:
{history}

손님: {user_input}"""


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
