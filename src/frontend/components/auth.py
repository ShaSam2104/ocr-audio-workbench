"""Authentication components."""
import streamlit as st
from services.api_client import APIClient


def show_login_form():
    """Display login form."""
    st.title("🔐 Login to OCR Workbench")

    with st.form("login_form"):
        username = st.text_input("Username", placeholder="Enter your username")
        password = st.text_input("Password", type="password", placeholder="Enter your password")
        submit = st.form_submit_button("🔓 Login", use_container_width=True)

        if submit and username and password:
            api_client = APIClient()
            result = api_client.login(username, password)

            if result:
                st.session_state.auth_token = result.get("access_token")
                st.session_state.user_id = result.get("user_id")
                st.session_state.username = result.get("username")
                st.success("✅ Login successful!")
                st.balloons()
                st.rerun()
            else:
                st.error("❌ Invalid username or password. Please try again.")
        elif submit:
            st.error("⚠️ Please enter both username and password.")


def show_logout_button():
    """Display logout button in top-right."""
    if st.button("🚪 Logout", key="logout_btn", use_container_width=True):
        st.session_state.clear()
        st.rerun()


def show_user_info():
    """Display user information."""
    if st.session_state.username:
        st.caption(f"👤 Logged in as: **{st.session_state.username}**")
    else:
        st.caption("Not logged in")
