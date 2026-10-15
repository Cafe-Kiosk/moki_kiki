"""HTI 흐름의 사진·언어·좌석·장바구니·주문 마감 통합 회귀 검사."""
from __future__ import annotations

import hashlib
import os
import re
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import patch

import openpyxl
from fastapi.testclient import TestClient

from api.index import app
from src.cart import CartItem, list_menus
from src.config import current_language, request_language
from src.content import menu_image_cards
from src.router import adapt_plan


ROOT = Path(__file__).resolve().parent.parent
STATE_SECRET = "hti-regression-state-secret-32-chars"
CART_LINE_FIELDS = (
    "menu_id",
    "variant_id",
    "qty",
    "bean",
    "extra_shots",
    "milk",
    "sweetness",
    "ice",
    "warming",
)


def _cart_lines(cart_payload: dict) -> list[dict]:
    """API 표시용 필드를 다음 요청의 신뢰 경계 안으로 가져간다."""
    return [
        {key: item.get(key) for key in CART_LINE_FIELDS}
        for item in cart_payload["items"]
    ]


class HtiRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_excel_embedded_images_match_every_catalog_url_and_served_jpeg(self):
        """웹이 노출하는 33장이 엑셀에 실제 임베드된 바이트와 같다."""
        workbook = openpyxl.load_workbook(
            ROOT / "data" / "moki_data.xlsx", data_only=True
        )
        sheet = workbook["사진메뉴판"]
        embedded: dict[str, bytes] = {}
        for image in sheet._images:
            # 사진 위치와 메뉴 ID 표 위치의 관계는 추출 스크립트와 같다.
            menu_id = str(sheet.cell(
                row=image.anchor._from.row + 16,
                column=image.anchor._from.col + 3,
            ).value)
            embedded[menu_id] = image._data()

        response = self.client.get("/api/menu")
        self.assertEqual(response.status_code, 200, response.text)
        api_items = {item["id"]: item for item in response.json()["items"]}
        excel_rows = {str(row["메뉴 ID"]): row for row in list_menus()}

        self.assertEqual(len(embedded), 33)
        self.assertEqual(set(api_items), set(excel_rows))
        self.assertEqual(set(embedded), set(excel_rows))
        for menu_id, excel_row in excel_rows.items():
            with self.subTest(menu_id=menu_id):
                item = api_items[menu_id]
                self.assertEqual(item["image"], f"/assets/menu/{menu_id}.jpg")
                self.assertEqual(item["name"], excel_row["메뉴명"])
                self.assertIn(
                    excel_row["사진 기준 주문 단위"],
                    {variant["id"] for variant in item["variants"]},
                )

                asset = ROOT / "public" / "assets" / "menu" / f"{menu_id}.jpg"
                self.assertEqual(
                    hashlib.sha256(asset.read_bytes()).digest(),
                    hashlib.sha256(embedded[menu_id]).digest(),
                )
                served = self.client.get(item["image"])
                self.assertEqual(served.status_code, 200)
                self.assertEqual(served.headers["content-type"], "image/jpeg")
                self.assertTrue(served.content.startswith(b"\xff\xd8\xff"))

    def test_photo_followup_resolves_recent_menu_not_policy_document(self):
        """사진도 보여줘”는 P14 정책이 아니라 직전 M14 사진을 보여 준다."""
        policy_document = SimpleNamespace(metadata={
            "id": "P14",
            "entity_id": "P14",
            "type": "policy",
            "name": "이미지 정책",
        })
        history = [{
            "role": "assistant",
            "content": "8살 아이에게는 핫초코(M14 HOT)를 추천해요.",
        }]
        cards = menu_image_cards(
            [policy_document],
            user_message="혹시 사진도 보여줄 수 있어?",
            rewritten="직전 추천 메뉴의 사진을 보여줘",
            reply="대표 사진을 아래에 보여드릴게요.",
            history=history,
        )
        self.assertEqual([card["id"] for card in cards], ["M14"])
        self.assertEqual(cards[0]["image"], "/assets/menu/M14.jpg")
        self.assertEqual(cards[0]["representative_variant_id"], "M14-HOT-ONE")
        self.assertNotIn("images/M14.png", repr(cards))

        result = SimpleNamespace(
            reply="대표 사진을 아래에 보여드릴게요.",
            quick_replies=[],
            docs=[policy_document],
            rewritten="직전 추천 메뉴의 사진",
        )
        with patch("api.index.is_mock", return_value=True), \
                patch("api.index.handle", return_value=result):
            response = self.client.post("/api/chat", json={
                "message": "혹시 사진도 보여줄 수 있어?",
                "table_id": 5,
                "history": history,
                "cart": [],
                "language": "ko",
            })

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual([card["id"] for card in payload["menu_images"]], ["M14"])
        self.assertEqual([card["menu_id"] for card in payload["menu_actions"]], ["M14"])
        self.assertEqual(payload["menu_actions"][0]["image"], "/assets/menu/M14.jpg")
        self.assertEqual(payload["table_id"], 5)
        self.assertEqual(payload["cart"]["table_id"], 5)
        self.assertEqual(payload["language"], "ko")
        self.assertTrue(payload["order_form"]["simulated"])
        self.assertFalse(payload["order_form"]["external_payment_performed"])
        self.assertEqual(
            self.client.get(payload["menu_images"][0]["image"]).status_code,
            200,
        )

    def test_request_language_is_scoped_nested_and_across_concurrent_contexts(self):
        self.assertEqual(current_language(), "ko")
        with request_language("en"):
            self.assertEqual(current_language(), "en")
            with request_language("ja"):
                self.assertEqual(current_language(), "ja")
            self.assertEqual(current_language(), "en")
        self.assertEqual(current_language(), "ko")

        barrier = Barrier(2)

        def observe(language: str) -> tuple[str, str]:
            with request_language(language):
                barrier.wait(timeout=2)
                inside = current_language()
            return inside, current_language()

        with ThreadPoolExecutor(max_workers=2) as executor:
            observed = list(executor.map(observe, ("zh", "ja")))
        self.assertEqual({inside for inside, _ in observed}, {"zh", "ja"})
        self.assertTrue(all(after == "ko" for _, after in observed))

    def test_chat_applies_selected_language_only_for_that_request(self):
        observed: list[str] = []

        def fake_handle(_message, _store, _cart, _history):
            observed.append(current_language())
            return SimpleNamespace(
                reply="ok", quick_replies=[], docs=[], menu_images=[]
            )

        env = {"OPENAI_API_KEY": "test-key", "VERCEL": "1"}
        with patch.dict(os.environ, env, clear=False), \
                patch("api.index.is_mock", return_value=False), \
                patch("api.index.handle", side_effect=fake_handle):
            for language in ("en", "zh", "ja", "ko"):
                response = self.client.post("/api/chat", json={
                    "message": "Show me the menu",
                    "table_id": 5,
                    "history": [],
                    "cart": [],
                    "language": language,
                })
                self.assertEqual(response.status_code, 200, response.text)

        self.assertEqual(observed, ["en", "zh", "ja", "ko"])
        self.assertEqual(current_language(), "ko")

    def test_order_review_intent_uses_structured_checkout_path(self):
        """HTI order_review도 확정 전 주문 검토 화면으로 연결된다."""
        adapted = adapt_plan(
            "주문 검토해줘",
            {"rewritten_utterance": "주문 검토", "language": "ko"},
            {
                "language": "ko",
                "actions": [{"intent": "order_review"}],
                "needs_clarification": False,
            },
        )
        self.assertEqual(adapted["intent"], "결제")

    def test_browser_chat_defers_cart_add_until_single_option_review(self):
        """대화 추천은 검토 화면을 열고 실제 담기·주류 확인은 아직 하지 않는다."""
        def propose(message, _store, cart, _history):
            is_alcohol = "하이볼" in message
            menu_id = "M34" if is_alcohol else "M02"
            cart.add(CartItem(
                menu_id=menu_id,
                variant_id=("M34-ICED-ONE" if is_alcohol else "M02-ICED-S"),
                name=("위스키 하이볼" if is_alcohol else "아메리카노"),
                temp="ICED",
                size=("ONE" if is_alcohol else "S"),
                is_alcohol=is_alcohol,
            ))
            document = SimpleNamespace(metadata={
                "id": menu_id, "entity_id": menu_id,
                "type": "menu", "name": menu_id,
            })
            return SimpleNamespace(
                reply="장바구니에 담았습니다.", intent="장바구니",
                quick_replies=[], docs=[document], menu_images=[],
            )

        env = {
            "OPENAI_API_KEY": "test-key",
            "MOKI_STATE_SECRET": STATE_SECRET,
        }
        with patch.dict(os.environ, env, clear=False), \
                patch("api.index.is_mock", return_value=False), \
                patch("api.index.handle", side_effect=propose):
            coffee = self.client.post("/api/chat", json={
                "message": "아이스 아메리카노를 담아줘",
                "table_id": 5, "history": [], "cart": [],
                "language": "ko", "defer_cart_add": True,
            })
            alcohol = self.client.post("/api/chat", json={
                "message": "위스키 하이볼을 담아줘",
                "table_id": 5, "history": [], "cart": [],
                "language": "ko", "defer_cart_add": True,
            })

        self.assertEqual(coffee.status_code, 200, coffee.text)
        coffee_payload = coffee.json()
        self.assertEqual(coffee_payload["cart"]["items"], [])
        self.assertEqual(coffee_payload["open_option_menu_id"], "M02")
        self.assertEqual(coffee_payload["menu_actions"][0]["menu_id"], "M02")
        self.assertEqual(
            coffee_payload["deferred_cart_items"][0]["menu_id"], "M02")
        self.assertFalse(coffee_payload["requires_staff_verification"])
        self.assertIn("담기 전에", coffee_payload["reply"])

        self.assertEqual(alcohol.status_code, 200, alcohol.text)
        alcohol_payload = alcohol.json()
        self.assertEqual(alcohol_payload["cart"]["items"], [])
        self.assertTrue(alcohol_payload["requires_staff_verification"])
        self.assertEqual(
            alcohol_payload["staff_verification_reason"], "alcohol_purchase")
        self.assertTrue(alcohol_payload["staff_challenge"])

    def test_browser_chat_keeps_non_add_cart_mutations_realtime(self):
        """defer_cart_add는 신규 담기만 보류하고 수량 변경은 즉시 반영한다."""
        line = {
            "menu_id": "M14", "variant_id": "M14-HOT-ONE", "qty": 1,
            "bean": None, "extra_shots": 0, "milk": None,
            "sweetness": None, "ice": None, "warming": None,
        }

        def change_quantity(_message, _store, cart, _history):
            cart.set_qty(0, 2)
            return SimpleNamespace(
                reply="수량을 2개로 바꾸었습니다.", intent="장바구니",
                quick_replies=[], docs=[], menu_images=[],
            )

        with patch("api.index.is_mock", return_value=True), \
                patch("api.index.handle", side_effect=change_quantity):
            response = self.client.post("/api/chat", json={
                "message": "수량을 2개로 바꿔줘",
                "table_id": 5, "history": [], "cart": [line],
                "language": "ko", "defer_cart_add": True,
            })

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["cart"]["items"][0]["qty"], 2)
        self.assertIsNone(payload["open_option_menu_id"])
        self.assertEqual(payload["deferred_cart_items"], [])
        self.assertIn("수량", payload["reply"])

    def test_browser_chat_payment_opens_required_review_without_confirming(self):
        line = {
            "menu_id": "M14", "variant_id": "M14-HOT-ONE", "qty": 1,
            "bean": None, "extra_shots": 0, "milk": None,
            "sweetness": None, "ice": None, "warming": None,
        }

        def premature_confirm(_message, _store, cart, _history):
            cart.confirm()
            return SimpleNamespace(
                reply="주문을 확정했습니다.", intent="결제",
                quick_replies=[], docs=[], menu_images=[],
            )

        env = {
            "OPENAI_API_KEY": "test-key",
            "MOKI_STATE_SECRET": STATE_SECRET,
        }
        with patch.dict(os.environ, env, clear=False), \
                patch("api.index.is_mock", return_value=False), \
                patch("api.index.handle", side_effect=premature_confirm):
            response = self.client.post("/api/chat", json={
                "message": "이대로 결제해줘", "table_id": 5,
                "history": [], "cart": [line], "language": "ko",
                "defer_cart_add": True,
            })

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertTrue(payload["open_order_form"])
        self.assertIsNone(payload["cart"]["order_no"])
        self.assertIn("주문 검토 화면", payload["reply"])

    def test_conversational_table_change_preserves_cart_and_signed_state(self):
        coffee = {
            "menu_id": "M14",
            "variant_id": "M14-HOT-ONE",
            "qty": 1,
            "bean": None,
            "extra_shots": 0,
            "milk": None,
            "sweetness": None,
            "ice": None,
            "warming": None,
        }
        env = {
            "MOKI_STATE_SECRET": STATE_SECRET,
            "OPENAI_API_KEY": "",
            "VERCEL": "1",
        }
        with patch.dict(os.environ, env, clear=False):
            added = self.client.post("/api/cart/action", json={
                "action": "add",
                "table_id": 5,
                "cart": [],
                "item": coffee,
                "language": "ko",
            })
            self.assertEqual(added.status_code, 200, added.text)
            before = added.json()

            with patch("api.index.is_mock", return_value=False), \
                    patch("api.index.handle") as handle_mock:
                changed = self.client.post("/api/chat", json={
                    "message": "좌석을 5번에서 4번으로 바꿔줘",
                    "table_id": 5,
                    "history": [],
                    "cart": _cart_lines(before["cart"]),
                    "state_token": before["state_token"],
                    "language": "ko",
                })

            self.assertEqual(changed.status_code, 200, changed.text)
            handle_mock.assert_not_called()
            payload = changed.json()
            self.assertEqual(payload["table_id"], 4)
            self.assertEqual(payload["cart"]["table_id"], 4)
            self.assertEqual(payload["cart"]["total"], before["cart"]["total"])
            self.assertEqual(
                _cart_lines(payload["cart"]),
                _cart_lines(before["cart"]),
            )
            self.assertIn("4", payload["reply"])

            # 좌석 변경 후 발급된 토큰은 실제로 4번 장바구니에 이어진다.
            quantity_changed = self.client.post("/api/cart/action", json={
                "action": "set_qty",
                "table_id": 4,
                "cart": _cart_lines(payload["cart"]),
                "state_token": payload["state_token"],
                "index": 0,
                "quantity": 2,
                "language": "ko",
            })
            self.assertEqual(quantity_changed.status_code, 200, quantity_changed.text)
            self.assertEqual(quantity_changed.json()["cart"]["items"][0]["qty"], 2)

    def test_cart_action_add_quantity_options_remove_and_invalid_is_atomic(self):
        initial = {
            "menu_id": "M03",
            "variant_id": "M03-ICED-S",
            "qty": 1,
            "bean": "B02",
            "extra_shots": 1,
            "milk": "oat",
            "sweetness": None,
            "ice": "less",
            "warming": None,
        }
        replacement = {
            **initial,
            "variant_id": "M03-HOT-S",
            "qty": 2,
            "bean": "B03",
            "extra_shots": 2,
            "milk": "soy",
            "ice": None,
        }
        invalid_replacement = {
            **replacement,
            "menu_id": "M18",
            "variant_id": "M18-NA-ONE",
            "milk": "oat",
            "extra_shots": 0,
            "bean": None,
        }
        env = {"MOKI_STATE_SECRET": STATE_SECRET}
        with patch.dict(os.environ, env, clear=False):
            added = self.client.post("/api/cart/action", json={
                "action": "add", "table_id": 5, "cart": [], "item": initial,
            })
            self.assertEqual(added.status_code, 200, added.text)
            added_payload = added.json()
            self.assertEqual(added_payload["cart"]["total"], 7600)
            self.assertEqual(added_payload["cart"]["items"][0]["subtotal"], 7600)
            self.assertIn("에티오피아", added_payload["cart"]["items"][0]["option_text"])
            self.assertIn("샷+1", added_payload["cart"]["items"][0]["option_text"])
            self.assertIn("오트", added_payload["cart"]["items"][0]["option_text"])

            quantity = self.client.post("/api/cart/action", json={
                "action": "set_qty",
                "table_id": 5,
                "cart": _cart_lines(added_payload["cart"]),
                "state_token": added_payload["state_token"],
                "index": 0,
                "quantity": 2,
            })
            self.assertEqual(quantity.status_code, 200, quantity.text)
            self.assertEqual(quantity.json()["cart"]["total"], 15_200)

            quantity_payload = quantity.json()
            replaced = self.client.post("/api/cart/action", json={
                "action": "replace",
                "table_id": 5,
                "cart": _cart_lines(quantity_payload["cart"]),
                "state_token": quantity_payload["state_token"],
                "index": 0,
                "item": replacement,
            })
            self.assertEqual(replaced.status_code, 200, replaced.text)
            replaced_payload = replaced.json()
            self.assertEqual(replaced_payload["cart"]["total"], 15_800)
            self.assertEqual(replaced_payload["cart"]["items"][0]["extra_shots"], 2)
            self.assertEqual(replaced_payload["cart"]["items"][0]["milk"], "soy")

            stable_cart = _cart_lines(replaced_payload["cart"])
            stable_token = replaced_payload["state_token"]
            rejected = self.client.post("/api/cart/action", json={
                "action": "replace",
                "table_id": 5,
                "cart": stable_cart,
                "state_token": stable_token,
                "index": 0,
                "item": invalid_replacement,
            })
            self.assertEqual(rejected.status_code, 422, rejected.text)

            # 실패한 교체는 서버 상태나 토큰을 부분 수정하지 않는다.
            after_rejection = self.client.post("/api/cart/action", json={
                "action": "set_qty",
                "table_id": 5,
                "cart": stable_cart,
                "state_token": stable_token,
                "index": 0,
                "quantity": 3,
            })
            self.assertEqual(after_rejection.status_code, 200, after_rejection.text)
            after_payload = after_rejection.json()
            self.assertEqual(after_payload["cart"]["items"][0]["menu_id"], "M03")
            self.assertEqual(after_payload["cart"]["items"][0]["milk"], "soy")
            self.assertEqual(after_payload["cart"]["total"], 23_700)

            removed = self.client.post("/api/cart/action", json={
                "action": "remove",
                "table_id": 5,
                "cart": _cart_lines(after_payload["cart"]),
                "state_token": after_payload["state_token"],
                "index": 0,
            })
            self.assertEqual(removed.status_code, 200, removed.text)
            self.assertEqual(removed.json()["cart"]["items"], [])
            self.assertEqual(removed.json()["cart"]["total"], 0)

    def test_simulated_checkout_validates_service_cup_split_receipt_and_retries(self):
        drink = {
            "menu_id": "M14",
            "variant_id": "M14-HOT-ONE",
            "qty": 1,
            "bean": None,
            "extra_shots": 0,
            "milk": None,
            "sweetness": None,
            "ice": None,
            "warming": None,
        }
        env = {"MOKI_STATE_SECRET": STATE_SECRET}
        with patch.dict(os.environ, env, clear=False):
            added = self.client.post("/api/cart/action", json={
                "action": "add", "table_id": 5, "cart": [], "item": drink,
            }).json()
            base = {
                "table_id": 5,
                "cart": _cart_lines(added["cart"]),
                "state_token": added["state_token"],
                "service_mode": "dine_in",
                "cup": "store",
                "supplies": ["straw", "straw"],
                "payment_method": "card",
                "split_mode": "equal",
                "split_count": 3,
                "receipt": "digital",
                "language": "ko",
            }
            confirmed = self.client.post("/api/order/confirm", json=base)
            self.assertEqual(confirmed.status_code, 200, confirmed.text)
            payload = confirmed.json()
            checkout = payload["checkout"]
            self.assertTrue(checkout["simulated"])
            self.assertEqual(checkout["discount"], 0)
            self.assertEqual(checkout["service_mode"], "dine_in")
            self.assertEqual(checkout["cup"], "store")
            self.assertEqual(checkout["supplies"], ["straw"])
            self.assertEqual(checkout["payment_method"], "card")
            self.assertEqual(checkout["split_mode"], "equal")
            self.assertEqual(checkout["split_count"], 3)
            self.assertEqual(
                [part["amount"] for part in checkout["split_parts"]],
                [1934, 1933, 1933],
            )
            self.assertEqual(
                sum(part["amount"] for part in checkout["split_parts"]),
                payload["cart"]["total"],
            )
            self.assertEqual(checkout["receipt"], "digital")
            self.assertRegex(payload["cart"]["order_no"], r"^M\d{4}$")
            self.assertIn("실제 결제", payload["message"])

            retry = self.client.post("/api/order/confirm", json={
                **base,
                "cart": _cart_lines(payload["cart"]),
                "state_token": payload["state_token"],
            })
            self.assertEqual(retry.status_code, 200, retry.text)
            self.assertEqual(
                retry.json()["cart"]["order_no"],
                payload["cart"]["order_no"],
            )

            mutation_after_confirm = self.client.post("/api/cart/action", json={
                "action": "set_qty",
                "table_id": 5,
                "cart": _cart_lines(payload["cart"]),
                "state_token": payload["state_token"],
                "index": 0,
                "quantity": 2,
            })
            self.assertEqual(
                mutation_after_confirm.status_code,
                409,
                mutation_after_confirm.text,
            )
            self.assertIn("이미 확정한 주문", mutation_after_confirm.json()["detail"])

            bad_dine_in_cup = self.client.post("/api/order/confirm", json={
                **base, "cup": "disposable", "split_mode": "none", "split_count": 1,
            })
            bad_takeout_cup = self.client.post("/api/order/confirm", json={
                **base,
                "service_mode": "takeout",
                "cup": "store",
                "split_mode": "none",
                "split_count": 1,
            })
            bad_split = self.client.post("/api/order/confirm", json={
                **base, "split_count": 1,
            })
            bad_dine_in_carrier = self.client.post("/api/order/confirm", json={
                **base,
                "supplies": ["carrier"],
                "split_mode": "none",
                "split_count": 1,
            })
            self.assertEqual(bad_dine_in_cup.status_code, 422)
            self.assertEqual(bad_takeout_cup.status_code, 422)
            self.assertEqual(bad_split.status_code, 422)
            self.assertEqual(bad_dine_in_carrier.status_code, 422)

    def test_alcohol_checkout_needs_staff_code_and_stays_dine_in_only(self):
        alcohol = {
            "menu_id": "M36",
            "variant_id": "M36-ICED-ONE",
            "qty": 1,
            "bean": None,
            "extra_shots": 0,
            "milk": None,
            "sweetness": None,
            "ice": None,
            "warming": None,
        }
        env = {"MOKI_STATE_SECRET": STATE_SECRET}
        with patch.dict(os.environ, env, clear=False):
            unverified = self.client.post("/api/order/confirm", json={
                "table_id": 5,
                "cart": [alcohol],
                "service_mode": "dine_in",
                "cup": "store",
                "supplies": [],
                "payment_method": "card",
                "split_mode": "none",
                "split_count": 1,
                "receipt": "none",
            })
            self.assertEqual(unverified.status_code, 409, unverified.text)

            added = self.client.post("/api/cart/action", json={
                "action": "add", "table_id": 5, "cart": [], "item": alcohol,
            })
            self.assertEqual(added.status_code, 200, added.text)
            gate = added.json()
            self.assertTrue(gate["requires_staff_verification"])
            self.assertEqual(gate["staff_verification_reason"], "alcohol_purchase")
            self.assertTrue(gate["staff_challenge"])

            verified = self.client.post("/api/staff/verify", json={
                "table_id": 5,
                "cart": _cart_lines(gate["cart"]),
                "state_token": gate["state_token"],
                "staff_challenge": gate["staff_challenge"],
                "reason": "alcohol_purchase",
            }, headers={"X-Moki-Staff-Code": "1234"})
            self.assertEqual(verified.status_code, 200, verified.text)
            verified_payload = verified.json()
            self.assertTrue(verified_payload["cart"]["staff_checked"])

            checkout = {
                "table_id": 5,
                "cart": _cart_lines(verified_payload["cart"]),
                "state_token": verified_payload["state_token"],
                "service_mode": "takeout",
                "cup": "personal",
                "supplies": [],
                "payment_method": "mobile",
                "split_mode": "none",
                "split_count": 1,
                "receipt": "paper",
            }
            takeout = self.client.post("/api/order/confirm", json=checkout)
            self.assertEqual(takeout.status_code, 422, takeout.text)
            self.assertIn("매장 이용만", takeout.json()["detail"])

            dine_in = self.client.post("/api/order/confirm", json={
                **checkout, "service_mode": "dine_in", "cup": "store",
            })
            self.assertEqual(dine_in.status_code, 200, dine_in.text)
            self.assertTrue(dine_in.json()["checkout"]["simulated"])
            self.assertEqual(dine_in.json()["checkout"]["receipt"], "paper")
            self.assertRegex(dine_in.json()["cart"]["order_no"], r"^M\d{4}$")


if __name__ == "__main__":
    unittest.main()
