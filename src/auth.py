"""비밀번호 게이트.

공개 배포하면 인터넷 누구나 들어와 조교님 공용 키로 API를 쓸 수 있다.
시크릿에 MOKI_PASSWORD 가 설정되어 있으면 통과해야 앱이 열린다.
로컬 개발에서는 비워 두면 잠기지 않는다.
"""
from __future__ import annotations
import hmac
import streamlit as st
from .config import APP_PASSWORD


def check() -> bool:
    if not APP_PASSWORD:              # 설정 안 하면 잠그지 않음 (로컬 개발)
        return True
    if st.session_state.get("_authed"):
        return True

    st.markdown("### ☕ 모키 커피바")
    st.caption("4조 시연용입니다. 조에서 공유한 비밀번호를 입력해 주세요.")
    pw = st.text_input("비밀번호", type="password", label_visibility="collapsed")
    if pw:
        if hmac.compare_digest(pw, APP_PASSWORD):
            st.session_state["_authed"] = True
            st.rerun()
        else:
            st.error("비밀번호가 맞지 않습니다.")
    st.info("공용 API 키를 쓰기 때문에 외부 공개를 막아 두었습니다.", icon="🔒")
    return False
