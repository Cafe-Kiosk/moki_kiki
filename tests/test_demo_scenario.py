"""End-to-end regression for the documented five-minute presentation script."""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from jsonschema import validate

from api.index import app
from src.demo_scenario import demo_plan, detect_demo_step
from src.prompts import load_schema


STATE_SECRET = "five-minute-demo-secret-at-least-32-characters"

SCRIPT = (
    "처음 왔어요. 달콤하고 우유가 들어간 커피를 추천해 주세요. 아직 담지는 말아 주세요.",
    "아메리카노랑 카푸치노의 맛과 가격은 어떻게 달라요? 카푸치노는 아이스로도 되나요?",
    "카페 라떼에 바닐라 시럽을 추가할 수 있나요? 그리고 약과는 어떤 디저트이고 한 접시에 몇 개, 얼마인가요?",
    "바닐라 라떼 아이스 S 한 잔 주세요. 디카페인 원두와 오트로 하고, 시럽은 절반으로 선택할게요. 샷은 추가하지 말고 얼음은 기본으로요. 약과도 한 접시 담아 주세요.",
    "그런데 오늘 축구 경기 결과도 알려줄 수 있어요?",
    "매장에서 먹을게요. 현재 좌석과 주문 내역, 적용된 옵션과 최종 금액을 보여 주세요.",
    "방금 확인한 바닐라 라떼 한 잔, 총 7,200원으로 시연 주문을 확정해 주세요.",
)


def _cart_lines(payload: dict) -> list[dict]:
    keys = {
        "menu_id", "variant_id", "qty", "bean", "extra_shots",
        "milk", "sweetness", "ice", "warming",
    }
    return [{key: item.get(key) for key in keys}
            for item in payload["cart"]["items"]]


class FiveMinuteDemoTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def _chat(self, message: str, cart: list[dict], state_token: str | None):
        return self.client.post("/api/chat", json={
            "message": message,
            "table_id": 5,
            "history": [],
            "cart": cart,
            "state_token": state_token,
            "language": "ko",
            "defer_cart_add": True,
        })

    def test_script_utterances_have_schema_valid_deterministic_plans(self):
        self.assertEqual(
            [detect_demo_step(message) for message in SCRIPT],
            [1, 2, 3, 4, 6, 7, 8],
        )
        schema = load_schema("intent")
        for message in SCRIPT:
            with self.subTest(message=message):
                validate(demo_plan(message), schema)

        order_targets = demo_plan(SCRIPT[3])["actions"][0]["targets"]
        self.assertEqual([target["menu_id"] for target in order_targets], ["M06", "M28"])
        self.assertEqual(order_targets[0]["variant_id"], "M06-ICED-S")
        self.assertEqual(order_targets[0]["options"], {
            "bean": "B03", "extra_shots": 0, "milk": "oat",
            "sweetness": "less", "ice": "normal", "warming": None,
        })

    def test_complete_script_preserves_cart_and_reaches_demo_receipt(self):
        env = {
            "OPENAI_API_KEY": "test-key",
            "MOKI_STATE_SECRET": STATE_SECRET,
        }
        with patch.dict(os.environ, env, clear=False), \
                patch("api.index.is_mock", return_value=False), \
                patch("src.router._invoke") as router_llm, \
                patch("src.chain.ChatOpenAI") as answer_llm:
            state_token = None
            cart: list[dict] = []

            for message, expected in zip(SCRIPT[:3], (
                ("바닐라 라떼", "6,000원", "담지 않았"),
                ("아메리카노", "카푸치노", "아이스로 제공하지 않"),
                ("지원하지 않", "2개", "4,500원"),
            )):
                response = self._chat(message, cart, state_token)
                self.assertEqual(response.status_code, 200, response.text)
                payload = response.json()
                self.assertEqual(payload["cart"]["items"], [])
                self.assertTrue(all(fragment in payload["reply"] for fragment in expected))
                state_token = payload["state_token"]

            order = self._chat(SCRIPT[3], cart, state_token)
            self.assertEqual(order.status_code, 200, order.text)
            order_payload = order.json()
            self.assertEqual(order_payload["cart"]["items"], [])
            self.assertEqual(
                [item["menu_id"] for item in order_payload["deferred_cart_items"]],
                ["M06", "M28"],
            )
            latte = order_payload["deferred_cart_items"][0]
            self.assertEqual(latte["variant_id"], "M06-ICED-S")
            self.assertEqual(
                (latte["bean"], latte["milk"], latte["sweetness"],
                 latte["extra_shots"], latte["ice"]),
                ("B03", "oat", "less", 0, "normal"),
            )

            state_token = order_payload["state_token"]
            for item in order_payload["deferred_cart_items"]:
                added = self.client.post("/api/cart/action", json={
                    "action": "add", "table_id": 5, "cart": cart,
                    "state_token": state_token, "item": item, "language": "ko",
                })
                self.assertEqual(added.status_code, 200, added.text)
                added_payload = added.json()
                cart = _cart_lines(added_payload)
                state_token = added_payload["state_token"]
            self.assertEqual(added_payload["cart"]["total"], 11700)

            removed = self.client.post("/api/cart/action", json={
                "action": "remove", "table_id": 5, "cart": cart,
                "state_token": state_token, "index": 1, "language": "ko",
            })
            self.assertEqual(removed.status_code, 200, removed.text)
            removed_payload = removed.json()
            self.assertEqual(removed_payload["cart"]["total"], 7200)
            self.assertEqual(removed_payload["cart"]["items"][0]["menu_id"], "M06")
            cart = _cart_lines(removed_payload)
            state_token = removed_payload["state_token"]

            football = self._chat(SCRIPT[4], cart, state_token)
            self.assertEqual(football.status_code, 200, football.text)
            football_payload = football.json()
            self.assertIn("축구 경기 결과는 안내하기 어렵", football_payload["reply"])
            self.assertEqual(football_payload["cart"]["total"], 7200)
            state_token = football_payload["state_token"]

            review = self._chat(SCRIPT[5], cart, state_token)
            self.assertEqual(review.status_code, 200, review.text)
            review_payload = review.json()
            self.assertTrue(all(fragment in review_payload["reply"] for fragment in (
                "좌석은 5번", "바닐라 라떼 아이스 S", "7,200원",
            )))
            self.assertEqual(review_payload["cart"]["total"], 7200)
            state_token = review_payload["state_token"]

            confirm = self._chat(SCRIPT[6], cart, state_token)
            self.assertEqual(confirm.status_code, 200, confirm.text)
            confirm_payload = confirm.json()
            self.assertTrue(confirm_payload["open_order_form"])
            self.assertIsNone(confirm_payload["cart"]["order_no"])

            completed = self.client.post("/api/order/confirm", json={
                "table_id": 5,
                "cart": cart,
                "state_token": confirm_payload["state_token"],
                "service_mode": "dine_in",
                "cup": "store",
                "supplies": [],
                "payment_method": "card",
                "split_mode": "none",
                "split_count": 1,
                "receipt": "paper",
                "language": "ko",
            })
            self.assertEqual(completed.status_code, 200, completed.text)
            checkout = completed.json()["checkout"]
            self.assertEqual(checkout["total_due"], 7200)
            self.assertTrue(checkout["order_no"].startswith("M"))
            self.assertFalse(checkout["external_payment_performed"])
            self.assertFalse(checkout["store_order_submitted"])

        router_llm.assert_not_called()
        answer_llm.assert_not_called()


if __name__ == "__main__":
    unittest.main()
