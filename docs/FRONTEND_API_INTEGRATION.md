# Frontend API Integration Guide

Complete mapping of OCR Workbench backend endpoints to Streamlit frontend implementation.

---

## Table of Contents

1. [Authentication & Session Management](#authentication--session-management)
2. [Book & Chapter Management](#book--chapter-management)
3. [Image Upload & Management](#image-upload--management)
4. [Audio Upload & Management](#audio-upload--management)
5. [OCR Processing (Background)](#ocr-processing-background)
6. [Audio Transcription (Background)](#audio-transcription-background)
7. [Text Retrieval](#text-retrieval)
8. [Search](#search)
9. [Export](#export)
10. [Error Handling](#error-handling)
11. [Code Examples](#code-examples)

---

## Authentication & Session Management

### Backend Endpoint

```
POST /auth/login
Request: { username: str, password: str }
Response: { access_token: str, token_type: str }
Status: 200, 401
```

### Frontend Implementation

**In `app.py` - Login Page:**

```python
import streamlit as st
import httpx

def show_login_page():
    st.title("🔐 OCR Workbench Login")
    
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    
    if st.button("Login"):
        try:
            response = httpx.post(
                f"{st.session_state.backend_url}/auth/login",
                json={"username": username, "password": password},
                timeout=10.0
            )
            
            if response.status_code == 200:
                data = response.json()
                st.session_state.auth_token = data["access_token"]
                st.session_state.token_type = data["token_type"]
                st.session_state.username = username
                st.success("✅ Logged in successfully!")
                st.rerun()
            elif response.status_code == 401:
                st.error("❌ Invalid username or password")
            else:
                st.error(f"❌ Login failed: {response.text}")
        except Exception as e:
            st.error(f"❌ Connection error: {str(e)}")

def show_logout_button():
    col1, col2 = st.columns([8, 2])
    with col2:
        if st.button("Logout"):
            st.session_state.auth_token = None
            st.session_state.username = None
            st.success("✅ Logged out successfully!")
            st.rerun()
```

### Session State Initialization

```python
def initialize_session_state():
    """Initialize all session state variables."""
    defaults = {
        # Auth
        "auth_token": None,
        "username": None,
        "backend_url": "http://localhost:8000",
        
        # Navigation
        "selected_book_id": None,
        "selected_chapter_id": None,
        "selected_image_id": None,
        "selected_audio_id": None,
        
        # OCR Background Processing
        "ocr_task_id": None,
        "ocr_status": None,
        "ocr_polling_active": False,
        
        # Audio Transcription Background Processing
        "transcription_task_id": None,
        "transcription_status": None,
        "transcription_polling_active": False,
        
        # Theme
        "theme": "light",
    }
    
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

# Call in app.py
initialize_session_state()
```

### Helper Function - API Calls with Auth

```python
def api_call(method: str, endpoint: str, json_data=None, files=None):
    """Make authenticated API call to backend."""
    if not st.session_state.auth_token:
        st.error("❌ Not authenticated. Please login first.")
        return None
    
    headers = {"Authorization": f"Bearer {st.session_state.auth_token}"}
    url = f"{st.session_state.backend_url}{endpoint}"
    
    try:
        if method.upper() == "GET":
            response = httpx.get(url, headers=headers, timeout=30.0)
        elif method.upper() == "POST":
            if files:
                response = httpx.post(url, headers=headers, files=files, timeout=60.0)
            else:
                response = httpx.post(url, headers=headers, json=json_data, timeout=30.0)
        elif method.upper() == "PUT":
            response = httpx.put(url, headers=headers, json=json_data, timeout=30.0)
        elif method.upper() == "DELETE":
            response = httpx.delete(url, headers=headers, timeout=30.0)
        else:
            st.error(f"❌ Unsupported method: {method}")
            return None
        
        return response
    except httpx.TimeoutException:
        st.error("❌ Request timeout. Server may be slow.")
        return None
    except Exception as e:
        st.error(f"❌ Connection error: {str(e)}")
        return None
```

---

## Book & Chapter Management

### Create Book

```
POST /books
Request: { name: str, description?: str }
Response: { id: int, name: str, description: str, created_at: str, updated_at: str }
Status: 201, 400
```

**Frontend:**

```python
def create_book():
    st.subheader("📚 Create New Book")
    
    book_name = st.text_input("Book Name")
    book_desc = st.text_area("Description (optional)")
    
    if st.button("Create Book"):
        response = api_call("POST", "/books", {
            "name": book_name,
            "description": book_desc or None
        })
        
        if response and response.status_code == 201:
            st.success(f"✅ Book '{book_name}' created!")
            st.rerun()
        elif response:
            st.error(f"❌ {response.json().get('detail', 'Failed to create book')}")
```

### List Books

```
GET /books?page=1
Response: { items: [BookSchema], total: int, page: int, page_size: int }
Status: 200
```

**Frontend:**

```python
def get_books(page: int = 1):
    response = api_call("GET", f"/books?page={page}")
    if response and response.status_code == 200:
        return response.json()
    return None

def render_books_sidebar():
    st.sidebar.title("📚 Books")
    
    books_data = get_books()
    if books_data:
        for book in books_data["items"]:
            if st.sidebar.button(f"📖 {book['name']}", key=f"book_{book['id']}"):
                st.session_state.selected_book_id = book["id"]
                st.session_state.selected_chapter_id = None
                st.rerun()
```

### List Chapters (for a Book)

```
GET /books/{book_id}/chapters?page=1
Response: { items: [ChapterSchema], total: int, page: int, page_size: int }
Status: 200, 404
```

**Frontend:**

```python
def get_chapters(book_id: int, page: int = 1):
    response = api_call("GET", f"/books/{book_id}/chapters?page={page}")
    if response and response.status_code == 200:
        return response.json()
    return None

def render_chapters_sidebar(book_id: int):
    st.sidebar.markdown("### 📄 Chapters")
    
    chapters_data = get_chapters(book_id)
    if chapters_data:
        for chapter in chapters_data["items"]:
            # Show chapter with image + audio counts
            col1, col2, col3 = st.sidebar.columns([2, 1, 1])
            
            with col1:
                if st.button(f"📑 {chapter['name']}", key=f"ch_{chapter['id']}"):
                    st.session_state.selected_chapter_id = chapter["id"]
                    st.rerun()
            
            with col2:
                st.caption(f"📸 {chapter.get('image_count', 0)}")
            
            with col3:
                st.caption(f"🎵 {chapter.get('audio_count', 0)}")
```

### Create Chapter

```
POST /books/{book_id}/chapters
Request: { name: str, description?: str }
Response: { id: int, book_id: int, name: str, ... }
Status: 201, 404
```

**Frontend:**

```python
def create_chapter(book_id: int):
    st.subheader("➕ Add Chapter")
    
    ch_name = st.text_input("Chapter Name")
    ch_desc = st.text_area("Description (optional)")
    
    if st.button("Create Chapter"):
        response = api_call("POST", f"/books/{book_id}/chapters", {
            "name": ch_name,
            "description": ch_desc or None
        })
        
        if response and response.status_code == 201:
            st.success(f"✅ Chapter '{ch_name}' created!")
            st.rerun()
        elif response:
            st.error(f"❌ {response.json().get('detail', 'Failed')}")
```

---

## Image Upload & Management

### Upload Images (including PDFs)

```
POST /chapters/{chapter_id}/images/upload
Request: multipart/form-data with files[] (images + PDFs)
Response: [{ id: int, chapter_id: int, filename: str, sequence_number: int, ocr_status: str, ... }]
Status: 201, 400, 404
```

**Frontend:**

```python
def upload_images(chapter_id: int):
    st.subheader("📤 Upload Images/PDFs")
    
    uploaded_files = st.file_uploader(
        "Select images or PDFs",
        type=["jpg", "jpeg", "png", "pdf"],
        accept_multiple_files=True,
        label_visibility="collapsed"
    )
    
    if uploaded_files:
        st.info(f"📁 {len(uploaded_files)} file(s) selected")
        
        # Show file types breakdown
        image_count = sum(1 for f in uploaded_files if f.name.lower().endswith(('.jpg', '.jpeg', '.png')))
        pdf_count = sum(1 for f in uploaded_files if f.name.lower().endswith('.pdf'))
        
        st.caption(f"📸 {image_count} images | 📄 {pdf_count} PDFs")
        
        if st.button("⬆️ Upload Files"):
            # Prepare multipart form data
            files_data = []
            for f in uploaded_files:
                files_data.append(("files", (f.name, f.read(), "application/octet-stream")))
            
            response = api_call("POST", f"/chapters/{chapter_id}/images/upload", files=files_data)
            
            if response and response.status_code == 201:
                created_images = response.json()
                st.success(f"✅ Uploaded {len(created_images)} file(s)!")
                st.rerun()
            elif response:
                st.error(f"❌ Upload failed: {response.json().get('detail', 'Unknown error')}")
```

### List Images in Chapter

```
GET /chapters/{chapter_id}/images?page=1
Response: { items: [ImageSchema], total: int, page: int, page_size: int }
Status: 200, 404
```

**Frontend:**

```python
def get_chapter_images(chapter_id: int, page: int = 1):
    response = api_call("GET", f"/chapters/{chapter_id}/images?page={page}")
    if response and response.status_code == 200:
        return response.json()
    return None

def render_image_grid(chapter_id: int):
    """Display 50 images per page in grid."""
    st.subheader("📸 Images")
    
    images_data = get_chapter_images(chapter_id, page=st.session_state.get("image_page", 1))
    
    if images_data and images_data["items"]:
        # Show grid
        cols = st.columns(5)
        for idx, img in enumerate(images_data["items"]):
            with cols[idx % 5]:
                # Image thumbnail with status badge
                st.image(f"{st.session_state.backend_url}/images/{img['id']}/thumbnail")
                
                # Status indicator
                status_icon = {
                    "pending": "⏸️",
                    "processing": "⏳",
                    "completed": "✅",
                    "failed": "❌"
                }.get(img["ocr_status"], "❓")
                
                st.caption(f"#{img['sequence_number']} {status_icon}")
                
                if st.button("👁️", key=f"view_img_{img['id']}"):
                    st.session_state.selected_image_id = img["id"]
                    st.rerun()
        
        # Pagination
        total_pages = (images_data["total"] + 49) // 50
        if total_pages > 1:
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                st.session_state.image_page = st.number_input(
                    "Page",
                    1,
                    total_pages,
                    value=st.session_state.get("image_page", 1),
                    key="img_page_input"
                )
    else:
        st.info("No images uploaded yet")
```

### Reorder Images

```
POST /chapters/{chapter_id}/images/reorder
Request: { new_order: [image_id, image_id, ...] }
Response: { message: str, updated_count: int }
Status: 200, 404, 400
```

**Frontend:**

```python
def reorder_images(chapter_id: int):
    st.subheader("🔄 Reorder Images")
    
    images_data = get_chapter_images(chapter_id)
    if not images_data or not images_data["items"]:
        st.info("No images to reorder")
        return
    
    images = images_data["items"]
    new_order = st.multiselect(
        "Drag to reorder (or click to reorder):",
        options=[f"#{img['sequence_number']}: {img['filename']}" for img in images],
        default=[f"#{img['sequence_number']}: {img['filename']}" for img in images]
    )
    
    if st.button("💾 Save New Order"):
        # Extract image IDs from selected order
        image_ids = []
        for item in new_order:
            for img in images:
                if f"#{img['sequence_number']}: {img['filename']}" == item:
                    image_ids.append(img["id"])
                    break
        
        response = api_call(
            "POST",
            f"/chapters/{chapter_id}/images/reorder",
            {"new_order": image_ids}
        )
        
        if response and response.status_code == 200:
            st.success("✅ Images reordered!")
            st.rerun()
        elif response:
            st.error(f"❌ Failed to reorder: {response.json().get('detail')}")
```

---

## Audio Upload & Management

### Upload Audio Files

```
POST /chapters/{chapter_id}/audios/upload
Request: multipart/form-data with files[] (audio files)
Response: [{ id: int, chapter_id: int, filename: str, sequence_number: int, duration_seconds: int, audio_format: str, transcription_status: str, ... }]
Status: 201, 400, 404
```

**Frontend:**

```python
def upload_audio_files(chapter_id: int):
    st.subheader("🎵 Upload Audio Files")
    
    audio_files = st.file_uploader(
        "Select audio files",
        type=["mp3", "wav", "m4a", "ogg", "flac"],
        accept_multiple_files=True,
        label_visibility="collapsed"
    )
    
    if audio_files:
        st.info(f"🎵 {len(audio_files)} audio file(s) selected")
        
        if st.button("⬆️ Upload Audio"):
            files_data = []
            for f in audio_files:
                files_data.append(("files", (f.name, f.read(), "audio/*")))
            
            response = api_call("POST", f"/chapters/{chapter_id}/audios/upload", files=files_data)
            
            if response and response.status_code == 201:
                created_audios = response.json()
                st.success(f"✅ Uploaded {len(created_audios)} audio file(s)!")
                st.rerun()
            elif response:
                st.error(f"❌ Upload failed: {response.json().get('detail')}")
```

### List Audio Files in Chapter

```
GET /chapters/{chapter_id}/audios?page=1
Response: { items: [AudioSchema], total: int, page: int, page_size: int }
Status: 200, 404
```

**Frontend:**

```python
def get_chapter_audios(chapter_id: int, page: int = 1):
    response = api_call("GET", f"/chapters/{chapter_id}/audios?page={page}")
    if response and response.status_code == 200:
        return response.json()
    return None

def render_audio_grid(chapter_id: int):
    """Display audio files in grid with player."""
    st.subheader("🎵 Audio Files")
    
    audios_data = get_chapter_audios(chapter_id, page=st.session_state.get("audio_page", 1))
    
    if audios_data and audios_data["items"]:
        for audio in audios_data["items"]:
            col1, col2, col3 = st.columns([2, 2, 1])
            
            with col1:
                st.caption(f"**#{audio['sequence_number']}** {audio['filename']}")
            
            with col2:
                duration = f"{audio['duration_seconds']}s" if audio.get('duration_seconds') else "??"
                st.caption(f"⏱️ {duration} · {audio['audio_format'].upper()}")
            
            with col3:
                status_icon = {
                    "pending": "⏸️",
                    "processing": "⏳",
                    "completed": "✅",
                    "failed": "❌"
                }.get(audio["transcription_status"], "❓")
                st.caption(f"{status_icon} {audio['transcription_status']}")
                
                if st.button("👁️", key=f"view_audio_{audio['id']}"):
                    st.session_state.selected_audio_id = audio["id"]
                    st.rerun()
        
        # Pagination
        total_pages = (audios_data["total"] + 49) // 50
        if total_pages > 1:
            st.session_state.audio_page = st.number_input(
                "Audio Page",
                1,
                total_pages,
                value=st.session_state.get("audio_page", 1),
                key="audio_page_input"
            )
    else:
        st.info("No audio files uploaded yet")
```

---

## OCR Processing (Background)

### Start OCR Processing

```
POST /ocr/process
Request: { image_ids: [int, ...], crop_coordinates?: { x: int, y: int, width: int, height: int } }
Response: { task_id: str, status: "queued", total_images: int, message: str }
Status: 202 (Accepted - returns immediately!)
```

**Frontend - Start Processing:**

```python
def start_ocr_processing(image_ids: list):
    """Submit images for OCR. Returns immediately with task_id."""
    st.info("📤 Submitting images for OCR processing...")
    
    response = api_call("POST", "/ocr/process", {
        "image_ids": image_ids,
        "crop_coordinates": None  # Add crop coords if user selected cropping
    })
    
    if response and response.status_code == 202:
        data = response.json()
        st.session_state.ocr_task_id = data["task_id"]
        st.session_state.ocr_polling_active = True
        st.success(f"✅ {data['message']}")
        st.info(f"Processing {data['total_images']} images...")
        return data["task_id"]
    elif response:
        st.error(f"❌ Failed to start OCR: {response.json().get('detail')}")
        return None

def render_ocr_button(chapter_id: int):
    """Button to start OCR for all pending images."""
    st.subheader("🔍 OCR Processing")
    
    images_data = get_chapter_images(chapter_id)
    if not images_data or not images_data["items"]:
        st.info("No images in chapter")
        return
    
    pending_images = [img for img in images_data["items"] if img["ocr_status"] == "pending"]
    
    if pending_images:
        col1, col2 = st.columns(2)
        with col1:
            st.caption(f"📸 {len(pending_images)} images pending OCR")
        with col2:
            if st.button("🔍 Extract Text from All"):
                image_ids = [img["id"] for img in pending_images]
                task_id = start_ocr_processing(image_ids)
                if task_id:
                    st.rerun()
    else:
        st.success("✅ All images have been processed!")
```

### Poll OCR Status

```
GET /ocr/status/{task_id}
Response: {
  task_id: str,
  status: "queued|processing|completed|failed",
  total_images: int,
  completed_count: int,
  progress_percent: int,
  images: [{ image_id: int, status: str, started_at?: str, completed_at?: str, error?: str }]
}
Status: 200, 404
```

**Frontend - Polling & Progress Display:**

```python
import time

def get_ocr_status(task_id: str):
    """Get current OCR task status."""
    response = api_call("GET", f"/ocr/status/{task_id}")
    if response and response.status_code == 200:
        return response.json()
    return None

def render_ocr_progress():
    """Show real-time OCR progress with per-image status."""
    if not st.session_state.ocr_task_id or not st.session_state.ocr_polling_active:
        return
    
    status_container = st.container()
    
    while st.session_state.ocr_polling_active:
        status_data = get_ocr_status(st.session_state.ocr_task_id)
        
        if not status_data:
            st.error("❌ Failed to fetch OCR status")
            st.session_state.ocr_polling_active = False
            break
        
        with status_container:
            # Progress bar
            col1, col2 = st.columns([3, 1])
            with col1:
                progress = status_data["progress_percent"] / 100
                st.progress(progress)
            with col2:
                st.caption(f"{status_data['completed_count']}/{status_data['total_images']} done")
            
            # Percent text
            st.caption(f"📊 Progress: {status_data['progress_percent']}%")
            
            # Per-image status
            st.markdown("**Image Status:**")
            status_cols = st.columns(5)
            for idx, img_status in enumerate(status_data["images"]):
                icon = {
                    "completed": "✅",
                    "processing": "⏳",
                    "pending": "⏸️",
                    "failed": "❌"
                }.get(img_status["status"], "❓")
                
                with status_cols[idx % 5]:
                    st.caption(f"{icon} #{idx + 1}")
                    if img_status.get("error"):
                        st.caption(f"_Error: {img_status['error'][:20]}..._")
        
        # Check if processing is done
        if status_data["status"] == "completed":
            st.success("✅ All images processed!")
            st.session_state.ocr_polling_active = False
            st.rerun()
            break
        elif status_data["status"] == "failed":
            st.error("❌ OCR processing failed")
            st.session_state.ocr_polling_active = False
            break
        
        # Poll every 2 seconds
        time.sleep(2)
```

---

## Audio Transcription (Background)

### Start Transcription

```
POST /audio/transcribe
Request: { audio_ids: [int, ...], language_hint?: str }
Response: { task_id: str, status: "queued", total_audios: int, message: str }
Status: 202 (Accepted - returns immediately!)
```

**Frontend - Start Transcription:**

```python
def start_audio_transcription(audio_ids: list):
    """Submit audio files for transcription. Returns immediately with task_id."""
    st.info("📤 Submitting audio files for transcription...")
    
    response = api_call("POST", "/audio/transcribe", {
        "audio_ids": audio_ids,
        "language_hint": None  # Optional: add detected language hint
    })
    
    if response and response.status_code == 202:
        data = response.json()
        st.session_state.transcription_task_id = data["task_id"]
        st.session_state.transcription_polling_active = True
        st.success(f"✅ {data['message']}")
        st.info(f"Processing {data['total_audios']} audio files...")
        return data["task_id"]
    elif response:
        st.error(f"❌ Failed to start transcription: {response.json().get('detail')}")
        return None

def render_transcribe_button(chapter_id: int):
    """Button to start transcription for all pending audio."""
    st.subheader("🎵 Audio Transcription")
    
    audios_data = get_chapter_audios(chapter_id)
    if not audios_data or not audios_data["items"]:
        st.info("No audio files in chapter")
        return
    
    pending_audios = [audio for audio in audios_data["items"] if audio["transcription_status"] == "pending"]
    
    if pending_audios:
        col1, col2 = st.columns(2)
        with col1:
            st.caption(f"🎵 {len(pending_audios)} audio files pending transcription")
        with col2:
            if st.button("🎤 Transcribe All"):
                audio_ids = [audio["id"] for audio in pending_audios]
                task_id = start_audio_transcription(audio_ids)
                if task_id:
                    st.rerun()
    else:
        st.success("✅ All audio files have been transcribed!")
```

### Poll Transcription Status

```
GET /transcription/status/{task_id}
Response: {
  task_id: str,
  status: "queued|processing|completed|failed",
  total_audios: int,
  completed_count: int,
  progress_percent: int,
  audios: [{ audio_id: int, status: str, started_at?: str, completed_at?: str, error?: str }]
}
Status: 200, 404
```

**Frontend - Polling & Progress Display:**

```python
def get_transcription_status(task_id: str):
    """Get current transcription task status."""
    response = api_call("GET", f"/transcription/status/{task_id}")
    if response and response.status_code == 200:
        return response.json()
    return None

def render_transcription_progress():
    """Show real-time transcription progress with per-audio status."""
    if not st.session_state.transcription_task_id or not st.session_state.transcription_polling_active:
        return
    
    status_container = st.container()
    
    while st.session_state.transcription_polling_active:
        status_data = get_transcription_status(st.session_state.transcription_task_id)
        
        if not status_data:
            st.error("❌ Failed to fetch transcription status")
            st.session_state.transcription_polling_active = False
            break
        
        with status_container:
            # Progress bar
            col1, col2 = st.columns([3, 1])
            with col1:
                progress = status_data["progress_percent"] / 100
                st.progress(progress)
            with col2:
                st.caption(f"{status_data['completed_count']}/{status_data['total_audios']} done")
            
            # Percent text
            st.caption(f"📊 Progress: {status_data['progress_percent']}%")
            
            # Per-audio status
            st.markdown("**Audio Status:**")
            status_cols = st.columns(5)
            for idx, audio_status in enumerate(status_data["audios"]):
                icon = {
                    "completed": "✅",
                    "processing": "⏳",
                    "pending": "⏸️",
                    "failed": "❌"
                }.get(audio_status["status"], "❓")
                
                with status_cols[idx % 5]:
                    st.caption(f"{icon} #{idx + 1}")
                    if audio_status.get("error"):
                        st.caption(f"_Error: {audio_status['error'][:20]}..._")
        
        # Check if processing is done
        if status_data["status"] == "completed":
            st.success("✅ All audio files transcribed!")
            st.session_state.transcription_polling_active = False
            st.rerun()
            break
        elif status_data["status"] == "failed":
            st.error("❌ Transcription processing failed")
            st.session_state.transcription_polling_active = False
            break
        
        # Poll every 2 seconds
        time.sleep(2)
```

---

## Text Retrieval

### Get OCR Text (Formatted)

```
GET /images/{image_id}/text
Response: {
  image_id: int,
  raw_text_with_formatting: str,  # Contains markdown tags: **bold**, *italic*, __underline__
  plain_text: str,                # Plain text version
  detected_language: str,
  created_at: str
}
Status: 200, 404
```

**Frontend - Display Formatted OCR Text:**

```python
def get_image_ocr_text(image_id: int):
    """Fetch OCR result for an image."""
    response = api_call("GET", f"/images/{image_id}/text")
    if response and response.status_code == 200:
        return response.json()
    return None

def render_formatted_text(text_with_markdown: str):
    """
    Render markdown-style tags as actual HTML formatting.
    Supports: **bold**, *italic*, __underline__, ~~strikethrough~~, ^superscript^, ~subscript~
    """
    import re
    
    # Convert markdown tags to HTML (order matters!)
    html = text_with_markdown
    html = re.sub(r'\*\*([^\*]+)\*\*', r'<b>\1</b>', html)
    html = re.sub(r'__([^_]+)__', r'<u>\1</u>', html)
    html = re.sub(r'\*([^\*]+)\*', r'<i>\1</i>', html)
    html = re.sub(r'~~([^~]+)~~', r'<s>\1</s>', html)
    html = re.sub(r'\^([^^]+)\^', r'<sup>\1</sup>', html)
    html = re.sub(r'~([^~]+)~', r'<sub>\1</sub>', html)
    html = html.replace('\n', '<br>')
    
    # Apply theme-aware styling
    theme = st.session_state.get("theme", "light")
    text_color = "#37352f" if theme == "light" else "#e8e6e1"
    
    html_with_style = f"""
    <div style="color: {text_color}; line-height: 1.6; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;">
        {html}
    </div>
    """
    
    st.markdown(html_with_style, unsafe_allow_html=True)

def render_image_workbench(image_id: int):
    """Display image + formatted OCR text side-by-side."""
    st.subheader("📷 Image Workbench")
    
    ocr_data = get_image_ocr_text(image_id)
    if not ocr_data:
        st.error("❌ Could not load image text")
        return
    
    left, right = st.columns([1, 1], gap="large")
    
    with left:
        st.caption("📷 Source Image")
        # Get image from MinIO via backend presigned URL
        response = api_call("GET", f"/images/{image_id}/preview")
        if response:
            st.image(response.content, use_column_width=True)
    
    with right:
        st.caption("📝 Extracted Text")
        
        # Display formatted text
        render_formatted_text(ocr_data["raw_text_with_formatting"])
        
        st.divider()
        
        # Show metadata
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Language", ocr_data.get("detected_language", "Unknown"))
        with col2:
            st.metric("Extracted", ocr_data["created_at"][:10])
        
        # Plain text version
        with st.expander("📋 Plain Text (Copy-Paste)"):
            st.text_area(
                "Plain text without formatting",
                value=ocr_data["plain_text"],
                height=200,
                disabled=True,
                label_visibility="collapsed"
            )
```

### Get Audio Transcript (Formatted)

```
GET /audio/{audio_id}/transcript
Response: {
  audio_id: int,
  raw_text_with_formatting: str,  # Contains markdown tags
  plain_text: str,
  detected_language: str,
  duration_seconds: int,
  created_at: str
}
Status: 200, 404
```

**Frontend - Display Audio + Transcript:**

```python
def get_audio_transcript(audio_id: int):
    """Fetch transcript for an audio file."""
    response = api_call("GET", f"/audio/{audio_id}/transcript")
    if response and response.status_code == 200:
        return response.json()
    return None

def render_audio_workbench(audio_id: int):
    """Display audio player + formatted transcript side-by-side."""
    st.subheader("🎵 Audio Workbench")
    
    transcript_data = get_audio_transcript(audio_id)
    if not transcript_data:
        st.error("❌ Could not load audio transcript")
        return
    
    left, right = st.columns([1, 1], gap="large")
    
    with left:
        st.caption("🎵 Audio Player")
        
        # Get audio file from backend
        response = api_call("GET", f"/audio/{audio_id}/file")
        if response:
            st.audio(response.content, format="audio/mp3")  # or appropriate format
        
        # Metadata
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Duration", f"{transcript_data['duration_seconds']}s")
        with col2:
            st.metric("Language", transcript_data.get("detected_language", "Unknown"))
        with col3:
            st.metric("Transcribed", transcript_data["created_at"][:10])
    
    with right:
        st.caption("📝 Transcript")
        
        # Display formatted transcript
        render_formatted_text(transcript_data["raw_text_with_formatting"])
        
        st.divider()
        
        # Plain text version
        with st.expander("📋 Plain Text"):
            st.text_area(
                "Plain text transcript",
                value=transcript_data["plain_text"],
                height=200,
                disabled=True,
                label_visibility="collapsed"
            )
```

---

## Search

### Search by Image Number

```
GET /search/images?chapter_id={id}&query=5-10
Response: [ImageSchema]
Status: 200, 404
```

### Full-Text Search in Chapter (Images + Audio)

```
GET /search/chapter?chapter_id={id}&text_query=keyword
Response: [{
  type: "image" | "audio",
  image?: ImageSchema,
  audio?: AudioSchema,
  excerpt: str
}]
Status: 200, 404
```

**Frontend - Search UI:**

```python
def search_text(chapter_id: int, query: str):
    """Search across images and audio in chapter."""
    response = api_call("GET", f"/search/chapter?chapter_id={chapter_id}&text_query={query}")
    if response and response.status_code == 200:
        return response.json()
    return None

def render_search_panel(chapter_id: int):
    """Search bar for full-text search across images + audio."""
    st.subheader("🔍 Search")
    
    search_query = st.text_input("Search extracted text and transcripts...")
    
    if search_query:
        results = search_text(chapter_id, search_query)
        
        if results:
            st.info(f"Found {len(results)} result(s)")
            
            for result in results:
                col1, col2 = st.columns([4, 1])
                
                with col1:
                    if result["type"] == "image":
                        st.markdown(f"📸 **Image #{result['image']['sequence_number']}**")
                        st.caption(result["image"]["filename"])
                    else:  # audio
                        st.markdown(f"🎵 **Audio #{result['audio']['sequence_number']}**")
                        st.caption(result["audio"]["filename"])
                    
                    # Show excerpt with highlighted query
                    excerpt = result["excerpt"]
                    highlighted = excerpt.replace(search_query, f"**{search_query}**")
                    st.caption(highlighted)
                
                with col2:
                    if st.button("View", key=f"search_{result['type']}_{result.get('image', {}).get('id') or result.get('audio', {}).get('id')}"):
                        if result["type"] == "image":
                            st.session_state.selected_image_id = result["image"]["id"]
                        else:
                            st.session_state.selected_audio_id = result["audio"]["id"]
                        st.rerun()
        else:
            st.info("No results found")
```

---

## Export

### Export Chapter to Docx/Txt

```
POST /export/folder
Request: {
  book_id: int,
  chapter_id?: int,
  format: "docx" | "txt",
  include_images?: bool,
  include_audio_transcripts?: bool
}
Response: File download
Status: 200, 404, 400
```

**Frontend - Export Dialog:**

```python
def render_export_dialog(book_id: int, chapter_id: int = None):
    """Export book/chapter to docx or txt."""
    st.subheader("📥 Export")
    
    export_format = st.radio("Format", ["Docx", "Text"], horizontal=True)
    
    col1, col2 = st.columns(2)
    with col1:
        include_images = st.checkbox("Include image numbers (docx only)", value=True)
    with col2:
        include_transcripts = st.checkbox("Include audio transcripts", value=True)
    
    if st.button("📥 Download Export"):
        response = api_call(
            "POST",
            "/export/folder",
            {
                "book_id": book_id,
                "chapter_id": chapter_id,
                "format": export_format.lower(),
                "include_images": include_images,
                "include_audio_transcripts": include_transcripts
            }
        )
        
        if response and response.status_code == 200:
            # Determine file extension and MIME type
            if export_format.lower() == "docx":
                filename = f"export.docx"
                mime_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            else:
                filename = f"export.txt"
                mime_type = "text/plain"
            
            # Trigger download
            st.download_button(
                label="✅ Download File",
                data=response.content,
                file_name=filename,
                mime=mime_type
            )
        elif response:
            st.error(f"❌ Export failed: {response.json().get('detail')}")
```

---

## Error Handling

### HTTP Status Codes & Meanings

| Status | Meaning | Example |
|--------|---------|---------|
| 200 | Success | Book retrieved |
| 201 | Created | Book created |
| 202 | Accepted | OCR/transcription queued |
| 400 | Bad Request | Invalid format in upload |
| 401 | Unauthorized | Missing/invalid token |
| 404 | Not Found | Book doesn't exist |
| 500 | Server Error | Gemini API error |

**Frontend - Error Handling Pattern:**

```python
def safe_api_call(method: str, endpoint: str, data=None, files=None):
    """Make API call with comprehensive error handling."""
    response = api_call(method, endpoint, data, files)
    
    if not response:
        return None, "Connection failed"
    
    if response.status_code == 401:
        st.error("🔐 Session expired. Please login again.")
        st.session_state.auth_token = None
        st.rerun()
        return None, "Unauthorized"
    
    elif response.status_code == 404:
        return None, "Resource not found"
    
    elif response.status_code == 400:
        error_detail = response.json().get("detail", "Invalid request")
        return None, f"Invalid request: {error_detail}"
    
    elif response.status_code >= 500:
        return None, "Server error. Try again later."
    
    return response, None

# Usage:
response, error = safe_api_call("POST", "/ocr/process", {"image_ids": [1, 2, 3]})
if error:
    st.error(f"❌ {error}")
else:
    st.success("✅ OCR started!")
```

---

## Code Examples

### Complete Workflow: Login → Create Book → Upload Images → Extract Text → Export

```python
import streamlit as st
import httpx
import time

# Initialize
st.set_page_config(page_title="OCR Workbench", layout="wide")
initialize_session_state()

# === STEP 1: LOGIN ===
if not st.session_state.auth_token:
    st.title("🔐 Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    
    if st.button("Login"):
        response = httpx.post(
            f"{st.session_state.backend_url}/auth/login",
            json={"username": username, "password": password}
        )
        if response.status_code == 200:
            st.session_state.auth_token = response.json()["access_token"]
            st.session_state.username = username
            st.success("✅ Logged in!")
            st.rerun()
        else:
            st.error("❌ Invalid credentials")
else:
    # === STEP 2: BOOK MANAGEMENT ===
    st.title("📚 OCR Workbench")
    
    col1, col2, col3 = st.columns([5, 1, 1])
    with col3:
        if st.button("Logout"):
            st.session_state.auth_token = None
            st.rerun()
    
    # Create book
    with st.sidebar:
        st.subheader("Create New Book")
        book_name = st.text_input("Book Name")
        if st.button("Create"):
            response = api_call("POST", "/books", {"name": book_name})
            if response and response.status_code == 201:
                st.success("✅ Book created!")
                st.rerun()
    
    # List books
    books_response = api_call("GET", "/books?page=1")
    if books_response:
        books = books_response.json()["items"]
        selected_book = st.selectbox(
            "Select Book",
            options=books,
            format_func=lambda b: b["name"]
        )
        
        if selected_book:
            st.session_state.selected_book_id = selected_book["id"]
            
            # === STEP 3: CHAPTER & IMAGE MANAGEMENT ===
            st.subheader(f"📖 {selected_book['name']}")
            
            # Create chapter
            ch_name = st.text_input("New Chapter Name")
            if st.button("Add Chapter"):
                response = api_call(
                    "POST",
                    f"/books/{selected_book['id']}/chapters",
                    {"name": ch_name}
                )
                if response and response.status_code == 201:
                    st.success("✅ Chapter created!")
                    st.rerun()
            
            # List chapters
            chapters_response = api_call(
                "GET",
                f"/books/{selected_book['id']}/chapters?page=1"
            )
            if chapters_response:
                chapters = chapters_response.json()["items"]
                selected_chapter = st.selectbox(
                    "Select Chapter",
                    options=chapters,
                    format_func=lambda c: c["name"]
                )
                
                if selected_chapter:
                    ch_id = selected_chapter["id"]
                    
                    # === STEP 4: UPLOAD IMAGES ===
                    st.subheader("📤 Upload Images")
                    uploaded_files = st.file_uploader(
                        "Select images/PDFs",
                        type=["jpg", "jpeg", "png", "pdf"],
                        accept_multiple_files=True
                    )
                    
                    if uploaded_files and st.button("Upload"):
                        files_data = [("files", (f.name, f.read())) for f in uploaded_files]
                        response = api_call(
                            "POST",
                            f"/chapters/{ch_id}/images/upload",
                            files=files_data
                        )
                        if response and response.status_code == 201:
                            st.success(f"✅ Uploaded {len(uploaded_files)} file(s)!")
                            st.rerun()
                    
                    # === STEP 5: EXTRACT TEXT ===
                    st.subheader("🔍 Extract Text")
                    images_response = api_call("GET", f"/chapters/{ch_id}/images?page=1")
                    if images_response:
                        images = images_response.json()["items"]
                        pending = [img for img in images if img["ocr_status"] == "pending"]
                        
                        if pending:
                            if st.button(f"Extract Text from {len(pending)} images"):
                                response = api_call(
                                    "POST",
                                    "/ocr/process",
                                    {"image_ids": [img["id"] for img in pending]}
                                )
                                if response and response.status_code == 202:
                                    task_id = response.json()["task_id"]
                                    st.session_state.ocr_task_id = task_id
                                    
                                    # Poll status
                                    progress_bar = st.progress(0)
                                    while True:
                                        status_response = api_call(
                                            "GET",
                                            f"/ocr/status/{task_id}"
                                        )
                                        if status_response:
                                            status = status_response.json()
                                            progress_bar.progress(
                                                status["progress_percent"] / 100
                                            )
                                            st.caption(
                                                f"{status['completed_count']}/{status['total_images']} done"
                                            )
                                            
                                            if status["status"] == "completed":
                                                st.success("✅ All done!")
                                                st.rerun()
                                                break
                                        time.sleep(2)
                        else:
                            st.info("✅ All images processed")
                    
                    # === STEP 6: VIEW & EXPORT ===
                    st.subheader("📁 Export")
                    if st.button("Export to Docx"):
                        response = api_call(
                            "POST",
                            "/export/folder",
                            {
                                "book_id": selected_book["id"],
                                "chapter_id": ch_id,
                                "format": "docx",
                                "include_images": True
                            }
                        )
                        if response and response.status_code == 200:
                            st.download_button(
                                label="Download Docx",
                                data=response.content,
                                file_name="export.docx",
                                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                            )
```

---

## Quick Reference: API Endpoints Summary

| Feature | Method | Endpoint | Returns |
|---------|--------|----------|---------|
| **Auth** | POST | `/auth/login` | `{access_token, token_type}` |
| **Books** | POST | `/books` | `{id, name, ...}` (201) |
| | GET | `/books?page=1` | `{items: [...], total, page}` |
| **Chapters** | POST | `/books/{id}/chapters` | `{id, name, ...}` (201) |
| | GET | `/books/{id}/chapters?page=1` | `{items: [...], total}` |
| **Images** | POST | `/chapters/{id}/images/upload` | `[{id, filename, sequence_number, ocr_status}]` (201) |
| | GET | `/chapters/{id}/images?page=1` | `{items: [...], total}` |
| | POST | `/chapters/{id}/images/reorder` | `{message, updated_count}` |
| **Audio** | POST | `/chapters/{id}/audios/upload` | `[{id, filename, duration_seconds, transcription_status}]` (201) |
| | GET | `/chapters/{id}/audios?page=1` | `{items: [...], total}` |
| **OCR** | POST | `/ocr/process` | `{task_id, status, total_images}` (202) |
| | GET | `/ocr/status/{task_id}` | `{task_id, status, progress_percent, images: [...]}` |
| **Transcription** | POST | `/audio/transcribe` | `{task_id, status, total_audios}` (202) |
| | GET | `/transcription/status/{task_id}` | `{task_id, status, progress_percent, audios: [...]}` |
| **Text** | GET | `/images/{id}/text` | `{raw_text_with_formatting, plain_text, detected_language}` |
| | GET | `/audio/{id}/transcript` | `{raw_text_with_formatting, plain_text, duration_seconds}` |
| **Search** | GET | `/search/chapter?chapter_id={id}&text_query=...` | `[{type, image/audio, excerpt}]` |
| **Export** | POST | `/export/folder` | Binary file (docx/txt) |

---

## Configuration

### Environment Variables (.env)

```
BACKEND_URL=http://localhost:8000
STREAMLIT_THEME=light
STREAMLIT_LOGGER_LEVEL=info
```

### Streamlit Config (pyproject.toml)

```toml
[tool.poetry.dependencies]
python = "^3.10"
streamlit = "^1.28"
streamlit-cropper = "^0.2"
httpx = "^0.25"
pillow = "^10"
pdf2image = "^1.16"
librosa = "^0.10"
pydub = "^0.25"
```

---

## Best Practices

1. **Always Include Authorization Header:**
   ```python
   headers = {"Authorization": f"Bearer {st.session_state.auth_token}"}
   ```

2. **Handle 202 Accepted Pattern:**
   - Save task_id immediately
   - Start polling in loop with 2-second intervals
   - Don't block UI during polling

3. **Preserve Formatting:**
   - Use `render_formatted_text()` for all OCR/transcript display
   - Markdown tags: `**bold**`, `*italic*`, `__underline__`, `~~strikethrough~~`, `^superscript^`, `~subscript~`

4. **Error Recovery:**
   - Catch connection errors gracefully
   - Show user-friendly messages
   - Log errors for debugging

5. **Performance:**
   - Cache images locally after download
   - Use pagination (50 items per page)
   - Lazy load chapters/images only when selected

---

This guide covers 100% of your backend API. Implement each section step-by-step, starting with authentication, then books/chapters, then images/audio, then OCR/transcription, and finally search/export.

