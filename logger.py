import logging
import os
from logging.handlers import RotatingFileHandler

LOG_DIR  = "logs"
LOG_FILE = os.path.join(LOG_DIR, "chatbot.log")

def setup_logger():
    os.makedirs(LOG_DIR, exist_ok=True)

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Rotating file handler — max 5MB, keep 3 backups
    fh = RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)

    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.WARNING)
    ch.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    if not root.handlers:
        root.addHandler(fh)
        root.addHandler(ch)

    return logging.getLogger("chatbot")