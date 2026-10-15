"""API를 전혀 쓰지 않는 로직 검사.

검증질문 중 금액·수량·구성 규칙은 전부 코드가 결정한다.
LLM 없이 기대값과 맞춰 볼 수 있으므로 토큰이 한 푼도 들지 않는다.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from src.cart import Cart, CartItem, resolve_variant, menu_by_id, find_variants
from src.retrieve import rule_hits, taste_candidates

ok = fail = 0
def check(label, got, want):
    global ok, fail
    good = got == want
    ok, fail = ok + good, fail + (not good)
    print(f"  {'✅' if good else '❌'} {label}")
    if not good:
        print(f"       기대 {want}\n       실제 {got}")

def add(cart, menu_id, temp=None, size=None, **kw):
    v, _ = resolve_variant(menu_id, temp, size)
    m = menu_by_id(menu_id)
    it = CartItem(menu_id, str(v["주문 단위 ID"]), str(m["메뉴명"]),
                  str(v.get("온도")), str(v.get("크기")),
                  is_alcohol=str(m.get("주류 구분","")).startswith("주류 포함"), **kw)
    return cart.add(it), it

print("\n【 금액 계산 — 검증질문 기대값과 대조 】")

c = Cart(table_id=1)                                    # Q03
add(c, "M03", "HOT", "S", bean="B03"); add(c, "M28")
check("Q03 디카페인 라떼 S + 약과 = 10,700원", c.total, 10700)

c = Cart(table_id=1)                                    # Q04
add(c, "M03", "ICED", "L", qty=2, bean="B03", milk="oat", extra_shots=2)
check("Q04 아이스라떼L 디카페인+오트+샷2 ×2 = 17,800원", c.total, 17800)
check("Q04 단가 8,900원", c.items[0].unit_price, 8900)

c = Cart(table_id=1)                                    # Q34
add(c, "M35"); add(c, "M20")
check("Q34 에스프레소 마티니 + 치즈케이크 = 18,800원", c.total, 18800)

c = Cart(table_id=1)                                    # Q45
add(c, "M36", qty=2); add(c, "M37", qty=2)
check("Q45 라거×2 + 레드와인×2 = 32,000원", c.total, 32000)

c = Cart(table_id=1)                                    # Q16
add(c, "M24")
check("Q16 에티오피아 원두 200g = 19,000원", c.total, 19000)

c = Cart(table_id=1)                                    # Q20
add(c, "M12", "HOT"); add(c, "M28")
check("Q20 디카페인 필터커피 + 약과 = 11,300원", c.total, 11300)

print("\n【 수량 검증 (P11 · Q14) 】")
c = Cart(table_id=1)
(okq, msg), _ = add(c, "M02", "ICED", "S", qty=0)
check("수량 0 거부", okq, False)
(okq, msg), _ = add(c, "M02", "ICED", "S", qty=-1)
check("수량 -1 거부", okq, False)
(okq, msg), _ = add(c, "M02", "ICED", "S", qty=11)
check("수량 11 거부", okq, False)
check("잘못된 수량은 담기지 않음", len(c.items), 0)

print("\n【 온도·크기 구성 (P03) 】")
v, all_v = resolve_variant("M02", "HOT", "XL")
check("Q07 아메리카노 XL 없음 → 확정 안 함", v, None)
check("   선택지 4개 제시", len(all_v), 4)
v, _ = resolve_variant("M04", "ICED")
check("Q06 카푸치노 ICED 없음 → 확정 안 함", v, None)
check("Q06 카푸치노는 HOT/ONE 하나뿐", len(find_variants("M04")), 1)

print("\n【 주류 (P15) 】")
c = Cart(table_id=1); add(c, "M32")
check("Q32 주류 담으면 pending_staff_check", c.status(), "pending_staff_check")
okc, msg = c.confirm()
check("Q32 직원 확인 전 확정 거부", okc, False)
c.staff_checked = True
okc, _ = c.confirm()
check("직원 확인 후 확정 가능", okc, True)

print("\n【 규칙 검색 (API 0회) 】")
check("Q47 '하이볼' → 두 메뉴 모두", sorted(rule_hits("하이볼 하나 주세요")[0]), ["M32", "M34"])
check("Q25 '아아' → 아메리카노", "M02" in rule_hits("아아 하나")[0], True)
check("Q25 '핫초코' → 초코 라떼", "M14" in rule_hits("핫초코 하나")[0], True)
check("Q17 '기프티콘' → 미지원 정책", "P07" in rule_hits("기프티콘 쓸래요")[1], True)
check("Q39 '마들렌' → 메뉴 없음", rule_hits("마들렌 하나 더")[0], set())
check("Q43 '김부각' → 메뉴 없음", rule_hits("김부각 주문해줘")[0], set())
check("'두유' → 우유 변경 옵션", "milk" in rule_hits("두유로 바꾸면 돈 더 내요?")[1], True)
check("Q01 산미 적고 고소한 커피 → 커피만", 
      all(menu_by_id(m)["분류"] in ("커피","디저트") for m in taste_candidates("산미 적고 고소한 커피랑 빵")), True)

def safe(fn):
    """아직 없는 함수를 부르는 테스트도 멈추지 않고 실패로 센다."""
    try:
        return fn()
    except Exception as e:
        return f"{type(e).__name__}: {e}"

def try_add(menu_id, temp=None, size=None, **kw):
    c = Cart(table_id=1)
    (okk, _), _ = add(c, menu_id, temp, size, **kw)
    return okk, len(c.items)

def rejected_keys(menu_id, temp=None, size=None, **opts):
    from src.cart import validate_options
    v, _ = resolve_variant(menu_id, temp, size)
    allowed, rejected = validate_options(menu_id, v, opts)
    return sorted(k for k, _ in rejected)

def apply(*items):
    """라우터가 준 order_items 를 그대로 흘려 본다 (LLM 없이)."""
    from src.kiosk import apply_order_items
    c = Cart(table_id=1)
    lines = apply_order_items(list(items), c)
    return c, "\n".join(lines)

print("\n【 옵션 적용 가능 여부 (옵션규칙 시트 · P15) 】")
check("Q05 콜드브루 + 디카페인 원두·샷 → 담지 않음",
      safe(lambda: try_add("M09", "ICED", bean="B03", extra_shots=1)), (False, 0))
check("Q05 거부 사유 2개 (bean, extra_shots)",
      safe(lambda: rejected_keys("M09", "ICED", bean="B03", extra_shots=1)), ["bean", "extra_shots"])
check("Q10 크림 라떼 우유 변경 → 담지 않음",
      safe(lambda: try_add("M07", milk="oat")), (False, 0))
check("유자티 샷 추가 → 담지 않음",
      safe(lambda: try_add("M16", "HOT", extra_shots=2)), (False, 0))
check("아메리카노 샷 5 → 담지 않음 (0~2)",
      safe(lambda: try_add("M02", "ICED", "S", extra_shots=5)), (False, 0))
check("아메리카노 샷 2 → 담김",
      safe(lambda: try_add("M02", "ICED", "S", extra_shots=2)), (True, 1))
check("Q21 치즈케이크 데우기 → 담지 않음",
      safe(lambda: try_add("M20", warming="warm")), (False, 0))
check("Q21 소금빵 데우기 → 담김",
      safe(lambda: try_add("M18", warming="warm")), (True, 1))
check("P15 유자 하이볼 얼음 적게 → 담지 않음",
      safe(lambda: try_add("M32", ice="less")), (False, 0))
check("약과 원두 선택 → 담지 않음",
      safe(lambda: try_add("M28", bean="B02")), (False, 0))
check("HOT 아메리카노 얼음 적게 → 거부 (ICED만)",
      safe(lambda: rejected_keys("M02", "HOT", "S", ice="less")), ["ice"])
check("ICED 아메리카노 얼음 적게 → 허용",
      safe(lambda: rejected_keys("M02", "ICED", "S", ice="less")), [])
check("기본값(콜드브루 B01·샷0)은 옵션이 아님 → 거부 없음",
      safe(lambda: rejected_keys("M09", "ICED", bean="B01", extra_shots=0)), [])
check("추가금은 엑셀에서 읽음 (B02 +1000, oat +500, 샷 600)",
      safe(lambda: __import__("src.cart", fromlist=["x"]).option_fee_table()),
      {"bean": {"B01": 0, "B02": 1000, "B03": 700},
       "milk": {"dairy": 0, "lowfat": 0, "oat": 500, "soy": 500},
       "sweetness": {"normal": 0, "less": 0}, "ice": {"normal": 0, "less": 0},
       "warming": {"room": 0, "warm": 0}, "extra_shots": 600})
c_q05 = safe(lambda: apply({"menu_name": "콜드브루", "temp": None, "size": None, "qty": 1,
                            "bean": "B03", "extra_shots": 1}))
check("Q05 담기 흐름: 장바구니 비어 있음",
      len(c_q05[0].items) if isinstance(c_q05, tuple) else c_q05, 0)
check("Q05 담기 흐름: 대안(디카페인 아메리카노·디카페인 필터커피) 안내",
      all(w in c_q05[1] for w in ["디카페인 아메리카노", "디카페인 필터커피"])
      if isinstance(c_q05, tuple) else c_q05, True)

print("\n【 카페인 필터 — 실측값 기준 (가격영양 · P10 · Q08 · Q42) 】")
def caf(mid):
    return min(int(v["카페인(mg)"]) for v in find_variants(mid))
for q in ["카페인 없는 거 추천해줘", "임산부가 마실만한 거", "caffeine free drink please"]:
    got = taste_candidates(q)
    check(f"'{q}' → 전부 0mg · 주류 없음 · 결과 있음",
          (bool(got), all(caf(m) == 0 for m in got),
           any(menu_by_id(m)["분류"] == "주류" for m in got)), (True, True, False))
check("Q08 '카페인 없는' 추천에 말차 라떼 없음", "M13" in taste_candidates("카페인 없는 거 추천해줘"), False)
low = taste_candidates("카페인 적은 음료 추천")
check("'카페인 적은' → 낮은 순 정렬", [caf(m) for m in low] == sorted(caf(m) for m in low), True)
check("'디카페인 커피 추천' → 디카페인 필터커피 포함", "M12" in taste_candidates("디카페인 커피 추천"), True)
check("'카페인 적은 음료' → 디카페인 메뉴도 포함", "M12" in low, True)
check("디카페인 메뉴가 근거에 들어가면 P10 동반",
      safe(lambda: "P10" in __import__("src.retrieve", fromlist=["x"]).with_decaf_policy(["M12"])), True)

print("\n【 별칭 최장 일치 (Q25 · Q34 · Q47) 】")
def cands(t):
    from src.kiosk import _menu_candidates
    ids, _ = _menu_candidates(t)
    return sorted(ids)
def attrs(t):
    from src.kiosk import _menu_candidates
    return _menu_candidates(t)[1]
check("바닐라라떼 → M06", safe(lambda: cands("바닐라라떼")), ["M06"])
check("바닐라 라떼 → M06", safe(lambda: cands("바닐라 라떼")), ["M06"])
check("초코라떼 → M14", safe(lambda: cands("초코라떼")), ["M14"])
check("말차라떼 → M13", safe(lambda: cands("말차라떼")), ["M13"])
check("Q34 에스프레소 마티니 → M35", safe(lambda: cands("에스프레소 마티니")), ["M35"])
check("콜드브루 라떼 → M10", safe(lambda: cands("콜드브루 라떼")), ["M10"])
check("Q47 하이볼 → M32·M34 둘 다 (되묻기)", safe(lambda: cands("하이볼")), ["M32", "M34"])
check("위스키 하이볼 → M34", safe(lambda: cands("위스키 하이볼")), ["M34"])
check("Q25 아아 → M02 + ICED", safe(lambda: (cands("아아"), attrs("아아").get("temp"))), (["M02"], "ICED"))
check("뜨아 → HOT", safe(lambda: attrs("뜨아").get("temp")), "HOT")
check("디카페인 카페라떼 → M03 + B03",
      safe(lambda: (cands("디카페인 카페라떼"), attrs("디카페인 카페라떼").get("bean"))), (["M03"], "B03"))
check("rule_hits '에스프레소 마티니 하나' → M35만", rule_hits("에스프레소 마티니 하나")[0], {"M35"})
check("rule_hits '콜드브루 라떼' → M10만", rule_hits("콜드브루 라떼 주세요")[0], {"M10"})
r = safe(lambda: apply({"menu_name": "아아", "temp": None, "size": "S", "qty": 1}))
check("Q25 담기 흐름: 아아(온도 null) → M02-ICED-S",
      [i.variant_id for i in r[0].items] if isinstance(r, tuple) else r, ["M02-ICED-S"])
r = safe(lambda: apply({"menu_name": "바닐라라떼", "temp": "HOT", "size": "S", "qty": 1}))
check("담기 흐름: 바닐라라떼 → 담김",
      [i.menu_id for i in r[0].items] if isinstance(r, tuple) else r, ["M06"])

print("\n【 수량 0·음수·비정수 (Q14 · P11) 】")
for q in [0, -1, 1.5, "두"]:
    r = safe(lambda: apply({"menu_name": "아메리카노", "temp": "ICED", "size": "S", "qty": q}))
    check(f"qty={q!r} → 담지 않고 사유 안내",
          (len(r[0].items), "수량" in r[1]) if isinstance(r, tuple) else r, (0, True))
r = safe(lambda: apply({"menu_name": "아메리카노", "temp": "ICED", "size": "S", "qty": None}))
check("qty=None → 1잔", [i.qty for i in r[0].items] if isinstance(r, tuple) else r, [1])

print(f"\n{'='*52}\n통과 {ok} · 실패 {fail}   (API 호출 0회)")
