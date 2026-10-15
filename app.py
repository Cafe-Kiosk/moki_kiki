"""모키 커피바 — 좌석 태블릿 주문 화면.

실행:  streamlit run app.py
"""
from __future__ import annotations
import html, json
import streamlit as st
import streamlit.components.v1 as components

from src.config import (TABLES, MOCK, ROUTER_MODEL, ANSWER_MODEL,
                        ensure_api_key, secret_status)
from src.index import load_index, active_index_dir
from src.cart import Cart
from src.kiosk import handle

st.set_page_config(page_title="모키 커피바", page_icon="☕", layout="wide")

from src.auth import check as _check_password
if not _check_password():
    st.stop()

CSS = """
<style>
:root {
  --ink:#2d211d; --wood:#3f251c; --wood-deep:#261713; --wood-soft:#6d4634;
  --hanji:#fbf6eb; --hanji-deep:#efe3cc; --amber:#d69a45; --persimmon:#a64e35;
  --pine:#53624d; --line:rgba(91,57,39,.18);
}
.stApp {
  background:
    radial-gradient(circle at 12% 8%, rgba(214,154,69,.14), transparent 26rem),
    linear-gradient(90deg, rgba(63,37,28,.045) 1px, transparent 1px),
    linear-gradient(#f8f1e4, #f3eadb);
  background-size:auto, 34px 34px, auto;
  color:var(--ink);
}
.stApp::before {
  content:""; position:fixed; inset:0 0 auto 0; height:10px; z-index:999;
  background:repeating-linear-gradient(90deg, var(--wood-deep) 0 72px, #6b412e 72px 78px);
  box-shadow:0 3px 12px rgba(38,23,19,.28);
}
[data-testid="stHeader"] {background:transparent;}
.block-container {padding-top:1.35rem; padding-bottom:2.5rem; max-width:1280px;}
[data-testid="stSidebar"] {
  background:linear-gradient(180deg, #2b1a15 0%, #45291f 58%, #2d1b16 100%);
  border-right:1px solid rgba(214,154,69,.4);
}
[data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3, [data-testid="stSidebar"] label,
[data-testid="stSidebar"] p {color:#f8eddb;}
[data-testid="stSidebar"] hr {border-color:rgba(247,230,201,.16);}
.side-brand {padding:.3rem 0 .8rem; text-align:center;}
.side-brand .stamp {display:inline-grid; place-items:center; width:54px; height:54px; border-radius:18px;
  background:#f4e5cb; color:#4a2d22; font-size:1.55rem; border:2px solid #c98a3d;
  box-shadow:0 8px 24px rgba(0,0,0,.22);}
.side-brand b {display:block; margin-top:.55rem; font-size:1.05rem; letter-spacing:.08em;}
.side-brand small {color:#d7b98e;}
.hanok-hero {position:relative; overflow:hidden; display:flex; align-items:center; justify-content:space-between;
  min-height:150px; padding:1.45rem 1.8rem 1.25rem; margin:.25rem 0 1.1rem;
  color:#fff9ed; border:1px solid rgba(214,154,69,.65); border-radius:8px 8px 22px 22px;
  background:linear-gradient(125deg, #271713 0%, #4b2c21 55%, #6a3c28 100%);
  box-shadow:0 16px 38px rgba(60,35,25,.18);}
.hanok-hero::before {content:""; position:absolute; top:0; left:0; right:0; height:16px;
  background:repeating-linear-gradient(90deg,#17100d 0 78px,#825239 78px 86px);
  box-shadow:0 5px 0 rgba(214,154,69,.25);}
.hanok-hero::after {content:""; position:absolute; right:10%; top:14px; width:54px; height:72px;
  background:radial-gradient(circle,#ffd992 0 15%,#d8993f 16% 34%,rgba(216,153,63,.18) 35% 62%,transparent 63%);
  filter:drop-shadow(0 8px 12px rgba(255,185,76,.3));}
.hero-copy {position:relative; z-index:1;}
.hero-kicker {font-size:.72rem; color:#e8bd78; letter-spacing:.18em; font-weight:700;}
.hanok-hero h1 {margin:.2rem 0 .25rem; font-size:2.25rem; color:#fffaf0; letter-spacing:-.04em;}
.hanok-hero p {margin:0; color:#e9d9c3; font-size:.9rem;}
.moki-mark {position:relative; z-index:1; min-width:116px; text-align:center; padding:.7rem .75rem;
  color:#3a251e; background:#f7ecd8; border:1px solid #d4a65f; border-radius:44% 44% 18px 18px;
  box-shadow:inset 0 0 0 4px rgba(255,255,255,.38),0 10px 24px rgba(0,0,0,.2);}
.moki-mark .face {font-size:1.55rem; letter-spacing:.08em;}.moki-mark small {display:block;font-weight:700;font-size:.7rem;}
div[data-testid="stVerticalBlockBorderWrapper"] {background:rgba(255,252,244,.88)!important;
  border:1px solid var(--line)!important; border-radius:18px!important;
  box-shadow:0 10px 28px rgba(66,42,30,.08); backdrop-filter:blur(8px);}
.section-head {display:flex; align-items:center; justify-content:space-between; margin:.05rem 0 .7rem;}
.section-head b {font-size:1.02rem; color:var(--wood);}.section-head span {font-size:.72rem;color:#9a7b65;}
.bubble-user {background:linear-gradient(135deg,#6a4030,#8a5138); color:#fffaf1;
  padding:.68rem .95rem; border-radius:16px 16px 4px 16px; margin:.38rem 0 .38rem auto;
  max-width:82%; width:fit-content; box-shadow:0 5px 14px rgba(71,40,28,.12);}
.bubble-bot {background:#fffaf0; color:#30231e; padding:.72rem .95rem; border-radius:16px 16px 16px 4px;
  border:1px solid #eadcc5; border-left:4px solid var(--amber); margin:.38rem auto .28rem 0;
  max-width:90%; width:fit-content; white-space:pre-wrap; box-shadow:0 5px 14px rgba(71,40,28,.07);}
.welcome-note {font-size:.73rem;color:#8c6b54;margin:.1rem 0 .65rem;}
.quick-label {font-size:.72rem; color:#8a684f; margin:.35rem 0 .25rem; font-weight:700; letter-spacing:.02em;}
.meta {font-size:.7rem; color:#a18876; margin:.1rem 0 .55rem 0; font-family:ui-monospace,monospace;}
.cart-line {font-size:.9rem; padding:.48rem .15rem; border-bottom:1px dashed #dfcfb7;}
.cart-total {font-weight:800; font-size:1.08rem; color:var(--wood); padding:.7rem 0 .15rem;}
.pill {display:inline-block; font-size:.68rem; padding:.12rem .46rem; border-radius:999px;
  background:#efe3d1; color:#704a36; margin-right:.25rem; font-family:ui-monospace,monospace;}
.pill-rule {background:#e3eadf; color:#43593f;}.pill-vec {background:#e6e8e4; color:#445244;}
.pill-cut {background:#f2dfd9; color:#8a3f31;}
.stButton > button {border:1px solid #d8bd96; border-radius:12px; background:#fffaf0; color:#573729;
  font-weight:700; box-shadow:0 3px 9px rgba(76,46,31,.06); transition:.15s ease;}
.stButton > button:hover {border-color:var(--amber); color:#7c3c28; background:#fff4df;
  transform:translateY(-1px); box-shadow:0 6px 14px rgba(76,46,31,.1);}
[data-testid="stChatInput"] {border:1px solid #d7bea0; border-radius:14px; background:#fffdf7;
  box-shadow:0 4px 14px rgba(70,42,28,.07);}
@media (max-width:760px) {.hanok-hero{padding:1.35rem 1.05rem;min-height:130px}.hanok-hero h1{font-size:1.75rem}
  .moki-mark{display:none}.block-container{padding-left:.8rem;padding-right:.8rem}}
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
    st.markdown(
        '<div class="side-brand"><div class="stamp">☕</div>'
        '<b>모키 커피바</b><small>MOKI · HANOK COFFEE BAR</small></div>',
        unsafe_allow_html=True)

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
    st.caption(f"인덱스 {'있음' if (active_index_dir() / 'index.faiss').exists() else '없음'}")
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
    '<div class="hanok-hero"><div class="hero-copy">'
    '<div class="hero-kicker">MOKI · HANOK COFFEE BAR</div>'
    '<h1>오늘도, 모키에서</h1>'
    f'<p>따뜻한 한옥 카페바 · 좌석 {cart.table_id}번에서 편하게 주문하세요.</p>'
    '</div><div class="moki-mark"><div class="face">ᘏ⑅ᘏ ☕</div>'
    '<small>귀 기울여 듣는 모키</small></div></div>',
    unsafe_allow_html=True)

left, right = st.columns([1.45, 1])
selected_quick: str | None = None

# ── 왼쪽: 대화 ──────────────────────────────────────────────
with left:
    with st.container(border=True):
        st.markdown(
            '<div class="section-head"><b>☕ 대화 마루</b>'
            '<span>말하거나 버튼을 눌러 주문하세요</span></div>',
            unsafe_allow_html=True)
        box = st.container(height=410, border=False)
        with box:
            if not st.session_state.history:
                st.markdown(
                    '<div class="bubble-bot">어서 오세요. 모키가 귀를 쫑긋 세우고 주문을 듣고 있어요. ☕\n'
                    '메뉴 추천부터 알레르기·옵션 확인까지 편하게 말씀해 주세요.</div>'
                    '<div class="welcome-note">어디서 시작할지 고민되면 아래에서 골라보세요.</div>',
                    unsafe_allow_html=True)
                starters = [
                    ("☕ 커피 추천", "산미가 적고 고소한 커피를 추천해 주세요"),
                    ("🍵 논커피 추천", "커피가 아닌 음료를 추천해 주세요"),
                    ("🍰 디저트 보기", "커피와 잘 어울리는 디저트를 알려주세요"),
                ]
                starter_cols = st.columns(len(starters))
                for starter_idx, ((label, value), column) in enumerate(zip(starters, starter_cols)):
                    if column.button(label, key=f"starter_{starter_idx}", use_container_width=True):
                        selected_quick = value

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

                    replies = m.get("quick_replies") or []
                    if i == len(st.session_state.history) - 1 and replies:
                        st.markdown('<div class="quick-label">아래에서 선택해 주세요</div>',
                                    unsafe_allow_html=True)
                        quick_cols = st.columns(min(len(replies), 2))
                        for reply_idx, reply in enumerate(replies):
                            column = quick_cols[reply_idx % len(quick_cols)]
                            if column.button(
                                reply["label"], key=f"quick_{i}_{reply_idx}",
                                use_container_width=True,
                            ):
                                selected_quick = reply["value"]

    typed_prompt = st.chat_input("예: 아아 하나랑 약과 주세요 / Is yakgwa gluten-free?")
    prompt = selected_quick or typed_prompt

# ── 오른쪽: 장바구니 + 검색 내역 ────────────────────────────
with right:
    with st.container(border=True):
        st.markdown(
            '<div class="section-head"><b>🧾 주문 내역</b>'
            f'<span>좌석 {cart.table_id}번</span></div>',
            unsafe_allow_html=True)
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
                    cart.remove(idx)
                    st.rerun()
            st.markdown(f'<div class="cart-total">합계 {cart.total:,}원</div>',
                        unsafe_allow_html=True)
            if cart.status() == "pending_staff_check":
                st.warning("주류 포함 — 직원 나이 확인 대기", icon="🪪")
            if cart.order_no:
                st.success(f"주문번호 {cart.order_no} (시연용)", icon="✅")

    with st.container(border=True):
        st.markdown(
            '<div class="section-head"><b>🔍 방금 검색한 근거</b>'
            '<span>모키가 참고한 메뉴·정책</span></div>',
            unsafe_allow_html=True)
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
    st.session_state.history.append({
        "role": "assistant", "content": res.reply,
        "quick_replies": res.quick_replies,
    })
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
