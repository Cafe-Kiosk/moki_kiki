"""검색 결과를 근거로 답변을 만든다. 같은 질문은 캐시에서 꺼내 쓴다."""
from __future__ import annotations
import json, hashlib
from langchain_openai import ChatOpenAI
from .config import (ANSWER_MODEL, ANSWER_MAX_TOKENS, ANSWER_TEMPERATURE, MOCK, CACHE_DIR,
                     ANSWER_CACHE, HISTORY_TURNS)

from .prompts import load as load_prompt

SYSTEM = load_prompt("system")
OFFTOPIC = load_prompt("offtopic")
INFO_RULES = load_prompt("info_rules")    # 정보·정책 질문에서만 덧붙인다


def offtopic_prompt(lang: str = "ko") -> str:
    """범위밖 경로 프롬프트. 영어 손님이면 영어로만 답하라는 줄을 덧붙인다 (Q40·Q42: 한국어가 섞이던 문제)."""
    return OFFTOPIC + ("\n\nThe customer wrote in English. Reply only in English." if lang == "en" else "")


def system_prompt(context: str, calc: str = "", info: bool = False) -> str:
    """주문 흐름용 system.md. info=True(메뉴질문·추천·옵션)면 <자료> 앞에 정보·정책 규칙을 넣는다."""
    s = SYSTEM.format(context=context, calc=calc or "(없음)")
    return s.replace("\n<자료>\n", "\n" + INFO_RULES + "\n\n<자료>\n", 1) if info else s   # 자료 블록 앞

# 앱은 캐시를 쓴다 (시연 리허설 답변 고정). 검증 스크립트는 기본으로 끈다 (run_checks --use-cache).
USE_CACHE = True


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
           info: bool = False, lang: str = "ko") -> tuple[str, bool]:
    """(답변, 캐시사용여부)를 돌려준다."""
    system = offtopic_prompt(lang) if offtopic else system_prompt(context, calc, info)

    convo = ""
    if history:
        for m in history[-HISTORY_TURNS * 2:]:
            who = "손님" if m["role"] == "user" else "모키"
            convo += f"{who}: {m['content'][:150]}\n"
    user = (convo + "손님: " + user_input) if convo else user_input

    if MOCK:
        return f"[MOCK] {user_input} 에 대한 가짜 응답입니다. 검색 문서 {context.count('---') + 1}건.", True

    cache = _cache_load() if USE_CACHE else {}
    key = _cache_key(system, user)
    if key in cache:
        return cache[key], True

    llm = ChatOpenAI(model=ANSWER_MODEL, temperature=ANSWER_TEMPERATURE, max_tokens=ANSWER_MAX_TOKENS)
    text = llm.invoke([{"role": "system", "content": system},
                       {"role": "user", "content": user}]).content.strip()
    if USE_CACHE:
        cache[key] = text
        ANSWER_CACHE.write_text(json.dumps(cache, ensure_ascii=False))
    return text, False
