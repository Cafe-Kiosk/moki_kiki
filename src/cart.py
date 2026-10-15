"""장바구니 · 가격 계산 · 주문번호.

가격은 모델이 말하게 두지 않고 코드가 계산한다. 모델은 계산 결과를 전달만 한다.
매장정책 P11: 단가 = 주문단위 가격 + 선택형 옵션 추가금 + 추가 샷 수 × 600
매장정책 P15: 주류가 있으면 직원 확인 전까지 pending_staff_check
"""
from __future__ import annotations
import openpyxl, random, re, string
from dataclasses import dataclass, field
from functools import lru_cache
from .config import DATA_XLSX, MIN_QTY, MAX_QTY
from .documents import _sheet_rows

OPTION_KEYS = ("bean", "extra_shots", "milk", "sweetness", "ice", "warming")


@lru_cache(maxsize=1)
def _tables():
    wb = openpyxl.load_workbook(DATA_XLSX, data_only=True)
    menus = {m["메뉴 ID"]: m for m in _sheet_rows(wb, "메뉴목록")}
    variants = {}
    for v in _sheet_rows(wb, "가격영양"):
        variants[str(v["주문 단위 ID"])] = v
    policies = {p["정책 ID"]: str(p.get("내용", "")) for p in _sheet_rows(wb, "매장정책")}
    return menus, variants, _parse_options(_sheet_rows(wb, "옵션규칙")), policies


def _parse_options(rows) -> dict:
    """옵션규칙 시트 → {옵션 ID: 규칙}. 추가금도 여기서 읽는다 (하드코딩 금지).

    choice  : "B02: 에티오피아 싱글오리진 +1000원" 한 줄에 선택값 하나
    integer : "0~2, 회당 600원"
    """
    out = {}
    for o in rows:
        raw = str(o.get("선택값과 추가금", ""))
        rule = {"name": str(o["옵션명"]), "default": str(o.get("기본값", "")).strip(),
                "menus": {x.strip() for x in str(o.get("적용 메뉴 ID", "")).split(",") if x.strip()},
                "limit": str(o.get("제한", "")).strip(), "kind": str(o.get("입력 형식", ""))}
        if rule["kind"] == "integer":
            lo, hi, price = map(int, re.search(r"(\d+)\s*~\s*(\d+).*?(\d+)\s*원", raw).groups())
            rule.update(range=(lo, hi), price=price, choice_text=raw)
        else:
            rule["choices"], rule["labels"] = {}, {}
            for ln in raw.splitlines():
                mt = re.match(r"\s*(\w+)\s*:\s*(.*?)\s*\+\s*(\d+)\s*원", ln)
                if mt:
                    rule["choices"][mt[1]] = int(mt[3])
                    rule["labels"][mt[1]] = mt[2]
        out[str(o["옵션 ID"])] = rule
    return out


def menu_by_id(mid): return _tables()[0].get(mid)
def variant_by_id(vid): return _tables()[1].get(vid)
def option_rules() -> dict: return _tables()[2]
def policy_text(pid: str) -> str: return _tables()[3].get(pid, "")


def is_alcohol(menu_id: str) -> bool:
    m = menu_by_id(menu_id) or {}
    return str(m.get("주류 구분", "")).startswith("주류 포함")


def option_fee_table() -> dict:
    """옵션별 추가금 (엑셀 기준). 샷은 1회 가격."""
    out = {}
    for oid, r in option_rules().items():
        out[oid] = r["price"] if r["kind"] == "integer" else dict(r["choices"])
    return out


def _alcohol_reason() -> str:
    """P15 본문에서 '고정 레시피' 문장을 사유로 쓴다."""
    for sent in re.split(r"\.\s+", policy_text("P15")):
        if "고정 레시피" in sent:
            return sent.strip().rstrip(".") + "."
    return "주류는 고정 레시피·제공 단위라 옵션을 바꿀 수 없습니다."


def _as_int(v):
    """정수만 받는다. True·1.5·'두' 같은 값은 None."""
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float) and v.is_integer():
        return int(v)
    if isinstance(v, str) and re.fullmatch(r"-?\d+", v.strip()):
        return int(v.strip())
    return None


def validate_options(menu_id: str, variant: dict | None, options: dict):
    """옵션 적용 가능 여부를 검사한다. (허용된 옵션, 거부 목록[(옵션, 사유)])

    - 사유는 옵션규칙 시트의 '제한' 문구를 그대로 쓴다
    - 기본값과 같은 값(B01·dairy·샷 0 ...)은 옵션이 아닌 것으로 본다
    - ice 는 ICED 주문 단위에만, extra_shots 는 0~2 정수만
    - 주류는 모든 옵션 거부 (P15)
    """
    rules = option_rules()
    temp = str((variant or {}).get("온도", "")).upper()
    allowed, rejected = {}, []
    for key, val in (options or {}).items():
        if val is None or val == "":
            continue
        rule = rules.get(key)
        if rule is None:
            rejected.append((key, "지원하지 않는 옵션입니다."))
            continue
        if rule["kind"] == "integer":
            n = _as_int(val)
            if n is None or not (rule["range"][0] <= n <= rule["range"][1]):
                rejected.append((key, f"{rule['name']} 횟수는 {rule['choice_text']} 범위의 정수만 가능합니다."))
                continue
            if str(n) == rule["default"]:
                continue
            val = n
        else:
            val = str(val).strip()
            if val == rule["default"]:
                continue
            if val not in rule["choices"]:
                opts = ", ".join(f"{k}({v})" for k, v in rule["labels"].items())
                rejected.append((key, f"{rule['name']} 선택값은 {opts} 중 하나입니다."))
                continue
        if is_alcohol(menu_id):
            rejected.append((key, _alcohol_reason()))
        elif menu_id not in rule["menus"]:
            rejected.append((key, f"이 메뉴는 {rule['name']} 적용 대상이 아닙니다. {rule['limit']}"))
        elif key == "ice" and temp != "ICED":
            rejected.append((key, rule["limit"]))
        else:
            allowed[key] = val
    return allowed, rejected


def option_label(key: str, val) -> str:
    """'원두 선택 콜롬비아 디카페인' 처럼 손님에게 보일 이름."""
    r = option_rules().get(key)
    if not r:
        return f"{key}={val}"
    if r["kind"] == "integer":
        return f"{r['name']} {val}회"
    return f"{r['name']} {r['labels'].get(str(val), val)}"


def option_alternatives(menu_id: str, key: str, val) -> list[str]:
    """옵션을 못 쓰는 메뉴 대신 고를 만한 메뉴 이름.

    같은 분류에서 그 옵션을 쓸 수 있는 메뉴를 맛 점수가 가까운 순으로 고른다.
    디카페인 원두를 원했다면 디카페인 메뉴(M12 등)도 함께 낸다.
    자동으로 담지 않는다 — 손님 확인용 안내일 뿐이다 (P03).
    """
    m = menu_by_id(menu_id)
    rule = option_rules().get(key)
    if not m or not rule or is_alcohol(menu_id):
        return []
    if menu_id in rule["menus"] and key != "ice":     # 메뉴가 아니라 값이 문제인 경우
        return []
    cols = ["단맛 1~5", "산미 1~5", "쓴맛 1~5", "바디 1~5"]
    tags = {t.strip() for t in str(m.get("추천 태그", "")).split(",")}

    def dist(o):
        shared = tags & {t.strip() for t in str(o.get("추천 태그", "")).split(",")}
        return sum(abs((o.get(c) or 0) - (m.get(c) or 0)) for c in cols) - 2 * len(shared)

    pool = [menu_by_id(x) for x in rule["menus"] if x != menu_id and menu_by_id(x)]
    pool = [o for o in pool if o["분류"] == m["분류"]]
    if key == "ice":                         # HOT 이라서 거부 → 같은 메뉴 ICED 가 있으면 그것
        if any(str(v.get("온도")).upper() == "ICED" for v in find_variants(menu_id)):
            return [f"{m['메뉴명']} ICED"]
    pool.sort(key=dist)
    decaf_bean = key == "bean" and str(val) == "B03"
    prefix = "디카페인 " if decaf_bean else ""
    suffix = "" if decaf_bean else f"({option_label(key, val)})"
    out = [prefix + str(o["메뉴명"]) + suffix for o in pool[:1 if decaf_bean else 2]]
    if decaf_bean:
        out += [str(x["메뉴명"]) for x in _tables()[0].values()
                if x["분류"] == m["분류"] and x["메뉴 ID"] != menu_id
                and "디카페인" in str(x["메뉴명"])]
    return out


def find_variants(menu_id: str) -> list[dict]:
    variants = _tables()[1]
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


QTY_MSG = f"수량은 {MIN_QTY}~{MAX_QTY} 사이의 정수만 가능합니다."


def valid_qty(qty) -> bool:
    return (isinstance(qty, int) and not isinstance(qty, bool)
            and MIN_QTY <= qty <= MAX_QTY)


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

    def options(self) -> dict:
        return {k: getattr(self, k) for k in OPTION_KEYS}

    @property
    def option_fee(self) -> int:
        fees = option_fee_table()
        fee = 0
        for k, v in self.options().items():
            if k == "extra_shots":
                fee += fees[k] * max(0, int(v or 0))
            elif v is not None:
                fee += fees.get(k, {}).get(v, 0)
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


@dataclass
class Cart:
    table_id: int | None = None
    items: list[CartItem] = field(default_factory=list)
    order_no: str | None = None
    staff_checked: bool = False      # P15 직원 나이 확인

    def add(self, item: CartItem) -> tuple[bool, str]:
        """검증을 통과한 품목만 담는다 (P11: 유효성 검증 전 장바구니 변경 금지)."""
        if not valid_qty(item.qty):
            return False, QTY_MSG
        _, rejected = validate_options(item.menu_id, variant_by_id(item.variant_id),
                                       item.options())
        if rejected:
            return False, " / ".join(f"{option_label(k, getattr(item, k, ''))}: {why}"
                                     for k, why in rejected)
        self.items.append(item)
        return True, ""

    def remove(self, idx: int):
        if 0 <= idx < len(self.items):
            self.items.pop(idx)

    def set_qty(self, idx: int, qty: int) -> tuple[bool, str]:
        if not valid_qty(qty):
            return False, QTY_MSG
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
