"""전체 처리 흐름.

손님 입력 → 질의 재작성(LLM) → 검색 → 의도·실행계획(LLM) → 서버 검증 → 답변(LLM)
일반 턴의 LLM 호출은 최대 3회이며, 상태 변경은 항상 코드가 재검증한다.
"""
from __future__ import annotations
from dataclasses import dataclass, field

from .router import rewrite, classify, adapt_plan
from .retrieve import hybrid_search_rewrite, as_context, _alias_map
from .chain import answer
from .cart import (Cart, CartItem, resolve_variant, menu_by_id, find_variants,
                   variant_by_id, validate_item_options)
from .config import is_mock
from .quick_replies import build_quick_replies, is_choice_prompt
from .content import menu_image_cards


def _menu_candidates(text: str) -> list[str]:
    """이름에 걸리는 메뉴를 모두 돌려준다.

    "하이볼"처럼 여러 메뉴의 별칭에 걸리는 말은 하나로 확정하면 안 된다.
    확정은 손님에게 묻고 나서 한다 (검증질문 Q47).
    """
    t = str(text).strip().lower()
    direct_id = t.upper()
    if menu_by_id(direct_id):
        return [direct_id]
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
    quick_replies: list[dict[str, str]] = field(default_factory=list)
    menu_images: list[dict[str, str]] = field(default_factory=list)


def _session_state(cart: Cart) -> dict:
    return {
        "table_id": cart.table_id,
        "cart_status": cart.status(),
        "order_no": cart.order_no,
        "staff_verification": "verified" if cart.staff_checked else "not_verified",
        "cart_items": [
            {
                "line_id": str(index),
                "menu_id": item.menu_id,
                "variant_id": item.variant_id,
                "quantity": item.qty,
                "options": {
                    "bean": item.bean,
                    "extra_shots": item.extra_shots,
                    "milk": item.milk,
                    "sweetness": item.sweetness,
                    "ice": item.ice,
                    "warming": item.warming,
                },
            }
            for index, item in enumerate(cart.items)
        ],
        "total_krw": cart.total,
    }


def handle(user_input: str, store, cart: Cart,
           history: list[dict] | None = None) -> TurnResult:
    history = history or []
    state = _session_state(cart)
    rewritten = rewrite(user_input, history, state)
    docs, trace = hybrid_search_rewrite(store, rewritten)
    context = as_context(docs)
    plan = classify(user_input, rewritten, context, history, state, _alias_map())
    r = adapt_plan(user_input, rewritten, plan)
    intent, rq, lang = r["intent"], r["rewritten_query"], r["language"]
    calls = 0 if is_mock() else 2
    menu_images = menu_image_cards(
        docs,
        user_message=user_input,
        rewritten=rq,
        history=history,
    )

    # 새 프롬프트 계약: 미해결 대상이나 필수값이 있으면 쓰기 작업 전체를 보류한다.
    if plan.get("needs_clarification"):
        question = plan.get("clarification_question") or "주문 조건을 조금 더 구체적으로 알려주세요."
        quick_replies = build_quick_replies(question, plan, rewritten)
        return TurnResult(
            question, intent, rq, lang, docs, trace,
            "상태 변경 없음 — 확인 필요", False, calls, quick_replies,
            menu_images,
        )

    # ── 범위 밖·잡담 : 검색을 건너뛴다 (비용 절약) ──────────
    if intent in ("범위밖", "잡담"):
        reply, cached = answer(user_input, "", history=history, offtopic=True,
                               session_state=state)
        return TurnResult(
            reply, intent, rq, lang, cached=cached,
            llm_calls=calls + (0 if cached else 1), menu_images=menu_images,
        )

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
        return TurnResult(
            reply, intent, rq, lang, calc=cart.as_text(), llm_calls=calls,
            menu_images=menu_images,
        )

    # ── 장바구니 담기 ──────────────────────────────────────
    calc_lines = []
    if intent == "장바구니" and r.get("order_items"):
        for it in r["order_items"]:
            cands = _menu_candidates(it.get("menu_id") or it.get("menu_name", ""))
            if not cands:
                calc_lines.append(f"'{it.get('menu_name')}' 은 메뉴에서 찾지 못했습니다.")
                continue
            if len(cands) > 1:
                names = " 또는 ".join(str(menu_by_id(c)["메뉴명"]) for c in cands)
                calc_lines.append(
                    f"'{it.get('menu_name')}' 은 {names} 중 어느 것인지 확인이 필요합니다. "
                    "담지 않았습니다.")
                continue
            mid = cands[0]
            m = menu_by_id(mid)
            requested_variant = it.get("variant_id")
            all_v = find_variants(mid)
            if requested_variant:
                v = variant_by_id(str(requested_variant))
                if not v or not str(requested_variant).startswith(mid + "-"):
                    v = None
            else:
                v, all_v = resolve_variant(mid, it.get("temp"), it.get("size"))
            if v is None:
                opts = " / ".join(
                    f"{x.get('온도')}·{x.get('크기')} {int(x['가격(원)']):,}원" for x in all_v)
                calc_lines.append(f"{m['메뉴명']}: 구성을 하나 골라야 합니다 → {opts}")
                continue
            if it.get("qty") is None:
                calc_lines.append(f"{m['메뉴명']}: 수량을 확인해야 합니다. 담지 않았습니다.")
                continue
            qty = int(it["qty"])
            item = CartItem(
                menu_id=mid, variant_id=str(v["주문 단위 ID"]), name=str(m["메뉴명"]),
                temp=str(v.get("온도")), size=str(v.get("크기")), qty=qty,
                bean=it.get("bean"), extra_shots=int(it.get("extra_shots") or 0),
                milk=it.get("milk"), sweetness=it.get("sweetness"),
                ice=it.get("ice"), warming=it.get("warming"),
                is_alcohol=str(m.get("주류 구분", "")).startswith("주류 포함"))
            valid, err = validate_item_options(item)
            if not valid:
                calc_lines.append(f"{m['메뉴명']}: {err} 담지 않았습니다.")
                continue
            ok, err = cart.add(item)
            if not ok:
                calc_lines.append(f"{m['메뉴명']}: {err}")
            else:
                calc_lines.append(
                    f"{item.name} {item.temp}/{item.size}"
                    + (f" ({item.option_text()})" if item.option_text() else "")
                    + f" ×{qty} = {item.subtotal:,}원 "
                      f"[기본 {item.base_price:,} + 옵션 {item.option_fee:,}]")
        if cart.items:
            calc_lines.append(f"현재 합계 {cart.total:,}원")
        if cart.status() == "pending_staff_check":
            calc_lines.append("주류 포함 — 직원 나이 확인 전까지 확정 불가")

    if intent == "장바구니" and not r.get("order_items"):
        mutating = [a for a in plan.get("actions", []) if a.get("mutates_state")]
        if mutating:
            names = ", ".join(str(a.get("intent")) for a in mutating)
            calc_lines.append(
                f"요청 작업({names})은 현재 실행 어댑터에서 처리되지 않아 장바구니를 변경하지 않았습니다."
            )
        else:
            calc_lines.append(cart.as_text())

    # ── 답변 생성 ──────────────────────────────────────────
    reply, cached = answer(user_input, context,
                           calc="\n".join(calc_lines), history=history,
                           session_state=_session_state(cart), plan=plan,
                           capabilities={
                               "menu_images_attached": bool(menu_images),
                               "menu_image_menu_ids": [
                                   card["id"] for card in menu_images
                               ],
                           })
    quick_replies = (build_quick_replies(reply, plan, rewritten)
                     if is_choice_prompt(reply) else [])
    return TurnResult(
        reply, intent, rq, lang, docs, trace,
        "\n".join(calc_lines), cached, calls + (0 if cached else 1),
        quick_replies, menu_images,
    )
