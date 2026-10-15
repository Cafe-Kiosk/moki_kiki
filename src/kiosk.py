"""전체 처리 흐름.

손님 입력 → 질의 재작성·의도 분류(LLM 1회) → 검색 또는 함수 호출 → 답변 생성(LLM 1회)
턴당 LLM 호출은 최대 2회이며, 범위 밖 질문은 검색을 건너뛴다.
"""
from __future__ import annotations
from dataclasses import dataclass, field

from .router import route
from .retrieve import hybrid_search, as_context, match_menus, alias_hits
from .chain import answer
from .cart import (Cart, CartItem, resolve_variant, menu_by_id, find_variants,
                   validate_options, option_label, option_alternatives, is_alcohol,
                   OPTION_KEYS, valid_qty, QTY_MSG)
from .conditions import screen, alternatives_line, added_item_caution, decaf_notes


def _menu_candidates(text: str) -> tuple[list[str], dict]:
    """이름에 걸리는 메뉴와, 별칭이 정해 주는 속성(온도·원두)을 돌려준다.

    긴 별칭부터 맞춘다 ('바닐라라떼'는 바닐라 라떼 하나). 그래도 둘 이상이면
    '하이볼'처럼 진짜 모호한 것이므로 확정하지 않고 손님에게 묻는다 (Q47).
    """
    ids, attrs = match_menus(text)
    return [i for i in ids if menu_by_id(i)], attrs


def _add_one(it: dict, cart: Cart, blocked: set[str] = frozenset()) -> str:
    """주문 항목 하나를 검증해 담고, 모델에게 넘길 계산 줄을 돌려준다.

    blocked 는 손님 조건과 충돌한 메뉴다. 담지 않고 온도·크기도 묻지 않는다 (Q08).
    """
    name = it.get("menu_name", "")
    cands, alias_attrs = _menu_candidates(name)
    if not cands:
        return f"'{name}' 은 메뉴에서 찾지 못했습니다."
    if len(cands) > 1:
        names = " 또는 ".join(str(menu_by_id(c)["메뉴명"]) for c in cands)
        return f"'{name}' 은 {names} 중 어느 것인지 확인이 필요합니다. 담지 않았습니다."
    mid = cands[0]
    m = menu_by_id(mid)
    if mid in blocked:
        return f"{m['메뉴명']}: 담지 않았습니다 (조건충돌)."
    # 수량이 없을 때만 1잔. 0·음수·비정수는 고치지 않고 검증에서 거부한다 (Q14·P11)
    # 온도·크기를 묻기 전에 본다. 0잔을 두고 구성부터 고르게 하지 않는다.
    qty = it.get("qty")
    if qty is None:
        qty = 1
    if not valid_qty(qty):
        return f"{m['메뉴명']}: 담지 않았습니다. 요청 수량 {qty!r} — {QTY_MSG}"
    # 라우터가 null 로 준 값은 별칭이 정해 주는 값으로 채운다 ('아아' → ICED)
    temp = it.get("temp") or alias_attrs.get("temp")
    v, all_v = resolve_variant(mid, temp, it.get("size"))
    if v is None:
        opts = " / ".join(
            f"{x.get('온도')}·{x.get('크기')} {int(x['가격(원)']):,}원" for x in all_v)
        return f"{m['메뉴명']}: 구성을 하나 골라야 합니다 → {opts}"

    # 옵션 검증 — 하나라도 안 되면 그 품목은 담지 않는다. 대체도 하지 않는다 (P03).
    options = {k: it.get(k) for k in OPTION_KEYS}
    if options["bean"] is None and alias_attrs.get("bean"):
        options["bean"] = alias_attrs["bean"]          # '디카페인 카페라떼' → B03
    allowed, rejected = validate_options(mid, v, options)
    if rejected:
        bits = []
        for k, why in rejected:
            alt = option_alternatives(mid, k, options[k])
            bits.append(f"{option_label(k, options[k])} 불가 — {why}"
                        + (f" 대안: {' · '.join(alt)} (손님 확인 후 담기)" if alt else ""))
        line = f"{m['메뉴명']}: 담지 않았습니다. " + " / ".join(bits)
        if any(k == "milk" for k, _ in rejected):          # 우유 변경 불가 → 우유 없는 음료 (Q10)
            line += "\n" + alternatives_line({"no_milk"}, mid)
        return line

    item = CartItem(
        menu_id=mid, variant_id=str(v["주문 단위 ID"]), name=str(m["메뉴명"]),
        temp=str(v.get("온도")), size=str(v.get("크기")), qty=qty,
        is_alcohol=is_alcohol(mid), **allowed)
    ok, err = cart.add(item)
    if not ok:
        return f"{m['메뉴명']}: {err}"
    line = (f"[담기완료] {item.name} {item.temp}/{item.size}"
            + (f" ({item.option_text()})" if item.option_text() else "")
            + f" ×{qty} · {item.subtotal:,}원 "
              f"[기본 {item.base_price:,} + 옵션 {item.option_fee:,}]")
    caution = added_item_caution(item)
    return line + (f"\n{caution}" if caution else "")


def apply_order_items(order_items: list[dict], cart: Cart,
                      blocked: set[str] = frozenset()) -> list[str]:
    """라우터의 order_items 를 장바구니에 반영한다. LLM 호출 없음."""
    lines = [_add_one(it, cart, blocked) for it in order_items]
    if cart.status() == "pending_staff_check":
        lines.append("주류 포함 — 직원 나이 확인 전까지 확정 불가")
    return lines


def cart_signature(cart: Cart) -> tuple:
    """장바구니가 이번 턴에 바뀌었는지 비교하는 데 쓴다."""
    return tuple((i.variant_id, i.qty, tuple(i.options().items())) for i in cart.items)


def receipt_line(cart: Cart) -> str:
    """합계는 모델이 말하지 않고 코드가 답변 마지막 줄에 붙인다 (Q34)."""
    line = f"🧾 합계 {cart.total:,}원"
    if cart.status() == "pending_staff_check":
        line += " · 직원 확인 대기"
    return line


def build_calc(user_input: str, intent: str, order_items: list[dict] | None,
               cart: Cart) -> list[str]:
    """모델에게 넘길 계산 결과. 판단은 여기서 끝내고 태그로 적는다. LLM 호출 없음."""
    lines, blocked = screen(user_input, order_items)
    lines += decaf_notes(user_input)
    if intent == "장바구니" and order_items:
        lines = apply_order_items(order_items, cart, blocked) + lines
    else:
        # 담기가 아니어도 '하이볼'처럼 두 메뉴에 걸리는 말은 되묻게 한다 (Q47)
        for alias, mids in alias_hits(user_input):
            names = [str(menu_by_id(m)["메뉴명"]) for m in mids if menu_by_id(m)]
            if len(names) > 1:
                lines.append(f"'{alias}' 은 {' 또는 '.join(names)} 중 어느 것인지 확인이 필요합니다.")
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
    # 메뉴 이름이 걸렸는데 범위밖·잡담으로 분류되면 코드가 뒤집는다 (Q47: '하이볼'을 범위밖으로 봄)
    if intent in ("범위밖", "잡담") and any(menu_by_id(m) for m in match_menus(user_input)[0]):
        intent = "메뉴질문"

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
    before = cart_signature(cart)
    calc_lines = build_calc(user_input, intent, r.get("order_items"), cart)

    # ── 검색 + 답변 ────────────────────────────────────────
    docs, trace = hybrid_search(store, rq)
    reply, cached = answer(user_input, as_context(docs),
                           calc="\n".join(calc_lines), history=history)
    if cart_signature(cart) != before:
        reply = reply.rstrip() + "\n\n" + receipt_line(cart)
    return TurnResult(reply, intent, rq, lang, docs, trace,
                      "\n".join(calc_lines), cached, calls + (0 if cached else 1))
