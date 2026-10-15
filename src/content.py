"""웹에서 데이터·프롬프트 연결 상태와 답변 근거를 보여 주는 도우미."""
from __future__ import annotations

from collections import Counter
from functools import lru_cache
import re

from .cart import list_menus
from .config import ROOT
from .documents import build_documents
from .prompts import load as load_prompt, load_schema

SOURCE_LABELS = {
    "menu": "메뉴",
    "bean": "원두",
    "policy": "매장 안내",
    "glossary": "용어 안내",
}

REQUIRED_PROMPT_SECTIONS = (
    "[모키 캐릭터]",
    "[자연스러운 대화 흐름]",
    "[입력 계약]",
    "[근거 제한]",
    "[안전·영양]",
)

MENU_IMAGE_REQUEST_TERMS = (
    "사진", "이미지", "생김새", "모습",
    "photo", "image", "picture", "写真", "画像", "图片", "照片",
)
MENU_IMAGE_FOLLOWUP_TERMS = (
    "사진도", "이미지도", "모습도", "아까", "추천한",
    "그 메뉴", "그거", "그것", "이거", "이것", "해당 메뉴",
    "photo too", "image too", "that one", "those", "it look",
)


@lru_cache(maxsize=1)
def content_status() -> dict:
    """엑셀·RAG·사진·시스템 프롬프트가 서로 맞는지 검사한다."""
    menus = list_menus()
    documents = build_documents()
    menu_ids = {str(menu["메뉴 ID"]) for menu in menus}
    rag_menu_ids = {
        str(doc.metadata["entity_id"])
        for doc in documents
        if doc.metadata.get("type") == "menu"
    }
    image_ids = {
        path.stem for path in (ROOT / "public" / "assets" / "menu").glob("M*.jpg")
    }
    system_prompt = load_prompt("system")
    rewrite_prompt = load_prompt("rewrite")
    intent_prompt = load_prompt("intent")
    document_types = Counter(doc.metadata.get("type") for doc in documents)
    errors: list[str] = []

    if len(menu_ids) != 33:
        errors.append("엑셀 판매 메뉴는 33개여야 합니다.")
    if document_types != {"menu": 66, "bean": 6, "policy": 38, "glossary": 12}:
        errors.append("RAG 문서 122개의 유형별 구성이 올바르지 않습니다.")
    if menu_ids != rag_menu_ids:
        errors.append("엑셀 메뉴와 RAG 메뉴가 일치하지 않습니다.")
    if menu_ids != image_ids:
        errors.append("메뉴와 사진 파일이 일치하지 않습니다.")
    if not all(section in system_prompt for section in REQUIRED_PROMPT_SECTIONS):
        errors.append("시스템 프롬프트의 필수 응대 규칙이 누락되었습니다.")
    if "conversation_history" not in rewrite_prompt or "conversation_history" not in intent_prompt:
        errors.append("대화 문맥을 전달하는 프롬프트 계약이 누락되었습니다.")
    if load_schema("rewrite").get("type") != "object" or load_schema("intent").get("type") != "object":
        errors.append("프롬프트 출력 스키마를 불러오지 못했습니다.")

    return {
        "ready": not errors,
        "menu_count": len(menu_ids),
        "document_count": len(documents),
        "image_count": len(image_ids),
        "prompt_ready": not any("프롬프트" in error for error in errors),
        "errors": errors,
    }


def source_cards(documents) -> list[dict[str, str]]:
    """검색 내부 점수 대신 고객이 이해할 수 있는 출처 목록을 만든다."""
    cards: list[dict[str, str]] = []
    seen: set[str] = set()
    for document in documents:
        metadata = document.metadata
        source_id = str(metadata.get("id") or metadata.get("entity_id") or "")
        entity_id = str(metadata.get("entity_id") or source_id).split(":", 1)[0]
        if entity_id in seen:
            continue
        seen.add(entity_id)
        kind = str(metadata.get("type") or "")
        cards.append({
            "id": entity_id,
            "label": SOURCE_LABELS.get(kind, "안내"),
            "name": str(metadata.get("name") or entity_id),
        })
    return cards


def wants_menu_images(text: str) -> bool:
    """메뉴 대표 사진을 보여 달라는 요청인지 확인한다."""
    lowered = str(text or "").casefold()
    return any(term in lowered for term in MENU_IMAGE_REQUEST_TERMS)


@lru_cache(maxsize=1)
def _menu_image_catalog() -> tuple[dict[str, dict], tuple[tuple[str, str], ...]]:
    """엑셀 메뉴를 웹 사진용 안전한 목록과 별칭 목록으로 만든다."""
    catalog: dict[str, dict] = {}
    aliases: list[tuple[str, str]] = []
    for row in list_menus():
        menu_id = str(row.get("메뉴 ID") or "").upper()
        if not re.fullmatch(r"M\d{2}", menu_id):
            continue
        image_file = ROOT / "public" / "assets" / "menu" / f"{menu_id}.jpg"
        if not image_file.is_file():
            continue
        catalog[menu_id] = row
        names = [str(row.get("메뉴명") or ""), str(row.get("영문명") or "")]
        names.extend(str(row.get("별칭") or "").split(","))
        for name in names:
            normalized = name.strip().casefold()
            if len(normalized) >= 2:
                aliases.append((normalized, menu_id))
    # 긴 메뉴명을 먼저 보아 '초코 라떼'에서 일반 '라떼'를 중복 선택하지 않는다.
    aliases = sorted(set(aliases), key=lambda pair: (-len(pair[0]), pair[0], pair[1]))
    return catalog, tuple(aliases)


def _mentioned_menu_ids(text: str) -> list[str]:
    """문장의 메뉴 ID·이름·별칭을 긴 표현 우선으로 찾는다."""
    lowered = str(text or "").casefold()
    if not lowered:
        return []
    catalog, aliases = _menu_image_catalog()
    found: list[str] = []

    for match in re.finditer(r"(?<![A-Za-z0-9])M\d{2}(?![A-Za-z0-9])", str(text), re.I):
        menu_id = match.group(0).upper()
        if menu_id in catalog and menu_id not in found:
            found.append(menu_id)

    matches: list[tuple[int, int, str]] = []
    for alias, menu_id in aliases:
        if alias.isascii():
            pattern = rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])"
        else:
            pattern = re.escape(alias)
        for match in re.finditer(pattern, lowered):
            matches.append((match.start(), match.end(), menu_id))

    # 같은 표현이 두 메뉴의 정식 별칭(예: 하이볼)이면 둘 다 유지한다.
    # 다만 '바닐라 라떼' 안의 '라떼'처럼 부분만 겹치는 짧은 별칭은 뺀다.
    accepted_spans: list[tuple[int, int]] = []
    for start, end, menu_id in sorted(matches, key=lambda item: (item[0], -(item[1] - item[0]), item[2])):
        exact_existing = (start, end) in accepted_spans
        overlaps = any(start < other_end and end > other_start
                       for other_start, other_end in accepted_spans)
        if overlaps and not exact_existing:
            continue
        if not overlaps:
            accepted_spans.append((start, end))
        if menu_id not in found:
            found.append(menu_id)
    return found


def _document_menu_ids(documents) -> list[str]:
    catalog, _ = _menu_image_catalog()
    found: list[str] = []
    for document in documents or []:
        metadata = getattr(document, "metadata", {}) or {}
        kind = str(metadata.get("type") or "").casefold()
        if kind not in {"menu", "메뉴"}:
            continue
        menu_id = str(metadata.get("entity_id") or metadata.get("menu_id")
                      or metadata.get("id") or "").split(":", 1)[0].upper()
        if menu_id in catalog and menu_id not in found:
            found.append(menu_id)
    return found


def menu_image_cards(
    documents,
    *,
    user_message: str = "",
    rewritten: str = "",
    reply: str = "",
    history: list[dict] | None = None,
    limit: int = 3,
) -> list[dict[str, str]]:
    """
    사진 요청에 대해 직전 대화까지 이어 붙인 검증된 메뉴 카드를 만든다.

    JSONL의 ``images/M14.png``는 원본 산출물 표기이며 공개 URL이 아니다.
    브라우저에는 엑셀에서 추출·검증한 ``/assets/menu/Mxx.jpg``만 보낸다.
    """
    if not wants_menu_images(user_message) or limit <= 0:
        return []

    direct_ids = _mentioned_menu_ids(user_message)
    rewritten_ids = _mentioned_menu_ids(rewritten)
    reply_ids = _mentioned_menu_ids(reply)
    document_ids = _document_menu_ids(documents)
    history_ids: list[str] = []
    for message in reversed(history or []):
        ids = _mentioned_menu_ids(str(message.get("content") or ""))
        if ids:
            history_ids = ids
            break

    lowered = str(user_message).casefold()
    looks_like_followup = any(term in lowered for term in MENU_IMAGE_FOLLOWUP_TERMS)
    # 재작성기가 '아메리카노 말고 라떼' 같은 부정 대상을 걸러
    # 직접 후보를 정확히 줄였다면 그 부분집합을 우선한다.
    if direct_ids and rewritten_ids and set(rewritten_ids) < set(direct_ids):
        selected = rewritten_ids
    elif direct_ids:
        selected = direct_ids
    elif rewritten_ids:
        selected = rewritten_ids
    elif reply_ids:
        selected = reply_ids
    elif looks_like_followup and history_ids:
        selected = history_ids
    elif document_ids:
        selected = document_ids
    else:
        selected = history_ids

    catalog, _ = _menu_image_catalog()
    cards: list[dict[str, str]] = []
    for menu_id in selected[:max(0, min(limit, 3))]:
        row = catalog.get(menu_id)
        if not row:
            continue
        name = str(row.get("메뉴명") or menu_id)
        description = str(row.get("사진 설명") or f"{name} 대표 이미지")
        cards.append({
            "id": menu_id,
            "name": name,
            "image": f"/assets/menu/{menu_id}.jpg",
            "alt": f"{name} 대표 이미지",
            "description": description,
            "representative_variant_id": str(row.get("사진 기준 주문 단위") or ""),
        })
    return cards
