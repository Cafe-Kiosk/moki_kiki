"""Static browser-contract checks for the compound option-review queue."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parent.parent


class FrontendCompoundOrderContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = (ROOT / "public" / "app.js").read_text(encoding="utf-8")
        cls.styles = (ROOT / "public" / "app.css").read_text(encoding="utf-8")
        cls.markup = (ROOT / "public" / "index.html").read_text(encoding="utf-8")

    def test_deferred_batch_is_the_only_visible_action_and_runs_in_order(self):
        start = self.script.index("function renderQuickReplies()")
        end = self.script.index("function renderStaffRetryButton()", start)
        render = self.script[start:end]

        self.assertIn("if (state.deferredItems.length)", render)
        self.assertIn("const proposal = state.deferredItems[0]", render)
        self.assertIn("batchProgress", render)
        self.assertIn("cancelDeferredBatch", render)
        self.assertLess(render.index("return;"), render.index("state.quickReplies.forEach"))
        self.assertNotIn("state.deferredItems.forEach", render)
        self.assertIn(".deferred-progress", self.styles)

    def test_new_chat_cannot_replace_a_pending_batch(self):
        start = self.script.index("async function sendMessage")
        end = self.script.index("async function retryPendingStaffRequest", start)
        send = self.script[start:end]

        queue_guard = send.index("if (state.deferredItems.length)")
        network_request = send.index("fetch('/api/chat'")
        self.assertLess(queue_guard, network_request)
        self.assertIn("announce(tr('batchPending'))", send)
        self.assertIn("setResponseChoices(", send)

    def test_queue_identity_progress_and_reload_state_are_preserved(self):
        self.assertIn("proposal.proposal_id = suppliedId ||", self.script)
        self.assertIn("return proposalId ? `id:${proposalId}`", self.script)
        self.assertIn("state.deferredBatch.completed += 1", self.script)
        self.assertIn("deferredItems: state.deferredItems", self.script)
        self.assertIn("deferredBatch: state.deferredBatch", self.script)
        self.assertIn(
            "state.deferredItems = current ? normalizeDeferredItems(saved.deferredItems) : []",
            self.script,
        )
        self.assertIn("state.deferredItems = normalizeDeferredItems(state.deferredItems)", self.script)

    def test_completed_actions_and_pairing_cannot_duplicate_the_batch(self):
        start = self.script.index("function setResponseChoices")
        end = self.script.index("function cancelDeferredBatch", start)
        choices = self.script[start:end]

        self.assertIn("state.quickReplies = []", choices)
        self.assertIn("state.menuActions = []", choices)
        self.assertIn("const pairingExclusions = new Set", self.script)
        self.assertIn("state.deferredBatch.menuIds", self.script)
        self.assertIn("...state.pairingTrail", self.script)
        self.assertIn("closeOptionDialog()", self.script)

    def test_staff_authorization_survives_options_and_is_consumed_by_alcohol_add(self):
        cart_start = self.script.index("async function cartAction")
        cart_end = self.script.index("async function submitOption", cart_start)
        cart_action = self.script[cart_start:cart_end]
        send_start = self.script.index("async function sendMessage")
        send_end = self.script.index("async function retryPendingStaffRequest", send_start)
        send = self.script[send_start:send_end]

        self.assertIn("cartActionNeedsAlcoholApproval(action, fields)", cart_action)
        self.assertIn("staff_authorization: staffAuthorization", cart_action)
        self.assertIn("if (staffAuthorization || state.staffVerificationRequired)", cart_action)
        self.assertIn("data.staff_authorization || options.staffAuthorization", send)
        self.assertIn("Boolean(data.staff_authorization)", send)
        self.assertIn("hasAuthorizedMenuSelection", send)
        self.assertIn("revealStaffVerification()", send)
        self.assertIn("staffCodeChatPrompt", send)

    def test_staff_code_appears_as_a_blocking_modal_when_alcohol_needs_approval(self):
        self.assertIn(
            '<dialog class="modal staff-code-modal" id="staffCodeModal"',
            self.markup,
        )
        self.assertIn('id="staffCodeInput"', self.markup)
        self.assertIn('id="staffVerifyButton"', self.markup)
        self.assertIn("openDialog($('#staffCodeModal'))", self.script)
        self.assertIn("closeDialog($('#staffCodeModal'))", self.script)
        self.assertIn("if (state.staffVerificationRequired) { revealStaffVerification(); return; }", self.script)
        self.assertIn("$('#staffCodeModal').addEventListener('cancel'", self.script)
        self.assertIn(".staff-code-card input", self.styles)

    def test_checkout_opens_from_chat_and_keeps_a_localized_detailed_receipt(self):
        send_start = self.script.index("async function sendMessage")
        send_end = self.script.index("async function retryPendingStaffRequest", send_start)
        send = self.script[send_start:send_end]
        self.assertLess(
            send.index("else if (data.open_order_form)"),
            send.index("else if (data.open_option_menu_id)"),
        )

        for element_id in (
            "benefitBeforeAmount", "benefitDiscountAmount", "benefitAfterAmount",
            "receiptCallout", "receiptItems", "receiptTable", "receiptBeforeDiscount",
            "receiptDiscount", "receiptPaidAmount", "receiptPaymentMethod",
            "receiptChoice", "receiptBenefitApplied", "orderNumber",
        ):
            self.assertIn(f'id="{element_id}"', self.markup)
        self.assertIn("function renderCheckoutReceipt", self.script)
        self.assertIn("items: state.cart.map", self.script)
        self.assertIn("lastCheckout: state.lastCheckout", self.script)
        self.assertIn("normalizeCheckoutReceipt(saved.lastCheckout)", self.script)
        self.assertIn("tr('receiptCallout'", self.script)
        self.assertGreaterEqual(self.script.count("receiptCallout:"), 4)
        self.assertIn(".receipt-item-line", self.styles)

    def test_checkout_benefits_are_explicitly_unsupported_and_discount_is_zero(self):
        review_start = self.script.index("function renderCheckoutReview")
        review_end = self.script.index("function normalizeCheckoutReceipt", review_start)
        review = self.script[review_start:review_end]
        self.assertIn("$('#benefitDiscountAmount').textContent = won(0)", review)
        self.assertIn("noLinkedBenefits", self.markup)
        self.assertNotIn("MOKI1234", self.script + self.markup)
        self.assertNotIn("demo_member_10", self.script + self.markup)


if __name__ == "__main__":
    unittest.main()
