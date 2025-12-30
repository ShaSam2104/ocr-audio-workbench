"""Audio handling service."""
import io
from pathlib import Path


class AudioHandler:
    """Handle audio operations."""

    SUPPORTED_FORMATS = {"mp3", "wav", "m4a", "ogg", "flac"}

    @staticmethod
    def get_audio_duration(file_data: bytes) -> float:
        """Get duration of audio file in seconds."""
        try:
            import librosa
            audio_data, sr = librosa.load(io.BytesIO(file_data), sr=None)
            duration = librosa.get_duration(y=audio_data, sr=sr)
            return duration
        except Exception as e:
            print(f"Error getting audio duration: {e}")
            return 0.0

    @staticmethod
    def is_supported_format(filename: str) -> bool:
        """Check if file format is supported."""
        ext = Path(filename).suffix.lower().strip(".")
        return ext in AudioHandler.SUPPORTED_FORMATS

    @staticmethod
    def get_file_size(file_data: bytes) -> int:
        """Get size of audio file in bytes."""
        return len(file_data)

    @staticmethod
    def convert_to_wav(file_data: bytes) -> bytes:
        """Convert audio file to WAV format."""
        try:
            import librosa
            import soundfile as sf

            audio_data, sr = librosa.load(io.BytesIO(file_data), sr=None)
            
            # Write to bytes buffer
            wav_buffer = io.BytesIO()
            sf.write(wav_buffer, audio_data, sr, format="WAV")
            wav_buffer.seek(0)
            
            return wav_buffer.getvalue()
        except Exception as e:
            print(f"Error converting to WAV: {e}")
            return file_data
