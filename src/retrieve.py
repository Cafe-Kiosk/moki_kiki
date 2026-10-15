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
    "bean":        ["원두", "에티오피아", "싱글오리진", "하우스 블렌드", "bean",
                    "디카페인", "decaf"],      # 라떼류는 디카페인 원두(B03)로 바꿀 수 있다
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


def _norm(text) -> str:
    """대소문자·공백을 없앤다. '바닐라 라떼'와 '바닐라라떼'를 같은 말로 본다."""
    return re.sub(r"\s+", "", str(text).lower())


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


# 데이터상 한 메뉴의 별칭이지만 실제로는 두 메뉴를 다 가리키는 말 (Q16).
# 엑셀은 그대로 두고 코드에서 되묻기 대상으로 만든다. 더 긴 별칭('디카페인 드립')이
# 먼저 걸리므로 그쪽은 계속 한 메뉴로 확정된다.
AMBIGUOUS_ALIASES = {
    "필터커피": ("M11", "M12"), "드립": ("M11", "M12"), "드립커피": ("M11", "M12"),
    "핸드드립": ("M11", "M12"), "filtercoffee": ("M11", "M12"),
    "dripcoffee": ("M11", "M12"), "drip": ("M11", "M12"),
}

# 2글자 이하 별칭은 공백을 지운 문자열에서 찾지 않고 원문의 단어 경계에서만 찾는다.
# 뒤에 조사가 붙는 것은 경계로 본다 ('모카는', '라떼랑 약과'). 단독 '요'는 빼서 '바라요'(동사)를 막는다.
SHORT_ALIAS_LEN = 2
_JOSA = "이랑|랑|하고|이나|나|도|는|은|이|가|을|를|으로|로|만|와|과|에|의"


def _short_alias_re(alias: str) -> re.Pattern:
    return re.compile(rf"(?<![가-힣a-z0-9]){re.escape(alias)}"
                      rf"(?=$|[^가-힣a-z0-9]|(?:{_JOSA})(?:요)?(?![가-힣]))")


@lru_cache(maxsize=1)
def _alias_index() -> list[tuple[str, tuple[str, ...]]]:
    """정규화한 별칭 → 메뉴 ID들. 긴 것부터.

    '하이볼'처럼 한 별칭이 두 메뉴에 걸리면 ID 둘을 함께 들고 있다 (Q47).
    """
    idx: dict[str, set[str]] = {}
    for alias, mid in _alias_map():
        n = _norm(alias)
        if len(n) >= 2:
            idx.setdefault(n, set()).add(mid)
    for alias, mids in AMBIGUOUS_ALIASES.items():
        idx[_norm(alias)] = set(mids)
    return sorted(((a, tuple(sorted(ids))) for a, ids in idx.items()),
                  key=lambda p: -len(p[0]))


@lru_cache(maxsize=1)
def _alias_attrs() -> dict[str, dict]:
    """메뉴목록 '별칭에 포함된 요청' 열. 예: 아아 → ICED, 디카페인 카페라떼 → B03."""
    wb = openpyxl.load_workbook(DATA_XLSX, data_only=True)
    out: dict[str, dict] = {}
    for m in _sheet_rows(wb, "메뉴목록"):
        for ln in str(m.get("별칭에 포함된 요청") or "").splitlines():
            if "→" not in ln:
                continue
            alias, req = ln.split("→", 1)
            attrs = {}
            for tok in req.split():
                if tok.upper() in ("HOT", "ICED"):
                    attrs["temp"] = tok.upper()
                elif re.fullmatch(r"B\d{2}", tok):
                    attrs["bean"] = tok
            if attrs:
                out[_norm(alias)] = attrs
    return out


def match_menus(text: str) -> tuple[list[str], dict]:
    """긴 별칭부터 찾고, 찾은 구간은 지워서 그 안의 짧은 별칭이 다시 걸리지 않게 한다.

    '에스프레소 마티니'가 에스프레소로, '콜드브루 라떼'가 카페 라떼로 같이 걸리던 문제.
    돌려주는 값: (메뉴·원두 ID 목록, 별칭이 정해 주는 속성 {temp, bean})
    """
    ids: list[str] = []
    attrs: dict = {}
    for alias, mids in alias_hits(text):
        ids += [m for m in mids if m not in ids]
        attrs.update(_alias_attrs().get(alias, {}))
    return ids, attrs


def alias_hits(text: str) -> list[tuple[str, tuple[str, ...]]]:
    """원문에 걸린 (별칭, 메뉴 ID들). 메뉴가 둘 이상인 별칭은 되묻기 대상이다 (Q47)."""
    t = _norm(text)
    raw = str(text).lower()          # 짧은 별칭은 공백이 남은 원문에서 찾는다
    hits = []
    for alias, mids in _alias_index():
        if len(alias) <= SHORT_ALIAS_LEN:
            pat = _short_alias_re(alias)
            if not pat.search(raw):
                continue
            raw = pat.sub("\0" * len(alias), raw)
        else:
            if alias not in t:
                continue
            t = t.replace(alias, "\0" * len(alias))
            # 원문에서도 지워서 그 안의 짧은 별칭이 다시 걸리지 않게 한다
            raw = re.sub(r"\s*".join(map(re.escape, alias)), "\0", raw)
        hits.append((alias, mids))
    return hits


def rule_hits(query: str) -> tuple[set[str], set[str]]:
    """질문에서 메뉴 ID와 정책 ID를 문자열로 찾아낸다. API 호출 없음."""
    q = query.lower()
    menu_ids, policy_ids = set(match_menus(query)[0]), set()
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


# 카페인 조건 — 문구는 가격영양 시트의 카페인(mg) 실측(시연)값으로 판정한다
NO_CAFFEINE_WORDS = ["카페인 없", "카페인없", "무카페인", "노카페인", "논카페인", "임산부", "임신",
                     "pregnan", "caffeine free", "caffeine-free", "no caffeine", "without caffeine"]
LOW_CAFFEINE_WORDS = ["카페인 적", "카페인적", "카페인 낮", "카페인 약", "저카페인", "디카페인",
                      "decaf", "low caffeine", "less caffeine"]
DRINK_CATEGORIES = ("커피", "차/논커피")
# 라우터가 "카페인 없는" 을 "카페인이 없는" 으로 바꿔 쓰면 위 단어 목록이 놓친다 (Q08)
NO_CAFFEINE_RE = re.compile(r"카페인\s*(?:이|은|가|도)?\s*(?:없|안\s*들|빼|0\s*mg)")


DECAF_WORDS = ["디카페인", "decaf"]


def wants_decaf(text: str) -> bool:
    q = str(text).lower()
    return any(w in q for w in DECAF_WORDS)


@lru_cache(maxsize=1)
def _bean_caffeine() -> dict[str, int]:
    """원두 시트의 샷당 카페인(mg)."""
    wb = openpyxl.load_workbook(DATA_XLSX, data_only=True)
    return {b["원두 ID"]: int(b["카페인(mg/샷)"]) for b in _sheet_rows(wb, "원두")}


def caffeine_with_bean(variant: dict, bean: str, extra_shots: int = 0) -> int | None:
    """원두를 바꿨을 때 카페인 = 샷당 카페인 × (기본 샷 + 추가 샷) + 에스프레소 외 카페인 (P10).

    기본 구성(B01·샷 2)으로 계산하면 가격영양 시트 값(120mg)과 같다.
    """
    shots, other = variant.get("기본 샷"), variant.get("에스프레소 외 카페인(mg)")
    if not isinstance(shots, (int, float)):
        return None
    return _bean_caffeine()[bean] * (int(shots) + int(extra_shots or 0)) + int(other or 0)


def decaf_bean_caffeine(menu_id: str) -> int | None:
    """원두 선택이 되는 메뉴를 디카페인 원두(B03)로 바꿨을 때 가장 낮은 카페인. 안 되면 None."""
    from .cart import option_rules, find_variants
    if menu_id not in option_rules()["bean"]["menus"]:
        return None
    vals = [caffeine_with_bean(v, "B03") for v in find_variants(menu_id)]
    vals = [v for v in vals if v is not None]
    return min(vals) if vals else None


def wants_no_caffeine(text: str) -> bool:
    q = str(text).lower()
    return any(w in q for w in NO_CAFFEINE_WORDS) or bool(NO_CAFFEINE_RE.search(q))


@lru_cache(maxsize=1)
def _menu_caffeine() -> dict[str, int]:
    """메뉴별 카페인(mg) 최솟값. 주문 단위가 여럿이면 가장 낮은 값."""
    wb = openpyxl.load_workbook(DATA_XLSX, data_only=True)
    out: dict[str, int] = {}
    for v in _sheet_rows(wb, "가격영양"):
        c = v.get("카페인(mg)")
        if not isinstance(c, (int, float)):
            continue
        mid = str(v["주문 단위 ID"]).split("-")[0]
        out[mid] = min(out.get(mid, int(c)), int(c))
    return out


def filter_by_caffeine(rows: list[dict], no_caffeine: bool = False) -> list[dict]:
    """카페인 실측(시연)값이 있는 메뉴만 남기고, no_caffeine 이면 0mg 만 남긴다.

    추천(taste_candidates)과 조건충돌 대안(conditions.alternatives)이 같이 쓴다.
    """
    caf = _menu_caffeine()
    rows = [r for r in rows if r["menu_id"] in caf]
    if no_caffeine:
        rows = [r for r in rows if caf[r["menu_id"]] == 0]
    return rows


def _is_decaf(r: dict) -> bool:
    return "디카페인" in str(r["name"]) or "디카페인" in r["tags"]


def with_decaf_policy(ids):
    """디카페인 메뉴가 근거에 들어가면 'P10 디카페인은 카페인 0이 아님'을 붙인다."""
    ids = list(ids)
    decaf = {r["menu_id"] for r in _menu_tastes() if _is_decaf(r)} | {"B03"}
    if any(i in decaf for i in ids) and "P10" not in ids:
        ids.append("P10")
    return ids


def taste_candidates(query: str, limit: int = 4) -> list[str]:
    """"산미 적고 고소한" 같은 맛 조건을 점수로 풀어 메뉴 ID를 고른다.

    벡터 검색은 이런 표현에 약하다. 데이터에 1~5 점수가 있으므로 숫자로 거른다.
    카페인은 분류(차/논커피)로 짐작하지 않고 가격영양 시트의 mg 값으로 거른다.
    말차 라떼(70mg)·홍차 밀크티(45mg)는 논커피지만 카페인이 있다 (Q08).
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

    # 카페인 조건 — "없는"은 0mg만, "적은·디카페인"은 낮은 순
    no_caffeine = wants_no_caffeine(q)
    low_caffeine = not no_caffeine and any(w in q for w in LOW_CAFFEINE_WORDS)

    conds = []
    for term, (col, direction) in TASTE_TERMS.items():
        if term not in q:
            continue
        neg = any(n in q for n in ["적", "낮", "없", "덜", "약한", "안 "])
        want_low = (direction == "low") or (direction is None and neg) or (direction == "high" and neg)
        conds.append((col, want_low))
    if not conds and not (no_caffeine or low_caffeine):
        return []

    caf = _menu_caffeine()
    # 주류는 카페인 0이어도 제외한다 (Q42: 카페인과 주류는 별개)
    rows = [r for r in _menu_tastes() if not r["is_alcohol"] and r["category"] != "원두"]
    if wants:
        filtered = [r for r in rows if r["category"] in wants]
        rows = filtered or rows
    if no_caffeine or low_caffeine:
        rows = filter_by_caffeine(rows, no_caffeine)
        if not wants:                         # "마실 만한 거" — 음료만
            rows = [r for r in rows if r["category"] in DRINK_CATEGORIES]

    def score(r):
        s = 0.0
        for col, want_low in conds:
            v = r.get(col)
            if isinstance(v, (int, float)):
                s += (5 - v) if want_low else v
        return s

    rows.sort(key=score, reverse=True)
    if low_caffeine and wants_decaf(q):
        # 디카페인 요청에는 일반 원두 커피(120mg 등)를 넣지 않는다 (Q09).
        # 디카페인 메뉴(M12)와, 원두를 B03 으로 바꿀 수 있는 커피만 B03 기준 카페인으로 줄 세운다.
        eff = {r["menu_id"]: (caf[r["menu_id"]] if _is_decaf(r) else decaf_bean_caffeine(r["menu_id"]))
               for r in rows if r["category"] == "커피"}
        rows = [r for r in rows if eff.get(r["menu_id"]) is not None]
        rows.sort(key=lambda r: eff[r["menu_id"]])          # 안정 정렬: 같은 mg 안에서는 맛 점수 순
        decaf = [r for r in rows if _is_decaf(r)]
        rows = (decaf + [r for r in rows if not _is_decaf(r)])[:limit]
    elif low_caffeine:
        rows.sort(key=lambda r: caf[r["menu_id"]])          # 안정 정렬: 같은 mg 안에서는 맛 점수 순
        decaf = [r for r in rows if _is_decaf(r)]
        if decaf:                                            # 디카페인 메뉴는 꼭 넣는다
            keep = decaf + [r for r in rows if not _is_decaf(r)]
            rows = sorted(keep[:limit], key=lambda r: caf[r["menu_id"]])
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
    if "P10" in with_decaf_policy([*menu_ids, *taste_ids]):
        policy_ids.add("P10")

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
