"""Main Streamlit application - OCR Workbench."""
import os
import streamlit as st
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import components
from components.auth import show_login_form, show_logout_button, show_user_info
from services.state_manager import initialize_session_state
from services.theme import load_theme_css
from pages import instant_scan, book_management

# Page configuration
st.set_page_config(
    page_title="OCR Workbench",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Initialize session state
initialize_session_state()

# Load theme CSS
load_theme_css(st.session_state.theme)

# ============================================================================
# HEADER & AUTHENTICATION
# ============================================================================

# Top navigation bar
col_title, col_theme, col_logout = st.columns([7, 1, 2])

with col_title:
    st.title("📚 OCR Workbench")

with col_theme:
    # Theme toggle
    theme_button = "🌙" if st.session_state.theme == "light" else "☀️"
    if st.button(theme_button, use_container_width=True, key="theme_toggle"):
        st.session_state.theme = (
            "dark" if st.session_state.theme == "light" else "light"
        )
        load_theme_css(st.session_state.theme)
        st.rerun()

# ============================================================================
# AUTHENTICATION CHECK
# ============================================================================

if not st.session_state.auth_token:
    # Show login page
    st.divider()
    show_login_form()
else:
    # Show logout button and user info
    with col_logout:
        show_logout_button()

    st.divider()

    # Display logged-in user info
    col_user, col_spacer = st.columns([1, 9])
    with col_user:
        show_user_info()

    st.divider()

    # ========================================================================
    # MAIN APPLICATION - MODE SELECTION
    # ========================================================================

    # Mode selection
    mode = st.radio(
        "Select Mode",
        ["📸 Instant Scan", "📚 Book Management"],
        horizontal=True,
        key="app_mode_radio",
    )

    # Render selected page
    if mode == "📸 Instant Scan":
        instant_scan.render()
    elif mode == "📚 Book Management":
        book_management.render()

    # ========================================================================
    # BACKGROUND POLLING FOR ASYNC TASKS
    # ========================================================================

    # Auto-refresh logic for OCR tasks
    # Note: In production, this would use Streamlit's session state callbacks
    # For now, polling is handled in the component level during active processing

    st.divider()

    # Footer
    st.caption(
        "🔐 Multi-user OCR Workbench with async processing | "
        f"Backend: {st.session_state.backend_url}"
    )
