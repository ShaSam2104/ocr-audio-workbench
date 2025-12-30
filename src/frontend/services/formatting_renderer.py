"""Formatting renderer service."""
import streamlit as st
from utils.formatting import convert_markdown_to_html


def render_formatted_text(text_with_markdown: str, theme: str = "light"):
    """
    Render markdown-style tags as actual HTML formatting.

    Supports:
    - **bold text** → <b>bold text</b>
    - *italic text* → <i>italic text</i>
    - __underline text__ → <u>underline text</u>
    - ~~strikethrough~~ → <s>strikethrough</s>
    - ^superscript^ → <sup>superscript</sup>
    - ~subscript~ → <sub>subscript</sub>
    """
    if not text_with_markdown:
        st.info("No text to display")
        return

    html = convert_markdown_to_html(text_with_markdown)

    # Apply theme colors
    text_color = "#37352f" if theme == "light" else "#e8e6e1"
    theme_style = f"""
    <style>
        .ocr-text {{
            color: {text_color};
            line-height: 1.6;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            word-wrap: break-word;
        }}
        .ocr-text b, .ocr-text strong {{ font-weight: 600; }}
        .ocr-text i, .ocr-text em {{ font-style: italic; }}
        .ocr-text u {{ text-decoration: underline; }}
        .ocr-text s {{ text-decoration: line-through; }}
    </style>
    <div class="ocr-text">
        {html}
    </div>
    """

    st.markdown(theme_style, unsafe_allow_html=True)


def render_status_badge(status: str):
    """Render status badge with appropriate styling."""
    status_map = {
        "completed": ("✅ Completed", "status-completed"),
        "processing": ("⏳ Processing", "status-processing"),
        "pending": ("⏸️ Pending", "status-pending"),
        "failed": ("❌ Failed", "status-failed"),
        "queued": ("📋 Queued", "status-pending"),
    }

    if status not in status_map:
        return st.write(status)

    label, css_class = status_map[status]

    badge_html = f"""
    <span class="status-badge {css_class}">{label}</span>
    """
    st.markdown(badge_html, unsafe_allow_html=True)
