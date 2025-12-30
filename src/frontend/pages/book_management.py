"""Book Management page - hierarchical organization."""
import streamlit as st
from services.api_client import APIClient
from components.ocr_status import render_ocr_status_dashboard, show_ocr_button
from components.transcription_status import (
    render_transcription_status_dashboard,
    show_transcribe_button,
)
from services.formatting_renderer import render_formatted_text
from utils.validators import validate_image_file, validate_pdf_file, validate_audio_file


def render():
    """Render book management page."""
    api_client = APIClient()
    api_client.set_token(st.session_state.auth_token)

    col1, col2, col3 = st.columns([7, 1, 2])

    with col1:
        st.title("📚 Book Management")

    with col3:
        if st.button("➕ New Book", use_container_width=True):
            st.session_state.show_new_book_form = True

    # Show new book form if needed
    if st.session_state.get("show_new_book_form"):
        render_new_book_form(api_client)

    # Sidebar navigation
    render_sidebar(api_client)

    # Main content area
    if st.session_state.selected_chapter_id:
        render_chapter_content(api_client)
    else:
        st.info("👈 Select a chapter from the sidebar to view its content")


def render_new_book_form(api_client: APIClient):
    """Render form to create a new book."""
    with st.form("new_book_form"):
        st.subheader("Create New Book")
        book_name = st.text_input("Book Name", placeholder="e.g., My Scanned Notes")
        book_desc = st.text_area(
            "Description", placeholder="What is this book about?", height=100
        )

        col1, col2 = st.columns(2)
        with col1:
            submit = st.form_submit_button("✅ Create Book", use_container_width=True)

        with col2:
            if st.form_submit_button("❌ Cancel", use_container_width=True):
                st.session_state.show_new_book_form = False

        if submit and book_name:
            with st.spinner("Creating book..."):
                result = api_client.create_book(book_name, book_desc)

            if result:
                st.success("✅ Book created successfully!")
                st.session_state.show_new_book_form = False
                st.rerun()
            else:
                st.error("❌ Failed to create book")


def render_sidebar(api_client: APIClient):
    """Render book and chapter navigation sidebar."""
    with st.sidebar:
        st.title("📚 Navigation")

        # Get books
        books_data = api_client.get_books()
        if not books_data:
            st.info("No books yet. Create one to get started!")
            return

        books = books_data.get("items", [])
        if not books:
            st.info("No books yet. Create one to get started!")
            return

        # Book selection
        selected_book = st.selectbox(
            "Select a Book",
            books,
            format_func=lambda x: f"📕 {x['name']}",
            key="book_selectbox",
        )

        if selected_book:
            st.session_state.selected_book_id = selected_book["id"]

            # Get chapters for selected book
            chapters_data = api_client.get_chapters(selected_book["id"])
            chapters = chapters_data.get("items", []) if chapters_data else []

            st.divider()
            st.subheader(f"Chapters ({len(chapters)})")

            if chapters:
                # Chapter selection
                selected_chapter = st.selectbox(
                    "Select a Chapter",
                    chapters,
                    format_func=lambda x: f"📄 {x['name']}",
                    key="chapter_selectbox",
                )

                if selected_chapter:
                    st.session_state.selected_chapter_id = selected_chapter["id"]
            else:
                st.info("No chapters yet")

            # New chapter button
            if st.button("➕ New Chapter", use_container_width=True):
                st.session_state.show_new_chapter_form = True

            # Show new chapter form if needed
            if st.session_state.get("show_new_chapter_form"):
                render_new_chapter_form(api_client, selected_book["id"])


def render_new_chapter_form(api_client: APIClient, book_id: int):
    """Render form to create a new chapter."""
    with st.form("new_chapter_form", border=False):
        st.subheader("Add New Chapter")
        ch_name = st.text_input("Chapter Name", placeholder="e.g., Chapter 1")
        ch_desc = st.text_area(
            "Description", placeholder="(optional)", height=50
        )

        col1, col2 = st.columns(2)
        with col1:
            submit = st.form_submit_button("✅ Create", use_container_width=True)

        with col2:
            if st.form_submit_button("❌ Cancel", use_container_width=True):
                st.session_state.show_new_chapter_form = False

        if submit and ch_name:
            with st.spinner("Creating chapter..."):
                result = api_client.create_chapter(book_id, ch_name, ch_desc)

            if result:
                st.success("✅ Chapter created!")
                st.session_state.show_new_chapter_form = False
                st.rerun()
            else:
                st.error("❌ Failed to create chapter")


def render_chapter_content(api_client: APIClient):
    """Render content for selected chapter."""
    chapter_id = st.session_state.selected_chapter_id

    # Create tabs for images and audio
    tab_images, tab_audio = st.tabs(["📷 Images", "🎵 Audio"])

    with tab_images:
        render_chapter_images(api_client, chapter_id)

    with tab_audio:
        render_chapter_audio(api_client, chapter_id)


def render_chapter_images(api_client: APIClient, chapter_id: int):
    """Render images section of chapter."""
    st.subheader("📷 Images")

    # Upload images
    uploaded_images = st.file_uploader(
        "Upload images or PDFs",
        type=["jpg", "jpeg", "png", "pdf"],
        accept_multiple_files=True,
        label_visibility="collapsed",
        key=f"image_upload_{chapter_id}",
    )

    if uploaded_images:
        st.info(f"📁 {len(uploaded_images)} file(s) selected")

        if st.button("📤 Upload Images", use_container_width=True):
            with st.spinner("Uploading images..."):
                result = api_client.upload_images(chapter_id, uploaded_images)

            if result:
                st.success(f"✅ {len(result)} image(s) uploaded!")
                st.rerun()
            else:
                st.error("❌ Failed to upload images")

    # Get and display existing images
    images_data = api_client.get_chapter_images(chapter_id)
    if images_data:
        images = images_data.get("items", [])
        st.divider()
        st.caption(f"Total images: {images_data.get('total', 0)}")

        if images:
            # Separate by OCR status
            pending_images = [img for img in images if img.get("ocr_status") == "pending"]
            completed_images = [img for img in images if img.get("ocr_status") == "completed"]
            processing_images = [img for img in images if img.get("ocr_status") == "processing"]
            failed_images = [img for img in images if img.get("ocr_status") == "failed"]

            # Status summary
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Pending", len(pending_images))
            col2.metric("Processing", len(processing_images))
            col3.metric("Completed", len(completed_images))
            col4.metric("Failed", len(failed_images))

            st.divider()

            # Show OCR button
            if pending_images:
                show_ocr_button(chapter_id, api_client, pending_images)

            # Show polling status if active
            task_id = st.session_state.ocr_task_ids.get(chapter_id)
            if st.session_state.ocr_polling_active and task_id:
                render_ocr_status_dashboard(chapter_id, task_id, api_client)

            # Display image grid
            if completed_images:
                st.subheader("✅ Processed Images")
                render_image_grid(completed_images, api_client)
        else:
            st.info("No images uploaded yet")


def render_chapter_audio(api_client: APIClient, chapter_id: int):
    """Render audio section of chapter."""
    st.subheader("🎵 Audio Files")

    # Upload audio
    uploaded_audio = st.file_uploader(
        "Upload audio files",
        type=["mp3", "wav", "m4a", "ogg", "flac"],
        accept_multiple_files=True,
        label_visibility="collapsed",
        key=f"audio_upload_{chapter_id}",
    )

    if uploaded_audio:
        st.info(f"🎵 {len(uploaded_audio)} audio file(s) selected")

        if st.button("📤 Upload Audio", use_container_width=True):
            with st.spinner("Uploading audio files..."):
                result = api_client.upload_audios(chapter_id, uploaded_audio)

            if result:
                st.success(f"✅ {len(result)} audio file(s) uploaded!")
                st.rerun()
            else:
                st.error("❌ Failed to upload audio")

    # Get and display existing audio
    audios_data = api_client.get_chapter_audios(chapter_id)
    if audios_data:
        audios = audios_data.get("items", [])
        st.divider()
        st.caption(f"Total audio files: {audios_data.get('total', 0)}")

        if audios:
            # Separate by transcription status
            pending_audios = [
                audio
                for audio in audios
                if audio.get("transcription_status") == "pending"
            ]
            completed_audios = [
                audio
                for audio in audios
                if audio.get("transcription_status") == "completed"
            ]
            processing_audios = [
                audio
                for audio in audios
                if audio.get("transcription_status") == "processing"
            ]
            failed_audios = [
                audio
                for audio in audios
                if audio.get("transcription_status") == "failed"
            ]

            # Status summary
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Pending", len(pending_audios))
            col2.metric("Processing", len(processing_audios))
            col3.metric("Completed", len(completed_audios))
            col4.metric("Failed", len(failed_audios))

            st.divider()

            # Show transcribe button
            if pending_audios:
                show_transcribe_button(chapter_id, api_client, pending_audios)

            # Show polling status if active
            task_id = st.session_state.transcription_task_ids.get(chapter_id)
            if st.session_state.transcription_polling_active and task_id:
                render_transcription_status_dashboard(chapter_id, task_id, api_client)

            # Display audio grid
            if completed_audios:
                st.subheader("✅ Transcribed Audio")
                render_audio_grid(completed_audios)
        else:
            st.info("No audio files uploaded yet")


def render_image_grid(images: list, api_client: APIClient):
    """Render grid of images."""
    cols = st.columns(3)

    for idx, image in enumerate(images):
        with cols[idx % 3]:
            st.write(f"**#{image.get('sequence_number')}** - {image.get('filename')}")

            # Show OCR status
            ocr_status = image.get("ocr_status")
            st.caption(f"Status: {ocr_status}")

            # Show OCR text preview
            text_data = api_client.get_image_text(image.get("id"))
            if text_data:
                plain_text = text_data.get("plain_text", "")[:100]
                if plain_text:
                    st.text(plain_text + "...")


def render_audio_grid(audios: list):
    """Render grid of audio files."""
    cols = st.columns(3)

    for idx, audio in enumerate(audios):
        with cols[idx % 3]:
            st.write(f"**#{audio.get('sequence_number')}** - {audio.get('filename')}")

            # Show transcription status
            trans_status = audio.get("transcription_status")
            st.caption(f"Status: {trans_status}")

            # Show duration
            duration = audio.get("duration_seconds", 0)
            st.caption(f"Duration: {duration}s")
