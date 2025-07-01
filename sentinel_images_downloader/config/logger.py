from sentinel_images_downloader.config.path import LOGS_DIR
import pathlib
import logging

def setup_logger(file_name: str | pathlib.Path) -> logging.Logger:
    logger = logging.getLogger()
    logger.setLevel(level=logging.INFO)
    logger.propagate = False

    file_name = pathlib.Path(file_name)

    if logger.hasHandlers():
        logger.handlers.clear()

    formatter = logging.Formatter(
        fmt="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(
        filename=LOGS_DIR / file_name, 
        encoding="utf-8",
        mode="w", 
    )
    file_handler.setFormatter(fmt=formatter)
    logger.addHandler(hdlr=file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(fmt=formatter)
    logger.addHandler(hdlr=console_handler)

    return logger