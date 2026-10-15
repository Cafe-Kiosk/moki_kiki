"""손님이 건 조건(카페인 없이·우유 빼고·술 없이)을 요청 메뉴와 코드로 대조한다.

판단은 코드가 하고, 모델은 calc 에 적힌 태그를 전달만 한다.
  [조건충돌] 요청 메뉴가 조건을 어긴다 — 담지 않고 온도·크기도 묻지 않는다 (Q08)
  [대안]     조건을 만족하는 메뉴 2~3개, 데이터에 적힌 값과 함께 (Q08·Q10)
  [주의]     알레르기 질문이면 항상 공용 기구 교차접촉 안내 (P09·Q10)
담긴 품목의 주류·카페인과 합계는 calc 가 아니라 코드가 답변 끝에 붙인다 (kiosk.footer_lines).
"""
from __future__ import annotations
import re
from .cart import menu_by_id, find_variants, option_rules, is_alcohol, CartItem
from .retrieve import (match_menus, wants_no_caffeine, filter_by_caffeine,
                       _menu_caffeine, _menu_tastes, DRINK_CATEGORIES,
                       wants_decaf, decaf_bean_caffeine, caffeine_with_bean,
                       taste_candidates)

NO_MILK_WORDS = ["우유 빼", "우유빼", "우유 없", "우유없", "우유 알레르기", "우유알레르기",
                 "유당", "유제품", "비건", "dairy free", "dairy-free", "no milk",
                 "without milk", "milk allerg", "lactose", "vegan"]
NO_ALCOHOL_WORDS = ["술 없", "술없", "술 빼", "술빼", "무알코올", "무알콜", "논알코올", "논알콜",
                    "알코올 없", "알콜 없", "non-alcoholic", "no alcohol", "alcohol free",
                    "alcohol-free", "without alcohol"]
ALLERGY_WORDS = ["알레르기", "알러지", "allerg"]
MILK_SWAP_WORDS = {"oat": ["오트", "oat"], "soy": ["두유", "soy"]}

COND_LABEL = {"no_caffeine": "카페인 없음", "no_milk": "우유 없음", "no_alcohol": "술 없음"}
CROSS_CONTACT = "[주의] 공용 기구 교차접촉 가능(P09) — 바리스타 확인 권장"


def customer_conditions(text: str) -> set[str]:
    q = str(text).lower()
    conds = set()
    if wants_no_caffeine(q):
        conds.add("no_caffeine")
    if any(w in q for w in NO_MILK_WORDS):
        conds.add("no_milk")
    if any(w in q for w in NO_ALCOHOL_WORDS):
        conds.add("no_alcohol")
    return conds


def is_allergy_question(text: str) -> bool:
    q = str(text).lower()
    return any(w in q for w in ALLERGY_WORDS)


def _milk_swap_in(text: str) -> str | None:
    q = str(text).lower()
    for val, words in MILK_SWAP_WORDS.items():
        if any(w in q for w in words):
            return val
    return None


def has_milk(menu_id: str) -> bool:
    return "우유" in str((menu_by_id(menu_id) or {}).get("알레르기 유발 재료", ""))


def abv_percent(menu_id: str) -> float | None:
    vals = [v.get("도수(계산 기준)") for v in find_variants(menu_id)]
    vals = [x for x in vals if isinstance(x, (int, float))]
    return round(max(vals) * 100, 1) if vals else None


def _price_text(menu_id: str) -> str:
    ps = sorted({int(v["가격(원)"]) for v in find_variants(menu_id)})
    if not ps:
        return ""
    return f"{ps[0]:,}원" if len(ps) == 1 else f"{ps[0]:,}~{ps[-1]:,}원"


def violations(menu_id: str, conds: set[str], milk_swap: str | None = None) -> list[str]:
    """조건을 어기는 사실들. 비어 있으면 그 메뉴는 조건을 만족한다."""
    out = []
    if "no_caffeine" in conds:
        mg = _menu_caffeine().get(menu_id, 0)
        if mg > 0:
            out.append(f"카페인 {mg}mg")
    if "no_milk" in conds and has_milk(menu_id):
        changeable = menu_id in option_rules()["milk"]["menus"]
        if not (changeable and milk_swap in ("oat", "soy")):
            out.append("우유 포함 — " + ("오트·두유로 변경 가능(손님 확인 필요)"
                                       if changeable else "우유 변경 미지원(고정 레시피)"))
    if "no_alcohol" in conds and is_alcohol(menu_id):
        abv = abv_percent(menu_id)
        out.append("주류 포함" + (f"·도수 {abv}%" if abv is not None else "")
                   + " — 술 제거 미지원(P15)")
    return out


# 거의 모든 메뉴에 들어가서 '비슷한 메뉴'를 가르는 데 쓸모없는 재료
_COMMON = {"물", "설탕", "우유", "얼음", "꿀", "탄산수"}


def _ingredients(menu_id: str) -> set[str]:
    """'유자청(유자·설탕), 물' → {유자청, 유자}."""
    raw = str((menu_by_id(menu_id) or {}).get("원재료(가상 레시피)", ""))
    toks = re.split(r"[,()·;]", raw)
    return {t.split()[0] for t in toks if t.strip()} - _COMMON


def alternatives(conds: set[str], like_menu_id: str, limit: int = 3) -> list[str]:
    """조건을 모두 만족하는 메뉴를 고른다. 주류는 넣지 않는다.

    순서: 같은 분류 → 주재료가 겹치는 메뉴(유자 하이볼 → 유자티) → 메뉴판 순서.
    판매 통계가 없으므로(P12) 인기순은 쓰지 않는다.
    """
    like = menu_by_id(like_menu_id) or {}
    cat = like.get("분류")
    pool_cats = DRINK_CATEGORIES if cat in (*DRINK_CATEGORIES, "주류") else (cat,)
    rows = [r for r in _menu_tastes()
            if not r["is_alcohol"] and r["category"] in pool_cats
            and r["menu_id"] != like_menu_id]
    if "no_caffeine" in conds:
        rows = filter_by_caffeine(rows, no_caffeine=True)
    if "no_milk" in conds:
        rows = [r for r in rows if not has_milk(r["menu_id"])]
    base = _ingredients(like_menu_id)
    rows.sort(key=lambda r: (r["category"] != cat,
                             -len(base & _ingredients(r["menu_id"]))))   # 안정 정렬: 나머지는 메뉴판 순서
    caf = _menu_caffeine()
    out = []
    for r in rows[:limit]:
        m = menu_by_id(r["menu_id"])
        facts = []
        if r["menu_id"] in caf:
            facts.append(f"카페인 {caf[r['menu_id']]}mg")
        if "no_milk" in conds:
            facts.append(f"알레르기 유발 재료: {m.get('알레르기 유발 재료')}")
        facts.append(_price_text(r["menu_id"]))
        out.append(f"{m['메뉴명']} ({' · '.join(f for f in facts if f)})")
    return out


def alternatives_line(conds: set[str], like_menu_id: str) -> str:
    alts = alternatives(conds, like_menu_id)
    if not alts:
        return "[대안] 조건을 만족하는 메뉴가 없습니다 — 바리스타 확인 권장"
    label = "·".join(COND_LABEL[c] for c in sorted(conds))
    return f"[대안] 조건({label})을 만족하는 메뉴: " + " / ".join(alts) + " — 손님이 고르면 담기"


def screen(user_text: str, order_items: list[dict] | None = None) -> tuple[list[str], set[str]]:
    """손님 조건과 요청 메뉴를 대조한다. (calc 줄, 담지 말아야 할 메뉴 ID)"""
    order_items = order_items or []
    conds = customer_conditions(user_text)
    lines, blocked = [], set()
    if conds:
        swap_by_menu: dict[str, str | None] = {}
        for it in order_items:
            ids, _ = match_menus(it.get("menu_name", ""))
            for mid in ids:
                swap_by_menu.setdefault(mid, it.get("milk"))
        mids = [m for m in match_menus(user_text)[0] if menu_by_id(m)]
        mids += [m for m in swap_by_menu if menu_by_id(m) and m not in mids]
        text_swap = _milk_swap_in(user_text)
        for mid in mids:
            facts = violations(mid, conds, swap_by_menu.get(mid) or text_swap)
            if facts:
                blocked.add(mid)
                lines.append(f"[조건충돌] {menu_by_id(mid)['메뉴명']} {' · '.join(facts)}"
                             " — 담지 않음, 온도·크기 묻지 않음")
        if blocked:
            lines.append(alternatives_line(conds, sorted(blocked)[0]))
    if is_allergy_question(user_text):
        lines.append(CROSS_CONTACT)
    return lines, blocked


def decaf_notes(text: str) -> list[str]:
    """디카페인 질문이면 메뉴별 디카페인 카페인을 계산해 넘긴다. 0이라고 말하지 않게 한다 (Q09·P10)."""
    if not wants_decaf(text):
        return []
    mids = [m for m in match_menus(text)[0] if menu_by_id(m)
            and menu_by_id(m)["분류"] in DRINK_CATEGORIES]
    mids = mids or taste_candidates(text)
    fee = option_rules()["bean"]["choices"].get("B03", 0)
    caf = _menu_caffeine()
    out = []
    for mid in mids:
        name = menu_by_id(mid)["메뉴명"]
        n = decaf_bean_caffeine(mid)
        if "디카페인" in name:
            out.append(f"{name}: 카페인 {caf.get(mid)}mg (0은 아님, P10)")
        elif n is not None:
            out.append(f"{name}: 디카페인 원두 선택 시 약 {n}mg (0은 아님, P10) · 원두 변경 +{fee:,}원")
        elif caf.get(mid, 0) > 0:
            out.append(f"{name}: 디카페인 원두 선택 불가 — 카페인 {caf[mid]}mg")
    return out


def item_caution_line(item: CartItem) -> str | None:
    """담긴 품목의 주류·카페인을 코드가 답변 끝에 붙일 한 줄로 만든다 (Q34).

    카페인은 커피·차·주류일 때만, 0mg 이면 생략한다. 원두·샷을 바꿨으면 바꾼 기준으로 계산한다 (P10).
    """
    from .cart import variant_by_id
    v = variant_by_id(item.variant_id) or {}
    bits = []
    if item.is_alcohol:
        abv = v.get("도수(계산 기준)")
        bits.append("주류" + (f" {round(abv * 100, 1)}%" if isinstance(abv, (int, float)) else ""))
    cat = (menu_by_id(item.menu_id) or {}).get("분류")
    mg = v.get("카페인(mg)")
    mg = int(mg) if isinstance(mg, (int, float)) else 0
    if cat in (*DRINK_CATEGORIES, "주류") and mg > 0:
        if item.bean not in (None, "B01") or item.extra_shots:
            est = caffeine_with_bean(v, item.bean or v.get("원두 ID"), item.extra_shots)
            if est is not None:
                bits.append(f"카페인 약 {est}mg" + (" (디카페인 원두, 0은 아님)" if item.bean == "B03" else ""))
            else:
                bits.append(f"카페인 {mg}mg (원두·샷 변경 전 기준)")
        else:
            bits.append(f"카페인 {mg}mg")
    if not bits:
        return None
    return f"⚠️ {item.name} — " + " · ".join(bits)


# P07 미지원 항목 — 범위밖 판정을 뒤집고 [미지원] 으로 넘길 때 쓴다 (S10 T2·Q17·Q18).
# POLICY_KEYWORDS 의 '대기'처럼 넓은 말은 '직원 확인 대기'에도 걸리므로 항목별로 좁혀 둔다.
UNSUPPORTED = {
    "쿠폰·기프티콘": ["기프티콘", "쿠폰", "gifticon", "coupon", "voucher"],
    "분할 결제": ["분할", "나눠서 결제", "나눠 결제", "나눠서 계산", "반씩", "따로 결제", "더치", "split"],
    "포인트 적립": ["적립", "포인트", "멤버십", "point", "membership"],
    "영수증 발급": ["영수증", "receipt"],
    "예약": ["예약", "reserv"],
    "실시간 재고·제조 진행·대기시간": ["몇 분", "대기시간", "대기 시간", "얼마나 걸", "언제 나와", "재고", "품절",
                              "how long", "wait time", "ready yet", "in stock"],
}


def unsupported_hits(text: str) -> list[str]:
    q = str(text).lower()
    return [label for label, words in UNSUPPORTED.items() if any(w in q for w in words)]


def unsupported_line(text: str) -> str | None:
    hits = unsupported_hits(text)
    if not hits:
        return None
    return (f"[미지원] {' · '.join(hits)} — 이 키오스크에서 지원하지 않음 (P07). "
            "지원된다거나 매장마다 다르다고 말하지 않는다")
