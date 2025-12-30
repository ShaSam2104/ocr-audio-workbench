"""Background task management for OCR processing."""
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


class ImageStatus(str, Enum):
    """Image processing status enumeration."""
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ImageTaskInfo:
    """Information about a single image in a task."""
    image_id: int
    status: ImageStatus = ImageStatus.QUEUED
    queued_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    processed_at: Optional[datetime] = None
    error: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        result = {
            "image_id": self.image_id,
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
class OCRTask:
    """OCR task information."""
    task_id: str
    status: TaskStatus = TaskStatus.QUEUED
    total_images: int = 0
    images: List[ImageTaskInfo] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None

    @property
    def completed_count(self) -> int:
        """Count of completed images."""
        return sum(1 for img in self.images if img.status == ImageStatus.COMPLETED)

    @property
    def progress_percent(self) -> int:
        """Overall progress percentage."""
        if self.total_images == 0:
            return 0
        return int((self.completed_count / self.total_images) * 100)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "task_id": self.task_id,
            "status": self.status.value,
            "total_images": self.total_images,
            "completed_count": self.completed_count,
            "progress_percent": self.progress_percent,
            "images": [img.to_dict() for img in self.images],
        }


class OCRTaskManager:
    """
    In-memory task manager for OCR processing.
    Tracks status of background OCR jobs and individual images.
    """

    def __init__(self):
        """Initialize task manager."""
        self.tasks: Dict[str, OCRTask] = {}
        logger.info("OCRTaskManager initialized")

    def create_task(self, image_ids: List[int]) -> str:
        """
        Create a new OCR task.
        
        Args:
            image_ids: List of image IDs to process
            
        Returns:
            task_id (UUID string)
        """
        task_id = str(uuid.uuid4())
        
        images = [ImageTaskInfo(image_id=img_id) for img_id in image_ids]
        task = OCRTask(
            task_id=task_id,
            status=TaskStatus.QUEUED,
            total_images=len(image_ids),
            images=images,
        )
        
        self.tasks[task_id] = task
        logger.info(f"OCR task created: {task_id} with {len(image_ids)} images")
        
        return task_id

    def get_task_status(self, task_id: str) -> Optional[OCRTask]:
        """
        Get status of a task.
        
        Args:
            task_id: Task ID
            
        Returns:
            OCRTask or None if not found
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

    def start_image_processing(self, task_id: str, image_id: int) -> bool:
        """
        Mark image as processing.
        
        Args:
            task_id: Task ID
            image_id: Image ID
            
        Returns:
            True if successful
        """
        task = self.tasks.get(task_id)
        if not task:
            return False
        
        for img in task.images:
            if img.image_id == image_id:
                img.status = ImageStatus.PROCESSING
                img.started_at = datetime.utcnow()
                logger.debug(f"Task {task_id}, image {image_id} status: {img.status.value}")
                return True
        
        return False

    def complete_image(self, task_id: str, image_id: int) -> bool:
        """
        Mark image as completed.
        
        Args:
            task_id: Task ID
            image_id: Image ID
            
        Returns:
            True if successful
        """
        task = self.tasks.get(task_id)
        if not task:
            return False
        
        for img in task.images:
            if img.image_id == image_id:
                img.status = ImageStatus.COMPLETED
                img.processed_at = datetime.utcnow()
                logger.debug(f"Task {task_id}, image {image_id} status: {img.status.value}")
                
                # If all images done, mark task as completed
                if task.completed_count == task.total_images:
                    task.status = TaskStatus.COMPLETED
                    task.completed_at = datetime.utcnow()
                    logger.info(f"Task {task_id} completed")
                
                return True
        
        return False

    def fail_image(self, task_id: str, image_id: int, error_msg: str) -> bool:
        """
        Mark image as failed.
        
        Args:
            task_id: Task ID
            image_id: Image ID
            error_msg: Error message
            
        Returns:
            True if successful
        """
        task = self.tasks.get(task_id)
        if not task:
            return False
        
        for img in task.images:
            if img.image_id == image_id:
                img.status = ImageStatus.FAILED
                img.processed_at = datetime.utcnow()
                img.error = error_msg
                logger.warning(f"Task {task_id}, image {image_id} failed: {error_msg}")
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
ocr_task_manager = OCRTaskManager()


def get_ocr_task_manager() -> OCRTaskManager:
    """Get the global OCR task manager."""
    return ocr_task_manager
