"""모키 커피바 — 좌석 태블릿 주문 화면.

실행:  streamlit run app.py
"""
from __future__ import annotations
import html, json
import streamlit as st
import streamlit.components.v1 as components

from src.config import (TABLES, MOCK, ROUTER_MODEL, ANSWER_MODEL, INDEX_DIR,
                        ensure_api_key, secret_status)
from src.index import load_index
from src.cart import Cart
from src.kiosk import handle

st.set_page_config(page_title="모키 커피바", page_icon="☕", layout="wide")

from src.auth import check as _check_password
if not _check_password():
    st.stop()

CSS = """
<style>
.block-container {padding-top: 2rem; max-width: 1280px;}
.moki-head {display:flex; align-items:baseline; gap:.7rem; margin-bottom:.2rem;}
.moki-head h1 {font-size:1.9rem; margin:0; color:#4A3426; letter-spacing:-.02em;}
.moki-head span {color:#9B8579; font-size:.9rem;}
.bubble-user {background:#6F4E37; color:#fff; padding:.65rem .9rem; border-radius:14px 14px 3px 14px;
  margin:.3rem 0 .3rem auto; max-width:82%; width:fit-content;}
.bubble-bot {background:#F6F1EB; color:#2B2320; padding:.65rem .9rem; border-radius:14px 14px 14px 3px;
  margin:.3rem auto .3rem 0; max-width:88%; width:fit-content; white-space:pre-wrap;}
.meta {font-size:.72rem; color:#A2928A; margin:.1rem 0 .5rem 0; font-family:ui-monospace,monospace;}
.cart-line {font-size:.9rem; padding:.28rem 0; border-bottom:1px solid #EFE8E1;}
.cart-total {font-weight:700; font-size:1.05rem; color:#4A3426; padding-top:.5rem;}
.pill {display:inline-block; font-size:.7rem; padding:.1rem .45rem; border-radius:999px;
  background:#EFE8E1; color:#6F4E37; margin-right:.25rem; font-family:ui-monospace,monospace;}
.pill-rule {background:#E3EFE6; color:#2F6B46;}
.pill-vec {background:#E6ECF5; color:#2F4E78;}
.pill-cut {background:#F5E6E6; color:#8A3A3A;}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


@st.cache_resource(show_spinner="메뉴 인덱스를 불러오는 중...")
def get_store():
    return load_index()


# ── 상태 ────────────────────────────────────────────────────
if "cart" not in st.session_state:
    st.session_state.cart = Cart(table_id=5)
if "history" not in st.session_state:
    st.session_state.history = []
if "turns" not in st.session_state:
    st.session_state.turns = []          # TurnResult 보관 (검색 내역 표시용)
if "llm_calls" not in st.session_state:
    st.session_state.llm_calls = 0

cart: Cart = st.session_state.cart

# ── 사이드바 ────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ☕ 모키 커피바")
    st.caption("좌석 태블릿 주문 · 시연용")

    cart.table_id = st.selectbox("좌석 번호", TABLES,
                                 index=TABLES.index(cart.table_id or 5))
    st.divider()

    st.markdown("**직원 확인** (주류 주문 시)")
    cart.staff_checked = st.toggle(
        "나이 확인 완료", value=cart.staff_checked,
        help="매장정책 P15 — 손님의 자기신고는 확인이 아닙니다. 직원이 확인한 경우에만 켭니다.")

    st.divider()
    st.markdown("**실행 상태**")
    _s = secret_status()
    st.caption(f"모델 {ROUTER_MODEL}")
    st.caption(f"인덱스 {'있음' if (INDEX_DIR / 'index.faiss').exists() else '없음'}")
    if _s["key_found"]:
        st.caption(f"API 키 ✅ {_s['key_head']} ({_s['key_source']})")
    else:
        st.error("API 키를 찾지 못했습니다. Secrets 에 OPENAI_API_KEY 를 넣어주세요.", icon="🔑")
    if not _s["password_set"]:
        st.warning("비밀번호 미설정 — 누구나 들어올 수 있습니다. "
                   "Secrets 에 MOKI_PASSWORD 를 넣어주세요.", icon="🔓")
    if MOCK:
        st.warning("MOCK 모드 — API를 호출하지 않습니다", icon="🧪")
    st.metric("이번 세션 LLM 호출", st.session_state.llm_calls)
    st.caption("캐시에 있는 질문은 호출 0회입니다.")

    st.divider()
    if st.button("대화·장바구니 초기화", use_container_width=True):
        st.session_state.cart = Cart(table_id=cart.table_id)
        st.session_state.history = []
        st.session_state.turns = []
        st.rerun()

# ── 헤더 ────────────────────────────────────────────────────
st.markdown(
    '<div class="moki-head"><h1>모키 커피바</h1>'
    f'<span>Moki Coffee Bar · 좌석 {cart.table_id}번</span></div>',
    unsafe_allow_html=True)
st.caption("말로 주문하세요. 메뉴·성분·옵션을 묻고 바로 담을 수 있습니다.")

left, right = st.columns([1.45, 1])

# ── 왼쪽: 대화 ──────────────────────────────────────────────
with left:
    box = st.container(height=460, border=False)
    with box:
        if not st.session_state.history:
            st.markdown(
                '<div class="bubble-bot">안녕하세요, 모키입니다. 귀가 커서 손님 말씀을 잘 듣습니다.☕\n'
                '무엇을 드시고 싶으신가요? "산미 적고 고소한 커피 추천해줘" 처럼 말씀하셔도 됩니다.</div>',
                unsafe_allow_html=True)
        for i, m in enumerate(st.session_state.history):
            if m["role"] == "user":
                st.markdown(f'<div class="bubble-user">{html.escape(m["content"])}</div>',
                            unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="bubble-bot">{html.escape(m["content"])}</div>',
                            unsafe_allow_html=True)
                t = next((t for t in st.session_state.turns if t["idx"] == i), None)
                if t:
                    st.markdown(
                        f'<div class="meta">의도 {t["intent"]} · 검색 {t["ndocs"]}건 · '
                        f'LLM {t["calls"]}회{" · 캐시" if t["cached"] else ""}</div>',
                        unsafe_allow_html=True)

    prompt = st.chat_input("예: 아아 하나랑 약과 주세요 / Is yakgwa gluten-free?")

# ── 오른쪽: 장바구니 + 검색 내역 ────────────────────────────
with right:
    st.markdown("#### 🧾 주문 내역")
    if not cart.items:
        st.caption("아직 담긴 메뉴가 없습니다.")
    else:
        for idx, it in enumerate(cart.items):
            c1, c2 = st.columns([5, 1])
            opt = it.option_text()
            c1.markdown(
                f'<div class="cart-line"><b>{html.escape(it.name)}</b> '
                f'<span class="pill">{it.temp}/{it.size}</span>'
                + (f'<br><span style="color:#8A7A70;font-size:.82rem">{html.escape(opt)}</span>' if opt else "")
                + f'<br>×{it.qty} · {it.subtotal:,}원</div>',
                unsafe_allow_html=True)
            if c2.button("✕", key=f"del{idx}", help="빼기"):
                cart.remove(idx); st.rerun()
        st.markdown(f'<div class="cart-total">합계 {cart.total:,}원</div>',
                    unsafe_allow_html=True)
        if cart.status() == "pending_staff_check":
            st.warning("주류 포함 — 직원 나이 확인 대기", icon="🪪")
        if cart.order_no:
            st.success(f"주문번호 {cart.order_no} (시연용)", icon="✅")

    st.divider()
    st.markdown("#### 🔍 방금 검색한 근거")
    if st.session_state.turns:
        last = st.session_state.turns[-1]
        if last["rewritten"] != last["user"]:
            st.caption(f"재작성: {last['rewritten']}")
        for how, name, score in last["trace"][:7]:
            cls = "pill-cut" if "초과" in how else ("pill-rule" if "규칙" in how or "맛" in how else "pill-vec")
            st.markdown(
                f'<span class="pill {cls}">{how}</span> {html.escape(str(name))}'
                + (f' <span style="color:#A2928A;font-size:.78rem">{score}</span>' if score is not None else ""),
                unsafe_allow_html=True)
        with st.expander("모델에게 넘긴 문서 전체"):
            st.text(last["context"][:4000])
    else:
        st.caption("대화를 시작하면 어떤 문서를 근거로 답했는지 여기에 보입니다.")

# ── 입력 처리 ───────────────────────────────────────────────
if prompt:
    store = get_store()
    st.session_state.history.append({"role": "user", "content": prompt})
    with st.spinner("모키가 메뉴를 찾는 중..."):
        res = handle(prompt, store, cart, st.session_state.history[:-1])
    st.session_state.history.append({"role": "assistant", "content": res.reply})
    st.session_state.llm_calls += res.llm_calls
    st.session_state.turns.append({
        "idx": len(st.session_state.history) - 1,
        "user": prompt, "rewritten": res.rewritten, "intent": res.intent,
        "trace": res.trace, "ndocs": len(res.docs), "calls": res.llm_calls,
        "cached": res.cached,
        "context": "\n\n---\n\n".join(d.metadata.get("full", d.page_content) for d in res.docs),
    })
    st.rerun()

# ── TTS: 브라우저 음성합성 (무료, API 호출 없음) ────────────
if st.session_state.history:
    last_bot = next((m["content"] for m in reversed(st.session_state.history)
                     if m["role"] == "assistant"), "")
    with left:
        if st.button("🔊 마지막 답변 읽어주기", use_container_width=True):
            components.html(f"""
                <script>
                  const u = new SpeechSynthesisUtterance({json.dumps(last_bot)});
                  u.lang = {json.dumps('en-US' if last_bot.isascii() else 'ko-KR')};
                  u.rate = 1.0;
                  window.speechSynthesis.cancel();
                  window.speechSynthesis.speak(u);
                </script>""", height=0)
            st.caption("브라우저 음성합성을 사용합니다. API 비용이 들지 않습니다.")
