import logging
import os
from logging.handlers import RotatingFileHandler

DATA_DIR = os.getenv("DATA_DIR", ".")
LOG_DIR = os.path.join(DATA_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        RotatingFileHandler(
            os.path.join(LOG_DIR, "agencia.log"),
            maxBytes=5 * 1024 * 1024,  # 5 MB
            backupCount=3,
            encoding="utf-8",
        ),
        logging.StreamHandler(),
    ],
)


logging.getLogger("watchfiles").setLevel(logging.WARNING)


def get_logger(name):
    return logging.getLogger(name)
