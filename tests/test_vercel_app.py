"""Vercel 진입점과 공개 웹 자산의 회귀 검사."""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.index import app
from src.lexical_store import LexicalStore
from src.retrieve import hybrid_search


class VercelAppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_public_site_and_assets_are_served(self):
        home = self.client.get("/")
        self.assertEqual(home.status_code, 200)
        self.assertIn("모키 커피바", home.text)
        self.assertIn("/assets/moki-listening-avatar.png", home.text)
        self.assertEqual(self.client.get("/app.css").status_code, 200)
        self.assertEqual(self.client.get("/assets/menu/M01.jpg").status_code, 200)
        avatar = self.client.get("/assets/moki-listening-avatar.png")
        self.assertEqual(avatar.status_code, 200)
        self.assertEqual(avatar.headers["content-type"], "image/png")
        self.assertGreater(len(avatar.content), 10_000)

    def test_health_and_menu_use_validated_content(self):
        health = self.client.get("/api/health")
        self.assertEqual(health.status_code, 200)
        payload = health.json()
        self.assertTrue(payload["content"]["ready"], payload["content"]["errors"])
        self.assertEqual(payload["content"]["menu_count"], 33)
        self.assertEqual(payload["content"]["document_count"], 122)
        self.assertEqual(payload["content"]["image_count"], 33)

        menu = self.client.get("/api/menu")
        self.assertEqual(menu.status_code, 200)
        self.assertEqual(len(menu.json()["items"]), 33)
        self.assertTrue(all(item["image"].startswith("/assets/menu/")
                            for item in menu.json()["items"]))

    def test_serverless_search_preserves_exact_menu_rules(self):
        documents, _ = hybrid_search(LexicalStore(), "아아 가격")
        self.assertEqual(documents[0].metadata["id"], "M02")

    def test_serverless_search_finds_chocolate_from_natural_korean(self):
        documents, _ = hybrid_search(
            LexicalStore(), "초콜릿 향이 나는 음료가 있나요")
        ids = {document.metadata["id"] for document in documents}
        self.assertTrue({"M08", "M14"}.issubset(ids), ids)
        self.assertEqual([document.metadata["id"] for document in documents[:2]],
                         ["M08", "M14"])
        self.assertTrue(all(document.metadata.get("lang") == "ko"
                            for document in documents))

    def test_serverless_english_taste_search_excludes_alcohol(self):
        documents, _ = hybrid_search(
            LexicalStore(), "Something smooth without much bitterness")
        ids = [document.metadata["id"] for document in documents]
        self.assertTrue(ids, "영문 맛 질문은 후보를 돌려줘야 합니다.")
        self.assertEqual([identifier.split(":", 1)[0] for identifier in ids[:4]],
                         ["M16", "M17", "M26", "M27"])
        self.assertFalse(any(identifier.split(":", 1)[0] in {
            "M32", "M33", "M34", "M35", "M36", "M37"
        } for identifier in ids), ids)
        self.assertTrue(all(document.metadata.get("lang") == "en"
                            for document in documents))

    def test_serverless_language_filter_runs_before_top_k(self):
        hits = LexicalStore().similarity_search_with_score_for_language(
            "smooth latte", language="en", k=3)
        self.assertEqual(len(hits), 3)
        self.assertTrue(all(document.metadata.get("lang") == "en"
                            for document, _ in hits))

    def test_mock_chat_endpoint_runs_without_external_api(self):
        with patch.dict(os.environ, {"MOKI_PASSWORD": ""}), \
                patch("api.index.is_mock", return_value=True), \
                patch("src.router.is_mock", return_value=True), \
                patch("src.chain.is_mock", return_value=True), \
                patch("src.kiosk.is_mock", return_value=True):
            response = self.client.post("/api/chat", json={
                "message": "아아 가격 알려줘",
                "table_id": 5,
                "history": [],
                "cart": [],
            })

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertIn("화면 체험 모드", payload["reply"])
        self.assertEqual(payload["sources"][0]["id"], "M02")
        self.assertEqual(payload["cart"]["total"], 0)

    def test_client_cannot_forge_order_or_staff_state(self):
        alcohol = {
            "menu_id": "M36", "variant_id": "M36-ICED-ONE", "qty": 1,
            "bean": None, "extra_shots": 0, "milk": None,
            "sweetness": None, "ice": None, "warming": None,
        }
        env = {"MOKI_PASSWORD": "", "MOKI_STATE_SECRET": "test-state-secret"}
        with patch.dict(os.environ, env, clear=False), \
                patch("api.index.is_mock", return_value=True), \
                patch("src.router.is_mock", return_value=True), \
                patch("src.chain.is_mock", return_value=True), \
                patch("src.kiosk.is_mock", return_value=True):
            response = self.client.post("/api/chat", json={
                "message": "장바구니 보여줘", "table_id": 5,
                "history": [], "cart": [alcohol],
                "staff_checked": True, "order_no": "FAKE-ORDER",
            })

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertFalse(payload["cart"]["staff_checked"])
        self.assertIsNone(payload["cart"]["order_no"])
        self.assertEqual(payload["cart"]["status"], "pending_staff_check")

    def test_staff_verification_uses_signed_cart_state(self):
        alcohol = {
            "menu_id": "M36", "variant_id": "M36-ICED-ONE", "qty": 1,
            "bean": None, "extra_shots": 0, "milk": None,
            "sweetness": None, "ice": None, "warming": None,
        }
        env = {
            "MOKI_PASSWORD": "", "MOKI_STAFF_PASSWORD": "staff-code",
            "MOKI_STATE_SECRET": "test-state-secret",
        }
        with patch.dict(os.environ, env, clear=False):
            rejected = self.client.post("/api/staff/verify", json={
                "table_id": 5, "cart": [alcohol],
            }, headers={"X-Moki-Staff-Password": "wrong"})
            verified = self.client.post("/api/staff/verify", json={
                "table_id": 5, "cart": [alcohol],
            }, headers={"X-Moki-Staff-Password": "staff-code"})

        self.assertEqual(rejected.status_code, 401)
        self.assertEqual(verified.status_code, 200, verified.text)
        payload = verified.json()
        self.assertTrue(payload["cart"]["staff_checked"])
        self.assertTrue(payload["state_token"])

        with patch.dict(os.environ, env, clear=False), \
                patch("api.index.is_mock", return_value=True), \
                patch("src.router.is_mock", return_value=True), \
                patch("src.chain.is_mock", return_value=True), \
                patch("src.kiosk.is_mock", return_value=True):
            restored = self.client.post("/api/chat", json={
                "message": "장바구니 보여줘", "table_id": 5,
                "history": [], "cart": [alcohol],
                "state_token": payload["state_token"],
            })
            changed = self.client.post("/api/chat", json={
                "message": "장바구니 보여줘", "table_id": 5,
                "history": [], "cart": [{**alcohol, "qty": 2}],
                "state_token": payload["state_token"],
            })

        self.assertTrue(restored.json()["cart"]["staff_checked"])
        self.assertFalse(changed.json()["cart"]["staff_checked"])


if __name__ == "__main__":
    unittest.main()
