"""Theme management for Streamlit app."""
import streamlit as st


def load_theme_css(theme: str = "light"):
    """Load and apply theme CSS."""
    light_mode = """
    <style>
    :root {
        --bg-primary: #ffffff;
        --bg-secondary: #f7f6f3;
        --text-primary: #37352f;
        --text-secondary: #5b5551;
        --accent-color: #3b82f6;
        --border-color: #e5e0da;
    }
    
    body {
        background-color: var(--bg-primary);
        color: var(--text-primary);
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    }
    
    h1, h2, h3, h4, h5, h6 {
        color: var(--text-primary);
        font-weight: 600;
    }
    
    .stButton > button {
        background-color: var(--accent-color);
        color: white;
        border: none;
        border-radius: 4px;
    }
    
    .stButton > button:hover {
        background-color: #2563eb;
    }
    
    .stTextInput input, .stTextArea textarea {
        background-color: var(--bg-secondary);
        color: var(--text-primary);
        border-color: var(--border-color);
    }
    
    .ocr-text {
        color: var(--text-primary);
        line-height: 1.6;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    }
    
    .ocr-text b, .ocr-text strong {
        font-weight: 600;
    }
    
    .ocr-text i, .ocr-text em {
        font-style: italic;
    }
    
    .ocr-text u {
        text-decoration: underline;
    }
    
    .ocr-text s {
        text-decoration: line-through;
    }
    
    .status-badge {
        display: inline-block;
        padding: 4px 8px;
        border-radius: 4px;
        font-size: 12px;
        font-weight: 500;
    }
    
    .status-completed {
        background-color: #d1fae5;
        color: #065f46;
    }
    
    .status-processing {
        background-color: #fef3c7;
        color: #92400e;
    }
    
    .status-pending {
        background-color: #f3f4f6;
        color: #374151;
    }
    
    .status-failed {
        background-color: #fee2e2;
        color: #991b1b;
    }
    </style>
    """

    dark_mode = """
    <style>
    :root {
        --bg-primary: #1a1a1a;
        --bg-secondary: #262422;
        --text-primary: #e8e6e1;
        --text-secondary: #9a9691;
        --accent-color: #60a5fa;
        --border-color: #3a3633;
    }
    
    body {
        background-color: var(--bg-primary);
        color: var(--text-primary);
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    }
    
    h1, h2, h3, h4, h5, h6 {
        color: var(--text-primary);
        font-weight: 600;
    }
    
    .stButton > button {
        background-color: var(--accent-color);
        color: #1a1a1a;
        border: none;
        border-radius: 4px;
    }
    
    .stButton > button:hover {
        background-color: #93c5fd;
    }
    
    .stTextInput input, .stTextArea textarea {
        background-color: var(--bg-secondary);
        color: var(--text-primary);
        border-color: var(--border-color);
    }
    
    .ocr-text {
        color: var(--text-primary);
        line-height: 1.6;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    }
    
    .ocr-text b, .ocr-text strong {
        font-weight: 600;
    }
    
    .ocr-text i, .ocr-text em {
        font-style: italic;
    }
    
    .ocr-text u {
        text-decoration: underline;
    }
    
    .ocr-text s {
        text-decoration: line-through;
    }
    
    .status-badge {
        display: inline-block;
        padding: 4px 8px;
        border-radius: 4px;
        font-size: 12px;
        font-weight: 500;
    }
    
    .status-completed {
        background-color: #064e3b;
        color: #d1fae5;
    }
    
    .status-processing {
        background-color: #78350f;
        color: #fef3c7;
    }
    
    .status-pending {
        background-color: #374151;
        color: #f3f4f6;
    }
    
    .status-failed {
        background-color: #7f1d1d;
        color: #fee2e2;
    }
    </style>
    """

    css = dark_mode if theme == "dark" else light_mode
    st.markdown(css, unsafe_allow_html=True)
