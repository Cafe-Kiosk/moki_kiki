"""Vercel에서 실행되는 모키 커피바 FastAPI 앱."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from src.cart import (BEAN_SURCHARGE, MILK_SURCHARGE, OPTION_MENUS, SHOT_PRICE,
                      Cart, CartItem, find_variants, list_menus, menu_by_id,
                      resolve_variant, validate_item_options, variant_by_id)
from src.config import (STAFF_VERIFICATION_CODE, TABLES, ensure_api_key,
                        is_mock, request_api_key, request_language)
from src.content import content_status, menu_image_cards, source_cards
from src.kiosk import handle
from src.lexical_store import LexicalStore

ROOT = Path(__file__).resolve().parent.parent
PUBLIC_DIR = ROOT / "public"

app = FastAPI(
    title="Moki Coffee Bar",
    version="1.0.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)


@app.middleware("http")
async def add_security_headers(request, call_next):
    """브라우저 메모리의 요청 키가 다른 출처로 새지 않도록 경계를 좁힌다."""
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' https://fonts.googleapis.com; "
        "font-src https://fonts.gstatic.com; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "object-src 'none'; base-uri 'self'; form-action 'self'; "
        "frame-ancestors 'none'"
    )
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Permissions-Policy"] = (
        "camera=(), microphone=(), geolocation=()")
    if request.url.path in {
        "/api/chat", "/api/cart/action", "/api/order/confirm", "/api/staff/verify",
    }:
        response.headers["Cache-Control"] = "no-store"
    return response


class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class CartLine(BaseModel):
    menu_id: str
    variant_id: str
    qty: int = Field(default=1, ge=1, le=10)
    bean: str | None = None
    extra_shots: int = Field(default=0, ge=0, le=2)
    milk: str | None = None
    sweetness: str | None = None
    ice: str | None = None
    warming: str | None = None


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    table_id: int = Field(default=5, ge=min(TABLES), le=max(TABLES))
    history: list[HistoryMessage] = Field(default_factory=list, max_length=8)
    cart: list[CartLine] = Field(default_factory=list, max_length=30)
    state_token: str | None = Field(default=None, max_length=2048)
    staff_authorization: str | None = Field(default=None, max_length=2048)
    language: Literal["ko", "en", "zh", "ja"] = "ko"
    # 웹은 메뉴를 곧바로 담지 않고 한 화면 옵션 검토로 넘긴다.
    # 이전 Streamlit/테스트 호출자는 생략해 기존 대화 주문 흐름을 유지한다.
    defer_cart_add: bool = False


class CartActionRequest(BaseModel):
    action: Literal["add", "replace", "remove", "set_qty"]
    table_id: int = Field(default=5, ge=min(TABLES), le=max(TABLES))
    cart: list[CartLine] = Field(default_factory=list, max_length=30)
    state_token: str | None = Field(default=None, max_length=2048)
    # A short, signed authorization returned after the staff code succeeds.
    # It is bound to this exact table/cart snapshot and is consumed by the
    # first subsequent alcohol increase in the browser option flow.
    staff_authorization: str | None = Field(default=None, max_length=2048)
    item: CartLine | None = None
    index: int | None = Field(default=None, ge=0, le=29)
    quantity: int | None = Field(default=None, ge=1, le=10)
    language: Literal["ko", "en", "zh", "ja"] = "ko"


class CheckoutRequest(BaseModel):
    table_id: int = Field(default=5, ge=min(TABLES), le=max(TABLES))
    cart: list[CartLine] = Field(default_factory=list, min_length=1, max_length=30)
    state_token: str | None = Field(default=None, max_length=2048)
    service_mode: Literal["dine_in", "takeout"]
    cup: Literal["store", "personal", "disposable"]
    supplies: list[Literal["carrier", "straw"]] = Field(default_factory=list, max_length=2)
    payment_method: Literal["card", "mobile", "gifticon"]
    split_mode: Literal["none", "by_item", "equal"] = "none"
    split_count: int = Field(default=1, ge=1, le=10)
    receipt: Literal["paper", "digital", "none"] = "none"
    language: Literal["ko", "en", "zh", "ja"] = "ko"


class StaffVerifyRequest(BaseModel):
    table_id: int = Field(default=5, ge=min(TABLES), le=max(TABLES))
    cart: list[CartLine] = Field(default_factory=list, max_length=30)
    state_token: str | None = Field(default=None, max_length=2048)
    staff_challenge: str | None = Field(default=None, max_length=2048)
    # 이전 클라이언트와의 요청 형식 호환용이다. 이 값만으로는 승인하지 않는다.
    reason: Literal["alcohol_purchase", "alcohol_inquiry"] | None = None
    language: Literal["ko", "en", "zh", "ja"] = "ko"


@lru_cache(maxsize=1)
def get_store() -> LexicalStore:
    return LexicalStore()


API_TEXTS = {
    "api_key_too_long": {
        "ko": "API 키가 너무 깁니다.",
        "en": "The API key is too long.",
        "zh": "API 密钥过长。",
        "ja": "API キーが長すぎます。",
    },
    "api_key_required": {
        "ko": "OPENAI_API_KEY 환경변수를 설정하거나 현재 요청에 API 키를 입력해 주세요.",
        "en": "Set OPENAI_API_KEY or enter an API key for this request.",
        "zh": "请设置 OPENAI_API_KEY 环境变量，或为本次请求输入 API 密钥。",
        "ja": "OPENAI_API_KEY を設定するか、このリクエスト用の API キーを入力してください。",
    },
    "api_key_invalid": {
        "ko": "OpenAI API 키를 확인해 주세요.",
        "en": "Please check the OpenAI API key.",
        "zh": "请检查 OpenAI API 密钥。",
        "ja": "OpenAI API キーを確認してください。",
    },
    "answer_failed": {
        "ko": "모키가 답변을 준비하지 못했습니다. 잠시 후 다시 시도해 주세요.",
        "en": "Moki could not prepare an answer. Please try again shortly.",
        "zh": "Moki 暂时无法准备回答，请稍后重试。",
        "ja": "モキが回答を用意できませんでした。しばらくしてからもう一度お試しください。",
    },
    "staff_code": {
        "ko": "직원 확인 코드를 확인해 주세요.",
        "en": "Please check the staff verification code.",
        "zh": "请检查员工确认码。",
        "ja": "スタッフ確認コードを確認してください。",
    },
    "cart_confirmed": {
        "ko": "이미 확정한 주문은 변경할 수 없습니다. 새 주문을 시작한 뒤 메뉴를 담아 주세요.",
        "en": "A confirmed order cannot be changed. Start a new order before adding items.",
        "zh": "已确认的订单无法修改。请开始新订单后再添加商品。",
        "ja": "確定済みの注文は変更できません。新しい注文を開始してから商品を追加してください。",
    },
    "cart_index": {
        "ko": "변경할 장바구니 항목을 다시 확인해 주세요.",
        "en": "Please check which cart item you want to change.",
        "zh": "请确认要修改的购物车商品。",
        "ja": "変更するカートの商品を確認してください。",
    },
    "cart_add_item": {
        "ko": "담을 메뉴 정보를 다시 확인해 주세요.",
        "en": "Please check the item you want to add.",
        "zh": "请确认要添加的商品信息。",
        "ja": "追加する商品の情報を確認してください。",
    },
    "cart_replace_item": {
        "ko": "변경할 메뉴 정보를 다시 확인해 주세요.",
        "en": "Please check the item you want to edit.",
        "zh": "请确认要修改的商品信息。",
        "ja": "変更する商品の情報を確認してください。",
    },
    "cart_same_menu": {
        "ko": "옵션 변경에서는 같은 메뉴만 선택할 수 있습니다.",
        "en": "Only options for the same menu item can be edited here.",
        "zh": "此处只能修改同一商品的选项。",
        "ja": "ここでは同じメニューのオプションのみ変更できます。",
    },
    "cart_quantity": {
        "ko": "변경할 수량을 확인해 주세요.",
        "en": "Please check the quantity.",
        "zh": "请确认数量。",
        "ja": "数量を確認してください。",
    },
    "alcohol_staff": {
        "ko": "주류 구매는 직원 확인을 먼저 완료해 주세요.",
        "en": "Complete staff verification before purchasing alcohol.",
        "zh": "购买酒类前请先完成员工确认。",
        "ja": "酒類を購入する前にスタッフ確認を完了してください。",
    },
    "alcohol_dine_in": {
        "ko": "주류는 매장 이용만 가능합니다.",
        "en": "Alcohol is available for dine-in only.",
        "zh": "酒类仅限店内饮用。",
        "ja": "酒類は店内利用のみです。",
    },
    "cup_mode": {
        "ko": "이용 방식에 맞는 컵을 선택해 주세요.",
        "en": "Choose a cup that matches the service mode.",
        "zh": "请选择符合用餐方式的杯具。",
        "ja": "利用方法に合ったカップを選んでください。",
    },
    "carrier_takeout": {
        "ko": "캐리어는 포장 주문에서 선택해 주세요.",
        "en": "A drink carrier can be selected for takeout orders.",
        "zh": "饮料托架仅可用于外带订单。",
        "ja": "ドリンクキャリアはテイクアウト注文で選択してください。",
    },
    "equal_split_min": {
        "ko": "나눠 결제할 인원을 2명 이상으로 선택해 주세요.",
        "en": "Choose at least two people for an equal split.",
        "zh": "平均分摊时请选择至少 2 人。",
        "ja": "均等割りでは2人以上を選んでください。",
    },
    "split_count_equal": {
        "ko": "N분의 1 결제에서만 나눌 인원 수를 선택할 수 있습니다.",
        "en": "The number of people is used only for an equal split.",
        "zh": "仅平均分摊时可以选择人数。",
        "ja": "人数は均等割りの場合のみ選択できます。",
    },
    "challenge_expired": {
        "ko": "직원 확인 요청이 없거나 만료되었습니다. 주류 구매를 다시 요청해 주세요.",
        "en": "The staff verification request is missing or expired. Please request the alcohol purchase again.",
        "zh": "员工确认请求不存在或已过期。请重新发起酒类购买。",
        "ja": "スタッフ確認リクエストがないか期限切れです。酒類の購入をもう一度行ってください。",
    },
}


def _api_text(language: str, key: str) -> str:
    messages = API_TEXTS[key]
    return messages.get(language, messages["ko"])


def _require_staff_code(code: str | None, language: str = "ko") -> None:
    if not secrets.compare_digest(code or "", STAFF_VERIFICATION_CODE):
        raise HTTPException(status_code=401, detail=_api_text(language, "staff_code"))


def _staff_scope(request: ChatRequest) -> str:
    """직원 승인을 정확히 같은 한 번의 대화 요청에 묶는다."""
    payload = {
        "message": request.message.strip(),
        "history": [message.model_dump() for message in request.history],
    }
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _cart_fingerprint(cart: Cart) -> str:
    lines = [{
        "menu_id": item.menu_id,
        "variant_id": item.variant_id,
        "qty": item.qty,
        "bean": item.bean,
        "extra_shots": item.extra_shots,
        "milk": item.milk,
        "sweetness": item.sweetness,
        "ice": item.ice,
        "warming": item.warming,
    } for item in cart.items]
    canonical = json.dumps(lines, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _alcohol_quantities(cart: Cart) -> dict[tuple, int]:
    """주류 종류·구성별 수량을 합쳐 새 구매가 늘었는지 비교할 수 있게 한다."""
    quantities: dict[tuple, int] = {}
    for item in cart.items:
        if not item.is_alcohol:
            continue
        key = (
            item.menu_id, item.variant_id, item.bean, item.extra_shots,
            item.milk, item.sweetness, item.ice, item.warming,
        )
        quantities[key] = quantities.get(key, 0) + item.qty
    return quantities


def _adds_alcohol(original: Cart, updated: Cart) -> bool:
    """새 주류 종류 추가 또는 기존 주류 수량 증가만 구매 확대로 본다."""
    before = _alcohol_quantities(original)
    return any(
        quantity > before.get(key, 0)
        for key, quantity in _alcohol_quantities(updated).items()
    )


def _state_secret() -> bytes | None:
    value = os.getenv("MOKI_STATE_SECRET", "").strip()
    return value.encode("utf-8") if len(value) >= 32 else None


def _require_state_secret() -> None:
    if not _state_secret():
        raise HTTPException(
            status_code=503,
            detail=("Vercel 환경변수 MOKI_STATE_SECRET에 32자 이상의 "
                    "무작위 값을 설정해 주세요."),
        )


def _sign_payload(payload: dict) -> str | None:
    secret = _state_secret()
    if not secret:
        return None
    encoded = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ).decode("ascii").rstrip("=")
    signature = hmac.new(secret, encoded.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{encoded}.{signature}"


def _read_signed_payload(token: str | None, purpose: str) -> dict | None:
    secret = _state_secret()
    if not secret or not token:
        return None
    try:
        encoded, signature = token.split(".", 1)
        expected = hmac.new(secret, encoded.encode("ascii"), hashlib.sha256).hexdigest()
        if not secrets.compare_digest(signature, expected):
            return None
        padded = encoded + "=" * (-len(encoded) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
        if (payload.get("v") != 1 or payload.get("purpose") != purpose
                or int(payload.get("exp", 0)) < int(time.time())):
            return None
        return payload
    except (ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def _issue_state_token(cart: Cart) -> str | None:
    return _sign_payload({
        "v": 1,
        "purpose": "cart_state",
        "table_id": cart.table_id,
        "cart": _cart_fingerprint(cart),
        "order_no": cart.order_no,
        "staff_checked": cart.staff_checked,
        "exp": int(time.time()) + 8 * 60 * 60,
    })


def _restore_signed_state(cart: Cart, token: str | None) -> None:
    payload = _read_signed_payload(token, "cart_state")
    if not payload:
        return
    try:
        if payload.get("table_id") != cart.table_id:
            return
        if payload.get("cart") != _cart_fingerprint(cart):
            return
        order_no = payload.get("order_no")
        if order_no is None or re.fullmatch(r"M\d{4}", str(order_no)):
            cart.order_no = order_no
        cart.staff_checked = bool(payload.get("staff_checked", False))
    except (ValueError, TypeError):
        return


def _issue_staff_challenge(
    cart: Cart,
    scope: str,
    *,
    authorization_mode: str = "none",
    allowed_cart_fingerprints: list[str] | None = None,
    allowed_menu_ids: list[str] | None = None,
) -> str | None:
    return _sign_payload({
        "v": 1,
        "purpose": "staff_challenge",
        "table_id": cart.table_id,
        "cart": _cart_fingerprint(cart),
        "scope": scope,
        "authorization_mode": authorization_mode,
        "allowed_cart_fingerprints": allowed_cart_fingerprints or [],
        "allowed_menu_ids": allowed_menu_ids or [],
        "exp": int(time.time()) + 5 * 60,
    })


def _challenge_payload(token: str | None, cart: Cart) -> dict | None:
    payload = _read_signed_payload(token, "staff_challenge")
    if not payload:
        return None
    scope = str(payload.get("scope", ""))
    if (payload.get("table_id") != cart.table_id
            or payload.get("cart") != _cart_fingerprint(cart)
            or not re.fullmatch(r"[0-9a-f]{64}", scope)):
        return None
    return payload


def _challenge_scope(token: str | None, cart: Cart) -> str | None:
    payload = _challenge_payload(token, cart)
    return str(payload["scope"]) if payload else None


def _issue_staff_authorization(
    cart: Cart,
    scope: str,
    *,
    authorization_mode: str = "none",
    allowed_cart_fingerprints: list[str] | None = None,
    allowed_menu_ids: list[str] | None = None,
) -> str | None:
    return _sign_payload({
        "v": 1,
        "purpose": "staff_authorization",
        "table_id": cart.table_id,
        "cart": _cart_fingerprint(cart),
        "scope": scope,
        "authorization_mode": authorization_mode,
        "allowed_cart_fingerprints": allowed_cart_fingerprints or [],
        "allowed_menu_ids": allowed_menu_ids or [],
        "exp": int(time.time()) + 5 * 60,
    })


def _has_staff_authorization(token: str | None, cart: Cart, scope: str) -> bool:
    payload = _read_signed_payload(token, "staff_authorization")
    return bool(
        payload
        and payload.get("table_id") == cart.table_id
        and payload.get("cart") == _cart_fingerprint(cart)
        and secrets.compare_digest(str(payload.get("scope", "")), scope)
    )


def _has_staff_preapproval(
    token: str | None,
    cart: Cart,
    updated: Cart,
) -> bool:
    """Allow one option-screen alcohol add after a verified chat request.

    The token is still bound to the signed table and the exact pre-add cart
    fingerprint.  Once an item is added, that fingerprint changes, so the same
    authorization cannot approve a later quantity/type increase.
    """
    payload = _read_signed_payload(token, "staff_authorization")
    if not (
        payload
        and payload.get("table_id") == cart.table_id
        and payload.get("cart") == _cart_fingerprint(cart)
        and re.fullmatch(r"[0-9a-f]{64}", str(payload.get("scope", "")))
    ):
        return False
    mode = str(payload.get("authorization_mode", "none"))
    if mode == "exact":
        allowed = payload.get("allowed_cart_fingerprints") or []
        return (
            len(allowed) <= 10
            and all(re.fullmatch(r"[0-9a-f]{64}", str(value)) for value in allowed)
            and _cart_fingerprint(updated) in allowed
        )
    if mode == "generic_one_alcohol_line":
        before = _alcohol_quantities(cart)
        increased = [
            key for key, quantity in _alcohol_quantities(updated).items()
            if quantity > before.get(key, 0)
        ]
        return len(increased) == 1
    if mode == "menu_ids_one_alcohol_line":
        allowed = payload.get("allowed_menu_ids") or []
        if not (
            len(allowed) <= 10
            and all(re.fullmatch(r"M\d{2}", str(value)) for value in allowed)
            and all(
                (row := menu_by_id(str(value)))
                and str(row.get("주류 구분", "")).startswith("주류 포함")
                for value in allowed
            )
        ):
            return False
        before = _alcohol_quantities(cart)
        increased = [
            key for key, quantity in _alcohol_quantities(updated).items()
            if quantity > before.get(key, 0)
        ]
        return len(increased) == 1 and increased[0][0] in allowed
    return False


def _cart_item_from_line(line: CartLine) -> CartItem:
    menu = menu_by_id(line.menu_id)
    variant = variant_by_id(line.variant_id)
    if not menu or not variant or not line.variant_id.startswith(line.menu_id + "-"):
        raise HTTPException(status_code=422, detail="장바구니 메뉴 정보를 다시 확인해 주세요.")
    item = CartItem(
        menu_id=line.menu_id,
        variant_id=line.variant_id,
        name=str(menu["메뉴명"]),
        temp=str(variant.get("온도")),
        size=str(variant.get("크기")),
        qty=line.qty,
        bean=line.bean,
        extra_shots=line.extra_shots,
        milk=line.milk,
        sweetness=line.sweetness,
        ice=line.ice,
        warming=line.warming,
        is_alcohol=str(menu.get("주류 구분", "")).startswith("주류 포함"),
    )
    valid, error = validate_item_options(item)
    if not valid:
        raise HTTPException(status_code=422, detail=error)
    return item


def _restore_cart(table_id: int, lines: list[CartLine], state_token: str | None) -> Cart:
    cart = Cart(table_id=table_id)
    for line in lines:
        item = _cart_item_from_line(line)
        added, error = cart.add(item)
        if not added:
            raise HTTPException(status_code=422, detail=error)
    _restore_signed_state(cart, state_token)
    return cart


def _cart_payload(cart: Cart) -> dict:
    return {
        "table_id": cart.table_id,
        "items": [
            {
                "line_id": str(index),
                "menu_id": item.menu_id,
                "variant_id": item.variant_id,
                "name": item.name,
                "image": f"/assets/menu/{item.menu_id}.jpg",
                "temp": item.temp,
                "size": item.size,
                "qty": item.qty,
                "bean": item.bean,
                "extra_shots": item.extra_shots,
                "milk": item.milk,
                "sweetness": item.sweetness,
                "ice": item.ice,
                "warming": item.warming,
                "option_text": item.option_text(),
                "unit_price": item.unit_price,
                "subtotal": item.subtotal,
                "is_alcohol": item.is_alcohol,
            }
            for index, item in enumerate(cart.items)
        ],
        "total": cart.total,
        "status": cart.status(),
        "order_no": cart.order_no,
        "staff_checked": cart.staff_checked,
    }


def _order_form_metadata() -> dict:
    """프런트가 HTI E/F 선택지를 서버 계약과 동일하게 그리도록 한다.

    결제·회원 계정과 연결되지 않은 수업용 프로토타입이라는 사실도 같은
    응답에 넣어, 화면이 실제 승인·적립을 했다고 오해시키지 않게 한다.
    """
    return {
        "simulated": True,
        "currency": "KRW",
        "service_modes": ["dine_in", "takeout"],
        "cup_options": {
            "dine_in": ["store", "personal"],
            "takeout": ["personal", "disposable"],
        },
        "supply_options": ["carrier", "straw"],
        "payment_methods": ["card", "mobile", "gifticon"],
        "split_modes": ["none", "by_item", "equal"],
        "receipt_options": ["paper", "digital", "none"],
        "membership": {
            "lookup_supported": False,
            "connected": False,
            "benefits_available": False,
            "message": "시연에서는 회원 계정 조회·연결을 지원하지 않습니다.",
        },
        "discounts": {
            "selection_supported": False,
            "account_connected": False,
            "benefits_available": False,
            "coupon_available": False,
            "points_available": False,
            "discount_amount": 0,
            "points_to_earn": 0,
            "options": [{
                "id": "none",
                "label": "적용 가능한 할인 없음",
                "amount": 0,
            }],
        },
        "constraints": {
            "alcohol_service_mode": "dine_in",
            "equal_split_min_people": 2,
            "equal_split_max_people": 10,
            "carrier_service_mode": "takeout",
        },
        "external_payment_performed": False,
        "store_order_submitted": False,
        "retry_supported": True,
    }


def _menu_actions(
    documents,
    menu_images=None,
    menu_ids=None,
    limit: int = 3,
) -> list[dict]:
    """검색 근거 중 실제 판매 메뉴만 옵션 선택 버튼으로 노출한다."""
    candidates: list[str] = [str(menu_id) for menu_id in (menu_ids or [])]
    for card in menu_images or []:
        candidates.append(str(card.get("id") or card.get("menu_id") or ""))
    for document in documents or []:
        metadata = getattr(document, "metadata", {}) or {}
        if str(metadata.get("type") or "").casefold() not in {"menu", "메뉴"}:
            continue
        candidates.append(str(
            metadata.get("entity_id")
            or metadata.get("menu_id")
            or metadata.get("id")
            or ""
        ).split(":", 1)[0])

    cards: list[dict] = []
    seen: set[str] = set()
    for raw_menu_id in candidates:
        menu_id = raw_menu_id.strip().upper()
        if menu_id in seen:
            continue
        row = menu_by_id(menu_id)
        if not row:
            continue
        seen.add(menu_id)
        cards.append({
            "id": menu_id,
            "menu_id": menu_id,
            "name": str(row["메뉴명"]),
            "image": f"/assets/menu/{menu_id}.jpg",
            "is_alcohol": str(row.get("주류 구분", "")).startswith("주류 포함"),
        })
        if len(cards) >= max(0, min(limit, 3)):
            break
    return cards


def _cart_line_payload(item: CartItem) -> dict:
    """검증된 제안 항목을 옵션 화면이 재사용할 수 있는 형태로 만든다."""
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


def _deferred_cart_reply(language: str, count: int) -> str:
    singular = count == 1
    return {
        "ko": ("장바구니에 담기 전에 메뉴 구성과 옵션을 한 화면에서 확인해 주세요. "
               "바꿀 옵션이 없으면 기본값 그대로 바로 담을 수 있어요."),
        "en": ("Review the menu setup and options on one screen before adding "
               f"{'it' if singular else 'them'} to the cart. Keep the defaults to skip changes."),
        "zh": "加入购物车前，请在同一画面确认菜单配置和选项。如无需修改，可保留默认值直接加入。",
        "ja": ("カートに入れる前に、メニュー構成とオプションを1つの画面で確認してください。"
               "変更がなければ初期値のまま追加できます。"),
    }[language]


def _additional_order_items(text: str) -> list[CartItem]:
    """Build option-review presets for explicitly named additional-order menus.

    The option dialog remains authoritative.  For one named menu we preserve a
    plainly stated HOT/ICED and S/L choice; all other options stay at their
    catalog defaults for the customer to review before adding.
    """
    from src.retrieve import rule_hits

    menu_ids, _ = rule_hits(text)
    ordered_ids = sorted(menu_id for menu_id in menu_ids if menu_by_id(menu_id))
    if not ordered_ids:
        return []

    normalized = str(text or "").casefold()
    temp = None
    size = None
    if len(ordered_ids) == 1:
        if re.search(r"(?:아이스|차갑|\biced\b|冰|アイス)", normalized):
            temp = "ICED"
        elif re.search(r"(?:핫|따뜻|뜨겁|\bhot\b|热|ホット)", normalized):
            temp = "HOT"
        if re.search(r"(?:\bl(?:arge)?\b|라지|大杯|ラージ)", normalized):
            size = "L"
        elif re.search(r"(?:\bs(?:mall)?\b|스몰|小杯|スモール)", normalized):
            size = "S"

    items: list[CartItem] = []
    for menu_id in ordered_ids[:10]:
        variant, variants = resolve_variant(menu_id, temp=temp, size=size)
        if variant is None:
            candidates = variants
            if temp:
                candidates = [row for row in candidates
                              if str(row.get("온도", "")).upper() == temp] or candidates
            if size:
                candidates = [row for row in candidates
                              if str(row.get("크기", "")).upper() == size] or candidates
            variant = candidates[0] if candidates else None
        menu = menu_by_id(menu_id)
        if not menu or not variant:
            continue
        items.append(CartItem(
            menu_id=menu_id,
            variant_id=str(variant["주문 단위 ID"]),
            name=str(menu["메뉴명"]),
            temp=str(variant.get("온도") or "NA"),
            size=str(variant.get("크기") or "ONE"),
            is_alcohol=str(menu.get("주류 구분", "")).startswith("주류 포함"),
        ))
    return items


def _additional_order_payload(cart: Cart, language: str, items: list[CartItem]) -> dict:
    return {
        "reply": _deferred_cart_reply(language, len(items)),
        "quick_replies": [],
        "sources": [],
        "menu_images": [],
        "menu_actions": [],
        "open_option_menu_id": None,
        "deferred_cart_items": [_cart_line_payload(item) for item in items],
        "open_order_form": False,
        "cart": _cart_payload(cart),
        "table_id": cart.table_id,
        "language": language,
        "state_token": _issue_state_token(cart),
        "requires_staff_verification": False,
        "staff_verification_reason": None,
        "staff_challenge": None,
        "order_form": _order_form_metadata(),
    }


def _order_review_reply(language: str, has_items: bool) -> str:
    if not has_items:
        return {
            "ko": "장바구니가 비어 있습니다. 메뉴를 먼저 골라 주세요.",
            "en": "Your cart is empty. Please choose a menu item first.",
            "zh": "购物车是空的，请先选择商品。",
            "ja": "カートが空です。先にメニューを選んでください。",
        }[language]
    return {
        "ko": ("주문 검토 화면에서 이용 방식, 컵, 결제 방법과 영수증을 "
               "한 번에 확인해 주세요. 실제 결제나 매장 접수는 이루어지지 않습니다."),
        "en": ("Use the order review to choose service, cup, payment method, "
               "and receipt in one place. No real payment or store submission occurs."),
        "zh": "请在订单检查画面一次选择用餐方式、杯具、支付方式和收据。不会进行真实付款或提交到门店。",
        "ja": ("注文確認画面で利用方法、カップ、支払い方法、レシートをまとめて確認してください。"
               "実際の決済や店舗への送信は行われません。"),
    }[language]


@app.get("/api/health")
def health():
    status = content_status()
    return {
        "ok": status["ready"],
        "content": status,
        "ai_ready": ensure_api_key() and not is_mock(),
        "mock_mode": is_mock(),
    }


@app.get("/api/menu")
def menu():
    items = []
    for row in list_menus():
        menu_id = str(row["메뉴 ID"])
        variants = find_variants(menu_id)
        prices = sorted({int(variant["가격(원)"]) for variant in variants})
        available_options = {
            "bean": ([
                {"value": "B01", "label": "하우스", "surcharge": BEAN_SURCHARGE["B01"]},
                {"value": "B02", "label": "에티오피아 싱글오리진", "surcharge": BEAN_SURCHARGE["B02"]},
                {"value": "B03", "label": "콜롬비아 디카페인", "surcharge": BEAN_SURCHARGE["B03"]},
            ] if menu_id in OPTION_MENUS["bean"] else []),
            "extra_shots": ([
                {"value": count, "label": "추가 없음" if count == 0 else f"+{count}샷",
                 "surcharge": count * SHOT_PRICE}
                for count in range(3)
            ] if menu_id in OPTION_MENUS["extra_shots"] else []),
            "milk": ([
                {"value": value, "label": label, "surcharge": MILK_SURCHARGE[value]}
                for value, label in (
                    ("dairy", "일반 우유"), ("lowfat", "저지방 우유"),
                    ("oat", "오트 음료"), ("soy", "두유"),
                )
            ] if menu_id in OPTION_MENUS["milk"] else []),
            "sweetness": ([
                {"value": "normal", "label": "기본", "surcharge": 0},
                {"value": "less", "label": "절반", "surcharge": 0},
            ] if menu_id in OPTION_MENUS["sweetness"] else []),
            "ice": ([
                {"value": "normal", "label": "기본", "surcharge": 0},
                {"value": "less", "label": "적게", "surcharge": 0},
            ] if menu_id in OPTION_MENUS["ice"] else []),
            "warming": ([
                {"value": "room", "label": "기본", "surcharge": 0},
                {"value": "warm", "label": "따뜻하게", "surcharge": 0},
            ] if menu_id in OPTION_MENUS["warming"] else []),
        }
        items.append({
            "id": menu_id,
            "name": str(row["메뉴명"]),
            "name_en": str(row.get("영문명") or ""),
            "category": str(row["분류"]),
            "description": str(row.get("설명") or ""),
            "ingredients": str(row.get("원재료(가상 레시피)") or ""),
            "allergens": str(row.get("알레르기 유발 재료") or ""),
            "image": f"/assets/menu/{menu_id}.jpg",
            "is_alcohol": str(row.get("주류 구분", "")).startswith("주류 포함"),
            "pairing_ids": [
                value.strip() for value in str(row.get("페어링 ID") or "").split(",")
                if value.strip()
            ],
            "variants": [{
                "id": str(variant["주문 단위 ID"]),
                "temp": str(variant.get("온도") or "NA"),
                "size": str(variant.get("크기") or "ONE"),
                "price": int(variant["가격(원)"]),
                "volume": variant.get("제공량(표준 구성)"),
                "unit": str(variant.get("단위") or ""),
            } for variant in variants],
            "options": available_options,
            "price": prices[0] if prices else None,
            "price_label": (
                f"{prices[0]:,}원" if len(prices) == 1
                else f"{prices[0]:,}원부터" if prices else "가격 확인 필요"
            ),
        })
    return {
        "categories": ["커피", "차/논커피", "디저트", "주류", "원두"],
        "items": items,
        "order_form": _order_form_metadata(),
        "capabilities": {
            "menu_option_selector": True,
            "live_cart_updates": True,
            "conversational_table_change": True,
            "simulated_checkout": True,
            "real_payment": False,
        },
    }


TABLE_CHANGE_WORDS = (
    "바꿔", "바꾸", "변경", "옮겨", "옮기", "설정해", "설정할", "로 해", "으로 해",
    "change", "switch", "move", "set table", "更改", "改", "换", "移动",
    "変更", "変え", "移動",
)

ALCOHOL_TERMS = (
    "술", "주류", "알코올", "맥주", "라거", "와인", "하이볼", "칵테일",
    "위스키", "막걸리", "소주", "beer", "wine", "alcohol", "liquor", "cocktail",
    "highball", "sake", "酒", "ビール", "ワイン",
)
ALCOHOL_PURCHASE_RE = re.compile(
    r"(?:구매(?:하고\s*싶|할게|할래|하려고\s*해|해\s*줘|해\s*주세요)|"
    r"주문(?:할게|할래|하고\s*싶|하려고\s*해|"
    r"해\s*줘|해\s*주세요)|"
    r"(?:구매|주문)(?:을|를)?\s*원(?:해(?:요)?|합니다|한다|함)|"
    r"장바구니.{0,12}(?:담|넣)|담아\s*(?:줘|주세요)?|"
    r"마실래|마시고\s*싶|살게|살래|"
    r"(?:술|주류|알코올|맥주|와인|하이볼)(?:을|를)?\s*(?:좀\s*)?(?:주세요|줘)|"
    r"(?:한|두|세|\d+)\s*(?:잔|병)\s*(?:주세요|줘)|"
    r"\b(?:buy|purchase|order|add\s+to\s+(?:my\s+)?cart|i(?:'d| would)\s+like)\b|"
    r"(?:购买|購買|下单|下單)|(?:購入|注文))",
    re.IGNORECASE,
)
ALCOHOL_PURCHASE_NEGATION_RE = re.compile(
    r"(?:술|주류|알코올|맥주|라거|와인|하이볼|칵테일|위스키)"
    r"(?:을|를|은|는)?\s*"
    r"(?:"
    r"(?:주문|구매|사|마시)(?:하고|하려고|할)?\s*싶지\s*않|"
    r"안\s*(?:살|사|구매|주문|마실|마시)|"
    r"(?:주문|구매|마시|사)하지\s*않"
    r")|"
    r"\b(?:i\s+)?(?:do\s+not|don't|dont|will\s+not|won't|wont)\s+"
    r"(?:want\s+to\s+)?"
    r"(?:buy|purchase|order|get|drink)\b.{0,32}"
    r"(?:alcohol|beer|wine|liquor|cocktail|highball)",
    re.IGNORECASE,
)

ADDITIONAL_ORDER_INFO_RE = re.compile(
    r"(?:how\s+to.{0,16}(?:another|additional)\s+order|"
    r"(?:추가\s*주문|another\s+order|additional\s+order|加单|追加订单|追加注文)"
    r".{0,12}(?:가능|어떻게|할\s*수|있나|있어\s*\?|possible|how\s+to|"
    r"可以吗|怎么|できますか|方法))",
    re.IGNORECASE,
)
ADDITIONAL_ORDER_COMMAND_RE = re.compile(
    r"(?:추가\s*주문(?:하고\s*싶|할게|할래|해\s*줘|해\s*주세요|시작|하려고)?|"
    r"더\s*(?:주문|시키|담)(?:하고\s*싶|할게|할래|을게|어\s*줘)?|"
    r"\b(?:another|additional|new)\s+order\b|\border\s+more\b|"
    r"加单|追加订单|再点|追加注文|もう.{0,8}注文)",
    re.IGNORECASE,
)


def _explicit_additional_order_intent(text: str) -> bool:
    """Recognize a command to start a new cart after confirmation."""
    normalized = str(text or "").strip()
    return bool(
        normalized
        and not ADDITIONAL_ORDER_INFO_RE.search(normalized)
        and ADDITIONAL_ORDER_COMMAND_RE.search(normalized)
    )


def _explicit_alcohol_purchase_intent(text: str) -> bool:
    """Gate purchase intent, never price/ABV/recommendation information alone."""
    lowered = str(text or "").casefold()
    if re.search(
        r"(?:술|주류|알코올)(?:이|가|은|는)?\s*"
        r"(?:말고|빼고|제외|없는|없이|아닌|안\s*든)|"
        r"(?:무|논)알코올|non[-\s]?alcoholic|without\s+alcohol",
        lowered,
    ):
        return False
    if ALCOHOL_PURCHASE_NEGATION_RE.search(lowered):
        return False
    return (
        any(term in lowered for term in ALCOHOL_TERMS)
        and bool(ALCOHOL_PURCHASE_RE.search(lowered))
    )


def _specific_alcohol_menu_ids(text: str) -> list[str]:
    """Return catalog-matched alcohol IDs in a deterministic order."""
    from src.retrieve import rule_hits

    menu_ids, _ = rule_hits(text)
    return sorted(
        menu_id for menu_id in menu_ids
        if (row := menu_by_id(menu_id))
        and str(row.get("주류 구분", "")).startswith("주류 포함")
    )


def _requested_table_change(text: str) -> int | None:
    """정보 질문이 아닌 명시적 좌석 변경 발화에서만 대상 번호를 찾는다."""
    lowered = str(text or "").casefold()
    has_table_context = any(word in lowered for word in (
        "좌석", "자리", "테이블", "table", "seat", "座位", "桌", "席",
        "テーブル",
    ))
    if not has_table_context or not any(word in lowered for word in TABLE_CHANGE_WORDS):
        return None
    patterns = (
        r"(?:좌석|자리|테이블).*?(?:에서|부터)\s*\d{1,2}\s*번?.*?(\d{1,2})\s*번?\s*(?:으로|로)",
        r"(\d{1,2})\s*번?\s*(?:으로|로)",
        r"(?:table|seat).*?\b(?:from\s+\d{1,2}\s+)?to\s+(\d{1,2})\b",
        r"(?:table|seat)\s*(?:number\s*)?(?:to\s*)?(\d{1,2})",
        r"(?:座位|桌).*?(?:改为|改為|更改为|更改為|为|為|到)\s*(\d{1,2})\s*号?",
        r"(?:座位|桌|席).*?(?:从|從)\s*\d{1,2}\s*号?.*?(?:到|改为|改為)\s*(\d{1,2})",
        r"(?:座席|席|テーブル).*?\d{1,2}\s*番.*?(\d{1,2})\s*番\s*(?:に|へ)",
        r"(?:座席|席|テーブル).*?(\d{1,2})\s*番\s*(?:に|へ)",
        r"(?:座位|桌|席).*?\d{1,2}\s*号?.*?(\d{1,2})\s*号?\s*(?:に|へ)",
        r"(?:좌석|자리|테이블)(?:\s*번호)?\s*(\d{1,2})",
        r"(?:座位|桌|席)\s*(\d{1,2})",
    )
    for pattern in patterns:
        matches = re.findall(pattern, lowered)
        if matches:
            return int(matches[-1])
    return None


def _localized_table_reply(language: str, table_id: int) -> str:
    return {
        "ko": f"좌석을 {table_id}번으로 바꿨어요. 장바구니는 그대로 유지했습니다.",
        "en": f"I changed the table to {table_id}. Your cart is unchanged.",
        "zh": f"已将座位更改为 {table_id} 号，购物车内容已保留。",
        "ja": f"席番号を {table_id} 番に変更しました。カートの内容はそのままです。",
    }[language]


def _cart_action_scope(request: CartActionRequest, cart: Cart) -> str:
    payload = {
        "action": request.action,
        "table_id": request.table_id,
        "cart": _cart_fingerprint(cart),
        "index": request.index,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@app.post("/api/cart/action")
def cart_action(request: CartActionRequest):
    """메뉴 선택 다이얼로그와 장바구니 버튼의 변경을 즉시 검증한다."""
    cart = _restore_cart(request.table_id, request.cart, request.state_token)
    original_snapshot = deepcopy(cart)
    if cart.order_no:
        raise HTTPException(
            status_code=409,
            detail=_api_text(request.language, "cart_confirmed"),
        )
    if request.action in {"replace", "remove", "set_qty"}:
        if request.index is None or not 0 <= request.index < len(cart.items):
            raise HTTPException(
                status_code=422,
                detail=_api_text(request.language, "cart_index"),
            )

    if request.action == "add":
        if request.item is None or len(cart.items) >= 30:
            raise HTTPException(
                status_code=422,
                detail=_api_text(request.language, "cart_add_item"),
            )
        item = _cart_item_from_line(request.item)
        ok, error = cart.add(item)
        if not ok:
            raise HTTPException(status_code=422, detail=error)
    elif request.action == "replace":
        if request.item is None:
            raise HTTPException(
                status_code=422,
                detail=_api_text(request.language, "cart_replace_item"),
            )
        previous = cart.items[request.index]
        was_checked = cart.staff_checked
        replacement = _cart_item_from_line(request.item)
        if replacement.menu_id != previous.menu_id:
            raise HTTPException(
                status_code=422,
                detail=_api_text(request.language, "cart_same_menu"),
            )
        cart.items[request.index] = replacement
        expands_alcohol = replacement.is_alcohol and (
            not previous.is_alcohol
            or replacement.menu_id != previous.menu_id
            or replacement.variant_id != previous.variant_id
            or replacement.qty > previous.qty
        )
        cart.staff_checked = bool(cart.has_alcohol and was_checked and not expands_alcohol)
    elif request.action == "remove":
        cart.remove(request.index)
        if not cart.has_alcohol:
            cart.staff_checked = False
    elif request.action == "set_qty":
        if request.quantity is None:
            raise HTTPException(
                status_code=422,
                detail=_api_text(request.language, "cart_quantity"),
            )
        ok, error = cart.set_qty(request.index, request.quantity)
        if not ok:
            raise HTTPException(status_code=422, detail=error)

    cart.order_no = None
    alcohol_increase = _adds_alcohol(original_snapshot, cart)
    preapproved = (
        alcohol_increase
        and _has_staff_preapproval(
            request.staff_authorization, original_snapshot, cart)
    )
    if alcohol_increase:
        # A previously verified existing alcohol cart does not authorize a new
        # quantity/type increase.  Only the one short preapproval above does.
        cart.staff_checked = bool(preapproved)
    elif cart.has_alcohol:
        cart.staff_checked = original_snapshot.staff_checked
    else:
        cart.staff_checked = False
    requires_staff = alcohol_increase and not cart.staff_checked
    scope = _cart_action_scope(request, cart)
    challenge = None
    if requires_staff:
        _require_state_secret()
        challenge = _issue_staff_challenge(cart, scope)
    return {
        "cart": _cart_payload(cart),
        "table_id": cart.table_id,
        "language": request.language,
        "state_token": _issue_state_token(cart),
        "requires_staff_verification": requires_staff,
        "staff_verification_reason": "alcohol_purchase" if requires_staff else None,
        "staff_challenge": challenge,
        "menu_actions": [],
        "open_order_form": False,
        "order_form": _order_form_metadata(),
    }


@app.post("/api/order/confirm")
def confirm_order(request: CheckoutRequest):
    """HTI E/F를 시연하는 주문 마무리. 실제 금융 결제는 하지 않는다."""
    cart = _restore_cart(request.table_id, request.cart, request.state_token)
    if cart.has_alcohol and not cart.staff_checked:
        raise HTTPException(
            status_code=409,
            detail=_api_text(request.language, "alcohol_staff"),
        )
    if cart.has_alcohol and request.service_mode != "dine_in":
        raise HTTPException(
            status_code=422,
            detail=_api_text(request.language, "alcohol_dine_in"),
        )
    allowed_cups = ({"store", "personal"} if request.service_mode == "dine_in"
                    else {"personal", "disposable"})
    if request.cup not in allowed_cups:
        raise HTTPException(
            status_code=422,
            detail=_api_text(request.language, "cup_mode"),
        )
    if request.service_mode == "dine_in" and "carrier" in request.supplies:
        raise HTTPException(
            status_code=422,
            detail=_api_text(request.language, "carrier_takeout"),
        )
    if request.split_mode == "equal" and request.split_count < 2:
        raise HTTPException(
            status_code=422,
            detail=_api_text(request.language, "equal_split_min"),
        )
    if request.split_mode != "equal" and request.split_count != 1:
        raise HTTPException(
            status_code=422,
            detail=_api_text(request.language, "split_count_equal"),
        )

    if not cart.order_no:
        ok, result = cart.confirm()
        if not ok:
            raise HTTPException(status_code=422, detail=result)
    if request.split_mode == "equal":
        quotient, remainder = divmod(cart.total, request.split_count)
        split_parts = [
            {"part": index + 1, "amount": quotient + (1 if index < remainder else 0)}
            for index in range(request.split_count)
        ]
    elif request.split_mode == "by_item":
        split_parts = [
            {
                "part": index + 1,
                "line_index": index,
                "menu_id": item.menu_id,
                "name": item.name,
                "quantity": item.qty,
                "amount": item.subtotal,
            }
            for index, item in enumerate(cart.items)
        ]
    else:
        split_parts = [{"part": 1, "amount": cart.total}]

    messages = {
        "ko": "시연용 주문을 확정했습니다. 실제 결제나 매장 접수는 이루어지지 않습니다.",
        "en": ("The demo order is confirmed. No real payment was processed "
               "and nothing was sent to the store."),
        "zh": "演示订单已确认，但未进行真实付款，也未发送至门店。",
        "ja": "デモ注文を確定しました。実際の決済や店舗への送信は行われていません。",
    }
    return {
        "message": messages[request.language],
        "order_no": cart.order_no,
        "cart": _cart_payload(cart),
        "table_id": cart.table_id,
        "language": request.language,
        "state_token": _issue_state_token(cart),
        "checkout": {
            "order_no": cart.order_no,
            "table_id": cart.table_id,
            "items": _cart_payload(cart)["items"],
            "service_mode": request.service_mode,
            "cup": request.cup,
            "supplies": list(dict.fromkeys(request.supplies)),
            "discount": 0,
            "subtotal": cart.total,
            "total_before_discount": cart.total,
            "total_due": cart.total,
            "membership_connected": False,
            "membership_applied": False,
            "benefits_available": False,
            "coupon_applied": False,
            "points_used": 0,
            "points_earned": 0,
            "payment_method": request.payment_method,
            "split_mode": request.split_mode,
            "split_count": (request.split_count if request.split_mode == "equal"
                            else len(split_parts)),
            "split_amount": (
                max(part["amount"] for part in split_parts)
                if request.split_mode == "equal" else None
            ),
            "split_parts": split_parts,
            "receipt": request.receipt,
            "simulated": True,
            "completion_status": "demo_complete",
            "payment_status": "simulation_complete",
            "external_payment_performed": False,
            "store_order_submitted": False,
        },
        "open_order_form": False,
        "order_form": _order_form_metadata(),
    }


def _staff_required_payload(
    cart: Cart,
    scope: str,
    language: str = "ko",
    *,
    authorization_mode: str = "none",
    allowed_cart_fingerprints: list[str] | None = None,
    allowed_menu_ids: list[str] | None = None,
) -> dict:
    _require_state_secret()
    replies = {
        "ko": "직원 확인이 필요한 내용입니다. 직원을 부르겠습니다.",
        "en": "This alcohol purchase requires staff verification. I'll call a staff member.",
        "zh": "购买酒类需要员工确认。我来呼叫员工。",
        "ja": "酒類の購入にはスタッフ確認が必要です。スタッフをお呼びします。",
    }
    return {
        "reply": replies.get(language, replies["ko"]),
        "quick_replies": [],
        "sources": [],
        "menu_images": [],
        "menu_actions": [],
        "open_option_menu_id": None,
        "deferred_cart_items": [],
        "open_order_form": False,
        "cart": _cart_payload(cart),
        "table_id": cart.table_id,
        "language": language,
        "state_token": _issue_state_token(cart),
        "requires_staff_verification": True,
        "staff_verification_reason": "alcohol_purchase",
        "staff_challenge": _issue_staff_challenge(
            cart,
            scope,
            authorization_mode=authorization_mode,
            allowed_cart_fingerprints=allowed_cart_fingerprints,
            allowed_menu_ids=allowed_menu_ids,
        ),
        "order_form": _order_form_metadata(),
    }


@app.post("/api/chat")
def chat(
    request: ChatRequest,
    x_openai_api_key: str | None = Header(default=None),
):
    # Pydantic의 자동 길이 검사는 오류 JSON에 입력값을 담을 수 있어
    # 비밀 키는 직접 검사하고 값을 포함하지 않는 오류만 반환한다.
    if x_openai_api_key is not None and len(x_openai_api_key) > 512:
        raise HTTPException(
            status_code=422,
            detail=_api_text(request.language, "api_key_too_long"),
        )
    with request_api_key(x_openai_api_key), request_language(request.language):
        cart = _restore_cart(request.table_id, request.cart, request.state_token)
        additional_order_requested = _explicit_additional_order_intent(
            request.message)
        if cart.order_no and additional_order_requested:
            # A confirmed order stays immutable.  Conversational "additional
            # order" starts a separate cart at the same table, matching the
            # explicit button flow in the browser.
            cart = Cart(table_id=cart.table_id)
        requested_table = _requested_table_change(request.message)
        if requested_table is not None:
            if requested_table not in TABLES:
                details = {
                    "ko": f"좌석은 {min(TABLES)}번부터 {max(TABLES)}번까지 선택할 수 있습니다.",
                    "en": f"Please choose a table from {min(TABLES)} to {max(TABLES)}.",
                    "zh": f"请选择 {min(TABLES)} 至 {max(TABLES)} 号座位。",
                    "ja": f"席番号は {min(TABLES)}〜{max(TABLES)} から選んでください。",
                }
                raise HTTPException(status_code=422, detail=details[request.language])
            if cart.order_no and requested_table != cart.table_id:
                details = {
                    "ko": "이미 확정한 주문의 좌석은 변경할 수 없습니다.",
                    "en": "The table for a confirmed order cannot be changed.",
                    "zh": "已确认订单的座位无法更改。",
                    "ja": "確定済み注文の席番号は変更できません。",
                }
                raise HTTPException(status_code=409, detail=details[request.language])
            cart.table_id = requested_table
            # Moving seats does not buy or increase alcohol, so it must never
            # interrupt the user with an age-check modal.
            requires_staff = False
            staff_challenge = None
            return {
                "reply": _localized_table_reply(request.language, requested_table),
                "quick_replies": [],
                "sources": [],
                "menu_images": [],
                "menu_actions": [],
                "open_option_menu_id": None,
                "deferred_cart_items": [],
                "open_order_form": False,
                "cart": _cart_payload(cart),
                "table_id": cart.table_id,
                "language": request.language,
                "state_token": _issue_state_token(cart),
                "requires_staff_verification": requires_staff,
                "staff_verification_reason": (
                    "alcohol_purchase" if requires_staff else None
                ),
                "staff_challenge": staff_challenge,
                "order_form": _order_form_metadata(),
            }

        scope = _staff_scope(request)
        staff_authorized = _has_staff_authorization(
            request.staff_authorization, cart, scope)
        explicit_alcohol_purchase = _explicit_alcohol_purchase_intent(
            request.message)
        specific_alcohol_menu_ids = _specific_alcohol_menu_ids(request.message)
        # Explicit alcohol purchases must be verified before the AI router or
        # API-key check.  This keeps the staff modal deterministic in production
        # for both generic requests and named menu requests such as
        # "맥주 주문할게요".  Information-only price, ABV and recommendation
        # questions continue to the normal answer path.
        if explicit_alcohol_purchase and not staff_authorized:
            return _staff_required_payload(
                cart,
                scope,
                request.language,
                authorization_mode=(
                    "menu_ids_one_alcohol_line"
                    if specific_alcohol_menu_ids
                    else "generic_one_alcohol_line"
                ),
                allowed_menu_ids=specific_alcohol_menu_ids,
            )

        if additional_order_requested:
            additional_items = _additional_order_items(request.message)
            if additional_items:
                return _additional_order_payload(
                    cart, request.language, additional_items)

        if not is_mock() and not ensure_api_key():
            raise HTTPException(
                status_code=503,
                detail=_api_text(request.language, "api_key_required"),
            )

        original_snapshot = deepcopy(cart)
        original_cart = _cart_fingerprint(cart)
        original_staff_checked = cart.staff_checked
        history = [message.model_dump() for message in request.history]
        try:
            result = handle(request.message.strip(), get_store(), cart, history)
        except HTTPException:
            raise
        except Exception as exc:
            # 외부 SDK 예외 문구에 요청 시크릿이 포함될 가능성을 차단한다.
            print(f"Moki chat error: {type(exc).__name__}")
            if (getattr(exc, "status_code", None) == 401
                    or type(exc).__name__ == "AuthenticationError"):
                raise HTTPException(
                    status_code=401,
                    detail=_api_text(request.language, "api_key_invalid"),
                ) from None
            raise HTTPException(
                status_code=500,
                detail=_api_text(request.language, "answer_failed"),
            ) from None

        result_intent = str(getattr(result, "intent", ""))
        deferred_items: list[CartItem] = []
        structured_checkout = False
        declared_added = getattr(result, "added_items", None)
        if declared_added is None:
            # Compatibility for patched/older TurnResult objects in callers.
            new_items = (
                cart.items[len(original_snapshot.items):]
                if len(cart.items) > len(original_snapshot.items) else []
            )
        else:
            new_items = list(declared_added)
        if (request.defer_cart_add and result_intent == "장바구니"
                and new_items):
            # 브라우저 주문은 모델이 제안한 항목을 즉시 확정하지 않는다.
            # 검증된 제안만 옵션 화면에 넘긴다. 같은 발화의 수정·삭제는
            # 즉시 반영하되, executor가 마지막에 append한 add 제안만 떼어낸다.
            deferred_items = deepcopy(new_items)
            if declared_added is None:
                cart = original_snapshot
            else:
                cart.items = cart.items[:-len(deferred_items)]
                cart.order_no = original_snapshot.order_no
                cart.staff_checked = original_snapshot.staff_checked
            result_reply = _deferred_cart_reply(
                request.language, max(1, len(deferred_items))
            )
        elif request.defer_cart_add and result_intent == "결제":
            # 브라우저에서는 E/F 필수 선택을 건너뛰고 대화만으로 주문번호를
            # 발급하지 않는다. 구조화된 검토 폼이 실제 확정 엔드포인트를 호출한다.
            cart = original_snapshot
            structured_checkout = bool(cart.items and not cart.order_no)
            result_reply = _order_review_reply(
                request.language, bool(cart.items)
            )
        else:
            result_reply = str(result.reply)

        # 서명된 상태를 복원한 뒤 장바구니 내용이 바뀌었다면 기존 주문번호와
        # 직원 확인을 이어받지 않는다. 새 구성은 다시 검토해야 한다.
        if _cart_fingerprint(cart) != original_cart:
            cart.order_no = None
            # 비주류 변경이나 주류 감소에는 기존 확인을 유지하지만, 새 주류
            # 종류·수량이 늘면 이 구매 요청에 대한 직원 확인을 다시 받는다.
            cart.staff_checked = bool(
                cart.has_alcohol
                and (
                    staff_authorized
                    or (original_staff_checked
                        and not _adds_alcohol(original_snapshot, cart))
                )
            )
        elif staff_authorized and cart.has_alcohol:
            cart.staff_checked = True

        # 실제 구매 요청으로 주류가 추가된 경우에만 답변을 보류한다. 변경 전
        # 장바구니를 돌려줘서 승인 후 자동 재시도가 중복 추가를 만들지 않게 한다.
        if (_adds_alcohol(original_snapshot, cart)
                and not cart.staff_checked):
            return _staff_required_payload(
                original_snapshot,
                scope,
                request.language,
                # A concrete chat purchase must be retried with the exact
                # scoped authorization.  Empty-cart state preapproval is
                # reserved for the generic "I want to buy alcohol" flow.
                authorization_mode="exact",
                allowed_cart_fingerprints=[_cart_fingerprint(cart)],
            )

        result_menu_images = getattr(result, "menu_images", None)
        if result_menu_images is None:
            # 단위 테스트·예전 호출자의 TurnResult에 새 필드가 없어도
            # 같은 검증 규칙으로 사진 후속 질문을 처리한다.
            result_menu_images = menu_image_cards(
                result.docs,
                user_message=request.message,
                rewritten=str(getattr(result, "rewritten", "")),
                reply=result_reply,
                history=history,
            )

        authorized_choice_ids = (
            specific_alcohol_menu_ids
            if staff_authorized and explicit_alcohol_purchase else []
        )
        menu_actions = _menu_actions(
            # During a deferred compound order, only the validated order
            # targets belong in the option queue.  Retrieved comparison or
            # policy context must not become an extra menu button.
            [] if deferred_items else result.docs,
            [] if deferred_items else result_menu_images,
            menu_ids=[item.menu_id for item in deferred_items] + authorized_choice_ids,
        )
        open_option_menu_id = (
            deferred_items[0].menu_id if deferred_items else None
        )
        if (open_option_menu_id is None
                and len(authorized_choice_ids) == 1):
            open_option_menu_id = authorized_choice_ids[0]
        pending_staff_challenge = (
            _issue_staff_challenge(cart, scope)
            if cart.has_alcohol and not cart.staff_checked else None
        )

        return {
            "reply": result_reply,
            "quick_replies": result.quick_replies,
            "sources": source_cards(result.docs),
            "menu_images": result_menu_images,
            "menu_actions": menu_actions,
            "open_option_menu_id": open_option_menu_id,
            "deferred_cart_items": [
                _cart_line_payload(item) for item in deferred_items
            ],
            "open_order_form": structured_checkout,
            "cart": _cart_payload(cart),
            "table_id": cart.table_id,
            "language": request.language,
            "state_token": _issue_state_token(cart),
            "requires_staff_verification": False,
            "staff_verification_reason": None,
            # A pending cart may be verified voluntarily, but viewing,
            # reducing or removing it is never blocked by this challenge.
            "staff_challenge": pending_staff_challenge,
            "staff_authorization": (
                request.staff_authorization
                if staff_authorized
                and (deferred_items or explicit_alcohol_purchase)
                else None
            ),
            "order_form": _order_form_metadata(),
        }


@app.post("/api/staff/verify")
def verify_staff(
    request: StaffVerifyRequest,
    x_moki_staff_code: str | None = Header(default=None),
):
    _require_staff_code(x_moki_staff_code, request.language)
    _require_state_secret()
    cart = _restore_cart(request.table_id, request.cart, request.state_token)
    challenge = _challenge_payload(request.staff_challenge, cart)
    if not challenge:
        raise HTTPException(
            status_code=410,
            detail=_api_text(request.language, "challenge_expired"),
        )
    cart.order_no = None
    # Empty-cart approval is carried only in the short authorization token,
    # never as a broadly reusable signed ``staff_checked`` cart state.
    cart.staff_checked = cart.has_alcohol
    scope = str(challenge["scope"])
    messages = {
        "ko": ("직원 나이 확인이 완료되었습니다."
               if cart.has_alcohol else "직원 확인이 완료되었습니다."),
        "en": ("Staff age verification is complete."
               if cart.has_alcohol else "Staff verification is complete."),
        "zh": ("员工年龄确认已完成。" if cart.has_alcohol else "员工确认已完成。"),
        "ja": ("スタッフによる年齢確認が完了しました。"
               if cart.has_alcohol else "スタッフ確認が完了しました。"),
    }
    return {
        "message": messages[request.language],
        "cart": _cart_payload(cart),
        "table_id": cart.table_id,
        "language": request.language,
        "state_token": _issue_state_token(cart),
        "staff_authorization": _issue_staff_authorization(
            cart,
            scope,
            authorization_mode=str(
                challenge.get("authorization_mode", "none")),
            allowed_cart_fingerprints=[
                str(value)
                for value in (challenge.get("allowed_cart_fingerprints") or [])
                if re.fullmatch(r"[0-9a-f]{64}", str(value))
            ][:10],
            allowed_menu_ids=[
                str(value)
                for value in (challenge.get("allowed_menu_ids") or [])
                if re.fullmatch(r"M\d{2}", str(value))
                and (row := menu_by_id(str(value)))
                and str(row.get("주류 구분", "")).startswith("주류 포함")
            ][:10],
        ),
        "open_order_form": False,
        "order_form": _order_form_metadata(),
    }


# FastAPI의 정적 프런트엔드 선언을 사용하면 Vercel은 public/**를 CDN으로 올리고,
# 로컬 TestClient/ASGI 실행에서도 같은 경로와 index.html 폴백을 제공한다.
app.frontend("/", directory=PUBLIC_DIR, fallback="index.html")
