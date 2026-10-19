import logging
import logging.handlers
from pathlib import Path

LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
MAX_LOG_BYTES = 1_000_000
LOG_BACKUP_COUNT = 3


def setup_logging(log_file: Path, level: int = logging.INFO) -> None:
    """Log to stderr and to a size-rotated file."""
    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=MAX_LOG_BYTES, backupCount=LOG_BACKUP_COUNT, encoding="utf-8"
    )
    logging.basicConfig(
        level=level,
        format=LOG_FORMAT,
        datefmt=DATE_FORMAT,
        handlers=[logging.StreamHandler(), file_handler],
        force=True,
    )
