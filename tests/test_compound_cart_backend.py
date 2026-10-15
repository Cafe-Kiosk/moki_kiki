"""Regression coverage for compound chat orders and atomic cart execution."""
from __future__ import annotations

from copy import deepcopy
import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.index import app, _explicit_alcohol_purchase_intent
from src.cart import Cart, CartItem
from src.kiosk import CartExecutionError, _execute_cart_actions
from src.router import adapt_plan, _is_checkout_command, _mock_plan


STATE_SECRET = "compound-cart-test-secret-at-least-32-characters"


def _options(**values):
    result = {
        "bean": None,
        "extra_shots": None,
        "milk": None,
        "sweetness": None,
        "ice": None,
        "warming": None,
    }
    result.update(values)
    return result


def _target(menu_id, variant_id=None, quantity=None, line_id=None, **options):
    return {
        "menu_id": menu_id,
        "variant_id": variant_id,
        "line_id": line_id,
        "quantity": quantity,
        "options": _options(**options),
    }


def _action(intent, targets, quantity_mode="none"):
    return {
        "action_id": f"test-{intent}",
        "intent": intent,
        "hti_ids": [],
        "targets": targets,
        "constraints": [],
        "quantity_mode": quantity_mode,
        "requires_tool": True,
        "mutates_state": intent.startswith("cart_"),
        "blocked_reason": None,
    }


def _plan(*actions):
    return {
        "schema_version": "1.0",
        "language": "ko",
        "actions": list(actions),
        "needs_retrieval": True,
        "needs_clarification": False,
        "clarification_question": None,
        "safety_flags": [],
        "preserve_state": True,
    }


def _line(item):
    return {
        "menu_id": item.menu_id,
        "variant_id": item.variant_id,
        "qty": item.qty,
        "bean": item.bean,
        "extra_shots": item.extra_shots,
        "milk": item.milk,
        "sweetness": item.sweetness,
        "ice": item.ice,
        "warming": item.warming,
    }


class CompoundRouterTests(unittest.TestCase):
    def test_mock_checkout_commands_exclude_payment_information_questions(self):
        rewrite = {"rewritten_utterance": "", "language": "ko"}
        for message in (
            "계산해줘",
            "이대로 주문할게",
            "주문 확정해줘",
            "결제할게",
        ):
            with self.subTest(message=message):
                self.assertTrue(_is_checkout_command(message))
                self.assertEqual(
                    _mock_plan(message, rewrite)["actions"][0]["intent"],
                    "order_confirm",
                )
        for message in (
            "주문 가능한가요?",
            "결제수단은 뭐가 있어요?",
            "결제 방법을 알려줘",
        ):
            with self.subTest(message=message):
                self.assertFalse(_is_checkout_command(message))
                self.assertNotEqual(
                    _mock_plan(message, rewrite)["actions"][0]["intent"],
                    "order_confirm",
                )

    def test_option_check_order_target_is_promoted_without_losing_second_item(self):
        utterance = (
            "바닐라 라떼 아이스 S 한 잔 주세요. 디카페인 원두와 오트로 하고, "
            "시럽은 절반으로 선택할게요. 샷은 추가하지 말고 얼음은 기본으로요. "
            "약과도 한 접시 담아주세요"
        )
        vanilla = _target(
            "M06", "M06-ICED-S", 1,
            bean="B03", milk="oat", sweetness="less",
            extra_shots=0, ice="normal",
        )
        yakgwa = _target("M28", "M28-NA-ONE", 1)
        routed = adapt_plan(
            utterance,
            {"rewritten_utterance": utterance, "language": "ko"},
            _plan(
                _action("option_check", [vanilla]),
                _action("cart_add", [yakgwa], "set"),
            ),
        )

        self.assertEqual(
            [item["menu_id"] for item in routed["order_items"]],
            ["M06", "M28"],
        )
        first = routed["order_items"][0]
        self.assertEqual(first["variant_id"], "M06-ICED-S")
        self.assertEqual(
            (first["bean"], first["milk"], first["sweetness"],
             first["extra_shots"], first["ice"]),
            ("B03", "oat", "less", 0, "normal"),
        )
        self.assertNotIn("M03", [item["menu_id"] for item in routed["order_items"]])
        self.assertNotIn("M25", [item["menu_id"] for item in routed["order_items"]])

    def test_option_question_and_nearby_information_clause_are_not_promoted(self):
        vanilla = _target("M06", "M06-ICED-S", 1, extra_shots=1)
        question = "바닐라 라떼에 샷 추가 가능한가요?"
        routed = adapt_plan(
            question,
            {"rewritten_utterance": question, "language": "ko"},
            _plan(_action("option_check", [vanilla])),
        )
        self.assertEqual(routed["order_items"], [])
        self.assertEqual(routed["plan"]["actions"][0]["intent"], "option_check")

        mixed = "바닐라 라떼 옵션 알려주고 약과만 담아줘"
        routed = adapt_plan(
            mixed,
            {"rewritten_utterance": mixed, "language": "ko"},
            _plan(
                _action("option_check", [vanilla]),
                _action("cart_add", [_target("M28", "M28-NA-ONE", 1)], "set"),
            ),
        )
        self.assertEqual(
            [item["menu_id"] for item in routed["order_items"]], ["M28"])


class AtomicCartExecutorTests(unittest.TestCase):
    def _compound_cart(self):
        cart = Cart(table_id=5)
        _execute_cart_actions(_plan(_action("cart_add", [
            _target(
                "M06", "M06-ICED-S", 1,
                bean="B03", milk="oat", sweetness="less",
                extra_shots=0, ice="normal",
            ),
            _target("M28", "M28-NA-ONE", 1),
        ], "set")), cart)
        return cart

    def test_exact_compound_order_has_two_lines_and_server_total(self):
        cart = self._compound_cart()
        self.assertEqual([item.menu_id for item in cart.items], ["M06", "M28"])
        self.assertEqual(cart.total, 11_700)
        self.assertEqual(cart.items[0].option_fee, 1_200)

    def test_remove_and_update_resolve_against_original_snapshot(self):
        cart = self._compound_cart()
        _execute_cart_actions(_plan(
            _action("cart_remove", [_target("M06", line_id="0")]),
            _action("cart_update", [_target("M28", quantity=2, line_id="1")], "set"),
        ), cart)
        self.assertEqual([(item.menu_id, item.qty) for item in cart.items], [("M28", 2)])
        self.assertEqual(cart.total, 9_000)

    def test_invalid_compound_plan_rolls_back_every_change(self):
        cart = self._compound_cart()
        before = deepcopy(cart)
        with self.assertRaises(CartExecutionError):
            _execute_cart_actions(_plan(
                _action("cart_update", [_target("M06", quantity=2, line_id="0")], "set"),
                _action("cart_update", [
                    _target("M28", quantity=2, line_id="1", milk="oat")
                ], "set"),
            ), cart)
        self.assertEqual(cart, before)

        empty = Cart(table_id=5)
        with self.assertRaises(CartExecutionError):
            _execute_cart_actions(_plan(_action("cart_add", [
                _target("M28", "M28-NA-ONE", 1),
                _target("M06", "M06-ICED-S", 1, extra_shots=3),
            ], "set")), empty)
        self.assertEqual(empty.items, [])

    def test_mixed_mutation_and_add_is_atomic_and_add_is_tracked(self):
        cart = self._compound_cart()
        _, added, changed = _execute_cart_actions(_plan(
            _action("cart_update", [_target("M28", quantity=2, line_id="1")], "set"),
            _action("cart_add", [_target("M14", "M14-HOT-ONE", 1)], "set"),
        ), cart)
        self.assertTrue(changed)
        self.assertEqual([item.menu_id for item in added], ["M14"])
        self.assertEqual(
            [(item.menu_id, item.qty) for item in cart.items],
            [("M06", 1), ("M28", 2), ("M14", 1)],
        )


class CompoundApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_browser_defers_add_but_keeps_same_turn_mutation(self):
        initial = CartItem(
            menu_id="M14", variant_id="M14-HOT-ONE", name="핫초코",
            temp="HOT", size="ONE",
        )

        def mixed(_message, _store, cart, _history):
            cart.set_qty(0, 2)
            added = CartItem(
                menu_id="M28", variant_id="M28-NA-ONE", name="약과 2개",
                temp="NA", size="ONE",
            )
            cart.add(added)
            return SimpleNamespace(
                reply="변경하고 담았어요.", intent="장바구니",
                quick_replies=[], docs=[], menu_images=[], added_items=[added],
            )

        with patch.dict(os.environ, {
            "OPENAI_API_KEY": "test-key", "MOKI_STATE_SECRET": STATE_SECRET,
        }, clear=False), patch("api.index.is_mock", return_value=False), \
                patch("api.index.handle", side_effect=mixed):
            response = self.client.post("/api/chat", json={
                "message": "핫초코는 2개로 바꾸고 약과도 담아줘",
                "table_id": 5,
                "history": [],
                "cart": [_line(initial)],
                "language": "ko",
                "defer_cart_add": True,
            })

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual([(x["menu_id"], x["qty"]) for x in payload["cart"]["items"]],
                         [("M14", 2)])
        self.assertEqual(payload["deferred_cart_items"][0]["menu_id"], "M28")

    def test_natural_checkout_commands_open_review_but_questions_do_not(self):
        cart_line = {
            "menu_id": "M14", "variant_id": "M14-HOT-ONE", "qty": 1,
            "bean": None, "extra_shots": 0, "milk": None,
            "sweetness": None, "ice": None, "warming": None,
        }
        patches = (
            patch("api.index.is_mock", return_value=True),
            patch("src.router.is_mock", return_value=True),
            patch("src.chain.is_mock", return_value=True),
            patch("src.kiosk.is_mock", return_value=True),
        )
        with patches[0], patches[1], patches[2], patches[3]:
            commands = [self.client.post("/api/chat", json={
                "message": message, "table_id": 5, "history": [],
                "cart": [cart_line], "language": "ko", "defer_cart_add": True,
            }) for message in (
                "계산해줘",
                "이대로 주문할게",
                "주문 확정해줘",
                "결제할게",
            )]
            questions = [self.client.post("/api/chat", json={
                "message": message, "table_id": 5, "history": [],
                "cart": [cart_line], "language": "ko", "defer_cart_add": True,
            }) for message in (
                "주문 가능한가요?",
                "결제수단은 뭐가 있어요?",
            )]

        self.assertTrue(all(response.status_code == 200 for response in commands))
        self.assertTrue(all(response.json()["open_order_form"] for response in commands))
        self.assertTrue(all(response.json()["cart"]["order_no"] is None
                            for response in commands))
        self.assertTrue(all(response.status_code == 200 for response in questions))
        self.assertTrue(all(not response.json()["open_order_form"]
                            for response in questions))

    def test_generic_alcohol_purchase_verifies_once_then_cart_add_consumes_token(self):
        request = {
            "message": "주류를 구매하고 싶어요",
            "table_id": 5,
            "history": [],
            "cart": [],
            "language": "ko",
            "defer_cart_add": True,
        }
        choice_result = SimpleNamespace(
            reply="원하는 주류 메뉴를 골라 주세요.",
            intent="메뉴질문", quick_replies=[], docs=[], menu_images=[], added_items=[],
        )
        alcohol = {
            "menu_id": "M36", "variant_id": "M36-ICED-ONE", "qty": 1,
            "bean": None, "extra_shots": 0, "milk": None,
            "sweetness": None, "ice": None, "warming": None,
        }
        env = {"OPENAI_API_KEY": "test-key", "MOKI_STATE_SECRET": STATE_SECRET}
        with patch.dict(os.environ, env, clear=False), \
                patch("api.index.is_mock", return_value=False), \
                patch("api.index.handle", return_value=choice_result) as handle_mock:
            gate = self.client.post("/api/chat", json=request)
            self.assertTrue(gate.json()["requires_staff_verification"])
            handle_mock.assert_not_called()
            verified = self.client.post("/api/staff/verify", json={
                "table_id": 5,
                "cart": [],
                "state_token": gate.json()["state_token"],
                "staff_challenge": gate.json()["staff_challenge"],
                "language": "ko",
            }, headers={"X-Moki-Staff-Code": "1234"})
            self.assertEqual(verified.status_code, 200, verified.text)
            authorization = verified.json()["staff_authorization"]
            self.assertFalse(verified.json()["cart"]["staff_checked"])

            retried = self.client.post("/api/chat", json={
                **request,
                "state_token": verified.json()["state_token"],
                "staff_authorization": authorization,
            })
            self.assertEqual(retried.status_code, 200, retried.text)
            self.assertEqual(retried.json()["staff_authorization"], authorization)

            added = self.client.post("/api/cart/action", json={
                "action": "add", "table_id": 5, "cart": [],
                "state_token": retried.json()["state_token"],
                "staff_authorization": authorization,
                "item": alcohol, "language": "ko",
            })
            self.assertEqual(added.status_code, 200, added.text)
            self.assertFalse(added.json()["requires_staff_verification"])
            self.assertTrue(added.json()["cart"]["staff_checked"])

            increased = self.client.post("/api/cart/action", json={
                "action": "set_qty", "table_id": 5,
                "cart": [alcohol],
                "state_token": added.json()["state_token"],
                "index": 0, "quantity": 2, "language": "ko",
            })
            self.assertEqual(increased.status_code, 200, increased.text)
            self.assertTrue(increased.json()["requires_staff_verification"])

    def test_exact_alcohol_authorization_cannot_approve_a_different_menu(self):
        requested = CartItem(
            menu_id="M34", variant_id="M34-ICED-ONE",
            name="위스키 하이볼", temp="ICED", size="ONE", is_alcohol=True,
        )
        m34 = _line(requested)
        m37 = {
            "menu_id": "M37", "variant_id": "M37-NA-ONE", "qty": 1,
            "bean": None, "extra_shots": 0, "milk": None,
            "sweetness": None, "ice": None, "warming": None,
        }

        def add_requested(_message, _store, cart, _history):
            cart.add(deepcopy(requested))
            return SimpleNamespace(
                reply="위스키 하이볼을 담았어요.", intent="장바구니",
                quick_replies=[], docs=[], menu_images=[], added_items=[requested],
            )

        env = {"OPENAI_API_KEY": "test-key", "MOKI_STATE_SECRET": STATE_SECRET}
        with patch.dict(os.environ, env, clear=False), \
                patch("api.index.is_mock", return_value=False), \
                patch("api.index.handle", side_effect=add_requested):
            gate = self.client.post("/api/chat", json={
                "message": "위스키 하이볼 한 잔 담아줘",
                "table_id": 5, "history": [], "cart": [], "language": "ko",
            })
            self.assertTrue(gate.json()["requires_staff_verification"])
            verified = self.client.post("/api/staff/verify", json={
                "table_id": 5, "cart": [],
                "state_token": gate.json()["state_token"],
                "staff_challenge": gate.json()["staff_challenge"],
                "language": "ko",
            }, headers={"X-Moki-Staff-Code": "1234"})
            authorization = verified.json()["staff_authorization"]

            wrong_menu = self.client.post("/api/cart/action", json={
                "action": "add", "table_id": 5, "cart": [],
                "state_token": verified.json()["state_token"],
                "staff_authorization": authorization,
                "item": m37, "language": "ko",
            })
            self.assertTrue(wrong_menu.json()["requires_staff_verification"])
            self.assertFalse(wrong_menu.json()["cart"]["staff_checked"])

            exact_menu = self.client.post("/api/cart/action", json={
                "action": "add", "table_id": 5, "cart": [],
                "state_token": verified.json()["state_token"],
                "staff_authorization": authorization,
                "item": m34, "language": "ko",
            })
            self.assertFalse(exact_menu.json()["requires_staff_verification"])
            self.assertTrue(exact_menu.json()["cart"]["staff_checked"])

    def test_generic_alcohol_purchase_phrases_are_distinct_from_policy_questions(self):
        purchase_messages = (
            "주류를 주문하고 싶어요",
            "술을 주문하려고 해요",
            "술 좀 주세요",
        )
        for message in purchase_messages:
            with self.subTest(message=message):
                self.assertTrue(_explicit_alcohol_purchase_intent(message))
        self.assertTrue(_explicit_alcohol_purchase_intent("안주와 맥주 주문할게요"))
        non_purchase_messages = (
            "주류 주문 가능한가요?",
            "술 가격과 도수를 알려줘",
            "도수가 낮은 술을 추천해줘",
            "술을 주문하고 싶지 않아요",
            "주류는 구매하고 싶지 않아",
            "맥주는 안 살게요",
            "I do not want to order alcohol",
            "I won't order alcohol",
            "술이 없는 음료 담아줘",
            "주류가 아닌 메뉴 주문할게",
            "술 안 든 하이볼 주세요",
            "논알코올 음료 담아줘",
        )
        for message in non_purchase_messages:
            with self.subTest(message=message):
                self.assertFalse(_explicit_alcohol_purchase_intent(message))

        with patch.dict(os.environ, {
            "OPENAI_API_KEY": "test-key", "MOKI_STATE_SECRET": STATE_SECRET,
        }, clear=False), patch("api.index.is_mock", return_value=False), \
                patch("api.index.handle") as handle_mock:
            gates = [self.client.post("/api/chat", json={
                "message": message, "table_id": 5, "history": [], "cart": [],
                "language": "ko",
            }) for message in purchase_messages]
        handle_mock.assert_not_called()
        self.assertTrue(all(
            response.status_code == 200
            and response.json()["requires_staff_verification"]
            and response.json()["staff_challenge"]
            for response in gates
        ))

    def test_mock_specific_alcohol_purchase_gates_and_carries_menu_bound_add(self):
        env = {"MOKI_STATE_SECRET": STATE_SECRET}
        request = {
            "message": "맥주 주문할게요", "table_id": 5,
            "history": [], "cart": [], "language": "ko",
            "defer_cart_add": True,
        }
        lager = {
            "menu_id": "M36", "variant_id": "M36-ICED-ONE", "qty": 1,
            "bean": None, "extra_shots": 0, "milk": None,
            "sweetness": None, "ice": None, "warming": None,
        }
        wine = {
            "menu_id": "M37", "variant_id": "M37-NA-ONE", "qty": 1,
            "bean": None, "extra_shots": 0, "milk": None,
            "sweetness": None, "ice": None, "warming": None,
        }
        mock_patches = (
            patch("api.index.is_mock", return_value=True),
            patch("src.router.is_mock", return_value=True),
            patch("src.chain.is_mock", return_value=True),
            patch("src.kiosk.is_mock", return_value=True),
        )
        with patch.dict(os.environ, env, clear=False), \
                mock_patches[0], mock_patches[1], mock_patches[2], mock_patches[3]:
            gates = [self.client.post("/api/chat", json={
                **request, "message": message,
            }) for message in ("맥주 주문할게요", "안주와 맥주 주문할게요")]
            self.assertTrue(all(
                response.status_code == 200
                and response.json()["requires_staff_verification"]
                for response in gates
            ))

            gate = gates[0].json()
            verified = self.client.post("/api/staff/verify", json={
                "table_id": 5, "cart": [],
                "state_token": gate["state_token"],
                "staff_challenge": gate["staff_challenge"],
                "language": "ko",
            }, headers={"X-Moki-Staff-Code": "1234"})
            authorization = verified.json()["staff_authorization"]
            retried = self.client.post("/api/chat", json={
                **request,
                "state_token": verified.json()["state_token"],
                "staff_authorization": authorization,
            })
            retry_payload = retried.json()
            self.assertFalse(retry_payload["requires_staff_verification"])
            self.assertEqual(retry_payload["open_option_menu_id"], "M36")
            self.assertEqual(
                [action["menu_id"] for action in retry_payload["menu_actions"]],
                ["M36"],
            )
            self.assertEqual(retry_payload["staff_authorization"], authorization)

            wrong_menu = self.client.post("/api/cart/action", json={
                "action": "add", "table_id": 5, "cart": [],
                "state_token": retry_payload["state_token"],
                "staff_authorization": authorization,
                "item": wine, "language": "ko",
            })
            self.assertTrue(wrong_menu.json()["requires_staff_verification"])

            added = self.client.post("/api/cart/action", json={
                "action": "add", "table_id": 5, "cart": [],
                "state_token": retry_payload["state_token"],
                "staff_authorization": authorization,
                "item": lager, "language": "ko",
            })
            self.assertFalse(added.json()["requires_staff_verification"])
            self.assertTrue(added.json()["cart"]["staff_checked"])

            no_gates = [self.client.post("/api/chat", json={
                **request, "message": message,
            }) for message in (
                "맥주 가격과 도수 알려줘",
                "맥주 주문 가능한가요?",
                "맥주 주문하고 싶지 않아요",
            )]
            self.assertTrue(all(
                response.status_code == 200
                and not response.json()["requires_staff_verification"]
                for response in no_gates
            ))

    def test_production_specific_alcohol_purchase_gates_before_api_key(self):
        requests = ("맥주 주문할게요", "위스키 하이볼 한 잔 주세요")
        with patch.dict(os.environ, {
            "MOKI_STATE_SECRET": STATE_SECRET,
        }, clear=False), patch("api.index.is_mock", return_value=False), \
                patch("api.index.ensure_api_key") as api_key_mock, \
                patch("api.index.handle") as handle_mock:
            responses = [self.client.post("/api/chat", json={
                "message": message, "table_id": 5,
                "history": [], "cart": [], "language": "ko",
            }) for message in requests]

        api_key_mock.assert_not_called()
        handle_mock.assert_not_called()
        for response in responses:
            with self.subTest(response=response):
                self.assertEqual(response.status_code, 200)
                payload = response.json()
                self.assertTrue(payload["requires_staff_verification"])
                self.assertEqual(
                    payload["staff_verification_reason"], "alcohol_purchase")
                self.assertTrue(payload["staff_challenge"])

    def test_alcohol_information_and_explicit_exclusion_do_not_gate(self):
        result = SimpleNamespace(
            reply="정보를 알려드릴게요.", intent="메뉴질문",
            quick_replies=[], docs=[], menu_images=[], added_items=[],
        )
        env = {"OPENAI_API_KEY": "test-key", "MOKI_STATE_SECRET": STATE_SECRET}
        messages = (
            "모키 라거 가격과 도수 알려줘",
            "도수가 낮은 술 추천해줘",
            "술 말고 달달한 커피 담아줘",
            "주류 구매 가능한가요?",
            "술을 주문하고 싶지 않아요",
            "주류는 구매하고 싶지 않아",
            "맥주는 안 살게요",
            "I do not want to order alcohol",
            "I won't order alcohol",
            "술이 없는 음료 담아줘",
            "주류가 아닌 메뉴 주문할게",
            "술 안 든 하이볼 주세요",
            "논알코올 음료 담아줘",
        )
        with patch.dict(os.environ, env, clear=False), \
                patch("api.index.is_mock", return_value=False), \
                patch("api.index.handle", return_value=result) as handle_mock:
            responses = [self.client.post("/api/chat", json={
                "message": message, "table_id": 5, "history": [], "cart": [],
                "language": "ko",
            }) for message in messages]
        self.assertEqual(handle_mock.call_count, len(messages))
        self.assertTrue(all(not response.json()["requires_staff_verification"]
                            for response in responses))

    def test_checkout_receipt_exposes_zero_discount_demo_contract(self):
        drink = {
            "menu_id": "M14", "variant_id": "M14-HOT-ONE", "qty": 1,
            "bean": None, "extra_shots": 0, "milk": None,
            "sweetness": None, "ice": None, "warming": None,
        }
        with patch.dict(os.environ, {"MOKI_STATE_SECRET": STATE_SECRET}, clear=False):
            added = self.client.post("/api/cart/action", json={
                "action": "add", "table_id": 4, "cart": [], "item": drink,
            }).json()
            response = self.client.post("/api/order/confirm", json={
                "table_id": 4,
                "cart": [_line(SimpleNamespace(**drink))],
                "state_token": added["state_token"],
                "service_mode": "dine_in", "cup": "store", "supplies": [],
                "payment_method": "card", "split_mode": "none", "split_count": 1,
                "receipt": "digital", "language": "ko",
            })

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        checkout = payload["checkout"]
        self.assertEqual(checkout["order_no"], payload["order_no"])
        self.assertEqual(checkout["table_id"], 4)
        self.assertEqual(checkout["items"][0]["menu_id"], "M14")
        self.assertEqual(checkout["subtotal"], checkout["total_before_discount"])
        self.assertEqual(checkout["discount"], 0)
        self.assertEqual(checkout["total_due"], checkout["subtotal"])
        self.assertFalse(checkout["membership_connected"])
        self.assertFalse(checkout["membership_applied"])
        self.assertFalse(checkout["benefits_available"])
        self.assertEqual(checkout["payment_method"], "card")
        self.assertEqual(checkout["receipt"], "digital")
        self.assertEqual(checkout["completion_status"], "demo_complete")
        metadata = payload["order_form"]
        self.assertFalse(metadata["membership"]["lookup_supported"])
        self.assertFalse(metadata["discounts"]["selection_supported"])
        self.assertEqual(metadata["discounts"]["discount_amount"], 0)


if __name__ == "__main__":
    unittest.main()
