"""Background task management for audio transcription processing."""
import uuid
from datetime import datetime
from typing import Optional, Dict, List
from dataclasses import dataclass, field
from enum import Enum
from app.logger import logger


class TaskStatus(str, Enum):
    """Task status enumeration."""
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class AudioStatus(str, Enum):
    """Audio processing status enumeration."""
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class AudioTaskInfo:
    """Information about a single audio in a task."""
    audio_id: int
    status: AudioStatus = AudioStatus.QUEUED
    queued_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    processed_at: Optional[datetime] = None
    error: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        result = {
            "audio_id": self.audio_id,
            "status": self.status.value,
            "queued_at": self.queued_at.isoformat(),
        }
        if self.started_at:
            result["started_at"] = self.started_at.isoformat()
        if self.processed_at:
            result["processed_at"] = self.processed_at.isoformat()
        if self.error:
            result["error"] = self.error
        return result


@dataclass
class AudioTranscriptionTask:
    """Audio transcription task information."""
    task_id: str
    status: TaskStatus = TaskStatus.QUEUED
    total_audios: int = 0
    audios: List[AudioTaskInfo] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None

    @property
    def completed_count(self) -> int:
        """Count of completed audios."""
        return sum(1 for audio in self.audios if audio.status == AudioStatus.COMPLETED)

    @property
    def progress_percent(self) -> int:
        """Overall progress percentage."""
        if self.total_audios == 0:
            return 0
        return int((self.completed_count / self.total_audios) * 100)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "task_id": self.task_id,
            "status": self.status.value,
            "total_audios": self.total_audios,
            "completed_count": self.completed_count,
            "progress_percent": self.progress_percent,
            "audios": [audio.to_dict() for audio in self.audios],
        }


class AudioTranscriptionTaskManager:
    """
    In-memory task manager for audio transcription processing.
    Tracks status of background transcription jobs and individual audios.
    """

    def __init__(self):
        """Initialize task manager."""
        self.tasks: Dict[str, AudioTranscriptionTask] = {}
        logger.info("AudioTranscriptionTaskManager initialized")

    def create_task(self, audio_ids: List[int]) -> str:
        """
        Create a new transcription task.
        
        Args:
            audio_ids: List of audio IDs to process
            
        Returns:
            task_id (UUID string)
        """
        task_id = str(uuid.uuid4())
        
        audios = [AudioTaskInfo(audio_id=audio_id) for audio_id in audio_ids]
        task = AudioTranscriptionTask(
            task_id=task_id,
            status=TaskStatus.QUEUED,
            total_audios=len(audio_ids),
            audios=audios,
        )
        
        self.tasks[task_id] = task
        logger.info(f"Audio transcription task created: {task_id} with {len(audio_ids)} audios")
        
        return task_id

    def get_task_status(self, task_id: str) -> Optional[AudioTranscriptionTask]:
        """
        Get status of a task.
        
        Args:
            task_id: Task ID
            
        Returns:
            AudioTranscriptionTask or None if not found
        """
        return self.tasks.get(task_id)

    def start_processing(self, task_id: str) -> bool:
        """
        Mark task as processing.
        
        Args:
            task_id: Task ID
            
        Returns:
            True if successful, False if task not found
        """
        task = self.tasks.get(task_id)
        if not task:
            return False
        
        task.status = TaskStatus.PROCESSING
        logger.debug(f"Task {task_id} status updated to: {task.status.value}")
        return True

    def start_audio_processing(self, task_id: str, audio_id: int) -> bool:
        """
        Mark audio as processing.
        
        Args:
            task_id: Task ID
            audio_id: Audio ID
            
        Returns:
            True if successful
        """
        task = self.tasks.get(task_id)
        if not task:
            return False
        
        for audio in task.audios:
            if audio.audio_id == audio_id:
                audio.status = AudioStatus.PROCESSING
                audio.started_at = datetime.utcnow()
                logger.debug(f"Task {task_id}, audio {audio_id} status: {audio.status.value}")
                return True
        
        return False

    def complete_audio(self, task_id: str, audio_id: int) -> bool:
        """
        Mark audio as completed.
        
        Args:
            task_id: Task ID
            audio_id: Audio ID
            
        Returns:
            True if successful
        """
        task = self.tasks.get(task_id)
        if not task:
            return False
        
        for audio in task.audios:
            if audio.audio_id == audio_id:
                audio.status = AudioStatus.COMPLETED
                audio.processed_at = datetime.utcnow()
                logger.debug(f"Task {task_id}, audio {audio_id} status: {audio.status.value}")
                
                # If all audios done, mark task as completed
                if task.completed_count == task.total_audios:
                    task.status = TaskStatus.COMPLETED
                    task.completed_at = datetime.utcnow()
                    logger.info(f"Task {task_id} completed")
                
                return True
        
        return False

    def fail_audio(self, task_id: str, audio_id: int, error_msg: str) -> bool:
        """
        Mark audio as failed.
        
        Args:
            task_id: Task ID
            audio_id: Audio ID
            error_msg: Error message
            
        Returns:
            True if successful
        """
        task = self.tasks.get(task_id)
        if not task:
            return False
        
        for audio in task.audios:
            if audio.audio_id == audio_id:
                audio.status = AudioStatus.FAILED
                audio.processed_at = datetime.utcnow()
                audio.error = error_msg
                logger.warning(f"Task {task_id}, audio {audio_id} failed: {error_msg}")
                return True
        
        return False

    def fail_task(self, task_id: str) -> bool:
        """
        Mark entire task as failed.
        
        Args:
            task_id: Task ID
            
        Returns:
            True if successful
        """
        task = self.tasks.get(task_id)
        if not task:
            return False
        
        task.status = TaskStatus.FAILED
        task.completed_at = datetime.utcnow()
        logger.error(f"Task {task_id} marked as failed")
        return True

    def cleanup_old_tasks(self, max_age_hours: int = 24) -> int:
        """
        Clean up completed tasks older than max_age_hours.
        
        Args:
            max_age_hours: Maximum age in hours
            
        Returns:
            Number of tasks removed
        """
        from datetime import timedelta
        
        cutoff_time = datetime.utcnow() - timedelta(hours=max_age_hours)
        to_remove = []
        
        for task_id, task in self.tasks.items():
            if task.completed_at and task.completed_at < cutoff_time:
                to_remove.append(task_id)
        
        for task_id in to_remove:
            del self.tasks[task_id]
            logger.debug(f"Cleaned up old task: {task_id}")
        
        return len(to_remove)


# Global task manager instance
audio_task_manager = AudioTranscriptionTaskManager()


def get_audio_task_manager() -> AudioTranscriptionTaskManager:
    """Get the global audio transcription task manager."""
    return audio_task_manager
