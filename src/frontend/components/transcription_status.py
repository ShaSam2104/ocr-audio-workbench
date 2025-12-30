"""Transcription status monitoring component."""
import streamlit as st
import time
from services.api_client import APIClient
from services.formatting_renderer import render_status_badge


def render_transcription_status_dashboard(
    chapter_id: int, task_id: str, api_client: APIClient
):
    """
    Display real-time transcription processing status with progress bar and per-audio status.
    Polls every 2 seconds until completion.
    """
    status_container = st.container()

    with status_container:
        st.subheader("🎵 Transcription Status")

        while st.session_state.transcription_polling_active and task_id:
            # Get current status
            status_data = api_client.get_transcription_status(task_id)

            if not status_data:
                st.error("❌ Failed to get transcription status. Processing may have failed.")
                break

            # Extract status information
            total_audios = status_data.get("total_audios", 0)
            completed_count = status_data.get("completed_count", 0)
            progress_percent = status_data.get("progress_percent", 0)
            overall_status = status_data.get("status", "processing")
            audios = status_data.get("audios", [])

            # Display progress bar
            col1, col2 = st.columns([4, 1])

            with col1:
                st.progress(
                    min(progress_percent / 100, 1.0),
                    text=f"Transcribing: {completed_count}/{total_audios} ({progress_percent}%)",
                )

            with col2:
                st.metric("Progress", f"{progress_percent}%")

            # Display per-audio status
            if audios:
                st.subheader("Audio Status")

                # Create expandable sections for each audio
                status_cols = st.columns(3)

                for idx, audio in enumerate(audios):
                    audio_id = audio.get("audio_id")
                    audio_status = audio.get("status", "pending")
                    col_idx = idx % 3

                    with status_cols[col_idx]:
                        st.write(f"Audio #{audio_id}")
                        render_status_badge(audio_status)

                        # Show error if failed
                        if audio_status == "failed":
                            error_msg = audio.get("error", "Unknown error")
                            st.error(f"Error: {error_msg}")

            # Check if processing is complete
            if overall_status == "completed":
                st.success("✅ All audio files transcribed successfully!")
                st.session_state.transcription_polling_active = False
                break
            elif overall_status == "failed":
                st.error(
                    "❌ Transcription failed. Please check the logs and try again."
                )
                st.session_state.transcription_polling_active = False
                break

            # Wait before next poll
            time.sleep(2)


def show_transcribe_button(
    chapter_id: int, api_client: APIClient, pending_audios: list
):
    """Show button to start transcription."""
    if not pending_audios:
        st.success("✅ All audio files have been transcribed!")
        return

    col1, col2 = st.columns(2)

    with col1:
        if st.button("🎵 Transcribe Audio Files", use_container_width=True):
            # Extract audio IDs
            audio_ids = [audio["id"] for audio in pending_audios]

            with st.spinner("📤 Submitting audio files for transcription..."):
                result = api_client.start_transcription(audio_ids)

            if result:
                task_id = result.get("task_id")
                st.session_state.transcription_task_ids[chapter_id] = task_id
                st.session_state.transcription_polling_active = True
                st.success(f"✅ Transcription started! Task ID: {task_id}")
                st.rerun()
            else:
                st.error("❌ Failed to start transcription")

    with col2:
        if st.session_state.transcription_polling_active:
            if st.button("⏹️ Stop Polling", use_container_width=True):
                st.session_state.transcription_polling_active = False
                st.info("Polling stopped. You can resume manually later.")
