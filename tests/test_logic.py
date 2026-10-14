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

print(f"\n{'='*52}\n통과 {ok} · 실패 {fail}   (API 호출 0회)")
