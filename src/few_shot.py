"""few-shot 라이브러리에서 현재 요청과 관련된 예시만 고른다.

원본 문서는 50개 사례를 담고 있어 매 요청에 전부 넣지 않는다. 사용자 발화,
실행 계획의 안전 플래그와 현재 상태를 기준으로 2~4개만 답변 모델에 제공한다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

from .prompts import PROMPT_DIR

FEW_SHOT_PATH = PROMPT_DIR / "few_shot.md"


@dataclass(frozen=True)
class Example:
    code: str
    category: str
    title: str
    user: str
    expected: str
    validation: str
    scenario: str = ""

    @property
    def searchable(self) -> str:
        return " ".join((self.title, self.user, self.validation, self.scenario)).lower()


_EXAMPLE_RE = re.compile(
    r"^###\s+(?P<code>[A-Z]+\d+)\s+—\s+(?P<title>.+?)\n"
    r"(?P<body>.*?)(?=^###\s+[A-Z]+\d+\s+—|\Z)",
    re.MULTILINE | re.DOTALL,
)


def _field(body: str, name: str) -> str:
    match = re.search(rf"^- {re.escape(name)}:\s*(.+)$", body, re.MULTILINE)
    return match.group(1).strip().strip("`") if match else ""


@lru_cache(maxsize=1)
def load_examples() -> tuple[Example, ...]:
    raw = FEW_SHOT_PATH.read_text(encoding="utf-8")
    examples = []
    for match in _EXAMPLE_RE.finditer(raw):
        body = match.group("body")
        code = match.group("code")
        examples.append(Example(
            code=code,
            category=re.match(r"[A-Z]+", code).group(0),
            title=match.group("title").strip(),
            user=_field(body, "사용자"),
            expected=_field(body, "기대 답변"),
            validation=_field(body, "검증"),
            scenario=_field(body, "상황"),
        ))
    return tuple(examples)


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9가-힣ぁ-んァ-ン一-龯]{2,}", text.lower()))


def _bigrams(text: str) -> set[str]:
    compact = re.sub(r"[^a-z0-9가-힣ぁ-んァ-ン一-龯]", "", text.lower())
    return {compact[i:i + 2] for i in range(max(0, len(compact) - 1))}


_CATEGORY_TERMS = {
    "SEC": (
        "시스템", "system", "프롬프트", "관리자", "규칙 삭제", "tool_results",
        "다른 고객", "다른 좌석", "주문내역 보여", "직원 확인 결과",
    ),
    "ABU": (
        "씨x", "병x", "멍청", "욕", "부숴", "신고", "난리", "공짜", "0원",
        "환불", "현금", "빨리", "몇 번 말", "안 나오면",
    ),
    "ACC": (
        "처음", "모르겠", "이해", "글씨", "화면", "소리", "안 들", "볼 수 없",
        "말하기 싫", "버튼", "긴 말", "하나씩", "손이 불편", "확대", "tts",
    ),
    "SAFE": (
        "알레르기", "임신", "카페인", "디카페인", "미성년", "성인", "주류", "술",
        "시럽", "얼음", "할인", "품절", "결제", "확정", "가격", "사진", "재고",
    ),
    "AMB": (
        "아무거나", "그거", "저거", "아까", "원래", "아니", "중간", "하나만",
        "덜 달", "더 달", "진하게", "연하게", "취소", "바꿔", "질문하지 마",
    ),
}


def _plan_categories(plan: dict | None, session_state: dict | None) -> set[str]:
    categories = set()
    plan = plan or {}
    flags = set(plan.get("safety_flags") or [])
    intents = {action.get("intent") for action in plan.get("actions") or []}
    if flags & {"injection"} or intents & {"injection_attempt"}:
        categories.add("SEC")
    if flags & {"allergy", "alcohol", "medical"}:
        categories.add("SAFE")
    if flags & {"conflict", "unknown_state"} or plan.get("needs_clarification"):
        categories.add("AMB")
    if "accessibility" in intents:
        categories.add("ACC")
    if intents & {"unsafe_request"}:
        categories.add("ABU")
    if (session_state or {}).get("cart_status") == "pending_staff_check":
        categories.add("SAFE")
    return categories


def select_examples(user_input: str, plan: dict | None = None,
                    session_state: dict | None = None, limit: int = 3) -> list[Example]:
    limit = max(2, min(4, limit))
    query = user_input.lower()
    query_tokens = _tokens(query)
    query_bigrams = _bigrams(query)
    signaled = _plan_categories(plan, session_state)
    for category, terms in _CATEGORY_TERMS.items():
        if any(term in query for term in terms):
            signaled.add(category)

    ranked = []
    for order, example in enumerate(load_examples()):
        example_tokens = _tokens(example.searchable)
        example_bigrams = _bigrams(example.title + " " + example.user)
        score = 5.0 * len(query_tokens & example_tokens)
        if query_bigrams:
            score += 8.0 * len(query_bigrams & example_bigrams) / len(query_bigrams)
        if example.category in signaled:
            score += 12.0
        if not signaled and example.category == "AMB":
            score += 1.0
        ranked.append((score, -order, example))

    ranked.sort(key=lambda row: (row[0], row[1]), reverse=True)
    return [example for _, _, example in ranked[:limit]]


def render_examples(user_input: str, plan: dict | None = None,
                    session_state: dict | None = None, limit: int = 3) -> str:
    selected = select_examples(user_input, plan, session_state, limit)
    blocks = [
        "아래 예시는 응답 방식 참고용이며 메뉴·가격·상태의 사실 근거가 아니다. "
        "현재 검색 문서와 서버 실행 결과가 다르면 반드시 현재 값을 따른다."
    ]
    for example in selected:
        blocks.append(
            f"[{example.code} — {example.title}]\n"
            f"사용자 예시: {example.user}\n"
            f"응답 예시: {example.expected}\n"
            f"검증 기준: {example.validation}"
        )
    return "\n\n".join(blocks)
