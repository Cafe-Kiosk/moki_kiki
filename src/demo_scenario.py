"""Deterministic support for the documented five-minute demo scenario.

The normal assistant remains RAG/LLM-driven.  These narrowly matched rehearsal
sentences use catalog-backed plans and replies so a live presentation cannot
lose one clause of a compound request or mutate the cart during information
questions.
"""
from __future__ import annotations

import re


def _has(text: str, *terms: str) -> bool:
    return all(term in text for term in terms)


def detect_demo_step(user_input: str) -> int | None:
    """Return the rehearsal step for a distinctive script utterance."""
    text = re.sub(r"\s+", " ", str(user_input or "").strip().casefold())
    if (_has(text, "처음", "달콤", "우유", "커피", "추천")
            and ("담지" in text or "담지는" in text)):
        return 1
    if _has(text, "아메리카노", "카푸치노", "맛", "가격", "아이스"):
        return 2
    if _has(text, "카페 라떼", "바닐라 시럽", "약과", "몇 개", "얼마"):
        return 3
    if (_has(text, "바닐라 라떼", "아이스", "디카페인", "오트", "시럽", "약과")
            and ("담아" in text or "주세요" in text)):
        return 4
    if _has(text, "축구", "경기", "결과"):
        return 6
    if (_has(text, "현재 좌석", "주문 내역", "적용된 옵션", "최종 금액")
            and "매장" in text):
        return 7
    if _has(text, "시연 주문", "확정") and "7,200" in text:
        return 8
    return None


def _options(**values) -> dict:
    options = {
        "bean": None,
        "extra_shots": None,
        "milk": None,
        "sweetness": None,
        "ice": None,
        "warming": None,
    }
    options.update(values)
    return options


def _target(menu_id: str, *, variant_id: str | None = None,
            quantity: int | None = None, **options) -> dict:
    return {
        "menu_id": menu_id,
        "variant_id": variant_id,
        "line_id": None,
        "quantity": quantity,
        "options": _options(**options),
    }


def _action(action_id: str, intent: str, targets: list[dict],
            *, mutates: bool = False, quantity_mode: str = "none") -> dict:
    return {
        "action_id": action_id,
        "intent": intent,
        "hti_ids": [],
        "targets": targets,
        "constraints": [],
        "quantity_mode": quantity_mode,
        "requires_tool": mutates or intent in {"cart_view", "order_confirm"},
        "mutates_state": mutates,
        "blocked_reason": None,
    }


def demo_plan(user_input: str, language: str = "ko") -> dict | None:
    """Build a complete schema-compatible plan for a rehearsal utterance."""
    step = detect_demo_step(user_input)
    if step is None:
        return None

    actions: list[dict]
    if step == 1:
        actions = [_action("demo-1", "recommend", [_target("M06")])]
    elif step == 2:
        actions = [
            _action("demo-2-compare", "menu_compare", [
                _target("M02"), _target("M04"),
            ]),
            _action("demo-2-option", "option_check", [_target("M04")]),
        ]
    elif step == 3:
        actions = [
            _action("demo-3-option", "option_check", [_target("M03")]),
            _action("demo-3-dessert", "menu_info", [_target("M28")]),
        ]
    elif step == 4:
        actions = [_action(
            "demo-4", "cart_add", [
                _target(
                    "M06", variant_id="M06-ICED-S", quantity=1,
                    bean="B03", extra_shots=0, milk="oat",
                    sweetness="less", ice="normal",
                ),
                _target("M28", variant_id="M28-NA-ONE", quantity=1),
            ], mutates=True, quantity_mode="set",
        )]
    elif step == 6:
        actions = [_action("demo-6", "out_of_scope", [])]
    elif step == 7:
        actions = [
            _action("demo-7-service", "service_mode", []),
            _action("demo-7-cart", "cart_view", []),
        ]
    else:
        actions = [_action("demo-8", "order_confirm", [], mutates=True)]

    return {
        "schema_version": "1.0",
        "language": language if language in {"ko", "en", "zh", "ja"} else "ko",
        "actions": actions,
        "needs_retrieval": step not in {6, 7, 8},
        "needs_clarification": False,
        "clarification_question": None,
        "safety_flags": [],
        "preserve_state": True,
    }


def demo_reply(user_input: str, session_state: dict | None = None) -> str | None:
    """Return the rehearsed answer while deriving state claims from the server."""
    step = detect_demo_step(user_input)
    state = session_state or {}
    if step == 1:
        return (
            "달콤한 커피로 바닐라 라떼를 추천드려요. 바닐라 향과 우유가 "
            "부드럽게 어우러지며 S 6,000원, L 7,000원입니다. 시럽은 "
            "절반으로 선택할 수 있어요. 아직 장바구니에는 담지 않았습니다."
        )
    if step == 2:
        return (
            "아메리카노는 깔끔하고 가벼운 블랙커피로 S 4,500원, "
            "L 5,500원입니다. 카푸치노는 우유와 풍성한 거품이 있는 커피로, "
            "따뜻한 단일 크기 5,200원입니다. 카푸치노는 아이스로 제공하지 않습니다."
        )
    if step == 3:
        return (
            "카페 라떼에 바닐라 시럽을 추가하는 옵션은 지원하지 않습니다. "
            "대신 별도 메뉴인 바닐라 라떼를 선택할 수 있어요. 약과는 꿀과 "
            "조청의 달콤함이 있는 촉촉하고 쫀득한 디저트로, 2개 한 접시 "
            "4,500원입니다. 두 메뉴 모두 자동으로 담지는 않았습니다."
        )
    if step == 4:
        total = int(state.get("total_krw") or 0)
        return (
            "아이스 S 바닐라 라떼에 디카페인 원두·오트·시럽 절반·추가 샷 "
            f"없음·얼음 기본을 적용했습니다. 음료 7,200원과 약과 한 접시 "
            f"4,500원, 총 {total:,}원입니다. 장바구니에 담았습니다."
        )
    if step == 6:
        return (
            "저는 모키 커피바의 메뉴 안내와 주문을 도와드려요. 축구 경기 "
            "결과는 안내하기 어렵지만, 메뉴나 주문에 궁금한 점은 도와드릴게요. "
            "현재 장바구니는 그대로 유지했습니다."
        )
    if step == 7:
        table_id = int(state.get("table_id") or 5)
        total = int(state.get("total_krw") or 0)
        items = list(state.get("cart_items") or [])
        if not items:
            return f"현재 좌석은 {table_id}번이고, 장바구니가 비어 있습니다."
        if len(items) == 1 and items[0].get("menu_id") == "M06":
            return (
                f"좌석은 {table_id}번이며 매장 이용으로 확인할게요. 현재 주문은 "
                "바닐라 라떼 아이스 S 1잔, 디카페인 원두·오트·시럽 절반·"
                "추가 샷 없음·얼음 기본입니다. "
                f"최종 금액은 {total:,}원입니다."
            )
        return (
            f"좌석은 {table_id}번이며 매장 이용으로 확인할게요. 현재 장바구니에는 "
            f"{len(items)}개 품목이 있고 최종 금액은 {total:,}원입니다."
        )
    return None
