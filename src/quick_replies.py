"""확인 질문을 눌러서 답할 수 있는 퀵 리플라이로 변환한다."""
from __future__ import annotations

import re

from .cart import find_variants, menu_by_id


def _unique(values):
    seen, result = set(), []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _reply(label: str, value: str | None = None) -> dict[str, str]:
    return {"label": label.strip(), "value": (value or label).strip()}


def _menu_ids(plan: dict, rewrite_result: dict) -> list[str]:
    ids = []
    for action in plan.get("actions") or []:
        for target in action.get("targets") or []:
            if target.get("menu_id"):
                ids.append(str(target["menu_id"]))
    for query in rewrite_result.get("queries") or []:
        ids.extend(str(mid) for mid in query.get("menu_ids") or [])
    return _unique(ids)


def _variant_replies(menu_id: str, question: str) -> list[dict[str, str]]:
    variants = find_variants(menu_id)
    if len(variants) < 2:
        return []

    q = question.lower()
    asks_temp = any(word in q for word in ("온도", "따뜻", "차갑", "핫", "아이스", "hot", "iced"))
    asks_size = any(word in q for word in ("크기", "사이즈", "size", " s", " l"))
    asks_variant = any(word in q for word in ("구성", "옵션", "variant"))
    if not (asks_temp or asks_size or asks_variant):
        return []
    temps = _unique(str(v.get("온도")) for v in variants if v.get("온도") not in (None, "NA"))
    sizes = _unique(str(v.get("크기")) for v in variants if v.get("크기") not in (None, "ONE"))

    temp_label = {"HOT": "따뜻하게", "ICED": "아이스"}
    if asks_temp and not asks_size and len(temps) > 1:
        return [_reply(temp_label.get(temp, temp), f"{temp}으로 할게요") for temp in temps]
    if asks_size and not asks_temp and len(sizes) > 1:
        return [_reply(f"{size} 사이즈", f"{size} 사이즈로 할게요") for size in sizes]

    replies = []
    for variant in variants:
        temp, size = str(variant.get("온도")), str(variant.get("크기"))
        bits = []
        if temp != "NA":
            bits.append(temp_label.get(temp, temp))
        if size != "ONE":
            bits.append(f"{size} 사이즈")
        if not bits:
            continue
        label = " · ".join(bits)
        replies.append(_reply(label, f"{label}로 할게요"))
    return replies[:4]


def _question_replies(question: str) -> list[dict[str, str]]:
    if any(word in question.lower() for word in ("수량", "몇 잔", "몇 개", "quantity")):
        return [_reply(f"{qty}개", f"{qty}개로 할게요") for qty in range(1, 4)]

    # 번호나 글머리표로 제시된 선택지
    listed = re.findall(r"(?:^|\n)\s*(?:\d+[.)]|[-•])\s*([^\n]{1,40})", question)
    if 2 <= len(listed) <= 4:
        return [_reply(item.rstrip(".?! "), f"{item.rstrip('.?! ')}로 할게요") for item in listed]

    # "A와 B 중", "A 또는 B 중" 형태
    match = re.search(
        r"([^\n?.]{1,45}?)\s*(?:와|과|또는)\s*([^\n?.]{1,45}?)\s*중(?:에서)?",
        question,
    )
    if match:
        choices = []
        for raw in match.groups():
            value = re.sub(r"^(?:혹시|그러면|그럼|메뉴는)\s*", "", raw).strip(" ,")
            choices.append(_reply(value, f"{value}로 할게요"))
        return choices

    # 짧은 슬래시 선택지: HOT / ICED, S / L 등
    slash = re.search(r"\b([A-Za-z]{1,8})\s*/\s*([A-Za-z]{1,8})\b", question)
    if slash:
        return [_reply(value, f"{value}로 할게요") for value in slash.groups()]

    if any(phrase in question for phrase in ("해드릴까요", "진행할까요", "맞나요", "괜찮을까요")):
        return [
            _reply("네, 좋아요", "네, 그렇게 해주세요"),
            _reply("아니요", "아니요, 다른 선택지를 볼게요"),
        ]
    return []


def build_quick_replies(question: str, plan: dict | None = None,
                        rewrite_result: dict | None = None) -> list[dict[str, str]]:
    """실제 카탈로그를 우선하고, 없을 때만 질문 문구에서 선택지를 찾는다."""
    plan = plan or {}
    rewrite_result = rewrite_result or {}
    menu_ids = _menu_ids(plan, rewrite_result)

    if 2 <= len(menu_ids) <= 4:
        replies = []
        for menu_id in menu_ids:
            menu = menu_by_id(menu_id)
            if menu:
                name = str(menu["메뉴명"])
                replies.append(_reply(name, f"{name}로 할게요"))
        if len(replies) >= 2:
            return replies

    if len(menu_ids) == 1:
        replies = _variant_replies(menu_ids[0], question)
        if len(replies) >= 2:
            return replies

    return _question_replies(question)[:4]


def is_choice_prompt(text: str) -> bool:
    return any(word in text for word in (
        "선택", "골라", "어느", "무엇을", "어떤", "할까요", "하시겠", "원하세요",
        "확인이 필요", "알려주세요", "알려주시겠", "맞나요", "수량", "몇 잔", "몇 개",
        "choose", "which", "would you like", "how many",
    ))
