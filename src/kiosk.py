"""모든 변경은 복사본에서 검증하고 답변 생성 성공 뒤 한 번에 반영한다."""
from __future__ import annotations
import copy, re, json
from dataclasses import dataclass, field
from .router import route
from .retrieve import hybrid_search, as_context, _alias_map
from .chain import answer
from .cart import Cart, CartItem, OPTION_FIELDS, resolve_variant, menu_by_id, variant_by_id, find_variants, option_rules

def _menu_candidates(text):
    t = str(text or "").lower()
    hits = [(alias, mid) for alias, mid in _alias_map() if alias in t and menu_by_id(mid)]
    if not hits: return []
    longest = max(len(alias) for alias, _ in hits)
    return list(dict.fromkeys(mid for alias, mid in hits if len(alias) == longest))

def _menu(target):
    name, mid = target.get("menu_name"), target.get("menu_id")
    candidates = _menu_candidates(name)
    if len(candidates) > 1:
        raise ValueError("어느 메뉴인가요? " + " / ".join(menu_by_id(m)["메뉴명"] for m in candidates))
    if candidates:
        if mid and mid != candidates[0]: raise ValueError("메뉴 이름과 ID를 다시 확인해 주세요.")
        return candidates[0]
    if name: raise ValueError(f"'{name}'은 현재 메뉴에서 찾지 못했습니다.")
    if mid and menu_by_id(mid): return mid
    raise ValueError("메뉴 이름을 알려 주세요.")

def _line(target, cart):
    if target.get("line_id"):
        found = [i for i, x in enumerate(cart.items) if x.line_id == target["line_id"]]
    else:
        mid = _menu(target)
        found = [i for i, x in enumerate(cart.items) if x.menu_id == mid]
    if len(found) != 1: raise ValueError("변경할 품목을 하나 골라 주세요. 주문 내역의 번호/조건을 알려 주세요.")
    return found[0]

def _new_item(target):
    mid = _menu(target)
    v, choices = resolve_variant(mid, target.get("temp"), target.get("size"))
    if not v:
        raise ValueError(menu_by_id(mid)["메뉴명"] + "의 가능한 구성을 골라 주세요: " +
                         " / ".join(f"{x['온도']}·{x['크기']} {int(x['가격(원)']):,}원" for x in choices))
    qty = 1 if target.get("quantity") is None else target["quantity"]
    opts = {k: target[k] for k in OPTION_FIELDS if target.get(k) is not None}
    return CartItem(mid, v["주문 단위 ID"], menu_by_id(mid)["메뉴명"], v["온도"], v["크기"], qty=qty, **opts)

@dataclass
class TurnResult:
    reply: str
    intent: str
    rewritten: str
    language: str
    docs: list = field(default_factory=list)
    trace: list = field(default_factory=list)
    calc: str = ""
    cached: bool = False
    llm_calls: int = 0
    success: bool = True

def _execute(actions, cart):
    reviewed_at_start = cart.reviewed_version
    messages = []
    for action in actions:
        kind, targets = action["intent"], action.get("targets", [])
        if kind == "cart_add":
            if not targets: raise ValueError("담을 메뉴를 알려 주세요.")
            if cart.order_no: cart.start_additional()
            for target in targets:
                item = _new_item(target)
                ok, msg = cart.add(item)
                if not ok: raise ValueError(msg)
            messages.append("요청한 품목을 담았습니다.")
        elif kind in ("cart_update", "cart_remove"):
            cart._editable()
            if not targets: raise ValueError("변경할 품목을 알려 주세요.")
            for target in targets:
                idx = _line(target, cart)
                if kind == "cart_remove":
                    cart.remove(idx); continue
                old = cart.items[idx]
                if target.get("menu_id") and target["menu_id"] != old.menu_id:
                    replacement = _new_item(target)
                    replacement.line_id = old.line_id
                    if target.get("quantity") is None: replacement.qty = old.qty
                    cart.validate_item(replacement)
                    if replacement.is_alcohol and cart.service_mode != "dine_in": raise ValueError("주류는 포장할 수 없습니다.")
                    cart.items[idx] = replacement; cart._changed(); continue
                changes = {k: target[k] for k in OPTION_FIELDS if target.get(k) is not None and target[k] != getattr(old, k)}
                defaults = {"bean":variant_by_id(old.variant_id).get("원두 ID"), "milk":"dairy", "sweetness":"normal", "ice":"normal", "warming":"room"}
                for k in list(changes):
                    applicable = old.menu_id in {x.strip() for x in option_rules()[k]["적용 메뉴 ID"].split(",")}
                    if applicable and getattr(old,k) is None and changes[k] == defaults.get(k): changes.pop(k)
                if (target.get("temp") and target["temp"] != old.temp) or (target.get("size") and target["size"] != old.size):
                    v, _ = resolve_variant(old.menu_id, target.get("temp") or old.temp,
                                           target.get("size") or old.size)
                    if not v: raise ValueError("지원하지 않는 온도·크기입니다. 가능한 구성을 다시 골라 주세요.")
                    changes.update(variant_id=v["주문 단위 ID"], temp=v["온도"], size=v["크기"])
                qty = target.get("quantity")
                mode = action.get("quantity_mode", "set")
                if changes:
                    if mode != "set": raise ValueError("옵션을 바꿀 기존 잔과 새로 추가할 잔을 구분해 주세요. 아직 변경하지 않았습니다.")
                    cart.update(idx, changes, affected_qty=qty)
                else:
                    if qty is None: raise ValueError("바꿀 수량 또는 옵션을 알려 주세요.")
                    qty = old.qty + qty if mode == "increment" else old.qty - qty if mode == "decrement" else qty
                    ok, msg = cart.set_qty(idx, qty)
                    if not ok: raise ValueError(msg)
            messages.append("요청한 품목을 변경했습니다.")
        elif kind == "undo":
            cart.undo(); messages.append("직전 변경을 되돌렸습니다.")
        elif kind == "cart_clear":
            cart._editable()
            if action.get("value") != "confirmed" or not cart.pending_cancel:
                cart.pending_cancel = True
                messages.append("현재 장바구니를 모두 취소할까요? 확인하면 취소합니다.")
            else:
                cart.items = []; cart.pending_cancel = False; cart._changed()
                messages.append("확정 전 장바구니를 취소했습니다.")
        elif kind in ("cart_view", "order_review"):
            cart.review(); messages.append("최종 내역을 확인한 뒤 확정해 주세요.")
        elif kind == "order_confirm":
            if not cart.order_no and reviewed_at_start != cart.version:
                raise ValueError("최종 내역을 먼저 화면에서 확인한 뒤 다시 확정해 주세요.")
            ok, msg = cart.confirm()
            if not ok: raise ValueError(msg)
            messages.append(f"시연 주문을 확정했습니다. 주문번호 {msg}. 실제 결제·매장 접수는 이루어지지 않았습니다.")
        elif kind == "start_order":
            cart.start_additional(); messages.append("같은 좌석에 추가 주문을 시작했습니다.")
        elif kind == "reorder":
            if cart.order_no: cart.start_additional()
            if cart.items: raise ValueError("현재 장바구니를 먼저 확인해 주세요.")
            if not cart.previous_orders: raise ValueError("다시 담을 확정 주문이 없습니다.")
            for data in cart.previous_orders[-1]["cart"]:
                item = CartItem(**{k: data[k] for k in CartItem.__dataclass_fields__ if k in data})
                ok, msg = cart.add(item)
                if not ok: raise ValueError(msg)
            messages.append("이전 주문을 새 장바구니에 담았습니다. 다시 확인하고 확정해 주세요.")
        elif kind == "service_mode":
            cart.set_service(action.get("value")); messages.append("이용 방식을 변경했습니다.")
        elif kind == "table_set":
            cart._editable()
            value = action.get("value")
            if value not in [str(i) for i in range(1, 13)]: raise ValueError("좌석은 1~12번입니다.")
            cart.table_id = int(value); cart._changed(); messages.append("좌석 번호를 변경했습니다.")
        elif kind == "language_set":
            if action.get("value") not in ("ko", "en"): raise ValueError("한국어 또는 영어를 골라 주세요.")
            cart.language = action["value"]
            messages.append("English selected. Your order is unchanged." if cart.language == "en" else "한국어로 안내합니다. 주문은 그대로입니다.")
        elif kind == "status_check":
            messages.append(f"주문 상태: {cart.status()}")
    return messages

def budget_recommendation(plan, user_input, language):
    budget, drinks, desserts = plan.get("budget_krw"), plan.get("drink_count"), plan.get("dessert_count")
    match = re.search(r"([0-9][0-9,]*)\s*(만|천)?\s*원", user_input)
    if match:
        budget = int(match[1].replace(",", "")) * {None:1,"만":10000,"천":1000}[match[2]]
        count = re.search(r"([0-9]+|한|두|세|네|다섯|여섯|일곱|여덟|아홉|열)\s*(잔|명|사람)", user_input)
        if count:
            numbers={"한":1,"두":2,"세":3,"네":4,"다섯":5,"여섯":6,"일곱":7,"여덟":8,"아홉":9,"열":10}
            drinks=int(count[1]) if count[1].isdigit() else numbers[count[1]]
        if desserts is None and re.search(r"케이크|간식|디저트", user_input): desserts=1
    if budget is None: return ""
    if type(budget) is not int or budget < 0 or type(drinks) is not int or type(desserts) is not int or not (0 <= drinks <= 10 and 0 <= desserts <= 10) or drinks + desserts == 0:
        return "음료·디저트 수와 원 단위 예산을 알려 주세요." if language == "ko" else "Please specify the drink count, dessert count and budget in KRW."
    from .cart import _tables
    menus, variants = _tables()
    coffee = bool(re.search(r"커피|coffee", user_input, re.I))
    cake = bool(re.search(r"케이크|cake", user_input, re.I))
    dv = [v for v in variants.values() if menus[v["주문 단위 ID"].split("-")[0]]["분류"] in (("커피",) if coffee else ("커피","차/논커피"))]
    sv = [v for v in variants.values() if menus[v["주문 단위 ID"].split("-")[0]]["분류"] == "디저트" and (not cake or re.search("케이크|티라미수",v["메뉴명"]))]
    if drinks and not dv or desserts and not sv: return "조건에 맞는 메뉴를 확인할 수 없습니다."
    dv = sorted(dv,key=lambda v:v["가격(원)"]) if drinks else [None]
    sv = sorted(sv,key=lambda v:v["가격(원)"]) if desserts else [None]
    combinations=[]
    for d in dv:
        for s in sv:
            cost=(d["가격(원)"]*drinks if d else 0)+(s["가격(원)"]*desserts if s else 0)
            combinations.append((cost,d,s))
    combinations.sort(key=lambda x:x[0])
    minimum = combinations[0][0]
    if minimum > budget:
        return (f"현재 판매 가격으로 음료 {drinks}잔과 디저트 {desserts}개의 최소 합계는 {minimum:,}원이라 {budget:,}원 예산을 초과합니다. 수량 또는 예산을 바꿔 주세요. 자동으로 담지 않았습니다." if language=="ko" else
                f"The minimum for {drinks} drinks and {desserts} desserts is {minimum:,} KRW, above your {budget:,} KRW budget. Please change the quantity or budget. Nothing was added.")
    lines=[]
    for cost,d,s in combinations[:3]:
        if cost>budget:continue
        parts=[f"{v['메뉴명']} {v['온도']}/{v['크기']} ×{count}" for v,count in ((d,drinks),(s,desserts)) if v]
        lines.append(" + ".join(parts)+f" = {cost:,} KRW")
    return ("코드로 계산한 예산 내 구성입니다. 옵션 추가 전 가격이며 자동으로 담지 않았습니다.\n" if language=="ko" else "Calculated combinations within your budget, before extra options. Nothing was added.\n")+"\n".join(lines)

def _resume_pending(cart, actions):
    """아직 담기지 않은 주문의 확인 답변을 기존 주문 수정으로 처리하지 않는다."""
    pending = [a for a in cart.pending_actions if a["intent"] == "cart_add"]
    incoming = [a for a in actions if a["intent"] in ("cart_add", "cart_update")]
    if not pending or not incoming or len(incoming) != len(actions): return actions
    merged = copy.deepcopy(pending)
    old_targets = [t for a in merged for t in a.get("targets", [])]
    unresolved = []
    for t in old_targets:
        try: _new_item(t)
        except ValueError: unresolved.append(t)
    for a in incoming:
        for t in a.get("targets", []):
            mid = t.get("menu_id")
            if not mid and t.get("menu_name"):
                candidates = _menu_candidates(t["menu_name"])
                if len(candidates) == 1: mid = candidates[0]
            candidates = [x for x in old_targets if x.get("menu_id") == mid] if mid else unresolved
            if len(candidates) != 1: return actions
            candidates[0].update({k:v for k,v in t.items() if v is not None and k != "line_id"})
    return merged

def handle(user_input, store, cart, history=None):
    history = history or []
    state = cart.snapshot() | {"pending_actions": cart.pending_actions, "pending_cancel": cart.pending_cancel,
                              "previous_orders": cart.previous_orders}
    try: r = route(user_input, history, state)
    except Exception:
        return TurnResult("연결이 원활하지 않습니다. 주문은 바뀌지 않았습니다. 잠시 후 다시 시도해 주세요.",
                          "error", user_input, cart.language, success=False)
    actions = _resume_pending(cart, r["actions"])
    if cart.pending_cancel and re.fullmatch(r"(?:네|예|응|yes|confirm)(?:[,!. ]*(?:취소(?:해줘|해주세요|해)?|cancel(?: the)?(?: draft)?(?: cart| items)?|please))?[!. ]*", user_input.strip(), re.I):
        actions = [{"intent":"cart_clear", "targets":[], "quantity_mode":"set", "value":"confirmed"}]
        r["needs_clarification"] = False
    if re.search(r"하나\s*더|잔\s*더|one more|same", user_input, re.I) and not re.search(r"오트|두유|저지방|디카페인|아이스|뜨거|따뜻|샷|시럽|사이즈|oat|decaf|hot|iced|large|small", user_input, re.I):
        for a in actions:
            if a["intent"] != "cart_add": continue
            for t in a.get("targets", []):
                try:
                    idx = _line(t, cart)
                    old = cart.items[idx]
                    for key in (*OPTION_FIELDS, "temp", "size"): t[key] = getattr(old,key)
                except ValueError:
                    r["needs_clarification"] = True
    order_targets = [t for a in actions if a["intent"] in ("cart_add","cart_update") for t in a.get("targets", [])]
    coffee_targets = [t for t in order_targets if menu_by_id(t.get("menu_id")) and menu_by_id(t["menu_id"])["분류"] == "커피"]
    if len(coffee_targets) == 1 and re.search(r"디카페인|decaf", user_input, re.I) and not re.search(r"말고|아닌|not decaf", user_input, re.I):
        coffee_targets[0]["bean"] = "B03"
    intents = [a["intent"] for a in actions]
    lang = "en" if user_input.isascii() and re.search("[A-Za-z]", user_input) and not re.search(r"(?:in|to|speak|use|respond in)\s+korean", user_input, re.I) else r["language"]; staged = copy.deepcopy(cart); staged.language = lang
    informational = all(i in ("menu_info", "recommend", "option_check", "help", "out_of_scope") for i in intents)
    if re.search(r"옆자리|다른 손님", user_input) and not _menu_candidates(user_input):
        return TurnResult("다른 손님의 확인은 해당 손님의 직원 확인을 대신하지 않습니다. 어떤 메뉴를 원하시는지 먼저 알려 주세요.", "help",r["rewritten_query"],lang,llm_calls=1,success=False)
    for field in ("avoid_allergens", "max_caffeine_mg", "avoid_alcohol"):
        if r.get(field) is not None:
            value = r[field]
            if field == "max_caffeine_mg" and (type(value) is not int or value < 0):
                return TurnResult("카페인 상한은 0 이상의 mg 값으로 알려 주세요.","help",r["rewritten_query"],lang,success=False)
            if getattr(staged,field) != value:
                setattr(cart,field,value);cart._changed()
                setattr(staged,field,value);staged._changed()
    clarifying = bool(r.get("needs_clarification"))
    # shortcut: 접시 메뉴의 개수/접시 모호성만 확인한다. 판매 단위가 늘면 해당 단위도 추가한다.
    bare_count = re.search(r"(?:get|have|add|order)\s+(?:me\s+)?(?:one|two|three|four|five|six|seven|eight|nine|ten|\d+)\b|(?:\d+|한|두|세|네)\s*개|하나|둘|셋|넷", user_input, re.I)
    if bare_count and not re.search(r"접시|plates?|servings?", user_input, re.I):
        for a in actions:
            for t in a.get("targets", []) if a["intent"] == "cart_add" else []:
                m = menu_by_id(t.get("menu_id")) or {}
                unit = str(m.get("판매 단위", "")); count = re.search(r"(\d+)개", unit)
                if "접시" in unit and count:
                    cart.pending_actions = actions
                    question = (f"{m.get('영문명')}: one plate contains {count[1]} pieces. How many plates would you like? Nothing was added." if lang == "en" else f"{m['메뉴명']}는 {unit} 단위로 판매합니다. 몇 접시를 원하시나요? 아직 담지 않았습니다.")
                    return TurnResult(question, ",".join(intents), r["rewritten_query"], lang, llm_calls=1)
    retry = bool(cart.items and re.search(r"오류|타임아웃|timeout|retry|failed", user_input, re.I))
    if retry:
        return TurnResult(("먼저 실제 주문을 확인했습니다. 자동으로 다시 담지 않았습니다. 추가하려면 새 요청을 알려 주세요.\n" if lang == "ko" else "Here is your current order. Nothing was added again. Please specify a new addition if needed.\n") + cart.as_text(), "status_check", r["rewritten_query"],lang,llm_calls=1)
    try: messages = [] if clarifying else _execute(actions, staged)
    except (ValueError, IndexError, TypeError, KeyError) as exc:
        cart.pending_actions = actions
        msg = str(exc)
        if any(w in user_input for w in ("성인", "직원", "나이")) and any(w in user_input for w in ("확정", "주문")):
            msg += "\n주류는 해당 손님의 직원 확인 전에는 확정할 수 없습니다. 손님의 체크나 가정은 직원 확인이 아닙니다."
        if lang == "en": msg = "Please check the requested menu, variant or options. Your order was not changed.\n" + msg
        return TurnResult(msg, ",".join(intents), r["rewritten_query"], lang, llm_calls=1, success=False)
    if any(i == "status_check" for i in intents) and re.search(r"몇 분|대기|minutes|ready", user_input, re.I):
        messages.append("실시간 제조 상태·예상 대기시간은 연결하지 않아 확인할 수 없습니다.")
    docs, trace, seen = [], [], set()
    info = clarifying or any(i in ("menu_info", "recommend", "option_check", "help", "out_of_scope") for i in intents)
    try:
        if info or any(i == "cart_add" for i in intents):
            for query in (r.get("queries") or [r["rewritten_query"]]):
                found, steps = hybrid_search(store, query)
                trace += steps
                for d in found:
                    key = d.metadata.get("doc_id") or d.metadata.get("name")
                    if key not in seen: seen.add(key); docs.append(d)
        if "recommend" in intents and re.search(r"한국|korean", user_input, re.I):
            for doc in store.docstore._dict.values():
                if doc.metadata.get("category") in ("차/논커피", "디저트") and doc.metadata.get("doc_id") not in seen:
                    seen.add(doc.metadata["doc_id"]); docs.append(doc)
        generated, cached = "", False
        quotes = []
        for act in actions:
            if act["intent"] not in ("menu_info", "option_check"): continue
            targets = act.get("targets", [])
            for target in targets:
                target = dict(target)
                if len(targets) == 1 and ("디카페인" in user_input or "decaf" in user_input.lower()) and not target.get("bean"):
                    target["bean"] = "B03"
                try:
                    mid = _menu(target)
                    for variant in find_variants(mid):
                        opts = {k: target[k] for k in OPTION_FIELDS if target.get(k) is not None}
                        quote = CartItem(mid, variant["주문 단위 ID"], menu_by_id(mid)["메뉴명"], variant["온도"], variant["크기"], **opts).validate()
                        quotes.append({"variant_id": quote.variant_id, "unit_price_krw": quote.unit_price, **quote.nutrition()})
                except ValueError as exc: quotes.append({"option_validation_error": str(exc)})
        budget = budget_recommendation(r, user_input, lang)
        abv_text = ""
        if re.search(r"도수|%|abv", user_input, re.I):
            ids = list(dict.fromkeys(t.get("menu_id") for a in actions for t in a.get("targets", []) if t.get("menu_id")))
            if len(ids) == 1:
                for v in find_variants(ids[0]):
                    if v.get("도수(계산 기준)") is not None:
                        pure = (v.get("주류 원액1(ml)") or 0)*(v.get("원액1 도수") or 0)+(v.get("주류 원액2(ml)") or 0)*(v.get("원액2 도수") or 0)
                        abv_text = f"{v['메뉴명']}: 시연 도수 {v['도수(계산 기준)']*100:.1f}%. 순알코올 {pure:g}ml ÷ 계산 액체량 {v['계산 액체량(ml)']:g}ml ×100으로 계산합니다. 얼음 포함 제공량과 계산 분모는 다릅니다. 실제 안전 음주 기준을 뜻하지 않습니다."
        syrup_unknown = "당류" in user_input and any(t.get("sweetness") == "less" for a in actions for t in a.get("targets", []))
        if budget:
            generated, cached = budget, True
        elif any(i == "menu_info" for i in intents) and re.search(r"비교|차이|versus|compare|\bvs\b", user_input, re.I) and len({t.get("menu_id") for a in actions for t in a.get("targets",[]) if t.get("menu_id")}) >= 2:
            ids=list(dict.fromkeys(t["menu_id"] for a in actions for t in a.get("targets",[]) if t.get("menu_id")))
            rows=[]
            for mid in ids:
                m=menu_by_id(mid)
                if not m: continue
                name=m.get("영문명") if lang=="en" else m["메뉴명"]
                prices=" / ".join(f"{v['온도']}/{v['크기']} {v['가격(원)']:,} KRW, {v['카페인(mg)']}mg caffeine" for v in find_variants(mid))
                rows.append(f"{name}: {prices}\n"+f"{'Taste scores (sweet/acidity/bitter/body)' if lang=='en' else '기본 맛 점수(단맛/산미/쓴맛/바디)'}: "+"/".join(str(m.get(k,"미산정")) for k in ("단맛 1~5","산미 1~5","쓴맛 1~5","바디 1~5")))
            generated="\n\n".join(rows)+("\nTaste strength and caffeine are different. Scores use the standard recipe." if lang=="en" else "\n맛의 진하기와 카페인 양은 다릅니다. 점수는 기본 레시피 기준입니다.")
            cached=True
        elif "cart_add" in intents and "menu_info" in intents and not clarifying:
            ids = {t.get("menu_id") for a in actions if a["intent"] == "menu_info" for t in a.get("targets", [])}
            generated = "\n".join(d.metadata.get("description_en" if lang == "en" else "description", "") for d in docs if d.metadata.get("menu_id") in ids)
            cached = True
        elif "임신" in user_input and "안전" in user_input:
            generated, cached = "임신 중 건강상 안전성을 보장할 수 없습니다. 제공된 성분·카페인은 가상 매장의 시연값이며, 개인의 섭취 가능 여부는 의료진에게 확인해 주세요.", True
        elif abv_text:
            generated, cached = abv_text, True
        elif clarifying and all(i == "help" for i in intents):
            generated, cached = ("현재 판매 목록에서 요청한 메뉴·조건을 확인하지 못했습니다. 메뉴 이름을 다시 알려 주세요." if lang == "ko" else "I could not match that item to the current menu. Please check the menu name."), True
        elif syrup_unknown:
            generated, cached = "시럽·청은 절반으로 줄일 수 있지만 변경 후 당류와 열량의 정확값은 미산정입니다. 전체 당류가 절반이라는 뜻은 아닙니다.", True
        elif info:
            generated, cached = answer(user_input, as_context(docs), calc="\n".join(messages) + ("\n조건 확인이 필요하여 주문 변경을 모두 보류했습니다. 실제 자료만 근거로 가능한 선택과 필요한 질문을 안내하세요." if clarifying else "") + ("\n서버 계산 견적(조회만, 주문 변경 아님): " + json.dumps(quotes, ensure_ascii=False) if quotes else ""),
                                       history=history, state=staged.snapshot(),
                                       offtopic=all(i == "out_of_scope" for i in intents))
        # No state change survives a failed lookup or generated response.
        staged.pending_actions = actions if clarifying else []
        if "undo" not in intents and not cart.order_no and not staged.order_no and (cart.items != staged.items or cart.service_mode != staged.service_mode):
            staged.undo_state = {"items":copy.deepcopy(cart.items), "table_id":cart.table_id, "service_mode":cart.service_mode}
        cart.__dict__.update(staged.__dict__)
        calc = cart.as_text() if messages else ""
        reply = generated
        if cart.language == "en":
            translations = {"직전 변경을 되돌렸습니다.": "Your last change was undone.", "현재 장바구니를 모두 취소할까요? 확인하면 취소합니다.": "Cancel the entire draft cart? Please confirm.", "요청한 품목을 담았습니다.": "The requested items were added.", "요청한 품목을 변경했습니다.": "The requested items were updated.", "최종 내역을 확인한 뒤 확정해 주세요.": "Review the final order before confirming.", "같은 좌석에 추가 주문을 시작했습니다.": "A new order has started at the same table.", "확정 전 장바구니를 취소했습니다.": "The draft cart was cancelled."}
            messages = [translations.get(m, m) for m in messages]
        if re.search(r"알레르기|allerg", user_input, re.I):
            notice = "Ingredient substitution does not guarantee allergy safety. Cross-contact is possible; please confirm ingredients with the barista." if lang == "en" else "재료 변경만으로 알레르기 안전성이 보장되지는 않습니다. 공용기구 교차접촉 가능성이 있어 바리스타에게 성분을 확인해 주세요."
            reply += "\n" + notice
        messages = list(dict.fromkeys(messages))
        if messages: reply += ("\n\n" if reply else "") + "\n".join(messages) + "\n" + calc
        if re.search(r"읽어주|글씨|글자.*크|read.*aloud|font|text size", user_input, re.I):
            reply += ("\nUse Text size in Settings and the Read last answer button yourself. Chat has not changed the font or played audio." if lang == "en" else "\n글자는 이용 설정의 ‘글자 크기’, 음성은 ‘마지막 답변 읽기’ 버튼을 직접 선택해 주세요. 채팅에서 글자 크기나 음성을 실행하지는 않았습니다.")
        return TurnResult(reply, ",".join(intents), r["rewritten_query"], cart.language,
                          docs, trace, calc, cached, 1 + (1 if info and not cached else 0))
    except Exception:
        return TurnResult("처리를 완료하지 못했습니다. 주문은 변경하지 않았습니다. 다시 시도해 주세요.",
                          "error", r["rewritten_query"], cart.language, llm_calls=1, success=False)
