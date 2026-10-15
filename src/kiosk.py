"""전체 처리 흐름.

손님 입력 → 질의 재작성(LLM) → 검색 → 의도·실행계획(LLM) → 서버 검증 → 답변(LLM)
일반 턴의 LLM 호출은 최대 3회이며, 상태 변경은 항상 코드가 재검증한다.
"""
from __future__ import annotations
from copy import deepcopy
from dataclasses import dataclass, field

from .router import rewrite, classify, adapt_plan
from .retrieve import hybrid_search_rewrite, as_context, _alias_map
from .chain import answer
from .cart import (Cart, CartItem, resolve_variant, menu_by_id, find_variants,
                   variant_by_id, validate_item_options)
from .config import is_mock
from .quick_replies import build_quick_replies, is_choice_prompt
from .content import menu_image_cards


_CART_MUTATIONS = {"cart_add", "cart_update", "cart_remove", "cart_clear"}


class CartExecutionError(ValueError):
    """A validated plan could not be applied without a partial cart change."""


def _target_menu_id(target: dict) -> str | None:
    menu_id = str(target.get("menu_id") or "").strip().upper()
    if menu_by_id(menu_id):
        return menu_id
    variant_id = str(target.get("variant_id") or "").strip().upper()
    if "-" in variant_id:
        candidate = variant_id.split("-", 1)[0]
        if menu_by_id(candidate):
            return candidate
    return None


def _new_item_from_target(target: dict) -> CartItem:
    """Build one item from a planner target using catalog truth only."""
    menu_id = _target_menu_id(target)
    if not menu_id:
        raise CartExecutionError("주문할 메뉴를 현재 메뉴에서 확인하지 못했어요.")
    menu = menu_by_id(menu_id)
    variants = find_variants(menu_id)
    requested_variant = str(target.get("variant_id") or "").strip()
    if requested_variant:
        variant = variant_by_id(requested_variant)
        if not variant or not requested_variant.startswith(menu_id + "-"):
            raise CartExecutionError(
                f"{menu['메뉴명']}: 주문 구성을 다시 확인해 주세요."
            )
    else:
        variant, variants = resolve_variant(menu_id, None, None)
    if variant is None:
        choices = " / ".join(
            f"{row.get('온도')}·{row.get('크기')} {int(row['가격(원)']):,}원"
            for row in variants
        )
        raise CartExecutionError(
            f"{menu['메뉴명']}: 온도·크기를 골라 주세요 → {choices}"
        )
    quantity = target.get("quantity")
    if quantity is None:
        raise CartExecutionError(f"{menu['메뉴명']}: 수량을 확인해 주세요.")
    if isinstance(quantity, bool):
        raise CartExecutionError(f"{menu['메뉴명']}: 수량은 1~10 정수로 알려주세요.")
    options = target.get("options") or {}
    extra_shots = options.get("extra_shots")
    item = CartItem(
        menu_id=menu_id,
        variant_id=str(variant["주문 단위 ID"]),
        name=str(menu["메뉴명"]),
        temp=str(variant.get("온도")),
        size=str(variant.get("크기")),
        qty=int(quantity),
        bean=options.get("bean"),
        extra_shots=0 if extra_shots is None else int(extra_shots),
        milk=options.get("milk"),
        sweetness=options.get("sweetness"),
        ice=options.get("ice"),
        warming=options.get("warming"),
        is_alcohol=str(menu.get("주류 구분", "")).startswith("주류 포함"),
    )
    valid, error = validate_item_options(item)
    if not valid:
        raise CartExecutionError(f"{item.name}: {error}")
    return item


def _snapshot_line_index(target: dict, snapshot: Cart) -> int:
    """Resolve a line once against the original cart, before any removal shifts it."""
    line_id = target.get("line_id")
    menu_id = _target_menu_id(target)
    if line_id not in (None, ""):
        try:
            index = int(str(line_id))
        except (TypeError, ValueError) as exc:
            raise CartExecutionError("변경할 장바구니 항목을 다시 골라 주세요.") from exc
        if not 0 <= index < len(snapshot.items):
            raise CartExecutionError("변경할 장바구니 항목을 다시 골라 주세요.")
        if menu_id and snapshot.items[index].menu_id != menu_id:
            raise CartExecutionError("선택한 항목과 메뉴가 서로 달라요. 주문 내역을 다시 확인해 주세요.")
        return index
    if not menu_id:
        raise CartExecutionError("변경할 메뉴를 알려주세요.")
    matches = [
        index for index, item in enumerate(snapshot.items)
        if item.menu_id == menu_id
    ]
    if len(matches) != 1:
        if not matches:
            raise CartExecutionError("해당 메뉴가 장바구니에 없어요.")
        raise CartExecutionError(
            "같은 메뉴가 여러 줄이에요. 변경할 항목의 번호를 골라 주세요."
        )
    return matches[0]


def _update_snapshot_item(
    current: CartItem,
    target: dict,
    quantity_mode: str,
) -> CartItem:
    updated = deepcopy(current)
    changed = False
    variant_id = str(target.get("variant_id") or "").strip()
    if variant_id and variant_id != updated.variant_id:
        variant = variant_by_id(variant_id)
        if not variant or not variant_id.startswith(updated.menu_id + "-"):
            raise CartExecutionError(f"{updated.name}: 지원하지 않는 온도·크기예요.")
        updated.variant_id = variant_id
        updated.temp = str(variant.get("온도"))
        updated.size = str(variant.get("크기"))
        if updated.temp != "ICED":
            updated.ice = None
        changed = True

    for key, value in (target.get("options") or {}).items():
        if value is None or key not in {
            "bean", "extra_shots", "milk", "sweetness", "ice", "warming"
        }:
            continue
        if key == "extra_shots":
            value = int(value)
        if getattr(updated, key) != value:
            setattr(updated, key, value)
            changed = True

    quantity = target.get("quantity")
    if quantity is not None:
        if isinstance(quantity, bool):
            raise CartExecutionError("수량은 1~10 정수로 알려주세요.")
        amount = int(quantity)
        if quantity_mode == "increment":
            new_quantity = updated.qty + amount
        elif quantity_mode == "decrement":
            new_quantity = updated.qty - amount
        elif quantity_mode == "set":
            new_quantity = amount
        else:
            raise CartExecutionError("수량을 총 몇 개로 바꿀지 확인해 주세요.")
        if not 1 <= new_quantity <= 10:
            raise CartExecutionError("수량은 변경 후에도 1~10 정수여야 해요.")
        changed = changed or new_quantity != updated.qty
        updated.qty = new_quantity
    if not changed:
        raise CartExecutionError(f"{updated.name}: 바꿀 수량이나 옵션을 알려주세요.")
    valid, error = validate_item_options(updated)
    if not valid:
        raise CartExecutionError(f"{updated.name}: {error}")
    return updated


def _alcohol_totals(cart: Cart) -> dict[tuple[str, str], int]:
    totals: dict[tuple[str, str], int] = {}
    for item in cart.items:
        if item.is_alcohol:
            key = (item.menu_id, item.variant_id)
            totals[key] = totals.get(key, 0) + item.qty
    return totals


def _alcohol_increased(before: Cart, after: Cart) -> bool:
    old = _alcohol_totals(before)
    return any(quantity > old.get(key, 0)
               for key, quantity in _alcohol_totals(after).items())


def _item_calc_line(item: CartItem) -> str:
    return (
        f"{item.name} {item.temp}/{item.size}"
        + (f" ({item.option_text()})" if item.option_text() else "")
        + f" ×{item.qty} = {item.subtotal:,}원 "
          f"[기본 {item.base_price:,} + 옵션 {item.option_fee:,}]"
    )


def _execute_cart_actions(plan: dict, cart: Cart) -> tuple[list[str], list[CartItem], bool]:
    """Apply every cart mutation atomically against snapshot-resolved targets."""
    actions = [
        action for action in plan.get("actions") or []
        if action.get("intent") in _CART_MUTATIONS
    ]
    if not actions:
        return [], [], False
    if cart.order_no:
        raise CartExecutionError("이미 확정한 주문은 변경할 수 없어요. 추가 주문을 새로 시작해 주세요.")
    if any(action.get("blocked_reason") for action in actions):
        raise CartExecutionError("확인이 필요한 조건이 있어 장바구니를 변경하지 않았어요.")

    kinds = {action.get("intent") for action in actions}
    if "cart_clear" in kinds and len(actions) != 1:
        raise CartExecutionError("전체 비우기와 다른 변경은 함께 처리할 수 없어요.")

    original = deepcopy(cart)
    staged = deepcopy(cart)
    lines: list[str] = []
    added_items: list[CartItem] = []

    if kinds == {"cart_clear"}:
        if len(actions[0].get("targets") or []) > 0:
            raise CartExecutionError("전체 비우기 요청을 다시 확인해 주세요.")
        staged.items = []
        staged.staff_checked = False
        lines.append("장바구니의 모든 메뉴를 비웠어요.")
    else:
        resolved: list[tuple[dict, dict, int]] = []
        for action in actions:
            if action.get("intent") == "cart_add":
                continue
            targets = list(action.get("targets") or [])
            if not targets:
                raise CartExecutionError("변경할 장바구니 항목을 알려주세요.")
            for target in targets:
                resolved.append((action, target, _snapshot_line_index(target, original)))

        removes = [index for action, _, index in resolved
                   if action.get("intent") == "cart_remove"]
        updates = [index for action, _, index in resolved
                   if action.get("intent") == "cart_update"]
        if len(set(removes)) != len(removes):
            raise CartExecutionError("같은 항목을 여러 번 삭제할 수 없어요.")
        if set(removes) & set(updates):
            raise CartExecutionError("같은 항목을 한번에 변경하고 삭제할 수 없어요.")

        # All indices refer to ``original``; update first and remove in descending
        # order so a prior deletion can never retarget a later operation.
        for action, target, index in resolved:
            if action.get("intent") != "cart_update":
                continue
            updated = _update_snapshot_item(
                staged.items[index], target, str(action.get("quantity_mode") or "none")
            )
            staged.items[index] = updated
            lines.append(f"변경: {_item_calc_line(updated)}")
        for index in sorted(removes, reverse=True):
            removed = staged.items[index]
            staged.remove(index)
            lines.append(f"삭제: {removed.name} ×{removed.qty}")

        # Validate and append additions only after every snapshot-based update
        # and removal has succeeded.  Nothing is committed to ``cart`` until
        # the whole mixed plan is valid, so an invalid add also rolls back the
        # preceding mutations.  The API can then defer these trailing items
        # while keeping the successful mutation result live in the browser.
        for action in actions:
            if action.get("intent") != "cart_add":
                continue
            targets = list(action.get("targets") or [])
            if not targets:
                raise CartExecutionError("담을 메뉴를 알려주세요.")
            for target in targets:
                item = _new_item_from_target(target)
                if len(staged.items) >= 30:
                    raise CartExecutionError("장바구니에는 최대 30개 항목만 담을 수 있어요.")
                ok, error = staged.add(item)
                if not ok:
                    raise CartExecutionError(f"{item.name}: {error}")
                added_items.append(deepcopy(item))
                lines.append(_item_calc_line(item))

    staged.order_no = None
    if not staged.has_alcohol:
        staged.staff_checked = False
    elif _alcohol_increased(original, staged):
        staged.staff_checked = False
    else:
        staged.staff_checked = original.staff_checked

    changed = staged.items != original.items
    if not changed:
        raise CartExecutionError("바뀐 내용이 없어 장바구니는 그대로예요.")
    cart.items = staged.items
    cart.order_no = staged.order_no
    cart.staff_checked = staged.staff_checked
    lines.append(f"현재 합계 {cart.total:,}원")
    if cart.status() == "pending_staff_check":
        lines.append("주류 포함 — 직원 나이 확인 전까지 확정 불가")
    return lines, added_items, True


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
    added_items: list[CartItem] = field(default_factory=list)
    cart_changed: bool = False
    execution_error: str | None = None


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
    # ``adapt_plan`` also applies the deterministic explicit-order coverage guard
    # for direct callers, so all downstream checks must use its normalized plan.
    plan = r["plan"]
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

    # ── 장바구니 변경: 원본 snapshot에서 대상 확정 후 복사본에 원자 적용 ──
    calc_lines: list[str] = []
    added_items: list[CartItem] = []
    cart_changed = False
    execution_error: str | None = None
    try:
        calc_lines, added_items, cart_changed = _execute_cart_actions(plan, cart)
    except CartExecutionError as exc:
        execution_error = str(exc)
        calc_lines = [execution_error, "장바구니는 변경하지 않았습니다."]

    if execution_error:
        reply = execution_error + " 장바구니는 변경하지 않았습니다."
        quick_replies = (build_quick_replies(reply, plan, rewritten)
                         if is_choice_prompt(reply) else [])
        return TurnResult(
            reply, intent, rq, lang, docs, trace,
            "\n".join(calc_lines), False, calls, quick_replies,
            menu_images, [], False, execution_error,
        )

    if intent == "장바구니" and not calc_lines:
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
        quick_replies, menu_images, added_items, cart_changed,
    )
