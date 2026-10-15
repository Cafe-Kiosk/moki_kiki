"""전체 처리 흐름.

손님 입력 → 질의 재작성·의도 분류(LLM 1회) → 검색 또는 함수 호출 → 답변 생성(LLM 1회)
턴당 LLM 호출은 최대 2회이며, 범위 밖 질문은 검색을 건너뛴다.
"""
from __future__ import annotations
from dataclasses import dataclass, field

from .router import route
from .retrieve import hybrid_search, as_context, match_menus, alias_hits, _alias_attrs
from .chain import answer
from .cart import (Cart, CartItem, resolve_variant, menu_by_id, find_variants,
                   validate_options, option_label, option_alternatives, is_alcohol,
                   OPTION_KEYS, valid_qty, QTY_MSG)
from .budget import budget_lines, parse_budget
from .cart_edit import remove_item, update_item
from . import orders
from .conditions import screen, alternatives_line, item_caution_line, decaf_notes


def _menu_candidates(text: str) -> tuple[list[str], dict]:
    """이름에 걸리는 메뉴와, 별칭이 정해 주는 속성(온도·원두)을 돌려준다.

    긴 별칭부터 맞춘다 ('바닐라라떼'는 바닐라 라떼 하나). 그래도 둘 이상이면
    '하이볼'처럼 진짜 모호한 것이므로 확정하지 않고 손님에게 묻는다 (Q47).
    """
    ids, attrs = match_menus(text)
    return [i for i in ids if menu_by_id(i)], attrs


_MIXED = object()      # 같은 메뉴에 서로 다른 온도 별칭이 함께 나온 경우 ('아아랑 뜨아')


def text_alias_attrs(text: str) -> dict[str, dict]:
    """손님 원문의 별칭이 정해 주는 속성을 메뉴별로 모은다. 예: '아아 하나' → {M02: {temp: ICED}}.

    라우터가 온도를 null 로 넘겨도 원문에서 채우기 위해 쓴다 (Q25).
    """
    out: dict[str, dict] = {}
    for alias, mids in alias_hits(text):
        if len(mids) != 1:
            continue
        cur = out.setdefault(mids[0], {})
        for k, v in _alias_attrs().get(alias, {}).items():
            cur[k] = v if cur.get(k) in (None, v) else _MIXED
    return out


def _add_one(it: dict, cart: Cart, blocked: set[str] = frozenset(),
             text_attrs: dict | None = None) -> str:
    """주문 항목 하나를 검증해 담고, 모델에게 넘길 계산 줄을 돌려준다.

    blocked 는 손님 조건과 충돌한 메뉴다. 담지 않고 온도·크기도 묻지 않는다 (Q08).
    text_attrs 는 손님 원문 별칭의 속성이다 (text_alias_attrs).
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
    # 음료에 붙은 '데우기'는 온도 HOT 을 잘못 넣은 것이다 ('따뜻한 라떼' → warming=warm). 데우기는 디저트 옵션
    if m.get("분류") in ("커피", "차/논커피") and it.get("warming") in ("warm", "room"):
        it = dict(it, warming=None, temp=it.get("temp") or ("HOT" if it["warming"] == "warm" else None))
    # 라우터가 null 로 준 온도는 별칭이 정해 주는 값으로 채운다 ('아아' → ICED).
    # 라우터 메뉴명의 별칭이 먼저, 없으면 손님 원문의 별칭 (Q25)
    alias_temp = alias_attrs.get("temp") or (text_attrs or {}).get(mid, {}).get("temp")
    if alias_temp is _MIXED:
        alias_temp = None
    router_temp = (it.get("temp") or "").upper() or None
    if router_temp and alias_temp and router_temp != alias_temp:
        # '뜨거운 아아' — 어느 쪽인지 코드가 정하지 않는다
        return (f"{m['메뉴명']}: 담지 않았습니다. 온도 확인 필요 — "
                f"별칭은 {alias_temp}, 요청 온도는 {router_temp}")
    temp = router_temp or alias_temp
    v, all_v = resolve_variant(mid, temp, it.get("size"))
    if v is None:
        # 온도는 정해졌고 크기만 남았으면 그 온도의 구성만 보여 준다 ('아아' → ICED S/L)
        same_temp = [x for x in all_v if temp and str(x.get("온도")).upper() == temp]
        if same_temp:
            opts = " / ".join(f"{x.get('크기')} {int(x['가격(원)']):,}원" for x in same_temp)
            return f"{m['메뉴명']} {temp}: 크기만 골라야 합니다 (온도는 {temp}로 정해짐) → {opts}"
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
    # NA·ONE 같은 내부 값은 숨기고, 개수가 든 품목은 판매 단위로 센다 (P17)
    line = (f"[담기완료] {item.label()} · {item.subtotal:,}원 "
            f"[기본 {item.base_price:,} + 옵션 {item.option_fee:,}]")
    return line


def apply_order_items(order_items: list[dict], cart: Cart,
                      blocked: set[str] = frozenset(), user_input: str = "") -> list[str]:
    """라우터의 order_items 를 장바구니에 반영한다. LLM 호출 없음."""
    text_attrs = text_alias_attrs(user_input)
    lines = []
    for it in order_items:
        action = (it.get("action") or "add").lower()
        if action == "remove":
            lines.append(remove_item(it, cart))
        elif action == "update":
            lines.append(update_item(it, cart))
        else:
            lines.append(_add_one(it, cart, blocked, text_attrs))
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


FOOTER_MARKS = ("⚠️", "⚠", "🧾")


def strip_footer_lines(reply: str) -> str:
    """모델이 흉내 낸 ⚠️/🧾 줄을 지운다. 이 줄은 코드만 붙인다 (S02·S03·Q34 중복)."""
    kept = [ln for ln in reply.splitlines() if not ln.lstrip().startswith(FOOTER_MARKS)]
    return "\n".join(kept).rstrip()


def footer_lines(cart: Cart) -> list[str]:
    """장바구니가 바뀐 턴에 답변 끝에 붙는 줄들: 품목별 ⚠️ 주류·카페인, 마지막에 🧾 합계."""
    lines = []
    for it in cart.items:
        ln = item_caution_line(it)
        if ln and ln not in lines:
            lines.append(ln)
    return lines + [receipt_line(cart)]


def build_calc(user_input: str, intent: str, order_items: list[dict] | None,
               cart: Cart, router: dict | None = None) -> list[str]:
    """모델에게 넘길 계산 결과. 판단은 여기서 끝내고 태그로 적는다. LLM 호출 없음."""
    if intent == "예산추천":
        return budget_lines(user_input, router)          # 장바구니는 건드리지 않는다
    lines, blocked = screen(user_input, order_items)
    lines += decaf_notes(user_input)
    if intent == "장바구니" and order_items:
        lines = apply_order_items(order_items, cart, blocked, user_input) + lines
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


def _code_turn(reply: str, intent: str, user_input: str, cart: Cart, before: tuple) -> TurnResult:
    """코드만으로 끝나는 턴 (확정 확인·직전 주문 복사). LLM 호출 0회."""
    if cart_signature(cart) != before and cart.items:
        reply = reply.rstrip() + "\n\n" + "\n".join(footer_lines(cart))
    lang = "en" if str(user_input).isascii() else "ko"
    return TurnResult(reply, intent, user_input, lang, calc=cart.as_text(), llm_calls=0)


def handle(user_input: str, store, cart: Cart,
           history: list[dict] | None = None) -> TurnResult:
    history = history or []
    before = cart_signature(cart)

    # ── 확인 대기 중이면 네/아니요는 코드가 처리한다 (P05·P06·Q19·Q23) ──
    pending_note = None
    if cart.pending:
        kind = cart.pending
        if orders.is_yes(user_input):
            reply = orders.do_confirm(cart) if kind == "confirm" else orders.do_copy(cart)
            return _code_turn(reply, "결제" if kind == "confirm" else "장바구니", user_input, cart, before)
        cart.pending = None
        what = "주문 확정" if kind == "confirm" else "직전 주문 다시 담기"
        if orders.is_no(user_input):
            return _code_turn(f"{what}를 취소했습니다. 장바구니는 그대로입니다.", "결제", user_input, cart, before)
        pending_note = f"{what} 대기를 취소했습니다 — 확정·복사는 하지 않았습니다."   # 다른 말 → 대기만 풀고 평소대로
    # ── "아까 주문한 것 하나 더" — 복사 전에 확인 (Q19) ──
    if orders.is_repeat_request(user_input):
        return _code_turn(orders.ask_copy(cart), "장바구니", user_input, cart, before)

    r = route(user_input, history)
    intent, rq, lang = r["intent"], r["rewritten_query"], r["language"]
    calls = 1
    router_trace = [("라우터·실패", e, None) for e in r.get("errors", [])]
    # 메뉴 이름이 걸렸는데 범위밖·잡담으로 분류되면 코드가 뒤집는다 (Q47: '하이볼'을 범위밖으로 봄)
    if intent in ("범위밖", "잡담") and any(menu_by_id(m) for m in match_menus(user_input)[0]):
        intent = "메뉴질문"
    # 금액이 들어간 추천은 예산추천으로 본다 ("만 원으로 뭐 마실까")
    if intent == "추천" and parse_budget(user_input):
        intent = "예산추천"

    # ── 범위 밖·잡담 : 검색을 건너뛴다 (비용 절약) ──────────
    if intent in ("범위밖", "잡담"):
        reply, cached = answer(user_input, "", history=history, offtopic=True)
        return TurnResult(reply, intent, rq, lang, trace=router_trace, cached=cached,
                          llm_calls=calls + (0 if cached else 1))

    # ── 결제 : 코드가 처리하고 모델을 부르지 않는다 ─────────
    if intent == "결제":
        from .retrieve import rule_hits
        _, pids = rule_hits(user_input)
        unsupported = ("P07" in pids)
        reply = orders.ask_confirm(cart)            # 바로 확정하지 않고 확인을 받는다 (P05)
        if unsupported:
            reply = ("기프티콘·쿠폰·적립·분할 결제는 이 키오스크에서 지원하지 않습니다.\n"
                     + reply)
        return TurnResult(reply, intent, rq, lang, trace=router_trace,
                          calc=cart.as_text(), llm_calls=calls)

    # ── 장바구니 담기 ──────────────────────────────────────
    calc_lines = build_calc(user_input, intent, r.get("order_items"), cart, r)
    if pending_note:
        calc_lines.insert(0, pending_note)
    if any(e.startswith("JSON 파싱 실패") for e in r.get("errors", [])):
        calc_lines.append("요청을 해석하지 못했습니다 — 담기·빼기·변경은 하지 않았습니다. 손님에게 다시 말해 달라고 요청")

    # ── 검색 + 답변 ────────────────────────────────────────
    docs, trace = hybrid_search(store, rq)
    trace = router_trace + trace
    reply, cached = answer(user_input, as_context(docs),
                           calc="\n".join(calc_lines), history=history)
    reply = strip_footer_lines(reply)
    if cart_signature(cart) != before:
        reply = reply + "\n\n" + "\n".join(footer_lines(cart))
    return TurnResult(reply, intent, rq, lang, docs, trace,
                      "\n".join(calc_lines), cached, calls + (0 if cached else 1))
