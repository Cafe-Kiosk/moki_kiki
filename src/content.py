"""웹에서 데이터·프롬프트 연결 상태와 답변 근거를 보여 주는 도우미."""
from __future__ import annotations

from collections import Counter
from functools import lru_cache

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
        path.stem for path in (ROOT / "assets" / "menu").glob("M*.jpg")
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
