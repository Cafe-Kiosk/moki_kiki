"""질의 재작성과 의도/실행계획 생성.

프롬프트팀 산출물의 두 단계 계약을 그대로 사용한다.
  1. rewrite: 검색 질의와 미해결 지시어 생성
  2. classify: 검색 문서를 참고해 구조화된 actions 생성

실제 상태 변경 권한은 이 모듈에 없다. 계획은 kiosk.py의 검증 코드가 실행한다.
"""
from __future__ import annotations

from copy import deepcopy
import json
import re
from typing import Any

from jsonschema import ValidationError, validate
from langchain_openai import ChatOpenAI

from .config import (ROUTER_MODEL, ROUTER_MAX_TOKENS, HISTORY_TURNS,
                     OPENAI_TIMEOUT_SECONDS, OPENAI_MAX_RETRIES,
                     current_api_key, current_language, is_mock)
from .prompts import load as load_prompt, load_schema
from .demo_scenario import demo_plan, detect_demo_step

REWRITE_PROMPT = load_prompt("rewrite")
INTENT_PROMPT = load_prompt("intent")
REWRITE_SCHEMA = load_schema("rewrite")
INTENT_SCHEMA = load_schema("intent")


def _llm():
    return ChatOpenAI(
        model=ROUTER_MODEL,
        temperature=0,
        max_tokens=ROUTER_MAX_TOKENS,
        api_key=current_api_key(),
        timeout=OPENAI_TIMEOUT_SECONDS,
        max_retries=OPENAI_MAX_RETRIES,
    )


def _language(text: str) -> str:
    if any("\u3040" <= c <= "\u30ff" for c in text):
        return "ja"
    if any("\u4e00" <= c <= "\u9fff" for c in text):
        return "zh"
    letters = [c for c in text if c.isalpha()]
    return "en" if letters and all(ord(c) < 128 for c in letters) else "ko"


def _history_summary(history: list[dict] | None) -> str:
    if not history:
        return "(없음)"
    lines = []
    for message in history[-HISTORY_TURNS * 2:]:
        who = "user" if message.get("role") == "user" else "assistant"
        lines.append(f"{who}: {str(message.get('content', ''))[:180]}")
    return "\n".join(lines)


def _history_messages(history: list[dict] | None) -> list[dict[str, str]]:
    """재작성·의도 분류에도 최근 대화의 역할과 충분한 문맥을 보존한다."""
    return [
        {
            "role": "user" if message.get("role") == "user" else "assistant",
            "content": str(message.get("content", ""))[:1200],
        }
        for message in (history or [])[-HISTORY_TURNS * 2:]
        if str(message.get("content", "")).strip()
    ]


def _parse_json(content: Any) -> dict:
    if isinstance(content, dict):
        return content
    text = str(content).strip()
    text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(text)


def _invoke(prompt: str, payload: dict, schema: dict) -> dict:
    schema_text = json.dumps(schema, ensure_ascii=False)
    payload_text = json.dumps(payload, ensure_ascii=False, default=str)
    response = _llm().invoke([
        {"role": "system", "content": prompt},
        {
            "role": "user",
            "content": (
                "다음 입력을 처리하고 JSON만 출력하세요.\n"
                f"입력:\n{payload_text}\n\n"
                f"반드시 따를 JSON Schema:\n{schema_text}"
            ),
        },
    ])
    parsed = _parse_json(response.content)
    validate(instance=parsed, schema=schema)
    return parsed


def _mock_rewrite(user_input: str) -> dict:
    return {
        "schema_version": "1.0",
        "language": _language(user_input),
        "rewritten_utterance": user_input,
        "queries": [{"query": user_input, "document_types": [], "menu_ids": []}],
        "resolved": True,
        "unresolved_references": [],
    }


def _empty_options() -> dict:
    return {key: None for key in (
        "bean", "extra_shots", "milk", "sweetness", "ice", "warming"
    )}


_CHECKOUT_INFO_RE = re.compile(
    r"(?:결제\s*(?:수단|방법|가능|되나|되는지)|"
    r"어떻게\s*결제|주문\s*(?:가능|방법|할\s*수)|"
    r"계산\s*(?:방법|가능)|"
    r"payment\s*(?:method|option)|can\s+i\s+(?:pay|order))",
    re.IGNORECASE,
)
_CHECKOUT_COMMAND_RE = re.compile(
    r"(?:"
    r"주문\s*확정(?:해\s*줘|해\s*주세요|할게|할래)?|"
    r"이대로\s*(?:주문|결제|계산)(?:할게|할래|해\s*줘|해\s*주세요)?|"
    r"결제(?:할게|할래|해\s*줘|해\s*주세요|진행해\s*줘)|"
    r"계산(?:할게|할래|해\s*줘|해\s*주세요|부탁해)|"
    r"\b(?:checkout|confirm\s+(?:my\s+)?order|pay\s+now)\b"
    r")",
    re.IGNORECASE,
)


def _is_checkout_command(user_input: str) -> bool:
    """Recognize an instruction to proceed, not a payment-policy question."""
    text = str(user_input or "").strip().casefold()
    if _CHECKOUT_INFO_RE.search(text):
        return False
    if text in {"결제", "계산", "주문 확정", "checkout", "confirm"}:
        return True
    return bool(_CHECKOUT_COMMAND_RE.search(text))


def _mock_plan(user_input: str, rewrite_result: dict) -> dict:
    lower = user_input.lower()
    if any(word in lower for word in ("검토", "review")):
        intent = "order_review"
    elif _is_checkout_command(user_input):
        intent = "order_confirm"
    elif any(word in lower for word in ("담아", "추가", "빼", "장바구니", "cart")):
        intent = "cart_view"
    elif any(word in lower for word in ("추천", "recommend")):
        intent = "recommend"
    else:
        intent = "menu_info"
    return {
        "schema_version": "1.0",
        "language": rewrite_result["language"],
        "actions": [{
            "action_id": "mock-1",
            "intent": intent,
            "hti_ids": [],
            "targets": [],
            "constraints": [],
            "quantity_mode": "none",
            "requires_tool": intent in {"order_review", "order_confirm", "cart_view"},
            "mutates_state": intent == "order_confirm",
            "blocked_reason": None,
        }],
        "needs_retrieval": intent not in {"order_review", "order_confirm", "cart_view"},
        "needs_clarification": False,
        "clarification_question": None,
        "safety_flags": [],
        "preserve_state": True,
    }


_ORDER_WORD_RE = re.compile(
    r"(?:담아|넣어|"
    r"추가(?:해\s*줘|해\s*주세요|해줘|해주세요)|"
    r"주문(?:할게|할래|해|해줘|해주세요)|"
    r"구매(?:할게|할래|해줘|해주세요|하고\s*싶|하려고\s*해)|"
    r"살게|살래|마실래|마시고\s*싶|"
    r"\b(?:add|order|get|give me|i(?:'d| would) like)\b|"
    r"(?:请给|加入|下单)|(?:ください|注文|追加))",
    re.IGNORECASE,
)
_CLAUSE_BREAK_RE = re.compile(r"[.!?\n。！？]")
_RETAIL_BEAN_IDS = {"M23", "M24", "M25"}


def _is_explicit_order_clause(clause: str) -> bool:
    """Separate purchase wording from information/option questions.

    A bare ``추가`` often means "is an extra shot available?", and ``주세요``
    can occur in "please explain".  Those phrases must never turn an
    ``option_check`` into a cart write.
    """
    if _ORDER_WORD_RE.search(clause):
        return True
    if not re.search(r"(?:주세요|줘|\b주래\b)", clause):
        return False
    if re.search(
        r"(?:알려|설명(?:해)?|확인(?:해)?|추천(?:해)?|"
        r"보여|말해|안내(?:해)?)\s*(?:주세요|줘)",
        clause,
    ):
        return False
    return True


def _catalog_mentions(
    user_input: str,
    catalog_aliases: list[tuple[str, str]] | None,
) -> list[tuple[int, int, str, str]]:
    """Return longest, non-overlapping catalog mentions in source order."""
    lowered = str(user_input).casefold()
    candidates: list[tuple[int, int, str, str]] = []
    for raw_alias, raw_menu_id in catalog_aliases or []:
        alias = str(raw_alias).strip().casefold()
        menu_id = str(raw_menu_id).strip().upper()
        if not alias or not re.fullmatch(r"M\d{2}", menu_id):
            continue
        for match in re.finditer(re.escape(alias), lowered):
            candidates.append((match.start(), match.end(), menu_id, alias))

    # Longest match prevents "바닐라 라떼" from also becoming generic M03.
    selected: list[tuple[int, int, str, str]] = []
    for candidate in sorted(
        candidates,
        key=lambda row: (-(row[1] - row[0]), row[0], row[2]),
    ):
        start, end, _, _ = candidate
        if any(start < chosen_end and end > chosen_start
               for chosen_start, chosen_end, _, _ in selected):
            continue
        selected.append(candidate)
    return sorted(selected, key=lambda row: (row[0], row[1]))


def _source_clause_bounds(text: str, start: int, end: int) -> tuple[int, int]:
    left = 0
    right = len(text)
    for match in _CLAUSE_BREAK_RE.finditer(text):
        if match.end() <= start:
            left = match.end()
        elif match.start() >= end:
            right = match.start()
            break
    return left, right


def _source_clause(text: str, start: int, end: int) -> str:
    left, right = _source_clause_bounds(text, start, end)
    return text[left:right]


def _explicit_order_menu_ids(
    user_input: str,
    catalog_aliases: list[tuple[str, str]] | None,
) -> list[str]:
    """Find catalog menus explicitly requested for purchase in each sentence.

    Retail bean aliases also occur as drink options (for example,
    "디카페인 원두와 오트").  Such text is not a bag-of-beans order without a
    retail cue, so M23--M25 are excluded from coverage in that case.
    """
    ordered: list[str] = []
    source = str(user_input)
    mentions = _catalog_mentions(source, catalog_aliases)
    for position, (start, end, menu_id, _) in enumerate(mentions):
        clause_start, clause_end = _source_clause_bounds(source, start, end)
        clause = source[clause_start:clause_end]
        next_start = (
            mentions[position + 1][0]
            if position + 1 < len(mentions)
            and mentions[position + 1][0] < clause_end
            else None
        )
        # Bind a predicate to the closest mentioned menu.  A final predicate may
        # cover a coordinated list ("아메리카노랑 약과 주세요"), but it must
        # not jump across an information request ("라떼 옵션 알려주고 약과 담아줘").
        local_end = next_start if next_start is not None else clause_end
        local = source[start:local_end]
        explicit = _is_explicit_order_clause(local)
        if not explicit and next_start is not None:
            bridge = source[end:next_start]
            bridge = re.sub(
                r"(?:\d+|한|두|세|네|다섯|여섯|칠|팔|구)\s*(?:개|잔|접시)?",
                "",
                bridge,
            )
            coordinated = bool(re.fullmatch(
                r"(?:[\s,/·]*(?:과|와|랑|이랑|하고|및|또)?)*[\s,/·]*",
                bridge,
            ))
            explicit = coordinated and _is_explicit_order_clause(
                source[next_start:clause_end]
            )
        if not explicit:
            continue
        if menu_id in _RETAIL_BEAN_IDS and not re.search(
            r"(?:200\s*g|봉지|팩|홀빈|원두\s*(?:구매|주문|사|담아|줘|주세요))",
            clause,
            re.IGNORECASE,
        ):
            continue
        if menu_id not in ordered:
            ordered.append(menu_id)
    return ordered


def normalize_explicit_order_actions(
    user_input: str,
    rewrite_result: dict,
    plan: dict,
    catalog_aliases: list[tuple[str, str]] | None = None,
) -> dict:
    """Promote explicit ordered targets mislabelled as option checks.

    The model can see wording such as "시럽은 절반으로 선택" and label
    the first ordered drink as ``option_check``, while retaining only the final menu
    as ``cart_add``.  We promote only an already identified catalog target when the
    source sentence explicitly orders that menu; no target, variant, or option is
    invented.  Missing coverage fails closed instead of allowing a partial order.
    """
    del rewrite_result  # reserved for future clause metadata; source text is authoritative
    normalized = deepcopy(plan)
    ordered_ids = _explicit_order_menu_ids(user_input, catalog_aliases)
    if not ordered_ids:
        return normalized

    actions: list[dict] = []
    for action in normalized.get("actions") or []:
        if (action.get("intent") == "reorder" and action.get("targets")
                and not action.get("blocked_reason")):
            reordered = deepcopy(action)
            reordered.update({
                "intent": "cart_add",
                "quantity_mode": "set",
                "requires_tool": True,
                "mutates_state": True,
            })
            actions.append(reordered)
            continue
        if action.get("intent") != "option_check" or action.get("blocked_reason"):
            actions.append(action)
            continue
        targets = list(action.get("targets") or [])
        promoted = [
            target for target in targets
            if str(target.get("menu_id") or "").upper() in ordered_ids
        ]
        remaining = [target for target in targets if target not in promoted]
        if promoted:
            promoted_action = deepcopy(action)
            promoted_action.update({
                "intent": "cart_add",
                "targets": promoted,
                "quantity_mode": "set",
                "requires_tool": True,
                "mutates_state": True,
                "blocked_reason": None,
            })
            actions.append(promoted_action)
        if remaining:
            remaining_action = deepcopy(action)
            remaining_action["targets"] = remaining
            actions.append(remaining_action)
    normalized["actions"] = actions

    cart_add_ids = {
        str(target.get("menu_id") or "").upper()
        for action in actions
        if action.get("intent") == "cart_add" and not action.get("blocked_reason")
        for target in action.get("targets") or []
    }
    missing = [menu_id for menu_id in ordered_ids if menu_id not in cart_add_ids]
    if missing:
        normalized["needs_clarification"] = True
        normalized["clarification_question"] = (
            "함께 주문하신 메뉴의 구성을 모두 확인해야 해요. "
            "각 메뉴의 온도·크기·수량을 한 번만 다시 알려주세요."
        )
        normalized["_coverage_missing_menu_ids"] = missing
    return normalized


def rewrite(user_input: str, history: list[dict] | None = None,
            session_state: dict | None = None) -> dict:
    if detect_demo_step(user_input) is not None:
        return _mock_rewrite(user_input)
    if is_mock():
        return _mock_rewrite(user_input)
    payload = {
        "user_message": user_input,
        "preferred_language": current_language(),
        "conversation_summary": _history_summary(history),
        "conversation_history": _history_messages(history),
        "session_state": session_state or {},
    }
    try:
        return _invoke(REWRITE_PROMPT, payload, REWRITE_SCHEMA)
    except (json.JSONDecodeError, ValidationError, TypeError, ValueError):
        return _mock_rewrite(user_input)


def classify(user_input: str, rewrite_result: dict, retrieved_documents: str,
             history: list[dict] | None = None,
             session_state: dict | None = None,
             catalog_aliases: list[tuple[str, str]] | None = None) -> dict:
    scripted = demo_plan(
        user_input,
        str(rewrite_result.get("language") or current_language()),
    )
    if scripted is not None:
        return normalize_explicit_order_actions(
            user_input, rewrite_result, scripted, catalog_aliases)
    if is_mock():
        return normalize_explicit_order_actions(
            user_input,
            rewrite_result,
            _mock_plan(user_input, rewrite_result),
            catalog_aliases,
        )
    payload = {
        "user_message": user_input,
        "preferred_language": current_language(),
        "rewrite_result": rewrite_result,
        "conversation_summary": _history_summary(history),
        "conversation_history": _history_messages(history),
        "session_state": session_state or {},
        "catalog_aliases": catalog_aliases or [],
        "retrieved_documents": retrieved_documents,
    }
    try:
        plan = _invoke(INTENT_PROMPT, payload, INTENT_SCHEMA)
    except (json.JSONDecodeError, ValidationError, TypeError, ValueError):
        plan = _mock_plan(user_input, rewrite_result)
    return normalize_explicit_order_actions(
        user_input, rewrite_result, plan, catalog_aliases)


def adapt_plan(user_input: str, rewrite_result: dict, plan: dict) -> dict:
    """새 actions 계약을 기존 키오스크 실행 코드가 읽는 형태로 변환한다."""
    # Keep direct callers and patched tests on the same coverage contract as
    # ``classify``.  The import is local to avoid loading the workbook until the
    # adapter is actually used.
    from .retrieve import _alias_map
    plan = normalize_explicit_order_actions(
        user_input, rewrite_result, plan, _alias_map())
    actions = plan.get("actions") or []
    intents = [action.get("intent") for action in actions]

    # order_review와 order_confirm 모두 웹에서는 구조화된 주문
    # 검토 폼을 여는 동일한 legacy 경로로 연결된다. 실제 확정은
    # /api/order/confirm에서 필수 선택지를 검증한 뒤에만 수행한다.
    if any(intent in {"order_review", "order_confirm"} for intent in intents):
        legacy_intent = "결제"
    elif any(i in {"cart_add", "cart_update", "cart_remove", "cart_view", "cart_clear"}
             for i in intents):
        legacy_intent = "장바구니"
    elif "recommend" in intents:
        legacy_intent = "추천"
    elif "option_check" in intents:
        legacy_intent = "옵션"
    elif any(i in {"out_of_scope", "unsafe_request", "injection_attempt"} for i in intents):
        legacy_intent = "범위밖"
    elif any(i in {"start_order", "reorder", "help", "accessibility", "language_set"} for i in intents):
        legacy_intent = "잡담"
    else:
        legacy_intent = "메뉴질문"

    order_items = []
    if not plan.get("needs_clarification"):
        for action in actions:
            if action.get("intent") != "cart_add" or action.get("blocked_reason"):
                continue
            for target in action.get("targets") or []:
                options = {**_empty_options(), **(target.get("options") or {})}
                order_items.append({
                    "menu_id": target.get("menu_id"),
                    "menu_name": target.get("menu_id") or "",
                    "variant_id": target.get("variant_id"),
                    "temp": None,
                    "size": None,
                    "qty": target.get("quantity"),
                    **options,
                })

    return {
        "intent": legacy_intent,
        "rewritten_query": rewrite_result.get("rewritten_utterance", user_input),
        "language": plan.get("language", rewrite_result.get("language", "ko")),
        "order_items": order_items,
        "rewrite_result": rewrite_result,
        "plan": plan,
    }


def route(user_input: str, history: list[dict] | None = None,
          retrieved_documents: str = "", session_state: dict | None = None,
          catalog_aliases: list[tuple[str, str]] | None = None) -> dict:
    """호환용 진입점. kiosk는 검색을 사이에 넣기 위해 두 함수를 따로 호출한다."""
    rewritten = rewrite(user_input, history, session_state)
    plan = classify(user_input, rewritten, retrieved_documents, history,
                    session_state, catalog_aliases)
    return adapt_plan(user_input, rewritten, plan)
