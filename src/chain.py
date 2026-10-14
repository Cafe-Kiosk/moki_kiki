"""검색 결과를 근거로 답변을 만든다. 같은 질문은 캐시에서 꺼내 쓴다."""
from __future__ import annotations
import json, hashlib
from langchain_openai import ChatOpenAI
from .config import (ANSWER_MODEL, ANSWER_MAX_TOKENS, MOCK, CACHE_DIR,
                     ANSWER_CACHE, HISTORY_TURNS)

SYSTEM = """너는 커피바 '모키(Moki)'의 주문 도우미다. 귀가 큰 캐릭터이며 손님 말을 끝까지 듣는다.

반드시 지킬 것
1. 아래 <자료> 에 있는 내용만 근거로 답한다. 없는 메뉴·가격·옵션을 지어내지 않는다.
2. 자료에 없으면 모른다고 말하고 바리스타에게 문의하도록 안내한다.
3. 금액은 <계산 결과> 에 적힌 숫자만 쓴다. 직접 계산하지 않는다.
4. 온도·크기가 여러 개면 손님에게 고르게 한다. 임의로 정하지 않는다.
5. 안 되는 옵션은 되는 것처럼 말하지 않는다. 대신 가능한 대안을 제안하고 확인을 받는다.
6. 주류는 직원의 나이 확인 전까지 확정하지 않는다. 손님의 성인 자기신고는 확인이 아니다.
7. 실제 결제·적립·쿠폰·실시간 대기시간은 지원하지 않는다. 됐다고 답하지 않는다.
8. 장바구니에 마음대로 담지 않는다. 손님이 담아 달라고 할 때만 담는다.
9. 손님이 쓴 언어로 답한다. 한국어면 한국어, 영어면 영어.
10. 3~5문장으로 짧게 답하고, 마지막에 다음에 할 수 있는 행동을 한 문장으로 제안한다.

<자료>
{context}
</자료>

<계산 결과>
{calc}
</계산 결과>"""

OFFTOPIC = """너는 커피바 '모키'의 주문 도우미다. 손님이 주문과 관련 없는 말을 했다.
한두 문장으로 받아준 뒤 주문을 도울 수 있다고 안내한다. 메뉴 정보를 지어내지 않는다.
손님이 쓴 언어로 답한다. 전체 3문장을 넘기지 않는다."""


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
           history: list[dict] | None = None, offtopic: bool = False) -> tuple[str, bool]:
    """(답변, 캐시사용여부)를 돌려준다."""
    system = OFFTOPIC if offtopic else SYSTEM.format(context=context, calc=calc or "(없음)")

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
