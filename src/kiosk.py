"""전체 처리 흐름.

손님 입력 → 질의 재작성·의도 분류(LLM 1회) → 검색 또는 함수 호출 → 답변 생성(LLM 1회)
턴당 LLM 호출은 최대 2회이며, 범위 밖 질문은 검색을 건너뛴다.
"""
from __future__ import annotations
from dataclasses import dataclass, field

from .router import route
from .retrieve import hybrid_search, as_context, _alias_map
from .chain import answer
from .cart import (Cart, CartItem, resolve_variant, menu_by_id, find_variants,
                   validate_options, option_label, option_alternatives, is_alcohol,
                   OPTION_KEYS)


def _menu_candidates(text: str) -> list[str]:
    """이름에 걸리는 메뉴를 모두 돌려준다.

    "하이볼"처럼 여러 메뉴의 별칭에 걸리는 말은 하나로 확정하면 안 된다.
    확정은 손님에게 묻고 나서 한다 (검증질문 Q47).
    """
    t = str(text).lower()
    found = []
    for alias, mid in _alias_map():
        if alias in t and mid not in found:
            found.append(mid)
    if len(found) <= 1:
        return found
    # 메뉴명 전체가 들어있으면 그것으로 확정한다 ("위스키 하이볼 주세요")
    exact = [mid for mid in found
             if str(menu_by_id(mid)["메뉴명"]).lower() in t]
    return exact if len(exact) == 1 else found


def _add_one(it: dict, cart: Cart) -> str:
    """주문 항목 하나를 검증해 담고, 모델에게 넘길 계산 줄을 돌려준다."""
    name = it.get("menu_name", "")
    cands = _menu_candidates(name)
    if not cands:
        return f"'{name}' 은 메뉴에서 찾지 못했습니다."
    if len(cands) > 1:
        names = " 또는 ".join(str(menu_by_id(c)["메뉴명"]) for c in cands)
        return f"'{name}' 은 {names} 중 어느 것인지 확인이 필요합니다. 담지 않았습니다."
    mid = cands[0]
    m = menu_by_id(mid)
    v, all_v = resolve_variant(mid, it.get("temp"), it.get("size"))
    if v is None:
        opts = " / ".join(
            f"{x.get('온도')}·{x.get('크기')} {int(x['가격(원)']):,}원" for x in all_v)
        return f"{m['메뉴명']}: 구성을 하나 골라야 합니다 → {opts}"

    # 옵션 검증 — 하나라도 안 되면 그 품목은 담지 않는다. 대체도 하지 않는다 (P03).
    options = {k: it.get(k) for k in OPTION_KEYS}
    allowed, rejected = validate_options(mid, v, options)
    if rejected:
        bits = []
        for k, why in rejected:
            alt = option_alternatives(mid, k, options[k])
            bits.append(f"{option_label(k, options[k])} 불가 — {why}"
                        + (f" 대안: {' · '.join(alt)} (손님 확인 후 담기)" if alt else ""))
        return f"{m['메뉴명']}: 담지 않았습니다. " + " / ".join(bits)

    qty = int(it.get("qty") or 1)
    item = CartItem(
        menu_id=mid, variant_id=str(v["주문 단위 ID"]), name=str(m["메뉴명"]),
        temp=str(v.get("온도")), size=str(v.get("크기")), qty=qty,
        is_alcohol=is_alcohol(mid), **allowed)
    ok, err = cart.add(item)
    if not ok:
        return f"{m['메뉴명']}: {err}"
    return (f"{item.name} {item.temp}/{item.size}"
            + (f" ({item.option_text()})" if item.option_text() else "")
            + f" ×{qty} = {item.subtotal:,}원 "
              f"[기본 {item.base_price:,} + 옵션 {item.option_fee:,}]")


def apply_order_items(order_items: list[dict], cart: Cart) -> list[str]:
    """라우터의 order_items 를 장바구니에 반영한다. LLM 호출 없음."""
    lines = [_add_one(it, cart) for it in order_items]
    if cart.items:
        lines.append(f"현재 합계 {cart.total:,}원")
    if cart.status() == "pending_staff_check":
        lines.append("주류 포함 — 직원 나이 확인 전까지 확정 불가")
    return lines


@dataclass
class TurnResult:
    reply: str
    intent: str
    rewritten: str
    language: str
    docs: list = field(default_factory=list)
    trace: list = field(default_factory=list)
    calc: str = ""
    cached: bool = False
    llm_calls: int = 0


def handle(user_input: str, store, cart: Cart,
           history: list[dict] | None = None) -> TurnResult:
    history = history or []
    r = route(user_input, history)
    intent, rq, lang = r["intent"], r["rewritten_query"], r["language"]
    calls = 1

    # ── 범위 밖·잡담 : 검색을 건너뛴다 (비용 절약) ──────────
    if intent in ("범위밖", "잡담"):
        reply, cached = answer(user_input, "", history=history, offtopic=True)
        return TurnResult(reply, intent, rq, lang, cached=cached,
                          llm_calls=calls + (0 if cached else 1))

    # ── 결제 : 코드가 처리하고 모델을 부르지 않는다 ─────────
    if intent == "결제":
        from .retrieve import rule_hits
        _, pids = rule_hits(user_input)
        unsupported = ("P07" in pids)
        ok, msg = cart.confirm()
        if ok:
            reply = (f"주문을 확정했습니다. 주문번호는 {msg} 입니다.\n{cart.as_text()}\n"
                     "시연용 주문번호이며 실제 결제가 이루어지지는 않았습니다.")
        else:
            reply = msg
        if unsupported:
            reply = ("기프티콘·쿠폰·적립·분할 결제는 이 키오스크에서 지원하지 않습니다.\n"
                     + reply)
        return TurnResult(reply, intent, rq, lang, calc=cart.as_text(), llm_calls=calls)

    # ── 장바구니 담기 ──────────────────────────────────────
    calc_lines = []
    if intent == "장바구니" and r.get("order_items"):
        calc_lines = apply_order_items(r["order_items"], cart)

    # ── 검색 + 답변 ────────────────────────────────────────
    docs, trace = hybrid_search(store, rq)
    reply, cached = answer(user_input, as_context(docs),
                           calc="\n".join(calc_lines), history=history)
    return TurnResult(reply, intent, rq, lang, docs, trace,
                      "\n".join(calc_lines), cached, calls + (0 if cached else 1))
