"""예산 추천 — "2만 원밖에 없는데 두 사람 음료랑 간식 추천해 줘".

조합은 코드가 고르고, 모델은 calc 의 [예산안] 줄을 전달만 한다. 장바구니에는 담지 않는다.

  조건 : 1인당 음료 1개, 요청하면 디저트 포함(1개 ~ 인원수), 주류 제외, 합계 ≤ 예산
  가격 : 온도·크기가 여러 개인 메뉴는 가장 싼 구성으로 계산하고 그렇게 표시한다
  고르기: 판매 통계가 없으므로(P12) 인기순은 쓰지 않는다.
          페어링 ID가 맞는 음료·디저트 쌍, 음료끼리의 맛 차이, 예산 활용으로 점수를 매기고
          서로 겹치지 않는 2~3안을 고른다. 같은 메뉴 2잔도 허용한다.
"""
from __future__ import annotations
import re
from dataclasses import dataclass
from functools import lru_cache
from itertools import combinations_with_replacement

from .cart import _tables, find_variants, is_alcohol, menu_by_id, unit_label

DRINK_CATS = ("커피", "차/논커피")
MAX_PEOPLE = 4          # 조합 전체를 훑는다. 4명이면 음료 조합 약 1만 개로 충분히 빠르다
TASTE_COLS = ("단맛 1~5", "산미 1~5", "쓴맛 1~5", "바디 1~5")


@dataclass(frozen=True)
class Pick:
    menu_id: str
    name: str
    price: int
    label: str          # '' 또는 'S(가장 싼 구성)'

    def text(self) -> str:
        return f"{self.name}" + (f" {self.label}" if self.label else "") + f" {self.price:,}원"


def _cheapest(menu_id: str) -> Pick | None:
    vs = find_variants(menu_id)
    if not vs:
        return None
    lo = min(int(v["가격(원)"]) for v in vs)
    label = ""
    if len({int(v["가격(원)"]) for v in vs}) > 1:          # 구성마다 가격이 다를 때만 표시
        low = [v for v in vs if int(v["가격(원)"]) == lo]
        sizes = {str(v.get("크기")) for v in low}
        temps = {str(v.get("온도")) for v in low}
        fixed = [*sizes] if len(sizes) == 1 else [*temps] if len(temps) == 1 else []
        label = f"{fixed[0] if fixed else ''}(가장 싼 구성)".strip()
    return Pick(menu_id, str(menu_by_id(menu_id)["메뉴명"]), lo, label)


@lru_cache(maxsize=1)
def _pools() -> tuple[tuple[Pick, ...], tuple[Pick, ...]]:
    drinks, desserts = [], []
    for mid, m in _tables()[0].items():
        if is_alcohol(mid):
            continue
        p = _cheapest(mid)
        if p is None:
            continue
        if m["분류"] in DRINK_CATS:
            drinks.append(p)
        elif m["분류"] == "디저트":
            desserts.append(p)
    return tuple(drinks), tuple(desserts)


def _pairs(mid: str) -> set[str]:
    return {x.strip() for x in str((menu_by_id(mid) or {}).get("페어링 ID", "")).split(",") if x.strip()}


def _taste(mid: str) -> tuple:
    m = menu_by_id(mid) or {}
    return tuple(m.get(c) or 0 for c in TASTE_COLS)


@dataclass
class Plan:
    drinks: tuple[Pick, ...]
    desserts: tuple[Pick, ...]
    budget: int

    @property
    def total(self) -> int:
        return sum(p.price for p in self.drinks + self.desserts)

    @property
    def ids(self) -> set[str]:
        return {p.menu_id for p in self.drinks + self.desserts}

    def score(self, people: int) -> float:
        pair_hits = sum(1 for d in self.drinks for s in self.desserts
                        if s.menu_id in _pairs(d.menu_id) or d.menu_id in _pairs(s.menu_id))
        distinct = {d.menu_id for d in self.drinks}
        tastes = [_taste(m) for m in distinct]
        spread = 0.0
        if len(tastes) > 1:
            dists = [sum(abs(a - b) for a, b in zip(x, y))
                     for i, x in enumerate(tastes) for y in tastes[i + 1:]]
            spread = min(1.0, sum(dists) / len(dists) / 8)   # 맛이 극단적인 메뉴만 계속 뽑히지 않게 상한
        return (2.0 * pair_hits
                + 1.0 * (len(distinct) - 1) + 0.5 * spread
                + 1.0 * (len(self.desserts) == people)     # 디저트도 1인당 하나면 가산
                + 1.5 * self.total / self.budget)          # 예산을 너무 남기지 않게

    def text(self) -> str:
        def group(picks):
            seen: dict[str, list[Pick]] = {}
            for p in picks:
                seen.setdefault(p.menu_id, []).append(p)
            out = []
            for ps in seen.values():
                counted = unit_label(ps[0].menu_id, len(ps))      # '약과(2개입) 2접시' (P17)
                if counted:
                    out.append(counted + (f" (접시당 {ps[0].price:,}원)" if len(ps) > 1
                                          else f" {ps[0].price:,}원"))
                else:
                    out.append(ps[0].text() + (f" ×{len(ps)}" if len(ps) > 1 else ""))
            return out
        return " + ".join(group(self.drinks) + group(self.desserts))


def plans(budget: int, people: int, want_dessert: bool, limit: int = 3) -> list[Plan]:
    drinks, desserts = _pools()
    cands = []
    dessert_sets = [()]
    if want_dessert:
        dessert_sets = [c for n in range(1, people + 1)
                        for c in combinations_with_replacement(desserts, n)]
    for ds in combinations_with_replacement(drinks, people):
        base = sum(p.price for p in ds)
        if base > budget:
            continue
        for ss in dessert_sets:
            if want_dessert and not ss:
                continue
            pl = Plan(ds, ss, budget)
            if pl.total <= budget:
                cands.append(pl)
    cands.sort(key=lambda p: (-p.score(people), -p.total,
                              [x.menu_id for x in p.drinks + p.desserts]))
    def drink_ids(p): return {x.menu_id for x in p.drinks}
    chosen: list[Plan] = []
    def sweets(p): return tuple(sorted(x.menu_id for x in p.desserts))
    # 1차: 앞선 안과 음료가 하나도 겹치지 않고 디저트 구성도 다른 안
    # 2차: 음료만 겹치지 않는 안. 3차(부족하면): 메뉴가 절반 미만 겹치는 안
    for ok in (lambda pl: all(not (drink_ids(pl) & drink_ids(c)) and sweets(pl) != sweets(c)
                              for c in chosen),
               lambda pl: all(not (drink_ids(pl) & drink_ids(c)) for c in chosen),
               lambda pl: all(len(pl.ids & c.ids) / len(pl.ids | c.ids) < 0.5 for c in chosen)):
        for pl in cands:
            if len(chosen) == limit:
                break
            if pl not in chosen and ok(pl):
                chosen.append(pl)
    return chosen


def minimum(people: int, want_dessert: bool) -> tuple[int, str]:
    drinks, desserts = _pools()
    d = min(drinks, key=lambda p: p.price)
    total, parts = d.price * people, [d.text() + (f" ×{people}" if people > 1 else "")]
    if want_dessert:
        s = min(desserts, key=lambda p: p.price)
        total += s.price
        counted = unit_label(s.menu_id, 1)
        parts.append(f"{counted} {s.price:,}원" if counted else s.text())
    return total, " + ".join(parts)


# ── 손님 말에서 예산·인원 읽기 (라우터 값이 없을 때 대비) ─────────────
_KOR_NUM = {"한": 1, "두": 2, "세": 3, "네": 4, "다섯": 5, "둘": 2, "셋": 3, "넷": 4, "혼자": 1}


_KOR_DIGIT = {"일": 1, "이": 2, "삼": 3, "사": 4, "오": 5, "육": 6, "칠": 7, "팔": 8, "구": 9}


def _num(s: str) -> float:
    """'2' '1.5' '오' '십오' '' → 숫자. 비어 있으면 1 ('만원' = 1만)."""
    s = s.strip()
    if not s:
        return 1
    if re.fullmatch(r"\d+(?:\.\d+)?", s):
        return float(s)
    n, cur = 0, 0
    for ch in s:
        if ch == "십":
            n += (cur or 1) * 10; cur = 0
        else:
            cur = _KOR_DIGIT.get(ch, 0)
    return n + cur


def parse_budget(text: str) -> int | None:
    """'2만 원' '1만 2천원' '만오천원' '15000원' '오천원' → 원 단위 정수."""
    t = str(text).replace(",", "")
    d = r"[\d.일이삼사오육칠팔구십]*"
    m = re.search(rf"({d})\s*만\s*(?:({d})\s*천)?", t)
    if m:
        return int(_num(m[1]) * 10000 + (_num(m[2]) * 1000 if m[2] is not None else 0))
    m = re.search(rf"({d})\s*천\s*원", t)
    if m:
        return int(_num(m[1]) * 1000)
    m = re.search(r"(\d{4,6})\s*원", t)
    return int(m[1]) if m else None


def parse_people(text: str) -> int | None:
    t = str(text)
    m = re.search(r"(\d+)\s*(?:명|사람|인)", t)
    if m:
        return int(m[1])
    if "혼자" in t:
        return 1
    m = re.search(r"(한|두|세|네|다섯)\s*(?:명|사람|분)|(둘|셋|넷)이", t)
    if m:
        return _KOR_NUM[m[1] or m[2]]
    return None


def wants_dessert_in(text: str) -> bool:
    return any(w in str(text) for w in ["간식", "디저트", "빵", "케이크", "다과", "snack", "dessert"])


def budget_lines(user_input: str, router: dict | None = None) -> list[str]:
    """[예산안] 줄. 예산·인원은 코드가 원문에서 읽은 값을 먼저 쓰고, 없으면 라우터 값을 쓴다."""
    router = router or {}
    budget = parse_budget(user_input) or router.get("budget")
    people = parse_people(user_input) or router.get("people") or 1
    wants = router.get("wants") or []
    want_dessert = "디저트" in wants or wants_dessert_in(user_input)
    if not isinstance(budget, int) or budget <= 0:
        return ["[예산안] 예산 금액을 알 수 없습니다 — 손님에게 예산을 묻기"]
    if not isinstance(people, int) or people < 1:
        people = 1
    if people > MAX_PEOPLE:
        return [f"[예산안] {people}명은 한 번에 계산하지 않습니다 — {MAX_PEOPLE}명 이하로 나눠 묻기"]
    what = "음료" + ("+디저트" if want_dessert else "")
    head = f"[예산안] 조건: 예산 {budget:,}원 · {people}명 · {what} · 주류 제외 · 장바구니에 담지 않음"
    ps = plans(budget, people, want_dessert)
    if not ps:
        lo, how = minimum(people, want_dessert)
        return [head, f"[예산안] 조합 없음 — {people}명 {what} 최소 {lo:,}원 ({how}). "
                      f"예산보다 {lo - budget:,}원 부족"]
    lines = [head]
    for i, pl in enumerate(ps, 1):
        lines.append(f"[예산안] {i}안: {pl.text()} = 합계 {pl.total:,}원 · 잔액 {budget - pl.total:,}원")
    # 모델이 괄호 속 잔액을 빠뜨리던 문제 (S02 T1) — 안별 잔액을 한 줄로 따로 넘긴다
    lines.append("[예산안] 잔액(코드 계산, 안마다 말하기): "
                 + " · ".join(f"{i}안 {budget - pl.total:,}원" for i, pl in enumerate(ps, 1)))
    if any(p.label for pl in ps for p in pl.drinks + pl.desserts):
        lines.append("[예산안] '가장 싼 구성'은 크기가 여럿인 메뉴를 가장 싼 크기로 계산한 것 — 다른 크기면 금액이 바뀜")
    return lines
