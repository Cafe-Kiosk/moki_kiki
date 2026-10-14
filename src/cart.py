"""장바구니 경계에서 데이터 규칙을 검증하고 확정 주문을 보존한다."""
from __future__ import annotations
import copy, re, uuid
from dataclasses import dataclass, field, replace, asdict
from functools import lru_cache
import openpyxl
from .config import DATA_XLSX, MIN_QTY, MAX_QTY, TABLES
from .documents import _sheet_rows

OPTION_FIELDS = ("bean", "extra_shots", "milk", "sweetness", "ice", "warming")
CHOICES = {"bean": {"B01", "B02", "B03"}, "milk": {"dairy", "lowfat", "oat", "soy"},
           "sweetness": {"normal", "less"}, "ice": {"normal", "less"}, "warming": {"room", "warm"}}

@lru_cache(maxsize=1)
def _tables():
    wb = openpyxl.load_workbook(DATA_XLSX, data_only=True)
    return ({m["메뉴 ID"]: m for m in _sheet_rows(wb, "메뉴목록")},
            {v["주문 단위 ID"]: v for v in _sheet_rows(wb, "가격영양")})

@lru_cache(maxsize=1)
def option_rules():
    wb = openpyxl.load_workbook(DATA_XLSX, data_only=True)
    return {r["옵션 ID"]: r for r in _sheet_rows(wb, "옵션규칙")}

def menu_by_id(mid): return _tables()[0].get(mid)
def variant_by_id(vid): return _tables()[1].get(vid)
def find_variants(mid): return [v for k, v in _tables()[1].items() if k.startswith(mid + "-")]

def resolve_variant(mid, temp=None, size=None):
    vs = find_variants(mid)
    cand = [v for v in vs if (not temp or v["온도"] == temp.upper()) and (not size or v["크기"] == size.upper())]
    return (cand[0] if len(cand) == 1 else None), vs

def _integer(value, low, high, label):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{label}: {low}~{high} 사이의 정수를 입력해 주세요.")

def _fee(rule, value):
    match = re.search(rf"(?:^|\n){re.escape(value)}:[^\n]*?\+(\d+)원", str(rule["선택값과 추가금"]))
    if not match: raise ValueError("옵션 가격 자료를 확인할 수 없습니다.")
    return int(match.group(1))

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
    line_id: str = field(default_factory=lambda: "L" + uuid.uuid4().hex[:8])

    def validate(self):
        m, v = menu_by_id(self.menu_id), variant_by_id(self.variant_id)
        if not m or not v or not self.variant_id.startswith(self.menu_id + "-"):
            raise ValueError("현재 판매하는 메뉴와 구성을 골라 주세요.")
        if self.temp != v["온도"] or self.size != v["크기"] or self.name != m["메뉴명"]:
            raise ValueError("메뉴·온도·크기 정보가 판매 구성과 다릅니다.")
        _integer(self.qty, MIN_QTY, MAX_QTY, "수량")
        for key in OPTION_FIELDS:
            value = getattr(self, key)
            if value is None and key != "extra_shots": continue
            rule = option_rules()[key]
            if key == "extra_shots":
                _integer(value, 0, 2, "추가 샷")
                if value == 0: continue
            elif value not in CHOICES[key]:
                raise ValueError(f"{rule['옵션명']}: 제공하지 않는 선택값입니다.")
            if self.menu_id not in {s.strip() for s in str(rule["적용 메뉴 ID"]).split(",")}:
                raise ValueError(f"{self.name}: {rule['옵션명']}은 지원하지 않습니다.")
            if key == "ice" and self.temp != "ICED":
                raise ValueError("얼음 양은 가능한 ICED 메뉴에서만 선택할 수 있습니다.")
        self.is_alcohol = str(m.get("주류 구분", "")).startswith("주류 포함")
        return self

    @property
    def base_price(self): return int(variant_by_id(self.variant_id)["가격(원)"])
    @property
    def option_fee(self):
        return sum(_fee(option_rules()[k], getattr(self, k)) for k in CHOICES if getattr(self, k) is not None) + 600 * self.extra_shots
    @property
    def unit_price(self): return self.base_price + self.option_fee
    @property
    def subtotal(self): return self.unit_price * self.qty

    def nutrition(self):
        v = variant_by_id(self.variant_id)
        caffeine = v.get("카페인(mg)")
        if self.bean or self.extra_shots:
            wb = openpyxl.load_workbook(DATA_XLSX, data_only=True)
            beans = {b["원두 ID"]: b for b in _sheet_rows(wb, "원두")}
            bid = self.bean or v.get("원두 ID")
            if bid in beans:
                caffeine = (int(v.get("기본 샷") or 0) + self.extra_shots) * beans[bid]["카페인(mg/샷)"] + (v.get("에스프레소 외 카페인(mg)") or 0)
        changed = self.extra_shots > 0 or self.bean not in (None, v.get("원두 ID")) or self.milk not in (None, "dairy") or self.sweetness == "less"
        return {"caffeine_mg_per_unit": caffeine, "nutrition": "미산정" if changed else "기본 레시피 시연값",
                "allergy_notice": "성분과 교차접촉 가능성은 바리스타에게 확인해 주세요."}

    def option_text(self, language="ko"):
        labels = {"B01": "하우스", "B02": "에티오피아", "B03": "디카페인", "dairy": "일반 우유",
                  "lowfat": "저지방 우유", "oat": "오트", "soy": "두유"}
        if language == "en":
            labels = {"B01": "house", "B02": "Ethiopian", "B03": "decaf", "dairy": "dairy", "lowfat": "low-fat", "oat": "oat", "soy": "soy"}
        bits = [labels[x] for x in (self.bean, self.milk) if x]
        if self.extra_shots: bits.append(f"샷+{self.extra_shots}")
        if self.sweetness == "less": bits.append("시럽/청 절반")
        if self.ice == "less": bits.append("얼음 적게")
        if self.warming == "warm": bits.append("데우기")
        text = " · ".join(bits)
        if language == "en":
            for ko,en in [("샷+","extra shots +"),("시럽/청 절반","half syrup"),("얼음 적게","less ice"),("데우기","warmed")]: text=text.replace(ko,en)
        return text

@dataclass
class Cart:
    table_id: int | None = None
    items: list[CartItem] = field(default_factory=list)
    order_no: str | None = None
    staff_checked: bool = False  # 호환 필드. 고객/LLM의 값은 직원 인증으로 신뢰하지 않는다.
    language: str = "ko"
    service_mode: str = "dine_in"
    version: int = 0
    reviewed_version: int | None = None
    previous_orders: list[dict] = field(default_factory=list)
    pending_actions: list[dict] = field(default_factory=list)
    pending_cancel: bool = False
    avoid_allergens: list[str] = field(default_factory=list)
    max_caffeine_mg: int | None = None
    avoid_alcohol: bool = False
    undo_state: dict | None = None

    def _editable(self):
        if self.order_no: raise ValueError("확정 주문은 바꿀 수 없습니다. 추가 주문을 새로 시작해 주세요.")
    def remember(self):
        self.undo_state = {"items":copy.deepcopy(self.items), "table_id":self.table_id, "service_mode":self.service_mode}

    def undo(self):
        self._editable()
        if self.undo_state is None: raise ValueError("되돌릴 변경이 없습니다.")
        saved = self.undo_state
        for item in saved["items"]: self.validate_item(item)
        self.items = copy.deepcopy(saved["items"]);self.table_id=saved["table_id"];self.service_mode=saved["service_mode"]
        self.undo_state=None;self._changed()

    def _changed(self):
        self.version += 1; self.reviewed_version = None

    def validate_item(self, item):
        checked = item.validate()
        if checked.is_alcohol and (self.service_mode != "dine_in" or self.avoid_alcohol):
            raise ValueError("주류는 포장하거나 알코올 회피 조건에서 담을 수 없습니다.")
        allergens = str(menu_by_id(checked.menu_id).get("알레르기 유발 재료") or "")
        if checked.milk and checked.milk != "dairy":
            replacement = {"lowfat":"우유", "oat":"귀리", "soy":"대두"}[checked.milk]
            allergens = allergens.replace("우유", replacement)
        if any(a and a in allergens for a in self.avoid_allergens):
            raise ValueError("피하기로 한 성분이 포함된 메뉴입니다. 다른 메뉴를 고르거나 바리스타에게 확인해 주세요.")
        caffeine = checked.nutrition()["caffeine_mg_per_unit"]
        if self.max_caffeine_mg is not None and (caffeine is None or caffeine > self.max_caffeine_mg):
            raise ValueError("카페인 상한을 충족한다고 확인할 수 없습니다. 다른 메뉴를 골라 주세요.")
        return checked

    def add(self, item):
        try:
            self._editable()
            checked = self.validate_item(copy.deepcopy(item))
            if checked.is_alcohol and self.service_mode != "dine_in": raise ValueError("주류는 포장할 수 없습니다.")
            self.remember(); self.items.append(checked); self._changed()
            return True, ""
        except ValueError as exc: return False, str(exc)

    def remove(self, idx):
        self._editable()
        if not 0 <= idx < len(self.items): raise ValueError("변경할 품목을 확인해 주세요.")
        self.remember(); self.items.pop(idx); self._changed()

    def set_qty(self, idx, qty):
        try:
            self._editable(); _integer(qty, MIN_QTY, MAX_QTY, "수량")
            if not 0 <= idx < len(self.items): raise ValueError("변경할 품목을확인해 주세요.")
            self.remember(); self.items[idx].qty = qty; self._changed()
            return True, ""
        except ValueError as exc: return False, str(exc)

    def update(self, idx, changes, affected_qty=None):
        self._editable()
        old = self.items[idx]; count = old.qty if affected_qty is None else affected_qty
        _integer(count, 1, old.qty, "변경할 잔 수")
        new = self.validate_item(replace(old, **changes, qty=count))
        if new.is_alcohol and self.service_mode != "dine_in": raise ValueError("주류는 포장할 수 없습니다.")
        self.remember()
        if count < old.qty:
            new.line_id = "L" + uuid.uuid4().hex[:8]
            self.items[idx] = replace(old, qty=old.qty-count); self.items.append(new)
        else: self.items[idx] = new
        self._changed()

    def start_additional(self):
        if not self.order_no: raise ValueError("현재 주문을 먼저 검토하거나 취소해 주세요.")
        self.previous_orders.append(self.snapshot())
        self.undo_state = None
        self.items = []; self.order_no = None; self.staff_checked = False
        self.pending_actions = []; self.pending_cancel = False; self._changed()

    def set_service(self, mode):
        self._editable()
        if mode not in ("dine_in", "takeout"): raise ValueError("매장 이용/포장을 골라 주세요.")
        if mode == "takeout" and self.has_alcohol: raise ValueError("주류는 포장할 수 없습니다.")
        self.remember(); self.service_mode = mode; self._changed()

    @property
    def total(self): return sum(i.subtotal for i in self.items)
    @property
    def has_alcohol(self): return any(i.is_alcohol for i in self.items)
    def status(self):
        if self.order_no: return "confirmed_demo"
        return "pending_staff_check" if self.has_alcohol else "draft"

    def review(self):
        self.reviewed_version = self.version
        return self.as_text()

    def confirm(self):
        if self.order_no: return True, self.order_no
        if not self.items: return False, "장바구니가 비어 있습니다."
        if type(self.table_id) is not int or self.table_id not in TABLES: return False, "좌석 1~12를 먼저 확인해 주세요."
        if self.has_alcohol: return False, "주류는 해당 손님의 직원 확인 전에는 확정할 수 없습니다. 현재 시연은 확인 대기까지 지원합니다."
        if self.reviewed_version != self.version: return False, "변경된 최종 주문 내역을 먼저 확인하고 다시 확정해 주세요."
        try:
            for item in self.items: self.validate_item(item)
        except ValueError as exc: return False, str(exc)
        self.undo_state = None
        self.order_no = "M" + uuid.uuid4().hex[:8].upper()
        return True, self.order_no

    def snapshot(self):
        return {"table_id": self.table_id, "language": self.language, "service_mode": self.service_mode,
                "cart_version": self.version, "undo_available": self.undo_state is not None, "avoid_allergens": self.avoid_allergens,
                "max_caffeine_mg": self.max_caffeine_mg, "avoid_alcohol": self.avoid_alcohol, "order_status": self.status(), "order_no": self.order_no,
                "cart": [asdict(i) | {"unit_price": i.unit_price, "subtotal": i.subtotal, **i.nutrition()} for i in self.items],
                "total_krw": self.total}

    def as_text(self):
        en = self.language == "en"
        if not self.items: return "Your cart is empty." if en else "장바구니가 비어 있습니다."
        mode = ("takeout" if self.service_mode == "takeout" else "dine-in") if en else ("포장" if self.service_mode == "takeout" else "매장 이용")
        lines = [f"{'Table' if en else '좌석'} {self.table_id} · {mode}"]
        for i, it in enumerate(self.items, 1):
            name = menu_by_id(it.menu_id).get("영문명") if en else it.name
            lines.append(f"{i}. {name} {it.temp}/{it.size} ({it.option_text(self.language) or ('standard' if en else '기본')}) ×{it.qty} = {it.subtotal:,} {'KRW' if en else '원'}")
        lines.append(f"{'Total' if en else '합계'} {self.total:,} {'KRW' if en else '원'}")
        if self.has_alcohol: lines.append("Alcohol — waiting for staff verification" if en else "주류 포함 — 해당 손님 직원 확인 대기")
        if self.order_no: lines.append(f"Demo order {self.order_no} · no real payment or store submission" if en else f"시연 주문번호 {self.order_no} · 실제 결제·접수 없음")
        return "\n".join(lines)
