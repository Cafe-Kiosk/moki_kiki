"""주문 확정 2단계와 직전 주문 다시 담기 (P05·P06·Q19·Q23). LLM 호출 없음.

  1) "확정할게요" → 좌석·품목·옵션·수량·합계를 보여 주고 "이대로 확정할까요?" (cart.pending = "confirm")
  2) 다음 턴이 긍정이면 확정, 부정이면 취소, 다른 말이면 대기만 풀고 그 말을 평소대로 처리
  "아까 주문한 것 하나 더" → 직전 확정 주문을 보여 주고 새 장바구니에 담을지 확인 (cart.pending = "copy")
"""
from __future__ import annotations
import re
from dataclasses import replace

from .cart import Cart, validate_options, variant_by_id, valid_qty

_YES = {"네", "넵", "예", "응", "어", "웅", "좋아요", "좋아", "그래요", "그래", "맞아요", "맞아", "맞습니다",
        "확정", "확정해", "확정해요", "확정해주세요", "확정할게요", "확정합니다", "결제할게요", "결제해주세요",
        "그대로", "그대로요", "그대로해주세요", "그렇게해주세요", "담아주세요", "담아줘", "네담아주세요",
        "네확정", "네확정해주세요", "네그대로", "yes", "y", "ok", "okay", "sure", "confirm", "yesplease"}
_NO = {"아니요", "아니오", "아니", "아뇨", "노", "취소", "취소해주세요", "안할게요", "아니요취소",
       "no", "n", "nope", "cancel"}

REPEAT_RE = re.compile(r"(아까|방금|이전|전에|직전|저번)\s*(에\s*)?(주문|시킨|시켰던|먹은|마신)\S*.*"
                       r"(하나\s*더|한\s*번\s*더|또|다시|같은\s*거|똑같이)|same\s+again|one\s+more\s+of\s+the\s+last",
                       re.IGNORECASE)


def _norm(text: str) -> str:
    return re.sub(r"[\s.!~?,]+", "", str(text).lower())


def is_yes(text: str) -> bool:
    return _norm(text) in _YES


def is_no(text: str) -> bool:
    return _norm(text) in _NO


def is_repeat_request(text: str) -> bool:
    return bool(REPEAT_RE.search(str(text)))


def summary(cart: Cart) -> str:
    return f"좌석 {cart.table_id}번\n{cart.as_text()}"


def ask_confirm(cart: Cart) -> str:
    """첫 확정 요청. 확정하지 않고 확인을 받는다."""
    ok, msg = cart.can_confirm()
    if not ok:
        cart.pending = None
        return msg + (f"\n{summary(cart)}" if cart.items else "")
    cart.pending = "confirm"
    return f"주문 내용을 확인해 주세요.\n{summary(cart)}\n이대로 확정할까요? (네 / 아니요)"


def do_confirm(cart: Cart) -> str:
    ok, msg = cart.confirm()
    if not ok:
        cart.pending = None
        return msg
    o = cart.confirmed_orders[-1]
    return (f"주문을 확정했습니다. 주문번호는 {o['order_no']} 입니다 (좌석 {o['table_id']}번).\n{o['text']}\n"
            "시연용 주문번호이며 실제 결제가 이루어지지는 않았습니다. 추가 주문은 새 주문으로 받습니다.")


def ask_copy(cart: Cart) -> str:
    """직전 확정 주문을 새 장바구니에 복사하기 전에 확인을 받는다 (Q19). 확정 주문은 바꾸지 않는다."""
    if not cart.confirmed_orders:
        cart.pending = None
        return "아직 확정된 주문이 없습니다. 원하시는 메뉴를 말씀해 주세요."
    o = cart.confirmed_orders[-1]
    cart.pending = "copy"
    return (f"직전 주문 {o['order_no']} (좌석 {o['table_id']}번)\n{o['text']}\n"
            f"같은 구성을 좌석 {cart.table_id}번의 새 주문으로 장바구니에 담을까요? (네 / 아니요)")


def do_copy(cart: Cart) -> str:
    """직전 주문 품목을 새 장바구니에 담는다. 담을 때 다시 검증한다."""
    cart.pending = None
    o = cart.confirmed_orders[-1]
    added, skipped = [], []
    for it in o["items"]:
        new = replace(it)                                   # 확정 주문의 품목 객체는 건드리지 않는다
        _, bad = validate_options(new.menu_id, variant_by_id(new.variant_id), new.options())
        if bad or not valid_qty(new.qty):
            skipped.append(new.label())
            continue
        ok, _ = cart.add(new)
        (added if ok else skipped).append(new.label())
    lines = [f"직전 주문 {o['order_no']} 의 구성을 새 장바구니에 담았습니다: " + ", ".join(added)]
    if skipped:
        lines.append("담지 못한 품목: " + ", ".join(skipped))
    if cart.status() == "pending_staff_check":
        lines.append("주류가 있어 이번 주문도 직원의 나이 확인이 필요합니다.")
    return "\n".join(lines)
