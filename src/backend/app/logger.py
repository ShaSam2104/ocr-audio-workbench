"""Logging configuration for OCR Workbench."""
import logging
import logging.handlers
from pathlib import Path
from datetime import datetime, timedelta
import os


def setup_logging(log_dir: str = "logs", retention_days: int = 30) -> logging.Logger:
    """
    Set up daily rotating file handler with auto-cleanup of old logs.

    Args:
        log_dir: Directory to store log files (default: "logs")
        retention_days: Keep logs for this many days (default: 30)

    Returns:
        Configured logger instance
    """
    # Create logs directory if it doesn't exist
    log_path = Path(log_dir)
    log_path.mkdir(exist_ok=True)

    # Clean up old log files
    cleanup_old_logs(log_dir, retention_days)

    # Get or create logger
    logger = logging.getLogger("ocr_workbench")
    logger.setLevel(logging.DEBUG)

    # Remove any existing handlers to avoid duplicates
    logger.handlers.clear()

    # Create daily rotating file handler
    # Format: ocr_workbench_YYYY-MM-DD.log
    log_filename = log_path / f"ocr_workbench_{datetime.now().strftime('%Y-%m-%d')}.log"

    # Daily rotation based on date
    file_handler = logging.handlers.RotatingFileHandler(
        filename=str(log_filename),
        mode="a",
        maxBytes=0,  # No size limit, rotation only by date
        backupCount=0,  # Will manage retention ourselves
    )

    # Create formatter
    formatter = logging.Formatter(
        fmt="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(formatter)

    # Add console handler for INFO and above
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    # Add handlers to logger
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    # Log startup message
    logger.info("=" * 80)
    logger.info("OCR Workbench logging initialized")
    logger.info(f"Log directory: {log_path.resolve()}")
    logger.info(f"Log retention: {retention_days} days")
    logger.info("=" * 80)

    return logger


def cleanup_old_logs(log_dir: str, retention_days: int) -> None:
    """
    Remove log files older than retention_days.

    Args:
        log_dir: Directory containing log files
        retention_days: Keep logs for this many days
    """
    log_path = Path(log_dir)

    if not log_path.exists():
        return

    cutoff_date = datetime.now() - timedelta(days=retention_days)

    for log_file in log_path.glob("ocr_workbench_*.log"):
        try:
            # Extract date from filename: ocr_workbench_YYYY-MM-DD.log
            date_str = log_file.stem.replace("ocr_workbench_", "")
            file_date = datetime.strptime(date_str, "%Y-%m-%d")

            if file_date < cutoff_date:
                log_file.unlink()
                print(f"Deleted old log file: {log_file.name}")
        except (ValueError, OSError) as e:
            print(f"Error processing log file {log_file.name}: {e}")


# Create a module-level logger instance for immediate use
logger = setup_logging()
