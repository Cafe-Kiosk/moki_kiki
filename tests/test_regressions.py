"""핵심 주문 규칙·원자성·검색 문서·화면의 회귀 검사. API 호출 없음."""
import copy, os, unittest, pathlib
from unittest.mock import patch
os.environ.setdefault("OPENAI_API_KEY", "unused-offline-tests")
from src.cart import Cart, CartItem, menu_by_id, resolve_variant
from src.kiosk import handle
from src.documents import build_documents
from src.router import validate_route
from src.index import load_index
from src.retrieve import hybrid_search

def item(mid="M03", temp="ICED", size="S", **kw):
    v, _ = resolve_variant(mid, temp, size)
    m = menu_by_id(mid)
    return CartItem(mid, v["주문 단위 ID"], m["메뉴명"], v["온도"], v["크기"], **kw)

def plan(*actions, **kw):
    return {"language": "ko", "rewritten_query": "라떼", "queries": [],
            "actions": list(actions), "needs_clarification": False, **kw}

def action(intent, **kw):
    return {"intent": intent, "targets": [], "quantity_mode": "set", "value": None, **kw}

class OrderTests(unittest.TestCase):
    def test_price_and_modified_nutrition(self):
        c=Cart(table_id=1)
        self.assertTrue(c.add(item(size="L",qty=2,bean="B03",milk="oat",extra_shots=2))[0])
        self.assertEqual(c.total,17800)
        self.assertEqual(c.items[0].nutrition()["caffeine_mg_per_unit"],20)
        self.assertEqual(c.items[0].nutrition()["nutrition"],"미산정")

    def test_reject_invalid_quantities(self):
        for q in [0,-1,11,1.5,True,"2"]:
            c=Cart(table_id=1);self.assertFalse(c.add(item(qty=q))[0]);self.assertEqual(c.items,[])

    def test_menu_option_boundaries(self):
        for mid,temp,size,kw in [
            ("M03","HOT","S",{"extra_shots":3}),("M09","ICED","ONE",{"bean":"B03"}),
            ("M09","ICED","ONE",{"extra_shots":1}),("M07","ICED","ONE",{"milk":"oat"}),
            ("M35","ICED","ONE",{"ice":"less"}),("M03","HOT","S",{"ice":"less"}),
            ("M20","NA","ONE",{"warming":"warm"}),("M03","HOT","S",{"milk":"unknown"})]:
            with self.subTest(mid=mid,kw=kw): self.assertFalse(Cart(table_id=1).add(item(mid,temp,size,**kw))[0])
        self.assertIsNone(resolve_variant("M04","ICED")[0])

    def test_two_phase_confirmation_and_immutable_order(self):
        c=Cart(table_id=1);c.add(item());self.assertFalse(c.confirm()[0]);c.review()
        ok,no=c.confirm();self.assertTrue(ok);self.assertEqual(c.confirm(),(True,no))
        self.assertFalse(c.add(item())[0])
        with self.assertRaises(ValueError):c.remove(0)
        c.start_additional();self.assertEqual(c.previous_orders[0]["order_no"],no)
        self.assertEqual(c.items,[]);c.add(item());self.assertEqual(len(c.previous_orders[0]["cart"]),1)

    def test_stale_review(self):
        c=Cart(table_id=1);c.add(item());c.review();c.set_qty(0,2)
        self.assertFalse(c.confirm()[0])

    def test_customer_staff_flag_never_authorizes_alcohol(self):
        c=Cart(table_id=1,staff_checked=True);c.add(item("M37","NA","ONE"));c.review()
        self.assertEqual(c.status(),"pending_staff_check");self.assertFalse(c.confirm()[0])
        with self.assertRaises(ValueError):c.set_service("takeout")

    def test_split_one_cup_preserves_other(self):
        c=Cart(table_id=1);c.add(item(qty=2,milk="oat"))
        c.update(0,{"milk":"dairy"},affected_qty=1)
        self.assertEqual([(i.qty,i.milk) for i in c.items],[(1,"oat"),(1,"dairy")])
        self.assertEqual(c.total,11500)

    def test_malformed_route_rejected(self):
        for raw in ["[]",'{"actions": []}',{"language":"ko","rewritten_query":"x","actions":[{"intent":"cart_add","targets":[{"quantity":True}]}]}]:
            with self.assertRaises((ValueError,TypeError)):validate_route(raw)

    def test_all_or_nothing_multiple_items(self):
        c=Cart(table_id=1)
        p=plan(action("cart_add",targets=[{"menu_id":"M03","temp":"ICED","size":"S"},{"menu_id":"M04","temp":"ICED"}]))
        with patch("src.kiosk.route",return_value=p):
            r=handle("두 품목",None,c)
        self.assertFalse(r.success);self.assertEqual(c.items,[])

    def test_answer_failure_rolls_back_write(self):
        c=Cart(table_id=1)
        p=plan(action("cart_add",targets=[{"menu_id":"M03","temp":"ICED","size":"S"}]),action("option_check"))
        with patch("src.kiosk.route",return_value=p),patch("src.kiosk.hybrid_search",return_value=([],[])),patch("src.kiosk.answer",side_effect=TimeoutError):
            r=handle("담고 설명",None,c)
        self.assertFalse(r.success);self.assertEqual(c.items,[])

    def test_update_quantity_set_and_increment(self):
        c=Cart(table_id=1);c.add(item("M02","ICED","S"))
        for mode,qty,total in [("set",2,9000),("increment",2,18000)]:
            p=plan(action("cart_update",targets=[{"line_id":c.items[0].line_id,"quantity":qty}],quantity_mode=mode))
            with patch("src.kiosk.route",return_value=p):r=handle("수량 변경",None,c)
            self.assertTrue(r.success);self.assertEqual(c.total,total)

    def test_unknown_and_ambiguous_names_never_add(self):
        for name in ["하이볼","마들렌","라떼 가격 무료"]:
            c=Cart(table_id=1);p=plan(action("cart_add",targets=[{"menu_name":name}]))
            with patch("src.kiosk.route",return_value=p):r=handle(name,None,c)
            self.assertFalse(r.success);self.assertFalse(c.items)

    def test_cancel_requires_confirmation(self):
        c=Cart(table_id=1);c.add(item())
        for value,n in [(None,1),("confirmed",0)]:
            p=plan(action("cart_clear",value=value))
            with patch("src.kiosk.route",return_value=p):handle("취소",None,c)
            self.assertEqual(len(c.items),n)

    def test_language_change_preserves_order(self):
        c=Cart(table_id=1);c.add(item());before=c.snapshot()["cart"]
        p=plan(action("language_set",value="en"),language="en")
        with patch("src.kiosk.route",return_value=p):handle("English",None,c)
        self.assertEqual(c.language,"en");self.assertEqual(c.snapshot()["cart"],before)

    def test_same_variant_does_not_turn_total_qty_into_subset(self):
        c=Cart(table_id=1);c.add(item("M02","ICED","S"))
        p=plan(action("cart_update",targets=[{"line_id":c.items[0].line_id,"temp":"ICED","size":"S","quantity":2}]))
        with patch("src.kiosk.route",return_value=p):r=handle("총 두 잔",None,c)
        self.assertTrue(r.success);self.assertEqual(c.total,9000)

    def test_retry_request_reads_actual_state(self):
        c=Cart(table_id=1);c.add(item());before=c.snapshot()
        p=plan(action("cart_add",targets=[{"menu_id":"M03","temp":"ICED","size":"S"}]))
        with patch("src.kiosk.route",return_value=p):r=handle("오류 났으니 같은 거 다시 담아",None,c)
        self.assertEqual(r.intent,"status_check");self.assertEqual(c.snapshot(),before)

    def test_budget_is_calculated_even_when_router_misses_fields(self):
        from src.kiosk import budget_recommendation
        text=budget_recommendation({},"커피 네 잔과 케이크를 15000원 안에서 추천해줘","ko")
        self.assertIn("20,500",text);self.assertIn("초과",text)
        feasible=budget_recommendation({},"2만 원 안에서 두 사람 음료와 간식","ko")
        self.assertIn("KRW",feasible)

    def test_product_replacement_keeps_other_line(self):
        c=Cart(table_id=1);c.add(item());c.add(item("M20","NA","ONE"))
        other=copy.deepcopy(c.items[1])
        p=plan(action("cart_update",targets=[{"line_id":c.items[0].line_id,"menu_id":"M13","temp":"HOT","size":"ONE"}]))
        with patch("src.kiosk.route",return_value=p):r=handle("라떼를 말차로",None,c)
        self.assertTrue(r.success);self.assertEqual(c.items[0].menu_id,"M13");self.assertEqual(c.items[1],other)

    def test_new_order_failure_preserves_confirmed_order(self):
        c=Cart(table_id=1);c.add(item());c.review();c.confirm();before=c.snapshot()
        p=plan(action("cart_add",targets=[{"menu_id":"M04","temp":"ICED"}]))
        with patch("src.kiosk.route",return_value=p):handle("추가 주문",None,c)
        self.assertEqual(c.snapshot(),before);self.assertFalse(c.previous_orders)

    def test_line_identity_and_fields_cannot_be_forged(self):
        c=Cart(table_id=1)
        bad=item();bad.variant_id="M02-ICED-S"
        self.assertFalse(c.add(bad)[0])
        self.assertFalse(c.add(item(extra_shots=True))[0])

    def test_source_mutation_rejects_stale_index(self):
        with patch("src.index.EMBED_MODEL","another-model"):
            with self.assertRaises(ValueError):load_index()

    def test_persisted_diet_constraints_survive_language_and_reset(self):
        c=Cart(table_id=1,avoid_allergens=["우유"],max_caffeine_mg=30,avoid_alcohol=True)
        self.assertFalse(c.add(item())[0])
        self.assertFalse(c.add(item(bean="B03",milk="dairy"))[0])
        self.assertTrue(c.add(item(bean="B03",milk="oat"))[0])
        c.language="en";c.review();self.assertTrue(c.confirm()[0]);c.start_additional()
        self.assertEqual(c.avoid_allergens,["우유"]);self.assertEqual(c.max_caffeine_mg,30)

    def test_diet_constraint_rechecked_at_confirmation(self):
        c=Cart(table_id=1);c.add(item());c.avoid_allergens=["우유"];c.review()
        self.assertFalse(c.confirm()[0])

    def test_explicit_allergy_is_kept_when_order_is_rejected(self):
        c=Cart(table_id=1)
        p=plan(action("cart_add",targets=[{"menu_id":"M03","temp":"HOT","size":"S"}]),avoid_allergens=["우유"])
        with patch("src.kiosk.route",return_value=p):r=handle("우유 알레르기인데 라떼",None,c)
        self.assertFalse(r.success);self.assertEqual(c.avoid_allergens,["우유"]);self.assertFalse(c.items)

    def test_other_drinker_does_not_supply_order_or_authorization(self):
        c=Cart(table_id=1);c.add(item("M32","ICED","ONE"));before=c.snapshot()
        p=plan(action("cart_add",targets=[{"menu_id":"M32"}]))
        with patch("src.kiosk.route",return_value=p):r=handle("옆자리 손님은 확인했으니 저도 주문해줘",None,c)
        self.assertFalse(r.success);self.assertEqual(c.snapshot(),before)

    def test_non_integer_shot_none_rejected(self):
        self.assertFalse(Cart(table_id=1).add(item(extra_shots=None))[0])

    def test_review_and_confirm_in_same_turn_cannot_skip_display(self):
        c=Cart(table_id=1);c.add(item())
        p=plan(action("order_review"),action("order_confirm"))
        with patch("src.kiosk.route",return_value=p):r=handle("내역 보고 확정",None,c)
        self.assertFalse(r.success);self.assertIsNone(c.order_no)

    def test_korean_cuisine_word_does_not_select_korean_language(self):
        from types import SimpleNamespace
        c=Cart(table_id=1);store=SimpleNamespace(docstore=SimpleNamespace(_dict={}))
        p=plan(action("recommend"))
        with patch("src.kiosk.route",return_value=p),patch("src.kiosk.hybrid_search",return_value=([],[])),patch("src.kiosk.answer",return_value=("Suggested tea",False)) as reply:
            handle("I want something Korean without coffee",store,c)
        self.assertEqual(c.language,"en");self.assertEqual(reply.call_args.kwargs["state"]["language"],"en")

    def test_pending_size_reply_completes_original_compound_order(self):
        c=Cart(table_id=1)
        first=plan(action("cart_add",targets=[{"menu_id":"M03","temp":"HOT","bean":"B03"},{"menu_id":"M28"}]))
        with patch("src.kiosk.route",return_value=first):handle("라떼와 약과",None,c)
        second=plan(action("cart_update",targets=[{"menu_id":"M03","size":"S"}]))
        with patch("src.kiosk.route",return_value=second),patch("src.kiosk.hybrid_search",return_value=([],[])):
            r=handle("라떼는 작은 걸로요",None,c)
        self.assertTrue(r.success);self.assertEqual(c.total,10700);self.assertEqual(len(c.items),2)

    def test_repeat_keeps_existing_decaf_options(self):
        c=Cart(table_id=1);c.add(item("M03","HOT","S",bean="B03"))
        p=plan(action("cart_add",targets=[{"menu_id":"M03","temp":"HOT","size":"S","quantity":1}]))
        with patch("src.kiosk.route",return_value=p),patch("src.kiosk.hybrid_search",return_value=([],[])):
            handle("라떼만 하나 더",None,c)
        self.assertEqual(c.total,12400);self.assertTrue(all(i.bean=="B03" for i in c.items))

    def test_quantity_increment_with_unchanged_options(self):
        c=Cart(table_id=1);c.add(item("M03","HOT","S",bean="B03"))
        p=plan(action("cart_update",targets=[{"line_id":c.items[0].line_id,"temp":"HOT","size":"S","bean":"B03","quantity":1}],quantity_mode="increment"))
        with patch("src.kiosk.route",return_value=p):r=handle("라떼만 하나 더",None,c)
        self.assertTrue(r.success);self.assertEqual(c.total,12400);self.assertEqual(c.items[0].qty,2)

    def test_default_options_do_not_hide_quantity_or_explicit_changes(self):
        c=Cart(table_id=1);c.add(item("M02","ICED","S"))
        p=plan(action("cart_update",targets=[{"line_id":c.items[0].line_id,"bean":"B01","quantity":2}],quantity_mode="increment"))
        with patch("src.kiosk.route",return_value=p):r=handle("아메리카노 두 잔 더",None,c)
        self.assertTrue(r.success);self.assertEqual(c.total,13500)
        for field,value in [("milk","dairy"),("bean","B03")]:
            p=plan(action("cart_update",targets=[{"line_id":c.items[0].line_id,field:value,"quantity":1}],quantity_mode="increment"))
            with patch("src.kiosk.route",return_value=p):r=handle("옵션과 추가 수량",None,c)
            self.assertFalse(r.success);self.assertEqual(c.total,13500)

    def test_bundle_count_requires_sales_unit_confirmation(self):
        c=Cart(table_id=1)
        p=plan(action("cart_add",targets=[{"menu_id":"M29","quantity":1}]),language="en")
        with patch("src.kiosk.route",return_value=p):r=handle("What is ssuk injeolmi? Could I get four?",None,c)
        self.assertFalse(c.items);self.assertIn("4 pieces",r.reply);self.assertIn("plates",r.reply)
        p=plan(action("cart_add",targets=[{"menu_id":"M29","quantity":1}]),language="en")
        with patch("src.kiosk.route",return_value=p),patch("src.kiosk.hybrid_search",return_value=([],[])):
            r=handle("One plate, please",None,c)
        self.assertTrue(r.success);self.assertEqual(c.total,5500)

    def test_accessibility_request_guides_actual_controls(self):
        c=Cart(table_id=1)
        with patch("src.kiosk.route",return_value=plan(action("cart_view"))):
            r=handle("주문 내용을 읽어주고 글씨도 크게 해",None,c)
        self.assertIn("직접 선택",r.reply);self.assertIn("실행하지는 않았습니다",r.reply)

    def test_explicit_decaf_is_preserved_when_parser_drops_it(self):
        c=Cart(table_id=1,max_caffeine_mg=30,avoid_allergens=["우유"])
        p=plan(action("cart_add",targets=[{"menu_id":"M03","temp":"ICED","size":"S","milk":"oat"}]))
        with patch("src.kiosk.route",return_value=p),patch("src.kiosk.hybrid_search",return_value=([],[])):
            r=handle("오트 디카페인 아이스 라떼 작은 거",None,c)
        self.assertTrue(r.success);self.assertEqual(c.total,6700)

    def test_undo_whole_compound_change_and_confirm_boundary(self):
        c=Cart(table_id=1)
        p=plan(action("cart_add",targets=[{"menu_id":"M03","temp":"ICED","size":"S"},{"menu_id":"M28"}]))
        with patch("src.kiosk.route",return_value=p),patch("src.kiosk.hybrid_search",return_value=([],[])):
            handle("두 품목 담아",None,c)
        c.undo();self.assertEqual(c.items,[])
        c.add(item());c.review();c.confirm()
        with self.assertRaises(ValueError):c.undo()

    def test_pending_cancel_accepts_explicit_yes_even_if_router_drops_value(self):
        c=Cart(table_id=1);c.add(item());c.pending_cancel=True
        p=plan(action("cart_clear"))
        with patch("src.kiosk.route",return_value=p):handle("Yes, cancel the draft cart",None,c)
        self.assertFalse(c.items);self.assertFalse(c.pending_cancel)

class DataTests(unittest.TestCase):
    def test_mock_never_uses_real_disk_embedding_cache(self):
        from src.index import get_embeddings, _MockEmbeddings
        with patch("src.index.MOCK",True),patch("src.index.CachedEmbeddings",side_effect=AssertionError("real cache accessed")):
            self.assertIsInstance(get_embeddings(),_MockEmbeddings)
            self.assertEqual(load_index().index.d,256)

    def test_current_documents_and_index(self):
        docs=build_documents();self.assertEqual(len(docs),61)
        self.assertEqual(len({d.metadata["doc_id"] for d in docs}),61)
        self.assertFalse(any(d.metadata["type"] in ("검증질문","선별내역") for d in docs))
        store=load_index()
        self.assertEqual({d.metadata["doc_id"] for d in store.docstore._dict.values()},
                         {d.metadata["doc_id"] for d in docs})
        self.assertTrue(all(d.metadata["version"]==docs[0].metadata["version"] for d in store.docstore._dict.values()))
        self.assertIn("16.7%",next(d.metadata["full"] for d in docs if d.metadata["doc_id"]=="M35"))

    def test_required_rule_hits_not_truncated(self):
        store=load_index()
        with patch.object(store,"similarity_search_with_score",return_value=[]):
            docs,_=hybrid_search(store,"아메리카노 카푸치노 라떼 원두 우유 샷 카페인 알레르기 사이즈 가격")
        ids={d.metadata["doc_id"] for d in docs}
        self.assertTrue({"M02","M04","M03","bean","milk","extra_shots","P09","P10"} <= ids)

class ScreenTests(unittest.TestCase):
    def test_screen_confirm_and_edit_preserve_order(self):
        from streamlit.testing.v1 import AppTest
        c=Cart(table_id=3);c.add(item(qty=2,milk="oat"))
        app=AppTest.from_file(str(pathlib.Path(__file__).resolve().parent.parent/"app.py"),default_timeout=15)
        app.session_state["cart"]=c
        app.run();self.assertFalse(app.exception)
        self.assertFalse(any("나이 확인 완료" in str(x.label) for x in app.toggle))
        app.button(key="edit"+c.items[0].line_id).click().run()
        self.assertFalse(app.exception)
        review=next(b for b in app.button if b.label.startswith("최종 내역"))
        review.click().run()
        confirm=next(b for b in app.button if b.label.startswith("이 내역"))
        self.assertFalse(confirm.disabled);confirm.click().run()
        self.assertFalse(app.exception);self.assertTrue(app.session_state["cart"].order_no)
        next(b for b in app.button if b.label.startswith("추가 주문")).click().run()
        self.assertEqual(len(app.session_state["cart"].previous_orders),1)

    def test_screen_language_and_service_callbacks(self):
        from streamlit.testing.v1 import AppTest
        c=Cart(table_id=3);c.add(item("M32","ICED","ONE"))
        app=AppTest.from_file(str(pathlib.Path(__file__).resolve().parent.parent/"app.py"),default_timeout=15);app.session_state["cart"]=c
        app.run()
        app.selectbox(key="ui_language").set_value("en").run()
        self.assertEqual(app.session_state["cart"].language,"en")
        app.selectbox(key="ui_service").set_value("takeout").run()
        self.assertEqual(app.session_state["cart"].service_mode,"dine_in")
        self.assertFalse(app.exception)

if __name__=="__main__":unittest.main()
