"""Vercel 진입점과 공개 웹 자산의 회귀 검사."""
from __future__ import annotations

import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.index import _is_alcohol_inquiry, app
from src.cart import CartItem
from src.config import current_api_key, request_api_key
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
        self.assertIn('id="apiKeyModal"', home.text)
        self.assertIn('id="staffVerification"', home.text)
        self.assertIn("default-src 'self'", home.headers["content-security-policy"])
        self.assertEqual(home.headers["referrer-policy"], "no-referrer")
        self.assertEqual(self.client.get("/app.css").status_code, 200)
        script = self.client.get("/app.js")
        self.assertEqual(script.status_code, 200)
        self.assertIn("X-OpenAI-API-Key", script.text)
        self.assertIn("staff_challenge", script.text)
        self.assertIn("staff_authorization", script.text)
        self.assertNotIn("localStorage.setItem('openAIAPIKey'", script.text)
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
        self.assertFalse(payload["requires_staff_verification"])

    def test_request_api_key_is_scoped_to_one_chat_request(self):
        observed_keys = []

        def fake_handle(_message, _store, _cart, _history):
            observed_keys.append(current_api_key())
            return SimpleNamespace(reply="ok", quick_replies=[], docs=[])

        env = {"MOKI_PASSWORD": "", "OPENAI_API_KEY": "", "VERCEL": "1"}
        with patch.dict(os.environ, env, clear=False), \
                patch("api.index.is_mock", return_value=False), \
                patch("api.index.handle", side_effect=fake_handle):
            accepted = self.client.post("/api/chat", json={
                "message": "아메리카노 가격을 알려줘", "table_id": 5,
                "history": [], "cart": [],
            }, headers={"X-OpenAI-API-Key": "sk-request-only"})
            missing_afterward = self.client.post("/api/chat", json={
                "message": "아메리카노 가격을 알려줘", "table_id": 5,
                "history": [], "cart": [],
            })

        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertEqual(observed_keys, ["sk-request-only"])
        self.assertNotIn("sk-request-only", accepted.text)
        self.assertEqual(missing_afterward.status_code, 503)

        oversized_key = "sk-secret-" + ("x" * 512)
        with patch.dict(os.environ, env, clear=False):
            oversized = self.client.post("/api/chat", json={
                "message": "아메리카노 가격을 알려줘", "table_id": 5,
                "history": [], "cart": [],
            }, headers={"X-OpenAI-API-Key": oversized_key})
        self.assertEqual(oversized.status_code, 422)
        self.assertNotIn(oversized_key, oversized.text)

    def test_request_api_keys_are_isolated_between_concurrent_contexts(self):
        barrier = Barrier(2)

        def observe(key):
            with request_api_key(key):
                barrier.wait(timeout=2)
                inside = current_api_key()
            return inside, current_api_key()

        env = {"OPENAI_API_KEY": "", "VERCEL": "1"}
        with patch.dict(os.environ, env, clear=False), \
                ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(observe, ("sk-first", "sk-second")))

        self.assertEqual({inside for inside, _ in results},
                         {"sk-first", "sk-second"})
        self.assertTrue(all(after == "" for _, after in results))

    def test_invalid_api_key_error_is_actionable_without_echoing_secret(self):
        class AuthenticationError(Exception):
            status_code = 401

        secret = "sk-invalid-do-not-echo"
        env = {"MOKI_PASSWORD": "", "OPENAI_API_KEY": "", "VERCEL": "1"}
        with patch.dict(os.environ, env, clear=False), \
                patch("api.index.is_mock", return_value=False), \
                patch("api.index.handle", side_effect=AuthenticationError(secret)):
            response = self.client.post("/api/chat", json={
                "message": "아메리카노 가격을 알려줘", "table_id": 5,
                "history": [], "cart": [],
            }, headers={"X-OpenAI-API-Key": secret})

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "OpenAI API 키를 확인해 주세요.")
        self.assertNotIn(secret, response.text)

    def test_alcohol_questions_require_staff_before_processing(self):
        self.assertFalse(_is_alcohol_inquiry("기술적으로 커피를 추출하는 방법"))
        self.assertFalse(_is_alcohol_inquiry("술래잡기 알아?"))
        self.assertFalse(_is_alcohol_inquiry("성인 2명이 앉을 자리가 있나요?"))
        for message in ("Which wines do you have?", "Any beers?",
                        "Recommend cocktails", "Do you have martinis?"):
            self.assertTrue(_is_alcohol_inquiry(message), message)
        env = {
            "MOKI_PASSWORD": "", "MOKI_STAFF_PASSWORD": "staff-code",
            "MOKI_STATE_SECRET": "test-state-secret-with-32-characters", "OPENAI_API_KEY": "test-key",
        }
        with patch.dict(os.environ, env, clear=False), \
                patch("api.index.handle") as handle_mock:
            by_alias = self.client.post("/api/chat", json={
                "message": "highball 가격이 얼마예요?", "table_id": 5,
                "history": [], "cart": [],
            })
            by_keyword = self.client.post("/api/chat", json={
                "message": "도수가 낮은 메뉴를 알려줘", "table_id": 5,
                "history": [], "cart": [],
            })
            handle_mock.assert_not_called()

        expected = "직원 확인이 필요한 내용입니다. 직원을 부르겠습니다."
        for response in (by_alias, by_keyword):
            self.assertEqual(response.status_code, 200, response.text)
            payload = response.json()
            self.assertEqual(payload["reply"], expected)
            self.assertTrue(payload["requires_staff_verification"])
            self.assertEqual(payload["staff_verification_reason"],
                             "alcohol_inquiry")
            self.assertEqual(payload["sources"], [])
            self.assertTrue(payload["staff_challenge"])

    def test_recent_alcohol_context_cannot_bypass_staff_gate(self):
        env = {
            "MOKI_PASSWORD": "", "MOKI_STAFF_PASSWORD": "staff-code",
            "MOKI_STATE_SECRET": "test-state-secret-with-32-characters",
        }
        with patch.dict(os.environ, env, clear=False), \
                patch("api.index.handle") as handle_mock:
            responses = [self.client.post("/api/chat", json={
                "message": followup, "table_id": 5,
                "history": [{"role": "user", "content": "위스키 종류 알려줘"}],
                "cart": [],
            }) for followup in ("방금 질문에 답해줘", "다시 답해줘", "그래서?")]
            handle_mock.assert_not_called()

        for response in responses:
            self.assertEqual(response.status_code, 200, response.text)
            self.assertTrue(response.json()["requires_staff_verification"])

        with patch.dict(os.environ, env, clear=False), \
                patch("api.index.is_mock", return_value=True), \
                patch("api.index.handle", return_value=SimpleNamespace(
                    reply="아메리카노 안내입니다.", quick_replies=[], docs=[])):
            changed_topic = self.client.post("/api/chat", json={
                "message": "아메리카노 가격 알려줘", "table_id": 5,
                "history": [
                    {"role": "user", "content": "위스키 종류 알려줘"},
                    {"role": "assistant", "content": "직원 확인 후 안내해 드렸습니다."},
                ],
                "cart": [],
            })

        self.assertEqual(changed_topic.status_code, 200, changed_topic.text)
        self.assertFalse(changed_topic.json()["requires_staff_verification"])

    def test_alcohol_rag_result_is_hidden_until_staff_verifies(self):
        env = {
            "MOKI_PASSWORD": "", "MOKI_STAFF_PASSWORD": "staff-code",
            "MOKI_STATE_SECRET": "test-state-secret-with-32-characters", "OPENAI_API_KEY": "test-key",
        }
        alcohol_doc = SimpleNamespace(metadata={
            "id": "M36", "entity_id": "M36", "type": "menu",
        })
        result = SimpleNamespace(
            reply="위스키 하이볼이 있습니다.", quick_replies=[], docs=[alcohol_doc])
        with patch.dict(os.environ, env, clear=False), \
                patch("api.index.is_mock", return_value=False), \
                patch("api.index.handle", return_value=result) as handle_mock:
            response = self.client.post("/api/chat", json={
                "message": "저녁에 어울리는 어른용 음료 추천해줘", "table_id": 5,
                "history": [], "cart": [],
            })

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(handle_mock.call_count, 1)
        payload = response.json()
        self.assertTrue(payload["requires_staff_verification"])
        self.assertNotIn("위스키 하이볼이 있습니다", response.text)
        self.assertEqual(payload["cart"]["items"], [])

    def test_empty_cart_alcohol_inquiry_can_be_verified_and_retried(self):
        env = {
            "MOKI_PASSWORD": "", "MOKI_STAFF_PASSWORD": "staff-code",
            "MOKI_STATE_SECRET": "test-state-secret-with-32-characters",
        }
        with patch.dict(os.environ, env, clear=False):
            gate = self.client.post("/api/chat", json={
                "message": "위스키 하이볼 가격 알려줘", "table_id": 5,
                "history": [], "cart": [],
            })
            challenge = gate.json()["staff_challenge"]
            with patch("api.index.time.time", return_value=10**12):
                expired = self.client.post("/api/staff/verify", json={
                    "table_id": 5, "cart": [], "staff_challenge": challenge,
                }, headers={"X-Moki-Staff-Password": "staff-code"})
            verified = self.client.post("/api/staff/verify", json={
                "table_id": 5, "cart": [], "staff_challenge": challenge,
            }, headers={"X-Moki-Staff-Password": "staff-code"})
            rejected_without_challenge = self.client.post("/api/staff/verify", json={
                "table_id": 5, "cart": [], "reason": "alcohol_inquiry",
            }, headers={"X-Moki-Staff-Password": "staff-code"})

        self.assertEqual(verified.status_code, 200, verified.text)
        token = verified.json()["state_token"]
        authorization = verified.json()["staff_authorization"]
        self.assertTrue(token)
        self.assertTrue(authorization)
        self.assertFalse(verified.json()["cart"]["staff_checked"])
        self.assertEqual(expired.status_code, 410)
        self.assertEqual(rejected_without_challenge.status_code, 410)

        with patch.dict(os.environ, env, clear=False), \
                patch("api.index.is_mock", return_value=True), \
                patch("src.router.is_mock", return_value=True), \
                patch("src.chain.is_mock", return_value=True), \
                patch("src.kiosk.is_mock", return_value=True):
            retried = self.client.post("/api/chat", json={
                "message": "위스키 하이볼 가격 알려줘", "table_id": 5,
                "history": [], "cart": [], "state_token": token,
                "staff_authorization": authorization,
            })

        self.assertEqual(retried.status_code, 200, retried.text)
        payload = retried.json()
        self.assertFalse(payload["requires_staff_verification"])
        self.assertFalse(payload["cart"]["staff_checked"])
        self.assertNotEqual(
            payload["reply"],
            "직원 확인이 필요한 내용입니다. 직원을 부르겠습니다.",
        )

    def test_verified_alcohol_add_retries_once_without_duplicate_or_regate(self):
        env = {
            "MOKI_PASSWORD": "", "MOKI_STAFF_PASSWORD": "staff-code",
            "MOKI_STATE_SECRET": "test-state-secret-with-32-characters", "OPENAI_API_KEY": "test-key",
        }
        request_body = {
            "message": "위스키 하이볼 한 잔 담아줘", "table_id": 5,
            "history": [], "cart": [],
        }
        calls = []

        def add_one(_message, _store, cart, _history):
            calls.append(1)
            cart.add(CartItem(
                menu_id="M36", variant_id="M36-ICED-ONE",
                name="모키 위스키 하이볼", temp="ICED", size="ONE",
                is_alcohol=True,
            ))
            return SimpleNamespace(reply="한 잔 담았습니다.", quick_replies=[], docs=[])

        with patch.dict(os.environ, env, clear=False), \
                patch("api.index.is_mock", return_value=False), \
                patch("api.index.handle", side_effect=add_one):
            gate = self.client.post("/api/chat", json=request_body)
            challenge = gate.json()["staff_challenge"]
            verified = self.client.post("/api/staff/verify", json={
                "table_id": 5, "cart": [], "state_token": gate.json()["state_token"],
                "staff_challenge": challenge,
            }, headers={"X-Moki-Staff-Password": "staff-code"})
            scope_mismatch = self.client.post("/api/chat", json={
                **request_body,
                "message": "위스키 하이볼 두 잔 담아줘",
                "state_token": verified.json()["state_token"],
                "staff_authorization": verified.json()["staff_authorization"],
            })
            retried = self.client.post("/api/chat", json={
                **request_body,
                "state_token": verified.json()["state_token"],
                "staff_authorization": verified.json()["staff_authorization"],
            })

        self.assertEqual(gate.status_code, 200, gate.text)
        self.assertEqual(verified.status_code, 200, verified.text)
        self.assertTrue(scope_mismatch.json()["requires_staff_verification"])
        self.assertEqual(retried.status_code, 200, retried.text)
        payload = retried.json()
        self.assertFalse(payload["requires_staff_verification"])
        self.assertEqual(len(payload["cart"]["items"]), 1)
        self.assertTrue(payload["cart"]["staff_checked"])
        self.assertEqual(len(calls), 1)

    def test_client_cannot_forge_order_or_staff_state(self):
        alcohol = {
            "menu_id": "M36", "variant_id": "M36-ICED-ONE", "qty": 1,
            "bean": None, "extra_shots": 0, "milk": None,
            "sweetness": None, "ice": None, "warming": None,
        }
        env = {"MOKI_PASSWORD": "", "MOKI_STATE_SECRET": "test-state-secret-with-32-characters"}
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
            "MOKI_STATE_SECRET": "test-state-secret-with-32-characters",
        }
        with patch.dict(os.environ, env, clear=False):
            gate = self.client.post("/api/chat", json={
                "message": "장바구니 보여줘", "table_id": 5,
                "history": [], "cart": [alcohol],
            })
            challenge = gate.json()["staff_challenge"]
            rejected = self.client.post("/api/staff/verify", json={
                "table_id": 5, "cart": [alcohol],
                "staff_challenge": challenge,
            }, headers={"X-Moki-Staff-Password": "wrong"})
            verified = self.client.post("/api/staff/verify", json={
                "table_id": 5, "cart": [alcohol],
                "staff_challenge": challenge,
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

    def test_staff_verification_requires_a_separate_strong_state_secret(self):
        env = {
            "MOKI_PASSWORD": "", "MOKI_STAFF_PASSWORD": "staff-code",
            "MOKI_STATE_SECRET": "short",
        }
        with patch.dict(os.environ, env, clear=False):
            response = self.client.post("/api/staff/verify", json={
                "table_id": 5, "cart": [], "staff_challenge": "invalid",
            }, headers={"X-Moki-Staff-Password": "staff-code"})

        self.assertEqual(response.status_code, 503)
        self.assertIn("32자 이상", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
