"""하이브리드 검색 — 별칭 정확매칭 + 벡터 유사도.

순수 벡터 검색만 쓰면 짧은 한국어 질문에서 자주 빗나간다.
실제로 "아아 하나"가 약과로, "두유로 바꾸면 돈 더 내요?"가 원두 선택으로 갔다.
데이터팀이 별칭과 정책 본문을 잘 적어 두었으므로, 문자열이 정확히 겹치는 경우는
벡터에 맡기지 않고 규칙으로 먼저 집어낸다.

  1단계 별칭·키워드 매칭 : 정확도가 높고 비용이 0이다 (API 호출 없음)
  2단계 벡터 검색        : 1단계가 놓치는 의미 기반 질문을 담당한다
"""
from __future__ import annotations
import re, openpyxl
from functools import lru_cache
from .config import DATA_XLSX, TOP_K, DISTANCE_THRESHOLD
from .documents import _sheet_rows

# 정책 문서를 부르는 말들 — 데이터의 정책 본문에 나오는 표현에서 뽑았다
POLICY_KEYWORDS = {
    "P02": ["좌석", "자리", "테이블", "몇 번", "table"],
    "P03": ["사이즈", "크기", "온도", "핫", "아이스", "hot", "iced", "size", "라지", "스몰"],
    "P04": ["포장", "테이크아웃", "매장", "to go", "takeout", "take out"],
    "P05": ["확정", "주문할게", "결제", "checkout", "confirm"],
    "P07": ["기프티콘", "쿠폰", "적립", "포인트", "영수증", "예약", "재고", "대기",
            "분할", "나눠서", "할인", "gifticon", "coupon", "receipt", "split"],
    "P08": ["직원", "호출", "바리스타", "도움", "staff", "help"],
    "P09": ["알레르기", "성분", "글루텐", "비건", "할랄", "allerg", "gluten", "vegan"],
    "P10": ["카페인", "칼로리", "열량", "영양", "당류", "디카페인", "임산부", "임신",
            "caffeine", "calorie", "sugar", "decaf", "pregnan"],
    "P12": ["인기", "잘 팔리", "베스트", "추천", "popular", "best"],
    "P13": ["원두 구매", "원두 사", "홀빈", "200g", "beans"],
    "P15": ["주류", "술", "성인", "나이", "민증", "alcohol", "adult", "id check"],
    "P17": ["몇 개", "몇 잔", "접시", "낱개", "how many"],
    "P19": ["도수", "알코올", "abv", "%"],
}


# 옵션 문서를 부르는 말들
OPTION_KEYWORDS = {
    "bean":        ["원두", "에티오피아", "싱글오리진", "하우스 블렌드", "bean"],
    "extra_shots": ["샷", "shot", "진하게", "연하게"],
    "milk":        ["우유", "두유", "오트", "저지방", "무지방", "milk", "soy", "oat", "lactose"],
    "sweetness":   ["덜 달게", "단맛", "시럽", "당도", "달게", "less sweet", "sweet"],
    "ice":         ["얼음", "ice cube", "얼음 적게", "얼음 많이"],
    "warming":     ["데워", "따뜻하게 해", "warm up", "heat"],
}

# 맛 표현 → (칼럼, 방향). 추천 질문을 숫자 조건으로 바꾼다.
TASTE_TERMS = {
    "산미": ("산미", None), "신맛": ("산미", None), "상큼": ("산미", "high"),
    "고소": ("쓴맛", "low"), "달": ("단맛", "high"), "단": ("단맛", "high"),
    "쓴": ("쓴맛", "high"), "진한": ("바디", "high"), "가벼": ("바디", "low"),
    "부드러": ("쓴맛", "low"),
}


@lru_cache(maxsize=1)
def _alias_map() -> list[tuple[str, str]]:
    """(검색어, 메뉴 ID) 목록. 긴 별칭부터 매칭되도록 정렬한다."""
    wb = openpyxl.load_workbook(DATA_XLSX, data_only=True)
    pairs: list[tuple[str, str]] = []
    for m in _sheet_rows(wb, "메뉴목록"):
        mid = m["메뉴 ID"]
        names = [str(m["메뉴명"]), str(m.get("영문명", ""))]
        names += [a.strip() for a in str(m.get("별칭", "")).split(",")]
        for n in names:
            n = n.strip()
            if len(n) >= 2:
                pairs.append((n.lower(), mid))
    for b in _sheet_rows(wb, "원두"):
        pairs.append((str(b["원두명"]).lower(), b["원두 ID"]))
    return sorted(set(pairs), key=lambda p: -len(p[0]))


def rule_hits(query: str) -> tuple[set[str], set[str]]:
    """질문에서 메뉴 ID와 정책 ID를 문자열로 찾아낸다. API 호출 없음."""
    q = query.lower()
    menu_ids, policy_ids = set(), set()
    for alias, mid in _alias_map():
        if alias in q:
            menu_ids.add(mid)
    for pid, words in POLICY_KEYWORDS.items():
        if any(w in q for w in words):
            policy_ids.add(pid)
    for oid, words in OPTION_KEYWORDS.items():
        if any(w in q for w in words):
            policy_ids.add(oid)      # 옵션 ID도 같은 통로로 넘긴다
    return menu_ids, policy_ids


@lru_cache(maxsize=1)
def _menu_tastes() -> list[dict]:
    wb = openpyxl.load_workbook(DATA_XLSX, data_only=True)
    out = []
    for m in _sheet_rows(wb, "메뉴목록"):
        out.append({
            "menu_id": m["메뉴 ID"], "name": m["메뉴명"], "category": m["분류"],
            "단맛": m.get("단맛 1~5"), "산미": m.get("산미 1~5"),
            "쓴맛": m.get("쓴맛 1~5"), "바디": m.get("바디 1~5"),
            "is_alcohol": str(m.get("주류 구분", "")).startswith("주류 포함"),
            "tags": str(m.get("추천 태그", "")),
        })
    return out


def taste_candidates(query: str, limit: int = 4) -> list[str]:
    """"산미 적고 고소한" 같은 맛 조건을 점수로 풀어 메뉴 ID를 고른다.

    벡터 검색은 이런 표현에 약하다. 데이터에 1~5 점수가 있으므로 숫자로 거른다.
    """
    q = query.lower()

    # 분류 힌트 — "커피 추천"에 차가 나오지 않게 한다
    wants = set()
    if any(w in q for w in ["커피", "coffee", "라떼", "아메리카노"]):
        wants.add("커피")
    if any(w in q for w in ["빵", "디저트", "케이크", "dessert", "cake", "bread"]):
        wants.add("디저트")
    if any(w in q for w in ["차", "티", "tea", "논커피"]):
        wants.add("차/논커피")

    # 카페인 조건 — 임산부·카페인 질문은 숫자로 거른다
    low_caffeine = any(w in q for w in
                       ["임산부", "임신", "카페인 없", "카페인 적", "무카페인",
                        "디카페인", "pregnan", "caffeine free", "no caffeine", "decaf"])

    conds = []
    for term, (col, direction) in TASTE_TERMS.items():
        if term not in q:
            continue
        neg = any(n in q for n in ["적", "낮", "없", "덜", "약한", "안 "])
        want_low = (direction == "low") or (direction is None and neg) or (direction == "high" and neg)
        conds.append((col, want_low))
    if not conds and not low_caffeine:
        return []

    rows = [r for r in _menu_tastes() if not r["is_alcohol"] and r["category"] != "원두"]
    if wants:
        filtered = [r for r in rows if r["category"] in wants]
        rows = filtered or rows
    if low_caffeine:
        rows = [r for r in rows
                if r["category"] == "차/논커피" or "디카페인" in r["name"]
                or "디카페인" in r["tags"]]

    def score(r):
        s = 0.0
        for col, want_low in conds:
            v = r.get(col)
            if isinstance(v, (int, float)):
                s += (5 - v) if want_low else v
        return s

    rows.sort(key=score, reverse=True)
    # 분류 힌트가 둘 이상이면 각 분류에서 고르게 뽑는다 ("커피랑 빵 추천")
    if len(wants) > 1:
        out, per = [], max(1, limit // len(wants))
        for c in wants:
            out += [r["menu_id"] for r in rows if r["category"] == c][:per]
        return out[:limit]
    return [r["menu_id"] for r in rows[:limit]]


def hybrid_search(store, query: str, k: int = TOP_K,
                  threshold: float = DISTANCE_THRESHOLD):
    """규칙으로 찾은 문서를 앞에 놓고, 벡터 검색 결과로 채운다.

    돌려주는 값: (최종 문서 목록, 디버그용 내역)
    """
    menu_ids, policy_ids = rule_hits(query)
    taste_ids = [t for t in taste_candidates(query) if t not in menu_ids]

    by_id = {}
    for doc_id, doc in store.docstore._dict.items():
        md = doc.metadata
        key = md.get("menu_id") or md.get("policy_id") or md.get("bean_id") or md.get("option_id")
        if key:
            by_id[key] = doc

    picked, seen = [], set()
    trace = []

    for mid in menu_ids:
        if mid in by_id and mid not in seen:
            seen.add(mid); picked.append(by_id[mid])
            trace.append(("규칙·별칭", by_id[mid].metadata["name"], None))
    for pid in policy_ids:
        if pid in by_id and pid not in seen:
            seen.add(pid); picked.append(by_id[pid])
            trace.append(("규칙·정책/옵션", by_id[pid].metadata["name"], None))
    for tid in taste_ids:
        if tid in by_id and tid not in seen:
            seen.add(tid); picked.append(by_id[tid])
            trace.append(("맛 점수", by_id[tid].metadata["name"], None))

    for doc, score in store.similarity_search_with_score(query, k=k + 2):
        md = doc.metadata
        key = md.get("menu_id") or md.get("policy_id") or md.get("bean_id") or md.get("option_id")
        if key in seen:
            continue
        if score > threshold:
            trace.append(("벡터·기준값초과", md["name"], round(float(score), 3)))
            continue
        seen.add(key); picked.append(doc)
        trace.append(("벡터", md["name"], round(float(score), 3)))
        if len(picked) >= k + len(menu_ids) + len(policy_ids):
            break

    return picked[: k + 3], trace


def as_context(docs) -> str:
    """검색된 문서를 모델에게 넘길 컨텍스트로 만든다. 전체 본문을 쓴다."""
    return "\n\n---\n\n".join(d.metadata.get("full", d.page_content) for d in docs)
