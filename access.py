from hashlib import sha256
from hmac import compare_digest
import os

import streamlit as st


def require_access() -> None:
    password = os.environ.get("APP_PASSWORD", "")
    if not password:
        if os.environ.get("DYNO"):
            st.error("Configura APP_PASSWORD en Heroku para habilitar el acceso.")
            st.stop()
        return
    token = sha256(password.encode("utf-8")).hexdigest()
    if compare_digest(st.session_state.get("access_token", ""), token):
        return
    with st.form("access_form"):
        st.subheader("Acceso")
        st.text_input("Contrase\u00f1a", type="password", key="access_password")
        submitted = st.form_submit_button("Entrar", icon=":material/login:")
    if submitted:
        entered = st.session_state.pop("access_password", "")
        if compare_digest(entered.encode("utf-8"), password.encode("utf-8")):
            st.session_state.access_token = token
            st.rerun()
        st.error("Contrase\u00f1a incorrecta.")
    st.stop()