"""모키 커피바 — 좌석 태블릿 주문 화면.

실행:  streamlit run app.py
"""
from __future__ import annotations
import base64, html, json, mimetypes
from pathlib import Path
import streamlit as st
import streamlit.components.v1 as components

from src.config import (TABLES, MOCK, ROUTER_MODEL,
                        ensure_api_key, is_mock, secret_status)
from src.index import load_index
from src.cart import Cart, find_variants, list_menus
from src.content import content_status, source_cards
from src.kiosk import handle

st.set_page_config(page_title="모키 커피바", page_icon="☕", layout="wide")

from src.auth import check as _check_password
if not _check_password():
    st.stop()

ASSET_DIR = Path(__file__).resolve().parent / "public" / "assets"


def _asset_uri(filename: str) -> str:
    path = ASSET_DIR / filename
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"


HANOK_HERO_URI = _asset_uri("hanok-cafe-hero-v2.jpg")
MOKI_MASCOT_URI = _asset_uri("moki-mascot.png")
MOKI_CHAT_AVATAR_URI = _asset_uri("moki-listening-avatar.png")

CSS = """
<style>
:root {
  --ink:#25211e; --muted:#81766d; --wood:#34231d; --accent:#9b5b3d;
  --paper:#faf8f3; --card:#fffefa; --line:#e5dfd5; --soft:#f1ece4;
}
.stApp {
  background:var(--paper);
  color:var(--ink);
}
[data-testid="stHeader"] {background:transparent;}
.block-container {padding-top:1.4rem; padding-bottom:3rem; max-width:1220px;}
#MainMenu, footer {visibility:hidden;}
[data-testid="stSidebar"] {
  background:#f5f1ea;
  border-right:1px solid var(--line);
}
[data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3, [data-testid="stSidebar"] label,
[data-testid="stSidebar"] p {color:var(--ink);}
[data-testid="stSidebar"] hr {border-color:var(--line);}
.side-brand {padding:.45rem 0 1rem; text-align:left; border-bottom:1px solid var(--line); margin-bottom:1rem;}
.side-brand .brand-row {display:flex; align-items:center; gap:.7rem;}
.side-brand .stamp {display:grid; place-items:center; width:40px; height:40px; border-radius:50%;
  background:var(--wood); color:#f8f1e7; font-size:.95rem; letter-spacing:-.1em;}
.side-brand b {font-size:1rem; letter-spacing:.06em;}.side-brand small {display:block;color:var(--muted);margin-top:.1rem;}
.masthead {display:flex; align-items:center; justify-content:space-between; padding:.25rem .1rem 1rem;
  border-bottom:1px solid var(--line); margin-bottom:1rem;}
.mast-brand {font-size:.74rem;letter-spacing:.2em;font-weight:700;color:var(--wood);}
.table-chip {font-size:.72rem;color:var(--muted);border:1px solid var(--line);padding:.34rem .7rem;border-radius:999px;background:#fff;}
.hanok-hero {position:relative; overflow:hidden; display:flex; align-items:center; justify-content:space-between;
  min-height:142px; padding:1.8rem 2rem; margin:0 0 1.15rem; border:1px solid var(--line);
  border-radius:4px 4px 22px 22px; background:var(--card); box-shadow:0 14px 40px rgba(52,35,29,.055);}
.hanok-hero::before {content:"";position:absolute;inset:0 0 auto;height:5px;background:var(--wood);}
.hanok-hero::after {content:"";position:absolute;right:0;top:0;width:28%;height:100%;opacity:.12;
  background:linear-gradient(90deg,var(--wood) 1px,transparent 1px),linear-gradient(var(--wood) 1px,transparent 1px);
  background-size:28px 28px;mask-image:linear-gradient(90deg,transparent,#000);}
.hero-copy {position:relative;z-index:1;}.hero-kicker {font-size:.69rem;color:var(--accent);letter-spacing:.18em;font-weight:700;}
.hanok-hero h1 {margin:.35rem 0 .35rem;font-size:2.15rem;line-height:1.15;color:var(--ink);letter-spacing:-.055em;}
.hanok-hero p {margin:0;color:var(--muted);font-size:.88rem;}
.moki-mark {position:relative;z-index:1;text-align:center;width:76px;height:76px;display:grid;place-items:center;
  color:var(--wood);background:#f4ede3;border:1px solid #ded2c4;border-radius:50%;}
.moki-mark .face {font-size:1.12rem;line-height:1.15}.moki-mark small {display:block;font-size:.62rem;letter-spacing:.08em;margin-top:.2rem;}
div[data-testid="stVerticalBlockBorderWrapper"] {background:var(--card)!important;border:1px solid var(--line)!important;
  border-radius:16px!important;box-shadow:0 8px 26px rgba(50,38,31,.045);}
.section-head {display:flex;align-items:center;justify-content:space-between;margin:.05rem 0 .8rem;padding-bottom:.7rem;border-bottom:1px solid #eee9e1;}
.section-head b {font-size:.95rem;color:var(--ink);}.section-head span {font-size:.7rem;color:var(--muted);}
.bubble-user {background:var(--wood);color:#fff;padding:.7rem 1rem;border-radius:16px 16px 4px 16px;
  margin:.48rem 0 .48rem auto;max-width:82%;width:fit-content;box-shadow:0 4px 14px rgba(52,35,29,.1);}
.bubble-bot {background:var(--soft);color:var(--ink);padding:.75rem 1rem;border-radius:16px 16px 16px 4px;
  margin:.48rem auto .3rem 0;max-width:90%;width:fit-content;white-space:pre-wrap;}
.welcome-note,.quick-label {font-size:.72rem;color:var(--muted);margin:.4rem 0 .55rem;}
.quick-label {font-weight:700;color:var(--accent);}
.mode-notice {margin:0 0 .8rem;padding:.7rem .85rem;border:1px solid #e8d3ae;border-radius:12px;
  background:#fff8e9;color:#73552f;font-size:.76rem;line-height:1.55;}
.mode-notice b {color:#5e4224;}
.menu-note {font-size:.73rem;color:var(--muted);margin:.1rem 0 .75rem;}
.menu-title {font-size:.9rem;font-weight:760;color:var(--ink);margin:.12rem 0 0;white-space:nowrap;
  overflow:hidden;text-overflow:ellipsis;}
.menu-en {font-size:.67rem;color:var(--muted);height:1.1rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.menu-price {font-size:.78rem;color:var(--accent);font-weight:720;margin:.16rem 0 .42rem;}
.cart-line {font-size:.88rem;padding:.55rem .1rem;border-bottom:1px solid #eee9e1;}
.cart-total {font-weight:750;font-size:1.05rem;color:var(--ink);padding:.8rem 0 .15rem;}
.pill {display:inline-block;font-size:.65rem;padding:.14rem .48rem;border-radius:999px;background:#eee8df;color:#67564d;margin-right:.25rem;}
.pill-rule {background:#e9efe7;color:#476047;}.pill-vec {background:#e9edf1;color:#4b5965;}.pill-cut {background:#f3e6e2;color:#884c3b;}
.stButton > button {border:1px solid #dcd4ca;border-radius:10px;background:#fff;color:var(--ink);font-weight:650;
  box-shadow:none;transition:.15s ease;min-height:2.45rem;}
.stButton > button:hover {border-color:#a87359;color:var(--accent);background:#fbf7f1;transform:translateY(-1px);}
[data-testid="stChatInput"] {border:1px solid #ddd5cb;border-radius:13px;background:#fff;box-shadow:0 6px 18px rgba(50,38,31,.055);}
[data-testid="stMetric"] {background:#fff;border:1px solid var(--line);border-radius:12px;padding:.55rem .7rem;}

/* 첫 접속 때만 나타나는 한옥 미닫이문 인트로 */
.entry-overlay {position:fixed;inset:0;z-index:999999;background:#e8dfd0;overflow:hidden;
  animation:entry-away .55s ease 2.5s forwards;pointer-events:none;}
.entry-courtyard {position:absolute;inset:0;display:grid;place-items:center;text-align:center;color:#f9f4eb;
  background:radial-gradient(circle at 50% 52%,#9a694c 0,#51372d 42%,#211713 100%);}
.entry-courtyard::before {content:"";position:absolute;left:15%;right:15%;top:18%;height:16px;background:#1f1613;
  box-shadow:0 8px 0 #a06d48,0 16px 0 #1f1613;clip-path:polygon(0 100%,8% 0,92% 0,100% 100%);}
.entry-copy {position:relative;z-index:2;animation:entry-copy 2.35s ease forwards;}
.entry-copy b {display:block;font-size:1.65rem;letter-spacing:.28em;margin-right:-.28em;}
.entry-copy small {display:block;margin-top:.55rem;letter-spacing:.14em;color:#d8bf9f;font-size:.68rem;}
.hanok-door {position:absolute;top:0;width:50.3%;height:100%;z-index:3;background:#3a251d;
  border:14px solid #241713;box-shadow:0 0 35px rgba(0,0,0,.35);}
.hanok-door::before {content:"";position:absolute;inset:6%;border:9px solid #5b3928;
  background-color:#eadfca;background-image:linear-gradient(#6a4633 4px,transparent 4px),linear-gradient(90deg,#6a4633 4px,transparent 4px);
  background-size:100% 25%,25% 100%;box-shadow:inset 0 0 0 3px #2a1b16;}
.hanok-door::after {content:"";position:absolute;top:48%;width:13px;height:28px;border-radius:8px;background:#b78a50;box-shadow:0 0 0 4px #2a1b16;}
.door-left {left:0;transform-origin:left center;animation:door-left 1.55s cubic-bezier(.65,0,.25,1) .45s forwards;}
.door-right {right:0;transform-origin:right center;animation:door-right 1.55s cubic-bezier(.65,0,.25,1) .45s forwards;}
.door-left::after {right:8%;}.door-right::after {left:8%;}
@keyframes door-left {to{transform:translateX(-96%);}}
@keyframes door-right {to{transform:translateX(96%);}}
@keyframes entry-copy {0%,28%{opacity:0;transform:translateY(7px)}55%,88%{opacity:1;transform:none}100%{opacity:0}}
@keyframes entry-away {to{opacity:0;visibility:hidden;}}
@media (prefers-reduced-motion:reduce){.entry-overlay{animation:entry-away .1s linear .5s forwards}.hanok-door{animation-duration:.1s}}
@media (max-width:760px){.hanok-hero{padding:1.4rem 1.15rem;min-height:125px}.hanok-hero h1{font-size:1.7rem}
  .moki-mark{width:62px;height:62px}.block-container{padding-left:.75rem;padding-right:.75rem}.section-head span{display:none}}
</style>
"""
ASSET_CSS = """
<style>
.hanok-hero {
  min-height:310px; align-items:flex-end; padding:1.5rem;
  background-image:linear-gradient(90deg,rgba(25,18,14,.14),rgba(25,18,14,0) 64%),url("__HERO__");
  background-size:cover; background-position:center 48%;
  box-shadow:0 18px 44px rgba(42,31,24,.12);
}
.hanok-hero::after {display:none;}
.hero-copy {max-width:480px;padding:1.05rem 1.2rem;border:1px solid rgba(255,255,255,.72);
  border-radius:14px;background:rgba(255,252,245,.9);backdrop-filter:blur(10px);
  box-shadow:0 10px 30px rgba(41,28,20,.13);}
.hero-mascot {position:absolute;z-index:2;right:2.2rem;bottom:-1.25rem;width:190px;height:218px;
  background:url("__MOKI__") center bottom/contain no-repeat;
  filter:drop-shadow(0 12px 14px rgba(50,30,18,.2));}
.entry-courtyard {background-image:linear-gradient(rgba(34,23,17,.2),rgba(34,23,17,.52)),url("__HERO__");
  background-size:cover;background-position:center;}
.entry-copy {display:flex;flex-direction:column;align-items:center;}
.entry-moki {width:190px;height:205px;margin-bottom:.25rem;background:url("__MOKI__") center bottom/contain no-repeat;
  filter:drop-shadow(0 10px 14px rgba(0,0,0,.24));}
.bot-row {display:flex;align-items:flex-end;gap:.55rem;margin:.45rem 0 .55rem;max-width:94%;}
.moki-avatar {flex:0 0 58px;width:58px;height:58px;background:#fff4e5 url("__CHAT_AVATAR__") center/110% no-repeat;
  border:1px solid #ead7bd;border-radius:50%;filter:drop-shadow(0 3px 5px rgba(48,30,20,.12));transform-origin:center bottom;}
.bot-content {min-width:0;max-width:calc(100% - 60px);}
.moki-name {display:flex;align-items:center;gap:.38rem;margin:0 0 .22rem .2rem;font-size:.68rem;font-weight:750;
  color:#775441;letter-spacing:.04em;}
.moki-status {display:inline-flex;gap:2px;align-items:center;}
.moki-status i {width:3px;height:3px;border-radius:50%;background:#b67a58;animation:moki-dot 1.1s ease-in-out infinite;}
.moki-status i:nth-child(2){animation-delay:.15s}.moki-status i:nth-child(3){animation-delay:.3s}
.bot-row .bubble-bot {max-width:100%;margin:0;}
.bot-row.speaking .moki-avatar {animation:moki-talk 1.8s ease-in-out infinite;}
@keyframes moki-talk {0%,100%{transform:translateY(0) rotate(0)}45%{transform:translateY(-3px) rotate(-1.2deg)}70%{transform:translateY(-1px) rotate(1deg)}}
@keyframes moki-dot {0%,65%,100%{opacity:.3;transform:translateY(0)}35%{opacity:1;transform:translateY(-2px)}}
@media (max-width:760px){.hanok-hero{min-height:270px;padding:.8rem;background-position:center}.hero-copy{max-width:78%;padding:.8rem .9rem}
  .hero-mascot{right:.4rem;width:110px;height:132px}.moki-avatar{flex-basis:48px;width:48px;height:48px}.entry-moki{width:150px;height:165px}}
</style>
""".replace("__HERO__", HANOK_HERO_URI).replace("__MOKI__", MOKI_MASCOT_URI).replace(
    "__CHAT_AVATAR__", MOKI_CHAT_AVATAR_URI
)
st.markdown(CSS + ASSET_CSS, unsafe_allow_html=True)

if not st.session_state.get("_entry_seen"):
    st.session_state["_entry_seen"] = True
    st.markdown(
        '<div class="entry-overlay"><div class="entry-courtyard">'
        '<div class="entry-copy"><div class="entry-moki" role="img" aria-label="한복을 입은 모키"></div>'
        '<b>모키 커피바</b><small>MOKI · HANOK COFFEE BAR</small></div>'
        '</div><div class="hanok-door door-left"></div>'
        '<div class="hanok-door door-right"></div></div>',
        unsafe_allow_html=True,
    )


@st.cache_resource(show_spinner="메뉴 인덱스를 불러오는 중...")
def get_store(mock_mode: bool):
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
if "_use_mock" not in st.session_state:
    st.session_state._use_mock = MOCK

cart: Cart = st.session_state.cart

# ── 사이드바 ────────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        '<div class="side-brand"><div class="brand-row"><div class="stamp">모키</div><div>'
        '<b>모키 커피바</b><small>MOKI COFFEE BAR</small></div></div></div>',
        unsafe_allow_html=True)

    cart.table_id = st.selectbox("좌석 번호", TABLES,
                                 index=TABLES.index(cart.table_id or 5))

    _s = secret_status()
    with st.expander("🔑 API 연결", expanded=not _s["key_found"]):
        if _s["key_found"]:
            st.success(f"연결됨 · {_s['key_head']} ({_s['key_source']})")
        else:
            st.caption("OpenAI API 키를 입력하면 실제 AI 답변을 사용할 수 있어요.")

        entered_key = st.text_input(
            "OpenAI API key", type="password", placeholder="sk-...",
            key="_api_key_input",
        )
        if st.button("키 적용", key="apply_api_key", use_container_width=True):
            cleaned_key = entered_key.strip()
            if not cleaned_key.startswith("sk-"):
                st.error("`sk-`로 시작하는 OpenAI API 키를 입력해 주세요.")
            else:
                st.session_state._openai_api_key = cleaned_key
                st.session_state._use_mock = False
                st.rerun()
        st.caption("입력한 키는 저장소나 파일에 저장하지 않습니다.")

    st.toggle(
        "화면 체험 모드 (프롬프트 미사용)", key="_use_mock",
        help="API를 호출하지 않는 UI 시험 모드입니다. 끄면 연결된 키로 실제 프롬프트와 검색을 사용합니다.",
    )
    if not is_mock() and not ensure_api_key():
        st.error("실제 AI 모드에는 API 키가 필요합니다.", icon="🔑")
    elif is_mock():
        st.caption("현재는 API를 호출하지 않는 화면 체험 모드입니다.")
    else:
        st.caption(f"실제 AI · {ROUTER_MODEL}")

    st.divider()
    _content = content_status()
    st.markdown("**콘텐츠 연결**")
    if _content["ready"]:
        st.caption(
            f"메뉴 {_content['menu_count']}개 · 검색 문서 {_content['document_count']}개 · "
            f"사진 {_content['image_count']}장"
        )
        if is_mock():
            st.caption("AI 응대 규칙은 API 연결 후 적용됩니다.")
        else:
            st.success("메뉴 데이터와 AI 응대 규칙이 연결되었습니다.")
    else:
        for content_error in _content["errors"]:
            st.error(content_error)

    st.divider()
    st.markdown("**매장 설정**")
    cart.staff_checked = st.toggle(
        "직원 나이 확인 완료", value=cart.staff_checked,
        help="주류 주문은 직원 확인 후에만 확정됩니다.")
    st.caption("메뉴 가격과 옵션은 서버가 데이터 원장과 다시 확인합니다.")

    st.divider()
    if st.button("대화·장바구니 초기화", use_container_width=True):
        st.session_state.cart = Cart(table_id=cart.table_id)
        st.session_state.history = []
        st.session_state.turns = []
        st.rerun()

# ── 헤더 ────────────────────────────────────────────────────
st.markdown(
    '<div class="masthead"><div class="mast-brand">MOKI COFFEE BAR</div>'
    f'<div class="table-chip">TABLE {cart.table_id:02d}</div></div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="hanok-hero"><div class="hero-copy">'
    '<div class="hero-kicker">A QUIET CUP IN HANOK</div>'
    '<h1>오늘의 한 잔을<br>천천히 골라보세요.</h1>'
    '<p>메뉴 추천부터 주문 옵션까지, 모키가 차분히 도와드릴게요.</p>'
    '</div><div class="hero-mascot" role="img" aria-label="손을 흔들며 커피를 든 모키"></div></div>',
    unsafe_allow_html=True)

selected_quick: str | None = None


def _menu_price(menu_id: str) -> str:
    prices = sorted({int(row["가격(원)"]) for row in find_variants(menu_id)})
    if not prices:
        return "가격 확인 필요"
    return f"{prices[0]:,}원" if len(prices) == 1 else f"{prices[0]:,}원부터"


# ── 데이터 파일의 대표 사진 메뉴판 ─────────────────────────
with st.expander("📸 사진 메뉴판 · 33개 메뉴", expanded=True):
    st.markdown(
        '<div class="menu-note">데이터 파일의 ‘사진메뉴판’ 시트에 포함된 대표 AI 연출 이미지입니다. '
        '온도·크기·옵션에 따라 실제 모습은 달라질 수 있습니다.</div>',
        unsafe_allow_html=True,
    )
    categories = ["커피", "차/논커피", "디저트", "주류", "원두"]
    category = st.radio(
        "분류", categories, horizontal=True, label_visibility="collapsed",
        key="menu_photo_category",
    )
    visible_menus = [menu for menu in list_menus() if menu.get("분류") == category]
    menu_columns = st.columns(4)
    for menu_index, menu in enumerate(visible_menus):
        menu_id = str(menu["메뉴 ID"])
        menu_name = str(menu["메뉴명"])
        with menu_columns[menu_index % len(menu_columns)]:
            with st.container(border=True):
                st.image(
                    str(ASSET_DIR / "menu" / f"{menu_id}.jpg"),
                    width="stretch",
                    alt=str(menu.get("사진 설명") or menu_name),
                )
                st.markdown(
                    f'<div class="menu-title">{html.escape(menu_name)}</div>'
                    f'<div class="menu-en">{html.escape(str(menu.get("영문명") or ""))}</div>'
                    f'<div class="menu-price">{_menu_price(menu_id)}</div>',
                    unsafe_allow_html=True,
                )
                if st.button(
                    "모키에게 물어보기", key=f"ask_menu_{menu_id}",
                    use_container_width=True,
                ):
                    selected_quick = f"{menu_name}에 대해 자세히 알려주세요"

left, right = st.columns([1.45, 1])

# ── 왼쪽: 대화 ──────────────────────────────────────────────
with left:
    with st.container(border=True):
        st.markdown(
            '<div class="section-head"><b>☕ 대화 마루</b>'
            '<span>말하거나 버튼을 눌러 주문하세요</span></div>',
            unsafe_allow_html=True)
        if is_mock():
            st.markdown(
                '<div class="mode-notice"><b>화면 체험 모드</b> · 이 모드에서는 시스템 프롬프트와 '
                '실제 AI를 사용하지 않습니다. 자연스러운 대화는 왼쪽 <b>API 연결</b>에서 키를 '
                '적용하면 시작됩니다.</div>',
                unsafe_allow_html=True,
            )
        box = st.container(height=410, border=False)
        with box:
            if not st.session_state.history:
                st.markdown(
                    '<div class="bot-row speaking"><div class="moki-avatar" role="img" aria-label="모키"></div>'
                    '<div class="bot-content"><div class="moki-name">모키 <span class="moki-status">'
                    '<i></i><i></i><i></i></span></div>'
                    '<div class="bubble-bot">어서 오세요. 모키가 주문을 듣고 있어요. ☕\n'
                    '메뉴 추천부터 알레르기·옵션 확인까지 편하게 말씀해 주세요.</div></div></div>'
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
                    latest = i == len(st.session_state.history) - 1
                    status_html = ('<span class="moki-status"><i></i><i></i><i></i></span>'
                                   if latest else "")
                    row_class = "bot-row speaking" if latest else "bot-row"
                    st.markdown(
                        f'<div class="{row_class}"><div class="moki-avatar" role="img" aria-label="모키"></div>'
                        f'<div class="bot-content"><div class="moki-name">모키 {status_html}</div>'
                        f'<div class="bubble-bot">{html.escape(m["content"])}</div></div></div>',
                        unsafe_allow_html=True,
                    )

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
            '<div class="section-head"><b>📖 답변에 참고한 정보</b>'
            '<span>메뉴·원두·매장 안내</span></div>',
            unsafe_allow_html=True)
        if st.session_state.turns:
            last = st.session_state.turns[-1]
            for source in last.get("sources", [])[:7]:
                st.markdown(
                    f'<span class="pill pill-rule">{html.escape(source["label"])}</span> '
                    f'{html.escape(source["name"])}',
                    unsafe_allow_html=True,
                )
            if not last.get("sources"):
                st.caption("이번 답변에는 별도의 메뉴 자료가 필요하지 않았습니다.")
            with st.expander("참고한 데이터 내용"):
                st.text(last["context"][:4000])
        else:
            st.caption("대화를 시작하면 답변에 사용한 메뉴와 안내 자료가 표시됩니다.")

# ── 입력 처리 ───────────────────────────────────────────────
if prompt and not is_mock() and not ensure_api_key():
    st.error("먼저 왼쪽의 **API 연결**에서 키를 입력하거나 데모 모드를 켜주세요.", icon="🔑")
elif prompt:
    store = get_store(is_mock())
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
        "sources": source_cards(res.docs),
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
        if st.button("🔊 모키 목소리로 마지막 답변 듣기", use_container_width=True):
            components.html(f"""
                <script>
                  const u = new SpeechSynthesisUtterance({json.dumps(last_bot)});
                  u.lang = {json.dumps('en-US' if last_bot.isascii() else 'ko-KR')};
                  u.rate = 1.0;
                  window.speechSynthesis.cancel();
                  window.speechSynthesis.speak(u);
                </script>""", height=0)
            st.caption("브라우저 음성합성을 사용합니다. API 비용이 들지 않습니다.")
