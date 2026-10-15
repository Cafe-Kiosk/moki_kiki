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

from src.cart import (Cart, CartItem, find_variants, list_menus, menu_by_id,
                      validate_item_options, variant_by_id)
from src.config import TABLES, ensure_api_key, is_mock, request_api_key
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
    if request.url.path in {"/api/chat", "/api/staff/verify"}:
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


class StaffVerifyRequest(BaseModel):
    table_id: int = Field(default=5, ge=min(TABLES), le=max(TABLES))
    cart: list[CartLine] = Field(default_factory=list, max_length=30)
    state_token: str | None = Field(default=None, max_length=2048)
    staff_challenge: str | None = Field(default=None, max_length=2048)
    # 이전 클라이언트와의 요청 형식 호환용이다. 이 값만으로는 승인하지 않는다.
    reason: Literal["alcohol_inquiry"] | None = None


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


_ALCOHOL_KEYWORDS = {
    "주류", "술", "알코올", "무알콜", "도수", "민증", "나이 확인", "성인 인증",
    "하이볼", "맥주", "와인", "소주", "위스키", "마티니", "스프리츠", "칵테일",
    "alcohol", "alcoholic", "abv", "beer", "wine", "soju", "whisky", "whiskey",
    "highball", "martini", "spritz", "cocktail", "liquor", "booze", "age check",
    "beers", "wines", "whiskies", "whiskeys", "highballs", "martinis", "spritzes",
    "cocktails", "liquors", "spirits",
}


@lru_cache(maxsize=1)
def _alcohol_terms() -> tuple[str, ...]:
    """정책 키워드와 판매 데이터의 실제 주류명·별칭을 합친다."""
    terms = {term.casefold() for term in _ALCOHOL_KEYWORDS}
    for row in list_menus():
        if not str(row.get("주류 구분", "")).startswith("주류 포함"):
            continue
        for value in (row.get("메뉴 ID"), row.get("메뉴명"), row.get("영문명")):
            normalized = str(value or "").strip().casefold()
            if len(normalized) >= 2:
                terms.add(normalized)
        for alias in re.split(r"[,\n]", str(row.get("별칭", ""))):
            normalized = alias.strip().casefold()
            if len(normalized) >= 2:
                terms.add(normalized)
    return tuple(sorted(terms, key=len, reverse=True))


@lru_cache(maxsize=1)
def _alcohol_menu_ids() -> frozenset[str]:
    return frozenset(
        str(row.get("메뉴 ID", ""))
        for row in list_menus()
        if str(row.get("주류 구분", "")).startswith("주류 포함")
    )


def _is_alcohol_inquiry(message: str) -> bool:
    normalized = " ".join(str(message).casefold().split())
    for term in _alcohol_terms():
        # 한 글자 키워드 ``술``은 ``기술``·``술래잡기`` 같은 일반 단어
        # 내부에서는 매칭하지 않는다.
        if term == "술":
            if re.search(r"(?<![가-힣])술(?![가-힣])", normalized):
                return True
            continue
        if term.isascii() and re.fullmatch(r"[a-z0-9 ]+", term):
            if re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", normalized):
                return True
        elif term in normalized:
            return True
    return False


def _has_alcohol_context(request: ChatRequest) -> bool:
    """현재 발화 또는 주류를 가리키는 후속 발화에서 주류 맥락을 찾는다."""
    if _is_alcohol_inquiry(request.message):
        return True
    # 웹 UI는 직원 확인 안내를 대화 기록에 저장하지 않는다. 따라서 마지막
    # 기록이 주류를 묻는 user 발화라면 아직 해결되지 않은 턴으로 간주한다.
    if (request.history and request.history[-1].role == "user"
            and _is_alcohol_inquiry(request.history[-1].content)):
        return True
    normalized = " ".join(request.message.casefold().split())
    followup = bool(
        re.search(
            r"방금|아까|앞에서|위\s*(?:질문|내용)|그(?:거|것|걸|메뉴|음료|중)|해당",
            normalized,
        )
        or re.search(
            r"\b(?:it|that|those|them|previous|above|same)\b",
            normalized,
        )
    )
    return followup and any(
        _is_alcohol_inquiry(item.content) for item in request.history[-4:])


def _staff_scope(request: ChatRequest) -> str:
    """직원 승인을 정확히 같은 한 번의 대화 요청에 묶는다."""
    payload = {
        "message": request.message.strip(),
        "history": [message.model_dump() for message in request.history],
    }
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _documents_have_alcohol(documents) -> bool:
    """검색 결과가 주류 메뉴·주류 정책을 근거로 삼았는지 확인한다."""
    for document in documents or []:
        metadata = getattr(document, "metadata", {}) or {}
        entity_id = str(
            metadata.get("entity_id")
            or metadata.get("menu_id")
            or metadata.get("id")
            or ""
        ).split(":", 1)[0]
        if entity_id in _alcohol_menu_ids() or entity_id in {"P15", "P19"}:
            return True
    return False


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


def _issue_staff_challenge(cart: Cart, scope: str) -> str | None:
    return _sign_payload({
        "v": 1,
        "purpose": "staff_challenge",
        "table_id": cart.table_id,
        "cart": _cart_fingerprint(cart),
        "scope": scope,
        "exp": int(time.time()) + 5 * 60,
    })


def _challenge_scope(token: str | None, cart: Cart) -> str | None:
    payload = _read_signed_payload(token, "staff_challenge")
    if not payload:
        return None
    scope = str(payload.get("scope", ""))
    if (payload.get("table_id") != cart.table_id
            or payload.get("cart") != _cart_fingerprint(cart)
            or not re.fullmatch(r"[0-9a-f]{64}", scope)):
        return None
    return scope


def _issue_staff_authorization(cart: Cart, scope: str) -> str | None:
    return _sign_payload({
        "v": 1,
        "purpose": "staff_authorization",
        "table_id": cart.table_id,
        "cart": _cart_fingerprint(cart),
        "scope": scope,
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


def _staff_required_payload(cart: Cart, scope: str) -> dict:
    return {
        "reply": "직원 확인이 필요한 내용입니다. 직원을 부르겠습니다.",
        "quick_replies": [],
        "sources": [],
        "cart": _cart_payload(cart),
        "state_token": _issue_state_token(cart),
        "requires_staff_verification": True,
        "staff_verification_reason": "alcohol_inquiry",
        "staff_challenge": _issue_staff_challenge(cart, scope),
    }


@app.post("/api/chat")
def chat(
    request: ChatRequest,
    x_moki_password: str | None = Header(default=None),
    x_openai_api_key: str | None = Header(default=None),
):
    _require_password(x_moki_password)
    # Pydantic의 자동 길이 검사는 오류 JSON에 입력값을 담을 수 있어
    # 비밀 키는 직접 검사하고 값을 포함하지 않는 오류만 반환한다.
    if x_openai_api_key is not None and len(x_openai_api_key) > 512:
        raise HTTPException(status_code=422, detail="API 키가 너무 깁니다.")
    with request_api_key(x_openai_api_key):
        cart = _restore_cart(request.table_id, request.cart, request.state_token)
        scope = _staff_scope(request)
        staff_authorized = _has_staff_authorization(
            request.staff_authorization, cart, scope)
        alcohol_context = _has_alcohol_context(request)
        query_needs_staff = alcohol_context and not staff_authorized
        cart_needs_staff = (
            cart.has_alcohol and not cart.staff_checked and not staff_authorized)
        if query_needs_staff or cart_needs_staff:
            return _staff_required_payload(cart, scope)

        if not is_mock() and not ensure_api_key():
            raise HTTPException(
                status_code=503,
                detail=("OPENAI_API_KEY 환경변수를 설정하거나 "
                        "현재 요청에 API 키를 입력해 주세요."),
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
                    detail="OpenAI API 키를 확인해 주세요.",
                ) from None
            raise HTTPException(
                status_code=500,
                detail="모키가 답변을 준비하지 못했습니다. 잠시 후 다시 시도해 주세요.",
            ) from None

        # 모호한 요청이 검색·분류 뒤에 주류 근거로 해석된 경우에도 답변과
        # 상태 변경을 숨기고, 변경 전 장바구니를 기준으로 직원 확인을 받는다.
        if _documents_have_alcohol(result.docs) and not staff_authorized:
            return _staff_required_payload(original_snapshot, scope)

        # 서명된 상태를 복원한 뒤 장바구니 내용이 바뀌었다면 기존 주문번호와
        # 직원 확인을 이어받지 않는다. 새 구성은 다시 검토해야 한다.
        if _cart_fingerprint(cart) != original_cart:
            cart.order_no = None
            # 유효한 서명 상태로 시작했거나 이 요청 자체를 직원이 승인했다면,
            # 서버가 만든 새 주류 장바구니에만 확인 상태를 이어 준다.
            cart.staff_checked = bool(
                cart.has_alcohol and (original_staff_checked or staff_authorized))
        elif staff_authorized and cart.has_alcohol:
            cart.staff_checked = True

        # 분류 단계에서 처음 드러난 주류도 답변을 노출하기 전에 차단한다.
        # 이때 변경 전 장바구니를 돌려줘서 승인 후 자동 재시도가 중복 추가를
        # 만들지 않게 한다.
        if cart.has_alcohol and not cart.staff_checked:
            return _staff_required_payload(original_snapshot, scope)

        return {
            "reply": result.reply,
            "quick_replies": result.quick_replies,
            "sources": source_cards(result.docs),
            "cart": _cart_payload(cart),
            "state_token": _issue_state_token(cart),
            "requires_staff_verification": False,
            "staff_verification_reason": None,
            "staff_challenge": None,
        }


@app.post("/api/staff/verify")
def verify_staff(
    request: StaffVerifyRequest,
    x_moki_password: str | None = Header(default=None),
    x_moki_staff_password: str | None = Header(default=None),
):
    _require_password(x_moki_password)
    _require_staff_password(x_moki_staff_password)
    _require_state_secret()
    cart = _restore_cart(request.table_id, request.cart, request.state_token)
    scope = _challenge_scope(request.staff_challenge, cart)
    if not scope:
        raise HTTPException(
            status_code=410,
            detail="직원 확인 요청이 없거나 만료되었습니다. 주류 내용을 다시 요청해 주세요.",
        )
    cart.order_no = None
    # 정보 질문만 확인한 빈 장바구니에는 포괄 승인을 남기지 않는다.
    # 이미 주류가 담긴 경우에만 해당 장바구니의 나이 확인 상태를 서명한다.
    cart.staff_checked = cart.has_alcohol
    return {
        "message": (
            "직원 확인이 완료되었습니다."
            if not cart.has_alcohol
            else "직원 나이 확인이 완료되었습니다."
        ),
        "cart": _cart_payload(cart),
        "state_token": _issue_state_token(cart),
        "staff_authorization": _issue_staff_authorization(cart, scope),
    }


# FastAPI의 정적 프런트엔드 선언을 사용하면 Vercel은 public/**를 CDN으로 올리고,
# 로컬 TestClient/ASGI 실행에서도 같은 경로와 index.html 폴백을 제공한다.
app.frontend("/", directory=PUBLIC_DIR, fallback="index.html")
