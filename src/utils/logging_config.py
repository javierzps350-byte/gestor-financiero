import logging
from src.config import LOG_DIR


def configure_logging():
    logging.basicConfig(
        filename=LOG_DIR / "gestor_financiero.log",
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        encoding="utf-8",
    )
