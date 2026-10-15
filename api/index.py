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
from functools import lru_cache
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from src.cart import (Cart, CartItem, find_variants, list_menus, menu_by_id,
                      validate_item_options, variant_by_id)
from src.config import TABLES, ensure_api_key, is_mock
from src.content import content_status, source_cards
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


class StaffVerifyRequest(BaseModel):
    table_id: int = Field(default=5, ge=min(TABLES), le=max(TABLES))
    cart: list[CartLine] = Field(default_factory=list, min_length=1, max_length=30)
    state_token: str | None = Field(default=None, max_length=2048)


@lru_cache(maxsize=1)
def get_store() -> LexicalStore:
    return LexicalStore()


def _require_password(password: str | None) -> None:
    expected = os.getenv("MOKI_PASSWORD", "").strip()
    if expected and not secrets.compare_digest(password or "", expected):
        raise HTTPException(status_code=401, detail="매장 접속 비밀번호를 확인해 주세요.")


def _require_staff_password(password: str | None) -> None:
    expected = os.getenv("MOKI_STAFF_PASSWORD", "").strip()
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="Vercel 환경변수 MOKI_STAFF_PASSWORD를 먼저 설정해 주세요.",
        )
    if not secrets.compare_digest(password or "", expected):
        raise HTTPException(status_code=401, detail="직원 확인 코드를 확인해 주세요.")


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


def _state_secret() -> bytes | None:
    value = (
        os.getenv("MOKI_STATE_SECRET", "").strip()
        or os.getenv("MOKI_STAFF_PASSWORD", "").strip()
    )
    return value.encode("utf-8") if value else None


def _issue_state_token(cart: Cart) -> str | None:
    secret = _state_secret()
    if not secret:
        return None
    payload = {
        "v": 1,
        "table_id": cart.table_id,
        "cart": _cart_fingerprint(cart),
        "order_no": cart.order_no,
        "staff_checked": cart.staff_checked,
        "exp": int(time.time()) + 8 * 60 * 60,
    }
    encoded = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ).decode("ascii").rstrip("=")
    signature = hmac.new(secret, encoded.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{encoded}.{signature}"


def _restore_signed_state(cart: Cart, token: str | None) -> None:
    secret = _state_secret()
    if not secret or not token:
        return
    try:
        encoded, signature = token.split(".", 1)
        expected = hmac.new(secret, encoded.encode("ascii"), hashlib.sha256).hexdigest()
        if not secrets.compare_digest(signature, expected):
            return
        padded = encoded + "=" * (-len(encoded) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
        if payload.get("v") != 1 or int(payload.get("exp", 0)) < int(time.time()):
            return
        if payload.get("table_id") != cart.table_id:
            return
        if payload.get("cart") != _cart_fingerprint(cart):
            return
        order_no = payload.get("order_no")
        if order_no is None or re.fullmatch(r"M\d{4}", str(order_no)):
            cart.order_no = order_no
        cart.staff_checked = bool(payload.get("staff_checked", False))
    except (ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError):
        return


def _restore_cart(table_id: int, lines: list[CartLine], state_token: str | None) -> Cart:
    cart = Cart(table_id=table_id)
    for line in lines:
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
        added, error = cart.add(item)
        if not added:
            raise HTTPException(status_code=422, detail=error)
    _restore_signed_state(cart, state_token)
    return cart


def _cart_payload(cart: Cart) -> dict:
    return {
        "items": [
            {
                "menu_id": item.menu_id,
                "variant_id": item.variant_id,
                "name": item.name,
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
            }
            for item in cart.items
        ],
        "total": cart.total,
        "status": cart.status(),
        "order_no": cart.order_no,
        "staff_checked": cart.staff_checked,
    }


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
        items.append({
            "id": menu_id,
            "name": str(row["메뉴명"]),
            "name_en": str(row.get("영문명") or ""),
            "category": str(row["분류"]),
            "description": str(row.get("설명") or ""),
            "image": f"/assets/menu/{menu_id}.jpg",
            "price": prices[0] if prices else None,
            "price_label": (
                f"{prices[0]:,}원" if len(prices) == 1
                else f"{prices[0]:,}원부터" if prices else "가격 확인 필요"
            ),
        })
    return {"categories": ["커피", "차/논커피", "디저트", "주류", "원두"], "items": items}


@app.post("/api/chat")
def chat(request: ChatRequest, x_moki_password: str | None = Header(default=None)):
    _require_password(x_moki_password)
    if not is_mock() and not ensure_api_key():
        raise HTTPException(
            status_code=503,
            detail="Vercel 환경변수 OPENAI_API_KEY를 설정한 뒤 다시 배포해 주세요.",
        )

    cart = _restore_cart(request.table_id, request.cart, request.state_token)
    original_cart = _cart_fingerprint(cart)
    history = [message.model_dump() for message in request.history]
    try:
        result = handle(request.message.strip(), get_store(), cart, history)
    except HTTPException:
        raise
    except Exception as exc:
        print(f"Moki chat error: {type(exc).__name__}: {exc}")
        raise HTTPException(
            status_code=500,
            detail="모키가 답변을 준비하지 못했습니다. 잠시 후 다시 시도해 주세요.",
        ) from exc

    # 서명된 상태를 복원한 뒤 장바구니 내용이 바뀌었다면 기존 주문번호와
    # 직원 확인을 이어받지 않는다. 새 구성은 다시 검토해야 한다.
    if _cart_fingerprint(cart) != original_cart:
        cart.order_no = None
        cart.staff_checked = False

    return {
        "reply": result.reply,
        "quick_replies": result.quick_replies,
        "sources": source_cards(result.docs),
        "cart": _cart_payload(cart),
        "state_token": _issue_state_token(cart),
    }


@app.post("/api/staff/verify")
def verify_staff(
    request: StaffVerifyRequest,
    x_moki_password: str | None = Header(default=None),
    x_moki_staff_password: str | None = Header(default=None),
):
    _require_password(x_moki_password)
    _require_staff_password(x_moki_staff_password)
    cart = _restore_cart(request.table_id, request.cart, request.state_token)
    if not cart.has_alcohol:
        raise HTTPException(status_code=422, detail="직원 확인이 필요한 주류가 없습니다.")
    cart.order_no = None
    cart.staff_checked = True
    return {
        "message": "직원 나이 확인이 완료되었습니다.",
        "cart": _cart_payload(cart),
        "state_token": _issue_state_token(cart),
    }


# FastAPI의 정적 프런트엔드 선언을 사용하면 Vercel은 public/**를 CDN으로 올리고,
# 로컬 TestClient/ASGI 실행에서도 같은 경로와 index.html 폴백을 제공한다.
app.frontend("/", directory=PUBLIC_DIR, fallback="index.html")
