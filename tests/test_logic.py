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

print("\n【 calc 태그 — 판단은 코드, 모델은 전달 (Q08 · Q10 · Q34) 】")
def calc(text, intent="장바구니", *items):
    """라우터 결과를 손으로 넣고 모델에게 갈 calc 문자열을 만든다 (LLM 없이)."""
    from src.kiosk import build_calc
    c = Cart(table_id=1)
    return c, "\n".join(build_calc(text, intent, list(items), c))

c, s = safe(lambda: calc("카페인 없는 말차라떼 주세요", "장바구니",
                         {"menu_name": "말차 라떼", "temp": None, "size": None, "qty": 1}))
check("Q08 [조건충돌] 말차 라떼 카페인 70mg", "[조건충돌] 말차 라떼 카페인 70mg" in s, True)
check("Q08 담지 않음", len(c.items), 0)
check("Q08 온도·크기 묻지 않음 (구성 선택 줄 없음)", "구성을 하나 골라야" in s, False)
check("Q08 [대안]에 유자티·루이보스티 (0mg)",
      all(w in s for w in ["[대안]", "유자티 (카페인 0mg", "루이보스티 (카페인 0mg"]), True)
check("Q08 [대안]에 카페인 있는 메뉴 없음",
      "보성 홍차 밀크티" not in s and "말차 라떼 (" not in s, True)
_, s = safe(lambda: calc("카페인이 없는 말차 라떼 주문", "메뉴질문"))
check("라우터 재작성 '카페인이 없는'도 조건으로 인식", "[조건충돌] 말차 라떼" in s, True)
check("재작성 문장으로도 무카페인 추천이 나옴",
      sorted(taste_candidates("카페인이 없는 말차 라떼 주문"))[:2], ["M16", "M17"])

c, s = safe(lambda: calc("우유 알레르기 있는데 크림 라떼를 오트로 바꿔줘", "옵션"))
check("Q10 [조건충돌] 크림 라떼 우유 변경 미지원",
      "[조건충돌] 고운결 크림 라떼 우유 포함 — 우유 변경 미지원" in s, True)
check("Q10 [대안] 우유 없는 음료만", "[대안]" in s and "알레르기 유발 재료: 우유" not in s, True)
check("Q10 [주의] 공용 기구 교차접촉(P09)",
      "[주의] 공용 기구 교차접촉 가능(P09) — 바리스타 확인 권장" in s, True)
c, s = safe(lambda: calc("우유 알레르기 있는데 크림 라떼를 오트로 바꿔줘", "장바구니",
                         {"menu_name": "크림 라떼", "milk": "oat", "qty": 1}))
check("Q10 담기 흐름도 담지 않음 + [대안]", (len(c.items), "[대안]" in s), (0, True))
c, s = safe(lambda: calc("크림 라떼 오트로 바꿔줘", "장바구니",
                         {"menu_name": "크림 라떼", "milk": "oat", "qty": 1}))
check("알레르기 없이 우유 변경 불가 → [대안], [주의] 없음",
      ("[대안] 조건(우유 없음)" in s, "[주의]" in s), (True, False))
c, s = safe(lambda: calc("우유 알레르기인데 말차라떼 오트로 주세요", "장바구니",
                         {"menu_name": "말차라떼", "temp": "HOT", "milk": "oat", "qty": 1}))
check("우유 변경 가능한 메뉴는 오트로 담김 + 알레르기 [주의]",
      (len(c.items), "[조건충돌]" in s, "교차접촉" in s), (1, False, True))
_, s = safe(lambda: calc("견과류 알레르기 있어요 뭐가 안전해요?", "메뉴질문"))
check("알레르기 질문이면 항상 [주의]", "[주의] 공용 기구 교차접촉 가능(P09)" in s, True)

c, s = safe(lambda: calc("에스프레소 마티니 하나랑 치즈케이크 한 조각 주세요", "장바구니",
                         {"menu_name": "에스프레소 마티니", "qty": 1},
                         {"menu_name": "치즈케이크", "qty": 1}))
check("Q34 [담기완료] 두 품목",
      ("[담기완료] 에스프레소 마티니" in s, "[담기완료] 바스크 치즈케이크" in s), (True, True))
check("Q34 calc 에 합계 없음 (모델이 말하지 않음)", "합계" in s.replace("직원 나이", ""), False)
from src.kiosk import receipt_line, cart_signature
check("Q34 영수증 줄 = 🧾 합계 18,800원 · 직원 확인 대기",
      safe(lambda: receipt_line(c)), "🧾 합계 18,800원 · 직원 확인 대기")
c2 = Cart(table_id=1); add(c2, "M28")
check("주류 없으면 직원 확인 문구 없음", safe(lambda: receipt_line(c2)), "🧾 합계 4,500원")
sig = cart_signature(c2); c2.set_qty(0, 2)
check("수량을 바꾸면 장바구니 변경으로 인식", cart_signature(c2) != sig, True)
check("Q34 calc 엔 품목 도수·카페인 없음 (코드가 답변 끝에 붙임)", "16.7%" in s, False)
from src.kiosk import footer_lines
check("Q34 끝줄: ⚠️ 마티니 주류·카페인 → 🧾 합계 (치즈케이크 ⚠️ 없음)",
      safe(lambda: footer_lines(c)),
      ["⚠️ 에스프레소 마티니 — 주류 16.7% · 카페인 70mg", "🧾 합계 18,800원 · 직원 확인 대기"])
c3 = Cart(table_id=1); add(c3, "M02", "ICED", "S"); add(c3, "M17", "HOT"); add(c3, "M32")
check("커피는 카페인만, 0mg 차는 생략, 0mg 주류는 도수만",
      safe(lambda: footer_lines(c3)),
      ["⚠️ 아메리카노 — 카페인 120mg", "⚠️ 유자 소주 하이볼 — 주류 5.3%",
       "🧾 합계 19,000원 · 직원 확인 대기"])
c4 = Cart(table_id=1); add(c4, "M21")
check("디저트는 ⚠️ 없음 (카페인은 커피·차·주류만)", safe(lambda: footer_lines(c4)), ["🧾 합계 " + f"{c4.total:,}원"])
_, s = safe(lambda: calc("술 없이 유자 하이볼 주세요", "장바구니",
                         {"menu_name": "유자 소주 하이볼", "qty": 1}))
check("술 없이 → [조건충돌] + 대안 첫째 유자티",
      ("[조건충돌] 유자 소주 하이볼 주류 포함" in s, "메뉴: 유자티" in s), (True, True))
_, s = safe(lambda: calc("아메리카노 0잔 담아줘", "장바구니",
                         {"menu_name": "아메리카노", "temp": "ICED", "size": "S", "qty": 0}))
check("Q14 잘못된 수량엔 [담기완료] 없음", "[담기완료]" in s, False)
_, s = safe(lambda: calc("아메리카노 0잔, 라떼 -1잔 담아줘", "장바구니",
                         {"menu_name": "아메리카노", "temp": None, "size": None, "qty": 0},
                         {"menu_name": "라떼", "temp": None, "size": None, "qty": -1}))
check("Q14 온도·크기 null 이어도 수량부터 거부 (구성 묻지 않음)",
      (s.count("요청 수량"), "구성을 하나 골라야" in s), (2, False))

print("\n【 묶음 A-1 디카페인 추천 — 일반 원두 커피 제외, B03 카페인 계산 (Q09 · P10) 】")
from src.retrieve import decaf_bean_caffeine, match_menus
dec = taste_candidates("디카페인 커피 추천")
check("'디카페인 커피 추천' → 디카페인 필터커피 포함", "M12" in dec, True)
check("'디카페인 커피 추천' → 원두 고정 일반 커피(콜드브루·에티오피아 필터) 없음",
      any(m in dec for m in ["M09", "M10", "M11"]), False)
check("후보는 전부 디카페인 메뉴이거나 원두 선택 가능 메뉴",
      all(m == "M12" or decaf_bean_caffeine(m) is not None for m in dec), True)
check("아메리카노 B03 = 4mg × 2샷 = 8mg", safe(lambda: decaf_bean_caffeine("M02")), 8)
check("Q09 모카 B03 = 4mg × 2샷 + 카카오 12mg = 20mg", safe(lambda: decaf_bean_caffeine("M08")), 20)
check("콜드브루는 원두 선택 불가 → None", safe(lambda: decaf_bean_caffeine("M09")), None)
_, s = safe(lambda: calc("디카페인 모카는 카페인 0이죠?", "메뉴질문"))
check("Q09 calc: 디카페인 원두 선택 시 약 20mg (0은 아님, P10)",
      "다크 카페 모카: 디카페인 원두 선택 시 약 20mg (0은 아님, P10)" in s, True)
_, s = safe(lambda: calc("디카페인 커피 추천해줘", "추천"))
check("디카페인 추천 calc 에 '120mg' 없음, 디카페인 필터커피 8mg",
      ("120mg" in s, "디카페인 필터커피: 카페인 8mg (0은 아님, P10)" in s), (False, True))
c, s = safe(lambda: calc("디카페인 카페라떼 HOT S 하나", "장바구니",
                         {"menu_name": "디카페인 카페라떼", "temp": "HOT", "size": "S", "qty": 1}))
check("디카페인 라떼 ⚠️ 카페인 약 8mg (변경 전 120mg 아님)",
      safe(lambda: footer_lines(c)[0]), "⚠️ 카페 라떼 — 카페인 약 8mg (디카페인 원두, 0은 아님)")
check("카페인 적은 음료 추천은 기존대로 (무카페인 차 포함)",
      "M17" in taste_candidates("카페인 적은 음료 추천"), True)

print("\n【 묶음 A-2 필터커피·드립 되묻기 (Q16 · Q47 방식) 】")
for w in ["필터커피", "드립", "핸드드립", "드립커피", "이 필터커피 원두도 한 봉지 주세요"]:
    check(f"'{w}' → M11·M12 둘 다", sorted(match_menus(w)[0]), ["M11", "M12"])
check("'에티오피아 필터커피' → M11만", match_menus("에티오피아 필터커피")[0], ["M11"])
check("'디카페인 드립' → M12만", match_menus("디카페인 드립")[0], ["M12"])
c, s = safe(lambda: apply({"menu_name": "필터커피", "temp": "HOT", "size": None, "qty": 1}))
check("필터커피 담기 → 담지 않고 둘 중 확인",
      (len(c.items), "에티오피아 필터커피 또는 디카페인 필터커피" in s), (0, True))

print("\n【 묶음 A-3 2글자 별칭은 원문 단어 경계에서만 】")
for text, want in [("아아 하나", ["M02"]), ("에쏘 한 잔", ["M01"]), ("뜨아 주세요", ["M02"]),
                   ("디카페인 모카는 카페인 0이죠?", ["M08"]), ("라떼랑 약과", ["M03", "M28"]),
                   ("아이스 바라 하나", ["M06"]), ("잘 되길 바라요", []), ("모카포트 팔아요?", []),
                   ("와인잔 있어요?", []), ("에쏘아아", []), ("바닐라라떼", ["M06"])]:
    check(f"'{text}' → {want}", sorted(match_menus(text)[0]), want)

_, s = safe(lambda: calc("하이볼 하나 주세요", "메뉴질문"))
check("Q47 담기 의도가 아니어도 calc 에 되묻기",
      "유자 소주 하이볼 또는 위스키 하이볼 중 어느 것인지 확인" in s, True)
import src.kiosk as K

def handle_stub(text, router_out, cart=None):
    """라우터·검색·답변 모델을 가짜로 바꿔 handle 의 코드 경로만 돌린다 (API 0회)."""
    saved = K.route, K.answer, K.hybrid_search
    K.route = lambda *a, **k: dict({"rewritten_query": text, "language": "ko",
                                    "order_items": []}, **router_out)
    K.answer = lambda *a, **k: ("(모델 답변)", True)
    K.hybrid_search = lambda *a, **k: ([], [])
    try:
        return K.handle(text, None, cart or Cart(table_id=1))
    finally:
        K.route, K.answer, K.hybrid_search = saved

r = safe(lambda: handle_stub("하이볼 하나 주세요", {"intent": "범위밖"}))
check("Q47 라우터가 범위밖이라 해도 메뉴명이 있으면 메뉴질문으로",
      (r.intent, "확인이 필요" in r.calc) if hasattr(r, "intent") else r, ("메뉴질문", True))
r = safe(lambda: handle_stub("오늘 날씨 어때요", {"intent": "범위밖"}))
check("메뉴명이 없는 범위밖은 그대로", getattr(r, "intent", r), "범위밖")
c = Cart(table_id=1)
r = safe(lambda: handle_stub("에스프레소 마티니 하나랑 치즈케이크 한 조각 주세요",
                             {"intent": "장바구니", "order_items": [
                                 {"menu_name": "에스프레소 마티니", "qty": 1},
                                 {"menu_name": "치즈케이크", "qty": 1}]}, c))
check("Q34 장바구니가 바뀐 턴엔 답변 마지막 줄이 🧾 합계",
      getattr(r, "reply", r).splitlines()[-1] if hasattr(r, "reply") else r,
      "🧾 합계 18,800원 · 직원 확인 대기")
r = safe(lambda: handle_stub("말차 라떼 카페인 얼마나 돼요?", {"intent": "메뉴질문"}, c))
check("장바구니가 안 바뀐 턴엔 🧾 줄 없음", "🧾" in getattr(r, "reply", ""), False)

print("\n【 별칭 속성으로 온도 보충 (Q25) 】")
c, s = safe(lambda: calc("아아 하나랑 핫초코 하나", "장바구니",
                         {"menu_name": "아메리카노", "temp": None, "size": None, "qty": 1},
                         {"menu_name": "초코 라떼", "temp": None, "size": None, "qty": 1}))
check("Q25 아아 → 아메리카노 ICED 의 S/L 만 묻기",
      ("아메리카노 ICED: 크기만 골라야" in s, "S 4,500원 / L 5,500원" in s,
       "HOT" in s.splitlines()[0]),
      (True, True, False))
check("[담기완료] 줄에 NA·ONE 내부 값 없음", ("NA" in s, "ONE" in s), (False, False))
check("Q25 핫초코 → 초코 라떼 HOT 확정", [i.variant_id for i in c.items], ["M14-HOT-ONE"])
c, s = safe(lambda: calc("뜨아 S 하나", "장바구니",
                         {"menu_name": "아메리카노", "temp": None, "size": "S", "qty": 1}))
check("뜨아 → HOT 으로 채워 담김", [i.variant_id for i in c.items], ["M02-HOT-S"])
c, s = safe(lambda: calc("iced latte large please", "장바구니",
                         {"menu_name": "latte", "temp": None, "size": "L", "qty": 1}))
check("iced latte → ICED 로 채워 담김", [i.variant_id for i in c.items], ["M03-ICED-L"])
c, s = safe(lambda: calc("뜨거운 아아 하나", "장바구니",
                         {"menu_name": "아메리카노", "temp": "HOT", "size": "S", "qty": 1}))
check("뜨거운 아아 (라우터 HOT ↔ 별칭 ICED) → 담지 않고 되묻기",
      (len(c.items), "온도 확인 필요" in s), (0, True))
c, s = safe(lambda: calc("아아랑 뜨아 하나씩, 둘 다 S", "장바구니",
                         {"menu_name": "아메리카노", "temp": "ICED", "size": "S", "qty": 1},
                         {"menu_name": "아메리카노", "temp": "HOT", "size": "S", "qty": 1}))
check("아아랑 뜨아 (원문 온도가 섞임) → 라우터 값대로 둘 다 담김",
      sorted(i.variant_id for i in c.items), ["M02-HOT-S", "M02-ICED-S"])

print("\n【 답변 캐시 스위치 】")
import src.chain as chain
import json
saved = chain.USE_CACHE, chain.MOCK, chain._cache_load
chain.MOCK = False
calls = []
class FakeLLM:
    def __init__(self, *a, **k): pass
    def invoke(self, msgs):
        calls.append(1)
        return type("R", (), {"content": "새 답변"})()
saved_llm = chain.ChatOpenAI
chain.ChatOpenAI = FakeLLM
key = chain._cache_key(chain.SYSTEM.format(context="ctx", calc="(없음)"), "질문")
chain._cache_load = lambda: {key: "옛 답변"}
written = []
saved_path = chain.ANSWER_CACHE
class FakePath:
    def write_text(self, s): written.append(s)
    def exists(self): return True
chain.ANSWER_CACHE = FakePath()
try:
    chain.USE_CACHE = False
    check("캐시 끔 → 저장된 옛 답변 대신 새로 생성", chain.answer("질문", "ctx"), ("새 답변", False))
    check("캐시 끔 → 캐시 파일에 쓰지 않음", len(written), 0)
    chain.USE_CACHE = True
    check("캐시 켬 → 저장된 답변 사용 (앱 기본)", chain.answer("질문", "ctx"), ("옛 답변", True))
finally:
    chain.USE_CACHE, chain.MOCK, chain._cache_load = saved
    chain.ChatOpenAI, chain.ANSWER_CACHE = saved_llm, saved_path
check("앱 기본값은 캐시 사용", chain.USE_CACHE, True)

print("\n【 묶음 B 예산 추천 (교수님 시나리오 · P12) 】")
from src.budget import plans, budget_lines, parse_budget, parse_people
from src.cart import is_alcohol
ps = safe(lambda: plans(20000, 2, True))
check("20,000원·2명·음료+디저트 → 2~3안", 2 <= len(ps) <= 3 if isinstance(ps, list) else ps, True)
check("모든 안 합계 ≤ 20,000원", all(p.total <= 20000 for p in ps), True)
check("모든 안 주류 0개", sum(is_alcohol(x.menu_id) for p in ps for x in p.drinks + p.desserts), 0)
check("모든 안 음료 정확히 2개 (1인당 1개)",
      all(len(p.drinks) == 2 and all(menu_by_id(x.menu_id)["분류"] in ("커피", "차/논커피")
                                     for x in p.drinks) for p in ps), True)
check("모든 안 디저트 1개 이상", all(len(p.desserts) >= 1 for p in ps), True)
check("안끼리 음료가 겹치지 않음",
      len({x.menu_id for p in ps for x in p.drinks}) == sum(len({x.menu_id for x in p.drinks}) for p in ps), True)
s = "\n".join(budget_lines("2만 원밖에 없는데 두 사람 음료랑 간식 추천해 줘"))
check("calc 형식 '[예산안] 1안: ... = 합계 N원 · 잔액 M원'",
      bool(__import__("re").search(r"\[예산안\] 1안: .+ = 합계 [\d,]+원 · 잔액 [\d,]+원", s)), True)
_ps = plans(20000, 2, True)
check("안별 잔액 줄 = 예산 − 합계 (S02 T1)",
      "[예산안] 잔액(코드 계산, 안마다 말하기): " + " · ".join(f"{i}안 {20000 - p.total:,}원"
                                                       for i, p in enumerate(_ps, 1)) in s, True)
check("calc 에 '인기' 없음 (P12)", "인기" in s, False)
s = "\n".join(budget_lines("5000원으로 두 명 음료랑 디저트"))
check("5,000원·2명 → 조합 없음 + 최소 금액 10,800원 안내",
      ("조합 없음" in s, "최소 10,800원" in s, "1안" in s), (True, True, False))
s = "\n".join(budget_lines("3만원으로 혼자 커피랑 케이크"))
check("가격이 갈리는 메뉴는 '가장 싼 구성'으로 표시",
      all(("(가장 싼 구성)" in ln) == any(n in ln for n in ["아메리카노", "카페 라떼", "바닐라 라떼"])
          for ln in s.splitlines() if "안:" in ln), True)
check("같은 메뉴 2잔 조합 허용", any(len({x.menu_id for x in p.drinks}) == 1
                                for p in plans(9000, 2, False, limit=50)), True)
for text, want in [("2만 원", 20000), ("1만 2천원", 12000), ("만오천원", 15000),
                   ("15,000원", 15000), ("오천원", 5000), ("이만원", 20000)]:
    check(f"예산 읽기 '{text}' → {want:,}", parse_budget(text), want)
for text, want in [("두 사람", 2), ("3명", 3), ("혼자", 1), ("둘이", 2)]:
    check(f"인원 읽기 '{text}' → {want}", parse_people(text), want)
c = Cart(table_id=1)
r = safe(lambda: handle_stub("2만 원밖에 없는데 두 사람 음료랑 간식 추천해 줘",
                             {"intent": "예산추천", "budget": 20000, "people": 2,
                              "wants": ["음료", "디저트"]}, c))
check("예산추천 → 장바구니에 담지 않음, 🧾 줄 없음",
      (len(c.items), "🧾" in getattr(r, "reply", "")), (0, False))
r = safe(lambda: handle_stub("만 원으로 혼자 마실 거 추천", {"intent": "추천"}))
check("라우터가 '추천'이라 해도 금액이 있으면 예산추천", getattr(r, "intent", r), "예산추천")

print("\n【 판매 단위 표시 — '약과(2개입) 2접시' (P17) 】")
from src.cart import unit_label
check("약과 ×2 → 약과(2개입) 2접시", unit_label("M28", 2), "약과(2개입) 2접시")
check("쑥인절미 ×1 → 쑥인절미(4개입) 1접시", unit_label("M29", 1), "쑥인절미(4개입) 1접시")
check("개수가 없는 메뉴는 해당 없음", (unit_label("M18", 2), unit_label("M02", 1)), (None, None))
c, s = safe(lambda: calc("약과 두 접시랑 인절미 하나", "장바구니",
                         {"menu_name": "약과", "qty": 2}, {"menu_name": "쑥인절미", "qty": 1}))
check("[담기완료] 줄도 판매 단위",
      ("[담기완료] 약과(2개입) 2접시 · 9,000원" in s, "[담기완료] 쑥인절미(4개입) 1접시 · 5,500원" in s),
      (True, True))
check("장바구니 줄도 판매 단위", c.as_text().splitlines()[:2],
      ["1. 약과(2개입) 2접시  9,000원", "2. 쑥인절미(4개입) 1접시  5,500원"])
check("장바구니에 '약과 2개 ×' 형식 없음", "약과 2개 ×" in c.as_text(), False)
s = "\n".join(budget_lines("2만 원밖에 없는데 두 사람 음료랑 간식 추천해 줘"))
check("예산안도 판매 단위 ('약과 2개' 원래 이름 없음)",
      ("약과(2개입)" in s, "약과 2개" in s), (True, False))

print("\n【 C-1 장바구니 빼기·수정 (Q15) 】")
from src.kiosk import apply_order_items
def cart_with(*specs):
    c = Cart(table_id=1)
    for s in specs:
        add(c, *s[0], **s[1])
    return c
def run(c, *items):
    return "\n".join(apply_order_items(list(items), c))

c = cart_with((("M03", "HOT", "S"), {"qty": 2, "milk": "oat", "bean": "B03"}))
s = run(c, {"action": "update", "menu_name": "카페 라떼", "match": {"milk": "oat"},
            "apply_to": 1, "milk": "dairy"})
check("Q15 오트 라떼 2잔 중 1잔만 일반 우유 → 줄 나눔",
      [(i.qty, i.milk, i.bean) for i in c.items], [(1, "oat", "B03"), (1, None, "B03")])
check("Q15 원두(디카페인)는 두 잔 모두 유지", all(i.bean == "B03" for i in c.items), True)
check("Q15 합계 재계산 (6,700 + 6,200)", c.total, 12900)
check("Q15 [수정완료] 줄", s.startswith("[수정완료]"), True)

c = cart_with((("M03", "HOT", "S"), {"milk": "oat"}), (("M03", "HOT", "S"), {}))
s = run(c, {"action": "update", "menu_name": "라떼", "match": {}, "milk": "soy"})
check("같은 메뉴 두 줄인데 대상 불명 → 바꾸지 않고 되묻기",
      ("어느 것인지 확인이 필요" in s, [i.milk for i in c.items]), (True, ["oat", None]))
s = run(c, {"action": "update", "menu_name": "라떼", "match": {"milk": "dairy"}, "milk": "soy"})
check("match 로 일반 우유 줄을 특정 → 그 줄만 두유", [i.milk for i in c.items], ["oat", "soy"])

c = cart_with((("M02", "ICED", "S"), {"qty": 2}))
s = run(c, {"action": "update", "menu_name": "아메리카노", "match": {}, "size": "L"})
check("크기만 변경 → 수량 유지, 주문 단위 변경",
      [(i.variant_id, i.qty) for i in c.items], [("M02-ICED-L", 2)])
s = run(c, {"action": "update", "menu_name": "아메리카노", "match": {}, "qty": 3})
check("수량 변경", [i.qty for i in c.items], [3])
s = run(c, {"action": "update", "menu_name": "아메리카노", "match": {}, "qty": 0})
check("수량 0 으로 변경 → 거부, 그대로", ([i.qty for i in c.items], "수량" in s), ([3], True))

c = cart_with((("M07",), {}))
s = run(c, {"action": "update", "menu_name": "크림 라떼", "match": {}, "milk": "oat"})
check("수정도 옵션 검증 — 크림 라떼 오트 거부, 그대로",
      ([i.milk for i in c.items], "바꾸지 않았습니다" in s), ([None], True))
c = cart_with((("M04",), {}))
s = run(c, {"action": "update", "menu_name": "카푸치노", "match": {}, "temp": "ICED"})
check("없는 구성(카푸치노 ICED)으로 변경 → 거부", ([i.temp for i in c.items], "그 구성은 없습니다" in s),
      (["HOT"], True))
c = cart_with((("M02", "ICED", "S"), {"ice": "less"}))
s = run(c, {"action": "update", "menu_name": "아메리카노", "match": {}, "temp": "HOT"})
check("HOT 으로 바꾸면 남은 '얼음 적게'가 안 맞음 → 거부", [i.temp for i in c.items], ["ICED"])

c = cart_with((("M02", "ICED", "S"), {"qty": 2}), (("M28",), {}))
s = run(c, {"action": "remove", "menu_name": "아메리카노", "match": {}, "qty": 1})
check("아메리카노 1잔 빼기 → 1잔 남음", [(i.menu_id, i.qty) for i in c.items], [("M02", 1), ("M28", 1)])
s = run(c, {"action": "remove", "menu_name": "약과", "match": {}, "qty": None})
check("약과 빼기 (수량 없음) → 줄 삭제 + [빼기완료]",
      ([i.menu_id for i in c.items], s.startswith("[빼기완료] 약과(2개입) 1접시")), (["M02"], True))
s = run(c, {"action": "remove", "menu_name": "치즈케이크", "match": {}})
check("없는 품목 빼기 → 안내만", ("맞는 품목이 없습니다" in s, len(c.items)), (True, 1))
c = cart_with((("M02", "ICED", "S"), {}), (("M02", "HOT", "S"), {}))
s = run(c, {"action": "remove", "menu_name": "아메리카노", "match": {}})
check("두 줄 중 대상 불명 빼기 → 되묻기 (번호 목록)",
      ("1번 아메리카노 ICED/S ×1 / 2번 아메리카노 HOT/S ×1" in s, len(c.items)), (True, 2))
s = run(c, {"action": "remove", "menu_name": "아메리카노", "match": {"temp": "HOT"}})
check("match 온도로 특정해 빼기", [i.temp for i in c.items], ["ICED"])
c = cart_with((("M02", "ICED", "S"), {}))
r = safe(lambda: handle_stub("아메리카노 빼 주세요", {"intent": "장바구니", "order_items": [
    {"action": "remove", "menu_name": "아메리카노", "match": {}}]}, c))
check("빼기도 장바구니 변경 → 🧾 줄", getattr(r, "reply", "").splitlines()[-1], "🧾 합계 0원")
c = Cart(table_id=1)
s = run(c, {"menu_name": "아아", "size": "S", "qty": 1})
check("action 없으면 add (기존 라우터 출력 호환)", len(c.items), 1)
c = Cart(table_id=1)
s = run(c, {"action": "add", "menu_name": "오트 라떼", "temp": None, "size": "S", "qty": 2,
            "bean": "B03", "milk": "oat", "warming": "warm"})
check("음료에 온 warming=warm 은 HOT 으로 (따뜻한 라떼)",
      [(i.variant_id, i.qty, i.milk, i.bean, i.warming) for i in c.items],
      [("M03-HOT-S", 2, "oat", "B03", None)])
c = Cart(table_id=1)
s = run(c, {"action": "add", "menu_name": "소금빵", "qty": 1, "warming": "warm"})
check("디저트 데우기는 그대로 옵션", [i.warming for i in c.items], ["warm"])

print("\n【 C-3 라우터 JSON 안정화 】")
from src.router import parse as rparse, _llm as router_llm
check("라우터는 JSON 모드로 호출", router_llm().model_kwargs.get("response_format"), {"type": "json_object"})
r = rparse('{"intent":"장바구니","rewritten_query":"x","language":"ko","order_items":[{"menu_name":"아아"}]}', "아아")
check("정상 JSON → errors 없음, 기본 키 채움",
      (r["errors"], r["budget"], r["wants"], len(r["order_items"])), ([], None, [], 1))
r = rparse('```json\n{"intent":"추천","rewritten_query":"x","language":"ko"}\n```', "x")
check("코드펜스가 붙어도 파싱", (r["intent"], r["errors"]), ("추천", []))
r = rparse("죄송합니다, 다시 말씀해 주세요", "아아 하나")
check("파싱 실패 → errors 에 기록 (조용히 넘어가지 않음)",
      (r["intent"], r["errors"][0].startswith("JSON 파싱 실패")), ("메뉴질문", True))
r = rparse('{"intent":"주문","order_items":"아아"}', "아아")
check("모르는 intent·잘못된 order_items → 기록 후 보정",
      (r["intent"], r["order_items"], len(r["errors"])), ("메뉴질문", [], 2))
r = rparse('{"intent":"장바구니","order_items":[{"menu_name":"아아"},"라떼",{"qty":1}]}', "x")
check("형식이 틀린 항목만 제외", (len(r["order_items"]), any("2개 형식 오류" in e for e in r["errors"])), (1, True))
c = Cart(table_id=1)
saved_route = K.route
K.route = lambda *a, **k: rparse("not json", "아아 하나 담아줘")
saved = K.answer, K.hybrid_search
K.answer = lambda *a, **k: ("(모델 답변)", True)
K.hybrid_search = lambda *a, **k: ([], [("벡터", "아메리카노", 0.9)])
try:
    res = K.handle("아아 하나 담아줘", None, c)
finally:
    K.route, (K.answer, K.hybrid_search) = saved_route, saved
check("파싱 실패 턴 → trace 맨 앞에 라우터·실패", res.trace[0][0], "라우터·실패")
check("파싱 실패 턴 → 담지 않고 calc 에 다시 말해 달라고", (len(c.items), "해석하지 못했습니다" in res.calc), (0, True))

print("\n【 C-2 주문 확정 2단계 · 확정 주문 보존 (P05 · P06 · Q19 · Q23) 】")
from src import orders
def turn(text, cart, router_out=None):
    """라우터를 부르면 실패로 표시한다 — 확인 턴은 LLM 0회여야 한다."""
    called = []
    saved = K.route, K.answer, K.hybrid_search
    def fake_route(*a, **k):
        called.append(1)
        return dict({"rewritten_query": text, "language": "ko", "order_items": [],
                     "budget": None, "people": None, "wants": [], "errors": []},
                    **(router_out or {"intent": "메뉴질문"}))
    K.route, K.answer = fake_route, (lambda *a, **k: ("(모델 답변)", True))
    K.hybrid_search = lambda *a, **k: ([], [])
    try:
        return K.handle(text, None, cart), bool(called)
    finally:
        K.route, K.answer, K.hybrid_search = saved

for w in ["네", "네!", "예", "확정해 주세요", "yes", "OK"]:
    check(f"긍정 '{w}'", orders.is_yes(w), True)
for w in ["네 그리고 라떼 하나 더", "라떼 추가", "아니요"]:
    check(f"긍정 아님 '{w}'", orders.is_yes(w), False)
check("'아까 주문한 것 하나 더' 인식", orders.is_repeat_request("아까 주문한 것 하나 더"), True)
check("'아메리카노 하나 더' 는 복사 요청 아님", orders.is_repeat_request("아메리카노 하나 더"), False)

c = Cart(table_id=5); add(c, "M02", "ICED", "S", qty=2); add(c, "M28")
r, _ = turn("지금 주문 확정할게요", c, {"intent": "결제"})
check("Q23 첫 확정 요청 → 확정하지 않고 확인 대기",
      (c.pending, len(c.confirmed_orders), len(c.items)), ("confirm", 0, 2))
check("Q23 확인 요약에 좌석·품목·옵션·수량·합계",
      all(w in r.reply for w in ["좌석 5번", "아메리카노 ICED/S ×2", "약과(2개입) 1접시", "합계 13,500원",
                                 "이대로 확정할까요?"]), True)
r, routed = turn("네", c)
check("Q23 '네' → 확정, LLM 0회", (len(c.confirmed_orders), routed, r.llm_calls), (1, False, 0))
o = c.confirmed_orders[0]
check("확정 주문 보존 (좌석·품목 2개·13,500원)", (o["table_id"], len(o["items"]), o["total"]), (5, 2, 13500))
check("확정 후 장바구니 비움 · 대기 해제", (len(c.items), c.pending), (0, None))
check("확정 답변에 주문번호·시연용 안내", (o["order_no"] in r.reply, "실제 결제가 이루어지지는 않았습니다" in r.reply),
      (True, True))

c = Cart(table_id=5); add(c, "M02", "ICED", "S")
turn("결제할게요", c, {"intent": "결제"})
r, routed = turn("아니요", c)
check("'아니요' → 확정 취소, 장바구니 유지, LLM 0회",
      (c.pending, len(c.items), len(c.confirmed_orders), routed), (None, 1, 0, False))
turn("결제할게요", c, {"intent": "결제"})
r, routed = turn("라떼 하나 추가해 주세요", c, {"intent": "장바구니", "order_items": [
    {"action": "add", "menu_name": "카페 라떼", "temp": "HOT", "size": "S", "qty": 1}]})
check("다른 말 → 대기 취소 후 평소대로 처리 (라떼 담김, 확정 안 됨)",
      (c.pending, len(c.items), len(c.confirmed_orders), routed), (None, 2, 0, True))
check("다른 말 턴의 calc 에 대기 취소 안내", "대기를 취소했습니다" in r.calc, True)
turn("결제할게요", c, {"intent": "결제"})
c.remove(0)
check("확인 대기 중 장바구니를 고치면 대기 해제 (옛 요약으로 확정 방지)", c.pending, None)

c = Cart(table_id=5); add(c, "M35")
r, _ = turn("확정할게요", c, {"intent": "결제"})
check("주류 + 직원 확인 전 → 확인 대기도 하지 않음",
      (c.pending, "직원의 나이 확인 전에는 확정할 수 없습니다" in r.reply), (None, True))
c.staff_checked = True
turn("확정할게요", c, {"intent": "결제"}); turn("네", c)
check("직원 확인 후엔 확정, 다음 주문에 확인 재사용 안 함 (Q23)",
      (len(c.confirmed_orders), c.staff_checked), (1, False))

c = Cart(table_id=5)
r, routed = turn("아까 주문한 것 하나 더", c)
check("Q19 확정 주문 없으면 안내만", ("확정된 주문이 없습니다" in r.reply, c.pending, routed), (True, None, False))
add(c, "M03", "HOT", "S", milk="oat"); add(c, "M28", qty=2)
turn("확정", c, {"intent": "결제"}); turn("네", c)
first = c.confirmed_orders[0]
r, routed = turn("아까 주문한 것 하나 더", c)
check("Q19 복사 전에 품목·옵션·수량 보여 주고 확인",
      (c.pending, len(c.items), "카페 라떼 HOT/S (오트) ×1" in r.reply, "약과(2개입) 2접시" in r.reply, routed),
      ("copy", 0, True, True, False))
r, _ = turn("네", c)
check("Q19 '네' → 새 장바구니에 같은 구성", [(i.menu_id, i.milk, i.qty) for i in c.items],
      [("M03", "oat", 1), ("M28", None, 2)])
check("Q19 복사 턴도 🧾 줄", r.reply.splitlines()[-1], f"🧾 합계 {c.total:,}원")
c.items[0].qty = 3
check("Q19 새 장바구니를 바꿔도 확정 주문은 그대로", first["items"][0].qty, 1)
turn("확정", c, {"intent": "결제"}); turn("네", c)
check("추가 주문은 같은 좌석의 새 주문 (주문번호 다름)",
      (len(c.confirmed_orders), c.confirmed_orders[1]["table_id"],
       c.confirmed_orders[0]["order_no"] != c.confirmed_orders[1]["order_no"]), (2, 5, True))

print("\n【 시연 시나리오 파일 형식 (tests/demo_scenarios.md) 】")
import importlib.util, re as _re
spec = importlib.util.spec_from_file_location("run_checks", pathlib.Path(__file__).parent / "run_checks.py")
rc = importlib.util.module_from_spec(spec); spec.loader.exec_module(rc)
scs = rc.parse_scenarios((pathlib.Path(__file__).parent / "demo_scenarios.md").read_text(encoding="utf-8"))
check("시나리오 10개 (S01~S10)", [s["id"] for s in scs], [f"S{i:02d}" for i in range(1, 11)])
check("모든 시나리오에 HTI 말단 과업 ID", all(_re.search(r"[A-F]\d", s["hti"]) for s in scs), True)
check("모든 시나리오에 검증질문 ID", all(_re.search(r"Q\d{2}", s["qids"]) for s in scs), True)
check("모든 손님 발화에 기대 처리",
      all(tn["expect"] for s in scs for tn in s["turns"] if "say" in tn), True)
check("S08 에 직원확인 단계", any(tn.get("staff_check") for tn in scs[7]["turns"]), True)

print("\n【 ⚠️/🧾 줄은 코드만 붙인다 (S02·S03 중복) 】")
from src.kiosk import strip_footer_lines
check("모델이 쓴 ⚠️/🧾 줄 제거, 본문은 유지",
      strip_footer_lines("루이보스티 담았습니다.\n⚠️ 카페인 0mg  \n🧾 합계 5,000원"), "루이보스티 담았습니다.")
check("⚠️/🧾 로 시작하지 않는 줄은 그대로", strip_footer_lines("합계는 아래에 있어요"), "합계는 아래에 있어요")
c = Cart(table_id=1)
saved = K.route, K.answer, K.hybrid_search
K.route = lambda *a, **k: {"intent": "장바구니", "rewritten_query": "x", "language": "ko", "errors": [],
                           "order_items": [{"action": "add", "menu_name": "루이보스티", "temp": "HOT", "qty": 1}]}
K.answer = lambda *a, **k: ("담았습니다.\n⚠️ 카페인 0mg\n🧾 합계 5,000원", True)
K.hybrid_search = lambda *a, **k: ([], [])
try:
    r = K.handle("루이보스티 따뜻하게 하나", None, c)
finally:
    K.route, K.answer, K.hybrid_search = saved
check("답변 끝 🧾 줄은 코드 것 하나뿐, 0mg ⚠️ 없음",
      (r.reply.count("🧾"), "⚠️" in r.reply, r.reply.splitlines()[-1]), (1, False, "🧾 합계 5,000원"))
import src.prompts as _sp
check("system.md 에 ⚠️/🧾 형식 설명 없음",
      any(m in _sp.load("system") for m in ("⚠️", "🧾")), False)

print("\n【 P07 미지원 — 범위밖 판정 뒤집기 (S10 T2 · Q17 · Q18) 】")
from src.conditions import unsupported_hits
check("기프티콘 + 반씩 → 쿠폰·기프티콘, 분할 결제", unsupported_hits("기프티콘 쓰고 반씩 결제해줘"),
      ["쿠폰·기프티콘", "분할 결제"])
check("몇 분 뒤에 나와요 → 대기시간", unsupported_hits("제 커피 몇 분 뒤에 나와요?"), ["실시간 재고·제조 진행·대기시간"])
check("'직원 확인 대기' 는 미지원 아님", unsupported_hits("직원 확인 대기 중이에요?"), [])
for text in ["기프티콘 쓰고 반씩 결제해줘", "제 커피 몇 분 뒤에 나와요?"]:
    r = safe(lambda: handle_stub(text, {"intent": "범위밖"}))
    check(f"라우터 범위밖이어도 '{text}' → 메뉴질문 + [미지원]",
          (getattr(r, "intent", r), "[미지원]" in getattr(r, "calc", "")), ("메뉴질문", True))
r = safe(lambda: handle_stub("오늘 날씨 어때요", {"intent": "범위밖"}))
check("미지원 키워드 없는 범위밖은 그대로", getattr(r, "intent", r), "범위밖")
r = safe(lambda: handle_stub("기프티콘 쓰고 반씩 결제해줘", {"intent": "결제"}))
check("결제 의도로 와도 미지원 항목을 코드가 안내",
      "이 키오스크에서 지원하지 않습니다: 쿠폰·기프티콘 · 분할 결제" in getattr(r, "reply", ""), True)
check("P07 문서가 검색에 들어감 ('몇 분')", "P07" in rule_hits("제 커피 몇 분 뒤에 나와요?")[1], True)


_sp.load.cache_clear(); _sys = _sp.load("system")
check("system.md: [담기완료] 면 '담아 드릴까요?' 묻지 않는 규칙 (S09 T3)",
      "[담기완료] 가 있으면 그 품목은 이번 턴에 이미 장바구니에 담겼다" in _sys and "담아 드릴까요?" in _sys, True)

print("\n【 답변 temperature 환경변수 】")
import subprocess, os as _os
def _temp(env_val):
    env = dict(_os.environ, MOKI_MOCK="1")
    env.pop("MOKI_ANSWER_TEMPERATURE", None)
    if env_val is not None:
        env["MOKI_ANSWER_TEMPERATURE"] = env_val
    out = subprocess.run([sys.executable, "-c", "from src.config import ANSWER_TEMPERATURE as t; print(t)"],
                         cwd=str(pathlib.Path(__file__).resolve().parent.parent), env=env,
                         capture_output=True, text=True)
    return out.stdout.strip().splitlines()[-1] if out.stdout.strip() else out.stderr[-200:]
check("기본값 0", _temp(None), "0.0")
check("MOKI_ANSWER_TEMPERATURE=0.3 → 0.3", _temp("0.3"), "0.3")
check("chain 이 설정값을 씀 (0.3 고정값 없음)",
      "temperature=0.3" in (pathlib.Path(__file__).resolve().parent.parent / "src/chain.py").read_text(), False)

print(f"\n{'='*52}\n통과 {ok} · 실패 {fail}   (API 호출 0회)")
