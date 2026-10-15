"""장바구니 · 가격 계산 · 주문번호.

가격은 모델이 말하게 두지 않고 코드가 계산한다. 모델은 계산 결과를 전달만 한다.
매장정책 P11: 단가 = 주문단위 가격 + 선택형 옵션 추가금 + 추가 샷 수 × 600
매장정책 P15: 주류가 있으면 직원 확인 전까지 pending_staff_check
"""
from __future__ import annotations
import openpyxl, random, string
from dataclasses import dataclass, field
from functools import lru_cache
from .config import DATA_XLSX, MIN_QTY, MAX_QTY
from .documents import _sheet_rows

BEAN_SURCHARGE = {"B01": 0, "B02": 1000, "B03": 700}
MILK_SURCHARGE = {"dairy": 0, "lowfat": 0, "oat": 500, "soy": 500}
SHOT_PRICE = 600

OPTION_MENUS = {
    "bean": {f"M{i:02d}" for i in range(1, 9)},
    "extra_shots": {f"M{i:02d}" for i in range(1, 9)},
    "milk": {"M03", "M04", "M05", "M06", "M10", "M13", "M15"},
    "sweetness": {"M06", "M16"},
    "ice": {"M02", "M03", "M06", "M07", "M08", "M09", "M10", "M11",
            "M12", "M13", "M14", "M15", "M16", "M17", "M26", "M27"},
    "warming": {"M18"},
}


@lru_cache(maxsize=1)
def _tables():
    wb = openpyxl.load_workbook(DATA_XLSX, data_only=True)
    menus = {m["메뉴 ID"]: m for m in _sheet_rows(wb, "메뉴목록")}
    variants = {}
    for v in _sheet_rows(wb, "가격영양"):
        variants[str(v["주문 단위 ID"])] = v
    return menus, variants


def menu_by_id(mid): return _tables()[0].get(mid)
def variant_by_id(vid): return _tables()[1].get(vid)


def list_menus() -> list[dict]:
    """엑셀에 정의된 판매 메뉴를 원본 순서대로 돌려준다."""
    return list(_tables()[0].values())


def find_variants(menu_id: str) -> list[dict]:
    _, variants = _tables()
    return [v for k, v in variants.items() if k.startswith(menu_id + "-")]


def resolve_variant(menu_id: str, temp: str | None = None, size: str | None = None):
    """온도·크기로 주문 단위를 찾는다. 하나뿐이면 그것을 쓴다.

    못 찾으면 (None, 선택지 목록)을 돌려준다. 임의로 대체하지 않는다 (P03).
    """
    vs = find_variants(menu_id)
    if not vs:
        return None, []

    cand = vs
    # 손님이 말한 온도·크기가 없으면 비슷한 것으로 바꾸지 않는다 (P03).
    # 카푸치노는 HOT 하나뿐인데 "아이스로" 라고 하면 HOT 을 담아 버리던 문제.
    if temp:
        hit = [v for v in cand if str(v.get("온도", "")).upper() == temp.upper()]
        if not hit:
            return None, vs
        cand = hit
    if size:
        hit = [v for v in cand if str(v.get("크기", "")).upper() == size.upper()]
        if not hit:
            return None, vs
        cand = hit

    if len(cand) == 1:
        return cand[0], vs
    return None, vs


@dataclass
class CartItem:
    menu_id: str
    variant_id: str
    name: str
    temp: str
    size: str
    qty: int = 1
    bean: str | None = None
    extra_shots: int = 0
    milk: str | None = None
    sweetness: str | None = None
    ice: str | None = None
    warming: str | None = None
    is_alcohol: bool = False

    @property
    def base_price(self) -> int:
        return int(variant_by_id(self.variant_id)["가격(원)"])

    @property
    def option_fee(self) -> int:
        fee = 0
        if self.bean:
            fee += BEAN_SURCHARGE.get(self.bean, 0)
        if self.milk:
            fee += MILK_SURCHARGE.get(self.milk, 0)
        fee += SHOT_PRICE * max(0, int(self.extra_shots))
        return fee

    @property
    def unit_price(self) -> int:
        return self.base_price + self.option_fee

    @property
    def subtotal(self) -> int:
        return self.unit_price * self.qty

    def option_text(self) -> str:
        bits = []
        if self.bean and self.bean != "B01":
            bits.append({"B02": "에티오피아", "B03": "디카페인"}.get(self.bean, self.bean))
        if self.extra_shots:
            bits.append(f"샷+{self.extra_shots}")
        if self.milk and self.milk != "dairy":
            bits.append({"lowfat": "저지방", "oat": "오트", "soy": "두유"}.get(self.milk, self.milk))
        if self.sweetness == "less":
            bits.append("덜 달게")
        if self.ice == "less":
            bits.append("얼음 적게")
        if self.warming == "warm":
            bits.append("따뜻하게")
        return " · ".join(bits)


def validate_item_options(item: CartItem) -> tuple[bool, str]:
    """LLM이 제안한 옵션을 Excel 허용 목록과 주문 단위에 대조한다."""
    checks = (
        ("bean", item.bean, {"B01", "B02", "B03"}),
        ("milk", item.milk, {"dairy", "lowfat", "oat", "soy"}),
        ("sweetness", item.sweetness, {"normal", "less"}),
        ("ice", item.ice, {"normal", "less"}),
        ("warming", item.warming, {"room", "warm"}),
    )
    labels = {
        "bean": "원두 선택", "milk": "우유 변경", "sweetness": "당도 변경",
        "ice": "얼음 양 변경", "warming": "데우기",
    }
    for key, value, allowed in checks:
        if value is None:
            continue
        if value not in allowed:
            return False, f"{labels[key]} 값 '{value}'은 지원하지 않습니다."
        if item.menu_id not in OPTION_MENUS[key]:
            return False, f"{item.name}에는 {labels[key]} 옵션을 적용할 수 없습니다."

    if not isinstance(item.extra_shots, int) or not 0 <= item.extra_shots <= 2:
        return False, "추가 샷은 0~2 사이의 정수만 가능합니다."
    if item.extra_shots and item.menu_id not in OPTION_MENUS["extra_shots"]:
        return False, f"{item.name}에는 샷을 추가할 수 없습니다."
    if item.ice is not None and item.temp != "ICED":
        return False, "얼음 양 변경은 ICED 주문 단위에서만 가능합니다."
    if item.is_alcohol and any((
        item.bean is not None, item.extra_shots != 0, item.milk is not None,
        item.sweetness is not None, item.ice is not None, item.warming is not None,
    )):
        return False, "주류는 고정 레시피라 옵션을 변경할 수 없습니다."
    return True, ""


@dataclass
class Cart:
    table_id: int | None = None
    items: list[CartItem] = field(default_factory=list)
    order_no: str | None = None
    staff_checked: bool = False      # P15 직원 나이 확인

    def add(self, item: CartItem) -> tuple[bool, str]:
        if not (MIN_QTY <= item.qty <= MAX_QTY):
            return False, f"수량은 {MIN_QTY}~{MAX_QTY} 사이의 정수만 가능합니다."
        self.items.append(item)
        if item.is_alcohol:
            self.staff_checked = False
        return True, ""

    def remove(self, idx: int):
        if 0 <= idx < len(self.items):
            self.items.pop(idx)

    def set_qty(self, idx: int, qty: int) -> tuple[bool, str]:
        if not (MIN_QTY <= qty <= MAX_QTY):
            return False, f"수량은 {MIN_QTY}~{MAX_QTY} 사이의 정수만 가능합니다."
        if self.items[idx].is_alcohol and qty > self.items[idx].qty:
            self.staff_checked = False
        self.items[idx].qty = qty
        return True, ""

    @property
    def total(self) -> int:
        return sum(i.subtotal for i in self.items)

    @property
    def has_alcohol(self) -> bool:
        return any(i.is_alcohol for i in self.items)

    def status(self) -> str:
        if self.has_alcohol and not self.staff_checked:
            return "pending_staff_check"
        return "ready"

    def confirm(self) -> tuple[bool, str]:
        if not self.items:
            return False, "장바구니가 비어 있습니다."
        if self.table_id is None:
            return False, "좌석 번호를 먼저 확인해 주세요."
        if self.status() == "pending_staff_check":
            return False, "주류가 포함되어 있어 직원의 나이 확인 전에는 확정할 수 없습니다."
        self.order_no = "M" + "".join(random.choices(string.digits, k=4))
        return True, self.order_no

    def as_text(self) -> str:
        if not self.items:
            return "장바구니가 비어 있습니다."
        lines = []
        for i, it in enumerate(self.items, 1):
            opt = it.option_text()
            lines.append(f"{i}. {it.name} {it.temp}/{it.size}"
                         + (f" ({opt})" if opt else "")
                         + f" ×{it.qty}  {it.subtotal:,}원")
        lines.append(f"합계 {self.total:,}원")
        if self.status() == "pending_staff_check":
            lines.append("※ 주류 포함 — 직원 확인 대기")
        return "\n".join(lines)
