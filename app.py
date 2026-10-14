"""모키 커피바 — 테이블에서 글로 주문하는 시연용 화면."""
from __future__ import annotations
import json
from dataclasses import replace
import streamlit as st
import streamlit.components.v1 as components
from src.config import TABLES, MOCK, ensure_api_key
from src.index import load_index
from src.cart import Cart, OPTION_FIELDS, CHOICES, option_rules, find_variants
from src.kiosk import handle
from src.auth import check as check_password

st.set_page_config(page_title="모키 커피바", page_icon="☕", layout="wide")
if not check_password(): st.stop()
if "cart" not in st.session_state: st.session_state.cart = Cart(table_id=5)
if "history" not in st.session_state: st.session_state.history = []
if "trace" not in st.session_state: st.session_state.trace = []
cart = st.session_state.cart

def variant_label(v):
    en = cart.language == "en"
    temp = ({"HOT":"Hot","ICED":"Iced","NA":""} if en else {"HOT":"따뜻하게","ICED":"아이스","NA":""})[v["온도"]]
    size = ({"S":"Small","L":"Large","ONE":"One serving","PACK":"200g bag"} if en else {"S":"작은 컵","L":"큰 컵","ONE":"기본 제공량","PACK":"200g 한 봉지"})[v["크기"]]
    return " · ".join(x for x in (temp,size) if x) + f" · {v['가격(원)']:,} KRW"

option_labels = {None:"기본 / Standard", "B01":"하우스 / House","B02":"에티오피아 / Ethiopian","B03":"디카페인 / Decaf",
                 "dairy":"일반 우유 / Dairy","lowfat":"저지방 우유 / Low-fat","oat":"오트 / Oat","soy":"두유 / Soy",
                 "normal":"기본 / Standard","less":"적게 / Less","room":"기본 제공 / Standard","warm":"데우기 / Warmed"}

@st.cache_resource
def get_store(): return load_index()

def change_language():
    st.session_state.cart.language = st.session_state.ui_language

def change_table():
    c = st.session_state.cart
    if not c.order_no: c.table_id = st.session_state.ui_table; c._changed()

def change_service():
    try: st.session_state.cart.set_service(st.session_state.ui_service)
    except ValueError as exc: st.session_state.settings_error = str(exc)

with st.sidebar:
    st.subheader("이용 설정 / Settings")
    st.session_state.ui_language = cart.language
    st.session_state.ui_table = cart.table_id or 5
    st.session_state.ui_service = cart.service_mode
    st.selectbox("언어 / Language", ["ko", "en"], key="ui_language", on_change=change_language)
    st.selectbox("좌석 / Table", TABLES, key="ui_table", on_change=change_table, disabled=bool(cart.order_no))
    st.selectbox("이용 방식 / Service", ["dine_in", "takeout"], key="ui_service", on_change=change_service, disabled=bool(cart.order_no))
    if st.session_state.get("settings_error"): st.error(st.session_state.pop("settings_error"))
    font = st.slider("글자 크기 / Text size", 16, 24, 18)
    contrast = st.checkbox("높은 대비 / High contrast")
    if cart.avoid_allergens: st.caption("피할 성분 / Avoid: " + ", ".join(cart.avoid_allergens))
    if cart.max_caffeine_mg is not None: st.caption(f"카페인 상한 / Caffeine limit: {cart.max_caffeine_mg}mg")
    st.caption("주류는 직원 확인 대기까지 지원합니다. 손님이 직원 인증을 대신할 수 없습니다.")
    st.caption("실제 결제·매장 접수·직원 호출은 연결하지 않은 과제 시연입니다.")
    if MOCK: st.warning("화면 시험용 가짜 응답 모드")
    if st.button("대화 새로 시작 / Clear conversation"):
        st.session_state.history = []; st.session_state.trace = []; st.rerun()
    if cart.previous_orders:
        with st.expander("확정한 과거 주문 / Previous orders"):
            for order in cart.previous_orders:
                st.write(order["order_no"], order["total_krw"], "KRW")

st.markdown(f"""<style>
.block-container {{max-width:1200px;padding-top:2rem}}
.stMarkdown p,.stChatMessage p {{font-size:{font}px}}
{"[data-testid='stAppViewContainer'] {background:#fff;color:#111}" if contrast else ""}
</style>""", unsafe_allow_html=True)
st.title("☕ 모키 커피바 · Moki Coffee Bar")
st.caption("테이블에서 글로 대화하며 주문하세요. / Type your questions and order at your table.")
left, right = st.columns([1.4, 1])
with right:
    st.subheader("주문 내역 / Your order")
    st.text(cart.as_text())
    if cart.has_alcohol: st.warning("직원 확인 대기 / Staff verification required")
    for idx, it in enumerate(cart.items):
        with st.expander(f"{idx+1}. {it.name} 수정 / Edit", expanded=False):
            if cart.order_no:
                st.caption("확정한 주문은 보존합니다. 추가 주문을 시작해 주세요.")
                continue
            vlist = find_variants(it.menu_id); vids = [v["주문 단위 ID"] for v in vlist]
            vid = st.selectbox("온도·크기 / Variant", vids, index=vids.index(it.variant_id), key="v"+it.line_id, format_func=lambda key:variant_label(next(v for v in vlist if v["주문 단위 ID"]==key)))
            quantity = st.number_input("수량 / Quantity",1,10,it.qty,key="q"+it.line_id)
            opts = {}
            for name in OPTION_FIELDS:
                rule = option_rules()[name]
                if it.menu_id not in {x.strip() for x in rule["적용 메뉴 ID"].split(",")}: continue
                choices = list(range(3)) if name=="extra_shots" else sorted(CHOICES[name])
                values = choices if name == "extra_shots" else [None] + choices
                current = getattr(it,name)
                opts[name] = st.selectbox(rule["옵션명"],values,index=values.index(current),key=name+it.line_id,format_func=lambda value:option_labels.get(value,str(value)))
            if st.button("변경 적용 / Apply",key="edit"+it.line_id):
                try:
                    v=next(v for v in vlist if v["주문 단위 ID"]==vid)
                    candidate=cart.validate_item(replace(it,variant_id=vid,temp=v["온도"],size=v["크기"],qty=quantity,**opts))
                    cart._editable();cart.remember();cart.items[idx]=candidate;cart._changed();st.rerun()
                except ValueError as exc: st.error(str(exc))
            if st.button("품목 삭제 / Remove",key="remove"+it.line_id):
                cart.remove(idx);st.rerun()
    if cart.undo_state is not None and not cart.order_no and st.button("직전 변경 되돌리기 / Undo last change"):
        try: cart.undo();st.rerun()
        except ValueError as exc: st.error(str(exc))
    if cart.order_no:
        st.success("시연 주문 확정 / Demo order confirmed")
        if st.button("추가 주문 시작 / Additional order"):
            cart.start_additional(); st.rerun()
    else:
        if st.button("최종 내역 확인 / Review order"):
            cart.review();st.rerun()
        if st.button("이 내역으로 시연 확정 / Confirm demo order",disabled=cart.reviewed_version!=cart.version):
            ok,msg=cart.confirm()
            if ok: st.rerun()
            else: st.error(msg)
    with st.expander("검색 근거 / Retrieved sources"):
        for doc in st.session_state.trace: st.write(doc.metadata["doc_id"],doc.metadata["name"])
        if st.session_state.trace: st.text("\n\n".join(d.metadata["full"] for d in st.session_state.trace))

with left:
    with st.expander("메뉴 둘러보기 / Browse menu"):
        from src.cart import _tables
        menus,_ = _tables()
        category = st.selectbox("메뉴 분류 / Category", ["전체 / All"] + list(dict.fromkeys(m["분류"] for m in menus.values())))
        for mid,m in menus.items():
            if category != "전체 / All" and m["분류"] != category: continue
            name=m.get("영문명") if cart.language=="en" else m["메뉴명"]
            st.markdown("**"+name+"**")
            st.caption(" / ".join(variant_label(v) for v in find_variants(mid)))
    for message in st.session_state.history:
        with st.chat_message(message["role"]):st.write(message["content"])
    prompt=st.chat_input("예: 산미 적은 커피와 빵 추천 / Recommend coffee and dessert")
    if prompt:
        if not MOCK and not ensure_api_key():
            st.error("실행 환경에 OPENAI_API_KEY를 설정해 주세요. 주문은 변경되지 않았습니다.")
        else:
            try:
                store=get_store()
                with st.spinner("메뉴를 확인하는 중 / Checking your request"):
                    result=handle(prompt,store,cart,st.session_state.history)
                st.session_state.history += [{"role":"user","content":prompt},{"role":"assistant","content":result.reply}]
                st.session_state.trace=result.docs;st.rerun()
            except Exception:
                st.error("실행 자료를 불러오지 못했습니다. 데이터와 인덱스 설정을 확인해 주세요.")
    last=next((m["content"] for m in reversed(st.session_state.history) if m["role"]=="assistant"),"")
    if last and st.button("🔊 마지막 답변 읽기 / Read last answer"):
        # JSON text is embedded in a script: escape closing tags from untrusted replies.
        text=json.dumps(last).replace("<","\\u003c")
        language=json.dumps("en-US" if cart.language=="en" else "ko-KR")
        components.html(f"<script>const u=new SpeechSynthesisUtterance({text});u.lang={language};speechSynthesis.cancel();speechSynthesis.speak(u);</script>",height=0)
