"""Tests for audio upload endpoints."""
import io
import pytest
from fastapi import status


class TestAudioUpload:
    """Test POST /chapters/{chapter_id}/audios/upload endpoint."""

    def test_upload_single_mp3_audio(self, client, auth_headers, db_session):
        """Test uploading a single MP3 audio file."""
        from app.models.hierarchy import Book, Chapter

        # Create book and chapter
        book = Book(name="Test Book")
        db_session.add(book)
        db_session.commit()

        chapter = Chapter(book_id=book.id, name="Test Chapter")
        db_session.add(chapter)
        db_session.commit()

        # Create a fake MP3 file (MP3 header)
        mp3_content = b"ID3" + b"fake mp3 content" * 1000  # Make it bigger so librosa doesn't fail
        files = [("files", ("test.mp3", io.BytesIO(mp3_content), "audio/mpeg"))]

        response = client.post(
            f"/chapters/{chapter.id}/audios/upload",
            files=files,
            headers=auth_headers,
        )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert len(data) == 1
        assert data[0]["filename"] == "test.mp3"
        assert data[0]["chapter_id"] == chapter.id
        assert data[0]["sequence_number"] == 1
        assert data[0]["transcription_status"] == "pending"
        assert data[0]["object_key"].startswith("audio/")
        assert data[0]["file_size"] > 0
        assert data[0]["audio_format"] == "mp3"

    def test_upload_multiple_audio_files(self, client, auth_headers, db_session):
        """Test uploading multiple audio files."""
        from app.models.hierarchy import Book, Chapter

        # Create book and chapter
        book = Book(name="Test Book")
        db_session.add(book)
        db_session.commit()

        chapter = Chapter(book_id=book.id, name="Test Chapter")
        db_session.add(chapter)
        db_session.commit()

        # Create multiple fake audio files
        mp3_content = b"ID3" + b"fake mp3 content" * 1000
        wav_content = b"RIFF" + b"fake wav content" * 1000
        
        files = [
            ("files", ("audio1.mp3", io.BytesIO(mp3_content), "audio/mpeg")),
            ("files", ("audio2.wav", io.BytesIO(wav_content), "audio/wav")),
            ("files", ("audio3.mp3", io.BytesIO(mp3_content), "audio/mpeg")),
        ]

        response = client.post(
            f"/chapters/{chapter.id}/audios/upload",
            files=files,
            headers=auth_headers,
        )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert len(data) == 3
        
        # Verify sequence numbers and formats
        for i, audio in enumerate(data, 1):
            assert audio["sequence_number"] == i
            assert audio["transcription_status"] == "pending"
            assert audio["object_key"].startswith(f"audio/{chapter.id}/")

    def test_upload_wav_audio(self, client, auth_headers, db_session):
        """Test uploading a WAV audio file."""
        from app.models.hierarchy import Book, Chapter

        # Create book and chapter
        book = Book(name="Test Book")
        db_session.add(book)
        db_session.commit()

        chapter = Chapter(book_id=book.id, name="Test Chapter")
        db_session.add(chapter)
        db_session.commit()

        # Create a fake WAV file (WAV header)
        wav_content = b"RIFF" + b"fake wav content" * 1000
        files = [("files", ("test.wav", io.BytesIO(wav_content), "audio/wav"))]

        response = client.post(
            f"/chapters/{chapter.id}/audios/upload",
            files=files,
            headers=auth_headers,
        )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert len(data) == 1
        assert data[0]["filename"] == "test.wav"
        assert data[0]["audio_format"] == "wav"
        assert data[0]["transcription_status"] == "pending"

    def test_upload_m4a_audio(self, client, auth_headers, db_session):
        """Test uploading an M4A audio file."""
        from app.models.hierarchy import Book, Chapter

        # Create book and chapter
        book = Book(name="Test Book")
        db_session.add(book)
        db_session.commit()

        chapter = Chapter(book_id=book.id, name="Test Chapter")
        db_session.add(chapter)
        db_session.commit()

        # Create a fake M4A file
        m4a_content = b"\x00\x00\x00\x20ftypmp42" + b"fake m4a content" * 1000
        files = [("files", ("test.m4a", io.BytesIO(m4a_content), "audio/mp4"))]

        response = client.post(
            f"/chapters/{chapter.id}/audios/upload",
            files=files,
            headers=auth_headers,
        )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data[0]["audio_format"] == "m4a"

    def test_upload_ogg_audio(self, client, auth_headers, db_session):
        """Test uploading an OGG audio file."""
        from app.models.hierarchy import Book, Chapter

        # Create book and chapter
        book = Book(name="Test Book")
        db_session.add(book)
        db_session.commit()

        chapter = Chapter(book_id=book.id, name="Test Chapter")
        db_session.add(chapter)
        db_session.commit()

        # Create a fake OGG file (OGG Vorbis header)
        ogg_content = b"OggS" + b"fake ogg content" * 1000
        files = [("files", ("test.ogg", io.BytesIO(ogg_content), "audio/ogg"))]

        response = client.post(
            f"/chapters/{chapter.id}/audios/upload",
            files=files,
            headers=auth_headers,
        )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data[0]["audio_format"] == "ogg"

    def test_upload_flac_audio(self, client, auth_headers, db_session):
        """Test uploading a FLAC audio file."""
        from app.models.hierarchy import Book, Chapter

        # Create book and chapter
        book = Book(name="Test Book")
        db_session.add(book)
        db_session.commit()

        chapter = Chapter(book_id=book.id, name="Test Chapter")
        db_session.add(chapter)
        db_session.commit()

        # Create a fake FLAC file (FLAC header)
        flac_content = b"fLaC" + b"fake flac content" * 1000
        files = [("files", ("test.flac", io.BytesIO(flac_content), "audio/flac"))]

        response = client.post(
            f"/chapters/{chapter.id}/audios/upload",
            files=files,
            headers=auth_headers,
        )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data[0]["audio_format"] == "flac"

    def test_upload_audio_chapter_not_found(self, client, auth_headers):
        """Test uploading to non-existent chapter."""
        mp3_content = b"ID3" + b"fake mp3 content" * 1000
        files = [("files", ("test.mp3", io.BytesIO(mp3_content), "audio/mpeg"))]

        response = client.post(
            "/chapters/99999/audios/upload",
            files=files,
            headers=auth_headers,
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "Chapter with id 99999 not found" in response.json()["detail"]

    def test_upload_invalid_file_format(self, client, auth_headers, db_session):
        """Test uploading invalid file format (e.g., video)."""
        from app.models.hierarchy import Book, Chapter

        # Create book and chapter
        book = Book(name="Test Book")
        db_session.add(book)
        db_session.commit()

        chapter = Chapter(book_id=book.id, name="Test Chapter")
        db_session.add(chapter)
        db_session.commit()

        # Try to upload a video file
        video_content = b"some video content"
        files = [("files", ("test.mp4", io.BytesIO(video_content), "video/mp4"))]

        response = client.post(
            f"/chapters/{chapter.id}/audios/upload",
            files=files,
            headers=auth_headers,
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Invalid audio format" in response.json()["detail"]

    def test_upload_wrong_mime_type(self, client, auth_headers, db_session):
        """Test uploading file with wrong MIME type."""
        from app.models.hierarchy import Book, Chapter

        # Create book and chapter
        book = Book(name="Test Book")
        db_session.add(book)
        db_session.commit()

        chapter = Chapter(book_id=book.id, name="Test Chapter")
        db_session.add(chapter)
        db_session.commit()

        # Upload MP3 file with text MIME type
        mp3_content = b"ID3" + b"fake mp3 content" * 1000
        files = [("files", ("test.mp3", io.BytesIO(mp3_content), "text/plain"))]

        response = client.post(
            f"/chapters/{chapter.id}/audios/upload",
            files=files,
            headers=auth_headers,
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Invalid audio format" in response.json()["detail"]

    def test_upload_creates_audios_in_db(self, client, auth_headers, db_session):
        """Test that uploaded audios are stored in database."""
        from app.models.hierarchy import Book, Chapter
        from app.models.audio import Audio

        # Create book and chapter
        book = Book(name="Test Book")
        db_session.add(book)
        db_session.commit()

        chapter = Chapter(book_id=book.id, name="Test Chapter")
        db_session.add(chapter)
        db_session.commit()

        mp3_content = b"ID3" + b"fake mp3 content" * 1000
        files = [("files", ("test.mp3", io.BytesIO(mp3_content), "audio/mpeg"))]

        response = client.post(
            f"/chapters/{chapter.id}/audios/upload",
            files=files,
            headers=auth_headers,
        )

        assert response.status_code == status.HTTP_201_CREATED

        # Verify audio is in database
        audios = db_session.query(Audio).filter(Audio.chapter_id == chapter.id).all()
        assert len(audios) == 1
        assert audios[0].filename == "test.mp3"
        assert audios[0].transcription_status == "pending"
        assert audios[0].object_key.startswith("audio/")
        assert audios[0].audio_format == "mp3"

    def test_upload_sequences_correctly(self, client, auth_headers, db_session):
        """Test that sequence numbers are assigned correctly."""
        from app.models.hierarchy import Book, Chapter
        from app.models.audio import Audio

        # Create book and chapter
        book = Book(name="Test Book")
        db_session.add(book)
        db_session.commit()

        chapter = Chapter(book_id=book.id, name="Test Chapter")
        db_session.add(chapter)
        db_session.commit()

        mp3_content = b"ID3" + b"fake mp3 content" * 1000

        # Upload first batch
        files1 = [
            ("files", ("audio1.mp3", io.BytesIO(mp3_content), "audio/mpeg")),
            ("files", ("audio2.mp3", io.BytesIO(mp3_content), "audio/mpeg")),
        ]
        response1 = client.post(
            f"/chapters/{chapter.id}/audios/upload",
            files=files1,
            headers=auth_headers,
        )
        assert response1.status_code == status.HTTP_201_CREATED
        data1 = response1.json()
        assert data1[0]["sequence_number"] == 1
        assert data1[1]["sequence_number"] == 2

        # Upload second batch
        files2 = [
            ("files", ("audio3.mp3", io.BytesIO(mp3_content), "audio/mpeg")),
            ("files", ("audio4.mp3", io.BytesIO(mp3_content), "audio/mpeg")),
        ]
        response2 = client.post(
            f"/chapters/{chapter.id}/audios/upload",
            files=files2,
            headers=auth_headers,
        )
        assert response2.status_code == status.HTTP_201_CREATED
        data2 = response2.json()
        assert data2[0]["sequence_number"] == 3
        assert data2[1]["sequence_number"] == 4

    def test_upload_no_auth(self, client, db_session):
        """Test uploading without authentication."""
        from app.models.hierarchy import Book, Chapter

        # Create book and chapter
        book = Book(name="Test Book")
        db_session.add(book)
        db_session.commit()

        chapter = Chapter(book_id=book.id, name="Test Chapter")
        db_session.add(chapter)
        db_session.commit()

        mp3_content = b"ID3" + b"fake mp3 content" * 1000
        files = [("files", ("test.mp3", io.BytesIO(mp3_content), "audio/mpeg"))]

        response = client.post(
            f"/chapters/{chapter.id}/audios/upload",
            files=files,
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_upload_stores_file_metadata(self, client, auth_headers, db_session):
        """Test that file metadata is stored (size)."""
        from app.models.hierarchy import Book, Chapter

        # Create book and chapter
        book = Book(name="Test Book")
        db_session.add(book)
        db_session.commit()

        chapter = Chapter(book_id=book.id, name="Test Chapter")
        db_session.add(chapter)
        db_session.commit()

        mp3_content = b"ID3" + b"fake mp3 content" * 1000
        files = [("files", ("test.mp3", io.BytesIO(mp3_content), "audio/mpeg"))]

        response = client.post(
            f"/chapters/{chapter.id}/audios/upload",
            files=files,
            headers=auth_headers,
        )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data[0]["file_size"] > 0

    def test_upload_object_key_format(self, client, auth_headers, db_session):
        """Test that object_key follows correct format: audio/{chapter_id}/{audio_id}.{ext}."""
        from app.models.hierarchy import Book, Chapter

        # Create book and chapter
        book = Book(name="Test Book")
        db_session.add(book)
        db_session.commit()

        chapter = Chapter(book_id=book.id, name="Test Chapter")
        db_session.add(chapter)
        db_session.commit()

        mp3_content = b"ID3" + b"fake mp3 content" * 1000
        files = [("files", ("test.mp3", io.BytesIO(mp3_content), "audio/mpeg"))]

        response = client.post(
            f"/chapters/{chapter.id}/audios/upload",
            files=files,
            headers=auth_headers,
        )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        audio_id = data[0]["id"]
        expected_prefix = f"audio/{chapter.id}/{audio_id}."
        assert data[0]["object_key"].startswith(expected_prefix)

    def test_upload_transcription_status_pending(self, client, auth_headers, db_session):
        """Test that uploaded audio has transcription_status=pending."""
        from app.models.hierarchy import Book, Chapter

        # Create book and chapter
        book = Book(name="Test Book")
        db_session.add(book)
        db_session.commit()

        chapter = Chapter(book_id=book.id, name="Test Chapter")
        db_session.add(chapter)
        db_session.commit()

        mp3_content = b"ID3" + b"fake mp3 content" * 1000
        files = [("files", ("test.mp3", io.BytesIO(mp3_content), "audio/mpeg"))]

        response = client.post(
            f"/chapters/{chapter.id}/audios/upload",
            files=files,
            headers=auth_headers,
        )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        # transcription_status should be "pending", NOT "processing"
        assert data[0]["transcription_status"] == "pending"
