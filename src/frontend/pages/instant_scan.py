"""Instant Scan page - quick OCR and transcription."""
import streamlit as st
from services.api_client import APIClient
from components.ocr_status import render_ocr_status_dashboard, show_ocr_button
from components.transcription_status import (
    render_transcription_status_dashboard,
    show_transcribe_button,
)
from services.formatting_renderer import render_formatted_text
import os


def render():
    """Render instant scan page."""
    api_client = APIClient()
    api_client.set_token(st.session_state.auth_token)

    st.title("📸 Instant Scan")
    st.markdown("Quick ad-hoc OCR and audio transcription without creating a book.")

    # Create tabs for images and audio
    tab_images, tab_audio = st.tabs(["📷 Images & PDFs", "🎵 Audio Files"])

    with tab_images:
        render_image_scan(api_client)

    with tab_audio:
        render_audio_scan(api_client)


def render_image_scan(api_client: APIClient):
    """Render image scanning interface."""
    st.subheader("Upload Images or PDFs")

    uploaded_files = st.file_uploader(
        "Select images or PDFs",
        type=["jpg", "jpeg", "png", "pdf"],
        accept_multiple_files=True,
        label_visibility="collapsed",
    )

    if uploaded_files:
        st.info(f"📁 {len(uploaded_files)} file(s) selected")

        # File type summary
        image_count = sum(1 for f in uploaded_files if f.type.startswith("image"))
        pdf_count = sum(1 for f in uploaded_files if f.type == "application/pdf")

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Images", image_count)
        with col2:
            st.metric("PDFs", pdf_count)

        # Crop option
        crop_option = st.checkbox("✂️ Crop images before OCR?")

        if crop_option:
            st.info("💡 Crop feature coming soon!")

        # Process button
        if st.button("🔍 Extract Text", key="instant_ocr", use_container_width=True):
            with st.spinner("📤 Processing images..."):
                st.info(
                    "✅ Files processed! (Integration with Book Management required for full OCR)"
                )


def render_audio_scan(api_client: APIClient):
    """Render audio scanning interface."""
    st.subheader("Upload Audio Files")

    audio_files = st.file_uploader(
        "Select audio files",
        type=["mp3", "wav", "m4a", "ogg", "flac"],
        accept_multiple_files=True,
        label_visibility="collapsed",
    )

    if audio_files:
        st.info(f"🎵 {len(audio_files)} audio file(s) selected")

        col1, col2 = st.columns(2)
        with col1:
            st.metric("Audio Files", len(audio_files))

        # Transcribe button
        if st.button("🎵 Transcribe Audio", key="instant_transcribe", use_container_width=True):
            with st.spinner("📤 Processing audio files..."):
                st.info(
                    "✅ Files processed! (Integration with Book Management required for full transcription)"
                )
