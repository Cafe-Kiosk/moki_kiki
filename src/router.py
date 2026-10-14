"""기존 한 번의 라우터 호출을 유지하고 복합 행동·실제 주문 상태를 연결한다."""
from __future__ import annotations
import json
from functools import lru_cache
from typing import Literal
from pydantic import BaseModel, ConfigDict, StrictInt, ValidationError
from langchain_openai import ChatOpenAI
from .config import ROUTER_MODEL, ROUTER_MAX_TOKENS, MOCK, HISTORY_TURNS
from .cart import _tables, option_rules, find_variants
from .prompts import load as load_prompt

Intent = Literal["menu_info", "recommend", "option_check", "cart_add", "cart_update",
                 "cart_remove", "cart_view", "cart_clear", "order_review", "order_confirm",
                 "start_order", "reorder", "service_mode", "table_set", "language_set",
                 "status_check", "help", "out_of_scope", "undo"]

class Target(BaseModel):
    model_config = ConfigDict(extra="forbid")
    menu_name: str | None = None
    menu_id: str | None = None
    line_id: str | None = None
    temp: str | None = None
    size: str | None = None
    quantity: StrictInt | None = None
    bean: str | None = None
    extra_shots: StrictInt | None = None
    milk: str | None = None
    sweetness: str | None = None
    ice: str | None = None
    warming: str | None = None

class Action(BaseModel):
    model_config = ConfigDict(extra="forbid")
    intent: Intent
    targets: list[Target] = []
    quantity_mode: Literal["set", "increment", "decrement"] = "set"
    value: str | None = None

class Route(BaseModel):
    model_config = ConfigDict(extra="forbid")
    language: Literal["ko", "en"] = "ko"
    rewritten_query: str
    queries: list[str] = []
    actions: list[Action]
    avoid_allergens: list[str] | None = None
    max_caffeine_mg: StrictInt | None = None
    avoid_alcohol: bool | None = None
    budget_krw: StrictInt | None = None
    drink_count: StrictInt | None = None
    dessert_count: StrictInt | None = None
    needs_clarification: bool = False
    clarification_question: str | None = None

@lru_cache(maxsize=1)
def catalog():
    menus, _ = _tables()
    return [
        {"menu_id": mid, "name": m["메뉴명"], "english_name": m.get("영문명"),
         "aliases": m.get("별칭"), "variants": [v["주문 단위 ID"] for v in find_variants(mid)]}
        for mid, m in menus.items()
    ]

def validate_route(raw):
    if isinstance(raw, str):
        raw = json.loads(raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip())
    out = Route.model_validate(raw)
    if not out.actions or len(out.actions) > 12: raise ValueError("행동 수가 유효하지 않습니다.")
    if any(len(a.targets) > 20 for a in out.actions): raise ValueError("품목 수가 너무 많습니다.")
    return out.model_dump()

def route(user_input, history=None, state=None):
    state = state or {}
    lang = state.get("language", "ko")
    if MOCK:
        return Route(language=lang, rewritten_query=user_input, actions=[Action(intent="menu_info")]).model_dump()
    payload = {"user_message": user_input, "recent_history": (history or [])[-HISTORY_TURNS*2:],
               "session_state": state, "catalog": catalog(),
               "option_rules": {k: {"menus": r["적용 메뉴 ID"], "choices": r["선택값과 추가금"],
                                    "restriction": r["제한"]} for k, r in option_rules().items()}}
    raw = ChatOpenAI(model=ROUTER_MODEL, temperature=0,
                     max_tokens=ROUTER_MAX_TOKENS, timeout=45, max_retries=1,
                     model_kwargs={"response_format": {"type": "json_object"}}).invoke([
        {"role": "system", "content": load_prompt("router") + "\nJSON Schema:\n" + json.dumps(Route.model_json_schema(), ensure_ascii=False)},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]).content
    try: return validate_route(raw)
    except (ValueError, TypeError, ValidationError):
        return Route(language=lang, rewritten_query=user_input, actions=[Action(intent="help")],
                     needs_clarification=True, clarification_question="요청을 정확히 이해하지 못했습니다. 메뉴와 변경 내용을 다시 알려 주세요.").model_dump()
