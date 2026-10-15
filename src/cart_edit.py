"""장바구니 빼기·수정 (Q15).

라우터 order_items 의 action 이 remove·update 인 항목을 처리한다. LLM 호출 없음.

  대상 찾기 : 메뉴명 + match(온도·크기·옵션)로 장바구니 줄을 고른다.
             두 줄 이상 걸리면 바꾸지 않고 어느 것인지 되묻는다.
  update   : 바꾸는 값만 바꾸고 나머지 옵션·수량은 그대로 둔다. 1단계 옵션·수량·구성 검증을 거친다.
             apply_to 가 그 줄 수량보다 적으면 줄을 나눈다 ('오트 라떼 2잔 중 하나만 일반 우유로').
  remove   : qty 가 있으면 그만큼 줄이고, 없거나 줄 수량 이상이면 줄을 지운다.
"""
from __future__ import annotations
from dataclasses import replace

from .cart import (Cart, CartItem, OPTION_KEYS, menu_by_id, option_rules, resolve_variant,
                   validate_options, option_label, valid_qty, QTY_MSG, variant_by_id)
from .retrieve import match_menus

MATCH_KEYS = ("temp", "size", *OPTION_KEYS)


def _menu_id(name: str) -> tuple[str | None, str]:
    ids = [i for i in match_menus(name)[0] if menu_by_id(i)]
    if not ids:
        return None, f"'{name}' 은 메뉴에서 찾지 못했습니다."
    if len(ids) > 1:
        names = " 또는 ".join(str(menu_by_id(i)["메뉴명"]) for i in ids)
        return None, f"'{name}' 은 {names} 중 어느 것인지 확인이 필요합니다. 바꾸지 않았습니다."
    return ids[0], ""


def _default(key: str):
    rule = option_rules().get(key)
    if not rule:
        return None
    return int(rule["default"]) if rule["kind"] == "integer" else rule["default"]


def _same(item: CartItem, key: str, want) -> bool:
    """장바구니 줄의 값이 match 조건과 같은가. 기본값(dairy·B01·샷 0)은 None 과 같게 본다."""
    if key in ("temp", "size"):
        return str(getattr(item, key)).upper() == str(want).upper()
    have = getattr(item, key)
    if have in (None, 0):
        have = _default(key)
    return str(have) == str(want)


def find_lines(cart: Cart, menu_id: str, match: dict | None) -> list[int]:
    match = {k: v for k, v in (match or {}).items() if k in MATCH_KEYS and v not in (None, "")}
    return [i for i, it in enumerate(cart.items)
            if it.menu_id == menu_id and all(_same(it, k, v) for k, v in match.items())]


def _which(cart: Cart, idxs: list[int]) -> str:
    return " / ".join(f"{n}번 {cart.items[i].label()}" for n, i in enumerate(idxs, 1))


def _target(it: dict, cart: Cart) -> tuple[int | None, str]:
    mid, err = _menu_id(it.get("menu_name", ""))
    if mid is None:
        return None, err
    name = menu_by_id(mid)["메뉴명"]
    idxs = find_lines(cart, mid, it.get("match"))
    if not idxs:
        return None, f"{name}: 장바구니에 맞는 품목이 없습니다. 바꾸지 않았습니다."
    if len(idxs) > 1:
        return None, (f"{name}: 장바구니에 {len(idxs)}줄이 있어 어느 것인지 확인이 필요합니다 → "
                      f"{_which(cart, idxs)}. 바꾸지 않았습니다.")
    return idxs[0], ""


def remove_item(it: dict, cart: Cart) -> str:
    idx, err = _target(it, cart)
    if idx is None:
        return err
    item = cart.items[idx]
    qty = it.get("qty")
    if qty is not None and not valid_qty(qty):
        return f"{item.name}: 빼지 않았습니다. 요청 수량 {qty!r} — {QTY_MSG}"
    before = item.label()
    if qty is None or qty >= item.qty:
        cart.remove(idx)
        return f"[빼기완료] {before} 뺌"
    cart.set_qty(idx, item.qty - qty)
    return f"[빼기완료] {before} 에서 {qty} 뺌 → {cart.items[idx].label()}"


def update_item(it: dict, cart: Cart) -> str:
    idx, err = _target(it, cart)
    if idx is None:
        return err
    old = cart.items[idx]
    changes = {k: it[k] for k in OPTION_KEYS if it.get(k) not in (None, "")}

    # 온도·크기를 바꾸면 주문 단위를 다시 찾는다. 없으면 대체하지 않는다 (P03)
    temp = it.get("temp") or old.temp
    size = it.get("size") or old.size
    variant_id = old.variant_id
    if it.get("temp") or it.get("size"):
        v, all_v = resolve_variant(old.menu_id, temp, size)
        if v is None:
            opts = " / ".join(f"{x.get('온도')}·{x.get('크기')}" for x in all_v)
            return f"{old.name}: 바꾸지 않았습니다. 그 구성은 없습니다 → {opts}"
        variant_id = str(v["주문 단위 ID"])

    # 바꾸는 옵션만 검증한다. 기본값으로 되돌리는 것('일반 우유로')은 옵션을 지우는 것이다
    allowed, rejected = validate_options(old.menu_id, variant_by_id(variant_id), changes)
    if rejected:
        return f"{old.name}: 바꾸지 않았습니다. " + " / ".join(
            f"{option_label(k, changes[k])} 불가 — {why}" for k, why in rejected)
    new_opts = {k: allowed.get(k) for k in changes}
    for k in changes:
        if k not in allowed:                        # 기본값 → 옵션 해제
            new_opts[k] = 0 if k == "extra_shots" else None

    v = variant_by_id(variant_id)
    new = replace(old, variant_id=variant_id, temp=str(v.get("온도")), size=str(v.get("크기")),
                  **new_opts)
    # 남은 옵션이 새 구성에서도 되는지 확인 (HOT 으로 바꿨는데 '얼음 적게'가 남는 경우)
    _, still_bad = validate_options(new.menu_id, v, new.options())
    if still_bad:
        return f"{old.name}: 바꾸지 않았습니다. " + " / ".join(
            f"{option_label(k, getattr(new, k))} — {why}" for k, why in still_bad)

    new_qty = it.get("qty")
    apply_to = it.get("apply_to")
    if apply_to is not None and not valid_qty(apply_to):
        return f"{old.name}: 바꾸지 않았습니다. 대상 수량 {apply_to!r} — {QTY_MSG}"
    if new_qty is not None and not valid_qty(new_qty):
        return f"{old.name}: 바꾸지 않았습니다. 요청 수량 {new_qty!r} — {QTY_MSG}"

    if apply_to is not None and apply_to > old.qty:
        return f"{old.name}: 바꾸지 않았습니다. 장바구니에는 {old.qty}개뿐입니다."

    before = old.label()
    if apply_to is not None and apply_to < old.qty:
        cart.items[idx] = replace(old, qty=old.qty - apply_to)     # 나머지 잔은 그대로
        cart.items.insert(idx + 1, replace(new, qty=apply_to))
        cart._changed()
        return (f"[수정완료] {before} 중 {apply_to}개만 변경 → "
                f"{cart.items[idx].label()} + {cart.items[idx + 1].label()}")
    cart.items[idx] = replace(new, qty=new_qty if new_qty is not None else old.qty)
    cart._changed()
    return f"[수정완료] {before} → {cart.items[idx].label()}"

