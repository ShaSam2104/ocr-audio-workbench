"""OCR status monitoring component."""
import streamlit as st
import time
from services.api_client import APIClient
from services.formatting_renderer import render_status_badge


def render_ocr_status_dashboard(chapter_id: int, task_id: str, api_client: APIClient):
    """
    Display real-time OCR processing status with progress bar and per-image status.
    Polls every 2 seconds until completion.
    """
    status_container = st.container()

    with status_container:
        st.subheader("🔍 OCR Processing Status")

        while st.session_state.ocr_polling_active and task_id:
            # Get current status
            status_data = api_client.get_ocr_status(task_id)

            if not status_data:
                st.error("❌ Failed to get OCR status. Processing may have failed.")
                break

            # Extract status information
            total_images = status_data.get("total_images", 0)
            completed_count = status_data.get("completed_count", 0)
            progress_percent = status_data.get("progress_percent", 0)
            overall_status = status_data.get("status", "processing")
            images = status_data.get("images", [])

            # Display progress bar
            col1, col2 = st.columns([4, 1])

            with col1:
                st.progress(
                    min(progress_percent / 100, 1.0),
                    text=f"Processing: {completed_count}/{total_images} ({progress_percent}%)",
                )

            with col2:
                st.metric("Progress", f"{progress_percent}%")

            # Display per-image status
            if images:
                st.subheader("Image Status")

                # Create expandable sections for each image
                status_cols = st.columns(3)

                for idx, image in enumerate(images):
                    image_id = image.get("image_id")
                    image_status = image.get("status", "pending")
                    col_idx = idx % 3

                    with status_cols[col_idx]:
                        st.write(f"Image #{image_id}")
                        render_status_badge(image_status)

                        # Show error if failed
                        if image_status == "failed":
                            error_msg = image.get("error", "Unknown error")
                            st.error(f"Error: {error_msg}")

            # Check if processing is complete
            if overall_status == "completed":
                st.success("✅ All images processed successfully!")
                st.session_state.ocr_polling_active = False
                break
            elif overall_status == "failed":
                st.error(
                    "❌ OCR processing failed. Please check the logs and try again."
                )
                st.session_state.ocr_polling_active = False
                break

            # Wait before next poll
            time.sleep(2)


def show_ocr_button(chapter_id: int, api_client: APIClient, pending_images: list):
    """Show button to start OCR processing."""
    if not pending_images:
        st.success("✅ All images have been processed!")
        return

    col1, col2 = st.columns(2)

    with col1:
        if st.button("🔍 Extract Text from Images", use_container_width=True):
            # Extract image IDs
            image_ids = [img["id"] for img in pending_images]

            with st.spinner("📤 Submitting images for OCR processing..."):
                result = api_client.start_ocr_processing(image_ids)

            if result:
                task_id = result.get("task_id")
                st.session_state.ocr_task_ids[chapter_id] = task_id
                st.session_state.ocr_polling_active = True
                st.success(
                    f"✅ OCR processing started! Task ID: {task_id}"
                )
                st.rerun()
            else:
                st.error("❌ Failed to start OCR processing")

    with col2:
        if st.session_state.ocr_polling_active:
            if st.button("⏹️ Stop Polling", use_container_width=True):
                st.session_state.ocr_polling_active = False
                st.info("Polling stopped. You can resume manually later.")
